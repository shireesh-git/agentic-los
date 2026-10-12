"""
Credit cases: running the analysis pipeline for a borrower, building the case
record, and loading cases from memory, SQLite or legacy output files.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Callable
from uuid import uuid4

from src.application.company_service import CompanyService
from src.application.errors import ConflictError, NotFoundError
from src.application.serialization import repair_mojibake, repair_mojibake_text, to_jsonable
from src.application.state import AppState
from src.core.config_manager import config

log = logging.getLogger(__name__)

ProgressCallback = Callable[[dict], None]


def build_case_result(entity_id: str, company_data: dict, context: dict, pipeline_log: list) -> dict:
    """Flatten a pipeline context into the case record stored and served by the API."""
    results = context.get("results", {})
    narrative = results.get("narrative", {})
    policy = results.get("policy", {})
    validation = results.get("validation", {})
    rec = policy.get("recommendation")
    rs = policy.get("risk_score")
    b = company_data["borrower"]
    f = company_data["facility"]
    case = {
        "run_id": uuid4().hex,
        "entity_id": entity_id,
        "company_name": b.company_name,
        "sector": b.sector.value,
        "case_type": f.case_type.value,
        "requested_amount_cr": f.amount_requested_cr,
        "facility_type": f.facility_type.value if hasattr(f.facility_type, "value") else str(f.facility_type),
        "recommendation": rec.recommendation.value if rec else "error",
        "risk_grade": rs.risk_grade if rs else "N/A",
        "composite_score": rs.composite_score if rs else 0,
        "financial_score": rs.financial_score if rs else 0,
        "conduct_score": rs.conduct_score if rs else 0,
        "governance_score": rs.governance_score if rs else 0,
        "market_score": rs.market_score if rs else 0,
        "conditions": rec.conditions if rec else [],
        "covenants_proposed": rec.covenants_proposed if rec else [],
        "rationale": rec.rationale if rec else "",
        "cam_text": narrative.get("cam_text", ""),
        "narrative_mode": narrative.get("narrative_mode", "template"),
        "data_provider": company_data.get("data_provider", "internal"),
        "fact_pack": narrative.get("fact_pack", {}),
        "pipeline_log": pipeline_log,
        "run_at": datetime.now().isoformat(),
        "tier1_decisions": to_jsonable(policy.get("tier1_decisions", [])),
        "exceptions": to_jsonable(validation.get("exceptions", [])),
    }
    # Credit observations are derived from this run's fact pack after the pipeline;
    # they never affect the recommendation or the CAM.
    from src.application.observation_service import observations_for_fact_pack
    case["observations"] = observations_for_fact_pack(case["fact_pack"], entity_id, case["run_at"])
    # The Investigation Agent opens follow-up tasks for those observations.
    from src.application.investigation_service import investigations_for_observations
    case["investigations"] = investigations_for_observations(case["observations"], entity_id, case["run_at"])
    # The Credit Challenge Agent questions the proposal against those findings (no decision is made).
    from src.application.challenge_service import challenges_for_case
    case["challenges"] = challenges_for_case(case["fact_pack"], case["observations"], case["investigations"],
                                             entity_id, case["run_at"])
    # Cash flow & repayment assessment from the same fact pack (the CAM is not changed).
    from src.application.repayment_service import repayment_for_case
    case["repayment_analysis"] = repayment_for_case(case["fact_pack"], case["observations"], entity_id, case["run_at"])
    # Stress test of the latest audited statement (no recommendation, not in the CAM).
    from src.application.stress_test_service import stress_for_case
    case["stress_test"] = stress_for_case(company_data, case["fact_pack"], entity_id, case["run_at"])
    # The reassessment reconsiders the proposal in the light of all of the above.
    from src.application.reassessment_service import reassessment_for_case
    case["reassessment"] = reassessment_for_case(case)
    # M7: the 12-section banker CAM composed from all of the above (the 21-section CAM stays the analyst view).
    from src.application.final_cam_service import final_cam_for_case
    case["final_cam"] = final_cam_for_case(case)
    return case


class CaseService:
    def __init__(self, state: AppState, persistence, companies: CompanyService,
                 output_dir: Path, pipeline_factory: Callable,
                 rerun_guard: Callable[[str], bool] | None = None):
        self.state = state
        # Returns True when a case must not be re-run (e.g. it is with an approver).
        self.rerun_guard = rerun_guard
        self.persistence = persistence
        self.companies = companies
        self.output_dir = output_dir
        self._pipeline_factory = pipeline_factory

    # ── Queries ──────────────────────────────────────────────────────────

    def get(self, entity_id: str) -> dict | None:
        """Latest case from memory, then SQLite, then legacy output files.

        Cases are text-repaired once when they enter memory (run, load), so a
        read does not walk the whole case — fact pack included — again.
        """
        if entity_id in self.state.cases:
            return self.state.cases[entity_id]
        stored = self.persistence.get_latest_case(entity_id)
        if stored:
            self.state.cases[entity_id] = repair_mojibake(stored)
            return self.state.cases[entity_id]
        return self._load_from_disk(entity_id)

    def require(self, entity_id: str, message: str = "Case not found") -> dict:
        case = self.get(entity_id)
        if not case:
            raise NotFoundError(message)
        return case

    def run_history(self, entity_id: str, limit: int = 20) -> list[dict]:
        """Every pipeline attempt for a company, newest first, including failed ones.

        A completed attempt carries its run's outcome (grade, score, recommendation)
        and that run's approval status; ``is_current`` marks the run the case now
        shows. Runs saved before attempts were tracked appear as completed attempts.
        """
        self.companies.require(entity_id)
        attempts = self.persistence.list_pipeline_runs(entity_id, limit)
        outcomes = self.persistence.list_case_run_summaries(entity_id)
        decisions = self.persistence.run_decision_statuses(entity_id)
        current_run_id = (self.get(entity_id) or {}).get("run_id")

        tracked = {a["case_run_id"] for a in attempts if a.get("case_run_id")}
        for run_id, outcome in outcomes.items():
            if run_id not in tracked:
                attempts.append({"run_id": run_id, "entity_id": entity_id, "status": "completed",
                                 "started_at": outcome.get("run_at"), "finished_at": None, "error": None,
                                 "llm_provider": None, "llm_model": None, "case_run_id": run_id})
        attempts.sort(key=lambda a: a.get("started_at") or "", reverse=True)

        for attempt in attempts:
            case_run_id = attempt.get("case_run_id")
            outcome = outcomes.get(case_run_id) or {}
            attempt.update({
                "risk_grade": outcome.get("risk_grade"),
                "composite_score": outcome.get("composite_score"),
                "recommendation": outcome.get("recommendation"),
                "workflow_status": decisions.get(case_run_id, "draft") if outcome else None,
                "is_current": bool(case_run_id) and case_run_id == current_run_id,
            })
        return attempts[:limit]

    def get_run(self, entity_id: str, run_id: str | None) -> dict:
        """The case as a given run produced it; the latest case when ``run_id`` is empty."""
        current = self.require(entity_id)
        if not run_id or run_id == current.get("run_id"):
            return current
        case = self.persistence.get_case_run(run_id)
        if not case or case.get("entity_id") != entity_id:
            raise NotFoundError(f"Run {run_id} not found for {entity_id}")
        return repair_mojibake(case)

    def summaries(self) -> list[dict]:
        keys = ("entity_id", "company_name", "sector", "case_type", "facility_type",
                "requested_amount_cr", "recommendation", "risk_grade", "data_provider",
                "composite_score", "financial_score", "conduct_score", "governance_score",
                "market_score", "narrative_mode", "run_at")
        return [{**{k: c[k] for k in keys if k in c}, **self._review_indicators(c)}
                for c in self.state.cases.values()]

    @staticmethod
    def _review_indicators(case: dict) -> dict:
        """Small review indicators so list views need not fetch the full case."""
        exceptions = case.get("exceptions") or []
        top = exceptions[0] if exceptions and isinstance(exceptions[0], dict) else {}
        key_risks = (case.get("fact_pack") or {}).get("key_risks")
        return {
            "exception_count": len(exceptions),
            "top_exception": top.get("message") or top.get("exception_code"),
            "key_risk_count": len(key_risks) if isinstance(key_risks, list) else 0,
            "documents_changed": bool(case.get("_documents_changed")),
        }

    def dashboard(self) -> dict:
        cases = list(self.state.cases.values())
        grade_dist: dict[str, int] = {}
        for c in cases:
            grade = c.get("risk_grade", "N/A")
            grade_dist[grade] = grade_dist.get(grade, 0) + 1
        recent = sorted(cases, key=lambda x: x.get("run_at", ""), reverse=True)[:5]

        # Human decisions on each company's latest run (metrics above are system recommendations).
        current_runs = {c.get("entity_id"): c.get("run_id") for c in cases}
        workflow_status: dict[str, int] = {}
        workflows: dict[str, dict] = {}
        for wf in self.persistence.list_workflows():
            if current_runs.get(wf["entity_id"]) == wf["case_run_id"]:
                workflow_status[wf["status"]] = workflow_status.get(wf["status"], 0) + 1
                workflows[wf["entity_id"]] = wf
        undecided_drafts = sum(1 for eid in current_runs if eid not in workflows)
        if undecided_drafts:
            workflow_status["draft"] = workflow_status.get("draft", 0) + undecided_drafts

        return {
            "workflow_status": workflow_status,
            "portfolio": self._portfolio_rows(cases, workflows),
            "metrics": {
                "total_cases": len(cases),
                "approved": sum(1 for c in cases if c.get("recommendation") in ("approve", "conditional_approve")),
                "declined": sum(1 for c in cases if c.get("recommendation") == "decline"),
                "referred": sum(1 for c in cases if c.get("recommendation") == "refer"),
            },
            "grade_distribution": grade_dist,
            "recent_cases": [
                {k: c[k] for k in ("entity_id", "company_name", "recommendation",
                                   "risk_grade", "composite_score", "run_at")}
                for c in recent
            ],
        }

    def _portfolio_rows(self, cases: list[dict], workflows: dict[str, dict]) -> list[dict]:
        """One row per company with a case or a pipeline attempt, for the Summary view.

        ``workflow_status`` is the human decision on the latest run (draft when none);
        ``last_run`` is the latest pipeline attempt, so a failed or running re-run of a
        company that already has a case is visible too.
        """
        last_runs = self.persistence.latest_pipeline_runs()
        rows = {}
        for c in cases:
            eid = c.get("entity_id")
            wf = workflows.get(eid) or {}
            rows[eid] = {
                "entity_id": eid,
                "company_name": c.get("company_name"),
                "sector": c.get("sector"),
                "case_type": c.get("case_type"),
                "facility_type": c.get("facility_type"),
                "requested_amount_cr": c.get("requested_amount_cr") or 0,
                "risk_grade": c.get("risk_grade"),
                "composite_score": c.get("composite_score"),
                "recommendation": c.get("recommendation"),
                "run_at": c.get("run_at"),
                "workflow_status": wf.get("status", "draft"),
                "workflow_updated_at": wf.get("updated_at"),
            }
        for eid, run in last_runs.items():
            if eid not in rows:
                company = self.state.companies.get(eid)
                if not company:
                    continue
                borrower, facility = company.get("borrower"), company.get("facility")
                sector = getattr(borrower, "sector", None)
                rows[eid] = {
                    "entity_id": eid,
                    "company_name": getattr(borrower, "company_name", eid),
                    "sector": getattr(sector, "value", sector),
                    "requested_amount_cr": getattr(facility, "amount_requested_cr", 0) or 0,
                    "workflow_status": None,
                }
            rows[eid]["last_run"] = {k: run.get(k) for k in ("status", "started_at", "finished_at", "error")}
        return list(rows.values())

    # ── Pipeline execution ───────────────────────────────────────────────

    def run(self, entity_id: str, on_progress: ProgressCallback | None = None,
            enrich: bool = True) -> tuple[dict, list]:
        """Run the full analysis pipeline and persist the resulting case.

        Returns ``(case_record, pipeline_log)``. Raises if a critical agent fails.
        """
        if not self.companies.exists(entity_id):
            raise NotFoundError(f"Company {entity_id} not found")
        if self.rerun_guard and self.rerun_guard(entity_id):
            raise ConflictError("Case is with the approving authority — recall it before re-running")

        tracking_id = uuid4().hex
        provider = config.get_active_llm_provider()
        self.persistence.start_pipeline_run(tracking_id, entity_id,
                                            llm_provider=config.get("llm_providers", "active_provider"),
                                            llm_model=provider.get("model") or provider.get("deployment"))
        try:
            company = self.companies.ensure_enriched(entity_id) if enrich else self.companies.get(entity_id)
            pipeline = self._pipeline_factory()
            context = pipeline.execute_pipeline(company, on_progress=on_progress,
                                                stores=self.state.pipeline_stores())
            # Text repair happens once, here and on load, not on every read.
            case = repair_mojibake(build_case_result(entity_id, company, context, pipeline.pipeline_log))
            self.state.cases[entity_id] = case
            self.persistence.save_case_run(case)
        except Exception as e:
            self.persistence.finish_pipeline_run(tracking_id, "failed", error=str(e))
            raise
        self.persistence.finish_pipeline_run(tracking_id, "completed", case_run_id=case["run_id"])
        self.persistence.reset_workflow(entity_id, case["run_id"])
        return case, pipeline.pipeline_log

    # ── Legacy output-file cases ─────────────────────────────────────────

    def load_all_from_disk(self) -> None:
        """Populate the cache from ``*_fact_pack.json`` files of earlier versions."""
        if not self.output_dir.exists():
            return
        for fp_file in self.output_dir.glob("*_fact_pack.json"):
            eid = fp_file.stem.replace("_fact_pack", "")
            if eid in self.state.companies and eid not in self.state.cases:
                self._load_from_disk(eid)

    def _read_json(self, path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            return repair_mojibake(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return {}

    def _load_from_disk(self, entity_id: str) -> dict | None:
        fact_pack_file = self.output_dir / f"{entity_id}_fact_pack.json"
        if not fact_pack_file.exists():
            return None

        fp = self._read_json(fact_pack_file)
        pr = self._read_json(self.output_dir / f"{entity_id}_pipeline_result.json")
        cam_text = ""
        cam_md_file = self.output_dir / f"{entity_id}_CAM.md"
        if cam_md_file.exists():
            try:
                cam_text = repair_mojibake_text(cam_md_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        company = self.state.companies.get(entity_id)
        company_name = company["borrower"].company_name if company else ""
        if not company_name:
            company_name = fp.get("company_name") or fp.get("borrower_name", entity_id)

        policy = fp.get("policy_decisions", {})
        risk_scores = policy.get("tier2_risk_scores", {})
        recommendation = policy.get("tier3_recommendation", {})
        case_summary = fp.get("case_summary", {})
        facility_details = fp.get("facility_details", {})
        borrower_profile = fp.get("borrower_profile", {})

        case = {
            "run_id": pr.get("run_id") or f"legacy-{entity_id}",
            "entity_id": entity_id,
            "company_name": company_name or borrower_profile.get("company_name", entity_id),
            "sector": pr.get("sector") or case_summary.get("sector", ""),
            "case_type": pr.get("case_type") or case_summary.get("case_type", ""),
            "requested_amount_cr": (pr.get("requested_amount_cr") or case_summary.get("amount_requested_cr")
                                    or facility_details.get("amount_requested_cr")),
            "facility_type": (pr.get("facility_type") or case_summary.get("facility_type")
                              or facility_details.get("facility_type")),
            "recommendation": pr.get("recommendation") or recommendation.get("recommendation", "pending"),
            "risk_grade": (pr.get("risk_grade") or recommendation.get("risk_grade")
                           or risk_scores.get("risk_grade", "N/A")),
            "composite_score": (pr.get("composite_score") or recommendation.get("composite_score")
                                or risk_scores.get("composite_score", 0) or 0),
            "financial_score": pr.get("financial_score") or risk_scores.get("financial_score", 0) or 0,
            "conduct_score": pr.get("conduct_score") or risk_scores.get("conduct_score", 0) or 0,
            "governance_score": pr.get("governance_score") or risk_scores.get("governance_score", 0) or 0,
            "market_score": pr.get("market_score") or risk_scores.get("market_score", 0) or 0,
            "cam_text": cam_text,
            "narrative_mode": pr.get("narrative_mode", "template"),
            "data_provider": company.get("data_provider", "internal") if company else "internal",
            "fact_pack": fp,
            "pipeline_log": pr.get("pipeline_log", []),
            "run_at": pr.get("run_at", ""),
            "conditions": pr.get("conditions") or recommendation.get("conditions", []),
            "covenants_proposed": pr.get("covenants_proposed") or recommendation.get("covenants_proposed", []),
            "rationale": pr.get("rationale") or recommendation.get("rationale", ""),
            "_loaded_from_disk": True,
        }
        self.state.cases[entity_id] = case
        self.persistence.save_case_run(case)
        return case
