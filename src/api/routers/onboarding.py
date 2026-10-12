"""Identifier-based onboarding and company resolution."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request

from src.api.dependencies import get_container
from src.application.container import ServiceContainer
from src.services.external_systems import resolve_company
from src.services.probe_service import resolve_company_with_probe

router = APIRouter(prefix="/api", tags=["onboarding"])

# Documents an RM must upload after a CIN lookup; public records come from Probe42.
_CIN_LOOKUP_RM_DOCUMENTS = [
    {"type": "audited_financial_fy2024", "description": "Audited Financial Statements FY2024 (PDF)",
     "source": "rm_upload", "ocr_required": True},
    {"type": "audited_financial_fy2023", "description": "Audited Financial Statements FY2023 (PDF)",
     "source": "rm_upload", "ocr_required": True},
    {"type": "provisional_fy2025", "description": "Provisional / Management Financials FY2025 (Excel/PDF)",
     "source": "rm_upload", "ocr_required": False},
    {"type": "board_resolution", "description": "Board Resolution for borrowing",
     "source": "rm_upload", "ocr_required": True},
    {"type": "cma_projection", "description": "CMA Data / Financial Projections",
     "source": "rm_upload", "ocr_required": False},
]


@router.post("/onboard")
async def smart_onboard(request: Request, svc: ServiceContainer = Depends(get_container)):
    """Onboard from one identifier (PAN / GSTIN / CIN / entity ID / name).

    Body: { identifier, case_type?, facility_type?, amount_requested_cr?, purpose?,
            tenor_months?, crilc_available?, etb_data? }
    """
    return await asyncio.to_thread(svc.companies.onboard, await request.json())


@router.post("/resolve")
async def resolve_identifier(request: Request):
    """Resolve a company identifier without onboarding — preview mode."""
    body = await request.json()
    identifier = body.get("identifier", "").strip()
    if not identifier:
        raise HTTPException(400, "Provide 'identifier'")
    result = await asyncio.to_thread(resolve_company_with_probe, identifier)
    if not result:
        raise HTTPException(404, f"Could not resolve: {identifier}")
    return result


@router.post("/onboard/cin-lookup")
async def cin_lookup(request: Request):
    """Resolve a CIN and list what the RM must still upload."""
    body = await request.json()
    cin = body.get("cin", "").strip()
    if not cin:
        raise HTTPException(400, "Provide 'cin' — Corporate Identification Number")

    resolved = resolve_company(cin) or await asyncio.to_thread(resolve_company_with_probe, cin)
    if not resolved:
        raise HTTPException(404, f"CIN {cin} not found")

    company_name = resolved.get("company_name", "")
    entity_id = resolved.get("entity_id")
    missing_documents = [dict(doc) for doc in _CIN_LOOKUP_RM_DOCUMENTS]
    return {
        "status": "found",
        "cin": cin,
        "entity_id": entity_id,
        "company_name": company_name,
        "pan": resolved.get("pan", ""),
        "is_listed": resolved.get("probe_summary", {}).get("listing_status", "").lower() == "listed",
        "data_sources_fetched": {"probe42": resolved.get("provider", "")},
        "missing_documents": missing_documents,
        "rm_action_required": True,
        "next_steps": [
            "Upload missing documents (audited financials, provisionals, board resolution, CMA)",
            "System will run OCR on uploaded PDFs to extract financial data",
            f"Run pipeline: POST /api/cases/{entity_id or '{entity_id}'}/run",
        ],
        "message": (
            f"Company '{company_name}' identified via CIN. "
            f"Probe42 data will be fetched during onboarding. "
            f"RM needs to upload {len(missing_documents)} documents to complete the case."
        ),
    }
