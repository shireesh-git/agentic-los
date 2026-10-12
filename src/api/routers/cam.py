"""CAM documents: markdown, HTML, PDF, one-pager, RM comments and section edits."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from src.api.dependencies import get_container
from src.application.container import ServiceContainer

router = APIRouter(prefix="/api/cases/{entity_id}", tags=["cam"])


@router.get("/cam")
async def get_cam(entity_id: str, run_id: str | None = None, svc: ServiceContainer = Depends(get_container)):
    return {"cam_text": svc.cam.cam_text(entity_id, run_id)}


@router.get("/comments")
async def get_cam_comments(entity_id: str, run_id: str | None = None, svc: ServiceContainer = Depends(get_container)):
    svc.cases.require(entity_id)
    return {"comments": svc.cam.load_comments(entity_id, run_id)}


@router.put("/comments")
async def update_cam_comments(entity_id: str, request: Request, svc: ServiceContainer = Depends(get_container)):
    body = await request.json()
    comments = svc.cam.save_comments(entity_id, body.get("comments", {}))
    return {"status": "saved", "comments": comments}


@router.get("/cam-section-edits")
async def get_cam_section_edits(entity_id: str, run_id: str | None = None, svc: ServiceContainer = Depends(get_container)):
    """RM-edited section overrides for a CAM report."""
    return {"edits": svc.cam.load_section_edits(entity_id, run_id)}


@router.put("/cam-section-edits")
async def save_cam_section_edit(entity_id: str, request: Request, svc: ServiceContainer = Depends(get_container)):
    """Save RM-edited content for one CAM section."""
    body = await request.json()
    edits = svc.cam.save_section_edit(entity_id, body.get("section_key", ""), body.get("edited_html", ""))
    return {"status": "saved", "edits": edits}


@router.get("/cam-html")
async def get_cam_html(entity_id: str, run_id: str | None = None, svc: ServiceContainer = Depends(get_container)):
    """CAM rendered as styled HTML for on-screen viewing."""
    return Response(content=svc.cam.html(entity_id, run_id), media_type="text/html")


@router.get("/cam-pdf")
async def get_cam_pdf(entity_id: str, run_id: str | None = None, svc: ServiceContainer = Depends(get_container)):
    """CAM as a PDF, including RM section edits and comments."""
    return Response(
        content=svc.cam.pdf(entity_id, run_id),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{entity_id}_CAM.pdf"'},
    )


@router.get("/one-pager")
async def get_one_pager(entity_id: str, run_id: str | None = None, svc: ServiceContainer = Depends(get_container)):
    """One-page graphical credit appraisal memo as HTML."""
    return Response(content=svc.cam.one_pager(entity_id, run_id), media_type="text/html")
