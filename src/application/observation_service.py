"""
Credit observations for a case: read, analyst review, on-demand AI wording.

Observations live inside the case record (``case["observations"]``), which is
already persisted per run in ``case_runs``, so review status and AI wording are
saved by re-saving that run — no separate store. Cases recorded before this
feature get their observations computed from the stored fact pack on first read.
Earlier runs are read-only, like their CAMs.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Callable

from src.application.errors import ConflictError, InvalidRequestError, NotFoundError
from src.engines.observation_engine import detect_observations, summarize
from src.models.observations import ObservationStatus

log = logging.getLogger(__name__)


def observations_for_fact_pack(fact_pack: dict, entity_id: str, created_at: str | None) -> list[dict]:
    """Observations for a run; never raises, so a detector problem cannot fail a pipeline run."""
    try:
        return detect_observations(fact_pack or {}, entity_id, created_at=created_at)
    except Exception as e:
        log.warning("Credit observations unavailable for %s: %s", entity_id, e)
        return []


def _default_llm_factory():
    from src.core.config_manager import config
    from src.core.llm_provider import create_llm_provider
    return create_llm_provider(config.get_active_llm_provider())


class ObservationService:
    def __init__(self, cases, persistence, llm_factory: Callable = _default_llm_factory):
        self.cases = cases
        self.persistence = persistence
        self.llm_factory = llm_factory
        self._lock = threading.Lock()

    # ── Queries ──────────────────────────────────────────────────────────

    def _ensure(self, case: dict) -> list[dict]:
        if "observations" not in case:
            case["observations"] = observations_for_fact_pack(case.get("fact_pack"), case["entity_id"],
                                                              case.get("run_at"))
            self.persistence.save_case_run(case)
        return case["observations"]

    def list(self, entity_id: str, run_id: str | None = None) -> dict:
        case = self.cases.get_run(entity_id, run_id)
        latest = self.cases.require(entity_id)
        observations = self._ensure(case)
        return {
            "entity_id": entity_id,
            "run_id": case.get("run_id"),
            "is_latest_run": case.get("run_id") == latest.get("run_id"),
            "company_name": case.get("company_name"),
            "observations": observations,
            "summary": summarize(observations),
        }

    # ── Analyst review ───────────────────────────────────────────────────

    def update(self, entity_id: str, observation_id: str, status: str | None = None,
               note: str | None = None, updated_by: str = "RM") -> dict:
        if status is not None and status not in {s.value for s in ObservationStatus}:
            raise InvalidRequestError(f"Unknown status '{status}'")
        with self._lock:
            case = self.cases.require(entity_id, "Case not found — run the pipeline first.")
            obs = self._find(self._ensure(case), observation_id)
            if status is not None:
                obs["status"] = status
            obs["review"] = {
                "note": (note if note is not None else (obs.get("review") or {}).get("note", "")) or "",
                "updated_by": updated_by,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
            self.persistence.save_case_run(case)
            return obs

    # ── AI wording ───────────────────────────────────────────────────────

    def explain(self, entity_id: str, observation_ids: list[str] | None = None) -> dict:
        """Ask the LLM to word the given observations (all when none given)."""
        from src.services.observation_narrator import explain_observations

        case = self.cases.require(entity_id, "Case not found — run the pipeline first.")
        observations = self._ensure(case)
        targets = ([self._find(observations, oid) for oid in observation_ids] if observation_ids
                   else list(observations))
        if not targets:
            return {"results": {}, "observations": observations}
        llm = self.llm_factory()
        if getattr(llm, "name", "") == "mock":
            raise ConflictError("AI explanations need a configured LLM provider (the active provider is 'mock').")
        results = explain_observations(targets, llm, case.get("company_name") or entity_id)
        with self._lock:
            for oid, result in results.items():
                if result["status"] == "ok":
                    self._find(observations, oid)["ai_explanation"] = result["ai_explanation"]
            self.persistence.save_case_run(case)
        return {"results": {oid: {k: v for k, v in r.items() if k != "ai_explanation"} for oid, r in results.items()},
                "observations": observations}

    @staticmethod
    def _find(observations: list[dict], observation_id: str) -> dict:
        for obs in observations:
            if obs.get("observation_id") == observation_id:
                return obs
        raise NotFoundError(f"Observation {observation_id} not found")
