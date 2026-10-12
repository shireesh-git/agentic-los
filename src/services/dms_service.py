"""
DMS (Document Management System) Service
==========================================
Simulates the bank's Document Management System API.

In production, this connects to the bank's DMS/LOS (Loan Origination System):
  - NTB cases: LOS uploads KYC, financials, ratings from branch scanning
  - ETB cases: Existing documents + conduct data already in DMS
  - All document fetching goes through DMS — no web crawling needed

For this platform, the DMS resolves documents from:
  1. Pre-generated storage (scripts/generate_poc_documents.py)
  2. Document downloader (web-verified data for INFY/APOL)
  3. CRILC report generator

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

        if len(existing_files) >= 5:
            emit(f"DMS cache hit — {len(existing_files)} documents already in storage")
            result["cache_hit"] = True
            result["files_fetched"] = [
                str(f.relative_to(entity_dir)) for f in existing_files
            ]
        else:
            # ── Step 3: Generate documents via DMS (simulates LOS upload) ──
            emit("Fetching documents from DMS...")
            self._generate_from_dms(entity_id, company_data, entity_dir, result, emit)

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

        # ── Step 5: For supported companies, fetch web-verified financials ──
        from src.engines.document_downloader import REAL_FINANCIAL_DATA
        if entity_id in REAL_FINANCIAL_DATA:
            audited_pdf = entity_dir / "financials" / "audited_financial_statements.pdf"
            if not audited_pdf.exists():
                emit("Fetching verified financial data from DMS...")
                try:
                    from src.engines.document_downloader import download_company_documents
                    dl_result = download_company_documents(entity_id)
                    if dl_result.get("status") == "success":
                        result["files_fetched"].extend(dl_result.get("files_generated", []))
                except Exception as e:
                    log.warning("Financial doc generation failed for %s: %s", entity_id, e)

        # ── Catalogue final state ──
        all_files = [f for f in entity_dir.rglob("*") if f.is_file() and f.name != "metadata.json"]
        result["total_documents"] = len(all_files)
        result["categories_populated"] = self._catalogue_categories(entity_dir)

        # Update metadata
        self._write_metadata(entity_id, entity_dir, result)

        emit(f"DMS fetch complete — {result['total_documents']} documents available")
        return result

    def _generate_from_dms(self, entity_id: str, company_data: dict,
                           entity_dir: Path, result: dict, emit: callable):
        """Generate documents that would come from DMS/LOS."""
        try:
            # Use the POC document generator
            import sys
            scripts_dir = str(Path(__file__).parent.parent.parent / "scripts")
            if scripts_dir not in sys.path:
                sys.path.insert(0, scripts_dir)

            from generate_poc_documents import COMPANY_DATA as POC_DATA
            from generate_poc_documents import (
                gen_pan_card, gen_certificate_of_incorporation, gen_board_resolution,
                gen_annual_report, gen_audited_financials, gen_provisional_financials_excel,
                gen_debt_schedule_excel, gen_rating_report, gen_gst_certificate,
                gen_collateral_report, gen_bank_statement, gen_request_note,
                gen_exchange_filing, gen_governance_report,
            )

            if entity_id not in POC_DATA:
                emit(f"No DMS data profile for {entity_id} — using minimal document set")
                return

            d = POC_DATA[entity_id]
            emit(f"Generating DMS documents for {d['name']}...")

            def _write(folder, filename, data):
                if data is None:
                    return False
                filepath = folder / filename
                mode = 'wb' if isinstance(data, bytes) else 'w'
                with open(filepath, mode) as f:
                    f.write(data)
                result["files_fetched"].append(f"{folder.name}/{filename}")
                return True

            # KYC
            _write(entity_dir / "kyc", "pan_card.pdf", gen_pan_card(entity_id))
            _write(entity_dir / "kyc", "certificate_of_incorporation.pdf",
                   gen_certificate_of_incorporation(entity_id))
            _write(entity_dir / "kyc", "board_resolution_borrowing.pdf",
                   gen_board_resolution(entity_id))

            # Financials
            _write(entity_dir / "financials", "annual_report_fy2024.pdf",
                   gen_annual_report(entity_id))
            _write(entity_dir / "financials", "audited_financial_statements.pdf",
                   gen_audited_financials(entity_id))
            _write(entity_dir / "financials", "provisional_financials_fy2025.xlsx",
                   gen_provisional_financials_excel(entity_id))
            _write(entity_dir / "financials", "debt_schedule.xlsx",
                   gen_debt_schedule_excel(entity_id))

            # Ratings
            _write(entity_dir / "ratings", "credit_rating_report.pdf",
                   gen_rating_report(entity_id))

            # GST
            _write(entity_dir / "gst", "gst_registration_certificate.pdf",
                   gen_gst_certificate(entity_id))

            # Collateral
            _write(entity_dir / "collateral", "valuation_report.pdf",
                   gen_collateral_report(entity_id))

            # Banking
            _write(entity_dir / "banking", "bank_statement_fy2025.pdf",
                   gen_bank_statement(entity_id))

            # Request
            _write(entity_dir / "request", "request_note.pdf",
                   gen_request_note(entity_id))

            # Exchange (listed only)
            if d.get("listed"):
                _write(entity_dir / "exchange", "quarterly_results_q3fy2025.pdf",
                       gen_exchange_filing(entity_id))
                _write(entity_dir / "exchange", "corporate_governance_report.pdf",
                       gen_governance_report(entity_id))

            emit(f"DMS generated {len(result['files_fetched'])} documents")

        except Exception as e:
            log.warning("DMS document generation failed for %s: %s", entity_id, e)
            result["generation_error"] = str(e)

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
