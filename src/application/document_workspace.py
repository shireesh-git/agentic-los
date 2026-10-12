"""
Document workspace: what a borrower's document folder contains, which RM
uploads are still missing, which public-record snapshots are absent, and which
reference documents belong to the borrower.
"""

import json
import re
from pathlib import Path

from src.services.document_classifier import requirement_is_satisfied

RM_UPLOAD_REQUIREMENTS = [
    {
        "type": "audited_financial_statements",
        "description": "Audited financial statements for latest 3 years",
        "category": "financials",
        "role": "audited_financial_statements",
    },
    {
        "type": "provisional_financials",
        "description": "Latest provisional or management financials",
        "category": "financials",
        "role": "provisional_financials",
    },
    {
        "type": "debt_schedule",
        "description": "Detailed debt schedule and lender-wise exposure",
        "category": "financials",
        "role": "debt_schedule",
    },
    {
        "type": "board_resolution",
        "description": "Board resolution / borrowing approval",
        "category": "kyc",
        "role": "board_resolution",
    },
    {
        "type": "cma_or_projection",
        "description": "CMA data / projections / repayment assumptions",
        "category": "request",
        "role": "cma_or_projection",
    },
]

PROBE_SOURCE_REQUIREMENTS = [
    {"category": "mca", "filename": "probe42_base_details.json", "description": "Probe42 company master profile"},
    {"category": "mca", "filename": "probe42_open_charges.json", "description": "Probe42 open charges profile"},
    {"category": "kyc", "filename": "probe42_kyc_details.json", "description": "Probe42 KYC profile"},
    {"category": "legal", "filename": "probe42_legal_history.json", "description": "Probe42 legal history"},
    {"category": "ratings", "filename": "probe42_credit_ratings.json", "description": "Probe42 credit ratings snapshot"},
    {"category": "gst", "filename": "probe42_gst_details.json", "description": "Probe42 GST profile"},
    {"category": "legal", "filename": "probe42_epfo_details.json", "description": "Probe42 EPFO profile"},
    {"category": "legal", "filename": "probe42_suit_filed_cases.json", "description": "Probe42 suit-filed cases"},
    {"category": "mca", "filename": "probe42_director_network.json", "description": "Probe42 director network"},
    {"category": "misc", "filename": "probe42_data_status.json", "description": "Probe42 data status and freshness"},
]

PROBE_PROVIDER = "probe42_mcp_v2"

_REFERENCE_STOP_WORDS = {
    "and", "co", "company", "corp", "corporation", "inc", "india", "industries",
    "limited", "ltd", "pvt", "private", "services", "solutions",
}


def _normalize_lookup_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def _significant_tokens(text: str) -> set[str]:
    return {
        token for token in _normalize_lookup_text(text).split()
        if len(token) >= 3 and token not in _REFERENCE_STOP_WORDS
    }


class DocumentWorkspaceService:
    """Read-side view over a company's documents plus completeness checks."""

    def __init__(self, documents_root: Path, reference_root: Path):
        self.documents_root = documents_root
        self.reference_root = reference_root

    # ── Completeness ─────────────────────────────────────────────────────

    @staticmethod
    def provider(company_data: dict | None, workspace: dict) -> str:
        provider = (company_data or {}).get("data_provider")
        if provider:
            return provider
        if PROBE_PROVIDER in set(workspace.get("active_sources") or []):
            return PROBE_PROVIDER
        return "internal"

    @staticmethod
    def required_missing_documents(workspace: dict) -> list[dict]:
        missing: list[dict] = []
        for requirement in RM_UPLOAD_REQUIREMENTS:
            category_info = (workspace.get("categories") or {}).get(requirement["category"]) or {}
            visible_files = category_info.get("files") or []
            if requirement_is_satisfied(requirement["category"], visible_files, requirement["role"]):
                continue
            # Also satisfied when an upload was explicitly tagged with the role.
            items = category_info.get("items") or []
            if any(item.get("document_role") == requirement["role"] for item in items):
                continue
            missing.append({
                "type": requirement["type"],
                "description": requirement["description"],
                "category": requirement["category"],
                "source": "rm_upload",
            })
        return missing

    @classmethod
    def source_gaps(cls, company_data: dict | None, workspace: dict) -> list[dict]:
        if cls.provider(company_data, workspace) != PROBE_PROVIDER:
            return []
        missing: list[dict] = []
        categories = workspace.get("categories") or {}
        for requirement in PROBE_SOURCE_REQUIREMENTS:
            files = set((categories.get(requirement["category"]) or {}).get("raw_files") or [])
            if requirement["filename"] in files:
                continue
            missing.append({
                "type": requirement["filename"].replace(".json", ""),
                "description": requirement["description"],
                "category": requirement["category"],
                "source": PROBE_PROVIDER,
            })
        return missing

    def augment(self, company_data: dict | None, workspace: dict) -> dict:
        """Annotate a document-store listing with coverage and gap information."""
        if not workspace.get("exists"):
            return workspace

        required_missing = self.required_missing_documents(workspace)
        requirement_map: dict[str, list[dict]] = {}
        for requirement in RM_UPLOAD_REQUIREMENTS:
            requirement_map.setdefault(requirement["category"], []).append(requirement)
        total_required = len(RM_UPLOAD_REQUIREMENTS)
        matched_required = total_required - len(required_missing)

        for category, info in (workspace.get("categories") or {}).items():
            visible_files = info.get("files") or []
            requirements = requirement_map.get(category, [])
            matched = 0
            missing_descriptions: list[str] = []
            for requirement in requirements:
                if requirement_is_satisfied(category, visible_files, requirement["role"]):
                    matched += 1
                else:
                    missing_descriptions.append(requirement["description"])
            info["upload_required_count"] = len(requirements)
            info["upload_matched_count"] = matched
            info["upload_missing_descriptions"] = missing_descriptions
            info["upload_coverage_pct"] = round(matched / len(requirements) * 100, 1) if requirements else None
            info["has_archived_reference"] = bool(
                (info.get("hidden_legacy_count") or 0) + (info.get("hidden_system_count") or 0)
            )

        workspace["provider"] = self.provider(company_data, workspace)
        workspace["required_missing_documents"] = required_missing
        workspace["source_gaps"] = self.source_gaps(company_data, workspace)
        workspace["upload_required_count"] = total_required
        workspace["upload_matched_count"] = matched_required
        workspace["upload_coverage_pct"] = (
            round(matched_required / total_required * 100, 1) if total_required else 100.0
        )
        workspace["hidden_artifact_count"] = (
            int(workspace.get("hidden_legacy_files", 0)) + int(workspace.get("hidden_system_files", 0))
        )
        workspace["summary_note"] = (
            f"Showing {workspace.get('total_files', 0)} borrower/reference files with "
            f"{workspace.get('hidden_artifact_count', 0)} additional source/system files available."
        )
        workspace["public_record_note"] = (
            "Verified public records are retained locally and reused automatically. "
            "Borrower, RM, and internal bank files must still be uploaded into the workspace."
        )
        return workspace

    # ── Probe42 snapshots ────────────────────────────────────────────────

    @staticmethod
    def probe_identifiers(entity_id: str, company_data: dict | None) -> list[str]:
        """Every identifier under which this company's Probe42 data may be cached."""
        identifiers: set[str] = {entity_id}
        company_data = company_data or {}
        borrower = company_data.get("borrower")
        for value in (
            getattr(borrower, "cin", None),
            getattr(borrower, "pan", None),
            getattr(borrower, "gstin", None),
            company_data.get("preferred_identifier"),
        ):
            if value:
                identifiers.add(str(value))

        bundle = company_data.get("probe_bundle") or {}
        for source in (company_data.get("probe_summary") or {}, bundle.get("resolved") or {}):
            if not isinstance(source, dict):
                continue
            for key in ("cin", "pan", "gstin", "company_name"):
                if source.get(key):
                    identifiers.add(str(source[key]))
        if bundle.get("resolved_identifier"):
            identifiers.add(str(bundle["resolved_identifier"]))
        return sorted(identifiers)

    def clear_probe_documents(self, entity_id: str) -> list[str]:
        """Delete stored ``probe42_*.json`` snapshots and their metadata entries."""
        entity_root = self.documents_root / entity_id
        deleted: list[str] = []
        if not entity_root.exists():
            return deleted

        for path in entity_root.rglob("probe42_*.json"):
            if not path.is_file():
                continue
            try:
                path.unlink()
                deleted.append(str(path.relative_to(entity_root)))
            except Exception:
                continue

        metadata_path = entity_root / "metadata.json"
        if metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                doc_index = metadata.get("document_index") or {}
                metadata["document_index"] = {
                    key: value for key, value in doc_index.items() if "probe42_" not in key
                }
                metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
            except Exception:
                pass
        return deleted

    # ── Reference documents (manual fact-check only) ─────────────────────

    def reference_groups(self) -> dict[str, list[str]]:
        if not self.reference_root.exists():
            return {}
        groups: dict[str, list[str]] = {}
        for filename in sorted(f.name for f in self.reference_root.iterdir() if f.is_file()):
            for sep in ("_AR_", "_Annual", "_Unaudited"):
                if sep in filename:
                    prefix = filename.split(sep)[0]
                    break
            else:
                prefix = filename.rsplit("_", 1)[0] if "_" in filename else filename
            groups.setdefault(prefix, []).append(filename)
        return groups

    @staticmethod
    def reference_aliases(entity_id: str, company_data: dict | None) -> list[str]:
        aliases: set[str] = set()
        normalized_entity = _normalize_lookup_text(entity_id).replace(" ", "")
        if normalized_entity:
            aliases.add(normalized_entity)
        if entity_id and len(entity_id) >= 4:
            aliases.add(_normalize_lookup_text(entity_id[:4]).replace(" ", ""))

        borrower = (company_data or {}).get("borrower")
        company_name = getattr(borrower, "company_name", "") if borrower else ""
        compact_name = _normalize_lookup_text(company_name).replace(" ", "")
        if compact_name:
            aliases.add(compact_name)
        aliases.update(_significant_tokens(company_name))
        return sorted(alias for alias in aliases if alias)

    @staticmethod
    def reference_match(group: str, aliases: list[str]) -> bool:
        compact_group = _normalize_lookup_text(group).replace(" ", "")
        group_tokens = _significant_tokens(group)
        for alias in aliases:
            compact_alias = alias.replace(" ", "")
            if not compact_alias:
                continue
            if compact_alias in compact_group or compact_group in compact_alias:
                return True
            if compact_alias in group_tokens:
                return True
        return False
