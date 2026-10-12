"""
CAM Composer (M7) — the banker-facing 12-section Credit Appraisal Memorandum.

Composes the final CAM from the authoritative structured outputs, not by
summarising the 21 narrative sections:

  fact pack (deterministic engines, with data provenance)
  + M1 observations, M2 investigations, M3 challenges
  + M4 repayment, M5 stress, M6 reassessment & recommendation
  → 12 banking sections of facts, tables and short rule-written statements,
    grouped under sub-headings (blocks)

Every item carries a provenance class (data_provenance.CLASS_LABELS):
source / calculated / derived / synthetic_demo / template / unavailable / ai.
Text is written in credit-memorandum language; the system architecture shows
only in the provenance metadata. The 21-section narrative stays the analytical
layer: each composed section links to (and embeds, for drill-down) the
analytical sections it draws on. An optional LLM interpretation per section is
added on demand by services/cam_composer_narrator.py and is always labelled AI.

Also composed here, for the borrower workspace and the CAM: the credit journey
(stage availability) and the decision trail (why the recommendation was reached).
"""

from __future__ import annotations

import re
from typing import Optional

from src.engines.data_provenance import CLASS_LABELS, NOT_AVAILABLE, NOT_VERIFIED

COMPOSER_VERSION = "cam_composer/v2"

SECTIONS = [
    ("executive_summary", "Executive Summary & Credit Proposal", ["executive_summary"]),
    ("borrower_group", "Borrower, Group & Promoter Profile",
     ["borrower_profile", "group_shareholders", "directors_kmp"]),
    ("business_overview", "Business Profile & Purpose of Finance", ["project_details", "operational_kpis"]),
    ("industry_risk", "Industry, Business & Management Assessment", ["industry_analysis", "benchmarking"]),
    ("rating_history_conduct", "Banking, Credit History & External Rating",
     ["external_rating", "conduct", "core_banking"]),
    ("key_risks", "Key Credit Risks & Mitigants", ["risk_assessment"]),
    ("compliance_intelligence", "Conduct, Compliance & Due Diligence", ["compliance", "social_media"]),
    ("financials_repayment", "Financial Performance & Repayment Capacity", ["financial_analysis"]),
    ("projections_stress", "Financial Outlook & Resilience Assessment", ["financial_projections"]),
    ("facility_structure", "Credit Facilities & Structure", ["facility_assessment"]),
    ("security_covenants", "Security, Collateral & Covenants", ["security_collateral", "covenants"]),
    ("final_recommendation", "Sanction Terms, Conditions & Recommendation", ["recommendation", "terms_conditions"]),
]

# Heading → analytical section id (works for template and LLM headings). Order matters.
_HEADING_IDS = [
    (r"executive summary", "executive_summary"), (r"social media", "social_media"),
    (r"borrower profile", "borrower_profile"), (r"client background|business activity", "project_details"),
    (r"group compan|shareholder", "group_shareholders"), (r"directors|key management", "directors_kmp"),
    (r"operational analysis", "operational_kpis"), (r"peer comparison|benchmarking", "benchmarking"),
    (r"industry", "industry_analysis"), (r"external credit rating", "external_rating"),
    (r"risk assessment", "risk_assessment"), (r"compliance", "compliance"), (r"conduct", "conduct"),
    (r"banking relationship", "core_banking"), (r"projection", "financial_projections"),
    (r"financial analysis", "financial_analysis"), (r"facility", "facility_assessment"),
    (r"security|collateral", "security_collateral"), (r"terms, conditions & (financial )?covenants|covenant", "covenants"),
    (r"recommendation", "recommendation"), (r"terms & conditions", "terms_conditions"),
]

DECISION_SENTENCES = {
    "SUPPORTED": "The proposal is recommended for sanction as requested: {rec}.",
    "SUPPORTED_WITH_CONDITIONS": "The proposal is recommended for sanction of {rec}, subject to the conditions set out "
                                 "in this memorandum.",
    "REDUCED_MODIFIED": "The proposal is recommended in a modified form: {rec} against {req} requested, structured as "
                        "{structure}.",
    "DEFERRED": "A decision on the proposal is recommended to be deferred until the open due-diligence items are closed.",
    "NOT_SUPPORTED": "The proposal is not supported in its present form ({req} requested).",
}

# M6 stress-resilience status → credit implication (wording only; the status and figures come from M5/M6).
RESILIENCE_IMPLICATIONS = {
    "RESILIENT": "Repayment capacity remains within policy under the downside case, and debt service remains covered "
                 "under the severe downside case.",
    "FAILS DOWNSIDE": "Debt-servicing capacity falls below the policy minimum under the downside case.",
    "FAILS SEVERE": "Debt-servicing capacity becomes constrained under the severe downside case, where cash accruals "
                    "no longer fully cover debt service or interest.",
}

# M6 condition / mitigant 'addresses' labels → the observation rules they answer.
_ADDRESS_RULES = {
    "Receivable deterioration": {"WC_DETERIORATION", "RECEIVABLE_COLLECTION"},
    "Inventory build-up": {"INVENTORY_BUILDUP"},
    "Stressed repayment capacity": {"DEBT_SERVICING_PRESSURE"},
    "Leverage above policy": {"LEVERAGE_INCREASE"},
    "Earnings-to-cash conversion": {"EARNINGS_CASH_CONVERSION"},
    "Margin compression": {"MARGIN_COMPRESSION"},
    "Policy exceptions": {"POLICY_DEVIATION"},
}

_CASE_TYPES = {"NTB": "New-to-bank", "ETB": "Existing customer"}
_RULE_RESULT = {"pass": "Pass", "fail": "Fail", "not_verified": NOT_VERIFIED}
# Benchmark metric → (label, unit) for the peer table.
_BENCH = {"debt_to_ebitda": ("Debt / EBITDA", "x"), "interest_coverage_ratio": ("Interest coverage", "x"),
          "dscr": ("DSCR", "x"), "net_profit_margin": ("Net profit margin", "fraction"),
          "ebitda_margin": ("EBITDA margin", "fraction"), "return_on_equity": ("Return on equity", "fraction"),
          "return_on_assets": ("Return on assets", "fraction"), "roce": ("ROCE", "fraction"),
          "debtor_days": ("Debtor days", "days"), "inventory_days": ("Inventory days", "days"),
          "payable_days": ("Creditor days", "days"), "working_capital_cycle": ("Working capital cycle", "days"),
          "current_ratio": ("Current ratio", "x"), "debt_to_equity": ("Debt / Equity", "x"),
          "asset_turnover": ("Asset turnover", "x")}
_CAP_NAMES = {"interest_cover": "interest-coverage test", "interest_cover_downside": "downside interest-coverage test",
              "eligible_drawing_power": "eligible drawing-power test"}
_OPEN = ("OPEN", "IN_PROGRESS")


def _num(v) -> Optional[float]:
    if isinstance(v, bool) or v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def fmt(value, unit: str = "") -> str:
    v = _num(value)
    if v is None:
        return NOT_AVAILABLE if value in (None, "", [], {}) else str(value)
    if unit == "cr":
        return f"-₹{abs(v):,.2f} Cr" if v < 0 else f"₹{v:,.2f} Cr"
    if unit == "pct":
        return f"{v:.1f}%"
    if unit == "fraction":
        return f"{v * 100:.1f}%"
    if unit == "x":
        return f"{v:.2f}x"
    if unit == "days":
        return f"{v:.1f} days"
    return f"{v:,.2f}".rstrip("0").rstrip(".") if not float(v).is_integer() else f"{int(v):,}"


def _label(v) -> str:
    return str(v or "").replace("_", " ").strip()


def _title(v) -> str:
    s = _label(v)
    return s[:1].upper() + s[1:] if s else ""


def _fact(label, value, cls, source="", unit=""):
    if value in (None, "", [], {}):
        cls = "unavailable"
    return {"label": label, "value": fmt(value, unit) if unit or _num(value) is not None else (value or NOT_AVAILABLE),
            "provenance": cls, "source": source}


def _text(text, cls, source=""):
    return {"text": text, "provenance": cls, "source": source}


def _table(title, columns, rows, cls, source="", note=""):
    return {"title": title, "columns": columns, "rows": rows, "provenance": cls, "source": source, "note": note}


def _short(items: list[str], n: int = 2) -> str:
    items = [i for i in items if i]
    if not items:
        return "—"
    return "; ".join(items[:n]) + (f" (+{len(items) - n} more)" if len(items) > n else "")


class _Ctx:
    def __init__(self, case: dict):
        self.case = case
        self.fp = case.get("fact_pack") or {}
        self.prov = self.fp.get("data_provenance") or {}
        self.obs = case.get("observations") or []
        self.inv = case.get("investigations") or []
        self.chl = case.get("challenges") or []
        self.rpy = case.get("repayment_analysis") or {}
        self.stress = case.get("stress_test") or {}
        self.rea = case.get("reassessment") or {}
        fin = (self.fp.get("financial_summary") or {}).get("periods") or {}
        self.periods = sorted(fin)
        self.latest = self.periods[-1] if self.periods else None
        self.prior = self.periods[-2] if len(self.periods) >= 2 else None
        self.obs_by_id = {o["observation_id"]: o for o in self.obs}
        self.inv_by_id = {t["investigation_id"]: t for t in self.inv}
        self.chl_by_id = {c["challenge_id"]: c for c in self.chl}

    def cls(self, key: str, default: str = "derived") -> str:
        return (self.prov.get(key) or {}).get("class", default)

    def ratio(self, period, name):
        entry = ((self.fp.get("ratio_analysis") or {}).get(period) or {}).get(name)
        return _num(entry.get("value") if isinstance(entry, dict) else entry)

    def scenario(self, name):
        return next((s for s in self.stress.get("scenarios") or [] if s["scenario"] == name), {})

    def metric(self, scenario, key):
        return _num((self.scenario(scenario).get("stressed_metrics") or {}).get(key))

    @property
    def fr(self) -> dict:
        return self.rea.get("facility_recommendation") or {}

    @property
    def threshold(self) -> dict:
        return self.fp.get("policy_thresholds") or {}

    def binding_label(self) -> str:
        """The binding sizing test as a noun phrase, e.g. 'interest-coverage test (keeps … at the 2.0x policy minimum)'."""
        sizing = self.fr.get("sizing") or {}
        cap = next((c for c in sizing.get("caps") or [] if c.get("cap") == sizing.get("binding_cap")), None)
        name = _CAP_NAMES.get(sizing.get("binding_cap"), _label(sizing.get("binding_cap")) + " test")
        return f"{name} ({cap['label'][:1].lower() + cap['label'][1:]})" if cap and cap.get("label") else name

    def decision_sentence(self) -> str:
        template = DECISION_SENTENCES.get(self.rea.get("decision"))
        if not template:
            return "A reassessed recommendation is not available for this case."
        return template.format(rec=fmt(self.fr.get("recommended_cr"), "cr"), req=fmt(self.fr.get("requested_cr"), "cr"),
                               structure=_label(self.fr.get("structure")).rstrip(".").lower() or "structure unchanged")

    def mitigants_for(self, register_entry: dict) -> list[str]:
        rule = (self.obs_by_id.get(register_entry["observation_id"]) or {}).get("trigger", {}).get("rule_id")
        out = []
        for bucket in ("recommended_mitigants", "conditions_precedent", "conditions_subsequent"):
            for item in self.rea.get(bucket) or []:
                addresses = item.get("addresses") or []
                if any(rule in _ADDRESS_RULES.get(a, ()) or a in register_entry.get("investigation_ids", [])
                       for a in addresses):
                    out.append(item["item"])
        return out

    def addresses(self, item: dict) -> str:
        return ", ".join(f"Due diligence: {self.inv_by_id[a]['title']}" if a in self.inv_by_id else a
                         for a in item.get("addresses") or [])

    def resilience(self) -> dict:
        return ((self.rea.get("overall_credit_assessment") or {}).get("dimensions") or {}).get("stress_resilience") or {}


class _Sec:
    """Collects a section's content in sub-headed blocks."""

    def __init__(self):
        self.blocks: list[dict] = []
        self.findings: list[dict] = []
        self.block(None)

    def block(self, heading):
        self.blocks.append({"heading": heading, "statements": [], "facts": [], "tables": []})
        return self

    def text(self, text, cls, source=""):
        if text:
            self.blocks[-1]["statements"].append(_text(text, cls, source))
        return self

    def fact(self, label, value, cls, source="", unit=""):
        self.blocks[-1]["facts"].append(_fact(label, value, cls, source, unit))
        return self

    def table(self, title, columns, rows, cls, source="", note="", empty=None):
        """A table; with no rows, the `empty` sentence (if any) is written instead."""
        if rows:
            self.blocks[-1]["tables"].append(_table(title, columns, rows, cls, source, note))
        elif empty:
            self.text(empty, "unavailable" if cls != "derived" else "derived", source)
        return self

    def out(self) -> dict:
        blocks = [b for b in self.blocks if b["statements"] or b["facts"] or b["tables"]]
        return {"blocks": blocks, "findings": self.findings,
                "statements": [x for b in blocks for x in b["statements"]],
                "facts": [x for b in blocks for x in b["facts"]],
                "tables": [x for b in blocks for x in b["tables"]]}


def _finding(o: dict) -> dict:
    return {"kind": "observation", "id": o["observation_id"], "severity": o["severity"], "status": o["status"],
            "text": f"{o['title']}: {o['summary']}"}


# ─── 1. Executive summary & credit proposal ──────────────────────────────────

def _executive(c: _Ctx) -> dict:
    s = _Sec()
    cs, fd = c.fp.get("case_summary") or {}, c.fp.get("facility_details") or {}
    bp = c.fp.get("borrower_profile") or {}
    fr = c.fr
    pol = (c.fp.get("policy_decisions") or {}).get("tier3_recommendation") or {}
    cls_f = c.cls("facility_details")
    p, sec = c.rpy.get("primary_repayment_source") or {}, c.rpy.get("secondary_repayment_source") or {}
    existing = fd.get("existing_limit_cr")
    exposure = c.fp.get("existing_exposure") or []
    if existing is None and exposure:
        existing = sum(_num(e.get("sanctioned_cr")) or 0 for e in exposure)
    s.block("Credit proposal")
    s.fact("Borrower", bp.get("company_name") or c.case.get("company_name"), c.cls("borrower_profile"), "borrower_profile")
    s.fact("Sector", _title(cs.get("subsector") or cs.get("sector")), c.cls("case_summary"), "case_summary")
    s.fact("Relationship", _CASE_TYPES.get(str(cs.get("case_type", "")).upper(), cs.get("case_type")),
           c.cls("case_summary"), "case_summary")
    s.fact("Facility requested", f"{_title(fd.get('facility_type'))} of {fmt(fd.get('amount_requested_cr'), 'cr')}"
           if fd.get("amount_requested_cr") is not None else None, cls_f, "facility_details")
    if existing is not None:
        s.fact("Existing exposure with the bank", existing, cls_f, "facility_details / existing exposure", "cr")
    elif str(cs.get("case_type", "")).upper() == "NTB":
        s.fact("Existing exposure with the bank", "Nil (new-to-bank)", c.cls("case_summary"), "case_summary")
    else:
        s.fact("Existing exposure with the bank", None, "unavailable", "existing exposure")
    s.fact("Proposed exposure", fd.get("proposed_limit_cr") or fd.get("amount_requested_cr"), cls_f, "facility_details", "cr")
    s.fact("Purpose", fd.get("purpose"), cls_f, "facility_details")
    s.fact("Tenor", f"{fd['tenor_months']} months" if fd.get("tenor_months") else None, cls_f, "facility_details")
    s.fact("Proposed structure", fr.get("structure"), "derived", "credit reassessment")
    s.fact("Primary repayment source", f"{p.get('source')} — {_label(p.get('adequacy')).lower()}" if p else None,
           "derived", "repayment assessment")
    s.fact("Secondary repayment source", f"{sec.get('source')} — {_label(sec.get('adequacy')).lower()}" if sec else None,
           "derived", "repayment assessment")
    s.fact("Security", fd.get("collateral_type") or ", ".join(
        x.get("type", "") for x in (c.fp.get("collateral_analysis") or {}).get("collaterals") or []) or None,
        c.cls("collateral_analysis"), "facility_details / collateral")
    s.fact("Recommended decision", c.rea.get("decision_label"), "derived", "credit reassessment")
    s.fact("Recommended amount", fr.get("recommended_cr"), "derived", "credit reassessment", "cr")
    cps = c.rea.get("conditions_precedent") or []
    s.fact("Key conditions", f"{len(cps)} condition(s) precedent, {len(c.rea.get('conditions_subsequent') or [])} "
           f"condition(s) subsequent, {len(c.rea.get('recommended_mitigants') or [])} mitigant(s) — see Section 12"
           if c.rea.get("available") else None, "derived", "credit reassessment")

    s.block("Key concerns")
    s.table("Key concerns", ["Risk", "Severity", "Status after review"],
            [[r["risk"], r["severity"], _title(r["status"].lower())] for r in (c.rea.get("key_risks") or [])[:5]],
            "derived", "credit reassessment (risk register)",
            empty="No material credit concerns remain open after review.")

    s.block("Credit rationale")
    if c.rea.get("available"):
        s.text(c.decision_sentence(), "derived", "credit reassessment")
        if fr.get("recommended_cr") is not None and fr.get("requested_cr") is not None \
                and _num(fr["recommended_cr"]) < _num(fr["requested_cr"]):
            s.text(f"The supportable amount is set by the {c.binding_label()}.", "derived",
                   "credit reassessment (sizing)")
    if c.rpy.get("available"):
        s.text(f"Repayment capacity is assessed as {_label(c.rpy.get('repayment_capacity')).lower()} with "
               f"{_label(c.rpy.get('repayment_risk')).lower()} repayment risk; DSCR is {fmt(c.metric('base', 'dscr'), 'x')} "
               f"in the base case, {fmt(c.metric('downside', 'dscr'), 'x')} in the downside case and "
               f"{fmt(c.metric('severe', 'dscr'), 'x')} in the severe downside case (policy minimum "
               f"{fmt(c.threshold.get('min_dscr'), 'x')}).", "calculated", "repayment and resilience assessment")
    implication = RESILIENCE_IMPLICATIONS.get(c.resilience().get("status"))
    if implication:
        s.text(implication, "derived", "resilience assessment")
    counts = (c.rea.get("overall_credit_assessment") or {}).get("risk_status_counts") or {}
    if c.rea.get("available"):
        s.text(f"{len(c.obs)} credit risk(s) were identified; after due diligence and credit challenge, "
               f"{counts.get('UNRESOLVED', 0)} remain open, {counts.get('MITIGATED', 0)} are mitigated and "
               f"{counts.get('RESOLVED', 0)} are resolved.", "derived", "credit reassessment")
    if pol:
        s.text(f"The bank's scoring model places the borrower at risk grade {pol.get('risk_grade')} (composite score "
               f"{pol.get('composite_score')}) with a system recommendation to {_label(pol.get('recommendation'))}"
               + ("; adopting the reassessed recommendation therefore requires the deviation route."
                  if fr.get("deviation_route_required") else "."), "derived", "policy engine")
    return s.out()


# ─── 2. Borrower, group & promoter profile ───────────────────────────────────

def _borrower(c: _Ctx) -> dict:
    s = _Sec()
    bp, gp = c.fp.get("borrower_profile") or {}, c.fp.get("group_profile") or {}
    cls_b, cls_g = c.cls("borrower_profile"), c.cls("group_profile")
    s.block("Legal entity")
    s.fact("Company", bp.get("company_name"), cls_b, "borrower_profile")
    s.fact("Constitution", "Listed company (" + bp["listed_exchange"] + ")" if bp.get("listed_exchange")
           else "Unlisted company", cls_b, "borrower_profile")
    s.fact("CIN", bp.get("cin"), cls_b, "borrower_profile")
    s.fact("PAN", bp.get("pan"), cls_b, "borrower_profile")
    s.fact("Date of incorporation", bp.get("date_of_incorporation"), cls_b, "borrower_profile")
    s.fact("Registered office", bp.get("registered_address") or bp.get("registered_state"), cls_b, "borrower_profile")
    s.fact("Paid-up capital", bp.get("paid_up_capital_cr"), cls_b, "borrower_profile", "cr")
    s.fact("Employees", bp.get("employee_count"), cls_b, "borrower_profile")

    s.block("Ownership & promoters")
    s.fact("Promoter holding", gp.get("promoter_holding_pct"), cls_g, "group_profile", "pct")
    s.fact("Institutional holding", gp.get("institutional_holding_pct"), cls_g, "group_profile", "pct")
    s.fact("Public holding", gp.get("public_holding_pct"), cls_g, "group_profile", "pct")
    directors = (c.fp.get("management_profile") or {}).get("directors") or []
    s.table("Board & key management", ["Name", "DIN", "Designation", "Promoter", "Appointed"],
            [[d.get("name"), d.get("din"), d.get("designation"), "Yes" if d.get("is_promoter") else "No",
              d.get("date_of_appointment") or "—"] for d in directors],
            c.cls("management_profile"), "management_profile", empty=f"Promoter and management details: {NOT_AVAILABLE}.")

    s.block("Group structure")
    s.fact("Group", gp.get("group_name"), cls_g, "group_profile")
    tree = [e for e in (c.fp.get("corporate_hierarchy") or {}).get("hierarchy_tree") or []
            if e.get("company_name") and e.get("company_name") != bp.get("company_name")]
    s.table("Related entities", ["Entity", "Relationship", "Holding", "Sector"],
            [[e.get("company_name"), _title(e.get("relationship")), fmt(e.get("holding_pct"), "pct")
              if e.get("holding_pct") is not None else "—", _title(e.get("sector")) or "—"] for e in tree],
            c.cls("corporate_hierarchy"), "corporate_hierarchy",
            empty=f"Related group entities: {NOT_AVAILABLE}.")

    s.block("Banking relationship")
    case_type = str((c.fp.get("case_summary") or {}).get("case_type", "")).upper()
    exposure = c.fp.get("existing_exposure") or []
    if exposure:
        s.table("Existing facilities with the bank", ["Facility", "Sanctioned", "Outstanding", "Utilisation", "Classification"],
                [[_title(e.get("facility_type")), fmt(e.get("sanctioned_cr"), "cr"), fmt(e.get("outstanding_cr"), "cr"),
                  fmt(e.get("utilization_pct"), "pct"), e.get("classification") or "—"] for e in exposure],
                c.cls("existing_exposure"), "existing_exposure")
    elif case_type == "NTB":
        s.text("New-to-bank proposal: the borrower has no existing relationship or exposure with the bank.",
               c.cls("case_summary"), "case_summary")
    else:
        s.text(f"Existing banking relationship: {NOT_AVAILABLE}.", "unavailable", "existing_exposure")
    return s.out()


# ─── 3. Business profile & purpose of finance ────────────────────────────────

def _flat_kpis(kpis: dict) -> list[list]:
    rows = []
    for group, values in kpis.items():
        if not isinstance(values, dict):
            continue
        for key, value in values.items():
            if key == "source" or isinstance(value, (dict, list)) or value in (None, ""):
                continue
            rows.append([_title(group), _title(key), fmt(value), values.get("source", "")])
    return rows


def _business(c: _Ctx) -> dict:
    s = _Sec()
    cs, fd = c.fp.get("case_summary") or {}, c.fp.get("facility_details") or {}
    ia = c.fp.get("industry_analysis") or {}
    s.block("Nature of business")
    s.fact("Sector", _title(cs.get("sector")), c.cls("case_summary"), "case_summary")
    s.fact("Business activity", cs.get("subsector"), c.cls("case_summary"), "case_summary")
    if ia.get("business_description"):
        s.text(str(ia["business_description"]), c.cls("industry_analysis"), "industry_analysis")
    sector_note = ia.get("sector_reference_description")
    if sector_note:
        s.text("Sector reference description (not borrower-specific): " + str(sector_note), "template",
               "industry_analysis (sector reference text)")
    kpis = c.fp.get("sector_kpis") or c.fp.get("infra_metrics") or {}
    kpi_key = "sector_kpis" if c.fp.get("sector_kpis") else "infra_metrics"
    s.table("Operating profile", ["Area", "Measure", "Value", "Source"], _flat_kpis(kpis)[:24], c.cls(kpi_key), kpi_key)
    s.text(f"Products and services, customer and supplier profile, concentration and order book: {NOT_AVAILABLE}."
           if not kpis else f"Customer and supplier profile and concentration: {NOT_AVAILABLE}.",
           "unavailable", "case data")

    s.block("Working capital cycle")
    cols = ["Measure"] + ([c.prior] if c.prior else []) + ([c.latest] if c.latest else [])
    periods = [p for p in (c.prior, c.latest) if p]
    rows = [[label] + [fmt(c.ratio(p, key), "days") for p in periods]
            for label, key in (("Debtor days", "debtor_days"), ("Inventory days", "inventory_days"),
                               ("Creditor days", "payable_days"), ("Working capital cycle", "working_capital_cycle"))]
    if periods and any(c.ratio(p, "debtor_days") is not None for p in periods):
        s.table("Working capital cycle", cols, rows, "calculated", "ratio engine")
    else:
        s.text(f"Working capital cycle measures: {NOT_AVAILABLE}.", "unavailable", "ratio engine")

    s.block("Purpose of finance & end use")
    s.fact("Facility", _title(fd.get("facility_type")), c.cls("facility_details"), "facility_details")
    s.fact("Amount requested", fd.get("amount_requested_cr"), c.cls("facility_details"), "facility_details", "cr")
    s.fact("Purpose", fd.get("purpose"), c.cls("facility_details"), "facility_details")
    s.fact("End use of funds", None, "unavailable", "facility_details")
    s.text(f"Borrower-specific end-use statement: {NOT_AVAILABLE}; end use is to be certified by the borrower and "
           "monitored after disbursement.", "unavailable", "facility_details")
    return s.out()


# ─── 4. Industry, business & management assessment ───────────────────────────

def _industry(c: _Ctx) -> dict:
    s = _Sec()
    ia = c.fp.get("industry_analysis") or {}
    bs = c.fp.get("benchmark_summary") or {}
    rows = bs.get("benchmarks") or []
    worse = [r for r in rows if r.get("status") == "worse_than_peer"]
    better = [r for r in rows if r.get("status") == "better_than_peer"]

    s.block("Industry risk")
    overview = ia.get("industry_overview") or ia.get("sector_overview") or ia.get("overview")
    if overview and len(str(overview)) > 60:
        s.text("Sector reference note: " + str(overview)[:700], "template", "industry_analysis (sector reference text)")
    else:
        s.text(f"Sector outlook: {NOT_AVAILABLE}.", "unavailable", "industry_analysis")
    drivers, headwinds = ia.get("growth_drivers") or [], ia.get("headwinds") or []
    if drivers or headwinds:
        n = max(len(drivers), len(headwinds))
        s.table("Sector drivers and headwinds (reference)", ["Growth drivers", "Headwinds"],
                [[drivers[i] if i < len(drivers) else "", headwinds[i] if i < len(headwinds) else ""] for i in range(n)],
                "template", "industry_analysis (sector reference text)")
    if rows:
        s.text(f"Against {_label(bs.get('sector'))} peers ({bs.get('period')}), the borrower is better than the peer band "
               f"on {len(better)} measure(s), within it on {len(rows) - len(better) - len(worse)} and worse on "
               f"{len(worse)}.", "calculated", "benchmark engine")
        def bench(r):
            label, unit = _BENCH.get(r["metric"], (_title(r["metric"]), ""))
            return [label] + [fmt(r.get(k), unit) for k in ("borrower", "peer_p25", "peer_median", "peer_p75")]                 + [_title(r.get("severity"))]

        s.table("Measures weaker than peers", ["Measure", "Borrower", "Peer P25", "Peer median", "Peer P75", "Deviation"],
                [bench(r) for r in worse], "calculated", "benchmark engine")
    else:
        s.text("Sector peer benchmarks are not available for this borrower's sector.", "unavailable", "benchmark engine")
    news = c.fp.get("web_crawl_news") or {}
    s.text("Adverse or market news: " + ("verified news feed reviewed — see supporting analysis." if news.get("verified")
           else "not available (no verified news source connected)."),
           "source" if news.get("verified") else "unavailable", "web_crawl_news")
    signals = c.fp.get("market_signals") or []
    if signals:
        demo = c.cls("market_signals") == "synthetic_demo"
        s.table("Market signals", ["Date", "Headline", "Sentiment", "Source"],
                [[x.get("date"), x.get("headline"), x.get("sentiment"), x.get("source")] for x in signals],
                c.cls("market_signals"), "market_signals", "Synthetic demo data — not verified." if demo else "")

    s.block("Business risk")
    fs = c.fp.get("financial_summary") or {}
    growth = (fs.get("growth_by_period") or {}).get(c.latest) or {}
    latest = (fs.get("periods") or {}).get(c.latest) or {}
    prior = (fs.get("periods") or {}).get(c.prior) or {}
    if latest:
        s.text(f"Revenue {'grew' if (_num(growth.get('revenue_yoy_pct')) or 0) >= 0 else 'declined'} "
               f"{fmt(abs(_num(growth.get('revenue_yoy_pct')) or 0), 'pct')} in {c.latest}; EBITDA margin was "
               f"{fmt(latest.get('ebitda_margin_pct'), 'pct')} against {fmt(prior.get('ebitda_margin_pct'), 'pct')} in "
               f"{c.prior}." if growth.get("revenue_yoy_pct") is not None and c.prior
               else f"EBITDA margin was {fmt(latest.get('ebitda_margin_pct'), 'pct')} in {c.latest}.",
               "calculated", "financial analysis")
    strengths = c.fp.get("credit_strengths") or []
    s.table("Business strengths (rule-based)", ["Area", "Strength"],
            [[x.get("category"), x.get("detail")] for x in strengths], "derived", "credit_strengths")
    business_risks = [o for o in c.obs if o["trigger"]["rule_id"] in ("SECTOR_UNDERPERFORMANCE", "MARGIN_COMPRESSION",
                                                                       "WC_DETERIORATION", "INVENTORY_BUILDUP")]
    s.table("Business risks identified", ["Risk", "Severity", "Evidence"],
            [[o["title"], o["severity"], o["summary"]] for o in business_risks], "derived", "risk identification",
            empty="No business-risk observations were triggered.")
    s.text(f"Customer and supplier concentration and cyclicality: {NOT_AVAILABLE}.", "unavailable",
           "case data")

    s.block("Management & promoter assessment")
    directors = (c.fp.get("management_profile") or {}).get("directors") or []
    gp = c.fp.get("group_profile") or {}
    if directors:
        promoters = [d.get("name") for d in directors if d.get("is_promoter")]
        s.text(f"The board comprises {len(directors)} director(s) on record"
               + (f", of whom {len(promoters)} are promoters ({', '.join(promoters)})" if promoters else "")
               + (f"; promoter holding is {fmt(gp.get('promoter_holding_pct'), 'pct')}." if gp.get("promoter_holding_pct")
                  is not None else "."), c.cls("management_profile"), "management_profile")
    else:
        s.text(f"Management details: {NOT_AVAILABLE}.", "unavailable", "management_profile")
    pep = c.fp.get("pep_screening") or {}
    if pep:
        s.text(f"Screening of {pep.get('total_persons_screened', 0)} promoter(s)/director(s) returned "
               f"{len(pep.get('pep_hits') or [])} PEP match(es); overall screening risk "
               f"{_label(pep.get('overall_risk')).lower() or 'not assessed'}.", "derived", "PEP screening")
    site = c.fp.get("site_visit_data") or {}
    s.text("Management interaction / site visit: " + ("recorded — see supporting analysis." if site.get("available")
           else "not available; to be completed before sanction."), "source" if site.get("available") else "unavailable",
           "site_visit_data")
    return s.out()


# ─── 5. Banking, credit history & external rating ────────────────────────────

def _rating(c: _Ctx) -> dict:
    s = _Sec()
    bp, ei = c.fp.get("borrower_profile") or {}, c.fp.get("external_intelligence") or {}
    cr, ca = c.fp.get("crilc_exposure") or {}, c.fp.get("conduct_analysis") or {}
    pol = (c.fp.get("policy_decisions") or {}).get("tier3_recommendation") or {}
    s.block("Internal & external rating")
    s.fact("Internal risk grade (scoring model)", f"{pol.get('risk_grade')} — composite score {pol.get('composite_score')}"
           if pol.get("risk_grade") else None, "derived", "policy engine")
    rating = str(bp.get("credit_rating") or "")
    s.fact("External rating", rating.split("/")[0].strip() or None, c.cls("borrower_profile"), "borrower_profile")
    s.fact("Rating agency", bp.get("rating_agency"), c.cls("borrower_profile"), "borrower_profile")
    s.fact("Rating outlook", rating.split("/", 1)[1].strip() if "/" in rating else None, c.cls("borrower_profile"),
           "borrower_profile")
    s.fact("Recent rating action", ei.get("rating_action"), c.cls("external_intelligence"), "external_intelligence")

    s.block("Credit bureau & CRILC")
    cls_e = c.cls("external_intelligence")
    s.fact("Bureau score", ei.get("bureau_score"), cls_e, "external_intelligence")
    s.fact("Bureau repayment status", ei.get("bureau_dpd_status"), cls_e, "external_intelligence")
    s.fact("Total exposure (bureau)", ei.get("bureau_total_exposure_cr"), cls_e, "external_intelligence", "cr")
    s.fact("Number of lenders (bureau)", ei.get("bureau_total_lenders"), cls_e, "external_intelligence")
    s.fact("SMA / asset classification (CRILC)", ei.get("crilc_asset_classification") or ei.get("crilc_sma_flag"),
           cls_e, "external_intelligence")
    fb = cr.get("fund_based_facilities") or []
    nfb = cr.get("non_fund_based_facilities") or []
    if fb or nfb:
        demo = c.cls("crilc_exposure") == "synthetic_demo"
        s.table("Borrowings from the banking system (CRILC)",
                ["Facility", "Type", "Sanctioned", "Outstanding", "DPD", "Classification"],
                [[_title(x.get("facility_type")), "Fund-based", fmt(x.get("sanction_limit_cr"), "cr"),
                  fmt(x.get("outstanding_cr"), "cr"), x.get("dpd", "—"), x.get("classification") or "—"] for x in fb]
                + [[_title(x.get("facility_type")), "Non-fund-based", fmt(x.get("sanction_limit_cr"), "cr"),
                    fmt(x.get("outstanding_cr"), "cr"), x.get("dpd", "—"), x.get("classification") or "—"] for x in nfb],
                c.cls("crilc_exposure"), "crilc_exposure", "Synthetic demo data — not verified." if demo else "")
        sma = cr.get("sma_history") or []
        if sma:
            s.table("SMA history", ["Month", "SMA-0", "SMA-1", "SMA-2", "Classification"],
                    [[x.get("month"), x.get("sma_0"), x.get("sma_1"), x.get("sma_2"), x.get("classification")]
                     for x in sma], c.cls("crilc_exposure"), "crilc_exposure")
    else:
        s.text(f"CRILC reporting for the borrower: {NOT_AVAILABLE}.", "unavailable", "crilc_exposure")

    s.block("Existing borrowings")
    latest = ((c.fp.get("financial_summary") or {}).get("periods") or {}).get(c.latest) or {}
    s.fact(f"Total debt per financial statements ({c.latest})", latest.get("total_debt_cr"),
           c.cls("financial_summary"), "financial_summary", "cr")
    exposure = c.fp.get("existing_exposure") or []
    s.table("Existing exposure with the bank", ["Facility", "Sanctioned", "Outstanding", "Utilisation", "Overdue days",
                                                "Classification"],
            [[_title(e.get("facility_type")), fmt(e.get("sanctioned_cr"), "cr"), fmt(e.get("outstanding_cr"), "cr"),
              fmt(e.get("utilization_pct"), "pct"), e.get("overdue_days"), e.get("classification")] for e in exposure],
            c.cls("existing_exposure"), "existing_exposure",
            empty="No existing exposure with the bank (new-to-bank) or none reported.")

    s.block("Banking conduct")
    if ca.get("available"):
        s.fact("Quarters reviewed", ca.get("quarters_analyzed"), c.cls("conduct_analysis"), "conduct_analysis")
        s.fact("Average limit utilisation", ca.get("avg_utilization_pct"), c.cls("conduct_analysis"), "conduct_analysis", "pct")
        s.fact("Utilisation trend", _title(ca.get("utilization_trend")), c.cls("conduct_analysis"), "conduct_analysis")
        s.fact("Cheque returns (total)", ca.get("total_cheque_returns"), c.cls("conduct_analysis"), "conduct_analysis")
        s.fact("Maximum overdue days", ca.get("max_dpd_overall"), c.cls("conduct_analysis"), "conduct_analysis")
        s.table("Account conduct by quarter", ["Period", "Average balance", "Credit turnover", "Utilisation", "Cheque returns",
                                               "Max overdue days"],
                [[r.get("period"), fmt(r.get("avg_balance_cr"), "cr"), fmt(r.get("credit_turnover_cr"), "cr"),
                  fmt(r.get("utilization_pct"), "pct"), r.get("cheque_returns"), r.get("max_overdue_days")]
                 for r in ca.get("records") or []], c.cls("conduct_analysis"), "conduct_analysis")
    else:
        s.text("Account conduct with the bank: not available" + (f" ({ca['note']})." if ca.get("note") else "."),
               "unavailable", "conduct_analysis")
    return s.out()


# ─── 6. Key credit risks & mitigants ─────────────────────────────────────────

def _residual(entry: dict, mitigants: list[str]) -> str:
    if entry["status"] == "RESOLVED":
        return "Closed"
    if entry["status"] == "MITIGATED":
        return "Accepted — mitigated"
    return "Open — subject to conditions" if mitigants else "Open"


def _risks(c: _Ctx) -> dict:
    s = _Sec()
    register = c.rea.get("risk_register") or []
    counts = (c.rea.get("overall_credit_assessment") or {}).get("risk_status_counts") or {}
    if register:
        s.text(f"{len(c.obs)} credit risk(s) were identified from the financial, benchmark, validation and policy "
               f"assessment. After due diligence and credit challenge, {counts.get('UNRESOLVED', 0)} remain open, "
               f"{counts.get('MITIGATED', 0)} are mitigated and {counts.get('RESOLVED', 0)} are resolved.",
               "derived", "risk identification and credit reassessment")
    rows = []
    for r in register:
        o = c.obs_by_id.get(r["observation_id"]) or {}
        dd = [f"{c.inv_by_id[i]['title']} ({_label(c.inv_by_id[i]['status']).lower()})" for i in r.get("investigation_ids") or []
              if i in c.inv_by_id]
        ch = [f"{c.chl_by_id[i]['title']} ({_label(c.chl_by_id[i]['status']).lower()})" for i in r.get("challenge_ids") or []
              if i in c.chl_by_id]
        mit = c.mitigants_for(r)
        rows.append([r["title"], o.get("summary", ""), r["severity"], _short(dd), _short(ch), _short(mit, 2),
                     _residual(r, mit)])
    s.table("Risk and mitigant matrix", ["Risk", "Evidence", "Severity", "Due diligence", "Credit challenge", "Mitigant",
                                         "Residual risk"], rows, "derived",
            "risk identification, due diligence, credit challenge and credit reassessment",
            "Residual risk reflects the review status: open risks are addressed only once the linked conditions are met.",
            empty="No credit risk observations were triggered for this proposal.")
    s.block("Challenges to the proposal")
    s.table("Credit challenges", ["Challenge", "Area", "Severity", "Status", "Required response"],
            [[x["title"], x["category"], x["severity"], _title(x["status"].lower()), _short(x.get("required_response") or [], 1)]
             for x in c.chl], "derived", "credit challenge review",
            empty="The proposal was reviewed and no credit challenges were raised.")
    s.findings = [{"kind": "challenge", "id": x["challenge_id"], "severity": x["severity"], "status": x["status"],
                   "text": x["challenge"]} for x in c.chl if x["status"] == "OPEN"][:4]
    return s.out()


# ─── 7. Conduct, compliance & due diligence ──────────────────────────────────

def _compliance(c: _Ctx) -> dict:
    s = _Sec()
    exc = c.fp.get("validation_exceptions") or []
    codes = {e.get("code") for e in exc}
    ei = c.fp.get("external_intelligence") or {}
    s.block("KYC & documentation")
    rules = {r.get("rule_code") or r.get("rule"): r for r in c.case.get("tier1_decisions") or []}
    for code, label in (("HR_KYC_COMPLETE", "KYC (policy hard rule)"), ("HR_COMPANY_ACTIVE", "MCA company status (policy hard rule)")):
        r = rules.get(code)
        if r:
            s.fact(label, f"{_RULE_RESULT.get(r.get('result'), r.get('result'))} — {r.get('details', '')}",
                   "derived", "policy engine (evidence-based hard rule)")
    for code, label in (("POL_MISSING_BOARD_RES", "Board resolution"),
                        ("POL_MISSING_COLLATERAL_DOCS", "Security / collateral documents")):
        s.fact(label, "Not on file — exception raised" if code in codes else "No exception raised", "derived",
               "validation engine (document checklist)")

    s.block("Screening")
    pep = c.fp.get("pep_screening") or {}
    s.fact("PEP screening", f"{len(pep.get('pep_hits') or [])} match(es) of {pep.get('total_persons_screened', 0)} "
           f"person(s) screened" if pep else None, "derived", "PEP screening (in-code reference list)")
    s.fact("Sanctions screening", f"{len(pep.get('sanctions_hits') or [])} match(es)" if pep else None, "derived",
           "PEP screening (in-code reference list)")
    s.fact("Overall screening risk", _title(pep.get("overall_risk")) or None, "derived", "PEP screening")
    news = c.fp.get("web_crawl_news") or {}
    s.fact("Adverse media", "Verified feed reviewed" if news.get("verified") else None,
           "source" if news.get("verified") else "unavailable", "web_crawl_news")
    sm = c.fp.get("social_media_analysis") or {}
    s.fact("Social-media intelligence", "Demo profile only — not verified" if sm else None,
           c.cls("social_media_analysis"), "social_media_analysis")
    s.fact("Fraud indicators", None, "unavailable", "fraud scan (run on request; not part of this assessment)")

    s.block("Statutory & regulatory")
    s.fact("MCA status", ei.get("mca_status") if ei.get("mca_status") not in (None, "Unknown") else None,
           c.cls("external_intelligence"), "external_intelligence")
    s.fact("GST filing status", ei.get("gst_filing_status"), c.cls("external_intelligence"), "external_intelligence")
    s.fact("GST turnover (FY2024)", ei.get("gst_fy2024_turnover_cr"), c.cls("external_intelligence"),
           "external_intelligence", "cr")
    checks = c.fp.get("compliance_checks") or {}
    items = (checks.get("items") or checks.get("checks") or []) if isinstance(checks, dict) else (checks or [])
    s.table("Statutory checks", ["Check", "Status", "Detail"],
            [[i.get("check") or i.get("name"), i.get("status"), i.get("details") or i.get("detail")]
             for i in items if isinstance(i, dict)], "derived", "compliance checks (MCA, GST, bureau)")

    s.block("Due diligence")
    s.table("Due diligence register", ["Priority", "Item", "Triggered by", "Evidence requested", "Status", "Finding"],
            [[t["priority"], t["title"], t.get("observation_title") or t.get("observation_id"),
              len(t.get("required_evidence") or []), _title(t["status"].lower()),
              (t.get("review") or {}).get("note") or ("Awaiting evidence" if t["status"] in _OPEN else "—")]
             for t in c.inv], "derived", "due diligence register",
            empty="No due-diligence items were required for this proposal.")
    s.table("Data validation exceptions", ["Code", "Severity", "Description"],
            [[e.get("code"), _title(e.get("severity")), e.get("description")] for e in exc], "derived", "validation engine",
            empty="No data validation exceptions were raised.")
    demo_keys = [k for k, v in c.prov.items() if v.get("class") == "synthetic_demo"]
    if demo_keys:
        s.block("Basis of information")
        s.text("The following inputs are synthetic demonstration data and are not verified: "
               + ", ".join(_label(k) for k in demo_keys) + ".", "derived", "data provenance")
    return s.out()


# ─── 8. Financial performance & repayment capacity ───────────────────────────

def _financials(c: _Ctx) -> dict:
    s = _Sec()
    fs = c.fp.get("financial_summary") or {}
    per = fs.get("periods") or {}
    growth = fs.get("growth_by_period") or {}
    s.block("Financial performance")
    lines = [("Revenue", "revenue_cr", "cr"), ("EBITDA", "ebitda_cr", "cr"), ("EBITDA margin", "ebitda_margin_pct", "pct"),
             ("PAT", "pat_cr", "cr"), ("Operating cash flow", "operating_cash_flow_cr", "cr"),
             ("Total debt", "total_debt_cr", "cr"), ("Net worth", "net_worth_cr", "cr")]
    s.table("Key financials", ["Particulars"] + c.periods,
            [[label] + [fmt(per[p].get(key), unit) for p in c.periods] for label, key, unit in lines],
            c.cls("financial_summary"), "financial statements as reported", empty="Financial statements are not available.")
    if len(c.periods) > 1:
        s.table("Growth and cash conversion", ["Measure"] + c.periods[1:],
                [[label] + [fmt(growth.get(p, {}).get(key), "pct") for p in c.periods[1:]]
                 for label, key in (("Revenue growth", "revenue_yoy_pct"), ("EBITDA growth", "ebitda_yoy_pct"),
                                    ("Operating cash flow growth", "ocf_yoy_pct"), ("Receivables growth", "receivables_yoy_pct"),
                                    ("Total debt growth", "total_debt_yoy_pct"))]
                + [["OCF / PAT"] + [fmt(growth.get(p, {}).get("ocf_to_pat"), "x") for p in c.periods[1:]]],
                "calculated", "financial analysis (growth metrics)",
                f"Revenue CAGR {fmt(fs.get('revenue_cagr_pct'), 'pct')} ({fs.get('cagr_basis', '')})."
                if fs.get("revenue_cagr_pct") is not None else "")

    s.block("Key credit metrics")
    bm = {r["metric"]: r for r in (c.fp.get("benchmark_summary") or {}).get("benchmarks") or []}
    thr = c.threshold

    def lim(key, op, suffix=""):
        return f"{op} {thr[key]}{suffix}" if thr.get(key) is not None else "—"

    ratio_rows = [("EBITDA margin", "ebitda_margin", "fraction", lim("min_ebitda_margin_pct", "≥", "%")),
                  ("Debt / EBITDA", "debt_to_ebitda", "x", lim("max_debt_to_ebitda", "≤")),
                  ("Interest coverage", "interest_coverage_ratio", "x", lim("min_interest_coverage", "≥")),
                  ("DSCR", "dscr", "x", lim("min_dscr", "≥")),
                  ("Debt / Equity", "debt_to_equity", "x", lim("max_debt_to_equity", "≤")),
                  ("Current ratio", "current_ratio", "x", lim("min_current_ratio", "≥")),
                  ("Debtor days", "debtor_days", "days", lim("max_debtor_days", "≤")),
                  ("Inventory days", "inventory_days", "days", "—"),
                  ("OCF / Debt", "ocf_to_debt", "fraction", "—")]
    periods = [p for p in (c.prior, c.latest) if p]
    rows = [["Revenue growth"] + [fmt((growth.get(p) or {}).get("revenue_yoy_pct"), "pct") for p in periods] + ["—", "—"]]
    for label, key, unit, policy in ratio_rows:
        median = (bm.get(key) or {}).get("peer_median")
        rows.append([label] + [fmt(c.ratio(p, key), unit) for p in periods]
                    + [fmt(median, unit) if median is not None else "—", policy])
    s.table("Key ratios", ["Measure"] + periods + ["Peer median", "Policy"], rows, "calculated",
            "ratio engine; peers: benchmark engine; limits: credit policy")

    s.block("Repayment capacity")
    if c.rpy.get("available"):
        p, sec = c.rpy.get("primary_repayment_source") or {}, c.rpy.get("secondary_repayment_source") or {}
        s.text(c.rpy.get("summary", ""), "calculated", "repayment assessment")
        s.fact("Repayment capacity", _title(_label(c.rpy.get("repayment_capacity")).lower()), "derived", "repayment assessment")
        s.fact("Repayment risk", _title(_label(c.rpy.get("repayment_risk")).lower()), "derived", "repayment assessment")
        s.fact("Primary repayment source", f"{p.get('source')} — {_label(p.get('adequacy')).lower()}", "derived",
               "repayment assessment")
        s.fact("Secondary repayment source", f"{sec.get('source')} — {_label(sec.get('adequacy')).lower()}", "derived",
               "repayment assessment")
        s.table("Positive factors", ["Factor", "Evidence"],
                [[x["factor"], x["evidence"]] for x in c.rpy.get("positive_factors") or []], "derived",
                "repayment assessment")
        s.table("Repayment concerns", ["Concern", "Severity", "Evidence"],
                [[x["concern"], x["severity"], x["evidence"]] for x in c.rpy.get("concerns") or []], "derived",
                "repayment assessment", empty="No repayment concerns were identified.")
    else:
        s.text("A repayment assessment is not available for this case.", "unavailable", "repayment assessment")
    return s.out()


# ─── 9. Financial outlook & resilience assessment ────────────────────────────

def _projections(c: _Ctx) -> dict:
    s = _Sec()
    proj = c.fp.get("financial_projections") or {}
    s.block("Financial outlook")
    if proj.get("available"):
        s.table("Projections", ["Year", "Basis", "Revenue", "EBITDA", "PAT"],
                [[y.get("year"), y.get("basis"), fmt(y.get("revenue_cr"), "cr"), fmt(y.get("ebitda_cr"), "cr"),
                  fmt(y.get("pat_cr"), "cr")] for y in proj.get("projected_years") or []], "calculated",
                "projection engine",
                "Projected coverage ratios are not relied on: the projection engine treats a working-capital limit and "
                "all existing debt as repayable within the year. Resilience is assessed on the latest audited year below.")
    else:
        s.text(f"Financial projections: {NOT_AVAILABLE}.", "unavailable", "projection engine")

    s.block("Resilience assessment")
    scen = c.stress.get("scenarios") or []
    if scen:
        checks = {p["metric"]: p for p in c.stress.get("policy_checks") or []}

        def policy(key):
            p = checks.get(key)
            return f"{'≥' if p['limit_type'] == 'min' else '≤'} {p['limit']}" if p and p.get("limit") is not None else "—"

        metrics = [("EBITDA", "ebitda_cr", "cr"), ("Operating cash flow", "operating_cash_flow_cr", "cr"),
                   ("DSCR", "dscr", "x"), ("Interest coverage", "interest_coverage_ratio", "x"),
                   ("Debt / EBITDA", "debt_to_ebitda", "x"), ("OCF / Debt", "ocf_to_debt_pct", "pct"),
                   ("Current ratio", "current_ratio", "x"), ("Additional working capital borrowing", "additional_borrowing_cr", "cr")]
        s.table(f"Scenario analysis ({c.stress.get('period')})", ["Metric"] + [x["label"] for x in scen] + ["Policy"],
                [[label] + [fmt(x["stressed_metrics"].get(key), unit) for x in scen] + [policy(key)]
                 for label, key, unit in metrics]
                + [["Policy breaches"] + [str(len(x["policy_breaches"])) for x in scen] + ["—"],
                   ["Scenario severity"] + [_title(x["severity"].lower()) for x in scen] + ["—"]],
                "calculated", "resilience assessment (ratio engine on shocked statements)")
        assumptions = "; ".join(
            f"{x['label']}: revenue {x['assumptions']['revenue_change_pct']}%, EBITDA margin "
            f"{x['assumptions']['margin_change_bps']} bps, debtor days +{x['assumptions']['debtor_days_change']}, "
            f"inventory days +{x['assumptions']['inventory_days_change']}, interest rate +{x['assumptions']['rate_shock_bps']} bps"
            for x in scen if x["scenario"] != "base")
        s.text(f"Scenario assumptions — {assumptions}.", "template", "credit policy scenario parameters")
    else:
        s.text("A resilience (scenario) assessment is not available for this case.", "unavailable", "resilience assessment")

    s.block("Credit implication")
    res = c.resilience()
    if res.get("status"):
        s.text(RESILIENCE_IMPLICATIONS.get(res["status"], ""), "derived", "credit reassessment")
        s.text(res.get("detail", ""), "calculated", "resilience assessment")
        cash = ((c.rea.get("overall_credit_assessment") or {}).get("dimensions") or {}).get("cash_flow") or {}
        if cash.get("detail"):
            s.text(f"Cash flow: {cash['detail']}", "calculated", "resilience assessment")
    for x in scen[1:]:
        for o in x["key_observations"][:2]:
            s.text(f"{x['label']}: {o}", "calculated", "resilience assessment")
    return s.out()


# ─── 10. Credit facilities & structure ───────────────────────────────────────

def _facility(c: _Ctx) -> dict:
    s = _Sec()
    fd = c.fp.get("facility_details") or {}
    fr = c.fr
    dp = c.fp.get("drawing_power") or {}
    pricing = c.fp.get("facility_pricing") or {}
    cls_f = c.cls("facility_details")
    s.block("Facility summary")
    rows = [[_title(e.get("facility_type")) + " (existing)", fmt(e.get("sanctioned_cr"), "cr"), "—", "—"]
            for e in c.fp.get("existing_exposure") or []]
    existing = fd.get("existing_limit_cr")
    rows.append([_title(fd.get("facility_type")) + " (proposed)",
                 fmt(existing, "cr") if existing is not None else ("Nil" if not rows else "—"),
                 fmt(fd.get("amount_requested_cr"), "cr"),
                 fmt(fr.get("recommended_cr"), "cr") if fr.get("recommended_cr") is not None else NOT_AVAILABLE])
    s.table("Facilities", ["Facility", "Existing", "Requested", "Recommended"], rows, cls_f,
            "facility details; recommended amount: credit reassessment")
    if fr.get("structure"):
        s.text(f"Recommended structure: {fr['structure']}.", "derived", "credit reassessment")

    s.block("Facility terms")
    s.fact("Purpose", fd.get("purpose"), cls_f, "facility_details")
    s.fact("Amount", fr.get("recommended_cr") if fr.get("recommended_cr") is not None else fd.get("amount_requested_cr"),
           "derived" if fr.get("recommended_cr") is not None else cls_f, "credit reassessment / facility_details", "cr")
    s.fact("Tenor", f"{fd['tenor_months']} months" if fd.get("tenor_months") else None, cls_f, "facility_details")
    s.fact("Repayment", fd.get("repayment_schedule") or fd.get("repayment_terms"), cls_f, "facility_details")
    s.fact("Indicative pricing (standard card rate)", pricing.get("interest_rate"), "template",
           "bank rate card (to be confirmed at sanction)")
    s.fact("Processing fee (standard)", pricing.get("processing_fee"), "template", "bank rate card")
    s.fact("Security", fd.get("collateral_type"), cls_f, "facility_details")
    if dp.get("components"):
        s.table("Drawing power", ["Component", "Value", "Margin", "Drawing power"],
                [[x["name"], fmt(x["value_cr"], "cr"), fmt(x["margin_pct"], "pct"), fmt(x["dp_cr"], "cr")]
                 for x in dp["components"]] + [["Total", "", "", fmt(dp.get("total_dp_cr"), "cr")]],
                "calculated", "drawing power computation",
                "Receivable ageing is not available: all trade receivables are counted.")

    sizing = fr.get("sizing") or {}
    if sizing.get("caps"):
        s.block("Sizing of the facility")
        s.table("How the amount was sized", ["Test", "Supportable amount", "Basis"],
                [["Requested", fmt(sizing.get("requested_cr"), "cr"), "facility details"]]
                + [[cap["label"] + (" (binding)" if cap["cap"] == sizing.get("binding_cap") else ""),
                    fmt(cap["amount_cr"], "cr"), cap["formula"]] for cap in sizing["caps"]]
                + [["Debt headroom at policy Debt/EBITDA", fmt(sizing.get("leverage_headroom_cr"), "cr"),
                    "max Debt/EBITDA × EBITDA − total debt"]], "derived", "credit reassessment (sizing)")
    s.findings = [{"kind": "challenge", "id": x["challenge_id"], "severity": x["severity"], "status": x["status"],
                   "text": x["challenge"]} for x in c.chl if x["category"] in ("Facility amount", "Working-capital requirement")]
    return s.out()


# ─── 11. Security, collateral & covenants ────────────────────────────────────

_PRIMARY_SECURITY = re.compile(r"current asset|stock|book debt|receivable|hypothecation|inventory|plant|machinery|project",
                               re.I)
_FINANCIAL_COVENANT = re.compile(r"dscr|debt|ratio|coverage|ebitda|net worth|equity|leverage|tnw|\d+(\.\d+)?x", re.I)
_MONITORING = re.compile(r"statement|audit|review|report|quarterly|monthly|half-yearly|annual|stock|inspection", re.I)


def _covenants(c: _Ctx) -> tuple[list, list, list]:
    """(financial covenants, operational covenants, monitoring requirements) as [item, basis] rows."""
    policy = list(((c.fp.get("policy_decisions") or {}).get("tier3_recommendation") or {}).get("covenants_proposed") or [])
    cs = [x["item"] for x in c.rea.get("conditions_subsequent") or []]
    fin = [[x, "Credit policy"] for x in policy if _FINANCIAL_COVENANT.search(x)]
    fin += [[x, "Credit reassessment"] for x in cs if "covenant" in x.lower()]
    ops = [[x, "Credit policy"] for x in policy if not _FINANCIAL_COVENANT.search(x)]
    mon = [[x, "Credit reassessment"] for x in cs if "covenant" not in x.lower() and _MONITORING.search(x)]
    return fin, ops, mon


def _security(c: _Ctx) -> dict:
    s = _Sec()
    ca = c.fp.get("collateral_analysis") or {}
    cls_c = c.cls("collateral_analysis")
    sec = (c.rpy.get("secondary_repayment_source") or {}).get("metrics") or {}
    items = ca.get("collaterals") or []
    primary = [x for x in items if _PRIMARY_SECURITY.search(f"{x.get('type')} {x.get('description')}")]
    collateral = [x for x in items if x not in primary]

    def rows(xs):
        return [[x.get("type"), x.get("description"), fmt(x.get("market_value_cr"), "cr"),
                 fmt(x.get("forced_sale_value_cr"), "cr"), x.get("valuation_date") or "—", _title(x.get("encumbrance"))]
                for x in xs]

    cols = ["Type", "Description", "Market value", "Forced-sale value", "Valued on", "Charge"]
    s.block("Primary security")
    s.table("Primary security", cols, rows(primary), cls_c, "collateral_analysis",
            empty=f"Primary security details: {NOT_AVAILABLE}.")
    s.block("Collateral security")
    s.table("Collateral security", cols, rows(collateral), cls_c, "collateral_analysis",
            empty="No collateral security is recorded in the case data.")
    s.block("Guarantees")
    guarantees = [x["item"] for x in c.rea.get("recommended_mitigants") or [] if "guarantee" in x["item"].lower()]
    if guarantees:
        for g in guarantees:
            s.text(g, "derived", "credit reassessment (proposed)")
    else:
        s.text("No guarantees are recorded or proposed.", "unavailable", "case data")
    s.block("Security coverage")
    s.fact("Total market value", ca.get("total_market_value_cr"), cls_c, "collateral_analysis", "cr")
    s.fact("Total forced-sale value", ca.get("total_forced_sale_value_cr"), cls_c, "collateral_analysis", "cr")
    s.fact("Security cover on market value", ca.get("coverage_ratio_market"), "calculated", "collateral_analysis", "x")
    s.fact("Security cover on forced-sale value", ca.get("coverage_ratio_fsv"), "calculated", "collateral_analysis", "x")
    s.fact("Hard-security cover (excluding current assets)", sec.get("hard_security_cover"), "calculated",
           "repayment assessment", "x")
    fin, ops, mon = _covenants(c)
    s.block("Financial covenants")
    s.table("Financial covenants", ["Covenant", "Basis"], fin, "derived", "credit policy and credit reassessment",
            empty="No financial covenants are proposed.")
    s.block("Operational covenants")
    s.table("Operational covenants", ["Covenant", "Basis"], ops, "derived", "credit policy",
            empty="No operational covenants are proposed.")
    s.block("Monitoring requirements")
    s.table("Monitoring requirements", ["Requirement", "Basis"], mon, "derived", "credit reassessment",
            empty="No additional monitoring requirements are proposed.")
    return s.out()


# ─── 12. Sanction terms, conditions & recommendation ─────────────────────────

def _final(c: _Ctx, trace: list[dict]) -> dict:
    s = _Sec()
    fr = c.fr
    auth = c.fp.get("approving_authority") or {}
    s.block("Recommended decision")
    if c.rea.get("available"):
        s.text(f"{str(c.rea.get('decision_label') or '').upper()}. {c.decision_sentence()}", "derived", "credit reassessment")
    else:
        s.text("A reassessed recommendation is not available for this case.", "unavailable", "credit reassessment")
    s.block("Recommended facility")
    s.fact("Facility", _title((c.fp.get("facility_details") or {}).get("facility_type")), c.cls("facility_details"),
           "facility_details")
    s.fact("Requested", fr.get("requested_cr"), c.cls("facility_details"), "facility_details", "cr")
    s.fact("Recommended", fr.get("recommended_cr"), "derived", "credit reassessment", "cr")
    s.fact("Structure", fr.get("structure"), "derived", "credit reassessment")
    s.fact("Sanctioning authority", (auth.get("name") or "") + (" (deviation route)" if fr.get("deviation_route_required")
                                                                 or auth.get("deviation_route") else "") or None,
           "derived", "delegation of powers")
    s.block("Conditions precedent")
    s.table("Conditions precedent", ["Condition", "Addresses"],
            [[x["item"], c.addresses(x)] for x in c.rea.get("conditions_precedent") or []],
            "derived", "credit reassessment", empty="No conditions precedent are proposed.")
    s.block("Conditions subsequent")
    s.table("Conditions subsequent", ["Condition", "Addresses"],
            [[x["item"], c.addresses(x)] for x in c.rea.get("conditions_subsequent") or []],
            "derived", "credit reassessment", empty="No conditions subsequent are proposed.")
    fin, _, mon = _covenants(c)
    s.block("Financial covenants & monitoring")
    s.table("Financial covenants", ["Covenant", "Basis"], fin, "derived", "credit policy and credit reassessment")
    s.table("Monitoring requirements", ["Requirement", "Basis"], mon, "derived", "credit reassessment")
    s.block("Mitigants")
    s.table("Mitigants", ["Mitigant", "Addresses"],
            [[x["item"], c.addresses(x)] for x in c.rea.get("recommended_mitigants") or []],
            "derived", "credit reassessment", empty="No additional mitigants are proposed.")
    s.block("Exceptions & deviations")
    hard_fail = [r for r in (c.case.get("tier1_decisions") or []) if r.get("result") not in ("pass", None)]   # incl. not verified
    breaches = (c.scenario("base") or {}).get("policy_breaches") or []
    rows = [[f"Hard rule: {r.get('rule_description') or r.get('description') or r.get('rule_code') or r.get('rule')}",
             _RULE_RESULT.get(r.get("result"), _title(r.get("result"))), r.get("details") or ""] for r in hard_fail]
    rows += [[f"Policy limit: {b['label']}", f"{b['value']} vs {'min' if b['limit_type'] == 'min' else 'max'} {b['limit']}",
              "Base case (latest audited year)"] for b in breaches]
    pol = (c.fp.get("policy_decisions") or {}).get("tier3_recommendation") or {}
    if fr.get("deviation_route_required"):
        rows.append(["System recommendation", _title(pol.get("recommendation") or fr.get("original_policy_recommendation")),
                     "Reassessed recommendation differs; deviation route required"])
    s.table("Exceptions and deviations", ["Item", "Position", "Note"], rows, "derived", "policy engine and resilience assessment",
            empty="No policy exceptions or deviations.")
    s.block("Final credit rationale")
    s.table("Basis of recommendation", ["Stage", "Outcome"],
            [[t["label"], t["text"]] for t in trace if t["status"] != "unavailable"], "derived", "decision trail")
    for r in c.rea.get("rationale") or []:
        s.text(re.sub(r"\(binding cap: [a-z_]+\)", f"(binding constraint: {c.binding_label()})", r),
               "derived", "credit reassessment")
    s.text(f"The sanction decision rests with the {auth.get('name') or 'approving authority'}; this memorandum records "
           "the credit assessment and recommendation.", "template", "")
    return s.out()


_BUILDERS = {"executive_summary": _executive, "borrower_group": _borrower, "business_overview": _business,
             "industry_risk": _industry, "rating_history_conduct": _rating, "key_risks": _risks,
             "compliance_intelligence": _compliance, "financials_repayment": _financials,
             "projections_stress": _projections, "facility_structure": _facility, "security_covenants": _security}


# ─── Credit journey & decision trail ─────────────────────────────────────────

def credit_journey(case: dict) -> list[dict]:
    """The nine credit-process stages with their availability and a one-line outcome (no new figures)."""
    c = _Ctx(case)
    pol = (c.fp.get("policy_decisions") or {}).get("tier3_recommendation") or {}
    hard_fail = [r for r in case.get("tier1_decisions") or [] if r.get("result") == "fail"]
    unverified = [r for r in case.get("tier1_decisions") or [] if r.get("result") == "not_verified"]
    high = [o for o in c.obs if o["severity"] in ("CRITICAL", "HIGH")]
    inv_open = [t for t in c.inv if t["status"] in _OPEN]
    chl_open = [x for x in c.chl if x["status"] == "OPEN"]
    res = c.resilience()

    def stage(sid, label, available, attention, summary):
        return {"id": sid, "label": label, "status": ("attention" if attention else "complete") if available else "unavailable",
                "summary": summary if available else "Not available"}

    return [
        stage("credit_assessment", "Credit Assessment", bool(c.fp.get("ratio_analysis") and pol),
              bool(hard_fail or unverified) or pol.get("recommendation") == "decline",
              f"Grade {pol.get('risk_grade')} · system view {_label(pol.get('recommendation'))}"
              + (f" · {len(hard_fail)} hard-rule failure(s)" if hard_fail else "")
              + (f" · {len(unverified)} not verified" if unverified else "")),
        stage("risk_identification", "Risk Identification", "observations" in case, bool(high),
              f"{len(c.obs)} risk(s), {len(high)} high or critical" if c.obs else "No risks triggered"),
        stage("due_diligence", "Due Diligence", "investigations" in case, bool(inv_open),
              f"{len(c.inv)} item(s), {len(inv_open)} open" if c.inv else "None required"),
        stage("credit_challenge", "Credit Challenge", "challenges" in case, bool(chl_open),
              f"{len(c.chl)} challenge(s), {len(chl_open)} open" if c.chl else "No challenges raised"),
        stage("repayment", "Repayment Assessment", bool(c.rpy.get("available")),
              c.rpy.get("repayment_capacity") in ("MODERATE", "STRESSED"),
              f"Capacity {_label(c.rpy.get('repayment_capacity')).lower()} · risk {_label(c.rpy.get('repayment_risk')).lower()}"),
        stage("resilience", "Resilience Assessment", bool(c.stress.get("available")),
              res.get("status") not in (None, "RESILIENT"),
              {"RESILIENT": "Resilient to downside", "FAILS DOWNSIDE": "Below policy in downside",
               "FAILS SEVERE": "Constrained in severe downside"}.get(res.get("status"), "Scenarios assessed")),
        stage("reassessment", "Credit Reassessment", bool(c.rea.get("available")),
              (c.rea.get("overall_credit_assessment") or {}).get("rating") in ("WEAK", "VERY WEAK", "POOR"),
              f"Overall {_label((c.rea.get('overall_credit_assessment') or {}).get('rating')).lower()}"),
        stage("decision", "Credit Decision", bool(c.rea.get("decision")), c.rea.get("decision") != "SUPPORTED",
              c.rea.get("decision_label") if c.rea.get("decision") in ("NOT_SUPPORTED", "DEFERRED")
              else f"{c.rea.get('decision_label')} · {fmt(c.fr.get('recommended_cr'), 'cr')}"),
        stage("cam", "CAM", bool(c.fp), False, "12-section memorandum"),
    ]


def decision_trail(case: dict) -> dict:
    """Why the recommendation was reached: the proposal through each stage to the decision, from the case outputs."""
    c = _Ctx(case)
    fd = c.fp.get("facility_details") or {}
    pol = (c.fp.get("policy_decisions") or {}).get("tier3_recommendation") or {}
    fr = c.fr
    steps = []

    def step(sid, label, available, text):
        steps.append({"id": sid, "label": label, "status": "complete" if available else "unavailable",
                      "text": text if available else "Not available"})

    step("proposal", "Original proposal", bool(fd), f"{_title(fd.get('facility_type'))} of "
         f"{fmt(fd.get('amount_requested_cr'), 'cr')} requested" + (f" — {fd['purpose'].rstrip('.')}." if fd.get("purpose") else "."))
    step("credit_assessment", "Credit assessment", bool(pol), f"Risk grade {pol.get('risk_grade')} (composite score "
         f"{pol.get('composite_score')}); system recommendation to {_label(pol.get('recommendation'))}.")
    top = [o for o in c.obs if o["severity"] in ("CRITICAL", "HIGH")] or c.obs
    step("risk_identification", "Risk identified", "observations" in case,
         (f"{len(c.obs)} credit risk(s) identified, led by " + ", ".join(o["title"].lower() for o in top[:2]) + ".")
         if c.obs else "No credit risk observations were triggered.")
    p1 = [t for t in c.inv if t["priority"] == "P1"] or c.inv
    inv_open = [t for t in c.inv if t["status"] in _OPEN]
    step("due_diligence", "Due diligence", "investigations" in case,
         (f"{len(c.inv)} due-diligence item(s) opened ({len(inv_open)} still open), including "
          f"{p1[0]['title'][:1].lower() + p1[0]['title'][1:]}.") if c.inv else "No due diligence was required.")
    step("credit_challenge", "Credit challenge", "challenges" in case,
         (f"{len(c.chl)} challenge(s) to the proposal, e.g. “{c.chl[0]['title']}”.") if c.chl
         else "The proposal was reviewed and not challenged.")
    step("repayment", "Repayment assessment", bool(c.rpy.get("available")),
         f"Repayment capacity {_label(c.rpy.get('repayment_capacity')).lower()} with "
         f"{_label(c.rpy.get('repayment_risk')).lower()} repayment risk; primary source "
         f"{_label((c.rpy.get('primary_repayment_source') or {}).get('adequacy')).lower()}.")
    res = c.resilience()
    step("resilience", "Resilience assessment", bool(c.stress.get("available")),
         f"DSCR {fmt(c.metric('base', 'dscr'), 'x')} base, {fmt(c.metric('downside', 'dscr'), 'x')} downside, "
         f"{fmt(c.metric('severe', 'dscr'), 'x')} severe downside. " + RESILIENCE_IMPLICATIONS.get(res.get("status"), ""))
    step("reassessment", "Credit reassessment", bool(c.rea.get("available")),
         f"Overall credit assessment {_label((c.rea.get('overall_credit_assessment') or {}).get('rating')).lower()}"
         + (f"; supportable amount set by the {c.binding_label()}." if (fr.get("sizing") or {}).get("binding_cap")
            and _num(fr.get("recommended_cr")) is not None and _num(fr.get("requested_cr")) is not None
            and _num(fr.get("recommended_cr")) < _num(fr.get("requested_cr")) else "."))
    changed = c.rea.get("decision") not in (None, "SUPPORTED", "SUPPORTED_WITH_CONDITIONS") or (
        _num(fr.get("recommended_cr")) is not None and _num(fr.get("requested_cr")) is not None
        and _num(fr.get("recommended_cr")) != _num(fr.get("requested_cr")))
    n_cp, n_cs = len(c.rea.get("conditions_precedent") or []), len(c.rea.get("conditions_subsequent") or [])
    decision = c.rea.get("decision")
    if decision in ("NOT_SUPPORTED", "DEFERRED"):
        decision_text = (f"{c.rea.get('decision_label')}: {fmt(fr.get('requested_cr'), 'cr')} requested; "
                         f"{n_cp} condition(s) would need to be met before the proposal is reconsidered.")
    else:
        decision_text = (f"{c.rea.get('decision_label')}: {fmt(fr.get('recommended_cr'), 'cr')} against "
                         f"{fmt(fr.get('requested_cr'), 'cr')} requested, with {n_cp} condition(s) precedent and "
                         f"{n_cs} condition(s) subsequent.")
    step("decision", "Credit decision", bool(decision), decision_text)
    if not decision:
        outcome = "Not available"
    elif decision == "NOT_SUPPORTED":
        outcome = "Following due diligence and resilience assessment, the proposal is not supported in its present form."
    elif decision == "DEFERRED":
        outcome = "Following due diligence, a decision on the proposal is deferred until open items are closed."
    elif changed:
        outcome = "The proposal was modified following due diligence and resilience assessment."
    else:
        outcome = "Credit assessment confirmed following due diligence and resilience assessment."
    return {"changed": bool(changed), "outcome": outcome, "steps": steps}


# ─── Analytical drill-down ───────────────────────────────────────────────────

def analytical_sections(cam_text: str) -> dict[str, dict]:
    """{analytical section id: {"heading", "text"}} parsed from the 21-section CAM (template or LLM)."""
    out: dict[str, dict] = {}
    for part in re.split(r"(?=^## )", cam_text or "", flags=re.M):
        if not part.startswith("## "):
            continue
        heading = part.split("\n", 1)[0][3:].strip()
        h = heading.lower()
        if not re.match(r"^\d+[a-z]?\.", h):
            continue
        for pattern, sid in _HEADING_IDS:
            if re.search(pattern, h) and sid not in out:
                out[sid] = {"heading": heading, "text": part.strip()}
                break
    return out


def compose_final_cam(case: dict) -> dict:
    """The 12-section banker CAM for a case (deterministic)."""
    c = _Ctx(case)
    if not c.fp:
        return {"available": False, "reason": "No fact pack for this case."}
    narrative_cls = "ai" if case.get("narrative_mode") == "llm" else "template"
    analytical = analytical_sections(case.get("cam_text", ""))
    trail = decision_trail(case)
    sections = []
    for number, (sid, title, sources) in enumerate(SECTIONS, start=1):
        body = _final(c, trail["steps"]) if sid == "final_recommendation" else _BUILDERS[sid](c)
        items = [x["provenance"] for x in body["statements"] + body["facts"] + body["tables"]]
        drill = [{"analytical_section": s, "heading": analytical[s]["heading"], "text": analytical[s]["text"],
                  "provenance": narrative_cls} for s in dict.fromkeys(sources) if s in analytical]
        sections.append({"id": sid, "number": number, "title": f"{number}. {title}",
                         "blocks": body["blocks"], "statements": body["statements"], "facts": body["facts"],
                         "tables": body["tables"], "findings": body["findings"],
                         "ai_interpretation": None, "analytical_sources": sources, "drill_down": drill,
                         "provenance_summary": {k: items.count(k) for k in dict.fromkeys(items)}})
    fr = c.fr
    res = c.resilience()
    return {
        "available": True, "version": COMPOSER_VERSION, "entity_id": case.get("entity_id"),
        "company_name": case.get("company_name"), "run_id": case.get("run_id"), "generated_at": case.get("run_at"),
        "headline": {"decision": c.rea.get("decision"), "decision_label": c.rea.get("decision_label"),
                     "decision_sentence": c.decision_sentence() if c.rea.get("available") else None,
                     "requested_cr": fr.get("requested_cr"), "recommended_cr": fr.get("recommended_cr"),
                     "structure": fr.get("structure"), "system_recommendation": case.get("recommendation"),
                     "risk_grade": case.get("risk_grade"), "composite_score": case.get("composite_score"),
                     "repayment_capacity": c.rpy.get("repayment_capacity"),
                     "repayment_risk": c.rpy.get("repayment_risk"),
                     "overall_assessment": (c.rea.get("overall_credit_assessment") or {}).get("rating"),
                     "dscr_by_scenario": {x["scenario"]: c.metric(x["scenario"], "dscr")
                                          for x in c.stress.get("scenarios") or []},
                     "dscr_breach_by_scenario": {x["scenario"]: any(b.get("metric") == "dscr" for b in x["policy_breaches"])
                                                 for x in c.stress.get("scenarios") or []},
                     "min_dscr": c.threshold.get("min_dscr"),
                     "resilience_status": res.get("status"),
                     "resilience_implication": RESILIENCE_IMPLICATIONS.get(res.get("status")),
                     "deviation_route_required": fr.get("deviation_route_required"),
                     "conditions": {"precedent": len(c.rea.get("conditions_precedent") or []),
                                    "subsequent": len(c.rea.get("conditions_subsequent") or []),
                                    "mitigants": len(c.rea.get("recommended_mitigants") or [])}
                     if c.rea.get("available") else None,
                     "approving_authority": (c.fp.get("approving_authority") or {}).get("name")},
        "journey": credit_journey(case),
        "decision_trail": trail,
        "provenance_legend": CLASS_LABELS,
        "narrative_layer": {"mode": case.get("narrative_mode"), "sections_found": sorted(analytical)},
        "sections": sections,
    }


# ─── Markdown rendition (HTML / PDF) ─────────────────────────────────────────

TAGS = {"source": "S", "external": "Ext", "calculated": "C", "derived": "R", "synthetic_demo": "Demo", "template": "T",
        "unavailable": "N/A", "ai": "AI"}


def _cell(v) -> str:
    return str("" if v is None else v).replace("|", "/").replace("\n", " ")


def _md_block(block: dict) -> list[str]:
    out = []
    if block.get("heading"):
        out += [f"### {block['heading']}", ""]
    for st in block["statements"]:
        out += [f"{st['text']} [{TAGS[st['provenance']]}]", ""]
    if block["facts"]:
        out += ["| Particulars | Details | Basis |", "|---|---|---|"]
        out += [f"| {_cell(f['label'])} | {_cell(f['value'])} | {TAGS[f['provenance']]} |" for f in block["facts"]]
        out.append("")
    for t in block["tables"]:
        if not t["rows"]:
            continue
        if t["title"] != block.get("heading"):
            out += [f"**{t['title']}** [{TAGS[t['provenance']]}]", ""]
        out += ["| " + " | ".join(t["columns"]) + " |", "|" + "---|" * len(t["columns"])]
        out += ["| " + " | ".join(_cell(v) for v in row) + " |" for row in t["rows"]]
        out.append("")
        if t.get("note"):
            out += [f"*{t['note']}*", ""]
    return out


def render_final_cam_markdown(final: dict) -> str:
    if not final.get("available"):
        return "# Credit Appraisal Memorandum\n\nThe final CAM is not available for this case."
    h = final["headline"]
    out = [f"# Credit Appraisal Memorandum — {final.get('company_name')}", "",
           f"**Recommended decision:** {h.get('decision_label') or 'Not available'} — "
           f"{fmt(h.get('recommended_cr'), 'cr')} (requested {fmt(h.get('requested_cr'), 'cr')}). "
           f"Internal risk grade {h.get('risk_grade')}; sanctioning authority {h.get('approving_authority') or 'n/a'}.", ""]
    for s in final["sections"]:
        out += [f"## {s['title']}", ""]
        for block in s.get("blocks") or [{"heading": None, "statements": s["statements"], "facts": s["facts"],
                                          "tables": s["tables"]}]:
            out += _md_block(block)
        ai = s.get("ai_interpretation")
        if ai:
            out += [f"> **Commentary (AI-assisted)** [AI]: {ai['text']}", ""]
        if s["drill_down"]:
            out += ["*Supporting analysis: " + "; ".join(d["heading"] for d in s["drill_down"]) + "*", ""]
    out += ["---", "", "*Basis of information: " + " · ".join(f"{TAGS[k]} = {v}" for k, v in final["provenance_legend"].items())
            + ".*", ""]
    return "\n".join(out)
