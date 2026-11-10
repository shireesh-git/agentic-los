"""
The agentic LOS: a five-stage credit chain, with agents doing the work between the decisions.

    Origination (RM) ─► Credit Underwriting ─► Sanctioning Authority ─► Credit Administration ─► Disbursement
                                                (config/flow.yaml: stages, users, credit data fields, conditions)

Agents populate and check; named officers decide:
  * the CAM engine generates the CAM (or the CAM intake agent reads the bank's CAM) and the credit data
    fields are populated from it, each with its source;
  * Credit Copilot (the chat) asks each officer only for what is theirs to provide or decide: missing
    fields to the RM, the RM's omissions to Underwriting, each underwriting override to the Sanctioning
    Authority (Sanction stays disabled until every override is concurred), each condition precedent to CAD;
  * after sanction the agent drafts the sanction letter, builds a risk-based list of conditions precedent
    and subsequent, checks each document CAD uploads, prepares the disbursement request and runs the
    pre-disbursement compliance checks.

Every step is an event (src/flow/store.py): the audit trail report and the TAT analytics read them.
"""

from __future__ import annotations

import logging
import re
import secrets
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

from src.application.errors import ConflictError, ForbiddenError, InvalidRequestError, NotFoundError
from src.flow import checks as chk
from src.flow import datapoints as dpx
from src.flow import risk as rk
from src.flow.camjob import CamJobs
from src.flow.store import FlowStore

log = logging.getLogger(__name__)

AGENT = "Credit Copilot"
SKIP_WORDS = {"skip", "skip it", "leave it", "leave", "no", "not now", "later", "n/a", "na", "none", "pass",
              "not provided", "not available"}
YES_WORDS = {"yes", "y", "ok", "okay", "proceed", "go ahead", "confirm", "confirmed", "yes, re-run", "yes, rerun",
             "re-run", "rerun", "yes, verified", "verified", "yes, submit", "submit"}
NO_WORDS = {"no", "n", "not now", "later", "cancel", "no, not yet", "not yet"}
CONCUR_WORDS = {"concur", "accept", "accepted", "agree", "i agree", "yes", "ok", "okay", "approve", "fine", "i concur"}
RETURN_WORDS = {"return", "return with remarks", "dispute", "disagree", "no", "reject", "i disagree"}
_QUESTION_START = ("what", "why", "how", "who", "when", "where", "which", "is ", "are ", "does", "do ", "can",
                   "show", "explain", "tell", "list", "summar", "compare", "give")
_EDIT = re.compile(r"^(?:please\s+)?(?:change|set|update|make|correct)\s+(?:the\s+)?(.+?)\s+(?:to|=|as)\s+(.+?)"
                   r"(?:\s*(?:,|;|\.)?\s+(?:because|since|reason:?|as)\s+(.+))?$", re.I | re.S)
_PLAN = re.compile(r"what (do|should|must|can) (i|we) do|what (do|should) i do next|next steps?|what now|what to do|"
                   r"what (i|we) (should|must|need to|have to|can) do|what should (be done|happen)|should i (proceed|"
                   r"approve|recommend|sanction|return|decline)|how (do|should) i proceed|"
                   r"how (do|can|should|would) (i|we) (resolve|answer|address|fix|handle|proceed|deal)|"
                   r"what action|action plan|how to proceed|what is pending for me|what do i have to", re.I)
_AMOUNT = re.compile(r"\b(amount|limit)\b.*\b(change|reduce|lower|cut|decrease|increase|revise|right|fit|fits|max|"
                     r"maximum|should|can|how much)\b|\b(change|reduce|lower|cut|decrease|increase|revise|how much|"
                     r"what)\b.*\b(amount|limit)\b", re.I)
PRODUCTS = {"working capital": "working_capital", "term loan": "term_loan", "project finance": "project_finance"}
MET = ("verified", "confirmed", "auto")                 # a condition that no longer needs anything
ROLE_SHORT = {"rm": "RM", "credit_risk": "Underwriting", "sanctioning_authority": "Sanctioning Authority",
              "cad": "CAD", "disbursement_authoriser": "Disbursement"}

# Suggested questions for Credit Copilot, by role; one asked is replaced by the next (see _suggestions).
SUGGESTIONS = {
    "rm": ["What is still missing?", "Summarise the borrower", "What are the key strengths?",
           "What security is offered?", "What is the recommendation?"],
    "credit_risk": ["What are the key risks?", "Why was it referred?", "Summarise the financial performance",
                    "What covenants are proposed?", "What did the RM not provide?", "What deviations are there?"],
    "sanctioning_authority": ["Summarise the proposal", "What did Underwriting change and why?",
                              "What are the key risk challenges?", "What is the recommended limit and pricing?",
                              "What deviations are there?"],
    "cad": ["Which conditions precedent are open?", "What is the sanctioned limit and validity?",
            "What security must be created?", "When is charge registration due?"],
    "disbursement_authoriser": ["Summarise the disbursement request", "Are all conditions precedent met?",
                                "What is the sanction validity?", "Which conditions subsequent are open?"],
}


def _now() -> datetime:
    return datetime.now()


def _day(v) -> str:
    """2026-11-09 → 9 Nov 2026 (left as it is when it is not an ISO date)."""
    try:
        d = date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return str(v or "")
    return f"{d.day} {d:%b %Y}"


def _cr(v) -> str:
    from src.flow.copilot import crore
    return crore(float(v or 0))


def _plain(label: str) -> str:
    """A field label for a sentence: the unit suffix dropped ("EBITDA (₹ Cr)" → "EBITDA"); values carry it."""
    return re.sub(r"\s*\((?:₹ Cr|months)[^)]*\)$", "", label or "")


class FlowService:
    def __init__(self, store: FlowStore, companies: dict, cases, cam_pdf: Callable, files_root: Path,
                 llm_factory: Optional[Callable] = None, register_prospect: Optional[Callable] = None,
                 now: Callable[[], datetime] = _now, acquirer=None, save_company: Optional[Callable] = None,
                 documents_root: Optional[Path] = None):
        self.store = store
        self.companies = companies              # entity_id → borrower record (shared with the CAM engine)
        self.cases = cases                      # CaseService: runs the CAM engine
        self.cam_pdf = cam_pdf                  # (entity_id, run_id) → CAM PDF bytes
        self.files_root = Path(files_root)
        self.llm_factory = llm_factory
        self.register_prospect = register_prospect
        self.acquirer = acquirer                # data-acquisition agents for new prospects (src/flow/acquire)
        self.save_company = save_company        # (entity_id, company) → persisted borrower record
        self.documents_root = Path(documents_root) if documents_root else None
        self.now = now
        self.sessions: dict[str, dict] = {}
        self._lock = threading.RLock()
        self.jobs = CamJobs(self._run_engine, self._cam_done, self._cam_failed)
        self._acq: dict[str, dict] = {}         # case_id → running acquisition (lanes, pending re-run)
        from src.flow.backtest import Backtests
        self.backtests = Backtests(companies, llm_factory)   # roadmap P1: the engine on past proposals

    # ── configuration ────────────────────────────────────────────────────────

    @staticmethod
    def cfg() -> dict:
        return dpx.flow_config()

    def stages(self) -> list[dict]:
        return list(self.cfg().get("stages") or [])

    def stage(self, stage_id: str) -> dict:
        s = next((s for s in self.stages() if s["id"] == stage_id), None)
        if not s:
            raise NotFoundError(f"No stage {stage_id} in config/flow.yaml")
        return s

    def stage_of_role(self, role: str) -> Optional[str]:
        return next((s["id"] for s in self.stages() if s["role"] == role), None)

    def users(self) -> list[dict]:
        return list(self.cfg().get("users") or [])

    def officer(self, stage_id: str) -> str:
        role = self.stage(stage_id)["role"]
        return next((u["name"] for u in self.users() if u["role"] == role), self.role_label(role))

    def role_label(self, role: str) -> str:
        return (self.cfg().get("roles") or {}).get(role, role)

    def _stamp(self) -> str:
        return self.now().isoformat(timespec="seconds")

    # ── sign-in ──────────────────────────────────────────────────────────────

    def directory(self) -> dict:
        return {"users": [{**u, "role_label": self.role_label(u["role"]),
                           "workspace": self.stage(self.stage_of_role(u["role"]))["label"]
                           if self.stage_of_role(u["role"]) else ""} for u in self.users()],
                "stages": [{"id": s["id"], "label": s["label"], "short": s.get("short") or s["label"],
                            "role": s["role"]} for s in self.stages()],
                "product_name": self.cfg().get("product_name") or "Corporate Credit Origination",
                "environment": self.cfg().get("environment") or "",
                "note": "Demo environment — single sign-on is disabled; choose a workspace to sign in."}

    def sign_in(self, user_id: str) -> dict:
        user = next((u for u in self.users() if u["id"] == user_id), None)
        if not user:
            raise NotFoundError("Unknown user")
        token = secrets.token_urlsafe(18)
        session = {"token": token, "user": {**user, "role_label": self.role_label(user["role"]),
                                            "stage": self.stage_of_role(user["role"])}}
        self.sessions[token] = session
        return session

    def session(self, token: Optional[str]) -> dict:
        s = self.sessions.get(token or "")
        if not s:
            raise ForbiddenError("Sign in first")
        return s

    @staticmethod
    def _actor(session: Optional[dict]) -> dict:
        if not session:
            return {"id": "agent", "name": AGENT, "role": "agent"}
        u = session["user"]
        return {"id": u["id"], "name": u["name"], "role": u["role"]}

    # ── cases ────────────────────────────────────────────────────────────────

    def _require(self, case_id: str) -> dict:
        case = self.store.get(case_id)
        if not case:
            raise NotFoundError(f"Proposal {case_id} not found")
        if (case.get("risk") or {}).get("v") != rk.VERSION and (case.get("cam") or {}).get("state") == "ready":
            engine = self._engine_of(case)
            if engine is None:                   # the run is gone: keep what this proposal had
                return case
            case["risk"] = rk.assess(engine)
            case["checks"] = chk.from_engine(engine) or case.get("checks")
            case["against"] = rk.challenges(engine)
            self._build_register(case, engine)
            self.store.save(case)                # kept, so a later CAM run for the borrower does not change it
        return case

    def _engine_of(self, case: dict) -> Optional[dict]:
        """The CAM engine run this proposal's CAM came from (None for an ingested bank CAM)."""
        run = (case.get("cam") or {}).get("run_id")
        if not run or not self.cases:
            return None
        try:
            engine = self.cases.get(case["entity_id"])
            if engine and engine.get("run_id") != run and hasattr(self.cases, "get_run"):
                engine = self.cases.get_run(case["entity_id"], run)     # an earlier run (a newer CAM exists)
        except Exception:
            return None
        return self._with_limit(engine) if engine and engine.get("run_id") == run else None

    def _with_limit(self, engine: Optional[dict]) -> Optional[dict]:
        """A CAM run made before the limit assessment existed (roadmap D8) gets it from the borrower's statements."""
        if not engine:
            return engine
        fp = engine.setdefault("fact_pack", {})
        if "notes_to_accounts" not in fp and engine.get("entity_id"):
            # a run made before the notes reader existed: read by rules now (fast, cached); a re-run uses the AI
            from src.engines import notes_reader
            fp["notes_to_accounts"] = notes_reader.for_entity(engine["entity_id"], use_model=False)
        if "limit_assessment" not in fp:
            company = self.companies.get(engine.get("entity_id") or "")
            if company:
                from src.engines import limit_assessment
                try:
                    fp["limit_assessment"] = limit_assessment.from_company(company, fp)
                except Exception:
                    log.exception("Limit assessment failed for %s", engine.get("entity_id"))
        return engine

    def _save(self, case: dict) -> None:
        case["updated_at"] = self._stamp()
        self.store.save(case)

    def _log(self, case: dict, kind: str, session: Optional[dict] = None, **detail) -> None:
        self.store.log(case["case_id"], self._stamp(), kind, case.get("stage"), self._actor(session), detail)

    def borrowers(self) -> list[dict]:
        out = []
        open_by_entity = {x["entity_id"]: x["case_id"] for x in self.store.all() if x["status"] == "open"}
        for eid, c in self.companies.items():
            b, f = c["borrower"], c["facility"]
            out.append({"entity_id": eid, "company_name": b.company_name, "sector": b.sector.value,
                        "cin": b.cin, "pan": b.pan, "external_rating": b.credit_rating,
                        "facility": {"product": getattr(f.facility_type, "value", str(f.facility_type)),
                                     "amount_cr": f.amount_requested_cr, "tenor_months": f.tenor_months,
                                     "purpose": f.purpose},
                        "has_financials": bool(c.get("financials")), "open_case": open_by_entity.get(eid)})
        out.sort(key=lambda r: (r["entity_id"] != "INFY001", r["company_name"]))
        return out

    def _require_role(self, session: dict, role: str) -> None:
        if session["user"]["role"] != role:
            raise ForbiddenError(f"Only the {self.role_label(role)} can do this")

    def _at_stage(self, case: dict, session: dict) -> dict:
        """The stage the proposal is at, which must be the signed-in officer's."""
        if case["status"] != "open":
            raise ConflictError(f"The proposal is {case['status']}")
        st = self.stage(case["stage"])
        if session["user"]["role"] != st["role"]:
            raise ForbiddenError(f"The proposal is with {st['label']}")
        return st

    def _enter(self, case: dict, stage_id: str) -> None:
        """Move the proposal to a stage, keeping the time spent at each (TAT, SLA ageing)."""
        at = self._stamp()
        hist = case.setdefault("stage_history", [])
        self._resume_clock(case, force=True)
        if hist and not hist[-1].get("left"):
            hist[-1]["left"] = at
            if case.get("paused_s"):
                hist[-1]["clarification_seconds"] = int(case["paused_s"])
        case["paused_s"] = 0
        case["stage"] = stage_id
        case["stage_since"] = at
        hist.append({"stage": stage_id, "entered": at, "left": None})

    def create(self, session: dict, entity_id: Optional[str] = None, prospect: Optional[dict] = None,
               facility: Optional[dict] = None) -> dict:
        """The RM initiates a proposal: a borrower on record, or a new prospect (name, CIN, PAN, sector)."""
        self._require_role(session, self.stages()[0]["role"])
        facility = dict(facility or {})
        with self._lock:
            if prospect and not entity_id:
                name = str(prospect.get("company_name") or "").strip()
                if not name:
                    raise InvalidRequestError("Enter the prospect's registered name")
                if not self.register_prospect:
                    raise InvalidRequestError("New prospects are not enabled")
                entity_id = "P" + re.sub(r"[^A-Z0-9]", "", name.upper())[:8] + secrets.token_hex(2).upper()
                self.register_prospect(entity_id, {"company_name": name, "cin": prospect.get("cin"),
                                                   "pan": prospect.get("pan"),
                                                   "sector": prospect.get("sector") or "manufacturing"},
                                       {"facility_type": PRODUCTS.get(str(facility.get("product") or "").lower(),
                                                                      facility.get("product") or "working_capital"),
                                        "amount_cr": facility.get("amount_cr"),
                                        "tenor_months": facility.get("tenor_months"),
                                        "purpose": facility.get("purpose")})
            company = self.companies.get(entity_id or "")
            if not company:
                raise NotFoundError(f"Borrower {entity_id} not found")
            if any(c["entity_id"] == entity_id and c["status"] == "open" for c in self.store.all()):
                raise ConflictError("This borrower already has a proposal in progress — open it, or reset it first")
            b, f = company["borrower"], company["facility"]
            product = facility.get("product") or getattr(f.facility_type, "value", str(f.facility_type))
            fac = {"product": PRODUCTS.get(str(product).lower(), str(product)),
                   "amount_cr": float(facility.get("amount_cr") or f.amount_requested_cr or 0),
                   "tenor_months": int(facility.get("tenor_months") or f.tenor_months or 12),
                   "purpose": facility.get("purpose") or f.purpose or ""}
            if fac["amount_cr"] <= 0:
                raise InvalidRequestError("Enter the proposed amount")
            at = self._stamp()
            case = {"case_id": f"LOS-{self.now():%y%m%d}-{secrets.token_hex(2).upper()}",
                    "entity_id": entity_id, "borrower_name": b.company_name, "cin": b.cin, "status": "open",
                    "stage": None, "created_at": at, "updated_at": at,
                    "created_by": session["user"]["id"], "rm_name": session["user"]["name"],
                    "facility": fac, "is_prospect": not company.get("financials"),
                    "cam": {"state": "none", "mode": None}, "dp": {}, "changes": [], "chat": [], "ask": None,
                    "offered": {}, "against": [], "conditions": [], "sanction": None, "drawdown": None,
                    "release": None, "decisions": [], "stage_history": []}
            self._enter(case, self.stages()[0]["id"])
            self._save(case)
            self._log(case, "created", session, facility=fac)
            acquire = bool(case["is_prospect"] and self.acquirer)
            if acquire:
                case["prospect"] = {"cin": (prospect or {}).get("cin") or None, "pan": (prospect or {}).get("pan") or None}
                case["acquisition"] = {"state": "running", "started_at": self._stamp()}
                self._say(case, f"Proposal initiated for {b.company_name}: {self._fac_text(fac)}. The data "
                                f"acquisition agents are gathering the borrower's data — APIs first; where an API is "
                                f"not connected I will ask you for the document.")
            else:
                self._say(case, f"Proposal initiated for {b.company_name}: {self._fac_text(fac)}. Next step: generate "
                                f"the CAM with the CAM engine, or ingest the bank's CAM. Credit data fields are "
                                f"populated from it.")
                self._run_checks(case, company)
            self._save(case)
        if acquire:
            self._start_acquire(case["case_id"])
        return case

    # ── Mandatory checks, brought forward to initiation (fix list E5) ─────────

    def _demo_enabled(self) -> bool:
        from src.core.config_manager import config
        return bool(config.get("data_sources", "demo_data", "enabled", default=False))

    def _run_checks(self, case: dict, company: dict) -> None:
        """Run the six data checks now and tell the RM what is clear, failed or not verifiable."""
        try:
            res = chk.precheck(company, demo_enabled=self._demo_enabled())
        except Exception:                                    # never block initiation on a check
            log.warning("Mandatory checks failed to run for %s", case["case_id"], exc_info=True)
            return
        if not res:
            return
        case["checks"] = res
        v = chk.view(res, case.get("check_notes"))
        demo = " (demo data: the bureau, MCA and registry APIs are not connected)" if v["demo"] else ""
        parts = []
        if v["failed"]:
            parts.append("Failed: " + "; ".join(f"{i['label']}: {i['detail']}" for i in v["failed"]))
        if v["not_verified"]:
            parts.append("Not verified: " + ", ".join(i["label"] for i in v["not_verified"])
                         + " — " + "; ".join(sorted({i["evidence"] for i in v["not_verified"]})) + " needed")
        if parts:
            self._say(case, f"Mandatory checks: {v['clear']} of {v['total']} clear{demo}. " + ". ".join(parts)
                      + ". Resolve these before submission; Underwriting and the Sanctioning Authority see them.",
                      kind="warn", stage=self.stages()[0]["id"])
        else:
            self._say(case, f"Mandatory checks: all {v['total']} clear{demo} — wilful defaulter, RBI defaulter and "
                            f"fraud lists, bureau status, MCA status and suits filed.", stage=self.stages()[0]["id"])

    def check_note(self, case_id: str, code: str, body: dict, session: dict) -> dict:
        """Record that an open check was verified from evidence seen, or why the case proceeds without it."""
        kind = str(body.get("kind") or "").strip()
        note = str(body.get("note") or "").strip()
        if kind not in ("verified", "justified"):
            raise InvalidRequestError("kind must be 'verified' or 'justified'")
        if len(note) < 10:
            raise InvalidRequestError("Say what evidence you saw, or why the case proceeds without it")
        with self._lock:
            case = self._require(case_id)
            st = self.stage(case["stage"])
            if case["status"] != "open" or st["role"] != session["user"]["role"]:
                raise ForbiddenError("Only the officer the proposal is with can record this")
            items = {i["code"]: i for i in (case.get("checks") or {}).get("items") or []}
            if code not in items or items[code]["status"] == "pass":
                raise InvalidRequestError("That check is not open")
            u = session["user"]
            case.setdefault("check_notes", {})[code] = {"kind": kind, "note": note[:600], "by": u["name"],
                                                        "role": self.role_label(u["role"]), "at": self._stamp()}
            self._log(case, "check_" + kind, session, check=items[code]["label"], note=note[:300])
            self._say(case, f"{items[code]['label']}: {'verified' if kind == 'verified' else 'proceeding with justification'}"
                            f" — {u['name']}: “{note[:300]}”", stage=case["stage"])
            self._save(case)
        return self.view(case_id, session)

    # ── Data acquisition (new prospects): API first, documents as the fallback ──

    def _acq_ctx(self, case: dict) -> dict:
        company = self.companies.get(case["entity_id"]) or {}
        b = company.get("borrower")
        pros = case.get("prospect") or {}
        return {"entity_id": case["entity_id"], "name": case["borrower_name"],
                "cin": pros.get("cin") or getattr(b, "cin", None) or None,
                "pan": pros.get("pan") or getattr(b, "pan", None) or None, "facility": dict(case["facility"])}

    def _start_acquire(self, case_id: str, only: Optional[set] = None) -> None:
        """Run the agents in the background (all, or ``only`` some); a request while they run is queued."""
        with self._lock:
            job = self._acq.get(case_id)
            if job and job.get("running"):
                job["again"] = None if (only is None or job.get("again", set()) is None) else \
                    (job.get("again") or set()) | only
                return
            job = {"running": True, "lanes": [], "again": set(), "only": only}
            self._acq[case_id] = job
        threading.Thread(target=self._acquire_run, args=(case_id, only), daemon=True,
                         name=f"flow-acquire-{case_id}").start()

    def _acquire_run(self, case_id: str, only: Optional[set]) -> None:
        job = self._acq[case_id]
        try:
            with self._lock:
                case = self._require(case_id)
                ctx = self._acq_ctx(case)
                prev = case.get("acquisition") or {}
            result = self.acquirer.run(ctx, previous=prev if only else None, only=only,
                                       on_event=lambda e: job.update(lanes=e.get("lanes") or job["lanes"]))
            with self._lock:
                case = self._require(case_id)
                company = self.companies.get(case["entity_id"])
                applied = {}
                if company is not None:
                    from src.flow.acquire import mapper
                    applied = mapper.apply(company, result["records"], result["statements"], case["facility"])
                    if self.save_company:
                        self.save_company(case["entity_id"], company)
                    case["cin"] = getattr(company["borrower"], "cin", None) or case.get("cin")
                first = prev.get("state") == "running" and not only
                full = ({"ms": result["ms"], "max_concurrency": result["max_concurrency"]} if not only
                        else prev.get("full_run"))
                case["acquisition"] = {**result, "state": "done", "applied": applied, "full_run": full,
                                       "last_agents": sorted(only) if only else list(self.acquirer.agents()),
                                       "started_at": prev.get("started_at"), "runs": int(prev.get("runs") or 0) + 1}
                cam = case.get("cam") or {}
                if only and cam.get("state") == "ready" and cam.get("mode") == "generate":
                    cam["stale"] = True
                    cam["stale_reason"] = "The borrower's data sources were updated after the CAM was generated"
                self._log(case, "data_acquired", None, agents=sorted(only) if only else "all", ms=result["ms"],
                          sources={k: v["status"] for k, v in result["sources"].items()})
                self._say(case, self._acq_summary(case, first), stage=self.stages()[0]["id"],
                          kind="warn" if any(c["status"] == "fail" for c in result["verification"]) else "info")
                if company is not None and (case.get("cam") or {}).get("state") != "ready":
                    self._run_checks(case, company)
                if case.get("stage") == self.stages()[0]["id"]:
                    self._ask_next(case)
                self._save(case)
        except Exception as e:                                   # recorded; the RM can retry from the panel
            log.exception("Data acquisition failed for %s", case_id)
            with self._lock:
                case = self._require(case_id)
                case["acquisition"] = {**(case.get("acquisition") or {}), "state": "failed", "error": str(e)}
                self._say(case, f"Data acquisition stopped: {e}. Retry from the Data Sources panel.", kind="warn",
                          stage=self.stages()[0]["id"])
                self._save(case)
        finally:
            with self._lock:
                again = job.get("again")
                job["running"] = False
            if again is None or again:
                self._start_acquire(case_id, again)

    def _acq_summary(self, case: dict, first: bool) -> str:
        acq = case["acquisition"]
        src = acq["sources"]
        api_ok = [s for s in src.values() if s["status"] in ("fetched",)]
        docs = [s for s in src.values() if s["status"] == "read"]
        need = [s for s in src.values() if s["status"] in ("awaiting_upload", "failed", "rejected", "match")
                and s["requirement"] == "required"]
        checks = acq.get("verification") or []
        warn = [c for c in checks if c["status"] in ("warn", "fail")]
        head = (f"Data acquisition complete in {acq['ms'] / 1000:.1f}s — five agents in parallel. " if first else
                "Agents updated the data sources. ")
        parts = [f"{len(api_ok)} source(s) fetched via API ({', '.join(s['label'] for s in api_ok) or '—'})"]
        if docs:
            parts.append(f"{len(docs)} read from documents")
        if need:
            parts.append(f"{len(need)} required source(s) still needed: {', '.join(s['label'] for s in need)}")
        text = head + "; ".join(parts) + "."
        if checks:
            text += (f" Verification: {sum(1 for c in checks if c['status'] == 'pass')} check(s) passed"
                     + (f", {len(warn)} to review in the Data Sources panel: " + "; ".join(c["label"] for c in warn)
                        if warn else "") + ".")
        return text

    def _sources_ok(self, case: dict, ids: list[str]) -> list[dict]:
        """The sources among ``ids`` that are not yet in (missing, failed, rejected, a sanctions match)."""
        src = (case.get("acquisition") or {}).get("sources") or {}
        return [src.get(i) or {"id": i, "label": i, "status": "pending"} for i in ids
                if (src.get(i) or {}).get("status") not in ("fetched", "read")]

    def _minimum_for_cam(self) -> list[str]:
        return list(((self.acquirer.cfg if self.acquirer else {}).get("requirements") or {}).get("minimum_for_cam") or [])

    def upload_source(self, case_id: str, session: dict, source_id: str, file_name: str, content: bytes) -> dict:
        """The RM uploads the document for a source whose API is not connected; its agent reads it."""
        with self._lock:
            case = self._require(case_id)
            st = self._at_stage(case, session)
            if st["id"] != self.stages()[0]["id"]:
                raise ForbiddenError("Data source documents are added at Origination")
            if not self.acquirer or not self.documents_root:
                raise InvalidRequestError("Data acquisition is not enabled")
            src = next((s for s in self.acquirer.sources() if s["id"] == source_id), None)
            if not src or not src.get("upload"):
                raise NotFoundError(f"No document is taken for data source {source_id}")
            if not content.startswith(b"%PDF"):
                raise InvalidRequestError("Upload a PDF document")
            if len(content) > 60 * 1024 * 1024:
                raise InvalidRequestError("The document is larger than 60 MB")
            safe = re.sub(r"[^A-Za-z0-9._-]", "_", Path(file_name or "document.pdf").name)[:120]
            folder = self.documents_root / case["entity_id"] / src["upload"]["category"]
            folder.mkdir(parents=True, exist_ok=True)
            (folder / safe).write_bytes(content)
            agent = src["agent"]
            label = (self.acquirer.agents().get(agent) or {}).get("label", agent)
            self._log(case, "source_document", session, source=source_id, file=safe, size=len(content))
            if (case.get("ask") or {}).get("kind") == "source_doc" and case["ask"].get("ref") == source_id:
                case["ask"] = None
            self._say(case, f"{safe} received for {src['label']}. The {label} is reading it.")
            src_state = ((case.get("acquisition") or {}).get("sources") or {}).get(source_id)
            if src_state:
                src_state.update(status="reading", documents=[*(src_state.get("documents") or []), safe])
            self._save(case)
        only = {agent} | ({"compliance"} if agent == "identity" else set())
        self._start_acquire(case_id, only)
        return self._require(case_id)

    def refresh_sources(self, case_id: str, session: dict) -> dict:
        with self._lock:
            case = self._require(case_id)
            if self._at_stage(case, session)["id"] != self.stages()[0]["id"]:
                raise ForbiddenError("Data sources are refreshed at Origination")
            if not case.get("is_prospect") or not self.acquirer:
                raise InvalidRequestError("Data acquisition runs for new prospects")
            case["acquisition"] = {**(case.get("acquisition") or {}), "state": "running"}
            self._save(case)
        self._start_acquire(case_id)
        return self._require(case_id)

    def wait_for_acquisition(self, case_id: str, timeout: float = 120) -> dict:
        end = time.time() + timeout
        while time.time() < end:
            job = self._acq.get(case_id)
            if not job or (not job.get("running") and not job.get("again")):
                break
            time.sleep(0.05)
        return self._require(case_id)

    def source_record(self, case_id: str, source_id: str) -> dict:
        acq = self._require(case_id).get("acquisition") or {}
        rec = (acq.get("records") or {}).get(source_id)
        state = (acq.get("sources") or {}).get(source_id)
        if not state:
            raise NotFoundError(f"No data source {source_id}")
        label = (self.acquirer.agents().get(state["agent"]) or {}).get("label") if self.acquirer else None
        out = {"source": {**state, "agent_label": label or state["agent"]}, "record": rec}
        if source_id == "financials":
            out["statements"] = acq.get("statements") or []
        return out

    def _acq_view(self, case: dict) -> Optional[dict]:
        acq = case.get("acquisition")
        if not acq or not self.acquirer:
            return None
        job = self._acq.get(case["case_id"]) or {}
        running = bool(job.get("running"))
        agents = self.acquirer.agents()
        srcs = acq.get("sources") or {}
        order = [s["id"] for s in self.acquirer.sources()]
        groups = []
        for a, meta in agents.items():
            items = [{k: v for k, v in srcs[i].items() if k not in ("upload",)} | {"upload": srcs[i].get("upload")}
                     for i in order if i in srcs and srcs[i]["agent"] == a]
            if not items:
                items = [{"id": s["id"], "label": s["label"], "agent": a, "provider": s.get("provider"),
                          "mode": self.acquirer.mode(s)[0], "mode_reason": self.acquirer.mode(s)[1],
                          "status": "pending", "requirement": "", "summary": "", "upload": s.get("upload")}
                         for s in self.acquirer.sources() if s["agent"] == a]
            lane = next((l for l in (job.get("lanes") if running else acq.get("lanes")) or [] if l["agent"] == a), {})
            groups.append({"agent": a, "label": meta.get("label", a), "description": meta.get("description", ""),
                           "lane": lane, "sources": items})
        vals = list(srcs.values())
        minimum = self._minimum_for_cam()
        return {"state": "running" if running else acq.get("state"), "groups": groups,
                "verification": acq.get("verification") or [], "finished_at": acq.get("finished_at"),
                "ms": (acq.get("full_run") or {}).get("ms") or acq.get("ms"),
                "max_concurrency": (acq.get("full_run") or {}).get("max_concurrency") or acq.get("max_concurrency"),
                "last_ms": acq.get("ms"), "last_agents": [(agents.get(a) or {}).get("label", a)
                                                          for a in acq.get("last_agents") or []],
                "runs": acq.get("runs") or 0,
                "counts": {"api_live": sum(1 for s in self.acquirer.sources() if self.acquirer.mode(s)[0] == "api"),
                           "fetched": sum(1 for s in vals if s["status"] == "fetched"),
                           "read": sum(1 for s in vals if s["status"] == "read"),
                           "needed": sum(1 for s in vals if s["status"] not in ("fetched", "read")
                                         and s.get("requirement") == "required"),
                           "total": len(order)},
                "blocking_cam": [s["label"] for s in self._sources_ok(case, minimum)] if case.get("is_prospect") else [],
                "network_calls": len(acq.get("network_calls") or []), "error": acq.get("error")}

    @staticmethod
    def _fac_text(fac: dict) -> str:
        return (f"{str(fac.get('product') or '').replace('_', ' ')} of {_cr(fac.get('amount_cr'))}"
                + (f", tenor {fac['tenor_months']} months" if fac.get("tenor_months") else ""))

    def reset(self, session: dict, entity_id: str) -> dict:
        """Remove every proposal of a borrower, so the journey can start again (the CAM engine's runs stay)."""
        with self._lock:
            for c in self.store.all():
                if c["entity_id"] == entity_id and self.jobs.running(c["case_id"]):
                    raise ConflictError("A CAM is being generated for this borrower — wait for it to finish")
            removed = self.store.delete_entity(entity_id)
        log.info("Flow reset for %s by %s: %s", entity_id, session["user"]["id"], removed)
        return {"entity_id": entity_id, "removed": removed}

    # ── one proposal's lifecycle: withdraw, archive, delete (never the borrower's other proposals) ──

    def _close_stage(self, case: dict) -> None:
        self._resume_clock(case, force=True)
        hist = case.get("stage_history") or []
        if hist and not hist[-1].get("left"):
            hist[-1]["left"] = self._stamp()
            if case.get("paused_s"):
                hist[-1]["clarification_seconds"] = int(case["paused_s"])

    def withdraw(self, case_id: str, session: dict, reason: str) -> dict:
        """The RM withdraws an open proposal (the borrower dropped it, or it was raised in error). It is kept,
        closed, for the record; the borrower can then have a new proposal."""
        with self._lock:
            case = self._require(case_id)
            self._require_role(session, self.stages()[0]["role"])
            if case["status"] != "open":
                raise ConflictError(f"The proposal is already {case['status']}")
            if self.jobs.running(case_id):
                raise ConflictError("Wait for the CAM run to finish")
            reason = (reason or "").strip()
            if not reason:
                raise InvalidRequestError("State why the proposal is withdrawn — it is recorded in the audit trail")
            for q in self._open_queries(case):
                q.update(status="closed", closed_note="Proposal withdrawn")
            self._close_stage(case)
            case["status"] = "withdrawn"
            case["withdrawn"] = {"by": session["user"]["name"], "at": self._stamp(), "reason": reason,
                                 "stage": case["stage"]}
            case["ask"] = None
            case["decisions"].append({"stage": case["stage"], "stage_label": self.stage(case["stage"])["label"],
                                      "action": "withdraw", "by": session["user"]["name"],
                                      "role": session["user"]["role"], "at": self._stamp(), "comment": reason})
            self._log(case, "withdraw", session, comment=reason, status="withdrawn")
            self._say(case, f"Withdrawn by {session['user']['name']}: “{reason}”. The proposal is closed and kept "
                            f"for the record.", kind="warn")
            self._save(case)
            return case

    def archive(self, case_id: str, session: dict, archived: bool = True) -> dict:
        """Take a closed proposal off the pipeline list (it stays in reports and can be brought back)."""
        with self._lock:
            case = self._require(case_id)
            if archived and case["status"] == "open":
                raise ConflictError("Only a closed proposal can be archived — withdraw it first")
            if archived:
                case["archived"] = {"by": session["user"]["name"], "at": self._stamp()}
            else:
                case.pop("archived", None)
            self._log(case, "archive" if archived else "unarchive", session)
            self._save(case)
            return case

    def delete_case(self, case_id: str, session: dict) -> dict:
        """Remove one proposal and its trail (demo housekeeping). A disbursed proposal is never removed."""
        with self._lock:
            case = self._require(case_id)
            self._require_role(session, self.stages()[0]["role"])
            if case["status"] == "disbursed" or case.get("sanction"):
                raise ConflictError("A sanctioned proposal is kept for the record — archive it instead")
            if self.jobs.running(case_id):
                raise ConflictError("Wait for the CAM run to finish")
            self.store.delete_case(case_id)
        log.info("Proposal %s (%s) deleted by %s", case_id, case["entity_id"], session["user"]["id"])
        return {"case_id": case_id, "deleted": True}

    # ── clarifications inside the stage: the proposal stays where it is, and its clock pauses ──

    @staticmethod
    def _open_queries(case: dict) -> list[dict]:
        return [q for q in case.get("queries") or [] if q["status"] == "open"]

    def _paused_seconds(self, case: dict) -> float:
        s = float(case.get("paused_s") or 0)
        if case.get("paused_since") and case["status"] == "open":
            s += max((self.now() - datetime.fromisoformat(case["paused_since"])).total_seconds(), 0)
        return s

    def _resume_clock(self, case: dict, force: bool = False) -> None:
        if case.get("paused_since") and (force or not self._open_queries(case)):
            case["paused_s"] = self._paused_seconds(case)
            case["paused_since"] = None

    def _query_targets(self, case: dict) -> list[dict]:
        """Who the officer at the current stage may ask: the officers of the earlier stages."""
        stages = self.stages()
        idx = next((i for i, s in enumerate(stages) if s["id"] == case["stage"]), 0)
        return [{"stage": s["id"], "label": s["label"], "who": self.officer(s["id"])} for s in stages[:idx]]

    def _query(self, case: dict, qid: str) -> dict:
        q = next((q for q in case.get("queries") or [] if q["id"] == qid), None)
        if not q:
            raise NotFoundError(f"Clarification {qid} not found")
        if q["status"] != "open":
            raise ConflictError(f"The clarification is already {q['status']}")
        return q

    def raise_query(self, case_id: str, session: dict, question: str, to_stage: Optional[str] = None) -> dict:
        with self._lock:
            case = self._require(case_id)
            st = self._at_stage(case, session)
            targets = {t["stage"]: t for t in self._query_targets(case)}
            if not targets:
                raise InvalidRequestError("Clarifications are asked of an earlier stage")
            to = targets.get(to_stage or self.stages()[0]["id"])
            if not to:
                raise InvalidRequestError("Ask an officer at an earlier stage")
            question = (question or "").strip()
            if not question:
                raise InvalidRequestError("Type the question")
            qs = case.setdefault("queries", [])
            q = {"id": f"Q{len(qs) + 1}", "stage": st["id"], "stage_label": st["label"],
                 "from_name": session["user"]["name"], "from_role": session["user"]["role"],
                 "to_stage": to["stage"], "to_label": to["label"], "to_role": self.stage(to["stage"])["role"],
                 "to_name": to["who"], "question": question, "raised_at": self._stamp(), "status": "open"}
            qs.append(q)
            if not case.get("paused_since"):
                case["paused_since"] = q["raised_at"]
            self._log(case, "query_raise", session, query=q["id"], to_stage=to["stage"], question=question)
            self._say(case, f"{q['from_name']} ({st['label']}) asks: “{question}” The proposal stays with "
                            f"{st['label']}; answer here and the answer goes straight back.", kind="warn",
                      stage=to["stage"])
            self._save(case)
            return case

    def answer_query(self, case_id: str, session: dict, qid: str, answer: str) -> dict:
        with self._lock:
            case = self._require(case_id)
            if case["status"] != "open":
                raise ConflictError(f"The proposal is {case['status']}")
            q = self._query(case, qid)
            if session["user"]["role"] != q["to_role"]:
                raise ForbiddenError(f"The clarification is addressed to {q['to_label']}")
            answer = (answer or "").strip()
            if not answer:
                raise InvalidRequestError("Type the answer")
            q.update(status="answered", answer=answer, answered_by=session["user"]["name"], answered_at=self._stamp())
            self._resume_clock(case)
            self._log(case, "query_answer", session, query=qid, answer=answer)
            self._say(case, f"{q['answered_by']} ({q['to_label']}) answered your clarification “{q['question']}”: "
                            f"“{answer}”.", kind="info", stage=q["stage"])
            self._save(case)
            return case

    def withdraw_query(self, case_id: str, session: dict, qid: str) -> dict:
        with self._lock:
            case = self._require(case_id)
            self._at_stage(case, session)
            q = self._query(case, qid)
            q.update(status="withdrawn", closed_note=f"Withdrawn by {session['user']['name']}")
            self._resume_clock(case)
            self._log(case, "query_withdraw", session, query=qid)
            self._save(case)
            return case

    # ── the pipeline (work queue, portfolio, executive summary) ─────────────

    def queue(self, session: dict) -> dict:
        role = session["user"]["role"]
        rows = [self._row(c) for c in self.store.all()]
        mine = [r for r in rows if r["status"] == "open" and (r["role"] == role or role in r["queries_for"])]
        return {"mine": mine, "all": rows, "others": [r for r in rows if r not in mine], "kpis": self._kpis(rows)}

    def _ageing(self, case: dict) -> tuple[float, int, str]:
        st = self.stage(case["stage"])
        sla = int(st.get("sla_hours") or 48)
        since = case.get("stage_since") or case["created_at"]
        end = self.now() if case["status"] == "open" else datetime.fromisoformat(case["updated_at"])
        # time waiting on a clarification is not the stage's time: the SLA clock pauses while a query is open
        hours = max(((end - datetime.fromisoformat(since)).total_seconds() - self._paused_seconds(case)) / 3600, 0)
        state = "breach" if hours >= sla else "amber" if hours >= 0.5 * sla else "ok"
        return round(hours, 2), sla, state if case["status"] == "open" else "closed"

    def _row(self, c: dict) -> dict:
        st = self.stage(c["stage"])
        hours, sla, sla_state = self._ageing(c)
        dp = c.get("dp") or {}
        rating = str((dp.get("internal_rating") or {}).get("value") or "").split(" ")[0] or None
        limit = (c.get("sanction") or {}).get("limit_cr") or (dp.get("recommended_cr") or {}).get("value") \
            or c["facility"]["amount_cr"]
        return {"case_id": c["case_id"], "entity_id": c["entity_id"], "borrower_name": c["borrower_name"],
                "cin": c.get("cin") or (dp.get("cin") or {}).get("value"),
                "amount_cr": c["facility"]["amount_cr"], "exposure_cr": float(limit or 0),
                "product": c["facility"]["product"], "tenor_months": c["facility"].get("tenor_months"),
                "internal_rating": rating, "external_rating": (dp.get("external_rating") or {}).get("value"),
                "status": c["status"], "stage": c["stage"], "stage_label": st["label"],
                "stage_short": st.get("short") or st["label"], "role": st["role"],
                "assigned_to": self.officer(c["stage"]) if c["status"] == "open" else None,
                "ageing_hours": hours, "sla_hours": sla, "sla_state": sla_state,
                "cam_state": (c.get("cam") or {}).get("state"), "updated_at": c["updated_at"],
                "created_at": c["created_at"], "sanctioned_cr": (c.get("sanction") or {}).get("limit_cr"),
                "disbursed_cr": (c.get("release") or {}).get("amount_cr"),
                "pending_changes": sum(1 for x in c.get("changes") or [] if x["status"] == "pending"),
                "open_queries": len(self._open_queries(c)),
                "queries_for": sorted({q["to_role"] for q in self._open_queries(c)}),
                "archived": bool(c.get("archived"))}

    def _kpis(self, rows: list[dict]) -> dict:
        open_ = [r for r in rows if r["status"] == "open"]
        done = [r for r in rows if r["status"] == "disbursed"]
        tat = [(datetime.fromisoformat(r["updated_at"]) - datetime.fromisoformat(r["created_at"])).total_seconds()
               for r in done]
        by_stage = [{"stage": s["id"], "label": s.get("short") or s["label"],
                     "count": sum(1 for r in open_ if r["stage"] == s["id"]),
                     "exposure_cr": round(sum(r["exposure_cr"] for r in open_ if r["stage"] == s["id"]), 2)}
                    for s in self.stages()]
        auto = []
        for c in self.store.all():
            vals = [v for v in (c.get("dp") or {}).values() if v.get("status") == "filled"]
            if vals:
                auto.append(sum(1 for v in vals if (v.get("source") or {}).get("kind") != "person") / len(dpx.specs()))
        return {"pipeline_count": len(open_), "pipeline_exposure_cr": round(sum(r["exposure_cr"] for r in open_), 2),
                "sanctioned_count": sum(1 for r in rows if r["sanctioned_cr"]),
                "sanctioned_cr": round(sum(r["sanctioned_cr"] or 0 for r in rows), 2),
                "disbursed_cr": round(sum(r["disbursed_cr"] or 0 for r in rows), 2),
                "sla_breaches": sum(1 for r in open_ if r["sla_state"] == "breach"),
                "avg_tat_seconds": int(sum(tat) / len(tat)) if tat else None,
                "auto_population_pct": round(100 * sum(auto) / len(auto), 1) if auto else None,
                "by_stage": by_stage}

    # ── CAM: generate ────────────────────────────────────────────────────────

    def _overrides(self, case: dict) -> dict:
        """What this proposal asks the CAM engine to assess: the facility as requested, and the figures an
        officer entered (an officer's value replaces the record's for this run)."""
        fac = dict(case["facility"])
        dp = case.get("dp") or {}

        def person(k):
            d = dp.get(k) or {}
            return d.get("value") if (d.get("source") or {}).get("kind") == "person" else None

        if person("amount_cr") is not None:
            fac["amount_cr"] = person("amount_cr")
        if person("tenor_months") is not None:
            fac["tenor_months"] = person("tenor_months")
        if person("purpose"):
            fac["purpose"] = person("purpose")
        if person("product"):
            fac["product"] = PRODUCTS.get(str(person("product")).lower(), person("product"))
        out = {"facility": {"amount_cr": fac["amount_cr"], "tenor_months": fac["tenor_months"],
                            "purpose": fac["purpose"], "facility_type": fac["product"]}}
        company = self.companies.get(case["entity_id"]) or {}
        fins = company.get("financials") or {}
        if fins:
            period = max(fins, key=lambda p: (getattr(fins[p], "as_of_date", date.min), p))
            items = {}
            if case.get("is_prospect") and (case.get("acquisition") or {}).get("statements"):
                # the Financials agent's reconciled reading of the audited statements: the engine's own
                # whole-document extraction must not replace it
                li = getattr(fins[period], "line_items", None) or {}
                items.update({k: li[k] for k in ("revenue_operating", "total_income", "ebitda", "pat", "pbt",
                                                 "depreciation", "finance_cost") if li.get(k) is not None})
            for sp in dpx.specs():
                if sp.get("line_item") and person(sp["id"]) is not None:
                    items[sp["line_item"]] = float(person(sp["id"]))
            if items:
                out["financials"] = {period: items}
        return out

    def _run_engine(self, entity_id: str, overrides: Optional[dict], on_progress):
        return self.cases.run(entity_id, on_progress=on_progress, overrides=overrides)

    def _can_generate(self, case: dict) -> bool:
        if not (self.companies.get(case["entity_id"]) or {}).get("financials"):
            return False
        if case.get("is_prospect") and case.get("acquisition"):
            return not self._sources_ok(case, self._minimum_for_cam())
        return True

    def _cannot_generate(self, case: dict) -> str:
        if case.get("is_prospect") and case.get("acquisition"):
            if (case["acquisition"].get("state") == "running") or (self._acq.get(case["case_id"]) or {}).get("running"):
                return "The data acquisition agents are still working — the CAM can be generated when they finish"
            gaps = self._sources_ok(case, self._minimum_for_cam())
            if gaps:
                return ("Before the CAM can be generated: " + "; ".join(
                    f"{g['label']} ({'potential sanctions match to review' if g.get('status') == 'match' else 'upload the document' if g.get('upload') else 'not available'})"
                    for g in gaps))
        return "No financial statements are on record for this borrower — ingest the bank's CAM instead"

    def generate_cam(self, case_id: str, session: dict) -> dict:
        """Generate (or re-run) the CAM with the CAM engine, in the background."""
        with self._lock:
            case = self._require(case_id)
            st = self._at_stage(case, session)
            if st["id"] not in ("rm", "credit_risk"):
                raise ForbiddenError("The CAM is generated at Origination and re-run at Underwriting")
            if not self._can_generate(case):
                raise InvalidRequestError(self._cannot_generate(case))
            if self.jobs.running(case_id):
                return self.cam_progress(case_id)
            resumed = (case.get("cam") or {}).get("state") == "failed"
            reason = "rerun" if (case.get("cam") or {}).get("run_id") else "generate"
            case["cam"] = {**(case.get("cam") or {}), "state": "running", "mode": "generate",
                           "started_at": self._stamp(), "error": None}
            case["ask"] = None
            self._save(case)
            self._log(case, "cam_rerun" if reason == "rerun" else "cam_generate", session, resume=resumed)
            self.jobs.start(case_id, case["entity_id"], self._overrides(case), reason)
            return self.cam_progress(case_id)

    def cam_progress(self, case_id: str) -> dict:
        case = self._require(case_id)
        job = self.jobs.get(case_id)
        view = job.view() if job else None
        cam = case.get("cam") or {}
        if cam.get("state") == "running" and not self.jobs.running(case_id) and (not job or job.state != "done"):
            # the server restarted mid-run, or the job failed before it could record it
            view = {**(view or {}), "state": "failed", "error": cam.get("error") or "The run was interrupted — resume it"}
        if cam.get("state") == "ready":
            view = {**(view or {}), "state": "done", "percent": 100, "step": "CAM ready"}
        return {"case_id": case_id, "cam": cam, "job": view}

    def _cam_done(self, case_id: str, job, engine: dict) -> None:
        engine = self._with_limit(engine)
        with self._lock:
            case = self._require(case_id)
            narrative = next((e for e in engine.get("pipeline_log") or [] if e.get("agent_name") == "narrative"), {})
            diag = narrative.get("diagnostics") or {}
            first = not (case.get("cam") or {}).get("run_id")
            case["cam"] = {**case["cam"], "state": "ready", "mode": "generate", "run_id": engine.get("run_id"),
                           "generated_at": self._stamp(), "stale": False, "stale_reason": None,
                           "model": diag.get("model"), "narrative_mode": engine.get("narrative_mode"),
                           "llm_calls": diag.get("llm_calls", 0),
                           "sections_total": job.sections_total, "sections_reused": job.sections_reused,
                           "sections_written": max(job.sections_done - job.sections_reused, 0),
                           "duration_seconds": int(job.view()["elapsed_seconds"]), "error": None,
                           "figure_check": job.figure_check() if engine.get("narrative_mode") == "llm" else None}
            fc = case["cam"]["figure_check"] or {}
            if fc.get("flagged"):
                n = sum(len(f["figures"]) for f in fc["flagged"])
                self._say(case, f"Figures to verify: the AI quoted {n} figure(s) not found in the data it was given, "
                                f"in {len(fc['flagged'])} section(s) — "
                                + "; ".join(f"{f['title']}: {', '.join(f['figures'][:6])}" for f in fc["flagged"][:4])
                                + ". Check them against the source before relying on the CAM (see **CAM** card).",
                          kind="warn")
            for offered in (case.get("offered") or {}).values():
                if "rerun" in offered:
                    offered.remove("rerun")
            found = dpx.from_engine(engine)
            self._fill(case, found)
            case["against"] = rk.challenges(engine)
            case["risk"] = rk.assess(engine)
            case["checks"] = chk.from_engine(engine) or case.get("checks")
            case["observations"] = [{k: o.get(k) for k in ("title", "severity", "summary")}
                                    for o in engine.get("observations") or []]
            self._build_register(case, engine)
            keep = {a["id"] for a in case["against"]}
            case["responses"] = {k: v for k, v in (case.get("responses") or {}).items() if k in keep}
            self._refresh_risks(case)
            self._log(case, "cam_ready", None, run_id=engine.get("run_id"), filled=len(found),
                      sections_written=case["cam"]["sections_written"], sections_reused=case["cam"]["sections_reused"],
                      model=case["cam"]["model"], llm_calls=case["cam"]["llm_calls"],
                      duration_seconds=case["cam"]["duration_seconds"])
            if first:
                self._intro_after_cam(case, "generated by the CAM engine")
            else:
                c = case["cam"]
                self._say(case, f"CAM re-run complete in {c['duration_seconds']}s: {c['sections_written']} "
                                f"section(s) rewritten for the change, {c['sections_reused']} unchanged and reused. "
                                f"Current recommendation: {self._value(case, 'recommendation')[:160]}")
                self._ask_next(case)
            self._save(case)

    @staticmethod
    def _explain(error: str) -> str:
        """An engine failure in words the officer can act on (the raw error stays in the log)."""
        from src.core.config_manager import config

        model = (config.get_active_llm_provider() or {}).get("model") or "the configured model"
        if "404" in error and "Not found for account" in error:
            return (f"The AI model {model} is not available to this NVIDIA account — choose another model in "
                    f"config/llm_providers.yaml (or set NVIDIA_NIM_MODEL), then Resume")
        if "401" in error or "403" in error or "Missing credentials" in error:
            return "The AI provider rejected the API key — check NVIDIA_NIM_API_KEY in .env.local, then Resume"
        if "429" in error:
            return "The AI provider is rate-limiting — wait a minute, then Resume (written sections are kept)"
        return error

    def _cam_failed(self, case_id: str, job, error: str) -> None:
        error = self._explain(error)
        job.error = error
        with self._lock:
            case = self._require(case_id)
            case["cam"] = {**case["cam"], "state": "failed", "error": error}
            self._log(case, "cam_failed", None, error=error, sections_done=job.sections_done)
            self._say(case, f"CAM generation stopped: {error[:200]}. Sections already written are saved; Resume "
                            f"continues from where it stopped.", kind="warn")
            self._save(case)

    def wait_for_cam(self, case_id: str, timeout: Optional[float] = None) -> dict:
        self.jobs.wait(case_id, timeout)
        return self._require(case_id)

    def cam_file(self, case_id: str, session: dict) -> tuple[bytes, str]:
        """The CAM as a PDF: the generated one (with its data sheet embedded) or the one ingested."""
        case = self._require(case_id)
        cam = case.get("cam") or {}
        if cam.get("state") != "ready":
            raise ConflictError("The CAM is not ready yet")
        name = re.sub(r"[^A-Za-z0-9]+", "_", case["borrower_name"]).strip("_")
        if cam.get("mode") == "upload":
            return Path(cam["file"]).read_bytes(), cam.get("file_name") or f"CAM_{name}.pdf"
        from src.flow import reports

        view = self.view(case_id, session)
        points = {p["id"]: p for g in view["groups"] for p in g["points"]}
        summary = reports.decision_summary(case, points, view["stage_label"])
        fc = cam.get("figure_check") or {}
        if fc:
            summary += ("\n\n**AI figures check:** " + (
                "; ".join(f"{f['title']}: {', '.join(f['figures'][:8])}" for f in fc.get("flagged") or [])
                + " — quoted by the AI but not found in its source data; verify before relying on them."
                if fc.get("flagged") else
                f"every figure in the {fc.get('sections_checked', 0)} AI-written sections was found in its source data."))
        pdf = self.cam_pdf(case["entity_id"], cam["run_id"], decision_summary=summary)
        sheet = {"format": dpx.SHEET_FORMAT, "entity_id": case["entity_id"], "case_id": case_id,
                 "run_id": cam["run_id"], "generated_at": cam.get("generated_at"),
                 "datapoints": {k: {"value": v.get("value"), "source": {kk: vv for kk, vv in (v.get("source") or {}).items()
                                                                         if kk != "excerpt"}}
                                for k, v in (case.get("dp") or {}).items() if v.get("value") not in (None, "")}}
        self._log(case, "cam_download", session)
        return dpx.embed_sheet(pdf, sheet), f"CAM_{name}_{(cam.get('generated_at') or '')[:10]}.pdf"

    # ── CAM: ingest the bank's CAM ───────────────────────────────────────────

    def upload_cam(self, case_id: str, session: dict, file_name: str, content: bytes) -> dict:
        if not content or not content.startswith(b"%PDF"):
            raise InvalidRequestError("Upload the CAM as a PDF")
        with self._lock:
            case = self._require(case_id)
            st = self._at_stage(case, session)
            if st["id"] != "rm":
                raise ForbiddenError("The CAM is ingested at Origination")
            if self.jobs.running(case_id):
                raise ConflictError("A CAM is being generated — wait for it to finish")
            folder = self.files_root / case_id / "cam"
            folder.mkdir(parents=True, exist_ok=True)
            safe = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(file_name or "cam.pdf").name) or "cam.pdf"
            path = folder / safe
            path.write_bytes(content)
            sheet = dpx.read_sheet(content)
            if sheet and sheet.get("entity_id") == case["entity_id"]:
                found, how = self._from_sheet(sheet, content, safe), "sheet"
            else:
                from src.flow import cam_intake
                llm = None
                if self.llm_factory:
                    try:
                        llm = self.llm_factory()
                    except Exception:
                        llm = None
                reading = cam_intake.read_cam(path, llm=llm)
                found, how = dpx.from_reading(reading, safe), "reader"
                self._identity_from_record(case, found)
                self._check_against_record(case, found)
            engine = self._with_limit(self.cases.get(case["entity_id"]) if self.cases else None)
            linked = sheet.get("run_id") if how == "sheet" else None
            case["cam"] = {"state": "ready", "mode": "upload", "file": str(path), "file_name": safe,
                           "read_by": how, "run_id": linked, "generated_at": self._stamp(), "stale": False,
                           "uploaded_at": self._stamp(), "pages": len(dpx.page_texts(content))}
            case["dp"] = {}
            self._fill(case, found)
            case["against"] = rk.challenges(engine) if engine else []
            case["risk"] = rk.assess(engine)
            case["checks"] = chk.from_engine(engine) or case.get("checks")
            self._build_register(case, engine)
            self._log(case, "cam_upload", session, file=safe, read_by=how, filled=len(found))
            self._intro_after_cam(case, "ingested from the bank's CAM" + (" (embedded data sheet)" if how == "sheet" else ""))
            self._save(case)
            return case

    def _from_sheet(self, sheet: dict, content: bytes, file_name: str) -> dict:
        pages = dpx.page_texts(content)
        out = {}
        for k, v in (sheet.get("datapoints") or {}).items():
            sp = dpx.spec(k)
            if not sp:
                continue
            page = dpx.find_page(pages, sp, v.get("value"))
            src = v.get("source") or {}
            out[k] = {"value": v.get("value"), "source": {
                "kind": "upload", "label": "Ingested CAM" + (f" · p.{page}" if page else " · data sheet"),
                "page": page, "document": file_name, "section": src.get("section"),
                "detail": f"Generated by the CAM engine (run {str(sheet.get('run_id'))[:8]}); "
                          + (src.get("detail") or ""),
                "confidence": dpx.confidence(max(((src.get("confidence") or {}).get("score") or 95) - 5, 0),
                                             "Exact value from this platform's data sheet embedded in the CAM; "
                                             + ((src.get("confidence") or {}).get("basis") or ""))
                if dpx.numeric(sp) else None,
                "excerpt": re.sub(r"\s+", " ", pages[page - 1])[:1200] if page else ""}}
        return out

    def _identity_from_record(self, case: dict, found: dict) -> None:
        """Identity and the request come from the borrower record and the proposal, not the CAM text."""
        b = self.companies[case["entity_id"]]["borrower"]
        rec = {"kind": "record", "label": "Borrower master", "detail": "Bank's borrower master"}
        for k, v in (("company_name", b.company_name), ("cin", b.cin), ("pan", b.pan)):
            if v and k not in found:
                found[k] = {"value": v, "source": dict(rec)}
        if "sector" not in found:
            found["sector"] = {"value": b.sector.value.replace("_", " ").capitalize(), "source": dict(rec)}
        req = {"kind": "record", "label": f"Proposal initiation ({case['rm_name']}, RM)"}
        fac = case["facility"]
        for k, v in (("product", fac["product"].replace("_", " ").capitalize()), ("amount_cr", fac["amount_cr"]),
                     ("tenor_months", fac["tenor_months"]), ("purpose", fac["purpose"])):
            if v not in (None, "") and k not in found:
                found[k] = {"value": v, "source": dict(req)}

    def _check_against_record(self, case: dict, found: dict) -> None:
        """A CAM figure that disagrees with the borrower's audited statements is flagged, not accepted silently."""
        fins = (self.companies.get(case["entity_id"]) or {}).get("financials") or {}
        audited = [fs for fs in fins.values() if getattr(fs, "source", "") == "audited"]
        if not audited:
            return
        latest = max(audited, key=lambda fs: fs.period)
        for sp in dpx.specs():
            hit = found.get(sp["id"])
            rec = latest.line_items.get(sp.get("line_item") or "") if sp.get("line_item") else None
            if hit and isinstance(rec, (int, float)) and isinstance(hit["value"], (int, float)) \
                    and abs(hit["value"] - rec) > 0.01 * max(abs(rec), 1):
                hit["flag"] = (f"The CAM states {_cr(hit['value'])}; the audited {latest.period} statements "
                               f"show {_cr(rec)} — confirm which is right")

    # ── credit data fields ───────────────────────────────────────────────────

    def _fill(self, case: dict, found: dict) -> None:
        """Agent values into the proposal: a value an officer entered is kept; the rest follow the CAM."""
        dp = case.setdefault("dp", {})
        for sp in dpx.specs():
            cur = dp.get(sp["id"]) or {}
            if (cur.get("source") or {}).get("kind") == "person":
                continue
            hit = found.get(sp["id"])
            if hit:
                dp[sp["id"]] = {"value": hit["value"], "source": hit["source"], "status": "filled",
                                "flag": hit.get("flag"), "history": cur.get("history") or []}
            elif cur.get("status") == "skipped":
                continue
            else:
                dp[sp["id"]] = {"value": None, "source": None, "status": "missing", "history": cur.get("history") or []}

    def _value(self, case: dict, dp_id: str):
        return ((case.get("dp") or {}).get(dp_id) or {}).get("value") or ""

    def _dp_question(self, case: dict, sp: dict) -> dict:
        """Ask for a field: its valid answers as buttons (a suggested one first, with the reason), "Not
        provided" last and secondary, and a typing hint for a free-text answer (fix list E1)."""
        options = list(sp.get("options") or [])
        suggested = self._suggest(case, sp) if options else None
        if suggested and suggested["value"] in options:
            options.remove(suggested["value"])
            options.insert(0, suggested["value"])
        text = sp.get("ask") or f"Provide {sp['label']}."
        if suggested:
            text += f" Suggested: {suggested['value']} — {suggested['reason']}."
        elif options:
            text += " Choose one below, or type the answer."
        else:
            text += " Type the answer below."
        return {"kind": "dp", "ref": sp["id"], "text": text, "quick": options,
                "secondary": [] if sp.get("required") else ["Not provided"],
                "suggested": suggested["value"] if suggested else None,
                "hint": sp.get("hint") or (f"Type the {sp['label'].lower()}, or choose above" if options
                                           else f"Type the {sp['label'].lower()} here")}

    def _suggest(self, case: dict, sp: dict) -> Optional[dict]:
        """An answer the record supports, with where it comes from; None when the record says nothing."""
        from src.data import demo_registry
        company = self.companies.get(case["entity_id"]) or {}
        ext = dict(company.get("external_data") or {})
        if self._demo_enabled():
            b = company.get("borrower")
            for k, v in demo_registry.external_data(case["entity_id"], getattr(b, "cin", None)).items():
                ext.setdefault(k, v)
        bureau = (ext.get("bureau_data") or {}).get("payload") or {}
        demo = " (demo data)" if ((ext.get("bureau_data") or {}).get("provenance") or {}).get("via") == "demo_file" else ""
        if sp["id"] == "banking_arrangement" and bureau.get("total_lenders"):
            n = int(bureau["total_lenders"])
            value = "Sole banking" if n <= 1 else "Multiple banking"
            return {"value": value, "reason": f"{n} lender(s) in the bureau report{demo}; choose Consortium if they "
                                              f"lend under a consortium agreement"}
        if sp["id"] == "constitution":
            mca = (ext.get("mca_data") or {}).get("payload") or {}
            cls = str(mca.get("company_class") or "").lower()
            if cls:
                value = ("Public limited (listed)" if "listed" in cls and "unlisted" not in cls else
                         "Public limited (unlisted)" if "public" in cls else "Private limited" if "private" in cls
                         else None)
                if value:
                    return {"value": value, "reason": f"MCA record: {mca['company_class']}"
                            + (" (demo data)" if ((ext.get('mca_data') or {}).get('provenance') or {}).get('via')
                               == "demo_file" else "")}
        return None

    def _incomplete(self, case: dict) -> list[dict]:
        """The credit data fields that are not filled, each with why and who should provide it (fix list E7)."""
        stages = [s["id"] for s in self.stages()]
        here = stages.index(case["stage"]) if case.get("stage") in stages else 0
        past_underwriting = case["status"] != "open" or here > stages.index("credit_risk")
        rm = self.officer(stages[0])
        out = []
        for sp in dpx.specs():
            d = case["dp"].get(sp["id"]) or {}
            status = d.get("status") or "missing"
            if status == "filled":
                continue
            if status == "skipped":
                who = d.get("skipped_by") or rm
                note = f"Not provided — marked by {who}"
                if past_underwriting:
                    note += f"; accepted by {self.officer('credit_risk')} (Underwriting)"
                out.append({"id": sp["id"], "label": sp["label"], "status": "not_provided",
                            "status_label": "Not provided", "note": note, "who": who})
            elif sp.get("agent_only"):
                out.append({"id": sp["id"], "label": sp["label"], "status": "not_available",
                            "status_label": "Not available",
                            "note": sp.get("unavailable") or "No source on record for this figure",
                            "who": "Data agents (needs a connected source)"})
            else:
                out.append({"id": sp["id"], "label": sp["label"], "status": "pending", "status_label": "Pending",
                            "note": ("Required — " if sp.get("required") else "") + f"to be provided by {rm} (RM)",
                            "who": rm})
        return out

    def _missing(self, case: dict, required_only: bool = False) -> list[dict]:
        return [sp for sp in dpx.specs()
                if ((case["dp"].get(sp["id"]) or {}).get("status") in (None, "missing")) and not sp.get("agent_only")
                and (sp.get("required") or not required_only)]

    def set_datapoint(self, case_id: str, session: dict, dp_id: str, value, reason: str = "",
                      via: str = "screen", challenge: str = "") -> dict:
        with self._lock:
            case = self._require(case_id)
            self._set(case, session, dp_id, value, reason, via)
            if challenge:
                sp = dpx.spec(dp_id)
                self._responded(case, session, challenge, "override",
                                f"{sp['label']} → {dpx.display(sp, case['dp'][dp_id]['value'])}"
                                + (f" ({reason.strip()})" if reason.strip() else ""))
            self._ask_next(case)
            self._save(case)
            return case

    def _set(self, case: dict, session: dict, dp_id: str, value, reason: str, via: str) -> Optional[dict]:
        if (dpx.spec(dp_id) or {}).get("computed"):
            raise ForbiddenError(f"{dpx.spec(dp_id)['label']} is calculated by the CAM engine from the statements — "
                                 f"change the underlying figure (e.g. EBITDA, total debt) and re-run the CAM")
        st = self._at_stage(case, session)
        if st["id"] not in ("rm", "credit_risk"):
            raise ForbiddenError("Credit data fields are entered at Origination and overridden at Underwriting — "
                                 "return the proposal to change one")
        if (case.get("cam") or {}).get("state") != "ready":
            raise ConflictError("Generate or ingest the CAM first")
        sp = dpx.spec(dp_id)
        if not sp:
            raise NotFoundError(f"No credit data field {dp_id}")
        try:
            new = dpx.parse_value(sp, value)
        except ValueError as e:
            raise InvalidRequestError(str(e))
        cur = case["dp"].setdefault(dp_id, {"value": None, "source": None, "status": "missing", "history": []})
        old = cur.get("value")
        if cur.get("status") == "filled" and dpx.same(sp, old, new):
            return None
        at, user = self._stamp(), session["user"]
        cur["history"] = (cur.get("history") or []) + [{"value": old, "source": (cur.get("source") or {}).get("label"),
                                                       "at": at}]
        cur.update({"value": new, "status": "filled", "flag": None,
                    "source": {"kind": "person", "label": f"{user['name']} · {self.role_label(user['role'])}",
                               "by": user["id"], "role": user["role"], "at": at, "reason": reason.strip() or None,
                               "via": via, "previous": (cur.get("source") or {}).get("label"),
                               "override": old not in (None, ""),
                               "confidence": dpx.person_confidence() if dpx.numeric(sp) else None}})
        change = None
        if st["id"] == "credit_risk":
            change = self._record_change(case, session, sp, old, new, reason)
        cam = case.get("cam") or {}
        if sp.get("engine") and (cam.get("mode") == "generate" or cam.get("run_id")) and self._can_generate(case):
            case["cam"]["stale"] = True
            case["cam"]["stale_reason"] = f"{sp['label']} changed — re-run the CAM so its analysis uses the new value"
            for offered in (case.get("offered") or {}).values():
                if "rerun" in offered:
                    offered.remove("rerun")
        self._log(case, "edit", session, datapoint=dp_id, old=old, new=new, reason=reason or None, via=via)
        return change

    def _record_change(self, case: dict, session: dict, sp: dict, old, new, reason: str) -> Optional[dict]:
        """An underwriting override the Sanctioning Authority must concur with. Changing the same field again
        updates the pending override; changing it back to the submitted value withdraws it."""
        pending = next((c for c in case["changes"] if c["dp"] == sp["id"] and c["status"] in ("pending", "draft")), None)
        if pending:
            if dpx.same(sp, pending["old"], new):
                case["changes"].remove(pending)
                return None
            pending.update({"new": new, "reason": reason.strip() or pending.get("reason"), "at": self._stamp()})
            return pending
        for c in case["changes"]:
            if c["dp"] == sp["id"] and c["status"] == "disputed":
                c["status"] = "superseded"
        change = {"id": f"CH{len(case['changes']) + 1}", "dp": sp["id"], "label": sp["label"], "type": sp.get("type"),
                  "old": old, "new": new, "reason": reason.strip() or None, "by": session["user"]["id"],
                  "by_name": session["user"]["name"], "at": self._stamp(), "status": "pending",
                  "decided_by": None, "decided_at": None, "comment": None,
                  "period": self._period(case) if sp["group"] == "financials" else None}
        case["changes"].append(change)
        return change

    def _period(self, case: dict) -> Optional[str]:
        fins = (self.companies.get(case["entity_id"]) or {}).get("financials") or {}
        return max(fins) if fins else None

    def skip_datapoint(self, case_id: str, session: dict, dp_id: str) -> dict:
        with self._lock:
            case = self._require(case_id)
            self._skip(case, session, dp_id)
            self._ask_next(case)
            self._save(case)
            return case

    def _skip(self, case: dict, session: dict, dp_id: str) -> None:
        st = self._at_stage(case, session)
        sp = dpx.spec(dp_id) or {}
        cur = case["dp"].get(dp_id) or {}
        if st["id"] == "rm":
            if sp.get("required"):
                raise InvalidRequestError(f"{sp.get('label')} is mandatory and cannot be marked not provided")
            case["dp"][dp_id] = {**cur, "status": "skipped", "skipped_by": session["user"]["name"],
                                 "skipped_at": self._stamp()}
        self._offer(case, st["id"], dp_id)
        self._log(case, "skip", session, datapoint=dp_id)

    @staticmethod
    def _offer(case: dict, stage: str, ref: str) -> None:
        offered = case.setdefault("offered", {}).setdefault(stage, [])
        if ref not in offered:
            offered.append(ref)

    def decide_change(self, case_id: str, session: dict, change_id: str, decision: str, comment: str = "") -> dict:
        with self._lock:
            case = self._require(case_id)
            self._decide(case, session, change_id, decision, comment)
            self._ask_next(case)
            self._save(case)
            return case

    def _decide(self, case: dict, session: dict, change_id: str, decision: str, comment: str) -> dict:
        st = self._at_stage(case, session)
        if st["id"] != "sanction":
            raise ForbiddenError("Underwriting overrides are reviewed by the Sanctioning Authority")
        ch = next((c for c in case["changes"] if c["id"] == change_id), None)
        if not ch or ch["status"] not in ("pending", "accepted", "disputed"):
            raise NotFoundError("No such override to review")
        if decision not in ("accept", "dispute"):
            raise InvalidRequestError("Concur, or return with remarks")
        if decision == "dispute" and not comment.strip():
            raise InvalidRequestError("Add remarks — Underwriting sees them when the proposal is returned")
        ch.update({"status": "accepted" if decision == "accept" else "disputed", "decided_by": session["user"]["name"],
                   "decided_at": self._stamp(), "comment": comment.strip() or None})
        self._log(case, f"change_{decision}", session, change=change_id, datapoint=ch["dp"], comment=comment or None)
        return ch

    # ── key risk challenges (the credit challenge agent) ────────────────────

    def respond(self, case_id: str, session: dict, challenge_id: str, kind: str, note: str = "") -> dict:
        """An officer's answer to a key risk challenge: a written justification (deviation note, mitigants)."""
        with self._lock:
            case = self._require(case_id)
            self._at_stage(case, session)
            if not any(a["id"] == challenge_id for a in case.get("against") or []):
                raise NotFoundError(f"No challenge {challenge_id}")
            if kind == "justify" and not (note or "").strip():
                raise InvalidRequestError("Write the justification — the next approver and the audit trail see it")
            self._responded(case, session, challenge_id, kind, note)
            self._save(case)
            return case

    def _responded(self, case: dict, session: dict, challenge_id: Optional[str], kind: str, note: str = "") -> None:
        a = next((x for x in case.get("against") or [] if x["id"] == challenge_id), None)
        if not a:
            return
        case.setdefault("responses", {})[challenge_id] = {
            "kind": kind, "note": (note or "").strip() or None, "by": session["user"]["name"],
            "role": session["user"]["role"], "stage": case["stage"], "at": self._stamp()}
        self._log(case, "challenge_response", session, challenge=challenge_id, title=a["title"], response=kind,
                  note=(note or "").strip()[:300] or None)
        self._refresh_risks(case)

    # ── deviation register (L1) ──────────────────────────────────────────────

    def _build_register(self, case: dict, engine: Optional[dict]) -> None:
        """One entry per policy breach in the engine's verdict; a re-run keeps what officers recorded
        against a breach that is still there, and drops breaches that are gone."""
        risk = case.get("risk") or {}
        fp = (engine or {}).get("fact_pack") or {}
        authority = (fp.get("approving_authority") or {}).get("name") or self.stage("sanction")["label"]
        deviable_rules = bool((self.cfg().get("deviation_register") or {}).get("hard_rules_deviable"))
        old = {d["id"]: d for d in case.get("register") or []}
        items = []
        for r in risk.get("ratios") or []:
            if r["status"] == "bad":
                items.append({"id": f"ratio:{r['id']}", "kind": "threshold",
                              "label": f"{r['label']} {r['display']} ({r['period']})", "policy": r["limit_display"],
                              "deviable": True})
        for h in (risk.get("hard_rules") or {}).get("failed") or []:
            items.append({"id": f"rule:{h['code']}", "kind": "hard_rule", "label": h["label"] or h["code"],
                          "policy": f"Hard rule {h['code']}" + (f" — {h['detail']}" if h.get("detail") else ""),
                          "deviable": deviable_rules})
        reg = []
        for it in items:
            prev = old.get(it["id"]) or {}
            reg.append({**it, "authority": authority,
                        **{k: prev.get(k) for k in ("mitigant", "justification", "proposed_by", "proposed_at",
                                                    "decided_by", "decided_at", "comment")},
                        "status": prev.get("status") or "open"})
        case["register"] = reg
        self._refresh_deviations(case)

    def _refresh_deviations(self, case: dict) -> None:
        cur = case["dp"].get("deviations") or {}
        if (cur.get("source") or {}).get("kind") == "person":
            return
        status = {"open": "no mitigant recorded", "proposed": "mitigant proposed, awaiting approval",
                  "approved": "approved", "rejected": "rejected"}
        lines = [f"• {d['label']} — {d['policy']} — "
                 + ("not deviable under policy; " if not d["deviable"] else "")
                 + (f"mitigant: {d['mitigant']}; " if d.get("mitigant") else "")
                 + status[d["status"]] + (f" by {d['decided_by']}" if d.get("decided_by") else "")
                 for d in case.get("register") or []]
        case["dp"]["deviations"] = {**cur, "value": "\n".join(lines) or "None", "status": "filled", "source": {
            "kind": "engine", "label": "Deviation register",
            "detail": "Policy breaches found by the CAM engine, with the mitigants and approvals on record"}}

    def deviation(self, case_id: str, session: dict, deviation_id: str, action: str, mitigant: str = "",
                  justification: str = "", comment: str = "") -> dict:
        """Record a mitigant (Origination / Underwriting) or decide a deviation (Sanctioning Authority)."""
        with self._lock:
            case = self._require(case_id)
            st = self._at_stage(case, session)
            d = next((x for x in case.get("register") or [] if x["id"] == deviation_id), None)
            if not d:
                raise NotFoundError(f"No deviation {deviation_id}")
            user = session["user"]
            if action == "propose":
                if st["id"] not in ("rm", "credit_risk"):
                    raise ForbiddenError("Mitigants are recorded at Origination or Underwriting")
                if not mitigant.strip() or not justification.strip():
                    raise InvalidRequestError("Record both the mitigant and the justification")
                d.update({"mitigant": mitigant.strip(), "justification": justification.strip(),
                          "proposed_by": user["name"], "proposed_at": self._stamp(),
                          "status": "proposed" if d["deviable"] else "open",
                          "decided_by": None, "decided_at": None, "comment": None})
            elif action in ("approve", "reject"):
                if st["id"] != "sanction":
                    raise ForbiddenError("Deviations are approved by the Sanctioning Authority")
                if action == "approve" and not d["deviable"]:
                    raise ConflictError(f"{d['label']}: a failed hard rule is not deviable under policy — resolve it "
                                        f"(return for the missing evidence) or decline")
                if action == "approve" and d["status"] != "proposed":
                    raise ConflictError("Underwriting has not recorded a mitigant for this deviation yet")
                if action == "reject" and not comment.strip():
                    raise InvalidRequestError("Add remarks — Underwriting sees them when the proposal is returned")
                d.update({"status": "approved" if action == "approve" else "rejected", "decided_by": user["name"],
                          "decided_at": self._stamp(), "comment": comment.strip() or None})
            else:
                raise InvalidRequestError(f"Unknown action {action}")
            self._log(case, f"deviation_{action}", session, deviation=deviation_id, label=d["label"],
                      mitigant=d.get("mitigant") if action == "propose" else None, comment=comment or None)
            self._refresh_deviations(case)
            self._save(case)
            return case

    def _refresh_risks(self, case: dict) -> None:
        """Risks and mitigants follow the challenges and their answers (unless an officer wrote the field)."""
        cur = case["dp"].get("risks_mitigants") or {}
        if (cur.get("source") or {}).get("kind") == "person" or not case.get("against"):
            return
        text = dpx.risks_text(case["against"], case.get("responses") or {}, case.get("observations") or [])
        case["dp"]["risks_mitigants"] = {**cur, "value": text, "status": "filled", "source": {
            **(cur.get("source") or {}), "kind": "engine", "label": "Credit Challenge Agent · answers on record",
            "detail": "Challenges with the officers' answers, then the engine's observations", "confidence": None}}

    # ── Credit Copilot: who is asked what ────────────────────────────────────

    def _say(self, case: dict, text: str, quick: Optional[list] = None, kind: str = "info",
             stage: Optional[str] = None) -> dict:
        """A Copilot message, addressed to the officer of ``stage`` (default: the stage the proposal is at).
        Officers see messages addressed to them; others see a one-line note (see the screen)."""
        msg = {"id": len(case["chat"]) + 1, "at": self._stamp(), "from": "agent", "name": AGENT,
               "stage": stage or case.get("stage"), "text": text, "quick": quick or [], "kind": kind}
        case["chat"].append(msg)
        return msg

    def _user_said(self, case: dict, session: dict, text: str) -> None:
        u = session["user"]
        case["chat"].append({"id": len(case["chat"]) + 1, "at": self._stamp(), "from": "user", "name": u["name"],
                             "role": u["role"], "stage": self.stage_of_role(u["role"]), "text": text, "quick": [],
                             "kind": "user"})

    def _intro_after_cam(self, case: dict, how: str) -> None:
        total = len(dpx.specs())
        filled = sum(1 for v in case["dp"].values() if v.get("status") == "filled")
        missing = self._missing(case)
        flags = [dpx.spec(k)["label"] for k, v in case["dp"].items() if v.get("flag")]
        text = f"CAM {how}. {filled} of {total} credit data fields auto-populated, each with its source."
        if flags:
            text += f" Verify: {', '.join(flags)} — the CAM differs from the audited statements."
        if missing:
            text += f" Pending: {', '.join(sp['label'] for sp in missing)}."
        self._say(case, text)
        self._ask_next(case)

    def _stale_text(self, case: dict, asking: dict) -> str:
        """Who changed which figure the CAM uses, since it was last generated."""
        since = (case.get("cam") or {}).get("generated_at") or ""
        parts = []
        for sp in dpx.specs():
            d = case["dp"].get(sp["id"]) or {}
            src = d.get("source") or {}
            if sp.get("engine") and src.get("kind") == "person" and (src.get("at") or "") >= since:
                prev = (d.get("history") or [{}])[-1].get("value")
                who = "You" if src.get("by") == asking["user"]["id"] else \
                    f"{src.get('label', '').split(' · ')[0]} ({ROLE_SHORT.get(src.get('role'), src.get('role'))})"
                parts.append(f"{who} changed {_plain(sp['label'])} from {dpx.display(sp, prev)} to "
                             f"{dpx.display(sp, d['value'])}")
        return ("; ".join(parts) + ".") if parts else ((case.get("cam") or {}).get("stale_reason") or "") + "."

    def _ask_next(self, case: dict, session: Optional[dict] = None) -> None:
        """Copilot's next question for the officer the proposal is with; posted once (an unchanged pending
        question is not repeated)."""
        prev = case.get("ask")
        want = self._next_question(case)
        if not want:
            case["ask"] = None
            return
        if prev and prev.get("kind") == want["kind"] and prev.get("ref") == want["ref"] and prev.get("stage") == case["stage"]:
            return
        if want.get("msg_kind", "ask") != "ask":
            last = next((m for m in reversed(case["chat"]) if m.get("from") == "agent" and m.get("stage") == case["stage"]),
                        None)
            if last and last["text"] == want["text"]:         # the same note is not repeated
                case["ask"] = None
                return
        msg = self._say(case, want["text"], quick=want.get("quick"), kind=want.get("msg_kind", "ask"))
        for k in ("upload", "goto", "secondary", "suggested", "hint"):
            if want.get(k):
                msg[k] = want[k]
        case["ask"] = {"stage": case["stage"], "kind": want["kind"], "ref": want["ref"], "text": want["text"],
                       "quick": want.get("quick") or [], "secondary": want.get("secondary") or [],
                       "suggested": want.get("suggested"), "hint": want.get("hint"),
                       "upload": want.get("upload"), "goto": want.get("goto"),
                       "msg": msg["id"]} if want.get("msg_kind", "ask") == "ask" else None

    def _next_question(self, case: dict) -> Optional[dict]:
        if case["status"] != "open":
            return None
        stage = case["stage"]
        offered = set((case.get("offered") or {}).get(stage) or [])
        cam = case.get("cam") or {}
        if stage in ("rm", "credit_risk") and cam.get("state") == "ready" and cam.get("stale") \
                and self._can_generate(case) and "rerun" not in offered:
            officer = next((u for u in self.users() if u["role"] == self.stage(stage)["role"]), {"id": ""})
            return {"kind": "rerun", "ref": "cam",
                    "text": f"{self._stale_text(case, {'user': officer})} Re-run the CAM now? Only the sections that "
                            f"use the changed figures are rewritten.", "quick": ["Yes, re-run", "No, not yet"]}
        if stage == "rm" and case.get("is_prospect") and (case.get("acquisition") or {}).get("state") == "done" \
                and cam.get("state") in (None, "none", "failed"):
            q = self._source_question(case, offered)
            if q:
                return q
        if stage == "rm" and cam.get("state") == "ready":
            for sp in sorted(self._missing(case), key=lambda s: not s.get("required")):
                if sp["id"] not in offered:
                    return self._dp_question(case, sp)
            if not self._missing(case, required_only=True) and not cam.get("stale"):
                return {"kind": "none", "ref": "rm_ready", "msg_kind": "done",
                        "text": "All mandatory credit data fields are complete. Review the proposal and submit it "
                                "for underwriting."}
        elif stage == "credit_risk":
            for sp in dpx.specs():
                d = case["dp"].get(sp["id"]) or {}
                if d.get("status") == "skipped" and sp["id"] not in offered:
                    return {"kind": "dp", "ref": sp["id"],
                            "text": f"{sp['label']} was not provided at Origination ({d.get('skipped_by') or 'RM'}). "
                                    f"Add it now? {sp.get('ask') or ''}", "quick": ["Leave as not provided"]}
        elif stage == "sanction":
            for ch in case["changes"]:
                if ch["status"] == "pending":
                    return {"kind": "change", "ref": ch["id"], "text": self._change_text(ch) + " Concur?",
                            "quick": ["Concur", "Return with remarks"]}
            if any(c["status"] == "disputed" for c in case["changes"]):
                return {"kind": "none", "ref": "disputed", "msg_kind": "warn",
                        "text": "An override is returned with remarks, so Sanction stays disabled. Return the "
                                "proposal to Underwriting, or concur if your view has changed."}
            if case["changes"]:
                return {"kind": "none", "ref": "concurred", "msg_kind": "done",
                        "text": "All underwriting overrides are concurred — Sanction is enabled."}
        elif stage == "cad":
            return self._cad_question(case)
        return None

    def _source_question(self, case: dict, offered: set) -> Optional[dict]:
        """The next document the RM is asked for: required sources first (those the CAM needs before the
        rest), then recommended ones (which can be skipped); then the go-ahead to generate the CAM."""
        acq = case["acquisition"]
        srcs = acq.get("sources") or {}
        minimum = self._minimum_for_cam()
        order = [s["id"] for s in self.acquirer.sources()] if self.acquirer else list(srcs)
        rank = {"required": 0, "recommended": 1}
        pending = sorted((srcs[i] for i in order if i in srcs and srcs[i]["status"] not in ("fetched", "read")
                          and srcs[i].get("requirement") in rank),
                         key=lambda s: (rank[s["requirement"]], s["id"] not in minimum, order.index(s["id"])))
        for s in pending:
            if s["id"] in offered:
                continue
            if s["status"] == "match":
                return {"kind": "none", "ref": f"src_{s['id']}", "msg_kind": "warn",
                        "text": f"Sanctions screening found a potential match ({s.get('summary')}). Compliance must "
                                f"clear it before the CAM is generated."}
            if not s.get("upload"):
                continue
            why = s.get("mode_reason") or "API not connected"
            err = f" ({s['error']})" if s.get("status") in ("failed", "rejected") and s.get("error") else ""
            optional = s["requirement"] != "required"
            return {"kind": "source_doc", "ref": s["id"],
                    "text": f"{s['label']}: {why}{err}. Upload {s['upload'].get('ask')} here and the "
                            f"{(self.acquirer.agents().get(s['agent']) or {}).get('label', 'agent')} reads it."
                            + (" (Recommended — it can be skipped.)" if optional else ""),
                    "quick": ["Skip for now"] if optional or s["id"] not in minimum else []}
        if self._can_generate(case):
            checks = acq.get("verification") or []
            review = [c for c in checks if c["status"] in ("warn", "fail")]
            api_n = sum(1 for s in srcs.values() if s["status"] == "fetched")
            doc_n = sum(1 for s in srcs.values() if s["status"] == "read")
            return {"kind": "generate", "ref": f"gen_{acq.get('runs', 0)}",
                    "text": f"The data needed for the CAM is in: {api_n} source(s) via API, {doc_n} from documents. "
                            f"{len(checks) - len(review)} verification check(s) passed"
                            + (f", {len(review)} for your review in the Data Sources panel" if review else "")
                            + ". Generate the CAM now?", "quick": ["Yes, generate", "Not yet"]}
        return None

    def _change_text(self, ch: dict) -> str:
        sp = dpx.spec(ch["dp"]) or {"type": ch.get("type"), "label": ch["label"]}
        what = f"{ch['period']} {_plain(ch['label'])}" if ch.get("period") else _plain(ch["label"])
        old = dpx.display(sp, ch["old"]) if ch["old"] not in (None, "") else "(not provided at Origination)"
        text = f"Underwriting override by {ch['by_name']}: {what} {old} → {dpx.display(sp, ch['new'])}."
        return text + (f" Rationale: {ch['reason']}." if ch.get("reason") else " No rationale recorded.")

    def _enter_stage(self, case: dict, prev: dict, how: str, session: dict, comment: str = "") -> None:
        """Copilot's note to the officer who acted, and its opening for the officer the proposal reached."""
        st = self.stage(case["stage"])
        who = session["user"]["name"]
        to = f"{self.officer(st['id'])} · {st['label']}"
        if how == "send_back":
            self._say(case, f"Returned to {to}.", stage=prev["id"], kind="done")
            self._say(case, f"Returned by {who} ({prev['label']}) with remarks: “{comment}”.", kind="warn")
            for ch in case["changes"]:
                if ch["status"] == "disputed":
                    self._say(case, f"Returned override — {self._change_text(ch)} Remarks from {ch['decided_by']}: "
                                    f"“{ch['comment']}”.", kind="warn")
            self._ask_next(case)
            return
        pend = [c for c in case["changes"] if c["status"] == "pending"]
        note = {"credit_risk": "", "sanction": f" with {len(pend)} underwriting override(s) for concurrence" if pend else "",
                "cad": "", "disbursement": ""}.get(st["id"], "")
        self._say(case, f"Submitted to {to}{note}.", stage=prev["id"], kind="done")
        if st["id"] == "credit_risk":
            skipped = [dpx.spec(k)["label"] for k, v in case["dp"].items() if v.get("status") == "skipped"]
            filled = sum(1 for v in case["dp"].values() if v.get("status") == "filled")
            text = (f"Proposal from {who} (Origination): {case['borrower_name']} — {self._fac_text(case['facility'])}. "
                    f"{filled} of {len(dpx.specs())} credit data fields complete.")
            if skipped:
                text += f" Not provided at Origination: {', '.join(skipped)}."
            self._say(case, text)
            self._risk_note(case)
            self._say(case, "Overrides can be made on screen or here, e.g. “change EBITDA to 35900 because one-off "
                            "gain excluded”. Each override goes to the Sanctioning Authority for concurrence.")
        elif st["id"] == "sanction":
            self._say(case, f"Recommended for sanction by {who}: {case['borrower_name']} — "
                            f"{self._fac_text(case['facility'])}, recommended limit "
                            f"{dpx.display({'type': 'amount'}, self._value(case, 'recommended_cr') or None)}. "
                      + (f"{len(pend)} underwriting override(s) need your concurrence before Sanction is enabled."
                         if pend else "No overrides after Origination."))
            self._risk_note(case)
        elif st["id"] == "cad":
            s = case["sanction"]
            cps = [c for c in case["conditions"] if c["when"] == "precedent" and c["status"] != "not_applicable"]
            css = [c for c in case["conditions"] if c["when"] == "subsequent" and c["status"] != "not_applicable"]
            auto = [c for c in cps if c["status"] == "auto"]
            na = [c for c in case["conditions"] if c["status"] == "not_applicable"]
            text = (f"Sanctioned by {who}: {_cr(s['limit_cr'])}, valid until {s['valid_until']}. Sanction letter "
                    f"drafted. {len(cps)} condition(s) precedent before release"
                    + (f" ({len(auto)} already met from the record)" if auto else "")
                    + (f"; {len(css)} condition(s) subsequent tracked after release" if css else "")
                    + (f"; not applicable: {', '.join(c['label'] for c in na)}" if na else "") + ". "
                    f"Disbursement request of {_cr(case['drawdown']['amount_cr'])} prepared.")
            self._say(case, text)
        elif st["id"] == "disbursement":
            checks = self.release_checks(case)
            ok = sum(1 for c in checks if c["ok"])
            self._say(case, f"Disbursement request from {who}: {_cr(case['drawdown']['amount_cr'])} to "
                            f"{case['drawdown']['account']}, value date {_day(case['drawdown']['value_date'])}. "
                            f"Pre-disbursement compliance: {ok} of {len(checks)} checks pass"
                            + ("." if ok == len(checks) else " — review before release."))
        self._ask_next(case)

    def _risk_note(self, case: dict) -> None:
        """What the officer the proposal reached must weigh: the engine's verdict, deviations recorded so far
        and the open challenges — with a pointer to the plan."""
        r = case.get("risk")
        if r and r.get("tone") in ("bad", "warn"):
            bad = [f"{x['label']} {x['display']} ({x['limit_display']})" for x in r["ratios"] if x["status"] == "bad"]
            self._say(case, f"CAM engine verdict: {r['label']} (internal rating {r.get('rating') or '—'})."
                      + (f" Hard rule(s) failed: {', '.join(h['label'] for h in r['hard_rules']['failed'])}."
                         if r["hard_rules"]["failed"] else "")
                      + (f" Outside policy: {'; '.join(bad)}." if bad else ""), kind="warn" if r["tone"] == "bad" else "info")
        for d in case.get("deviations") or []:
            if d.get("noted_to") != case["stage"]:
                self._say(case, f"{d['by']} ({d['stage_label']}) proceeded despite {'; '.join(d['reasons'])}. "
                                f"Justification: “{d['text']}”.", kind="warn")
                d["noted_to"] = case["stage"]
        reg = case.get("register") or []
        if reg:
            todo = [d for d in reg if d["status"] in ("open", "rejected") and d["deviable"]]
            pend = [d for d in reg if d["status"] == "proposed"]
            hard = [d for d in reg if not d["deviable"]]
            self._say(case, f"Deviation register: {len(reg)} policy breach(es)"
                      + (f"; {len(todo)} without a mitigant" if todo else "")
                      + (f"; {len(pend)} with a mitigant awaiting the Sanctioning Authority" if pend else "")
                      + (f"; {len(hard)} failed hard rule(s), not deviable" if hard else "") + ".",
                      kind="warn" if todo or hard else "info")
        open_ = [a for a in case.get("against") or [] if a["id"] not in (case.get("responses") or {})]
        if open_:
            self._say(case, f"Key risk challenges open ({len(open_)}): "
                      + " · ".join(f"{a['title']} ({str(a.get('severity') or '').lower()})" for a in open_)
                      + ". Ask “What should I do next?” for the steps, or use the buttons on each challenge.")

    def _plan(self, case: dict, session: dict, focus: Optional[str] = None) -> None:
        st = self.stage(case["stage"])
        mine = case["status"] == "open" and st["role"] == session["user"]["role"]
        if not mine:
            self._say(case, f"The proposal is with {self.officer(st['id'])} ({st['label']}); nothing is pending for "
                            f"you." if case["status"] == "open" else "The proposal is closed; nothing is pending.",
                      stage=self.stage_of_role(session["user"]["role"]), kind="answer")
            return
        editable = st["id"] in ("rm", "credit_risk") and (case.get("cam") or {}).get("state") == "ready"
        checks_view = chk.view(case.get("checks"), case.get("check_notes"))
        verdict = rk.verdict(case.get("risk"), checks_view,
                             f"{self.officer('sanction')} ({self.stage('sanction')['label']})")
        text, buttons = rk.plan(st["id"], st.get("actions") or [], case.get("risk"), case.get("against") or [],
                                case.get("responses") or {}, self.blockers(case, st), editable, focus,
                                case.get("register") or [], labels=self._labels(st), checks=checks_view,
                                standing=(f"{verdict['label']}. {verdict['text']}" if verdict else None))
        msg = self._say(case, text, kind="answer")
        msg["actions"] = buttons
        self._log(case, "chat_question", session, question="next steps", answered_by="plan")

    def _labels(self, st: dict) -> dict:
        """The stage's action buttons as the screen labels them."""
        labels = dict(st.get("labels") or {})
        labels.setdefault("approve", "Approve")
        labels.setdefault("reject", "Decline")
        if st.get("send_back_to"):
            labels.setdefault("send_back", f"Return to {self.stage(st['send_back_to'])['label']}")
        return labels

    def _amount(self, case: dict, session: dict) -> None:
        r = case.get("risk") or {}
        text = rk.amount_text(r.get("headroom"))
        h = r.get("headroom") or {}
        st = self.stage(case["stage"])
        msg = self._say(case, text, kind="answer", stage=self.stage_of_role(session["user"]["role"]))
        mine = case["status"] == "open" and st["role"] == session["user"]["role"]
        if mine and st["id"] in ("rm", "credit_risk"):
            act = rk.structure_action(h)
            if act:
                msg["actions"] = [act]
            elif h and not h["fits"]:
                msg["actions"] = [b for b in ({"kind": "send_back", "label": "Return for a deleveraging plan",
                                               "prefill": "Leverage is above policy at any amount: provide a deleveraging "
                                                          "plan (equity infusion / debt reduction) and the lender-wise "
                                                          "debt schedule."},
                                              {"kind": "reject", "label": "Decline",
                                               "prefill": "Declined: leverage above policy at any amount."})
                                  if b["kind"] in (st.get("actions") or [])]
        self._log(case, "chat_question", session, question="amount check", answered_by="engine")

    def chat(self, case_id: str, session: dict, message: str) -> dict:
        text = (message or "").strip()
        if not text:
            raise InvalidRequestError("Type a message")
        with self._lock:
            case = self._require(case_id)
            self._user_said(case, session, text[:1000])
            try:
                self._handle(case, session, text[:1000])
            except (InvalidRequestError, ForbiddenError, ConflictError, NotFoundError) as e:
                self._say(case, str(e), kind="warn")
            then = case.pop("_then", None)
            self._save(case)
        if then == "rerun":
            self.generate_cam(case_id, session)
        elif then == "submit":
            try:
                self.act(case_id, session, "approve", "Submitted via Credit Copilot")
            except (ConflictError, InvalidRequestError) as e:
                with self._lock:
                    case = self._require(case_id)
                    self._say(case, str(e), kind="warn")
                    self._save(case)
        return self._require(case_id)

    def _handle(self, case: dict, session: dict, text: str) -> None:
        low = text.lower().strip(" .!")
        mine = case["status"] == "open" and self.stage(case["stage"])["role"] == session["user"]["role"]
        ask = case.get("ask") if mine and (case.get("ask") or {}).get("stage") == case.get("stage") else None
        kind = (ask or {}).get("kind")
        if kind == "change_reason":
            ch = next(c for c in case["changes"] if c["id"] == ask["ref"])
            ch["reason"] = text
            case["ask"] = None
            self._say(case, f"Rationale recorded for the Sanctioning Authority: “{text}”.")
            self._ask_next(case)
            return
        if kind == "dispute_reason":
            self._decide(case, session, ask["ref"], "dispute", text)
            case["ask"] = None
            self._say(case, "Override returned with your remarks.")
            self._ask_next(case)
            return
        if kind == "source_doc" and (low.startswith("skip") or low in NO_WORDS or low.startswith("not now")):
            src = ((case.get("acquisition") or {}).get("sources") or {}).get(ask["ref"]) or {}
            self._offer(case, case["stage"], ask["ref"])
            case["ask"] = None
            self._say(case, f"{src.get('label', ask['ref'])} skipped for now — add it from the Data Sources panel "
                            f"any time" + (" (it is required before submission)." if src.get("requirement") == "required"
                                           else "."))
            self._ask_next(case)
            return
        if kind == "generate" and (low in YES_WORDS or low.startswith("yes")):
            case["ask"] = None
            self._say(case, "Generating the CAM with the CAM engine.")
            case["_then"] = "rerun"
            return
        if kind == "generate" and (low in NO_WORDS or low.startswith("no") or low.startswith("not")):
            self._offer(case, case["stage"], ask["ref"])
            case["ask"] = None
            self._say(case, "Understood — generate it from the CAM card when ready.")
            return
        if kind == "rerun" and (low in YES_WORDS or low.startswith("yes")):
            case["ask"] = None
            self._say(case, "Re-running the CAM — only the sections that use the changed figures are rewritten.")
            case["_then"] = "rerun"
            return
        if kind == "rerun" and (low in NO_WORDS or low.startswith("no")):
            self._offer(case, case["stage"], "rerun")
            case["ask"] = None
            self._say(case, "The CAM stays out of date; submission is blocked until it is re-run (Re-run CAM).",
                      kind="warn")
            self._ask_next(case)
            return
        m = _EDIT.match(text)
        if m and mine and case["stage"] in ("rm", "credit_risk"):
            sp = self._match_datapoint(m.group(1))
            if sp:
                value, reason = m.group(2).strip(), (m.group(3) or "").strip()
                change = self._set(case, session, sp["id"], value, reason, "chat")
                d = case["dp"][sp["id"]]
                self._say(case, f"{sp['label']} updated to {dpx.display(sp, d['value'])}.")
                if change and not change.get("reason"):
                    case["ask"] = {"stage": case["stage"], "kind": "change_reason", "ref": change["id"],
                                   "text": "State the rationale for this override (the Sanctioning Authority sees it).",
                                   "quick": []}
                    self._say(case, case["ask"]["text"], kind="ask")
                    return
                self._ask_next(case)
                return
        if kind == "dp":
            sp = dpx.spec(ask["ref"])
            if low in SKIP_WORDS or low.startswith(("skip", "leave", "not provided")):
                self._skip(case, session, sp["id"])
                self._say(case, f"{sp['label']}: marked not provided.")
                self._ask_next(case)
                return
            if not self._is_question(text):
                self._set(case, session, sp["id"], text, "", "chat")
                self._offer(case, case["stage"], sp["id"])
                self._say(case, f"{sp['label']} recorded: {dpx.display(sp, case['dp'][sp['id']]['value'])}.")
                self._ask_next(case)
                return
        if kind == "change":
            if low in CONCUR_WORDS:
                self._decide(case, session, ask["ref"], "accept", "")
                self._say(case, "Concurred.")
                self._ask_next(case)
                return
            if low in RETURN_WORDS or low.startswith(("return", "dispute")):
                case["ask"] = {"stage": case["stage"], "kind": "dispute_reason", "ref": ask["ref"],
                               "text": "State your remarks — Underwriting sees them when the proposal is returned.",
                               "quick": []}
                self._say(case, case["ask"]["text"], kind="ask")
                return
        if kind == "cond_confirm":
            cond = self._cond(case, ask["ref"])
            if low in YES_WORDS or low.startswith("yes"):
                self._confirm(case, session, cond, "Verified against the original by CAD (Credit Copilot)")
                self._say(case, f"{cond['label']}: confirmed. {self._cp_progress(case)}")
                self._ask_next(case)
                return
            if low in NO_WORDS or low.startswith("no"):
                self._offer(case, case["stage"], f"confirm:{cond['id']}")
                case["ask"] = None
                self._say(case, f"{cond['label']} stays open — upload a corrected document.", kind="warn")
                self._ask_next(case)
                return
        if kind == "cond_doc" and low.startswith(("add demo", "demo")):
            self._demo_documents(case, session)
            return
        if kind == "submit_release":
            if low in YES_WORDS or low.startswith("yes"):
                case["ask"] = None
                case["_then"] = "submit"
                return
            if low in NO_WORDS or low.startswith(("no", "edit")):
                self._offer(case, case["stage"], "submit_release")
                case["ask"] = None
                self._say(case, "Adjust the disbursement request on screen, then submit it.")
                return
        if _PLAN.search(text):
            focus = re.sub(r"^.*?answer:\s*", "", text).rstrip("?") if "answer:" in low else None
            self._plan(case, session, focus)
            return
        if _AMOUNT.search(text) and (case.get("risk") or {}).get("headroom"):
            self._amount(case, session)
            return
        self._answer(case, session, text)

    @staticmethod
    def _is_question(text: str) -> bool:
        t = text.strip().lower()
        return t.endswith("?") or t.startswith(_QUESTION_START)

    @staticmethod
    def _match_datapoint(phrase: str) -> Optional[dict]:
        def norm(s):
            s = re.sub(r"\(.*?\)|fy\s?\d{2,4}|the|latest|year|'s", " ", s.lower())
            return " ".join(re.findall(r"[a-z0-9]+", s))

        p = norm(phrase)
        if not p:
            return None
        best = None
        for sp in dpx.specs():
            names = {norm(sp["label"]), norm(sp["id"].replace("_cr", "").replace("_", " "))}
            if p in names:
                return sp
            if any(n and (p in n or n in p) for n in names):
                best = best or sp
        return best

    def _answer(self, case: dict, session: dict, question: str) -> None:
        from src.flow import copilot as cp

        llm = None
        if self.llm_factory:
            try:
                llm = self.llm_factory()
            except Exception:
                llm = None
        rec = self._record(case)
        st = self.stage(case["stage"])
        rec["asked_by"] = {"role": self.role_label(session["user"]["role"]),
                           "proposal_is_with_them": case["status"] == "open" and st["role"] == session["user"]["role"],
                           # the real buttons, by their screen labels and where they are (fix list E4)
                           "actions_available_on_screen": [
                               f"“{self._labels(st).get(a, a)}” — action bar" for a in st.get("actions") or []]
                           + (["“Edit” on a credit data field (with rationale) — Credit Data Fields"]
                              if st["id"] == "credit_risk" else [])
                           + (["“Record justification” — Key Risk Challenges card, under the challenge"]
                              if case.get("against") else [])
                           + (["“Record verification” / “Proceed with justification” — Mandatory checks card"]
                              if any(i.get("open") for i in (chk.view(case.get("checks"), case.get("check_notes"))
                                                             or {}).get("items") or []) else [])}
        out = cp.ask(question, cp.clean(rec), llm, system_prompt=cp.ADVISE_SYSTEM_PROMPT)
        text = out["answer"]
        if out.get("mode") != "ai" and out.get("note"):
            text += f"\n\n({out['note']})"
        msg = self._say(case, text, kind="answer", stage=self.stage_of_role(session["user"]["role"]))
        msg["provenance"] = out.get("mode")
        self._log(case, "chat_question", session, question=question[:300], answered_by=out.get("mode"))

    def _record(self, case: dict) -> dict:
        """What Copilot may answer from: this proposal's fields, overrides, checks and the CAM engine's view."""
        rec = {"borrower": case["borrower_name"], "stage": self.stage(case["stage"])["label"], "status": case["status"],
               "facility_requested": case["facility"],
               "credit_data_fields": {sp["label"]: (case["dp"].get(sp["id"]) or {}).get("value") for sp in dpx.specs()},
               "not_provided_at_origination": [dpx.spec(k)["label"] for k, v in case["dp"].items()
                                               if v.get("status") == "skipped"],
               "underwriting_overrides": [{k: c[k] for k in ("label", "old", "new", "reason", "status", "by_name")}
                                          for c in case["changes"]],
               "key_risk_challenges": [{"title": a["title"], "severity": a["severity"], "what": a["what"],
                                        "why": a["why"], "required_response": a.get("asks"),
                                        "suggested_actions": [x["label"] for x in a.get("actions") or []],
                                        "answered": (case.get("responses") or {}).get(a["id"])}
                                       for a in case.get("against") or []],
               "risk_assessment": {k: v for k, v in (case.get("risk") or {}).items()
                                   if k not in ("run_id", "thresholds")} or None,
               "mandatory_checks": [{"check": i["label"], "result": i["status_label"], "detail": i["detail"],
                                     "source": i["source"] or None, "evidence_that_clears_it": i["evidence"]
                                     if i["status"] != "pass" else None,
                                     "recorded": (f"{i['note']['kind']} by {i['note']['by']}: {i['note']['note']}"
                                                  if i.get("note") else None)}
                                    for i in (chk.view(case.get("checks"), case.get("check_notes")) or {}).get("items") or []],
               "deviations": [{k: d[k] for k in ("by", "stage_label", "reasons", "text")}
                              for d in case.get("deviations") or []],
               "deviation_register": [{k: d.get(k) for k in ("label", "policy", "deviable", "mitigant", "justification",
                                                             "status", "authority", "decided_by")}
                                      for d in case.get("register") or []],
               "cam": {k: v for k, v in (case.get("cam") or {}).items()
                       if k in ("mode", "state", "generated_at", "stale_reason")}}
        engine = self.cases.get(case["entity_id"]) if self.cases else None
        if engine and (case.get("cam") or {}).get("run_id") == engine.get("run_id"):
            rec["engine"] = {"risk_grade": engine.get("risk_grade"), "recommendation": engine.get("recommendation"),
                             "rationale": engine.get("rationale"), "conditions": engine.get("conditions"),
                             "covenants": engine.get("covenants_proposed"),
                             "ratios": ((engine.get("fact_pack") or {}).get("ratio_analysis") or {})}
        acq = case.get("acquisition") or {}
        if acq.get("sources"):
            rec["data_sources"] = [{"source": s["label"], "how": {"fetched": "via API", "read": "from document"}.get(
                s["status"], s["status"]), "provider": s.get("provider"), "requirement": s.get("requirement"),
                "summary": s.get("summary"), "documents": s.get("documents")} for s in acq["sources"].values()]
            rec["verification_checks"] = [{k: c[k] for k in ("label", "status", "detail")}
                                          for c in acq.get("verification") or []]
            rec["audited_financials_cr"] = {s["period"]: {k: s["items"].get(k) for k in (
                "revenue_operating", "other_income", "ebitda", "pat", "total_equity", "total_debt", "current_assets",
                "current_liabilities", "inventory", "trade_receivables", "ocf")} for s in acq.get("statements") or []}
        if case.get("sanction"):
            rec["sanction"] = case["sanction"]
            rec["conditions"] = [{"condition": c["label"], "type": "precedent" if c["when"] == "precedent" else "subsequent",
                                  "status": c["status"], "due": c.get("due")} for c in case["conditions"]]
            rec["disbursement_request"] = self._drawdown_record(case)
        return rec

    def _drawdown_record(self, case: dict) -> Optional[dict]:
        """The disbursement request for the Copilot: people named, nothing empty (fix list E9)."""
        d = case.get("drawdown")
        if not d:
            return None
        out = {"amount_cr": d.get("amount_cr"), "account": d.get("account"), "value_date": d.get("value_date"),
               "purpose": d.get("purpose"),
               "drafted": "by the agent from the sanction terms"}
        if d.get("submitted_by"):
            out["submitted"] = (f"by {d['submitted_by']} ({d.get('submitted_role') or 'CAD'}) on "
                                f"{d.get('submitted_at')}")
        else:
            out["submitted"] = f"not yet — with {self.officer('cad')} (CAD)"
        edits = d.get("edits") or []
        out["edited"] = ("; ".join(f"by {e['by']} on {e['at']}: amount_cr {e['amount_cr']}, value date {e['value_date']}"
                                   for e in edits) if edits else
                         f"by {d['edited_by']}" if d.get("edited_by") else "no — as drafted")
        return out

    def _suggestions(self, case: dict, session: dict) -> list[str]:
        """Two suggested questions for this officer; one already asked on this proposal is replaced by the next."""
        role = session["user"]["role"]
        asked = {m["text"].strip().lower() for m in case.get("chat") or [] if m.get("from") == "user"}
        pool = list(SUGGESTIONS.get(role, []))
        if role == "rm" and case.get("acquisition") and (case.get("cam") or {}).get("state") != "ready":
            pool[:0] = ["What did the agents find?", "Which verification checks need review?"]
        if role in ("credit_risk", "sanctioning_authority") and case.get("against"):
            pool.insert(1, f"How do we answer: {case['against'][0]['title']}?")
        r = case.get("risk") or {}
        if role in ("rm", "credit_risk") and r.get("headroom") and not r["headroom"]["fits"]:
            pool.insert(0, "Should the amount be reduced?")
        if role != "cad" and (case.get("against") or r.get("tone") == "bad") and case["status"] == "open":
            pool.insert(0, "What should I do next?")
        return [q for q in pool if q.lower() not in asked][:2]

    # ── actions ──────────────────────────────────────────────────────────────

    def blockers(self, case: dict, stage: Optional[dict] = None) -> list[str]:
        st = stage or self.stage(case["stage"])
        out = [f"Clarification {q['id']} awaits {q['to_name']} ({q['to_label']})" for q in self._open_queries(case)
               if q["stage"] == st["id"]]
        cam = case.get("cam") or {}
        if st["id"] == self.stages()[0]["id"] and case.get("is_prospect") and case.get("acquisition"):
            srcs = case["acquisition"].get("sources") or {}
            need = [s["label"] for s in srcs.values()
                    if s.get("requirement") == "required" and s["status"] not in ("fetched", "read")]
            if need:
                out.append("Required data sources pending: " + ", ".join(need))
            if any(c["status"] == "fail" for c in case["acquisition"].get("verification") or []):
                out.append("Data verification failed: " + "; ".join(
                    c["label"] for c in case["acquisition"]["verification"] if c["status"] == "fail"))
        for g in st.get("gates") or []:
            if g == "cam_ready" and cam.get("state") != "ready":
                out.append("Generate or ingest the CAM" if cam.get("state") != "running" else
                           "CAM generation in progress")
            elif g == "cam_current" and cam.get("stale"):
                out.append("CAM out of date — " + (cam.get("stale_reason") or "re-run it"))
            elif g == "required_answered" and cam.get("state") == "ready":
                miss = self._missing(case, required_only=True)
                if miss:
                    out.append("Mandatory fields pending: " + ", ".join(sp["label"] for sp in miss))
            elif g == "changes_accepted":
                pend = [c for c in case["changes"] if c["status"] == "pending"]
                disp = [c for c in case["changes"] if c["status"] == "disputed"]
                if pend:
                    out.append(f"{len(pend)} underwriting override(s) awaiting concurrence")
                if disp:
                    out.append(f"{len(disp)} override(s) returned with remarks — return the proposal to Underwriting")
            elif g == "deviations_proposed":
                reg = case.get("register") or []
                todo = [d for d in reg if d["deviable"] and d["status"] in ("open", "rejected")]
                if todo:
                    out.append(f"{len(todo)} policy deviation(s) need a mitigant and justification: "
                               + "; ".join(d["label"] for d in todo[:3]) + ("…" if len(todo) > 3 else ""))
            elif g == "deviations_approved":
                reg = case.get("register") or []
                hard = [d for d in reg if not d["deviable"]]
                if hard:
                    out.append("Hard rule failed — not deviable under policy: "
                               + "; ".join(d["label"] for d in hard) + ". Return for the evidence, or decline")
                pend = [d for d in reg if d["deviable"] and d["status"] != "approved"]
                if pend:
                    out.append(f"{len(pend)} policy deviation(s) awaiting your approval")
            elif g == "conditions_met":
                open_ = [c["label"] for c in self._cps(case) if c["status"] not in MET]
                if open_:
                    out.append(f"{len(open_)} condition(s) precedent open: " + "; ".join(open_[:3])
                               + ("…" if len(open_) > 3 else ""))
            elif g == "drawdown_ready":
                d, s = case.get("drawdown") or {}, case.get("sanction") or {}
                if not d or float(d.get("amount_cr") or 0) <= 0:
                    out.append("Prepare the disbursement request")
                elif float(d["amount_cr"]) > float(s.get("limit_cr") or 0) + 1e-6:
                    out.append("Disbursement request exceeds the sanctioned limit")
            elif g == "release_checks":
                bad = [c["label"] for c in self.release_checks(case) if not c["ok"]]
                if bad:
                    out.append("Compliance checks failing: " + "; ".join(bad))
        return out

    @staticmethod
    def _cam_section_count() -> int:
        from src.engines.cam_sections import active_sections
        return sum(1 for s in active_sections() if not s.get("skip_llm"))

    def _justify(self, case: dict) -> list[str]:
        """Why moving this proposal forward needs a justification: only before sanction."""
        return [] if case.get("sanction") else rk.needs_justification(case.get("risk"))

    def act(self, case_id: str, session: dict, action: str, comment: str = "", challenge: str = "") -> dict:
        with self._lock:
            case = self._require(case_id)
            st = self._at_stage(case, session)
            if action not in st.get("actions") or []:
                raise InvalidRequestError(f"“{action}” is not available at {st['label']}")
            if self.jobs.running(case_id):
                raise ConflictError("Wait for the CAM run to finish")
            comment = (comment or "").strip()
            stages = self.stages()
            idx = next(i for i, s in enumerate(stages) if s["id"] == st["id"])
            if action == "approve":
                blocked = self.blockers(case, st)
                if blocked:
                    raise ConflictError("Not yet: " + " · ".join(blocked))
                why = self._justify(case)
                if why and not comment:
                    raise InvalidRequestError("A written justification is required because " + "; ".join(why))
                if why:
                    case.setdefault("deviations", []).append({
                        "stage": st["id"], "stage_label": st["label"], "by": session["user"]["name"],
                        "role": session["user"]["role"], "at": self._stamp(), "reasons": why, "text": comment})
                self._on_approve(case, st, session)
                if idx + 1 < len(stages):
                    self._enter(case, stages[idx + 1]["id"])
                else:
                    case["status"] = "disbursed"
                    self._close_stage(case)
            elif action in ("reject", "send_back"):
                if not comment:
                    raise InvalidRequestError("Add remarks — they are recorded and shown to the next officer")
                for q in self._open_queries(case):          # the proposal moves on: its open questions close
                    q.update(status="closed", closed_note="Proposal " + ("declined" if action == "reject" else "returned"))
                if action == "reject":
                    case["status"] = "rejected"
                    self._close_stage(case)
                else:
                    self._enter(case, st.get("send_back_to") or stages[max(idx - 1, 0)]["id"])
                    case.setdefault("offered", {}).pop(case["stage"], None)
            case["ask"] = None
            if challenge and action in ("send_back", "reject"):
                self._responded(case, session, challenge, action, comment)
            case["decisions"].append({"stage": st["id"], "stage_label": st["label"], "action": action,
                                      "by": session["user"]["name"], "role": session["user"]["role"],
                                      "at": self._stamp(), "comment": comment or None})
            self._log(case, action, session, from_stage=st["id"], to_stage=case["stage"], comment=comment or None,
                      status=case["status"])
            if case["status"] == "open":
                self._enter_stage(case, st, "send_back" if action == "send_back" else action, session, comment)
            elif case["status"] == "rejected":
                self._say(case, f"Declined by {session['user']['name']} ({st['label']}): “{comment}”.", kind="warn",
                          stage=st["id"])
            else:
                r = case["release"]
                self._apply_due_dates(case)
                cs = [c for c in case["conditions"] if c["when"] == "subsequent" and c["status"] not in MET + ("not_applicable",)]
                self._say(case, f"Released {_cr(r['amount_cr'])} to {r['account']} (UTR {r['reference']}). Proposal "
                                f"disbursed." + (f" Conditions subsequent to track: "
                                                 + "; ".join(f"{c['label']} by {c['due']}" for c in cs) if cs else ""),
                          kind="done", stage=st["id"])
            self._save(case)
            return case

    def _on_approve(self, case: dict, st: dict, session: dict) -> None:
        if st["id"] == "rm":
            case["submitted"] = {k: (v or {}).get("value") for k, v in case["dp"].items()}
        elif st["id"] == "credit_risk":
            for ch in case["changes"]:
                if ch["status"] == "disputed":
                    ch["status"] = "pending"          # unchanged after the return: the SA decides again
                    ch["comment_before"] = ch.pop("comment", None)
        elif st["id"] == "sanction":
            self._sanction(case, session)
        elif st["id"] == "cad" and case.get("drawdown"):
            case["drawdown"]["submitted_by"] = session["user"]["name"]
            case["drawdown"]["submitted_role"] = self.role_label(session["user"]["role"])
            case["drawdown"]["submitted_at"] = self._stamp()
        elif st["id"] == "disbursement":
            d = case["drawdown"]
            case["release"] = {"at": self._stamp(), "by": session["user"]["name"], "amount_cr": d["amount_cr"],
                               "account": d["account"], "reference": "UTR" + secrets.token_hex(5).upper(),
                               "note": "Demo release — no payment system is called"}

    def _sanction(self, case: dict, session: dict) -> None:
        v = lambda k: self._value(case, k)
        limit = float(v("recommended_cr") or v("amount_cr") or case["facility"]["amount_cr"])
        today = self.now().date()
        case["sanction"] = {"at": self._stamp(), "by": session["user"]["name"], "limit_cr": limit,
                            "product": v("product") or case["facility"]["product"],
                            "tenor_months": v("tenor_months") or case["facility"]["tenor_months"],
                            "purpose": v("purpose") or case["facility"]["purpose"], "pricing": v("pricing"),
                            "security": v("security"), "covenants": v("covenants"), "key_terms": v("key_terms"),
                            "valid_until": (today + timedelta(days=90)).isoformat(),
                            "reference": f"SL/{case['case_id']}"}
        case["conditions"] = self._build_conditions(case, limit)
        case["drawdown"] = {"amount_cr": limit, "account": f"{case['borrower_name']} — current account",
                            "value_date": today.isoformat(), "purpose": case["sanction"]["purpose"],
                            "prepared_by": AGENT, "edited_by": None}

    # ── conditions precedent and subsequent ──────────────────────────────────

    def _build_conditions(self, case: dict, limit: float) -> list[dict]:
        """The sanction's conditions, risk-based: precedent (before release) or subsequent (after, with a due
        period); an amount threshold; conditions tied to the security; and those already met from the record."""
        security = str(self._value(case, "security") or "").lower()
        out = []
        for c in self.cfg().get("conditions") or []:
            cond = {"id": c["id"], "label": c["label"], "kind": c.get("kind") or [],
                    "when": c.get("when") or "precedent", "within_days": c.get("within_days"), "due": None,
                    "status": "open", "documents": [], "confirmed_by": None, "note": None, "basis": None}
            if c.get("min_amount_cr") and limit < float(c["min_amount_cr"]):
                cond.update(status="not_applicable",
                            basis=f"Required at or above {_cr(c['min_amount_cr'])}; sanctioned {_cr(limit)}")
            elif c.get("applies_if_security") and not any(w in security for w in c["applies_if_security"]):
                cond.update(status="not_applicable", basis="Not required for this security: "
                                                           + (str(self._value(case, "security"))[:120] or "none recorded"))
            elif c.get("auto") == "kyc_policy_check":
                basis = self._kyc_on_record(case)
                if basis:
                    cond.update(status="auto", basis=basis)
            out.append(cond)
        return out

    def _kyc_on_record(self, case: dict) -> Optional[str]:
        engine = self.cases.get(case["entity_id"]) if self.cases else None
        rules = ((engine or {}).get("fact_pack") or {}).get("policy_decisions", {}).get("tier1_hard_rules") or []
        rule = next((r for r in rules if r.get("rule") == "HR_KYC_COMPLETE"), None)
        if rule and rule.get("result") == "pass":
            return f"Met from the record — credit policy check HR_KYC_COMPLETE passed: {rule.get('details') or 'KYC on file'}"
        return None

    def _apply_due_dates(self, case: dict) -> None:
        released = date.fromisoformat((case.get("release") or {}).get("at", self._stamp())[:10])
        for c in case.get("conditions") or []:
            if c["when"] == "subsequent" and c.get("within_days"):
                c["due"] = (released + timedelta(days=int(c["within_days"]))).isoformat()

    @staticmethod
    def _cps(case: dict) -> list[dict]:
        return [c for c in case.get("conditions") or [] if c["when"] == "precedent" and c["status"] != "not_applicable"]

    @staticmethod
    def _cond(case: dict, condition_id: str) -> dict:
        cond = next((c for c in case.get("conditions") or [] if c["id"] == condition_id), None)
        if not cond:
            raise NotFoundError("No such condition")
        return cond

    def _cp_progress(self, case: dict) -> str:
        cps = self._cps(case)
        return f"{sum(1 for c in cps if c['status'] in MET)} of {len(cps)} conditions precedent met."

    def _cad_question(self, case: dict) -> Optional[dict]:
        """CAD's next step, one condition at a time; then the disbursement request."""
        offered = set((case.get("offered") or {}).get("cad") or [])
        cps = self._cps(case)
        for c in cps:
            if c["status"] == "review" and f"confirm:{c['id']}" not in offered:
                note = c["documents"][-1]["check"]["note"] if c["documents"] else ""
                return {"kind": "cond_confirm", "ref": c["id"],
                        "text": f"{c['label']}: {note}. Have you verified it against the original?",
                        "quick": ["Yes, verified", "No"]}
        for c in cps:
            if c["status"] == "open":
                return {"kind": "cond_doc", "ref": c["id"],
                        "text": f"{self._cp_progress(case)} Next: {c['label']} — upload the executed document "
                                f"here, or against its row in **Conditions Precedent**.",
                        "quick": ["Add demo signed documents"],
                        "upload": {"condition": c["id"], "label": c["label"]},
                        "goto": {"target": "sec-cp", "row": c["id"], "label": "Go to condition"}}
        if cps and all(c["status"] in MET for c in cps) and "submit_release" not in offered:
            d = case["drawdown"]
            return {"kind": "submit_release", "ref": "drawdown",
                    "text": f"All {len(cps)} conditions precedent are met. Submit the disbursement request of "
                            f"{_cr(d['amount_cr'])} (value date {_day(d['value_date'])}) for release?",
                    "quick": ["Yes, submit", "No, edit first"]}
        return None

    def _check_document(self, case: dict, cond: dict, content: bytes) -> dict:
        """The agent's check of an uploaded document: the right borrower, and the words that identify the
        document type. What it cannot see (signatures, stamps on a scan) is left to CAD."""
        try:
            text = re.sub(r"\s+", " ", " ".join(dpx.page_texts(content, 20))).lower()
        except Exception:
            return {"ok": False, "found": [], "missing": [], "note": "The file could not be read — verify it manually"}
        if len(text.strip()) < 20:
            return {"ok": False, "found": [], "missing": [], "note": "No text layer (scanned copy) — verify it manually"}
        name_words = [w for w in re.findall(r"[a-z]+", case["borrower_name"].lower()) if len(w) > 2
                      and w not in ("limited", "private", "ltd", "pvt", "the")]
        borrower_ok = bool(name_words) and name_words[0] in text
        found = [k for k in cond.get("kind") or [] if k.lower() in text]
        missing = [k for k in cond.get("kind") or [] if k.lower() not in text]
        ok = borrower_ok and not missing
        if ok:
            note = f"Names {case['borrower_name']}; identified as: {', '.join(found)}"
        elif not borrower_ok:
            note = f"Does not name {case['borrower_name']} — check it is this borrower's document"
        else:
            note = f"“{', '.join(missing)}” not found in the document"
        return {"ok": ok, "found": found, "missing": missing, "note": note}

    def _can_cad(self, case: dict, session: dict, cond: dict) -> None:
        """CAD works the conditions at its stage; conditions subsequent also after release."""
        if session["user"]["role"] != "cad":
            raise ForbiddenError("Conditions are handled by Credit Administration")
        if case["status"] == "open" and case["stage"] == "cad":
            return
        if case["status"] == "disbursed" and cond["when"] == "subsequent":
            return
        raise ConflictError("Conditions precedent are handled while the proposal is with Credit Administration")

    def upload_document(self, case_id: str, session: dict, condition_id: str, file_name: str, content: bytes,
                        demo: bool = False) -> dict:
        with self._lock:
            case = self._require(case_id)
            self._upload(case, session, condition_id, file_name, content, demo, announce=True)
            self._save(case)
            return case

    def _upload(self, case: dict, session: dict, condition_id: str, file_name: str, content: bytes,
                demo: bool, announce: bool) -> dict:
        cond = self._cond(case, condition_id)
        self._can_cad(case, session, cond)
        if cond["status"] == "not_applicable":
            raise ConflictError(f"{cond['label']} is not applicable to this sanction")
        if not content or not content.startswith(b"%PDF"):
            raise InvalidRequestError("Upload the document as a PDF")
        folder = self.files_root / case["case_id"] / "documents"
        folder.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(file_name or "document.pdf").name) or "document.pdf"
        path = folder / f"{condition_id}__{safe}"
        path.write_bytes(content)
        check = self._check_document(case, cond, content)
        cond["documents"].append({"name": safe, "path": str(path), "at": self._stamp(),
                                  "by": session["user"]["name"], "check": check, "demo": demo})
        if cond["status"] not in ("confirmed", "auto"):
            cond["status"] = "verified" if check["ok"] else "review"
        offered = (case.get("offered") or {}).get("cad") or []
        if f"confirm:{cond['id']}" in offered:              # a new document: ask CAD to verify it again
            offered.remove(f"confirm:{cond['id']}")
        self._log(case, "doc_upload", session, condition=condition_id, file=safe, agent_ok=check["ok"],
                  agent_note=check["note"])
        if announce:
            mark = "Verified by the agent" if check["ok"] else "Needs your verification"
            self._say(case, f"{cond['label']} — {safe}: {mark}. {check['note']}."
                      + (f" {self._cp_progress(case)}" if case["status"] == "open" else ""), stage="cad")
            self._ask_next(case)
        return cond

    def _confirm(self, case: dict, session: dict, cond: dict, note: str) -> None:
        self._can_cad(case, session, cond)
        if not cond["documents"] and not note.strip():
            raise InvalidRequestError("Upload the document, or record why the condition is met without one")
        cond.update({"status": "confirmed", "confirmed_by": session["user"]["name"], "note": note or None,
                     "confirmed_at": self._stamp()})
        self._log(case, "condition_confirm", session, condition=cond["id"], note=note or None)

    def confirm_condition(self, case_id: str, session: dict, condition_id: str, note: str = "",
                          reopen: bool = False) -> dict:
        with self._lock:
            case = self._require(case_id)
            cond = self._cond(case, condition_id)
            if reopen:
                self._can_cad(case, session, cond)
                cond.update({"status": "open", "confirmed_by": None, "note": note or None, "documents": []})
                self._log(case, "condition_reopen", session, condition=condition_id, note=note or None)
            else:
                self._confirm(case, session, cond, note)
                self._say(case, f"{cond['label']}: confirmed by {session['user']['name']}."
                          + (f" {self._cp_progress(case)}" if case["status"] == "open" else ""), stage="cad")
            if case["status"] == "open":
                self._ask_next(case)
            self._save(case)
            return case

    def demo_documents(self, case_id: str, session: dict) -> dict:
        with self._lock:
            case = self._require(case_id)
            self._demo_documents(case, session)
            self._save(case)
            return case

    def _demo_documents(self, case: dict, session: dict) -> None:
        """Demo only: an executed-document set for this borrower's open conditions precedent (insurance, where it
        applies, omits the bank clause so the agent leaves it for CAD to verify)."""
        import fitz

        texts = {
            "accepted_sanction_letter": "SANCTION LETTER {ref} — ACCEPTANCE. We, {name}, accept the terms of the "
                                        "sanction letter for {amt}. Signed by the authorised signatory.",
            "board_resolution": "CERTIFIED TRUE COPY OF THE BOARD RESOLUTION of {name} authorising the borrowing of {amt}.",
            "facility_agreement": "FACILITY AGREEMENT between the Bank and {name} for {amt}. Stamp duty paid; "
                                  "e-stamp certificate attached.",
            "security_documents": "SECURITY DOCUMENTS executed by {name} in favour of the Bank: {security}.",
            "charge_filing": "Form CHG-1 filed with the Registrar of Companies by {name}; CERSAI registration done.",
            "legal_vetting": "VETTING REPORT by the panel advocate: documents executed by {name} are in order.",
            "insurance": "INSURANCE POLICY of {name} covering the charged assets.",       # no bank clause: CAD checks
            "kyc_refresh": "KYC of {name} and its authorised signatories verified (CKYC, PAN, Aadhaar).",
        }
        s = case.get("sanction") or {}
        amt = f"Rs {float(s.get('limit_cr') or 0):,.2f} crore"
        done = []
        for cond in self._cps(case):
            if cond["status"] != "open":
                continue
            body = texts.get(cond["id"], "{name}: " + cond["label"]).format(
                name=case["borrower_name"], amt=amt, ref=s.get("reference", ""),
                security=str(s.get("security") or "as sanctioned")[:300].replace("\n", "; "))
            doc = fitz.open()
            page = doc.new_page()
            page.insert_textbox(fitz.Rect(56, 72, 540, 760), "DEMO DOCUMENT — NOT A REAL INSTRUMENT\n\n" + body,
                                fontsize=11)
            done.append(self._upload(case, session, cond["id"], f"{cond['id']}_demo.pdf", doc.tobytes(),
                                     demo=True, announce=False))
            doc.close()
        ok = [c for c in done if c["status"] == "verified"]
        # each document by name, against its condition, with the agent's check and a link (fix list E8)
        docs = [{"condition": c["id"], "label": c["label"], "name": c["documents"][-1]["name"],
                 "index": len(c["documents"]) - 1, "note": c["documents"][-1]["check"]["note"],
                 "status": c["status"], "demo": True} for c in done if c.get("documents")]
        lines = "\n".join(f"• {d['label']}: {d['name']} — {d['note']}" + ("" if d["status"] == "verified"
                                                                           else " (needs your verification)")
                          for d in docs)
        msg = self._say(case, f"Demo executed documents (marked DEMO) attached in **Conditions Precedent**, one per "
                              f"open condition — {len(ok)} of {len(done)} verified by the agent"
                              + (f", {len(done) - len(ok)} need your verification" if len(done) > len(ok) else "")
                              + f":\n{lines}\n{self._cp_progress(case)}")
        msg["docs"] = docs
        msg["goto"] = {"target": "sec-cp", "label": "View in Conditions Precedent"}
        self._ask_next(case)

    def set_drawdown(self, case_id: str, session: dict, amount_cr=None, account: Optional[str] = None,
                     value_date: Optional[str] = None) -> dict:
        with self._lock:
            case = self._require(case_id)
            st = self._at_stage(case, session)
            if st["id"] != "cad":
                raise ForbiddenError("The disbursement request is prepared by Credit Administration")
            d = case["drawdown"]
            if amount_cr not in (None, ""):
                amount = float(amount_cr)
                if amount <= 0 or amount > float(case["sanction"]["limit_cr"]) + 1e-6:
                    raise InvalidRequestError(f"The disbursement amount must be above zero and within the sanctioned "
                                              f"{_cr(case['sanction']['limit_cr'])}")
                d["amount_cr"] = round(amount, 2)
            if account:
                d["account"] = account.strip()
            if value_date:
                d["value_date"] = date.fromisoformat(value_date).isoformat()
            d["edited_by"] = session["user"]["name"]
            d.setdefault("edits", []).append({"by": session["user"]["name"], "at": self._stamp(),
                                              **{k: d[k] for k in ("amount_cr", "account", "value_date")}})
            offered = (case.get("offered") or {}).get("cad") or []
            if "submit_release" in offered:
                offered.remove("submit_release")
            self._log(case, "drawdown_edit", session, **{k: d[k] for k in ("amount_cr", "account", "value_date")})
            case["ask"] = None
            self._ask_next(case)
            self._save(case)
            return case

    def release_checks(self, case: dict) -> list[dict]:
        s, d = case.get("sanction") or {}, case.get("drawdown") or {}
        cps = self._cps(case)
        met = [c for c in cps if c["status"] in MET]
        kyc = next((c for c in case.get("conditions") or [] if c["id"] == "kyc_refresh"), None)
        today = self.now().date().isoformat()
        return [
            {"id": "sanction_valid", "label": "Sanction in force", "ok": bool(s) and today <= s.get("valid_until", ""),
             "detail": f"Valid until {s.get('valid_until')}" if s else "No sanction"},
            {"id": "conditions", "label": "All conditions precedent met", "ok": bool(cps) and len(met) == len(cps),
             "detail": f"{len(met)} of {len(cps)} met"},
            {"id": "within_limit", "label": "Within the sanctioned limit",
             "ok": bool(d) and float(d.get("amount_cr") or 0) <= float(s.get("limit_cr") or 0) + 1e-6
                   and float(d.get("amount_cr") or 0) > 0,
             "detail": f"{_cr(d.get('amount_cr'))} of {_cr(s.get('limit_cr'))}"},
            {"id": "kyc", "label": "KYC compliant", "ok": bool(kyc) and kyc["status"] in MET + ("not_applicable",),
             "detail": (kyc.get("basis") or kyc["status"]) if kyc else "not in the conditions"},
            {"id": "no_open_disputes", "label": "All underwriting overrides concurred",
             "ok": not any(c["status"] in ("pending", "disputed") for c in case.get("changes") or []),
             "detail": f"{sum(1 for c in case.get('changes') or [] if c['status'] == 'accepted')} concurred"},
            {"id": "account", "label": "Beneficiary account validated", "ok": bool(d.get("account")),
             "detail": d.get("account") or "—"},
        ]

    def document_file(self, case_id: str, condition_id: str, index: int) -> tuple[bytes, str]:
        case = self._require(case_id)
        cond = next((c for c in case.get("conditions") or [] if c["id"] == condition_id), None)
        if not cond or index >= len(cond["documents"]):
            raise NotFoundError("No such document")
        doc = cond["documents"][index]
        return Path(doc["path"]).read_bytes(), doc["name"]

    # ── the screen ───────────────────────────────────────────────────────────

    def view(self, case_id: str, session: dict) -> dict:
        case = self._require(case_id)
        role = session["user"]["role"]
        my_stage = self.stage_of_role(role)
        st = self.stage(case["stage"])
        is_mine = case["status"] == "open" and st["role"] == role
        stages = self.stages()
        idx = next(i for i, s in enumerate(stages) if s["id"] == st["id"])
        spent: dict[str, float] = {}
        for h in case.get("stage_history") or []:
            end = datetime.fromisoformat(h["left"]) if h.get("left") else self.now()
            spent[h["stage"]] = spent.get(h["stage"], 0) + max((end - datetime.fromisoformat(h["entered"])).total_seconds(), 0)
        chain = [{"id": s["id"], "label": s["label"], "short": s.get("short") or s["label"], "who": self.officer(s["id"]),
                  "seconds": int(spent.get(s["id"], 0)) if s["id"] in spent else None,
                  "state": ("done" if (i < idx or case["status"] == "disbursed") else
                            "current" if i == idx and case["status"] == "open" else
                            "rejected" if i == idx and case["status"] in ("rejected", "withdrawn") else "todo")}
                 for i, s in enumerate(stages)]
        editable = is_mine and st["id"] in ("rm", "credit_risk") and (case.get("cam") or {}).get("state") == "ready"
        groups = []
        changed = {c["dp"]: c for c in case["changes"] if c["status"] != "superseded"}
        thresholds = (case.get("risk") or {}).get("thresholds") or {}
        values = {k: (v or {}).get("value") for k, v in case["dp"].items()}
        ratio_of = {("interest_cover" if r["id"] == "interest_coverage_ratio" else r["id"]): r
                    for r in (case.get("risk") or {}).get("ratios") or [] if isinstance(r.get("value"), (int, float))}
        for g in self.cfg().get("groups") or []:
            pts = []
            for sp in dpx.specs():
                if sp["group"] != g["id"]:
                    continue
                d = case["dp"].get(sp["id"]) or {"status": "missing"}
                if d.get("value") in (None, "") and sp["id"] in ratio_of:
                    r = ratio_of[sp["id"]]
                    d = {**d, "value": r["value"], "status": "filled",
                         "source": {"kind": "engine", "label": f"Calculated from the {r.get('period') or ''} statements".replace("  ", " ")}}
                status = d.get("status") or "missing"
                if status == "missing" and sp.get("agent_only"):
                    status = "unavailable"                        # the agents found no source; not asked
                pts.append({"id": sp["id"], "label": sp["label"], "type": sp.get("type"),
                            "required": bool(sp.get("required")), "engine": bool(sp.get("engine")),
                            "computed": bool(sp.get("computed")), "agent_only": bool(sp.get("agent_only")),
                            "value": d.get("value"),
                            "display": dpx.display(sp, d.get("value")) if status != "unavailable"
                            else sp.get("unavailable") or "Not on record",
                            "status": status, "source": d.get("source"), "flag": d.get("flag"),
                            "skipped_by": d.get("skipped_by"), "history": d.get("history") or [],
                            "change": changed.get(sp["id"]),
                            "band": dpx.band(sp, d.get("value"), thresholds, values),
                            "confidence": (d.get("source") or {}).get("confidence"),
                            "options": sp.get("options"), "hint": sp.get("hint")})
            groups.append({"id": g["id"], "label": g["label"], "points": pts,
                           "missing": sum(1 for p in pts if p["status"] == "missing"),
                           "skipped": sum(1 for p in pts if p["status"] == "skipped")})
        by_role: dict[str, int] = {}
        for v in case["dp"].values():
            src = v.get("source") or {}
            if src.get("kind") == "person":
                r = src.get("role") or next((u["role"] for u in self.users() if u["id"] == src.get("by")), "")
                by_role[r] = by_role.get(r, 0) + 1
        counts = {"total": len(dpx.specs()),
                  "filled": sum(1 for v in case["dp"].values() if v.get("status") == "filled"),
                  "by_agent": sum(1 for v in case["dp"].values() if v.get("status") == "filled"
                                  and (v.get("source") or {}).get("kind") in ("engine", "upload", "record")),
                  "by_person": sum(by_role.values()),
                  "by_role": [{"role": r, "label": self.role_label(r), "short": ROLE_SHORT.get(r, r), "count": n}
                              for r, n in by_role.items()],
                  "skipped": sum(1 for v in case["dp"].values() if v.get("status") == "skipped"),
                  "missing": len(self._missing(case))}
        actions = []
        if is_mine:
            blocked = self.blockers(case, st)
            labels = st.get("labels") or {}
            for a in st.get("actions") or []:
                label = labels.get(a) or {"approve": "Approve", "reject": "Decline",
                                          "send_back": f"Return to {self.stage(st['send_back_to'])['label']}"
                                          if st.get("send_back_to") else "Return"}[a]
                actions.append({"id": a, "label": label, "enabled": a != "approve" or not blocked,
                                "blockers": blocked if a == "approve" else [],
                                "justify": self._justify(case) if a == "approve" else []})
        cam = dict(case.get("cam") or {})
        cam.pop("file", None)
        checks_view = chk.view(case.get("checks"), case.get("check_notes"))
        if checks_view:
            checks_view["can_note"] = is_mine
            checks_view["can_return"] = is_mine and bool(st.get("send_back_to")) and "send_back" in (st.get("actions") or [])
            checks_view["return_label"] = ((st.get("labels") or {}).get("send_back") or "Return") if checks_view["can_return"] else ""
        hours, sla, sla_state = self._ageing(case)
        dp = case["dp"]
        out = {k: case[k] for k in ("case_id", "entity_id", "borrower_name", "status", "stage", "created_at",
                                    "updated_at", "facility", "rm_name", "changes", "chat", "against", "sanction",
                                    "drawdown", "release", "decisions", "is_prospect")}
        out.update({"stage_label": st["label"], "chain": chain, "is_mine": is_mine, "my_stage": my_stage,
                    "acquisition": self._acq_view(case),
                    "can_sources": is_mine and st["id"] == self.stages()[0]["id"] and bool(case.get("acquisition")),
                    "can_generate": self._can_generate(case),
                    "generate_blocker": None if self._can_generate(case) else self._cannot_generate(case),
                    "editable": editable, "can_cam": is_mine and st["id"] == "rm",
                    "can_rerun": is_mine and st["id"] in ("rm", "credit_risk") and cam.get("state") in ("ready", "failed")
                    and bool(cam.get("run_id") or cam.get("mode") == "generate") and self._can_generate(case),
                    "cam": cam, "progress": self.cam_progress(case_id)["job"] if cam.get("state") in ("running", "failed")
                    else None, "groups": groups, "counts": counts, "actions": actions,
                    "ask": case.get("ask") if is_mine and (case.get("ask") or {}).get("stage") == case["stage"] else None,
                    "suggestions": self._suggestions(case, session),
                    "header": {"cin": case.get("cin") or (dp.get("cin") or {}).get("value"),
                               "internal_rating": (dp.get("internal_rating") or {}).get("value"),
                               "external_rating": (dp.get("external_rating") or {}).get("value"),
                               "proposed_limit_cr": (case.get("sanction") or {}).get("limit_cr")
                               or (dp.get("recommended_cr") or {}).get("value") or case["facility"]["amount_cr"],
                               "tat_seconds": int(((self.now() if case["status"] == "open"
                                                    else datetime.fromisoformat(case["updated_at"]))
                                                   - datetime.fromisoformat(case["created_at"])).total_seconds()),
                               "ageing_hours": hours, "sla_hours": sla, "sla_state": sla_state},
                    "conditions": [{k: v for k, v in c.items() if k != "kind"} | {"documents": [
                        {kk: vv for kk, vv in d.items() if kk != "path"} for d in c["documents"]]}
                        for c in case.get("conditions") or []],
                    "can_conditions": role == "cad" and ((case["status"] == "open" and case["stage"] == "cad")
                                                         or case["status"] == "disbursed"),
                    "release_checks": self.release_checks(case) if case.get("sanction") else [],
                    "pending_changes": sum(1 for c in case["changes"] if c["status"] == "pending"),
                    "risk": self._risk_view(case), "responses": case.get("responses") or {},
                    "checks": checks_view, "verdict": rk.verdict(case.get("risk"), checks_view,
                                                                 f"{self.officer('sanction')} "
                                                                 f"({self.stage('sanction')['label']})"),
                    "ews_about": rk.EWS_ABOUT, "incomplete": self._incomplete(case),
                    "register": case.get("register") or [],
                    "cam_sections": self._cam_section_count(),
                    "deviations": case.get("deviations") or [],
                    "queries": case.get("queries") or [],
                    "query_targets": self._query_targets(case) if is_mine else [],
                    "clock_paused": bool(case.get("paused_since")) and case["status"] == "open",
                    "withdrawn": case.get("withdrawn"), "archived": case.get("archived"),
                    "can_withdraw": case["status"] == "open" and role == stages[0]["role"],
                    "can_archive": case["status"] != "open",
                    "can_delete": role == stages[0]["role"] and not case.get("sanction")
                    and case["status"] != "disbursed"})
        return out

    @staticmethod
    def _risk_view(case: dict) -> Optional[dict]:
        """The engine's assessment for the screen: rule codes in its rationale read as plain names."""
        risk = case.get("risk")
        if not risk or not risk.get("rationale"):
            return risk
        text = re.sub(r"HR_[A-Z_]+", lambda m: chk.plain(m.group(0)).lower(), risk["rationale"])
        return {**risk, "rationale": text}

    # ── reports ──────────────────────────────────────────────────────────────

    def audit_pack(self, case_id: str, session: dict) -> str:
        from src.flow import reports

        case = self._require(case_id)
        self._log(case, "audit_pack", session)
        return reports.audit_pack(case, self.store.events(case_id), self.stages(),
                                  self.release_checks(case) if case.get("sanction") else [], self._stamp())

    def governance(self, case_id: str, session: dict) -> dict:
        """The AI governance pack (roadmap L2): AI use, figures check, human oversight, data, fairness."""
        from src.flow import governance
        case = self._require(case_id)
        self._log(case, "ai_governance_pack", session)
        return governance.build(case, self.store.events(case_id), self._stamp())

    def governance_html(self, case_id: str, session: dict) -> str:
        from src.flow import governance
        return governance.html(self.governance(case_id, session))

    def audit_json(self, case_id: str) -> dict:
        case = self._require(case_id)
        return {"case": case, "events": self.store.events(case_id),
                "release_checks": self.release_checks(case) if case.get("sanction") else []}

    def sanction_letter(self, case_id: str) -> str:
        from src.flow import reports

        case = self._require(case_id)
        if not case.get("sanction"):
            raise ConflictError("The proposal is not sanctioned yet")
        return reports.sanction_letter(case, self.cfg().get("bank_name") or "The Bank")

    def backtest(self) -> dict:
        return self.backtests.last()

    def run_backtest(self, session: dict) -> dict:
        try:
            return self.backtests.start(session["user"]["name"])
        except ValueError as e:
            raise InvalidRequestError(str(e))

    def time_report(self) -> dict:
        from src.flow import reports

        now = self.now()
        cases = [self._require(c["case_id"]) if "risk" not in c else c for c in self.store.all()]
        events ={c["case_id"]: self.store.events(c["case_id"]) for c in cases}
        rows = [reports.case_times(c, events[c["case_id"]], self.stages(), now) for c in cases]
        baseline = self.cfg().get("baseline") or {}
        out = reports.time_report(rows, baseline)
        out["analytics"] = reports.run_analytics(cases, events, self.stages(), rows, [self._row(c) for c in cases],
                                                 baseline, now)
        return out

    def timeline(self, case_id: str) -> list[dict]:
        from src.flow.reports import _KIND_LABEL

        self._require(case_id)
        return [{"at": e["at"], "who": e.get("actor_name"), "role": e.get("role"),
                 "what": _KIND_LABEL.get(e["kind"], e["kind"]), "kind": e["kind"], "detail": e.get("detail")}
                for e in self.store.events(case_id) if e["kind"] not in ("cam_download", "audit_pack", "ai_governance_pack")]
