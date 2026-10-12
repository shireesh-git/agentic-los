"""Credit cases: list, fetch, and run the analysis pipeline (blocking or streamed)."""

import asyncio
import json
import logging
import threading
import traceback

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from src.api.dependencies import get_container
from src.application.container import ServiceContainer
from src.application.errors import ApplicationError

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["cases"])

_KEEPALIVE_SECONDS = 15


def _run_summary(case: dict) -> dict:
    return {
        "recommendation": case["recommendation"],
        "risk_grade": case["risk_grade"],
        "composite_score": case["composite_score"],
        "narrative_mode": case.get("narrative_mode", "template"),
    }


@router.get("/cases")
async def list_cases(svc: ServiceContainer = Depends(get_container)):
    return {"cases": svc.cases.summaries()}


@router.get("/cases/{entity_id}")
async def get_case(entity_id: str, svc: ServiceContainer = Depends(get_container)):
    """The case record. In-memory bookkeeping keys (``_``-prefixed) are not sent."""
    case = svc.cases.require(entity_id, "Case not found — run the pipeline first.")
    public = {key: value for key, value in case.items() if not key.startswith("_")}
    public["documents_changed"] = bool(case.get("_documents_changed"))
    return public


@router.get("/cases/{entity_id}/runs")
async def list_runs(entity_id: str, limit: int = 20, svc: ServiceContainer = Depends(get_container)):
    """Pipeline attempts for a company (running / completed / failed, with errors)."""
    return {"entity_id": entity_id, "runs": svc.cases.run_history(entity_id, limit)}


@router.post("/cases/{entity_id}/run")
async def run_case(entity_id: str, svc: ServiceContainer = Depends(get_container)):
    svc.companies.require(entity_id)
    try:
        case, pipeline_log = await asyncio.to_thread(svc.cases.run, entity_id)
    except ApplicationError:
        raise
    except Exception as e:
        log.error("Pipeline failed for %s: %s", entity_id, e)
        traceback.print_exc()
        raise HTTPException(500, f"Pipeline failed: {str(e)}")
    return {"status": "completed", "entity_id": entity_id, **_run_summary(case),
            "pipeline_log": pipeline_log}


@router.get("/cases/{entity_id}/run-stream")
async def run_case_stream(entity_id: str, svc: ServiceContainer = Depends(get_container)):
    """Server-sent events: run the pipeline and stream agent/section progress."""
    svc.companies.require(entity_id)
    # The pipeline runs in a worker thread and hands events to the event loop, so
    # the stream wakes only when there is something to send (no polling).
    loop = asyncio.get_running_loop()
    events: asyncio.Queue = asyncio.Queue()

    def _publish(event: dict) -> None:
        try:
            loop.call_soon_threadsafe(events.put_nowait, event)
        except RuntimeError:  # event loop closed (server shutting down)
            pass

    def _pipeline_thread():
        try:
            case, _ = svc.cases.run(entity_id, on_progress=_publish)
            _publish({"type": "done", "entity_id": entity_id, **_run_summary(case)})
        except Exception as e:
            _publish({"type": "error", "message": str(e)})

    threading.Thread(target=_pipeline_thread, daemon=True).start()

    async def _event_generator():
        while True:
            try:
                event = await asyncio.wait_for(events.get(), timeout=_KEEPALIVE_SECONDS)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"  # keeps proxies from closing a quiet stream
                continue
            yield f"data: {json.dumps(event)}\n\n"
            if event.get("type") in ("done", "error"):
                break

    return StreamingResponse(_event_generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/pipeline/run-all")
async def run_all(svc: ServiceContainer = Depends(get_container)):
    """Run every company in turn; one failure is reported and does not stop the batch."""

    def _run_all() -> list[dict]:
        results = []
        for entity_id in list(svc.state.companies):
            if svc.approvals.is_locked_for_rerun(entity_id):
                results.append({"entity_id": entity_id, "skipped": "with approving authority"})
                continue
            try:
                case, _ = svc.cases.run(entity_id)
            except Exception as e:
                log.error("Pipeline failed for %s during run-all: %s", entity_id, e)
                results.append({"entity_id": entity_id, "error": str(e)})
                continue
            results.append({"entity_id": entity_id, "recommendation": case["recommendation"],
                            "risk_grade": case["risk_grade"]})
        return results

    results = await asyncio.to_thread(_run_all)
    failed = sum(1 for r in results if "error" in r)
    return {"status": "completed_with_errors" if failed else "completed",
            "failed": failed, "results": results}
