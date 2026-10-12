"""Final (banker) CAM — 12 composed sections with provenance; the 21-section CAM stays the analyst view."""

import asyncio

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel

from src.api.dependencies import get_container
from src.application.container import ServiceContainer
from src.rendering import generate_cam_pdf, markdown_to_html

router = APIRouter(prefix="/api/cases/{entity_id}", tags=["final-cam"])


class InterpretRequest(BaseModel):
    section_ids: list[str] | None = None


@router.get("/final-cam")
async def get_final_cam(entity_id: str, run_id: str | None = None, svc: ServiceContainer = Depends(get_container)):
    """The 12-section banker CAM as structured JSON (facts, tables, findings, provenance, drill-down)."""
    return svc.final_cam.get(entity_id, run_id)


@router.get("/final-cam-html")
async def get_final_cam_html(entity_id: str, run_id: str | None = None, svc: ServiceContainer = Depends(get_container)):
    md, company = svc.final_cam.markdown(entity_id, run_id)
    return Response(content=markdown_to_html(md, company), media_type="text/html")


@router.get("/final-cam-pdf")
async def get_final_cam_pdf(entity_id: str, run_id: str | None = None, svc: ServiceContainer = Depends(get_container)):
    md, company = svc.final_cam.markdown(entity_id, run_id)
    return Response(content=generate_cam_pdf(md, company), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{entity_id}_CAM_final.pdf"'})


@router.post("/final-cam/interpret")
async def interpret_final_cam(entity_id: str, body: InterpretRequest | None = None,
                              svc: ServiceContainer = Depends(get_container)):
    """On-demand AI interpretation per section (labelled AI; facts and recommendation unchanged)."""
    return await asyncio.to_thread(svc.final_cam.interpret, entity_id, body.section_ids if body else None)
