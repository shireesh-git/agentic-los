"""
Approval workflow API.

Actor identity comes from the ``X-User-Id`` and ``X-User-Role`` headers. This
is a placeholder until the platform has real authentication (SSO); do not
expose these routes beyond a trusted network before that is in place.
"""

from fastapi import APIRouter, Depends, Header, Request

from src.api.dependencies import get_container
from src.application.approval_service import Actor
from src.application.container import ServiceContainer
from src.core.config_manager import config

router = APIRouter(prefix="/api", tags=["approvals"])


def get_actor(x_user_id: str = Header(default=""), x_user_role: str = Header(default="")) -> Actor:
    return Actor(user_id=x_user_id.strip(), role=x_user_role.strip())


@router.get("/approvals/authority-matrix")
async def authority_matrix(svc: ServiceContainer = Depends(get_container)):
    """Delegation-of-powers levels, maker roles and the decision TAT from config/approval.yaml."""
    return {"levels": svc.approvals.authority_matrix(),
            "maker_roles": list(svc.approvals.matrix.maker_roles),
            "decision_tat_days": int(config.get("approval", "decision_tat_days", default=3) or 3)}


@router.get("/approvals/queue")
async def approval_queue(authority: str, svc: ServiceContainer = Depends(get_container)):
    """Submitted cases that the given authority level may decide."""
    return {"authority": authority, "cases": svc.approvals.queue(authority)}


@router.get("/cases/{entity_id}/workflow")
async def workflow_status(entity_id: str, svc: ServiceContainer = Depends(get_container)):
    """Status, required authority, allowed actions and decision history."""
    return svc.approvals.status(entity_id)


@router.post("/cases/{entity_id}/workflow/{action}")
async def workflow_action(entity_id: str, action: str, request: Request,
                          actor: Actor = Depends(get_actor), svc: ServiceContainer = Depends(get_container)):
    """Actions: submit, recall (maker); approve, reject, return (approving authority).

    Body (optional): { "comments": str, "conditions": [str] }
    """
    body = await request.json() if await request.body() else {}
    return svc.approvals.act(entity_id, action, actor,
                             comments=body.get("comments", ""),
                             conditions=body.get("conditions") or [])
