"""
Postman-style Mock Server
=========================
Serves canned responses from the CAM Platform for tweaking/testing
without the full backend running. Reads mock data from pre-generated
snapshots and serves them on a configurable port.

Usage:
  python scripts/mock_server.py                # port 8002
  python scripts/mock_server.py --port 9000    # custom port
  docker compose up mock                       # via Docker
"""

import json
import sys
import os
import argparse
from pathlib import Path

# Allow running from project root
_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from src.data.synthetic_companies import ALL_COMPANIES
from src.engines.fraud_detection_engine import run_fraud_scan

app = FastAPI(title="CAM Platform Mock Server", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ─── Pre-compute mock data ──────────────────────────────────────────────────

_company_list = []
_company_map = {}
for eid, cd in ALL_COMPANIES.items():
    b = cd["borrower"]
    entry = {
        "entity_id": eid,
        "company_name": b.company_name,
        "sector": b.sector,
        "pan": b.pan,
        "cin": b.cin,
    }
    _company_list.append(entry)
    _company_map[eid] = cd

# Pre-compute fraud results for all companies
_fraud_cache = {}
for eid, cd in ALL_COMPANIES.items():
    try:
        report = run_fraud_scan(cd)
        _fraud_cache[eid] = {
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
    except Exception:
        _fraud_cache[eid] = {"entity_id": eid, "risk_grade": "N/A", "composite_score": 0}


# ─── Health & Dashboard ─────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "mode": "mock", "companies": len(_company_list)}


@app.get("/api/dashboard")
async def dashboard():
    return {
        "metrics": {
            "available_companies": len(_company_list),
            "approved": 6, "declined": 2, "pending": 8,
        },
        "recent_cases": [],
        "sector_distribution": {},
    }


@app.get("/api/enums")
async def enums():
    return {
        "sectors": ["manufacturing", "infrastructure", "pharma", "logistics",
                     "steel", "energy", "it_services", "ports", "nbfc",
                     "automobile", "retail", "power", "banking"],
        "borrower_types": ["private_limited", "public_limited", "partnership",
                           "llp", "sole_proprietor"],
        "case_types": ["NTB", "ETB"],
        "facility_types": ["working_capital", "term_loan", "project_finance",
                           "letter_of_credit", "bank_guarantee"],
    }


# ─── Companies ───────────────────────────────────────────────────────────────

@app.get("/api/companies")
async def list_companies():
    return _company_list


@app.get("/api/companies/{entity_id}")
async def get_company(entity_id: str):
    if entity_id not in _company_map:
        raise HTTPException(404, f"Company {entity_id} not found")
    b = _company_map[entity_id]["borrower"]
    return {
        "entity_id": entity_id,
        "company_name": b.company_name,
        "sector": b.sector,
        "pan": b.pan,
        "cin": b.cin,
        "status": "active",
    }


# ─── Onboarding ─────────────────────────────────────────────────────────────

@app.post("/api/onboard")
async def onboard():
    return {
        "status": "onboarded",
        "entity_id": "MOCK001",
        "company_name": "Mock Company",
        "message": "Mock onboarding — use real server for full pipeline",
    }


@app.post("/api/resolve")
async def resolve():
    return {"matches": _company_list[:3], "count": 3}


# ─── Cases & Pipeline ───────────────────────────────────────────────────────

@app.get("/api/cases")
async def list_cases():
    return [{"entity_id": c["entity_id"], "status": "pending"} for c in _company_list[:4]]


@app.get("/api/cases/{entity_id}")
async def get_case(entity_id: str):
    return {"entity_id": entity_id, "status": "pending", "decision": None}


@app.post("/api/cases/{entity_id}/run")
async def run_case(entity_id: str):
    return {"status": "completed", "entity_id": entity_id, "decision": "approved_with_conditions"}


@app.get("/api/cases/{entity_id}/cam")
async def get_cam(entity_id: str):
    return {"entity_id": entity_id, "cam_html": f"<h1>CAM: {entity_id}</h1><p>Mock CAM Narrative</p>"}


@app.post("/api/pipeline/run-all")
async def pipeline_run_all():
    return {"results": [{"entity_id": c["entity_id"], "status": "completed"} for c in _company_list]}


# ─── Documents ───────────────────────────────────────────────────────────────

@app.get("/api/companies/{entity_id}/documents")
async def list_docs(entity_id: str):
    storage = _root / "storage" / "documents" / entity_id
    if not storage.exists():
        return {"entity_id": entity_id, "categories": {}, "total_documents": 0}
    categories = {}
    for cat_dir in sorted(storage.iterdir()):
        if cat_dir.is_dir():
            files = [f.name for f in sorted(cat_dir.iterdir()) if f.is_file()]
            if files:
                categories[cat_dir.name] = files
    total = sum(len(v) for v in categories.values())
    return {"entity_id": entity_id, "categories": categories, "total_documents": total}


# ─── Extraction ──────────────────────────────────────────────────────────────

@app.post("/api/companies/{entity_id}/extract")
async def extract(entity_id: str):
    return {"status": "extracted", "entity_id": entity_id, "document_count": 15}


@app.get("/api/companies/{entity_id}/extraction")
async def get_extraction(entity_id: str):
    return {"entity_id": entity_id, "document_count": 15, "documents": []}


# ─── ETB Analytics ───────────────────────────────────────────────────────────

@app.post("/api/companies/{entity_id}/etb-analytics")
async def run_etb(entity_id: str):
    return {"status": "analysed", "entity_id": entity_id,
            "composite_score": 72.5, "risk_grade": "MODERATE"}


@app.get("/api/companies/{entity_id}/etb-analytics")
async def get_etb(entity_id: str):
    return {"entity_id": entity_id, "composite_score": 72.5,
            "risk_grade": "MODERATE", "summary": "Mock ETB analysis."}


# ─── Fraud Detection ────────────────────────────────────────────────────────

@app.post("/api/companies/{entity_id}/fraud-analysis")
async def run_fraud(entity_id: str):
    if entity_id in _fraud_cache:
        return {"status": "analysed", **_fraud_cache[entity_id]}
    raise HTTPException(404, f"Company {entity_id} not found")


@app.get("/api/companies/{entity_id}/fraud-analysis")
async def get_fraud(entity_id: str):
    if entity_id in _fraud_cache:
        return _fraud_cache[entity_id]
    raise HTTPException(404, f"Run fraud analysis first")


# ─── OCR ─────────────────────────────────────────────────────────────────────

@app.post("/api/companies/{entity_id}/ocr/{category}/{filename:path}")
async def run_ocr(entity_id: str, category: str, filename: str):
    return {"entity_id": entity_id, "category": category, "filename": filename,
            "extraction_strategy": "native", "total_chars": 5000,
            "pages": [{"page_num": 1, "text": "Mock extracted text..."}]}


@app.post("/api/companies/{entity_id}/ocr-metadata/{category}/{filename:path}")
async def run_ocr_metadata(entity_id: str, category: str, filename: str):
    return {"entity_id": entity_id, "filename": filename, "risk_score": 0, "anomalies": []}


# ─── Chat ────────────────────────────────────────────────────────────────────

@app.post("/api/chat/{entity_id}")
async def chat(entity_id: str):
    return {"entity_id": entity_id, "response": "Mock response. Use real server for LLM chat.",
            "session_id": entity_id}


@app.get("/api/chat/{entity_id}/history")
async def chat_history(entity_id: str):
    return {"entity_id": entity_id, "messages": []}


@app.delete("/api/chat/{entity_id}")
async def chat_clear(entity_id: str):
    return {"status": "cleared"}


@app.get("/api/chat/sessions")
async def chat_sessions():
    return {"sessions": []}


# ─── 360° View ───────────────────────────────────────────────────────────────

@app.get("/api/companies/{entity_id}/360")
async def view_360(entity_id: str):
    if entity_id not in _company_map:
        raise HTTPException(404, "Not found")
    b = _company_map[entity_id]["borrower"]
    return {
        "entity_id": entity_id,
        "company_name": b.company_name,
        "overview": {"sector": b.sector, "status": "active"},
        "financials": {}, "credit_risk": {}, "market_intel": {},
    }


# ─── External Systems ───────────────────────────────────────────────────────

@app.get("/api/external/mca/company/{cin}")
async def ext_mca(cin: str):
    return {"cin": cin, "status": "Active", "mock": True}

@app.get("/api/external/mca/directors/{cin}")
async def ext_mca_dirs(cin: str):
    return {"cin": cin, "directors": [], "mock": True}

@app.get("/api/external/mca/charges/{cin}")
async def ext_mca_charges(cin: str):
    return {"cin": cin, "charges": [], "mock": True}

@app.get("/api/external/gstin/{gstin}")
async def ext_gstin(gstin: str):
    return {"gstin": gstin, "status": "Active", "mock": True}

@app.get("/api/external/gst-turnover/{pan}")
async def ext_gst_turnover(pan: str):
    return {"pan": pan, "turnover_cr": 500, "mock": True}

@app.get("/api/external/bureau/{pan}")
async def ext_bureau(pan: str):
    return {"pan": pan, "score": 750, "mock": True}

@app.get("/api/external/rating/{entity_id}")
async def ext_rating(entity_id: str):
    return {"entity_id": entity_id, "rating": "A+", "mock": True}

@app.get("/api/external/market/{entity_id}")
async def ext_market(entity_id: str):
    return {"entity_id": entity_id, "signals": [], "mock": True}

@app.get("/api/external/crilc/{pan}")
async def ext_crilc(pan: str):
    return {"pan": pan, "exposures": [], "mock": True}

@app.get("/api/external/epfo/{pan}")
async def ext_epfo(pan: str):
    return {"pan": pan, "compliant": True, "mock": True}

@app.get("/api/external/itr/{pan}")
async def ext_itr(pan: str):
    return {"pan": pan, "filed": True, "mock": True}


# ─── Config & Engines ───────────────────────────────────────────────────────

@app.get("/api/config/{section}")
async def get_config(section: str):
    return {"section": section, "data": {}, "mock": True}

@app.get("/api/engines")
async def list_engines():
    return [{"name": n, "enabled": True} for n in
            ["ratio_analysis", "validation", "benchmark", "policy_check"]]

@app.get("/api/llm/providers")
async def llm_providers():
    return [{"name": "mock", "enabled": True}]

@app.get("/api/llm/active")
async def llm_active():
    return {"provider": "mock", "model": "mock-v1"}

@app.get("/api/agents")
async def agents():
    return [{"name": "SuperAgent", "status": "ready"}]


# ─── Entry Point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CAM Platform Mock Server")
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    args = parser.parse_args()
    print(f"Mock server starting on {args.host}:{args.port}")
    print(f"Companies loaded: {len(_company_list)}")
    print(f"Fraud scores pre-computed: {len(_fraud_cache)}")
    uvicorn.run(app, host=args.host, port=args.port)
