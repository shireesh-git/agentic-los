"""
Fraud Detection Engine — Multi-Signal Forensic Analysis
========================================================
Implements 7 fraud detection methodologies:
  1. Beneish M-Score (financial manipulation probability)
  2. Benford's Law (digit distribution anomaly)
  3. Revenue Consistency Score (cross-source divergence)
  4. Altman Z-Score (distress / fraud overlap)
  5. Governance Red Flags (board, auditor, filing anomalies)
  6. Document Anomaly Detection (metadata forensics)
  7. Circular Transaction / Evergreening Signals

Each returns a component score; composite fraud risk = weighted average.
"""

import math
import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from src.models.canonical_model import (
    FinancialStatement, Borrower, GroupEntity, DirectorPromoter,
    MarketSignal, ConductRecord, CovenantRecord,
    ExistingExposure, RiskSeverity,
)


# ─── Data Structures ────────────────────────────────────────────────────────

@dataclass
class FraudFlag:
    category: str          # e.g. "beneish", "benford", "governance"
    indicator: str         # specific check name
    severity: str          # LOW, MEDIUM, HIGH, CRITICAL
    score: float           # 0–100
    details: str           # human-readable explanation
    evidence: dict = field(default_factory=dict)


@dataclass
class FraudReport:
    entity_id: str
    company_name: str
    composite_score: float = 0.0      # 0–100 (higher = more suspicious)
    risk_grade: str = "LOW"            # LOW / MEDIUM / HIGH / CRITICAL
    beneish_m_score: Optional[float] = None
    beneish_probability: str = "N/A"
    altman_z_score: Optional[float] = None
    altman_zone: str = "N/A"
    benford_chi_sq: Optional[float] = None
    benford_verdict: str = "N/A"
    revenue_consistency: float = 100.0
    governance_score: float = 100.0
    document_anomaly_score: float = 0.0
    circular_txn_score: float = 0.0
    flags: list = field(default_factory=list)
    summary: str = ""


# ─── Component Weights ──────────────────────────────────────────────────────

WEIGHTS = {
    "beneish": 0.25,
    "benford": 0.10,
    "revenue_consistency": 0.20,
    "altman": 0.10,
    "governance": 0.15,
    "document_anomaly": 0.10,
    "circular_txn": 0.10,
}

GRADE_THRESHOLDS = {"LOW": 25, "MEDIUM": 45, "HIGH": 65}  # >=65 = CRITICAL


# ─── 1. Beneish M-Score ─────────────────────────────────────────────────────

def _safe_div(a, b, default=0.0):
    if b is None or b == 0:
        return default
    return a / b


def compute_beneish_m_score(current: dict, prior: dict) -> tuple[Optional[float], list[FraudFlag]]:
    """
    Beneish M-Score: 8-variable model for earnings manipulation.
    M > -1.78 suggests likely manipulation.
    Returns (m_score, flags).
    """
    flags = []
    try:
        # Days Sales in Receivables Index (DSRI)
        dsri = _safe_div(
            _safe_div(current.get("trade_receivables", 0), current.get("revenue_operating", 1)),
            _safe_div(prior.get("trade_receivables", 0), prior.get("revenue_operating", 1)),
            default=1.0
        )

        # Gross Margin Index (GMI)
        gm_curr = 1 - _safe_div(current.get("raw_material_cost", 0), current.get("revenue_operating", 1))
        gm_prior = 1 - _safe_div(prior.get("raw_material_cost", 0), prior.get("revenue_operating", 1))
        gmi = _safe_div(gm_prior, gm_curr, default=1.0)

        # Asset Quality Index (AQI)
        ca_curr = current.get("current_assets", 0) + current.get("net_fixed_assets", 0)
        ta_curr = current.get("total_assets", 1)
        ca_prior = prior.get("current_assets", 0) + prior.get("net_fixed_assets", 0)
        ta_prior = prior.get("total_assets", 1)
        aqi = _safe_div(1 - _safe_div(ca_curr, ta_curr), 1 - _safe_div(ca_prior, ta_prior), default=1.0)

        # Sales Growth Index (SGI)
        sgi = _safe_div(current.get("revenue_operating", 0), prior.get("revenue_operating", 1), default=1.0)

        # Depreciation Index (DEPI)
        dep_rate_curr = _safe_div(
            current.get("depreciation", 0),
            current.get("depreciation", 0) + current.get("net_fixed_assets", 1)
        )
        dep_rate_prior = _safe_div(
            prior.get("depreciation", 0),
            prior.get("depreciation", 0) + prior.get("net_fixed_assets", 1)
        )
        depi = _safe_div(dep_rate_prior, dep_rate_curr, default=1.0)

        # SGA Expense Index (SGAI)
        sga_curr = _safe_div(
            current.get("employee_cost", 0) + current.get("other_expenses", 0),
            current.get("revenue_operating", 1)
        )
        sga_prior = _safe_div(
            prior.get("employee_cost", 0) + prior.get("other_expenses", 0),
            prior.get("revenue_operating", 1)
        )
        sgai = _safe_div(sga_curr, sga_prior, default=1.0)

        # Leverage Index (LVGI)
        lev_curr = _safe_div(current.get("total_debt", 0), current.get("total_assets", 1))
        lev_prior = _safe_div(prior.get("total_debt", 0), prior.get("total_assets", 1))
        lvgi = _safe_div(lev_curr, lev_prior, default=1.0)

        # Total Accruals to Total Assets (TATA)
        tata = _safe_div(
            current.get("pat", 0) - current.get("operating_cash_flow", 0),
            current.get("total_assets", 1)
        )

        # M-Score = -4.84 + 0.920*DSRI + 0.528*GMI + 0.404*AQI + 0.892*SGI
        #           + 0.115*DEPI - 0.172*SGAI + 4.679*TATA - 0.327*LVGI
        m = (-4.84 + 0.920 * dsri + 0.528 * gmi + 0.404 * aqi + 0.892 * sgi
             + 0.115 * depi - 0.172 * sgai + 4.679 * tata - 0.327 * lvgi)

        components = {"DSRI": round(dsri, 3), "GMI": round(gmi, 3), "AQI": round(aqi, 3),
                      "SGI": round(sgi, 3), "DEPI": round(depi, 3), "SGAI": round(sgai, 3),
                      "LVGI": round(lvgi, 3), "TATA": round(tata, 4)}

        if m > -1.78:
            sev = "CRITICAL" if m > -1.0 else "HIGH"
            flags.append(FraudFlag(
                category="beneish", indicator="M-Score Manipulation Signal",
                severity=sev, score=min(100, max(0, (m + 3) * 25)),
                details=f"Beneish M-Score = {m:.2f} (threshold: -1.78). "
                        f"Score above threshold suggests likely earnings manipulation.",
                evidence=components
            ))
        elif dsri > 1.3:
            flags.append(FraudFlag(
                category="beneish", indicator="Receivables Growth Anomaly",
                severity="MEDIUM", score=40,
                details=f"DSRI = {dsri:.2f} — receivables growing faster than revenue. "
                        f"May indicate channel stuffing or revenue acceleration.",
                evidence={"DSRI": round(dsri, 3)}
            ))
        if tata > 0.05:
            flags.append(FraudFlag(
                category="beneish", indicator="High Accruals vs Cash Flow",
                severity="HIGH", score=55,
                details=f"TATA = {tata:.4f} — earnings significantly exceed operating cash. "
                        f"Common in manipulation scenarios.",
                evidence={"TATA": round(tata, 4), "PAT": current.get("pat"),
                          "OCF": current.get("operating_cash_flow")}
            ))

        return round(m, 3), flags

    except Exception:
        return None, []


# ─── 2. Benford's Law ───────────────────────────────────────────────────────

BENFORD_EXPECTED = {1: 0.301, 2: 0.176, 3: 0.125, 4: 0.097,
                    5: 0.079, 6: 0.067, 7: 0.058, 8: 0.051, 9: 0.046}


def compute_benford_score(financials: dict) -> tuple[Optional[float], list[FraudFlag]]:
    """
    Chi-squared test of leading-digit distribution vs Benford's Law.
    Returns (chi_sq, flags). Higher chi_sq = more deviation.
    """
    digits = []
    for period_data in financials.values():
        items = period_data.line_items if hasattr(period_data, "line_items") else period_data
        if isinstance(items, dict):
            for v in items.values():
                if isinstance(v, (int, float)) and abs(v) >= 10:
                    first = int(str(abs(v)).lstrip("0")[0]) if str(abs(v)).lstrip("0") else 0
                    if 1 <= first <= 9:
                        digits.append(first)

    if len(digits) < 20:
        return None, []

    counts = Counter(digits)
    total = len(digits)
    chi_sq = 0.0
    for d in range(1, 10):
        observed = counts.get(d, 0) / total
        expected = BENFORD_EXPECTED[d]
        chi_sq += ((observed - expected) ** 2) / expected

    flags = []
    # Critical threshold ~21.67 for df=8 at p=0.005
    if chi_sq > 21.67:
        flags.append(FraudFlag(
            category="benford", indicator="Benford's Law Significant Deviation",
            severity="HIGH", score=min(100, chi_sq * 3),
            details=f"Chi-squared = {chi_sq:.2f} (critical: 21.67). "
                    f"Financial figures deviate significantly from expected digit distribution. "
                    f"Sample size: {total} values.",
            evidence={"chi_squared": round(chi_sq, 3), "sample_size": total,
                      "distribution": {str(d): round(counts.get(d, 0)/total, 3) for d in range(1, 10)}}
        ))
    elif chi_sq > 15.51:
        flags.append(FraudFlag(
            category="benford", indicator="Benford's Law Moderate Deviation",
            severity="MEDIUM", score=min(80, chi_sq * 2.5),
            details=f"Chi-squared = {chi_sq:.2f} (warning: 15.51). "
                    f"Mild deviation from Benford's Law detected.",
            evidence={"chi_squared": round(chi_sq, 3), "sample_size": total}
        ))

    return round(chi_sq, 3), flags


# ─── 3. Revenue Consistency Score ───────────────────────────────────────────

def compute_revenue_consistency(company_data: dict) -> tuple[float, list[FraudFlag]]:
    """
    Cross-source revenue consistency: audited vs provisional vs exchange vs GST.
    Returns (consistency_pct, flags). 100 = perfect match.
    """
    flags = []
    sources = {}

    # Audited revenue (latest)
    financials = company_data.get("financials", {})
    for period in sorted(financials.keys(), reverse=True):
        fs = financials[period]
        items = fs.line_items if hasattr(fs, "line_items") else fs
        if isinstance(items, dict) and items.get("revenue_operating"):
            sources["audited"] = items["revenue_operating"]
            break

    # Provisional
    prov = company_data.get("provisional")
    if prov:
        items = prov.line_items if hasattr(prov, "line_items") else prov
        if isinstance(items, dict) and items.get("revenue_operating"):
            sources["provisional"] = items["revenue_operating"]

    # Exchange filing
    ef = company_data.get("exchange_filing")
    if ef:
        items = ef.line_items if hasattr(ef, "line_items") else ef
        if isinstance(items, dict) and items.get("revenue_operating"):
            sources["exchange"] = items["revenue_operating"]

    if len(sources) < 2:
        return 100.0, []

    values = list(sources.values())
    mean_val = statistics.mean(values)
    if mean_val == 0:
        return 100.0, []

    max_dev = max(abs(v - mean_val) / mean_val for v in values)
    consistency = max(0.0, 100.0 - max_dev * 200)

    if max_dev > 0.15:
        sev = "CRITICAL" if max_dev > 0.30 else "HIGH"
        flags.append(FraudFlag(
            category="revenue_consistency", indicator="Multi-Source Revenue Mismatch",
            severity=sev, score=min(100, max_dev * 200),
            details=f"Maximum revenue deviation = {max_dev*100:.1f}% across sources. "
                    f"Sources: {', '.join(f'{k}=₹{v:.0f}Cr' for k, v in sources.items())}. "
                    f"Large discrepancies may indicate revenue inflation or selective reporting.",
            evidence=sources
        ))
    elif max_dev > 0.05:
        flags.append(FraudFlag(
            category="revenue_consistency", indicator="Revenue Source Variation",
            severity="MEDIUM", score=min(60, max_dev * 150),
            details=f"Revenue deviation = {max_dev*100:.1f}% across sources. "
                    f"Minor variation — may reflect timing or provisional estimates.",
            evidence=sources
        ))

    return round(consistency, 1), flags


# ─── 4. Altman Z-Score ──────────────────────────────────────────────────────

def compute_altman_z(current: dict, borrower: Optional[Borrower] = None) -> tuple[Optional[float], list[FraudFlag]]:
    """
    Altman Z-Score for bankruptcy/distress prediction.
    Z > 2.99 = safe, 1.81–2.99 = grey, < 1.81 = distress.
    Distressed companies may be more prone to fraud (desperation-driven manipulation).
    """
    flags = []
    try:
        ta = current.get("total_assets", 0)
        if ta == 0:
            return None, []

        wc = current.get("current_assets", 0) - current.get("current_liabilities", 0)
        re = current.get("reserves_surplus", 0)
        ebit = current.get("ebit", 0)
        equity = current.get("total_equity", 0)
        debt = current.get("total_debt", 0)
        revenue = current.get("revenue_operating", 0)

        x1 = wc / ta
        x2 = re / ta
        x3 = ebit / ta
        x4 = equity / (debt if debt > 0 else 1)
        x5 = revenue / ta

        z = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5

        if z < 1.81:
            flags.append(FraudFlag(
                category="altman", indicator="Distress Zone — Elevated Fraud Risk",
                severity="HIGH", score=min(100, (2.5 - z) * 50),
                details=f"Altman Z-Score = {z:.2f} (distress zone < 1.81). "
                        f"Financially distressed entities show higher propensity for "
                        f"earnings manipulation and fraud.",
                evidence={"z_score": round(z, 3), "X1_WC/TA": round(x1, 3),
                          "X2_RE/TA": round(x2, 3), "X3_EBIT/TA": round(x3, 3),
                          "X4_EQ/TD": round(x4, 3), "X5_Rev/TA": round(x5, 3)}
            ))
        elif z < 2.99:
            flags.append(FraudFlag(
                category="altman", indicator="Grey Zone — Moderate Distress Risk",
                severity="MEDIUM", score=min(60, (3.0 - z) * 30),
                details=f"Altman Z-Score = {z:.2f} (grey zone: 1.81–2.99). "
                        f"Inconclusive distress prediction — monitor closely.",
                evidence={"z_score": round(z, 3)}
            ))

        return round(z, 3), flags

    except Exception:
        return None, []


# ─── 5. Governance Red Flags ────────────────────────────────────────────────

def compute_governance_flags(borrower: Borrower, group: GroupEntity,
                             directors: list, market_signals: list,
                             existing_exposure: list) -> tuple[float, list[FraudFlag]]:
    """
    Governance risk scoring: board composition, related parties, signals, structure.
    Returns (governance_score 0-100 where 100=clean, flags).
    """
    flags = []
    score = 100.0

    # Check board independence
    if directors:
        independent = sum(1 for d in directors
                          if hasattr(d, 'designation') and 'independent' in d.designation.lower())
        total_board = len(directors)
        indep_pct = independent / total_board * 100 if total_board > 0 else 0

        if indep_pct < 33:
            penalty = min(25, (33 - indep_pct))
            score -= penalty
            flags.append(FraudFlag(
                category="governance", indicator="Low Board Independence",
                severity="HIGH" if indep_pct < 20 else "MEDIUM",
                score=penalty * 2,
                details=f"Independent directors: {independent}/{total_board} ({indep_pct:.0f}%). "
                        f"SEBI mandates minimum 33% for listed entities. "
                        f"Low independence increases fraud risk.",
                evidence={"independent": independent, "total": total_board, "pct": round(indep_pct, 1)}
            ))

    # Promoter holding concentration
    if group and hasattr(group, 'promoter_holding_pct'):
        if group.promoter_holding_pct > 75:
            score -= 15
            flags.append(FraudFlag(
                category="governance", indicator="Excessive Promoter Concentration",
                severity="MEDIUM", score=30,
                details=f"Promoter holding = {group.promoter_holding_pct}%. "
                        f"High concentration (>75%) weakens minority oversight.",
                evidence={"promoter_pct": group.promoter_holding_pct}
            ))

    # Cross-directorships (related party risk)
    if directors:
        total_other = sum(len(getattr(d, 'other_directorships', []) or []) for d in directors
                          if hasattr(d, 'is_promoter') and d.is_promoter)
        if total_other > 5:
            score -= 10
            flags.append(FraudFlag(
                category="governance", indicator="Extensive Promoter Cross-Directorships",
                severity="MEDIUM", score=25,
                details=f"Promoter directors hold {total_other} directorships in other entities. "
                        f"May indicate related party complexity and tunneling risk.",
                evidence={"promoter_external_directorships": total_other}
            ))

    # Market signal analysis
    negative_signals = [s for s in (market_signals or [])
                        if hasattr(s, 'sentiment') and s.sentiment == "negative"]
    critical_signals = [s for s in negative_signals
                        if hasattr(s, 'severity') and s.severity == RiskSeverity.CRITICAL]

    if critical_signals:
        score -= min(30, len(critical_signals) * 15)
        flags.append(FraudFlag(
            category="governance", indicator="Critical Market Intelligence",
            severity="CRITICAL", score=min(80, len(critical_signals) * 25),
            details=f"{len(critical_signals)} critical negative signal(s): "
                    + "; ".join(s.headline for s in critical_signals[:3]),
            evidence={"critical_count": len(critical_signals),
                      "signals": [s.headline for s in critical_signals[:5]]}
        ))
    elif len(negative_signals) > 2:
        score -= min(15, len(negative_signals) * 5)
        flags.append(FraudFlag(
            category="governance", indicator="Multiple Negative Signals",
            severity="MEDIUM", score=min(40, len(negative_signals) * 10),
            details=f"{len(negative_signals)} negative market/news signals detected.",
            evidence={"negative_count": len(negative_signals)}
        ))

    # Rating watch / downgrade
    if borrower and hasattr(borrower, 'credit_rating') and borrower.credit_rating:
        rating = borrower.credit_rating.lower()
        if any(w in rating for w in ["watch negative", "downgrade", "default", "d/"]):
            score -= 20
            flags.append(FraudFlag(
                category="governance", indicator="Rating Under Stress",
                severity="HIGH", score=50,
                details=f"Credit rating '{borrower.credit_rating}' indicates stress/watch. "
                        f"Rating downgrades correlate with heightened fraud risk.",
                evidence={"rating": borrower.credit_rating}
            ))

    return max(0, round(score, 1)), flags


# ─── 6. Document Anomaly Detection ──────────────────────────────────────────

def compute_document_anomalies(extraction_data: Optional[dict] = None,
                               ocr_results: Optional[dict] = None) -> tuple[float, list[FraudFlag]]:
    """
    Analyse document extraction and OCR metadata for anomalies.
    Returns (anomaly_score 0-100, flags). 0 = clean.
    """
    flags = []
    score = 0.0

    if ocr_results:
        for doc_name, result in ocr_results.items():
            meta = result.get("metadata", {})
            risk = meta.get("risk_score", 0)
            if risk > 50:
                score += min(30, risk * 0.3)
                anom = meta.get("anomalies", [])
                flags.append(FraudFlag(
                    category="document_anomaly", indicator=f"Document Metadata Risk: {doc_name}",
                    severity="HIGH" if risk > 70 else "MEDIUM",
                    score=risk,
                    details=f"Document '{doc_name}' metadata risk={risk}. "
                            f"Anomalies: {', '.join(anom[:3]) if anom else 'see evidence'}.",
                    evidence=meta
                ))

    if extraction_data:
        sources = extraction_data.get("cross_source", {})
        mismatches = sources.get("mismatches", [])
        if len(mismatches) > 2:
            penalty = min(30, len(mismatches) * 8)
            score += penalty
            flags.append(FraudFlag(
                category="document_anomaly", indicator="Cross-Document Inconsistencies",
                severity="HIGH" if len(mismatches) > 4 else "MEDIUM",
                score=min(70, penalty * 2),
                details=f"{len(mismatches)} cross-document mismatches found during extraction. "
                        f"Inconsistent figures across documents suggest tampering or fabrication.",
                evidence={"mismatch_count": len(mismatches),
                          "examples": mismatches[:3]}
            ))

    return min(100, round(score, 1)), flags


# ─── 7. Circular Transaction / Evergreening Detection ───────────────────────

def compute_circular_txn_score(company_data: dict) -> tuple[float, list[FraudFlag]]:
    """
    Detect patterns suggestive of circular transactions or loan evergreening.
    Indicators:
      - Trade receivables growing much faster than revenue
      - Receivables concentrated (high as % of revenue)
      - Operating cash flow consistently negative despite profits
      - Related-party transactions identified via group structure
      - Loans outstanding increasing while utilization remains maxed
    Returns (score 0-100, flags).
    """
    flags = []
    score = 0.0

    financials = company_data.get("financials", {})
    periods = sorted(financials.keys())

    if len(periods) >= 2:
        latest = financials[periods[-1]]
        prior = financials[periods[-2]]
        li = latest.line_items if hasattr(latest, "line_items") else latest
        pi = prior.line_items if hasattr(prior, "line_items") else prior

        if isinstance(li, dict) and isinstance(pi, dict):
            # Revenue vs receivables growth divergence
            rev_growth = _safe_div(li.get("revenue_operating", 0) - pi.get("revenue_operating", 0),
                                   pi.get("revenue_operating", 1)) * 100
            rec_growth = _safe_div(li.get("trade_receivables", 0) - pi.get("trade_receivables", 0),
                                   pi.get("trade_receivables", 1)) * 100

            if rec_growth > rev_growth * 2 and rec_growth > 20:
                penalty = min(30, (rec_growth - rev_growth) * 0.5)
                score += penalty
                flags.append(FraudFlag(
                    category="circular_txn", indicator="Receivables Growing Faster Than Revenue",
                    severity="HIGH", score=min(70, penalty * 2),
                    details=f"Revenue growth = {rev_growth:.1f}%, receivables growth = {rec_growth:.1f}%. "
                            f"Receivables decoupled from sales — potential channel stuffing or circular billing.",
                    evidence={"revenue_growth_pct": round(rev_growth, 1),
                              "receivables_growth_pct": round(rec_growth, 1)}
                ))

            # Receivables as % of revenue (concentration)
            rec_pct = _safe_div(li.get("trade_receivables", 0),
                                li.get("revenue_operating", 1)) * 100
            if rec_pct > 40:
                score += 15
                flags.append(FraudFlag(
                    category="circular_txn", indicator="High Receivable Concentration",
                    severity="MEDIUM", score=40,
                    details=f"Trade receivables = {rec_pct:.1f}% of revenue. "
                            f"Normal range: 15–25%. High concentration suggests collection issues "
                            f"or fictitious sales.",
                    evidence={"receivables_pct_of_revenue": round(rec_pct, 1)}
                ))

            # Profits without cash flow (accrual manipulation)
            pat = li.get("pat", 0)
            ocf = li.get("operating_cash_flow", 0)
            if pat > 0 and ocf < 0:
                score += 20
                flags.append(FraudFlag(
                    category="circular_txn", indicator="Profit Without Operating Cash Flow",
                    severity="HIGH", score=55,
                    details=f"PAT = ₹{pat:.0f}Cr but OCF = ₹{ocf:.0f}Cr (negative). "
                            f"Persistent profit without cash generation is a classic fraud signal.",
                    evidence={"pat": pat, "ocf": ocf}
                ))

    # ETB-specific: utilization + conduct degradation = evergreening
    conduct = company_data.get("conduct", [])
    if conduct:
        recent = conduct[-4:] if len(conduct) >= 4 else conduct
        avg_util = statistics.mean(
            getattr(c, "limit_utilization_pct", 0) if hasattr(c, "limit_utilization_pct")
            else c.get("limit_utilization_pct", 0) if isinstance(c, dict) else 0
            for c in recent
        )
        avg_cheque = statistics.mean(
            getattr(c, "cheque_returns", 0) if hasattr(c, "cheque_returns")
            else c.get("cheque_returns", 0) if isinstance(c, dict) else 0
            for c in recent
        )
        if avg_util > 90 and avg_cheque > 5:
            score += 20
            flags.append(FraudFlag(
                category="circular_txn", indicator="Evergreening Signal — Max Utilization + Returns",
                severity="HIGH", score=60,
                details=f"Average limit utilization = {avg_util:.0f}%, "
                        f"average cheque returns = {avg_cheque:.1f}/quarter. "
                        f"Classic evergreening pattern: maxed limits with failing payments.",
                evidence={"avg_utilization_pct": round(avg_util, 1),
                          "avg_cheque_returns": round(avg_cheque, 1)}
            ))

    return min(100, round(score, 1)), flags


# ═══════════════════════════════════════════════════════════════════════════════
# COMPOSITE FRAUD SCAN
# ═══════════════════════════════════════════════════════════════════════════════

def run_fraud_scan(company_data: dict,
                   extraction_data: Optional[dict] = None,
                   ocr_results: Optional[dict] = None) -> FraudReport:
    """
    Run all 7 fraud detection modules and produce composite report.
    """
    borrower = company_data.get("borrower")
    if not borrower:
        return FraudReport(entity_id="unknown", company_name="Unknown")

    eid = borrower.entity_id if hasattr(borrower, "entity_id") else "unknown"
    name = borrower.company_name if hasattr(borrower, "company_name") else "Unknown"
    report = FraudReport(entity_id=eid, company_name=name)

    financials = company_data.get("financials", {})
    periods = sorted(financials.keys())

    # Get latest and prior financial line items
    current_li, prior_li = {}, {}
    if periods:
        latest_fs = financials[periods[-1]]
        current_li = latest_fs.line_items if hasattr(latest_fs, "line_items") else (latest_fs if isinstance(latest_fs, dict) else {})
    if len(periods) >= 2:
        prior_fs = financials[periods[-2]]
        prior_li = prior_fs.line_items if hasattr(prior_fs, "line_items") else (prior_fs if isinstance(prior_fs, dict) else {})

    component_scores = {}

    # 1. Beneish M-Score
    if current_li and prior_li:
        m_score, m_flags = compute_beneish_m_score(current_li, prior_li)
        report.beneish_m_score = m_score
        report.beneish_probability = (
            "Likely Manipulator" if m_score and m_score > -1.78
            else "Unlikely Manipulator" if m_score else "N/A"
        )
        report.flags.extend(m_flags)
        component_scores["beneish"] = min(100, max(0, ((m_score or -5) + 3) * 20)) if m_score else 0

    # 2. Benford's Law
    benford_chi, benford_flags = compute_benford_score(financials)
    report.benford_chi_sq = benford_chi
    report.benford_verdict = (
        "Significant Deviation" if benford_chi and benford_chi > 21.67
        else "Moderate Deviation" if benford_chi and benford_chi > 15.51
        else "Conforming" if benford_chi else "Insufficient Data"
    )
    report.flags.extend(benford_flags)
    component_scores["benford"] = min(100, (benford_chi or 0) * 3)

    # 3. Revenue Consistency
    consistency, rev_flags = compute_revenue_consistency(company_data)
    report.revenue_consistency = consistency
    report.flags.extend(rev_flags)
    component_scores["revenue_consistency"] = max(0, 100 - consistency)

    # 4. Altman Z-Score
    if current_li:
        z_score, z_flags = compute_altman_z(current_li, borrower)
        report.altman_z_score = z_score
        report.altman_zone = (
            "Safe Zone" if z_score and z_score > 2.99
            else "Grey Zone" if z_score and z_score > 1.81
            else "Distress Zone" if z_score else "N/A"
        )
        report.flags.extend(z_flags)
        component_scores["altman"] = min(100, max(0, (3.0 - (z_score or 3.0)) * 30))

    # 5. Governance
    gov_score, gov_flags = compute_governance_flags(
        borrower,
        company_data.get("group"),
        company_data.get("directors", []),
        company_data.get("market_signals", []),
        company_data.get("existing_exposure", [])
    )
    report.governance_score = gov_score
    report.flags.extend(gov_flags)
    component_scores["governance"] = max(0, 100 - gov_score)

    # 6. Document Anomalies
    doc_score, doc_flags = compute_document_anomalies(extraction_data, ocr_results)
    report.document_anomaly_score = doc_score
    report.flags.extend(doc_flags)
    component_scores["document_anomaly"] = doc_score

    # 7. Circular Transaction / Evergreening
    circ_score, circ_flags = compute_circular_txn_score(company_data)
    report.circular_txn_score = circ_score
    report.flags.extend(circ_flags)
    component_scores["circular_txn"] = circ_score

    # Composite weighted score
    composite = 0.0
    total_weight = 0.0
    for key, weight in WEIGHTS.items():
        if key in component_scores:
            composite += component_scores[key] * weight
            total_weight += weight
    if total_weight > 0:
        composite /= total_weight

    report.composite_score = round(composite, 1)

    # Risk grade
    if report.composite_score >= GRADE_THRESHOLDS["HIGH"]:
        report.risk_grade = "CRITICAL"
    elif report.composite_score >= GRADE_THRESHOLDS["MEDIUM"]:
        report.risk_grade = "HIGH"
    elif report.composite_score >= GRADE_THRESHOLDS["LOW"]:
        report.risk_grade = "MEDIUM"
    else:
        report.risk_grade = "LOW"

    # Summary
    flag_count = len(report.flags)
    critical = sum(1 for f in report.flags if f.severity == "CRITICAL")
    high = sum(1 for f in report.flags if f.severity == "HIGH")
    report.summary = (
        f"Fraud Risk: {report.risk_grade} (Score: {report.composite_score}/100). "
        f"{flag_count} flag(s) detected — {critical} critical, {high} high severity. "
        f"M-Score: {report.beneish_probability}, Z-Score: {report.altman_zone}, "
        f"Benford: {report.benford_verdict}."
    )

    return report


def fraud_report_to_dict(report: FraudReport) -> dict:
    """Serialize FraudReport to JSON-safe dict."""
    return {
        "entity_id": report.entity_id,
        "company_name": report.company_name,
        "composite_score": report.composite_score,
        "risk_grade": report.risk_grade,
        "summary": report.summary,
        "components": {
            "beneish_m_score": report.beneish_m_score,
            "beneish_probability": report.beneish_probability,
            "altman_z_score": report.altman_z_score,
            "altman_zone": report.altman_zone,
            "benford_chi_squared": report.benford_chi_sq,
            "benford_verdict": report.benford_verdict,
            "revenue_consistency_pct": report.revenue_consistency,
            "governance_score": report.governance_score,
            "document_anomaly_score": report.document_anomaly_score,
            "circular_txn_score": report.circular_txn_score,
        },
        "flags": [
            {
                "category": f.category,
                "indicator": f.indicator,
                "severity": f.severity,
                "score": f.score,
                "details": f.details,
                "evidence": f.evidence,
            }
            for f in report.flags
        ],
        "flag_summary": {
            "total": len(report.flags),
            "critical": sum(1 for f in report.flags if f.severity == "CRITICAL"),
            "high": sum(1 for f in report.flags if f.severity == "HIGH"),
            "medium": sum(1 for f in report.flags if f.severity == "MEDIUM"),
            "low": sum(1 for f in report.flags if f.severity == "LOW"),
        }
    }
