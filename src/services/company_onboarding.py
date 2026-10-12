"""
Company Onboarding Service — Auto-fetch from external systems.

User provides ONLY one of: PAN, GSTIN, or Company Name.
System auto-resolves identity, fetches all data from mock external APIs,
builds canonical dataclasses, and populates document store.
"""

from datetime import date
from typing import Optional

from src.models.canonical_model import (
    Borrower, GroupEntity, DirectorPromoter, FinancialStatement,
    FacilityRequest, Collateral, ExistingExposure, MarketSignal,
    ConductRecord, CaseType, BorrowerType, FacilityType, Sector,
)
from src.services.external_systems import (
    resolve_company, mca_company_master, mca_directors, mca_charges,
    gstin_details, gstin_turnover, bureau_commercial_report,
    rating_action, market_intelligence, crilc_report,
    epfo_compliance, itr_filing_status,
    _PAN_TO_GSTIN, _ENTITY_TO_IDS,
)
from src.services.document_store import doc_store
from src.services.probe_service import onboard_company_via_probe


# Maps NIC codes to our Sector enum
_NIC_TO_SECTOR = {
    # Manufacturing
    "28": Sector.MANUFACTURING, "29": Sector.MANUFACTURING,
    "27": Sector.MANUFACTURING, "25": Sector.MANUFACTURING,
    "10": Sector.MANUFACTURING, "20": Sector.MANUFACTURING,
    "22": Sector.MANUFACTURING, "24": Sector.MANUFACTURING,
    "34": Sector.MANUFACTURING,
    # Infrastructure
    "42": Sector.INFRASTRUCTURE, "41": Sector.INFRASTRUCTURE,
    "43": Sector.INFRASTRUCTURE,
    # Pharma
    "21": Sector.PHARMA,
    # Logistics
    "49": Sector.LOGISTICS, "52": Sector.LOGISTICS,
    "53": Sector.LOGISTICS, "50": Sector.LOGISTICS,
    # IT Services
    "62": Sector.IT_SERVICES, "63": Sector.IT_SERVICES,
    # Healthcare
    "86": Sector.HEALTHCARE, "87": Sector.HEALTHCARE,
    "85": Sector.HEALTHCARE,
    # Hospitality
    "55": Sector.HOSPITALITY, "56": Sector.HOSPITALITY,
    # Energy
    "35": Sector.ENERGY, "40": Sector.ENERGY,
    # NBFC / Banking
    "64": Sector.NBFC, "65": Sector.NBFC, "66": Sector.NBFC,
    # Real Estate
    "68": Sector.REAL_ESTATE,
    # Trading
    "46": Sector.TRADING, "47": Sector.TRADING,
}


def _infer_sector(nic_code: str) -> Sector:
    """Infer sector from NIC code (first 2 digits). An unmapped code falls back to manufacturing;
    sector_basis() tells the two apart."""
    prefix = nic_code[:2] if nic_code else ""
    return _NIC_TO_SECTOR.get(prefix, Sector.MANUFACTURING)


def sector_basis(nic_code: str) -> str:
    """"nic_code" when the NIC code maps to a sector, else "default" (placeholder, not evidence)."""
    return "nic_code" if (nic_code or "")[:2] in _NIC_TO_SECTOR else "default"


def _infer_borrower_type(mca_data: dict) -> BorrowerType:
    """Determine borrower type from MCA listing status."""
    if mca_data.get("listing_status") == "Listed":
        return BorrowerType.LISTED
    return BorrowerType.UNLISTED


def _build_financials_from_gst_bureau(entity_id: str, pan: str, gstin_data: dict,
                                       bureau_data: dict) -> dict:
    """
    Build approximate financials from GST turnover + bureau exposure.
    In production, actual financials come from audited statements / ITR.
    For onboarding, we create an auto-populated template.
    """
    financials = {}
    turnover = gstin_data.get("payload", {})
    fy_turnovers = {
        "FY2024": turnover.get("aggregate_turnover_fy2024_cr"),
        "FY2023": turnover.get("aggregate_turnover_fy2023_cr"),
        "FY2022": turnover.get("aggregate_turnover_fy2022_cr"),
    }

    bureau_payload = bureau_data.get("payload", {})
    total_exposure = bureau_payload.get("total_exposure_cr", 0)

    for period, revenue in fy_turnovers.items():
        if not revenue:
            continue
        # Build approximate line items based on industry averages
        debt = total_exposure if period == "FY2024" else round(total_exposure * 0.90, 2)
        line_items = {
            "revenue_operating": revenue,
            "other_income": round(revenue * 0.012, 2),
            "total_income": round(revenue * 1.012, 2),
            "total_debt": debt,
            "long_term_debt": round(debt * 0.6, 2),
            # Placeholder — will be replaced once actual statements are uploaded
            "ebitda": round(revenue * 0.18, 2),  # conservative 18% margin
            "depreciation": round(revenue * 0.05, 2),
            "ebit": round(revenue * 0.13, 2),
            "finance_cost": round(total_exposure * 0.095, 2),  # ~9.5% avg cost
            "pbt": round(revenue * 0.13 - total_exposure * 0.095, 2),
            "tax_expense": round((revenue * 0.13 - total_exposure * 0.095) * 0.25, 2),
            "pat": round((revenue * 0.13 - total_exposure * 0.095) * 0.75, 2),
            "total_equity": round(total_exposure * 0.8, 2),  # assumed
            "current_assets": round(revenue * 0.35, 2),
            "current_liabilities": round(revenue * 0.22, 2),
            "total_assets": round(revenue * 0.95, 2),
            "trade_receivables": round(revenue * 0.14, 2),
            "inventory": round(revenue * 0.10, 2),
            "trade_payables": round(revenue * 0.09, 2),
            "intangible_assets": round(revenue * 0.02, 2),
        }
        financials[period] = FinancialStatement(
            entity_id=entity_id,
            period=period,
            statement_type="standalone",
            source="auto_estimated" if period != "FY2024" else "auto_estimated",
            as_of_date=date(int("20" + period[2:4]), 3, 31),
            line_items=line_items,
        )

    return financials


def _build_exposure_from_bureau(entity_id: str, bureau_data: dict) -> list:
    """Build ExistingExposure list from bureau facilities."""
    exposures = []
    facilities = bureau_data.get("payload", {}).get("facilities", [])
    for i, fac in enumerate(facilities):
        limit = fac.get("limit_cr", 0)
        outstanding = fac.get("outstanding_cr", 0)
        util = round(outstanding / limit * 100, 1) if limit else 0
        exposures.append(ExistingExposure(
            facility_id=f"BUR-{entity_id}-{i+1}",
            entity_id=entity_id,
            facility_type=fac.get("type", "TL"),
            sanctioned_limit_cr=limit,
            outstanding_cr=outstanding,
            utilization_pct=util,
            overdue_days=fac.get("dpd", 0),
            classification=fac.get("classification", "Standard"),
        ))
    return exposures


def _build_conduct_from_bureau(entity_id: str, bureau_data: dict) -> list:
    """Build ConductRecord from bureau data."""
    bp = bureau_data.get("payload", {})
    if not bp:
        return []
    max_dpd = bp.get("max_dpd_last_12m", 0)
    enquiries = bp.get("enquiries_last_6m", 0)
    record = ConductRecord(
        entity_id=entity_id,
        period="FY2024",
        avg_bank_balance_cr=0,
        credit_turnover_cr=bp.get("total_exposure_cr", 0),
        debit_turnover_cr=0,
        cheque_returns=0,
        limit_utilization_pct=85.0,
        overdue_instances=1 if max_dpd > 0 else 0,
        max_overdue_days=max_dpd,
        dpd_30_count=1 if max_dpd >= 30 else 0,
        dpd_60_count=1 if max_dpd >= 60 else 0,
        dpd_90_count=1 if max_dpd >= 90 else 0,
    )
    return [record]


def _build_market_signals(entity_id: str, market_data: dict, rating_data: dict) -> list:
    """Build MarketSignal list from market intelligence and rating data."""
    from src.models.canonical_model import RiskSeverity
    signals = []
    mp = market_data.get("payload", {})
    rp = rating_data.get("payload", {})

    if mp:
        score = mp.get("sentiment_score", 0)
        sentiment_str = "positive" if score > 0.5 else "negative" if score < -0.3 else "neutral"
        signals.append(MarketSignal(
            entity_id=entity_id,
            signal_type="sentiment",
            headline=f"Sentiment: {mp.get('overall_sentiment', 'unknown').title()} "
                     f"(score: {score:.2f})",
            sentiment=sentiment_str,
            severity=RiskSeverity.LOW if score > 0.3 else RiskSeverity.MEDIUM,
            source_name="market_intelligence",
            signal_date=date.today(),
        ))

    if rp:
        sentiment_str = "positive" if "Stable" in rp.get("outlook", "") else "negative"
        signals.append(MarketSignal(
            entity_id=entity_id,
            signal_type="rating",
            headline=f"{rp.get('long_term_rating', 'NR')} — {rp.get('last_action', '')}",
            sentiment=sentiment_str,
            severity=RiskSeverity.LOW,
            source_name=rp.get("rating_agency", "unknown"),
            signal_date=date.today(),
        ))

    return signals


def _store_fetched_documents(entity_id: str, fetched: dict):
    """Store document summaries from each external source into the document store."""
    import json
    doc_store.init_company_folder(entity_id)

    for source_name, data in fetched.items():
        if not data or data.get("source_status") == "not_found":
            continue
        # Determine category
        cat_map = {
            "mca_master": "mca", "mca_directors": "mca", "mca_charges": "mca",
            "gstin": "gst", "gst_turnover": "gst",
            "bureau": "bureau", "crilc": "bureau",
            "rating": "ratings", "market": "misc",
            "epfo": "legal", "itr": "financials",
        }
        category = cat_map.get(source_name, "misc")
        filename = f"{source_name}_auto_fetch.json"
        content = json.dumps(data, indent=2, default=str).encode("utf-8")
        doc_store.store_document(entity_id, category, filename, content)


def onboard_company(identifier: str,
                    case_type: str = "NTB",
                    facility_type: str = "working_capital",
                    amount_requested_cr: float = 100.0,
                    purpose: str = "General corporate purpose",
                    tenor_months: Optional[int] = None) -> dict:
    """
    Auto-onboard a company from a single identifier (PAN / GSTIN / Name / CIN / Entity ID).

    Returns: dict with { entity_id, company_data, fetched_sources, status }
    """
    try:
        probe_result = onboard_company_via_probe(
            identifier=identifier,
            case_type=case_type,
            facility_type=facility_type,
            amount_requested_cr=amount_requested_cr,
            purpose=purpose,
            tenor_months=tenor_months,
        )
        if probe_result:
            return probe_result
    except Exception:
        pass  # Fall through to mock external API path

    # Step 1: Resolve identity
    resolved = resolve_company(identifier)
    if not resolved:
        return {"status": "not_found",
                "message": f"Could not resolve company from identifier: {identifier}"}

    cin = resolved["cin"]
    pan = resolved["pan"]
    gstin = resolved["gstin"]
    entity_id = resolved["entity_id"]
    company_name = resolved["company_name"]

    if not entity_id:
        # Generate entity_id from company name
        entity_id = company_name[:4].upper().replace(" ", "") + "001"

    # Step 2: Fetch from all external sources
    fetched = {}
    fetched["mca_master"] = mca_company_master(cin)
    fetched["mca_directors"] = mca_directors(cin)
    fetched["mca_charges"] = mca_charges(cin)
    if pan:
        fetched["bureau"] = bureau_commercial_report(pan)
        fetched["gst_turnover"] = gstin_turnover(pan)
        fetched["crilc"] = crilc_report(pan)
        fetched["epfo"] = epfo_compliance(pan)
        fetched["itr"] = itr_filing_status(pan)
    if gstin:
        fetched["gstin"] = gstin_details(gstin)
    if entity_id:
        fetched["rating"] = rating_action(entity_id)
        fetched["market"] = market_intelligence(entity_id)

    # Step 3: Build canonical objects from fetched data
    mca_payload = fetched["mca_master"].get("payload", {})

    sector = _infer_sector(mca_payload.get("nic_code", ""))
    borrower_type = _infer_borrower_type(mca_payload)

    borrower = Borrower(
        entity_id=entity_id,
        company_name=company_name,
        cin=cin,
        pan=pan or "",
        borrower_type=borrower_type,
        sector=sector,
        subsector=mca_payload.get("industrial_class", sector.value),
        date_of_incorporation=date.fromisoformat(mca_payload["date_of_incorporation"])
            if mca_payload.get("date_of_incorporation") else date(2010, 1, 1),
        registered_state=mca_payload.get("registered_state", "Unknown"),
        registered_address=mca_payload.get("registered_office", ""),
        authorized_capital=mca_payload.get("authorized_capital_inr", 0) / 1e7,  # INR → Cr
        paid_up_capital=mca_payload.get("paid_up_capital_inr", 0) / 1e7,
        listed_exchange=mca_payload.get("listed_exchange"),
        credit_rating=fetched.get("rating", {}).get("payload", {}).get("long_term_rating"),
        rating_agency=fetched.get("rating", {}).get("payload", {}).get("rating_agency"),
        employee_count=fetched.get("epfo", {}).get("payload", {}).get("active_members"),
        website=mca_payload.get("email", "").replace("info@", "www.").replace("corp@", "www.")
            .replace("finance@", "www.").replace("accounts@", "www.") if mca_payload.get("email") else None,
    )

    # Directors
    directors = []
    for d in fetched.get("mca_directors", {}).get("payload", {}).get("directors", []):
        directors.append(DirectorPromoter(
            din=d.get("din", "00000000"),
            name=d["name"],
            designation=d.get("designation", "Director"),
            entity_id=entity_id,
            pan=d.get("pan"),
            date_of_appointment=date.fromisoformat(d["date_of_appointment"])
                if d.get("date_of_appointment") else None,
            other_directorships=d.get("other_companies", []),
            is_promoter="Managing" in d.get("designation", "") or
                        "Whole-time" in d.get("designation", "") or
                        d.get("shareholding_pct", 0) > 10,
        ))

    # Group (if directors have other companies)
    group = None
    other_entities = set()
    for d in directors:
        if d.other_directorships:
            for od in d.other_directorships:
                other_entities.add(od)
    if other_entities:
        group = GroupEntity(
            group_id=f"GRP_{entity_id}",
            group_name=f"{company_name.split()[0]} Group",
            parent_entity_id=entity_id,
            entities=[entity_id] + list(other_entities),
            promoter_holding_pct=sum(
                d.get("shareholding_pct", 0) for d in
                fetched.get("mca_directors", {}).get("payload", {}).get("directors", [])
                if d.get("shareholding_pct", 0) > 5
            ),
        )

    # Financials from GST + Bureau
    financials = _build_financials_from_gst_bureau(
        entity_id, pan or "",
        fetched.get("gst_turnover", {}),
        fetched.get("bureau", {}),
    )

    # Existing exposure from bureau
    existing_exposure = _build_exposure_from_bureau(entity_id, fetched.get("bureau", {}))

    # Conduct from bureau
    conduct = _build_conduct_from_bureau(entity_id, fetched.get("bureau", {}))

    # Market signals
    market_signals = _build_market_signals(
        entity_id, fetched.get("market", {}), fetched.get("rating", {}))

    # Facility request
    try:
        ct = CaseType(case_type)
    except ValueError:
        ct = CaseType.NTB
    try:
        ft = FacilityType(facility_type)
    except ValueError:
        ft = FacilityType.WORKING_CAPITAL

    # If ETB, check existing exposure
    if existing_exposure:
        # If we detect prior banking relationship (any existing exposure), mark as ETB
        if len(existing_exposure) > 0:
            ct = CaseType.ETB

    facility = FacilityRequest(
        facility_id=f"FAC-{entity_id}",
        entity_id=entity_id,
        case_type=ct,
        facility_type=ft,
        amount_requested_cr=amount_requested_cr,
        purpose=purpose,
        tenor_months=tenor_months,
    )

    # Step 4: Store documents
    _store_fetched_documents(entity_id, fetched)

    # Step 4b: Crawl web news (especially useful for NTB)
    web_crawl_news = []
    try:
        from src.services.web_crawl_service import crawl_company_news
        sector_val = sector.value if hasattr(sector, "value") else str(sector)
        news_result = crawl_company_news(company_name, sector_val, is_ntb=(ct == CaseType.NTB))
        web_crawl_news = news_result.get("articles", [])
    except Exception:
        pass

    # Step 5: Build the company data dict (same format as company_store)
    company_data = {
        "borrower": borrower,
        "sector_basis": sector_basis(mca_payload.get("nic_code", "")),
        "group": group,
        "directors": directors,
        "financials": financials,
        "provisional": None,
        "facility": facility,
        "collateral": [],
        "market_signals": market_signals,
        "existing_exposure": existing_exposure,
        "conduct": conduct,
        "covenants": [],
        "exchange_filing": None,
        "web_crawl_news": web_crawl_news,
    }

    # Build summary of what was fetched
    source_summary = {}
    for name, data in fetched.items():
        status = data.get("source_status", "unknown") if isinstance(data, dict) else "error"
        source_summary[name] = status

    return {
        "status": "success",
        "entity_id": entity_id,
        "company_name": company_name,
        "resolved": resolved,
        "company_data": company_data,
        "source_summary": source_summary,
        "documents_stored": doc_store.list_company_documents(entity_id),
    }
