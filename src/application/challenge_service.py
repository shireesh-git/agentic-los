"""
Credit challenges for a case: raise from the analysis, record the analyst's handling, optional AI wording.

Challenges live in the case record (``case["challenges"]``), saved with the run
in ``case_runs`` like observations and investigations. Every read re-runs the
Credit Challenge Agent on the current observations and investigation status
and merges with stored challenges, so resolving an investigation or dismissing
an observation is reflected without a pipeline run.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime

from src.agents.challenge_agent import CreditChallengeAgent, sync_challenges
from src.application.errors import ConflictError, InvalidRequestError, NotFoundError
from src.models.challenges import ChallengeStatus

log = logging.getLogger(__name__)


def challenges_for_case(fact_pack: dict, observations: list[dict], investigations: list[dict],
                        entity_id: str, created_at: str | None) -> list[dict]:
    """Challenges for a run; never raises, so a rule problem cannot fail a pipeline run."""
    try:
        return CreditChallengeAgent().challenge(fact_pack or {}, observations or [], investigations or [],
                                                entity_id, created_at=created_at)
    except Exception as e:
        log.warning("Credit challenges unavailable for %s: %s", entity_id, e)
        return []


def summarize(challenges: list[dict]) -> dict:
    by_status = {s.value: 0 for s in ChallengeStatus}
    open_by_severity = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for ch in challenges:
        by_status[ch["status"]] = by_status.get(ch["status"], 0) + 1
        if ch["status"] == ChallengeStatus.OPEN.value:
            open_by_severity[ch["severity"]] = open_by_severity.get(ch["severity"], 0) + 1
    return {"total": len(challenges), "open": by_status["OPEN"], "by_status": by_status,
            "open_by_severity": open_by_severity}


class ChallengeService:
    def __init__(self, cases, persistence, investigations, llm_factory=None):
        self.cases = cases
        self.persistence = persistence
        self.investigations = investigations      # InvestigationService (owns observations too)
        self.llm_factory = llm_factory or investigations.llm_factory
        self._lock = threading.Lock()

    def _ensure(self, case: dict) -> list[dict]:
        tasks = self.investigations._ensure(case)
        planned = challenges_for_case(case.get("fact_pack"), case.get("observations"), tasks,
                                      case["entity_id"], case.get("run_at"))
        merged = sync_challenges(planned, case.get("challenges"))
        if merged != case.get("challenges"):
            case["challenges"] = merged
            self.persistence.save_case_run(case)
        return case["challenges"]

    def list(self, entity_id: str, run_id: str | None = None) -> dict:
        with self._lock:
            case = self.cases.get_run(entity_id, run_id)
            latest = self.cases.require(entity_id)
            challenges = self._ensure(case)
        labels = {o["observation_id"]: {"title": o.get("title"), "severity": o.get("severity")}
                  for o in case.get("observations") or []}
        labels.update({t["investigation_id"]: {"title": t.get("title"), "priority": t.get("priority"),
                                               "status": t.get("status")}
                       for t in case.get("investigations") or []})
        return {"entity_id": entity_id, "run_id": case.get("run_id"),
                "is_latest_run": case.get("run_id") == latest.get("run_id"),
                "challenges": challenges, "links": labels, "summary": summarize(challenges)}

    def update(self, entity_id: str, challenge_id: str, status: str | None = None,
               response: str | None = None, updated_by: str = "RM") -> dict:
        if status is not None and status not in {s.value for s in ChallengeStatus}:
            raise InvalidRequestError(f"Unknown status '{status}'")
        with self._lock:
            case = self.cases.require(entity_id, "Case not found — run the pipeline first.")
            ch = self._find(self._ensure(case), challenge_id)
            if status is not None:
                ch["status"] = status
            ch["review"] = {
                "response": (response if response is not None else (ch.get("review") or {}).get("response", "")) or "",
                "updated_by": updated_by,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
            self.persistence.save_case_run(case)
            return ch

    def word(self, entity_id: str, challenge_ids: list[str] | None = None) -> dict:
        """LLM wording for the given challenges (all open ones when none given)."""
        from src.services.challenge_narrator import word_challenges

        with self._lock:
            case = self.cases.require(entity_id, "Case not found — run the pipeline first.")
            challenges = self._ensure(case)
        targets = ([self._find(challenges, cid) for cid in challenge_ids] if challenge_ids
                   else [ch for ch in challenges if ch["status"] == ChallengeStatus.OPEN.value])
        if not targets:
            return {"results": {}, "challenges": challenges}
        llm = self.llm_factory()
        if getattr(llm, "name", "") == "mock":
            raise ConflictError("AI wording needs a configured LLM provider (the active provider is 'mock').")
        results = word_challenges(targets, llm, case.get("company_name") or entity_id)
        with self._lock:
            for cid, result in results.items():
                if result["status"] == "ok":
                    self._find(challenges, cid)["ai_wording"] = result["ai_wording"]
            self.persistence.save_case_run(case)
        return {"results": {cid: {k: v for k, v in r.items() if k != "ai_wording"} for cid, r in results.items()},
                "challenges": challenges}

    @staticmethod
    def _find(challenges: list[dict], challenge_id: str) -> dict:
        for ch in challenges:
            if ch.get("challenge_id") == challenge_id:
                return ch
        raise NotFoundError(f"Challenge {challenge_id} not found")
