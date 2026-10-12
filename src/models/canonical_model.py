"""
Canonical Lending Data Model
All incoming data normalizes to these structures.
This is the single source of truth for the deterministic pipeline.
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
from datetime import date


# ─── Enums ───────────────────────────────────────────────────────────────────

class CaseType(Enum):
    NTB = "NTB"
    ETB = "ETB"

class BorrowerType(Enum):
    LISTED = "listed"
    UNLISTED = "unlisted"

class FacilityType(Enum):
    WORKING_CAPITAL = "working_capital"
    TERM_LOAN = "term_loan"
    PROJECT_FINANCE = "project_finance"

class Sector(Enum):
    MANUFACTURING = "manufacturing"
    INFRASTRUCTURE = "infrastructure"
    PHARMA = "pharma"
    LOGISTICS = "logistics"
    IT_SERVICES = "it_services"
    REAL_ESTATE = "real_estate"
    NBFC = "nbfc"
    TRADING = "trading"
    HOSPITALITY = "hospitality"
    HEALTHCARE = "healthcare"
    ENERGY = "energy"


# ─── PEP Screening ──────────────────────────────────────────────────────────

@dataclass
class PEPMatch:
    """A single PEP match result for a director/promoter."""
    person_name: str
    din: Optional[str] = None
    match_type: str = ""                # "exact", "partial", "alias"
    pep_category: str = ""              # "politician", "bureaucrat", "judiciary", "regulatory", "military"
    pep_designation: str = ""           # "Member of Parliament", "IAS Officer", etc.
    pep_jurisdiction: str = ""          # "India", "State - Maharashtra", etc.
    risk_level: str = "low"             # "low", "medium", "high", "critical"
    sanctions_list_hit: bool = False
    adverse_media_count: int = 0
    related_pep: bool = False           # True if relative/associate of PEP
    source: str = ""                    # "WorldCheck", "Dow Jones", "internal", "mock"
    remarks: str = ""


@dataclass
class PEPScreeningResult:
    """Aggregate PEP screening result for an entity."""
    entity_id: str
    screening_date: Optional[date] = None
    total_persons_screened: int = 0
    pep_hits: list = field(default_factory=list)   # list of PEPMatch
    sanctions_hits: int = 0
    adverse_media_hits: int = 0
    overall_risk: str = "low"           # "low", "medium", "high", "critical"
    status: str = "clear"               # "clear", "flagged", "escalate"
    remarks: str = ""


# ─── ETB Core Banking ───────────────────────────────────────────────────────

@dataclass
class LoanAccount:
    """Core banking loan account details for ETB."""
    account_number: str
    entity_id: str
    facility_type: str          # "CC", "TL", "BG", "LC", "WCDL"
    sanction_limit_cr: float
    outstanding_cr: float
    disbursement_date: Optional[date] = None
    maturity_date: Optional[date] = None
    interest_rate_pct: float = 0.0
    overdue_amount_cr: float = 0.0
    dpd: int = 0
    asset_classification: str = "Standard"  # "Standard", "SMA-0", "SMA-1", "SMA-2", "NPA"
    last_payment_date: Optional[date] = None


@dataclass
class BCLCPosition:
    """Borrower-wise Credit Limit Check (BCLC) position."""
    entity_id: str
    total_fund_based_cr: float
    total_non_fund_based_cr: float
    total_exposure_cr: float
    group_exposure_cr: float = 0.0
    single_borrower_limit_pct: float = 0.0   # % of bank's net worth
    group_borrower_limit_pct: float = 0.0
    within_single_limit: bool = True
    within_group_limit: bool = True
    as_of_date: Optional[date] = None


@dataclass
class LiabilityPosition:
    """Liability-side position from core banking."""
    entity_id: str
    current_account_balance_cr: float = 0.0
    savings_balance_cr: float = 0.0
    fixed_deposit_cr: float = 0.0
    total_deposits_cr: float = 0.0
    average_balance_6m_cr: float = 0.0
    reciprocal_business_cr: float = 0.0  # business routed to bank
    cross_sell_products: list = field(default_factory=list)  # insurance, MF, etc.


@dataclass
class FeesCommission:
    """Fee and commission income from the borrower."""
    entity_id: str
    period: str
    processing_fees_cr: float = 0.0
    renewal_fees_cr: float = 0.0
    lc_commission_cr: float = 0.0
    bg_commission_cr: float = 0.0
    forex_income_cr: float = 0.0
    other_charges_cr: float = 0.0
    total_income_cr: float = 0.0


@dataclass
class CoreBankingData:
    """Consolidated core banking position for an ETB borrower."""
    entity_id: str
    loan_accounts: list = field(default_factory=list)    # list of LoanAccount
    bclc: Optional[BCLCPosition] = None
    liability: Optional[LiabilityPosition] = None
    fees_commission: list = field(default_factory=list)   # list of FeesCommission (multi-period)
    total_exposure_cr: float = 0.0
    overall_asset_classification: str = "Standard"
    relationship_since: Optional[date] = None
    relationship_years: int = 0
    last_review_date: Optional[date] = None


class RiskSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class ValidationStatus(Enum):
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"

class BenchmarkStatus(Enum):
    BETTER_THAN_PEER = "better_than_peer"
    WITHIN_BAND = "within_band"
    WORSE_THAN_PEER = "worse_than_peer"

class RecommendationType(Enum):
    APPROVE = "approve"
    CONDITIONAL_APPROVE = "conditional_approve"
    REFER = "refer"
    DECLINE = "decline"


# ─── Core Entities ───────────────────────────────────────────────────────────

@dataclass
class Borrower:
    entity_id: str
    company_name: str
    cin: str
    pan: str
    borrower_type: BorrowerType
    sector: Sector
    subsector: str
    date_of_incorporation: date
    registered_state: str
    registered_address: str
    authorized_capital: float
    paid_up_capital: float
    listed_exchange: Optional[str] = None
    isin: Optional[str] = None
    bse_code: Optional[str] = None
    nse_symbol: Optional[str] = None
    credit_rating: Optional[str] = None
    rating_agency: Optional[str] = None
    employee_count: Optional[int] = None
    website: Optional[str] = None


@dataclass
class CorporateNode:
    """A node in the corporate hierarchy tree."""
    entity_id: str
    company_name: str
    relationship: str  # "parent", "subsidiary", "associate", "jv", "self"
    holding_pct: float = 0.0
    cin: str = ""
    pan: str = ""
    sector: str = ""
    revenue_cr: Optional[float] = None
    pat_cr: Optional[float] = None
    net_worth_cr: Optional[float] = None
    total_debt_cr: Optional[float] = None
    credit_rating: Optional[str] = None
    children: list = field(default_factory=list)  # list of CorporateNode


@dataclass
class GroupEntity:
    group_id: str
    group_name: str
    parent_entity_id: str
    entities: list = field(default_factory=list)
    promoter_holding_pct: float = 0.0
    institutional_holding_pct: float = 0.0
    public_holding_pct: float = 0.0
    hierarchy: Optional[list] = None  # list of CorporateNode (tree roots)
    ultimate_parent: Optional[str] = None
    group_revenue_cr: Optional[float] = None
    group_net_worth_cr: Optional[float] = None
    group_total_debt_cr: Optional[float] = None


@dataclass
class DirectorPromoter:
    din: str
    name: str
    designation: str
    entity_id: str
    pan: Optional[str] = None
    date_of_appointment: Optional[date] = None
    other_directorships: list = field(default_factory=list)
    net_worth_cr: Optional[float] = None
    is_promoter: bool = False


@dataclass
class FinancialLineItem:
    """A single line item in a financial statement."""
    canonical_label: str
    value_cr: float
    period: str  # e.g., "FY2024", "FY2023"
    statement_type: str  # "standalone" or "consolidated"
    source: str  # "audited", "provisional", "exchange", "borrower"
    source_priority: int  # 1=highest trust


@dataclass
class FinancialStatement:
    """Complete financial data for one period."""
    entity_id: str
    period: str
    statement_type: str
    source: str
    as_of_date: date
    line_items: dict = field(default_factory=dict)  # canonical_label -> value_cr

    def get(self, label: str, default: float = 0.0) -> float:
        return self.line_items.get(label, default)


@dataclass
class FacilityRequest:
    facility_id: str
    entity_id: str
    case_type: CaseType
    facility_type: FacilityType
    amount_requested_cr: float
    purpose: str
    tenor_months: Optional[int] = None
    collateral_type: Optional[str] = None
    collateral_value_cr: Optional[float] = None
    existing_limit_cr: Optional[float] = None
    proposed_limit_cr: Optional[float] = None


@dataclass
class ExistingExposure:
    facility_id: str
    entity_id: str
    facility_type: str
    sanctioned_limit_cr: float
    outstanding_cr: float
    utilization_pct: float
    overdue_days: int = 0
    classification: str = "Standard"


@dataclass
class Collateral:
    collateral_id: str
    entity_id: str
    collateral_type: str
    description: str
    market_value_cr: float
    forced_sale_value_cr: float
    valuation_date: date
    encumbrance_status: str = "clear"


@dataclass
class MarketSignal:
    entity_id: str
    signal_type: str  # "news", "social", "analyst", "event"
    headline: str
    sentiment: str  # "positive", "neutral", "negative"
    severity: RiskSeverity
    source_name: str
    signal_date: date
    details: str = ""


@dataclass
class ValidationException:
    exception_code: str
    severity: RiskSeverity
    entity_id: str
    description: str
    expected_value: Optional[str] = None
    observed_value: Optional[str] = None
    source_doc_ref: str = ""
    impacted_metric: str = ""
    resolution_status: str = "unresolved"


@dataclass
class BenchmarkResult:
    entity_id: str
    metric: str
    borrower_value: float
    peer_median: float
    peer_p25: float
    peer_p75: float
    status: BenchmarkStatus
    severity: RiskSeverity
    sector: str
    period: str


@dataclass
class ConductRecord:
    """ETB internal banking conduct data."""
    entity_id: str
    period: str
    avg_bank_balance_cr: float
    credit_turnover_cr: float
    debit_turnover_cr: float
    cheque_returns: int
    limit_utilization_pct: float
    overdue_instances: int
    max_overdue_days: int
    dpd_30_count: int = 0
    dpd_60_count: int = 0
    dpd_90_count: int = 0


@dataclass
class CovenantRecord:
    entity_id: str
    covenant_type: str
    required_value: str
    actual_value: str
    compliance_status: str  # "compliant", "breached", "waived"
    period: str
    breach_details: str = ""


@dataclass
class RatioResult:
    """Output of deterministic ratio calculation."""
    entity_id: str
    period: str
    ratio_name: str
    numerator: float
    denominator: float
    value: Optional[float]
    formula: str
    status: str  # "computed", "div_by_zero", "data_missing"


@dataclass
class PolicyDecision:
    entity_id: str
    tier: str  # "tier1_hard_rules", "tier2_scoring", "tier3_recommendation"
    rule_code: str
    rule_description: str
    result: str  # "pass", "fail", "flag"
    details: str = ""


@dataclass
class CAMSection:
    section_id: str
    section_title: str
    section_order: int
    factual_data: dict = field(default_factory=dict)
    narrative: str = ""
    citations: list = field(default_factory=list)


@dataclass
class SourceEvidence:
    evidence_id: str
    source_type: str
    document_name: str
    page_ref: str = ""
    field_ref: str = ""
    extracted_value: str = ""
    confidence: float = 1.0


@dataclass
class AuditEvent:
    event_id: str
    entity_id: str
    event_type: str
    event_detail: str
    timestamp: str
    parser_version: str = "v1.0"
    rule_pack_version: str = "v1.0"
    workflow_version: str = "v1.0"
