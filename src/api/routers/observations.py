"""Credit risk observations: list, analyst review, on-demand AI explanations."""

import asyncio

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.dependencies import get_container
from src.application.container import ServiceContainer
from src.models.observations import ObservationStatus

router = APIRouter(prefix="/api/cases/{entity_id}/observations", tags=["observations"])


class ObservationReview(BaseModel):
    status: ObservationStatus | None = None
    note: str | None = None


class ExplainRequest(BaseModel):
    observation_ids: list[str] | None = None


@router.get("")
async def list_observations(entity_id: str, run_id: str | None = None,
                            svc: ServiceContainer = Depends(get_container)):
    """Deterministic credit observations for a run (latest when ``run_id`` is empty), with counts."""
    return svc.observations.list(entity_id, run_id)


@router.patch("/{observation_id}")
async def review_observation(entity_id: str, observation_id: str, body: ObservationReview,
                             svc: ServiceContainer = Depends(get_container)):
    """Set an observation's analyst status and/or note (latest run only)."""
    status = body.status.value if body.status else None
    return {"observation": svc.observations.update(entity_id, observation_id, status=status, note=body.note)}


@router.post("/explain")
async def explain_observations(entity_id: str, body: ExplainRequest | None = None,
                               svc: ServiceContainer = Depends(get_container)):
    """AI wording for detected observations. The LLM explains; it does not detect or score."""
    ids = body.observation_ids if body else None
    return await asyncio.to_thread(svc.observations.explain, entity_id, ids)
