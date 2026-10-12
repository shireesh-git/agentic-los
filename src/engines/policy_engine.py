"""
Deterministic Policy & Decision Engine
3-tier decision logic: hard rules → scoring → recommendation.
Uses DMN-style decision tables — no LLM involvement.
"""

from dataclasses import dataclass
from src.core.config_manager import config
from src.models.canonical_model import (
    Borrower, FacilityRequest, ValidationException, BenchmarkResult,
    PolicyDecision, RatioResult, CaseType, BorrowerType, RiskSeverity,
    BenchmarkStatus, RecommendationType, ConductRecord, CovenantRecord,
)


def _policy_rules() -> dict:
    config.reload()
    return config.get_rules() or {}


def _hard_rule_config(rule_key: str) -> dict:
    return (_policy_rules().get("hard_rules") or {}).get(rule_key, {}) or {}


def _scoring_config() -> dict:
    return _policy_rules().get("scoring") or {}


def _recommendation_config() -> dict:
    return _policy_rules().get("recommendation") or {}


def _number(value, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _kyc_result(inventory: dict | None) -> tuple[str, str]:
    """KYC from the document inventory: pass only when KYC documents are on file."""
    if not inventory:
        return NOT_VERIFIED, "No document inventory for this case — KYC documents not verified"
    declared = "demo fixture" in str(inventory.get("source", ""))
    if not inventory.get("has_kyc"):
        return "fail", f"KYC documents not on file ({inventory.get('source', 'document store')})"
    if declared or not inventory.get("kyc_files"):
        return NOT_VERIFIED, "KYC documents declared in the synthetic demo fixture; no documents on file to verify"
    return "pass", "KYC documents on file: " + ", ".join(inventory["kyc_files"])


# ═══════════════════════════════════════════════════════════════════════════════
# TIER 1: HARD RULES — Pass/Fail gates
# ═══════════════════════════════════════════════════════════════════════════════

NOT_VERIFIED = "not_verified"   # hard-rule result when the evidence needed to decide is absent


def tier1_hard_rules(
    borrower: Borrower,
    facility: FacilityRequest,
    exceptions: list[ValidationException],
    bureau_payload: dict = None,
    document_inventory: dict | None = None,
    mca_status: str | None = None,
    demo_evidence: bool = False,
) -> list[PolicyDecision]:
    """Hard rules that must pass before proceeding.

    Each rule is decided on evidence: "pass", "fail", or "not_verified" when the evidence needed to
    decide is absent (a rule is never passed by default). ``document_inventory`` is the ingestion
    agent's inventory of storage/documents/{entity}; ``mca_status`` is the MCA company status from the
    public-record payload; ``demo_evidence`` marks a synthetic demo borrower whose evidence is declared,
    not on file.
    """
    decisions = []
    case_type_value = getattr(facility.case_type, "value", str(facility.case_type or ""))
    bureau = (bureau_payload or {}).get("payload") or {}
    no_bureau = "No bureau report available from submitted information"

    def bureau_rule(code, description, field, failed, pass_details, fail_details):
        """A rule on one bureau field: not_verified when the report or the field is absent."""
        if field not in bureau:
            result, details = NOT_VERIFIED, (no_bureau if not bureau else f"Bureau report does not state '{field}'")
        else:
            bad = failed(bureau[field])
            result, details = ("fail", fail_details(bureau[field])) if bad else ("pass", pass_details(bureau[field]))
        decisions.append(PolicyDecision(entity_id=borrower.entity_id, tier="tier1_hard_rules", rule_code=code,
                                        rule_description=description, result=result, details=details))

    # Rule 1: No Wilful Defaulter
    wilful_cfg = _hard_rule_config("wilful_defaulter")
    if wilful_cfg.get("enabled", True):
        bureau_rule("HR_WILFUL_DEFAULTER",
                    wilful_cfg.get("description", "Borrower must not be flagged as Wilful Defaulter"),
                    "wilful_defaulter", bool, lambda v: "Bureau: not flagged as wilful defaulter",
                    lambda v: "Public records show Wilful Defaulter flag")

    # Rule 2: Company status must be Active
    company_active_cfg = _hard_rule_config("company_active")
    if company_active_cfg.get("enabled", True):
        known = mca_status not in (None, "", "Unknown")
        result = ("pass" if mca_status == "Active" else "fail") if known else NOT_VERIFIED
        decisions.append(PolicyDecision(
            entity_id=borrower.entity_id,
            tier="tier1_hard_rules",
            rule_code="HR_COMPANY_ACTIVE",
            rule_description=company_active_cfg.get("description", "Company status must be Active in MCA records"),
            result=result,
            details=(f"MCA company status: {mca_status}" + (" (synthetic demo fixture)" if demo_evidence else "")
                     if known else "MCA company status not available from submitted information"),
        ))

    # Rule 3: No unresolved CRITICAL exceptions
    critical_unresolved = [e for e in exceptions
                          if e.severity == RiskSeverity.CRITICAL
                          and e.resolution_status == "unresolved"]
    critical_cfg = _hard_rule_config("no_critical_exceptions")
    if critical_cfg.get("enabled", True):
        decisions.append(PolicyDecision(
            entity_id=borrower.entity_id,
            tier="tier1_hard_rules",
            rule_code="HR_NO_CRITICAL_EXCEPTIONS",
            rule_description=critical_cfg.get("description", "No unresolved CRITICAL validation exceptions"),
            result="fail" if critical_unresolved else "pass",
            details=f"{len(critical_unresolved)} critical exceptions unresolved" if critical_unresolved
                    else "No critical exceptions",
        ))

    # Rule 4: KYC completeness (NTB)
    kyc_cfg = _hard_rule_config("kyc_complete")
    kyc_applies = str(kyc_cfg.get("applies_to", "NTB")).upper()
    if kyc_cfg.get("enabled", True) and case_type_value.upper() == kyc_applies:
        result, details = _kyc_result(document_inventory)
        decisions.append(PolicyDecision(
            entity_id=borrower.entity_id,
            tier="tier1_hard_rules",
            rule_code="HR_KYC_COMPLETE",
            rule_description=kyc_cfg.get("description", "KYC package must be complete for NTB"),
            result=result,
            details=details,
        ))

    # Rule 5: Bureau SMA/NPA check
    bureau_cfg = _hard_rule_config("bureau_status")
    if bureau_cfg.get("enabled", True):
        blocked_statuses = tuple(bureau_cfg.get("blocked_statuses") or ("SMA-2", "Substandard", "Doubtful", "Loss"))
        bureau_rule("HR_BUREAU_STATUS",
                    bureau_cfg.get("description", "Public-record stress status must not be SMA-2 or worse"),
                    "dpd_status", lambda v: v in blocked_statuses,
                    lambda v: f"Public-record DPD status: {v}", lambda v: f"Public-record DPD status: {v}")

    # Rule 6: Minimum vintage for NTB
    vintage_cfg = _hard_rule_config("min_vintage")
    vintage_applies = str(vintage_cfg.get("applies_to", "NTB")).upper()
    if vintage_cfg.get("enabled", True) and case_type_value.upper() == vintage_applies:
        from datetime import date
        min_years = _number(vintage_cfg.get("min_years"), 3)
        age_years = (date.today() - borrower.date_of_incorporation).days / 365.25
        decisions.append(PolicyDecision(
            entity_id=borrower.entity_id,
            tier="tier1_hard_rules",
            rule_code="HR_MIN_VINTAGE",
            rule_description=vintage_cfg.get("description", "Company must be at least 3 years old for NTB lending"),
            result="pass" if age_years >= min_years else "fail",
            details=f"Company age: {age_years:.1f} years",
        ))

    # Rule 7: RBI fraud registry check
    bureau_rule("HR_FRAUD_REGISTRY", "Borrower must not be flagged in fraud registry (RBI CFMC)", "fraud_flag", bool,
                lambda v: "Bureau: no fraud flag", lambda v: "Fraud flag detected in bureau")

    # Rule 8: RBI defaulter list check
    bureau_rule("HR_RBI_DEFAULTER", "Borrower must not be on RBI defaulter list", "rbi_defaulter_list", bool,
                lambda v: "Bureau: not on RBI defaulter list", lambda v: "On RBI defaulter list")

    # Rule 9: Suit filed amount check (significant litigation)
    total_exp = bureau.get("total_exposure_cr") or 0

    def suit_pct(amount):
        return (amount / total_exp * 100) if total_exp > 0 else 0

    bureau_rule("HR_SUIT_FILED", "Suit-filed amount must be < 25% of total exposure", "suit_filed_amount_cr",
                lambda v: suit_pct(v or 0) > 25,
                lambda v: f"Suit filed: ₹{(v or 0):.1f} Cr ({suit_pct(v or 0):.1f}% of exposure)",
                lambda v: f"Suit filed: ₹{(v or 0):.1f} Cr ({suit_pct(v or 0):.1f}% of exposure)")

    return decisions


# ═══════════════════════════════════════════════════════════════════════════════
# TIER 2: SCORING — Risk score computation
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class RiskScore:
    financial_score: float  # 0-100
    conduct_score: float    # 0-100
    governance_score: float # 0-100
    market_score: float     # 0-100
    composite_score: float  # 0-100
    risk_grade: str         # A/B/C/D/E


def _financial_score(
    ratios: list[RatioResult],
    benchmarks: list[BenchmarkResult],
    infra_metrics: dict | None = None,
) -> float:
    """Score based on financial ratios and benchmark position. 0-100.
    Follows CRISIL RAM (Rating Assessment Methodology) scoring logic:
    - Base score 65 (neutral)
    - Benchmark position adjustments
    - Key ratio-specific adjustments aligned with RBI/rating agency thresholds
    - Sector-specific operational KPI adjustments (infra/road)
    """
    scoring_cfg = _scoring_config()
    financial_penalties = scoring_cfg.get("financial_penalties") or {}
    score = _number(scoring_cfg.get("base_financial_score"), 65.0)

    # Benchmark position adjustments
    benchmark_penalty_high = _number(scoring_cfg.get("benchmark_penalty_high"), 6)
    benchmark_penalty_medium = _number(scoring_cfg.get("benchmark_penalty_medium"), 3)
    benchmark_bonus_per_better = _number(scoring_cfg.get("benchmark_bonus_per_better"), 2)
    for bm in benchmarks:
        if bm.status == BenchmarkStatus.WORSE_THAN_PEER:
            if bm.severity == RiskSeverity.HIGH:
                score -= benchmark_penalty_high
            elif bm.severity == RiskSeverity.MEDIUM:
                score -= benchmark_penalty_medium
        elif bm.status == BenchmarkStatus.BETTER_THAN_PEER:
            score += benchmark_bonus_per_better

    # Build ratio lookup
    rmap = {r.ratio_name: r.value for r in ratios if r.value is not None}

    # ── LEVERAGE RATIOS (max penalty -25) ────────────────────
    de = rmap.get("debt_to_equity")
    if de is not None:
        de_critical = financial_penalties.get("de_critical") or {}
        de_warning = financial_penalties.get("de_warning") or {}
        if de > _number(de_critical.get("threshold"), 4.0):
            score -= _number(de_critical.get("penalty"), 12)
        elif de > _number(de_warning.get("threshold"), 2.0):
            score -= _number(de_warning.get("penalty"), 4)
        elif de < 0.5:  score += 5
        elif de < 1.0:  score += 3

    dte = rmap.get("debt_to_ebitda")
    if dte is not None:
        if dte > 6.0:   score -= 10
        elif dte > 4.0: score -= 5
        elif dte < 2.0: score += 5

    # ── COVERAGE RATIOS (max penalty -25) ────────────────────
    icr = rmap.get("interest_coverage_ratio")
    if icr is not None:
        icr_critical = financial_penalties.get("icr_critical") or {}
        icr_warning = financial_penalties.get("icr_warning") or {}
        icr_bonus = financial_penalties.get("icr_bonus") or {}
        if icr < _number(icr_critical.get("threshold"), 1.5):
            score -= _number(icr_critical.get("penalty"), 10)
        elif icr < _number(icr_warning.get("threshold"), 2.0):
            score -= _number(icr_warning.get("penalty"), 5)
        elif icr > _number(icr_bonus.get("threshold"), 4.0):
            score += _number(icr_bonus.get("bonus"), 5)

    d = rmap.get("dscr")
    if d is not None:
        dscr_critical = financial_penalties.get("dscr_critical") or {}
        dscr_warning = financial_penalties.get("dscr_warning") or {}
        dscr_bonus = financial_penalties.get("dscr_bonus") or {}
        if d < _number(dscr_critical.get("threshold"), 1.0):
            score -= _number(dscr_critical.get("penalty"), 15)
        elif d < _number(dscr_warning.get("threshold"), 1.2):
            score -= _number(dscr_warning.get("penalty"), 5)
        elif d > _number(dscr_bonus.get("threshold"), 1.5):
            score += _number(dscr_bonus.get("bonus"), 5)

    fcc = rmap.get("fixed_charge_coverage")
    if fcc is not None:
        if fcc < 1.0:    score -= 8
        elif fcc < 1.2:  score -= 4
        elif fcc > 2.0:  score += 3

    # ── PROFITABILITY (max penalty -15) ──────────────────────
    npm = rmap.get("net_profit_margin")
    if npm is not None:
        if npm < 0:       score -= 12
        elif npm < 0.02:  score -= 6
        elif npm > 0.12:  score += 4

    em = rmap.get("ebitda_margin")
    if em is not None:
        if em < 0.05:    score -= 8
        elif em < 0.10:  score -= 4
        elif em > 0.25:  score += 5

    r_val = rmap.get("roce")
    if r_val is not None:
        if r_val > 0.18:  score += 4
        elif r_val < 0.08: score -= 4

    # ── LIQUIDITY (max penalty -15) ──────────────────────────
    cr = rmap.get("current_ratio")
    if cr is not None:
        cr_critical = financial_penalties.get("cr_critical") or {}
        cr_warning = financial_penalties.get("cr_warning") or {}
        if cr < _number(cr_critical.get("threshold"), 1.0):
            score -= _number(cr_critical.get("penalty"), 8)
        elif cr < _number(cr_warning.get("threshold"), 1.1):
            score -= _number(cr_warning.get("penalty"), 4)
        elif cr > 1.5:   score += 3

    # ── CASH FLOW (max penalty -10) ──────────────────────────
    ocf_debt = rmap.get("ocf_to_debt")
    if ocf_debt is not None:
        if ocf_debt < 0.10:  score -= 8
        elif ocf_debt > 0.30: score += 4

    # ── DISTRESS SIGNAL ──────────────────────────────────────
    z = rmap.get("altman_z_score")
    if z is not None:
        if z < 1.81:      score -= 10  # Distress zone
        elif z < 2.99:    score -= 3   # Grey zone
        elif z > 3.5:     score += 5   # Safe zone

    # ── INFRASTRUCTURE / ROAD SECTOR OPERATIONAL KPIs ────────
    if infra_metrics:
        score += _infra_sector_adjustment(infra_metrics)

    return max(0, min(100, round(score, 1)))


def _infra_sector_adjustment(im: dict) -> float:
    """Sector-specific scoring for road/highway/infrastructure companies.

    Evaluates operational KPIs that standard financial ratios miss:
    - Order book depth (revenue visibility)
    - Execution velocity (km/year trend)
    - Construction cost efficiency
    - BOT/HAM annuity income stability
    - Land acquisition cost reasonableness

    Returns adjustment value (can be positive or negative, capped ±15).
    """
    adj = 0.0

    # 1. Order Book Depth — Book-to-Bill ≥ 3x is strong revenue visibility
    ob = im.get("order_book", {})
    btb = ob.get("book_to_bill_ratio", 0)
    if btb >= 4.0:
        adj += 5   # Exceptional pipeline
    elif btb >= 3.0:
        adj += 3   # Strong pipeline
    elif btb >= 2.0:
        adj += 1   # Adequate
    elif btb > 0 and btb < 1.5:
        adj -= 4   # Weak pipeline — revenue risk

    # 2. Execution Velocity — improving trend is positive
    em = im.get("execution_metrics", {})
    km_fy25 = em.get("km_executed_fy25", 0)
    km_fy24 = em.get("km_executed_fy24", 0)
    km_fy23 = em.get("km_executed_fy23", 0)
    if km_fy25 > 0 and km_fy24 > 0 and km_fy23 > 0:
        # YoY growth in execution
        growth_latest = (km_fy25 - km_fy24) / km_fy24 if km_fy24 else 0
        growth_prior = (km_fy24 - km_fy23) / km_fy23 if km_fy23 else 0
        if growth_latest > 0.10 and growth_prior > 0.05:
            adj += 3   # Consistently accelerating execution
        elif growth_latest > 0.05:
            adj += 1   # Moderate growth
        elif growth_latest < -0.10:
            adj -= 3   # Execution slowdown — red flag

    # 3. Construction Cost per Km — benchmark vs NHAI norms (~₹15-20 Cr/km for 4-lane)
    cost_per_km = em.get("avg_construction_cost_per_km_cr", 0)
    if cost_per_km > 0:
        if cost_per_km <= 16:
            adj += 2   # Cost-efficient execution
        elif cost_per_km <= 20:
            adj += 0   # Within norms
        elif cost_per_km > 25:
            adj -= 3   # Above norms — margin risk

    # 4. Land Acquisition Cost per Sq Km — benchmark ₹5-12 Cr/sq km typical
    lac = em.get("avg_land_acquisition_cost_per_sq_km_cr", 0)
    if lac > 0:
        if lac > 15:
            adj -= 2   # High land cost — project viability risk
        elif lac <= 8:
            adj += 1   # Favorable land acquisition

    # 5. BOT/HAM Annuity Portfolio — stable toll/annuity income de-risks EPC cyclicality
    bh = im.get("bot_ham_portfolio", {})
    toll_rev = bh.get("annual_toll_revenue_cr", 0)
    residual = bh.get("avg_residual_concession_years", 0)
    if toll_rev > 0 and residual > 0:
        if toll_rev > 1500 and residual > 12:
            adj += 4   # Strong annuity base with long residual
        elif toll_rev > 500 and residual > 8:
            adj += 2   # Moderate annuity income
        elif residual < 5:
            adj -= 1   # Short residual — nearing concession end

    # 6. Equipment Utilization — >80% is healthy
    util = em.get("equipment_utilization_pct", 0)
    if util > 0:
        if util >= 85:
            adj += 1
        elif util < 65:
            adj -= 2   # Under-utilization — capacity/demand concern

    return max(-15, min(15, adj))


def _conduct_score(conduct: list[ConductRecord], covenants: list[CovenantRecord]) -> float:
    """Score based on ETB conduct. 0-100."""
    scoring_cfg = _scoring_config()
    conduct_cfg = scoring_cfg.get("conduct_thresholds") or {}
    if not conduct:
        return _number(scoring_cfg.get("base_conduct_score"), 70.0)  # Neutral for NTB

    score = _number(scoring_cfg.get("base_conduct_score"), 75.0)

    total_returns = sum(c.cheque_returns for c in conduct)
    if total_returns > _number(conduct_cfg.get("cheque_returns_high"), 20):
        score -= 15
    elif total_returns > _number(conduct_cfg.get("cheque_returns_medium"), 10):
        score -= 8

    max_dpd = max(c.max_overdue_days for c in conduct)
    if max_dpd > _number(conduct_cfg.get("dpd_critical"), 60):
        score -= 20
    elif max_dpd > _number(conduct_cfg.get("dpd_high"), 30):
        score -= 12
    elif max_dpd > _number(conduct_cfg.get("dpd_medium"), 15):
        score -= 5

    avg_util = sum(c.limit_utilization_pct for c in conduct) / len(conduct)
    if avg_util > _number(conduct_cfg.get("utilization_critical"), 95):
        score -= 10
    elif avg_util > _number(conduct_cfg.get("utilization_high"), 90):
        score -= 5

    if covenants:
        breaches = sum(1 for c in covenants if c.compliance_status == "breached")
        score -= breaches * _number(conduct_cfg.get("covenant_breach_penalty"), 8)

    return max(0, min(100, round(score, 1)))


def _governance_score(borrower: Borrower, directors: list, group_entities: int) -> float:
    """Score governance quality. 0-100.
    Follows SEBI/RBI corporate governance assessment framework:
    - Board composition, independence
    - Rating quality (external validation of governance)
    - Group complexity and contagion risk
    - Promoter profile indicators
    """
    score = _number(_scoring_config().get("base_governance_score"), 65.0)

    # Rating quality assessment (strongest signal of governance)
    if borrower.credit_rating:
        rating_str = borrower.credit_rating.upper()
        if "AAA" in rating_str:
            score += 15
        elif "AA+" in rating_str or "AA " in rating_str:
            score += 12
        elif "A+" in rating_str:
            score += 8
        elif "A-" in rating_str or rating_str.endswith(" A"):
            score += 5
        elif "A " in rating_str or rating_str.endswith("A"):
            score += 5
        elif "BBB+" in rating_str:
            score += 2
        elif "BBB" in rating_str:
            score += 0
        elif "BBB-" in rating_str:
            score -= 3
        elif "BB" in rating_str:
            score -= 8
        elif "B " in rating_str or rating_str.endswith("B"):
            score -= 15
        # Outlook adjustments
        if "WATCH NEGATIVE" in rating_str or "WATCH NEG" in rating_str:
            score -= 10
        elif "NEGATIVE" in rating_str:
            score -= 5
        elif "POSITIVE" in rating_str:
            score += 3

    # Board composition
    if directors:
        independent = sum(1 for d in directors if not d.is_promoter)
        total = len(directors)
        pct_independent = (independent / total * 100) if total > 0 else 0
        if pct_independent >= 50:   # SEBI requirement for listed
            score += 5
        elif pct_independent >= 33:
            score += 2
        elif independent == 0:
            score -= 10

        # Promoter concentration
        promoters = [d for d in directors if d.is_promoter]
        if len(promoters) == 1 and total <= 2:
            score -= 5  # Key person risk

    # Group complexity and contagion risk
    if group_entities > 8:
        score -= 10
    elif group_entities > 5:
        score -= 6
    elif group_entities > 3:
        score -= 3
    elif group_entities <= 1:
        score += 2  # Simple structure

    # Listed vs Unlisted (disclosure quality)
    if borrower.borrower_type == BorrowerType.LISTED:
        score += 5  # Better disclosure, regulatory oversight

    return max(0, min(100, round(score, 1)))


def _market_score(market_signals: list) -> float:
    """Score based on market/news/social signals. 0-100."""
    score = _number(_scoring_config().get("base_market_score"), 70.0)

    for s in market_signals:
        if s.sentiment == "negative":
            if s.severity == RiskSeverity.CRITICAL:
                score -= 18
            elif s.severity == RiskSeverity.HIGH:
                score -= 10
            elif s.severity == RiskSeverity.MEDIUM:
                score -= 5
        elif s.sentiment == "positive":
            score += 3

    return max(0, min(100, round(score, 1)))


def tier2_scoring(
    borrower: Borrower,
    ratios: list[RatioResult],
    benchmarks: list[BenchmarkResult],
    conduct: list[ConductRecord],
    covenants: list[CovenantRecord],
    directors: list,
    group_entities: int,
    market_signals: list,
    infra_metrics: dict | None = None,
) -> RiskScore:
    """Compute composite risk score."""
    config.reload()
    fin = _financial_score(ratios, benchmarks, infra_metrics=infra_metrics)
    cond = _conduct_score(conduct, covenants)
    gov = _governance_score(borrower, directors, group_entities)
    mkt = _market_score(market_signals)

    # Weighted composite
    weights = config.get_scoring_weights()
    composite = round(
        fin * _number(weights.get("financial"), 0.40)
        + cond * _number(weights.get("conduct"), 0.25)
        + gov * _number(weights.get("governance"), 0.20)
        + mkt * _number(weights.get("market"), 0.15),
        1,
    )

    # Grade
    grade_thresholds = config.get_grade_thresholds()
    if composite >= _number(grade_thresholds.get("A"), 80):
        grade = "A"
    elif composite >= _number(grade_thresholds.get("B"), 65):
        grade = "B"
    elif composite >= _number(grade_thresholds.get("C"), 50):
        grade = "C"
    elif composite >= _number(grade_thresholds.get("D"), 35):
        grade = "D"
    else:
        grade = "E"

    return RiskScore(
        financial_score=fin,
        conduct_score=cond,
        governance_score=gov,
        market_score=mkt,
        composite_score=composite,
        risk_grade=grade,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TIER 3: RECOMMENDATION ASSEMBLY
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class CreditRecommendation:
    recommendation: RecommendationType
    risk_grade: str
    composite_score: float
    conditions: list  # list of str
    covenants_proposed: list  # list of str
    exception_notes: list  # list of str
    collateral_requirement: str
    monitoring_conditions: list  # list of str
    rationale: str


def tier3_recommendation(
    tier1_decisions: list[PolicyDecision],
    risk_score: RiskScore,
    exceptions: list[ValidationException],
    facility: FacilityRequest,
    collateral_coverage: float,
    infra_metrics: dict | None = None,
) -> CreditRecommendation:
    """Assemble final recommendation from tier1 + tier2 outputs."""
    recommendation_cfg = _recommendation_config()

    # Check hard rule failures; a rule that could not be verified never allows an approval
    hard_fails = [d for d in tier1_decisions if d.result == "fail"]
    unverified = [d for d in tier1_decisions if d.result == NOT_VERIFIED]
    critical_exceptions = [e for e in exceptions if e.severity == RiskSeverity.CRITICAL]
    high_exceptions = [e for e in exceptions if e.severity == RiskSeverity.HIGH]

    conditions = []
    covenants_proposed = []
    exception_notes = []
    monitoring = []

    # Determine recommendation
    if hard_fails:
        recommendation = RecommendationType.DECLINE
        rationale = (f"Hard rule failures detected: "
                     f"{', '.join(d.rule_code for d in hard_fails)}. "
                     f"Case cannot proceed without resolution.")
    elif risk_score.risk_grade in ("D", "E"):
        recommendation = RecommendationType.DECLINE
        rationale = (f"Risk grade {risk_score.risk_grade} (composite {risk_score.composite_score}) "
                     f"is below minimum threshold for lending.")
    elif risk_score.risk_grade == "C" or len(high_exceptions) >= 3:
        recommendation = RecommendationType.REFER
        rationale = (f"Risk grade {risk_score.risk_grade} (composite {risk_score.composite_score}). "
                     f"{len(high_exceptions)} high-severity exceptions require committee review.")
        conditions.append("Requires Credit Committee approval")
        conditions.append("All HIGH/CRITICAL exceptions must be resolved before disbursement")
    elif risk_score.risk_grade == "B" or len(high_exceptions) >= 1:
        recommendation = RecommendationType.CONDITIONAL_APPROVE
        rationale = (f"Risk grade {risk_score.risk_grade} (composite {risk_score.composite_score}). "
                     f"Acceptable with conditions.")
        if high_exceptions:
            conditions.append(f"Resolve {len(high_exceptions)} HIGH exception(s) before disbursement")
    else:
        recommendation = RecommendationType.APPROVE
        rationale = (f"Risk grade {risk_score.risk_grade} (composite {risk_score.composite_score}). "
                     f"Strong credit profile with acceptable risk parameters.")

    if unverified:
        if recommendation in (RecommendationType.APPROVE, RecommendationType.CONDITIONAL_APPROVE):
            recommendation = RecommendationType.REFER
            rationale += (f" Referred: hard rule(s) not verified ({', '.join(d.rule_code for d in unverified)}); "
                          f"evidence is required before approval.")
        conditions.append("Evidence to be obtained and verified before sanction: "
                          + "; ".join(d.rule_description for d in unverified))

    # Standard covenants
    covenants_proposed.extend(recommendation_cfg.get("standard_covenants") or [
        "Minimum Current Ratio >= 1.25x",
        "Maximum Debt/Equity <= 2.5x",
        "Minimum DSCR >= 1.20x",
        "Maximum Cheque Returns <= 5 per quarter",
    ])

    if risk_score.risk_grade in ("B", "C"):
        covenants_proposed.extend(recommendation_cfg.get("enhanced_covenants") or [
            "Quarterly financial submission within 45 days",
            "No dividend payment without bank NOC",
        ])
        monitoring.extend(recommendation_cfg.get("monitoring_standard") or [
            "Quarterly review of financial covenants",
            "Monthly stock/receivable statements",
        ])

    if risk_score.market_score < 50:
        monitoring.extend(recommendation_cfg.get("monitoring_enhanced") or [
            "Enhanced media/news monitoring — weekly",
        ])

    # Infrastructure / Road sector-specific covenants
    if infra_metrics:
        ob = infra_metrics.get("order_book", {})
        em = infra_metrics.get("execution_metrics", {})
        bh = infra_metrics.get("bot_ham_portfolio", {})
        # Order book covenant — maintain minimum pipeline
        if ob.get("book_to_bill_ratio", 0) > 0:
            covenants_proposed.append("Minimum Book-to-Bill Ratio >= 2.5x (order book / annual revenue)")
        # Execution monitoring
        if em.get("km_executed_fy25", 0) > 0:
            covenants_proposed.append("Quarterly project execution progress report with km completed vs target")
        # Cost overrun covenant
        if em.get("avg_construction_cost_per_km_cr", 0) > 0:
            covenants_proposed.append("Construction cost per km to remain within ±15% of bid estimates")
        # Land acquisition cost monitoring
        if em.get("avg_land_acquisition_cost_per_sq_km_cr", 0) > 0:
            monitoring.append("Land acquisition cost variance monitoring — quarterly")
        # BOT/HAM toll escrow
        if bh.get("annual_toll_revenue_cr", 0) > 500:
            covenants_proposed.append("Toll revenue escrow account for debt servicing on BOT/HAM assets")
            monitoring.append("Monthly toll collection report for concession assets")

    # Collateral requirement
    if collateral_coverage >= 1.5:
        collateral_req = f"Adequate — coverage ratio {collateral_coverage:.2f}x"
    elif collateral_coverage >= 1.0:
        collateral_req = f"Marginal — coverage ratio {collateral_coverage:.2f}x. Consider additional security."
        conditions.append("Explore additional collateral to improve coverage to 1.5x")
    else:
        collateral_req = f"Insufficient — coverage ratio {collateral_coverage:.2f}x"
        conditions.append("MANDATORY: Additional collateral required before disbursement")

    # Exception notes
    for e in exceptions:
        if e.severity in (RiskSeverity.CRITICAL, RiskSeverity.HIGH):
            exception_notes.append(f"[{e.severity.value.upper()}] {e.exception_code}: {e.description}")

    return CreditRecommendation(
        recommendation=recommendation,
        risk_grade=risk_score.risk_grade,
        composite_score=risk_score.composite_score,
        conditions=conditions,
        covenants_proposed=covenants_proposed,
        exception_notes=exception_notes,
        collateral_requirement=collateral_req,
        monitoring_conditions=monitoring,
        rationale=rationale,
    )
