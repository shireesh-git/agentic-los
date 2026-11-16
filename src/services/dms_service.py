"""
DMS (Document Management System) Service
==========================================
Simulates the bank's Document Management System API.

In production, this connects to the bank's DMS/LOS (Loan Origination System):
  - NTB cases: LOS uploads KYC, financials, ratings from branch scanning
  - ETB cases: Existing documents + conduct data already in DMS
  - All document fetching goes through DMS — no web crawling needed

For this platform, the DMS resolves documents from storage/documents/{entity_id}/: the borrower's latest public
filings (config/borrower_documents.yaml) and its labelled demo documents, plus the CRILC report generated from the
borrower's data file.

Flow:  LOS → DMS API → storage/documents/{entity_id}/ → Pipeline
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from src.core.runtime_paths import DOCUMENTS_ROOT

log = logging.getLogger(__name__)

STORAGE_ROOT = DOCUMENTS_ROOT

# Document categories expected from DMS
DMS_CATEGORIES = {
    "kyc": "KYC & Identity (PAN, CIN, Board Resolution)",
    "financials": "Financial Statements (Audited, Provisional, Schedules)",
    "bureau": "Internal Banking & CRILC Reports",
    "legal": "Legal Documents (MOA, AOA, Charges)",
    "collateral": "Collateral & Valuation Reports",
    "ratings": "Credit Rating Letters & Rationale",
    "gst": "GST Returns & Registration",
    "mca": "MCA Filings & Annual Returns",
    "banking": "Bank Statements & Facility Letters",
    "exchange": "Exchange Filings (for listed companies)",
    "request": "Loan Request & Sanction Notes",
}


class DMSService:
    """
    Document Management System interface.
    In production, each method would call the bank's DMS REST API.
    Here, it orchestrates local document generation and storage.
    """

    def __init__(self, storage_root: Path = None):
        self.storage_root = storage_root or STORAGE_ROOT

    def fetch_documents(self, entity_id: str, company_data: dict = None,
                        on_progress: callable = None) -> dict[str, Any]:
        """
        Fetch all documents for a company from DMS into local storage.

        Args:
            entity_id: Company identifier
            company_data: Canonical company data dict (borrower, financials, etc.)
            on_progress: Optional callback for progress updates

        Returns:
            dict with fetch status, files available, and source info
        """
        def emit(msg):
            log.info("[DMS] %s: %s", entity_id, msg)
            if on_progress:
                on_progress(msg)

        entity_dir = self.storage_root / entity_id
        result = {
            "entity_id": entity_id,
            "status": "success",
            "source": "dms",
            "files_fetched": [],
            "categories_populated": [],
            "fetch_timestamp": datetime.now().isoformat(),
        }

        # ── Step 1: Ensure folder structure ──
        for cat in DMS_CATEGORIES:
            (entity_dir / cat).mkdir(parents=True, exist_ok=True)

        # ── Step 2: Check if documents already exist in storage (DMS cache) ──
        existing_files = list(entity_dir.rglob("*"))
        existing_files = [f for f in existing_files if f.is_file() and f.name != "metadata.json"]

        # Documents on file are the borrower's (uploaded through the LOS, or a previous fetch): never mixed
        # with simulated DMS documents — a new prospect with four real documents keeps exactly those.
        if existing_files:
            emit(f"DMS cache hit — {len(existing_files)} documents already in storage")
            result["cache_hit"] = True
            result["files_fetched"] = [
                str(f.relative_to(entity_dir)) for f in existing_files
            ]
        else:
            # nothing is generated: the borrower's documents are those on file (data/borrowers + storage/documents)
            emit("No documents on file for this borrower in the DMS")

        # ── Step 4: Generate CRILC report if not present ──
        crilc_file = entity_dir / "bureau" / "crilc_report.pdf"
        if not crilc_file.exists():
            try:
                from src.engines.crilc_report_generator import generate_crilc_report
                emit("Generating CRILC exposure report...")
                generate_crilc_report(entity_id)
                result["files_fetched"].append("bureau/crilc_report.pdf")
            except Exception as e:
                log.warning("CRILC generation failed for %s: %s", entity_id, e)

        # (no financial documents are generated: the real filings are fetched — config/borrower_documents.yaml)

        # ── Catalogue final state ──
        all_files = [f for f in entity_dir.rglob("*") if f.is_file() and f.name != "metadata.json"]
        result["total_documents"] = len(all_files)
        result["categories_populated"] = self._catalogue_categories(entity_dir)

        # Update metadata
        self._write_metadata(entity_id, entity_dir, result)

        emit(f"DMS fetch complete — {result['total_documents']} documents available")
        return result

    def _catalogue_categories(self, entity_dir: Path) -> list[dict]:
        """Catalogue documents by category."""
        cats = []
        for cat, desc in DMS_CATEGORIES.items():
            cat_dir = entity_dir / cat
            if cat_dir.exists():
                files = [f.name for f in cat_dir.iterdir() if f.is_file()]
                if files:
                    cats.append({"category": cat, "description": desc,
                                 "files": files, "count": len(files)})
        return cats

    def _write_metadata(self, entity_id: str, entity_dir: Path, result: dict):
        """Write DMS metadata file."""
        meta_path = entity_dir / "metadata.json"
        meta = {
            "entity_id": entity_id,
            "source": "dms",
            "last_fetched": result["fetch_timestamp"],
            "total_documents": result["total_documents"],
            "categories": [c["category"] for c in result["categories_populated"]],
        }
        meta_path.write_text(json.dumps(meta, indent=2))

    def get_document_status(self, entity_id: str) -> dict:
        """Check DMS document availability for a company."""
        entity_dir = self.storage_root / entity_id
        if not entity_dir.exists():
            return {"entity_id": entity_id, "available": False, "total_documents": 0}

        all_files = [f for f in entity_dir.rglob("*") if f.is_file() and f.name != "metadata.json"]
        return {
            "entity_id": entity_id,
            "available": True,
            "total_documents": len(all_files),
            "categories": self._catalogue_categories(entity_dir),
        }


# Module-level singleton
dms_service = DMSService()
