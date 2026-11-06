"""
Data acquisition for a new prospect: a planner, five specialist agents working in
parallel, and a verification agent.

  planner       what this proposal needs (product, listing) and why
  identity      LEI (GLEIF API), MCA master / directors / charges (Probe42 API or document)
  financials    audited statements (exchange feed or annual reports), reconciled
  credit        commercial bureau, bank statements (Account Aggregator), GST (GSP)
  compliance    sanctions screening of the company and its directors (OFAC + UN), KYC
  market        external rating (rationale), adverse media (GDELT)
  verification  cross-checks the sources against each other

Each source is tried API first; when its API is inactive (or fails) the agent reads the
document the RM uploaded instead, and otherwise reports what it needs. Both paths
produce the same record, so turning an API on later changes nothing downstream.
"""

from __future__ import annotations

import json
import logging
import re
import os
import time
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Optional

from src.agentic.graph import AgentGraph, Node
from src.flow.acquire import connectors as api
from src.flow.acquire import readers
from src.flow.acquire.connectors import name_score
from src.flow.acquire.polite import NetworkError, PoliteClient

log = logging.getLogger(__name__)

AGENT_ORDER = ("identity", "financials", "credit", "compliance", "market")
OK = ("fetched", "read")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _cr(v) -> str:
    return f"₹{v:,.2f} Cr" if isinstance(v, (int, float)) else "—"


class Acquisition:
    def __init__(self, cfg: dict, client: PoliteClient, documents_root: Path,
                 llm_factory: Optional[Callable] = None, sanctions: Optional[api.SanctionsLists] = None):
        self.cfg = cfg or {}
        self.client = client
        self.documents_root = Path(documents_root)
        self.llm_factory = llm_factory
        self.sanctions = sanctions or api.SanctionsLists(client, cache_hours=self._src("sanctions").get("cache_hours", 24))

    @classmethod
    def from_config(cls, documents_root: Path, cache_dir: Path, llm_factory=None) -> "Acquisition":
        from src.core.config_manager import config
        cfg = config.get("data_sources") or {}
        return cls(cfg, PoliteClient.from_config(cfg.get("network") or {}, cache_dir), documents_root, llm_factory)

    # ── configuration ────────────────────────────────────────────────────────

    def _src(self, sid: str) -> dict:
        return next((s for s in self.cfg.get("sources") or [] if s["id"] == sid), {})

    def sources(self) -> list[dict]:
        return list(self.cfg.get("sources") or [])

    def agents(self) -> dict:
        return dict(self.cfg.get("agents") or {})

    def mode(self, src: dict) -> tuple[str, str]:
        """("api", "") or ("inactive", reason)."""
        if src.get("mode") != "api":
            return "inactive", src.get("inactive_reason") or "API not connected"
        key = src.get("requires_key")
        if key and not os.getenv(key, "").strip():
            return "inactive", f"No {src.get('provider', 'provider').split(' (')[0]} API key configured ({key})"
        return "api", ""

    def plan(self, ctx: dict) -> dict:
        req = self.cfg.get("requirements") or {}
        product = str((ctx.get("facility") or {}).get("product") or "")
        need = set(req.get("always") or []) | set((req.get("by_product") or {}).get(product) or [])
        rec = set(req.get("recommended") or [])
        why = {"mca": "identity, directors and charges are verified for every borrower",
               "financials": "the CAM is built on three years of audited statements",
               "bureau": "credit history and existing lenders are required for every proposal",
               "kyc": "KYC must be complete before sanction",
               "sanctions": "the company and its directors are screened for every proposal",
               "bank_statements": f"a {product.replace('_', ' ')} limit is assessed on account conduct",
               "gst": f"a {product.replace('_', ' ')} limit is assessed on GST turnover",
               "lei": "LEI confirms the legal entity (mandatory for exposures of ₹50 Cr and above)",
               "rating": "an external rating informs the internal rating",
               "adverse_media": "news screening informs reputation risk"}
        out = {}
        for s in self.sources():
            sid = s["id"]
            level = "required" if sid in need else ("recommended" if sid in rec else "not_required")
            out[sid] = {"requirement": level, "basis": why.get(sid, "")}
        out["_minimum_for_cam"] = list(req.get("minimum_for_cam") or [])
        return out

    # ── run ──────────────────────────────────────────────────────────────────

    def run(self, ctx: dict, *, previous: Optional[dict] = None, only: Optional[set] = None,
            on_event: Optional[Callable] = None) -> dict:
        """Run the agents (all, or ``only`` some of them, keeping the previous results of the others)."""
        started = time.perf_counter()
        plan = self.plan(ctx)
        prev = previous or {}
        llm = self._llm()
        ctx = {**ctx, "plan": plan, "llm": llm, "docs": self.documents_root / ctx["entity_id"],
               "mca_record": (prev.get("records") or {}).get("mca")}
        agents = [a for a in AGENT_ORDER if not only or a in only]
        lanes = {a: {"agent": a, "label": self.agents().get(a, {}).get("label", a), "status": "waiting"}
                 for a in AGENT_ORDER}
        for a in AGENT_ORDER:
            if a not in agents:
                lanes[a]["status"] = "kept"

        def emit(lane, status, **extra):
            lanes[lane].update(status=status, **extra)
            if on_event:
                on_event({"lanes": list(lanes.values())})

        fns = {"identity": self._identity, "financials": self._financials, "credit": self._credit,
               "compliance": self._compliance, "market": self._market}
        nodes = [Node(a, run=(lambda c, a=a: fns[a](c)), description=self.agents().get(a, {}).get("description", ""),
                      waits_for=("identity",) if a == "compliance" and "identity" in agents else ())
                 for a in agents]
        graph = AgentGraph(nodes, name="prospect-acquire", max_workers=len(nodes) or 1,
                           on_start=lambda n, s: emit(n.name, "running"),
                           on_result=lambda n, s, r: emit(n.name, "done" if r.status == "completed" else "failed",
                                                          ms=round(r.duration_ms), error=r.error))
        gctx = {"ctx": ctx}
        run = graph.run(gctx) if nodes else None
        states = dict(prev.get("sources") or {})
        records = dict(prev.get("records") or {})
        statements = list(prev.get("statements") or [])
        for a in agents:
            out = run.data(a) if run else None
            if out is None:
                err = getattr(run.results.get(a), "error", None) if run else None
                for s in self.sources():
                    if s["agent"] == a:
                        states[s["id"]] = self._state(s, plan, "failed", error=err or "agent failed")
                continue
            for sid, st in out.get("sources", {}).items():
                states[sid] = st
                rec = st.pop("_record", None)
                if rec is not None:
                    records[sid] = rec
                elif sid in records and st["status"] not in OK:
                    records.pop(sid, None)
            if a == "financials":
                statements = out.get("statements") or []
        verification = verify(ctx, states, records, statements)
        if on_event:
            on_event({"lanes": list(lanes.values()), "verifying": False})
        ms = round((time.perf_counter() - started) * 1000)
        return {"plan": plan, "sources": states, "records": records, "statements": statements,
                "verification": verification, "lanes": list(lanes.values()), "ms": ms,
                "max_concurrency": run.max_concurrency if run else 0, "finished_at": _now(),
                "network_calls": self.client.calls[-40:]}

    def _llm(self):
        if not self.llm_factory:
            return None
        try:
            return self.llm_factory()
        except Exception:
            return None

    # ── helpers ──────────────────────────────────────────────────────────────

    def _state(self, src: dict, plan: dict, status: str, **kw) -> dict:
        mode, reason = self.mode(src)
        p = plan.get(src["id"]) or {}
        return {"id": src["id"], "label": src["label"], "agent": src["agent"], "provider": src.get("provider"),
                "mode": mode, "mode_reason": reason, "requirement": p.get("requirement", "not_required"),
                "basis": p.get("basis", ""), "status": status, "summary": kw.pop("summary", ""),
                "documents": kw.pop("documents", []), "provenance": kw.pop("provenance", None),
                "error": kw.pop("error", None), "upload": src.get("upload"), "at": _now(), **kw}

    def _docs(self, ctx: dict, src: dict) -> list[Path]:
        up = src.get("upload") or {}
        d = ctx["docs"] / up.get("category", src["id"])
        if not d.exists():
            return []
        files = sorted((p for p in d.iterdir() if p.suffix.lower() == ".pdf"), key=lambda p: p.stat().st_mtime)
        return files if up.get("multiple") else files[-1:]

    def _belongs(self, ctx: dict, env: dict) -> Optional[str]:
        """None when the document is about this borrower, else why not."""
        ident = env.get("identity") or {}
        if ctx.get("cin") and ident.get("cin") and ident["cin"] != ctx["cin"]:
            return f"the document is for CIN {ident['cin']}, not {ctx['cin']}"
        found = env.get("name_found")
        if found and name_score(found, ctx["name"]) < 0.75 and not (ctx.get("cin") and ident.get("cin") == ctx["cin"]):
            return f"the document names {found}, not {ctx['name']}"
        return None

    def _api_or_docs(self, ctx: dict, sid: str, call: Optional[Callable], summarise: Callable) -> dict:
        """One source: the API when active, else (or on failure) the uploaded document."""
        src = self._src(sid)
        plan = ctx["plan"]
        mode, _ = self.mode(src)
        api_error = None
        if mode == "api" and call:
            try:
                env = call()
                status = "fetched" if env.get("source_status") == "success" else "not_found"
                return self._state(src, plan, status, summary=summarise(env), provenance=env.get("provenance"),
                                   _record=env if status == "fetched" else None)
            except NetworkError as e:
                api_error = str(e)
            except Exception as e:                         # a provider answered something unexpected
                log.warning("%s API failed", sid, exc_info=True)
                api_error = f"{type(e).__name__}: {e}"
        docs = self._docs(ctx, src)
        if docs and src.get("upload"):
            path = docs[-1]
            try:
                env = readers.read_source_document(sid, path, ctx["llm"])
            except Exception as e:
                log.warning("Reading %s failed", path, exc_info=True)
                return self._state(src, plan, "failed", error=f"{path.name} could not be read: {e}",
                                   documents=[path.name])
            wrong = self._belongs(ctx, env)
            if wrong:
                return self._state(src, plan, "rejected", error=f"{path.name}: {wrong}", documents=[path.name])
            return self._state(src, plan, "read", summary=summarise(env), provenance=env.get("provenance"),
                               documents=[path.name], api_error=api_error, _record=env)
        if src.get("upload"):
            return self._state(src, plan, "awaiting_upload", api_error=api_error,
                               summary=f"Upload {src['upload'].get('ask')}")
        return self._state(src, plan, "failed" if api_error else "not_found", error=api_error)

    # ── agents ───────────────────────────────────────────────────────────────

    def _identity(self, g: dict) -> dict:
        ctx = g["ctx"]
        lei = self._api_or_docs(ctx, "lei", lambda: api.gleif(self.client, name=ctx["name"], cin=ctx.get("cin"),
                                                              cache_hours=self._src("lei").get("cache_hours", 168)),
                                lambda e: (f"LEI {e['payload']['lei']} · {e['payload']['registration_status']} · "
                                           f"registered as {e['payload'].get('registered_as') or '—'}")
                                if e.get("source_status") == "success" else "No LEI record found")
        ident = ctx.get("cin") or ctx["name"]
        mca = self._api_or_docs(ctx, "mca", lambda: api.probe42(ident),
                                lambda e: (f"{e['payload'].get('company_name')} · {e['payload'].get('cin')} · "
                                           f"{e['payload'].get('status') or '—'} · "
                                           f"{len(e['payload'].get('directors') or [])} directors · "
                                           f"{len(e['payload'].get('charges') or [])} charges"))
        return {"sources": {"lei": lei, "mca": mca}}

    def _financials(self, g: dict) -> dict:
        ctx = g["ctx"]
        src = self._src("financials")
        plan = ctx["plan"]
        mode, _ = self.mode(src)
        docs = self._docs(ctx, src)
        if not docs:
            return {"sources": {"financials": self._state(src, plan, "awaiting_upload",
                                                         summary=f"Upload {src['upload']['ask']}")}, "statements": []}
        readings, errors = [], []
        for p in docs:
            try:
                r = readers.read_financial_statements(p, ctx["llm"])
            except Exception as e:
                errors.append(f"{p.name}: {e}")
                continue
            wrong = self._belongs(ctx, {"identity": r["identity"], "name_found": r["name_found"]})
            if wrong:
                errors.append(f"{p.name}: {wrong}")
                continue
            readings.append(r)
        by_period: dict[str, dict] = {}
        cross = []
        for r in sorted(readings, key=lambda r: max(s["as_of"] for s in r["statements"])):
            for s in r["statements"]:
                s = {**s, "document": r["document"], "page": r["pages"], "method": r["method"], "unit": r["unit"]}
                if s["period"] in by_period:
                    a, b = by_period[s["period"]]["items"], s["items"]
                    diffs = [k for k in ("revenue_operating", "pat", "total_assets", "total_equity")
                             if abs((a.get(k) or 0) - (b.get(k) or 0)) > max(0.5, abs(a.get(k) or 0) * 0.005)]
                    cross.append({"period": s["period"], "documents": [by_period[s["period"]]["document"],
                                                                        r["document"]], "differences": diffs})
                by_period[s["period"]] = s            # the later document (restated comparatives) wins
        statements = sorted(by_period.values(), key=lambda s: s["as_of"], reverse=True)[:3]
        if not statements:
            return {"sources": {"financials": self._state(src, plan, "failed", error="; ".join(errors) or
                                                         "no statements found", documents=[p.name for p in docs])},
                    "statements": []}
        latest = statements[0]["items"]
        summary = (f"{len(statements)} audited year(s) {statements[-1]['period']}–{statements[0]['period']} "
                   f"({statements[0]['basis']}) · revenue {_cr(latest.get('revenue_operating'))} · "
                   f"PAT {_cr(latest.get('pat'))} · net worth {_cr(latest.get('total_equity'))}")
        st = self._state(src, plan, "read", summary=summary, documents=[r["document"] for r in readings],
                         provenance={"via": "document", "document": statements[0]["document"],
                                     "page": statements[0]["page"].get("bs"), "method": statements[0]["method"]},
                         cross_document=cross, errors=errors)
        return {"sources": {"financials": st}, "statements": statements}

    def _credit(self, g: dict) -> dict:
        ctx = g["ctx"]

        def bureau(e):
            p = e["payload"]
            return (f"{p.get('cmr_rank') or p.get('credit_score') or '—'} · {p.get('total_lenders') or 0} lenders · sanctioned "
                    f"{_cr(p.get('total_exposure_cr'))} · outstanding {_cr(p.get('total_outstanding_cr'))} · "
                    f"{p.get('dpd_status') or '—'}")

        def bank(e):
            p = e["payload"]
            return (f"{p.get('bank') or 'Bank'} · {len(p.get('months') or [])} months · credits "
                    f"{_cr(p.get('total_credits_cr'))} · {p.get('returns', 0)} return(s)")

        def gst(e):
            p = e["payload"]
            t = sorted(k for k in p if k.startswith("aggregate_turnover_fy"))
            return (f"GSTIN {p.get('gstin') or '—'} · " + (f"FY{t[-1][21:25]} turnover {_cr(p[t[-1]])} · " if t else "")
                    + (p.get("filing_detail") or p.get("filing_status") or ""))
        return {"sources": {"bureau": self._api_or_docs(ctx, "bureau", None, bureau),
                            "bank_statements": self._api_or_docs(ctx, "bank_statements", None, bank),
                            "gst": self._api_or_docs(ctx, "gst", None, gst)}}

    def _compliance(self, g: dict) -> dict:
        ctx = g["ctx"]
        ident = (g.get("results") or {}).get("identity") or {}
        mca_rec = ((ident.get("sources") or {}).get("mca") or {}).get("_record") or ctx.get("mca_record")
        directors = ((mca_rec or {}).get("payload") or {}).get("directors") or []
        names = [{"name": ctx["name"], "role": "Borrower"}] + [{"name": d["name"], "role": d.get("designation") or
                                                                "Director"} for d in directors]

        def screen():
            res = self.sanctions.screen(names)
            return api.envelope("sanctions", "screening", ctx.get("cin") or ctx["name"], res,
                                provenance={"via": "api", "provider": "OFAC SDN + UN consolidated",
                                            "url": api.OFAC_SDN, "lists": res["lists"],
                                            "fetched_at": _now()})

        def summarise(e):
            p = e["payload"]
            lists = " + ".join(f"{x['list']} ({x['entries']:,})" for x in p["lists"])
            who = f"{len(p['screened'])} name(s): the company" + (f" and {len(p['screened']) - 1} director(s)"
                                                                  if len(p["screened"]) > 1 else "")
            return (f"{p['matches']} potential match(es)" if p["matches"] else "No match") + f" · {who} · {lists}"
        sanc = self._api_or_docs(ctx, "sanctions", screen, summarise)
        if sanc.get("status") == "fetched":
            rec = sanc.get("_record") or {}
            if (rec.get("payload") or {}).get("matches"):
                sanc["status"] = "match"
            if not directors:
                sanc["note"] = "Directors are screened once the MCA record is in"

        def kyc(e):
            p = e["payload"]
            return (f"PAN {p.get('pan') or '—'} · {p.get('kyc_status') or 'status not stated'} · "
                    f"{len(p.get('authorised_signatories') or [])} signatories · "
                    f"{len(p.get('beneficial_owners') or [])} beneficial owner(s)")
        return {"sources": {"sanctions": sanc, "kyc": self._api_or_docs(ctx, "kyc", None, kyc)}}

    def _market(self, g: dict) -> dict:
        ctx = g["ctx"]
        src = self._src("rating")
        rating = None
        docs = self._docs(ctx, src)
        if docs:
            path = docs[-1]
            try:
                env = readers.read_source_document("rating", path)
                p = env["payload"]
                wrong = self._belongs(ctx, env)
                if wrong:
                    rating = self._state(src, ctx["plan"], "rejected", error=f"{path.name}: {wrong}",
                                         documents=[path.name])
                elif not p.get("long_term_rating") and not p.get("short_term_rating"):
                    rating = self._state(src, ctx["plan"], "failed", error=f"{path.name}: no rating found",
                                         documents=[path.name])
                else:
                    rating = self._state(src, ctx["plan"], "read", documents=[path.name], provenance=env["provenance"],
                                         summary=f"{p.get('rating_agency')} {p.get('long_term_rating') or ''} "
                                                 f"{('/ ' + p['short_term_rating']) if p.get('short_term_rating') else ''}"
                                                 f" · {p.get('last_action') or ''} {p.get('action_date') or ''} · "
                                                 f"rated limits {_cr(p.get('total_rated_cr'))}", _record=env)
            except Exception as e:
                rating = self._state(src, ctx["plan"], "failed", error=f"{path.name} could not be read: {e}",
                                     documents=[path.name])
        if rating is None:
            rating = self._state(src, ctx["plan"], "awaiting_upload", summary=f"Upload {src['upload']['ask']}")

        def media():
            env = api.gdelt(self.client, name=ctx["name"], cache_hours=self._src("adverse_media").get("cache_hours", 24))
            arts = env["payload"]["articles"]
            flags = classify_news([a["title"] for a in arts], ctx["name"], ctx.get("llm"))
            for a, f in zip(arts, flags):
                a.update(f)
            env["payload"]["method"] = "ai" if any(f.get("by") == "ai" for f in flags) else "keywords"
            return env

        def summarise(e):
            arts = e["payload"]["articles"]
            adverse = [a for a in arts if a.get("adverse")]
            return (f"{len(arts)} article(s) in {e['payload']['window_months']} months · "
                    + (f"{len(adverse)} adverse: " + "; ".join(a['title'][:70] for a in adverse[:2])
                       if adverse else "none adverse"))
        return {"sources": {"rating": rating, "adverse_media": self._api_or_docs(ctx, "adverse_media", media, summarise)}}


def classify_news(titles: list[str], company: str, llm=None) -> list[dict]:
    """Which headlines are adverse for the borrower (AI when available, keywords otherwise)."""
    base = []
    for t in titles:
        hit = api.keyword_adverse(t) if api.names_company(t, company) else None
        base.append({"adverse": bool(hit), "adverse_reason": hit, "by": "keywords"})
    if not titles or llm is None or getattr(llm, "name", "") == "mock":
        return base
    from src.services.observation_narrator import _parse_json_object
    listing = "\n".join(f"{i}. {t}" for i, t in enumerate(titles[:60]))
    try:
        raw = llm.generate(prompt=(f"Borrower: {company}. For each headline decide whether it is ADVERSE for "
                                   "the borrower's credit or reputation (fraud, regulatory action, default, "
                                   "litigation, accidents, loss of a major customer, governance issues). "
                                   "Routine results, share-price moves and product news are not adverse. Return "
                                   "{\"adverse\": [{\"i\": index, \"reason\": \"few words\"}]}.\n\n" + listing),
                           system_prompt="You screen news for a bank's credit team. Return only JSON.",
                           temperature=0.0, max_tokens=800)
        data = _parse_json_object(raw)
        # guards on the model: a headline must name the borrower (sector or market moves are not about it),
        # and a reason that itself says "not adverse" is not a flag
        flagged = {int(x["i"]): x.get("reason") for x in data.get("adverse") or [] if str(x.get("i", "")).isdigit()
                   and int(x["i"]) < len(titles) and api.names_company(titles[int(x["i"])], company)
                   and not re.search(r"\bnot (?:inherently |necessarily )?adverse\b",str(x.get("reason") or ""), re.I)}
        return [{"adverse": i in flagged, "adverse_reason": flagged.get(i), "by": "ai"} if i < 60 else base[i]
                for i in range(len(titles))]
    except Exception:
        log.warning("AI news screening failed; keyword screening used", exc_info=True)
        return base


# ── Verification agent ───────────────────────────────────────────────────────

def verify(ctx: dict, states: dict, records: dict, statements: list[dict]) -> list[dict]:
    """Cross-checks between sources: identity, reconciliation, consistency, conduct, screening."""
    checks = []

    def add(cid, label, status, detail, sources):
        checks.append({"id": cid, "label": label, "status": status, "detail": detail, "sources": sources})

    def p(sid):
        return (records.get(sid) or {}).get("payload") or {}
    mca, lei, kyc, gst, bureau, bank = p("mca"), p("lei"), p("kyc"), p("gst"), p("bureau"), p("bank_statements")

    cins = {k: v for k, v in (("entered", ctx.get("cin")), ("MCA", mca.get("cin")), ("LEI", lei.get("registered_as")),
                              ("KYC", kyc.get("cin"))) if v}
    if len(cins) >= 2:
        same = len({v.upper() for v in cins.values()}) == 1
        add("cin", "CIN matches across sources", "pass" if same else "fail",
            ", ".join(f"{k} {v}" for k, v in cins.items()), list(cins))
    else:
        add("cin", "CIN matches across sources", "pending", "Needs the MCA record and one other source", ["mca"])

    pans = {k: v for k, v in (("KYC", kyc.get("pan")), ("GSTIN", (gst.get("gstin") or "")[2:12] or None),
                              ("bureau", bureau.get("pan"))) if v}
    if len(pans) >= 2:
        same = len(set(pans.values())) == 1
        add("pan", "PAN matches across sources", "pass" if same else "fail",
            ", ".join(f"{k} {v}" for k, v in pans.items()), list(pans))

    if statements:
        bad = [f"{s['period']}: {c['check']} ({c['detail']})" for s in statements for c in s["checks"] if not c["ok"]]
        add("reconcile", "Audited statements reconcile", "fail" if bad else "pass",
            "; ".join(bad) if bad else f"{len(statements)} year(s): assets = equity + liabilities, PBT − tax = PAT",
            ["financials"])
        cross = (states.get("financials") or {}).get("cross_document") or []
        if cross:
            diff = [c for c in cross if c["differences"]]
            add("cross_doc", "Same year agrees across annual reports", "warn" if diff else "pass",
                "; ".join(f"{c['period']} differs in {', '.join(c['differences'])} (restated?)" for c in diff)
                or "; ".join(f"{c['period']} identical in {' and '.join(c['documents'])}" for c in cross),
                ["financials"])
        latest = statements[0]
        today = date.today()
        expected = today.year if today.month > 6 else today.year - 1        # accounts are out by ~June
        y = int(latest["period"][2:])
        add("fresh", "Latest audited year is current", "pass" if y >= expected else "warn",
            f"Latest audited: {latest['period']} (as of {latest['as_of']})", ["financials"])
        it = latest["items"]
        if it.get("pbt") and it.get("other_income"):
            share = it["other_income"] / it["pbt"] if it["pbt"] > 0 else 1
            op = it.get("ebitda", 0) - it.get("other_income", 0)
            add("earnings_quality", "Earnings quality (other income share of PBT)",
                "warn" if share > 0.5 else "pass",
                f"{latest['period']}: other income {_cr(it['other_income'])} is {share:.0%} of PBT {_cr(it['pbt'])}; "
                f"operating EBITDA (excl. other income) {_cr(op)}" + (" — review what other income contains"
                                                                       if share > 0.5 else ""), ["financials"])
        rev = it.get("revenue_operating")
        key = f"aggregate_turnover_fy{y}_cr"
        if gst and rev:
            t = gst.get(key)
            if t:
                gap = abs(t - rev) / rev
                add("gst_vs_revenue", "GST turnover vs reported revenue",
                    "pass" if gap <= 0.10 else ("warn" if gap <= 0.25 else "fail"),
                    f"{latest['period']}: GST {_cr(t)} vs revenue {_cr(rev)} ({gap:.1%} apart)", ["gst", "financials"])
            else:
                add("gst_vs_revenue", "GST turnover vs reported revenue", "pending",
                    f"The GST record has no turnover for {latest['period']}", ["gst"])
        if bank.get("months") and rev:
            n = len(bank["months"])
            annual = bank["total_credits_cr"] * 12 / n
            ratio = annual / rev
            add("bank_vs_revenue", "Bank credits vs revenue", "pass" if 0.75 <= ratio <= 1.35 else "warn",
                f"{n} months' credits annualise to {_cr(annual)} = {ratio:.2f}× {latest['period']} revenue "
                f"{_cr(rev)}" + ("" if 0.75 <= ratio <= 1.35 else
                                 " — credits include GST and reflect current-year growth; confirm with recent results"),
                ["bank_statements", "financials"])
        if bureau and it.get("total_debt") is not None:
            fb = sum(f["outstanding_cr"] for f in bureau.get("facilities") or []
                     if str(f.get("type", "")).upper() in ("CC", "WCDL", "TL", "CASH CREDIT", "TERM LOAN", "WCTL", "OD"))
            bs = it.get("total_debt", 0)
            if abs(fb - bs) > max(5.0, bs * 0.2):
                add("bureau_vs_bs", "Bank borrowings: bureau vs balance sheet", "warn",
                    f"Balance-sheet borrowings {_cr(bs)} vs bureau fund-based outstanding {_cr(fb)} "
                    f"({latest['as_of']} vs {bureau.get('report_date') or 'report date'}). Borrowings not from banks "
                    "(inter-corporate or related-party loans) are not in the bureau — confirm from the borrowings note.",
                    ["bureau", "financials"])
            else:
                add("bureau_vs_bs", "Bank borrowings: bureau vs balance sheet", "pass",
                    f"Balance sheet {_cr(bs)} · bureau fund-based outstanding {_cr(fb)}", ["bureau", "financials"])
    if bureau:
        bad = []
        if bureau.get("wilful_defaulter"):
            bad.append("wilful defaulter")
        if (bureau.get("suit_filed_amount_cr") or 0) > 0:
            bad.append(f"suit filed {_cr(bureau['suit_filed_amount_cr'])}")
        if (bureau.get("max_dpd_last_12m") or 0) > 0:
            bad.append(f"max DPD {bureau['max_dpd_last_12m']} days")
        add("bureau_conduct", "Bureau: repayment conduct", "fail" if bad else "pass",
            ", ".join(bad) or f"{bureau.get('dpd_status') or 'Standard'} · no suit filed · not a wilful defaulter",
            ["bureau"])
        rating = p("rating")
        if rating.get("total_rated_cr") and bureau.get("total_exposure_cr"):
            r, b = rating["total_rated_cr"], bureau["total_exposure_cr"]
            add("rating_vs_bureau", "Rated bank limits vs bureau sanctioned limits",
                "pass" if abs(r - b) <= r * 0.1 else "warn",
                f"Rated {_cr(r)} ({rating.get('rating_agency')}) vs bureau sanctioned {_cr(b)}", ["rating", "bureau"])
    if bank.get("months"):
        add("bank_conduct", "Account conduct", "pass" if not bank.get("returns") else "warn",
            f"{bank.get('returns', 0)} cheque/ECS return(s) in {len(bank['months'])} months", ["bank_statements"])
    san = p("sanctions")
    if san:
        hits = [s for s in san.get("screened") or [] if s.get("matches")]
        add("sanctions", "Sanctions screening", "fail" if hits else "pass",
            "; ".join(f"{h['name']} ~ {h['matches'][0]['name']} ({h['matches'][0]['list']}, score "
                      f"{h['matches'][0]['score']}) — review" for h in hits)
            or f"{len(san.get('screened') or [])} name(s) screened against "
               f"{' and '.join(x['list'] for x in san.get('lists') or [])}: no match", ["sanctions"])
    media = p("adverse_media")
    if "articles" in media:
        adverse = [a for a in media["articles"] if a.get("adverse")]
        add("adverse_media", "Adverse media", "warn" if adverse else "pass",
            ("; ".join(f"{a['title'][:90]} ({a.get('source')}, {a.get('date')})" for a in adverse[:3])
             if adverse else f"{len(media['articles'])} article(s) reviewed, none adverse"), ["adverse_media"])
    if kyc:
        ok = str(kyc.get("kyc_status") or "").lower().startswith(("verified", "complete"))
        add("kyc", "KYC complete", "pass" if ok else "warn",
            f"{kyc.get('kyc_status') or 'status not stated'} · {len(kyc.get('authorised_signatories') or [])} "
            f"signatories · {len(kyc.get('beneficial_owners') or [])} beneficial owner(s)", ["kyc"])
    return checks
