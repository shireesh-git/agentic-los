"""
Synthetic Data: 4 Test Companies for End-to-End CAM Pipeline Testing

Company 1: Bharat Manufacturing Ltd — NTB, Listed, Manufacturing (CLEAN)
Company 2: Pinnacle Infra Projects Ltd — NTB, Listed, Infrastructure (STRESSED)
Company 3: Sunrise Pharma Pvt Ltd — NTB, Unlisted, Pharma (GROUP RISK)
Company 4: Omega Logistics Pvt Ltd — ETB, Unlisted, Logistics (CONDUCT ISSUES)
"""

from datetime import date
from src.models.canonical_model import (
    Borrower, GroupEntity, DirectorPromoter, FinancialStatement,
    FacilityRequest, ExistingExposure, Collateral, MarketSignal,
    ConductRecord, CovenantRecord, CaseType, BorrowerType,
    FacilityType, Sector, RiskSeverity,
)


# ═══════════════════════════════════════════════════════════════════════════════
# COMPANY 1: BHARAT MANUFACTURING LTD (NTB, Listed, Manufacturing — CLEAN)
# ═══════════════════════════════════════════════════════════════════════════════

BHARAT_MFG = Borrower(
    entity_id="BMFG001",
    company_name="Bharat Manufacturing Ltd",
    cin="L29100MH2008PLC185432",
    pan="AABCB1234F",
    borrower_type=BorrowerType.LISTED,
    sector=Sector.MANUFACTURING,
    subsector="Auto Components",
    date_of_incorporation=date(2009, 4, 15),
    registered_state="Maharashtra",
    registered_address="Plot 45, MIDC Industrial Area, Pune, Maharashtra 411018",
    authorized_capital=100.00,
    paid_up_capital=62.50,
    listed_exchange="NSE",
    nse_symbol="BHARATMFG",
    isin="INE987A01023",
    credit_rating="CRISIL A+/Stable",
    rating_agency="CRISIL",
    employee_count=2850,
    website="www.bharatmanufacturing.com",
)

BHARAT_MFG_GROUP = GroupEntity(
    group_id="GRP_BMFG",
    group_name="Bharat Group",
    parent_entity_id="BMFG001",
    entities=["BMFG001", "Bharat Auto Parts Pvt Ltd", "Bharat Tooling Pvt Ltd"],
    promoter_holding_pct=52.3,
    institutional_holding_pct=28.7,
    public_holding_pct=19.0,
)

BHARAT_MFG_DIRECTORS = [
    DirectorPromoter(din="00112233", name="Rajesh K. Mehta", designation="Chairman & MD",
                     entity_id="BMFG001", pan="AABPM1234A",
                     date_of_appointment=date(2009, 4, 15),
                     other_directorships=["Bharat Auto Parts Pvt Ltd"],
                     net_worth_cr=185.0, is_promoter=True),
    DirectorPromoter(din="00112234", name="Sunita R. Mehta", designation="Whole-time Director",
                     entity_id="BMFG001", pan="AABPM1235B",
                     date_of_appointment=date(2011, 7, 1),
                     other_directorships=["Bharat Tooling Pvt Ltd"],
                     net_worth_cr=95.0, is_promoter=True),
    DirectorPromoter(din="00112235", name="Amit Deshmukh", designation="Independent Director",
                     entity_id="BMFG001", pan="AABPD1236C",
                     date_of_appointment=date(2019, 9, 15),
                     other_directorships=["HDFC Securities Ltd", "L&T Infra Ltd"],
                     net_worth_cr=45.0, is_promoter=False),
    DirectorPromoter(din="00112236", name="Kavita Sharma", designation="CFO",
                     entity_id="BMFG001", pan="AASKS1237D",
                     date_of_appointment=date(2020, 3, 1),
                     other_directorships=[],
                     net_worth_cr=12.0, is_promoter=False),
]

# 3 years audited financials (FY2024, FY2023, FY2022)
BHARAT_MFG_FINANCIALS = {
    "FY2025": FinancialStatement(
        entity_id="BMFG001", period="FY2025", statement_type="standalone",
        source="audited", as_of_date=date(2025, 3, 31),
        line_items={
            "revenue_operating": 1850.00,
            "other_income": 22.50,
            "total_income": 1872.50,
            "raw_material_cost": 1017.50,
            "employee_cost": 185.00,
            "other_expenses": 222.00,
            "ebitda": 448.00,
            "depreciation": 92.50,
            "ebit": 355.50,
            "finance_cost": 67.00,
            "pbt": 288.50,
            "tax_expense": 72.13,
            "pat": 216.37,
            "total_equity": 685.00,
            "reserves_surplus": 622.50,
            "long_term_debt": 425.00,
            "short_term_debt": 280.00,
            "total_debt": 705.00,
            "current_assets": 620.00,
            "inventory": 195.00,
            "trade_receivables": 285.00,
            "cash_equivalents": 45.00,
            "other_current_assets": 95.00,
            "current_liabilities": 385.00,
            "trade_payables": 210.00,
            "other_current_liabilities": 175.00,
            "total_assets": 1710.00,
            "net_fixed_assets": 685.00,
            "capital_wip": 55.00,
            "intangible_assets": 12.00,
            "investments": 38.00,
            "operating_cash_flow": 325.00,
            "investing_cash_flow": -145.00,
            "financing_cash_flow": -165.00,
            "capex": 135.00,
            "dividend_paid": 37.50,
            "contingent_liabilities": 28.50,
        }
    ),
    "FY2024": FinancialStatement(
        entity_id="BMFG001", period="FY2024", statement_type="standalone",
        source="audited", as_of_date=date(2024, 3, 31),
        line_items={
            "revenue_operating": 1620.00,
            "other_income": 18.50,
            "total_income": 1638.50,
            "raw_material_cost": 891.00,
            "employee_cost": 162.00,
            "other_expenses": 194.40,
            "ebitda": 391.10,
            "depreciation": 82.00,
            "ebit": 309.10,
            "finance_cost": 62.00,
            "pbt": 247.10,
            "tax_expense": 61.78,
            "pat": 185.32,
            "total_equity": 580.00,
            "reserves_surplus": 517.50,
            "long_term_debt": 380.00,
            "short_term_debt": 250.00,
            "total_debt": 630.00,
            "current_assets": 545.00,
            "inventory": 170.00,
            "trade_receivables": 245.00,
            "cash_equivalents": 40.00,
            "other_current_assets": 90.00,
            "current_liabilities": 340.00,
            "trade_payables": 185.00,
            "other_current_liabilities": 155.00,
            "total_assets": 1530.00,
            "net_fixed_assets": 620.00,
            "capital_wip": 35.00,
            "intangible_assets": 10.00,
            "investments": 30.00,
            "operating_cash_flow": 285.00,
            "investing_cash_flow": -95.00,
            "financing_cash_flow": -175.00,
            "capex": 88.00,
            "dividend_paid": 31.25,
            "contingent_liabilities": 22.00,
        }
    ),
    "FY2023": FinancialStatement(
        entity_id="BMFG001", period="FY2023", statement_type="standalone",
        source="audited", as_of_date=date(2023, 3, 31),
        line_items={
            "revenue_operating": 1380.00,
            "other_income": 15.00,
            "total_income": 1395.00,
            "raw_material_cost": 759.00,
            "employee_cost": 138.00,
            "other_expenses": 165.60,
            "ebitda": 332.40,
            "depreciation": 72.00,
            "ebit": 260.40,
            "finance_cost": 58.00,
            "pbt": 202.40,
            "tax_expense": 50.60,
            "pat": 151.80,
            "total_equity": 480.00,
            "reserves_surplus": 417.50,
            "long_term_debt": 350.00,
            "short_term_debt": 220.00,
            "total_debt": 570.00,
            "current_assets": 465.00,
            "inventory": 148.00,
            "trade_receivables": 205.00,
            "cash_equivalents": 32.00,
            "other_current_assets": 80.00,
            "current_liabilities": 295.00,
            "trade_payables": 165.00,
            "other_current_liabilities": 130.00,
            "total_assets": 1325.00,
            "net_fixed_assets": 540.00,
            "capital_wip": 25.00,
            "intangible_assets": 8.00,
            "investments": 22.00,
            "operating_cash_flow": 245.00,
            "investing_cash_flow": -78.00,
            "financing_cash_flow": -155.00,
            "capex": 72.00,
            "dividend_paid": 25.00,
            "contingent_liabilities": 18.00,
        }
    ),
}

# Provisional FY2025 (matches audited trend — CLEAN scenario)
BHARAT_MFG_PROVISIONAL = FinancialStatement(
    entity_id="BMFG001", period="FY2026_P", statement_type="standalone",
    source="provisional", as_of_date=date(2026, 12, 31),
    line_items={
        "revenue_operating": 2050.00,
        "ebitda": 502.25,
        "pat": 248.50,
        "total_debt": 680.00,
        "total_equity": 780.00,
    }
)

BHARAT_MFG_FACILITY = FacilityRequest(
    facility_id="FAC_BMFG_001",
    entity_id="BMFG001",
    case_type=CaseType.NTB,
    facility_type=FacilityType.WORKING_CAPITAL,
    amount_requested_cr=150.00,
    purpose="Working capital for capacity expansion in auto-component manufacturing. "
            "New plant at Chakan, Pune — production ramp-up expected H2 FY2026.",
    tenor_months=12,
    collateral_type="Plant & Machinery + Inventory",
    collateral_value_cr=220.00,
    proposed_limit_cr=150.00,
)

BHARAT_MFG_COLLATERAL = [
    Collateral(
        collateral_id="COL_BMFG_001", entity_id="BMFG001",
        collateral_type="Plant & Machinery",
        description="CNC machines and assembly line at MIDC Pune — 12 machines",
        market_value_cr=165.00, forced_sale_value_cr=115.50,
        valuation_date=date(2026, 11, 15), encumbrance_status="clear"
    ),
    Collateral(
        collateral_id="COL_BMFG_002", entity_id="BMFG001",
        collateral_type="Inventory",
        description="Raw material and finished goods inventory — auto components",
        market_value_cr=55.00, forced_sale_value_cr=33.00,
        valuation_date=date(2027, 1, 10), encumbrance_status="clear"
    ),
]

BHARAT_MFG_MARKET_SIGNALS = [
    MarketSignal(entity_id="BMFG001", signal_type="news", headline="Bharat Manufacturing wins Rs 400 Cr order from Tata Motors",
                 sentiment="positive", severity=RiskSeverity.LOW, source_name="Economic Times",
                 signal_date=date(2026, 12, 5), details="Multi-year supply agreement for EV components."),
    MarketSignal(entity_id="BMFG001", signal_type="analyst", headline="CRISIL reaffirms A+/Stable for Bharat Manufacturing",
                 sentiment="positive", severity=RiskSeverity.LOW, source_name="CRISIL",
                 signal_date=date(2026, 10, 20), details="Stable outlook driven by improving order book and margin expansion."),
]


# ═══════════════════════════════════════════════════════════════════════════════
# COMPANY 2: PINNACLE INFRA PROJECTS LTD (NTB, Listed, Infra — STRESSED)
# ═══════════════════════════════════════════════════════════════════════════════

PINNACLE_INFRA = Borrower(
    entity_id="PINF001",
    company_name="Pinnacle Infra Projects Ltd",
    cin="L45200DL2005PLC134567",
    pan="AABCP5678G",
    borrower_type=BorrowerType.LISTED,
    sector=Sector.INFRASTRUCTURE,
    subsector="Roads & Highways EPC",
    date_of_incorporation=date(2006, 8, 22),
    registered_state="Delhi",
    registered_address="502, Nehru Place, New Delhi 110019",
    authorized_capital=200.00,
    paid_up_capital=125.00,
    listed_exchange="NSE",
    nse_symbol="PINNACLEINFRA",
    isin="INE456B01034",
    credit_rating="ICRA BBB-/Watch Negative",
    rating_agency="ICRA",
    employee_count=4200,
    website="www.pinnacleinfra.com",
)

PINNACLE_INFRA_GROUP = GroupEntity(
    group_id="GRP_PINF",
    group_name="Pinnacle Group",
    parent_entity_id="PINF001",
    entities=["PINF001", "Pinnacle Realty Pvt Ltd", "Pinnacle Equipment Leasing Pvt Ltd"],
    promoter_holding_pct=44.8,
    institutional_holding_pct=18.2,
    public_holding_pct=37.0,
)

PINNACLE_INFRA_DIRECTORS = [
    DirectorPromoter(din="00223344", name="Vikram Singh Rathore", designation="Chairman & MD",
                     entity_id="PINF001", pan="AABPV2345B",
                     date_of_appointment=date(2006, 8, 22),
                     other_directorships=["Pinnacle Realty Pvt Ltd", "Pinnacle Equipment Leasing Pvt Ltd"],
                     net_worth_cr=120.0, is_promoter=True),
    DirectorPromoter(din="00223345", name="Anita Rathore", designation="Director",
                     entity_id="PINF001", pan="AABPA2346C",
                     date_of_appointment=date(2011, 1, 1),
                     other_directorships=["Pinnacle Realty Pvt Ltd"],
                     net_worth_cr=65.0, is_promoter=True),
    DirectorPromoter(din="00223346", name="Ramesh Iyer", designation="Independent Director",
                     entity_id="PINF001", pan="AABPR2347D",
                     date_of_appointment=date(2021, 6, 15),
                     other_directorships=["ABC Bank Ltd"],
                     net_worth_cr=30.0, is_promoter=False),
]

PINNACLE_INFRA_FINANCIALS = {
    "FY2025": FinancialStatement(
        entity_id="PINF001", period="FY2025", statement_type="standalone",
        source="audited", as_of_date=date(2025, 3, 31),
        line_items={
            "revenue_operating": 2200.00,
            "other_income": 15.00,
            "total_income": 2215.00,
            "raw_material_cost": 1430.00,
            "employee_cost": 176.00,
            "other_expenses": 330.00,
            "ebitda": 279.00,
            "depreciation": 110.00,
            "ebit": 169.00,
            "finance_cost": 145.00,
            "pbt": 24.00,
            "tax_expense": 6.00,
            "pat": 18.00,
            "total_equity": 520.00,
            "reserves_surplus": 395.00,
            "long_term_debt": 980.00,
            "short_term_debt": 450.00,
            "total_debt": 1430.00,
            "current_assets": 1150.00,
            "inventory": 180.00,
            "trade_receivables": 680.00,
            "cash_equivalents": 25.00,
            "other_current_assets": 265.00,
            "current_liabilities": 920.00,
            "trade_payables": 520.00,
            "other_current_liabilities": 400.00,
            "total_assets": 2870.00,
            "net_fixed_assets": 580.00,
            "capital_wip": 320.00,
            "intangible_assets": 15.00,
            "investments": 85.00,
            "operating_cash_flow": 35.00,
            "investing_cash_flow": -280.00,
            "financing_cash_flow": 220.00,
            "capex": 265.00,
            "dividend_paid": 0.00,
            "contingent_liabilities": 185.00,
        }
    ),
    "FY2024": FinancialStatement(
        entity_id="PINF001", period="FY2024", statement_type="standalone",
        source="audited", as_of_date=date(2024, 3, 31),
        line_items={
            "revenue_operating": 2550.00,
            "other_income": 18.00,
            "total_income": 2568.00,
            "raw_material_cost": 1581.00,
            "employee_cost": 178.50,
            "other_expenses": 306.00,
            "ebitda": 502.50,
            "depreciation": 102.00,
            "ebit": 400.50,
            "finance_cost": 128.00,
            "pbt": 272.50,
            "tax_expense": 68.13,
            "pat": 204.37,
            "total_equity": 640.00,
            "reserves_surplus": 515.00,
            "long_term_debt": 850.00,
            "short_term_debt": 380.00,
            "total_debt": 1230.00,
            "current_assets": 980.00,
            "inventory": 155.00,
            "trade_receivables": 510.00,
            "cash_equivalents": 55.00,
            "other_current_assets": 260.00,
            "current_liabilities": 780.00,
            "trade_payables": 440.00,
            "other_current_liabilities": 340.00,
            "total_assets": 2650.00,
            "net_fixed_assets": 550.00,
            "capital_wip": 280.00,
            "intangible_assets": 12.00,
            "investments": 78.00,
            "operating_cash_flow": 180.00,
            "investing_cash_flow": -195.00,
            "financing_cash_flow": 30.00,
            "capex": 180.00,
            "dividend_paid": 12.50,
            "contingent_liabilities": 140.00,
        }
    ),
    "FY2023": FinancialStatement(
        entity_id="PINF001", period="FY2023", statement_type="standalone",
        source="audited", as_of_date=date(2023, 3, 31),
        line_items={
            "revenue_operating": 2380.00,
            "other_income": 12.00,
            "total_income": 2392.00,
            "raw_material_cost": 1428.00,
            "employee_cost": 166.60,
            "other_expenses": 285.60,
            "ebitda": 511.80,
            "depreciation": 95.00,
            "ebit": 416.80,
            "finance_cost": 115.00,
            "pbt": 301.80,
            "tax_expense": 75.45,
            "pat": 226.35,
            "total_equity": 560.00,
            "reserves_surplus": 435.00,
            "long_term_debt": 720.00,
            "short_term_debt": 320.00,
            "total_debt": 1040.00,
            "current_assets": 850.00,
            "inventory": 130.00,
            "trade_receivables": 420.00,
            "cash_equivalents": 70.00,
            "other_current_assets": 230.00,
            "current_liabilities": 680.00,
            "trade_payables": 380.00,
            "other_current_liabilities": 300.00,
            "total_assets": 2320.00,
            "net_fixed_assets": 520.00,
            "capital_wip": 230.00,
            "intangible_assets": 10.00,
            "investments": 60.00,
            "operating_cash_flow": 220.00,
            "investing_cash_flow": -165.00,
            "financing_cash_flow": -40.00,
            "capex": 155.00,
            "dividend_paid": 18.75,
            "contingent_liabilities": 95.00,
        }
    ),
}

# Provisional FY2025 — DELIBERATE MISMATCH vs exchange data
PINNACLE_INFRA_PROVISIONAL = FinancialStatement(
    entity_id="PINF001", period="FY2026_P", statement_type="standalone",
    source="provisional", as_of_date=date(2026, 12, 31),
    line_items={
        "revenue_operating": 2400.00,  # Borrower claims 2400
        "ebitda": 360.00,
        "pat": 85.00,
        "total_debt": 1500.00,
        "total_equity": 550.00,
    }
)

# Exchange-filed data shows DIFFERENT revenue (this creates mismatch)
PINNACLE_INFRA_EXCHANGE_FILING = FinancialStatement(
    entity_id="PINF001", period="FY2026_Q3", statement_type="standalone",
    source="exchange", as_of_date=date(2026, 12, 31),
    line_items={
        "revenue_operating": 1650.00,  # Exchange says only 1650 for 9M
        "ebitda": 198.00,
        "pat": -12.00,  # Actually loss-making!
    }
)

PINNACLE_INFRA_FACILITY = FacilityRequest(
    facility_id="FAC_PINF_001",
    entity_id="PINF001",
    case_type=CaseType.NTB,
    facility_type=FacilityType.TERM_LOAN,
    amount_requested_cr=350.00,
    purpose="Term loan for highway project — NH48 bypass section (65 km). "
            "NHAI BOT toll project with 20-year concession.",
    tenor_months=120,
    collateral_type="Project Assets + Escrow of Toll Revenue",
    collateral_value_cr=420.00,
    proposed_limit_cr=350.00,
)

PINNACLE_INFRA_COLLATERAL = [
    Collateral(
        collateral_id="COL_PINF_001", entity_id="PINF001",
        collateral_type="Project Assets",
        description="Highway project assets — NH48 bypass",
        market_value_cr=280.00, forced_sale_value_cr=168.00,
        valuation_date=date(2026, 9, 30), encumbrance_status="clear"
    ),
    Collateral(
        collateral_id="COL_PINF_002", entity_id="PINF001",
        collateral_type="Toll Revenue Escrow",
        description="Escrow of projected toll revenue for debt servicing",
        market_value_cr=140.00, forced_sale_value_cr=98.00,
        valuation_date=date(2026, 9, 30), encumbrance_status="clear"
    ),
]

PINNACLE_INFRA_MARKET_SIGNALS = [
    MarketSignal(entity_id="PINF001", signal_type="news",
                 headline="ICRA places Pinnacle Infra on Watch Negative amid project delays",
                 sentiment="negative", severity=RiskSeverity.HIGH, source_name="Business Standard",
                 signal_date=date(2026, 11, 15),
                 details="Two highway projects face 6-month execution delay; cost overrun concerns."),
    MarketSignal(entity_id="PINF001", signal_type="social",
                 headline="Employee reviews flag salary delays at Pinnacle Infra",
                 sentiment="negative", severity=RiskSeverity.MEDIUM, source_name="Glassdoor",
                 signal_date=date(2026, 10, 3),
                 details="Multiple reviews mention 2-3 month salary delays in project sites."),
    MarketSignal(entity_id="PINF001", signal_type="news",
                 headline="NHAI terminates 2 BOT contracts of Pinnacle Group subsidiary",
                 sentiment="negative", severity=RiskSeverity.HIGH, source_name="Mint",
                 signal_date=date(2026, 8, 20),
                 details="Contracts terminated due to non-compliance with construction milestones."),
]


# ═══════════════════════════════════════════════════════════════════════════════
# COMPANY 3: SUNRISE PHARMA PVT LTD (NTB, Unlisted, Pharma — GROUP RISK)
# ═══════════════════════════════════════════════════════════════════════════════

SUNRISE_PHARMA = Borrower(
    entity_id="SPHR001",
    company_name="Sunrise Pharma Pvt Ltd",
    cin="U24230GJ2012PTC068945",
    pan="AABCS9012H",
    borrower_type=BorrowerType.UNLISTED,
    sector=Sector.PHARMA,
    subsector="API Manufacturing",
    date_of_incorporation=date(2013, 6, 10),
    registered_state="Gujarat",
    registered_address="Survey No 142, GIDC Ankleshwar, Gujarat 393002",
    authorized_capital=50.00,
    paid_up_capital=35.00,
    credit_rating="CARE BBB/Stable",
    rating_agency="CARE",
    employee_count=680,
    website="www.sunrisepharma.in",
)

SUNRISE_PHARMA_GROUP = GroupEntity(
    group_id="GRP_SPHR",
    group_name="Sunrise Healthcare Group",
    parent_entity_id="SPHR001",
    entities=["SPHR001", "Sunrise Biotech Pvt Ltd", "Sunrise Formulations Pvt Ltd",
              "Sunrise Medicare Pvt Ltd"],
    promoter_holding_pct=85.0,
    institutional_holding_pct=0.0,
    public_holding_pct=15.0,
)

SUNRISE_PHARMA_DIRECTORS = [
    DirectorPromoter(din="00334455", name="Dr. Harish Patel", designation="Managing Director",
                     entity_id="SPHR001", pan="AABPH3456E",
                     date_of_appointment=date(2013, 6, 10),
                     other_directorships=["Sunrise Biotech Pvt Ltd", "Sunrise Formulations Pvt Ltd",
                                          "Sunrise Medicare Pvt Ltd", "Global Health Exports LLC"],
                     net_worth_cr=42.0, is_promoter=True),
    DirectorPromoter(din="00334456", name="Meera H. Patel", designation="Director",
                     entity_id="SPHR001", pan="AABPM3457F",
                     date_of_appointment=date(2013, 6, 10),
                     other_directorships=["Sunrise Biotech Pvt Ltd", "Sunrise Medicare Pvt Ltd"],
                     net_worth_cr=28.0, is_promoter=True),
    DirectorPromoter(din="00334457", name="Kiran Shah", designation="Director — Finance",
                     entity_id="SPHR001", pan="AABPK3458G",
                     date_of_appointment=date(2017, 4, 1),
                     other_directorships=["Sunrise Formulations Pvt Ltd"],
                     net_worth_cr=8.5, is_promoter=False),
]

SUNRISE_PHARMA_FINANCIALS = {
    "FY2025": FinancialStatement(
        entity_id="SPHR001", period="FY2025", statement_type="standalone",
        source="audited", as_of_date=date(2025, 3, 31),
        line_items={
            "revenue_operating": 420.00,
            "other_income": 5.50,
            "total_income": 425.50,
            "raw_material_cost": 210.00,
            "employee_cost": 42.00,
            "other_expenses": 63.00,
            "ebitda": 110.50,
            "depreciation": 21.00,
            "ebit": 89.50,
            "finance_cost": 32.00,
            "pbt": 57.50,
            "tax_expense": 14.38,
            "pat": 43.12,
            "total_equity": 165.00,
            "reserves_surplus": 130.00,
            "long_term_debt": 120.00,
            "short_term_debt": 85.00,
            "total_debt": 205.00,
            "current_assets": 185.00,
            "inventory": 62.00,
            "trade_receivables": 78.00,
            "cash_equivalents": 12.00,
            "other_current_assets": 33.00,
            "current_liabilities": 115.00,
            "trade_payables": 65.00,
            "other_current_liabilities": 50.00,
            "total_assets": 490.00,
            "net_fixed_assets": 180.00,
            "capital_wip": 25.00,
            "intangible_assets": 8.00,
            "investments": 42.00,   # Investments in group entities — risk flag
            "operating_cash_flow": 72.00,
            "investing_cash_flow": -55.00,
            "financing_cash_flow": -12.00,
            "capex": 35.00,
            "dividend_paid": 5.00,
            "contingent_liabilities": 15.00,
        }
    ),
    "FY2024": FinancialStatement(
        entity_id="SPHR001", period="FY2024", statement_type="standalone",
        source="audited", as_of_date=date(2024, 3, 31),
        line_items={
            "revenue_operating": 385.00,
            "other_income": 4.80,
            "total_income": 389.80,
            "raw_material_cost": 196.35,
            "employee_cost": 38.50,
            "other_expenses": 57.75,
            "ebitda": 97.20,
            "depreciation": 18.50,
            "ebit": 78.70,
            "finance_cost": 28.00,
            "pbt": 50.70,
            "tax_expense": 12.68,
            "pat": 38.02,
            "total_equity": 148.00,
            "reserves_surplus": 113.00,
            "long_term_debt": 105.00,
            "short_term_debt": 72.00,
            "total_debt": 177.00,
            "current_assets": 162.00,
            "inventory": 55.00,
            "trade_receivables": 68.00,
            "cash_equivalents": 10.00,
            "other_current_assets": 29.00,
            "current_liabilities": 98.00,
            "trade_payables": 56.00,
            "other_current_liabilities": 42.00,
            "total_assets": 425.00,
            "net_fixed_assets": 160.00,
            "capital_wip": 18.00,
            "intangible_assets": 6.00,
            "investments": 35.00,
            "operating_cash_flow": 62.00,
            "investing_cash_flow": -42.00,
            "financing_cash_flow": -15.00,
            "capex": 28.00,
            "dividend_paid": 4.00,
            "contingent_liabilities": 12.00,
        }
    ),
    "FY2023": FinancialStatement(
        entity_id="SPHR001", period="FY2023", statement_type="standalone",
        source="audited", as_of_date=date(2023, 3, 31),
        line_items={
            "revenue_operating": 340.00,
            "other_income": 3.50,
            "total_income": 343.50,
            "raw_material_cost": 170.00,
            "employee_cost": 34.00,
            "other_expenses": 51.00,
            "ebitda": 88.50,
            "depreciation": 16.00,
            "ebit": 72.50,
            "finance_cost": 24.00,
            "pbt": 48.50,
            "tax_expense": 12.13,
            "pat": 36.37,
            "total_equity": 130.00,
            "reserves_surplus": 95.00,
            "long_term_debt": 92.00,
            "short_term_debt": 60.00,
            "total_debt": 152.00,
            "current_assets": 140.00,
            "inventory": 48.00,
            "trade_receivables": 58.00,
            "cash_equivalents": 8.00,
            "other_current_assets": 26.00,
            "current_liabilities": 82.00,
            "trade_payables": 48.00,
            "other_current_liabilities": 34.00,
            "total_assets": 362.00,
            "net_fixed_assets": 142.00,
            "capital_wip": 12.00,
            "intangible_assets": 5.00,
            "investments": 25.00,
            "operating_cash_flow": 55.00,
            "investing_cash_flow": -35.00,
            "financing_cash_flow": -18.00,
            "capex": 25.00,
            "dividend_paid": 3.50,
            "contingent_liabilities": 10.00,
        }
    ),
}

SUNRISE_PHARMA_PROVISIONAL = FinancialStatement(
    entity_id="SPHR001", period="FY2026_P", statement_type="standalone",
    source="provisional", as_of_date=date(2026, 12, 31),
    line_items={
        "revenue_operating": 465.00,
        "ebitda": 120.90,
        "pat": 48.00,
        "total_debt": 225.00,
        "total_equity": 185.00,
    }
)

SUNRISE_PHARMA_FACILITY = FacilityRequest(
    facility_id="FAC_SPHR_001",
    entity_id="SPHR001",
    case_type=CaseType.NTB,
    facility_type=FacilityType.TERM_LOAN,
    amount_requested_cr=75.00,
    purpose="Capacity expansion of API manufacturing facility at Ankleshwar GIDC. "
            "Addition of 2 new reaction vessels and effluent treatment plant upgrade.",
    tenor_months=84,
    collateral_type="Factory Land & Building + Plant & Machinery",
    collateral_value_cr=110.00,
    proposed_limit_cr=75.00,
)

SUNRISE_PHARMA_COLLATERAL = [
    Collateral(
        collateral_id="COL_SPHR_001", entity_id="SPHR001",
        collateral_type="Factory Land & Building",
        description="Factory premises at GIDC Ankleshwar — 5 acres with building",
        market_value_cr=72.00, forced_sale_value_cr=50.40,
        valuation_date=date(2026, 10, 20), encumbrance_status="clear"
    ),
    Collateral(
        collateral_id="COL_SPHR_002", entity_id="SPHR001",
        collateral_type="Plant & Machinery",
        description="Reaction vessels, distillation units, ETP — existing setup",
        market_value_cr=38.00, forced_sale_value_cr=22.80,
        valuation_date=date(2026, 10, 20), encumbrance_status="clear"
    ),
]

SUNRISE_PHARMA_MARKET_SIGNALS = [
    MarketSignal(entity_id="SPHR001", signal_type="news",
                 headline="Sunrise Biotech (group entity) faces FDA warning letter",
                 sentiment="negative", severity=RiskSeverity.HIGH, source_name="Pharma Biz",
                 signal_date=date(2026, 9, 12),
                 details="US FDA issued warning letter to Sunrise Biotech for GMP violations at Ankleshwar unit."),
    MarketSignal(entity_id="SPHR001", signal_type="news",
                 headline="Sunrise Medicare defaults on bank loan — Rs 8 Cr overdue",
                 sentiment="negative", severity=RiskSeverity.CRITICAL, source_name="Money Control",
                 signal_date=date(2026, 7, 28),
                 details="Group company Sunrise Medicare classified as SMA-2 by consortium banks."),
    MarketSignal(entity_id="SPHR001", signal_type="analyst",
                 headline="API prices stabilize after 18-month correction",
                 sentiment="positive", severity=RiskSeverity.LOW, source_name="ICRA Research",
                 signal_date=date(2026, 11, 5),
                 details="Indian API manufacturers expected to benefit from China+1 sourcing trend."),
]


# ═══════════════════════════════════════════════════════════════════════════════
# COMPANY 4: OMEGA LOGISTICS PVT LTD (ETB, Unlisted, Logistics — CONDUCT ISSUES)
# ═══════════════════════════════════════════════════════════════════════════════

OMEGA_LOGISTICS = Borrower(
    entity_id="OLOG001",
    company_name="Omega Logistics Pvt Ltd",
    cin="U63090KA2010PTC052345",
    pan="AABCO3456J",
    borrower_type=BorrowerType.UNLISTED,
    sector=Sector.LOGISTICS,
    subsector="3PL & Warehousing",
    date_of_incorporation=date(2011, 3, 25),
    registered_state="Karnataka",
    registered_address="No 78, Whitefield Main Road, Bangalore 560066",
    authorized_capital=25.00,
    paid_up_capital=18.00,
    credit_rating="BWR BBB+/Stable",
    rating_agency="Brickwork",
    employee_count=1450,
    website="www.omegalogistics.in",
)

OMEGA_LOGISTICS_GROUP = GroupEntity(
    group_id="GRP_OLOG",
    group_name="Omega Group",
    parent_entity_id="OLOG001",
    entities=["OLOG001", "Omega Cold Chain Pvt Ltd"],
    promoter_holding_pct=72.0,
    institutional_holding_pct=0.0,
    public_holding_pct=28.0,
)

OMEGA_LOGISTICS_DIRECTORS = [
    DirectorPromoter(din="00445566", name="Pradeep Nair", designation="Managing Director",
                     entity_id="OLOG001", pan="AABPN4567H",
                     date_of_appointment=date(2011, 3, 25),
                     other_directorships=["Omega Cold Chain Pvt Ltd"],
                     net_worth_cr=22.0, is_promoter=True),
    DirectorPromoter(din="00445567", name="Deepa P. Nair", designation="Director",
                     entity_id="OLOG001", pan="AABPD4568I",
                     date_of_appointment=date(2013, 4, 1),
                     other_directorships=["Omega Cold Chain Pvt Ltd"],
                     net_worth_cr=15.0, is_promoter=True),
    DirectorPromoter(din="00445568", name="Sanjay Kulkarni", designation="Independent Director",
                     entity_id="OLOG001", pan="AABPS4569J",
                     date_of_appointment=date(2023, 8, 1),
                     other_directorships=["XYZ Freight Ltd"],
                     net_worth_cr=5.0, is_promoter=False),
]

OMEGA_LOGISTICS_FINANCIALS = {
    "FY2025": FinancialStatement(
        entity_id="OLOG001", period="FY2025", statement_type="standalone",
        source="audited", as_of_date=date(2025, 3, 31),
        line_items={
            "revenue_operating": 580.00,
            "other_income": 8.00,
            "total_income": 588.00,
            "raw_material_cost": 290.00,
            "employee_cost": 87.00,
            "other_expenses": 110.20,
            "ebitda": 100.80,
            "depreciation": 34.80,
            "ebit": 66.00,
            "finance_cost": 38.00,
            "pbt": 28.00,
            "tax_expense": 7.00,
            "pat": 21.00,
            "total_equity": 92.00,
            "reserves_surplus": 74.00,
            "long_term_debt": 145.00,
            "short_term_debt": 110.00,
            "total_debt": 255.00,
            "current_assets": 195.00,
            "inventory": 18.00,
            "trade_receivables": 120.00,
            "cash_equivalents": 8.00,
            "other_current_assets": 49.00,
            "current_liabilities": 155.00,
            "trade_payables": 85.00,
            "other_current_liabilities": 70.00,
            "total_assets": 502.00,
            "net_fixed_assets": 185.00,
            "capital_wip": 15.00,
            "intangible_assets": 12.00,
            "investments": 5.00,
            "operating_cash_flow": 52.00,
            "investing_cash_flow": -38.00,
            "financing_cash_flow": -8.00,
            "capex": 32.00,
            "dividend_paid": 2.00,
            "contingent_liabilities": 8.50,
        }
    ),
    "FY2024": FinancialStatement(
        entity_id="OLOG001", period="FY2024", statement_type="standalone",
        source="audited", as_of_date=date(2024, 3, 31),
        line_items={
            "revenue_operating": 520.00,
            "other_income": 6.50,
            "total_income": 526.50,
            "raw_material_cost": 260.00,
            "employee_cost": 78.00,
            "other_expenses": 98.80,
            "ebitda": 89.70,
            "depreciation": 31.00,
            "ebit": 58.70,
            "finance_cost": 34.00,
            "pbt": 24.70,
            "tax_expense": 6.18,
            "pat": 18.52,
            "total_equity": 82.00,
            "reserves_surplus": 64.00,
            "long_term_debt": 130.00,
            "short_term_debt": 95.00,
            "total_debt": 225.00,
            "current_assets": 172.00,
            "inventory": 15.00,
            "trade_receivables": 108.00,
            "cash_equivalents": 10.00,
            "other_current_assets": 39.00,
            "current_liabilities": 138.00,
            "trade_payables": 76.00,
            "other_current_liabilities": 62.00,
            "total_assets": 445.00,
            "net_fixed_assets": 168.00,
            "capital_wip": 10.00,
            "intangible_assets": 10.00,
            "investments": 5.00,
            "operating_cash_flow": 48.00,
            "investing_cash_flow": -28.00,
            "financing_cash_flow": -15.00,
            "capex": 25.00,
            "dividend_paid": 2.00,
            "contingent_liabilities": 6.00,
        }
    ),
    "FY2023": FinancialStatement(
        entity_id="OLOG001", period="FY2023", statement_type="standalone",
        source="audited", as_of_date=date(2023, 3, 31),
        line_items={
            "revenue_operating": 465.00,
            "other_income": 5.00,
            "total_income": 470.00,
            "raw_material_cost": 232.50,
            "employee_cost": 69.75,
            "other_expenses": 88.35,
            "ebitda": 79.40,
            "depreciation": 27.50,
            "ebit": 51.90,
            "finance_cost": 30.00,
            "pbt": 21.90,
            "tax_expense": 5.48,
            "pat": 16.42,
            "total_equity": 72.00,
            "reserves_surplus": 54.00,
            "long_term_debt": 115.00,
            "short_term_debt": 82.00,
            "total_debt": 197.00,
            "current_assets": 148.00,
            "inventory": 12.00,
            "trade_receivables": 92.00,
            "cash_equivalents": 12.00,
            "other_current_assets": 32.00,
            "current_liabilities": 118.00,
            "trade_payables": 65.00,
            "other_current_liabilities": 53.00,
            "total_assets": 387.00,
            "net_fixed_assets": 152.00,
            "capital_wip": 8.00,
            "intangible_assets": 8.00,
            "investments": 4.00,
            "operating_cash_flow": 42.00,
            "investing_cash_flow": -22.00,
            "financing_cash_flow": -18.00,
            "capex": 20.00,
            "dividend_paid": 1.50,
            "contingent_liabilities": 5.00,
        }
    ),
}

OMEGA_LOGISTICS_PROVISIONAL = FinancialStatement(
    entity_id="OLOG001", period="FY2026_P", statement_type="standalone",
    source="provisional", as_of_date=date(2026, 12, 31),
    line_items={
        "revenue_operating": 610.00,
        "ebitda": 97.60,
        "pat": 18.00,
        "total_debt": 270.00,
        "total_equity": 98.00,
    }
)

OMEGA_LOGISTICS_FACILITY = FacilityRequest(
    facility_id="FAC_OLOG_001",
    entity_id="OLOG001",
    case_type=CaseType.ETB,
    facility_type=FacilityType.WORKING_CAPITAL,
    amount_requested_cr=25.00,
    purpose="Enhancement of working capital limit from Rs 110 Cr to Rs 135 Cr "
            "to support growing contract logistics volumes.",
    tenor_months=12,
    collateral_type="Receivables + Vehicles",
    collateral_value_cr=48.00,
    existing_limit_cr=110.00,
    proposed_limit_cr=135.00,
)

OMEGA_LOGISTICS_EXISTING_EXPOSURE = [
    ExistingExposure(
        facility_id="EXP_OLOG_WC", entity_id="OLOG001",
        facility_type="Working Capital", sanctioned_limit_cr=110.00,
        outstanding_cr=105.60, utilization_pct=96.0, overdue_days=0
    ),
    ExistingExposure(
        facility_id="EXP_OLOG_TL", entity_id="OLOG001",
        facility_type="Term Loan", sanctioned_limit_cr=85.00,
        outstanding_cr=62.50, utilization_pct=73.5, overdue_days=15
    ),
]

OMEGA_LOGISTICS_CONDUCT = [
    ConductRecord(entity_id="OLOG001", period="Q1_FY2026",
                  avg_bank_balance_cr=3.2, credit_turnover_cr=145.00,
                  debit_turnover_cr=148.00, cheque_returns=8,
                  limit_utilization_pct=94.0, overdue_instances=2,
                  max_overdue_days=18, dpd_30_count=1),
    ConductRecord(entity_id="OLOG001", period="Q2_FY2026",
                  avg_bank_balance_cr=2.8, credit_turnover_cr=138.00,
                  debit_turnover_cr=142.00, cheque_returns=12,
                  limit_utilization_pct=97.0, overdue_instances=3,
                  max_overdue_days=25, dpd_30_count=1),
    ConductRecord(entity_id="OLOG001", period="Q3_FY2026",
                  avg_bank_balance_cr=2.1, credit_turnover_cr=130.00,
                  debit_turnover_cr=135.00, cheque_returns=15,
                  limit_utilization_pct=98.5, overdue_instances=4,
                  max_overdue_days=32, dpd_30_count=2, dpd_60_count=1),
    ConductRecord(entity_id="OLOG001", period="Q4_FY2025",
                  avg_bank_balance_cr=4.5, credit_turnover_cr=155.00,
                  debit_turnover_cr=152.00, cheque_returns=5,
                  limit_utilization_pct=88.0, overdue_instances=1,
                  max_overdue_days=12, dpd_30_count=0),
]

OMEGA_LOGISTICS_COVENANTS = [
    CovenantRecord(entity_id="OLOG001", covenant_type="Minimum Current Ratio",
                   required_value=">=1.25", actual_value="1.26",
                   compliance_status="compliant", period="FY2024"),
    CovenantRecord(entity_id="OLOG001", covenant_type="Minimum Current Ratio",
                   required_value=">=1.25", actual_value="1.26",
                   compliance_status="compliant", period="FY2025"),
    CovenantRecord(entity_id="OLOG001", covenant_type="Maximum Debt/Equity",
                   required_value="<=3.0", actual_value="2.77",
                   compliance_status="compliant", period="FY2025"),
    CovenantRecord(entity_id="OLOG001", covenant_type="Minimum DSCR",
                   required_value=">=1.20", actual_value="1.08",
                   compliance_status="breached", period="FY2025",
                   breach_details="DSCR fell below covenant threshold due to increased debt servicing costs."),
    CovenantRecord(entity_id="OLOG001", covenant_type="Maximum Cheque Returns",
                   required_value="<=5 per quarter", actual_value="15",
                   compliance_status="breached", period="Q3_FY2026",
                   breach_details="Cheque returns spiked to 15 in Q3 FY2025 vs limit of 5."),
]

OLOG_CORE_BANKING = {
    "loan_accounts": [
        {"account_number": "ACC_OLG_TL01", "entity_id": "OLOG001", "facility_type": "TL",
         "sanction_limit_cr": 45.00, "outstanding_cr": 38.50, "interest_rate_pct": 11.25,
         "overdue_amount_cr": 1.20, "dpd": 28, "asset_classification": "Standard",
         "sanction_date": "2022-04-10", "maturity_date": "2029-04-10", "repayment_frequency": "Monthly"},
        {"account_number": "ACC_OLG_CC01", "entity_id": "OLOG001", "facility_type": "CC",
         "sanction_limit_cr": 20.00, "outstanding_cr": 19.70, "interest_rate_pct": 12.50,
         "overdue_amount_cr": 0.0, "dpd": 0, "asset_classification": "Standard",
         "sanction_date": "2023-01-15", "maturity_date": "2026-01-15", "repayment_frequency": "Monthly"},
    ],
    "bclc": {
        "total_fund_based_cr": 58.20, "total_non_fund_based_cr": 0.0,
        "total_exposure_cr": 58.20,
        "single_borrower_limit_pct": 0.12, "group_borrower_limit_pct": 0.12,
        "within_single_limit": True, "within_group_limit": True,
        "industry_exposure_pct": 1.8, "sector_ceiling_pct": 10.0,
        "rating_based_limit_cr": 200.00,
    },
    "liability": {
        "current_account_balance_cr": 2.10, "savings_balance_cr": 0.0,
        "fixed_deposit_cr": 0.0, "total_deposits_cr": 2.10,
        "average_balance_6m_cr": 2.80, "reciprocal_business_cr": 2.10,
        "cross_sell_products": ["Cash Management"],
    },
    "fees_commission": [
        {"period": "FY2025", "processing_fees_cr": 0.25, "renewal_fees_cr": 0.10,
         "lc_commission_cr": 0.0, "bg_commission_cr": 0.0,
         "forex_income_cr": 0.0, "other_charges_cr": 0.05, "total_income_cr": 0.40},
        {"period": "FY2024", "processing_fees_cr": 0.20, "renewal_fees_cr": 0.08,
         "lc_commission_cr": 0.0, "bg_commission_cr": 0.0,
         "forex_income_cr": 0.0, "other_charges_cr": 0.04, "total_income_cr": 0.32},
    ],
    "total_exposure_cr": 58.20,
    "overall_asset_classification": "Standard",
    "relationship_since": "2020-07-01",
    "relationship_years": 6,
}

OMEGA_LOGISTICS_COLLATERAL = [
    Collateral(
        collateral_id="COL_OLOG_001", entity_id="OLOG001",
        collateral_type="Fleet Vehicles",
        description="24 commercial vehicles — 16-tonne trucks",
        market_value_cr=32.00, forced_sale_value_cr=19.20,
        valuation_date=date(2026, 8, 15), encumbrance_status="hypothecated"
    ),
    Collateral(
        collateral_id="COL_OLOG_002", entity_id="OLOG001",
        collateral_type="Receivables",
        description="Trade receivables from top 10 customers",
        market_value_cr=16.00, forced_sale_value_cr=9.60,
        valuation_date=date(2027, 1, 5), encumbrance_status="assigned"
    ),
]

OMEGA_LOGISTICS_MARKET_SIGNALS = [
    MarketSignal(entity_id="OLOG001", signal_type="news",
                 headline="India 3PL market grows 12% YoY; Omega Logistics adds 3 warehouses",
                 sentiment="positive", severity=RiskSeverity.LOW, source_name="ET Logistics",
                 signal_date=date(2026, 11, 10),
                 details="3PL sector sees tailwinds from e-commerce and cold-chain demand."),
    MarketSignal(entity_id="OLOG001", signal_type="social",
                 headline="Customer complaints about delayed shipments from Omega Logistics",
                 sentiment="negative", severity=RiskSeverity.MEDIUM, source_name="Twitter/X",
                 signal_date=date(2026, 12, 20),
                 details="Multiple B2B customers report service quality deterioration in last 2 months."),
]


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRY: All companies for easy test iteration
# ═══════════════════════════════════════════════════════════════════════════════

ALL_COMPANIES = {
    "BMFG001": {
        "borrower": BHARAT_MFG,
        "group": BHARAT_MFG_GROUP,
        "directors": BHARAT_MFG_DIRECTORS,
        "financials": BHARAT_MFG_FINANCIALS,
        "provisional": BHARAT_MFG_PROVISIONAL,
        "facility": BHARAT_MFG_FACILITY,
        "collateral": BHARAT_MFG_COLLATERAL,
        "market_signals": BHARAT_MFG_MARKET_SIGNALS,
        "existing_exposure": [],
        "conduct": [],
        "covenants": [],
        "exchange_filing": None,
    },
    "PINF001": {
        "borrower": PINNACLE_INFRA,
        "group": PINNACLE_INFRA_GROUP,
        "directors": PINNACLE_INFRA_DIRECTORS,
        "financials": PINNACLE_INFRA_FINANCIALS,
        "provisional": PINNACLE_INFRA_PROVISIONAL,
        "facility": PINNACLE_INFRA_FACILITY,
        "collateral": PINNACLE_INFRA_COLLATERAL,
        "market_signals": PINNACLE_INFRA_MARKET_SIGNALS,
        "existing_exposure": [],
        "conduct": [],
        "covenants": [],
        "exchange_filing": PINNACLE_INFRA_EXCHANGE_FILING,
    },
    "SPHR001": {
        "borrower": SUNRISE_PHARMA,
        "group": SUNRISE_PHARMA_GROUP,
        "directors": SUNRISE_PHARMA_DIRECTORS,
        "financials": SUNRISE_PHARMA_FINANCIALS,
        "provisional": SUNRISE_PHARMA_PROVISIONAL,
        "facility": SUNRISE_PHARMA_FACILITY,
        "collateral": SUNRISE_PHARMA_COLLATERAL,
        "market_signals": SUNRISE_PHARMA_MARKET_SIGNALS,
        "existing_exposure": [],
        "conduct": [],
        "covenants": [],
        "exchange_filing": None,
    },
    "OLOG001": {
        "borrower": OMEGA_LOGISTICS,
        "group": OMEGA_LOGISTICS_GROUP,
        "directors": OMEGA_LOGISTICS_DIRECTORS,
        "financials": OMEGA_LOGISTICS_FINANCIALS,
        "provisional": OMEGA_LOGISTICS_PROVISIONAL,
        "facility": OMEGA_LOGISTICS_FACILITY,
        "collateral": OMEGA_LOGISTICS_COLLATERAL,
        "market_signals": OMEGA_LOGISTICS_MARKET_SIGNALS,
        "existing_exposure": OMEGA_LOGISTICS_EXISTING_EXPOSURE,
        "conduct": OMEGA_LOGISTICS_CONDUCT,
        "covenants": OMEGA_LOGISTICS_COVENANTS,
        "core_banking": OLOG_CORE_BANKING,
        "exchange_filing": None,
    },
}

# Merge 12 real Indian companies
from src.data.real_companies import REAL_COMPANIES
ALL_COMPANIES.update(REAL_COMPANIES)

# Inject sector-specific KPIs into every company
from src.data.sector_kpis import SECTOR_KPIS
for _eid, _kpis in SECTOR_KPIS.items():
    if _eid in ALL_COMPANIES:
        ALL_COMPANIES[_eid]["sector_kpis"] = _kpis
