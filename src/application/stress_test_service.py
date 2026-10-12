"""
Stress test results for a case.

Results are stored in the case record (``case["stress_test"]``) and saved with
the run in ``case_runs``. They need the latest audited FinancialStatement, which
the case record does not carry, so they are computed when the run is built and,
for older runs, from the company record — with a check that its base case still
reproduces the run's recorded ratios.
"""

from __future__ import annotations

import logging
import threading

from src.engines.stress_test_engine import GENERATED_BY, run_stress_tests

log = logging.getLogger(__name__)


def latest_statement(company: dict | None):
    financials = (company or {}).get("financials") or {}
    return financials[sorted(financials)[-1]] if financials else None


def stress_for_case(company: dict | None, fact_pack: dict, entity_id: str, created_at: str | None) -> dict:
    """Stress results for a run; never raises, so it cannot fail a pipeline run."""
    try:
        return run_stress_tests(latest_statement(company), fact_pack or {}, entity_id, created_at=created_at)
    except Exception as e:
        log.warning("Stress test unavailable for %s: %s", entity_id, e)
        return {"available": False, "reason": str(e)}


class StressTestService:
    def __init__(self, cases, persistence, companies):
        self.cases = cases
        self.persistence = persistence
        self.companies = companies
        self._lock = threading.Lock()

    def _ensure(self, case: dict) -> dict:
        stored = case.get("stress_test")
        if stored is None or (stored.get("available") and stored.get("generated_by") != GENERATED_BY):
            case["stress_test"] = stress_for_case(self.companies.get(case["entity_id"]), case.get("fact_pack"),
                                                  case["entity_id"], case.get("run_at"))
            self.persistence.save_case_run(case)
        return case["stress_test"]

    def get(self, entity_id: str, run_id: str | None = None) -> dict:
        with self._lock:
            case = self.cases.get_run(entity_id, run_id)
            latest = self.cases.require(entity_id)
            result = self._ensure(case)
        return {"entity_id": entity_id, "run_id": case.get("run_id"),
                "is_latest_run": case.get("run_id") == latest.get("run_id"), "stress_test": result}
