"""Back-test on past proposals (roadmap P1): would the engine have flagged the accounts that later went bad?

Each case in config/backtest.yaml names a borrower, the year it was assessed in (``as_of``) and what happened
afterwards (``outcome``: performing / stressed / npa). The real CAM engine runs on the borrower as it stood then:

    financial statements     only the years up to ``as_of`` (no provisional or later figures)
    annual report            only the report for ``as_of`` or earlier (auditor's report, CARO, notes)
    bureau, registries,      left out: today's bureau or news would leak the outcome into the past
    news, conduct            (a case may give its own point-in-time ``external_data``)
    facility                 the amount and product of the original proposal

The engine's agents then run as in a live CAM (financial analysis, validation, benchmarks, policy, the notes
reader, the challenge agent, the limit assessment), with the narrative in template mode: no AI-written text and no
model cost, because a back-test judges the signals, not the prose. Nothing is saved to the live cases.

The scorecard compares the signals with the outcomes: of the accounts that went bad, how many were flagged at
origination (and by which signal), and how many performing accounts were flagged (false alarms).
"""

from __future__ import annotations

import copy
import json
import logging
import re
import threading
import time
from datetime import datetime
from typing import Optional

log = logging.getLogger(__name__)

BAD = ("stressed", "npa", "fraud", "restructured", "written_off")
SIGNALS = [  # id, label, shown when it fired
    ("decline", "Engine verdict: Decline"),
    ("hard_rule_failed", "A hard rule failed"),
    ("high_challenge", "High-severity risk challenge"),
    ("notes_red_flag", "Red flag in the auditor's report / CARO"),
    ("limit_above", "Request above the assessed limit"),
    ("ews", "Early-warning flags at origination"),
    ("weak_grade", "Internal grade C or worse"),
]
# what counts as "flagged at origination" (config backtest.flag_on). Early-warning flags are shown but not counted
# by default: some are measured against today's date (e.g. stale financials), not the as-of date.
FLAG_ON = ["decline", "hard_rule_failed", "high_challenge", "notes_red_flag", "limit_above", "weak_grade"]
PROCESS_CHALLENGES = {"UNRESOLVED_INVESTIGATIONS"}      # "key questions are still open": a prompt, not a risk


def _cfg() -> dict:
    from src.core.config_manager import config
    return config.get("backtest", default=None) or {}


def _fy(p: str) -> int:
    m = re.search(r"(\d{4})", str(p))
    return int(m.group(1)) if m else 0


def point_in_time(company: dict, spec: dict) -> dict:
    """The borrower as it stood at ``as_of``: later figures and present-day external data removed."""
    cd = copy.deepcopy(company)
    cut = _fy(spec["as_of"])
    cd["financials"] = {p: fs for p, fs in (cd.get("financials") or {}).items() if _fy(p) <= cut}
    if not cd["financials"]:
        raise ValueError(f"No financial statements up to {spec['as_of']}")
    cd["provisional"] = None
    cd["external_data"] = spec.get("external_data") or {}
    cd["market_signals"], cd["conduct"], cd["core_banking"] = [], [], {}
    kpis = dict(cd.get("sector_kpis") or {})
    kpis.pop("development_projections", None)           # guidance given later
    cd["sector_kpis"] = kpis
    fac = cd["facility"]
    if spec.get("amount_cr"):
        fac.amount_requested_cr = float(spec["amount_cr"])
    if spec.get("tenor_months"):
        fac.tenor_months = int(spec["tenor_months"])
    cd["_as_of"] = spec["as_of"]
    return cd


def _agents(llm_notes, as_of: str):
    from src.agents.analysis_agents import BenchmarkAgent, FinancialAnalysisAgent, PolicyAgent, ValidationAgent
    from src.agents.base_agent import BaseAgent
    from src.agents.narrative_agent import NarrativeAgent
    from src.agents.notes_agent import NotesReaderAgent
    from src.agents.screening_agent import PEPScreeningAgent

    class PointInTimeIngestion(BaseAgent):
        """Stands in for document ingestion: the point-in-time record is already prepared."""
        name, description, critical = "data_ingestion", "Point-in-time record (back-test)", True

        def run(self, context):
            return {"point_in_time": context["company_data"].get("_as_of")}

    class PointInTimeNotes(NotesReaderAgent):
        def run(self, context):
            from src.engines import notes_reader
            cd = context["company_data"]
            fins = cd.get("financials") or {}
            nw = fins[sorted(fins)[-1]].get("total_equity") if fins else None
            return {"notes": notes_reader.for_entity(cd["borrower"].entity_id, llm=self.llm, net_worth_cr=nw,
                                                     use_model=self.llm is not None, max_year=_fy(as_of))}

    return [PointInTimeIngestion(), PEPScreeningAgent(), FinancialAnalysisAgent(), ValidationAgent(), BenchmarkAgent(),
            PolicyAgent(), PointInTimeNotes(llm_provider=llm_notes), NarrativeAgent(llm_provider=None)]


def signals(engine: dict) -> dict:
    """Which warning signals the engine raised for one case."""
    from src.flow import risk as rk
    risk = rk.assess(engine) or {}
    ch = rk.challenges(engine, limit=20)
    fp = engine.get("fact_pack") or {}
    lim, notes = risk.get("limit") or {}, risk.get("notes") or {}
    ews = (fp.get("ews_indicators") or {})
    grade = str(engine.get("risk_grade") or "")[:1].upper()
    fired = {
        "decline": risk.get("recommendation") in ("decline", "reject"),
        "hard_rule_failed": bool((risk.get("hard_rules") or {}).get("failed")),
        "high_challenge": any(c.get("severity") in ("HIGH", "CRITICAL") and c.get("rule_id") not in PROCESS_CHALLENGES
                              for c in ch),
        "notes_red_flag": bool(notes.get("red_flags")),
        "limit_above": lim.get("within") is False,
        "ews": bool(ews.get("flags")),
        "weak_grade": grade in ("C", "D", "E"),
    }
    why = []
    if fired["decline"]:
        why.append("engine recommends Decline")
    why += [f"hard rule failed: {r.get('label') or r.get('code')}" for r in (risk.get("hard_rules") or {}).get("failed") or []][:2]
    why += [f"{c['title']} ({c['severity'].lower()})" for c in ch
            if c.get("severity") in ("HIGH", "CRITICAL") and c.get("rule_id") not in PROCESS_CHALLENGES][:3]
    why += [f"{f['label']} p.{f['page']}" for f in notes.get("findings") or [] if f.get("severity") == "high"][:2]
    if fired["limit_above"]:
        why.append(f"request {lim.get('requested_cr')} Cr above assessed {lim.get('available_cr')} Cr")
    if fired["ews"]:
        why.append(f"{ews.get('flags')} early-warning flag(s)")
    flag_on = _cfg().get("flag_on") or FLAG_ON
    return {"fired": fired, "flagged": any(fired.get(k) for k in flag_on), "why": why, "verdict": risk.get("label"),
            "grade": engine.get("risk_grade"), "score": engine.get("composite_score"),
            "notes_mode": notes.get("mode"), "limit_method": lim.get("method_label"),
            "challenges": [{"title": c["title"], "severity": c["severity"]} for c in ch[:6]]}


def run_case(spec: dict, companies: dict, llm_notes=None) -> dict:
    from src.agents.pipeline import SuperAgent
    from src.application.case_service import build_case_result

    eid = spec["entity_id"]
    company = companies.get(eid)
    if not company:
        return {**spec, "error": f"Borrower {eid} not found"}
    started = time.time()
    try:
        cd = point_in_time(company, spec)
        agent = SuperAgent(agents=_agents(llm_notes, spec["as_of"]))
        ctx = agent.execute_pipeline(cd)
        failed = [e for e in agent.pipeline_log if e.get("status") == "failed"]
        if "narrative" not in ctx.get("results", {}):
            raise RuntimeError("; ".join(f"{e['agent_name']}: {e.get('error')}" for e in failed) or "the engine did not finish")
        engine = build_case_result(eid, cd, ctx, agent.pipeline_log)
        return {**spec, "borrower": company["borrower"].company_name, "periods": sorted(cd["financials"]),
                **signals(engine), "seconds": round(time.time() - started, 1)}
    except Exception as e:
        log.exception("Back-test case %s failed", eid)
        return {**spec, "borrower": company["borrower"].company_name, "error": str(e)[:300],
                "seconds": round(time.time() - started, 1)}


def scorecard(rows: list[dict]) -> dict:
    ok = [r for r in rows if not r.get("error")]
    bad = [r for r in ok if str(r.get("outcome")).lower() in BAD]
    good = [r for r in ok if r not in bad]
    caught = [r for r in bad if r.get("flagged")]
    alarms = [r for r in good if r.get("flagged")]
    by_signal = []
    for sid, label in SIGNALS:
        on_bad = sum(1 for r in bad if (r.get("fired") or {}).get(sid))
        on_good = sum(1 for r in good if (r.get("fired") or {}).get(sid))
        by_signal.append({"id": sid, "label": label, "on_bad": on_bad, "on_good": on_good,
                          "precision_pct": round(100 * on_bad / (on_bad + on_good)) if on_bad + on_good else None})
    pct = lambda a, b: round(100 * len(a) / len(b)) if b else None
    text = (f"Of {len(bad)} account(s) that went bad, the engine flagged {len(caught)} at origination"
            + (f" ({pct(caught, bad)}%)" if bad else "") + f"; it flagged {len(alarms)} of {len(good)} performing "
            f"account(s) (false alarms).")
    return {"cases": len(rows), "errors": len(rows) - len(ok), "bad": len(bad), "good": len(good),
            "caught": len(caught), "missed": [r["borrower"] for r in bad if not r.get("flagged")],
            "false_alarms": len(alarms), "caught_pct": pct(caught, bad), "false_alarm_pct": pct(alarms, good),
            "by_signal": by_signal, "text": text}


class Backtests:
    """Runs the back-test in the background and keeps the last result (storage/flow/backtest.json)."""

    def __init__(self, companies: dict, llm_factory=None):
        from src.core.runtime_paths import STORAGE_ROOT
        self.companies = companies
        self.llm_factory = llm_factory
        self.file = STORAGE_ROOT / "flow" / "backtest.json"
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self.progress: dict = {}

    def last(self) -> dict:
        cfg = _cfg()
        out = {"label": cfg.get("label") or "", "cases_configured": len(cfg.get("cases") or []),
               "running": self.running(), "progress": self.progress if self.running() else None}
        if self.file.exists():
            try:
                out["result"] = json.loads(self.file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return out

    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self, by: str) -> dict:
        with self._lock:
            if self.running():
                return self.last()
            cfg = _cfg()
            cases = cfg.get("cases") or []
            if not cases:
                raise ValueError("No back-test cases in config/backtest.yaml")
            self.progress = {"done": 0, "total": len(cases), "current": None}
            self._thread = threading.Thread(target=self._run, args=(cases, cfg, by), name="backtest", daemon=True)
            self._thread.start()
        return self.last()

    def _run(self, cases: list[dict], cfg: dict, by: str) -> None:
        started = datetime.now()
        llm = None
        if cfg.get("notes_with_ai") and self.llm_factory:
            try:
                llm = self.llm_factory()
            except Exception:
                log.warning("Back-test: no AI model for the notes reader — reading by rules", exc_info=True)
        rows = []
        for spec in cases:
            self.progress["current"] = spec.get("entity_id")
            rows.append(run_case(spec, self.companies, llm))
            self.progress["done"] += 1
        result = {"run_at": started.isoformat(timespec="seconds"), "by": by,
                  "seconds": round((datetime.now() - started).total_seconds()),
                  "label": cfg.get("label") or "", "rows": rows, "scorecard": scorecard(rows)}
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self.file.write_text(json.dumps(result, ensure_ascii=False, default=str), encoding="utf-8")
        self.progress["current"] = None
