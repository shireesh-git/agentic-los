"""SPA shell, health, enums, dashboard metrics and Probe42 readiness."""

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, Response

from src.api.dependencies import get_container
from src.application.container import ServiceContainer
from src.core.config_manager import config
from src.core.engine_registry import registry
from src.core.runtime_paths import DOCUMENTS_ROOT, OUTPUT_ROOT
from src.core.ui_paths import render_spa
from src.models.canonical_model import BorrowerType, CaseType, FacilityType, Sector
from src.services.probe_service import get_probe_status

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def serve_spa():
    return render_spa()


@router.get("/los", response_class=HTMLResponse)
async def serve_los():
    """The Corporate LOS front end (the CAM workspace stays at /)."""
    return render_spa("los.html")


@router.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)


@router.get("/api/dashboard")
async def get_dashboard(svc: ServiceContainer = Depends(get_container)):
    summary = svc.cases.dashboard()
    # Sanctioning authority per case, from the delegation-of-powers matrix.
    for row in summary["portfolio"]:
        case = svc.cases.get(row["entity_id"]) if row.get("workflow_status") else None
        row["required_authority"] = svc.approvals.required_authority(case).name if case else None
    return summary


@router.get("/api/health")
async def health_check(svc: ServiceContainer = Depends(get_container)):
    return {
        "status": "healthy",
        "version": "1.0.0",
        "companies": len(svc.state.companies),
        "cases_analysed": len(svc.state.cases),
        "active_llm": config.get_llm_config().get("active_provider", "mock"),
        "engines_enabled": sum(1 for e in registry.list_engines() if e["enabled"]),
        "probe42": get_probe_status(include_tools=False),
        "storage": {
            "documents_root": str(DOCUMENTS_ROOT),
            "output_root": str(OUTPUT_ROOT),
        },
        "database": svc.persistence.describe(),
    }


@router.get("/api/probe/status")
async def probe_status():
    """Report Probe42 MCP integration readiness."""
    return get_probe_status(include_tools=True)


@router.get("/api/enums")
async def get_enums():
    """Valid enum values for the Add Company form."""
    return {
        "sectors": [s.value for s in Sector],
        "case_types": [c.value for c in CaseType],
        "facility_types": [f.value for f in FacilityType],
        "borrower_types": [b.value for b in BorrowerType],
    }
