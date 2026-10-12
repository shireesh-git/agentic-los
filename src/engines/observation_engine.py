"""
Credit Risk Observation Engine — deterministic.

Turns the analytical engines' outputs, as assembled in the CAM fact pack,
into structured credit observations. It reads:

  * ``financial_summary``     — per-period line items and EBITDA margin (fact-pack builder)
  * ``ratio_analysis``        — every ratio for every period (ratio_engine)
  * ``benchmark_summary``     — latest-period peer comparison (benchmark_engine)
  * ``validation_exceptions`` — validation_engine findings
  * ``policy_decisions``      — tier-1 hard rules (policy_engine)
  * ``policy_thresholds``     — the bank's policy limits (config/rules.yaml)

No ratio is recomputed here. The only arithmetic is the period-on-period
change between two values those engines already produced (growth %, change in
days / bps / x) and the threshold comparison. This engine alone decides
whether an observation exists, its severity, metrics and trigger; the LLM may
only reword an observation afterwards (src/services/observation_narrator.py).

Thresholds: ``credit_observations`` in config/rules.yaml.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable, Optional

from src.models.observations import (
    SEVERITY_ORDER, CreditObservation, ObservationSeverity as Sev, ObservationStatus,
)

log = logging.getLogger(__name__)

ENGINE_VERSION = "obs_v1"
GENERATED_BY = f"observation_engine/{ENGINE_VERSION}"

_DEFAULT_POLICY_THRESHOLDS = {
    "min_dscr": 1.20, "max_debt_to_equity": 2.5, "min_current_ratio": 1.25,
    "min_interest_coverage": 2.0, "max_debt_to_ebitda": 4.0, "min_ebitda_margin_pct": 10,
    "max_tol_tnw": 4.0, "min_roe_pct": 12, "max_debtor_days": 90,
}

RATIO_LABELS = {
    "current_ratio": "Current ratio", "debt_to_equity": "Debt / Equity", "debt_to_ebitda": "Debt / EBITDA",
    "interest_coverage_ratio": "Interest coverage (ICR)", "dscr": "DSCR", "tol_tnw": "TOL / TNW",
    "net_profit_margin": "Net profit margin", "ebitda_margin": "EBITDA margin",
    "return_on_equity": "Return on equity", "return_on_assets": "Return on assets",
    "asset_turnover": "Asset turnover", "debtor_days": "Debtor days", "inventory_days": "Inventory days",
    "payable_days": "Payable days", "working_capital_cycle": "Working capital cycle",
    "altman_z_score": "Altman Z-score", "ocf_to_debt": "OCF / Debt",
}
# Ratios the ratio engine returns as fractions (0.13 = 13%).
_FRACTION_RATIOS = {"net_profit_margin", "ebitda_margin", "return_on_equity", "return_on_assets", "ocf_to_debt"}
_DAY_RATIOS = {"debtor_days", "inventory_days", "payable_days", "working_capital_cycle"}


# ─── Config ──────────────────────────────────────────────────────────────────

def observation_config() -> dict:
    from src.core.config_manager import config
    return config.get("rules", "credit_observations", default={}) or {}


def _policy_thresholds(fact_pack: dict) -> dict:
    configured = fact_pack.get("policy_thresholds")
    if not configured:
        try:
            from src.core.config_manager import config
            configured = config.get("rules", "policy_thresholds", default={}) or {}
        except Exception:
            configured = {}
    return {**_DEFAULT_POLICY_THRESHOLDS, **configured}


# ─── Reading the fact pack ───────────────────────────────────────────────────

def _num(value) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct_change(prev: Optional[float], curr: Optional[float]) -> Optional[float]:
    """Percentage change; None unless the base is positive."""
    if prev is None or curr is None or prev <= 0:
        return None
    return round((curr - prev) / prev * 100, 1)


class _Facts:
    """Read-only view of the fact-pack sections the detectors use."""

    def __init__(self, fact_pack: dict, case_id: str, created_at: str, settings: dict):
        self.fp = fact_pack
        self.case_id = case_id
        self.created_at = created_at
        self.settings = settings
        self.policy = _policy_thresholds(fact_pack)
        self.fin = (fact_pack.get("financial_summary") or {}).get("periods") or {}
        self.ratios = fact_pack.get("ratio_analysis") or {}
        periods = sorted(self.fin) or sorted(self.ratios)
        self.latest = periods[-1] if periods else None
        self.prior = periods[-2] if len(periods) >= 2 else None
        self.exceptions = fact_pack.get("validation_exceptions") or []
        self.tier1 = (fact_pack.get("policy_decisions") or {}).get("tier1_hard_rules") or []
        self.benchmarks = fact_pack.get("benchmark_summary") or {}

    def cfg(self, detector: str) -> dict:
        return self.settings.get(detector) or {}

    def line(self, period: Optional[str], key: str) -> Optional[float]:
        return _num((self.fin.get(period) or {}).get(key)) if period else None

    def ratio(self, period: Optional[str], name: str) -> Optional[float]:
        if not period:
            return None
        entry = (self.ratios.get(period) or {}).get(name)
        return _num(entry.get("value") if isinstance(entry, dict) else entry)

    def exception(self, code: str) -> Optional[dict]:
        return next((e for e in self.exceptions if e.get("code") == code), None)


# ─── Building blocks ─────────────────────────────────────────────────────────

def _metric(metric: str, label: str, period: str, value, unit: str, source: str) -> dict:
    return {"metric": metric, "label": label, "period": period, "value": value, "unit": unit, "source": source}


def _line_metric(f: _Facts, period: str, key: str, label: str) -> dict:
    return _metric(key, label, period, f.line(period, key), "cr", f"financial_summary.periods.{period}.{key}")


def _ratio_metric(f: _Facts, period: str, name: str) -> dict:
    unit = "fraction" if name in _FRACTION_RATIOS else "days" if name in _DAY_RATIOS else "x"
    return _metric(name, RATIO_LABELS.get(name, name), period, f.ratio(period, name), unit,
                   f"ratio_engine:{period}.{name}")


def _change(metric: str, label: str, prev, curr, change, change_unit: str) -> dict:
    return {"metric": metric, "label": label, "from": prev, "to": curr, "change": change, "change_unit": change_unit}


def _comparison(f: _Facts, changes: list[dict]) -> Optional[dict]:
    if not f.prior or not changes:
        return None
    return {"from_period": f.prior, "to_period": f.latest, "changes": changes}


def _evidence(kind: str, ref: str, description: str) -> dict:
    return {"type": kind, "ref": ref, "description": description}


def _exception_evidence(f: _Facts, code: str) -> list[dict]:
    e = f.exception(code)
    return [_evidence("validation_exception", code, e.get("description", ""))] if e else []


def _fmt_x(v) -> str:
    return "n/a" if v is None else f"{v:.2f}x"


def _fmt_pct(v) -> str:
    return "n/a" if v is None else f"{v:.1f}%"


def _fmt_cr(v) -> str:
    return "n/a" if v is None else f"₹{v:,.2f} Cr"


def _fmt_days(v) -> str:
    return "n/a" if v is None else f"{v:.1f} days"


def _make(f: _Facts, code: str, *, category: str, title: str, severity: Sev, summary: str,
          explanation: str, metrics: list[dict], comparison: Optional[dict], condition: str,
          thresholds: dict, observed: dict, evidence: list[dict], investigation: list[str],
          source_type: str) -> CreditObservation:
    return CreditObservation(
        observation_id=f"OBS-{f.case_id}-{code}",
        case_id=f.case_id,
        category=category,
        title=title,
        severity=severity.value,
        status=ObservationStatus.NEW.value,
        summary=summary,
        detailed_explanation=explanation,
        metrics=metrics,
        period_comparison=comparison,
        trigger={"rule_id": code, "condition": condition, "thresholds": thresholds, "observed": observed},
        evidence_references=evidence,
        recommended_investigation=investigation,
        source_type=source_type,
        generated_by=GENERATED_BY,
        created_at=f.created_at,
    )


# ─── Detectors ───────────────────────────────────────────────────────────────

def detect_working_capital_deterioration(f: _Facts) -> Optional[CreditObservation]:
    """Receivables growing materially faster than revenue."""
    c = f.cfg("working_capital_deterioration")
    rev0, rev1 = f.line(f.prior, "revenue_cr"), f.line(f.latest, "revenue_cr")
    rec0, rec1 = f.line(f.prior, "trade_receivables_cr"), f.line(f.latest, "trade_receivables_cr")
    rev_g, rec_g = _pct_change(rev0, rev1), _pct_change(rec0, rec1)
    if rev_g is None or rec_g is None or rec_g <= 0:
        return None
    gap = round(rec_g - rev_g, 1)
    min_gap, high_gap = c.get("min_growth_gap_pp", 20), c.get("high_growth_gap_pp", 30)
    if gap < min_gap:
        return None
    severity = Sev.HIGH if gap >= high_gap else Sev.MEDIUM
    return _make(
        f, "WC_DETERIORATION", category="Working Capital", title="Working Capital Deterioration",
        severity=severity,
        summary=f"Receivables grew {rec_g:.1f}% in {f.latest} against revenue growth of {rev_g:.1f}% "
                f"— a gap of {gap:.1f} percentage points.",
        explanation=f"Trade receivables rose from {_fmt_cr(rec0)} to {_fmt_cr(rec1)} while revenue rose from "
                    f"{_fmt_cr(rev0)} to {_fmt_cr(rev1)}. When receivables outgrow sales, a larger share of "
                    f"revenue is not being collected in cash, tying up working capital and raising questions "
                    f"about collection quality, client concentration or aggressive revenue recognition.",
        metrics=[_line_metric(f, f.prior, "trade_receivables_cr", "Trade receivables"),
                 _line_metric(f, f.latest, "trade_receivables_cr", "Trade receivables"),
                 _line_metric(f, f.prior, "revenue_cr", "Revenue"),
                 _line_metric(f, f.latest, "revenue_cr", "Revenue")],
        comparison=_comparison(f, [
            _change("trade_receivables_cr", "Trade receivables", rec0, rec1, rec_g, "pct"),
            _change("revenue_cr", "Revenue", rev0, rev1, rev_g, "pct")]),
        condition="receivables growth % - revenue growth % >= min_growth_gap_pp",
        thresholds={"min_growth_gap_pp": min_gap, "high_growth_gap_pp": high_gap},
        observed={"receivables_growth_pct": rec_g, "revenue_growth_pct": rev_g, "growth_gap_pp": gap},
        evidence=[_evidence("financial_summary", f"{f.prior}->{f.latest}.trade_receivables_cr",
                            "Trade receivables per audited balance sheet")]
                 + _exception_evidence(f, "ANAL_RECEIVABLE_SPIKE"),
        investigation=["Obtain the debtor ageing schedule and identify balances over 90 / 180 days.",
                       "Review the top-10 debtors, their share of receivables and any disputed or retention amounts.",
                       "Check revenue recognition policy (milestone billing, unbilled revenue) for the latest year.",
                       "Compare collections in the bank statements against billed revenue."],
        source_type="financial_trend",
    )


def detect_earnings_cash_conversion(f: _Facts) -> Optional[CreditObservation]:
    """EBITDA holding up or rising while operating cash flow falls."""
    c = f.cfg("earnings_cash_conversion")
    e0, e1 = f.line(f.prior, "ebitda_cr"), f.line(f.latest, "ebitda_cr")
    o0, o1 = f.line(f.prior, "operating_cash_flow_cr"), f.line(f.latest, "operating_cash_flow_cr")
    if e1 is None or o1 is None or e1 <= 0:
        return None
    ebitda_g, ocf_g = _pct_change(e0, e1), _pct_change(o0, o1)
    conversion = round(o1 / e1 * 100, 1)
    min_decline = c.get("min_ocf_decline_pct", 20)
    floor, high_floor = c.get("min_ocf_to_ebitda_pct", 50), c.get("high_ocf_to_ebitda_pct", 25)
    diverging = ebitda_g is not None and ebitda_g >= 0 and ocf_g is not None and ocf_g <= -min_decline
    if not diverging and conversion >= floor:
        return None
    severity = Sev.HIGH if (o1 < 0 or conversion < high_floor) else Sev.MEDIUM
    trend = (f"EBITDA moved {ebitda_g:+.1f}% while operating cash flow moved {ocf_g:+.1f}%"
             if ebitda_g is not None and ocf_g is not None else "Operating cash flow is weak relative to EBITDA")
    prior_conv = round(o0 / e0 * 100, 1) if (o0 is not None and e0) else None
    return _make(
        f, "EARNINGS_CASH_CONVERSION", category="Cash Flow", title="Earnings-to-Cash Conversion Concern",
        severity=severity,
        summary=f"{trend} in {f.latest}; only {conversion:.1f}% of EBITDA converted to operating cash.",
        explanation=f"Operating cash flow was {_fmt_cr(o1)} against EBITDA of {_fmt_cr(e1)} "
                    f"(prior year: {_fmt_cr(o0)} against {_fmt_cr(e0)}). Reported profit that does not turn into "
                    f"cash usually means it is being absorbed by working capital (receivables, inventory, "
                    f"contract assets). Debt is serviced from cash, not from accounting profit.",
        metrics=[_line_metric(f, f.prior, "ebitda_cr", "EBITDA"), _line_metric(f, f.latest, "ebitda_cr", "EBITDA"),
                 _line_metric(f, f.prior, "operating_cash_flow_cr", "Operating cash flow"),
                 _line_metric(f, f.latest, "operating_cash_flow_cr", "Operating cash flow"),
                 _ratio_metric(f, f.latest, "ocf_to_debt")],
        comparison=_comparison(f, [
            _change("ebitda_cr", "EBITDA", e0, e1, ebitda_g, "pct"),
            _change("operating_cash_flow_cr", "Operating cash flow", o0, o1, ocf_g, "pct"),
            _change("ocf_to_ebitda_pct", "OCF / EBITDA", prior_conv, conversion,
                    round(conversion - prior_conv, 1) if prior_conv is not None else None, "pp")]),
        condition="(EBITDA growth >= 0 and OCF decline >= min_ocf_decline_pct) or OCF/EBITDA < min_ocf_to_ebitda_pct",
        thresholds={"min_ocf_decline_pct": min_decline, "min_ocf_to_ebitda_pct": floor,
                    "high_ocf_to_ebitda_pct": high_floor},
        observed={"ebitda_growth_pct": ebitda_g, "ocf_growth_pct": ocf_g, "ocf_to_ebitda_pct": conversion},
        evidence=[_evidence("financial_summary", f"{f.latest}.operating_cash_flow_cr", "Cash flow statement")]
                 + _exception_evidence(f, "ANAL_NEGATIVE_OCF"),
        investigation=["Reconcile EBITDA to operating cash flow and identify the working-capital lines absorbing cash.",
                       "Check for unbilled revenue / contract assets and the timing of milestone certifications.",
                       "Review whether any one-off items (advances, tax refunds) distort either year.",
                       "Assess how the shortfall was funded — short-term borrowing, creditor stretch or equity."],
        source_type="financial_trend",
    )


def detect_leverage_increase(f: _Facts) -> Optional[CreditObservation]:
    """Debt growing materially faster than EBITDA, or Debt/EBITDA stepping up."""
    c = f.cfg("leverage_increase")
    d0, d1 = f.line(f.prior, "total_debt_cr"), f.line(f.latest, "total_debt_cr")
    e0, e1 = f.line(f.prior, "ebitda_cr"), f.line(f.latest, "ebitda_cr")
    de0, de1 = f.ratio(f.prior, "debt_to_ebitda"), f.ratio(f.latest, "debt_to_ebitda")
    debt_g, ebitda_g = _pct_change(d0, d1), _pct_change(e0, e1)
    min_gap, min_step = c.get("min_growth_gap_pp", 15), c.get("min_debt_to_ebitda_increase", 0.5)
    max_de = f.policy.get("max_debt_to_ebitda")
    gap = round(debt_g - ebitda_g, 1) if (debt_g is not None and ebitda_g is not None) else None
    step = round(de1 - de0, 2) if (de0 is not None and de1 is not None) else None
    if not ((gap is not None and debt_g > 0 and gap >= min_gap) or (step is not None and step >= min_step)):
        return None
    above_policy = de1 is not None and max_de is not None and de1 > max_de
    severity = Sev.HIGH if (above_policy or (e1 is not None and e1 <= 0)) else Sev.MEDIUM
    growth_text = (f"Debt grew {debt_g:.1f}% against EBITDA growth of {ebitda_g:.1f}%"
                   if gap is not None else "Leverage increased")
    return _make(
        f, "LEVERAGE_INCREASE", category="Leverage", title="Increasing Leverage Risk", severity=severity,
        summary=f"{growth_text}; Debt/EBITDA moved from {_fmt_x(de0)} to {_fmt_x(de1)}"
                + (f", above the policy maximum of {_fmt_x(max_de)}." if above_policy else "."),
        explanation=f"Total debt rose from {_fmt_cr(d0)} to {_fmt_cr(d1)} while EBITDA moved from {_fmt_cr(e0)} to "
                    f"{_fmt_cr(e1)}. Borrowing that grows faster than the earnings available to repay it lengthens "
                    f"the payback period and reduces headroom for any further downturn.",
        metrics=[_line_metric(f, f.prior, "total_debt_cr", "Total debt"),
                 _line_metric(f, f.latest, "total_debt_cr", "Total debt"),
                 _ratio_metric(f, f.prior, "debt_to_ebitda"), _ratio_metric(f, f.latest, "debt_to_ebitda"),
                 _ratio_metric(f, f.latest, "debt_to_equity")],
        comparison=_comparison(f, [
            _change("total_debt_cr", "Total debt", d0, d1, debt_g, "pct"),
            _change("ebitda_cr", "EBITDA", e0, e1, ebitda_g, "pct"),
            _change("debt_to_ebitda", "Debt / EBITDA", de0, de1, step, "x")]),
        condition="debt growth % - EBITDA growth % >= min_growth_gap_pp, or Debt/EBITDA increase >= min_debt_to_ebitda_increase",
        thresholds={"min_growth_gap_pp": min_gap, "min_debt_to_ebitda_increase": min_step,
                    "policy_max_debt_to_ebitda": max_de},
        observed={"debt_growth_pct": debt_g, "ebitda_growth_pct": ebitda_g, "growth_gap_pp": gap,
                  "debt_to_ebitda": de1, "debt_to_ebitda_change": step},
        evidence=[_evidence("ratio", f"ratio_engine:{f.latest}.debt_to_ebitda", "Debt / EBITDA"),
                  _evidence("policy_threshold", "max_debt_to_ebitda", f"Policy maximum {_fmt_x(max_de)}")],
        investigation=["Obtain the debt schedule: new facilities, lenders, tenors and repayment profile.",
                       "Identify the use of incremental debt — capex, working capital or losses.",
                       "Check whether new borrowing was raised against assets already charged to other lenders.",
                       "Review the funding plan and projected Debt/EBITDA path over the facility tenor."],
        source_type="financial_trend",
    )


def detect_debt_servicing_pressure(f: _Facts) -> Optional[CreditObservation]:
    """DSCR / ICR below, or close to and falling towards, policy minimums."""
    c = f.cfg("debt_servicing_pressure")
    dscr0, dscr1 = f.ratio(f.prior, "dscr"), f.ratio(f.latest, "dscr")
    icr0, icr1 = f.ratio(f.prior, "interest_coverage_ratio"), f.ratio(f.latest, "interest_coverage_ratio")
    min_dscr, min_icr = f.policy.get("min_dscr"), f.policy.get("min_interest_coverage")
    band = 1 + c.get("warning_band_pct", 10) / 100
    if dscr1 is None and icr1 is None:
        return None
    dscr_breach = dscr1 is not None and min_dscr is not None and dscr1 < min_dscr
    icr_breach = icr1 is not None and min_icr is not None and icr1 < min_icr
    dscr_near = (dscr1 is not None and min_dscr is not None and dscr1 < min_dscr * band
                 and dscr0 is not None and dscr1 < dscr0)
    icr_near = (icr1 is not None and min_icr is not None and icr1 < min_icr * band
                and icr0 is not None and icr1 < icr0)
    if dscr_breach or icr_breach:
        severity = Sev.CRITICAL if (dscr1 is not None and dscr1 < 1.0) else Sev.HIGH
    elif dscr_near or icr_near:
        severity = Sev.MEDIUM
    else:
        return None
    breaches = [t for t, hit in (("DSCR", dscr_breach), ("ICR", icr_breach)) if hit]
    return _make(
        f, "DEBT_SERVICING_PRESSURE", category="Debt Servicing", title="Debt Servicing Pressure", severity=severity,
        summary=f"DSCR moved from {_fmt_x(dscr0)} to {_fmt_x(dscr1)} (policy minimum {_fmt_x(min_dscr)}); "
                f"ICR moved from {_fmt_x(icr0)} to {_fmt_x(icr1)} (policy minimum {_fmt_x(min_icr)}).",
        explanation=("Coverage is below policy (" + ", ".join(breaches) + "). " if breaches else
                     "Coverage is approaching the policy minimum and falling. ")
                    + "Cash accruals are covering scheduled interest and principal with a thinner margin, so a "
                      "modest fall in earnings or a rise in rates could leave debt service uncovered.",
        metrics=[_ratio_metric(f, f.prior, "dscr"), _ratio_metric(f, f.latest, "dscr"),
                 _ratio_metric(f, f.prior, "interest_coverage_ratio"),
                 _ratio_metric(f, f.latest, "interest_coverage_ratio"),
                 _ratio_metric(f, f.latest, "fixed_charge_coverage")],
        comparison=_comparison(f, [
            _change("dscr", "DSCR", dscr0, dscr1,
                    round(dscr1 - dscr0, 2) if None not in (dscr0, dscr1) else None, "x"),
            _change("interest_coverage_ratio", "ICR", icr0, icr1,
                    round(icr1 - icr0, 2) if None not in (icr0, icr1) else None, "x")]),
        condition="DSCR < min_dscr or ICR < min_interest_coverage (HIGH); within warning band and falling (MEDIUM)",
        thresholds={"min_dscr": min_dscr, "min_interest_coverage": min_icr,
                    "warning_band_pct": c.get("warning_band_pct", 10)},
        observed={"dscr": dscr1, "interest_coverage_ratio": icr1, "breaches": breaches},
        evidence=[_evidence("ratio", f"ratio_engine:{f.latest}.dscr",
                            "DSCR = (PAT + depreciation + finance cost) / (finance cost + principal)"),
                  _evidence("policy_threshold", "min_dscr", f"Policy minimum {_fmt_x(min_dscr)}")],
        investigation=["Prepare a month-wise repayment schedule for existing and proposed facilities.",
                       "Re-run DSCR on actual (not assumed) principal repayments for the next 3 years.",
                       "Stress DSCR for a 10% EBITDA decline and a 100 bps rate increase.",
                       "Consider a DSCR covenant, DSRA or cash-sweep as mitigants."],
        source_type="ratio_threshold",
    )


def detect_receivable_collection(f: _Facts) -> Optional[CreditObservation]:
    """Debtor days rising sharply or above policy."""
    c = f.cfg("receivable_collection")
    d0, d1 = f.ratio(f.prior, "debtor_days"), f.ratio(f.latest, "debtor_days")
    if d1 is None:
        return None
    min_inc, max_days = c.get("min_increase_days", 15), f.policy.get("max_debtor_days")
    # A zero prior value means receivables were not reported that year: no comparison, not a jump.
    inc = round(d1 - d0, 1) if (d0 is not None and d0 > 0) else None
    rising = inc is not None and inc >= min_inc
    above = max_days is not None and d1 > max_days
    if not rising and not above:
        return None
    severity = Sev.HIGH if (rising and above) else Sev.MEDIUM if rising else Sev.LOW
    return _make(
        f, "RECEIVABLE_COLLECTION", category="Working Capital", title="Receivable Collection Risk", severity=severity,
        summary=f"Debtor days moved from {_fmt_days(d0)} to {_fmt_days(d1)}"
                + (f" (+{inc:.1f} days)" if inc is not None else "")
                + (f", above the policy maximum of {max_days:.0f} days." if above else "."),
        explanation="The company is taking longer to collect from customers. Slower collection lengthens the "
                    "cash cycle, increases reliance on working-capital borrowing and can signal disputes, "
                    "weaker counterparties or stretched credit terms offered to win business.",
        metrics=[_ratio_metric(f, f.prior, "debtor_days"), _ratio_metric(f, f.latest, "debtor_days")],
        comparison=_comparison(f, [_change("debtor_days", "Debtor days", d0, d1, inc, "days")]),
        condition="debtor days increase >= min_increase_days or debtor days > policy max_debtor_days",
        thresholds={"min_increase_days": min_inc, "policy_max_debtor_days": max_days},
        observed={"debtor_days": d1, "increase_days": inc},
        evidence=[_evidence("ratio", f"ratio_engine:{f.latest}.debtor_days",
                            "Debtor days = trade receivables / revenue x 365")],
        investigation=["Obtain customer-wise ageing and compare contractual vs actual credit periods.",
                       "Identify government / municipal receivables and their payment history.",
                       "Check for disputed claims, retention money or arbitration amounts within receivables.",
                       "Set drawing-power rules that exclude receivables older than 90 days."],
        source_type="ratio_threshold",
    )


def detect_inventory_buildup(f: _Facts) -> Optional[CreditObservation]:
    """Inventory days rising significantly."""
    c = f.cfg("inventory_buildup")
    i0, i1 = f.ratio(f.prior, "inventory_days"), f.ratio(f.latest, "inventory_days")
    if i0 is None or i1 is None:
        return None
    inc = round(i1 - i0, 1)
    inc_pct = _pct_change(i0, i1)
    min_days, min_pct, high_days = (c.get("min_increase_days", 15), c.get("min_increase_pct", 25),
                                    c.get("high_increase_days", 30))
    if inc < min_days or inc_pct is None or inc_pct < min_pct:
        return None
    severity = Sev.HIGH if inc >= high_days else Sev.MEDIUM
    s0, s1 = f.line(f.prior, "inventory_cr"), f.line(f.latest, "inventory_cr")
    return _make(
        f, "INVENTORY_BUILDUP", category="Working Capital", title="Inventory Build-up Risk", severity=severity,
        summary=f"Inventory days rose from {_fmt_days(i0)} to {_fmt_days(i1)} (+{inc:.1f} days, +{inc_pct:.1f}%); "
                f"inventory moved from {_fmt_cr(s0)} to {_fmt_cr(s1)}.",
        explanation="Inventory is building faster than sales. This can reflect slow-moving or obsolete stock, "
                    "stalled project sites, or advance buying — all of which lock up cash and may need "
                    "write-downs later.",
        metrics=[_ratio_metric(f, f.prior, "inventory_days"), _ratio_metric(f, f.latest, "inventory_days"),
                 _line_metric(f, f.prior, "inventory_cr", "Inventory"),
                 _line_metric(f, f.latest, "inventory_cr", "Inventory")],
        comparison=_comparison(f, [_change("inventory_days", "Inventory days", i0, i1, inc, "days"),
                                   _change("inventory_cr", "Inventory", s0, s1, _pct_change(s0, s1), "pct")]),
        condition="inventory days increase >= min_increase_days and % increase >= min_increase_pct",
        thresholds={"min_increase_days": min_days, "min_increase_pct": min_pct, "high_increase_days": high_days},
        observed={"inventory_days": i1, "increase_days": inc, "increase_pct": inc_pct},
        evidence=[_evidence("ratio", f"ratio_engine:{f.latest}.inventory_days",
                            "Inventory days = inventory / revenue x 365")],
        investigation=["Obtain the stock statement with ageing and site-wise / item-wise split.",
                       "Identify slow-moving and non-moving items and any provisioning.",
                       "Reconcile stock with the latest stock audit or site visit report.",
                       "Check whether stalled projects explain the build-up and when they restart."],
        source_type="ratio_threshold",
    )


def detect_margin_compression(f: _Facts) -> Optional[CreditObservation]:
    """EBITDA margin falling materially."""
    c = f.cfg("margin_compression")
    m0, m1 = f.line(f.prior, "ebitda_margin_pct"), f.line(f.latest, "ebitda_margin_pct")
    if m0 is None or m1 is None:
        return None
    decline_bps = round((m0 - m1) * 100)
    min_bps, high_bps = c.get("min_decline_bps", 200), c.get("high_decline_bps", 400)
    floor = f.policy.get("min_ebitda_margin_pct")
    if decline_bps < min_bps:
        return None
    severity = Sev.HIGH if (decline_bps >= high_bps or (floor is not None and m1 < floor)) else Sev.MEDIUM
    return _make(
        f, "MARGIN_COMPRESSION", category="Profitability", title="Margin Compression", severity=severity,
        summary=f"EBITDA margin fell from {_fmt_pct(m0)} to {_fmt_pct(m1)} ({decline_bps} bps) in {f.latest}.",
        explanation="Costs are rising faster than revenue. In contract businesses this often points to fixed-price "
                    "orders without adequate escalation clauses, input-cost inflation or aggressive bidding to "
                    "win volume; sustained compression erodes cash accruals available for debt service.",
        metrics=[_metric("ebitda_margin_pct", "EBITDA margin", f.prior, m0, "pct",
                         f"financial_summary.periods.{f.prior}.ebitda_margin_pct"),
                 _metric("ebitda_margin_pct", "EBITDA margin", f.latest, m1, "pct",
                         f"financial_summary.periods.{f.latest}.ebitda_margin_pct"),
                 _line_metric(f, f.latest, "ebitda_cr", "EBITDA")],
        comparison=_comparison(f, [_change("ebitda_margin_pct", "EBITDA margin", m0, m1, -decline_bps, "bps")]),
        condition="EBITDA margin decline >= min_decline_bps",
        thresholds={"min_decline_bps": min_bps, "high_decline_bps": high_bps, "policy_min_ebitda_margin_pct": floor},
        observed={"ebitda_margin_pct": m1, "decline_bps": decline_bps},
        evidence=[_evidence("financial_summary", f"{f.latest}.ebitda_margin_pct", "EBITDA / revenue")]
                 + _exception_evidence(f, "ANAL_MARGIN_DECLINE"),
        investigation=["Split the margin decline into material, employee and other cost drivers.",
                       "Review the order book for fixed-price contracts and price-escalation clauses.",
                       "Compare bid margins on new orders with executed margins.",
                       "Ask management for the margin outlook and any cost pass-through mechanism."],
        source_type="financial_trend",
    )


_SEVERITY_FROM_EXCEPTION = {"critical": Sev.CRITICAL, "high": Sev.HIGH, "medium": Sev.MEDIUM, "low": Sev.LOW}


def detect_data_reliability(f: _Facts) -> Optional[CreditObservation]:
    """Financial data that conflicts across sources (validation engine findings)."""
    c = f.cfg("data_reliability")
    prefixes = tuple(c.get("code_prefixes") or ("XSRC_", "STRUCT_", "DOC_"))
    excluded = set(c.get("exclude_codes") or ())
    hits = [e for e in f.exceptions
            if str(e.get("code", "")).startswith(prefixes) and e.get("code") not in excluded]
    if not hits:
        return None
    severity = min((_SEVERITY_FROM_EXCEPTION.get(str(e.get("severity", "")).lower(), Sev.MEDIUM) for e in hits),
                   key=lambda s: SEVERITY_ORDER[s.value])
    first = hits[0]
    return _make(
        f, "DATA_RELIABILITY", category="Data Quality", title="Data Reliability Concern", severity=severity,
        summary=f"{len(hits)} data consistency exception(s): {first.get('description', '')}",
        explanation="Figures for the same item disagree across sources (financial statements, GST returns, "
                    "public-record exposure or exchange filings). Until reconciled, the reported financials "
                    "on which ratios and the recommendation rest cannot be fully relied upon.",
        metrics=[_metric(e.get("metric") or e.get("code"), e.get("code"), f.latest,
                         e.get("observed"), "text", f"validation_engine:{e.get('code')}") for e in hits],
        comparison=None,
        condition="validation exception with a cross-source / structural / document code",
        thresholds={"code_prefixes": list(prefixes)},
        observed={"exceptions": [{"code": e.get("code"), "expected": e.get("expected"),
                                  "observed": e.get("observed"), "severity": e.get("severity")} for e in hits]},
        evidence=[_evidence("validation_exception", e.get("code"), e.get("description", "")) for e in hits],
        investigation=["Obtain a reconciliation between the conflicting sources signed by the CFO / auditor.",
                       "For GST gaps: reconcile GSTR-1 / 3B turnover with audited revenue (unbilled revenue, "
                       "exempt supplies, timing).",
                       "For exposure gaps: obtain lender-wise balance confirmations.",
                       "Hold the sanction note until material differences are explained."],
        source_type="validation",
    )


def detect_sector_underperformance(f: _Facts) -> Optional[CreditObservation]:
    """Material underperformance against sector peers."""
    c = f.cfg("sector_underperformance")
    rows = f.benchmarks.get("benchmarks") or []
    worse = [r for r in rows if r.get("status") == "worse_than_peer"]
    high = [r for r in worse if r.get("severity") == "high"]
    medium = [r for r in worse if r.get("severity") == "medium"]
    min_high, min_medium = c.get("min_high_metrics", 1), c.get("min_medium_metrics", 3)
    if len(high) < min_high and len(medium) < min_medium:
        return None
    severity = Sev.HIGH if len(high) >= c.get("high_severity_min_high_metrics", 2) else Sev.MEDIUM
    period = f.benchmarks.get("period") or f.latest
    sector = f.benchmarks.get("sector", "")
    labels = [RATIO_LABELS.get(r.get("metric"), r.get("metric")) for r in high + medium]
    return _make(
        f, "SECTOR_UNDERPERFORMANCE", category="Peer Benchmarking", title="Sector Underperformance", severity=severity,
        summary=f"{len(worse)} metric(s) worse than {sector} peers in {period}; {len(high)} in the weakest peer band "
                f"({', '.join(labels[:4])}{'...' if len(labels) > 4 else ''}).",
        explanation="Compared with the sector peer set (P25 / median / P75), the borrower sits in the weaker part "
                    "of the distribution on several metrics. Underperformance against peers facing the same "
                    "market conditions points to company-specific issues rather than a sector cycle.",
        metrics=[{**_metric(r.get("metric"), RATIO_LABELS.get(r.get("metric"), r.get("metric")), period,
                            r.get("borrower"), "fraction" if r.get("metric") in _FRACTION_RATIOS
                            else "days" if r.get("metric") in _DAY_RATIOS else "x",
                            f"benchmark_engine:{period}.{r.get('metric')}"),
                  "peer_p25": r.get("peer_p25"), "peer_median": r.get("peer_median"), "peer_p75": r.get("peer_p75"),
                  "benchmark_severity": r.get("severity")} for r in high + medium],
        comparison=None,
        condition="metrics in the weakest peer band >= min_high_metrics, or below peer median >= min_medium_metrics",
        thresholds={"min_high_metrics": min_high, "min_medium_metrics": min_medium,
                    "high_severity_min_high_metrics": c.get("high_severity_min_high_metrics", 2)},
        observed={"worse_than_peer": len(worse), "weakest_band": len(high), "below_median": len(medium)},
        evidence=[_evidence("benchmark", f"benchmark_engine:{period}.{r.get('metric')}",
                            f"Borrower {r.get('borrower')} vs peer median {r.get('peer_median')}") for r in high],
        investigation=["Ask management to explain the gap to peers on the weakest-band metrics.",
                       "Check whether peers use different contract mix or business models.",
                       "Review the peer set used for benchmarking for relevance to this borrower."],
        source_type="benchmark",
    )


# (ratio, policy threshold key, "min" | "max", display scale for the threshold)
_POLICY_CHECKS = [
    ("dscr", "min_dscr", "min", 1),
    ("interest_coverage_ratio", "min_interest_coverage", "min", 1),
    ("current_ratio", "min_current_ratio", "min", 1),
    ("debt_to_equity", "max_debt_to_equity", "max", 1),
    ("debt_to_ebitda", "max_debt_to_ebitda", "max", 1),
    ("tol_tnw", "max_tol_tnw", "max", 1),
    ("return_on_equity", "min_roe_pct", "min", 100),
    ("debtor_days", "max_debtor_days", "max", 1),
]


def detect_policy_deviation(f: _Facts) -> Optional[CreditObservation]:
    """Failed hard rules and breaches of the bank's policy thresholds."""
    c = f.cfg("policy_deviation")
    failed = [d for d in f.tier1 if str(d.get("result", "")).lower() == "fail"]
    unverified = [d for d in f.tier1 if str(d.get("result", "")).lower() == "not_verified"]
    breaches = []
    for ratio, key, kind, scale in _POLICY_CHECKS:
        value, limit = f.ratio(f.latest, ratio), _num(f.policy.get(key))
        if value is None or limit is None:
            continue
        shown = round(value * scale, 2)
        if (kind == "min" and shown < limit) or (kind == "max" and shown > limit):
            breaches.append({"metric": ratio, "label": RATIO_LABELS.get(ratio, ratio), "value": shown,
                             "limit": limit, "limit_type": kind, "threshold_key": key})
    margin, floor = f.line(f.latest, "ebitda_margin_pct"), _num(f.policy.get("min_ebitda_margin_pct"))
    if margin is not None and floor is not None and margin < floor:
        breaches.append({"metric": "ebitda_margin_pct", "label": "EBITDA margin", "value": margin,
                         "limit": floor, "limit_type": "min", "threshold_key": "min_ebitda_margin_pct"})
    if not failed and not breaches and not unverified:
        return None
    if failed:
        severity = Sev.CRITICAL
    elif len(breaches) >= c.get("high_severity_min_breaches", 3):
        severity = Sev.HIGH
    else:
        severity = Sev.MEDIUM
    parts = [f"{len(failed)} hard rule(s) failed"] if failed else []
    if unverified:
        parts.append(f"{len(unverified)} hard rule(s) not verified ("
                     + ", ".join(d.get("rule") or "" for d in unverified) + ")")
    if breaches:
        parts.append(f"{len(breaches)} policy threshold(s) breached: "
                     + "; ".join(f"{b['label']} {b['value']} vs {b['limit_type']} {b['limit']}" for b in breaches))
    return _make(
        f, "POLICY_DEVIATION", category="Policy", title="Policy Exception / Deviation", severity=severity,
        summary=" — ".join(parts) + ".",
        explanation="The proposal falls outside the bank's credit policy on the items listed. Approving it "
                    "requires a recorded deviation with justification, compensating mitigants and sanction at "
                    "the authority level empowered to approve deviations.",
        metrics=[_metric(b["metric"], b["label"], f.latest, b["value"],
                         "pct" if b["metric"] in ("return_on_equity", "ebitda_margin_pct") else
                         "days" if b["metric"] == "debtor_days" else "x",
                         f"policy_thresholds.{b['threshold_key']}") for b in breaches],
        comparison=None,
        condition="any tier-1 hard rule = fail (CRITICAL) or not verified, or latest ratio outside policy_thresholds",
        thresholds={b["threshold_key"]: b["limit"] for b in breaches},
        observed={"failed_hard_rules": [d.get("rule") for d in failed],
                  "unverified_hard_rules": [d.get("rule") for d in unverified], "breaches": breaches},
        evidence=[_evidence("policy_rule", d.get("rule"), d.get("details", "")) for d in failed + unverified]
                 + [_evidence("policy_threshold", b["threshold_key"],
                              f"{b['label']}: {b['value']} vs {b['limit_type']} {b['limit']}") for b in breaches],
        investigation=["Prepare a deviation note for each breached parameter with business justification.",
                       "Identify compensating mitigants (additional security, guarantees, covenants, pricing).",
                       "Confirm the sanctioning authority empowered to approve these deviations.",
                       "Define covenants and a cure period for the breached ratios."],
        source_type="policy",
    )


def detect_liquidity_stress(f: _Facts) -> Optional[CreditObservation]:
    """Current ratio below policy or falling sharply."""
    c = f.cfg("liquidity_stress")
    cr0, cr1 = f.ratio(f.prior, "current_ratio"), f.ratio(f.latest, "current_ratio")
    if cr1 is None:
        return None
    floor = f.policy.get("min_current_ratio")
    drop = round(cr0 - cr1, 2) if cr0 is not None else None
    below = floor is not None and cr1 < floor
    falling = drop is not None and drop >= c.get("min_decline", 0.20)
    if not below and not falling:
        return None
    severity = Sev.HIGH if cr1 < c.get("high_below", 1.0) else Sev.MEDIUM if below else Sev.LOW
    ca0, ca1 = f.line(f.prior, "current_assets_cr"), f.line(f.latest, "current_assets_cr")
    cl0, cl1 = f.line(f.prior, "current_liabilities_cr"), f.line(f.latest, "current_liabilities_cr")
    return _make(
        f, "LIQUIDITY_STRESS", category="Liquidity", title="Liquidity Stress", severity=severity,
        summary=f"Current ratio {'fell' if (drop or 0) > 0 else 'moved'} from {_fmt_x(cr0)} to {_fmt_x(cr1)}"
                + (f", below the policy minimum of {_fmt_x(floor)}." if below else "."),
        explanation=f"Current liabilities rose from {_fmt_cr(cl0)} to {_fmt_cr(cl1)} against current assets of "
                    f"{_fmt_cr(ca0)} to {_fmt_cr(ca1)}. A thinner liquidity cushion means short-term "
                    f"obligations depend more on rolling over borrowings and collecting receivables on time.",
        metrics=[_ratio_metric(f, f.prior, "current_ratio"), _ratio_metric(f, f.latest, "current_ratio"),
                 _line_metric(f, f.latest, "current_assets_cr", "Current assets"),
                 _line_metric(f, f.latest, "current_liabilities_cr", "Current liabilities")],
        comparison=_comparison(f, [_change("current_ratio", "Current ratio", cr0, cr1,
                                           -drop if drop is not None else None, "x")]),
        condition="current ratio < policy min_current_ratio, or decline >= min_decline",
        thresholds={"policy_min_current_ratio": floor, "min_decline": c.get("min_decline", 0.20),
                    "high_below": c.get("high_below", 1.0)},
        observed={"current_ratio": cr1, "decline": drop},
        evidence=[_evidence("ratio", f"ratio_engine:{f.latest}.current_ratio", "Current assets / current liabilities")],
        investigation=["Review the maturity profile of short-term debt and rollover arrangements.",
                       "Check use of short-term funds for long-term purposes (capex).",
                       "Assess drawing power against current assets net of aged receivables.",
                       "Confirm undrawn committed lines and cash available."],
        source_type="ratio_threshold",
    )


def detect_financial_distress(f: _Facts) -> Optional[CreditObservation]:
    """Altman Z-score in the distress zone, or slipping out of the safe zone."""
    c = f.cfg("financial_distress")
    z0, z1 = f.ratio(f.prior, "altman_z_score"), f.ratio(f.latest, "altman_z_score")
    if z1 is None:
        return None
    distress, safe, min_drop = c.get("distress_below", 1.81), c.get("safe_above", 2.99), c.get("min_decline", 0.30)
    drop = round(z0 - z1, 2) if z0 is not None else None
    if z1 < distress:
        severity, zone = Sev.HIGH, "distress"
    elif z1 <= safe and drop is not None and (z0 > safe or drop >= min_drop):
        severity, zone = Sev.LOW, "grey"
    else:
        return None
    return _make(
        f, "FINANCIAL_DISTRESS", category="Solvency", title="Financial Distress Signal", severity=severity,
        summary=f"Altman Z-score moved from {z0 if z0 is not None else 'n/a'} to {z1} — now in the {zone} zone "
                f"(distress < {distress}, safe > {safe}).",
        explanation="The Altman Z-score combines liquidity, retained earnings, operating returns, leverage and "
                    "asset turnover. A move out of the safe zone is an early-warning indicator rather than a "
                    "prediction of default; it should be read with the cash-flow and coverage observations.",
        metrics=[_ratio_metric(f, f.prior, "altman_z_score"), _ratio_metric(f, f.latest, "altman_z_score")],
        comparison=_comparison(f, [_change("altman_z_score", "Altman Z-score", z0, z1,
                                           -drop if drop is not None else None, "score")]),
        condition="Z < distress_below (HIGH); Z in grey zone after leaving safe zone or falling >= min_decline (LOW)",
        thresholds={"distress_below": distress, "safe_above": safe, "min_decline": min_drop},
        observed={"altman_z_score": z1, "decline": drop, "zone": zone},
        evidence=[_evidence("ratio", f"ratio_engine:{f.latest}.altman_z_score", "Altman Z-score (manufacturing model)")],
        investigation=["Read together with cash-flow and coverage observations before drawing conclusions.",
                       "Track the Z-score on quarterly results as an early-warning indicator."],
        source_type="ratio_threshold",
    )


DETECTORS: list[tuple[str, Callable[[_Facts], Optional[CreditObservation]]]] = [
    ("working_capital_deterioration", detect_working_capital_deterioration),
    ("earnings_cash_conversion", detect_earnings_cash_conversion),
    ("leverage_increase", detect_leverage_increase),
    ("debt_servicing_pressure", detect_debt_servicing_pressure),
    ("receivable_collection", detect_receivable_collection),
    ("inventory_buildup", detect_inventory_buildup),
    ("margin_compression", detect_margin_compression),
    ("data_reliability", detect_data_reliability),
    ("sector_underperformance", detect_sector_underperformance),
    ("policy_deviation", detect_policy_deviation),
    ("liquidity_stress", detect_liquidity_stress),
    ("financial_distress", detect_financial_distress),
]


# ─── Entry points ────────────────────────────────────────────────────────────

def detect_observations(fact_pack: dict, case_id: str, created_at: str | None = None,
                        settings: dict | None = None) -> list[dict]:
    """All observations for a case, most severe first. Deterministic for a given fact pack.

    A detector that fails is logged and skipped so one bad input never blocks the rest.
    """
    if not fact_pack:
        return []
    settings = observation_config() if settings is None else settings
    facts = _Facts(fact_pack, case_id, created_at or datetime.now().isoformat(), settings)
    found: list[CreditObservation] = []
    for name, detector in DETECTORS:
        if not (settings.get(name) or {}).get("enabled", True):
            continue
        try:
            obs = detector(facts)
        except Exception as e:  # defensive: incomplete fact packs from older runs
            log.warning("Observation detector %s failed for %s: %s", name, case_id, e)
            continue
        if obs:
            found.append(obs)
    order = {name: i for i, (name, _) in enumerate(DETECTORS)}
    found.sort(key=lambda o: (SEVERITY_ORDER[o.severity], order.get(o.trigger["rule_id"], 0)))
    return [o.to_dict() for o in found]


def summarize(observations: list[dict]) -> dict:
    """Counts by severity, status and category for the UI and other consumers."""
    by_severity = {s.value: 0 for s in Sev}
    by_status = {s.value: 0 for s in ObservationStatus}
    by_category: dict[str, int] = {}
    for o in observations:
        by_severity[o["severity"]] = by_severity.get(o["severity"], 0) + 1
        by_status[o["status"]] = by_status.get(o["status"], 0) + 1
        by_category[o["category"]] = by_category.get(o["category"], 0) + 1
    return {"total": len(observations), "by_severity": by_severity, "by_status": by_status,
            "by_category": by_category, "engine_version": ENGINE_VERSION}
