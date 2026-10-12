"""
Real Indian Company Data: 12 Companies Inspired by Actual Indian Corporates
============================================================================
Covers diverse sectors, listing status, case types, and risk profiles.
All financial data is realistic but fictional — inspired by public disclosures.

Company  5: TSTL001 — Tata Steel-like     | Listed NTB, Steel (Clean)
Company  6: REIL001 — Reliance-like        | Listed NTB, Energy (High Leverage)
Company  7: INFY001 — Infosys-like         | Listed NTB, IT Services (Asset-Light)
Company  8: ADPT001 — Adani Ports-like     | Listed NTB, Infrastructure (Growth)
Company  9: BJFN001 — Bajaj Finance-like   | Listed NTB, NBFC (High Growth)
Company 10: CIPL001 — Cipla-like           | Listed NTB, Pharma (Clean)
Company 11: DLFR001 — DLF-like             | Listed ETB, Real Estate (Stressed)
Company 12: JSWL001 — JSW Steel-like       | Listed NTB, Manufacturing (Cyclical)
Company 13: MRUT001 — Maruti-like          | Listed NTB, Manufacturing (Strong)
Company 14: TITN001 — Titan-like           | Listed NTB, Trading/Retail (Clean)
Company 15: NTPC001 — NTPC-like            | Listed ETB, Infrastructure (Stable)
Company 16: YESB001 — Yes Bank-like        | Listed ETB, NBFC (Fraud Signals)
Company 17: DRRD001 — Dr. Reddy's Labs     | Listed NTB, Pharma (Clean)
Company 18: IHCL001 — Indian Hotels (Taj)  | Listed ETB, Hospitality (Strong)
"""

from datetime import date
from src.models.canonical_model import (
    Borrower, GroupEntity, DirectorPromoter, FinancialStatement,
    FacilityRequest, ExistingExposure, Collateral, MarketSignal,
    ConductRecord, CovenantRecord, CaseType, BorrowerType,
    FacilityType, Sector, RiskSeverity,
)


# ═══════════════════════════════════════════════════════════════════════════════
# COMPANY 5: TATA STEEL INDUSTRIES LTD (Listed NTB, Steel — CLEAN)
# ═══════════════════════════════════════════════════════════════════════════════

TSTL_BORROWER = Borrower(
    entity_id="TSTL001",
    company_name="Tara Steels Industries Ltd",
    cin="L27100MH1907PLC000260",
    pan="AAACT1234A",
    borrower_type=BorrowerType.LISTED,
    sector=Sector.MANUFACTURING,
    subsector="Iron & Steel",
    date_of_incorporation=date(1908, 8, 26),
    registered_state="Maharashtra",
    registered_address="Bombay House, 24 Homi Mody Street, Mumbai 400001",
    authorized_capital=1500.00,
    paid_up_capital=1221.40,
    listed_exchange="BSE, NSE",
    nse_symbol="TARASTEEL",
    isin="INE081A01020",
    credit_rating="CRISIL AA/Stable",
    rating_agency="CRISIL",
    employee_count=33500,
    website="www.tarasteels.com",
)

TSTL_GROUP = GroupEntity(
    group_id="GRP_TSTL", group_name="Tara Group",
    parent_entity_id="TSTL001",
    entities=["TSTL001", "Tara Metaliks Ltd", "Tara Steel BSL Ltd", "Tara Long Products Ltd"],
    promoter_holding_pct=33.9, institutional_holding_pct=44.5, public_holding_pct=21.6,
)

TSTL_DIRECTORS = [
    DirectorPromoter(din="00004009", name="Natarajan C.", designation="Chairman",
                     entity_id="TSTL001", is_promoter=True, net_worth_cr=850.0,
                     other_directorships=["Tara Metaliks Ltd", "Indian Hotels Co Ltd"]),
    DirectorPromoter(din="03083605", name="T.V. Narendran", designation="Managing Director & CEO",
                     entity_id="TSTL001", is_promoter=False, net_worth_cr=125.0,
                     other_directorships=["CII", "World Steel Association"]),
    DirectorPromoter(din="06639356", name="Koushik Chatterjee", designation="Executive Director & CFO",
                     entity_id="TSTL001", is_promoter=False, net_worth_cr=82.0),
    DirectorPromoter(din="00014615", name="Deepak Kapoor", designation="Independent Director",
                     entity_id="TSTL001", is_promoter=False, net_worth_cr=45.0),
]

TSTL_FINANCIALS = {
    "FY2025": FinancialStatement(
        entity_id="TSTL001", period="FY2025", statement_type="standalone",
        source="audited", as_of_date=date(2025, 3, 31),
        line_items={
            "revenue_operating": 63780.00, "other_income": 1240.00,
            "total_income": 65020.00, "raw_material_cost": 38268.00,
            "employee_cost": 5740.20, "other_expenses": 7653.60,
            "ebitda": 13358.20, "depreciation": 4400.00,
            "ebit": 8958.20, "finance_cost": 3190.00,
            "pbt": 5768.20, "tax_expense": 1442.05, "pat": 4326.15,
            "total_assets": 98500.00, "fixed_assets": 52000.00,
            "current_assets": 28500.00, "investments": 18000.00,
            "total_equity": 42500.00, "long_term_debt": 32000.00,
            "short_term_debt": 12000.00, "total_debt": 44000.00,
            "current_liabilities": 22000.00, "trade_receivables": 9800.00,
            "inventory": 12500.00, "cash_equivalents": 4200.00,
            "trade_payables": 11500.00,
            "ocf": 9800.00, "capex": -5200.00, "fcff": 4600.00,
            "market_cap": 185000.00, "working_capital": 6500.00,
            "retained_earnings": 28500.00,
        }
    ),
    "FY2024": FinancialStatement(
        entity_id="TSTL001", period="FY2024", statement_type="standalone",
        source="audited", as_of_date=date(2024, 3, 31),
        line_items={
            "revenue_operating": 58420.00, "other_income": 1050.00,
            "total_income": 59470.00, "raw_material_cost": 35652.20,
            "employee_cost": 5258.00, "other_expenses": 7010.40,
            "ebitda": 11549.40, "depreciation": 4100.00,
            "ebit": 7449.40, "finance_cost": 2920.00,
            "pbt": 4529.40, "tax_expense": 1132.35, "pat": 3397.05,
            "total_assets": 92000.00, "fixed_assets": 48500.00,
            "current_assets": 26000.00, "investments": 17500.00,
            "total_equity": 39800.00, "long_term_debt": 30000.00,
            "short_term_debt": 11200.00, "total_debt": 41200.00,
            "current_liabilities": 21000.00, "trade_receivables": 8900.00,
            "inventory": 11200.00, "cash_equivalents": 3800.00,
            "trade_payables": 10800.00,
            "ocf": 8500.00, "capex": -4800.00, "fcff": 3700.00,
        }
    ),
    "FY2023": FinancialStatement(
        entity_id="TSTL001", period="FY2023", statement_type="standalone",
        source="audited", as_of_date=date(2023, 3, 31),
        line_items={
            "revenue_operating": 52100.00, "other_income": 880.00,
            "total_income": 52980.00, "raw_material_cost": 32302.00,
            "employee_cost": 4689.00, "other_expenses": 6252.00,
            "ebitda": 9737.00, "depreciation": 3800.00,
            "ebit": 5937.00, "finance_cost": 2700.00,
            "pbt": 3237.00, "tax_expense": 809.25, "pat": 2427.75,
            "total_assets": 85000.00, "fixed_assets": 45000.00,
            "current_assets": 24000.00, "investments": 16000.00,
            "total_equity": 37200.00, "long_term_debt": 28000.00,
            "short_term_debt": 10500.00, "total_debt": 38500.00,
            "current_liabilities": 19800.00,
            "ocf": 7200.00, "capex": -4300.00, "fcff": 2900.00,
        }
    ),
}

TSTL_PROVISIONAL = FinancialStatement(
    entity_id="TSTL001", period="FY2026_P", statement_type="standalone",
    source="provisional", as_of_date=date(2026, 12, 31),
    line_items={
        "revenue_operating": 68500.00, "ebitda": 14900.00,
        "pat": 5100.00, "total_debt": 42000.00, "total_equity": 46000.00,
        "total_assets": 102000.00,
    }
)

TSTL_FACILITY = FacilityRequest(
    facility_id="FAC_TSTL_001", entity_id="TSTL001",
    case_type=CaseType.NTB, facility_type=FacilityType.WORKING_CAPITAL,
    amount_requested_cr=2500.00,
    purpose="Working capital facility for raw material procurement and operational expenses for Kalinganagar expansion Phase 2",
    tenor_months=12, collateral_value_cr=3500.00, proposed_limit_cr=2500.00,
)

TSTL_COLLATERAL = [
    Collateral(collateral_id="COL_TSTL_01", entity_id="TSTL001",
               collateral_type="Plant & Machinery", description="Blast Furnace Unit 3, Kalinganagar, Odisha",
               market_value_cr=2500.00, forced_sale_value_cr=1750.00,
               valuation_date=date(2026, 6, 15), encumbrance_status="clear"),
    Collateral(collateral_id="COL_TSTL_02", entity_id="TSTL001",
               collateral_type="Inventory", description="Raw material + finished goods steel inventory",
               market_value_cr=1000.00, forced_sale_value_cr=600.00,
               valuation_date=date(2026, 6, 15), encumbrance_status="hypothecated"),
]

TSTL_MARKET_SIGNALS = [
    MarketSignal(entity_id="TSTL001", signal_type="news",
                 headline="Tara Steels commissions 5 MTPA Kalinganagar expansion; EBITDA boost expected",
                 sentiment="positive", severity=RiskSeverity.LOW,
                 source_name="Economic Times", signal_date=date(2026, 10, 5),
                 details="Expansion adds 5 MTPA capacity at industry-best cost structure."),
    MarketSignal(entity_id="TSTL001", signal_type="analyst",
                 headline="CRISIL reaffirms AA/Stable for Tara Steels; deleveraging on track",
                 sentiment="positive", severity=RiskSeverity.LOW,
                 source_name="CRISIL", signal_date=date(2026, 11, 12)),
]


# ═══════════════════════════════════════════════════════════════════════════════
# COMPANY 6: RELIANCE ENERGY LTD (Listed NTB, Energy — HIGH LEVERAGE)
# ═══════════════════════════════════════════════════════════════════════════════

REIL_BORROWER = Borrower(
    entity_id="REIL001",
    company_name="Reliable Energy Industries Ltd",
    cin="L17110MH1973PLC019786",
    pan="AAACR2345B",
    borrower_type=BorrowerType.LISTED,
    sector=Sector.MANUFACTURING,
    subsector="Petroleum Refining & Petrochemicals",
    date_of_incorporation=date(1974, 5, 8),
    registered_state="Maharashtra",
    registered_address="Maker Chambers IV, Nariman Point, Mumbai 400021",
    authorized_capital=15000.00,
    paid_up_capital=6766.00,
    listed_exchange="BSE, NSE",
    nse_symbol="RELENERGY",
    isin="INE002A01018",
    credit_rating="CRISIL AAA/Stable",
    rating_agency="CRISIL",
    employee_count=45000,
    website="www.reliableenergy.com",
)

REIL_GROUP = GroupEntity(
    group_id="GRP_REIL", group_name="Reliable Group",
    parent_entity_id="REIL001",
    entities=["REIL001", "Reliable Jio Infocomm Ltd", "Reliable Retail Ventures Ltd",
              "Reliable Digital Platform Ltd"],
    promoter_holding_pct=50.3, institutional_holding_pct=35.2, public_holding_pct=14.5,
)

REIL_DIRECTORS = [
    DirectorPromoter(din="00001695", name="Mukund D. Ambani", designation="Chairman & Managing Director",
                     entity_id="REIL001", is_promoter=True, net_worth_cr=52000.0),
    DirectorPromoter(din="00002345", name="Nikhil D. Ambani", designation="Non-Executive Director",
                     entity_id="REIL001", is_promoter=True, net_worth_cr=8500.0),
    DirectorPromoter(din="00003456", name="P.M.S. Prasad", designation="Executive Director",
                     entity_id="REIL001", is_promoter=False, net_worth_cr=350.0),
    DirectorPromoter(din="00004567", name="Hital R. Meswani", designation="Executive Director",
                     entity_id="REIL001", is_promoter=False, net_worth_cr=280.0),
]

REIL_FINANCIALS = {
    "FY2025": FinancialStatement(
        entity_id="REIL001", period="FY2025", statement_type="standalone",
        source="audited", as_of_date=date(2025, 3, 31),
        line_items={
            "revenue_operating": 542000.00, "other_income": 18500.00,
            "total_income": 560500.00, "raw_material_cost": 378400.00,
            "employee_cost": 10840.00, "other_expenses": 48780.00,
            "ebitda": 122480.00, "depreciation": 32500.00,
            "ebit": 89980.00, "finance_cost": 25800.00,
            "pbt": 64180.00, "tax_expense": 16045.00, "pat": 48135.00,
            "total_assets": 850000.00, "fixed_assets": 425000.00,
            "current_assets": 185000.00, "investments": 240000.00,
            "total_equity": 485000.00, "long_term_debt": 185000.00,
            "short_term_debt": 65000.00, "total_debt": 250000.00,
            "current_liabilities": 165000.00, "trade_receivables": 42000.00,
            "inventory": 52000.00, "cash_equivalents": 28000.00,
            "trade_payables": 68000.00,
            "ocf": 85000.00, "capex": -42000.00, "fcff": 43000.00,
            "market_cap": 1950000.00, "working_capital": 20000.00,
        }
    ),
    "FY2024": FinancialStatement(
        entity_id="REIL001", period="FY2024", statement_type="standalone",
        source="audited", as_of_date=date(2024, 3, 31),
        line_items={
            "revenue_operating": 498000.00, "other_income": 15200.00,
            "total_income": 513200.00, "raw_material_cost": 353580.00,
            "employee_cost": 9960.00, "other_expenses": 44820.00,
            "ebitda": 104840.00, "depreciation": 29800.00,
            "ebit": 75040.00, "finance_cost": 23500.00,
            "pbt": 51540.00, "tax_expense": 12885.00, "pat": 38655.00,
            "total_assets": 790000.00, "fixed_assets": 395000.00,
            "current_assets": 170000.00, "investments": 225000.00,
            "total_equity": 450000.00, "long_term_debt": 175000.00,
            "short_term_debt": 60000.00, "total_debt": 235000.00,
            "current_liabilities": 155000.00,
            "ocf": 72000.00, "capex": -38000.00, "fcff": 34000.00,
        }
    ),
    "FY2023": FinancialStatement(
        entity_id="REIL001", period="FY2023", statement_type="standalone",
        source="audited", as_of_date=date(2023, 3, 31),
        line_items={
            "revenue_operating": 421000.00, "other_income": 12800.00,
            "total_income": 433800.00, "raw_material_cost": 302320.00,
            "employee_cost": 8840.00, "other_expenses": 37890.00,
            "ebitda": 84750.00, "depreciation": 27200.00,
            "ebit": 57550.00, "finance_cost": 21000.00,
            "pbt": 36550.00, "tax_expense": 9137.50, "pat": 27412.50,
            "total_assets": 720000.00, "fixed_assets": 365000.00,
            "current_assets": 155000.00, "investments": 200000.00,
            "total_equity": 420000.00, "long_term_debt": 165000.00,
            "short_term_debt": 55000.00, "total_debt": 220000.00,
            "current_liabilities": 145000.00,
            "ocf": 62000.00, "capex": -35000.00, "fcff": 27000.00,
        }
    ),
}

REIL_PROVISIONAL = FinancialStatement(
    entity_id="REIL001", period="FY2026_P", statement_type="standalone",
    source="provisional", as_of_date=date(2026, 12, 31),
    line_items={
        "revenue_operating": 580000.00, "ebitda": 135000.00,
        "pat": 55000.00, "total_debt": 240000.00, "total_equity": 520000.00,
        "total_assets": 900000.00,
    }
)

REIL_FACILITY = FacilityRequest(
    facility_id="FAC_REIL_001", entity_id="REIL001",
    case_type=CaseType.NTB, facility_type=FacilityType.TERM_LOAN,
    amount_requested_cr=5000.00,
    purpose="Term loan for new ethylene cracker complex at Jamnagar, Gujarat",
    tenor_months=84, collateral_value_cr=7500.00, proposed_limit_cr=5000.00,
)

REIL_COLLATERAL = [
    Collateral(collateral_id="COL_REIL_01", entity_id="REIL001",
               collateral_type="Plant & Machinery", description="Refinery Unit SEZ Jamnagar",
               market_value_cr=5500.00, forced_sale_value_cr=3850.00,
               valuation_date=date(2026, 7, 20), encumbrance_status="clear"),
    Collateral(collateral_id="COL_REIL_02", entity_id="REIL001",
               collateral_type="Land & Building", description="SEZ land parcel 450 acres Jamnagar",
               market_value_cr=2000.00, forced_sale_value_cr=1400.00,
               valuation_date=date(2026, 7, 20), encumbrance_status="clear"),
]

REIL_MARKET_SIGNALS = [
    MarketSignal(entity_id="REIL001", signal_type="news",
                 headline="Reliable Energy GRM expands to $12.5/bbl; record quarterly EBITDA",
                 sentiment="positive", severity=RiskSeverity.LOW,
                 source_name="Bloomberg Quint", signal_date=date(2026, 10, 22)),
    MarketSignal(entity_id="REIL001", signal_type="analyst",
                 headline="Moody's affirms Baa2 for Reliable Energy; outlook stable",
                 sentiment="positive", severity=RiskSeverity.LOW,
                 source_name="Moody's", signal_date=date(2026, 11, 5)),
]


# ═══════════════════════════════════════════════════════════════════════════════
# COMPANY 7: INFOSYS LIMITED (Listed NTB, IT — ASSET LIGHT, CLEAN)
# ═══════════════════════════════════════════════════════════════════════════════

INFY_BORROWER = Borrower(
    entity_id="INFY001",
    company_name="Infosys Limited",
    cin="L85110KA1981PLC013115",
    pan="AAACI3456C",
    borrower_type=BorrowerType.LISTED,
    sector=Sector.IT_SERVICES,
    subsector="IT Consulting & Software Services",
    date_of_incorporation=date(1981, 7, 2),
    registered_state="Karnataka",
    registered_address="Electronics City, Hosur Road, Bengaluru 560100",
    authorized_capital=2400.00,
    paid_up_capital=2086.00,
    listed_exchange="BSE, NSE",
    nse_symbol="INFY",
    isin="INE009A01021",
    credit_rating="CRISIL AAA/Stable",
    rating_agency="CRISIL",
    employee_count=317240,
    website="www.infosys.com",
)

INFY_GROUP = GroupEntity(
    group_id="GRP_INFY", group_name="Infosys Group",
    parent_entity_id="INFY001",
    entities=["INFY001", "Infosys BPM Ltd", "Infosys Consulting Pte Ltd", "EdgeVerve Systems Ltd"],
    promoter_holding_pct=14.78, institutional_holding_pct=62.5, public_holding_pct=22.72,
)

INFY_DIRECTORS = [
    DirectorPromoter(din="07912940", name="Salil S. Parekh", designation="CEO & Managing Director",
                     entity_id="INFY001", is_promoter=False, net_worth_cr=450.0),
    DirectorPromoter(din="08126573", name="Nilanjan Roy", designation="CFO",
                     entity_id="INFY001", is_promoter=False, net_worth_cr=120.0),
    DirectorPromoter(din="00041059", name="Nandan M. Nilekani", designation="Non-Executive Chairman",
                     entity_id="INFY001", is_promoter=True, net_worth_cr=28000.0),
]

INFY_FINANCIALS = {
    "FY2025": FinancialStatement(
        entity_id="INFY001", period="FY2025", statement_type="standalone",
        source="audited", as_of_date=date(2025, 3, 31),
        line_items={
            "revenue_operating": 153670.00, "other_income": 4250.00,
            "total_income": 157920.00, "raw_material_cost": 3073.00,
            "employee_cost": 92202.00, "other_expenses": 23050.50,
            "ebitda": 39594.50, "depreciation": 4150.00,
            "ebit": 35444.50, "finance_cost": 680.00,
            "pbt": 34764.50, "tax_expense": 8691.13, "pat": 26073.37,
            "total_assets": 128000.00, "fixed_assets": 28000.00,
            "current_assets": 72000.00, "investments": 28000.00,
            "total_equity": 85000.00, "long_term_debt": 2500.00,
            "short_term_debt": 1500.00, "total_debt": 4000.00,
            "current_liabilities": 43000.00, "trade_receivables": 32000.00,
            "inventory": 0.00, "cash_equivalents": 25000.00,
            "trade_payables": 8500.00,
            "ocf": 28500.00, "capex": -4800.00, "fcff": 23700.00,
            "market_cap": 650000.00, "working_capital": 29000.00,
        }
    ),
    "FY2024": FinancialStatement(
        entity_id="INFY001", period="FY2024", statement_type="standalone",
        source="audited", as_of_date=date(2024, 3, 31),
        line_items={
            "revenue_operating": 146767.00, "other_income": 3800.00,
            "total_income": 150567.00, "raw_material_cost": 2935.00,
            "employee_cost": 88060.20, "other_expenses": 22015.05,
            "ebitda": 37556.75, "depreciation": 3900.00,
            "ebit": 33656.75, "finance_cost": 620.00,
            "pbt": 33036.75, "tax_expense": 8259.19, "pat": 24777.56,
            "total_assets": 118000.00, "fixed_assets": 26500.00,
            "current_assets": 66500.00, "investments": 25000.00,
            "total_equity": 78000.00, "long_term_debt": 2200.00,
            "short_term_debt": 1300.00, "total_debt": 3500.00,
            "current_liabilities": 40000.00,
            "ocf": 26000.00, "capex": -4200.00, "fcff": 21800.00,
        }
    ),
    "FY2023": FinancialStatement(
        entity_id="INFY001", period="FY2023", statement_type="standalone",
        source="audited", as_of_date=date(2023, 3, 31),
        line_items={
            "revenue_operating": 121641.00, "other_income": 3200.00,
            "total_income": 124841.00, "raw_material_cost": 2433.00,
            "employee_cost": 72984.60, "other_expenses": 18246.15,
            "ebitda": 31177.25, "depreciation": 3600.00,
            "ebit": 27577.25, "finance_cost": 550.00,
            "pbt": 27027.25, "tax_expense": 6756.81, "pat": 20270.44,
            "total_assets": 105000.00, "fixed_assets": 24000.00,
            "current_assets": 59000.00, "investments": 22000.00,
            "total_equity": 72000.00, "long_term_debt": 2000.00,
            "short_term_debt": 1000.00, "total_debt": 3000.00,
            "current_liabilities": 33000.00,
            "ocf": 22000.00, "capex": -3800.00, "fcff": 18200.00,
        }
    ),
}

INFY_PROVISIONAL = FinancialStatement(
    entity_id="INFY001", period="FY2026_P", statement_type="standalone",
    source="provisional", as_of_date=date(2026, 12, 31),
    line_items={
        "revenue_operating": 162000.00, "ebitda": 42000.00,
        "pat": 28000.00, "total_debt": 3800.00, "total_equity": 92000.00,
        "total_assets": 138000.00,
    }
)

INFY_FACILITY = FacilityRequest(
    facility_id="FAC_INFY_001", entity_id="INFY001",
    case_type=CaseType.NTB, facility_type=FacilityType.WORKING_CAPITAL,
    amount_requested_cr=500.00,
    purpose="Non-fund based working capital (BG/LC) for client contract performance guarantees",
    tenor_months=12, collateral_value_cr=0.00, proposed_limit_cr=500.00,
)

INFY_COLLATERAL = [
    Collateral(collateral_id="COL_INFY_01", entity_id="INFY001",
               collateral_type="Fixed Deposits", description="FD lien with SBI for BG margin",
               market_value_cr=125.00, forced_sale_value_cr=125.00,
               valuation_date=date(2026, 8, 1), encumbrance_status="clear"),
]

INFY_MARKET_SIGNALS = [
    MarketSignal(entity_id="INFY001", signal_type="news",
                 headline="Infosys bags mega $2B deal from European telecom major for digital transformation",
                 sentiment="positive", severity=RiskSeverity.LOW,
                 source_name="Mint", signal_date=date(2026, 9, 18)),
    MarketSignal(entity_id="INFY001", signal_type="analyst",
                 headline="CRISIL AAA/Stable reaffirmed for Infosys; industry-best cash generation noted",
                 sentiment="positive", severity=RiskSeverity.LOW,
                 source_name="CRISIL", signal_date=date(2026, 10, 8)),
]


# ═══════════════════════════════════════════════════════════════════════════════
# COMPANY 8: ADANI PORTS LTD (Listed NTB, Infrastructure — GROWTH)
# ═══════════════════════════════════════════════════════════════════════════════

ADPT_BORROWER = Borrower(
    entity_id="ADPT001",
    company_name="Advik Ports & SEZ Ltd",
    cin="L63090GJ1998PLC034182",
    pan="AAACA4567D",
    borrower_type=BorrowerType.LISTED,
    sector=Sector.INFRASTRUCTURE,
    subsector="Ports & Logistics",
    date_of_incorporation=date(1999, 5, 26),
    registered_state="Gujarat",
    registered_address="Advik House, Nr Mithakhali Circle, Ahmedabad 380009",
    authorized_capital=2200.00,
    paid_up_capital=2164.00,
    listed_exchange="BSE, NSE",
    nse_symbol="ADVIKPORTS",
    isin="INE742F01042",
    credit_rating="ICRA AA+/Stable",
    rating_agency="ICRA",
    employee_count=18500,
    website="www.advikports.com",
)

ADPT_GROUP = GroupEntity(
    group_id="GRP_ADPT", group_name="Advik Group",
    parent_entity_id="ADPT001",
    entities=["ADPT001", "Advik Enterprises Ltd", "Advik Green Energy Ltd",
              "Advik Power Ltd", "Advik Transmission Ltd"],
    promoter_holding_pct=65.9, institutional_holding_pct=22.1, public_holding_pct=12.0,
)

ADPT_DIRECTORS = [
    DirectorPromoter(din="00006789", name="Karan S. Adani", designation="Managing Director",
                     entity_id="ADPT001", is_promoter=True, net_worth_cr=35000.0,
                     other_directorships=["Advik Logistics Ltd", "Advik Agri Fresh Ltd"]),
    DirectorPromoter(din="00007890", name="Rajesh S. Adani", designation="Chairman",
                     entity_id="ADPT001", is_promoter=True, net_worth_cr=95000.0),
    DirectorPromoter(din="00008901", name="Subrata Talukdar", designation="Independent Director",
                     entity_id="ADPT001", is_promoter=False, net_worth_cr=55.0),
]

ADPT_FINANCIALS = {
    "FY2025": FinancialStatement(
        entity_id="ADPT001", period="FY2025", statement_type="standalone",
        source="audited", as_of_date=date(2025, 3, 31),
        line_items={
            "revenue_operating": 26500.00, "other_income": 2800.00,
            "total_income": 29300.00, "raw_material_cost": 2650.00,
            "employee_cost": 1855.00, "other_expenses": 5300.00,
            "ebitda": 19495.00, "depreciation": 4500.00,
            "ebit": 14995.00, "finance_cost": 5800.00,
            "pbt": 9195.00, "tax_expense": 2298.75, "pat": 6896.25,
            "total_assets": 85000.00, "fixed_assets": 52000.00,
            "current_assets": 18000.00, "investments": 15000.00,
            "total_equity": 35000.00, "long_term_debt": 32000.00,
            "short_term_debt": 8000.00, "total_debt": 40000.00,
            "current_liabilities": 18000.00, "trade_receivables": 5200.00,
            "inventory": 1800.00, "cash_equivalents": 6500.00,
            "trade_payables": 4500.00,
            "ocf": 16000.00, "capex": -8500.00, "fcff": 7500.00,
            "market_cap": 265000.00, "working_capital": 0.00,
        }
    ),
    "FY2024": FinancialStatement(
        entity_id="ADPT001", period="FY2024", statement_type="standalone",
        source="audited", as_of_date=date(2024, 3, 31),
        line_items={
            "revenue_operating": 22800.00, "other_income": 2200.00,
            "total_income": 25000.00, "raw_material_cost": 2280.00,
            "employee_cost": 1596.00, "other_expenses": 4560.00,
            "ebitda": 16564.00, "depreciation": 4100.00,
            "ebit": 12464.00, "finance_cost": 5200.00,
            "pbt": 7264.00, "tax_expense": 1816.00, "pat": 5448.00,
            "total_assets": 78000.00, "fixed_assets": 48000.00,
            "current_assets": 16000.00, "investments": 14000.00,
            "total_equity": 31000.00, "long_term_debt": 30000.00,
            "short_term_debt": 7500.00, "total_debt": 37500.00,
            "current_liabilities": 17000.00,
            "ocf": 13500.00, "capex": -7200.00, "fcff": 6300.00,
        }
    ),
    "FY2023": FinancialStatement(
        entity_id="ADPT001", period="FY2023", statement_type="standalone",
        source="audited", as_of_date=date(2023, 3, 31),
        line_items={
            "revenue_operating": 18900.00, "other_income": 1800.00,
            "total_income": 20700.00, "raw_material_cost": 1890.00,
            "employee_cost": 1323.00, "other_expenses": 3780.00,
            "ebitda": 13707.00, "depreciation": 3700.00,
            "ebit": 10007.00, "finance_cost": 4600.00,
            "pbt": 5407.00, "tax_expense": 1351.75, "pat": 4055.25,
            "total_assets": 72000.00, "fixed_assets": 44000.00,
            "current_assets": 15000.00, "investments": 13000.00,
            "total_equity": 28000.00, "long_term_debt": 28000.00,
            "short_term_debt": 7000.00, "total_debt": 35000.00,
            "current_liabilities": 16000.00,
            "ocf": 11000.00, "capex": -6200.00, "fcff": 4800.00,
        }
    ),
}

ADPT_PROVISIONAL = FinancialStatement(
    entity_id="ADPT001", period="FY2026_P", statement_type="standalone",
    source="provisional", as_of_date=date(2026, 12, 31),
    line_items={
        "revenue_operating": 30500.00, "ebitda": 22000.00,
        "pat": 8200.00, "total_debt": 38000.00, "total_equity": 40000.00,
        "total_assets": 92000.00,
    }
)

ADPT_FACILITY = FacilityRequest(
    facility_id="FAC_ADPT_001", entity_id="ADPT001",
    case_type=CaseType.NTB, facility_type=FacilityType.PROJECT_FINANCE,
    amount_requested_cr=3000.00,
    purpose="Project finance for Vizhinjam International Container Transshipment Terminal Phase 2",
    tenor_months=120, collateral_value_cr=4200.00, proposed_limit_cr=3000.00,
)

ADPT_COLLATERAL = [
    Collateral(collateral_id="COL_ADPT_01", entity_id="ADPT001",
               collateral_type="Land & Building", description="Vizhinjam Port terminal building + land lease",
               market_value_cr=3000.00, forced_sale_value_cr=2100.00,
               valuation_date=date(2026, 5, 10), encumbrance_status="clear"),
    Collateral(collateral_id="COL_ADPT_02", entity_id="ADPT001",
               collateral_type="Plant & Machinery", description="Container cranes and port handling equipment",
               market_value_cr=1200.00, forced_sale_value_cr=720.00,
               valuation_date=date(2026, 5, 10), encumbrance_status="clear"),
]

ADPT_MARKET_SIGNALS = [
    MarketSignal(entity_id="ADPT001", signal_type="news",
                 headline="Hindenburg report raises governance concerns over Advik Group promoter entities",
                 sentiment="negative", severity=RiskSeverity.HIGH,
                 source_name="Hindenburg Research", signal_date=date(2026, 1, 24),
                 details="Short seller alleges stock manipulation and accounting fraud across group companies."),
    MarketSignal(entity_id="ADPT001", signal_type="news",
                 headline="Supreme Court panel clears Advik Group of securities fraud allegations",
                 sentiment="positive", severity=RiskSeverity.MEDIUM,
                 source_name="LiveLaw", signal_date=date(2026, 4, 15)),
    MarketSignal(entity_id="ADPT001", signal_type="analyst",
                 headline="ICRA reaffirms AA+/Stable; robust cargo volumes support credit profile",
                 sentiment="positive", severity=RiskSeverity.LOW,
                 source_name="ICRA", signal_date=date(2026, 8, 22)),
]


# ═══════════════════════════════════════════════════════════════════════════════
# COMPANY 9: BAJAJ FINANCE LTD (Listed NTB, NBFC — HIGH GROWTH)
# ═══════════════════════════════════════════════════════════════════════════════

BJFN_BORROWER = Borrower(
    entity_id="BJFN001",
    company_name="Bajrang Finance Ltd",
    cin="L65910MH1987PLC042961",
    pan="AABCB5678E",
    borrower_type=BorrowerType.LISTED,
    sector=Sector.NBFC,
    subsector="Diversified NBFC",
    date_of_incorporation=date(1988, 3, 25),
    registered_state="Maharashtra",
    registered_address="Bajrang Auto Complex, Mumbai-Pune Road, Akurdi, Pune 411035",
    authorized_capital=500.00,
    paid_up_capital=123.16,
    listed_exchange="BSE, NSE",
    nse_symbol="BAJFINANCE",
    isin="INE296A01024",
    credit_rating="CRISIL AAA/Stable",
    rating_agency="CRISIL",
    employee_count=42000,
    website="www.bajrangfinance.com",
)

BJFN_GROUP = GroupEntity(
    group_id="GRP_BJFN", group_name="Bajrang Group",
    parent_entity_id="BJFN001",
    entities=["BJFN001", "Bajrang Finserv Ltd", "Bajrang Housing Finance Ltd",
              "Bajrang Financial Securities Ltd"],
    promoter_holding_pct=54.7, institutional_holding_pct=32.8, public_holding_pct=12.5,
)

BJFN_DIRECTORS = [
    DirectorPromoter(din="00009012", name="Sanjiv Bajaj", designation="Non-Executive Chairman",
                     entity_id="BJFN001", is_promoter=True, net_worth_cr=18000.0),
    DirectorPromoter(din="00010123", name="Rajeev Jain", designation="Managing Director",
                     entity_id="BJFN001", is_promoter=False, net_worth_cr=2500.0),
    DirectorPromoter(din="00011234", name="Anami N. Roy", designation="Independent Director",
                     entity_id="BJFN001", is_promoter=False, net_worth_cr=35.0),
]

BJFN_FINANCIALS = {
    "FY2025": FinancialStatement(
        entity_id="BJFN001", period="FY2025", statement_type="standalone",
        source="audited", as_of_date=date(2025, 3, 31),
        line_items={
            "revenue_operating": 52500.00, "other_income": 1800.00,
            "total_income": 54300.00, "raw_material_cost": 0.00,
            "employee_cost": 6825.00, "other_expenses": 8400.00,
            "ebitda": 39075.00, "depreciation": 1050.00,
            "ebit": 38025.00, "finance_cost": 22050.00,
            "pbt": 15975.00, "tax_expense": 3993.75, "pat": 11981.25,
            "total_assets": 310000.00, "fixed_assets": 5200.00,
            "current_assets": 42000.00, "investments": 28000.00,
            "total_equity": 62000.00, "long_term_debt": 150000.00,
            "short_term_debt": 65000.00, "total_debt": 215000.00,
            "current_liabilities": 48000.00, "trade_receivables": 0.00,
            "inventory": 0.00, "cash_equivalents": 18000.00,
            "trade_payables": 5200.00,
            "ocf": 25000.00, "capex": -1500.00, "fcff": 23500.00,
            "market_cap": 450000.00, "working_capital": -6000.00,
            "loan_book_cr": 265000.00, "gnpa_pct": 0.95,
            "nnpa_pct": 0.35, "provision_coverage_pct": 63.2,
            "capital_adequacy_pct": 22.8,
        }
    ),
    "FY2024": FinancialStatement(
        entity_id="BJFN001", period="FY2024", statement_type="standalone",
        source="audited", as_of_date=date(2024, 3, 31),
        line_items={
            "revenue_operating": 42000.00, "other_income": 1500.00,
            "total_income": 43500.00, "employee_cost": 5460.00,
            "other_expenses": 6720.00, "ebitda": 31320.00,
            "depreciation": 840.00, "ebit": 30480.00,
            "finance_cost": 17640.00, "pbt": 12840.00,
            "tax_expense": 3210.00, "pat": 9630.00,
            "total_assets": 258000.00, "total_equity": 52000.00,
            "long_term_debt": 126000.00, "short_term_debt": 52000.00,
            "total_debt": 178000.00,
            "ocf": 20000.00, "capex": -1200.00, "fcff": 18800.00,
        }
    ),
    "FY2023": FinancialStatement(
        entity_id="BJFN001", period="FY2023", statement_type="standalone",
        source="audited", as_of_date=date(2023, 3, 31),
        line_items={
            "revenue_operating": 33500.00, "other_income": 1200.00,
            "total_income": 34700.00, "employee_cost": 4355.00,
            "other_expenses": 5360.00, "ebitda": 24985.00,
            "depreciation": 670.00, "ebit": 24315.00,
            "finance_cost": 14740.00, "pbt": 9575.00,
            "tax_expense": 2393.75, "pat": 7181.25,
            "total_assets": 210000.00, "total_equity": 44000.00,
            "long_term_debt": 102000.00, "short_term_debt": 42000.00,
            "total_debt": 144000.00,
            "ocf": 15000.00, "capex": -900.00, "fcff": 14100.00,
        }
    ),
}

BJFN_PROVISIONAL = FinancialStatement(
    entity_id="BJFN001", period="FY2026_P", statement_type="standalone",
    source="provisional", as_of_date=date(2026, 12, 31),
    line_items={
        "revenue_operating": 62000.00, "ebitda": 45000.00,
        "pat": 14500.00, "total_debt": 245000.00, "total_equity": 72000.00,
        "total_assets": 360000.00,
    }
)

BJFN_FACILITY = FacilityRequest(
    facility_id="FAC_BJFN_001", entity_id="BJFN001",
    case_type=CaseType.NTB, facility_type=FacilityType.TERM_LOAN,
    amount_requested_cr=2000.00,
    purpose="Subordinated debt for regulatory Tier-II capital augmentation per RBI NBFC norms",
    tenor_months=60, collateral_value_cr=0.00, proposed_limit_cr=2000.00,
)

BJFN_COLLATERAL = [
    Collateral(collateral_id="COL_BJFN_01", entity_id="BJFN001",
               collateral_type="Receivables Pool", description="Securitized retail loan receivables pool",
               market_value_cr=3000.00, forced_sale_value_cr=2400.00,
               valuation_date=date(2026, 9, 15), encumbrance_status="hypothecated"),
]

BJFN_MARKET_SIGNALS = [
    MarketSignal(entity_id="BJFN001", signal_type="news",
                 headline="Bajrang Finance AUM crosses Rs 3 lakh crore; GNPA stable at sub-1%",
                 sentiment="positive", severity=RiskSeverity.LOW,
                 source_name="Business Standard", signal_date=date(2026, 10, 28)),
    MarketSignal(entity_id="BJFN001", signal_type="analyst",
                 headline="RBI expresses concern over unsecured retail lending growth across NBFCs",
                 sentiment="negative", severity=RiskSeverity.MEDIUM,
                 source_name="RBI Bulletin", signal_date=date(2026, 11, 15)),
]


# ═══════════════════════════════════════════════════════════════════════════════
# COMPANY 10: CIPLA PHARMA LTD (Listed NTB, Pharma — CLEAN)
# ═══════════════════════════════════════════════════════════════════════════════

CIPL_BORROWER = Borrower(
    entity_id="CIPL001",
    company_name="Ciplex Pharmaceuticals Ltd",
    cin="L24239MH1935PLC002380",
    pan="AAACC6789F",
    borrower_type=BorrowerType.LISTED,
    sector=Sector.PHARMA,
    subsector="Formulations & Generic Drugs",
    date_of_incorporation=date(1936, 8, 22),
    registered_state="Maharashtra",
    registered_address="Ciplex House, Peninsula Business Park, Ganpatrao Kadam Marg, Mumbai 400013",
    authorized_capital=400.00,
    paid_up_capital=161.02,
    listed_exchange="BSE, NSE",
    nse_symbol="CPLXPHARMA",
    isin="INE059A01026",
    credit_rating="CRISIL AA+/Stable",
    rating_agency="CRISIL",
    employee_count=25000,
    website="www.ciplexpharma.com",
)

CIPL_GROUP = GroupEntity(
    group_id="GRP_CIPL", group_name="Ciplex Group",
    parent_entity_id="CIPL001",
    entities=["CIPL001", "Ciplex Health Ltd", "Ciplex Medpro SA"],
    promoter_holding_pct=33.5, institutional_holding_pct=48.2, public_holding_pct=18.3,
)

CIPL_DIRECTORS = [
    DirectorPromoter(din="00012345", name="Umang Vohra", designation="Managing Director & CEO",
                     entity_id="CIPL001", is_promoter=False, net_worth_cr=320.0),
    DirectorPromoter(din="00013456", name="Y.K. Hamied", designation="Non-Executive Chairman",
                     entity_id="CIPL001", is_promoter=True, net_worth_cr=14500.0),
    DirectorPromoter(din="00014567", name="Ashok Kumar Malhotra", designation="Independent Director",
                     entity_id="CIPL001", is_promoter=False, net_worth_cr=42.0),
]

CIPL_FINANCIALS = {
    "FY2025": FinancialStatement(
        entity_id="CIPL001", period="FY2025", statement_type="standalone",
        source="audited", as_of_date=date(2025, 3, 31),
        line_items={
            "revenue_operating": 22500.00, "other_income": 980.00,
            "total_income": 23480.00, "raw_material_cost": 7875.00,
            "employee_cost": 3375.00, "other_expenses": 4500.00,
            "ebitda": 7730.00, "depreciation": 1350.00,
            "ebit": 6380.00, "finance_cost": 280.00,
            "pbt": 6100.00, "tax_expense": 1525.00, "pat": 4575.00,
            "total_assets": 32000.00, "fixed_assets": 9500.00,
            "current_assets": 14500.00, "investments": 8000.00,
            "total_equity": 22000.00, "long_term_debt": 1200.00,
            "short_term_debt": 800.00, "total_debt": 2000.00,
            "current_liabilities": 10000.00, "trade_receivables": 5800.00,
            "inventory": 4200.00, "cash_equivalents": 2800.00,
            "trade_payables": 3200.00,
            "ocf": 5500.00, "capex": -2000.00, "fcff": 3500.00,
            "market_cap": 98000.00, "working_capital": 4500.00,
        }
    ),
    "FY2024": FinancialStatement(
        entity_id="CIPL001", period="FY2024", statement_type="standalone",
        source="audited", as_of_date=date(2024, 3, 31),
        line_items={
            "revenue_operating": 20800.00, "other_income": 850.00,
            "total_income": 21650.00, "raw_material_cost": 7280.00,
            "employee_cost": 3120.00, "other_expenses": 4160.00,
            "ebitda": 7090.00, "depreciation": 1250.00,
            "ebit": 5840.00, "finance_cost": 250.00,
            "pbt": 5590.00, "tax_expense": 1397.50, "pat": 4192.50,
            "total_assets": 29500.00, "total_equity": 20000.00,
            "total_debt": 1800.00,
            "ocf": 4800.00, "capex": -1800.00, "fcff": 3000.00,
        }
    ),
    "FY2023": FinancialStatement(
        entity_id="CIPL001", period="FY2023", statement_type="standalone",
        source="audited", as_of_date=date(2023, 3, 31),
        line_items={
            "revenue_operating": 18500.00, "other_income": 720.00,
            "total_income": 19220.00, "raw_material_cost": 6475.00,
            "employee_cost": 2775.00, "other_expenses": 3700.00,
            "ebitda": 6270.00, "depreciation": 1100.00,
            "ebit": 5170.00, "finance_cost": 220.00,
            "pbt": 4950.00, "tax_expense": 1237.50, "pat": 3712.50,
            "total_assets": 27000.00, "total_equity": 18000.00,
            "total_debt": 1500.00,
            "ocf": 4200.00, "capex": -1500.00, "fcff": 2700.00,
        }
    ),
}

CIPL_PROVISIONAL = FinancialStatement(
    entity_id="CIPL001", period="FY2026_P", statement_type="standalone",
    source="provisional", as_of_date=date(2026, 12, 31),
    line_items={
        "revenue_operating": 24500.00, "ebitda": 8500.00,
        "pat": 5100.00, "total_debt": 1800.00, "total_equity": 24500.00,
        "total_assets": 35000.00,
    }
)

CIPL_FACILITY = FacilityRequest(
    facility_id="FAC_CIPL_001", entity_id="CIPL001",
    case_type=CaseType.NTB, facility_type=FacilityType.WORKING_CAPITAL,
    amount_requested_cr=300.00,
    purpose="Working capital for US FDA approved inhalation product launch inventory buildup",
    tenor_months=12, collateral_value_cr=450.00, proposed_limit_cr=300.00,
)

CIPL_COLLATERAL = [
    Collateral(collateral_id="COL_CIPL_01", entity_id="CIPL001",
               collateral_type="Inventory", description="Finished goods and API inventory at Goa plant",
               market_value_cr=450.00, forced_sale_value_cr=315.00,
               valuation_date=date(2026, 7, 1), encumbrance_status="clear"),
]

CIPL_MARKET_SIGNALS = [
    MarketSignal(entity_id="CIPL001", signal_type="news",
                 headline="Ciplex Pharma gets US FDA approval for generic Advair; $5B market opportunity",
                 sentiment="positive", severity=RiskSeverity.LOW,
                 source_name="CNBC TV18", signal_date=date(2026, 8, 10)),
    MarketSignal(entity_id="CIPL001", signal_type="analyst",
                 headline="CRISIL upgrades Ciplex to AA+/Stable from AA/Positive",
                 sentiment="positive", severity=RiskSeverity.LOW,
                 source_name="CRISIL", signal_date=date(2026, 9, 20)),
]


# ═══════════════════════════════════════════════════════════════════════════════
# COMPANY 11: DLF REALTY LTD (Listed ETB, Real Estate — STRESSED)
# ═══════════════════════════════════════════════════════════════════════════════

DLFR_BORROWER = Borrower(
    entity_id="DLFR001",
    company_name="Delhi Land & Realty Ltd",
    cin="L70101HR1963PLC002484",
    pan="AAACD7890G",
    borrower_type=BorrowerType.LISTED,
    sector=Sector.REAL_ESTATE,
    subsector="Residential & Commercial Real Estate",
    date_of_incorporation=date(1964, 3, 15),
    registered_state="Haryana",
    registered_address="Shopping Mall, 3rd Floor, Arjun Marg, Phase I, DLF City, Gurgaon 122002",
    authorized_capital=350.00,
    paid_up_capital=247.82,
    listed_exchange="BSE, NSE",
    nse_symbol="DLFREALTY",
    isin="INE271C01023",
    credit_rating="CARE A-/Negative",
    rating_agency="CARE",
    employee_count=4200,
    website="www.delrealty.com",
)

DLFR_GROUP = GroupEntity(
    group_id="GRP_DLFR", group_name="DL Realty Group",
    parent_entity_id="DLFR001",
    entities=["DLFR001", "DL Cyber City Developers Ltd", "DL Home Developers Ltd",
              "DL Assets Pvt Ltd", "Hines DL JV Ltd"],
    promoter_holding_pct=74.1, institutional_holding_pct=15.2, public_holding_pct=10.7,
)

DLFR_DIRECTORS = [
    DirectorPromoter(din="00015678", name="Rajiv K. Singh", designation="Managing Director",
                     entity_id="DLFR001", is_promoter=False, net_worth_cr=180.0),
    DirectorPromoter(din="00016789", name="K.P. Singh", designation="Chairman Emeritus",
                     entity_id="DLFR001", is_promoter=True, net_worth_cr=22000.0,
                     other_directorships=["DL Cyber City Developers Ltd", "DL Home Developers Ltd"]),
    DirectorPromoter(din="00017890", name="Pia Singh", designation="Non-Executive Director",
                     entity_id="DLFR001", is_promoter=True, net_worth_cr=8500.0),
]

DLFR_FINANCIALS = {
    "FY2025": FinancialStatement(
        entity_id="DLFR001", period="FY2025", statement_type="standalone",
        source="audited", as_of_date=date(2025, 3, 31),
        line_items={
            "revenue_operating": 6200.00, "other_income": 480.00,
            "total_income": 6680.00, "raw_material_cost": 2790.00,
            "employee_cost": 496.00, "other_expenses": 1240.00,
            "ebitda": 2154.00, "depreciation": 320.00,
            "ebit": 1834.00, "finance_cost": 1450.00,
            "pbt": 384.00, "tax_expense": 96.00, "pat": 288.00,
            "total_assets": 45000.00, "fixed_assets": 8500.00,
            "current_assets": 28000.00, "investments": 8500.00,
            "total_equity": 18000.00, "long_term_debt": 14500.00,
            "short_term_debt": 5500.00, "total_debt": 20000.00,
            "current_liabilities": 12000.00, "trade_receivables": 4800.00,
            "inventory": 18500.00, "cash_equivalents": 1200.00,
            "trade_payables": 6500.00,
            "ocf": 1800.00, "capex": -500.00, "fcff": 1300.00,
            "market_cap": 42000.00, "working_capital": 16000.00,
        }
    ),
    "FY2024": FinancialStatement(
        entity_id="DLFR001", period="FY2024", statement_type="standalone",
        source="audited", as_of_date=date(2024, 3, 31),
        line_items={
            "revenue_operating": 5800.00, "other_income": 420.00,
            "total_income": 6220.00, "raw_material_cost": 2610.00,
            "employee_cost": 464.00, "other_expenses": 1160.00,
            "ebitda": 1986.00, "depreciation": 300.00,
            "ebit": 1686.00, "finance_cost": 1520.00,
            "pbt": 166.00, "tax_expense": 41.50, "pat": 124.50,
            "total_assets": 44000.00, "total_equity": 17500.00,
            "total_debt": 20500.00,
            "ocf": 1500.00, "capex": -450.00, "fcff": 1050.00,
        }
    ),
    "FY2023": FinancialStatement(
        entity_id="DLFR001", period="FY2023", statement_type="standalone",
        source="audited", as_of_date=date(2023, 3, 31),
        line_items={
            "revenue_operating": 5200.00, "other_income": 380.00,
            "total_income": 5580.00, "raw_material_cost": 2340.00,
            "employee_cost": 416.00, "other_expenses": 1040.00,
            "ebitda": 1784.00, "depreciation": 280.00,
            "ebit": 1504.00, "finance_cost": 1580.00,
            "pbt": -76.00, "tax_expense": 0.00, "pat": -76.00,
            "total_assets": 43500.00, "total_equity": 17000.00,
            "total_debt": 21000.00,
            "ocf": 1200.00, "capex": -400.00, "fcff": 800.00,
        }
    ),
}

DLFR_PROVISIONAL = FinancialStatement(
    entity_id="DLFR001", period="FY2026_P", statement_type="standalone",
    source="provisional", as_of_date=date(2026, 12, 31),
    line_items={
        "revenue_operating": 7000.00, "ebitda": 2500.00,
        "pat": 450.00, "total_debt": 19000.00, "total_equity": 19000.00,
        "total_assets": 46000.00,
    }
)

# INTENTIONAL MISMATCH: Exchange filing shows much weaker Q3
DLFR_EXCHANGE_FILING = FinancialStatement(
    entity_id="DLFR001", period="FY2026_Q3", statement_type="standalone",
    source="exchange", as_of_date=date(2025, 12, 31),
    line_items={
        "revenue_operating": 4200.00,
        "ebitda": 1200.00,
        "pat": -150.00,
        "total_debt": 21500.00,
        "total_equity": 17200.00,
    }
)

DLFR_FACILITY = FacilityRequest(
    facility_id="FAC_DLFR_001", entity_id="DLFR001",
    case_type=CaseType.ETB, facility_type=FacilityType.WORKING_CAPITAL,
    amount_requested_cr=500.00,
    purpose="Enhancement of existing working capital limit for new residential project Phase V launch at Gurugram",
    tenor_months=24, collateral_value_cr=800.00,
    existing_limit_cr=1200.00, proposed_limit_cr=1700.00,
)

DLFR_EXISTING_EXPOSURE = [
    ExistingExposure(facility_id="EXP_DLFR_01", entity_id="DLFR001",
                     facility_type="working_capital", sanctioned_limit_cr=1200.00,
                     outstanding_cr=1140.00, utilization_pct=95.0, overdue_days=0),
    ExistingExposure(facility_id="EXP_DLFR_02", entity_id="DLFR001",
                     facility_type="term_loan", sanctioned_limit_cr=800.00,
                     outstanding_cr=620.00, utilization_pct=77.5, overdue_days=22),
]

DLFR_CONDUCT = [
    ConductRecord(entity_id="DLFR001", period="Q1_FY2026",
                   avg_bank_balance_cr=4.5, credit_turnover_cr=52.0,
                   debit_turnover_cr=51.2, cheque_returns=3,
                   limit_utilization_pct=92.0, overdue_instances=1,
                   max_overdue_days=12, dpd_30_count=1, dpd_60_count=0, dpd_90_count=0),
    ConductRecord(entity_id="DLFR001", period="Q2_FY2026",
                   avg_bank_balance_cr=3.8, credit_turnover_cr=48.0,
                   debit_turnover_cr=49.5, cheque_returns=5,
                   limit_utilization_pct=94.0, overdue_instances=2,
                   max_overdue_days=18, dpd_30_count=1, dpd_60_count=0, dpd_90_count=0),
    ConductRecord(entity_id="DLFR001", period="Q3_FY2026",
                   avg_bank_balance_cr=2.9, credit_turnover_cr=42.0,
                   debit_turnover_cr=44.8, cheque_returns=8,
                   limit_utilization_pct=96.0, overdue_instances=3,
                   max_overdue_days=25, dpd_30_count=2, dpd_60_count=0, dpd_90_count=0),
    ConductRecord(entity_id="DLFR001", period="Q4_FY2026",
                   avg_bank_balance_cr=2.1, credit_turnover_cr=38.0,
                   debit_turnover_cr=40.2, cheque_returns=11,
                   limit_utilization_pct=98.0, overdue_instances=4,
                   max_overdue_days=32, dpd_30_count=3, dpd_60_count=1, dpd_90_count=0),
]

DLFR_COVENANTS = [
    CovenantRecord(entity_id="DLFR001", covenant_type="DSCR", required_value=">=1.20",
                   actual_value="1.08", compliance_status="breached", period="Q3_FY2026",
                   breach_details="DSCR fell below 1.20x due to slow sales velocity"),
    CovenantRecord(entity_id="DLFR001", covenant_type="Debt/Equity", required_value="<=1.50",
                   actual_value="1.11", compliance_status="compliant", period="Q3_FY2026"),
    CovenantRecord(entity_id="DLFR001", covenant_type="Max Cheque Returns", required_value="<=5/quarter",
                   actual_value="11", compliance_status="breached", period="Q4_FY2026",
                   breach_details="Cheque returns spiked due to collection delays from home buyers"),
]

DLFR_COLLATERAL = [
    Collateral(collateral_id="COL_DLFR_01", entity_id="DLFR001",
               collateral_type="Land & Building", description="Plot at Sector 63, Gurugram for Phase V project",
               market_value_cr=600.00, forced_sale_value_cr=420.00,
               valuation_date=date(2026, 6, 1), encumbrance_status="clear"),
    Collateral(collateral_id="COL_DLFR_02", entity_id="DLFR001",
               collateral_type="Receivables Pool", description="Unsold inventory receivables from Phase III",
               market_value_cr=200.00, forced_sale_value_cr=120.00,
               valuation_date=date(2026, 6, 1), encumbrance_status="hypothecated"),
]

DLFR_MARKET_SIGNALS = [
    MarketSignal(entity_id="DLFR001", signal_type="news",
                 headline="CARE downgrades Delhi Land & Realty to A-/Negative; debt servicing concerns",
                 sentiment="negative", severity=RiskSeverity.HIGH,
                 source_name="CARE Ratings", signal_date=date(2026, 9, 5),
                 details="Rating downgrade driven by slowing sales velocity, high inventory and stretched debt metrics."),
    MarketSignal(entity_id="DLFR001", signal_type="social",
                 headline="Home buyer association files NCLT petition against DL Realty for delivery delays",
                 sentiment="negative", severity=RiskSeverity.MEDIUM,
                 source_name="Money Control Forum", signal_date=date(2026, 10, 18)),
    MarketSignal(entity_id="DLFR001", signal_type="news",
                 headline="Gurugram real estate sees 15% pickup in new launches; DL poised to benefit",
                 sentiment="positive", severity=RiskSeverity.LOW,
                 source_name="ET Realty", signal_date=date(2026, 11, 8)),
]


# ═══════════════════════════════════════════════════════════════════════════════
# COMPANY 12: JSW ALLOYS LTD (Listed NTB, Steel — CYCLICAL)
# ═══════════════════════════════════════════════════════════════════════════════

JSWL_BORROWER = Borrower(
    entity_id="JSWL001",
    company_name="JSW Alloys & Steel Ltd",
    cin="L27102MH1994PLC083190",
    pan="AAACJ8901H",
    borrower_type=BorrowerType.LISTED,
    sector=Sector.MANUFACTURING,
    subsector="Alloy & Special Steels",
    date_of_incorporation=date(1995, 3, 15),
    registered_state="Maharashtra",
    registered_address="JSW Centre, Bandra Kurla Complex, Mumbai 400051",
    authorized_capital=550.00,
    paid_up_capital=242.12,
    listed_exchange="BSE, NSE",
    nse_symbol="JSWALLOYS",
    isin="INE019A01038",
    credit_rating="ICRA AA/Stable",
    rating_agency="ICRA",
    employee_count=15500,
    website="www.jswalloys.com",
)

JSWL_GROUP = GroupEntity(
    group_id="GRP_JSWL", group_name="JSW Alloys Group",
    parent_entity_id="JSWL001",
    entities=["JSWL001", "JSW Energy Corp Ltd", "JSW Cement Ltd",
              "JSW Infrastructure Ltd"],
    promoter_holding_pct=42.3, institutional_holding_pct=38.5, public_holding_pct=19.2,
)

JSWL_DIRECTORS = [
    DirectorPromoter(din="00018901", name="Sajjan Jindal", designation="Chairman & Managing Director",
                     entity_id="JSWL001", is_promoter=True, net_worth_cr=25000.0,
                     other_directorships=["JSW Energy Corp Ltd", "JSW Cement Ltd"]),
    DirectorPromoter(din="00019012", name="Seshagiri Rao MVS", designation="Joint MD & Group CFO",
                     entity_id="JSWL001", is_promoter=False, net_worth_cr=180.0),
    DirectorPromoter(din="00020123", name="Jayant Acharya", designation="Executive Director",
                     entity_id="JSWL001", is_promoter=False, net_worth_cr=65.0),
]

JSWL_FINANCIALS = {
    "FY2025": FinancialStatement(
        entity_id="JSWL001", period="FY2025", statement_type="standalone",
        source="audited", as_of_date=date(2025, 3, 31),
        line_items={
            "revenue_operating": 45600.00, "other_income": 850.00,
            "total_income": 46450.00, "raw_material_cost": 28272.00,
            "employee_cost": 3192.00, "other_expenses": 5472.00,
            "ebitda": 9514.00, "depreciation": 3200.00,
            "ebit": 6314.00, "finance_cost": 2850.00,
            "pbt": 3464.00, "tax_expense": 866.00, "pat": 2598.00,
            "total_assets": 72000.00, "fixed_assets": 42000.00,
            "current_assets": 20000.00, "investments": 10000.00,
            "total_equity": 28000.00, "long_term_debt": 22000.00,
            "short_term_debt": 12000.00, "total_debt": 34000.00,
            "current_liabilities": 18000.00, "trade_receivables": 6500.00,
            "inventory": 8500.00, "cash_equivalents": 2800.00,
            "trade_payables": 7200.00,
            "ocf": 7200.00, "capex": -4500.00, "fcff": 2700.00,
            "market_cap": 168000.00, "working_capital": 2000.00,
        }
    ),
    "FY2024": FinancialStatement(
        entity_id="JSWL001", period="FY2024", statement_type="standalone",
        source="audited", as_of_date=date(2024, 3, 31),
        line_items={
            "revenue_operating": 42800.00, "other_income": 750.00,
            "total_income": 43550.00, "raw_material_cost": 26936.00,
            "employee_cost": 2996.00, "other_expenses": 5136.00,
            "ebitda": 8482.00, "depreciation": 2900.00,
            "ebit": 5582.00, "finance_cost": 2650.00,
            "pbt": 2932.00, "tax_expense": 733.00, "pat": 2199.00,
            "total_assets": 68000.00, "total_equity": 26000.00,
            "total_debt": 32000.00,
            "ocf": 6200.00, "capex": -4000.00, "fcff": 2200.00,
        }
    ),
    "FY2023": FinancialStatement(
        entity_id="JSWL001", period="FY2023", statement_type="standalone",
        source="audited", as_of_date=date(2023, 3, 31),
        line_items={
            "revenue_operating": 38500.00, "other_income": 620.00,
            "total_income": 39120.00, "raw_material_cost": 24640.00,
            "employee_cost": 2695.00, "other_expenses": 4620.00,
            "ebitda": 7165.00, "depreciation": 2600.00,
            "ebit": 4565.00, "finance_cost": 2400.00,
            "pbt": 2165.00, "tax_expense": 541.25, "pat": 1623.75,
            "total_assets": 64000.00, "total_equity": 24000.00,
            "total_debt": 30000.00,
            "ocf": 5000.00, "capex": -3500.00, "fcff": 1500.00,
        }
    ),
}

JSWL_PROVISIONAL = FinancialStatement(
    entity_id="JSWL001", period="FY2026_P", statement_type="standalone",
    source="provisional", as_of_date=date(2026, 12, 31),
    line_items={
        "revenue_operating": 50000.00, "ebitda": 11000.00,
        "pat": 3200.00, "total_debt": 32000.00, "total_equity": 30000.00,
        "total_assets": 76000.00,
    }
)

JSWL_FACILITY = FacilityRequest(
    facility_id="FAC_JSWL_001", entity_id="JSWL001",
    case_type=CaseType.NTB, facility_type=FacilityType.TERM_LOAN,
    amount_requested_cr=1500.00,
    purpose="Capex for 2.5 MTPA capacity expansion at Dolvi, Raigad, Maharashtra",
    tenor_months=84, collateral_value_cr=2200.00, proposed_limit_cr=1500.00,
)

JSWL_COLLATERAL = [
    Collateral(collateral_id="COL_JSWL_01", entity_id="JSWL001",
               collateral_type="Plant & Machinery", description="Steel rolling mill and hot strip mill at Dolvi",
               market_value_cr=1800.00, forced_sale_value_cr=1260.00,
               valuation_date=date(2026, 5, 20), encumbrance_status="clear"),
    Collateral(collateral_id="COL_JSWL_02", entity_id="JSWL001",
               collateral_type="Land & Building", description="Factory premises at Dolvi industrial plot",
               market_value_cr=400.00, forced_sale_value_cr=280.00,
               valuation_date=date(2026, 5, 20), encumbrance_status="clear"),
]

JSWL_MARKET_SIGNALS = [
    MarketSignal(entity_id="JSWL001", signal_type="news",
                 headline="JSW Alloys reports strong Q2 with auto-grade steel demand up 18%",
                 sentiment="positive", severity=RiskSeverity.LOW,
                 source_name="ET Markets", signal_date=date(2026, 10, 15)),
    MarketSignal(entity_id="JSWL001", signal_type="news",
                 headline="Global steel prices soften on China demand slowdown; margin pressure likely",
                 sentiment="negative", severity=RiskSeverity.MEDIUM,
                 source_name="Bloomberg", signal_date=date(2026, 11, 20)),
]


# ═══════════════════════════════════════════════════════════════════════════════
# COMPANY 13: MARUTI AUTO LTD (Listed NTB, Auto — STRONG)
# ═══════════════════════════════════════════════════════════════════════════════

MRUT_BORROWER = Borrower(
    entity_id="MRUT001",
    company_name="Maruti Auto Industries Ltd",
    cin="L34103HR1981PLC013258",
    pan="AAACM9012J",
    borrower_type=BorrowerType.LISTED,
    sector=Sector.MANUFACTURING,
    subsector="Passenger Vehicles",
    date_of_incorporation=date(1982, 2, 24),
    registered_state="Haryana",
    registered_address="1, Nelson Mandela Road, Vasant Kunj, New Delhi 110070",
    authorized_capital=600.00,
    paid_up_capital=151.00,
    listed_exchange="BSE, NSE",
    nse_symbol="MARUTIAUTO",
    isin="INE585B01010",
    credit_rating="CRISIL AAA/Stable",
    rating_agency="CRISIL",
    employee_count=38000,
    website="www.marutiauto.com",
)

MRUT_GROUP = GroupEntity(
    group_id="GRP_MRUT", group_name="Maruti Auto Group",
    parent_entity_id="MRUT001",
    entities=["MRUT001", "Maruti Suzuki Financial Services Ltd", "True Value Network Ltd"],
    promoter_holding_pct=56.4, institutional_holding_pct=30.8, public_holding_pct=12.8,
)

MRUT_DIRECTORS = [
    DirectorPromoter(din="00021234", name="Hisashi Takeuchi", designation="Managing Director & CEO",
                     entity_id="MRUT001", is_promoter=False, net_worth_cr=85.0),
    DirectorPromoter(din="00022345", name="R.C. Bhargava", designation="Chairman",
                     entity_id="MRUT001", is_promoter=False, net_worth_cr=250.0),
    DirectorPromoter(din="00023456", name="Kenichi Ayukawa", designation="Non-Executive Director",
                     entity_id="MRUT001", is_promoter=True, net_worth_cr=120.0),
]

MRUT_FINANCIALS = {
    "FY2025": FinancialStatement(
        entity_id="MRUT001", period="FY2025", statement_type="standalone",
        source="audited", as_of_date=date(2025, 3, 31),
        line_items={
            "revenue_operating": 135700.00, "other_income": 4200.00,
            "total_income": 139900.00, "raw_material_cost": 90369.00,
            "employee_cost": 5428.00, "other_expenses": 15241.00,
            "ebitda": 28862.00, "depreciation": 4100.00,
            "ebit": 24762.00, "finance_cost": 220.00,
            "pbt": 24542.00, "tax_expense": 6135.50, "pat": 18406.50,
            "total_assets": 82000.00, "fixed_assets": 25000.00,
            "current_assets": 35000.00, "investments": 22000.00,
            "total_equity": 62000.00, "long_term_debt": 0.00,
            "short_term_debt": 0.00, "total_debt": 0.00,
            "current_liabilities": 20000.00, "trade_receivables": 3200.00,
            "inventory": 5800.00, "cash_equivalents": 12000.00,
            "trade_payables": 12500.00,
            "ocf": 22000.00, "capex": -6500.00, "fcff": 15500.00,
            "market_cap": 380000.00, "working_capital": 15000.00,
        }
    ),
    "FY2024": FinancialStatement(
        entity_id="MRUT001", period="FY2024", statement_type="standalone",
        source="audited", as_of_date=date(2024, 3, 31),
        line_items={
            "revenue_operating": 117571.00, "other_income": 3500.00,
            "total_income": 121071.00, "raw_material_cost": 79548.00,
            "employee_cost": 4703.00, "other_expenses": 13209.00,
            "ebitda": 23611.00, "depreciation": 3650.00,
            "ebit": 19961.00, "finance_cost": 190.00,
            "pbt": 19771.00, "tax_expense": 4942.75, "pat": 14828.25,
            "total_assets": 72000.00, "total_equity": 52000.00,
            "total_debt": 0.00,
            "ocf": 18000.00, "capex": -5500.00, "fcff": 12500.00,
        }
    ),
    "FY2023": FinancialStatement(
        entity_id="MRUT001", period="FY2023", statement_type="standalone",
        source="audited", as_of_date=date(2023, 3, 31),
        line_items={
            "revenue_operating": 88330.00, "other_income": 2800.00,
            "total_income": 91130.00, "raw_material_cost": 61831.00,
            "employee_cost": 3533.00, "other_expenses": 9717.00,
            "ebitda": 16049.00, "depreciation": 3200.00,
            "ebit": 12849.00, "finance_cost": 160.00,
            "pbt": 12689.00, "tax_expense": 3172.25, "pat": 9516.75,
            "total_assets": 60000.00, "total_equity": 42000.00,
            "total_debt": 0.00,
            "ocf": 12500.00, "capex": -4500.00, "fcff": 8000.00,
        }
    ),
}

MRUT_PROVISIONAL = FinancialStatement(
    entity_id="MRUT001", period="FY2026_P", statement_type="standalone",
    source="provisional", as_of_date=date(2026, 12, 31),
    line_items={
        "revenue_operating": 148000.00, "ebitda": 32000.00,
        "pat": 21000.00, "total_debt": 0.00, "total_equity": 72000.00,
        "total_assets": 92000.00,
    }
)

MRUT_FACILITY = FacilityRequest(
    facility_id="FAC_MRUT_001", entity_id="MRUT001",
    case_type=CaseType.NTB, facility_type=FacilityType.WORKING_CAPITAL,
    amount_requested_cr=800.00,
    purpose="Non-fund BG/LC facility for import of CKD kits and vendor advance guarantees for new EV plant Kharkhoda",
    tenor_months=12, collateral_value_cr=0.00, proposed_limit_cr=800.00,
)

MRUT_COLLATERAL = [
    Collateral(collateral_id="COL_MRUT_01", entity_id="MRUT001",
               collateral_type="Fixed Deposits", description="FD lien for LC/BG margin at SBI",
               market_value_cr=200.00, forced_sale_value_cr=200.00,
               valuation_date=date(2026, 8, 15), encumbrance_status="clear"),
]

MRUT_MARKET_SIGNALS = [
    MarketSignal(entity_id="MRUT001", signal_type="news",
                 headline="Maruti Auto reports record FY2025 vehicle sales at 2.35M units; SUV share rises to 35%",
                 sentiment="positive", severity=RiskSeverity.LOW,
                 source_name="Auto Car Professional", signal_date=date(2026, 10, 1)),
    MarketSignal(entity_id="MRUT001", signal_type="analyst",
                 headline="CRISIL reaffirms AAA/Stable; debt-free balance sheet and strong brand franchise",
                 sentiment="positive", severity=RiskSeverity.LOW,
                 source_name="CRISIL", signal_date=date(2026, 10, 20)),
]


# ═══════════════════════════════════════════════════════════════════════════════
# COMPANY 14: TITAN RETAIL LTD (Listed NTB, Retail — CLEAN)
# ═══════════════════════════════════════════════════════════════════════════════

TITN_BORROWER = Borrower(
    entity_id="TITN001",
    company_name="Titan Luxe Retail Ltd",
    cin="L74999TN1984PLC010491",
    pan="AAACT0123K",
    borrower_type=BorrowerType.LISTED,
    sector=Sector.TRADING,
    subsector="Watches, Jewellery & Eyewear Retail",
    date_of_incorporation=date(1985, 7, 26),
    registered_state="Tamil Nadu",
    registered_address="3, SIPCOT Industrial Complex, Hosur, Tamil Nadu 635126",
    authorized_capital=150.00,
    paid_up_capital=88.74,
    listed_exchange="BSE, NSE",
    nse_symbol="TITANLUXE",
    isin="INE280A01028",
    credit_rating="CRISIL AA+/Stable",
    rating_agency="CRISIL",
    employee_count=12500,
    website="www.titanluxeretail.com",
)

TITN_GROUP = GroupEntity(
    group_id="GRP_TITN", group_name="Titan Luxe Group",
    parent_entity_id="TITN001",
    entities=["TITN001", "Tanishq Brand Retail Ltd", "Titan Eyeplus Ltd"],
    promoter_holding_pct=52.9, institutional_holding_pct=34.6, public_holding_pct=12.5,
)

TITN_DIRECTORS = [
    DirectorPromoter(din="00024567", name="CK Venkataraman", designation="Managing Director",
                     entity_id="TITN001", is_promoter=False, net_worth_cr=280.0),
    DirectorPromoter(din="00025678", name="N. Chandrasekaran", designation="Non-Executive Chairman",
                     entity_id="TITN001", is_promoter=True, net_worth_cr=1200.0),
    DirectorPromoter(din="00026789", name="Ashwini Deshpande", designation="Independent Director",
                     entity_id="TITN001", is_promoter=False, net_worth_cr=22.0),
]

TITN_FINANCIALS = {
    "FY2025": FinancialStatement(
        entity_id="TITN001", period="FY2025", statement_type="standalone",
        source="audited", as_of_date=date(2025, 3, 31),
        line_items={
            "revenue_operating": 51200.00, "other_income": 680.00,
            "total_income": 51880.00, "raw_material_cost": 37376.00,
            "employee_cost": 2560.00, "other_expenses": 4608.00,
            "ebitda": 7336.00, "depreciation": 1024.00,
            "ebit": 6312.00, "finance_cost": 380.00,
            "pbt": 5932.00, "tax_expense": 1483.00, "pat": 4449.00,
            "total_assets": 28000.00, "fixed_assets": 6500.00,
            "current_assets": 16000.00, "investments": 5500.00,
            "total_equity": 13500.00, "long_term_debt": 2000.00,
            "short_term_debt": 3500.00, "total_debt": 5500.00,
            "current_liabilities": 14500.00, "trade_receivables": 1800.00,
            "inventory": 10500.00, "cash_equivalents": 2200.00,
            "trade_payables": 6800.00,
            "ocf": 5500.00, "capex": -1800.00, "fcff": 3700.00,
            "market_cap": 285000.00, "working_capital": 1500.00,
        }
    ),
    "FY2024": FinancialStatement(
        entity_id="TITN001", period="FY2024", statement_type="standalone",
        source="audited", as_of_date=date(2024, 3, 31),
        line_items={
            "revenue_operating": 40570.00, "other_income": 520.00,
            "total_income": 41090.00, "raw_material_cost": 29616.00,
            "employee_cost": 2029.00, "other_expenses": 3651.00,
            "ebitda": 5794.00, "depreciation": 892.00,
            "ebit": 4902.00, "finance_cost": 320.00,
            "pbt": 4582.00, "tax_expense": 1145.50, "pat": 3436.50,
            "total_assets": 24500.00, "total_equity": 11500.00,
            "total_debt": 4800.00,
            "ocf": 4200.00, "capex": -1500.00, "fcff": 2700.00,
        }
    ),
    "FY2023": FinancialStatement(
        entity_id="TITN001", period="FY2023", statement_type="standalone",
        source="audited", as_of_date=date(2023, 3, 31),
        line_items={
            "revenue_operating": 29049.00, "other_income": 380.00,
            "total_income": 29429.00, "raw_material_cost": 21206.00,
            "employee_cost": 1452.00, "other_expenses": 2614.00,
            "ebitda": 4157.00, "depreciation": 780.00,
            "ebit": 3377.00, "finance_cost": 280.00,
            "pbt": 3097.00, "tax_expense": 774.25, "pat": 2322.75,
            "total_assets": 21500.00, "total_equity": 10000.00,
            "total_debt": 4200.00,
            "ocf": 3200.00, "capex": -1200.00, "fcff": 2000.00,
        }
    ),
}

TITN_PROVISIONAL = FinancialStatement(
    entity_id="TITN001", period="FY2026_P", statement_type="standalone",
    source="provisional", as_of_date=date(2026, 12, 31),
    line_items={
        "revenue_operating": 58000.00, "ebitda": 8500.00,
        "pat": 5200.00, "total_debt": 5000.00, "total_equity": 16000.00,
        "total_assets": 31000.00,
    }
)

TITN_FACILITY = FacilityRequest(
    facility_id="FAC_TITN_001", entity_id="TITN001",
    case_type=CaseType.NTB, facility_type=FacilityType.WORKING_CAPITAL,
    amount_requested_cr=400.00,
    purpose="Working capital for gold inventory procurement for Diwali/wedding season and new store expansion",
    tenor_months=12, collateral_value_cr=500.00, proposed_limit_cr=400.00,
)

TITN_COLLATERAL = [
    Collateral(collateral_id="COL_TITN_01", entity_id="TITN001",
               collateral_type="Inventory", description="Gold bullion and studded jewellery inventory across 400+ Tanishq stores",
               market_value_cr=500.00, forced_sale_value_cr=425.00,
               valuation_date=date(2026, 7, 1), encumbrance_status="hypothecated"),
]

TITN_MARKET_SIGNALS = [
    MarketSignal(entity_id="TITN001", signal_type="news",
                 headline="Titan Luxe Retail Q2 jewellery revenue up 26% driven by gold price rally and wedding demand",
                 sentiment="positive", severity=RiskSeverity.LOW,
                 source_name="Business Standard", signal_date=date(2026, 10, 25)),
    MarketSignal(entity_id="TITN001", signal_type="analyst",
                 headline="Gold prices at all-time high of Rs 75,000/10g; margin pressure risk for Titan",
                 sentiment="negative", severity=RiskSeverity.LOW,
                 source_name="Kotak Institutional Equities", signal_date=date(2026, 11, 5)),
]


# ═══════════════════════════════════════════════════════════════════════════════
# COMPANY 15: NTPC POWER LTD (Listed ETB, Power — STABLE)
# ═══════════════════════════════════════════════════════════════════════════════

NTPC_BORROWER = Borrower(
    entity_id="NTPC001",
    company_name="National Thermal Power Corp Ltd",
    cin="L40101DL1975GOI007966",
    pan="AAACN1234L",
    borrower_type=BorrowerType.LISTED,
    sector=Sector.INFRASTRUCTURE,
    subsector="Power Generation — Thermal & Renewable",
    date_of_incorporation=date(1976, 11, 7),
    registered_state="Delhi",
    registered_address="NTPC Bhawan, Scope Complex, 7 Institutional Area, Lodhi Road, New Delhi 110003",
    authorized_capital=15000.00,
    paid_up_capital=9697.00,
    listed_exchange="BSE, NSE",
    nse_symbol="NTPCPWR",
    isin="INE733E01010",
    credit_rating="CRISIL AAA/Stable",
    rating_agency="CRISIL",
    employee_count=22000,
    website="www.ntpcpower.com",
)

NTPC_GROUP = GroupEntity(
    group_id="GRP_NTPC", group_name="NTPC Power Group",
    parent_entity_id="NTPC001",
    entities=["NTPC001", "NTPC Green Energy Ltd", "NTPC Vidyut Vyapar Nigam Ltd",
              "North Eastern Electric Power Corp"],
    promoter_holding_pct=51.1, institutional_holding_pct=36.4, public_holding_pct=12.5,
)

NTPC_DIRECTORS = [
    DirectorPromoter(din="00027890", name="Gurdeep Singh", designation="CMD",
                     entity_id="NTPC001", is_promoter=False, net_worth_cr=18.0),
    DirectorPromoter(din="00028901", name="Dillip Kumar Patel", designation="Director (Finance)",
                     entity_id="NTPC001", is_promoter=False, net_worth_cr=12.0),
    DirectorPromoter(din="00029012", name="Ramesh Babu V.", designation="Director (Operations)",
                     entity_id="NTPC001", is_promoter=False, net_worth_cr=10.0),
]

NTPC_FINANCIALS = {
    "FY2025": FinancialStatement(
        entity_id="NTPC001", period="FY2025", statement_type="standalone",
        source="audited", as_of_date=date(2025, 3, 31),
        line_items={
            "revenue_operating": 178500.00, "other_income": 5200.00,
            "total_income": 183700.00, "raw_material_cost": 125950.00,
            "employee_cost": 8032.50, "other_expenses": 10710.00,
            "ebitda": 39007.50, "depreciation": 12000.00,
            "ebit": 27007.50, "finance_cost": 11200.00,
            "pbt": 15807.50, "tax_expense": 3951.88, "pat": 11855.62,
            "total_assets": 350000.00, "fixed_assets": 240000.00,
            "current_assets": 65000.00, "investments": 45000.00,
            "total_equity": 148000.00, "long_term_debt": 125000.00,
            "short_term_debt": 32000.00, "total_debt": 157000.00,
            "current_liabilities": 52000.00, "trade_receivables": 28000.00,
            "inventory": 12000.00, "cash_equivalents": 8500.00,
            "trade_payables": 18000.00,
            "ocf": 28000.00, "capex": -18000.00, "fcff": 10000.00,
            "market_cap": 350000.00, "working_capital": 13000.00,
        }
    ),
    "FY2024": FinancialStatement(
        entity_id="NTPC001", period="FY2024", statement_type="standalone",
        source="audited", as_of_date=date(2024, 3, 31),
        line_items={
            "revenue_operating": 168200.00, "other_income": 4800.00,
            "total_income": 173000.00, "raw_material_cost": 121104.00,
            "employee_cost": 7569.00, "other_expenses": 10092.00,
            "ebitda": 34235.00, "depreciation": 11200.00,
            "ebit": 23035.00, "finance_cost": 10500.00,
            "pbt": 12535.00, "tax_expense": 3133.75, "pat": 9401.25,
            "total_assets": 330000.00, "total_equity": 140000.00,
            "total_debt": 148000.00,
            "ocf": 25000.00, "capex": -16000.00, "fcff": 9000.00,
        }
    ),
    "FY2023": FinancialStatement(
        entity_id="NTPC001", period="FY2023", statement_type="standalone",
        source="audited", as_of_date=date(2023, 3, 31),
        line_items={
            "revenue_operating": 152800.00, "other_income": 4200.00,
            "total_income": 157000.00, "raw_material_cost": 112064.00,
            "employee_cost": 6876.00, "other_expenses": 9168.00,
            "ebitda": 28892.00, "depreciation": 10400.00,
            "ebit": 18492.00, "finance_cost": 9800.00,
            "pbt": 8692.00, "tax_expense": 2173.00, "pat": 6519.00,
            "total_assets": 310000.00, "total_equity": 132000.00,
            "total_debt": 140000.00,
            "ocf": 22000.00, "capex": -14000.00, "fcff": 8000.00,
        }
    ),
}

NTPC_PROVISIONAL = FinancialStatement(
    entity_id="NTPC001", period="FY2026_P", statement_type="standalone",
    source="provisional", as_of_date=date(2026, 12, 31),
    line_items={
        "revenue_operating": 190000.00, "ebitda": 42000.00,
        "pat": 13000.00, "total_debt": 160000.00, "total_equity": 155000.00,
        "total_assets": 370000.00,
    }
)

NTPC_FACILITY = FacilityRequest(
    facility_id="FAC_NTPC_001", entity_id="NTPC001",
    case_type=CaseType.ETB, facility_type=FacilityType.TERM_LOAN,
    amount_requested_cr=5000.00,
    purpose="Term loan for 4.75 GW solar + wind renewable energy park at Khavda, Gujarat",
    tenor_months=180, collateral_value_cr=6500.00,
    existing_limit_cr=8000.00, proposed_limit_cr=13000.00,
)

NTPC_EXISTING_EXPOSURE = [
    ExistingExposure(facility_id="EXP_NTPC_01", entity_id="NTPC001",
                     facility_type="term_loan", sanctioned_limit_cr=5000.00,
                     outstanding_cr=3200.00, utilization_pct=64.0, overdue_days=0),
    ExistingExposure(facility_id="EXP_NTPC_02", entity_id="NTPC001",
                     facility_type="working_capital", sanctioned_limit_cr=3000.00,
                     outstanding_cr=1850.00, utilization_pct=61.7, overdue_days=0),
]

NTPC_CONDUCT = [
    ConductRecord(entity_id="NTPC001", period="Q1_FY2026",
                   avg_bank_balance_cr=85.0, credit_turnover_cr=4200.00,
                   debit_turnover_cr=4150.00, cheque_returns=0,
                   limit_utilization_pct=62.0, overdue_instances=0,
                   max_overdue_days=0),
    ConductRecord(entity_id="NTPC001", period="Q2_FY2026",
                   avg_bank_balance_cr=92.0, credit_turnover_cr=4500.00,
                   debit_turnover_cr=4420.00, cheque_returns=0,
                   limit_utilization_pct=60.0, overdue_instances=0,
                   max_overdue_days=0),
    ConductRecord(entity_id="NTPC001", period="Q3_FY2026",
                   avg_bank_balance_cr=88.0, credit_turnover_cr=4350.00,
                   debit_turnover_cr=4300.00, cheque_returns=0,
                   limit_utilization_pct=63.0, overdue_instances=0,
                   max_overdue_days=0),
    ConductRecord(entity_id="NTPC001", period="Q4_FY2026",
                   avg_bank_balance_cr=95.0, credit_turnover_cr=4600.00,
                   debit_turnover_cr=4580.00, cheque_returns=0,
                   limit_utilization_pct=58.0, overdue_instances=0,
                   max_overdue_days=0),
]

NTPC_COVENANTS = [
    CovenantRecord(entity_id="NTPC001", covenant_type="DSCR", required_value=">=1.30",
                   actual_value="1.52", compliance_status="compliant", period="Q4_FY2026"),
    CovenantRecord(entity_id="NTPC001", covenant_type="Debt/Equity", required_value="<=1.20",
                   actual_value="1.06", compliance_status="compliant", period="Q4_FY2026"),
    CovenantRecord(entity_id="NTPC001", covenant_type="Fixed Asset Coverage", required_value=">=1.50",
                   actual_value="1.53", compliance_status="compliant", period="Q4_FY2026"),
]

NTPC_COLLATERAL = [
    Collateral(collateral_id="COL_NTPC_01", entity_id="NTPC001",
               collateral_type="Plant & Machinery", description="Vindhyachal STPS Units 1-6 thermal plant",
               market_value_cr=4500.00, forced_sale_value_cr=3150.00,
               valuation_date=date(2026, 4, 15), encumbrance_status="clear"),
    Collateral(collateral_id="COL_NTPC_02", entity_id="NTPC001",
               collateral_type="Land & Building", description="Khavda solar park land lease 5000 acres Gujarat",
               market_value_cr=2000.00, forced_sale_value_cr=1400.00,
               valuation_date=date(2026, 4, 15), encumbrance_status="clear"),
]

NTPC_MARKET_SIGNALS = [
    MarketSignal(entity_id="NTPC001", signal_type="news",
                 headline="NTPC Power achieves 70 GW installed capacity milestone; green portfolio at 18 GW",
                 sentiment="positive", severity=RiskSeverity.LOW,
                 source_name="ET Energy World", signal_date=date(2026, 9, 15)),
    MarketSignal(entity_id="NTPC001", signal_type="analyst",
                 headline="GoI sovereign backing + regulated return model make NTPC lowest risk infra credit",
                 sentiment="positive", severity=RiskSeverity.LOW,
                 source_name="Morgan Stanley", signal_date=date(2026, 10, 8)),
]


# ═══════════════════════════════════════════════════════════════════════════════
# COMPANY 16: YES BANK LTD (Listed ETB, NBFC — FRAUD SIGNALS)
# ═══════════════════════════════════════════════════════════════════════════════

YESB_BORROWER = Borrower(
    entity_id="YESB001",
    company_name="Yashwant Commercial Bank Ltd",
    cin="L65190MH2003PLC143249",
    pan="AAACY2345M",
    borrower_type=BorrowerType.LISTED,
    sector=Sector.NBFC,
    subsector="Private Sector Bank / Financial Services",
    date_of_incorporation=date(2004, 11, 21),
    registered_state="Maharashtra",
    registered_address="Nehru Centre, 9th Floor, Discovery of India, Worli, Mumbai 400018",
    authorized_capital=1100.00,
    paid_up_capital=628.00,
    listed_exchange="BSE, NSE",
    nse_symbol="YASHBANK",
    isin="INE528G01035",
    credit_rating="ICRA BBB/Watch Negative",
    rating_agency="ICRA",
    employee_count=28000,
    website="www.yashwantbank.com",
)

YESB_GROUP = GroupEntity(
    group_id="GRP_YESB", group_name="Yashwant Bank Group",
    parent_entity_id="YESB001",
    entities=["YESB001", "YB Capital Advisors Ltd", "YB Securities Ltd"],
    promoter_holding_pct=23.2, institutional_holding_pct=52.8, public_holding_pct=24.0,
)

YESB_DIRECTORS = [
    DirectorPromoter(din="00030123", name="Prashant Kumar", designation="Managing Director & CEO",
                     entity_id="YESB001", is_promoter=False, net_worth_cr=15.0),
    DirectorPromoter(din="00031234", name="Rana Kapoor", designation="Former MD (removed by RBI)",
                     entity_id="YESB001", is_promoter=True, net_worth_cr=2.0,
                     other_directorships=["YES Capital (India) Pvt Ltd", "Three Sisters Institutional Office LLP"]),
    DirectorPromoter(din="00032345", name="Sunil Kaul", designation="Non-Executive Director (SBI nominee)",
                     entity_id="YESB001", is_promoter=False, net_worth_cr=8.0),
]

YESB_FINANCIALS = {
    "FY2025": FinancialStatement(
        entity_id="YESB001", period="FY2025", statement_type="standalone",
        source="audited", as_of_date=date(2025, 3, 31),
        line_items={
            "revenue_operating": 28500.00, "other_income": 3200.00,
            "total_income": 31700.00, "raw_material_cost": 0.00,
            "employee_cost": 4275.00, "other_expenses": 5700.00,
            "ebitda": 21725.00, "depreciation": 850.00,
            "ebit": 20875.00, "finance_cost": 18525.00,
            "pbt": 2350.00, "tax_expense": 587.50, "pat": 1762.50,
            "total_assets": 385000.00, "fixed_assets": 4800.00,
            "current_assets": 85000.00, "investments": 95000.00,
            "total_equity": 38000.00, "long_term_debt": 200000.00,
            "short_term_debt": 120000.00, "total_debt": 320000.00,
            "current_liabilities": 47000.00, "trade_receivables": 0.00,
            "inventory": 0.00, "cash_equivalents": 32000.00,
            "trade_payables": 2800.00,
            "ocf": 8500.00, "capex": -1200.00, "fcff": 7300.00,
            "market_cap": 52000.00, "working_capital": 38000.00,
            "loan_book_cr": 225000.00, "gnpa_pct": 2.20,
            "nnpa_pct": 0.85, "provision_coverage_pct": 78.5,
            "capital_adequacy_pct": 17.4,
            # FRAUD SIGNALS — Unusual spikes
            "investments_in_group_entities": 12500.00,
            "related_party_advances": 8200.00,
            "contingent_liabilities": 45000.00,
        }
    ),
    "FY2024": FinancialStatement(
        entity_id="YESB001", period="FY2024", statement_type="standalone",
        source="audited", as_of_date=date(2024, 3, 31),
        line_items={
            "revenue_operating": 24800.00, "other_income": 2800.00,
            "total_income": 27600.00, "employee_cost": 3720.00,
            "other_expenses": 4960.00, "ebitda": 18920.00,
            "depreciation": 740.00, "ebit": 18180.00,
            "finance_cost": 17360.00, "pbt": 820.00,
            "tax_expense": 205.00, "pat": 615.00,
            "total_assets": 350000.00, "total_equity": 36500.00,
            "long_term_debt": 185000.00, "short_term_debt": 105000.00,
            "total_debt": 290000.00,
            "ocf": 5200.00, "capex": -800.00, "fcff": 4400.00,
            "gnpa_pct": 3.80, "nnpa_pct": 1.50,
        }
    ),
    "FY2023": FinancialStatement(
        entity_id="YESB001", period="FY2023", statement_type="standalone",
        source="audited", as_of_date=date(2023, 3, 31),
        line_items={
            "revenue_operating": 21200.00, "other_income": 2400.00,
            "total_income": 23600.00, "employee_cost": 3180.00,
            "other_expenses": 4240.00, "ebitda": 16180.00,
            "depreciation": 636.00, "ebit": 15544.00,
            "finance_cost": 15900.00, "pbt": -356.00,
            "tax_expense": 0.00, "pat": -356.00,
            "total_assets": 320000.00, "total_equity": 35500.00,
            "long_term_debt": 170000.00, "short_term_debt": 95000.00,
            "total_debt": 265000.00,
            "ocf": 2800.00, "capex": -600.00, "fcff": 2200.00,
            "gnpa_pct": 13.90, "nnpa_pct": 5.20,
        }
    ),
}

YESB_PROVISIONAL = FinancialStatement(
    entity_id="YESB001", period="FY2026_P", statement_type="standalone",
    source="provisional", as_of_date=date(2026, 12, 31),
    line_items={
        "revenue_operating": 32000.00, "ebitda": 24000.00,
        "pat": 2500.00, "total_debt": 340000.00, "total_equity": 40000.00,
        "total_assets": 410000.00,
    }
)

# INTENTIONAL MISMATCH: Exchange filing shows worse position
YESB_EXCHANGE_FILING = FinancialStatement(
    entity_id="YESB001", period="FY2026_Q3", statement_type="standalone",
    source="exchange", as_of_date=date(2025, 12, 31),
    line_items={
        "revenue_operating": 22500.00,
        "ebitda": 16500.00,
        "pat": 380.00,
        "total_debt": 355000.00,
        "total_equity": 37000.00,
    }
)

YESB_FACILITY = FacilityRequest(
    facility_id="FAC_YESB_001", entity_id="YESB001",
    case_type=CaseType.ETB, facility_type=FacilityType.TERM_LOAN,
    amount_requested_cr=1000.00,
    purpose="Tier-II subordinated debt for capital adequacy maintenance per RBI Prompt Corrective Action framework",
    tenor_months=120, collateral_value_cr=0.00,
    existing_limit_cr=3500.00, proposed_limit_cr=4500.00,
)

YESB_EXISTING_EXPOSURE = [
    ExistingExposure(facility_id="EXP_YESB_01", entity_id="YESB001",
                     facility_type="term_loan", sanctioned_limit_cr=2500.00,
                     outstanding_cr=2350.00, utilization_pct=94.0, overdue_days=0),
    ExistingExposure(facility_id="EXP_YESB_02", entity_id="YESB001",
                     facility_type="working_capital", sanctioned_limit_cr=1000.00,
                     outstanding_cr=920.00, utilization_pct=92.0, overdue_days=5),
]

YESB_CONDUCT = [
    ConductRecord(entity_id="YESB001", period="Q1_FY2026",
                   avg_bank_balance_cr=15.0, credit_turnover_cr=850.00,
                   debit_turnover_cr=845.00, cheque_returns=2,
                   limit_utilization_pct=90.0, overdue_instances=1,
                   max_overdue_days=8, dpd_30_count=1, dpd_60_count=0, dpd_90_count=0),
    ConductRecord(entity_id="YESB001", period="Q2_FY2026",
                   avg_bank_balance_cr=12.0, credit_turnover_cr=820.00,
                   debit_turnover_cr=825.00, cheque_returns=4,
                   limit_utilization_pct=92.0, overdue_instances=2,
                   max_overdue_days=12, dpd_30_count=1, dpd_60_count=0, dpd_90_count=0),
    ConductRecord(entity_id="YESB001", period="Q3_FY2026",
                   avg_bank_balance_cr=8.5, credit_turnover_cr=780.00,
                   debit_turnover_cr=790.00, cheque_returns=7,
                   limit_utilization_pct=94.0, overdue_instances=3,
                   max_overdue_days=22, dpd_30_count=2, dpd_60_count=1, dpd_90_count=0),
    ConductRecord(entity_id="YESB001", period="Q4_FY2026",
                   avg_bank_balance_cr=5.5, credit_turnover_cr=720.00,
                   debit_turnover_cr=740.00, cheque_returns=12,
                   limit_utilization_pct=96.0, overdue_instances=4,
                   max_overdue_days=35, dpd_30_count=3, dpd_60_count=1, dpd_90_count=0),
]

YESB_COVENANTS = [
    CovenantRecord(entity_id="YESB001", covenant_type="Capital Adequacy", required_value=">=15.0%",
                   actual_value="17.4%", compliance_status="compliant", period="Q2_FY2026"),
    CovenantRecord(entity_id="YESB001", covenant_type="GNPA Ratio", required_value="<=3.0%",
                   actual_value="2.2%", compliance_status="compliant", period="Q2_FY2026"),
    CovenantRecord(entity_id="YESB001", covenant_type="GNPA Ratio", required_value="<=3.0%",
                   actual_value="3.5%", compliance_status="breached", period="Q4_FY2026",
                   breach_details="GNPA spiked due to stress in mid-corporate book; delayed recognition"),
    CovenantRecord(entity_id="YESB001", covenant_type="Max Cheque Returns", required_value="<=5/quarter",
                   actual_value="12", compliance_status="breached", period="Q4_FY2026",
                   breach_details="Deteriorating conduct; rising interbank obligations"),
]

# Core Banking — Stressed: SMA-1 with high exposure, deteriorating quality
YESB_CORE_BANKING = {
    "loan_accounts": [
        {"account_number": "ACC_YES_TL01", "facility_type": "TL",
         "sanction_limit_cr": 2500.00, "outstanding_cr": 2350.00, "interest_rate_pct": 10.75,
         "overdue_amount_cr": 85.00, "dpd": 42, "asset_classification": "SMA-1",
         "sanction_date": "2020-03-15", "maturity_date": "2027-03-15", "repayment_frequency": "Monthly"},
        {"account_number": "ACC_YES_CC01", "facility_type": "CC",
         "sanction_limit_cr": 1000.00, "outstanding_cr": 920.00, "interest_rate_pct": 11.50,
         "overdue_amount_cr": 12.00, "dpd": 5, "asset_classification": "Standard",
         "sanction_date": "2021-06-01", "maturity_date": "2026-05-31", "repayment_frequency": "Monthly"},
        {"account_number": "ACC_YES_BG01", "facility_type": "BG",
         "sanction_limit_cr": 500.00, "outstanding_cr": 480.00, "interest_rate_pct": 1.80,
         "overdue_amount_cr": 0.0, "dpd": 0, "asset_classification": "Standard",
         "sanction_date": "2022-01-10", "maturity_date": "2026-12-31", "repayment_frequency": "NA"},
    ],
    "bclc": {
        "total_fund_based_cr": 3270.00, "total_non_fund_based_cr": 480.00,
        "total_exposure_cr": 3750.00,
        "single_borrower_limit_pct": 6.8, "group_borrower_limit_pct": 11.2,
        "within_single_limit": True, "within_group_limit": True,
        "industry_exposure_pct": 12.5, "sector_ceiling_pct": 20.0,
        "rating_based_limit_cr": 4000.00,
    },
    "liability": {
        "current_account_balance_cr": 5.50, "savings_balance_cr": 0.0,
        "fixed_deposit_cr": 15.00, "total_deposits_cr": 20.50,
        "average_balance_6m_cr": 8.20, "reciprocal_business_cr": 20.50,
        "cross_sell_products": ["Current Account", "Treasury Operations"],
    },
    "fees_commission": [
        {"period": "FY2025", "processing_fees_cr": 2.80, "renewal_fees_cr": 0.90,
         "lc_commission_cr": 0.0, "bg_commission_cr": 1.20,
         "forex_income_cr": 0.35, "other_charges_cr": 0.45, "total_income_cr": 5.70},
        {"period": "FY2024", "processing_fees_cr": 3.50, "renewal_fees_cr": 1.10,
         "lc_commission_cr": 0.0, "bg_commission_cr": 1.50,
         "forex_income_cr": 0.55, "other_charges_cr": 0.60, "total_income_cr": 7.25},
    ],
    "total_exposure_cr": 3750.00,
    "overall_asset_classification": "SMA-1",
    "relationship_since": "2016-04-01",
    "relationship_years": 10,
}

YESB_COLLATERAL = [
    Collateral(collateral_id="COL_YESB_01", entity_id="YESB001",
               collateral_type="Government Securities", description="G-Sec portfolio pledged under SLR",
               market_value_cr=18000.00, forced_sale_value_cr=17100.00,
               valuation_date=date(2026, 9, 30), encumbrance_status="hypothecated"),
]

YESB_MARKET_SIGNALS = [
    MarketSignal(entity_id="YESB001", signal_type="news",
                 headline="RBI imposes Rs 2 Cr penalty on Yashwant Bank for non-compliance with KYC/AML norms",
                 sentiment="negative", severity=RiskSeverity.HIGH,
                 source_name="RBI Press Release", signal_date=date(2026, 7, 20),
                 details="Penalty under Section 47A(1)(c) of Banking Regulation Act, 1949."),
    MarketSignal(entity_id="YESB001", signal_type="news",
                 headline="Former Yashwant Bank MD Rana Kapoor convicted for money laundering by ED court",
                 sentiment="negative", severity=RiskSeverity.CRITICAL,
                 source_name="Economic Times", signal_date=date(2026, 8, 15),
                 details="Rs 4,300 Cr fraud case involving DHFL kickbacks and family trusts."),
    MarketSignal(entity_id="YESB001", signal_type="news",
                 headline="SBI-led consortium infuses Rs 10,000 Cr; Yashwant Bank turnaround on track",
                 sentiment="positive", severity=RiskSeverity.MEDIUM,
                 source_name="Business Standard", signal_date=date(2026, 10, 5)),
    MarketSignal(entity_id="YESB001", signal_type="analyst",
                 headline="ICRA places Yashwant Bank on Watch Negative; asset quality concerns persist",
                 sentiment="negative", severity=RiskSeverity.HIGH,
                 source_name="ICRA", signal_date=date(2026, 11, 12)),
]


# ═══════════════════════════════════════════════════════════════════════════════
# COMPANY 17: DR. REDDY'S LABORATORIES LTD (Listed NTB, Pharma — CLEAN)
# ═══════════════════════════════════════════════════════════════════════════════

DRRD_BORROWER = Borrower(
    entity_id="DRRD001",
    company_name="Dr. Reddy's Laboratories Limited",
    cin="L85195TG1984PLC004507",
    pan="AABCD1234R",
    borrower_type=BorrowerType.LISTED,
    sector=Sector.PHARMA,
    subsector="Pharmaceuticals — Generics & Biosimilars",
    date_of_incorporation=date(1984, 2, 24),
    registered_state="Telangana",
    registered_address="8-2-337, Road No. 3, Banjara Hills, Hyderabad 500034",
    authorized_capital=500.00,
    paid_up_capital=166.68,
    listed_exchange="BSE, NSE, NYSE",
    nse_symbol="DRREDDY",
    isin="INE089A01023",
    credit_rating="CRISIL AA+/Stable",
    rating_agency="CRISIL",
    employee_count=24800,
    website="www.drreddys.com",
)

DRRD_GROUP = GroupEntity(
    group_id="GRP_DRRD", group_name="Dr. Reddy's Group",
    parent_entity_id="DRRD001",
    entities=["DRRD001", "Dr. Reddy's Laboratories Inc (USA)", "Aurigene Pharmaceutical Services",
              "Dr. Reddy's Laboratories SA (Switzerland)"],
    promoter_holding_pct=26.68, institutional_holding_pct=52.40, public_holding_pct=20.92,
)

DRRD_DIRECTORS = [
    DirectorPromoter(din="00107737", name="K. Satish Reddy", designation="Chairman",
                     entity_id="DRRD001", is_promoter=True, net_worth_cr=12500.0),
    DirectorPromoter(din="02951532", name="G.V. Prasad", designation="Co-Chairman & Managing Director",
                     entity_id="DRRD001", is_promoter=True, net_worth_cr=18000.0,
                     other_directorships=["Aurigene Pharmaceutical Services Ltd"]),
    DirectorPromoter(din="08934439", name="Erez Israeli", designation="CEO",
                     entity_id="DRRD001", is_promoter=False, net_worth_cr=80.0),
    DirectorPromoter(din="00003894", name="Kalpana Morparia", designation="Independent Director",
                     entity_id="DRRD001", is_promoter=False, net_worth_cr=120.0),
]

DRRD_FINANCIALS = {
    "FY2025": FinancialStatement(
        entity_id="DRRD001", period="FY2025", statement_type="standalone",
        source="audited", as_of_date=date(2025, 3, 31),
        line_items={
            "revenue_operating": 27130.00, "other_income": 780.00,
            "total_income": 27910.00, "raw_material_cost": 7867.70,
            "employee_cost": 3797.00, "other_expenses": 6783.00,
            "ebitda": 9462.30, "depreciation": 1628.00,
            "ebit": 7834.30, "finance_cost": 185.00,
            "pbt": 7649.30, "tax_expense": 1912.33, "pat": 5736.97,
            "total_assets": 38500.00, "fixed_assets": 12800.00,
            "current_assets": 18200.00, "investments": 7500.00,
            "total_equity": 26800.00, "long_term_debt": 1200.00,
            "short_term_debt": 800.00, "total_debt": 2000.00,
            "current_liabilities": 11700.00, "trade_receivables": 7200.00,
            "inventory": 4500.00, "cash_equivalents": 3800.00,
            "trade_payables": 4200.00,
            "ocf": 6800.00, "capex": -2400.00, "fcff": 4400.00,
            "market_cap": 102000.00, "working_capital": 6500.00,
        }
    ),
    "FY2024": FinancialStatement(
        entity_id="DRRD001", period="FY2024", statement_type="standalone",
        source="audited", as_of_date=date(2024, 3, 31),
        line_items={
            "revenue_operating": 24950.00, "other_income": 680.00,
            "total_income": 25630.00, "raw_material_cost": 7235.50,
            "employee_cost": 3493.00, "other_expenses": 6237.50,
            "ebitda": 8664.00, "depreciation": 1480.00,
            "ebit": 7184.00, "finance_cost": 165.00,
            "pbt": 7019.00, "tax_expense": 1754.75, "pat": 5264.25,
            "total_assets": 35200.00, "fixed_assets": 11800.00,
            "current_assets": 16500.00, "investments": 6900.00,
            "total_equity": 24500.00, "long_term_debt": 1100.00,
            "short_term_debt": 600.00, "total_debt": 1700.00,
            "current_liabilities": 10700.00,
            "ocf": 6200.00, "capex": -2200.00, "fcff": 4000.00,
        }
    ),
    "FY2023": FinancialStatement(
        entity_id="DRRD001", period="FY2023", statement_type="standalone",
        source="audited", as_of_date=date(2023, 3, 31),
        line_items={
            "revenue_operating": 22250.00, "other_income": 560.00,
            "total_income": 22810.00, "raw_material_cost": 6675.00,
            "employee_cost": 3115.00, "other_expenses": 5562.50,
            "ebitda": 7457.50, "depreciation": 1350.00,
            "ebit": 6107.50, "finance_cost": 140.00,
            "pbt": 5967.50, "tax_expense": 1491.88, "pat": 4475.62,
            "total_assets": 32000.00, "fixed_assets": 10800.00,
            "current_assets": 15000.00, "investments": 6200.00,
            "total_equity": 22200.00, "long_term_debt": 1000.00,
            "short_term_debt": 500.00, "total_debt": 1500.00,
            "current_liabilities": 9800.00,
            "ocf": 5500.00, "capex": -1900.00, "fcff": 3600.00,
        }
    ),
}

DRRD_PROVISIONAL = FinancialStatement(
    entity_id="DRRD001", period="FY2026_P", statement_type="standalone",
    source="provisional", as_of_date=date(2026, 12, 31),
    line_items={
        "revenue_operating": 29500.00, "ebitda": 10325.00,
        "pat": 6200.00, "total_debt": 1800.00, "total_equity": 29000.00,
        "total_assets": 42000.00,
    }
)

DRRD_FACILITY = FacilityRequest(
    facility_id="FAC_DRRD_001", entity_id="DRRD001",
    case_type=CaseType.NTB, facility_type=FacilityType.WORKING_CAPITAL,
    amount_requested_cr=750.00,
    purpose="Fund-based working capital (CC/WCDL) for raw material (API) procurement and export receivable financing",
    tenor_months=12, collateral_value_cr=200.00, proposed_limit_cr=750.00,
)

DRRD_COLLATERAL = [
    Collateral(collateral_id="COL_DRRD_01", entity_id="DRRD001",
               collateral_type="Plant & Machinery", description="Formulation facility at Bachupally, Hyderabad",
               market_value_cr=450.00, forced_sale_value_cr=315.00,
               valuation_date=date(2026, 6, 15), encumbrance_status="clear"),
    Collateral(collateral_id="COL_DRRD_02", entity_id="DRRD001",
               collateral_type="Fixed Deposits", description="FD lien with Indian Bank for WC margin",
               market_value_cr=200.00, forced_sale_value_cr=200.00,
               valuation_date=date(2026, 7, 1), encumbrance_status="clear"),
]

DRRD_MARKET_SIGNALS = [
    MarketSignal(entity_id="DRRD001", signal_type="news",
                 headline="Dr. Reddy's receives USFDA final approval for gRevlimid (lenalidomide) — $9B US market",
                 sentiment="positive", severity=RiskSeverity.LOW,
                 source_name="Business Standard", signal_date=date(2026, 8, 22)),
    MarketSignal(entity_id="DRRD001", signal_type="analyst",
                 headline="CRISIL AA+/Stable reaffirmed; strong cash flows and low leverage noted",
                 sentiment="positive", severity=RiskSeverity.LOW,
                 source_name="CRISIL", signal_date=date(2026, 10, 15)),
    MarketSignal(entity_id="DRRD001", signal_type="news",
                 headline="Dr. Reddy's invests ₹1,500 Cr in biosimilar manufacturing capacity at Genome Valley",
                 sentiment="positive", severity=RiskSeverity.LOW,
                 source_name="Economic Times", signal_date=date(2026, 11, 5)),
]


# ═══════════════════════════════════════════════════════════════════════════════
# COMPANY 18: THE INDIAN HOTELS COMPANY LTD — TAJ (Listed ETB, Hospitality)
# ═══════════════════════════════════════════════════════════════════════════════

IHCL_BORROWER = Borrower(
    entity_id="IHCL001",
    company_name="The Indian Hotels Company Limited",
    cin="L74999MH1902PLC000183",
    pan="AAACT5678H",
    borrower_type=BorrowerType.LISTED,
    sector=Sector.HOSPITALITY,
    subsector="Hotels — Luxury & Premium",
    date_of_incorporation=date(1902, 10, 1),
    registered_state="Maharashtra",
    registered_address="Mandlik House, Mandlik Road, Mumbai 400001",
    authorized_capital=1000.00,
    paid_up_capital=142.20,
    listed_exchange="BSE, NSE",
    nse_symbol="INDHOTEL",
    isin="INE053A01029",
    credit_rating="CRISIL AA/Positive",
    rating_agency="CRISIL",
    employee_count=28000,
    website="www.ihcltata.com",
)

IHCL_GROUP = GroupEntity(
    group_id="GRP_IHCL", group_name="IHCL — Tata Hotels Group",
    parent_entity_id="IHCL001",
    entities=["IHCL001", "Taj SATS Air Catering Ltd", "Roots Corporation Ltd (Ginger Hotels)",
              "Benares Hotels Ltd", "IHCL (UK) Ltd"],
    promoter_holding_pct=38.12, institutional_holding_pct=42.50, public_holding_pct=19.38,
)

IHCL_DIRECTORS = [
    DirectorPromoter(din="00104093", name="N. Chandrasekaran", designation="Chairman",
                     entity_id="IHCL001", is_promoter=False, net_worth_cr=320.0,
                     other_directorships=["Tata Sons Pvt Ltd", "Tata Consultancy Services Ltd", "Tata Motors Ltd"]),
    DirectorPromoter(din="00102445", name="Puneet Chhatwal", designation="Managing Director & CEO",
                     entity_id="IHCL001", is_promoter=False, net_worth_cr=95.0),
    DirectorPromoter(din="06581972", name="Giridhar Sanjeevi", designation="Executive VP & CFO",
                     entity_id="IHCL001", is_promoter=False, net_worth_cr=25.0),
    DirectorPromoter(din="00112233", name="Hema Ravichandar", designation="Independent Director",
                     entity_id="IHCL001", is_promoter=False, net_worth_cr=45.0),
]

IHCL_FINANCIALS = {
    "FY2025": FinancialStatement(
        entity_id="IHCL001", period="FY2025", statement_type="standalone",
        source="audited", as_of_date=date(2025, 3, 31),
        line_items={
            "revenue_operating": 6854.00, "other_income": 485.00,
            "total_income": 7339.00, "raw_material_cost": 1028.10,
            "employee_cost": 1644.96, "other_expenses": 1713.50,
            "ebitda": 2952.44, "depreciation": 620.00,
            "ebit": 2332.44, "finance_cost": 385.00,
            "pbt": 1947.44, "tax_expense": 486.86, "pat": 1460.58,
            "total_assets": 14200.00, "fixed_assets": 8500.00,
            "current_assets": 3200.00, "investments": 2500.00,
            "total_equity": 7200.00, "long_term_debt": 3800.00,
            "short_term_debt": 1200.00, "total_debt": 5000.00,
            "current_liabilities": 3500.00, "trade_receivables": 850.00,
            "inventory": 420.00, "cash_equivalents": 1250.00,
            "trade_payables": 1100.00,
            "ocf": 2650.00, "capex": -1800.00, "fcff": 850.00,
            "market_cap": 98000.00, "working_capital": -300.00,
        }
    ),
    "FY2024": FinancialStatement(
        entity_id="IHCL001", period="FY2024", statement_type="standalone",
        source="audited", as_of_date=date(2024, 3, 31),
        line_items={
            "revenue_operating": 5960.00, "other_income": 420.00,
            "total_income": 6380.00, "raw_material_cost": 894.00,
            "employee_cost": 1430.40, "other_expenses": 1490.00,
            "ebitda": 2565.60, "depreciation": 560.00,
            "ebit": 2005.60, "finance_cost": 420.00,
            "pbt": 1585.60, "tax_expense": 396.40, "pat": 1189.20,
            "total_assets": 12800.00, "fixed_assets": 7900.00,
            "current_assets": 2800.00, "investments": 2100.00,
            "total_equity": 6200.00, "long_term_debt": 3500.00,
            "short_term_debt": 1100.00, "total_debt": 4600.00,
            "current_liabilities": 3100.00,
            "ocf": 2200.00, "capex": -1500.00, "fcff": 700.00,
        }
    ),
    "FY2023": FinancialStatement(
        entity_id="IHCL001", period="FY2023", statement_type="standalone",
        source="audited", as_of_date=date(2023, 3, 31),
        line_items={
            "revenue_operating": 5180.00, "other_income": 350.00,
            "total_income": 5530.00, "raw_material_cost": 777.00,
            "employee_cost": 1243.20, "other_expenses": 1295.00,
            "ebitda": 2214.80, "depreciation": 510.00,
            "ebit": 1704.80, "finance_cost": 480.00,
            "pbt": 1224.80, "tax_expense": 306.20, "pat": 918.60,
            "total_assets": 11500.00, "fixed_assets": 7200.00,
            "current_assets": 2400.00, "investments": 1900.00,
            "total_equity": 5300.00, "long_term_debt": 3200.00,
            "short_term_debt": 1000.00, "total_debt": 4200.00,
            "current_liabilities": 3000.00,
            "ocf": 1800.00, "capex": -1200.00, "fcff": 600.00,
        }
    ),
}

IHCL_PROVISIONAL = FinancialStatement(
    entity_id="IHCL001", period="FY2026_P", statement_type="standalone",
    source="provisional", as_of_date=date(2026, 12, 31),
    line_items={
        "revenue_operating": 7800.00, "ebitda": 3432.00,
        "pat": 1700.00, "total_debt": 4500.00, "total_equity": 8200.00,
        "total_assets": 16000.00,
    }
)

IHCL_FACILITY = FacilityRequest(
    facility_id="FAC_IHCL_001", entity_id="IHCL001",
    case_type=CaseType.ETB, facility_type=FacilityType.TERM_LOAN,
    amount_requested_cr=1200.00,
    purpose="Term loan for renovation and capacity expansion of Taj Palace Delhi and new Taj property in Udaipur",
    tenor_months=84, collateral_value_cr=2800.00, proposed_limit_cr=1200.00,
    existing_limit_cr=800.00,
)

IHCL_COLLATERAL = [
    Collateral(collateral_id="COL_IHCL_01", entity_id="IHCL001",
               collateral_type="Land & Building", description="Taj Palace Hotel, 2 Sardar Patel Marg, New Delhi — freehold property",
               market_value_cr=2200.00, forced_sale_value_cr=1540.00,
               valuation_date=date(2026, 5, 20), encumbrance_status="clear"),
    Collateral(collateral_id="COL_IHCL_02", entity_id="IHCL001",
               collateral_type="Land & Building", description="Land parcel at Udaipur (8 acres) for new Taj resort",
               market_value_cr=600.00, forced_sale_value_cr=420.00,
               valuation_date=date(2026, 5, 20), encumbrance_status="clear"),
]

IHCL_MARKET_SIGNALS = [
    MarketSignal(entity_id="IHCL001", signal_type="news",
                 headline="IHCL reports record ARR of ₹14,500 across Taj portfolio; occupancy at 75%",
                 sentiment="positive", severity=RiskSeverity.LOW,
                 source_name="Economic Times", signal_date=date(2026, 7, 15)),
    MarketSignal(entity_id="IHCL001", signal_type="analyst",
                 headline="CRISIL upgrades IHCL outlook to Positive from Stable; strong deleveraging noted",
                 sentiment="positive", severity=RiskSeverity.LOW,
                 source_name="CRISIL", signal_date=date(2026, 9, 22)),
    MarketSignal(entity_id="IHCL001", signal_type="news",
                 headline="Taj Hotels wins World's Strongest Hotel Brand 2026 by Brand Finance",
                 sentiment="positive", severity=RiskSeverity.LOW,
                 source_name="Brand Finance", signal_date=date(2026, 10, 5)),
]

# ── ETB data for IHCL (existing banking relationship) ──
IHCL_EXISTING_EXPOSURE = [
    ExistingExposure(facility_id="EXP_IHCL_01", entity_id="IHCL001",
                     facility_type="Term Loan", sanctioned_limit_cr=800.00,
                     outstanding_cr=520.00, utilization_pct=65.0,
                     overdue_days=0, classification="Standard"),
    ExistingExposure(facility_id="EXP_IHCL_02", entity_id="IHCL001",
                     facility_type="BG/LC (Non-Fund)", sanctioned_limit_cr=200.00,
                     outstanding_cr=145.00, utilization_pct=72.5,
                     overdue_days=0, classification="Standard"),
]

IHCL_CONDUCT = [
    ConductRecord(entity_id="IHCL001", period="Q1 FY2026",
                  avg_bank_balance_cr=85.00, credit_turnover_cr=320.00,
                  debit_turnover_cr=305.00, cheque_returns=0,
                  limit_utilization_pct=65.0, overdue_instances=0, max_overdue_days=0),
    ConductRecord(entity_id="IHCL001", period="Q2 FY2026",
                  avg_bank_balance_cr=92.00, credit_turnover_cr=340.00,
                  debit_turnover_cr=325.00, cheque_returns=0,
                  limit_utilization_pct=62.0, overdue_instances=0, max_overdue_days=0),
    ConductRecord(entity_id="IHCL001", period="Q3 FY2026",
                  avg_bank_balance_cr=110.00, credit_turnover_cr=380.00,
                  debit_turnover_cr=360.00, cheque_returns=0,
                  limit_utilization_pct=58.0, overdue_instances=0, max_overdue_days=0),
    ConductRecord(entity_id="IHCL001", period="Q4 FY2026",
                  avg_bank_balance_cr=125.00, credit_turnover_cr=420.00,
                  debit_turnover_cr=395.00, cheque_returns=0,
                  limit_utilization_pct=55.0, overdue_instances=0, max_overdue_days=0),
]

IHCL_COVENANTS = [
    CovenantRecord(entity_id="IHCL001", covenant_type="Financial",
                   required_value="Debt/EBITDA ≤ 2.5x", actual_value="1.69x",
                   compliance_status="compliant", period="FY2025"),
    CovenantRecord(entity_id="IHCL001", covenant_type="Financial",
                   required_value="DSCR ≥ 1.5x", actual_value="2.82x",
                   compliance_status="compliant", period="FY2025"),
    CovenantRecord(entity_id="IHCL001", covenant_type="Financial",
                   required_value="Current Ratio ≥ 0.8x", actual_value="0.91x",
                   compliance_status="compliant", period="FY2025"),
]


# ═══════════════════════════════════════════════════════════════════════════════
# CORE BANKING DATA — ETB Companies (LOAN, BCLC, LIABILITY, FEES/COMMISSION)
# ═══════════════════════════════════════════════════════════════════════════════

IHCL_CORE_BANKING = {
    "loan_accounts": [
        {"account_number": "ACC_IHC_TL01", "entity_id": "IHCL001", "facility_type": "TL",
         "sanction_limit_cr": 800.00, "outstanding_cr": 680.00, "interest_rate_pct": 8.75,
         "overdue_amount_cr": 0.0, "dpd": 0, "asset_classification": "Standard",
         "sanction_date": "2021-06-15", "maturity_date": "2028-06-15", "repayment_frequency": "Monthly"},
        {"account_number": "ACC_IHC_BG01", "entity_id": "IHCL001", "facility_type": "BG",
         "sanction_limit_cr": 200.00, "outstanding_cr": 165.00, "interest_rate_pct": 1.50,
         "overdue_amount_cr": 0.0, "dpd": 0, "asset_classification": "Standard",
         "sanction_date": "2022-03-20", "maturity_date": "2026-03-20", "repayment_frequency": "NA"},
    ],
    "bclc": {
        "total_fund_based_cr": 680.00, "total_non_fund_based_cr": 165.00,
        "total_exposure_cr": 845.00,
        "single_borrower_limit_pct": 1.8, "group_borrower_limit_pct": 3.2,
        "within_single_limit": True, "within_group_limit": True,
        "industry_exposure_pct": 4.5, "sector_ceiling_pct": 15.0,
        "rating_based_limit_cr": 2500.00,
    },
    "liability": {
        "current_account_balance_cr": 12.50, "savings_balance_cr": 0.0,
        "fixed_deposit_cr": 85.00, "total_deposits_cr": 97.50,
        "average_balance_6m_cr": 42.80, "reciprocal_business_cr": 97.50,
        "cross_sell_products": ["Cash Management", "Trade Finance", "Forex Services"],
    },
    "fees_commission": [
        {"period": "FY2025", "processing_fees_cr": 2.40, "renewal_fees_cr": 0.80,
         "lc_commission_cr": 1.20, "bg_commission_cr": 0.95,
         "forex_income_cr": 0.45, "other_charges_cr": 0.30, "total_income_cr": 6.10},
        {"period": "FY2024", "processing_fees_cr": 1.80, "renewal_fees_cr": 0.60,
         "lc_commission_cr": 0.90, "bg_commission_cr": 0.85,
         "forex_income_cr": 0.35, "other_charges_cr": 0.25, "total_income_cr": 4.75},
    ],
    "total_exposure_cr": 845.00,
    "overall_asset_classification": "Standard",
    "relationship_since": "2018-04-01",
    "relationship_years": 8,
}

DLFR_CORE_BANKING = {
    "loan_accounts": [
        {"account_number": "ACC_DLF_TL01", "entity_id": "DLFR001", "facility_type": "TL",
         "sanction_limit_cr": 1500.00, "outstanding_cr": 1380.00, "interest_rate_pct": 9.50,
         "overdue_amount_cr": 45.00, "dpd": 38, "asset_classification": "SMA-1",
         "sanction_date": "2020-09-10", "maturity_date": "2027-09-10", "repayment_frequency": "Monthly"},
        {"account_number": "ACC_DLF_CC01", "entity_id": "DLFR001", "facility_type": "CC",
         "sanction_limit_cr": 800.00, "outstanding_cr": 765.00, "interest_rate_pct": 10.25,
         "overdue_amount_cr": 0.0, "dpd": 0, "asset_classification": "Standard",
         "sanction_date": "2021-04-01", "maturity_date": "2026-03-31", "repayment_frequency": "Monthly"},
    ],
    "bclc": {
        "total_fund_based_cr": 2145.00, "total_non_fund_based_cr": 250.00,
        "total_exposure_cr": 2395.00,
        "single_borrower_limit_pct": 5.2, "group_borrower_limit_pct": 8.8,
        "within_single_limit": True, "within_group_limit": True,
        "industry_exposure_pct": 6.8, "sector_ceiling_pct": 15.0,
        "rating_based_limit_cr": 3000.00,
    },
    "liability": {
        "current_account_balance_cr": 8.20, "savings_balance_cr": 0.0,
        "fixed_deposit_cr": 25.00, "total_deposits_cr": 33.20,
        "average_balance_6m_cr": 18.50, "reciprocal_business_cr": 33.20,
        "cross_sell_products": ["Current Account", "Project Finance"],
    },
    "fees_commission": [
        {"period": "FY2025", "processing_fees_cr": 3.50, "renewal_fees_cr": 1.20,
         "lc_commission_cr": 0.0, "bg_commission_cr": 0.45,
         "forex_income_cr": 0.0, "other_charges_cr": 0.85, "total_income_cr": 6.00},
    ],
    "total_exposure_cr": 2395.00,
    "overall_asset_classification": "SMA-1",
    "relationship_since": "2015-08-01",
    "relationship_years": 11,
}

NTPC_CORE_BANKING = {
    "loan_accounts": [
        {"account_number": "ACC_NTP_TL01", "entity_id": "NTPC001", "facility_type": "TL",
         "sanction_limit_cr": 5000.00, "outstanding_cr": 4200.00, "interest_rate_pct": 7.80,
         "overdue_amount_cr": 0.0, "dpd": 0, "asset_classification": "Standard",
         "sanction_date": "2019-01-15", "maturity_date": "2029-01-15", "repayment_frequency": "Quarterly"},
        {"account_number": "ACC_NTP_BG01", "entity_id": "NTPC001", "facility_type": "BG",
         "sanction_limit_cr": 2000.00, "outstanding_cr": 1650.00, "interest_rate_pct": 0.75,
         "overdue_amount_cr": 0.0, "dpd": 0, "asset_classification": "Standard",
         "sanction_date": "2020-06-01", "maturity_date": "2027-06-01", "repayment_frequency": "NA"},
    ],
    "bclc": {
        "total_fund_based_cr": 4200.00, "total_non_fund_based_cr": 1650.00,
        "total_exposure_cr": 5850.00,
        "single_borrower_limit_pct": 3.5, "group_borrower_limit_pct": 6.0,
        "within_single_limit": True, "within_group_limit": True,
        "industry_exposure_pct": 8.2, "sector_ceiling_pct": 20.0,
        "rating_based_limit_cr": 15000.00,
    },
    "liability": {
        "current_account_balance_cr": 125.00, "savings_balance_cr": 0.0,
        "fixed_deposit_cr": 500.00, "total_deposits_cr": 625.00,
        "average_balance_6m_cr": 280.00, "reciprocal_business_cr": 625.00,
        "cross_sell_products": ["Cash Management", "LC/BG", "Trade Finance", "Forex"],
    },
    "fees_commission": [
        {"period": "FY2025", "processing_fees_cr": 5.00, "renewal_fees_cr": 2.50,
         "lc_commission_cr": 3.80, "bg_commission_cr": 4.50,
         "forex_income_cr": 1.20, "other_charges_cr": 0.80, "total_income_cr": 17.80},
        {"period": "FY2024", "processing_fees_cr": 4.50, "renewal_fees_cr": 2.00,
         "lc_commission_cr": 3.20, "bg_commission_cr": 4.00,
         "forex_income_cr": 1.00, "other_charges_cr": 0.60, "total_income_cr": 15.30},
    ],
    "total_exposure_cr": 5850.00,
    "overall_asset_classification": "Standard",
    "relationship_since": "2010-04-01",
    "relationship_years": 16,
}


# ═══════════════════════════════════════════════════════════════════════════════
# COMPANY 19: APOLLO HOSPITALS ENTERPRISE LTD (Listed NTB, Healthcare — GROWTH)
# ═══════════════════════════════════════════════════════════════════════════════

APOL_BORROWER = Borrower(
    entity_id="APOL001",
    company_name="Apollo Hospitals Enterprise Limited",
    cin="L85110TN1979PLC008035",
    pan="AAACA1234K",
    borrower_type=BorrowerType.LISTED,
    sector=Sector.HEALTHCARE,
    subsector="Hospitals & Health Services",
    date_of_incorporation=date(1979, 1, 30),
    registered_state="Tamil Nadu",
    registered_address="19, Bishop Gardens, Raja Annamalai Puram, Chennai 600028",
    authorized_capital=350.00,
    paid_up_capital=143.60,
    listed_exchange="BSE, NSE",
    nse_symbol="APOLLOHOSP",
    isin="INE437A01024",
    credit_rating="ICRA AA+/Stable",
    rating_agency="ICRA",
    employee_count=89000,
    website="www.apollohospitals.com",
)

APOL_GROUP = GroupEntity(
    group_id="GRP_APOL", group_name="Apollo Group",
    parent_entity_id="APOL001",
    entities=["APOL001", "Apollo Health & Lifestyle Ltd", "Apollo Pharmacy",
              "Apollo Munich Health Insurance", "Apollo Medics Ltd"],
    promoter_holding_pct=29.27, institutional_holding_pct=48.5, public_holding_pct=22.23,
)

APOL_DIRECTORS = [
    DirectorPromoter(din="00003964", name="Dr. Prathap C. Reddy", designation="Executive Chairman",
                     entity_id="APOL001", is_promoter=True, net_worth_cr=18500.0,
                     other_directorships=["Apollo Health & Lifestyle Ltd", "Apollo Medics Ltd"]),
    DirectorPromoter(din="00001873", name="Suneeta Reddy", designation="Managing Director",
                     entity_id="APOL001", is_promoter=True, net_worth_cr=4200.0,
                     other_directorships=["Apollo Health & Lifestyle Ltd"]),
    DirectorPromoter(din="00056809", name="Shobana Kamineni", designation="Executive Vice Chairperson",
                     entity_id="APOL001", is_promoter=True, net_worth_cr=3800.0),
    DirectorPromoter(din="05171022", name="Krishnan Akhileswaran", designation="CFO",
                     entity_id="APOL001", is_promoter=False, net_worth_cr=85.0),
]

APOL_FINANCIALS = {
    "FY2025": FinancialStatement(
        entity_id="APOL001", period="FY2025", statement_type="consolidated",
        source="audited", as_of_date=date(2025, 3, 31),
        line_items={
            "revenue_operating": 21245.00, "other_income": 412.00,
            "total_income": 21657.00, "raw_material_cost": 5463.00,
            "employee_cost": 5842.00, "other_expenses": 5359.00,
            "ebitda": 3609.00, "depreciation": 1124.00,
            "ebit": 2897.00, "finance_cost": 578.00,
            "pbt": 2319.00, "tax_expense": 727.00, "pat": 1592.00,
            "total_assets": 24300.00, "fixed_assets": 12800.00,
            "current_assets": 6200.00, "investments": 5300.00,
            "total_equity": 10800.00, "long_term_debt": 4200.00,
            "short_term_debt": 1700.00, "total_debt": 5900.00,
            "current_liabilities": 6850.00, "trade_receivables": 2310.00,
            "inventory": 680.00, "cash_equivalents": 1420.00,
            "trade_payables": 2940.00,
            "ocf": 3200.00, "capex": -2100.00, "fcff": 1100.00,
            "market_cap": 98000.00, "working_capital": -650.00,
        }
    ),
    "FY2024": FinancialStatement(
        entity_id="APOL001", period="FY2024", statement_type="consolidated",
        source="audited", as_of_date=date(2024, 3, 31),
        line_items={
            "revenue_operating": 19059.00, "other_income": 378.00,
            "total_income": 19437.00, "raw_material_cost": 4989.00,
            "employee_cost": 5245.00, "other_expenses": 4927.00,
            "ebitda": 2898.00, "depreciation": 1018.00,
            "ebit": 2252.00, "finance_cost": 524.00,
            "pbt": 1734.00, "tax_expense": 351.00, "pat": 1383.00,
            "total_assets": 22100.00, "fixed_assets": 11600.00,
            "current_assets": 5680.00, "investments": 4820.00,
            "total_equity": 9500.00, "long_term_debt": 3700.00,
            "short_term_debt": 1500.00, "total_debt": 5200.00,
            "current_liabilities": 6320.00, "trade_receivables": 2050.00,
            "inventory": 620.00, "cash_equivalents": 1180.00,
            "trade_payables": 2640.00,
            "ocf": 2800.00, "capex": -1850.00, "fcff": 950.00,
        }
    ),
    "FY2023": FinancialStatement(
        entity_id="APOL001", period="FY2023", statement_type="consolidated",
        source="audited", as_of_date=date(2023, 3, 31),
        line_items={
            "revenue_operating": 16612.00, "other_income": 325.00,
            "total_income": 16937.00, "raw_material_cost": 4395.00,
            "employee_cost": 4572.00, "other_expenses": 4236.00,
            "ebitda": 2451.00, "depreciation": 923.00,
            "ebit": 1853.00, "finance_cost": 478.00,
            "pbt": 1375.00, "tax_expense": 231.00, "pat": 1144.00,
            "total_assets": 19800.00, "fixed_assets": 10200.00,
            "current_assets": 5120.00, "investments": 4480.00,
            "total_equity": 8200.00, "long_term_debt": 3300.00,
            "short_term_debt": 1500.00, "total_debt": 4800.00,
            "current_liabilities": 5740.00,
            "ocf": 2400.00, "capex": -1600.00, "fcff": 800.00,
        }
    ),
    "FY2022": FinancialStatement(
        entity_id="APOL001", period="FY2022", statement_type="consolidated",
        source="audited", as_of_date=date(2022, 3, 31),
        line_items={
            "revenue_operating": 14738.00, "other_income": 287.00,
            "total_income": 15025.00, "raw_material_cost": 3952.00,
            "employee_cost": 4028.00, "other_expenses": 3805.00,
            "ebitda": 1918.00, "depreciation": 842.00,
            "ebit": 1443.00, "finance_cost": 435.00,
            "pbt": 1078.00, "tax_expense": 162.00, "pat": 916.00,
            "total_assets": 18500.00, "fixed_assets": 9500.00,
            "current_assets": 4680.00, "investments": 4320.00,
            "total_equity": 7200.00, "long_term_debt": 3000.00,
            "short_term_debt": 1500.00, "total_debt": 4500.00,
            "current_liabilities": 5210.00,
            "ocf": 2100.00, "capex": -1400.00, "fcff": 700.00,
        }
    ),
}

APOL_PROVISIONAL = FinancialStatement(
    entity_id="APOL001", period="FY2026_P", statement_type="consolidated",
    source="provisional", as_of_date=date(2026, 12, 31),
    line_items={
        "revenue_operating": 24200.00, "ebitda": 4356.00,
        "pat": 1900.00, "total_debt": 6200.00, "total_equity": 12500.00,
        "total_assets": 27500.00,
    }
)

APOL_FACILITY = FacilityRequest(
    facility_id="FAC_APOL_001", entity_id="APOL001",
    case_type=CaseType.NTB, facility_type=FacilityType.TERM_LOAN,
    amount_requested_cr=750.00,
    purpose="Term loan for hospital expansion (new 500-bed hospital in Pune) and working capital for pharmacy operations",
    tenor_months=84, collateral_value_cr=1200.00, proposed_limit_cr=750.00,
)

APOL_COLLATERAL = [
    Collateral(collateral_id="COL_APOL_01", entity_id="APOL001",
               collateral_type="Immovable Property", description="First charge on Apollo Health City, Hyderabad — land & building",
               market_value_cr=850.00, forced_sale_value_cr=595.00,
               valuation_date=date(2025, 6, 1), encumbrance_status="clear"),
    Collateral(collateral_id="COL_APOL_02", entity_id="APOL001",
               collateral_type="Movable Assets", description="Hypothecation of medical equipment across 73 hospitals",
               market_value_cr=420.00, forced_sale_value_cr=252.00,
               valuation_date=date(2025, 6, 1), encumbrance_status="clear"),
]

APOL_MARKET_SIGNALS = [
    MarketSignal(entity_id="APOL001", signal_type="news",
                 headline="Apollo Hospitals revenue crosses ₹21,000 Cr; EBITDA margin expands to 17%",
                 sentiment="positive", severity=RiskSeverity.LOW,
                 source_name="Economic Times", signal_date=date(2025, 5, 15)),
    MarketSignal(entity_id="APOL001", signal_type="analyst",
                 headline="ICRA reaffirms AA+/Stable for Apollo; strong hospital ARPOB growth noted",
                 sentiment="positive", severity=RiskSeverity.LOW,
                 source_name="ICRA", signal_date=date(2025, 7, 10)),
    MarketSignal(entity_id="APOL001", signal_type="news",
                 headline="Apollo 24|7 digital platform crosses 100M users; pharmacy network at 4,200+ stores",
                 sentiment="positive", severity=RiskSeverity.LOW,
                 source_name="Mint", signal_date=date(2025, 8, 22)),
]


# ═══════════════════════════════════════════════════════════════════════════════
# COMPANY 19: PNC INFRATECH LIMITED (Listed NTB, Infrastructure — Road EPC)
# ═══════════════════════════════════════════════════════════════════════════════

PNCR_BORROWER = Borrower(
    entity_id="PNCR001",
    company_name="PNC Infratech Limited",
    cin="L45201DL1999PLC195937",
    pan="AABCP1234R",
    borrower_type=BorrowerType.LISTED,
    sector=Sector.INFRASTRUCTURE,
    subsector="Road & Highway Construction — EPC",
    date_of_incorporation=date(1999, 8, 9),
    registered_state="Delhi",
    registered_address="NBCC Plaza, Tower II, 4th Floor, Pushp Vihar, Sector V, Saket, New Delhi 110017",
    authorized_capital=150.00,
    paid_up_capital=51.30,
    listed_exchange="BSE, NSE",
    nse_symbol="PNCINFRA",
    isin="INE195N01029",
    credit_rating="CARE AA+/Stable",
    rating_agency="CARE",
    employee_count=14500,
    website="www.pncinfra.com",
)

PNCR_GROUP = GroupEntity(
    group_id="GRP_PNCR", group_name="PNC Infratech Group",
    parent_entity_id="PNCR001",
    entities=["PNCR001", "PNC Infratech Pvt Ltd", "PNC Raebareli Highways Ltd",
              "PNC Bundelkhand Expressway Ltd", "PNC Kanpur Highways Ltd"],
    promoter_holding_pct=56.07, institutional_holding_pct=33.10, public_holding_pct=10.83,
)

PNCR_DIRECTORS = [
    DirectorPromoter(din="00056994", name="Pradeep Kumar Jain", designation="Chairman & Managing Director",
                     entity_id="PNCR001", is_promoter=True, net_worth_cr=1200.0,
                     other_directorships=["PNC Infratech Pvt Ltd", "PNC Bundelkhand Expressway Ltd"]),
    DirectorPromoter(din="00057760", name="Chakresh Kumar Jain", designation="Managing Director",
                     entity_id="PNCR001", is_promoter=True, net_worth_cr=980.0,
                     other_directorships=["PNC Raebareli Highways Ltd", "PNC Kanpur Highways Ltd"]),
    DirectorPromoter(din="07889421", name="Yogesh Kumar Jain", designation="Managing Director",
                     entity_id="PNCR001", is_promoter=True, net_worth_cr=650.0,
                     other_directorships=["PNC Infratech Pvt Ltd"]),
    DirectorPromoter(din="08123456", name="Ruchi Bisht", designation="Independent Director",
                     entity_id="PNCR001", is_promoter=False, net_worth_cr=18.0,
                     other_directorships=["NHAI Advisory Board"]),
]

PNCR_FINANCIALS = {
    "FY2025": FinancialStatement(
        entity_id="PNCR001", period="FY2025", statement_type="consolidated",
        source="audited", as_of_date=date(2025, 3, 31),
        line_items={
            "revenue_operating": 8650.00, "other_income": 185.00,
            "total_income": 8835.00, "raw_material_cost": 4152.00,
            "employee_cost": 519.00, "other_expenses": 2160.00,
            "ebitda": 2004.00, "depreciation": 520.00,
            "ebit": 1484.00, "finance_cost": 610.00,
            "pbt": 1059.00, "tax_expense": 150.00, "pat": 909.00,
            "total_assets": 15610.00, "fixed_assets": 6800.00,
            "current_assets": 5850.00, "investments": 2960.00,
            "total_equity": 5185.00, "long_term_debt": 5618.00,
            "short_term_debt": 2407.00, "total_debt": 8025.00,
            "current_liabilities": 4425.00, "trade_receivables": 1640.00,
            "inventory": 1970.00, "cash_equivalents": 680.00,
            "trade_payables": 2450.00,
            "ocf": 1850.00, "capex": -780.00, "fcff": 1070.00,
            "market_cap": 22500.00, "working_capital": 1425.00,
            "retained_earnings": 4200.00,
        }
    ),
    "FY2024": FinancialStatement(
        entity_id="PNCR001", period="FY2024", statement_type="consolidated",
        source="audited", as_of_date=date(2024, 3, 31),
        line_items={
            "revenue_operating": 7956.00, "other_income": 152.00,
            "total_income": 8108.00, "raw_material_cost": 3978.00,
            "employee_cost": 477.00, "other_expenses": 2068.00,
            "ebitda": 1585.00, "depreciation": 445.00,
            "ebit": 1140.00, "finance_cost": 490.00,
            "pbt": 802.00, "tax_expense": 144.00, "pat": 658.00,
            "total_assets": 12632.00, "fixed_assets": 5200.00,
            "current_assets": 4880.00, "investments": 2552.00,
            "total_equity": 4285.00, "long_term_debt": 4180.00,
            "short_term_debt": 2102.00, "total_debt": 6282.00,
            "current_liabilities": 3865.00, "trade_receivables": 1505.00,
            "inventory": 1810.00, "cash_equivalents": 520.00,
            "trade_payables": 2210.00,
            "ocf": 1420.00, "capex": -650.00, "fcff": 770.00,
            "market_cap": 19200.00, "working_capital": 1015.00,
            "retained_earnings": 3350.00,
        }
    ),
    "FY2023": FinancialStatement(
        entity_id="PNCR001", period="FY2023", statement_type="consolidated",
        source="audited", as_of_date=date(2023, 3, 31),
        line_items={
            "revenue_operating": 7208.00, "other_income": 120.00,
            "total_income": 7328.00, "raw_material_cost": 3604.00,
            "employee_cost": 433.00, "other_expenses": 1802.00,
            "ebitda": 1489.00, "depreciation": 380.00,
            "ebit": 1109.00, "finance_cost": 420.00,
            "pbt": 809.00, "tax_expense": 229.00, "pat": 580.00,
            "total_assets": 10645.00, "fixed_assets": 4350.00,
            "current_assets": 4120.00, "investments": 2175.00,
            "total_equity": 3628.00, "long_term_debt": 3115.00,
            "short_term_debt": 1678.00, "total_debt": 4793.00,
            "current_liabilities": 3224.00, "trade_receivables": 1360.00,
            "inventory": 1640.00, "cash_equivalents": 380.00,
            "trade_payables": 1980.00,
            "ocf": 1250.00, "capex": -580.00, "fcff": 670.00,
            "market_cap": 14800.00, "working_capital": 896.00,
            "retained_earnings": 2690.00,
        }
    ),
    "FY2022": FinancialStatement(
        entity_id="PNCR001", period="FY2022", statement_type="consolidated",
        source="audited", as_of_date=date(2022, 3, 31),
        line_items={
            "revenue_operating": 5620.00, "other_income": 98.00,
            "total_income": 5718.00, "raw_material_cost": 2810.00,
            "employee_cost": 337.00, "other_expenses": 1405.00,
            "ebitda": 1166.00, "depreciation": 310.00,
            "ebit": 856.00, "finance_cost": 340.00,
            "pbt": 614.00, "tax_expense": 172.00, "pat": 442.00,
            "total_assets": 8520.00, "fixed_assets": 3600.00,
            "current_assets": 3380.00, "investments": 1540.00,
            "total_equity": 3050.00, "long_term_debt": 2380.00,
            "short_term_debt": 1290.00, "total_debt": 3670.00,
            "current_liabilities": 2470.00, "trade_receivables": 1080.00,
            "inventory": 1370.00, "cash_equivalents": 280.00,
            "trade_payables": 1520.00,
            "ocf": 980.00, "capex": -450.00, "fcff": 530.00,
            "market_cap": 11500.00, "working_capital": 910.00,
            "retained_earnings": 2050.00,
        }
    ),
}

PNCR_PROVISIONAL = FinancialStatement(
    entity_id="PNCR001", period="FY2026_P", statement_type="consolidated",
    source="provisional", as_of_date=date(2026, 12, 31),
    line_items={
        "revenue_operating": 10200.00, "ebitda": 2448.00,
        "pat": 1100.00, "total_debt": 9200.00, "total_equity": 6100.00,
        "total_assets": 18500.00,
    }
)

PNCR_FACILITY = FacilityRequest(
    facility_id="FAC_PNCR_001", entity_id="PNCR001",
    case_type=CaseType.NTB, facility_type=FacilityType.TERM_LOAN,
    amount_requested_cr=1500.00,
    purpose="Term loan for execution of NHAI highway EPC projects — 4-laning of NH-44 (Agra-Lucknow section, 220 km) and Bundelkhand Expressway Phase-II (145 km). Funds to cover mobilization advance, equipment procurement (pavers, batching plants, excavators), and bridge/flyover sub-contracting.",
    tenor_months=72, collateral_value_cr=2100.00, proposed_limit_cr=1500.00,
)

PNCR_COLLATERAL = [
    Collateral(collateral_id="COL_PNCR_001", entity_id="PNCR001",
               collateral_type="Immovable Property",
               description="BOT toll collection rights — Agra-Lucknow section (22-year concession, residual 16 years)",
               market_value_cr=1400.00, forced_sale_value_cr=980.00,
               valuation_date=date(2025, 3, 15)),
    Collateral(collateral_id="COL_PNCR_002", entity_id="PNCR001",
               collateral_type="Movable Assets",
               description="Construction equipment fleet: 28 pavers, 15 batching plants, 42 excavators, 65 tippers",
               market_value_cr=520.00, forced_sale_value_cr=312.00,
               valuation_date=date(2025, 2, 28)),
    Collateral(collateral_id="COL_PNCR_003", entity_id="PNCR001",
               collateral_type="Immovable Property",
               description="Registered office building and land — 2.5 acres, Gomti Nagar, Lucknow",
               market_value_cr=180.00, forced_sale_value_cr=126.00,
               valuation_date=date(2025, 1, 10)),
]

PNCR_MARKET_SIGNALS = [
    MarketSignal(entity_id="PNCR001", signal_type="news",
                 headline="PNC Infratech bags NHAI highway project worth ₹2,400 Cr in Uttar Pradesh",
                 sentiment="positive", severity=RiskSeverity.LOW,
                 source_name="Economic Times", signal_date=date(2025, 7, 15)),
    MarketSignal(entity_id="PNCR001", signal_type="rating_action",
                 headline="CARE reaffirms AA+/Stable on PNC Infratech; order book at 3.2x revenue",
                 sentiment="positive", severity=RiskSeverity.LOW,
                 source_name="CARE Ratings", signal_date=date(2025, 6, 20)),
    MarketSignal(entity_id="PNCR001", signal_type="news",
                 headline="PNC Infratech completes 220 km of NH-44 4-laning ahead of schedule; NHAI bonus of ₹45 Cr",
                 sentiment="positive", severity=RiskSeverity.LOW,
                 source_name="Business Standard", signal_date=date(2025, 5, 10)),
    MarketSignal(entity_id="PNCR001", signal_type="news",
                 headline="Rising bitumen and steel prices may compress EPC margins in H2 FY26 — analyst report",
                 sentiment="negative", severity=RiskSeverity.MEDIUM,
                 source_name="Motilal Oswal Research", signal_date=date(2025, 4, 28)),
]

# Infrastructure-specific operational metrics for road/highway EPC companies
PNCR_INFRA_METRICS = {
    "order_book": {
        "total_order_book_cr": 27680.00,
        "book_to_bill_ratio": 3.2,
        "epc_orders_cr": 18500.00,
        "bot_ham_orders_cr": 9180.00,
        "orders_received_fy25_cr": 12400.00,
        "executable_order_book_cr": 24500.00,
    },
    "project_pipeline": [
        {"project_name": "NH-44 4-Laning (Agra-Lucknow)", "length_km": 220, "contract_value_cr": 3850.00,
         "completion_pct": 92, "model": "EPC", "client": "NHAI", "target_completion": "Q2 FY2026"},
        {"project_name": "Bundelkhand Expressway Phase-II", "length_km": 145, "contract_value_cr": 2680.00,
         "completion_pct": 35, "model": "HAM", "client": "UPEIDA", "target_completion": "Q4 FY2028"},
        {"project_name": "Delhi-Vadodara Greenfield (Pkg-4)", "length_km": 118, "contract_value_cr": 2200.00,
         "completion_pct": 68, "model": "EPC", "client": "NHAI", "target_completion": "Q1 FY2027"},
        {"project_name": "Gorakhpur Link Expressway", "length_km": 92, "contract_value_cr": 1580.00,
         "completion_pct": 15, "model": "HAM", "client": "UPEIDA", "target_completion": "Q2 FY2029"},
        {"project_name": "NH-30 Widening (Varanasi-Jaunpur)", "length_km": 76, "contract_value_cr": 1250.00,
         "completion_pct": 55, "model": "EPC", "client": "MoRTH", "target_completion": "Q3 FY2026"},
    ],
    "execution_metrics": {
        "km_executed_fy25": 385,
        "km_executed_fy24": 340,
        "km_executed_fy23": 295,
        "avg_construction_cost_per_km_cr": 17.5,
        "avg_land_acquisition_cost_per_sq_km_cr": 8.2,
        "avg_land_acquisition_cost_per_hectare_cr": 0.82,
        "effective_construction_days_per_year": 255,
        "equipment_utilization_pct": 82.5,
    },
    "bot_ham_portfolio": {
        "total_concession_assets": 4,
        "total_concession_value_cr": 9180.00,
        "annual_toll_revenue_cr": 1905.00,
        "avg_residual_concession_years": 14.5,
        "assets": [
            {"name": "Agra-Lucknow BOT (NH-44)", "length_km": 220, "concession_years": 22,
             "residual_years": 16, "annual_toll_cr": 680.00, "model": "BOT-Toll"},
            {"name": "Raebareli-Prayagraj BOT", "length_km": 165, "concession_years": 20,
             "residual_years": 14, "annual_toll_cr": 520.00, "model": "BOT-Toll"},
            {"name": "Kanpur Southern Bypass HAM", "length_km": 85, "concession_years": 15,
             "residual_years": 12, "annual_toll_cr": 385.00, "model": "HAM"},
            {"name": "Lucknow Ring Road HAM", "length_km": 62, "concession_years": 15,
             "residual_years": 13, "annual_toll_cr": 320.00, "model": "HAM"},
        ],
    },
    "development_projections": {
        "projected_km_fy26": 450,
        "projected_km_fy27": 520,
        "projected_revenue_fy26_cr": 10200.00,
        "projected_revenue_fy27_cr": 12500.00,
        "capex_plan_fy26_cr": 950.00,
        "capex_plan_fy27_cr": 1100.00,
        "land_bank_hectares": 185,
        "land_bank_value_cr": 151.70,
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# COMPANY 19: MADRAS FERTILIZERS LIMITED (Listed NTB, Manufacturing — PSU)
# ═══════════════════════════════════════════════════════════════════════════════

MFL_BORROWER = Borrower(
    entity_id="MFL001",
    company_name="Madras Fertilizers Limited",
    cin="L24100TN1966GOI005765",
    pan="AAACM1234A",
    borrower_type=BorrowerType.LISTED,
    sector=Sector.MANUFACTURING,
    subsector="Fertilizers — PSU",
    date_of_incorporation=date(1966, 12, 20),
    registered_state="Tamil Nadu",
    registered_address="Manali, Chennai — 600 068, Tamil Nadu",
    authorized_capital=1000.0,
    paid_up_capital=474.2,
    listed_exchange="NSE/BSE",
    nse_symbol="MADRASFERT",
    bse_code="590011",
    credit_rating="CARE BBB-/Stable",
    rating_agency="CARE",
    website="www.madrasfert.co.in",
    employee_count=1650,
)

MFL_GROUP = GroupEntity(
    group_id="GRP-MFL001",
    group_name="Madras Fertilizers Limited",
    parent_entity_id="MFL001",
    entities=["MFL001"],
)

MFL_DIRECTORS = [
    DirectorPromoter(
        entity_id="MFL001", name="Shri K. Ramanathan",
        din="DIN08123456", designation="Chairman & Managing Director",
        date_of_appointment=date(2021, 8, 1),
        is_promoter=False,
    ),
    DirectorPromoter(
        entity_id="MFL001", name="Shri V. Shanmugam",
        din="DIN07234567", designation="Director (Finance)",
        date_of_appointment=date(2020, 3, 15),
        is_promoter=False,
    ),
    DirectorPromoter(
        entity_id="MFL001", name="Shri N. Palaniswamy",
        din="DIN06345678", designation="Director (Technical)",
        date_of_appointment=date(2019, 6, 10),
        is_promoter=False,
    ),
    DirectorPromoter(
        entity_id="MFL001", name="Smt. R. Lakshmi",
        din="DIN09456789", designation="Independent Director",
        date_of_appointment=date(2022, 9, 20),
        is_promoter=False,
    ),
]

MFL_FINANCIALS = {
    "FY2023": FinancialStatement(
        entity_id="MFL001", period="FY2023", statement_type="standalone",
        source="audited", as_of_date=date(2023, 3, 31),
        line_items={
            "revenue_operating": 810.50, "other_income": 12.30,
            "total_income": 822.80, "raw_material_cost": 545.00,
            "employee_cost": 68.50, "other_expenses": 95.00,
            "ebitda": -11.50, "depreciation": 18.20,
            "ebit": -29.70, "finance_cost": 22.50,
            "pbt": -33.20, "tax_expense": -8.20, "pat": -25.00,
            "total_assets": 920.00, "fixed_assets": 310.00,
            "current_assets": 380.00, "investments": 0.0,
            "total_equity": 185.00, "long_term_debt": 180.00,
            "short_term_debt": 130.00, "total_debt": 310.00,
            "current_liabilities": 340.00, "trade_receivables": 125.00,
            "inventory": 95.00, "cash_equivalents": 22.00,
            "trade_payables": 145.00,
            "ocf": -5.00, "capex": -12.00, "fcff": -17.00,
        }
    ),
    "FY2024": FinancialStatement(
        entity_id="MFL001", period="FY2024", statement_type="standalone",
        source="audited", as_of_date=date(2024, 3, 31),
        line_items={
            "revenue_operating": 935.00, "other_income": 14.50,
            "total_income": 949.50, "raw_material_cost": 620.00,
            "employee_cost": 72.00, "other_expenses": 100.00,
            "ebitda": 25.00, "depreciation": 19.50,
            "ebit": 5.50, "finance_cost": 24.00,
            "pbt": 1.50, "tax_expense": 0.40, "pat": 1.10,
            "total_assets": 965.00, "fixed_assets": 320.00,
            "current_assets": 400.00, "investments": 0.0,
            "total_equity": 186.10, "long_term_debt": 195.00,
            "short_term_debt": 135.00, "total_debt": 330.00,
            "current_liabilities": 355.00, "trade_receivables": 135.00,
            "inventory": 110.00, "cash_equivalents": 18.00,
            "trade_payables": 155.00,
            "ocf": 15.00, "capex": -14.00, "fcff": 1.00,
        }
    ),
    "FY2025": FinancialStatement(
        entity_id="MFL001", period="FY2025", statement_type="standalone",
        source="audited", as_of_date=date(2025, 3, 31),
        line_items={
            "revenue_operating": 1050.00, "other_income": 16.00,
            "total_income": 1066.00, "raw_material_cost": 695.00,
            "employee_cost": 76.00, "other_expenses": 105.00,
            "ebitda": 45.00, "depreciation": 21.00,
            "ebit": 24.00, "finance_cost": 25.50,
            "pbt": 14.50, "tax_expense": 3.70, "pat": 10.80,
            "total_assets": 1020.00, "fixed_assets": 335.00,
            "current_assets": 420.00, "investments": 0.0,
            "total_equity": 196.90, "long_term_debt": 205.00,
            "short_term_debt": 140.00, "total_debt": 345.00,
            "current_liabilities": 365.00, "trade_receivables": 145.00,
            "inventory": 120.00, "cash_equivalents": 25.00,
            "trade_payables": 160.00,
            "ocf": 28.00, "capex": -18.00, "fcff": 10.00,
        }
    ),
}

MFL_PROVISIONAL = FinancialStatement(
    entity_id="MFL001", period="FY2026_P", statement_type="standalone",
    source="provisional", as_of_date=date(2026, 12, 31),
    line_items={
        "revenue_operating": 1180.00, "other_income": 18.00,
        "total_income": 1198.00, "raw_material_cost": 780.00,
        "employee_cost": 80.00, "other_expenses": 110.00,
        "ebitda": 55.00, "depreciation": 22.50,
        "ebit": 32.50, "finance_cost": 27.00,
        "pbt": 23.50, "tax_expense": 6.00, "pat": 17.50,
        "total_assets": 1080.00, "fixed_assets": 350.00,
        "current_assets": 445.00, "investments": 0.0,
        "total_equity": 214.40, "long_term_debt": 210.00,
        "short_term_debt": 145.00, "total_debt": 355.00,
        "current_liabilities": 375.00,
    }
)

MFL_FACILITY = FacilityRequest(
    facility_id="FAC-MFL001", entity_id="MFL001",
    case_type=CaseType.NTB, facility_type=FacilityType.WORKING_CAPITAL,
    amount_requested_cr=120.0,
    purpose="Working capital for procurement of raw materials (naphtha, ammonia) and operations",
    proposed_limit_cr=120.0,
)

MFL_COLLATERAL = [
    Collateral(
        collateral_id="COL_MFL_001", entity_id="MFL001",
        collateral_type="Plant & Machinery",
        description="Fertilizer manufacturing plant at Manali, Chennai — urea and complex fertilizer units",
        market_value_cr=220.00, forced_sale_value_cr=132.00,
        valuation_date=date(2025, 9, 15), encumbrance_status="hypothecated",
    ),
    Collateral(
        collateral_id="COL_MFL_002", entity_id="MFL001",
        collateral_type="Inventory",
        description="Raw material and finished goods inventory — urea, ammonium phosphate",
        market_value_cr=120.00, forced_sale_value_cr=72.00,
        valuation_date=date(2026, 1, 10), encumbrance_status="hypothecated",
    ),
    Collateral(
        collateral_id="COL_MFL_003", entity_id="MFL001",
        collateral_type="Trade Receivables",
        description="Receivables from state cooperative bodies and wholesale dealers",
        market_value_cr=145.00, forced_sale_value_cr=87.00,
        valuation_date=date(2026, 1, 10), encumbrance_status="assigned",
    ),
]

MFL_MARKET_SIGNALS = [
    MarketSignal(
        entity_id="MFL001", signal_type="news",
        headline="Central govt subsidy scheme boosts PSU fertilizer producers' margins",
        sentiment="positive", severity=RiskSeverity.LOW, source_name="Economic Times",
        signal_date=date(2025, 11, 15),
        details="New nutrient-based subsidy revision benefits complex fertilizer producers including Madras Fertilizers.",
    ),
    MarketSignal(
        entity_id="MFL001", signal_type="news",
        headline="Madras Fertilizers to revamp Manali plant with ₹250 Cr capex",
        sentiment="positive", severity=RiskSeverity.LOW, source_name="Business Standard",
        signal_date=date(2026, 2, 10),
        details="Company received board approval for plant modernization to improve ammonia and urea capacity.",
    ),
    MarketSignal(
        entity_id="MFL001", signal_type="regulatory",
        headline="CAG flags operational inefficiencies at Madras Fertilizers",
        sentiment="negative", severity=RiskSeverity.MEDIUM, source_name="CAG Report",
        signal_date=date(2025, 8, 20),
        details="CAG report highlights production downtime and inventory management issues at Manali plant.",
    ),
]


# ═══════════════════════════════════════════════════════════════════════════════
# COMPANY 20: MRF LIMITED (Listed NTB, Manufacturing — Tyres)
# ═══════════════════════════════════════════════════════════════════════════════

MRF_BORROWER = Borrower(
    entity_id="MRF001",
    company_name="MRF Limited",
    cin="L25111KL1960PLC001049",
    pan="AAACM5678B",
    borrower_type=BorrowerType.LISTED,
    sector=Sector.MANUFACTURING,
    subsector="Tyres — Premium Branded",
    date_of_incorporation=date(1960, 11, 5),
    registered_state="Kerala",
    registered_address="No. 114, Greams Road, Chennai — 600 006, Tamil Nadu",
    authorized_capital=10.0,
    paid_up_capital=4.24,
    listed_exchange="NSE/BSE",
    nse_symbol="MRF",
    bse_code="500290",
    credit_rating="CRISIL AA+/Stable",
    rating_agency="CRISIL",
    website="www.mrftyres.com",
    employee_count=20000,
)

MRF_GROUP = GroupEntity(
    group_id="GRP-MRF001",
    group_name="MRF Limited",
    parent_entity_id="MRF001",
    entities=["MRF001"],
)

MRF_DIRECTORS = [
    DirectorPromoter(
        entity_id="MRF001", name="Shri K.M. Mammen",
        din="DIN00020202", designation="Chairman & Managing Director",
        date_of_appointment=date(2014, 1, 1),
        is_promoter=True, net_worth_cr=4500.00,
    ),
    DirectorPromoter(
        entity_id="MRF001", name="Shri Arun Mammen",
        din="DIN00020303", designation="Vice Chairman & Managing Director",
        date_of_appointment=date(2016, 4, 1),
        is_promoter=True, net_worth_cr=1200.00,
    ),
    DirectorPromoter(
        entity_id="MRF001", name="Shri V. Sridhar",
        din="DIN00789012", designation="Director (Finance) & CFO",
        date_of_appointment=date(2019, 7, 15),
        is_promoter=False,
    ),
    DirectorPromoter(
        entity_id="MRF001", name="Smt. Ambika Mammen",
        din="DIN00345678", designation="Independent Director",
        date_of_appointment=date(2020, 10, 1),
        is_promoter=False,
    ),
]

MRF_FINANCIALS = {
    "FY2023": FinancialStatement(
        entity_id="MRF001", period="FY2023", statement_type="standalone",
        source="audited", as_of_date=date(2023, 3, 31),
        line_items={
            "revenue_operating": 22150.00, "other_income": 280.00,
            "total_income": 22430.00, "raw_material_cost": 13500.00,
            "employee_cost": 2200.00, "other_expenses": 4700.00,
            "ebitda": 1750.00, "depreciation": 1280.00,
            "ebit": 470.00, "finance_cost": 320.00,
            "pbt": 1430.00, "tax_expense": 360.00, "pat": 1070.00,
            "total_assets": 20500.00, "fixed_assets": 9500.00,
            "current_assets": 8200.00, "investments": 2800.00,
            "total_equity": 11200.00, "long_term_debt": 2500.00,
            "short_term_debt": 1300.00, "total_debt": 3800.00,
            "current_liabilities": 5800.00, "trade_receivables": 2400.00,
            "inventory": 3500.00, "cash_equivalents": 450.00,
            "trade_payables": 3200.00,
            "ocf": 2100.00, "capex": -1500.00, "fcff": 600.00,
            "market_cap": 52000.00,
        }
    ),
    "FY2024": FinancialStatement(
        entity_id="MRF001", period="FY2024", statement_type="standalone",
        source="audited", as_of_date=date(2024, 3, 31),
        line_items={
            "revenue_operating": 24500.00, "other_income": 310.00,
            "total_income": 24810.00, "raw_material_cost": 14800.00,
            "employee_cost": 2380.00, "other_expenses": 5020.00,
            "ebitda": 2300.00, "depreciation": 1350.00,
            "ebit": 950.00, "finance_cost": 340.00,
            "pbt": 1960.00, "tax_expense": 490.00, "pat": 1470.00,
            "total_assets": 22500.00, "fixed_assets": 10200.00,
            "current_assets": 9000.00, "investments": 3300.00,
            "total_equity": 12670.00, "long_term_debt": 2700.00,
            "short_term_debt": 1400.00, "total_debt": 4100.00,
            "current_liabilities": 6200.00, "trade_receivables": 2650.00,
            "inventory": 3800.00, "cash_equivalents": 550.00,
            "trade_payables": 3500.00,
            "ocf": 2800.00, "capex": -1800.00, "fcff": 1000.00,
            "market_cap": 58000.00,
        }
    ),
    "FY2025": FinancialStatement(
        entity_id="MRF001", period="FY2025", statement_type="standalone",
        source="audited", as_of_date=date(2025, 3, 31),
        line_items={
            "revenue_operating": 26200.00, "other_income": 350.00,
            "total_income": 26550.00, "raw_material_cost": 15800.00,
            "employee_cost": 2500.00, "other_expenses": 5450.00,
            "ebitda": 2500.00, "depreciation": 1420.00,
            "ebit": 1080.00, "finance_cost": 360.00,
            "pbt": 2140.00, "tax_expense": 540.00, "pat": 1600.00,
            "total_assets": 24200.00, "fixed_assets": 11000.00,
            "current_assets": 9800.00, "investments": 3400.00,
            "total_equity": 14270.00, "long_term_debt": 2800.00,
            "short_term_debt": 1500.00, "total_debt": 4300.00,
            "current_liabilities": 6500.00, "trade_receivables": 2850.00,
            "inventory": 4000.00, "cash_equivalents": 680.00,
            "trade_payables": 3700.00,
            "ocf": 3200.00, "capex": -2000.00, "fcff": 1200.00,
            "market_cap": 65000.00,
        }
    ),
}

MRF_PROVISIONAL = FinancialStatement(
    entity_id="MRF001", period="FY2026_P", statement_type="standalone",
    source="provisional", as_of_date=date(2026, 12, 31),
    line_items={
        "revenue_operating": 28500.00, "other_income": 380.00,
        "total_income": 28880.00, "raw_material_cost": 17100.00,
        "employee_cost": 2650.00, "other_expenses": 5730.00,
        "ebitda": 2900.00, "depreciation": 1500.00,
        "ebit": 1400.00, "finance_cost": 380.00,
        "pbt": 2520.00, "tax_expense": 630.00, "pat": 1890.00,
        "total_assets": 26000.00, "total_equity": 16160.00,
        "long_term_debt": 2900.00, "short_term_debt": 1600.00,
        "total_debt": 4500.00, "current_liabilities": 6800.00,
    }
)

MRF_FACILITY = FacilityRequest(
    facility_id="FAC-MRF001", entity_id="MRF001",
    case_type=CaseType.NTB, facility_type=FacilityType.WORKING_CAPITAL,
    amount_requested_cr=300.0,
    purpose="Working capital for procurement of natural rubber, carbon black, and operational requirements",
    proposed_limit_cr=300.0,
)

MRF_COLLATERAL = [
    Collateral(
        collateral_id="COL_MRF_001", entity_id="MRF001",
        collateral_type="Plant & Machinery",
        description="Tyre manufacturing plants at Kottayam, Arakonam, Puducherry, and Trichy",
        market_value_cr=4500.00, forced_sale_value_cr=2700.00,
        valuation_date=date(2025, 10, 20), encumbrance_status="hypothecated",
    ),
    Collateral(
        collateral_id="COL_MRF_002", entity_id="MRF001",
        collateral_type="Inventory",
        description="Raw material (natural & synthetic rubber, carbon black) and finished goods",
        market_value_cr=4000.00, forced_sale_value_cr=2400.00,
        valuation_date=date(2026, 1, 15), encumbrance_status="hypothecated",
    ),
    Collateral(
        collateral_id="COL_MRF_003", entity_id="MRF001",
        collateral_type="Trade Receivables",
        description="Receivables from OEM and replacement market dealers",
        market_value_cr=2850.00, forced_sale_value_cr=1710.00,
        valuation_date=date(2026, 1, 15), encumbrance_status="assigned",
    ),
]

MRF_MARKET_SIGNALS = [
    MarketSignal(
        entity_id="MRF001", signal_type="news",
        headline="MRF reports strong Q3 margins on easing rubber prices",
        sentiment="positive", severity=RiskSeverity.LOW, source_name="Mint",
        signal_date=date(2026, 1, 20),
        details="Natural rubber prices declined 8% QoQ, boosting gross margins for tyre manufacturers.",
    ),
    MarketSignal(
        entity_id="MRF001", signal_type="news",
        headline="MRF Cricket sponsorship extension strengthens brand visibility",
        sentiment="positive", severity=RiskSeverity.LOW, source_name="Economic Times",
        signal_date=date(2025, 12, 5),
        details="MRF extends long-standing association with Indian cricket — premium brand recognition remains strong.",
    ),
    MarketSignal(
        entity_id="MRF001", signal_type="regulatory",
        headline="BIS tyre safety rating compliance deadline extended for domestic producers",
        sentiment="positive", severity=RiskSeverity.LOW, source_name="Ministry of Commerce",
        signal_date=date(2025, 9, 10),
        details="Extended timeline relieves compliance cost pressures for FY26.",
    ),
]


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRY: All 18 real companies
# ═══════════════════════════════════════════════════════════════════════════════

REAL_COMPANIES = {
    "TSTL001": {
        "borrower": TSTL_BORROWER, "group": TSTL_GROUP, "directors": TSTL_DIRECTORS,
        "financials": TSTL_FINANCIALS, "provisional": TSTL_PROVISIONAL,
        "facility": TSTL_FACILITY, "collateral": TSTL_COLLATERAL,
        "market_signals": TSTL_MARKET_SIGNALS,
        "existing_exposure": [], "conduct": [], "covenants": [],
        "exchange_filing": None,
    },
    "REIL001": {
        "borrower": REIL_BORROWER, "group": REIL_GROUP, "directors": REIL_DIRECTORS,
        "financials": REIL_FINANCIALS, "provisional": REIL_PROVISIONAL,
        "facility": REIL_FACILITY, "collateral": REIL_COLLATERAL,
        "market_signals": REIL_MARKET_SIGNALS,
        "existing_exposure": [], "conduct": [], "covenants": [],
        "exchange_filing": None,
    },
    "INFY001": {
        "borrower": INFY_BORROWER, "group": INFY_GROUP, "directors": INFY_DIRECTORS,
        "financials": INFY_FINANCIALS, "provisional": INFY_PROVISIONAL,
        "facility": INFY_FACILITY, "collateral": INFY_COLLATERAL,
        "market_signals": INFY_MARKET_SIGNALS,
        "existing_exposure": [], "conduct": [], "covenants": [],
        "exchange_filing": None,
    },
    "ADPT001": {
        "borrower": ADPT_BORROWER, "group": ADPT_GROUP, "directors": ADPT_DIRECTORS,
        "financials": ADPT_FINANCIALS, "provisional": ADPT_PROVISIONAL,
        "facility": ADPT_FACILITY, "collateral": ADPT_COLLATERAL,
        "market_signals": ADPT_MARKET_SIGNALS,
        "existing_exposure": [], "conduct": [], "covenants": [],
        "exchange_filing": None,
    },
    "BJFN001": {
        "borrower": BJFN_BORROWER, "group": BJFN_GROUP, "directors": BJFN_DIRECTORS,
        "financials": BJFN_FINANCIALS, "provisional": BJFN_PROVISIONAL,
        "facility": BJFN_FACILITY, "collateral": BJFN_COLLATERAL,
        "market_signals": BJFN_MARKET_SIGNALS,
        "existing_exposure": [], "conduct": [], "covenants": [],
        "exchange_filing": None,
    },
    "CIPL001": {
        "borrower": CIPL_BORROWER, "group": CIPL_GROUP, "directors": CIPL_DIRECTORS,
        "financials": CIPL_FINANCIALS, "provisional": CIPL_PROVISIONAL,
        "facility": CIPL_FACILITY, "collateral": CIPL_COLLATERAL,
        "market_signals": CIPL_MARKET_SIGNALS,
        "existing_exposure": [], "conduct": [], "covenants": [],
        "exchange_filing": None,
    },
    "DLFR001": {
        "borrower": DLFR_BORROWER, "group": DLFR_GROUP, "directors": DLFR_DIRECTORS,
        "financials": DLFR_FINANCIALS, "provisional": DLFR_PROVISIONAL,
        "facility": DLFR_FACILITY, "collateral": DLFR_COLLATERAL,
        "market_signals": DLFR_MARKET_SIGNALS,
        "existing_exposure": DLFR_EXISTING_EXPOSURE,
        "conduct": DLFR_CONDUCT, "covenants": DLFR_COVENANTS,
        "exchange_filing": DLFR_EXCHANGE_FILING,
        "core_banking": DLFR_CORE_BANKING,
    },
    "JSWL001": {
        "borrower": JSWL_BORROWER, "group": JSWL_GROUP, "directors": JSWL_DIRECTORS,
        "financials": JSWL_FINANCIALS, "provisional": JSWL_PROVISIONAL,
        "facility": JSWL_FACILITY, "collateral": JSWL_COLLATERAL,
        "market_signals": JSWL_MARKET_SIGNALS,
        "existing_exposure": [], "conduct": [], "covenants": [],
        "exchange_filing": None,
    },
    "MRUT001": {
        "borrower": MRUT_BORROWER, "group": MRUT_GROUP, "directors": MRUT_DIRECTORS,
        "financials": MRUT_FINANCIALS, "provisional": MRUT_PROVISIONAL,
        "facility": MRUT_FACILITY, "collateral": MRUT_COLLATERAL,
        "market_signals": MRUT_MARKET_SIGNALS,
        "existing_exposure": [], "conduct": [], "covenants": [],
        "exchange_filing": None,
    },
    "TITN001": {
        "borrower": TITN_BORROWER, "group": TITN_GROUP, "directors": TITN_DIRECTORS,
        "financials": TITN_FINANCIALS, "provisional": TITN_PROVISIONAL,
        "facility": TITN_FACILITY, "collateral": TITN_COLLATERAL,
        "market_signals": TITN_MARKET_SIGNALS,
        "existing_exposure": [], "conduct": [], "covenants": [],
        "exchange_filing": None,
    },
    "NTPC001": {
        "borrower": NTPC_BORROWER, "group": NTPC_GROUP, "directors": NTPC_DIRECTORS,
        "financials": NTPC_FINANCIALS, "provisional": NTPC_PROVISIONAL,
        "facility": NTPC_FACILITY, "collateral": NTPC_COLLATERAL,
        "market_signals": NTPC_MARKET_SIGNALS,
        "existing_exposure": NTPC_EXISTING_EXPOSURE,
        "conduct": NTPC_CONDUCT, "covenants": NTPC_COVENANTS,
        "exchange_filing": None,
        "core_banking": NTPC_CORE_BANKING,
    },
    "YESB001": {
        "borrower": YESB_BORROWER, "group": YESB_GROUP, "directors": YESB_DIRECTORS,
        "financials": YESB_FINANCIALS, "provisional": YESB_PROVISIONAL,
        "facility": YESB_FACILITY, "collateral": YESB_COLLATERAL,
        "market_signals": YESB_MARKET_SIGNALS,
        "existing_exposure": YESB_EXISTING_EXPOSURE,
        "conduct": YESB_CONDUCT, "covenants": YESB_COVENANTS,
        "exchange_filing": YESB_EXCHANGE_FILING,
        "core_banking": YESB_CORE_BANKING,
    },
    "DRRD001": {
        "borrower": DRRD_BORROWER, "group": DRRD_GROUP, "directors": DRRD_DIRECTORS,
        "financials": DRRD_FINANCIALS, "provisional": DRRD_PROVISIONAL,
        "facility": DRRD_FACILITY, "collateral": DRRD_COLLATERAL,
        "market_signals": DRRD_MARKET_SIGNALS,
        "existing_exposure": [], "conduct": [], "covenants": [],
        "exchange_filing": None,
    },
    "IHCL001": {
        "borrower": IHCL_BORROWER, "group": IHCL_GROUP, "directors": IHCL_DIRECTORS,
        "financials": IHCL_FINANCIALS, "provisional": IHCL_PROVISIONAL,
        "facility": IHCL_FACILITY, "collateral": IHCL_COLLATERAL,
        "market_signals": IHCL_MARKET_SIGNALS,
        "existing_exposure": IHCL_EXISTING_EXPOSURE,
        "conduct": IHCL_CONDUCT, "covenants": IHCL_COVENANTS,
        "exchange_filing": None,
        "core_banking": IHCL_CORE_BANKING,
    },
    "APOL001": {
        "borrower": APOL_BORROWER, "group": APOL_GROUP, "directors": APOL_DIRECTORS,
        "financials": APOL_FINANCIALS, "provisional": APOL_PROVISIONAL,
        "facility": APOL_FACILITY, "collateral": APOL_COLLATERAL,
        "market_signals": APOL_MARKET_SIGNALS,
        "existing_exposure": [], "conduct": [], "covenants": [],
        "exchange_filing": None,
    },
    "PNCR001": {
        "borrower": PNCR_BORROWER, "group": PNCR_GROUP, "directors": PNCR_DIRECTORS,
        "financials": PNCR_FINANCIALS, "provisional": PNCR_PROVISIONAL,
        "facility": PNCR_FACILITY, "collateral": PNCR_COLLATERAL,
        "market_signals": PNCR_MARKET_SIGNALS,
        "existing_exposure": [], "conduct": [], "covenants": [],
        "exchange_filing": None,
        "infra_metrics": PNCR_INFRA_METRICS,
    },
    "MFL001": {
        "borrower": MFL_BORROWER, "group": MFL_GROUP, "directors": MFL_DIRECTORS,
        "financials": MFL_FINANCIALS, "provisional": MFL_PROVISIONAL,
        "facility": MFL_FACILITY, "collateral": MFL_COLLATERAL,
        "market_signals": MFL_MARKET_SIGNALS,
        "existing_exposure": [], "conduct": [], "covenants": [],
        "exchange_filing": None,
    },
    "MRF001": {
        "borrower": MRF_BORROWER, "group": MRF_GROUP, "directors": MRF_DIRECTORS,
        "financials": MRF_FINANCIALS, "provisional": MRF_PROVISIONAL,
        "facility": MRF_FACILITY, "collateral": MRF_COLLATERAL,
        "market_signals": MRF_MARKET_SIGNALS,
        "existing_exposure": [], "conduct": [], "covenants": [],
        "exchange_filing": None,
    },
}
