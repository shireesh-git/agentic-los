"""
Risk Maker workspace (LOS Phase 2a): the credit case, laid out as the Risk Maker tabs.

Pure presentation over the credit-intelligence outputs — fact pack (deterministic
engines), M4 repayment, M5 resilience, M6 reassessment and the composed CAM.
Nothing here re-derives a financial figure: ratios come from the ratio engine,
security cover from the collateral analysis, conditions from M6.

The bank's own models are not connected in this demo. Where the wireframe needs
them (internal MLRA rating scale and sub-scores, PD / LGD / expected loss, compliance
due dates), the values are SYNTHETIC, produced by a fixed demo mapping, and every
one is labelled ``synthetic_demo`` so it can never be read as bank evidence.

Tabs: Customer Info, Financial Statements, Risk Rating, Project Info, Security &
Collateral, Terms & Covenants, Pricing & RAROC, ESMS / ESDD, Decision Signoff.
Every field has a stable ``id`` (tab.section.label) so the analyst can confirm or
override it (see LosService.review_fields).
"""

from __future__ import annotations

import re
from typing import Optional

from src.engines.cam_composer import _PRIMARY_SECURITY, _Ctx, _covenants, _flat_kpis, fmt
from src.engines.data_provenance import NOT_AVAILABLE

VIEW_VERSION = "los_risk_maker/v1"
RISK_MAKER_STEPS = ("ip_risk_maker", "ap_risk_maker")

# ── Demo mappings (synthetic; the bank's MLRA / PD models are not connected) ──
_MLRA_SCALE = {"A": "IR-2 (Low risk)", "B": "IR-4 (Moderate risk)", "C": "IR-6 (Average risk)",
               "D": "IR-8 (High risk)", "E": "IR-10 (Very high risk)"}
_DEMO_PD_PCT = {"A": 0.5, "B": 1.5, "C": 4.0, "D": 10.0, "E": 25.0}
_DEMO_LGD_SECURED_PCT, _DEMO_LGD_UNSECURED_PCT = 35.0, 45.0
# Demo pricing grid (synthetic): spread over the benchmark by risk grade, cost of funds, opex and capital.
_DEMO_SPREAD_BPS = {"A": 75, "B": 125, "C": 175, "D": 250, "E": 350}
_DEMO_BENCHMARK = ("1-year MCLR", 8.40)
_DEMO_COST_OF_FUNDS_PCT, _DEMO_OPEX_PCT, _DEMO_CAPITAL_PCT = 7.20, 0.50, 12.0
_DEMO_HURDLE_RAROC_PCT = 15.0
_DECISION_MAP = {"SUPPORTED": "Approved", "SUPPORTED_WITH_CONDITIONS": "Conditionally Approved",
                 "REDUCED_MODIFIED": "Conditionally Approved (modified amount / structure)",
                 "DEFERRED": "Deferred", "NOT_SUPPORTED": "Rejected"}
DEMO_NOTE = ("Demo mapping — the bank's MLRA rating and PD / LGD models are not connected; "
             "these values are synthetic and for illustration only.")


def _f(label, value, provenance, source="", unit=""):
    """A field: formatted value with its provenance class."""
    if value in (None, "", [], {}):
        return {"label": label, "value": NOT_AVAILABLE, "provenance": "unavailable", "source": source}
    shown = fmt(value, unit) if (unit or isinstance(value, (int, float))) and not isinstance(value, bool) else value
    return {"label": label, "value": shown, "provenance": provenance, "source": source}


def _fields(title, fields, note=""):
    return {"kind": "fields", "title": title, "fields": fields, "note": note}


def _table(title, columns, rows, provenance, source="", note="", empty=""):
    return {"kind": "table", "title": title, "columns": columns, "rows": rows, "provenance": provenance,
            "source": source, "note": note, "empty": empty or NOT_AVAILABLE}


def _text(title, lines, provenance, source=""):
    return {"kind": "text", "title": title, "lines": [x for x in lines if x], "provenance": provenance, "source": source}


# ─── Tabs ────────────────────────────────────────────────────────────────────

def _financials(c: _Ctx) -> dict:
    fs = c.fp.get("financial_summary") or {}
    per, growth = fs.get("periods") or {}, fs.get("growth_by_period") or {}
    cls = c.cls("financial_summary")
    lines = [("Total revenue", "revenue_cr", "cr"), ("EBITDA", "ebitda_cr", "cr"), ("EBITDA margin", "ebitda_margin_pct", "pct"),
             ("PAT", "pat_cr", "cr"), ("Total assets", "total_assets_cr", "cr"), ("Total debt", "total_debt_cr", "cr"),
             ("Net worth", "net_worth_cr", "cr"), ("Operating cash flow", "operating_cash_flow_cr", "cr")]
    statements = _table("Key financials", ["Particulars"] + c.periods,
                        [[label] + [fmt(per[p].get(key), unit) for p in c.periods] for label, key, unit in lines],
                        cls, "financial statements as reported (margin from the ratio engine)")
    ratios = [("Debt / Equity", "debt_to_equity", "x"), ("DSCR", "dscr", "x"), ("Current ratio", "current_ratio", "x"),
              ("Interest coverage", "interest_coverage_ratio", "x"), ("RoCE", "roce", "fraction"),
              ("Debt / EBITDA", "debt_to_ebitda", "x"), ("OCF / Debt", "ocf_to_debt", "fraction")]
    ratio_table = _table("Key ratios", ["Ratio"] + c.periods,
                         [[label] + [fmt(c.ratio(p, key), unit) for p in c.periods] for label, key, unit in ratios],
                         "calculated", "ratio engine (financial analysis agent)")
    growth_table = _table("Growth", ["Measure"] + c.periods[1:],
                          [[label] + [fmt((growth.get(p) or {}).get(key), "pct") for p in c.periods[1:]]
                           for label, key in (("Revenue growth", "revenue_yoy_pct"), ("EBITDA growth", "ebitda_yoy_pct"),
                                              ("Total debt growth", "total_debt_yoy_pct"))],
                          "calculated", "financial analysis (growth metrics)")
    latest = per.get(c.latest) or {}
    other = _fields("Other financial information", [
        _f("Latest audited year", c.latest, cls, "financial_summary"),
        _f("Contingent liabilities", None, "unavailable", "financial statements"),
        _f("Project cost / means of finance", None, "unavailable", "facility details"),
        _f("Revenue CAGR", fs.get("revenue_cagr_pct"), "calculated", f"financial analysis ({fs.get('cagr_basis', '')})", "pct"),
        _f("Capex (latest year)", latest.get("capex_cr"), cls, "financial_summary", "cr"),
    ])
    remarks = _text("Financial remarks", [c.rpy.get("summary")] + [f"{x['concern']}: {x['evidence']}"
                                                                    for x in (c.rpy.get("concerns") or [])[:3]],
                    "derived", "repayment assessment (M4)")
    return {"id": "financials", "title": "Financial Statements",
            "sections": [statements, ratio_table, growth_table, other, remarks]}


def _grade(c: _Ctx) -> Optional[str]:
    pol = (c.fp.get("policy_decisions") or {}).get("tier3_recommendation") or {}
    return pol.get("risk_grade") or c.case.get("risk_grade")


def _loss_inputs(c: _Ctx) -> tuple:
    """(grade, demo PD %, demo LGD %, exposure) — shared by the rating and pricing tabs."""
    grade = _grade(c)
    amount = (c.fr.get("recommended_cr") if c.fr.get("recommended_cr") not in (None, 0)
              else (c.fp.get("facility_details") or {}).get("amount_requested_cr"))
    hard_cover = ((c.rpy.get("secondary_repayment_source") or {}).get("metrics") or {}).get("hard_security_cover")
    lgd = _DEMO_LGD_SECURED_PCT if (hard_cover or 0) >= 1 else _DEMO_LGD_UNSECURED_PCT
    return grade, _DEMO_PD_PCT.get(grade), lgd, amount


def _rule(c: _Ctx, code: str) -> dict:
    return next((r for r in c.case.get("tier1_decisions") or [] if (r.get("rule_code") or r.get("rule")) == code), {})


def _customer(c: _Ctx, context: dict) -> dict:
    bp, cs = c.fp.get("borrower_profile") or {}, c.fp.get("case_summary") or {}
    ei, pep = c.fp.get("external_intelligence") or {}, c.fp.get("pep_screening") or {}
    cls_b = c.cls("borrower_profile")
    info = _fields("Customer information", [
        _f("Name of applicant", bp.get("company_name"), cls_b, "borrower_profile"),
        _f("Constitution", "Listed company" if bp.get("listed_exchange") else "Unlisted company", cls_b, "borrower_profile"),
        _f("CIN", bp.get("cin"), cls_b, "borrower_profile"),
        _f("PAN", bp.get("pan"), cls_b, "borrower_profile"),
        _f("Date of incorporation", bp.get("date_of_incorporation"), cls_b, "borrower_profile"),
        _f("Registered address", bp.get("registered_address"), cls_b, "borrower_profile"),
        _f("Relationship", {"NTB": "New-to-bank", "ETB": "Existing customer"}.get(str(cs.get("case_type")).upper(),
                                                                                  cs.get("case_type")),
           c.cls("case_summary"), "case_summary"),
        _f("Relationship manager", context.get("relationship_manager"), "source", "LOS application"),
    ])
    kyc, active = _rule(c, "HR_KYC_COMPLETE"), _rule(c, "HR_COMPANY_ACTIVE")
    wilful = _rule(c, "HR_WILFUL_DEFAULTER")
    kyc_status = {"pass": "Verified", "fail": "Incomplete", "not_verified": "Pending verification"}.get(kyc.get("result"))
    others = context.get("other_applications") or []
    checks = _fields("KYC & verification", [
        _f("KYC status", kyc_status, "derived", f"policy rule HR_KYC_COMPLETE — {kyc.get('details', '')}"),
        _f("Credit bureau score", ei.get("bureau_score"), c.cls("external_intelligence"), "external_intelligence"),
        _f("Watchlist / wilful-defaulter check",
           {"pass": "Clear", "fail": "Flagged", "not_verified": "Not verified"}.get(wilful.get("result")),
           "derived", f"policy rule HR_WILFUL_DEFAULTER — {wilful.get('details', '')}"),
        _f("MCA verification",
           {"pass": "Active", "fail": "Not active", "not_verified": "Not verified"}.get(active.get("result")),
           "derived", f"policy rule HR_COMPANY_ACTIVE — {active.get('details', '')}"),
        _f("GSTIN verification", ei.get("gst_filing_status") and f"Filing status: {ei['gst_filing_status']}",
           c.cls("external_intelligence"), "external_intelligence"),
        _f("PAN verification (NSDL)", None, "unavailable", "NSDL check not connected"),
        _f("CERSAI check", None, "unavailable", "CERSAI search not connected"),
        _f("CBS dedupe", None, "unavailable", "core banking system not connected"),
        _f("LOS dedupe", f"{len(others)} other application(s) for this borrower" if others else "No other applications",
           "derived", "LOS applications"),
        _f("AML screening", None, "unavailable", "AML system not connected"),
        _f("Sanctions screening", f"{len(pep.get('sanctions_hits') or [])} match(es)" if pep else None, "derived",
           "PEP / sanctions screening (in-code reference list)"),
        _f("Politically exposed person", (f"{len(pep.get('pep_hits') or [])} match(es) of "
                                          f"{pep.get('total_persons_screened', 0)} screened") if pep else None,
           "derived", "PEP screening (in-code reference list)"),
        _f("Negative news check", "Verified feed reviewed" if (c.fp.get("web_crawl_news") or {}).get("verified") else None,
           "source" if (c.fp.get("web_crawl_news") or {}).get("verified") else "unavailable", "web_crawl_news"),
    ])
    directors = (c.fp.get("management_profile") or {}).get("directors") or []
    board = _table("Directors & key management", ["Name", "DIN", "Designation", "Promoter"],
                   [[d.get("name"), d.get("din"), d.get("designation"), "Yes" if d.get("is_promoter") else "No"]
                    for d in directors], c.cls("management_profile"), "management_profile")
    return {"id": "customer", "title": "Customer Info", "sections": [info, checks, board]}


def _project(c: _Ctx) -> dict:
    fd, cs = c.fp.get("facility_details") or {}, c.fp.get("case_summary") or {}
    proj = c.fp.get("financial_projections") or {}
    facility = _fields("Facility and project", [
        _f("Facility type", str(fd.get("facility_type") or "").replace("_", " ").title() or None,
           c.cls("facility_details"), "facility_details"),
        _f("Project type", None, "unavailable", "facility details"),
        _f("Sector / activity", cs.get("subsector") or cs.get("sector"), c.cls("case_summary"), "case_summary"),
        _f("Purpose", fd.get("purpose"), c.cls("facility_details"), "facility_details"),
        _f("Project cost", None, "unavailable", "facility details"),
        _f("Means of finance", None, "unavailable", "facility details"),
        _f("Promoter contribution", None, "unavailable", "facility details"),
        _f("Commercial operations date", None, "unavailable", "facility details"),
    ])
    kpis = c.fp.get("sector_kpis") or c.fp.get("infra_metrics") or {}
    key = "sector_kpis" if c.fp.get("sector_kpis") else "infra_metrics"
    operating = _table("Operating / project indicators", ["Area", "Measure", "Value", "Source"], _flat_kpis(kpis)[:30],
                       c.cls(key), key, empty="Borrower-specific operating or project indicators: " + NOT_AVAILABLE + ".")
    outlook = _table("Projections (projection engine)", ["Year", "Basis", "Revenue", "EBITDA", "PAT"],
                     [[y.get("year"), y.get("basis"), fmt(y.get("revenue_cr"), "cr"), fmt(y.get("ebitda_cr"), "cr"),
                       fmt(y.get("pat_cr"), "cr")] for y in proj.get("projected_years") or []] if proj.get("available") else [],
                     "calculated", "projection engine",
                     "Projected coverage ratios are not relied on; resilience is assessed on the latest audited year.")
    return {"id": "project", "title": "Project Info", "sections": [facility, operating, outlook]}


def _pricing(c: _Ctx) -> dict:
    grade, pd, lgd, amount = _loss_inputs(c)
    pricing = c.fp.get("facility_pricing") or {}
    spread = _DEMO_SPREAD_BPS.get(grade)
    benchmark, base = _DEMO_BENCHMARK
    roi = round(base + spread / 100, 2) if spread is not None else None
    el_rate = round(pd * lgd / 100, 2) if pd is not None else None
    raroc = (round((roi - _DEMO_COST_OF_FUNDS_PCT - el_rate - _DEMO_OPEX_PCT) / _DEMO_CAPITAL_PCT * 100, 1)
             if roi is not None and el_rate is not None else None)
    rate = _fields("Rate of interest — demo pricing grid", [
        _f("Benchmark", f"{benchmark} {base:.2f}%", "synthetic_demo", "demo benchmark rate"),
        _f("Spread for the risk grade", f"{spread} bps" if spread is not None else None, "synthetic_demo",
           f"demo spread grid by risk grade ({grade or '—'})"),
        _f("Rate of interest", roi, "synthetic_demo", "benchmark + spread", "pct"),
        _f("Concession", "0 bps", "synthetic_demo", "none proposed (demo)"),
        _f("Effective rate of interest", roi, "synthetic_demo", "rate of interest − concession", "pct"),
        _f("Processing fee (standard card)", pricing.get("processing_fee"), "template", "bank rate card"),
        _f("Commitment charge (standard card)", pricing.get("commitment_charge"), "template", "bank rate card"),
    ], note=("Pricing grid is synthetic for the demo: spreads by risk grade over an illustrative benchmark. "
             "The bank's pricing and RAROC models are not connected."))
    rar = _fields("RAROC — demo", [
        _f("Cost of funds", _DEMO_COST_OF_FUNDS_PCT, "synthetic_demo", "demo cost of funds", "pct"),
        _f("Expected loss rate", el_rate, "synthetic_demo", "demo PD × LGD (Risk Rating tab)", "pct"),
        _f("Operating cost", _DEMO_OPEX_PCT, "synthetic_demo", "demo operating cost", "pct"),
        _f("Economic capital", _DEMO_CAPITAL_PCT, "synthetic_demo", "demo capital allocation", "pct"),
        _f("RAROC", raroc, "synthetic_demo", "(ROI − cost of funds − EL − opex) ÷ capital", "pct"),
        _f("Hurdle RAROC", _DEMO_HURDLE_RAROC_PCT, "synthetic_demo", "demo hurdle", "pct"),
        _f("Meets hurdle", None if raroc is None else ("Yes" if raroc >= _DEMO_HURDLE_RAROC_PCT else "No"),
           "synthetic_demo", "RAROC vs hurdle (demo)"),
        _f("Exposure priced", amount, "derived", "recommended (else requested) amount", "cr"),
    ], note="All RAROC inputs are demo assumptions; the result illustrates the calculation only.")
    return {"id": "pricing", "title": "Pricing & RAROC", "sections": [rate, rar]}


def _esms(c: _Ctx) -> dict:
    esg = c.fp.get("esg_regulatory") or {}
    sector = (c.fp.get("case_summary") or {}).get("sector")
    sector_risk = (esg.get("environmental") or {}).get("sector_risk")
    category = {"High": "A", "Medium": "B", "Low": "C"}.get(sector_risk)
    social = esg.get("social") or {}
    screening = _fields("E&S categorisation", [
        _f("Sector", str(sector or "").replace("_", " ").title() or None, c.cls("case_summary"), "case_summary"),
        _f("Sector E&S risk", sector_risk, "derived", "rule on the borrower's sector (not a borrower assessment)"),
        _f("E&S category", f"Category {category}" if category else None, "derived",
           "rule: sector risk High → A, Medium → B, Low → C"),
        _f("ESDD required", "Yes" if category in ("A", "B") else ("No" if category else None), "derived",
           "rule: Category A / B need environmental and social due diligence"),
        _f("ESDD status", "Not started" if category in ("A", "B") else None, "derived", "LOS application"),
    ])
    evidence = _fields("E&S evidence", [
        _f("Environmental clearances", None, "unavailable", "borrower documents"),
        _f("Pollution-control consents", None, "unavailable", "borrower documents"),
        _f("Employees", social.get("employee_count"), c.cls("borrower_profile"), "borrower_profile"),
        _f("EPFO compliance", social.get("epfo_compliant"), "source", "EPFO payload"),
        _f("Labour disputes", social.get("labor_disputes"), "source", "borrower disclosures"),
        _f("Board / governance observations", (esg.get("governance") or {}).get("audit_observations"), "source",
           "audit report"),
    ])
    return {"id": "esms", "title": "ESMS / ESDD", "sections": [screening, evidence]}


def _rating(c: _Ctx) -> dict:
    pol = (c.fp.get("policy_decisions") or {}).get("tier3_recommendation") or {}
    scores = (c.fp.get("policy_decisions") or {}).get("tier2_risk_scores") or {}
    grade = pol.get("risk_grade") or c.case.get("risk_grade")
    bp = c.fp.get("borrower_profile") or {}
    sector = (c.fp.get("case_summary") or {}).get("sector")
    facility_type = (c.fp.get("facility_details") or {}).get("facility_type")
    model = ("MLRA Project Finance" if facility_type == "project_finance" else
             "MLRA Infrastructure" if sector == "infrastructure" else "MLRA Corporate")
    scoring = _fields("Scoring model (credit-intelligence engine)", [
        _f("Risk grade", grade, "derived", "policy engine tier 2"),
        _f("Composite score", pol.get("composite_score") or c.case.get("composite_score"), "derived", "policy engine tier 2"),
        _f("Financial score", scores.get("financial_score") or c.case.get("financial_score"), "derived", "policy engine"),
        _f("Conduct score", scores.get("conduct_score") or c.case.get("conduct_score"), "derived", "policy engine"),
        _f("Governance score", scores.get("governance_score") or c.case.get("governance_score"), "derived", "policy engine"),
        _f("Market score", scores.get("market_score") or c.case.get("market_score"), "derived", "policy engine"),
        _f("System recommendation", str(pol.get("recommendation") or c.case.get("recommendation") or "").replace("_", " ").title(),
           "derived", "policy engine tier 3"),
    ])
    mlra = _fields("Internal rating (MLRA) — demo mapping", [
        _f("Risk rating model", model, "synthetic_demo", "demo mapping by sector / facility"),
        _f("Industry risk score", scores.get("market_score") or c.case.get("market_score"), "synthetic_demo",
           "demo mapping ← market score"),
        _f("Business risk score", scores.get("conduct_score") or c.case.get("conduct_score"), "synthetic_demo",
           "demo mapping ← conduct score"),
        _f("Management risk score", scores.get("governance_score") or c.case.get("governance_score"), "synthetic_demo",
           "demo mapping ← governance score"),
        _f("Financial risk score", scores.get("financial_score") or c.case.get("financial_score"), "synthetic_demo",
           "demo mapping ← financial score"),
        _f("Internal risk rating", _MLRA_SCALE.get(grade), "synthetic_demo", "demo mapping ← risk grade"),
    ], note=DEMO_NOTE)
    rating = str(bp.get("credit_rating") or "")
    external = _fields("External rating", [
        _f("External credit rating", rating.split("/")[0].strip() or None, c.cls("borrower_profile"), "borrower_profile"),
        _f("Rating agency", bp.get("rating_agency"), c.cls("borrower_profile"), "borrower_profile"),
        _f("Outlook", rating.split("/", 1)[1].strip() if "/" in rating else None, c.cls("borrower_profile"), "borrower_profile"),
    ])
    grade, pd, lgd, amount = _loss_inputs(c)
    el = round(amount * pd / 100 * lgd / 100, 2) if (pd is not None and amount) else None
    loss = _fields("Probability of default and expected loss — demo", [
        _f("Probability of default", pd, "synthetic_demo", "demo PD by risk grade", "pct"),
        _f("Loss given default", lgd, "synthetic_demo",
           "demo LGD: 35% when hard security covers the limit, else 45%", "pct"),
        _f("Exposure at default", amount, "derived", "recommended (else requested) amount", "cr"),
        _f("Expected loss", el, "synthetic_demo", "PD × LGD × EAD on the demo PD / LGD", "cr"),
    ], note=DEMO_NOTE)
    remarks = _text("Risk remarks", [f"{r['risk']} ({r['severity'].lower()}, {r['status'].lower()}): {r['why']}"
                                     for r in (c.rea.get("key_risks") or [])[:5]], "derived", "credit reassessment (M6)")
    return {"id": "rating", "title": "Risk Rating", "sections": [scoring, mlra, external, loss, remarks]}


def _security(c: _Ctx) -> dict:
    ca = c.fp.get("collateral_analysis") or {}
    cls = c.cls("collateral_analysis")
    items = ca.get("collaterals") or []
    primary = [x for x in items if _PRIMARY_SECURITY.search(f"{x.get('type')} {x.get('description')}")]
    collateral = [x for x in items if x not in primary]
    cols = ["Type", "Description", "Market value", "Forced-sale value", "Valued on", "Charge"]

    def rows(xs):
        return [[x.get("type"), x.get("description"), fmt(x.get("market_value_cr"), "cr"),
                 fmt(x.get("forced_sale_value_cr"), "cr"), x.get("valuation_date") or "—",
                 str(x.get("encumbrance") or "—").title()] for x in xs]

    sec = (c.rpy.get("secondary_repayment_source") or {}).get("metrics") or {}
    cover = _fields("Security cover", [
        _f("Total market value", ca.get("total_market_value_cr"), cls, "collateral_analysis", "cr"),
        _f("Total forced-sale value", ca.get("total_forced_sale_value_cr"), cls, "collateral_analysis", "cr"),
        _f("Cover on market value", ca.get("coverage_ratio_market"), "calculated", "collateral_analysis", "x"),
        _f("Cover on forced-sale value", ca.get("coverage_ratio_fsv"), "calculated", "collateral_analysis", "x"),
        _f("Hard-security cover (excl. current assets)", sec.get("hard_security_cover"), "calculated",
           "repayment assessment (M4)", "x"),
        _f("Secondary repayment source", (c.rpy.get("secondary_repayment_source") or {}).get("adequacy"), "derived",
           "repayment assessment (M4)"),
    ])
    dp = c.fp.get("drawing_power") or {}
    dp_table = _table("Drawing power", ["Component", "Value", "Margin", "Drawing power"],
                      [[x["name"], fmt(x["value_cr"], "cr"), fmt(x["margin_pct"], "pct"), fmt(x["dp_cr"], "cr")]
                       for x in dp.get("components") or []]
                      + ([["Total", "", "", fmt(dp.get("total_dp_cr"), "cr")]] if dp.get("components") else []),
                      "calculated", "drawing power computation", "Receivable ageing not available: all receivables counted.")
    guarantees = [x["item"] for x in c.rea.get("recommended_mitigants") or [] if "guarantee" in x["item"].lower()]
    extra = [x["item"] for x in c.rea.get("conditions_precedent") or [] if "security" in x["item"].lower()]
    proposed = _text("Proposed security enhancements", guarantees + extra, "derived", "credit reassessment (M6)")
    return {"id": "security", "title": "Security & Collateral", "sections": [
        _table("Primary security", cols, rows(primary), cls, "collateral_analysis"),
        _table("Collateral security", cols, rows(collateral), cls, "collateral_analysis"),
        cover, dp_table, proposed]}


def _terms(c: _Ctx) -> dict:
    def addresses(x):
        return c.addresses(x) or "—"

    conditions = ([["Condition precedent", x["item"], addresses(x), "Before first disbursement", "Pending"]
                   for x in c.rea.get("conditions_precedent") or []]
                  + [["Condition subsequent", x["item"], addresses(x), "Post disbursement (per condition)", "Pending"]
                     for x in c.rea.get("conditions_subsequent") or []]
                  + [["Mitigant", x["item"], addresses(x), "At sanction", "Pending"]
                     for x in c.rea.get("recommended_mitigants") or []])
    fin, ops, mon = _covenants(c)
    frequency = {"Credit policy": "Annual (audited accounts)", "Credit reassessment": "As stated in the covenant"}
    covenants = ([[x, basis, frequency.get(basis, "—")] for x, basis in fin]
                 + [[x, basis, "Quarterly"] for x, basis in ops])
    breaches = (c.scenario("base") or {}).get("policy_breaches") or []
    deviations = _fields("Deviations", [
        _f("Deviation applicable", "Yes" if (breaches or c.fr.get("deviation_route_required")) else "No", "derived",
           "policy engine / credit reassessment"),
        _f("Deviation description", "; ".join(f"{b['label']} {b['value']} vs {b['limit_type']} {b['limit']}"
                                              for b in breaches) or None, "calculated", "resilience assessment (base case)"),
        _f("Deviation route", "Required — reassessed recommendation differs from the system recommendation"
           if c.fr.get("deviation_route_required") else "Not required", "derived", "credit reassessment (M6)"),
    ])
    return {"id": "terms", "title": "Terms & Covenants", "sections": [
        _table("Terms and conditions", ["Condition type", "Description", "Addresses", "Compliance by", "Status"],
               conditions, "derived", "credit reassessment (M6)",
               "Compliance-by timing is a standard demo default (template), to be set at sanction.",
               empty="No conditions are proposed."),
        _table("Financial and operational covenants", ["Covenant", "Basis", "Testing frequency"], covenants, "derived",
               "credit policy and credit reassessment", "Testing frequency is a standard demo default (template).",
               empty="No covenants are proposed."),
        _table("Monitoring requirements", ["Requirement", "Basis"], [[x, b] for x, b in mon], "derived",
               "credit reassessment (M6)", empty="No additional monitoring is proposed."),
        deviations]}


def _decision(c: _Ctx, final_cam: dict) -> dict:
    fd = c.fp.get("facility_details") or {}
    trail = (final_cam or {}).get("decision_trail") or {}
    hard = [r for r in c.case.get("tier1_decisions") or [] if r.get("result") in ("fail", "not_verified")]
    breaches = (c.scenario("base") or {}).get("policy_breaches") or []
    nature = (["Exposure limit"] if c.fr.get("deviation_route_required") else []) + \
             (["Covenant / ratio"] if breaches else []) + (["Hard rule"] if hard else [])
    decision = _fields("Recommended decision", [
        _f("Decision", _DECISION_MAP.get(c.rea.get("decision")), "derived", "credit reassessment (M6)"),
        _f("Reassessed recommendation", c.rea.get("decision_label"), "derived", "credit reassessment (M6)"),
        _f("Requested", c.fr.get("requested_cr") or fd.get("amount_requested_cr"), c.cls("facility_details"),
           "facility details", "cr"),
        _f("Recommended", c.fr.get("recommended_cr"), "derived", "credit reassessment (M6)", "cr"),
        _f("Structure", c.fr.get("structure"), "derived", "credit reassessment (M6)"),
        _f("Overall credit assessment", (c.rea.get("overall_credit_assessment") or {}).get("rating"), "derived",
           "credit reassessment (M6)"),
        _f("Sanctioning authority", (c.fp.get("approving_authority") or {}).get("name"), "derived",
           "delegation of powers"),
    ])
    approval = _fields("Approval note", [
        _f("Purpose for approval", fd.get("purpose"), c.cls("facility_details"), "facility details"),
        _f("Significant changes from last review", "First credit assessment for this application", "derived",
           "application history"),
        _f("Any deviations from policy", "Yes" if nature else "No", "derived", "policy engine / credit reassessment"),
        _f("Nature of deviation", ", ".join(nature) or None, "derived", "policy engine / credit reassessment"),
        _f("Hard rules failed or not verified", ", ".join(f"{r.get('rule_code')} ({r.get('result')})" for r in hard) or "None",
           "derived", "policy engine tier 1"),
    ])
    reasons = [re.sub(r"\(binding cap: [a-z_]+\)", f"(binding constraint: {c.binding_label()})", r)
               for r in c.rea.get("rationale") or []]
    rationale = _text("Final recommendation", [final_cam.get("headline", {}).get("decision_sentence") if final_cam else None]
                      + reasons, "derived", "credit reassessment (M6)")
    why = _table("Why this recommendation", ["Stage", "Outcome"],
                 [[s["label"], s["text"]] for s in trail.get("steps") or [] if s.get("status") != "unavailable"],
                 "derived", "decision trail", trail.get("outcome", ""))
    return {"id": "decision", "title": "Decision Signoff", "sections": [decision, approval, rationale, why]}


# ─── Entry point ─────────────────────────────────────────────────────────────

def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")


def _assign_ids(tabs: list[dict]) -> list[dict]:
    """Stable ids (tab.section.label) so analyst reviews survive a re-run."""
    for t in tabs:
        for sec in t["sections"]:
            sec["id"] = f"{t['id']}.{_slug(sec['title'])}"
            for f in sec.get("fields") or []:
                f["id"] = f"{sec['id']}.{_slug(f['label'])}"
    return tabs


def build_risk_maker_view(case: Optional[dict], final_cam: Optional[dict] = None,
                          context: Optional[dict] = None) -> dict:
    """The Risk Maker tabs for a credit case (``None`` → not yet assessed).

    ``context``: LOS facts the case does not hold (relationship manager, other applications)."""
    if not case or not case.get("fact_pack"):
        return {"available": False, "reason": "No credit assessment has been run for this borrower yet."}
    c = _Ctx(case)
    headline = (final_cam or {}).get("headline") or {}
    pol = (c.fp.get("policy_decisions") or {}).get("tier3_recommendation") or {}
    return {
        "available": True, "version": VIEW_VERSION,
        "run_id": case.get("run_id"), "run_at": case.get("run_at"), "narrative_mode": case.get("narrative_mode"),
        "headline": {"decision": c.rea.get("decision"), "decision_label": c.rea.get("decision_label"),
                     "requested_cr": c.fr.get("requested_cr"), "recommended_cr": c.fr.get("recommended_cr"),
                     "risk_grade": pol.get("risk_grade") or case.get("risk_grade"),
                     "composite_score": pol.get("composite_score") or case.get("composite_score"),
                     "repayment_capacity": c.rpy.get("repayment_capacity"),
                     "resilience_implication": headline.get("resilience_implication"),
                     "observations": len(c.obs), "investigations": len(c.inv), "challenges": len(c.chl)},
        "tabs": _assign_ids([_customer(c, context or {}), _financials(c), _rating(c), _project(c), _security(c),
                             _terms(c), _pricing(c), _esms(c), _decision(c, final_cam or {})]),
        "demo_note": DEMO_NOTE,
    }
