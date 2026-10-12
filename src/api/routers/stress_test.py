"""Stress test results (base, downside, severe downside) for a case."""

from fastapi import APIRouter, Depends

from src.api.dependencies import get_container
from src.application.container import ServiceContainer

router = APIRouter(prefix="/api/cases/{entity_id}/stress-test", tags=["stress-test"])


@router.get("")
async def get_stress_test(entity_id: str, run_id: str | None = None, svc: ServiceContainer = Depends(get_container)):
    """Deterministic stressed metrics and policy breaches for a run (latest when ``run_id`` is empty)."""
    return svc.stress.get(entity_id, run_id)
