"""CAM generation in the background, with the progress the RM sees.

The CAM engine (src/agents/pipeline.py) reports each agent and each CAM section as it starts and
finishes. A job keeps two phases, and nothing is shown as done until its own completion event arrives:

    Analysis          the seven analysis agents (ingestion, screening, financials, validation, notes,
                      benchmarking, policy), each with its own time            0–5 %
    Writing the CAM   one entry per CAM section: waiting → writing → done
                      (or reused, when an earlier run already wrote it)         5–95 %
    then              assembling the case and reading its data fields           95–100 %

The engine saves each finished section, so a failed run that is resumed only writes what is left.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Callable, Optional

log = logging.getLogger(__name__)

AGENT_LABELS = {"data_ingestion": "Data ingestion", "pep_screening": "PEP / KYC screening",
                "financial_analysis": "Financial analysis", "validation": "Data validation",
                "benchmark": "Peer benchmarking", "policy": "Credit policy checks",
                "notes_reader": "Auditor's report & notes"}


def _section_plan() -> list[tuple[str, str]]:
    """The CAM sections the writer may produce, in document order (id, title)."""
    try:
        from src.engines.cam_llm_renderer import active_sections
        return [(s["id"], s["title"]) for s in active_sections() if not s.get("skip_llm")]
    except Exception:                                   # the plan is cosmetic: events still drive the view
        return []


def _doc_label(name: str) -> str:
    """annual_report_fy2024.pdf → annual report FY2024"""
    import re
    stem = re.sub(r"\.[A-Za-z0-9]+$", "", name or "").replace("_", " ").replace("-", " ").strip()
    return re.sub(r"\bfy\s?(\d{2,4})\b", lambda m: "FY" + m.group(1), stem, flags=re.I)


class CamJob:
    def __init__(self, case_id: str, entity_id: str, reason: str = "generate"):
        self.case_id, self.entity_id, self.reason = case_id, entity_id, reason
        self.state = "queued"
        self.started = time.monotonic()
        self.started_at = datetime.now().isoformat(timespec="seconds")
        self.agents = {a: {"status": "waiting", "ms": None} for a in AGENT_LABELS}
        self.writer = "waiting"                         # the narrative agent: waiting | running | done | failed
        self.sections: dict[str, dict] = {sid: {"title": title, "status": "waiting"} for sid, title in _section_plan()}
        self.sections_total = 0
        self.sections_done = 0
        self.sections_reused = 0
        self.first_section_at: Optional[float] = None
        self.finishing = False
        self.error: Optional[str] = None
        self.result: Optional[dict] = None
        self._lock = threading.Lock()

    # ── engine events ────────────────────────────────────────────────────────

    def on_event(self, ev: dict) -> None:
        with self._lock:
            t, agent = ev.get("type"), ev.get("agent")
            if t == "agent_start":
                self.state = "running"
                if agent in self.agents:
                    self.agents[agent]["status"] = "running"
                elif agent == "narrative":
                    self.writer = "running"
            elif t == "agent_complete":
                ok = ev.get("status") == "completed"
                if agent in self.agents:
                    self.agents[agent] = {"status": "done" if ok else (ev.get("status") or "failed"),
                                          "ms": ev.get("duration_ms")}
                elif agent == "narrative":
                    self.writer = "done" if ok else "failed"
                    self.finishing = ok
            elif t == "doc_progress":
                self.docs = {"done": int(ev.get("done") or 0), "total": int(ev.get("total") or 0),
                             "name": ev.get("name") or "", "cached": bool(ev.get("cached"))}
            elif t == "section_start":
                sid = ev.get("section")
                self.sections_total = int(ev.get("total") or self.sections_total)
                self.sections.setdefault(sid, {"title": ev.get("title") or sid})["status"] = "writing"
                if self.first_section_at is None:
                    self.first_section_at = time.monotonic()
            elif t == "section_complete":
                sid = ev.get("section")
                self.sections_total = int(ev.get("total") or self.sections_total)
                sec = self.sections.setdefault(sid, {"title": ev.get("title") or sid})
                sec["status"] = "reused" if ev.get("resumed") else "done"
                # figures the AI quoted that are not in the data it was given (after one corrective rewrite)
                sec["flagged"] = list(ev.get("flagged") or [])
                sec["rewritten"] = bool(ev.get("rewritten"))
                sec["model"] = ev.get("model")
                self.sections_done += 1
                if ev.get("resumed"):
                    self.sections_reused += 1

    def figure_check(self) -> dict:
        """The figures check over the AI-written sections: which quote figures not in their data."""
        with self._lock:
            done = {k: v for k, v in self.sections.items() if v.get("status") in ("done", "reused")}
            return {"sections_checked": len(done),
                    "rewritten": [v["title"] for v in done.values() if v.get("rewritten")],
                    "flagged": [{"section": k, "title": v["title"], "figures": v.get("flagged") or []}
                                for k, v in done.items() if v.get("flagged")],
                    "models": sorted({v["model"] for v in done.values() if v.get("model")})}

    # ── what the screen shows ────────────────────────────────────────────────

    def percent(self) -> int:
        if self.state == "done":
            return 100
        done = sum(1 for a in self.agents.values() if a["status"] == "done")
        pct = 5.0 * done / len(self.agents)
        docs = getattr(self, "docs", None)
        base = 5.0
        if docs and docs["total"]:
            # documents read cold can take minutes: they get their own share of the bar
            base = 20.0
            pct = max(pct, 18.0 * min(docs["done"], docs["total"]) / docs["total"])
        if self.sections_total:
            pct = base + (95.0 - base) * min(self.sections_done, self.sections_total) / self.sections_total
        if self.finishing:
            pct = 96.0
        return int(min(pct, 99))

    def eta_seconds(self) -> Optional[int]:
        written = self.sections_done - self.sections_reused
        left = max(self.sections_total - self.sections_done, 0)
        if self.finishing:
            return 5
        if not self.first_section_at or written <= 0:
            return None
        return int((time.monotonic() - self.first_section_at) / written * left) + 5

    def step_label(self) -> str:
        if self.state == "done":
            return "CAM ready"
        if self.state == "failed":
            return "Generation stopped"
        if self.finishing:
            return "Assembling the CAM and extracting credit data fields"
        if self.writer == "running":
            total = self.sections_total or len(self.sections)
            return f"Writing the CAM · section {min(self.sections_done + 1, total)} of {total}"
        docs = getattr(self, "docs", None)
        if docs and self.agents.get("data_ingestion", {}).get("status") == "running":
            return (f"Reading documents · {docs['done']} of {docs['total']} · {_doc_label(docs['name'])}"
                    + (" (already read)" if docs["cached"] else ""))
        running = [AGENT_LABELS[a] for a, s in self.agents.items() if s["status"] == "running"]
        return "Analysis · " + ", ".join(running) if running else "Starting the CAM engine"

    def view(self) -> dict:
        with self._lock:
            sections = self.sections
            if self.state == "done" or self.finishing:
                # sections the writer had no data for are not sent to it: shown as not applicable, not pending
                sections = {k: ({**v, "status": "not_applicable"} if v["status"] == "waiting" else v)
                            for k, v in sections.items()}
            analysis_done = all(a["status"] == "done" for a in self.agents.values())
            return {"state": self.state, "reason": self.reason, "percent": self.percent(),
                    "eta_seconds": self.eta_seconds(), "step": self.step_label(),
                    "elapsed_seconds": int(time.monotonic() - self.started), "started_at": self.started_at,
                    "phases": [
                        {"id": "analysis", "label": "Analysis",
                         "status": "done" if analysis_done else ("running" if self.state == "running" else "waiting"),
                         "items": [{"id": a, "label": AGENT_LABELS[a], "status": s["status"], "ms": s["ms"]}
                                   for a, s in self.agents.items()]},
                        {"id": "writing", "label": "Writing the CAM", "status": self.writer,
                         "items": [{"id": k, "label": v["title"], "status": v["status"]} for k, v in sections.items()]}],
                    "sections": {"total": self.sections_total, "done": self.sections_done,
                                 "reused": self.sections_reused,
                                 "writing": [v["title"] for v in sections.values() if v["status"] == "writing"][:4]},
                    "error": self.error}


class CamJobs:
    """One background CAM run per case at a time."""

    def __init__(self, run_engine: Callable, on_done: Callable, on_failed: Callable):
        self._run_engine = run_engine        # (entity_id, overrides, on_progress) -> (case, pipeline_log)
        self._on_done = on_done              # (case_id, job, engine_case)
        self._on_failed = on_failed          # (case_id, job, error)
        self._jobs: dict[str, CamJob] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    def get(self, case_id: str) -> Optional[CamJob]:
        return self._jobs.get(case_id)

    def running(self, case_id: str) -> bool:
        t = self._threads.get(case_id)
        return bool(t and t.is_alive())

    def start(self, case_id: str, entity_id: str, overrides: Optional[dict], reason: str) -> CamJob:
        with self._lock:
            if self.running(case_id):
                return self._jobs[case_id]
            job = CamJob(case_id, entity_id, reason)
            self._jobs[case_id] = job
            t = threading.Thread(target=self._run, args=(job, overrides), name=f"cam-{case_id}", daemon=True)
            self._threads[case_id] = t
            t.start()
            return job

    def wait(self, case_id: str, timeout: Optional[float] = None) -> Optional[CamJob]:
        t = self._threads.get(case_id)
        if t:
            t.join(timeout)
        return self._jobs.get(case_id)

    def _run(self, job: CamJob, overrides: Optional[dict]) -> None:
        job.state = "running"
        try:
            engine_case, _ = self._run_engine(job.entity_id, overrides, job.on_event)
            job.result = engine_case
            self._on_done(job.case_id, job, engine_case)
            job.state = "done"
        except Exception as e:                                   # shown on the screen; Resume re-runs
            log.exception("CAM generation failed for %s", job.case_id)
            job.state, job.error = "failed", str(e)[:400]
            try:
                self._on_failed(job.case_id, job, job.error)
            except Exception:
                log.exception("Recording the CAM failure for %s failed", job.case_id)
