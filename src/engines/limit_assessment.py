"""Limit assessment (roadmap D8): how much bank finance the borrower's operations support.

A working-capital limit is sized from the operating cycle, not taken from the request. The method follows the
facility and the borrower (all thresholds in config/rules.yaml → ``limit_assessment``):

    turnover method      small fund-based limits (up to ``turnover.max_limit_cr``): working-capital need = 25% of
                         projected turnover, of which the borrower brings 5% and the banks finance 20%
    MPBF (method II)     maximum permissible bank finance: projected current assets less other current
                         liabilities (the working-capital gap), less the borrower's margin, which is the higher of
                         25% of current assets and the net working capital it already has
    operating cycle      service and contract businesses that carry little stock (sectors in
                         ``operating_cycle.sectors``): projected turnover × (inventory + receivable − payable
                         days) / 365, of which the banks finance 75%
    non-fund             bank guarantees and letters of credit are sized on the guarantee pipeline or the import
                         purchases, which are not on record: the assessment says so instead of guessing

The banks' total is reduced by working-capital borrowings already with other banks (short-term debt; for an
existing borrower, less our own existing limit) to give what is available for this proposal.

Term loans are sized on debt service (the DSCR schedule and the sustainable limit elsewhere in the CAM); this
module adds the break-even point and the margin of safety from the cost structure. A project IRR needs the
project's own cash flows (cost, phasing, incremental revenue), which are not on record, and is not invented.

Every figure is deterministic and shown with its formula, so the CAM and the screen quote the same numbers.
"""

from __future__ import annotations

import re
from typing import Optional

DEFAULTS = {
    "fund_based": ["working_capital", "cash_credit"],
    "term": ["term_loan", "project_finance"],
    "non_fund_words": r"\b(non[- ]fund|bank guarantee|guarantees?|BG|letters? of credit|LC|LCs)\b",
    "turnover": {"max_limit_cr": 5.0, "need_share": 0.25, "bank_share": 0.20},
    "mpbf": {"margin_on_current_assets": 0.25},
    "operating_cycle": {"sectors": ["it_services", "services", "infrastructure", "hospitality", "healthcare"],
                        "bank_share": 0.75},
    "growth": {"floor_pct": -10.0, "cap_pct": 25.0},
    "break_even": {"variable": ["raw_material_cost"], "other_expenses_variable_share": 0.5},
}


def _cfg() -> dict:
    from src.core.config_manager import config
    got = config.get("rules", "limit_assessment", default=None) or {}
    out = {**DEFAULTS, **got}
    for k in ("turnover", "mpbf", "operating_cycle", "growth", "break_even"):
        out[k] = {**DEFAULTS[k], **(got.get(k) or {})}
    return out


def _cr(v: Optional[float]) -> str:
    if v is None:
        return "—"
    from src.flow.copilot import crore
    return crore(v)


def _f(d: dict, k: str) -> float:
    try:
        return float(d.get(k) or 0)
    except (TypeError, ValueError):
        return 0.0


def _days(part: float, revenue: float) -> float:
    return 365.0 * part / revenue if revenue else 0.0


def _value(x) -> str:
    return getattr(x, "value", x) or ""


def _kind(product: str, purpose: str, cfg: dict) -> str:
    if re.search(cfg["non_fund_words"], purpose or "", re.I) and product not in cfg["term"]:
        return "non_fund"
    if product in cfg["term"]:
        return "term"
    return "fund"


def assess(*, periods: dict, product: str, purpose: str = "", sector: str = "", requested_cr: float = 0,
           existing_limit_cr: Optional[float] = None, case_type: str = "", projected_revenue_cr: Optional[float] = None,
           cfg: Optional[dict] = None) -> dict:
    """``periods``: {period: {canonical line item: ₹ Cr}} (e.g. FinancialStatement.line_items), oldest first or not."""
    cfg = cfg or _cfg()
    if not periods:
        return {"available": False, "reason": "No financial statements on record to assess the limit from"}
    keys = sorted(periods)
    period = keys[-1]
    li = periods[period]
    rev = _f(li, "revenue_operating")
    if rev <= 0:
        return {"available": False, "reason": f"No revenue in {period} to assess the limit from"}
    kind = _kind(product, purpose, cfg)

    # projected turnover: the CAM's own year-1 projection when it has one, else last year's growth, bounded
    if projected_revenue_cr:
        proj, growth, growth_basis = float(projected_revenue_cr), float(projected_revenue_cr) / rev - 1, "CAM projection (year 1)"
    else:
        prev = _f(periods[keys[-2]], "revenue_operating") if len(keys) > 1 else 0
        g = (rev / prev - 1) if prev else 0.0
        lo, hi = cfg["growth"]["floor_pct"] / 100, cfg["growth"]["cap_pct"] / 100
        growth = min(max(g, lo), hi)
        proj, growth_basis = rev * (1 + growth), (f"{period} growth {g * 100:.1f}%"
                                                  + (" (bounded)" if growth != g else "") if prev else "flat (one year on record)")
    scale = proj / rev
    base = {"available": True, "kind": kind, "period": period, "requested_cr": round(requested_cr or 0, 2),
            "revenue_cr": round(rev, 2), "projected_revenue_cr": round(proj, 2), "growth_pct": round(growth * 100, 1),
            "growth_basis": growth_basis, "assumptions": []}

    if kind == "term":
        return {**base, **_break_even(li, rev, cfg), "assessed_cr": None, "available_cr": None,
                "within": None, "method": "break_even", "method_label": "Break-even and margin of safety"}

    if kind == "non_fund":
        return {**base, "method": "non_fund", "method_label": "Non-fund limit (guarantees / letters of credit)",
                "assessed_cr": None, "available_cr": None, "within": None, "rows": [],
                "needs": "the guarantee pipeline (contracts needing a guarantee, value and tenor) or the import "
                         "purchases and lead time for letters of credit",
                "basis": ("A non-fund limit is sized on the guarantees the borrower's contracts need, or on its "
                          "import purchases for letters of credit. Neither is on record, so the limit is not assessed "
                          "here: ask the RM for the pipeline.")}

    inv, rec, pay = _f(li, "inventory"), _f(li, "trade_receivables"), _f(li, "trade_payables")
    ca, cl, std = _f(li, "current_assets"), _f(li, "current_liabilities"), _f(li, "short_term_debt")
    methods = []

    # 1. turnover method
    t = cfg["turnover"]
    need, bank = proj * t["need_share"], proj * t["bank_share"]
    methods.append({"method": "turnover", "label": "Turnover method", "assessed_cr": round(bank, 2), "rows": [
        {"label": "Projected turnover", "value": _cr(proj), "how": growth_basis},
        {"label": "Working-capital need", "value": _cr(need), "how": f"{t['need_share'] * 100:.0f}% of turnover"},
        {"label": "Borrower’s margin", "value": _cr(need - bank), "how": f"{(t['need_share'] - t['bank_share']) * 100:.0f}% of turnover"},
        {"label": "Permissible bank finance", "value": _cr(bank), "how": f"{t['bank_share'] * 100:.0f}% of turnover"}]})

    # 2. MPBF, method II, on projected current assets and liabilities
    if ca > 0:
        m = cfg["mpbf"]["margin_on_current_assets"]
        ca_p, ocl_p = ca * scale, max(cl - std, 0) * scale
        nwc_p = (ca - cl) * scale
        gap = ca_p - ocl_p
        margin = max(m * ca_p, nwc_p)
        mpbf = max(gap - margin, 0)
        methods.append({"method": "mpbf", "label": "MPBF (method II)", "assessed_cr": round(mpbf, 2), "rows": [
            {"label": "Projected current assets", "value": _cr(ca_p), "how": f"{period} {_cr(ca)} × turnover growth"},
            {"label": "Other current liabilities", "value": _cr(ocl_p),
             "how": f"current liabilities {_cr(cl)} less short-term bank borrowings {_cr(std)}, × growth"},
            {"label": "Working-capital gap", "value": _cr(gap), "how": "current assets − other current liabilities"},
            {"label": "Borrower’s margin", "value": _cr(margin),
             "how": (f"higher of {m * 100:.0f}% of current assets ({_cr(m * ca_p)}) and its net working capital "
                     f"({_cr(nwc_p)})")},
            {"label": "Maximum permissible bank finance", "value": _cr(mpbf), "how": "gap − margin"}]})
        if not std and cl:
            base["assumptions"].append("No short-term bank borrowings on record: all current liabilities are treated "
                                       "as other current liabilities")

    # 3. operating cycle
    cyc = _days(inv, rev) + _days(rec, rev) - _days(pay, rev)
    if cyc > 0:
        share = cfg["operating_cycle"]["bank_share"]
        need = proj * cyc / 365
        methods.append({"method": "operating_cycle", "label": "Operating cycle", "assessed_cr": round(need * share, 2), "rows": [
            {"label": "Operating cycle", "value": f"{cyc:.0f} days",
             "how": (f"inventory {_days(inv, rev):.0f} + receivables {_days(rec, rev):.0f} − payables "
                     f"{_days(pay, rev):.0f} days ({period})")},
            {"label": "Working-capital need", "value": _cr(need), "how": "projected turnover × cycle / 365"},
            {"label": "Borrower’s margin", "value": _cr(need * (1 - share)), "how": f"{(1 - share) * 100:.0f}% of the need"},
            {"label": "Permissible bank finance", "value": _cr(need * share), "how": f"{share * 100:.0f}% of the need"}]})

    by = {x["method"]: x for x in methods}
    if requested_cr and requested_cr <= t["max_limit_cr"]:
        primary, why = "turnover", f"limits up to {_cr(t['max_limit_cr'])} are assessed on turnover"
    elif str(sector).lower() in [s.lower() for s in cfg["operating_cycle"]["sectors"]] and "operating_cycle" in by:
        primary, why = "operating_cycle", f"{str(sector).replace('_', ' ')} carries little stock: assessed on the operating cycle"
    elif "mpbf" in by:
        primary, why = "mpbf", "fund-based working capital above the turnover-method limit"
    else:
        primary, why = "turnover", "no balance sheet detail for MPBF"
    chosen = by[primary]

    other_banks = std
    if str(case_type).upper() == "ETB" and existing_limit_cr:
        other_banks = max(std - float(existing_limit_cr), 0)
    if other_banks:
        base["assumptions"].append("Short-term borrowings on record are treated as working-capital finance from other "
                                   "banks; confirm against the banking arrangement and the bureau report")
    available = max(chosen["assessed_cr"] - other_banks, 0)
    within = (requested_cr or 0) <= available + 1e-6
    rows = chosen["rows"] + [
        {"label": "Less: working-capital finance with other banks", "value": _cr(other_banks),
         "how": "short-term bank borrowings" + (" less our existing limit" if other_banks != std else "")},
        {"label": "Available for this proposal", "value": _cr(available), "how": "", "total": True}]
    basis = (f"{chosen['label']} ({why}): {_cr(chosen['assessed_cr'])} of bank finance on projected turnover of "
             f"{_cr(proj)}; {_cr(available)} available for this proposal after {_cr(other_banks)} with other banks. "
             + (f"The request of {_cr(requested_cr)} is within it." if within else
                f"The request of {_cr(requested_cr)} exceeds it by {_cr(requested_cr - available)}."))
    return {**base, "method": primary, "method_label": chosen["label"], "method_reason": why,
            "assessed_cr": chosen["assessed_cr"], "other_banks_cr": round(other_banks, 2),
            "available_cr": round(available, 2), "within": within,
            "gap_cr": round(max((requested_cr or 0) - available, 0), 2), "rows": rows,
            "alternatives": [{"method": x["method"], "label": x["label"], "assessed_cr": x["assessed_cr"]}
                             for x in methods if x["method"] != primary],
            "basis": basis}


def _break_even(li: dict, rev: float, cfg: dict) -> dict:
    be = cfg["break_even"]
    share = float(be["other_expenses_variable_share"])
    variable = sum(_f(li, k) for k in be["variable"]) + share * _f(li, "other_expenses")
    fixed_cash = _f(li, "employee_cost") + (1 - share) * _f(li, "other_expenses") + _f(li, "finance_cost")
    fixed = fixed_cash + _f(li, "depreciation")
    cm = (rev - variable) / rev if rev else 0
    if cm <= 0 or not (variable or fixed):
        return {"rows": [], "basis": "The cost lines needed for a break-even point are not on record.",
                "break_even_cr": None, "margin_of_safety_pct": None}
    bep, cash_bep = fixed / cm, fixed_cash / cm
    mos = (rev - bep) / rev
    rows = [
        {"label": "Revenue", "value": _cr(rev), "how": "latest audited year"},
        {"label": "Variable costs", "value": _cr(variable),
         "how": "materials + " + f"{share * 100:.0f}% of other expenses"},
        {"label": "Contribution margin", "value": f"{cm * 100:.1f}%", "how": "(revenue − variable costs) / revenue"},
        {"label": "Fixed costs", "value": _cr(fixed), "how": "employees, the rest of other expenses, finance cost, depreciation"},
        {"label": "Break-even revenue", "value": _cr(bep), "how": "fixed costs / contribution margin"},
        {"label": "Cash break-even revenue", "value": _cr(cash_bep), "how": "fixed costs less depreciation / contribution margin"},
        {"label": "Margin of safety", "value": f"{mos * 100:.1f}%", "how": "(revenue − break-even) / revenue", "total": True}]
    return {"rows": rows, "break_even_cr": round(bep, 2), "cash_break_even_cr": round(cash_bep, 2),
            "margin_of_safety_pct": round(mos * 100, 1),
            "irr_note": ("Project IRR needs the project’s own cash flows (cost, phasing, incremental revenue): not "
                         "on record."),
            "basis": (f"Revenue can fall {mos * 100:.0f}% before the borrower stops covering its fixed costs "
                      f"(break-even {_cr(bep)} against revenue {_cr(rev)}). The term loan is sized on debt service: "
                      f"see the DSCR schedule and the sustainable limit.")}


def from_company(company_data: dict, fact_pack: Optional[dict] = None) -> dict:
    """The assessment for a proposal, from the company record the CAM engine works on. The facility comes from
    the fact pack when there is one (it carries an amount or product an officer changed for the run)."""
    fins = company_data.get("financials") or {}
    periods = {p: dict(getattr(fs, "line_items", fs) or {}) for p, fs in fins.items()}
    fac = company_data.get("facility")
    fd = (fact_pack or {}).get("facility_details") or {}
    borrower = company_data.get("borrower")
    proj = None
    years = ((fact_pack or {}).get("financial_projections") or {}).get("years") or []
    if years and years[0].get("revenue_cr"):
        proj = years[0]["revenue_cr"]
    return assess(periods=periods, product=str(fd.get("facility_type") or _value(getattr(fac, "facility_type", ""))),
                  purpose=fd.get("purpose") or getattr(fac, "purpose", "") or "",
                  sector=_value(getattr(borrower, "sector", "")),
                  requested_cr=float(fd.get("amount_requested_cr") or getattr(fac, "amount_requested_cr", 0) or 0),
                  existing_limit_cr=fd.get("existing_limit_cr", getattr(fac, "existing_limit_cr", None)),
                  case_type=_value(getattr(fac, "case_type", "")), projected_revenue_cr=proj)
