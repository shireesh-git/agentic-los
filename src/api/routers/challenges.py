"""Credit challenges raised by the Credit Challenge Agent against the proposed facility."""

import asyncio

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.dependencies import get_container
from src.application.container import ServiceContainer
from src.models.challenges import ChallengeStatus

router = APIRouter(prefix="/api/cases/{entity_id}/challenges", tags=["challenges"])


class ChallengeReview(BaseModel):
    status: ChallengeStatus | None = None
    response: str | None = None


class WordRequest(BaseModel):
    challenge_ids: list[str] | None = None


@router.get("")
async def list_challenges(entity_id: str, run_id: str | None = None,
                          svc: ServiceContainer = Depends(get_container)):
    """Challenges to the proposal for a run (latest when ``run_id`` is empty), with counts. No decision is made."""
    return svc.challenges.list(entity_id, run_id)


@router.patch("/{challenge_id}")
async def review_challenge(entity_id: str, challenge_id: str, body: ChallengeReview,
                           svc: ServiceContainer = Depends(get_container)):
    """Record how a challenge was dealt with (status) and the RM's response (latest run only)."""
    status = body.status.value if body.status else None
    return {"challenge": svc.challenges.update(entity_id, challenge_id, status=status, response=body.response)}


@router.post("/word")
async def word_challenges(entity_id: str, body: WordRequest | None = None,
                          svc: ServiceContainer = Depends(get_container)):
    """AI wording of challenges in credit-committee language. Triggers, figures and severity are unchanged."""
    ids = body.challenge_ids if body else None
    return await asyncio.to_thread(svc.challenges.word, entity_id, ids)
