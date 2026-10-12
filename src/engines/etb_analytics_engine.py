"""
ETB Analytics Engine
=====================
Behavioral analytics for Existing-To-Bank (ETB) customers.
Analyses account conduct, repayment patterns, covenant compliance,
and facility utilization from internal bank data (CSVs).

Returns structured scoring and red-flag identification for CAM integration.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConductScore:
    """Monthly account conduct analysis."""
    avg_utilization_pct: float = 0.0
    peak_utilization_pct: float = 0.0
    total_cheque_returns: int = 0
    months_with_returns: int = 0
    avg_credit_turnover: float = 0.0
    avg_debit_turnover: float = 0.0
    turnover_trend: str = "stable"        # improving / stable / deteriorating
    utilization_trend: str = "stable"
    score: float = 0.0                    # 0-100
    flags: list[str] = field(default_factory=list)


@dataclass
class RepaymentScore:
    """Repayment behavior analysis."""
    total_installments: int = 0
    on_time_count: int = 0
    delayed_count: int = 0
    max_dpd: int = 0
    avg_dpd: float = 0.0
    shortfall_instances: int = 0
    recovery_trend: str = "stable"
    score: float = 0.0
    flags: list[str] = field(default_factory=list)


@dataclass
class CovenantScore:
    """Covenant compliance analysis."""
    total_covenants_tested: int = 0
    compliance_count: int = 0
    breach_count: int = 0
    breach_rate_pct: float = 0.0
    consecutive_breaches: int = 0
    covenants_at_risk: list[str] = field(default_factory=list)
    score: float = 0.0
    flags: list[str] = field(default_factory=list)


@dataclass
class UtilizationScore:
    """Facility utilization analysis."""
    facilities: dict[str, dict] = field(default_factory=dict)
    avg_utilization_pct: float = 0.0
    over_limit_instances: int = 0
    drawing_power_breaches: int = 0
    score: float = 0.0
    flags: list[str] = field(default_factory=list)


@dataclass
class ETBAnalysis:
    """Complete ETB behavioral analysis."""
    entity_id: str = ""
    conduct: ConductScore = field(default_factory=ConductScore)
    repayment: RepaymentScore = field(default_factory=RepaymentScore)
    covenant: CovenantScore = field(default_factory=CovenantScore)
    utilization: UtilizationScore = field(default_factory=UtilizationScore)
    composite_score: float = 0.0
    risk_grade: str = "N/A"
    summary: str = ""
    all_flags: list[str] = field(default_factory=list)


# ─── Weights ─────────────────────────────────────────────────────────────────
CONDUCT_WEIGHT = 0.30
REPAYMENT_WEIGHT = 0.35
COVENANT_WEIGHT = 0.20
UTILIZATION_WEIGHT = 0.15


# ═══════════════════════════════════════════════════════════════════════════════
#  Analysis Functions
# ═══════════════════════════════════════════════════════════════════════════════

def analyze_conduct(rows: list[dict]) -> ConductScore:
    """Analyze account conduct data."""
    cs = ConductScore()
    if not rows:
        return cs

    utilizations = []
    credit_turnovers = []
    debit_turnovers = []
    cheque_return_months = 0

    for row in rows:
        util_pct = _f(row.get("utilization_pct", 0)) or (_f(row.get("utilized_cr", 0)) / max(_f(row.get("limit_cr", 1)), 0.01) * 100)
        utilizations.append(util_pct)
        credit_turnovers.append(_f(row.get("credit_turnover_cr", 0)))
        debit_turnovers.append(_f(row.get("debit_turnover_cr", 0)))
        cr = int(_f(row.get("cheque_returns", 0)))
        cs.total_cheque_returns += cr
        if cr > 0:
            cheque_return_months += 1

    n = len(rows)
    cs.avg_utilization_pct = sum(utilizations) / n if n else 0
    cs.peak_utilization_pct = max(utilizations) if utilizations else 0
    cs.months_with_returns = cheque_return_months
    cs.avg_credit_turnover = sum(credit_turnovers) / n if n else 0
    cs.avg_debit_turnover = sum(debit_turnovers) / n if n else 0

    # Trends (compare first half vs second half)
    mid = n // 2
    if mid > 0:
        first_half_util = sum(utilizations[:mid]) / mid
        second_half_util = sum(utilizations[mid:]) / (n - mid)
        if second_half_util > first_half_util * 1.05:
            cs.utilization_trend = "deteriorating"
        elif second_half_util < first_half_util * 0.95:
            cs.utilization_trend = "improving"

        first_half_cr = sum(credit_turnovers[:mid]) / mid
        second_half_cr = sum(credit_turnovers[mid:]) / (n - mid)
        if second_half_cr > first_half_cr * 1.05:
            cs.turnover_trend = "improving"
        elif second_half_cr < first_half_cr * 0.95:
            cs.turnover_trend = "deteriorating"

    # Scoring (100 = perfect conduct)
    score = 100.0
    # Penalize high utilization
    if cs.avg_utilization_pct > 90:
        score -= 25
    elif cs.avg_utilization_pct > 80:
        score -= 15
    elif cs.avg_utilization_pct > 70:
        score -= 8

    # Penalize cheque returns
    if cs.total_cheque_returns > 6:
        score -= 20
    elif cs.total_cheque_returns > 3:
        score -= 12
    elif cs.total_cheque_returns > 0:
        score -= 5

    # Penalize deteriorating trends
    if cs.utilization_trend == "deteriorating":
        score -= 8
    if cs.turnover_trend == "deteriorating":
        score -= 8

    cs.score = max(0, min(100, score))

    # Flags
    if cs.peak_utilization_pct > 95:
        cs.flags.append(f"Peak utilization hit {cs.peak_utilization_pct:.0f}% — near limit breach")
    if cs.total_cheque_returns > 5:
        cs.flags.append(f"{cs.total_cheque_returns} cheque returns in {n} months — cash flow stress")
    if cs.utilization_trend == "deteriorating":
        cs.flags.append("CC utilization trend is deteriorating")
    if cs.turnover_trend == "deteriorating":
        cs.flags.append("Credit turnover declining — revenue stress signal")

    return cs


def analyze_repayment(rows: list[dict]) -> RepaymentScore:
    """Analyze repayment history."""
    rs = RepaymentScore()
    if not rows:
        return rs

    rs.total_installments = len(rows)
    dpds = []
    consecutive_delay = 0
    max_consecutive = 0

    for row in rows:
        status = str(row.get("status", "")).strip()
        dpd = int(_f(row.get("dpd", 0)))
        dpds.append(dpd)

        if status == "OnTime":
            rs.on_time_count += 1
            max_consecutive = max(max_consecutive, consecutive_delay)
            consecutive_delay = 0
        else:
            rs.delayed_count += 1
            consecutive_delay += 1

        paid = _f(row.get("paid_cr", 0))
        due = _f(row.get("installment_due_cr", 0))
        if due > 0 and paid < due:
            rs.shortfall_instances += 1

    max_consecutive = max(max_consecutive, consecutive_delay)
    rs.max_dpd = max(dpds) if dpds else 0
    rs.avg_dpd = sum(dpds) / len(dpds) if dpds else 0

    # Recovery trend
    mid = len(dpds) // 2
    if mid > 0:
        first_avg = sum(dpds[:mid]) / mid
        second_avg = sum(dpds[mid:]) / (len(dpds) - mid)
        if second_avg < first_avg * 0.7:
            rs.recovery_trend = "improving"
        elif second_avg > first_avg * 1.3:
            rs.recovery_trend = "deteriorating"

    # Scoring
    score = 100.0
    on_time_pct = rs.on_time_count / rs.total_installments * 100 if rs.total_installments else 100
    if on_time_pct < 50:
        score -= 40
    elif on_time_pct < 70:
        score -= 25
    elif on_time_pct < 85:
        score -= 12
    elif on_time_pct < 95:
        score -= 5

    if rs.max_dpd >= 90:
        score -= 30
    elif rs.max_dpd >= 60:
        score -= 20
    elif rs.max_dpd >= 30:
        score -= 10

    if max_consecutive >= 3:
        score -= 15
    elif max_consecutive >= 2:
        score -= 8

    if rs.shortfall_instances > 2:
        score -= 10

    rs.score = max(0, min(100, score))

    # Flags
    if rs.max_dpd >= 30:
        rs.flags.append(f"Max DPD of {rs.max_dpd} days — SMA classification risk")
    if max_consecutive >= 3:
        rs.flags.append(f"{max_consecutive} consecutive delayed payments — structural issue")
    if rs.shortfall_instances > 0:
        rs.flags.append(f"{rs.shortfall_instances} instances of partial payment")
    if rs.recovery_trend == "deteriorating":
        rs.flags.append("Repayment behavior deteriorating over time")
    if on_time_pct < 75:
        rs.flags.append(f"Only {on_time_pct:.0f}% on-time payments — poor discipline")

    return rs


def analyze_covenants(rows: list[dict]) -> CovenantScore:
    """Analyze covenant compliance."""
    cvs = CovenantScore()
    if not rows:
        return cvs

    cvs.total_covenants_tested = len(rows)
    covenant_breach_runs = {}

    for row in rows:
        status = str(row.get("status", "")).strip()
        covenant = str(row.get("covenant", ""))
        period = str(row.get("period", ""))

        if status.lower() == "compliant":
            cvs.compliance_count += 1
            covenant_breach_runs[covenant] = 0
        else:
            cvs.breach_count += 1
            covenant_breach_runs.setdefault(covenant, 0)
            covenant_breach_runs[covenant] += 1

    cvs.breach_rate_pct = cvs.breach_count / cvs.total_covenants_tested * 100 if cvs.total_covenants_tested else 0
    cvs.consecutive_breaches = max(covenant_breach_runs.values()) if covenant_breach_runs else 0

    # Identify at-risk covenants
    for covenant, run in covenant_breach_runs.items():
        if run >= 2:
            cvs.covenants_at_risk.append(covenant)

    # Scoring
    score = 100.0
    if cvs.breach_rate_pct > 50:
        score -= 35
    elif cvs.breach_rate_pct > 30:
        score -= 20
    elif cvs.breach_rate_pct > 15:
        score -= 10

    if cvs.consecutive_breaches >= 3:
        score -= 20
    elif cvs.consecutive_breaches >= 2:
        score -= 10

    cvs.score = max(0, min(100, score))

    # Flags
    if cvs.breach_rate_pct > 40:
        cvs.flags.append(f"Covenant breach rate at {cvs.breach_rate_pct:.0f}% — structural concerns")
    for cov in cvs.covenants_at_risk:
        cvs.flags.append(f"Repeated breaches in: {cov}")
    if cvs.consecutive_breaches >= 3:
        cvs.flags.append("3+ consecutive covenant breaches — potential recall trigger")

    return cvs


def analyze_utilization(rows: list[dict]) -> UtilizationScore:
    """Analyze facility utilization patterns."""
    us = UtilizationScore()
    if not rows:
        return us

    by_facility: dict[str, list] = {}
    for row in rows:
        fac = str(row.get("facility", "unknown"))
        by_facility.setdefault(fac, []).append(row)

    all_utils = []
    for fac, fac_rows in by_facility.items():
        utils = [_f(r.get("utilization_pct", 0)) or (_f(r.get("utilized_cr", 0)) / max(_f(r.get("limit_cr", 1)), 0.01) * 100 ) for r in fac_rows]
        avg = sum(utils) / len(utils) if utils else 0
        peak = max(utils) if utils else 0
        all_utils.extend(utils)

        dp_breaches = 0
        for r in fac_rows:
            utilized = _f(r.get("utilized_cr", 0))
            dp = _f(r.get("drawing_power_cr", 999999))
            if utilized > dp:
                dp_breaches += 1
                us.drawing_power_breaches += 1

            limit = _f(r.get("limit_cr", 0))
            if limit > 0 and utilized > limit:
                us.over_limit_instances += 1

        us.facilities[fac] = {
            "avg_utilization_pct": round(avg, 1),
            "peak_utilization_pct": round(peak, 1),
            "dp_breaches": dp_breaches,
            "data_points": len(fac_rows),
        }

    us.avg_utilization_pct = sum(all_utils) / len(all_utils) if all_utils else 0

    # Scoring
    score = 100.0
    if us.avg_utilization_pct > 90:
        score -= 20
    elif us.avg_utilization_pct > 80:
        score -= 10

    if us.over_limit_instances > 0:
        score -= 15 * min(us.over_limit_instances, 3)

    if us.drawing_power_breaches > 3:
        score -= 20
    elif us.drawing_power_breaches > 0:
        score -= 10

    us.score = max(0, min(100, score))

    # Flags
    if us.over_limit_instances > 0:
        us.flags.append(f"{us.over_limit_instances} instances of over-limit utilization")
    if us.drawing_power_breaches > 0:
        us.flags.append(f"{us.drawing_power_breaches} drawing power breaches — irregular operations")
    if us.avg_utilization_pct > 90:
        us.flags.append(f"Average utilization at {us.avg_utilization_pct:.0f}% — insufficient headroom")

    return us


# ═══════════════════════════════════════════════════════════════════════════════
#  Main Entry Point
# ═══════════════════════════════════════════════════════════════════════════════

def run_etb_analytics(etb_data: dict[str, list], entity_id: str = "") -> ETBAnalysis:
    """
    Run full ETB behavioral analysis.

    Parameters:
        etb_data: Dict with keys 'account_conduct', 'repayment_history',
                  'covenant_tracker', 'loan_utilization' — each a list of row dicts.
        entity_id: Entity identifier for labeling.

    Returns:
        ETBAnalysis with composite scoring and flags.
    """
    analysis = ETBAnalysis(entity_id=entity_id)

    analysis.conduct = analyze_conduct(etb_data.get("account_conduct", []))
    analysis.repayment = analyze_repayment(etb_data.get("repayment_history", []))
    analysis.covenant = analyze_covenants(etb_data.get("covenant_tracker", []))
    analysis.utilization = analyze_utilization(etb_data.get("loan_utilization", []))

    # Composite score
    analysis.composite_score = (
        analysis.conduct.score * CONDUCT_WEIGHT +
        analysis.repayment.score * REPAYMENT_WEIGHT +
        analysis.covenant.score * COVENANT_WEIGHT +
        analysis.utilization.score * UTILIZATION_WEIGHT
    )

    # Risk grade
    cs = analysis.composite_score
    if cs >= 80:
        analysis.risk_grade = "Low"
    elif cs >= 60:
        analysis.risk_grade = "Moderate"
    elif cs >= 40:
        analysis.risk_grade = "High"
    else:
        analysis.risk_grade = "Very High"

    # Collect all flags
    analysis.all_flags = (
        analysis.conduct.flags +
        analysis.repayment.flags +
        analysis.covenant.flags +
        analysis.utilization.flags
    )

    # Summary narrative
    analysis.summary = _build_summary(analysis)

    return analysis


def etb_analysis_to_dict(analysis: ETBAnalysis) -> dict[str, Any]:
    """Convert ETBAnalysis to serializable dict."""
    return {
        "entity_id": analysis.entity_id,
        "composite_score": round(analysis.composite_score, 1),
        "risk_grade": analysis.risk_grade,
        "summary": analysis.summary,
        "all_flags": analysis.all_flags,
        "conduct": {
            "score": round(analysis.conduct.score, 1),
            "avg_utilization_pct": round(analysis.conduct.avg_utilization_pct, 1),
            "peak_utilization_pct": round(analysis.conduct.peak_utilization_pct, 1),
            "total_cheque_returns": analysis.conduct.total_cheque_returns,
            "months_with_returns": analysis.conduct.months_with_returns,
            "utilization_trend": analysis.conduct.utilization_trend,
            "turnover_trend": analysis.conduct.turnover_trend,
            "flags": analysis.conduct.flags,
        },
        "repayment": {
            "score": round(analysis.repayment.score, 1),
            "total_installments": analysis.repayment.total_installments,
            "on_time_count": analysis.repayment.on_time_count,
            "delayed_count": analysis.repayment.delayed_count,
            "max_dpd": analysis.repayment.max_dpd,
            "avg_dpd": round(analysis.repayment.avg_dpd, 1),
            "shortfall_instances": analysis.repayment.shortfall_instances,
            "recovery_trend": analysis.repayment.recovery_trend,
            "flags": analysis.repayment.flags,
        },
        "covenant": {
            "score": round(analysis.covenant.score, 1),
            "total_tested": analysis.covenant.total_covenants_tested,
            "compliance_count": analysis.covenant.compliance_count,
            "breach_count": analysis.covenant.breach_count,
            "breach_rate_pct": round(analysis.covenant.breach_rate_pct, 1),
            "consecutive_breaches": analysis.covenant.consecutive_breaches,
            "covenants_at_risk": analysis.covenant.covenants_at_risk,
            "flags": analysis.covenant.flags,
        },
        "utilization": {
            "score": round(analysis.utilization.score, 1),
            "facilities": analysis.utilization.facilities,
            "avg_utilization_pct": round(analysis.utilization.avg_utilization_pct, 1),
            "over_limit_instances": analysis.utilization.over_limit_instances,
            "drawing_power_breaches": analysis.utilization.drawing_power_breaches,
            "flags": analysis.utilization.flags,
        },
    }


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _f(v) -> float:
    """Safely convert to float."""
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", ""))
    except (ValueError, TypeError):
        return 0.0


def _build_summary(a: ETBAnalysis) -> str:
    """Build narrative summary of ETB analysis."""
    parts = [f"ETB Behavioral Analysis — Composite Score: {a.composite_score:.0f}/100 ({a.risk_grade} Risk)"]

    # Conduct
    c = a.conduct
    parts.append(f"\nAccount Conduct (Score: {c.score:.0f}/100): "
                 f"Average CC utilization at {c.avg_utilization_pct:.0f}% with {c.total_cheque_returns} cheque returns. "
                 f"Utilization trend: {c.utilization_trend}. Turnover trend: {c.turnover_trend}.")

    # Repayment
    r = a.repayment
    on_time_pct = r.on_time_count / r.total_installments * 100 if r.total_installments else 0
    parts.append(f"\nRepayment Behavior (Score: {r.score:.0f}/100): "
                 f"{on_time_pct:.0f}% on-time rate ({r.on_time_count}/{r.total_installments}). "
                 f"Max DPD: {r.max_dpd} days. Trend: {r.recovery_trend}.")

    # Covenants
    cv = a.covenant
    parts.append(f"\nCovenant Compliance (Score: {cv.score:.0f}/100): "
                 f"{cv.compliance_count}/{cv.total_covenants_tested} compliant. "
                 f"Breach rate: {cv.breach_rate_pct:.0f}%.")
    if cv.covenants_at_risk:
        parts.append(f"  At-risk covenants: {', '.join(cv.covenants_at_risk)}")

    # Utilization
    u = a.utilization
    parts.append(f"\nFacility Utilization (Score: {u.score:.0f}/100): "
                 f"Average utilization {u.avg_utilization_pct:.0f}%. "
                 f"DP breaches: {u.drawing_power_breaches}.")

    if a.all_flags:
        parts.append(f"\nRed Flags ({len(a.all_flags)}):")
        for flag in a.all_flags:
            parts.append(f"  ⚠ {flag}")

    return "\n".join(parts)
