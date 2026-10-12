"""Cash flow & repayment assessment for a case."""

import asyncio

from fastapi import APIRouter, Depends

from src.api.dependencies import get_container
from src.application.container import ServiceContainer

router = APIRouter(prefix="/api/cases/{entity_id}/repayment", tags=["repayment"])


@router.get("")
async def get_repayment(entity_id: str, run_id: str | None = None, svc: ServiceContainer = Depends(get_container)):
    """Deterministic repayment assessment for a run (latest when ``run_id`` is empty)."""
    return svc.repayment.get(entity_id, run_id)


@router.post("/explain")
async def explain_repayment(entity_id: str, svc: ServiceContainer = Depends(get_container)):
    """AI explanation of the assessment. Grades and figures are unchanged."""
    return await asyncio.to_thread(svc.repayment.explain, entity_id)
