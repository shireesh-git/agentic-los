"""Quality of the numbers and the size of the loan — deterministic, added to the fact pack so the CAM, the
workflow's credit data fields and Credit Copilot all quote the same figures (Phase 1: D2, D3).

    debt_capacity     the sustainable limit: the largest amount every policy limit allows (leverage, interest
                      cover, DSCR, TOL/TNW, debt/equity, drawing power for working capital), which limit binds,
                      and the structure (amount × tenor) that passes — or why no structure does
    earnings_quality  how much of profit is operating and cash-backed: other-income share of PBT, cash
                      conversion (OCF/EBITDA), accruals, receivables growing ahead of revenue
    revenue_truth     audited revenue against independent sources (GST turnover, bank credits, provisional
                      and exchange filings): a score, and "not verifiable" when only one source exists
    ews_indicators    early-warning indicators at origination, in the spirit of RBI's fraud-risk Master
                      Directions (2024): statutory dues, cheque returns, bureau / CRILC stress, manipulation
                      and evergreening signals from the forensic engine, distress, stale financials

Nothing here is estimated by a model; each item carries the formula or the source it came from.
"""

from __future__ import annotations

import re
from typing import Optional

def _n(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f


def _cr(v: float) -> str:
    return f"₹{v:,.2f} Cr"


def _items(fs) -> dict:
    return fs.line_items if hasattr(fs, "line_items") else (fs if isinstance(fs, dict) else {})


def _latest(financials: dict) -> tuple[Optional[str], dict, dict]:
    periods = sorted(financials or {})
    if not periods:
        return None, {}, {}
    prior = _items(financials[periods[-2]]) if len(periods) > 1 else {}
    return periods[-1], _items(financials[periods[-1]]), prior


# ── D2: sustainable limit and the structure that passes policy ──────────────

def debt_capacity(financials: dict, facility, thresholds: dict, projections: dict, drawing_power: dict) -> dict:
    period, it, _ = _latest(financials)
    if not it:
        return {"available": False, "reason": "No financial statements"}
    product = getattr(getattr(facility, "facility_type", None), "value", str(getattr(facility, "facility_type", "")))
    is_wc = "working" in product
    amount = _n(getattr(facility, "proposed_limit_cr", None)) or _n(getattr(facility, "amount_requested_cr", None)) or 0.0
    tenor = int(getattr(facility, "tenor_months", None) or (12 if is_wc else 60))
    rate = (_n(((projections or {}).get("assumptions") or {}).get("interest_rate_pct")) or 9.5) / 100

    ebitda = _n(it.get("ebitda")) or 0.0
    dep = _n(it.get("depreciation")) or 0.0
    fc = _n(it.get("finance_cost")) or 0.0
    ebit = _n(it.get("ebit")) if it.get("ebit") is not None else ebitda - dep
    pat = _n(it.get("pat")) or 0.0
    debt = _n(it.get("total_debt")) or 0.0
    ltd = _n(it.get("long_term_debt")) or 0.0
    equity = _n(it.get("total_equity")) or 0.0
    tnw = equity - (_n(it.get("intangible_assets")) or 0.0)
    cl = _n(it.get("current_liabilities")) or 0.0
    cads = pat + dep + fc                           # cash available for debt service (ratio engine's DSCR basis)
    p_exist = 0.20 * ltd                            # the ratio engine's assumed annual principal on existing debt
    t = thresholds or {}

    def principal_factor(months: int) -> float:
        return 0.0 if is_wc else 12.0 / max(months, 1)

    def constraints(months: int) -> list[dict]:
        out = []

        def add(cid, label, limit, value, formula):
            if value is None:
                return
            out.append({"id": cid, "label": label, "limit_display": limit, "max_amount_cr": round(value, 2),
                        "breached_at_zero": value < 0, "formula": formula})

        if t.get("max_debt_to_ebitda") and ebitda > 0:
            add("debt_to_ebitda", "Debt / EBITDA", f"max {t['max_debt_to_ebitda']:.2f}x",
                t["max_debt_to_ebitda"] * ebitda - debt, "max Debt/EBITDA × EBITDA − existing debt")
        elif t.get("max_debt_to_ebitda"):
            add("debt_to_ebitda", "Debt / EBITDA", f"max {t['max_debt_to_ebitda']:.2f}x", -debt,
                "EBITDA is not positive — no debt capacity")
        if t.get("min_interest_coverage") and rate > 0:
            add("interest_cover", "Interest cover", f"min {t['min_interest_coverage']:.2f}x",
                (ebit / t["min_interest_coverage"] - fc) / rate, "(EBIT ÷ min ICR − finance cost) ÷ rate")
        if t.get("min_dscr"):
            denom = rate + principal_factor(months)
            add("dscr", "DSCR", f"min {t['min_dscr']:.2f}x",
                (cads / t["min_dscr"] - fc - p_exist) / denom if denom else None,
                "(cash accruals ÷ min DSCR − existing debt service) ÷ (rate + annual principal share)")
        if t.get("max_tol_tnw") and tnw > 0:
            add("tol_tnw", "TOL / TNW", f"max {t['max_tol_tnw']:.2f}x", t["max_tol_tnw"] * tnw - debt - cl,
                "max TOL/TNW × TNW − existing debt − current liabilities")
        if t.get("max_debt_to_equity") and equity > 0:
            add("debt_to_equity", "Debt / equity", f"max {t['max_debt_to_equity']:.2f}x",
                t["max_debt_to_equity"] * equity - debt, "max D/E × net worth − existing debt")
        dp = _n((drawing_power or {}).get("total_dp_cr"))
        if is_wc and dp is not None:
            existing = _n(getattr(facility, "existing_limit_cr", None)) or 0.0
            add("drawing_power", "Drawing power", f"{_cr(dp)} DP", dp - existing,
                "drawing power − existing working-capital limit")
        return out

    def sized(months: int) -> tuple[float, Optional[dict], list[dict]]:
        cons = constraints(months)
        if not cons:
            return amount, None, cons
        bind = min(cons, key=lambda c: c["max_amount_cr"])
        return max(round(bind["max_amount_cr"], 2), 0.0), bind, cons

    sustainable, bind, cons = sized(tenor)
    for c in cons:
        c["binding"] = bind is not None and c["id"] == bind["id"]
    tenors = [tenor] if is_wc else sorted({tenor, 60, 84, 120} - {m for m in (60, 84, 120) if m < tenor})
    options = []
    for m in tenors:
        cap, b, _ = sized(m)
        options.append({"tenor_months": m, "max_amount_cr": cap, "binding": b["label"] if b else None,
                        "fits": cap >= amount})
    fits = sustainable >= amount
    longer = next((o for o in options if o["fits"] and o["tenor_months"] > tenor), None)
    best = max(options, key=lambda o: o["max_amount_cr"]) if options else None
    zero = [c for c in cons if c["breached_at_zero"]]
    if fits:
        rec = {"amount_cr": amount, "tenor_months": tenor,
               "text": f"The requested {_cr(amount)} is within every policy limit (sustainable limit {_cr(sustainable)}, "
                       f"bound by {bind['label'] if bind else 'no limit'})."}
    elif longer:
        rec = {"amount_cr": amount, "tenor_months": longer["tenor_months"],
               "text": f"The requested {_cr(amount)} passes policy if the tenor is extended to "
                       f"{longer['tenor_months']} months (DSCR improves as annual principal falls)."}
    elif best and best["max_amount_cr"] > 0:
        rec = {"amount_cr": best["max_amount_cr"], "tenor_months": best["tenor_months"],
               "text": f"The largest limit within policy is {_cr(best['max_amount_cr'])}"
                       + (f" over {best['tenor_months']} months" if not is_wc else "")
                       + f", bound by {best['binding']} (requested {_cr(amount)})."}
    else:
        rec = {"amount_cr": 0.0, "tenor_months": tenor,
               "text": "No amount or tenor brings the proposal within policy: "
                       + "; ".join(f"{c['label']} is already outside its limit ({c['limit_display']})" for c in zero)
                       + ". It needs equity, debt reduction or a policy deviation."}
    return {"available": True, "period": period, "product": product, "requested_cr": amount, "tenor_months": tenor,
            "rate_pct": round(rate * 100, 2), "sustainable_cr": sustainable, "binding": bind["label"] if bind else None,
            "fits": fits, "constraints": cons, "options": options, "recommendation": rec,
            "not_fixable": [c["label"] for c in zero],
            "inputs": {"ebitda_cr": ebitda, "ebit_cr": ebit, "finance_cost_cr": fc, "cash_accruals_cr": round(cads, 2),
                       "existing_debt_cr": debt, "existing_principal_cr": round(p_exist, 2), "tnw_cr": round(tnw, 2)}}


# ── D3: earnings quality ─────────────────────────────────────────────────────

def _ocf(it: dict) -> Optional[float]:
    for k in ("operating_cash_flow", "ocf", "cash_from_operations"):
        if it.get(k) is not None:
            return _n(it[k])
    return None


def _metric(mid, label, value, display, status, basis) -> dict:
    return {"id": mid, "label": label, "value": value, "display": display, "status": status, "basis": basis}


def earnings_quality(financials: dict) -> dict:
    period, it, prior = _latest(financials)
    if not it:
        return {"available": False}
    out = []
    pbt, oi = _n(it.get("pbt")), _n(it.get("other_income"))
    if pbt is not None and oi is not None:
        if pbt <= 0:
            out.append(_metric("other_income_share", "Other income share of PBT", None, "PBT not positive", "bad",
                               f"{period}: PBT {_cr(pbt)}, other income {_cr(oi)}"))
        else:
            s = oi / pbt
            out.append(_metric("other_income_share", "Other income share of PBT", round(s * 100, 1), f"{s:.0%}",
                               "bad" if s > 0.5 else "warn" if s > 0.25 else "good",
                               f"{period}: other income {_cr(oi)} ÷ PBT {_cr(pbt)}"))
    ebitda, ocf = _n(it.get("ebitda")), _ocf(it)
    if ebitda and ebitda > 0 and ocf is not None:
        c = ocf / ebitda
        out.append(_metric("cash_conversion", "Cash conversion (OCF ÷ EBITDA)", round(c * 100, 1), f"{c:.0%}",
                           "bad" if c < 0.3 else "warn" if c < 0.6 else "good",
                           f"{period}: OCF {_cr(ocf)} ÷ EBITDA {_cr(ebitda)}"))
    pat, ta = _n(it.get("pat")), _n(it.get("total_assets"))
    if pat is not None and ocf is not None and ta:
        a = (pat - ocf) / ta
        out.append(_metric("accruals", "Accruals ((PAT − OCF) ÷ total assets)", round(a * 100, 1), f"{a:.1%}",
                           "bad" if a > 0.10 else "warn" if a > 0.05 else "good",
                           f"{period}: PAT {_cr(pat)} − OCF {_cr(ocf)} over assets {_cr(ta)}"))
    r1, r0 = _n(it.get("trade_receivables")), _n(prior.get("trade_receivables"))
    v1, v0 = _n(it.get("revenue_operating")), _n(prior.get("revenue_operating"))
    if r1 and r0 and v1 and v0 and 0.2 <= r1 / r0 <= 5:          # outside that range the prior figure is suspect
        gap = (r1 / r0 - 1) * 100 - (v1 / v0 - 1) * 100
        out.append(_metric("receivables_gap", "Receivables growth ahead of revenue", round(gap, 1), f"{gap:+.1f} pp",
                           "bad" if gap > 30 else "warn" if gap > 15 else "good",
                           f"receivables {r0:,.2f} → {r1:,.2f}; revenue {v0:,.2f} → {v1:,.2f}"))
    ex = _n(it.get("exceptional_items"))
    if ex and pbt and pbt > 0:
        s = abs(ex) / pbt
        out.append(_metric("exceptional_share", "Exceptional items share of PBT", round(s * 100, 1), f"{s:.0%}",
                           "bad" if s > 0.25 else "warn" if s > 0.10 else "good",
                           f"{period}: exceptional items {_cr(ex)} ÷ PBT {_cr(pbt)}"))
    if not out:
        return {"available": False, "period": period}
    penalty = sum({"bad": 25, "warn": 10}.get(m["status"], 0) for m in out)
    score = max(0, 100 - penalty)
    return {"available": True, "period": period, "score": score,
            "status": "bad" if score < 60 else "warn" if score < 85 else "good", "metrics": out}


# ── D3: revenue truth ───────────────────────────────────────────────────────

_MON = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"))}


def _months(period: str) -> Optional[int]:
    """How many months a conduct record covers: 'Apr 2026 – Sep 2026' → 6, 'Q1 FY26' → 3, 'FY2025' → 12."""
    p = str(period or "")
    m = re.findall(r"([A-Za-z]{3})[a-z]*[\s\-']+(\d{2,4})", p)
    if len(m) >= 2:
        (a, y1), (b, y2) = m[0], m[-1]
        if a.lower()[:3] in _MON and b.lower()[:3] in _MON:
            y1, y2 = int(y1[-2:]), int(y2[-2:])
            return (y2 - y1) * 12 + _MON[b.lower()[:3]] - _MON[a.lower()[:3]] + 1
    if re.search(r"\bQ[1-4]\b", p, re.I):
        return 3
    if re.search(r"\bH[12]\b", p, re.I):
        return 6
    if re.search(r"FY\s?\d{2,4}", p, re.I):
        return 12
    return None


def revenue_truth(company_data: dict, financials: dict) -> dict:
    period, it, _ = _latest(financials)
    rev = _n(it.get("revenue_operating")) if it else None
    if not rev:
        return {"available": False, "status": "na", "reason": "No audited revenue"}
    year = re.sub(r"\D", "", period or "")[-4:]
    checks = []
    gst = (((company_data.get("external_data") or {}).get("gst_data") or {}).get("payload")
           or (company_data.get("external_data") or {}).get("gst_data") or {})
    t = _n(gst.get(f"aggregate_turnover_fy{year}_cr")) if year else None
    if t:
        gap = abs(t - rev) / rev
        checks.append({"source": "GST returns", "value_cr": t, "basis": f"aggregate turnover FY{year}",
                       "gap_pct": round(gap * 100, 1), "status": "good" if gap <= 0.10 else "warn" if gap <= 0.25 else "bad"})
    credits, months = 0.0, 0
    for c in company_data.get("conduct") or []:
        m = _months(getattr(c, "period", ""))
        if m and getattr(c, "credit_turnover_cr", None):
            credits += float(c.credit_turnover_cr)
            months += m
    if months:
        annual = credits * 12 / months
        ratio = annual / rev
        checks.append({"source": "Bank credits", "value_cr": round(annual, 2),
                       "basis": f"{months} months' credits annualised (include GST and non-sales receipts)",
                       "gap_pct": round((ratio - 1) * 100, 1),
                       "status": "good" if 0.75 <= ratio <= 1.35 else "warn" if 0.5 <= ratio <= 1.6 else "bad"})
    for key, label in (("provisional", "Provisional results"), ("exchange_filing", "Exchange filing")):
        doc = company_data.get(key)
        v = _n(_items(doc).get("revenue_operating")) if doc else None
        if v and getattr(doc, "period", None) == period:
            gap = abs(v - rev) / rev
            checks.append({"source": label, "value_cr": v, "basis": f"same period ({period})",
                           "gap_pct": round(gap * 100, 1), "status": "good" if gap <= 0.05 else "warn" if gap <= 0.15 else "bad"})
    if not checks:
        return {"available": True, "period": period, "audited_cr": rev, "score": None, "status": "na",
                "checks": [], "summary": "Not verifiable: no independent source (GST, bank statements) on record"}
    pen = sum({"bad": 40, "warn": 15}.get(c["status"], 0) for c in checks)
    score = max(0, 100 - pen)
    agree = sum(1 for c in checks if c["status"] == "good")
    return {"available": True, "period": period, "audited_cr": rev, "score": score,
            "status": "bad" if score < 60 else "warn" if score < 85 else "good", "checks": checks,
            "summary": f"{agree} of {len(checks)} independent source(s) agree with audited revenue {_cr(rev)}"}


# ── D3: early-warning indicators at origination ─────────────────────────────

def ews_indicators(company_data: dict, fact_pack: dict, truth: dict, quality: dict) -> dict:
    ind = []

    def add(iid, label, status, detail, source):
        ind.append({"id": iid, "label": label, "status": status, "detail": detail, "source": source})

    ei = fact_pack.get("external_intelligence") or {}
    cc = fact_pack.get("compliance_checks") or {}
    gst_ok = cc.get("gst_filing_compliant")
    add("statutory_dues", "Default / delay in statutory dues (GST filings)",
        "na" if gst_ok is None else ("clear" if gst_ok else "flag"),
        f"GST filing status: {ei.get('gst_filing_status') or 'not on record'}", "GST")
    returns = sum(int(getattr(c, "cheque_returns", 0) or 0) for c in company_data.get("conduct") or [])
    bsa = fact_pack.get("bank_statement_analysis") or {}
    if company_data.get("conduct") or bsa.get("available"):
        bounced = returns > 0 or bool(bsa.get("cheque_returns_found"))
        add("cheque_returns", "Cheque / ECS returns", "flag" if bounced else "clear",
            f"{returns} return(s) in the statements on record" if returns else
            ("Returns found in the bank statement" if bounced else "No returns in the statements on record"),
            "Bank statements")
    else:
        add("cheque_returns", "Cheque / ECS returns", "na", "No bank statements on record", "Bank statements")
    sma, dpd = ei.get("crilc_sma_flag"), ei.get("bureau_dpd_status")
    if sma is None and dpd is None:
        add("bureau_stress", "Overdues / SMA with other lenders", "na", "No bureau or CRILC report on record",
            "Bureau / CRILC")
    else:
        stressed = (sma not in (None, "", "None", "NA", "Standard", False)) or str(dpd or "").lower() not in ("", "0", "none", "nil", "standard", "current")
        add("bureau_stress", "Overdues / SMA with other lenders", "flag" if stressed else "clear",
            f"CRILC SMA: {sma or '—'}; bureau DPD: {dpd or '—'}", "Bureau / CRILC")
    if truth.get("status") == "bad":
        add("revenue_mismatch", "Revenue not supported by GST / bank data", "flag", truth.get("summary", ""),
            "Revenue truth check")
    elif truth.get("checks"):
        add("revenue_mismatch", "Revenue not supported by GST / bank data", "clear", truth.get("summary", ""),
            "Revenue truth check")
    eq = {m["id"]: m for m in (quality.get("metrics") or [])}
    if "other_income_share" in eq:
        m = eq["other_income_share"]
        add("non_operating_profit", "Profit dependent on non-operating income",
            "flag" if m["status"] == "bad" else "clear", f"{m['label']}: {m['display']}", "Earnings quality")
    periods = sorted(company_data.get("financials") or {})
    ocfs = [_ocf(_items(company_data["financials"][p])) for p in periods[-2:]]
    if len(ocfs) == 2 and all(o is not None for o in ocfs):
        add("negative_ocf", "Negative operating cash flow two years running",
            "flag" if all(o < 0 for o in ocfs) else "clear", f"OCF {', '.join(_cr(o) for o in ocfs)}", "Cash flow")
    stale = [e for e in fact_pack.get("validation_exceptions") or [] if "STALE" in str(e.get("code") or "")]
    add("stale_financials", "Delay in submission of financial statements", "flag" if stale else "clear",
        stale[0].get("description") if stale else "Latest audited statements are current", "Validation engine")
    if "receivables_gap" in eq:
        m = eq["receivables_gap"]
        add("receivables_decoupled", "Receivables growing well ahead of sales (channel stuffing / evergreening)",
            "flag" if m["status"] == "bad" else "clear", f"{m['display']} ({m['basis']})", "Earnings quality")
    _forensic(company_data, fact_pack, add)
    flags = [i for i in ind if i["status"] == "flag"]
    return {"available": True, "indicators": ind, "flags": len(flags),
            "checked": sum(1 for i in ind if i["status"] != "na"), "not_checked": sum(1 for i in ind if i["status"] == "na"),
            "status": "bad" if len(flags) >= 2 else "warn" if flags else "good"}


_BENEISH_INPUTS = ("trade_receivables", "revenue_operating", "total_assets", "current_assets", "net_fixed_assets",
                   "depreciation", "pat", "total_debt")


def _forensic(company_data: dict, fact_pack: dict, add) -> None:
    """Forensic signals, each only when its inputs are on record — a missing line item is 'not checked',
    never a red flag (the forensic engine reads a missing value as zero)."""
    periods = sorted(company_data.get("financials") or {})
    if len(periods) >= 2:
        cur, pri = (dict(_items(company_data["financials"][p])) for p in periods[-2:][::-1])
        missing = sorted({k for k in _BENEISH_INPUTS for d in (cur, pri) if not d.get(k)}
                         | ({"operating cash flow"} if _ocf(cur) is None else set()))
        if missing:
            add("forensic_beneish", "Earnings manipulation (Beneish M-score)", "na",
                f"Not computable — not on record for both years: {', '.join(missing)}", "Forensic engine")
        else:
            from src.engines.fraud_detection_engine import compute_beneish_m_score
            cur["operating_cash_flow"] = _ocf(cur)
            m, _ = compute_beneish_m_score(cur, pri)
            add("forensic_beneish", "Earnings manipulation (Beneish M-score)",
                "na" if m is None else ("flag" if m > -1.78 else "clear"),
                f"M-score {m:.2f} (threshold −1.78)" if m is not None else "Not computable", "Forensic engine")
    ra = fact_pack.get("ratio_analysis") or {}
    z = ((ra.get(max(ra)) or {}).get("altman_z_score") or {}).get("value") if ra else None
    if z is not None:
        add("distress", "Financial distress (Altman Z)", "flag" if z < 1.81 else "clear",
            f"Altman Z {z:.2f} ({'distress' if z < 1.81 else 'grey' if z < 2.99 else 'safe'} zone)", "Ratio engine")
    directors = company_data.get("directors") or []
    if any("independent" in str(getattr(d, "designation", "")).lower() for d in directors):
        indep = sum(1 for d in directors if "independent" in str(getattr(d, "designation", "")).lower())
        share = indep / len(directors)
        add("board_independence", "Board independence below one-third", "flag" if share < 1 / 3 else "clear",
            f"{indep} of {len(directors)} directors independent", "Directors on record")
    else:
        add("board_independence", "Board independence below one-third", "na",
            "Director independence is not recorded in the data", "Directors on record")


def build(company_data: dict, fact_pack: dict) -> dict:
    """The quality blocks for the fact pack."""
    financials = company_data.get("financials") or {}
    eq = earnings_quality(financials)
    truth = revenue_truth(company_data, financials)
    return {"debt_capacity": debt_capacity(financials, company_data.get("facility"), fact_pack.get("policy_thresholds"),
                                           fact_pack.get("financial_projections"), fact_pack.get("drawing_power")),
            "earnings_quality": eq, "revenue_truth": truth,
            "ews_indicators": ews_indicators(company_data, fact_pack, truth, eq)}
