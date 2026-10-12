"""Investigations opened by the Investigation Agent from credit observations."""

import asyncio

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.dependencies import get_container
from src.application.container import ServiceContainer
from src.models.investigations import InvestigationStatus

router = APIRouter(prefix="/api/cases/{entity_id}/investigations", tags=["investigations"])


class InvestigationReview(BaseModel):
    status: InvestigationStatus | None = None
    note: str | None = None


class PhraseRequest(BaseModel):
    investigation_ids: list[str] | None = None


@router.get("")
async def list_investigations(entity_id: str, run_id: str | None = None,
                              svc: ServiceContainer = Depends(get_container)):
    """Investigation tasks for a run (latest when ``run_id`` is empty), re-planned from its observations."""
    return svc.investigations.list(entity_id, run_id)


@router.patch("/{investigation_id}")
async def review_investigation(entity_id: str, investigation_id: str, body: InvestigationReview,
                               svc: ServiceContainer = Depends(get_container)):
    """Set a task's status and/or note (latest run only)."""
    status = body.status.value if body.status else None
    return {"investigation": svc.investigations.update(entity_id, investigation_id, status=status, note=body.note)}


@router.post("/phrase")
async def phrase_investigations(entity_id: str, body: PhraseRequest | None = None,
                                svc: ServiceContainer = Depends(get_container)):
    """LLM-worded borrower information request. The task itself is not changed."""
    ids = body.investigation_ids if body else None
    return await asyncio.to_thread(svc.investigations.phrase, entity_id, ids)
