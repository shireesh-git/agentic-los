"""Deterministic CAM parts for the streamlined CAM (Phase 1: C1, C2) — rendered from the fact pack, never written
by a model, so the page an approver decides on and the figures it quotes are exactly the engine's:

    render_decision_summary   the one-page Decision Summary that opens the CAM (the workflow replaces it at
                              download with its live version: challenges answered, deviations, confidence)
    render_debt_capacity      sustainable limit: every policy limit's capacity and the structure that passes
    render_earnings_quality   other-income share, cash conversion, accruals, receivables vs revenue
    render_revenue_truth      audited revenue against GST, bank credits and other filings
    render_ews                early-warning indicators at origination
    render_toc                contents of the streamlined CAM
"""

from __future__ import annotations

STATUS = {"good": "Within policy", "warn": "Close to the limit", "bad": "Outside policy", "na": "No policy limit"}
CHECK = {"good": "Agrees", "warn": "Differs", "bad": "Does not support", "na": "—"}
FLAG = {"flag": "FLAG", "clear": "Clear", "na": "Not checked"}

RATIOS = [("dscr", "DSCR", "min_dscr", "min"), ("interest_coverage_ratio", "Interest cover", "min_interest_coverage", "min"),
          ("debt_to_ebitda", "Debt / EBITDA", "max_debt_to_ebitda", "max"), ("current_ratio", "Current ratio", "min_current_ratio", "min"),
          ("tol_tnw", "TOL / TNW", "max_tol_tnw", "max"), ("debt_to_equity", "Debt / equity", "max_debt_to_equity", "max")]


def _h(text: str, level: int = 2) -> str:
    return f"{'#' * level} {text}\n\n"


def _row(cells) -> str:
    return "| " + " | ".join(str(c) for c in cells) + " |\n"


def _cr(v) -> str:
    try:
        return f"₹{float(v):,.2f} Cr"
    except (TypeError, ValueError):
        return "—"


def ratio_rows(fp: dict) -> list[dict]:
    ra = fp.get("ratio_analysis") or {}
    if not ra:
        return []
    period = max(ra)
    latest, limits, out = ra[period] or {}, fp.get("policy_thresholds") or {}, []
    for rid, label, key, way in RATIOS:
        v = (latest.get(rid) or {}).get("value")
        if v is None:
            continue
        lim = limits.get(key)
        st = "na"
        if lim is not None:
            st = (("bad" if v < lim else "warn" if v < lim * 1.1 else "good") if way == "min" else
                  ("bad" if v > lim or v < 0 else "warn" if v > lim * 0.9 else "good"))
        out.append({"label": label, "value": f"{v:.2f}x", "policy": f"{way} {lim:.2f}x" if lim is not None else "—",
                    "status": st, "period": period})
    return out


def render_decision_summary(fp: dict) -> str:
    cs, bp, fd = fp.get("case_summary") or {}, fp.get("borrower_profile") or {}, fp.get("facility_details") or {}
    pd = fp.get("policy_decisions") or {}
    t3, auth = pd.get("tier3_recommendation") or {}, fp.get("approving_authority") or {}
    out = _h("DECISION SUMMARY")
    out += "*Prepared from the engine's data — no model-written text on this page.*\n\n"
    out += _h("The Proposal", 3)
    out += _row(["Borrower", "Facility", "Amount", "Tenor", "Purpose"]) + _row(["---"] * 5)
    out += _row([bp.get("company_name") or "—", str(cs.get("facility_type") or "").replace("_", " ").title(),
                 _cr(fd.get("proposed_limit_cr") or cs.get("amount_requested_cr")),
                 f"{fd.get('tenor_months')} months" if fd.get("tenor_months") else "—", cs.get("purpose") or "—"]) + "\n"
    out += _h("Engine Verdict", 3)
    rules = pd.get("tier1_hard_rules") or []
    failed = [r for r in rules if r.get("result") == "fail"]
    unver = [r for r in rules if r.get("result") == "not_verified"]
    out += _row(["Item", "Result", "Basis"]) + _row(["---"] * 3)
    out += _row(["Recommendation", str(t3.get("recommendation") or "—").replace("_", " ").upper(), "Policy engine (tier 3)"])
    out += _row(["Internal rating", f"{t3.get('risk_grade') or '—'} (score {t3.get('composite_score') or '—'}/100)",
                 "Rating scorecard"])
    out += _row(["Hard rules", f"{len(failed)} failed · {len(unver)} not verifiable · "
                 f"{len(rules) - len(failed) - len(unver)} passed",
                 "; ".join(r.get("description") or r.get("rule") for r in failed) or "None failed"])
    out += _row(["Approving authority", auth.get("name") or "—",
                 ("Deviation route" if auth.get("deviation_route") else "Within delegation") + f" — {auth.get('basis') or ''}"])
    out += "\n"
    rows = ratio_rows(fp)
    if rows:
        out += _h(f"Key Ratios Against Policy ({rows[0]['period']})", 3)
        out += _row(["Ratio", "Value", "Policy", "Status"]) + _row(["---"] * 4)
        for r in rows:
            out += _row([r["label"], r["value"], r["policy"], STATUS[r["status"]]])
        out += "\n"
    dc = fp.get("debt_capacity") or {}
    eq, rt, ews = fp.get("earnings_quality") or {}, fp.get("revenue_truth") or {}, fp.get("ews_indicators") or {}
    out += _h("Size and Quality", 3)
    out += _row(["Check", "Result", "Detail"]) + _row(["---"] * 3)
    if dc.get("available"):
        out += _row(["Sustainable limit", _cr(dc["sustainable_cr"]),
                     f"Bound by {dc.get('binding') or '—'}; requested {_cr(dc['requested_cr'])} — "
                     + ("within policy" if dc["fits"] else "above it")])
    if eq.get("available"):
        out += _row(["Earnings quality", f"{eq['score']}/100", "; ".join(f"{m['label']} {m['display']}" for m in eq["metrics"])])
    out += _row(["Revenue truth", f"{rt['score']}/100" if rt.get("score") is not None else "Not verifiable",
                 rt.get("summary") or rt.get("reason") or "—"])
    if ews.get("available"):
        flagged = [i["label"] for i in ews["indicators"] if i["status"] == "flag"]
        out += _row(["Early-warning flags", f"{ews['flags']} of {ews['checked']} checked",
                     "; ".join(flagged) or "None"])
    out += "\n"
    risks = fp.get("key_risks") or []
    if risks:
        out += _h("Principal Risks", 3)
        for r in risks[:4]:
            out += f"- {r.get('detail') if isinstance(r, dict) else r}\n"
        out += "\n"
    return out


def render_debt_capacity(fp: dict) -> str:
    dc = fp.get("debt_capacity") or {}
    if not dc.get("available"):
        return ""
    out = _h("Debt Capacity and Sustainable Limit", 3)
    out += (f"Each policy limit, applied to the {dc['period']} figures at {dc['rate_pct']}% interest, gives the largest "
            f"new facility it allows. The smallest of them is the sustainable limit.\n\n")
    out += _row(["Policy limit", "Limit", "Largest facility allowed", "Basis"]) + _row(["---"] * 4)
    for c in dc["constraints"]:
        out += _row([c["label"] + (" (binding)" if c.get("binding") else ""), c["limit_display"],
                     _cr(c["max_amount_cr"]) if c["max_amount_cr"] >= 0 else "None — already outside", c["formula"]])
    out += f"\n**Sustainable limit:** {_cr(dc['sustainable_cr'])} (requested {_cr(dc['requested_cr'])}). "
    out += (dc.get("recommendation") or {}).get("text", "") + "\n\n"
    if len(dc.get("options") or []) > 1:
        out += _row(["Tenor", "Largest limit", "Binding limit", "Requested amount fits"]) + _row(["---"] * 4)
        for o in dc["options"]:
            out += _row([f"{o['tenor_months']} months", _cr(o["max_amount_cr"]), o["binding"] or "—",
                         "Yes" if o["fits"] else "No"])
        out += "\n"
    return out


def render_earnings_quality(fp: dict) -> str:
    eq = fp.get("earnings_quality") or {}
    if not eq.get("available"):
        return ""
    out = _h(f"Earnings Quality ({eq['period']}) — score {eq['score']}/100", 3)
    out += _row(["Measure", "Value", "Assessment", "Basis"]) + _row(["---"] * 4)
    for m in eq["metrics"]:
        out += _row([m["label"], m["display"], {"good": "Healthy", "warn": "Watch", "bad": "Concern"}[m["status"]], m["basis"]])
    return out + "\n"


def render_revenue_truth(fp: dict) -> str:
    rt = fp.get("revenue_truth") or {}
    if not rt.get("available"):
        return ""
    out = _h("Revenue Truth Check", 3)
    if not rt.get("checks"):
        return out + f"{rt.get('summary')}. Revenue is taken from the audited statements as reported.\n\n"
    out += f"Audited revenue {rt['period']}: {_cr(rt['audited_cr'])}. Score {rt['score']}/100 — {rt['summary']}.\n\n"
    out += _row(["Independent source", "Value", "Gap to audited", "Result", "Basis"]) + _row(["---"] * 5)
    for c in rt["checks"]:
        out += _row([c["source"], _cr(c["value_cr"]), f"{c['gap_pct']:+.1f}%", CHECK[c["status"]], c["basis"]])
    return out + "\n"


def render_ews(fp: dict) -> str:
    ews = fp.get("ews_indicators") or {}
    if not ews.get("available"):
        return ""
    out = _h(f"Early-Warning Indicators at Origination — {ews['flags']} flag(s), {ews['not_checked']} not checkable", 3)
    out += _row(["Indicator", "Result", "Detail", "Source"]) + _row(["---"] * 4)
    for i in ews["indicators"]:
        out += _row([i["label"], FLAG[i["status"]], i["detail"], i["source"]])
    return out + "\n"


TABLES = {"debt_capacity": render_debt_capacity, "earnings_quality": render_earnings_quality,
          "revenue_truth": render_revenue_truth, "ews": render_ews}


def render_toc(sections: list[dict]) -> str:
    out = _h("TABLE OF CONTENTS")
    for s in sections:
        if s["id"] in ("cover_page", "toc", "disclaimer"):
            continue
        out += f"{s['title']}  \n"
    return out + "\n---\n\n"
