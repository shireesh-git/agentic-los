"""
Demo documents for the borrowers on record
==========================================
Generates the non-public documents a bank holds for a borrower — KYC pack, GST returns summary, commercial bureau
report, bank statement, sanction note, collateral valuation, request note — as labelled synthetic stand-ins, from the
borrower's data file (data/borrowers/<id>.json). Real public filings (annual reports, results, rating rationales) are
not generated: they are fetched (config/borrower_documents.yaml). No borrower data is held in this module.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from src.core.runtime_paths import DOCUMENTS_ROOT
from src.services.document_operations import document_operations
from src.data.company_catalog import catalog_company_ids

logger = logging.getLogger(__name__)


def _profile(entity_id: str) -> dict[str, Any]:
    """The borrower's documents profile from its data file (data/borrowers/<id>.json, ``profile``): auditor, BSE code,
    official site and the narrative used in generated demo documents. No borrower data is held in this module."""
    from src.data import borrowers
    try:
        return dict(borrowers.load(entity_id).get("profile") or {})
    except FileNotFoundError:
        return {}


def _latest_year_key(financials: dict[str, dict]) -> str:
    fiscal_years = sorted(financials.keys(), reverse=True)
    return fiscal_years[0] if fiscal_years else "FY2025"


def _extract_canonical_items(financial_statement: Any) -> dict[str, Any]:
    if financial_statement is None:
        return {}
    if hasattr(financial_statement, "line_items"):
        return dict(financial_statement.line_items or {})
    if isinstance(financial_statement, dict):
        return dict(financial_statement)
    return {}


def _canonical_to_download_financials(financials: dict[str, Any]) -> dict[str, dict[str, float]]:
    mapped: dict[str, dict[str, float]] = {}
    for period, statement in financials.items():
        if not str(period).startswith("FY"):
            continue
        items = _extract_canonical_items(statement)
        current_assets = float(items.get("current_assets", 0) or 0)
        total_assets = float(items.get("total_assets", 0) or 0)
        non_current_assets = float(items.get("non_current_assets", 0) or 0)
        if not non_current_assets and total_assets:
            non_current_assets = max(total_assets - current_assets, 0)
        revenue = float(items.get("revenue_from_operations", items.get("revenue_operating", 0)) or 0)
        other_income = float(items.get("other_income", 0) or 0)
        total_income = float(items.get("total_income", 0) or (revenue + other_income))
        mapped[period] = {
            "period": period,
            "revenue_from_operations": revenue,
            "other_income": other_income,
            "total_income": total_income,
            "employee_benefit_expense": float(items.get("employee_benefit_expense", items.get("employee_cost", 0)) or 0),
            "cost_of_materials": float(items.get("cost_of_materials", items.get("raw_material_cost", 0)) or 0),
            "depreciation_amortisation": float(items.get("depreciation_amortisation", items.get("depreciation", 0)) or 0),
            "finance_cost": float(items.get("finance_cost", 0) or 0),
            "other_expenses": float(items.get("other_expenses", 0) or 0),
            "ebitda": float(items.get("ebitda", 0) or 0),
            "profit_before_tax": float(items.get("profit_before_tax", items.get("pbt", 0)) or 0),
            "tax_expense": float(items.get("tax_expense", 0) or 0),
            "profit_after_tax": float(items.get("profit_after_tax", items.get("pat", 0)) or 0),
            "total_assets": total_assets,
            "total_equity": float(items.get("total_equity", 0) or 0),
            "total_debt": float(items.get("total_debt", 0) or 0),
            "current_assets": current_assets,
            "current_liabilities": float(items.get("current_liabilities", 0) or 0),
            "non_current_assets": non_current_assets,
            "cash_and_equivalents": float(items.get("cash_and_equivalents", items.get("cash_equivalents", 0)) or 0),
            "trade_receivables": float(items.get("trade_receivables", 0) or 0),
            "inventory": float(items.get("inventory", 0) or 0),
            "trade_payables": float(items.get("trade_payables", 0) or 0),
            "total_income_note": "Synthetic financial pack derived from canonical company dataset and aligned to public-company profile.",
        }
    return mapped


def _guess_auditor(company_name: str, sector: str) -> str:
    sector_key = (sector or "").lower()
    if "bank" in sector_key or "nbfc" in sector_key:
        return f"M/s S R Batliboi & Co. LLP, statutory auditors for {company_name}"
    if "pharma" in sector_key or "health" in sector_key:
        return f"M/s Deloitte Haskins & Sells LLP, statutory auditors for {company_name}"
    return f"M/s B S R & Associates LLP, statutory auditors for {company_name}"


def _format_crore(val: float) -> str:
    return f"₹{val:,.0f} Cr"


def _build_generated_highlights(company_record: dict, financials: dict[str, dict]) -> dict[str, dict[str, Any]]:
    borrower = company_record.get("borrower")
    profile_override = _profile(getattr(borrower, "entity_id", "")).get("narrative", {})
    market_signals = company_record.get("market_signals") or []
    latest_year = _latest_year_key(financials)
    latest = financials.get(latest_year, {})
    revenue = float(latest.get("revenue_from_operations", 0) or 0)
    ebitda = float(latest.get("ebitda", 0) or 0)
    pat = float(latest.get("profit_after_tax", 0) or 0)
    total_debt = float(latest.get("total_debt", 0) or 0)
    total_equity = float(latest.get("total_equity", 0) or 0)
    ebitda_margin = (ebitda / revenue * 100) if revenue else 0
    debt_equity = (total_debt / total_equity) if total_equity else 0
    positives = [s for s in market_signals if getattr(s, "sentiment", "").lower() == "positive"]
    negatives = [s for s in market_signals if getattr(s, "sentiment", "").lower() == "negative"]
    key_highlights = [
        f"Revenue from operations: {_format_crore(revenue)}",
        f"EBITDA: {_format_crore(ebitda)} with margin of {ebitda_margin:.1f}%",
        f"Profit after tax: {_format_crore(pat)}",
        f"Debt / Equity: {debt_equity:.2f}x",
    ]
    if borrower and getattr(borrower, "credit_rating", None):
        key_highlights.append(f"External rating profile: {borrower.credit_rating}")
    if borrower and getattr(borrower, "employee_count", None):
        key_highlights.append(f"Employee base: {borrower.employee_count:,}")

    risk_factors = []
    for signal in negatives[:4]:
        risk_factors.append(getattr(signal, "headline", "Market volatility and sector execution risk"))
    if not risk_factors:
        risk_factors = profile_override.get("risk_factors") or [
            "Execution risk on growth capex and sector demand cycles",
            "Working-capital intensity and input-cost volatility",
            "Regulatory and compliance obligations associated with listed entities",
        ]

    chairman_message = profile_override.get("chairman_message") or (
        f"{borrower.company_name if borrower else company_record.get('company_name', 'The company')} delivered a broadly credible operating profile in {latest_year} "
        f"with revenue of {_format_crore(revenue)} and PAT of {_format_crore(pat)}. "
        f"This document set is synthetic, but grounded in the canonical borrower model and aligned with the real-world market profile of the reference company."
    )
    if positives:
        chairman_message += f" Recent positive developments include {getattr(positives[0], 'headline', 'improving business momentum').lower()}."

    mda_summary = profile_override.get("mda_summary") or (
        f"The borrower operates in {getattr(borrower, 'subsector', getattr(borrower, 'sector', 'its sector'))}. "
        f"The synthetic financial pack follows the internal canonical statements while preserving listed-company style disclosures, exchange filing summaries, and market context."
    )
    if positives:
        mda_summary += f" Market backdrop is supported by signals such as {getattr(positives[0], 'headline', '')}."

    return {
        "FY2024": {
            "chairman_message": chairman_message,
            "key_highlights": key_highlights,
            "mda_summary": mda_summary,
            "risk_factors": risk_factors,
        }
    }










def _canonical_directors(company_record: dict) -> list[dict[str, Any]]:
    directors = []
    for director in company_record.get("directors") or []:
        directors.append({
            "name": getattr(director, "name", "Unknown Director"),
            "designation": getattr(director, "designation", "Director"),
            "din": getattr(director, "din", None),
            "is_promoter": getattr(director, "is_promoter", False),
        })
    return directors


def _canonical_collateral(company_record: dict) -> list[dict[str, Any]]:
    collaterals = []
    for item in company_record.get("collateral") or []:
        collaterals.append({
            "type": getattr(item, "collateral_type", "Collateral"),
            "description": getattr(item, "description", ""),
            "market_value_cr": float(getattr(item, "market_value_cr", 0) or 0),
            "forced_sale_value_cr": float(getattr(item, "forced_sale_value_cr", 0) or 0),
            "encumbrance_status": getattr(item, "encumbrance_status", "clear"),
        })
    return collaterals


def _canonical_facility(company_record: dict) -> dict[str, Any]:
    facility = company_record.get("facility")
    if not facility:
        return {}
    return {
        "facility_type": getattr(getattr(facility, "facility_type", None), "value", str(getattr(facility, "facility_type", ""))),
        "case_type": getattr(getattr(facility, "case_type", None), "value", str(getattr(facility, "case_type", ""))),
        "amount_requested_cr": float(getattr(facility, "amount_requested_cr", 0) or 0),
        "purpose": getattr(facility, "purpose", "General corporate purpose"),
        "tenor_months": getattr(facility, "tenor_months", None),
        "proposed_limit_cr": float(getattr(facility, "proposed_limit_cr", 0) or 0),
    }


def _get_canonical_company_record(entity_id: str) -> Optional[dict[str, Any]]:
    """The borrower's record from its data file (None for a borrower without one)."""
    from src.data import borrowers
    try:
        return borrowers.load(entity_id)
    except FileNotFoundError:
        return None


def _enrich_company_data(entity_id: str, company_data: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(company_data)
    canonical = _get_canonical_company_record(entity_id)
    profile = _profile(entity_id)
    borrower = canonical.get("borrower") if canonical else None

    if borrower:
        enriched.setdefault("cin", getattr(borrower, "cin", None))
        enriched.setdefault("pan", getattr(borrower, "pan", None))
        enriched.setdefault("isin", getattr(borrower, "isin", None))
        enriched.setdefault("registered_address", getattr(borrower, "registered_address", None))
        enriched.setdefault("incorporated_date", getattr(getattr(borrower, "date_of_incorporation", None), "strftime", lambda *_: None)("%d-%b-%Y"))
        enriched.setdefault("listed_exchange", getattr(borrower, "listed_exchange", None))
        enriched.setdefault("credit_rating", getattr(borrower, "credit_rating", None))
        enriched.setdefault("rating_agency", getattr(borrower, "rating_agency", None))
        enriched.setdefault("employee_count", getattr(borrower, "employee_count", None))
        enriched.setdefault("website", getattr(borrower, "website", None))
        enriched.setdefault("sector", getattr(borrower, "subsector", None) or getattr(getattr(borrower, "sector", None), "value", None))
        enriched["company_name"] = profile.get("actual_company_name", enriched.get("company_name") or borrower.company_name)
        enriched.setdefault("directors", _canonical_directors(canonical))
        enriched.setdefault("collateral_assets", _canonical_collateral(canonical))
        enriched.setdefault("facility_request", _canonical_facility(canonical))

    if profile.get("bse_code"):
        enriched["bse_code"] = profile["bse_code"]
    if profile.get("auditor"):
        enriched["auditor"] = profile["auditor"]
    return enriched




def _build_company_data_from_registry(entity_id: str) -> Optional[dict[str, Any]]:
    company_record = _get_canonical_company_record(entity_id)
    if not company_record:
        return None

    borrower = company_record.get("borrower")
    if borrower is None or not getattr(borrower, "nse_symbol", None):
        return None

    financials = _canonical_to_download_financials(company_record.get("financials") or {})
    if not financials:
        return None

    alias = _profile(entity_id)
    company_name = alias.get("actual_company_name", borrower.company_name)
    sector_label = getattr(borrower, "subsector", None) or getattr(getattr(borrower, "sector", None), "value", str(getattr(borrower, "sector", "")))
    return _enrich_company_data(entity_id, {
        "company_name": company_name,
        "cin": borrower.cin,
        "bse_code": getattr(borrower, "bse_code", None),
        "nse_symbol": borrower.nse_symbol,
        "isin": getattr(borrower, "isin", None),
        "sector": sector_label,
        "auditor": alias.get("auditor") or _guess_auditor(company_name, sector_label),
        "financials": financials,
        "annual_report_highlights": _build_generated_highlights(company_record, financials),
        "derived_from": "canonical_registry",
        "synthetic_source": {
            "entity_id": entity_id,
            "borrower_name": borrower.company_name,
            "website": getattr(borrower, "website", None),
            "rating": getattr(borrower, "credit_rating", None),
        },
    })


def _get_company_download_config(entity_id: str) -> Optional[dict[str, Any]]:
    return _build_company_data_from_registry(entity_id)


def _generate_simple_profile_pdf(title: str, subtitle: str, paragraphs: list[str], output_file: Path) -> Path:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(output_file), pagesize=A4, topMargin=2 * cm, bottomMargin=1.5 * cm, leftMargin=1.8 * cm, rightMargin=1.8 * cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("DocTitle", parent=styles["Title"], fontSize=17, spaceAfter=8)
    subtitle_style = ParagraphStyle("DocSub", parent=styles["Normal"], fontSize=10, alignment=1, textColor=colors.HexColor("#4a5568"), spaceAfter=10)
    body_style = ParagraphStyle("DocBody", parent=styles["Normal"], fontSize=10, leading=14, spaceAfter=8)

    elements = [Paragraph(title, title_style), Paragraph(subtitle, subtitle_style), HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cbd5e0")), Spacer(1, 0.4 * cm)]
    for paragraph in paragraphs:
        elements.append(Paragraph(paragraph, body_style))
    doc.build(elements)
    return output_file


def _generate_kyc_documents(entity_id: str, company_data: dict[str, Any], output_dir: Path) -> list[str]:
    facility = company_data.get("facility_request", {})
    first_director = (company_data.get("directors") or [{}])[0]
    kyc_dir = output_dir / "kyc"
    files = []
    files.append(str(_generate_simple_profile_pdf(
        company_data["company_name"],
        "Permanent Account Number verification copy",
        [
            f"<b>PAN:</b> {company_data.get('pan', 'N/A')}",
            f"<b>Legal Name:</b> {company_data['company_name']}",
            f"<b>CIN:</b> {company_data.get('cin', 'N/A')}",
            f"<b>Incorporated:</b> {company_data.get('incorporated_date', 'N/A')}",
            "This synthetic KYC artifact is generated for credit workflow testing and mirrors a standard bank-side PAN verification pack.",
        ],
        kyc_dir / "pan_card.pdf",
    ).relative_to(output_dir)))
    files.append(str(_generate_simple_profile_pdf(
        company_data["company_name"],
        "Certificate of incorporation summary",
        [
            f"<b>CIN:</b> {company_data.get('cin', 'N/A')}",
            f"<b>Registered Office:</b> {company_data.get('registered_address', 'N/A')}",
            f"<b>Listed Exchange:</b> {company_data.get('listed_exchange', 'BSE/NSE')}",
            f"<b>Corporate Website:</b> {company_data.get('website', 'N/A')}",
            "This synthetic document condenses key company-registration fields typically verified during onboarding.",
        ],
        kyc_dir / "certificate_of_incorporation.pdf",
    ).relative_to(output_dir)))
    files.append(str(_generate_simple_profile_pdf(
        company_data["company_name"],
        "Board resolution for borrowing powers",
        [
            f"The Board authorizes {first_director.get('name', 'the authorized signatory')} to execute and deliver all credit documents for the proposed {facility.get('facility_type', 'facility')}.",
            f"Requested limit under review: {_format_crore(facility.get('amount_requested_cr', 0) or 0)}.",
            f"Primary purpose stated by management: {facility.get('purpose', 'general corporate purpose')}.",
            "The resolution format is synthetic and intended to mimic a lender-collected authorization record.",
        ],
        kyc_dir / "board_resolution_borrowing.pdf",
    ).relative_to(output_dir)))
    return files




def _generate_collateral_report(entity_id: str, company_data: dict[str, Any], output_dir: Path) -> str:
    collateral_assets = company_data.get("collateral_assets") or []
    paragraphs = []
    if collateral_assets:
        total_mv = sum(item.get("market_value_cr", 0) for item in collateral_assets)
        total_fsv = sum(item.get("forced_sale_value_cr", 0) for item in collateral_assets)
        paragraphs.append(f"Total collateral market value assessed at {_format_crore(total_mv)} with aggregate forced-sale value of {_format_crore(total_fsv)}.")
        for item in collateral_assets[:5]:
            paragraphs.append(
                f"<b>{item.get('type', 'Collateral')}:</b> {item.get('description', '')} | MV {_format_crore(item.get('market_value_cr', 0))} | FSV {_format_crore(item.get('forced_sale_value_cr', 0))} | Encumbrance: {item.get('encumbrance_status', 'clear')}"
            )
    else:
        paragraphs.append("No specific collateral rows were available in the canonical registry; this placeholder valuation note is retained for workflow completeness.")
    return str(_generate_simple_profile_pdf(
        company_data["company_name"],
        "Collateral valuation and security cover note",
        paragraphs,
        output_dir / "collateral" / "valuation_report.pdf",
    ).relative_to(output_dir))


def _generate_request_note(entity_id: str, company_data: dict[str, Any], output_dir: Path) -> str:
    facility = company_data.get("facility_request", {})
    latest_year = _latest_year_key(company_data.get("financials", {}))
    latest = company_data.get("financials", {}).get(latest_year, {})
    narrative = _profile(entity_id).get("narrative", {})
    paragraphs = [
        f"<b>Facility Requested:</b> {facility.get('facility_type', 'Facility')} | <b>Case Type:</b> {facility.get('case_type', 'NTB')}",
        f"<b>Amount Requested:</b> {_format_crore(facility.get('amount_requested_cr', 0) or 0)} | <b>Tenor:</b> {facility.get('tenor_months', 'N/A')} months",
        f"<b>Purpose:</b> {facility.get('purpose') or narrative.get('request_focus', 'general corporate purposes')}",
        f"<b>Latest Financial Snapshot ({latest_year}):</b> Revenue {_format_crore(latest.get('revenue_from_operations', 0))}, EBITDA {_format_crore(latest.get('ebitda', 0))}, PAT {_format_crore(latest.get('profit_after_tax', 0))}, Debt {_format_crore(latest.get('total_debt', 0))}.",
        f"<b>Credit View:</b> {narrative.get('chairman_message', 'Management has represented a stable business trajectory with sector-aligned funding needs.')}",
    ]
    return str(_generate_simple_profile_pdf(
        company_data["company_name"],
        "Management request note for credit facilities",
        paragraphs,
        output_dir / "request" / "request_note.pdf",
    ).relative_to(output_dir))




def _generate_gst_summaries(entity_id: str, company_data: dict[str, Any], output_dir: Path) -> list[str]:
    financials = company_data.get("financials", {})
    latest_year = _latest_year_key(financials)
    latest = financials.get(latest_year, {})
    revenue = float(latest.get("revenue_from_operations", 0) or 0)
    monthly_turnover = revenue / 12 if revenue else 0
    monthly_tax = monthly_turnover * 0.18
    paragraphs_3b = [
        f"Synthetic GST 3B summary prepared for {company_data['company_name']}.",
        f"Estimated monthly taxable turnover anchored to {latest_year} revenue run-rate: {_format_crore(monthly_turnover)}.",
        f"Indicative monthly GST liability at 18%: {_format_crore(monthly_tax)}.",
    ]
    paragraphs_1 = [
        f"Synthetic outward supplies summary for {company_data['company_name']}.",
        f"Average monthly outward taxable supplies estimated at {_format_crore(monthly_turnover)} based on the internal financial pack.",
        f"Primary registration references include PAN {company_data.get('pan', 'N/A')} and CIN {company_data.get('cin', 'N/A')}.",
    ]
    return [
        str(_generate_simple_profile_pdf(company_data["company_name"], "GST 3B filing summary", paragraphs_3b, output_dir / "gst" / "gstr3b_summary.pdf").relative_to(output_dir)),
        str(_generate_simple_profile_pdf(company_data["company_name"], "GST 1 outward supplies summary", paragraphs_1, output_dir / "gst" / "gstr1_summary.pdf").relative_to(output_dir)),
    ]


def _generate_bureau_documents(entity_id: str, company_data: dict[str, Any], output_dir: Path) -> list[str]:
    financials = company_data.get("financials", {})
    latest_year = _latest_year_key(financials)
    latest = financials.get(latest_year, {})
    debt = float(latest.get("total_debt", 0) or 0)
    equity = float(latest.get("total_equity", 0) or 0)
    bureau_paragraphs = [
        f"Synthetic bureau summary prepared for {company_data['company_name']} using canonical leverage and size indicators.",
        f"Latest total debt in {latest_year}: {_format_crore(debt)} against total equity of {_format_crore(equity)}.",
        f"The referenced external rating is {company_data.get('credit_rating', 'not available')}, used as a directional proxy for bureau positioning.",
    ]
    exposure_paragraphs = [
        f"Existing facility detail note for {company_data['company_name']}.",
        "Synthetic bureau output assumes a lender group exposure aligned with requested funding and leverage levels.",
        "This document supports extraction, validation, and CAM drafting workflows where lender-wise exposure detail is expected.",
    ]
    return [
        str(_generate_simple_profile_pdf(company_data["company_name"], "Commercial bureau summary", bureau_paragraphs, output_dir / "bureau" / "commercial_bureau_report.pdf").relative_to(output_dir)),
        str(_generate_simple_profile_pdf(company_data["company_name"], "Existing facility detail note", exposure_paragraphs, output_dir / "banking" / "existing_facility_details.pdf").relative_to(output_dir)),
    ]


def _generate_banking_documents(entity_id: str, company_data: dict[str, Any], output_dir: Path) -> list[str]:
    facility = company_data.get("facility_request", {})
    requested = float(facility.get("amount_requested_cr", 0) or 0)
    latest_year = _latest_year_key(company_data.get("financials", {}))
    latest = company_data.get("financials", {}).get(latest_year, {})
    balance = float(latest.get("cash_and_equivalents", 0) or 0)
    bank_statement_paragraphs = [
        f"Six-month banking summary for {company_data['company_name']} based on synthetic operating run-rate assumptions.",
        f"Indicative closing bank / liquid balance reference from {latest_year}: {_format_crore(balance)}.",
        "Monthly turnover is inferred from the generated financial pack and translated into a simplified conduct-style statement artifact.",
    ]
    sanction_paragraphs = [
        f"Illustrative sanction structure for {_format_crore(requested)} requested by {company_data['company_name']}.",
        f"Facility type: {facility.get('facility_type', 'Facility')} | Tenor: {facility.get('tenor_months', 'N/A')} months.",
        f"Primary purpose: {facility.get('purpose', 'general corporate purpose')}.",
    ]
    return [
        str(_generate_simple_profile_pdf(company_data["company_name"], "Bank statement summary - last 6 months", bank_statement_paragraphs, output_dir / "banking" / "bank_statement_6m.pdf").relative_to(output_dir)),
        str(_generate_simple_profile_pdf(company_data["company_name"], "Illustrative sanction letter summary", sanction_paragraphs, output_dir / "banking" / "sanction_letter.pdf").relative_to(output_dir)),
    ]


def generate_demo_documents(entity_id: str, company_data: dict[str, Any], output_dir: Path) -> list[str]:
    """The non-public documents a bank holds, as labelled demo stand-ins (no rating report or governance report: the
    real rating rationale and annual report are on file)."""
    files = []
    files.extend(_generate_kyc_documents(entity_id, company_data, output_dir))
    files.append(_generate_collateral_report(entity_id, company_data, output_dir))
    files.append(_generate_request_note(entity_id, company_data, output_dir))
    files.extend(_generate_gst_summaries(entity_id, company_data, output_dir))
    files.extend(_generate_bureau_documents(entity_id, company_data, output_dir))
    files.extend(_generate_banking_documents(entity_id, company_data, output_dir))
    return files


def populate_supported_company_documents(force_refresh: bool = False) -> dict[str, Any]:
    storage_root = DOCUMENTS_ROOT
    started_at = datetime.now().isoformat()
    generated: list[dict[str, Any]] = []
    skipped: list[str] = []
    failed: list[dict[str, str]] = []

    for company in get_supported_companies():
        entity_id = company["entity_id"]
        entity_dir = storage_root / entity_id
        required_paths = [
            entity_dir / "financials" / "audited_financial_statements.pdf",
            entity_dir / "kyc" / "pan_card.pdf",
            entity_dir / "ratings" / "credit_rating_report.pdf",
            entity_dir / "collateral" / "valuation_report.pdf",
            entity_dir / "request" / "request_note.pdf",
        ]
        if not force_refresh and all(path.exists() for path in required_paths):
            skipped.append(entity_id)
            continue

        result = download_company_documents(entity_id, force_refresh=force_refresh)
        if result.get("status") == "success":
            generated.append({
                "entity_id": entity_id,
                "files_generated": len(result.get("files_generated", [])),
            })
        else:
            failed.append({"entity_id": entity_id, "message": result.get("message", "unknown error")})

    result = {
        "status": "success" if not failed else "partial",
        "generated": generated,
        "skipped": skipped,
        "failed": failed,
        "total_generated": len(generated),
        "total_skipped": len(skipped),
        "total_failed": len(failed),
    }
    document_operations.record({
        "operation_type": "bulk_company_generation",
        "status": result["status"],
        "started_at": started_at,
        "completed_at": datetime.now().isoformat(),
        "summary": f"Bulk generation: {result['total_generated']} generated, {result['total_skipped']} skipped, {result['total_failed']} failed",
        "details": {
            "generated": generated,
            "skipped": skipped,
            "failed": failed,
            "force_refresh": force_refresh,
        },
    })
    return result

# ─── NSE API Fetcher ──────────────────────────────────────────────────────────



# ─── PDF Generator ────────────────────────────────────────────────────────────

def _fmt_cr(val: float) -> str:
    """Format number in crores with Indian number system."""
    if val >= 100000:
        return f"{val:,.2f}"
    return f"{val:,.2f}"












# ─── Main Download Orchestrator ───────────────────────────────────────────────

def download_company_documents(
    entity_id: str,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Generate the borrower's demo (non-public) documents from its data file: KYC pack, GST returns summary, bureau
    report, bank statement, sanction note, collateral valuation and request note, each labelled synthetic.

    Round 8: it no longer writes financial statements, annual reports, provisional figures or exchange filings (the
    real ones are fetched — config/borrower_documents.yaml), and it makes no network call while a CAM runs.
    """
    company_data = _get_company_download_config(entity_id)
    if not company_data:
        return {"status": "error", "entity_id": entity_id,
                "message": f"No data file for {entity_id} (data/borrowers/{entity_id}.json)"}
    storage_root = DOCUMENTS_ROOT / entity_id
    files = generate_demo_documents(entity_id, company_data, storage_root)
    return {"status": "success", "entity_id": entity_id, "company_name": company_data["company_name"],
            "files_generated": files, "started_at": datetime.now().isoformat()}


def get_supported_companies() -> list[dict]:
    """Return list of companies that support web document download."""
    supported: list[dict[str, Any]] = []
    seen: set[str] = set()
    allowed_ids = set(catalog_company_ids())
    for eid in catalog_company_ids():
        if eid not in allowed_ids:
            continue
        if eid in seen:
            continue
        seen.add(eid)
        data = _get_company_download_config(eid)
        if not data:
            continue
        supported.append({
            "entity_id": eid,
            "company_name": data["company_name"],
            "nse_symbol": data["nse_symbol"],
            "bse_code": data.get("bse_code"),
            "years_available": sorted(data["financials"].keys()),
            "source": "borrower_record",
        })
    return supported


def get_real_financials(entity_id: str) -> Optional[dict]:
    """Get pre-verified real financial data for a company (direct access for fact builder)."""
    data = _get_company_download_config(entity_id)
    if not data:
        return None
    return data["financials"]
