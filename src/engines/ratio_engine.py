"""
Deterministic Ratio Engine
Pure mathematical functions — same input always produces same output.
No LLM, no randomness, no external calls.
"""

from typing import Optional
from src.models.canonical_model import FinancialStatement, RatioResult


# ─── Rounding & Safety Policy ────────────────────────────────────────────────

DECIMAL_PLACES = 2
# Ratios that are fractions of a whole (margins, returns, OCF / debt). They are kept to 4 decimals so a
# value shown as a percentage to one decimal is exact (0.1288 → 12.9%, not 0.13 → 13.0%). Multiples (x)
# and day counts keep DECIMAL_PLACES. Every layer that shows a percentage converts with as_pct().
FRACTION_RATIOS = frozenset({"ebitda_margin", "net_profit_margin", "cash_profit_margin", "return_on_equity",
                             "return_on_assets", "roce", "ocf_to_debt", "nwc_to_revenue", "contingent_liability_ratio"})
FRACTION_DECIMAL_PLACES = 4
PCT_DECIMAL_PLACES = 1


def as_pct(fraction: Optional[float]) -> Optional[float]:
    """A fraction ratio as a percentage, to the platform's single display precision (one decimal)."""
    return None if fraction is None else round(fraction * 100, PCT_DECIMAL_PLACES)

def _safe_divide(numerator: float, denominator: float, entity_id: str,
                 period: str, ratio_name: str, formula: str) -> RatioResult:
    """Deterministic division with fixed null/zero handling."""
    if denominator == 0:
        return RatioResult(
            entity_id=entity_id, period=period, ratio_name=ratio_name,
            numerator=numerator, denominator=denominator, value=None,
            formula=formula, status="div_by_zero"
        )
    places = FRACTION_DECIMAL_PLACES if ratio_name in FRACTION_RATIOS else DECIMAL_PLACES
    value = round(numerator / denominator, places)
    return RatioResult(
        entity_id=entity_id, period=period, ratio_name=ratio_name,
        numerator=numerator, denominator=denominator, value=value,
        formula=formula, status="computed"
    )


# ─── Ratio Definitions ──────────────────────────────────────────────────────

def current_ratio(fs: FinancialStatement) -> RatioResult:
    return _safe_divide(
        fs.get("current_assets"), fs.get("current_liabilities"),
        fs.entity_id, fs.period, "current_ratio",
        "current_assets / current_liabilities"
    )

def debt_to_equity(fs: FinancialStatement) -> RatioResult:
    return _safe_divide(
        fs.get("total_debt"), fs.get("total_equity"),
        fs.entity_id, fs.period, "debt_to_equity",
        "total_debt / total_equity"
    )

def debt_to_ebitda(fs: FinancialStatement) -> RatioResult:
    return _safe_divide(
        fs.get("total_debt"), fs.get("ebitda"),
        fs.entity_id, fs.period, "debt_to_ebitda",
        "total_debt / ebitda"
    )

def interest_coverage_ratio(fs: FinancialStatement) -> RatioResult:
    return _safe_divide(
        fs.get("ebit"), fs.get("finance_cost"),
        fs.entity_id, fs.period, "interest_coverage_ratio",
        "ebit / finance_cost"
    )

def net_profit_margin(fs: FinancialStatement) -> RatioResult:
    return _safe_divide(
        fs.get("pat"), fs.get("revenue_operating"),
        fs.entity_id, fs.period, "net_profit_margin",
        "pat / revenue_operating"
    )

def ebitda_margin(fs: FinancialStatement) -> RatioResult:
    return _safe_divide(
        fs.get("ebitda"), fs.get("revenue_operating"),
        fs.entity_id, fs.period, "ebitda_margin",
        "ebitda / revenue_operating"
    )

def return_on_equity(fs: FinancialStatement) -> RatioResult:
    return _safe_divide(
        fs.get("pat"), fs.get("total_equity"),
        fs.entity_id, fs.period, "return_on_equity",
        "pat / total_equity"
    )

def return_on_assets(fs: FinancialStatement) -> RatioResult:
    return _safe_divide(
        fs.get("pat"), fs.get("total_assets"),
        fs.entity_id, fs.period, "return_on_assets",
        "pat / total_assets"
    )

def asset_turnover(fs: FinancialStatement) -> RatioResult:
    return _safe_divide(
        fs.get("revenue_operating"), fs.get("total_assets"),
        fs.entity_id, fs.period, "asset_turnover",
        "revenue_operating / total_assets"
    )

def debtor_days(fs: FinancialStatement) -> RatioResult:
    rev = fs.get("revenue_operating")
    rec = fs.get("trade_receivables")
    if rev == 0:
        return RatioResult(entity_id=fs.entity_id, period=fs.period,
                           ratio_name="debtor_days", numerator=rec,
                           denominator=rev, value=None,
                           formula="(trade_receivables / revenue_operating) * 365",
                           status="div_by_zero")
    value = round((rec / rev) * 365, DECIMAL_PLACES)
    return RatioResult(entity_id=fs.entity_id, period=fs.period,
                       ratio_name="debtor_days", numerator=rec,
                       denominator=rev, value=value,
                       formula="(trade_receivables / revenue_operating) * 365",
                       status="computed")

def inventory_days(fs: FinancialStatement) -> RatioResult:
    rev = fs.get("revenue_operating")
    inv = fs.get("inventory")
    if rev == 0:
        return RatioResult(entity_id=fs.entity_id, period=fs.period,
                           ratio_name="inventory_days", numerator=inv,
                           denominator=rev, value=None,
                           formula="(inventory / revenue_operating) * 365",
                           status="div_by_zero")
    value = round((inv / rev) * 365, DECIMAL_PLACES)
    return RatioResult(entity_id=fs.entity_id, period=fs.period,
                       ratio_name="inventory_days", numerator=inv,
                       denominator=rev, value=value,
                       formula="(inventory / revenue_operating) * 365",
                       status="computed")

def payable_days(fs: FinancialStatement) -> RatioResult:
    rev = fs.get("revenue_operating")
    pay = fs.get("trade_payables")
    if rev == 0:
        return RatioResult(entity_id=fs.entity_id, period=fs.period,
                           ratio_name="payable_days", numerator=pay,
                           denominator=rev, value=None,
                           formula="(trade_payables / revenue_operating) * 365",
                           status="div_by_zero")
    value = round((pay / rev) * 365, DECIMAL_PLACES)
    return RatioResult(entity_id=fs.entity_id, period=fs.period,
                       ratio_name="payable_days", numerator=pay,
                       denominator=rev, value=value,
                       formula="(trade_payables / revenue_operating) * 365",
                       status="computed")

def working_capital_cycle(fs: FinancialStatement) -> RatioResult:
    """Net working capital cycle = debtor days + inventory days - payable days"""
    dd = debtor_days(fs)
    id_ = inventory_days(fs)
    pd_ = payable_days(fs)
    if any(r.value is None for r in [dd, id_, pd_]):
        return RatioResult(entity_id=fs.entity_id, period=fs.period,
                           ratio_name="working_capital_cycle",
                           numerator=0, denominator=0, value=None,
                           formula="debtor_days + inventory_days - payable_days",
                           status="data_missing")
    value = round(dd.value + id_.value - pd_.value, DECIMAL_PLACES)
    return RatioResult(entity_id=fs.entity_id, period=fs.period,
                       ratio_name="working_capital_cycle",
                       numerator=dd.value + id_.value, denominator=pd_.value,
                       value=value,
                       formula="debtor_days + inventory_days - payable_days",
                       status="computed")

def dscr(fs: FinancialStatement) -> RatioResult:
    """Simplified DSCR = (PAT + Depreciation + Finance Cost) / (Finance Cost + Long-term debt repayment)
    Assuming annual principal repayment ~ 20% of long-term debt."""
    pat = fs.get("pat")
    dep = fs.get("depreciation")
    fc = fs.get("finance_cost")
    ltd = fs.get("long_term_debt")
    cash_for_ds = pat + dep + fc
    annual_principal = ltd * 0.20  # assume 5-year repayment
    total_ds = fc + annual_principal
    return _safe_divide(cash_for_ds, total_ds,
                        fs.entity_id, fs.period, "dscr",
                        "(pat + depreciation + finance_cost) / (finance_cost + annual_principal_repayment)")

def tocl_ratio(fs: FinancialStatement) -> RatioResult:
    """Total Outside Liabilities to Tangible Net Worth"""
    tol = fs.get("total_debt") + fs.get("current_liabilities")
    tnw = fs.get("total_equity") - fs.get("intangible_assets", 0)
    return _safe_divide(tol, tnw,
                        fs.entity_id, fs.period, "tol_tnw",
                        "(total_debt + current_liabilities) / (total_equity - intangible_assets)")


# ─── Market-Standard Extended Ratios ─────────────────────────────────────────

def roce(fs: FinancialStatement) -> RatioResult:
    """Return on Capital Employed = EBIT / (Total Equity + Long-term Debt).
    Standard credit metric used by CRISIL, ICRA, CARE for assessing capital efficiency."""
    ebit = fs.get("ebit")
    ce = fs.get("total_equity") + fs.get("long_term_debt")
    return _safe_divide(ebit, ce, fs.entity_id, fs.period, "roce",
                        "ebit / (total_equity + long_term_debt)")


def fixed_charge_coverage(fs: FinancialStatement) -> RatioResult:
    """Fixed Charge Coverage = (EBITDA) / (Finance Cost + Annual Principal).
    RBI/Basel III convention — measures ability to service all fixed obligations."""
    ebitda = fs.get("ebitda")
    fc = fs.get("finance_cost")
    ltd = fs.get("long_term_debt")
    annual_principal = ltd * 0.20
    total_fixed = fc + annual_principal
    return _safe_divide(ebitda, total_fixed, fs.entity_id, fs.period,
                        "fixed_charge_coverage",
                        "ebitda / (finance_cost + annual_principal_repayment)")


def cash_profit_margin(fs: FinancialStatement) -> RatioResult:
    """Cash Profit Margin = (PAT + Depreciation) / Revenue.
    Preferred by banks over net margin — eliminates non-cash distortions."""
    cash_profit = fs.get("pat") + fs.get("depreciation")
    return _safe_divide(cash_profit, fs.get("revenue_operating"),
                        fs.entity_id, fs.period, "cash_profit_margin",
                        "(pat + depreciation) / revenue_operating")


def tangible_net_worth(fs: FinancialStatement) -> RatioResult:
    """Tangible Net Worth = Total Equity - Intangible Assets.
    Critical for collateral coverage assessment. Returns absolute value."""
    tnw = fs.get("total_equity") - fs.get("intangible_assets", 0)
    return RatioResult(
        entity_id=fs.entity_id, period=fs.period, ratio_name="tangible_net_worth",
        numerator=fs.get("total_equity"), denominator=fs.get("intangible_assets", 0),
        value=round(tnw, DECIMAL_PLACES),
        formula="total_equity - intangible_assets", status="computed")


def debt_to_tangible_net_worth(fs: FinancialStatement) -> RatioResult:
    """Debt / Tangible Net Worth — more conservative than D/E, used by RBI for exposure norms."""
    td = fs.get("total_debt")
    tnw = fs.get("total_equity") - fs.get("intangible_assets", 0)
    return _safe_divide(td, tnw, fs.entity_id, fs.period, "debt_to_tnw",
                        "total_debt / (total_equity - intangible_assets)")


def operating_cash_flow_to_debt(fs: FinancialStatement) -> RatioResult:
    """OCF / Total Debt — measures debt repayment capacity from operations.
    Key ratio in CRISIL/ICRA rating methodology."""
    ocf = fs.get("operating_cash_flow", 0)
    return _safe_divide(ocf, fs.get("total_debt"),
                        fs.entity_id, fs.period, "ocf_to_debt",
                        "operating_cash_flow / total_debt")


def free_cash_flow_to_firm(fs: FinancialStatement) -> RatioResult:
    """FCFF = Operating Cash Flow - Capex. Absolute value."""
    ocf = fs.get("operating_cash_flow", 0)
    capex = fs.get("capex", 0)
    fcff = ocf - capex
    return RatioResult(
        entity_id=fs.entity_id, period=fs.period, ratio_name="fcff",
        numerator=ocf, denominator=capex, value=round(fcff, DECIMAL_PLACES),
        formula="operating_cash_flow - capex", status="computed")


def altman_z_score(fs: FinancialStatement) -> RatioResult:
    """Altman Z-Score (manufacturing model) for distress prediction.
    Z = 1.2*A + 1.4*B + 3.3*C + 0.6*D + 1.0*E
    where A=WC/TA, B=RE/TA, C=EBIT/TA, D=Equity/TotalDebt, E=Revenue/TA.
    Z > 2.99 = safe zone, 1.81-2.99 = grey zone, < 1.81 = distress zone.
    Standard academic + practitioner model used globally in credit assessment."""
    ta = fs.get("total_assets")
    if ta == 0:
        return RatioResult(entity_id=fs.entity_id, period=fs.period,
                           ratio_name="altman_z_score", numerator=0, denominator=ta,
                           value=None, formula="Altman Z = 1.2*A + 1.4*B + 3.3*C + 0.6*D + 1.0*E",
                           status="div_by_zero")
    wc = fs.get("current_assets") - fs.get("current_liabilities")
    a = wc / ta
    b = fs.get("reserves_surplus", fs.get("total_equity") * 0.85) / ta
    c = fs.get("ebit") / ta
    td = fs.get("total_debt")
    d = fs.get("total_equity") / td if td > 0 else 3.0
    e = fs.get("revenue_operating") / ta
    z = round(1.2 * a + 1.4 * b + 3.3 * c + 0.6 * d + 1.0 * e, DECIMAL_PLACES)
    return RatioResult(
        entity_id=fs.entity_id, period=fs.period, ratio_name="altman_z_score",
        numerator=z, denominator=1, value=z,
        formula="1.2*(WC/TA) + 1.4*(RE/TA) + 3.3*(EBIT/TA) + 0.6*(Eq/Debt) + 1.0*(Rev/TA)",
        status="computed")


def net_debt_to_ebitda(fs: FinancialStatement) -> RatioResult:
    """Net Debt / EBITDA = (Total Debt - Cash) / EBITDA.
    Used by rating agencies for leverage assessment net of cash buffers."""
    net_debt = fs.get("total_debt") - fs.get("cash_equivalents", 0)
    return _safe_divide(net_debt, fs.get("ebitda"),
                        fs.entity_id, fs.period, "net_debt_to_ebitda",
                        "(total_debt - cash_equivalents) / ebitda")


def capex_to_depreciation(fs: FinancialStatement) -> RatioResult:
    """Capex / Depreciation — measures whether company is reinvesting.
    Ratio > 1.0 = expanding, < 1.0 = harvesting / underinvesting."""
    capex = fs.get("capex", 0)
    dep = fs.get("depreciation")
    return _safe_divide(capex, dep, fs.entity_id, fs.period,
                        "capex_to_depreciation", "capex / depreciation")


def working_capital_to_revenue(fs: FinancialStatement) -> RatioResult:
    """Net Working Capital / Revenue — working capital intensity.
    Lower is better (less capital tied up). Industry-specific benchmarks."""
    nwc = fs.get("current_assets") - fs.get("current_liabilities")
    return _safe_divide(nwc, fs.get("revenue_operating"),
                        fs.entity_id, fs.period, "nwc_to_revenue",
                        "(current_assets - current_liabilities) / revenue_operating")


def contingent_liability_ratio(fs: FinancialStatement) -> RatioResult:
    """Contingent Liabilities / Net Worth — off-balance-sheet risk metric.
    Banks watch this for hidden exposure risk."""
    cl = fs.get("contingent_liabilities", 0)
    return _safe_divide(cl, fs.get("total_equity"),
                        fs.entity_id, fs.period, "contingent_liability_ratio",
                        "contingent_liabilities / total_equity")


# ─── Full Ratio Suite ────────────────────────────────────────────────────────

ALL_RATIO_FUNCTIONS = [
    # Liquidity
    current_ratio,
    # Leverage
    debt_to_equity, debt_to_ebitda, debt_to_tangible_net_worth,
    net_debt_to_ebitda, tocl_ratio,
    # Coverage
    interest_coverage_ratio, dscr, fixed_charge_coverage,
    # Profitability
    net_profit_margin, ebitda_margin, cash_profit_margin,
    return_on_equity, return_on_assets, roce,
    # Efficiency
    asset_turnover, debtor_days, inventory_days, payable_days,
    working_capital_cycle, working_capital_to_revenue,
    # Cash Flow
    operating_cash_flow_to_debt, free_cash_flow_to_firm,
    capex_to_depreciation,
    # Solvency / Distress
    altman_z_score, tangible_net_worth, contingent_liability_ratio,
]

def compute_all_ratios(fs: FinancialStatement) -> list[RatioResult]:
    """Run every ratio for a single period. Deterministic."""
    return [fn(fs) for fn in ALL_RATIO_FUNCTIONS]

def compute_multi_period_ratios(financials: dict[str, FinancialStatement]) -> dict[str, list[RatioResult]]:
    """Run all ratios for all periods. Returns {period: [RatioResult]}."""
    return {period: compute_all_ratios(fs) for period, fs in financials.items()}

def revenue_growth_rate(fs_current: FinancialStatement, fs_prior: FinancialStatement) -> RatioResult:
    """Year-on-year revenue growth."""
    curr = fs_current.get("revenue_operating")
    prev = fs_prior.get("revenue_operating")
    if prev == 0:
        return RatioResult(entity_id=fs_current.entity_id, period=fs_current.period,
                           ratio_name="revenue_growth_yoy", numerator=curr,
                           denominator=prev, value=None,
                           formula="(current_revenue - prior_revenue) / prior_revenue",
                           status="div_by_zero")
    value = round((curr - prev) / prev, 4)
    return RatioResult(entity_id=fs_current.entity_id, period=fs_current.period,
                       ratio_name="revenue_growth_yoy", numerator=curr - prev,
                       denominator=prev, value=value,
                       formula="(current_revenue - prior_revenue) / prior_revenue",
                       status="computed")


# ─── Growth & cash-conversion metrics (multi-period) ─────────────────────────

GROWTH_LINES = {"revenue_operating": "revenue", "ebitda": "ebitda", "pat": "pat", "total_debt": "total_debt",
                "operating_cash_flow": "ocf", "trade_receivables": "receivables", "inventory": "inventory"}


def _yoy(curr: float, prev: float):
    return round((curr - prev) / prev * 100, 1) if prev and prev > 0 else None


def compute_growth_metrics(financials: dict[str, FinancialStatement]) -> dict:
    """Year-on-year growth of key lines, OCF/PAT, and revenue CAGR - so no consumer (template or LLM)
    has to derive them. Growth is None when the base is not positive."""
    periods = sorted(financials)
    by_period = {}
    for i, p in enumerate(periods):
        fs = financials[p]
        row = {}
        if i:
            prev = financials[periods[i - 1]]
            for item, label in GROWTH_LINES.items():
                row[f"{label}_yoy_pct"] = _yoy(fs.get(item), prev.get(item))
        pat, ocf = fs.get("pat"), fs.get("operating_cash_flow", 0)
        row["ocf_to_pat"] = round(ocf / pat, 2) if pat > 0 else None
        by_period[p] = row
    cagr = total = None
    if len(periods) >= 2:
        first, last = financials[periods[0]].get("revenue_operating"), financials[periods[-1]].get("revenue_operating")
        if first > 0 and last > 0:
            cagr = round(((last / first) ** (1 / (len(periods) - 1)) - 1) * 100, 1)
            total = round((last - first) / first * 100, 1)
    return {"by_period": by_period, "revenue_cagr_pct": cagr, "revenue_total_growth_pct": total,
            "cagr_from": periods[0] if periods else None, "cagr_to": periods[-1] if periods else None,
            "cagr_years": max(len(periods) - 1, 0)}
