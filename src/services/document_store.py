"""
Document Storage Service — Local filesystem with S3-compatible abstraction.
Manages corporate document lifecycle: upload, fetch, index, retrieve.
Folder structure mirrors real banking document management:

  storage/documents/{entity_id}/
    ├── kyc/              (PAN, GST Cert, CIN Certificate, Board Resolution)
    ├── financials/       (Audited BS, P&L, Cash Flow, Schedules)
    ├── bureau/           (internal exposure or conduct files)
    ├── legal/            (MOA, AOA, Charges, Undertakings)
    ├── collateral/       (Valuation reports, Title docs)
    ├── ratings/          (Rating letters, Rationale)
    ├── gst/              (GST returns, Certificates)
    ├── mca/              (MCA filings, Annual Returns)
    ├── banking/          (Bank statements, Sanction letters)
    ├── exchange/         (Exchange & stock filings)
    ├── request/          (Loan request notes & applications)
    └── misc/             (Other supporting documents)
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from src.core.runtime_paths import DOCUMENTS_ROOT
from src.services.document_classifier import classify_document_role, requirement_is_satisfied, role_label


# Base storage path — would be S3 bucket in production
STORAGE_ROOT = DOCUMENTS_ROOT

# Document categories and their expected files
DOCUMENT_CATEGORIES = {
    "kyc": {
        "description": "KYC & Identity Documents",
        "source_hint": "Borrower identity pack and statutory approvals uploaded by RM or borrower.",
        "public_record_note": "Public records can verify identity fields, but borrower document files are maintained separately here.",
        "expected_files": [
            "pan_card.pdf", "certificate_of_incorporation.pdf",
            "board_resolution_borrowing.pdf", "gst_registration_certificate.pdf",
        ]
    },
    "financials": {
        "description": "Financial Statements & Reports",
        "source_hint": "Audited, provisional, and debt schedule files uploaded by RM, borrower, or finance team.",
        "public_record_note": "Verified public records do not replace the latest borrower financial pack stored in this workspace.",
        "expected_files": [
            "audited_financial_statements.pdf", "annual_report_fy2024.pdf",
            "provisional_financials_fy2025.xlsx", "debt_schedule.xlsx",
            "web_scraped_financials.json", "itr_auto_fetch.json",
        ]
    },
    "bureau": {
        "description": "Banking & Internal Exposure",
        "source_hint": "Internal banking conduct and lender exposure files maintained by the bank.",
        "public_record_note": "This category is not supplied by verified public records.",
        "expected_files": [
            "commercial_bureau_report.pdf", "bureau_auto_fetch.json",
            "crilc_auto_fetch.json", "crilc_report.pdf",
        ]
    },
    "legal": {
        "description": "Legal, Charges & Compliance",
        "source_hint": "Legal, compliance, and registry-backed evidence kept for review.",
        "public_record_note": "Verified public records can populate legal and compliance data points, but borrower-facing document files may still be separate.",
        "expected_files": [
            "epfo_auto_fetch.json",
        ]
    },
    "collateral": {
        "description": "Collateral & Valuation Documents",
        "source_hint": "Valuation and collateral comfort documents from valuers, collateral team, or RM.",
        "public_record_note": "This category is not supplied by verified public records.",
        "expected_files": [
            "valuation_report.pdf",
        ]
    },
    "ratings": {
        "description": "Agency Ratings & Rationale",
        "source_hint": "Rating letters, rationale documents, and public rating snapshots.",
        "public_record_note": "Ratings data can be verified from public records, while supporting files can still be uploaded separately.",
        "expected_files": [
            "credit_rating_report.pdf", "rating_auto_fetch.json",
        ]
    },
    "gst": {
        "description": "GST Registration & Returns",
        "source_hint": "GST certificates, return summaries, and supporting tax files.",
        "public_record_note": "GST profile data can be verified from public records, but working files remain separate here.",
        "expected_files": [
            "gstr3b_summary.pdf", "gstr1_summary.pdf",
            "gstin_auto_fetch.json", "gst_turnover_auto_fetch.json",
        ]
    },
    "mca": {
        "description": "MCA Filings & Annual Returns",
        "source_hint": "Registry extracts and annual-return support files.",
        "public_record_note": "This category is primarily aligned to verified public-record coverage.",
        "expected_files": [
            "mca_master_auto_fetch.json", "mca_charges_auto_fetch.json",
            "mca_directors_auto_fetch.json",
        ]
    },
    "banking": {
        "description": "Banking Statements & Sanctions",
        "source_hint": "Borrower bank statements, sanction letters, and internal facility papers.",
        "public_record_note": "This category is not supplied by verified public records.",
        "expected_files": [
            "bank_statement_6m.pdf", "bank_statement_fy2025.pdf", "sanction_letter.pdf",
            "existing_facility_details.pdf",
        ]
    },
    "exchange": {
        "description": "Exchange & Stock Filings",
        "source_hint": "Listed-company filings and exchange disclosures uploaded for reference.",
        "public_record_note": "This category is not supplied by verified public records in the current integration.",
        "expected_files": [
            "quarterly_results_q3fy2025.pdf", "corporate_governance_report.pdf", "nse_live_quote.json",
        ]
    },
    "request": {
        "description": "Loan Request Documents",
        "source_hint": "Borrower request note, CMA, projections, and repayment assumptions.",
        "public_record_note": "This category is not supplied by verified public records.",
        "expected_files": [
            "request_note.pdf",
        ]
    },
    "misc": {
        "description": "Miscellaneous Supporting Documents",
        "source_hint": "Internal notes and supporting files added by RM or analyst teams.",
        "public_record_note": "This category is not supplied by verified public records.",
        "expected_files": ["company_profile_web.json", "market_auto_fetch.json"]
    },
}

REQUIRED_DOCUMENT_FILES = {
    "kyc": [
        "pan_card.pdf",
        "certificate_of_incorporation.pdf",
        "board_resolution_borrowing.pdf",
    ],
    "financials": [
        "audited_financial_statements.pdf",
        "annual_report_fy2024.pdf",
        "provisional_financials_fy2025.xlsx",
        "debt_schedule.xlsx",
    ],
    "bureau": [],
    "legal": [],
    "collateral": [
        "valuation_report.pdf",
    ],
    "ratings": [],
    "gst": [],
    "mca": [],
    "banking": [
        "bank_statement_6m.pdf",
        "bank_statement_fy2025.pdf",
        "sanction_letter.pdf",
        "existing_facility_details.pdf",
    ],
    "exchange": [
        "quarterly_results_q3fy2025.pdf",
        "corporate_governance_report.pdf",
    ],
    "request": [
        "request_note.pdf",
    ],
    "misc": [],
}

VISIBLE_DOCUMENT_EXTENSIONS = {
    ".pdf", ".xlsx", ".xls", ".csv", ".txt", ".doc", ".docx",
    ".png", ".jpg", ".jpeg", ".md",
}

LEGACY_ARTIFACT_FILENAMES = {
    "bureau_auto_fetch.json",
    "company_profile_web.json",
    "crilc_auto_fetch.json",
    "epfo_auto_fetch.json",
    "gst_turnover_auto_fetch.json",
    "gstin_auto_fetch.json",
    "itr_auto_fetch.json",
    "market_auto_fetch.json",
    "mca_charges_auto_fetch.json",
    "mca_directors_auto_fetch.json",
    "mca_master_auto_fetch.json",
    "mca_master_data.json",
    "nse_live_quote.json",
    "rating_auto_fetch.json",
    "web_scraped_financials.json",
}

HIDDEN_SYSTEM_FILENAMES = {
    "probe42_bundle.json",
    "probe42_data_status.json",
}

SOURCE_LABELS = {
    "manual_upload": "Manual Upload",
    "probe42_mcp_v2": "Verified Public Records",
    "reference_library": "Reference Library",
    "synthetic_assets": "Synthetic PDF",
    "upload": "Manual Upload",
}


class DocumentStore:
    """
    Local document store with S3-compatible interface.
    In production, swap _local_* methods for boto3 S3 calls.
    """

    def __init__(self, root: Path = None):
        self.root = root or STORAGE_ROOT
        self.root.mkdir(parents=True, exist_ok=True)

    # ── Company Folder Management ────────────────────────────────

    def init_company_folder(self, entity_id: str) -> dict:
        """Create full folder structure for a company. Idempotent."""
        base = self.root / entity_id
        created = []
        for category in DOCUMENT_CATEGORIES:
            folder = base / category
            folder.mkdir(parents=True, exist_ok=True)
            created.append(str(folder.relative_to(self.root)))

        # Create metadata file
        meta_path = base / "metadata.json"
        if not meta_path.exists():
            meta = {
                "entity_id": entity_id,
                "created_at": datetime.now().isoformat(),
                "document_index": {},
                "fetch_status": {},
            }
            meta_path.write_text(json.dumps(meta, indent=2))

        return {"entity_id": entity_id, "folders_created": created}

    def list_company_documents(self, entity_id: str) -> dict:
        """List company documents with active-vs-legacy classification."""
        base = self.root / entity_id
        if not base.exists():
            return {"entity_id": entity_id, "exists": False, "categories": {}}

        metadata = self._load_metadata(entity_id)
        indexed_documents = metadata.get("document_index", {}) if isinstance(metadata, dict) else {}

        result = {
            "entity_id": entity_id,
            "exists": True,
            "categories": {},
            "metadata": {
                "source": metadata.get("source"),
                "last_fetched": metadata.get("last_fetched"),
            },
        }
        total_files = 0
        raw_total_files = 0
        hidden_legacy_files = 0
        hidden_system_files = 0
        source_artifact_count = 0
        document_file_count = 0
        active_sources: set[str] = set()
        indexed_active_files = 0
        total_expected = 0
        total_matched = 0

        for category, info in DOCUMENT_CATEGORIES.items():
            cat_path = base / category
            if not cat_path.exists():
                cat_path.mkdir(parents=True, exist_ok=True)

            files = sorted(f.name for f in cat_path.iterdir() if f.is_file())
            raw_total_files += len(files)

            items: list[dict[str, Any]] = []
            legacy_items: list[dict[str, Any]] = []
            hidden_items: list[dict[str, Any]] = []
            visible_document_stems: set[str] = set()
            visible_document_names: list[str] = []

            for filename in files:
                index_key = f"{category}/{filename}"
                index_entry = indexed_documents.get(index_key)
                item = self._build_document_item(category, filename, index_entry)
                visibility = item["visibility"]
                if visibility == "active":
                    items.append(item)
                    total_files += 1
                    if item["file_type"] == "document":
                        document_file_count += 1
                        visible_document_stems.add(Path(filename).stem)
                        visible_document_names.append(filename)
                    else:
                        source_artifact_count += 1
                        indexed_active_files += 1
                    if item.get("source"):
                        active_sources.add(item["source"])
                elif visibility == "legacy":
                    legacy_items.append(item)
                    hidden_legacy_files += 1
                else:
                    hidden_items.append(item)
                    hidden_system_files += 1

            required = REQUIRED_DOCUMENT_FILES.get(category, [])
            matched_files: list[str] = []
            missing_files: list[str] = []
            for required_file in required:
                required_role = classify_document_role(category, required_file)
                if required_role:
                    is_present = requirement_is_satisfied(category, visible_document_names, required_role)
                else:
                    is_present = Path(required_file).stem in visible_document_stems
                if is_present:
                    matched_files.append(required_file)
                else:
                    missing_files.append(required_file)
            total_expected += len(required)
            total_matched += len(matched_files)

            result["categories"][category] = {
                "description": info["description"],
                "source_hint": info.get("source_hint", ""),
                "public_record_note": info.get("public_record_note", ""),
                "files": [item["filename"] for item in items],
                "items": sorted(items, key=lambda item: (item["file_type"] != "document", item["filename"])),
                "legacy_items": sorted(legacy_items, key=lambda item: (item["file_type"] != "document", item["filename"])),
                "system_items": sorted(hidden_items, key=lambda item: (item["file_type"] != "document", item["filename"])),
                "expected": required,
                "missing": missing_files,
                "raw_files": files,
                "hidden_legacy_count": len(legacy_items),
                "hidden_legacy_files": [item["filename"] for item in legacy_items],
                "hidden_system_count": len(hidden_items),
                "hidden_system_files": [item["filename"] for item in hidden_items],
                "completeness_pct": self._category_completeness(required, len(matched_files), len(items)),
            }

        result["total_files"] = total_files
        result["raw_total_files"] = raw_total_files
        result["document_file_count"] = document_file_count
        result["source_artifact_count"] = source_artifact_count
        result["indexed_active_files"] = indexed_active_files
        result["hidden_legacy_files"] = hidden_legacy_files
        result["hidden_system_files"] = hidden_system_files
        result["active_sources"] = sorted(active_sources)
        result["overall_completeness_pct"] = round(total_matched / total_expected * 100, 1) if total_expected else 100.0
        return result

    def store_document(self, entity_id: str, category: str, filename: str,
                       content: bytes, source: str = "upload", document_role: str | None = None) -> dict:
        """Store a document file. Returns metadata."""
        if category not in DOCUMENT_CATEGORIES:
            raise ValueError(f"Invalid category: {category}")

        self.init_company_folder(entity_id)
        file_path = self.root / entity_id / category / filename
        file_path.write_bytes(content)

        # Update metadata
        self._update_index(entity_id, category, filename, source, document_role=document_role)

        return {
            "entity_id": entity_id,
            "category": category,
            "filename": filename,
            "size_bytes": len(content),
            "source": source,
            "stored_at": datetime.now().isoformat(),
            "path": str(file_path.relative_to(self.root)),
        }

    def get_document(self, entity_id: str, category: str, filename: str) -> Optional[bytes]:
        """Retrieve document content."""
        file_path = self.root / entity_id / category / filename
        if file_path.exists():
            return file_path.read_bytes()
        return None

    def delete_company(self, entity_id: str) -> bool:
        """Remove all documents for a company."""
        base = self.root / entity_id
        if base.exists():
            shutil.rmtree(base)
            return True
        return False

    def delete_document(self, entity_id: str, category: str, filename: str) -> bool:
        """Delete a single document file and remove from index."""
        file_path = self.root / entity_id / category / filename
        if not file_path.exists():
            return False
        file_path.unlink()
        # Remove from metadata index
        meta_path = self.root / entity_id / "metadata.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                key = f"{category}/{filename}"
                meta.get("document_index", {}).pop(key, None)
                meta_path.write_text(json.dumps(meta, indent=2))
            except Exception:
                pass
        return True

    def list_all_companies(self) -> list[str]:
        """List all companies with document folders."""
        if not self.root.exists():
            return []
        return [d.name for d in self.root.iterdir() if d.is_dir()]

    # ── Internal ─────────────────────────────────────────────────

    def _update_index(self, entity_id: str, category: str, filename: str, source: str, document_role: str | None = None):
        meta_path = self.root / entity_id / "metadata.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
        else:
            meta = {"entity_id": entity_id, "document_index": {}, "fetch_status": {}}

        # Ensure required keys exist (metadata may have been created by document_downloader)
        meta.setdefault("document_index", {})
        meta.setdefault("fetch_status", {})

        key = f"{category}/{filename}"
        entry = {
            "filename": filename,
            "category": category,
            "source": source,
            "indexed_at": datetime.now().isoformat(),
        }
        if document_role:
            entry["document_role"] = document_role
        meta["document_index"][key] = entry
        meta_path.write_text(json.dumps(meta, indent=2))

    def _load_metadata(self, entity_id: str) -> dict[str, Any]:
        meta_path = self.root / entity_id / "metadata.json"
        if not meta_path.exists():
            return {"entity_id": entity_id, "document_index": {}, "fetch_status": {}}
        try:
            meta = json.loads(meta_path.read_text())
        except Exception:
            return {"entity_id": entity_id, "document_index": {}, "fetch_status": {}}
        meta.setdefault("document_index", {})
        meta.setdefault("fetch_status", {})
        return meta

    def _build_document_item(self, category: str, filename: str, index_entry: dict[str, Any] | None) -> dict[str, Any]:
        lower_name = filename.lower()
        suffix = Path(filename).suffix.lower()
        source = (index_entry or {}).get("source")
        file_type = "document" if suffix in VISIBLE_DOCUMENT_EXTENSIONS else "source_artifact"
        stored_role = (index_entry or {}).get("document_role")
        document_role = stored_role or (classify_document_role(category, filename) if file_type == "document" else None)
        visibility = "active"

        if lower_name in HIDDEN_SYSTEM_FILENAMES:
            visibility = "hidden"
        elif index_entry:
            visibility = "active"
        elif lower_name in LEGACY_ARTIFACT_FILENAMES or lower_name.endswith("_auto_fetch.json"):
            visibility = "legacy"
            file_type = "source_artifact"
            source = "legacy_system"
        elif suffix == ".json":
            visibility = "legacy"
            file_type = "source_artifact"
            source = source or "system_artifact"
        elif suffix not in VISIBLE_DOCUMENT_EXTENSIONS:
            visibility = "hidden"
            source = source or "system_artifact"
        else:
            source = source or "local_file"

        return {
            "category": category,
            "filename": filename,
            "file_type": file_type,
            "document_role": document_role,
            "document_role_label": role_label(document_role) if document_role else None,
            "source": source,
            "source_label": SOURCE_LABELS.get(source or "", "Local File" if source == "local_file" else str(source or "System")),
            "is_indexed": bool(index_entry),
            "indexed_at": (index_entry or {}).get("indexed_at"),
            "visibility": visibility,
        }

    def _category_completeness(self, required: list[str], matched_count: int, visible_count: int) -> float:
        if required:
            return round(matched_count / len(required) * 100, 1)
        return 100.0


# Singleton
doc_store = DocumentStore()
