"""
Repayment & cash-flow assessment for a case, with an optional LLM explanation.

The assessment is stored in the case record (``case["repayment_analysis"]``) and
saved with the run in ``case_runs``. Each read recomputes it from the run's
fact pack and current observations (deterministic, cheap) and keeps a stored
AI explanation only while the assessment it explained is unchanged.
"""

from __future__ import annotations

import logging
import threading

from src.application.errors import ConflictError, InvalidRequestError
from src.engines.repayment_analysis import analyse_repayment

log = logging.getLogger(__name__)

_VOLATILE = ("ai_explanation", "created_at")


def repayment_for_case(fact_pack: dict, observations: list[dict], entity_id: str, created_at: str | None) -> dict:
    """The assessment for a run; never raises, so it cannot fail a pipeline run."""
    try:
        return analyse_repayment(fact_pack or {}, entity_id, observations or [], created_at=created_at)
    except Exception as e:
        log.warning("Repayment analysis unavailable for %s: %s", entity_id, e)
        return {"available": False, "reason": str(e)}


def _core(assessment: dict | None) -> dict:
    return {k: v for k, v in (assessment or {}).items() if k not in _VOLATILE}


class RepaymentService:
    def __init__(self, cases, persistence, observations, llm_factory=None):
        self.cases = cases
        self.persistence = persistence
        self.observations = observations          # ObservationService
        self.llm_factory = llm_factory or observations.llm_factory
        self._lock = threading.Lock()

    def _ensure(self, case: dict) -> dict:
        observations = self.observations._ensure(case)
        fresh = repayment_for_case(case.get("fact_pack"), observations, case["entity_id"], case.get("run_at"))
        stored = case.get("repayment_analysis")
        if _core(fresh) != _core(stored):
            case["repayment_analysis"] = fresh
            self.persistence.save_case_run(case)
        return case["repayment_analysis"]

    def get(self, entity_id: str, run_id: str | None = None) -> dict:
        with self._lock:
            case = self.cases.get_run(entity_id, run_id)
            latest = self.cases.require(entity_id)
            assessment = self._ensure(case)
        return {"entity_id": entity_id, "run_id": case.get("run_id"),
                "is_latest_run": case.get("run_id") == latest.get("run_id"), "assessment": assessment}

    def explain(self, entity_id: str) -> dict:
        from src.services.repayment_narrator import explain_repayment

        with self._lock:
            case = self.cases.require(entity_id, "Case not found — run the pipeline first.")
            assessment = self._ensure(case)
        if not assessment.get("available"):
            raise InvalidRequestError("No repayment assessment is available for this case.")
        llm = self.llm_factory()
        if getattr(llm, "name", "") == "mock":
            raise ConflictError("AI explanations need a configured LLM provider (the active provider is 'mock').")
        try:
            explanation = explain_repayment(assessment, llm, case.get("company_name") or entity_id)
        except ValueError as e:
            log.warning("Repayment explanation rejected for %s: %s", entity_id, e)
            return {"status": "rejected", "reason": str(e), "assessment": assessment}
        with self._lock:
            assessment["ai_explanation"] = explanation
            self.persistence.save_case_run(case)
        return {"status": "ok", "assessment": assessment}
