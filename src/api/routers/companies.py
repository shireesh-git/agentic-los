"""Borrower records: list, manual add, delete, hierarchy, Probe42 snapshot, 360 view."""

import asyncio

from fastapi import APIRouter, Depends, Request

from src.agents.dashboard_360_agent import generate_360_view
from src.api.dependencies import get_container
from src.application.container import ServiceContainer
from src.services.corporate_hierarchy import build_corporate_hierarchy, hierarchy_to_dict
from src.services.probe_service import company_probe_snapshot

router = APIRouter(prefix="/api/companies", tags=["companies"])


@router.get("")
async def list_companies(executed_only: bool = False, svc: ServiceContainer = Depends(get_container)):
    return {"companies": svc.companies.summaries(executed_only)}


@router.post("")
async def add_company(request: Request, svc: ServiceContainer = Depends(get_container)):
    """Add a company manually. Builds canonical dataclass objects from JSON."""
    return svc.companies.create_from_payload(await request.json())


@router.delete("/{entity_id}")
async def delete_company(entity_id: str, svc: ServiceContainer = Depends(get_container)):
    return svc.companies.delete(entity_id)


@router.get("/{entity_id}/hierarchy")
async def get_hierarchy(entity_id: str, svc: ServiceContainer = Depends(get_container)):
    cd = svc.companies.require(entity_id)
    group = cd.get("group")
    if not group:
        return {"entity_id": entity_id, "hierarchy": [], "message": "No group structure"}
    tree, g_revenue, g_nw, g_debt = build_corporate_hierarchy(
        entity_id=entity_id,
        borrower=cd.get("borrower"),
        directors=cd.get("directors", []),
        group=group,
    )
    return {
        "entity_id": entity_id,
        "group_name": group.group_name if hasattr(group, "group_name") else str(group),
        "group_revenue_cr": g_revenue,
        "group_net_worth_cr": g_nw,
        "group_total_debt_cr": g_debt,
        "hierarchy": hierarchy_to_dict(tree),
    }


@router.get("/{entity_id}/probe")
async def get_company_probe(entity_id: str, svc: ServiceContainer = Depends(get_container)):
    """Cached Probe42 snapshot for a company, if available."""
    company = svc.companies.require(entity_id, "Company not found")
    return {"entity_id": entity_id, **company_probe_snapshot(company)}


@router.delete("/{entity_id}/verified-public-data")
async def delete_verified_public_data(entity_id: str, svc: ServiceContainer = Depends(get_container)):
    """Remove the retained public-record snapshot for a company."""
    return svc.companies.clear_verified_public_data(entity_id)


@router.get("/{entity_id}/360")
async def get_360_view(entity_id: str, svc: ServiceContainer = Depends(get_container)):
    """360-degree view: overview, financials, credit risk, market intel, sell perspective."""
    return await asyncio.to_thread(generate_360_view, entity_id, svc.companies.get(entity_id),
                                   svc.cases.get(entity_id))
