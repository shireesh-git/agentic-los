"""Credit reassessment, facility recommendation and mitigants for a case."""

from fastapi import APIRouter, Depends

from src.api.dependencies import get_container
from src.application.container import ServiceContainer

router = APIRouter(prefix="/api/cases/{entity_id}/reassessment", tags=["reassessment"])


@router.get("")
async def get_reassessment(entity_id: str, run_id: str | None = None, svc: ServiceContainer = Depends(get_container)):
    """Deterministic reassessment of the proposal after observations, investigations, challenges and stress tests."""
    return svc.reassessment.get(entity_id, run_id)
