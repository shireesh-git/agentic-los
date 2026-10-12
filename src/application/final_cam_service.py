"""
Final (banker) CAM for a case — M7.

Stored in the case record (``case["final_cam"]``) and saved with the run. Each
read recomposes it from the current M1–M6 state (analyst statuses included);
a stored AI interpretation is kept for a section only while that section's
content is unchanged.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading

from src.application.errors import ConflictError, InvalidRequestError, NotFoundError
from src.engines.cam_composer import compose_final_cam, render_final_cam_markdown

log = logging.getLogger(__name__)


def final_cam_for_case(case: dict) -> dict:
    """The composed CAM for a run; never raises, so it cannot fail a pipeline run."""
    try:
        return compose_final_cam(case)
    except Exception as e:
        log.warning("Final CAM unavailable for %s: %s", case.get("entity_id"), e)
        return {"available": False, "reason": str(e)}


def _digest(section: dict) -> str:
    from src.services.cam_composer_narrator import section_content
    return hashlib.sha1(json.dumps(section_content(section), sort_keys=True, default=str).encode()).hexdigest()


class FinalCamService:
    def __init__(self, cases, persistence, reassessment, llm_factory=None):
        self.cases = cases
        self.persistence = persistence
        self.reassessment = reassessment      # ReassessmentService (refreshes M1–M6)
        self.llm_factory = llm_factory or reassessment.challenges.llm_factory
        self._lock = threading.Lock()

    def _ensure(self, case: dict) -> dict:
        self.reassessment._ensure(case)
        fresh = final_cam_for_case(case)
        stored = case.get("final_cam") or {}
        old = {s["id"]: s for s in stored.get("sections") or []}
        for s in fresh.get("sections") or []:
            prev = old.get(s["id"])
            if prev and prev.get("ai_interpretation") and prev.get("_digest") == _digest(s):
                s["ai_interpretation"] = prev["ai_interpretation"]
            s["_digest"] = _digest(s)
        if fresh != stored:
            case["final_cam"] = fresh
            self.persistence.save_case_run(case)
        return case["final_cam"]

    def get(self, entity_id: str, run_id: str | None = None) -> dict:
        with self._lock:
            case = self.cases.get_run(entity_id, run_id)
            latest = self.cases.require(entity_id)
            final = self._ensure(case)
        return {"entity_id": entity_id, "run_id": case.get("run_id"),
                "is_latest_run": case.get("run_id") == latest.get("run_id"), "final_cam": final}

    def markdown(self, entity_id: str, run_id: str | None = None) -> tuple[str, str]:
        with self._lock:
            case = self.cases.get_run(entity_id, run_id)
            final = self._ensure(case)
        return render_final_cam_markdown(final), case.get("company_name", entity_id)

    def interpret(self, entity_id: str, section_ids: list[str] | None = None) -> dict:
        """AI interpretation for the given sections (all when none given). Facts and recommendation are unchanged."""
        from src.services.cam_composer_narrator import interpret_sections

        with self._lock:
            case = self.cases.require(entity_id, "Case not found — run the pipeline first.")
            final = self._ensure(case)
        if not final.get("available"):
            raise InvalidRequestError("The final CAM is not available for this case.")
        by_id = {s["id"]: s for s in final["sections"]}
        unknown = [sid for sid in section_ids or [] if sid not in by_id]
        if unknown:
            raise NotFoundError(f"Unknown section(s): {', '.join(unknown)}")
        targets = [by_id[sid] for sid in section_ids] if section_ids else list(by_id.values())
        llm = self.llm_factory()
        if getattr(llm, "name", "") == "mock":
            raise ConflictError("AI interpretation needs a configured LLM provider (the active provider is 'mock').")
        results = interpret_sections(targets, llm, case.get("company_name") or entity_id)
        with self._lock:
            for sid, r in results.items():
                if r["status"] == "ok":
                    by_id[sid]["ai_interpretation"] = r["ai_interpretation"]
            self.persistence.save_case_run(case)
        return {"results": {sid: {k: v for k, v in r.items() if k != "ai_interpretation"} for sid, r in results.items()},
                "final_cam": final}
