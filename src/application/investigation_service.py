"""
Investigations for a case: plan from observations, analyst status, optional LLM phrasing.

Tasks live in the case record (``case["investigations"]``), saved with the run in
``case_runs`` like observations. Every read re-plans from the current
observations and merges with stored tasks (``sync_investigations``), so an
analyst dismissing an observation or flagging one for investigation is
reflected without a pipeline run, while task status and notes are kept.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime

from src.agents.investigation_agent import InvestigationAgent, sync_investigations
from src.application.errors import ConflictError, InvalidRequestError, NotFoundError
from src.models.investigations import InvestigationPriority, InvestigationStatus

log = logging.getLogger(__name__)


def investigations_for_observations(observations: list[dict], entity_id: str, created_at: str | None) -> list[dict]:
    """Planned tasks for a run; never raises, so planning cannot fail a pipeline run."""
    try:
        return InvestigationAgent().plan(observations or [], entity_id, created_at=created_at)
    except Exception as e:
        log.warning("Investigations unavailable for %s: %s", entity_id, e)
        return []


def summarize(tasks: list[dict]) -> dict:
    by_status = {s.value: 0 for s in InvestigationStatus}
    by_priority = {p.value: 0 for p in InvestigationPriority}
    for t in tasks:
        by_status[t["status"]] = by_status.get(t["status"], 0) + 1
        if t["status"] in (InvestigationStatus.OPEN.value, InvestigationStatus.IN_PROGRESS.value):
            by_priority[t["priority"]] = by_priority.get(t["priority"], 0) + 1
    return {"total": len(tasks), "open": by_status["OPEN"] + by_status["IN_PROGRESS"],
            "by_status": by_status, "open_by_priority": by_priority}


class InvestigationService:
    def __init__(self, cases, persistence, observations, llm_factory=None):
        self.cases = cases
        self.persistence = persistence
        self.observations = observations          # ObservationService
        self.llm_factory = llm_factory or observations.llm_factory
        self.agent = InvestigationAgent()
        self._lock = threading.Lock()

    def _ensure(self, case: dict) -> list[dict]:
        observations = self.observations._ensure(case)
        planned = investigations_for_observations(observations, case["entity_id"], case.get("run_at"))
        merged = sync_investigations(planned, case.get("investigations"))
        if merged != case.get("investigations"):
            case["investigations"] = merged
            self.persistence.save_case_run(case)
        return case["investigations"]

    def list(self, entity_id: str, run_id: str | None = None) -> dict:
        with self._lock:
            case = self.cases.get_run(entity_id, run_id)
            latest = self.cases.require(entity_id)
            tasks = self._ensure(case)
            observations = case.get("observations") or []
        titles = {o["observation_id"]: {"title": o.get("title"), "severity": o.get("severity"),
                                        "status": o.get("status")} for o in observations}
        return {
            "entity_id": entity_id,
            "run_id": case.get("run_id"),
            "is_latest_run": case.get("run_id") == latest.get("run_id"),
            "investigations": tasks,
            "observations": titles,
            "unrouted_observations": self.agent.unrouted(observations),
            "summary": summarize(tasks),
        }

    def update(self, entity_id: str, investigation_id: str, status: str | None = None,
               note: str | None = None, updated_by: str = "RM") -> dict:
        if status is not None and status not in {s.value for s in InvestigationStatus}:
            raise InvalidRequestError(f"Unknown status '{status}'")
        with self._lock:
            case = self.cases.require(entity_id, "Case not found — run the pipeline first.")
            task = self._find(self._ensure(case), investigation_id)
            if status is not None:
                task["status"] = status
            task["review"] = {
                "note": (note if note is not None else (task.get("review") or {}).get("note", "")) or "",
                "updated_by": updated_by,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
            self.persistence.save_case_run(case)
            return task

    def phrase(self, entity_id: str, investigation_ids: list[str] | None = None) -> dict:
        """LLM-worded borrower request for the given tasks (all open ones when none given)."""
        from src.services.investigation_narrator import phrase_requests

        with self._lock:
            case = self.cases.require(entity_id, "Case not found — run the pipeline first.")
            tasks = self._ensure(case)
        targets = ([self._find(tasks, iid) for iid in investigation_ids] if investigation_ids
                   else [t for t in tasks if t["status"] in ("OPEN", "IN_PROGRESS")])
        if not targets:
            return {"results": {}, "investigations": tasks}
        llm = self.llm_factory()
        if getattr(llm, "name", "") == "mock":
            raise ConflictError("Drafting requests needs a configured LLM provider (the active provider is 'mock').")
        results = phrase_requests(targets, llm, case.get("company_name") or entity_id)
        with self._lock:
            for iid, result in results.items():
                if result["status"] == "ok":
                    self._find(tasks, iid)["request_text"] = result["request_text"]
            self.persistence.save_case_run(case)
        return {"results": {iid: {k: v for k, v in r.items() if k != "request_text"} for iid, r in results.items()},
                "investigations": tasks}

    @staticmethod
    def _find(tasks: list[dict], investigation_id: str) -> dict:
        for task in tasks:
            if task.get("investigation_id") == investigation_id:
                return task
        raise NotFoundError(f"Investigation {investigation_id} not found")
