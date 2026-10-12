from __future__ import annotations

import copy
import json
import re
from datetime import date
from typing import Any

from src.core.runtime_paths import ETB_OVERLAY_ROOT, REFERENCE_CAM_ROOT
from src.models.canonical_model import (
    Borrower,
    BorrowerType,
    CaseType,
    ConductRecord,
    CovenantRecord,
    ExistingExposure,
    FacilityRequest,
    FacilityType,
    GroupEntity,
    Sector,
)
from src.services.document_store import doc_store


CATALOG_COMPANIES: list[dict[str, Any]] = [
    {
        "entity_id": "APOL001",
        "company_name": "Apollo Hospitals Enterprise Limited",
        "sector": Sector.HEALTHCARE,
        "borrower_type": BorrowerType.LISTED,
        "case_type": CaseType.NTB,
        "facility_type": FacilityType.WORKING_CAPITAL,
        "default_amount_cr": 600.0,
        "reference_prefix": "Apollo Hosp",
        "preferred_identifier": "Apollo Hospitals Enterprise Limited",
    },
    {
        "entity_id": "INFY001",
        "company_name": "Infosys Limited",
        "sector": Sector.IT_SERVICES,
        "borrower_type": BorrowerType.LISTED,
        "case_type": CaseType.NTB,
        "facility_type": FacilityType.WORKING_CAPITAL,
        "default_amount_cr": 500.0,
        "reference_prefix": "Infy",
        "preferred_identifier": "Infosys Limited",
    },
    {
        "entity_id": "IHCL001",
        "company_name": "The Indian Hotels Company Limited",
        "sector": Sector.HOSPITALITY,
        "borrower_type": BorrowerType.LISTED,
        "case_type": CaseType.ETB,
        "facility_type": FacilityType.WORKING_CAPITAL,
        "default_amount_cr": 350.0,
        "reference_prefix": "IHCL",
        "preferred_identifier": "The Indian Hotels Company Limited",
    },
    {
        "entity_id": "MFL001",
        "company_name": "Madras Fertilizers Limited",
        "sector": Sector.MANUFACTURING,
        "borrower_type": BorrowerType.LISTED,
        "case_type": CaseType.NTB,
        "facility_type": FacilityType.WORKING_CAPITAL,
        "default_amount_cr": 120.0,
        "reference_prefix": "Madras Fert",
        "preferred_identifier": "Madras Fertilizers Limited",
    },
    {
        "entity_id": "MRF001",
        "company_name": "MRF Limited",
        "sector": Sector.MANUFACTURING,
        "borrower_type": BorrowerType.LISTED,
        "case_type": CaseType.NTB,
        "facility_type": FacilityType.WORKING_CAPITAL,
        "default_amount_cr": 300.0,
        "reference_prefix": "MRF",
        "preferred_identifier": "MRF Limited",
    },
    {
        "entity_id": "PNCR001",
        "company_name": "PNC Infratech Limited",
        "sector": Sector.INFRASTRUCTURE,
        "subsector": "Road & Highway Construction \u2014 EPC",
        "borrower_type": BorrowerType.LISTED,
        "case_type": CaseType.NTB,
        "facility_type": FacilityType.TERM_LOAN,
        "default_amount_cr": 1500.0,
        "cin": "L45201DL1999PLC195937",
        "pan": "AABCP1234R",
        "credit_rating": "CARE AA+/Stable",
        "rating_agency": "CARE",
        "date_of_incorporation": date(1999, 8, 9),
        "registered_state": "Delhi",
        "employee_count": 14500,
        "website": "www.pncinfra.com",
        "authorized_capital": 150.0,
        "paid_up_capital": 51.3,
        "reference_prefix": "PNCR",
        "preferred_identifier": "PNC Infratech Limited",
    },
]


def _build_company_payload(entry: dict[str, Any]) -> dict[str, Any]:
    borrower = Borrower(
        entity_id=entry["entity_id"],
        company_name=entry["company_name"],
        cin=entry.get("cin", ""),
        pan=entry.get("pan", ""),
        borrower_type=entry["borrower_type"],
        sector=entry["sector"],
        subsector=entry.get("subsector", entry["sector"].value),
        date_of_incorporation=entry.get("date_of_incorporation", date(2000, 1, 1)),
        registered_state=entry.get("registered_state", "Unknown"),
        registered_address=entry.get("registered_address", "To be populated from verified public records"),
        authorized_capital=float(entry.get("authorized_capital", 0.0)),
        paid_up_capital=float(entry.get("paid_up_capital", 0.0)),
        listed_exchange=entry.get("listed_exchange", "NSE/BSE"),
        isin=entry.get("isin"),
        bse_code=entry.get("bse_code"),
        nse_symbol=entry.get("nse_symbol"),
        credit_rating=entry.get("credit_rating"),
        rating_agency=entry.get("rating_agency"),
        employee_count=entry.get("employee_count"),
        website=entry.get("website"),
    )
    group = GroupEntity(
        group_id=f"GRP-{entry['entity_id']}",
        group_name=entry.get("group_name", entry["company_name"]),
        parent_entity_id=entry["entity_id"],
        entities=[entry["entity_id"]],
    )
    facility = FacilityRequest(
        facility_id=f"FAC-{entry['entity_id']}",
        entity_id=entry["entity_id"],
        case_type=entry["case_type"],
        facility_type=entry["facility_type"],
        amount_requested_cr=float(entry.get("default_amount_cr", 0.0)),
        purpose=entry.get("purpose", "To be captured by RM during onboarding"),
        proposed_limit_cr=float(entry.get("default_amount_cr", 0.0)) if entry.get("default_amount_cr") else None,
    )
    payload = {
        "borrower": borrower,
        "group": group,
        "directors": [],
        "financials": {},
        "provisional": None,
        "facility": facility,
        "collateral": [],
        "market_signals": [],
        "existing_exposure": [],
        "conduct": [],
        "covenants": [],
        "exchange_filing": None,
        "core_banking": {},
        "data_provider": "verified_public_records",
        "catalog_source": "reference_catalog",
        "preferred_identifier": entry.get("preferred_identifier", entry["company_name"]),
        "reference_prefix": entry.get("reference_prefix"),
    }
    overlay = _load_etb_overlay(entry["entity_id"])
    payload.update(overlay)
    if overlay:
        payload["etb_overlay"] = True   # synthetic conduct / core-banking data (data provenance)
    return payload


def _load_etb_overlay(entity_id: str) -> dict[str, Any]:
    overlay_path = ETB_OVERLAY_ROOT / f"{entity_id}.json"
    if not overlay_path.exists():
        return {}

    try:
        payload = json.loads(overlay_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    overlay: dict[str, Any] = {}
    overlay["core_banking"] = payload.get("core_banking") or {}
    overlay["existing_exposure"] = [
        ExistingExposure(
            facility_id=str(item.get("facility_id") or f"EXP-{entity_id}"),
            entity_id=str(item.get("entity_id") or entity_id),
            facility_type=str(item.get("facility_type") or "facility"),
            sanctioned_limit_cr=float(item.get("sanctioned_limit_cr") or 0.0),
            outstanding_cr=float(item.get("outstanding_cr") or 0.0),
            utilization_pct=float(item.get("utilization_pct") or 0.0),
            overdue_days=int(item.get("overdue_days") or 0),
            classification=str(item.get("classification") or "Standard"),
        )
        for item in (payload.get("existing_exposure") or [])
        if isinstance(item, dict)
    ]
    overlay["conduct"] = [
        ConductRecord(
            entity_id=str(item.get("entity_id") or entity_id),
            period=str(item.get("period") or ""),
            avg_bank_balance_cr=float(item.get("avg_bank_balance_cr") or 0.0),
            credit_turnover_cr=float(item.get("credit_turnover_cr") or 0.0),
            debit_turnover_cr=float(item.get("debit_turnover_cr") or 0.0),
            cheque_returns=int(item.get("cheque_returns") or 0),
            limit_utilization_pct=float(item.get("limit_utilization_pct") or 0.0),
            overdue_instances=int(item.get("overdue_instances") or 0),
            max_overdue_days=int(item.get("max_overdue_days") or 0),
            dpd_30_count=int(item.get("dpd_30_count") or 0),
            dpd_60_count=int(item.get("dpd_60_count") or 0),
            dpd_90_count=int(item.get("dpd_90_count") or 0),
        )
        for item in (payload.get("conduct") or [])
        if isinstance(item, dict)
    ]
    overlay["covenants"] = [
        CovenantRecord(
            entity_id=str(item.get("entity_id") or entity_id),
            covenant_type=str(item.get("covenant_type") or ""),
            required_value=str(item.get("required_value") or ""),
            actual_value=str(item.get("actual_value") or ""),
            compliance_status=str(item.get("compliance_status") or "compliant"),
            period=str(item.get("period") or ""),
            breach_details=str(item.get("breach_details") or ""),
        )
        for item in (payload.get("covenants") or [])
        if isinstance(item, dict)
    ]
    return overlay


def seed_company_store() -> dict[str, dict[str, Any]]:
    store = {entry["entity_id"]: _build_company_payload(entry) for entry in CATALOG_COMPANIES}
    # Merge in rich seed data (financials, provisional, directors) from real_companies
    try:
        from src.data.real_companies import REAL_COMPANIES
        for eid, real in REAL_COMPANIES.items():
            if eid in store:
                for key in ("financials", "provisional", "directors", "market_signals", "collateral",
                            "borrower", "facility", "group", "exchange_filing", "infra_metrics",
                            "core_banking", "existing_exposure", "conduct", "covenants"):
                    if real.get(key):
                        store[eid][key] = real[key]
    except ImportError:
        pass
    # Merge sector-specific KPIs (road_construction, pharma, etc.)
    try:
        from src.data.sector_kpis import SECTOR_KPIS
        for eid, kpis in SECTOR_KPIS.items():
            if eid in store:
                store[eid]["sector_kpis"] = kpis
    except ImportError:
        pass
    # Synthetic demo borrowers built to exercise specific capabilities (fully specified, no enrichment).
    from src.data.demo_companies import DEMO_COMPANIES
    store.update(copy.deepcopy(DEMO_COMPANIES))
    return store


def catalog_company_ids() -> list[str]:
    return [entry["entity_id"] for entry in CATALOG_COMPANIES]


def _fiscal_year_suffix(filename: str) -> str | None:
    if "Unaudited" in filename:
        match = re.search(r"(\d{4})-(\d{2})", filename)
        if not match:
            return None
        return f"FY20{match.group(2)}"

    match = re.search(r"(\d{2,4})[-_](\d{2,4})", filename)
    if not match:
        return None
    end_token = match.group(2)
    if len(end_token) == 2:
        return f"FY20{end_token}"
    return f"FY{end_token}"


def _target_filename(source_name: str) -> str:
    fiscal_year = (_fiscal_year_suffix(source_name) or "FYUnknown").lower()
    if "Unaudited" in source_name:
        return f"unaudited_results_{fiscal_year}.pdf"
    return f"annual_report_{fiscal_year}.pdf"


def bootstrap_reference_documents(replace_existing: bool = False) -> dict[str, int]:
    summary: dict[str, int] = {}
    if not REFERENCE_CAM_ROOT.exists():
        return summary

    for entry in CATALOG_COMPANIES:
        entity_id = entry["entity_id"]
        prefix = entry["reference_prefix"]
        matching_files = sorted(REFERENCE_CAM_ROOT.glob(f"{prefix}*.pdf"))
        if not matching_files:
            continue

        summary[entity_id] = 0
        doc_store.init_company_folder(entity_id)
        for source_path in matching_files:
            target_name = _target_filename(source_path.name)
            existing = doc_store.root / entity_id / "financials" / target_name
            if existing.exists() and not replace_existing:
                continue
            doc_store.store_document(
                entity_id,
                "financials",
                target_name,
                source_path.read_bytes(),
                source="reference_library",
            )
            summary[entity_id] += 1
    return summary
