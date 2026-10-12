"""Pass-through endpoints for external data sources (MCA, GST, bureau, CRILC, ...)."""

import asyncio

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from src.api.dependencies import get_container
from src.application.container import ServiceContainer
from src.rendering import build_crilc_pdf
from src.services.external_systems import (
    bureau_commercial_report, crilc_report, epfo_compliance, exchange_financial_results,
    exchange_governance_filings, gstin_details, gstin_turnover, itr_filing_status,
    market_intelligence, mca_charges, mca_company_master, mca_directors, rating_action,
    social_reputation_signals,
)

router = APIRouter(prefix="/api/external", tags=["external"])


@router.get("/mca/company/{cin}")
async def ext_mca_company(cin: str):
    return mca_company_master(cin)


@router.get("/mca/directors/{cin}")
async def ext_mca_directors(cin: str):
    return mca_directors(cin)


@router.get("/mca/charges/{cin}")
async def ext_mca_charges(cin: str):
    return mca_charges(cin)


@router.get("/gstin/{gstin}")
async def ext_gstin(gstin: str):
    return gstin_details(gstin)


@router.get("/gst-turnover/{pan}")
async def ext_gst_turnover(pan: str):
    return gstin_turnover(pan)


@router.get("/bureau/{pan}")
async def ext_bureau(pan: str):
    return bureau_commercial_report(pan)


@router.get("/rating/{entity_id}")
async def ext_rating(entity_id: str):
    return rating_action(entity_id)


@router.get("/market/{entity_id}")
async def ext_market(entity_id: str):
    return market_intelligence(entity_id)


@router.get("/crilc/{pan}")
async def ext_crilc(pan: str):
    return crilc_report(pan)


@router.get("/crilc/{pan}/pdf")
async def ext_crilc_pdf(pan: str):
    """CRILC exposure report as PDF."""
    return Response(
        content=build_crilc_pdf(pan, crilc_report(pan)),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="CRILC_{pan}.pdf"'},
    )


@router.get("/epfo/{pan}")
async def ext_epfo(pan: str):
    return epfo_compliance(pan)


@router.get("/itr/{pan}")
async def ext_itr(pan: str):
    return itr_filing_status(pan)


@router.get("/exchange/financial-results/{entity_id}")
async def ext_exchange_financials(entity_id: str):
    return exchange_financial_results(entity_id)


@router.get("/exchange/governance/{entity_id}")
async def ext_exchange_governance(entity_id: str):
    return exchange_governance_filings(entity_id)


@router.get("/social/reputation/{entity_id}")
async def ext_social_reputation(entity_id: str):
    return social_reputation_signals(entity_id)


@router.get("/web-crawl/{entity_id}")
async def ext_web_crawl(entity_id: str, svc: ServiceContainer = Depends(get_container)):
    """News & market intelligence for a company (NTB focus)."""
    from src.services.web_crawl_service import crawl_company_news
    company = svc.companies.require(entity_id)
    b = company.get("borrower")
    name = b.company_name if b else entity_id
    sector = b.sector.value if b and hasattr(b.sector, "value") else "general"
    is_ntb = company.get("facility") and company["facility"].case_type.value == "NTB"
    return await asyncio.to_thread(crawl_company_news, name, sector, is_ntb=bool(is_ntb))
