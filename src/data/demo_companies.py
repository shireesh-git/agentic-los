"""
Demo borrower for the Credit Risk Observations capability.

ABC Engineering & Infrastructure Ltd (ABCE001) — NTB, unlisted, infrastructure EPC.

The story: three steady years (FY2023-FY2025) of ~10% growth, a 15% EBITDA
margin, ~80 debtor days, ~25 inventory days, a 1.45x current ratio and
Debt/EBITDA around 2.4x. In FY2026 the company chases growth (+18% revenue)
on fixed-price contracts: input costs squeeze the margin, municipal and state
clients pay late, inventory piles up at stalled sites, and the gap plus a
capex programme is funded with debt. EBITDA still edges up, but operating
cash flow collapses and debt-service metrics breach policy.

Every statement is internally consistent (EBITDA = total income - costs,
PAT = PBT - tax, total assets = equity + long-term debt + current
liabilities, equity rolls forward by PAT - dividends, and cash moves by
OCF + investing + financing). The one deliberate inconsistency is the GST
turnover for FY2026, which is ~12% below the reported revenue — the data
reliability concern (revenue recognised on milestones not yet invoiced).

Expected observations: docs/cam-engine/CREDIT_OBSERVATIONS.md and
tests/fixtures/abce001_expected_observations.json.
"""

from datetime import date

from src.models.canonical_model import (
    Borrower, BorrowerType, CaseType, Collateral, DirectorPromoter, FacilityRequest,
    FacilityType, FinancialStatement, GroupEntity, MarketSignal, RiskSeverity, Sector,
)

ENTITY_ID = "ABCE001"

ABC_ENGG = Borrower(
    entity_id=ENTITY_ID,
    company_name="ABC Engineering & Infrastructure Ltd.",
    cin="U45200MH2009PLC191234",
    pan="AAGCA4321K",
    borrower_type=BorrowerType.UNLISTED,
    sector=Sector.INFRASTRUCTURE,
    subsector="Industrial & Urban Infrastructure EPC",
    date_of_incorporation=date(2009, 6, 18),
    registered_state="Maharashtra",
    registered_address="Plot 14, MIDC Industrial Area, Andheri (East), Mumbai 400093",
    authorized_capital=120.00,
    paid_up_capital=80.00,
    listed_exchange=None,
    credit_rating="CARE BBB+/Negative",
    rating_agency="CARE",
    employee_count=2650,
    website="www.abc-engg-infra.example",
)

ABC_ENGG_GROUP = GroupEntity(
    group_id="GRP_ABCE",
    group_name="ABC Group",
    parent_entity_id=ENTITY_ID,
    entities=[ENTITY_ID, "ABC Precast Structures Pvt Ltd"],
    promoter_holding_pct=72.5,
    institutional_holding_pct=17.5,
    public_holding_pct=10.0,
)

ABC_ENGG_DIRECTORS = [
    DirectorPromoter(din="07112233", name="Arvind B. Chitale", designation="Chairman & Managing Director",
                     entity_id=ENTITY_ID, pan="AAKPC1122D", date_of_appointment=date(2009, 6, 18),
                     other_directorships=["ABC Precast Structures Pvt Ltd"], net_worth_cr=145.0, is_promoter=True),
    DirectorPromoter(din="07112234", name="Bhavna A. Chitale", designation="Whole-time Director",
                     entity_id=ENTITY_ID, pan="AAKPC1123E", date_of_appointment=date(2012, 4, 1),
                     other_directorships=["ABC Precast Structures Pvt Ltd"], net_worth_cr=60.0, is_promoter=True),
    DirectorPromoter(din="08223344", name="Suresh K. Menon", designation="Independent Director",
                     entity_id=ENTITY_ID, pan="AAKPM3344F", date_of_appointment=date(2020, 9, 1),
                     other_directorships=[], net_worth_cr=18.0, is_promoter=False),
]


def _statement(period: str, as_of: date, items: dict) -> FinancialStatement:
    return FinancialStatement(entity_id=ENTITY_ID, period=period, statement_type="standalone",
                              source="audited", as_of_date=as_of, line_items=items)


ABC_ENGG_FINANCIALS = {
    # ── FY2023: steady ───────────────────────────────────────────────
    "FY2023": _statement("FY2023", date(2023, 3, 31), {
        "revenue_operating": 1450.00, "other_income": 8.00, "total_income": 1458.00,
        "raw_material_cost": 899.00, "employee_cost": 145.00, "other_expenses": 196.50,
        "ebitda": 217.50, "depreciation": 45.00, "ebit": 172.50, "finance_cost": 52.00,
        "pbt": 120.50, "tax_expense": 30.13, "pat": 90.37,
        "total_equity": 820.00, "reserves_surplus": 740.00,
        "long_term_debt": 350.00, "short_term_debt": 210.00, "total_debt": 560.00,
        "current_assets": 682.00, "inventory": 100.00, "trade_receivables": 318.00,
        "cash_equivalents": 60.00, "other_current_assets": 204.00,
        "current_liabilities": 470.00, "trade_payables": 200.00, "other_current_liabilities": 60.00,
        "total_assets": 1640.00, "net_fixed_assets": 780.00, "capital_wip": 60.00,
        "intangible_assets": 18.00, "investments": 100.00,
        "operating_cash_flow": 150.00, "investing_cash_flow": -105.00, "financing_cash_flow": -40.00,
        "capex": 95.00, "dividend_paid": 16.00, "contingent_liabilities": 60.00,
    }),
    # ── FY2024: steady ───────────────────────────────────────────────
    "FY2024": _statement("FY2024", date(2024, 3, 31), {
        "revenue_operating": 1600.00, "other_income": 9.00, "total_income": 1609.00,
        "raw_material_cost": 992.00, "employee_cost": 158.00, "other_expenses": 215.80,
        "ebitda": 243.20, "depreciation": 50.00, "ebit": 193.20, "finance_cost": 56.00,
        "pbt": 137.20, "tax_expense": 34.30, "pat": 102.90,
        "total_equity": 905.00, "reserves_surplus": 825.00,
        "long_term_debt": 370.00, "short_term_debt": 230.00, "total_debt": 600.00,
        "current_assets": 748.00, "inventory": 110.00, "trade_receivables": 352.00,
        "cash_equivalents": 65.00, "other_current_assets": 221.00,
        "current_liabilities": 516.00, "trade_payables": 222.00, "other_current_liabilities": 64.00,
        "total_assets": 1791.00, "net_fixed_assets": 840.00, "capital_wip": 75.00,
        "intangible_assets": 18.00, "investments": 110.00,
        "operating_cash_flow": 170.00, "investing_cash_flow": -131.00, "financing_cash_flow": -34.00,
        "capex": 121.00, "dividend_paid": 17.90, "contingent_liabilities": 65.00,
    }),
    # ── FY2025: steady (the base year for the FY2026 comparison) ───────
    "FY2025": _statement("FY2025", date(2025, 3, 31), {
        "revenue_operating": 1760.00, "other_income": 10.00, "total_income": 1770.00,
        "raw_material_cost": 1091.20, "employee_cost": 172.00, "other_expenses": 242.80,
        "ebitda": 264.00, "depreciation": 55.00, "ebit": 209.00, "finance_cost": 60.00,
        "pbt": 149.00, "tax_expense": 37.25, "pat": 111.75,
        "total_equity": 998.00, "reserves_surplus": 918.00,
        "long_term_debt": 380.00, "short_term_debt": 260.00, "total_debt": 640.00,
        "current_assets": 829.00, "inventory": 121.00, "trade_receivables": 386.00,
        "cash_equivalents": 70.00, "other_current_assets": 252.00,
        "current_liabilities": 572.00, "trade_payables": 244.00, "other_current_liabilities": 68.00,
        "total_assets": 1950.00, "net_fixed_assets": 900.00, "capital_wip": 85.00,
        "intangible_assets": 20.00, "investments": 116.00,
        "operating_cash_flow": 190.00, "investing_cash_flow": -146.00, "financing_cash_flow": -39.00,
        "capex": 140.00, "dividend_paid": 18.75, "contingent_liabilities": 70.00,
    }),
    # ── FY2026: growth on fixed-price contracts, funded with debt ──────
    "FY2026": _statement("FY2026", date(2026, 3, 31), {
        "revenue_operating": 2080.00, "other_income": 12.00, "total_income": 2092.00,
        "raw_material_cost": 1352.00, "employee_cost": 198.00, "other_expenses": 274.00,
        "ebitda": 268.00, "depreciation": 62.00, "ebit": 206.00, "finance_cost": 88.00,
        "pbt": 118.00, "tax_expense": 29.50, "pat": 88.50,
        "total_equity": 1070.00, "reserves_surplus": 990.00,
        "long_term_debt": 560.00, "short_term_debt": 540.00, "total_debt": 1100.00,
        "current_assets": 1020.00, "inventory": 245.00, "trade_receivables": 587.00,
        "cash_equivalents": 38.00, "other_current_assets": 150.00,
        "current_liabilities": 890.00, "trade_payables": 270.00, "other_current_liabilities": 80.00,
        "total_assets": 2520.00, "net_fixed_assets": 1080.00, "capital_wip": 260.00,
        "intangible_assets": 20.00, "investments": 140.00,
        "operating_cash_flow": 45.00, "investing_cash_flow": -432.00, "financing_cash_flow": 355.00,
        "capex": 410.00, "dividend_paid": 16.50, "contingent_liabilities": 140.00,
    }),
}

# Management estimate for FY2027 (H1 actuals annualised) — the trend continues.
ABC_ENGG_PROVISIONAL = FinancialStatement(
    entity_id=ENTITY_ID, period="FY2027_P", statement_type="standalone",
    source="provisional", as_of_date=date(2026, 9, 30),
    line_items={
        "revenue_operating": 2300.00,
        "ebitda": 285.00,
        "pat": 80.00,
        "total_debt": 1180.00,
        "total_equity": 1130.00,
    },
)

ABC_ENGG_FACILITY = FacilityRequest(
    facility_id="FAC_ABCE_001",
    entity_id=ENTITY_ID,
    case_type=CaseType.NTB,
    facility_type=FacilityType.WORKING_CAPITAL,
    amount_requested_cr=250.00,
    purpose="Fund-based working capital (cash credit) to support execution of the "
            "municipal water-supply and industrial-park EPC order book.",
    tenor_months=12,
    collateral_type="Hypothecation of current assets + equitable mortgage of Pune factory",
    collateral_value_cr=410.00,
    proposed_limit_cr=250.00,
)

ABC_ENGG_COLLATERAL = [
    Collateral(collateral_id="COL_ABCE_001", entity_id=ENTITY_ID, collateral_type="Current Assets",
               description="First pari-passu hypothecation charge on stock and book debts",
               market_value_cr=260.00, forced_sale_value_cr=182.00,
               valuation_date=date(2026, 6, 30), encumbrance_status="pari-passu"),
    Collateral(collateral_id="COL_ABCE_002", entity_id=ENTITY_ID, collateral_type="Land & Building",
               description="Factory land and building, Chakan, Pune (12 acres)",
               market_value_cr=150.00, forced_sale_value_cr=112.50,
               valuation_date=date(2026, 6, 30), encumbrance_status="clear"),
]

ABC_ENGG_MARKET_SIGNALS = [
    MarketSignal(entity_id=ENTITY_ID, signal_type="news",
                 headline="ABC Engineering wins Rs 640 Cr industrial-park EPC order",
                 sentiment="positive", severity=RiskSeverity.LOW, source_name="Economic Times",
                 signal_date=date(2026, 5, 12),
                 details="Order book now about 2.1x FY2026 revenue."),
    MarketSignal(entity_id=ENTITY_ID, signal_type="news",
                 headline="CARE revises ABC Engineering outlook to Negative on stretched working capital",
                 sentiment="negative", severity=RiskSeverity.MEDIUM, source_name="CARE Ratings",
                 signal_date=date(2026, 7, 28),
                 details="Delayed payments from municipal clients; rising reliance on short-term debt."),
]

# Cached public-record bundle (the ingestion agent reads company_data["external_data"]).
ABC_ENGG_EXTERNAL_DATA = {
    "mca_data": {
        "source": "mca", "record_type": "COMPANY_MASTER", "entity_key": ABC_ENGG.cin,
        "source_status": "valid",
        "payload": {"company_name": ABC_ENGG.company_name, "status": "Active",
                    "date_of_incorporation": "2009-06-18", "paid_up_capital_cr": 80.0},
    },
    "bureau_data": {
        "source": "bureau_commercial", "record_type": "COMMERCIAL_BUREAU_REPORT",
        "entity_key": ABC_ENGG.pan, "source_status": "valid",
        "payload": {"entity_name": ABC_ENGG.company_name, "credit_score": 712, "score_band": "B",
                    "total_exposure_cr": 1065.0, "total_lenders": 5, "dpd_status": "Standard",
                    "max_dpd_last_12m": 0, "worst_status_12m": "Standard", "suit_filed_amount_cr": 0.0,
                    "wilful_defaulter": False, "enquiries_last_6m": 7},
    },
    "gst_data": {
        "source": "gst", "record_type": "GST_TURNOVER", "entity_key": "27AAGCA4321K1Z5",
        "source_status": "valid",
        "payload": {"gstin": "27AAGCA4321K1Z5", "filing_status": "Regular",
                    "aggregate_turnover_fy2024_cr": 1585.0, "aggregate_turnover_fy2025_cr": 1742.0,
                    # Deliberate conflict: ~11.8% below FY2026 reported revenue of 2,080 Cr.
                    "aggregate_turnover_fy2026_cr": 1835.0},
    },
    "market_data": {
        "source": "market", "record_type": "MARKET_INTELLIGENCE", "entity_key": ENTITY_ID,
        "source_status": "valid",
        "payload": {"overall_sentiment": "mixed", "reputation_risk_score": "medium"},
    },
    "rating_data": {},
}

DEMO_COMPANIES = {
    ENTITY_ID: {
        "borrower": ABC_ENGG,
        "group": ABC_ENGG_GROUP,
        "directors": ABC_ENGG_DIRECTORS,
        "financials": ABC_ENGG_FINANCIALS,
        "provisional": ABC_ENGG_PROVISIONAL,
        "facility": ABC_ENGG_FACILITY,
        "collateral": ABC_ENGG_COLLATERAL,
        "market_signals": ABC_ENGG_MARKET_SIGNALS,
        "existing_exposure": [],
        "conduct": [],
        "covenants": [],
        "exchange_filing": None,
        "core_banking": {},
        "external_data": ABC_ENGG_EXTERNAL_DATA,
        "data_provider": "synthetic_demo",
        # Intentional synthetic demo data: the borrower's document checklist (no files on disk).
        "declared_documents": {"has_kyc": True, "has_board_resolution": True, "has_collateral_docs": True},
        "catalog_source": "demo_catalog",
        "preferred_identifier": ABC_ENGG.company_name,
        "reference_prefix": None,
    },
}
