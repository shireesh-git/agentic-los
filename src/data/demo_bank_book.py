"""The bank's own records about a borrower, as labelled demo data (round 9: no CAM section without data).

A bank holds records no public source has: its existing facilities to the borrower, account conduct, covenant
testing, the core-banking summary, the CRILC report of all lenders' exposure, and the MCA charges register. For the
demo they are generated here from the borrower's data file, so they agree with its real audited figures:

    sizes        the bank's share of the borrower's audited borrowings (config data_sources.yaml →
                 demo_data.bank_book), split between term loans (long-term borrowings) and working capital
                 (short-term borrowings) as the balance sheet shows them
    conduct      account turnover from audited revenue; clean (no overdue, no cheque returns) for a real
                 company — a real company's stress shows in its real figures, never in invented events
    covenants    tested on the latest audited year against the bank's policy limits (rules.yaml) — the result
                 follows from the real figures
    CRILC        all lenders' exposure = audited borrowings; classification from the demo registry record
    charges      one charge per class of secured borrowing, in favour of "the lenders (demo)"

A new-to-bank borrower (facility case_type NTB) has no facilities, accounts, conduct or covenants with the bank:
only the CRILC report and the charges register, which exist whatever the relationship.

A fictional borrower keeps any story its data file already tells (ABC Group, Omega …); only missing blocks are
added. Every block says it is demo data.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

NOTE = "DEMO DATA: the bank's own records (not public). Generated from the borrower's audited figures."


def _g(obj, k):
    return obj.get(k) if isinstance(obj, dict) else getattr(obj, k, None)


def _latest(rec: dict) -> tuple[Optional[str], dict]:
    fins = rec.get("financials") or {}
    if not fins:
        return None, {}
    p = max(fins)
    return p, dict(_g(fins[p], "line_items") or {})


def _r(v, n=2):
    return round(float(v), n) if v is not None else None


def build(rec: dict, cfg: dict, policy: dict, status: str = "Standard") -> dict:
    """The demo bank-internal blocks for one borrower: existing_exposure, conduct, covenants, core_banking, crilc
    and charges. ``cfg``: demo_data.bank_book; ``policy``: rules.yaml policy_thresholds; ``status``: the demo
    registry's bureau classification (Standard for a real company)."""
    b = rec["borrower"]
    eid = _g(b, "entity_id")
    period, li = _latest(rec)
    fy = int(period[2:6]) if period and period[2:6].isdigit() else date.today().year
    ltd = float(li.get("long_term_debt") or 0)
    std = float(li.get("short_term_debt") or 0)
    debt = float(li.get("total_debt") or (ltd + std))
    revenue = float(li.get("revenue_operating") or 0)
    share = float(cfg.get("share_of_borrowings", 0.08))
    util = float(cfg.get("utilisation_pct", 72))
    # a borrower with little or no debt still banks with us: a working-capital line sized on revenue
    floor = revenue * float(cfg.get("min_limit_share_of_revenue", 0.01))
    tl = max(ltd * share, 0)
    wc = max(std * share, floor if debt * share < floor else 0)
    nfb_share = float(cfg.get("non_fund_based_share", 0.15))
    tier1 = float(cfg.get("tier1_capital_cr") or 0) or None
    cap = tier1 * float(cfg.get("max_share_of_tier1", 0.10)) if tier1 else None
    if cap and (tl + wc) * (1 + nfb_share) > cap:      # within the bank's single-borrower appetite
        k = cap / ((tl + wc) * (1 + nfb_share))
        tl, wc = tl * k, wc * k
    nfb = (tl + wc) * nfb_share
    clean = status == "Standard"

    exposure = []
    if tl > 0:
        exposure.append({"facility_id": f"EXP_{eid}_TL", "entity_id": eid, "facility_type": "term_loan",
                         "sanctioned_limit_cr": _r(tl / 0.85), "outstanding_cr": _r(tl), "utilization_pct": 85.0,
                         "overdue_days": 0, "classification": status})
    if wc > 0:
        exposure.append({"facility_id": f"EXP_{eid}_WC", "entity_id": eid, "facility_type": "working_capital",
                         "sanctioned_limit_cr": _r(wc / (util / 100)), "outstanding_cr": _r(wc),
                         "utilization_pct": util, "overdue_days": 0, "classification": status})

    turnover_q = revenue * float(cfg.get("banking_share_of_revenue", 0.12)) / 4
    conduct = [{"entity_id": eid, "period": f"Q{q}_FY{fy}", "avg_bank_balance_cr": _r(turnover_q * 0.06),
                "credit_turnover_cr": _r(turnover_q), "debit_turnover_cr": _r(turnover_q * 0.98),
                "cheque_returns": 0, "limit_utilization_pct": util, "overdue_instances": 0,
                "max_overdue_days": 0, "dpd_30_count": 0, "dpd_60_count": 0, "dpd_90_count": 0}
               for q in (1, 2, 3, 4)] if revenue else []

    covenants = []
    eq, ebitda = li.get("total_equity"), li.get("ebitda")
    ca, cl = li.get("current_assets"), li.get("current_liabilities")
    tests = [("Debt/Equity", "max_debt_to_equity", debt / eq if eq and eq > 0 else None, "<="),
             ("Debt/EBITDA", "max_debt_to_ebitda", debt / ebitda if ebitda and ebitda > 0 else None, "<="),
             ("Current ratio", "min_current_ratio", ca / cl if ca and cl else None, ">=")]
    for name, key, actual, way in tests:
        lim = policy.get(key)
        if lim is None or actual is None:
            continue
        ok = actual <= lim if way == "<=" else actual >= lim
        covenants.append({"entity_id": eid, "covenant_type": name, "required_value": f"{way}{lim:.2f}",
                          "actual_value": f"{actual:.2f}", "compliance_status": "compliant" if ok else "breached",
                          "period": period, "breach_details": "" if ok else
                          f"{name} {actual:.2f} against {way}{lim:.2f} on the audited {period} statements"})

    accounts = [{"account_number": f"DEMO-{eid}-{x['facility_type'][:2].upper()}", "entity_id": eid,
                 "facility_type": "TL" if x["facility_type"] == "term_loan" else "CC",
                 "sanction_limit_cr": x["sanctioned_limit_cr"], "outstanding_cr": x["outstanding_cr"],
                 "interest_rate_pct": float(cfg.get("rate_pct", 9.5)), "overdue_amount_cr": 0.0, "dpd": 0,
                 "asset_classification": status, "sanction_date": f"{fy - 3}-04-01",
                 "maturity_date": f"{fy + 4}-03-31", "repayment_frequency": "Monthly"} for x in exposure]
    funded = sum(x["outstanding_cr"] or 0 for x in exposure)
    core = {"note": NOTE, "loan_accounts": accounts,
            "bclc": {"total_fund_based_cr": _r(funded), "total_non_fund_based_cr": _r(nfb),
                     "total_exposure_cr": _r(funded + nfb),
                     "single_borrower_limit_pct": _r((funded + nfb) / tier1 * 100) if tier1 else None},
            "total_exposure_cr": _r(funded + nfb), "overall_asset_classification": status,
            "relationship_since": f"{fy - int(cfg.get('relationship_years', 6))}-04-01",
            "relationship_years": int(cfg.get("relationship_years", 6))}

    lenders = int(cfg.get("lenders", 6))
    crilc = {"note": NOTE, "borrower_name": _g(b, "company_name"), "cin": _g(b, "cin"), "pan": None,
             "credit_rating": _g(b, "credit_rating"), "reporting_date": f"31-Mar-{fy}",
             "reporting_bank": "All lenders (demo aggregation)", "bank_code": "DEMO",
             "sector": str(_g(b, "sector") or "").replace("_", " ").title(),
             "group": _g(rec.get("group"), "group_name") if rec.get("group") is not None else None,
             "fund_based": [x for x in (
                 {"facility_type": "Term loans (all lenders)", "sanction_limit_cr": _r(ltd / 0.85),
                  "outstanding_cr": _r(ltd), "dpd": 0, "classification": status, "sma_flag": "None" if clean else status,
                  "security": "As per the charges register"} if ltd else None,
                 {"facility_type": "Working capital (all lenders)", "sanction_limit_cr": _r(std / (util / 100)),
                  "outstanding_cr": _r(std), "dpd": 0, "classification": status, "sma_flag": "None" if clean else status,
                  "security": "Hypothecation of current assets"} if std else None) if x],
             "non_fund_based": [],
             "aggregate_exposure": {"total_fund_based_sanction": _r(ltd / 0.85 + std / (util / 100)),
                                    "total_fund_based_outstanding": _r(ltd + std), "total_non_fund_based_sanction": 0.0,
                                    "total_non_fund_based_outstanding": 0.0, "total_exposure_sanction": _r(ltd / 0.85 + std / (util / 100)),
                                    "total_exposure_outstanding": _r(ltd + std), "number_of_lenders": lenders},
             "sma_history": []}

    charges = {"note": NOTE, "source": "demo_mca_charges", "charges": [x for x in (
        {"charge_holder": "Term lenders (demo)", "amount_cr": _r(ltd / 0.85), "status": "Open",
         "assets": "Fixed assets (first pari-passu charge)"} if ltd else None,
        {"charge_holder": "Working capital lenders (demo)", "amount_cr": _r(std / (util / 100)), "status": "Open",
         "assets": "Current assets (hypothecation)"} if std else None) if x]}
    charges["count"] = len(charges["charges"])
    if str(getattr(_g(rec.get("facility") or {}, "case_type"), "value", _g(rec.get("facility") or {}, "case_type"))
           or "").upper() == "NTB":
        # new to this bank: no facilities, accounts, conduct or covenants with us — only what all lenders report
        exposure, conduct, covenants, core = [], [], [], {}
    return {"existing_exposure": exposure, "conduct": conduct, "covenants": covenants, "core_banking": core,
            "crilc": crilc, "charges": charges}
