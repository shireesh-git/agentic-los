"""
Agent evaluation & debug harness (development only).

Runs individual pipeline agents — the real agent classes from src/agents — on a
cached post-ingestion snapshot of a case, and reports for each run: timing,
execution mode, LLM calls (prompt, model, response; never keys), inputs,
raw and structured output, evidence, warnings/errors, output schema, and which
output keys downstream agents actually read (observed at runtime).

Caching: the existing per-file OCR/extraction cache (storage/cache/extractions)
already avoids re-OCR; this adds a post-ingestion *case snapshot* so the
data_ingestion agent itself (DMS fetch, report OCR, extraction, verification)
runs once per case and is reused until the company record, its documents or the
ingestion code change. Snapshots live in storage/cache/agent_snapshots/
(git-ignored) and are pickles read only by this tool.

The production pipeline does not import this module.
"""

from __future__ import annotations

import contextvars
import copy
import hashlib
import json
import logging
import pickle
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from src.devtools.agent_contracts import (
    AGENT_ORDER, CONTRACTS, NARRATIVE_OWN_ANALYSIS, SOURCE_FILES,
)

log = logging.getLogger(__name__)

HARNESS_VERSION = "agent_harness/1.0"
NARRATIVE_MODES = ("plan", "template", "llm", "full")


def _paths():
    from src.core.runtime_paths import CACHE_ROOT, DOCUMENTS_ROOT, OUTPUT_ROOT, PROJECT_ROOT
    return {"snapshots": CACHE_ROOT / "agent_snapshots", "results": OUTPUT_ROOT / "agent_harness",
            "documents": DOCUMENTS_ROOT, "project": PROJECT_ROOT}


def _now() -> str:
    return datetime.now().isoformat(timespec="milliseconds")


def code_version(agent: str) -> str:
    """Short hash of the source files behind an agent — changes whenever its behaviour can."""
    root = _paths()["project"]
    h = hashlib.sha1()
    for rel in SOURCE_FILES.get(agent, []):
        path = root / rel
        h.update(rel.encode())
        h.update(path.read_bytes() if path.exists() else b"missing")
    return h.hexdigest()[:10]


# ─── Observing reads of agent results ────────────────────────────────────────

_reader: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("agent_reader", default=None)


class TrackedResult(dict):
    """An agent's result dict that records which other agent reads which key."""

    def __init__(self, data: dict, owner: str, reads: dict):
        super().__init__(data)
        self._owner, self._reads = owner, reads

    def _note(self, key):
        reader = _reader.get()
        if reader and reader != self._owner:
            self._reads.setdefault(self._owner, {}).setdefault(key, set()).add(reader)

    def __getitem__(self, key):
        self._note(key)
        return super().__getitem__(key)

    def get(self, key, default=None):
        if key in self:
            self._note(key)
        return super().get(key, default)


# ─── Recording LLM calls ─────────────────────────────────────────────────────

class RecordingLLM:
    """Wraps an LLM provider and records every generate() call. Credentials are never recorded."""

    def __init__(self, inner, calls: list | None = None):
        self._inner = inner
        self.calls = calls if calls is not None else []

    def __getattr__(self, name):
        return getattr(self._inner, name)

    @property
    def identity(self) -> dict:
        inner = self._inner
        return {"provider": getattr(inner, "name", type(inner).__name__),
                "model": getattr(inner, getattr(inner, "_model_attr", "model"), None)}

    def with_model(self, model):
        return RecordingLLM(self._inner.with_model(model), self.calls)

    def generate(self, prompt: str, system_prompt: str = "", temperature: float = 0.1, max_tokens: int = 4000) -> str:
        started = time.perf_counter()
        record = {**self.identity, "temperature": temperature, "max_tokens": max_tokens,
                  "system_prompt": system_prompt, "prompt": prompt, "prompt_chars": len(prompt) + len(system_prompt),
                  "started_at": _now()}
        try:
            text = self._inner.generate(prompt=prompt, system_prompt=system_prompt, temperature=temperature,
                                        max_tokens=max_tokens)
            record.update(response=text, response_chars=len(text or ""), error=None)
            return text
        except Exception as e:
            record.update(response=None, response_chars=0, error=str(e))
            raise
        finally:
            record["duration_ms"] = round((time.perf_counter() - started) * 1000, 1)
            self.calls.append(record)


# ─── Loading a case and its snapshot ─────────────────────────────────────────

def load_company(entity_id: str, loader: Callable[[str], dict] | None = None) -> dict:
    """The company record as the app holds it (seed catalog + persisted records). No enrichment calls."""
    if loader:
        company = loader(entity_id)
    else:
        from src.data.company_catalog import seed_company_store
        from src.services.persistence import persistence
        store = seed_company_store()
        store.update(persistence.load_companies())
        company = store.get(entity_id)
    if not company:
        raise ValueError(f"Company {entity_id} not found")
    if not company.get("financials"):
        raise ValueError(f"Company {entity_id} has no financial statements yet — run it once in the app first")
    return company


def _fingerprint(entity_id: str, company: dict) -> str:
    from src.services.persistence import _plain
    h = hashlib.sha256()
    h.update(json.dumps(_plain(company), sort_keys=True, default=str).encode())
    docs = _paths()["documents"] / entity_id
    if docs.exists():
        for f in sorted(p for p in docs.rglob("*") if p.is_file() and p.name != "metadata.json"):
            st = f.stat()
            h.update(f"{f.relative_to(docs)}|{st.st_size}|{st.st_mtime_ns}".encode())
    h.update(code_version("data_ingestion").encode())
    return h.hexdigest()[:16]


def snapshot_path(entity_id: str) -> Path:
    return _paths()["snapshots"] / f"{entity_id}.pkl"


def get_snapshot(entity_id: str, company: dict, refresh: bool = False) -> dict:
    """Post-ingestion case snapshot: reused while the company, its documents and the ingestion code are unchanged."""
    from src.agents.ingestion_agent import DataIngestionAgent

    path = snapshot_path(entity_id)
    fingerprint = _fingerprint(entity_id, company)
    stale_reason = "refresh requested" if refresh else None
    if path.exists() and not refresh:
        with path.open("rb") as fh:
            snap = pickle.load(fh)          # dev-only file written by this tool
        if snap["meta"]["fingerprint"] == fingerprint:
            snap["meta"]["source"] = "cache"
            return snap
        stale_reason = "company record, documents or ingestion code changed"

    messages: list[str] = []
    ctx = {"company_data": copy.deepcopy(company), "results": {}, "_stores": {"extraction": {}, "etb": {}},
           "_on_progress": lambda e: messages.append(e.get("message", "")) if e.get("type") == "info" else None}
    result = DataIngestionAgent().execute(ctx)
    if result.status != "completed":
        raise RuntimeError(f"data_ingestion failed for {entity_id}: {result.error}")
    snap = {
        "company_data": ctx["company_data"],
        "ingestion": {"data": result.data, "duration_ms": result.duration_ms, "diagnostics": result.diagnostics,
                      "started_at": result.started_at, "completed_at": result.completed_at, "messages": messages},
        "meta": {"entity_id": entity_id, "fingerprint": fingerprint, "created_at": _now(),
                 "harness": HARNESS_VERSION, "path": str(path), "stale_reason": stale_reason},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        pickle.dump(snap, fh, protocol=pickle.HIGHEST_PROTOCOL)
    snap["meta"]["source"] = "fresh"
    return snap


def snapshot_status(entity_ids: list[str]) -> list[dict]:
    rows = []
    for eid in entity_ids:
        path = snapshot_path(eid)
        if not path.exists():
            rows.append({"entity_id": eid, "snapshot": "none"})
            continue
        with path.open("rb") as fh:
            meta = pickle.load(fh)["meta"]
        rows.append({"entity_id": eid, "snapshot": str(path), "created_at": meta["created_at"],
                     "fingerprint": meta["fingerprint"]})
    return rows


# ─── Describing outputs ──────────────────────────────────────────────────────

def _jsonable(obj):
    from src.application.serialization import to_jsonable
    return to_jsonable(obj)


def _schema(value) -> str:
    if isinstance(value, list):
        inner = type(value[0]).__name__ if value else "empty"
        return f"list[{inner}] ({len(value)})"
    if isinstance(value, dict):
        return f"dict ({len(value)} keys)"
    return type(value).__name__


def _structured(data) -> dict:
    from src.agents.base_agent import _meaningful
    if not isinstance(data, dict):
        return {}
    return {k: {"type": _schema(v), "empty": not _meaningful(v)} for k, v in data.items()}


def _input_summary(name: str, ctx: dict) -> dict:
    cd, r = ctx["company_data"], ctx["results"]
    fin = cd.get("financials") or {}
    latest = fin[sorted(fin)[-1]] if fin else None
    ing = r.get("data_ingestion") or {}
    base = {"case_type": getattr(cd["facility"].case_type, "value", None),
            "financial_periods": sorted(fin), "sector": cd["borrower"].sector.value}
    extraction = cd.get("extraction") or {}
    if name == "data_ingestion":
        ext = cd.get("external_data") or {}
        return {**base, "external_data_sources": sorted(k for k, v in ext.items() if v),
                "documents_extracted": extraction.get("document_count", len(extraction.get("documents") or []))}
    if name == "pep_screening":
        return {"directors": len(cd.get("directors") or [])}
    if name == "financial_analysis":
        return {**base, "line_items_latest": len(getattr(latest, "line_items", {}) or {}),
                "statement_sources": {p: fin[p].source for p in sorted(fin)}}
    if name == "validation":
        return {**base, "bureau_payload": bool(dict.get(ing, "bureau_data")),
                "gst_payload": bool(dict.get(ing, "gst_data")), "provisional": cd.get("provisional") is not None,
                "exchange_filing": cd.get("exchange_filing") is not None,
                "extraction_documents": extraction.get("document_count", 0),
                "conduct_records": len(cd.get("conduct") or []), "covenants": len(cd.get("covenants") or [])}
    if name == "benchmark":
        return {**base, "subsector": cd["borrower"].subsector}
    if name == "policy":
        val, fa, bm = (dict.get(r.get(k) or {}, f) for k, f in
                       (("validation", "exceptions"), ("financial_analysis", "latest_ratios"),
                        ("benchmark", "latest_benchmarks")))
        return {"validation_exceptions": len(val or []), "latest_ratios": len(fa or []),
                "latest_benchmarks": len(bm or []), "bureau_payload": bool(dict.get(ing, "bureau_data")),
                "collateral_items": len(cd.get("collateral") or [])}
    if name == "narrative":
        return {"analytical_results_available": [k for k in ("financial_analysis", "validation", "benchmark",
                                                              "policy", "pep_screening") if k in r],
                "company_data_keys": len(cd)}
    return base


# ─── Running agents ──────────────────────────────────────────────────────────

def _agents():
    from src.agents.pipeline import default_agents
    return {a.name: a for a in default_agents(llm_provider=None)}


def _plan_narrative(ctx: dict, mode: str, sections: list[str] | None, llm) -> tuple[dict, dict, list]:
    """Narrative without the full CAM: build the fact pack and every section prompt; optionally
    send selected sections to the LLM. Returns (output, diagnostics, llm calls)."""
    from src.agents.narrative_agent import NarrativeAgent
    from src.engines.cam_fact_builder import build_cam_fact_pack
    from src.engines.cam_llm_renderer import (
        CAM_SECTIONS, PROMPT_VERSION, SYSTEM_PROMPT, _section_prompt, _should_render_section, clean_section_output,
    )
    from src.services.observation_narrator import unsupported_figures

    pep = ctx["results"].get("pep_screening") or {}
    started = time.perf_counter()
    fact_pack = build_cam_fact_pack(ctx["company_data"], assessment=NarrativeAgent._assessment(ctx),
                                    pep_result=pep.get("pep_result"),
                                    financial_analysis=ctx["results"]["financial_analysis"])
    fact_pack_ms = round((time.perf_counter() - started) * 1000, 1)
    plan, calls = [], []
    recorder = RecordingLLM(llm, calls) if llm is not None else None
    for section in CAM_SECTIONS:
        sid = section["id"]
        if section.get("skip_llm"):
            plan.append({"section": sid, "title": section["title"], "kind": "template (structural)"})
            continue
        if not _should_render_section(section, fact_pack):
            plan.append({"section": sid, "title": section["title"], "kind": "skipped"})
            continue
        prompt, data_json = _section_prompt(section, fact_pack)
        keys = section.get("data_keys", [])
        entry = {"section": sid, "title": section["title"], "kind": "llm", "data_keys": keys,
                 "empty_data_keys": [k for k in keys if not fact_pack.get(k)],
                 "prompt_chars": len(prompt) + len(SYSTEM_PROMPT), "data_chars": len(data_json),
                 "max_tokens": section.get("max_tokens"), "prompt": prompt,
                 "mock_inputs": [k for k in keys if k in ("web_crawl_news", "social_media_analysis",
                                                          "social_media_cam_summary") and fact_pack.get(k)]}
        if mode == "llm" and recorder is not None and sections and sid in sections:
            t0 = time.perf_counter()
            text = clean_section_output(recorder.generate(prompt=prompt, system_prompt=SYSTEM_PROMPT,
                                                          temperature=0.1,
                                                          max_tokens=int(section.get("max_tokens") or 1500)))
            entry.update(generated_chars=len(text), generated_ms=round((time.perf_counter() - t0) * 1000, 1),
                         unsupported_figures=unsupported_figures(text, data_json), text=text)
        plan.append(entry)
    diag = {"execution_mode": "llm (selected sections)" if calls else "plan (no LLM)", "llm_invoked": bool(calls),
            "llm_calls": len(calls), "fact_pack_ms": fact_pack_ms, "prompt_version": PROMPT_VERSION}
    return {"fact_pack": fact_pack, "section_plan": plan, "cam_text": None}, diag, calls


def run_case(entity_id: str, agents: str | list[str] = "all", stop_after: str | None = None,
             narrative_mode: str = "plan", sections: list[str] | None = None, refresh_snapshot: bool = False,
             observe_downstream: bool = True, loader: Callable | None = None,
             llm_factory: Callable | None = None, use_checkpoints: bool = True) -> dict:
    """Run agents for one case from its snapshot; return a report per requested agent."""
    from src.agents.base_agent import AgentResult

    targets = list(AGENT_ORDER) if agents in ("all", ["all"]) else ([agents] if isinstance(agents, str) else agents)
    for name in targets + ([stop_after] if stop_after else []):
        if name not in AGENT_ORDER:
            raise ValueError(f"Unknown agent '{name}'. Choose from: {', '.join(AGENT_ORDER)}")
    if narrative_mode not in NARRATIVE_MODES:
        raise ValueError(f"narrative_mode must be one of {NARRATIVE_MODES}")
    last = stop_after or (AGENT_ORDER[-1] if observe_downstream else max(targets, key=AGENT_ORDER.index))
    order = AGENT_ORDER[:AGENT_ORDER.index(last) + 1]

    company = load_company(entity_id, loader)
    snap = get_snapshot(entity_id, company, refresh_snapshot)
    ctx = {"company_data": copy.deepcopy(snap["company_data"]), "results": {}}
    reads: dict = {}
    traces: dict[str, dict] = {}
    instances = _agents()

    def llm_provider():
        if llm_factory:
            return llm_factory()
        from src.core.config_manager import config
        from src.core.llm_provider import create_llm_provider
        return create_llm_provider(config.get_active_llm_provider())

    for name in order:
        trace = {"agent": name, "case_id": entity_id, "llm_calls": [], "input_summary": _input_summary(name, ctx)}
        token = _reader.set(name)
        try:
            if name == "data_ingestion":
                ing = snap["ingestion"]
                cached = snap["meta"]["source"] == "cache"
                result = AgentResult(name, "completed", data=copy.deepcopy(ing["data"]),
                                     started_at=ing["started_at"], completed_at=ing["completed_at"],
                                     duration_ms=ing["duration_ms"],
                                     diagnostics={**ing["diagnostics"],
                                                  "execution_mode": "cached snapshot" if cached
                                                  else ing["diagnostics"].get("execution_mode")})
                trace["messages"] = ing.get("messages", [])
            elif name == "narrative" and narrative_mode in ("plan", "llm"):
                start, clock = datetime.now(), time.perf_counter()
                llm = llm_provider() if narrative_mode == "llm" else None
                try:
                    data, diag, calls = _plan_narrative(ctx, narrative_mode, sections, llm)
                    status, error = "completed", None
                except Exception as e:
                    data, diag, calls, status, error = None, {"execution_mode": "failed"}, [], "failed", str(e)
                end = datetime.now()
                result = AgentResult(name, status, data=data, error=error, started_at=start.isoformat(),
                                     completed_at=end.isoformat(),
                                     duration_ms=round((time.perf_counter() - clock) * 1000, 3), diagnostics=diag)
                trace["llm_calls"] = calls
            else:
                agent = instances[name]
                recorder = None
                if name == "narrative":
                    from src.agents.narrative_agent import NarrativeAgent
                    if narrative_mode == "full":
                        recorder = RecordingLLM(llm_provider())
                        factory = None
                        if use_checkpoints:
                            from functools import partial
                            from src.services.cam_checkpoints import PersistentSectionCheckpoints
                            from src.services.persistence import persistence
                            factory = partial(PersistentSectionCheckpoints, persistence)
                        agent = NarrativeAgent(llm_provider=recorder, checkpoint_factory=factory)
                    else:
                        agent = NarrativeAgent(llm_provider=None)       # template mode
                missing = [d for d in agent.requires if d not in ctx["results"]]
                if missing:
                    result = AgentResult(name, "failed", error=f"Missing results from: {', '.join(missing)}",
                                         diagnostics={"execution_mode": "skipped", "llm_invoked": False})
                else:
                    result = agent.execute(ctx)
                if recorder is not None:
                    trace["llm_calls"] = recorder.calls
        finally:
            _reader.reset(token)
        trace["result"] = result
        traces[name] = trace
        if result.status == "completed" and result.data is not None:
            ctx["results"][name] = TrackedResult(result.data, name, reads) if isinstance(result.data, dict) \
                else result.data

    reports = [_report(traces[t], ctx, reads, order, snap, narrative_mode)
               for t in targets if t in traces]
    return {"case_id": entity_id, "harness": HARNESS_VERSION, "generated_at": _now(),
            "snapshot": {k: v for k, v in snap["meta"].items()}, "executed": order, "reports": reports}


# ─── Evaluation ──────────────────────────────────────────────────────────────

def _check(name: str, status: str, detail: str) -> dict:
    return {"check": name, "status": status, "detail": detail}


def _evaluate(name: str, data: dict, ctx: dict, extra: dict) -> list[dict]:
    """Checks against the agent's actual contract (agent_contracts.CONTRACTS)."""
    cd = ctx["company_data"]
    checks: list[dict] = []
    if name == "data_ingestion":
        periods = sorted(cd.get("financials") or {})
        checks.append(_check("Financial statements available", "pass" if len(periods) >= 2 else "fail",
                             f"{len(periods)} period(s): {', '.join(periods)}"))
        ext = cd.get("extraction") or {}
        n_docs = ext.get("document_count", len(ext.get("documents") or []))
        checks.append(_check("Documents extracted", "pass" if n_docs and not ext.get("warning") else "warn",
                             f"{n_docs} document(s): {', '.join((ext.get('selected_documents') or {}).values())}"
                             + (f"; extraction aborted: {ext['warning']}" if ext.get("warning") else "")))
        for key in ("bureau_data", "gst_data"):
            checks.append(_check(f"{key} available for validation", "pass" if data.get(key) else "warn",
                                 "present" if data.get(key) else "empty — dependent cross-source checks cannot run"))
        placeholders = [k for k in ("web_crawl_news", "swot_signals", "social_media") if k in data]
        checks.append(_check("Placeholder outputs", "warn",
                             f"{', '.join(placeholders)} are returned as hard-coded empty values"))
    elif name == "pep_screening":
        n = data.get("directors_screened", 0)
        checks.append(_check("Directors screened", "pass" if n else "warn", f"{n} director(s)"))
        res = data.get("pep_result")
        checks.append(_check("Screening result", "pass" if res is not None else "fail",
                             f"status {getattr(res, 'status', '?')}, {len(getattr(res, 'pep_hits', []) or [])} hit(s), "
                             f"overall risk {getattr(res, 'overall_risk', '?')}"))
        from src.services.pep_service import _PEP_DATABASE
        checks.append(_check("Screening source", "warn",
                             f"in-code list of {len(_PEP_DATABASE)} PEP entries plus a name list; no external service"))
        checks.append(_check("Placeholder outputs", "warn",
                             "adverse_media_articles, adverse_headlines, social_controversy_index are constants"))
    elif name == "financial_analysis":
        from src.engines.ratio_engine import ALL_RATIO_FUNCTIONS
        latest = data.get("latest_ratios") or []
        computed = [r for r in latest if r.value is not None]
        missing = [r.ratio_name for r in latest if r.value is None]
        checks.append(_check("Ratios computed (latest period)",
                             "pass" if len(computed) == len(ALL_RATIO_FUNCTIONS) else "warn",
                             f"{len(computed)}/{len(ALL_RATIO_FUNCTIONS)}"
                             + (f"; not computed: {', '.join(missing)}" if missing else "")))
        mp = data.get("multi_period_ratios") or {}
        checks.append(_check("Periods analysed", "pass" if len(mp) >= 2 else "warn", ", ".join(sorted(mp))))
        key = {r.ratio_name: r.value for r in latest}
        core = ["dscr", "interest_coverage_ratio", "debt_to_equity", "debt_to_ebitda", "current_ratio",
                "ebitda_margin", "debtor_days", "working_capital_cycle", "ocf_to_debt"]
        absent = [k for k in core if key.get(k) is None]
        checks.append(_check("Core credit ratios", "pass" if not absent else "warn",
                             "all present" if not absent else f"missing: {', '.join(absent)}"))
        checks.append(_check("Trend / growth / commentary", "info",
                             "not produced by this agent (ratios only, by design)"))
    elif name == "validation":
        exc = data.get("exceptions") or []
        by = {}
        for e in exc:
            by[e.severity.value] = by.get(e.severity.value, 0) + 1
        checks.append(_check("Exceptions raised", "pass", f"{len(exc)} {by}" if exc else "none"))
        with_ref = sum(1 for e in exc if e.source_doc_ref)
        checks.append(_check("Exceptions cite a source", "pass" if with_ref == len(exc) else "warn",
                             f"{with_ref}/{len(exc)}"))
        ing = ctx["results"].get("data_ingestion") or {}
        skipped = [n for n, ok in (("debt vs bureau / DPD", dict.get(ing, "bureau_data")),
                                   ("revenue vs GST", dict.get(ing, "gst_data")),
                                   ("revenue vs exchange filing", cd.get("provisional") and cd.get("exchange_filing")),
                                   ("extracted revenue cross-check", cd.get("extraction")))
                   if not ok]
        checks.append(_check("Cross-source checks that could run", "pass" if not skipped else "warn",
                             "all" if not skipped else f"skipped (no input): {', '.join(skipped)}"))
        inv = cd.get("document_inventory")
        checks.append(_check("NTB document checks", "pass" if inv else "warn",
                             (f"inventory from {inv['source']}: KYC {inv['has_kyc']}, board resolution "
                              f"{inv['has_board_resolution']}, collateral documents {inv['has_collateral_docs']}")
                             if inv else "no document inventory — checklist cannot be evaluated"))
    elif name == "benchmark":
        latest = data.get("latest_benchmarks") or []
        sector = cd["borrower"].sector.value
        from src.engines.benchmark_engine import SECTOR_BENCHMARKS
        has_table = sector in SECTOR_BENCHMARKS
        # No peer table for the sector is a data gap (warn), not a malfunction; peers from another sector are never used.
        checks.append(_check("Sector peer table", "pass" if latest else ("fail" if has_table else "warn"),
                             f"{len(latest)} metric(s) benchmarked for '{sector}'" if latest
                             else (f"peer table for '{sector}' exists but nothing was benchmarked" if has_table
                                   else f"no peer table for '{sector}' — benchmarking not available (no sourced peer data)")))
        worse = [b.metric for b in latest if b.status.value == "worse_than_peer"]
        checks.append(_check("Metrics worse than peers", "info", ", ".join(worse) or "none"))
        fa_reads = (extra.get("reads") or {}).get("financial_analysis") or {}
        reused = "benchmark" in fa_reads.get("multi_period_ratios", set())
        checks.append(_check("Uses financial_analysis output", "pass" if reused else "warn",
                             "yes — financial_analysis.multi_period_ratios" if reused
                             else "no — recomputes every ratio for every period itself"))
    elif name == "policy":
        tier1 = data.get("tier1_decisions") or []
        rs, rec = data.get("risk_score"), data.get("recommendation")
        checks.append(_check("Hard rules evaluated", "pass" if tier1 else "fail",
                             f"{len(tier1)} rule(s), {sum(d.result == 'fail' for d in tier1)} failed, "
                             f"{sum(d.result == 'not_verified' for d in tier1)} not verified"))
        checks.append(_check("Risk score", "pass" if rs else "fail",
                             f"composite {getattr(rs, 'composite_score', '?')} grade {getattr(rs, 'risk_grade', '?')} "
                             f"(financial {getattr(rs, 'financial_score', '?')}, conduct {getattr(rs, 'conduct_score', '?')}, "
                             f"governance {getattr(rs, 'governance_score', '?')}, market {getattr(rs, 'market_score', '?')})"))
        checks.append(_check("Recommendation", "pass" if rec else "fail",
                             f"{getattr(getattr(rec, 'recommendation', None), 'value', '?')} — "
                             f"{getattr(rec, 'rationale', '')[:120]}"))
        evidence = {d.rule_code: d for d in tier1 if d.rule_code in ("HR_COMPANY_ACTIVE", "HR_KYC_COMPLETE")}
        unverified = [code for code, d in evidence.items() if d.result == "not_verified"]
        checks.append(_check("Evidence-based hard rules", "warn" if unverified else "pass",
                             "; ".join(f"{code} {d.result}: {d.details}" for code, d in evidence.items()) or "none"))
        bm = (ctx["results"].get("benchmark") or {})
        if not dict.get(bm, "latest_benchmarks"):
            checks.append(_check("Benchmark input", "warn", "no peer benchmarks — financial score is unbenchmarked"))
    elif name == "narrative":
        checks += _narrative_checks(data, ctx, extra)
    return checks


def _narrative_checks(data: dict, ctx: dict, extra: dict) -> list[dict]:
    """Does the narrative consume the analytical agents, or redo their work?"""
    checks: list[dict] = []
    fp = data.get("fact_pack") or {}
    r = {k: dict(v) if isinstance(v, dict) else v for k, v in ctx["results"].items()}
    fa = r.get("financial_analysis") or {}
    mp = fa.get("multi_period_ratios") or {}
    ra = fp.get("ratio_analysis") or {}
    diffs = [f"{p}.{x.ratio_name}" for p, ratios in mp.items() for x in ratios
             if (ra.get(p) or {}).get(x.ratio_name, {}).get("value") != x.value]
    fa_reads = (extra.get("reads") or {}).get("financial_analysis") or {}
    consumed = "narrative" in fa_reads.get("multi_period_ratios", set())
    checks.append(_check("ratio_analysis from financial_analysis", "pass" if consumed and not diffs else "warn",
                         ("consumed (financial_analysis.multi_period_ratios)" if consumed else
                          "NOT read from financial_analysis — recomputed in the narrative step")
                         + ("; values identical" if not diffs else f"; {len(diffs)} value(s) differ: {diffs[:5]}")))
    growth_fp = (fp.get("financial_summary") or {}).get("growth_by_period")
    growth_fa = (fa.get("growth_metrics") or {}).get("by_period")
    checks.append(_check("Growth figures from financial_analysis",
                         "pass" if growth_fp and growth_fp == growth_fa and "growth_metrics" in fa_reads else "warn",
                         "financial_summary.growth_by_period = financial_analysis.growth_metrics"
                         if growth_fp == growth_fa else "growth not supplied by financial_analysis"))
    bm = r.get("benchmark") or {}
    same_bm = len((fp.get("benchmark_summary") or {}).get("benchmarks") or []) == len(bm.get("latest_benchmarks") or [])
    checks.append(_check("benchmark_summary from benchmark agent", "pass" if same_bm else "warn",
                         "consumed (benchmark.view)" if same_bm else "row count differs from the agent's output"))
    val = r.get("validation") or {}
    codes_fp = [e.get("code") for e in fp.get("validation_exceptions") or []]
    codes_ag = [e.exception_code for e in val.get("exceptions") or []]
    checks.append(_check("validation_exceptions from validation agent", "pass" if codes_fp == codes_ag else "warn",
                         f"{len(codes_fp)} exception(s); {'identical' if codes_fp == codes_ag else 'differs'}"))
    pol = r.get("policy") or {}
    score_fp = ((fp.get("policy_decisions") or {}).get("tier2_risk_scores") or {}).get("composite_score")
    score_ag = getattr(pol.get("risk_score"), "composite_score", None)
    checks.append(_check("policy_decisions from policy agent", "pass" if score_fp == score_ag else "warn",
                         f"composite {score_fp} vs agent {score_ag}"))
    pep = r.get("pep_screening") or {}
    checks.append(_check("pep_screening from PEP agent", "pass" if pep.get("pep_result") is not None else "warn",
                         "consumed" if pep.get("pep_result") is not None else "re-screened inside the narrative"))
    own = {k: v for k, v in NARRATIVE_OWN_ANALYSIS.items() if fp.get(k)}
    checks.append(_check("Deterministic sections built in the narrative step", "info",
                         f"{len(own)} (no duplicate agent output exists): {', '.join(own)}"))
    provenance = fp.get("data_provenance") or {}
    news = fp.get("web_crawl_news") or {}
    fabricated = bool(news.get("articles")) and not news.get("verified")
    social = fp.get("social_media_analysis") or {}
    unlabeled_social = bool(social) and "data_provenance" not in social
    checks.append(_check("No fabricated external intelligence", "fail" if fabricated or unlabeled_social else "pass",
                         "unverified news articles in the fact pack" if fabricated else
                         "social-media data without a provenance label" if unlabeled_social else
                         "news: " + ("verified feed" if news.get("verified") else "not available") + "; social media: "
                         + ("labelled synthetic demo" if social else "not available")))
    by_class: dict = {}
    for key, p in provenance.items():
        by_class.setdefault(p["class"], []).append(key)
    checks.append(_check("Data provenance labelled", "pass" if provenance else "warn",
                         "; ".join(f"{cls}: {len(keys)}" for cls, keys in sorted(by_class.items()))
                         + (f" — synthetic demo: {', '.join(by_class['synthetic_demo'])}"
                            if by_class.get("synthetic_demo") else "")))
    asks = _prompts_asking_to_compute()
    checks.append(_check("Prompts asking the LLM to compute", "warn" if asks else "pass",
                         "; ".join(f"{s}: '{t}'" for s, t in asks) if asks else "none found"))
    plan = data.get("section_plan") or []
    llm_sections = [p for p in plan if p.get("kind") == "llm"]
    if llm_sections:
        total = sum(p.get("prompt_chars", 0) for p in llm_sections)
        empty = [f"{p['section']}({', '.join(p['empty_data_keys'])})" for p in llm_sections if p.get("empty_data_keys")]
        checks.append(_check("LLM sections planned", "info",
                             f"{len(llm_sections)} section(s), {total:,} prompt characters in total"))
        if empty:
            checks.append(_check("Sections given empty data", "warn", "; ".join(empty)))
        generated = [p for p in llm_sections if "text" in p]
        for p in generated:
            bad = p.get("unsupported_figures") or []
            checks.append(_check(f"Section {p['section']} figures", "pass" if not bad else "warn",
                                 f"{p['generated_chars']} chars in {p['generated_ms']} ms; "
                                 + ("all figures found in its data" if not bad else f"not in its data: {bad[:8]}")))
    if extra.get("fact_pack_ms") is not None:
        checks.append(_check("Fact-pack build time", "info", f"{extra['fact_pack_ms']} ms"))
    return checks


def _prompts_asking_to_compute() -> list[tuple[str, str]]:
    """Section instructions that ask the LLM to compute/calculate/derive (not negated)."""
    import re
    from src.engines.cam_sections import CAM_SECTIONS
    found = []
    for section in CAM_SECTIONS:
        text = section.get("instruction", "")
        for m in re.finditer(r"\b(compute|calculat\w*|derive)\b", text, flags=re.I):
            before = text[max(0, m.start() - 30):m.start()].lower()
            if not re.search(r"\b(not|never|n't|no)\b", before):
                found.append((section["id"], text[max(0, m.start() - 40):m.end() + 30].replace("\n", " ")))
    return found


def _evidence(name: str, data) -> dict:
    if not isinstance(data, dict):
        return {"present": False, "detail": "no output"}
    if name == "financial_analysis":
        return {"present": True, "detail": "formula + numerator/denominator per ratio; no document/page references"}
    if name == "validation":
        exc = data.get("exceptions") or []
        return {"present": any(e.source_doc_ref for e in exc),
                "detail": "source_doc_ref per exception (document type, no page numbers)"}
    if name == "benchmark":
        return {"present": True, "detail": "peer P25/median/P75 per metric (in-code peer table)"}
    if name == "policy":
        return {"present": True, "detail": "rule code + details per hard rule; rationale text"}
    if name == "pep_screening":
        res = data.get("pep_result")
        return {"present": bool(getattr(res, "pep_hits", None)), "detail": "source per PEP hit"}
    if name == "data_ingestion":
        return {"present": bool(data.get("bureau_data")), "detail": "source envelopes on external payloads"}
    if name == "narrative":
        return {"present": True, "detail": "fact-pack JSON per section; 'Source / Remarks' columns requested from the LLM"}
    return {"present": False, "detail": ""}


def _report(trace: dict, ctx: dict, reads: dict, executed: list[str], snap: dict, narrative_mode: str) -> dict:
    name, result = trace["agent"], trace["result"]
    data = result.data if isinstance(result.data, dict) else {}
    diag = result.diagnostics or {}
    contract = CONTRACTS[name]
    downstream_ran = executed.index(name) < len(executed) - 1
    downstream = {}
    for key in (data or {}):
        readers = sorted((reads.get(name) or {}).get(key, set()))
        static = contract.get("consumers", {}).get(key, [])
        downstream[key] = {"read_by_at_runtime": readers, "consumers_in_code": static,
                           "consumed": bool(readers or static) if downstream_ran else None}
    warnings = []
    errors = [result.error] if result.error else []
    checks = _evaluate(name, data, ctx, {**diag, "reads": reads}) if result.status == "completed" else []
    for key, d in downstream.items():
        if downstream_ran and not d["read_by_at_runtime"] and not d["consumers_in_code"]:
            warnings.append(f"output '{key}' is not consumed by any downstream agent")
    warnings += [c["detail"] for c in checks if c["status"] == "warn"]
    if result.status != "completed":
        status = "FAIL"
    elif any(c["status"] == "fail" for c in checks):
        status = "FAIL"
    elif warnings:
        status = "PARTIAL"
    else:
        status = "PASS"
    raw = _jsonable(result.data) if result.data is not None else None
    raw_json = json.dumps(raw, default=str, ensure_ascii=False) if raw is not None else ""
    calls = [{k: v for k, v in c.items()} for c in trace.get("llm_calls") or []]
    models = sorted({f"{c.get('provider')}:{c.get('model')}" for c in calls})
    if name == "narrative":
        from src.engines.cam_sections import PROMPT_VERSION
        prompt_version = PROMPT_VERSION
    else:
        prompt_version = None
    return {
        "agent": name,
        "case_id": trace["case_id"],
        "status": status,
        "started_at": result.started_at, "ended_at": result.completed_at, "duration_ms": result.duration_ms,
        "execution_mode": diag.get("execution_mode"), "llm_invoked": bool(calls) or bool(diag.get("llm_invoked")),
        "llm_call_count": len(calls), "models": models or ([f"{diag.get('provider')}:{diag.get('model')}"]
                                                           if diag.get("model") else []),
        "prompt_version": prompt_version, "code_version": code_version(name),
        "narrative_mode": narrative_mode if name == "narrative" else None,
        "contract": contract,
        "input_summary": trace["input_summary"],
        "diagnostics": diag,
        "structured_output": _structured(result.data),
        "output_size_bytes": len(raw_json.encode()),
        "evidence": _evidence(name, result.data),
        "confidence": "not produced by this agent",
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
        "downstream": downstream,
        "downstream_observed": downstream_ran,
        "llm_calls": calls,
        "messages": trace.get("messages", []),
        "raw_output": raw,
        "snapshot_source": snap["meta"]["source"],
    }


# ─── Rendering, comparison, baselines ────────────────────────────────────────

def render_report(rep: dict, show_output: bool = False, show_prompts: bool = False) -> str:
    yn = lambda b: "YES" if b else "NO"   # noqa: E731
    lines = [f"Agent: {rep['agent']}", f"Case:  {rep['case_id']}", "", f"Status: {rep['status']}", "",
             "Execution:",
             f"  Started / ended: {rep['started_at']} → {rep['ended_at']}",
             f"  Duration:        {rep['duration_ms']} ms",
             f"  Execution mode:  {rep['execution_mode']}  (snapshot: {rep['snapshot_source']})",
             f"  LLM invoked:     {yn(rep['llm_invoked'])}  calls={rep['llm_call_count']}",
             f"  Model:           {', '.join(rep['models']) or '—'}",
             f"  Prompt version:  {rep['prompt_version'] or 'n/a (no prompt)'}   code version: {rep['code_version']}",
             "", "Contract (from the code):", f"  Purpose:    {rep['contract']['purpose']}"]
    for p in rep["contract"]["processing"]:
        lines.append(f"  Processing: {p}")
    lines += ["", "Input:"] + [f"  {k}: {v}" for k, v in rep["input_summary"].items()]
    lines += ["", "Output:"]
    for k, v in rep["structured_output"].items():
        d = rep["downstream"].get(k, {})
        consumed = ("consumed by " + ", ".join(d["read_by_at_runtime"] or d["consumers_in_code"])) if d.get("consumed") \
            else ("NOT consumed downstream" if d.get("consumed") is False else "downstream not run")
        lines.append(f"  {k}: {v['type']}{' (EMPTY)' if v['empty'] else ''} — {consumed}")
    lines.append(f"  size: {rep['output_size_bytes']:,} bytes")
    lines += ["", "Evidence:", f"  Present: {yn(rep['evidence']['present'])} — {rep['evidence']['detail']}",
              f"  Confidence: {rep['confidence']}", "", "Checks:"]
    for c in rep["checks"]:
        lines.append(f"  [{c['status'].upper():4}] {c['check']}: {c['detail']}")
    if rep["errors"]:
        lines += ["", "Errors:"] + [f"  - {e}" for e in rep["errors"]]
    if rep["warnings"]:
        lines += ["", "Quality concerns:"] + [f"  - {w}" for w in dict.fromkeys(rep["warnings"])]
    if rep["llm_calls"]:
        lines += ["", "LLM calls:"]
        for c in rep["llm_calls"]:
            lines.append(f"  {c.get('provider')}:{c.get('model')} {c['duration_ms']} ms, prompt {c['prompt_chars']:,} chars, "
                         f"response {c['response_chars']:,} chars{' ERROR ' + c['error'] if c.get('error') else ''}")
            if show_prompts:
                lines += ["  --- system prompt ---", c["system_prompt"], "  --- prompt ---", c["prompt"],
                          "  --- response ---", c.get("response") or ""]
    if show_prompts and rep["agent"] == "narrative" and rep.get("raw_output"):
        for p in rep["raw_output"].get("section_plan") or []:
            if p.get("kind") == "llm" and not any(c["prompt"] == p.get("prompt") for c in rep["llm_calls"]):
                lines += [f"  --- planned prompt: {p['section']} ---", p["prompt"]]
    if show_output:
        lines += ["", "Raw output:", json.dumps(rep["raw_output"], indent=2, default=str, ensure_ascii=False)[:20000]]
    return "\n".join(lines)


def comparison_rows(reports: list[dict]) -> list[dict]:
    return [{"case": r["case_id"], "agent": r["agent"], "status": r["status"], "duration_ms": r["duration_ms"],
             "llm_called": r["llm_invoked"], "output_bytes": r["output_size_bytes"],
             "structured_output": any(not v["empty"] for v in r["structured_output"].values()),
             "evidence": r["evidence"]["present"], "errors": len(r["errors"]),
             "warnings": len(dict.fromkeys(r["warnings"]))} for r in reports]


def render_comparison(rows: list[dict]) -> str:
    cols = ["case", "agent", "status", "duration_ms", "llm_called", "output_bytes", "structured_output", "evidence",
            "errors", "warnings"]
    widths = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in cols}
    out = ["  ".join(c.ljust(widths[c]) for c in cols), "  ".join("-" * widths[c] for c in cols)]
    out += ["  ".join(str(r[c]).ljust(widths[c]) for c in cols) for r in rows]
    return "\n".join(out)


def _digest(value) -> str:
    return hashlib.sha1(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()[:12]


def baseline_path(case_id: str, agent: str, label: str) -> Path:
    return _paths()["results"] / "baselines" / case_id / agent / f"{label}.json"


def _summary(rep: dict) -> dict:
    raw = rep.get("raw_output") or {}
    return {k: rep[k] for k in ("agent", "case_id", "status", "duration_ms", "execution_mode", "llm_invoked",
                                "llm_call_count", "models", "prompt_version", "code_version", "output_size_bytes")} | {
        "checks": {c["check"]: c["status"] for c in rep["checks"]},
        "warnings": list(dict.fromkeys(rep["warnings"])),
        "output_digests": {k: _digest(v) for k, v in raw.items()} if isinstance(raw, dict) else {},
        "timestamp": rep["ended_at"],
    }


def save_baseline(rep: dict, label: str) -> Path:
    path = baseline_path(rep["case_id"], rep["agent"], label)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"summary": _summary(rep), "report": rep}, indent=2, default=str, ensure_ascii=False),
                    encoding="utf-8")
    return path


def compare_with_baseline(rep: dict, label: str) -> dict:
    path = baseline_path(rep["case_id"], rep["agent"], label)
    if not path.exists():
        raise FileNotFoundError(f"No baseline '{label}' for {rep['agent']} / {rep['case_id']} ({path})")
    before, after = json.loads(path.read_text(encoding="utf-8"))["summary"], _summary(rep)
    changes = []
    for key in ("status", "execution_mode", "llm_invoked", "llm_call_count", "models", "prompt_version",
                "code_version"):
        if before.get(key) != after.get(key):
            changes.append({"field": key, "before": before.get(key), "after": after.get(key)})
    if before["duration_ms"] and after["duration_ms"] is not None:
        changes.append({"field": "duration_ms", "before": before["duration_ms"], "after": after["duration_ms"]})
    for name in sorted(set(before["checks"]) | set(after["checks"])):
        if before["checks"].get(name) != after["checks"].get(name):
            changes.append({"field": f"check: {name}", "before": before["checks"].get(name),
                            "after": after["checks"].get(name)})
    for key in sorted(set(before["output_digests"]) | set(after["output_digests"])):
        if before["output_digests"].get(key) != after["output_digests"].get(key):
            changes.append({"field": f"output: {key}", "before": before["output_digests"].get(key, "absent"),
                            "after": after["output_digests"].get(key, "absent")})
    added = [w for w in after["warnings"] if w not in before["warnings"]]
    removed = [w for w in before["warnings"] if w not in after["warnings"]]
    return {"baseline": label, "path": str(path), "before_timestamp": before["timestamp"],
            "after_timestamp": after["timestamp"], "changes": changes, "warnings_added": added,
            "warnings_removed": removed, "output_changed": any(c["field"].startswith("output:") for c in changes)}


def render_baseline_diff(diff: dict) -> str:
    lines = [f"BEFORE ({diff['baseline']}, {diff['before_timestamp']})  →  AFTER ({diff['after_timestamp']})"]
    if not diff["changes"] and not diff["warnings_added"] and not diff["warnings_removed"]:
        lines.append("  no changes")
    for c in diff["changes"]:
        lines.append(f"  {c['field']}: {c['before']} → {c['after']}")
    lines += [f"  + warning: {w}" for w in diff["warnings_added"]]
    lines += [f"  - warning: {w}" for w in diff["warnings_removed"]]
    return "\n".join(lines)


def save_run(result: dict) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    agents = "-".join(r["agent"] for r in result["reports"]) or "none"
    path = _paths()["results"] / "runs" / f"{stamp}_{result['case_id']}_{agents[:80]}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    return path


def strip_heavy(rep: dict) -> dict:
    """A report without raw output and full prompts (for APIs and comparison tables)."""
    out = {k: v for k, v in rep.items() if k not in ("raw_output",)}
    out["llm_calls"] = [{k: v for k, v in c.items() if k not in ("system_prompt", "prompt", "response")}
                        for c in rep.get("llm_calls") or []]
    return out



# ─── M1–M6 post-pipeline contract ────────────────────────────────────────────

def build_case_from_snapshot(entity_id: str, loader: Callable | None = None, refresh_snapshot: bool = False) -> dict:
    """The case record a pipeline run would store, built from the cached snapshot with the narrative in
    plan mode (fact pack, no LLM). M1–M6 are computed exactly as build_case_result does after a run."""
    from src.application.case_service import build_case_result

    company = load_company(entity_id, loader)
    result = run_case(entity_id, agents="all", narrative_mode="plan", loader=loader,
                      refresh_snapshot=refresh_snapshot)
    snap = get_snapshot(entity_id, company)
    reports = {r["agent"]: r for r in result["reports"]}
    # Re-run the agents (cheap) to get live objects for build_case_result.
    ctx = {"company_data": copy.deepcopy(snap["company_data"]), "results": {}}
    instances = _agents()
    ctx["results"]["data_ingestion"] = copy.deepcopy(snap["ingestion"]["data"])
    for name in AGENT_ORDER[1:-1]:
        res = instances[name].execute(ctx)
        if res.status == "completed":
            ctx["results"][name] = res.data
    data, _, _ = _plan_narrative(ctx, "plan", None, None)
    ctx["results"]["narrative"] = {"fact_pack": data["fact_pack"], "cam_text": "", "narrative_mode": "plan"}
    case = build_case_result(entity_id, ctx["company_data"], ctx, [])
    case["_agent_reports"] = reports
    return case


def validate_case_outputs(case: dict) -> list[dict]:
    """Checks that each M1–M6 output exists, is structured, links correctly and is consumed downstream."""
    checks = []
    fp = case.get("fact_pack") or {}
    obs = case.get("observations")
    inv = case.get("investigations")
    chl = case.get("challenges")
    rpy = case.get("repayment_analysis") or {}
    st = case.get("stress_test") or {}
    rea = case.get("reassessment") or {}
    obs_ids = {o["observation_id"] for o in obs or []}
    inv_ids = {t["investigation_id"] for t in inv or []}
    chl_ids = {c["challenge_id"] for c in chl or []}

    checks.append(_check("M1 observations", "pass" if isinstance(obs, list) else "fail",
                         f"{len(obs or [])} structured observation(s); severities "
                         + str({s: sum(o['severity'] == s for o in obs or []) for s in ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')})))
    bad = [t["investigation_id"] for t in inv or [] if t["observation_id"] not in obs_ids]
    checks.append(_check("M2 investigations ← M1", "pass" if isinstance(inv, list) and not bad else "fail",
                         f"{len(inv or [])} task(s), all linked to M1 observations" if not bad else f"orphan links: {bad}"))
    bad = [c["challenge_id"] for c in chl or []
           if not set(c["linked_observation_ids"]) <= obs_ids or not set(c["linked_investigation_ids"]) <= inv_ids]
    checks.append(_check("M3 challenges ← M1/M2", "pass" if isinstance(chl, list) and not bad else "fail",
                         f"{len(chl or [])} challenge(s), links valid" if not bad else f"broken links: {bad}"))
    latest = rpy.get("period")
    dscr_ok = rpy.get("available") and any(
        m["metric"] == "dscr" and m["latest"] == ((fp.get("ratio_analysis") or {}).get(latest) or {}).get("dscr", {}).get("value")
        for m in rpy.get("key_metrics") or [])
    checks.append(_check("M4 repayment ← ratios", "pass" if dscr_ok else "fail",
                         f"capacity {rpy.get('repayment_capacity')}, risk {rpy.get('repayment_risk')}; DSCR equals the "
                         "ratio engine value" if dscr_ok else f"unavailable or inconsistent: {rpy.get('reason', '')}"))
    checks.append(_check("M5 stress ← ratio engine", "pass" if st.get("available") and st.get("base_reconciles") else "fail",
                         ", ".join(f"{s['label']} {s['severity']}" for s in st.get("scenarios") or [])
                         + ("; base reconciles" if st.get("base_reconciles") else f"; {st.get('reason', 'not reconciled')}")))
    links_ok = (rea.get("available") and set(rea.get("linked_observations") or []) == obs_ids
                and set(rea.get("linked_investigations") or []) == inv_ids
                and set(rea.get("linked_challenges") or []) == chl_ids and len(rea.get("linked_stress_scenarios") or []) == 3)
    checks.append(_check("M6 reassessment ← M1–M5", "pass" if links_ok else "fail",
                         f"{rea.get('decision_label')}: {rea.get('facility_recommendation', {}).get('requested_cr')} → "
                         f"{rea.get('facility_recommendation', {}).get('recommended_cr')} Cr; consumes all M1–M5 outputs"
                         if links_ok else f"missing links or unavailable: {rea.get('reason', '')}"))
    final = case.get("final_cam")
    if final is not None:
        checks.append(_check("M7 final CAM ← M1–M6", "pass" if final.get("available") and len(final.get("sections") or []) == 12
                             else "fail", f"{len(final.get('sections') or [])} section(s)"))
    else:
        checks.append(_check("M1–M6 consumer", "warn", "no final CAM composer yet — M6 output not consumed downstream"))
    return checks
