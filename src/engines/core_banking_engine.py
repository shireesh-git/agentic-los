"""
Core Banking Analysis Engine
==============================
Analyzes ETB core banking data — LOAN accounts, BCLC (Borrower-wise Credit Limit
Concentration), LIABILITY (deposits/balances), and FEES/COMMISSION income.

All data points become factors in the CAM recommendation.
For NTB: returns "not_applicable" gracefully.
For ETB: provides comprehensive relationship profitability and risk analysis.
"""

import logging
from datetime import date

_log = logging.getLogger(__name__)


def analyze_core_banking(entity_id: str, core_banking_data: dict, case_type: str = "NTB") -> dict:
    """
    Comprehensive core banking analysis for ETB customers.
    Returns structured data for CAM integration.
    """
    if not core_banking_data or case_type.upper() == "NTB":
        return {
            "available": False,
            "entity_id": entity_id,
            "note": "NTB case — no core banking relationship data available",
            "loan_analysis": {},
            "bclc_analysis": {},
            "liability_analysis": {},
            "fees_analysis": {},
            "relationship_assessment": {},
            "decision_impact": "Not Applicable — fresh relationship",
        }

    result = {
        "available": True,
        "entity_id": entity_id,
        "analysis_date": str(date.today()),
    }

    # ── LOAN Account Analysis ──
    loan_accounts = core_banking_data.get("loan_accounts", [])
    result["loan_analysis"] = _analyze_loans(loan_accounts)

    # ── BCLC Analysis ──
    bclc = core_banking_data.get("bclc", {})
    result["bclc_analysis"] = _analyze_bclc(bclc)

    # ── LIABILITY (Deposits) Analysis ──
    liability = core_banking_data.get("liability", {})
    result["liability_analysis"] = _analyze_liability(liability)

    # ── FEES & COMMISSION Analysis ──
    fees = core_banking_data.get("fees_commission", [])
    result["fees_analysis"] = _analyze_fees(fees)

    # ── Relationship Assessment ──
    result["relationship_assessment"] = _assess_relationship(
        core_banking_data, result["loan_analysis"],
        result["liability_analysis"], result["fees_analysis"]
    )

    # ── Decision Impact ──
    result["decision_impact"] = _compute_decision_impact(result)

    return result


def _analyze_loans(loan_accounts: list) -> dict:
    """Analyze all loan/facility accounts."""
    if not loan_accounts:
        return {"available": False, "accounts": [], "summary": {}}

    accounts = []
    total_sanctioned = 0.0
    total_outstanding = 0.0
    total_overdue = 0.0
    max_dpd = 0
    has_sma = False
    has_npa = False

    for acc in loan_accounts:
        sanctioned = acc.get("sanction_limit_cr", 0)
        outstanding = acc.get("outstanding_cr", 0)
        overdue = acc.get("overdue_amount_cr", 0)
        dpd = acc.get("dpd", 0)
        classification = acc.get("asset_classification", "Standard")

        utilization_pct = round(outstanding / sanctioned * 100, 1) if sanctioned > 0 else 0

        accounts.append({
            "account_number": acc.get("account_number"),
            "facility_type": acc.get("facility_type"),
            "sanction_limit_cr": sanctioned,
            "outstanding_cr": outstanding,
            "utilization_pct": utilization_pct,
            "interest_rate_pct": acc.get("interest_rate_pct"),
            "overdue_amount_cr": overdue,
            "dpd": dpd,
            "asset_classification": classification,
            "sanction_date": acc.get("sanction_date"),
            "maturity_date": acc.get("maturity_date"),
            "repayment_frequency": acc.get("repayment_frequency"),
        })

        total_sanctioned += sanctioned
        total_outstanding += outstanding
        total_overdue += overdue
        max_dpd = max(max_dpd, dpd)

        if "SMA" in classification.upper():
            has_sma = True
        if "NPA" in classification.upper() or "SUB" in classification.upper():
            has_npa = True

    overall_utilization = round(total_outstanding / total_sanctioned * 100, 1) if total_sanctioned > 0 else 0

    # Risk classification
    if has_npa:
        account_health = "CRITICAL — Active NPA account(s) detected"
    elif has_sma:
        account_health = "WATCH — SMA classification present; close monitoring required"
    elif max_dpd > 0:
        account_health = f"CAUTION — Max DPD of {max_dpd} days; repayment delay noted"
    else:
        account_health = "HEALTHY — All accounts Standard with zero DPD"

    return {
        "available": True,
        "account_count": len(accounts),
        "accounts": accounts,
        "summary": {
            "total_sanctioned_cr": total_sanctioned,
            "total_outstanding_cr": total_outstanding,
            "overall_utilization_pct": overall_utilization,
            "total_overdue_cr": total_overdue,
            "max_dpd": max_dpd,
            "has_sma": has_sma,
            "has_npa": has_npa,
            "account_health": account_health,
        },
    }


def _analyze_bclc(bclc: dict) -> dict:
    """Analyze Borrower-wise Credit Limit Concentration."""
    if not bclc:
        return {"available": False}

    flags = []
    single_pct = bclc.get("single_borrower_limit_pct", 0)
    group_pct = bclc.get("group_borrower_limit_pct", 0)
    industry_pct = bclc.get("industry_exposure_pct", 0)
    sector_ceiling = bclc.get("sector_ceiling_pct", 15)

    # Check single borrower limit (RBI norm: 20% of capital funds)
    if single_pct > 15:
        flags.append(f"Single borrower exposure at {single_pct}% — approaching RBI limit of 20%")
    # Check group limit (RBI norm: 25%)
    if group_pct > 20:
        flags.append(f"Group exposure at {group_pct}% — approaching RBI limit of 25%")
    # Check sector concentration
    if industry_pct > sector_ceiling * 0.8:
        flags.append(f"Industry exposure at {industry_pct}% — nearing sector ceiling of {sector_ceiling}%")

    concentration_risk = "LOW"
    if flags:
        concentration_risk = "HIGH" if len(flags) >= 2 else "MEDIUM"

    return {
        "available": True,
        "total_fund_based_cr": bclc.get("total_fund_based_cr"),
        "total_non_fund_based_cr": bclc.get("total_non_fund_based_cr"),
        "total_exposure_cr": bclc.get("total_exposure_cr"),
        "single_borrower_limit_pct": single_pct,
        "group_borrower_limit_pct": group_pct,
        "within_single_limit": bclc.get("within_single_limit", True),
        "within_group_limit": bclc.get("within_group_limit", True),
        "industry_exposure_pct": industry_pct,
        "sector_ceiling_pct": sector_ceiling,
        "rating_based_limit_cr": bclc.get("rating_based_limit_cr"),
        "concentration_risk": concentration_risk,
        "flags": flags,
    }


def _analyze_liability(liability: dict) -> dict:
    """Analyze liability (deposit) relationship."""
    if not liability:
        return {"available": False}

    total_deposits = liability.get("total_deposits_cr", 0)
    avg_balance = liability.get("average_balance_6m_cr", 0)
    reciprocal = liability.get("reciprocal_business_cr", 0)
    cross_sell = liability.get("cross_sell_products", [])

    # Assess deposit stickiness
    if total_deposits > 0 and avg_balance > 0:
        stickiness = round(avg_balance / total_deposits * 100, 1)
    else:
        stickiness = 0

    # Relationship depth (cross-sell score)
    depth_score = len(cross_sell) * 15  # ~15 per product, max 100
    if depth_score > 100:
        depth_score = 100

    if depth_score >= 60:
        depth_label = "DEEP — multi-product relationship"
    elif depth_score >= 30:
        depth_label = "MODERATE — some cross-sell"
    else:
        depth_label = "SHALLOW — limited product penetration"

    return {
        "available": True,
        "current_account_balance_cr": liability.get("current_account_balance_cr"),
        "fixed_deposit_cr": liability.get("fixed_deposit_cr"),
        "total_deposits_cr": total_deposits,
        "average_balance_6m_cr": avg_balance,
        "reciprocal_business_cr": reciprocal,
        "deposit_stickiness_pct": stickiness,
        "cross_sell_products": cross_sell,
        "cross_sell_count": len(cross_sell),
        "relationship_depth_score": depth_score,
        "relationship_depth_label": depth_label,
    }


def _analyze_fees(fees: list) -> dict:
    """Analyze fee & commission income from the relationship."""
    if not fees:
        return {"available": False, "periods": [], "summary": {}}

    periods_data = []
    total_income_all = 0.0
    latest_income = 0.0

    for period in sorted(fees, key=lambda x: x.get("period", ""), reverse=True):
        period_total = period.get("total_income_cr", 0)
        total_income_all += period_total
        if not latest_income:
            latest_income = period_total

        periods_data.append({
            "period": period.get("period"),
            "processing_fees_cr": period.get("processing_fees_cr", 0),
            "renewal_fees_cr": period.get("renewal_fees_cr", 0),
            "lc_commission_cr": period.get("lc_commission_cr", 0),
            "bg_commission_cr": period.get("bg_commission_cr", 0),
            "forex_income_cr": period.get("forex_income_cr", 0),
            "other_charges_cr": period.get("other_charges_cr", 0),
            "total_income_cr": period_total,
        })

    # Income trend
    if len(fees) >= 2:
        sorted_fees = sorted(fees, key=lambda x: x.get("period", ""))
        first = sorted_fees[0].get("total_income_cr", 0)
        last = sorted_fees[-1].get("total_income_cr", 0)
        if first > 0:
            growth = round((last - first) / first * 100, 1)
            trend = "Growing" if growth > 5 else ("Declining" if growth < -5 else "Stable")
        else:
            growth = 0
            trend = "Stable"
    else:
        growth = 0
        trend = "N/A"

    # Profitability assessment
    if latest_income >= 10:
        profitability = "HIGH — significant fee income relationship"
    elif latest_income >= 5:
        profitability = "MODERATE — reasonable fee contribution"
    elif latest_income > 0:
        profitability = "LOW — marginal fee income"
    else:
        profitability = "NIL — no fee income recorded"

    return {
        "available": True,
        "periods": periods_data,
        "summary": {
            "latest_income_cr": latest_income,
            "total_income_all_periods_cr": total_income_all,
            "income_trend": trend,
            "income_growth_pct": growth,
            "profitability_assessment": profitability,
        },
    }


def _assess_relationship(core_banking: dict, loan_analysis: dict,
                         liability_analysis: dict, fees_analysis: dict) -> dict:
    """Overall relationship assessment combining all core banking dimensions."""
    relationship_since = core_banking.get("relationship_since", "")
    relationship_years = core_banking.get("relationship_years", 0)
    overall_classification = core_banking.get("overall_asset_classification", "Standard")

    # Compute relationship score (0-100)
    score = 50.0  # Base

    # Longevity bonus
    if relationship_years >= 10:
        score += 15
    elif relationship_years >= 5:
        score += 10
    elif relationship_years >= 3:
        score += 5

    # Account health
    loan_summary = loan_analysis.get("summary", {})
    if loan_summary.get("has_npa"):
        score -= 30
    elif loan_summary.get("has_sma"):
        score -= 15
    elif loan_summary.get("max_dpd", 0) == 0:
        score += 15

    # Deposit relationship
    if liability_analysis.get("available"):
        depth = liability_analysis.get("relationship_depth_score", 0)
        score += depth * 0.1  # Up to +10

    # Fee income
    fees_summary = fees_analysis.get("summary", {})
    if fees_summary.get("latest_income_cr", 0) >= 10:
        score += 10
    elif fees_summary.get("latest_income_cr", 0) >= 5:
        score += 5

    score = min(100, max(0, score))

    if score >= 75:
        rating = "STRONG — valued relationship with multiple positive indicators"
    elif score >= 55:
        rating = "SATISFACTORY — relationship in good standing"
    elif score >= 40:
        rating = "NEEDS ATTENTION — some areas of concern"
    else:
        rating = "WEAK — significant issues in banking relationship"

    return {
        "relationship_since": relationship_since,
        "relationship_years": relationship_years,
        "overall_asset_classification": overall_classification,
        "relationship_score": round(score, 1),
        "relationship_rating": rating,
        "total_exposure_cr": core_banking.get("total_exposure_cr", 0),
    }


def _compute_decision_impact(result: dict) -> str:
    """Compute how core banking data impacts the credit decision."""
    if not result.get("available"):
        return "Not Applicable — NTB customer"

    impacts = []
    loan_a = result.get("loan_analysis", {})
    bclc_a = result.get("bclc_analysis", {})
    liability_a = result.get("liability_analysis", {})
    fees_a = result.get("fees_analysis", {})
    rel = result.get("relationship_assessment", {})

    # Loan health impact
    summary = loan_a.get("summary", {})
    if summary.get("has_npa"):
        impacts.append("NEGATIVE: Active NPA — existing facility requires resolution before new sanction")
    elif summary.get("has_sma"):
        impacts.append("CAUTION: SMA classification — enhanced monitoring & additional security may be required")
    elif summary.get("max_dpd", 0) == 0:
        impacts.append("POSITIVE: Clean repayment record supports fresh facility sanction")

    # BCLC impact
    if bclc_a.get("flags"):
        impacts.append(f"CAUTION: Concentration risk — {'; '.join(bclc_a['flags'])}")
    elif bclc_a.get("available"):
        impacts.append("POSITIVE: Well within regulatory exposure limits")

    # Liability impact
    if liability_a.get("available"):
        depth = liability_a.get("relationship_depth_label", "")
        if "DEEP" in depth:
            impacts.append("POSITIVE: Deep multi-product relationship — high client stickiness")
        elif "SHALLOW" in depth:
            impacts.append("NEUTRAL: Limited product penetration — cross-sell opportunity")

    # Fee income impact
    profitability = fees_a.get("summary", {}).get("profitability_assessment", "")
    if "HIGH" in profitability:
        impacts.append("POSITIVE: High fee income justifies continued relationship investment")
    elif "LOW" in profitability or "NIL" in profitability:
        impacts.append("NEUTRAL: Low fee income — consider fee structure in new facility")

    # Relationship tenure
    years = rel.get("relationship_years", 0)
    if years >= 10:
        impacts.append(f"POSITIVE: {years}-year banking relationship provides comfort")
    elif years >= 5:
        impacts.append(f"POSITIVE: {years}-year relationship track record")

    return " | ".join(impacts) if impacts else "Insufficient data for impact assessment"


def core_banking_risk_factor(core_analysis: dict) -> float:
    """
    Extract a 0-100 risk score from core banking for the policy engine.
    0 = no risk (perfect ETB), 100 = maximum risk.
    """
    if not core_analysis or not core_analysis.get("available"):
        return 50.0  # Neutral for NTB

    rel_score = core_analysis.get("relationship_assessment", {}).get("relationship_score", 50)
    # Invert: high relationship score = low risk
    return round(100 - rel_score, 1)
