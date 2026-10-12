"""Analyst copilot chat, grounded in the case, extraction and Probe42 context."""

from fastapi import APIRouter, Depends, HTTPException, Request

from src.api.dependencies import get_container
from src.application.container import ServiceContainer
from src.services.analyst_chat import (
    chat as analyst_chat_fn, clear_session, get_session_history, list_sessions,
)
from src.services.probe_service import probe_context_text

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/sessions")
async def chat_sessions():
    """All active chat sessions."""
    return {"sessions": list_sessions()}


@router.post("/{entity_id}")
async def chat_endpoint(entity_id: str, request: Request, svc: ServiceContainer = Depends(get_container)):
    body = await request.json()
    message = body.get("message", "").strip()
    if not message:
        raise HTTPException(400, "Provide 'message' in request body")
    company = svc.companies.get(entity_id) or {}
    return await analyst_chat_fn(
        entity_id=entity_id,
        user_message=message,
        case_data=svc.cases.get(entity_id),
        extraction=svc.state.extractions.get(entity_id),
        etb_analysis=svc.state.etb_analytics.get(entity_id),
        probe_context=probe_context_text(company.get("probe_bundle")),
    )


@router.get("/{entity_id}/history")
async def chat_history(entity_id: str):
    return {"entity_id": entity_id, "messages": get_session_history(entity_id)}


@router.delete("/{entity_id}")
async def chat_clear(entity_id: str):
    clear_session(entity_id)
    return {"status": "cleared", "entity_id": entity_id}
