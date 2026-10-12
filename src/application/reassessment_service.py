"""
Credit reassessment for a case.

Runs the Credit Reassessment Agent on the case after making sure every input
is current: observations, investigations and challenges (with the analyst's
statuses), the repayment assessment and the stress test. The result is stored
in the case record (``case["reassessment"]``) and saved with the run; it is
recomputed on every read so that resolving an investigation or accepting a
challenge immediately changes the reassessment.
"""

from __future__ import annotations

import logging
import threading

from src.agents.reassessment_agent import reassess

log = logging.getLogger(__name__)


def reassessment_for_case(case: dict) -> dict:
    """The reassessment for a run; never raises, so it cannot fail a pipeline run."""
    try:
        return reassess(case, created_at=case.get("run_at"))
    except Exception as e:
        log.warning("Credit reassessment unavailable for %s: %s", case.get("entity_id"), e)
        return {"available": False, "reason": str(e)}


def _core(result: dict | None) -> dict:
    return {k: v for k, v in (result or {}).items() if k != "created_at"}


class ReassessmentService:
    def __init__(self, cases, persistence, challenges, repayment, stress):
        self.cases = cases
        self.persistence = persistence
        self.challenges = challenges     # ChallengeService (also refreshes observations and investigations)
        self.repayment = repayment       # RepaymentService
        self.stress = stress             # StressTestService
        self._lock = threading.Lock()

    def _ensure(self, case: dict) -> dict:
        self.challenges._ensure(case)
        self.repayment._ensure(case)
        self.stress._ensure(case)
        fresh = reassessment_for_case(case)
        if _core(fresh) != _core(case.get("reassessment")):
            case["reassessment"] = fresh
            self.persistence.save_case_run(case)
        return case["reassessment"]

    def get(self, entity_id: str, run_id: str | None = None) -> dict:
        with self._lock:
            case = self.cases.get_run(entity_id, run_id)
            latest = self.cases.require(entity_id)
            result = self._ensure(case)
        return {"entity_id": entity_id, "run_id": case.get("run_id"),
                "is_latest_run": case.get("run_id") == latest.get("run_id"), "reassessment": result}
