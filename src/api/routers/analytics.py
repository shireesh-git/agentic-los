"""Standalone analytics: ETB conduct, PEP screening, core banking, social media, fraud."""

import asyncio
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import get_container
from src.application.container import ServiceContainer
from src.engines.etb_analytics_engine import etb_analysis_to_dict, run_etb_analytics
from src.engines.fraud_detection_engine import run_fraud_scan

router = APIRouter(prefix="/api/companies/{entity_id}", tags=["analytics"])


@router.post("/etb-analytics")
async def run_etb_analytics_endpoint(entity_id: str, svc: ServiceContainer = Depends(get_container)):
    """ETB behavioural analytics on extracted conduct data."""
    ext = svc.state.extractions.get(entity_id)
    if not ext or not ext.get("etb_conduct"):
        raise HTTPException(400, "No ETB conduct data. Run extraction first, and ensure entity has ETB CSVs.")
    result = etb_analysis_to_dict(run_etb_analytics(ext["etb_conduct"], entity_id))
    svc.state.etb_analytics[entity_id] = result
    return {"status": "analysed", "entity_id": entity_id,
            "composite_score": result.get("composite_score"),
            "risk_grade": result.get("risk_grade")}


@router.get("/etb-analytics")
async def get_etb_analytics(entity_id: str, svc: ServiceContainer = Depends(get_container)):
    if entity_id not in svc.state.etb_analytics:
        raise HTTPException(404, "Run ETB analytics first: POST /api/companies/{id}/etb-analytics")
    return svc.state.etb_analytics[entity_id]


@router.get("/pep-screening")
async def pep_screening(entity_id: str, svc: ServiceContainer = Depends(get_container)):
    """PEP, sanctions and adverse-media screening of directors/promoters."""
    from src.services.pep_service import screen_directors
    company = svc.companies.require(entity_id)
    directors = company.get("directors", [])
    if not directors:
        b = company.get("borrower")
        return {"entity_id": entity_id, "company_name": b.company_name if b else entity_id,
                "pep_hits": [], "sanctions_hits": [], "adverse_media": [],
                "summary": "No directors on record for screening"}
    screening = await asyncio.to_thread(screen_directors, entity_id=entity_id, directors=directors)
    return {"entity_id": entity_id, **asdict(screening)}


@router.get("/core-banking")
async def core_banking_analysis(entity_id: str, svc: ServiceContainer = Depends(get_container)):
    """Core banking (loan, BCLC, liability, fees) analysis for ETB customers."""
    from src.engines.core_banking_engine import analyze_core_banking
    company = svc.companies.require(entity_id)
    case_type = company["facility"].case_type.value if company.get("facility") else "NTB"
    return {"entity_id": entity_id,
            **analyze_core_banking(entity_id, company.get("core_banking"), case_type)}


@router.get("/social-media")
async def social_media_analysis(entity_id: str, svc: ServiceContainer = Depends(get_container)):
    """Social media sentiment, reputation risk and digital intelligence."""
    from src.engines.social_media_engine import analyze_social_media
    company = svc.companies.require(entity_id)
    b = company.get("borrower")
    name = b.company_name if b else entity_id
    sector = b.sector.value if b and hasattr(b.sector, "value") else "general"
    return {"entity_id": entity_id, **(await asyncio.to_thread(analyze_social_media, entity_id, name, sector))}


@router.post("/fraud-analysis")
async def run_fraud_analysis(entity_id: str, svc: ServiceContainer = Depends(get_container)):
    """Multi-signal fraud detection (Beneish, Altman, Benford, governance, documents)."""
    company = svc.companies.require(entity_id, f"Company {entity_id} not found. Onboard first.")
    report = await asyncio.to_thread(run_fraud_scan, company,
                                     extraction_data=svc.state.extractions.get(entity_id))
    result = {
        "entity_id": report.entity_id,
        "company_name": report.company_name,
        "composite_score": round(report.composite_score, 2),
        "risk_grade": report.risk_grade,
        "beneish_m_score": round(report.beneish_m_score, 4) if report.beneish_m_score else None,
        "beneish_probability": report.beneish_probability,
        "altman_z_score": round(report.altman_z_score, 4) if report.altman_z_score else None,
        "altman_zone": report.altman_zone,
        "benford_chi_sq": round(report.benford_chi_sq, 4) if report.benford_chi_sq else None,
        "benford_verdict": report.benford_verdict,
        "revenue_consistency": round(report.revenue_consistency, 2),
        "governance_score": round(report.governance_score, 2),
        "document_anomaly_score": round(report.document_anomaly_score, 2),
        "circular_txn_score": round(report.circular_txn_score, 2),
        "summary": report.summary,
        "flags": [
            {"category": f.category, "indicator": f.indicator, "severity": f.severity,
             "score": round(f.score, 2), "details": f.details, "evidence": f.evidence}
            for f in report.flags
        ],
    }
    svc.state.fraud_reports[entity_id] = result
    return {"status": "analysed", "entity_id": entity_id, **result}


@router.get("/fraud-analysis")
async def get_fraud_analysis(entity_id: str, svc: ServiceContainer = Depends(get_container)):
    if entity_id not in svc.state.fraud_reports:
        raise HTTPException(404, "Run fraud analysis first: POST /api/companies/{id}/fraud-analysis")
    return svc.state.fraud_reports[entity_id]
