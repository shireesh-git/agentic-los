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

import copy as _copy

from src.models.canonical_model import (
    Borrower, BorrowerType, CaseType, Collateral, ConductRecord, DirectorPromoter, FacilityRequest,
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


# ═══════════════════════════════════════════════════════════════════════════════
# Fictional demo borrowers for the demo institution profiles (DFI / corporate /
# MSME). Deliberately invented names, CINs and PANs — clearly not real customers.
# Seeded applications under each profile (see config/institution_profiles/*.yaml)
# are replayed to a deterministic stage; they do not need financial statements.
# ═══════════════════════════════════════════════════════════════════════════════

def _fictional_borrower(entity_id, name, cin, pan, sector, subsector, state, address,
                        inc_year, rating=None, listed=False, exchange=None):
    return Borrower(
        entity_id=entity_id, company_name=name, cin=cin, pan=pan,
        borrower_type=BorrowerType.UNLISTED if not listed else BorrowerType.LISTED,
        sector=sector, subsector=subsector,
        date_of_incorporation=date(inc_year, 3, 15),
        registered_state=state, registered_address=address,
        authorized_capital=50.0, paid_up_capital=40.0,
        listed_exchange=exchange, credit_rating=rating,
        rating_agency=rating.split()[0] if rating else None,
        employee_count=120, website=f"www.{name.split()[0].lower()}.example",
    )


def _fictional_facility(entity_id, fac_id, ftype, amount, tenor, purpose, coll_type, coll_value):
    return FacilityRequest(
        facility_id=fac_id, entity_id=entity_id, case_type=CaseType.NTB,
        facility_type=ftype, amount_requested_cr=amount, purpose=purpose,
        tenor_months=tenor, collateral_type=coll_type, collateral_value_cr=coll_value,
        proposed_limit_cr=amount,
    )


KAVG = _fictional_borrower(
    "KAVG001", "Kaveri Greenways Energy LLP", "U40101KA2021OPC987654", "AAJCK8871Q",
    Sector.ENERGY, "Utility-scale solar EPC & operations", "Karnataka",
    "Office 21, Level 4, Green Corridor Business Park, Whitefield, Bengaluru 560066", 2021,
    rating=None)
SAPT = _fictional_borrower(
    "SAPT001", "Saptagiri Transit Infrastructure Ltd", "U45200TN2018PLC445566", "AAACS2210B",
    Sector.INFRASTRUCTURE, "Urban transit & highway concessions", "Tamil Nadu",
    "Saptagiri House, 14 Perambur Road, Chennai 600011", 2018, rating="CARE BB+/Stable")
BLUE = _fictional_borrower(
    "BLUE001", "BlueOrchid Polymers Ltd", "U29309GJ1999PLC012345", "AAACB5598F",
    Sector.MANUFACTURING, "Specialty polymers & resins", "Gujarat",
    "Plot 7, GIDC Dahej Industrial Estate, Vadodara 391110", 1999, rating="CRISIL BBB/Positive")
DECC = _fictional_borrower(
    "DECC001", "Deccan Agro Foods Ltd", "U10203MH2004PLC556677", "AAACD3324M",
    Sector.MANUFACTURING, "Processed foods & agri supply chain", "Maharashtra",
    "Deccan House, Bhandup (West), Mumbai 400078", 2004, rating="ICRA BBB-/Negative")
KARI = _fictional_borrower(
    "KARI001", "Karigari Textiles Pvt Ltd", "U13100KL2011PTC889900", "AABCK7765P",
    Sector.MANUFACTURING, "Apparel processing & export", "Kerala",
    "Karigari House, Kalamassery Industrial Area, Ernakulam 682007", 2011)
NIRM = _fictional_borrower(
    "NIRM001", "Nirmal Packaging Works", "U23200UP2008PTC112233", "AAJCN4432T",
    Sector.MANUFACTURING, "Corrugated packaging", "Uttar Pradesh",
    "Nirmal House, Ghaziabad Industrial Estate, Greater Noida 201306", 2008)

def _conduct(entity_id, period, overdue=0, cheques=0, max_days=0, dpd90=0):
    return ConductRecord(entity_id=entity_id, period=period, avg_bank_balance_cr=12.0,
                         credit_turnover_cr=96.0, debit_turnover_cr=94.0,
                         cheque_returns=cheques, limit_utilization_pct=62.0,
                         overdue_instances=overdue, max_overdue_days=max_days, dpd_90_count=dpd90)



def _fictional_financials(entity_id, revenue0, growth, margin0, margin_step, debt0, debt_step,
                          equity0, div_pct=0.10, dep_pct=0.035):
    """Three-plus-one years of internally consistent standalone statements (in ₹ Cr).

    Identities held every year: total income = revenue + other income; EBITDA = total income -
    costs; PBT = EBIT - finance cost; PAT = PBT - tax; equity rolls by PAT - dividend; total
    assets = equity + long-term debt + current liabilities; cash rolls by the three cash flows.
    """
    out = {}
    equity = equity0
    cash = 0.12 * revenue0
    nfa = 0.9 * revenue0
    for i, (year, asof) in enumerate(((2023, (2023, 3, 31)), (2024, (2024, 3, 31)),
                                      (2025, (2025, 3, 31)), (2026, (2026, 3, 31)))):
        rev = round(revenue0 * (1 + growth) ** i, 1)
        margin = margin0 + margin_step * i
        other = round(rev * 0.005, 1)
        tin = round(rev + other, 1)
        costs = round(tin * (1 - margin), 1)
        ebitda = round(tin - costs, 1)
        raw = round(costs * 0.62, 1)
        emp = round(costs * 0.18, 1)
        oth_exp = round(costs - raw - emp, 1)
        dep = round(nfa * dep_pct, 1)
        ebit = round(ebitda - dep, 1)
        ltd = debt0 + debt_step * i
        std = round(ltd * 0.35, 1)
        fc = round((ltd + std) * 0.09, 1)
        pbt = round(ebit - fc, 1)
        tax = round(pbt * 0.25, 1) if pbt > 0 else 0.0
        pat = round(pbt - tax, 1)
        dividend = round(pat * div_pct, 1) if i > 0 else 0.0
        if i > 0:
            equity = round(equity + pat_prev - dividend_prev, 1)
        prev_equity = equity0 if i == 0 else equity - pat + dividend
        rece = round(tin * 0.24, 1)
        inv = round(tin * 0.16, 1)
        oca = round(tin * 0.04, 1)
        ca = round(rece + inv + cash + oca, 1)
        tpay = round(tin * 0.20, 1)
        ocl = round(tin * 0.12, 1)
        cl = round(tpay + ocl, 1)
        capex = round(rev * 0.07, 1)
        nfa = round(nfa + capex - dep, 1)
        cwip = round(rev * 0.03, 1)
        integ = round(rev * 0.008, 1)
        invst = round(equity * 0.06, 1)
        ta = round(equity + ltd + cl, 1)
        ocf = round(ebitda + dep - (tax + fc * 0.2) - (rece if i == 0 else 0), 1)
        icf = round(-capex - cwip, 1)
        fcf = round(dividend + (std if i == 0 else 0) - ocf - icf, 1)
        cash = round(cash + ocf + icf + fcf, 1)
        if cash < 1:
            cash = 1.0
        items = {
            "revenue_operating": rev, "other_income": other, "total_income": tin,
            "raw_material_cost": raw, "employee_cost": emp, "other_expenses": oth_exp,
            "ebitda": ebitda, "depreciation": dep, "ebit": ebit, "finance_cost": fc,
            "pbt": pbt, "tax_expense": tax, "pat": pat,
            "total_equity": equity, "reserves_surplus": round(equity - 0.05 * equity0, 1),
            "long_term_debt": ltd, "short_term_debt": std, "total_debt": round(ltd + std, 1),
            "current_assets": ca, "inventory": inv, "trade_receivables": rece,
            "cash_equivalents": cash, "other_current_assets": oca,
            "current_liabilities": cl, "trade_payables": tpay, "other_current_liabilities": ocl,
            "total_assets": ta, "net_fixed_assets": nfa, "capital_wip": cwip,
            "intangible_assets": integ, "investments": invst,
            "operating_cash_flow": ocf, "investing_cash_flow": icf, "financing_cash_flow": fcf,
            "capex": capex, "dividend_paid": dividend, "contingent_liabilities": round(rev * 0.02, 1),
        }
        out[f"FY{year}"] = _statement(f"FY{year}", date(*asof), items)
        pat_prev, dividend_prev = pat, dividend
    return out


PROFILE_DEMO_COMPANIES = {
    "KAVG001": {"borrower": KAVG, "facility": _fictional_facility(
        "KAVG001", "FAC_KAVG_001", FacilityType.PROJECT_FINANCE, 650.0, 96,
        "Project finance for a 300 MW utility-scale solar plant (Karnataka): debt component "
        "against the project's cash flows, land and PPA receivables.", "Project assets, land & PPA receivables", 980.0),
        "financials": _fictional_financials("KAVG001", 180.0, 0.28, 0.20, 0.01, 90.0, 60.0, 220.0),
        "collateral": [], "market_signals": [], "existing_exposure": [],
        "conduct": [_conduct("KAVG001", "H1-FY26"), _conduct("KAVG001", "H2-FY26")],
        "group": None, "directors": [], "provisional": None,
        "data_provider": "fictional_demo"},
    "SAPT001": {"borrower": SAPT, "facility": _fictional_facility(
        "SAPT001", "FAC_SAPT_001", FacilityType.TERM_LOAN, 120.0, 60,
        "Term loan for the Chennai suburban shuttle-rail rolling stock (units 1-40). "
        "Note: promoter-group fund movement under regulatory review — enhanced due diligence required.",
        "Hypothecation of rolling stock + guarantees", 140.0),
        "financials": _fictional_financials("SAPT001", 260.0, 0.12, 0.15, 0.0, 120.0, 25.0, 310.0),
        "collateral": [], "market_signals": [], "existing_exposure": [],
        "conduct": [_conduct("SAPT001", "H1-FY26"), _conduct("SAPT001", "H2-FY26")],
        "group": None, "directors": [], "provisional": None,
        "data_provider": "fictional_demo"},
    "BLUE001": {"borrower": BLUE, "facility": _fictional_facility(
        "BLUE001", "FAC_BLUE_001", FacilityType.WORKING_CAPITAL, 90.0, 12,
        "Cash credit limit against stock and book debts to fund polymer resin production.",
        "Hypothecation of current assets", 150.0),
        "financials": _fictional_financials("BLUE001", 940.0, 0.09, 0.19, 0.0, 420.0, 30.0, 860.0),
        "collateral": [], "market_signals": [], "existing_exposure": [],
        "conduct": [_conduct("BLUE001", "H1-FY26"), _conduct("BLUE001", "H2-FY26")],
        "group": None, "directors": [], "provisional": None,
        "data_provider": "fictional_demo"},
    "DECC001": {"borrower": DECC, "facility": _fictional_facility(
        "DECC001", "FAC_DECC_001", FacilityType.TERM_LOAN, 240.0, 84,
        "Term loan for a new processing plant and working-capital bridge during commissioning. "
        "Rating outlook Negative; monitor input-cost inflation.",
        "Mortgage of plant land & building + hypothecation of plant", 300.0),
        "financials": _fictional_financials("DECC001", 1350.0, 0.07, 0.16, -0.02, 640.0, 90.0, 1150.0),
        "collateral": [], "market_signals": [], "existing_exposure": [],
        "conduct": [_conduct("DECC001", "H1-FY26"), _conduct("DECC001", "H2-FY26")],
        "group": None, "directors": [], "provisional": None,
        "data_provider": "fictional_demo"},
    "KARI001": {"borrower": KARI, "facility": _fictional_facility(
        "KARI001", "FAC_KARI_001", FacilityType.TERM_LOAN, 12.0, 36,
        "MSME term loan for capacity expansion (two additional sewing lines).",
        "Hypothecation of machinery", 20.0),
        "financials": _fictional_financials("KARI001", 55.0, 0.14, 0.17, 0.0, 18.0, 4.0, 42.0),
        "collateral": [], "market_signals": [], "existing_exposure": [],
        "conduct": [_conduct("KARI001", "H1-FY26"), _conduct("KARI001", "H2-FY26")],
        "group": None, "directors": [], "provisional": None,
        "data_provider": "fictional_demo"},
    "NIRM001": {"borrower": NIRM, "facility": _fictional_facility(
        "NIRM001", "FAC_NIRM_001", FacilityType.WORKING_CAPITAL, 38.0, 12,
        "MSME working-capital limit for a large order book (corporate gifting season). "
        "Note: GST filings for two months pending — collection risk flagged.",
        "Hypothecation of current assets", 60.0),
        "financials": _fictional_financials("NIRM001", 150.0, 0.10, 0.13, -0.01, 70.0, 12.0, 95.0),
        "collateral": [], "market_signals": [], "existing_exposure": [],
        # The exception story: two months of conduct trouble behind the pending GST filings.
        "conduct": [_conduct("NIRM001", "H1-FY26"),
                    _conduct("NIRM001", "H2-FY26", overdue=3, cheques=2, max_days=21)],
        "group": None, "directors": [], "provisional": None,
        "data_provider": "fictional_demo"},
}

DEMO_COMPANIES.update(_copy.deepcopy(PROFILE_DEMO_COMPANIES))
