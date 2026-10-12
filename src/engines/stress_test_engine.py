"""
Stress Testing — deterministic.

Applies adverse scenarios (config/rules.yaml → stress_testing) to the latest
audited FinancialStatement and recomputes the credit metrics with the existing
ratio engine (``compute_all_ratios``), so a stressed DSCR, ICR, Debt/EBITDA,
OCF/Debt or current ratio is calculated exactly as the real one is. The base
case is the unmodified statement and is checked against the fact pack's ratios.

How a scenario changes the statement (one-year, no forecasting):

  revenue'        = revenue × (1 + revenue_change)
  EBITDA'         = revenue' × (EBITDA margin + margin_change)
  EBIT'           = EBITDA' − depreciation            (depreciation unchanged)
  receivables'    = revenue' × (debtor days + Δdays) / 365
  inventory'      = revenue' × (inventory days + Δdays) / 365
  payables'       = revenue' × payable days / 365      (supplier terms unchanged)
  extra WC        = Δreceivables + Δinventory − Δpayables, funded by short-term debt
  interest'       = (debt + extra WC) × (current rate + rate shock)
  tax'            = PBT' × effective tax rate (0 when PBT' ≤ 0)
  OCF'            = OCF + ΔEBITDA − Δtax − extra WC
  current assets' = current assets + Δreceivables + Δinventory
  current liab.'  = current liabilities + Δpayables + extra WC

Equity and long-term debt are held at the latest balance. No recommendation is made.
"""

from __future__ import annotations

import copy
import logging
from datetime import datetime
from typing import Optional

from src.engines.ratio_engine import as_pct, compute_all_ratios

log = logging.getLogger(__name__)

ENGINE_VERSION = "stress_v2"   # v2: EBIT reported per scenario
GENERATED_BY = f"stress_test_engine/{ENGINE_VERSION}"

_DEFAULT_SCENARIOS = {
    "base": {"label": "Base case", "revenue_change_pct": 0, "margin_change_bps": 0, "debtor_days_change": 0,
             "inventory_days_change": 0, "rate_shock_bps": 0},
    "downside": {"label": "Downside", "revenue_change_pct": -5, "margin_change_bps": -100, "debtor_days_change": 10,
                 "inventory_days_change": 5, "rate_shock_bps": 50},
    "severe": {"label": "Severe downside", "revenue_change_pct": -15, "margin_change_bps": -300,
               "debtor_days_change": 25, "inventory_days_change": 15, "rate_shock_bps": 150},
}

# (key, label, unit) of the metrics reported for every scenario.
METRICS = [
    ("revenue_cr", "Revenue", "cr"),
    ("ebitda_cr", "EBITDA", "cr"),
    ("ebitda_margin_pct", "EBITDA margin", "pct"),
    ("finance_cost_cr", "Interest (finance cost)", "cr"),
    ("operating_cash_flow_cr", "Operating cash flow", "cr"),
    ("total_debt_cr", "Total debt", "cr"),
    ("additional_borrowing_cr", "Extra working capital borrowed", "cr"),
    ("dscr", "DSCR", "x"),
    ("interest_coverage_ratio", "Interest coverage (ICR)", "x"),
    ("debt_to_ebitda", "Debt / EBITDA", "x"),
    ("ocf_to_debt_pct", "OCF / Debt", "pct"),
    ("current_ratio", "Current ratio", "x"),
    ("debtor_days", "Debtor days", "days"),
    ("inventory_days", "Inventory days", "days"),
    ("debt_to_equity", "Debt / Equity", "x"),
]

# (metric, policy threshold key, "min" | "max", label)
POLICY_CHECKS = [
    ("dscr", "min_dscr", "min", "DSCR"),
    ("interest_coverage_ratio", "min_interest_coverage", "min", "Interest coverage"),
    ("debt_to_ebitda", "max_debt_to_ebitda", "max", "Debt / EBITDA"),
    ("current_ratio", "min_current_ratio", "min", "Current ratio"),
    ("debt_to_equity", "max_debt_to_equity", "max", "Debt / Equity"),
    ("ebitda_margin_pct", "min_ebitda_margin_pct", "min", "EBITDA margin (%)"),
    ("debtor_days", "max_debtor_days", "max", "Debtor days"),
]


def stress_config() -> dict:
    from src.core.config_manager import config
    return config.get("rules", "stress_testing", default={}) or {}


def _num(v) -> Optional[float]:
    if isinstance(v, bool) or v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _r(v, digits=2):
    return None if v is None else round(v, digits)


def _cr(v) -> str:
    if v is None:
        return "n/a"
    return f"-₹{abs(v):,.2f} Cr" if v < 0 else f"₹{v:,.2f} Cr"


def _x(v) -> str:
    return "n/a" if v is None else f"{v:.2f}x"


def _stress_statement(fs, shock: dict, tax_default: float):
    """A copy of ``fs`` with the scenario applied to its line items, plus the working figures."""
    g = fs.get
    rev, ebitda, dep = g("revenue_operating"), g("ebitda"), g("depreciation")
    fc, debt, ocf = g("finance_cost"), g("total_debt"), g("operating_cash_flow", 0)
    rec, inv, pay = g("trade_receivables"), g("inventory"), g("trade_payables")
    pbt, tax = g("pbt"), g("tax_expense")
    if rev <= 0:
        raise ValueError("latest revenue is not positive")

    tax_rate = tax / pbt if pbt > 0 and tax >= 0 else tax_default / 100
    rate = fc / debt if debt > 0 else 0.0
    if not any(shock[k] for k in ("revenue_change_pct", "margin_change_bps", "debtor_days_change",
                                  "inventory_days_change", "rate_shock_bps")):
        # No shock: the statement exactly as audited, so the base case is the ratio engine's own result.
        return copy.deepcopy(fs), {"interest_rate_pct": _r(rate * 100), "stressed_interest_rate_pct": _r(rate * 100),
                                   "tax_rate_pct": _r(tax_rate * 100, 1), "extra_working_capital_cr": 0.0,
                                   "additional_borrowing_cr": 0.0}
    rev2 = rev * (1 + shock["revenue_change_pct"] / 100)
    margin2 = ebitda / rev + shock["margin_change_bps"] / 10000
    ebitda2 = rev2 * margin2
    ebit2 = ebitda2 - dep
    debtor_days, inventory_days, payable_days = rec / rev * 365, inv / rev * 365, pay / rev * 365
    rec2 = rev2 * (debtor_days + shock["debtor_days_change"]) / 365
    inv2 = rev2 * (inventory_days + shock["inventory_days_change"]) / 365
    pay2 = rev2 * payable_days / 365
    extra_wc = (rec2 - rec) + (inv2 - inv) - (pay2 - pay)
    borrowing = max(extra_wc, 0.0)
    rate2 = rate + shock["rate_shock_bps"] / 10000
    fc2 = (debt + borrowing) * rate2 if debt > 0 else fc
    pbt2 = ebit2 - fc2
    tax2 = max(pbt2, 0.0) * tax_rate
    pat2 = pbt2 - tax2
    ocf2 = ocf + (ebitda2 - ebitda) - (tax2 - tax) - extra_wc

    stressed = copy.deepcopy(fs)
    li = stressed.line_items
    li.update({
        "revenue_operating": rev2, "ebitda": ebitda2, "ebit": ebit2, "finance_cost": fc2, "pbt": pbt2,
        "tax_expense": tax2, "pat": pat2, "trade_receivables": rec2, "inventory": inv2, "trade_payables": pay2,
        "short_term_debt": g("short_term_debt") + borrowing, "total_debt": debt + borrowing,
        "current_assets": g("current_assets") + (rec2 - rec) + (inv2 - inv),
        "current_liabilities": g("current_liabilities") + (pay2 - pay) + borrowing,
        "total_assets": g("total_assets") + (rec2 - rec) + (inv2 - inv),
        "operating_cash_flow": ocf2,
    })
    working = {"interest_rate_pct": _r(rate * 100), "stressed_interest_rate_pct": _r(rate2 * 100),
               "tax_rate_pct": _r(tax_rate * 100, 1), "extra_working_capital_cr": _r(extra_wc),
               "additional_borrowing_cr": _r(borrowing)}
    return stressed, working


def _metrics(fs, working: dict) -> dict:
    ratios = {r.ratio_name: r.value for r in compute_all_ratios(fs)}
    g = fs.get
    ocf_debt = ratios.get("ocf_to_debt")
    return {
        "revenue_cr": _r(g("revenue_operating")),
        "ebitda_cr": _r(g("ebitda")),
        "ebitda_margin_pct": as_pct(ratios.get("ebitda_margin")),
        "ebit_cr": _r(g("ebit")),
        "finance_cost_cr": _r(g("finance_cost")),
        "operating_cash_flow_cr": _r(g("operating_cash_flow", 0)),
        "total_debt_cr": _r(g("total_debt")),
        "additional_borrowing_cr": working.get("additional_borrowing_cr", 0.0),
        "dscr": ratios.get("dscr"),
        "interest_coverage_ratio": ratios.get("interest_coverage_ratio"),
        "debt_to_ebitda": ratios.get("debt_to_ebitda"),
        "ocf_to_debt_pct": as_pct(ocf_debt),
        "current_ratio": ratios.get("current_ratio"),
        "debtor_days": ratios.get("debtor_days"),
        "inventory_days": ratios.get("inventory_days"),
        "debt_to_equity": ratios.get("debt_to_equity"),
    }


def _breaches(metrics: dict, policy: dict) -> list[dict]:
    found = []
    for metric, key, kind, label in POLICY_CHECKS:
        value, limit = metrics.get(metric), _num(policy.get(key))
        if value is None or limit is None:
            continue
        # A negative Debt/EBITDA means EBITDA is negative — always outside policy.
        breached = (value < limit) if kind == "min" else (value > limit or (metric == "debt_to_ebitda" and value < 0))
        if breached:
            found.append({"metric": metric, "label": label, "value": value, "limit": limit, "limit_type": kind,
                          "threshold_key": key})
    return found


def _severity(m: dict, breaches: list) -> str:
    if (m["dscr"] is not None and m["dscr"] < 1.0) or (m["interest_coverage_ratio"] is not None
                                                        and m["interest_coverage_ratio"] < 1.0):
        return "CRITICAL"
    if len(breaches) >= 3 or (m["operating_cash_flow_cr"] is not None and m["operating_cash_flow_cr"] < 0):
        return "HIGH"
    return "MEDIUM" if breaches else "LOW"


def _observations(name: str, m: dict, base: dict, breaches: list, base_breaches: list, policy: dict) -> list[str]:
    """Plain statements of what changed versus the base case; every figure is from the metrics."""
    if name == "base":
        notes = [f"Latest audited position: DSCR {_x(m['dscr'])}, interest coverage {_x(m['interest_coverage_ratio'])}, "
                 f"Debt/EBITDA {_x(m['debt_to_ebitda'])}, operating cash flow {_cr(m['operating_cash_flow_cr'])}."]
        if breaches:
            notes.append(f"{len(breaches)} policy threshold(s) already breached before any stress: "
                         + ", ".join(b["label"] for b in breaches) + ".")
        return notes
    notes = [f"EBITDA falls from {_cr(base['ebitda_cr'])} to {_cr(m['ebitda_cr'])} (margin {base['ebitda_margin_pct']}% → "
             f"{m['ebitda_margin_pct']}%)."]
    if m["dscr"] is not None:
        floor = _num(policy.get("min_dscr"))
        notes.append(f"DSCR moves from {_x(base['dscr'])} to {_x(m['dscr'])}"
                     + (" — cash accruals no longer cover debt service." if m["dscr"] < 1.0 else
                        f" against a {_x(floor)} minimum." if floor else "."))
    if m["interest_coverage_ratio"] is not None and m["interest_coverage_ratio"] < 1.0:
        notes.append(f"Interest coverage falls to {_x(m['interest_coverage_ratio'])}: operating profit does not cover "
                     f"interest of {_cr(m['finance_cost_cr'])}.")
    if m["operating_cash_flow_cr"] is not None and m["operating_cash_flow_cr"] < 0 <= (base["operating_cash_flow_cr"] or 0):
        notes.append(f"Operating cash flow turns negative ({_cr(m['operating_cash_flow_cr'])}) as working capital absorbs cash.")
    if m["additional_borrowing_cr"]:
        notes.append(f"Slower collections and stock need {_cr(m['additional_borrowing_cr'])} of extra working capital, "
                     f"taking debt to {_cr(m['total_debt_cr'])} and Debt/EBITDA to {_x(m['debt_to_ebitda'])}.")
    new = [b["label"] for b in breaches if b["metric"] not in {x["metric"] for x in base_breaches}]
    if new:
        notes.append("Newly breached versus the base case: " + ", ".join(new) + ".")
    return notes


def run_stress_tests(fs_latest, fact_pack: dict, case_id: str, created_at: str | None = None,
                     settings: dict | None = None) -> dict:
    """Base, downside and severe scenarios for the latest period."""
    settings = stress_config() if settings is None else settings
    if fs_latest is None:
        return {"available": False, "reason": "The latest financial statement is not available."}
    scenarios = settings.get("scenarios") or _DEFAULT_SCENARIOS
    tax_default = _num(settings.get("default_tax_rate_pct")) or 25.0
    policy = (fact_pack or {}).get("policy_thresholds") or {}

    results, base_metrics, base_breaches = [], None, []
    for name in ("base", "downside", "severe"):
        shock = {**_DEFAULT_SCENARIOS[name], **(scenarios.get(name) or {})}
        stressed, working = _stress_statement(fs_latest, shock, tax_default)
        m = _metrics(stressed, working)
        breaches = _breaches(m, policy)
        if name == "base":
            base_metrics, base_breaches = m, breaches
        results.append({
            "scenario": name,
            "label": shock.get("label", name.title()),
            "assumptions": {k: shock[k] for k in ("revenue_change_pct", "margin_change_bps", "debtor_days_change",
                                                  "inventory_days_change", "rate_shock_bps")},
            "working": working,
            "stressed_metrics": m,
            "change_vs_base": {k: (_r(m[k] - base_metrics[k]) if (m.get(k) is not None and base_metrics.get(k) is not None)
                                   else None) for k, _, _ in METRICS},
            "policy_breaches": breaches,
            "new_breaches": [b["metric"] for b in breaches if b["metric"] not in {x["metric"] for x in base_breaches}],
            "severity": _severity(m, breaches),
            "key_observations": _observations(name, m, base_metrics, breaches, base_breaches, policy),
        })

    # The base case must reproduce the ratio engine's figures in the fact pack.
    period = fs_latest.period
    recorded = ((fact_pack or {}).get("ratio_analysis") or {}).get(period) or {}
    mismatches = [k for k in ("dscr", "interest_coverage_ratio", "debt_to_ebitda", "current_ratio")
                  if isinstance(recorded.get(k), dict) and recorded[k].get("value") != base_metrics.get(k)]
    return {
        "available": True,
        "case_id": case_id,
        "period": period,
        "scenarios": results,
        "metrics": [{"metric": k, "label": label, "unit": unit} for k, label, unit in METRICS],
        "policy_checks": [{"metric": m, "threshold_key": key, "limit": _num(policy.get(key)), "limit_type": kind,
                           "label": label} for m, key, kind, label in POLICY_CHECKS],
        "base_reconciles": not mismatches,
        "reconciliation_mismatches": mismatches,
        "generated_by": GENERATED_BY,
        "created_at": created_at or datetime.now().isoformat(timespec="seconds"),
    }
