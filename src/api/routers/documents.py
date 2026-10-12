"""
Borrower documents: listing and completeness, upload/download/delete,
reference documents, extraction, DMS, document packs, CRILC files and OCR.
"""

import asyncio
import logging
import traceback
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response

from src.api.dependencies import get_container
from src.application.container import ServiceContainer
from src.core.runtime_paths import DOCUMENTS_ROOT
from src.services.document_extractor import extract_all_documents
from src.services.document_operations import document_operations
from src.services.document_store import doc_store
from src.services.ocr_service import analyze_document_metadata, extract_document as ocr_extract

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["documents"])

_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".csv": "text/csv",
    ".json": "application/json",
    ".txt": "text/plain",
}
_BINARY_EXTENSIONS = (".pdf", ".xlsx", ".xls")


def _stored_file(entity_id: str, category: str, filename: str) -> Path:
    """Resolve a stored document path, refusing paths that escape the company folder."""
    company_root = (DOCUMENTS_ROOT / entity_id).resolve()
    filepath = (company_root / category / filename).resolve()
    if not filepath.is_relative_to(company_root) or not filepath.exists():
        raise HTTPException(404, f"Document not found: {category}/{filename}")
    return filepath


# ── Listing & completeness ───────────────────────────────────────────────

@router.get("/companies/{entity_id}/documents")
async def list_documents(entity_id: str, svc: ServiceContainer = Depends(get_container)):
    """All documents for a company with completeness tracking."""
    workspace = doc_store.list_company_documents(entity_id)
    return svc.workspace.augment(svc.companies.get(entity_id), workspace)


@router.get("/document-operations")
async def list_document_operations(entity_id: str | None = Query(default=None),
                                   limit: int = Query(default=25, ge=1, le=100)):
    """Recent document generation operations, optionally filtered by company."""
    return {
        "operations": document_operations.list(entity_id=entity_id, limit=limit),
        "entity_id": entity_id,
        "limit": limit,
    }


@router.get("/companies/{entity_id}/document-operations")
async def list_company_document_operations(entity_id: str, limit: int = Query(default=10, ge=1, le=50)):
    return {"entity_id": entity_id,
            "operations": document_operations.list(entity_id=entity_id, limit=limit)}


@router.get("/companies/{entity_id}/data-gaps")
async def check_data_gaps(entity_id: str, svc: ServiceContainer = Depends(get_container)):
    """Data coverage for a company: uploads, public-record snapshots and news."""
    company = svc.companies.get(entity_id)
    docs = svc.workspace.augment(company, doc_store.list_company_documents(entity_id))
    web_crawl_count = 0
    if company:
        from src.services.web_crawl_service import crawl_company_news
        b = company.get("borrower")
        name = b.company_name if b else entity_id
        sector = b.sector.value if b and hasattr(b.sector, "value") else "general"
        try:
            web_crawl_count = len((await asyncio.to_thread(crawl_company_news, name, sector)).get("articles", []))
        except Exception:
            pass

    categories = docs.get("categories", {})
    return {
        "entity_id": entity_id,
        "provider": docs.get("provider"),
        "total_files": docs.get("total_files", 0),
        "upload_coverage_pct": docs.get("upload_coverage_pct", 0),
        "hidden_legacy_files": docs.get("hidden_legacy_files", 0),
        "hidden_system_files": docs.get("hidden_system_files", 0),
        "categories_with_docs": [cat for cat, info in categories.items() if info.get("files")],
        "categories_empty": {cat: info for cat, info in categories.items()
                             if not info.get("files") and info.get("expected")},
        "required_missing_documents": docs.get("required_missing_documents", []),
        "source_gaps": docs.get("source_gaps", []),
        "web_crawl_available": web_crawl_count > 0,
        "web_crawl_article_count": web_crawl_count,
        "data_sources": "APIs + Web Crawl (automated)",
    }


@router.get("/reference-documents")
async def list_reference_documents(entity_id: str | None = Query(default=None),
                                   svc: ServiceContainer = Depends(get_container)):
    """Reference documents for manual fact-checking (never ingested by the pipeline)."""
    groups = svc.workspace.reference_groups()
    aliases: list[str] = []
    if entity_id:
        aliases = svc.workspace.reference_aliases(entity_id, svc.companies.get(entity_id))
        groups = {group: files for group, files in groups.items()
                  if svc.workspace.reference_match(group, aliases)}
    files = sorted(filename for file_list in groups.values() for filename in file_list)
    return {
        "entity_id": entity_id,
        "aliases": aliases,
        "files": files,
        "groups": groups,
        "total": len(files),
        "purpose": "fact-check",
        "note": "Reference documents for manual verification only; "
                "filtered to the selected company when entity_id is provided",
    }


# ── Upload / download / delete ───────────────────────────────────────────

@router.get("/companies/{entity_id}/documents/{category}/{filename}")
async def get_document(entity_id: str, category: str, filename: str):
    """Binary files download inline; text files return as JSON."""
    content = doc_store.get_document(entity_id, category, filename)
    if content is None:
        raise HTTPException(404, f"Document not found: {category}/{filename}")

    ext = Path(filename).suffix.lower()
    mime = _MIME_TYPES.get(ext, "application/octet-stream")
    if ext in _BINARY_EXTENSIONS:
        return Response(content=content, media_type=mime,
                        headers={"Content-Disposition": f'inline; filename="{filename}"'})
    try:
        return {"entity_id": entity_id, "category": category,
                "filename": filename, "content": content.decode("utf-8")}
    except (UnicodeDecodeError, AttributeError):
        return Response(content=content, media_type=mime)


@router.post("/companies/{entity_id}/documents/{category}")
async def upload_document(entity_id: str, category: str, request: Request,
                          svc: ServiceContainer = Depends(get_container)):
    """Upload a document as JSON. Body: { filename, content }"""
    body = await request.json()
    filename = body.get("filename", "").strip()
    content = body.get("content", "")
    if not filename:
        raise HTTPException(400, "Provide 'filename'")
    doc_store.init_company_folder(entity_id)
    doc_store.store_document(entity_id, category, filename,
                             content.encode("utf-8") if isinstance(content, str) else content)
    svc.state.invalidate_derived(entity_id)
    return {"status": "stored", "entity_id": entity_id, "category": category, "filename": filename}


@router.post("/companies/{entity_id}/upload")
async def upload_file(entity_id: str, category: str = Form("misc"), file: UploadFile = File(...),
                      document_role: str = Form(None), svc: ServiceContainer = Depends(get_container)):
    """Multipart upload (UI drag-drop / file picker)."""
    if not file.filename:
        raise HTTPException(400, "No file provided")
    content = await file.read()
    doc_store.init_company_folder(entity_id)
    result = doc_store.store_document(entity_id, category, file.filename, content,
                                      source="manual_upload", document_role=document_role or None)
    svc.state.invalidate_derived(entity_id)
    return {"status": "stored", **result}


@router.delete("/companies/{entity_id}/documents/{category}/{filename:path}")
async def delete_document_file(entity_id: str, category: str, filename: str,
                               svc: ServiceContainer = Depends(get_container)):
    if not doc_store.delete_document(entity_id, category, filename):
        raise HTTPException(404, "Document not found")
    svc.state.invalidate_derived(entity_id)
    return {"status": "deleted", "entity_id": entity_id, "category": category, "filename": filename}


# ── Extraction ───────────────────────────────────────────────────────────

@router.post("/companies/{entity_id}/extract")
async def run_extraction(entity_id: str, svc: ServiceContainer = Depends(get_container)):
    """Run the full document extraction pipeline for an entity."""
    if not (DOCUMENTS_ROOT / entity_id).exists():
        raise HTTPException(404, f"No documents found for {entity_id}")
    try:
        result = await asyncio.to_thread(extract_all_documents, entity_id, DOCUMENTS_ROOT)
    except Exception as e:
        log.error("Extraction failed for %s: %s\n%s", entity_id, e, traceback.format_exc())
        raise HTTPException(500, f"Extraction failed: {str(e)}")
    if result.get("error"):
        raise HTTPException(404, result["error"])
    svc.state.extractions[entity_id] = result
    return {"status": "extracted", "entity_id": entity_id,
            "document_count": result.get("document_count", 0)}


@router.get("/companies/{entity_id}/extraction")
async def get_extraction(entity_id: str, svc: ServiceContainer = Depends(get_container)):
    """Cached extraction results."""
    if entity_id not in svc.state.extractions:
        return {
            "entity_id": entity_id,
            "status": "not_started",
            "document_count": 0,
            "financials": {},
            "documents": {},
            "message": "Run extraction first: POST /api/companies/{id}/extract",
        }
    return svc.state.extractions[entity_id]


# ── DMS & document packs ─────────────────────────────────────────────────

@router.post("/companies/{entity_id}/dms-fetch")
async def dms_fetch(entity_id: str, svc: ServiceContainer = Depends(get_container)):
    """Fetch all documents from the DMS for a company."""
    from src.services.dms_service import dms_service
    company = svc.companies.require(entity_id)
    result = await asyncio.to_thread(dms_service.fetch_documents, entity_id, company_data=company)
    return {"entity_id": entity_id, **result}


@router.get("/companies/{entity_id}/dms-status")
async def dms_status(entity_id: str, svc: ServiceContainer = Depends(get_container)):
    from src.services.dms_service import dms_service
    svc.companies.require(entity_id)
    return dms_service.get_document_status(entity_id)


@router.post("/companies/fetch-documents/bulk")
async def fetch_documents_bulk(force_refresh: bool = False):
    """Backfill document packs for all supported listed companies."""
    from src.engines.document_downloader import populate_supported_company_documents
    return await asyncio.to_thread(populate_supported_company_documents, force_refresh=force_refresh)


@router.post("/companies/{entity_id}/fetch-documents")
async def fetch_documents(entity_id: str, svc: ServiceContainer = Depends(get_container)):
    """Download/generate financial documents for a supported listed company."""
    from src.engines.document_downloader import download_company_documents, get_supported_companies
    supported_ids = [c["entity_id"] for c in get_supported_companies()]
    if entity_id not in supported_ids:
        raise HTTPException(400, f"Document download not supported for {entity_id}. "
                                 f"Supported: {supported_ids}")
    result = await asyncio.to_thread(download_company_documents, entity_id)
    svc.state.invalidate_derived(entity_id)
    return {"entity_id": entity_id, **result}


@router.get("/companies/supported-downloads")
async def supported_downloads():
    from src.engines.document_downloader import get_supported_companies
    return get_supported_companies()


# ── CRILC report files ───────────────────────────────────────────────────

@router.post("/companies/{entity_id}/crilc-pdf")
async def generate_crilc_pdf(entity_id: str):
    from src.engines.crilc_report_generator import generate_crilc_report
    result = await asyncio.to_thread(generate_crilc_report, entity_id)
    if result["status"] == "error":
        raise HTTPException(400, result["message"])
    return result


@router.get("/companies/{entity_id}/crilc-pdf")
async def get_crilc_pdf(entity_id: str):
    crilc_file = DOCUMENTS_ROOT / entity_id / "bureau" / "crilc_report.pdf"
    if not crilc_file.exists():
        raise HTTPException(404, f"No CRILC report found for {entity_id}. Generate first via POST.")
    return Response(content=crilc_file.read_bytes(), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="crilc_report_{entity_id}.pdf"'})


# ── OCR / document intelligence ──────────────────────────────────────────

@router.post("/companies/{entity_id}/ocr/{category}/{filename:path}")
async def run_ocr(entity_id: str, category: str, filename: str):
    """Extract text from a stored PDF using OCR/native extraction."""
    filepath = _stored_file(entity_id, category, filename)
    if filepath.suffix.lower() != ".pdf":
        raise HTTPException(400, "OCR is only supported for PDF files")
    result = await asyncio.to_thread(ocr_extract, filepath)
    if result.get("error"):
        raise HTTPException(500, result["error"])
    return {"entity_id": entity_id, "category": category, "filename": filename, **result}


@router.post("/companies/{entity_id}/ocr-metadata/{category}/{filename:path}")
async def run_ocr_metadata(entity_id: str, category: str, filename: str):
    """Analyse document metadata for fraud indicators."""
    filepath = _stored_file(entity_id, category, filename)
    result = await asyncio.to_thread(analyze_document_metadata, filepath)
    if result.get("error"):
        raise HTTPException(500, result["error"])
    return {"entity_id": entity_id, "category": category, "filename": filename, **result}
