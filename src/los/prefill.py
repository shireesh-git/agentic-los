"""
IP and AP pre-fill agents (S9: R-P1, R-P2) — more reconciliation agents in the same population graph.

    narrative_more   the remaining proposal narratives (marketing arrangements, corporate
                     governance, weaknesses, other material information) and the proposal
                     summary (purpose, pricing, security)
    external_rating  the borrower's external rating and agency (the credit case, else the CAM)
    shareholding     the shareholding pattern (promoter / institutional / public)
    banking          the banking arrangement (the bank's CAM, else the lenders on the bureau)
    project          a project record for a term loan / project finance, from the purpose and
                     the projection engine
    esms             ESMS screening proposals from the sector rule (must verify)
    fees             the processing fee per facility from the rate card (labelled template)
    inter_firm       the inter-firm comparison against the sector peer cohort (benchmark pack)
    cma_projection   the CMA projections from the projection engine (AP)
    tnc              the terms & conditions (src/los/terms.py)

Every value is a field-store proposal with its evidence and target, written into the workspace by
``reconcile.materialise`` — never over a person's own entry. Nothing is invented: a source that is
missing gives an unavailable proposal (shown as "not available", never pre-ticked).
"""

from __future__ import annotations

import re
from typing import Optional

from src.los import projects as proj_mod
from src.los import terms as terms_mod
from src.los.reconcile import _p

_PAYOR = re.compile(r"(payor|customer|channel|segment|mix|dealer|distribut|export|order|client|store|network)", re.I)


def _cam_label(ctx: dict, fid: str) -> Optional[dict]:
    return ((ctx["app"].get("cam") or {}).get("labels") or {}).get(fid)


def _cam_evidence(ctx: dict, hit: dict) -> dict:
    cam = ctx["app"].get("cam") or {}
    return {"document": cam.get("document"), "page": hit.get("page"), "snippet": hit.get("snippet"), "category": "cam"}


def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:,.2f}".rstrip("0").rstrip(".")
    return f"{v:,}" if isinstance(v, int) else str(v)


def _latest_statement(company: dict):
    fins = (company or {}).get("financials") or {}
    if not fins:
        return None, {}
    period = sorted(fins)[-1]
    fs = fins[period]
    return period, ((fs.get("line_items") if isinstance(fs, dict) else getattr(fs, "line_items", {})) or {})


# ── R-P1: the IP sections ──────────────────────────────────────────────────────

def resolve_narrative_more(ctx: dict) -> list[dict]:
    fp, reg, case, app = ctx["fact_pack"], ctx["registry"], ctx["case"], ctx["app"]
    rea = case.get("reassessment") or {}
    ind, kpis = fp.get("industry_analysis") or {}, fp.get("sector_kpis") or {}

    # Marketing arrangements: the business model as the documents and the sector KPIs state it
    parts = [ind.get("business_description")]
    for label, key in (("Revenue segments", "revenue_segments"), ("Geographic mix", "geographic_mix"),
                       ("Competitors", "competitors")):
        items = [str(x.get("name") if isinstance(x, dict) else x) for x in ind.get(key) or []][:5]
        if items:
            parts.append(f"{label}: " + "; ".join(items) + ".")
    for group, values in kpis.items():
        if not isinstance(values, dict) or not _PAYOR.search(group + " " + " ".join(values)):
            continue
        facts = [f"{k.replace('_', ' ')} {_fmt(v)}" for k, v in values.items()
                 if isinstance(v, (int, float)) and _PAYOR.search(k)][:5]
        if facts:
            parts.append(f"{group.replace('_', ' ').capitalize()}: " + "; ".join(facts)
                         + (f" ({values['source']})" if values.get("source") else "") + ".")
    marketing = " ".join(p for p in parts if p) or None

    # Corporate governance: board / promoters, shareholding, listing
    directors = (fp.get("management_profile") or {}).get("directors") or []
    gp, gov = fp.get("group_profile") or {}, ((fp.get("esg_regulatory") or {}).get("governance") or {})
    lines = []
    if directors:
        lines.append("Board and management: " + "; ".join(
            f"{d['name']} ({d.get('designation') or 'Director'}{', promoter' if d.get('is_promoter') else ''})"
            for d in directors[:6] if d.get("name")) + ".")
    if gp.get("promoter_holding_pct") is not None:
        lines.append(f"Shareholding: promoters {gp['promoter_holding_pct']}%"
                     + (f", institutions {gp['institutional_holding_pct']}%" if gp.get("institutional_holding_pct") is not None else "")
                     + (f", public {gp['public_holding_pct']}%" if gp.get("public_holding_pct") is not None else "") + ".")
    if gp.get("group_name"):
        lines.append(f"Part of the {gp['group_name']}.")
    if gov.get("listed"):
        lines.append("Listed entity: subject to SEBI listing and disclosure obligations.")
    if gov.get("board_composition"):
        lines.append(f"Board composition: {gov['board_composition']}.")
    governance = " ".join(lines) or None

    # Weaknesses: what the reassessment still holds against the case, and the weak peer benchmarks
    weak = [f"• {r.get('risk')}: {r.get('why')}" + (f" ({r['severity']})" if r.get("severity") else "")
            for r in rea.get("key_risks") or [] if r.get("risk")]
    for b in (fp.get("benchmark_summary") or {}).get("worst_performers") or []:
        if isinstance(b, dict) and b.get("metric"):
            weak.append(f"• {str(b['metric']).replace('_', ' ')} below the sector peer cohort "
                        f"({b.get('borrower_value')} vs median {b.get('peer_median')})")
    weaknesses = "\n".join(weak[:8]) or None

    # Other material information: the reassessment's summary and its open items
    other = " ".join(x for x in [rea.get("reassessment_summary"),
                                 (f"{len(rea['unresolved_issues'])} item(s) remain open: "
                                  + "; ".join(str(i.get("title")) for i in rea["unresolved_issues"][:4]) + ".")
                                 if rea.get("unresolved_issues") else ""] if x) or None

    # Proposal summary: purpose, pricing, security
    fac = app.get("facility") or {}
    price = fp.get("facility_pricing") or {}
    pricing = "; ".join(x for x in [price.get("interest_rate"),
                                    f"processing fee {price['processing_fee']}" if price.get("processing_fee") else ""] if x)
    ca = fp.get("collateral_analysis") or {}
    security = None
    if ca.get("collaterals"):
        security = "; ".join(f"{c.get('description') or c.get('type')} (market value ₹{_fmt(c.get('market_value_cr'))} Cr)"
                             for c in ca["collaterals"][:4])
        if ca.get("coverage_ratio_market") is not None:
            security += f". Security cover {ca['coverage_ratio_market']}x on market value"

    facts = {"engine": "fact pack and reassessment (M6)"}
    mk = lambda fid, label, value, target, eng, prov="derived": _p(
        fid, label, value, provenance=prov, source="engine", registry=reg, evidence={**facts, "engine": eng},
        target=target, run_id=ctx.get("run_id"))
    bg = ["proposal", "background"]
    return [mk("narrative.background.marketing_arrangements", "Marketing arrangements", marketing,
               bg + ["marketing_arrangements"], "industry analysis and sector KPIs (fact pack)"),
            mk("narrative.background.corporate_governance", "Corporate governance", governance,
               bg + ["corporate_governance"], "management profile, group profile, ESG governance (fact pack)"),
            mk("narrative.background.weaknesses", "Weaknesses", weaknesses, bg + ["weaknesses"],
               "reassessment key risks and peer benchmarks"),
            mk("narrative.background.other_material_information", "Other material information", other,
               bg + ["other_material_information"], "reassessment summary and open items (M6)"),
            mk("narrative.summary.purpose", "Purpose of the facility", fac.get("purpose"),
               ["proposal", "summary", "purpose"], "the application's facility", "source"),
            mk("narrative.summary.pricing_note", "Pricing (rate card)", pricing or None,
               ["proposal", "summary", "pricing_note"], f"rate card: {price.get('basis') or 'indicative'}", "template"),
            mk("narrative.summary.security_note", "Security offered", security,
               ["proposal", "summary", "security_note"], "collateral analysis (fact pack)")]


def resolve_external_rating(ctx: dict) -> list[dict]:
    fp, reg = ctx["fact_pack"], ctx["registry"]
    bp = fp.get("borrower_profile") or {}
    rating, agency = bp.get("credit_rating"), bp.get("rating_agency")
    evidence, prov, issues, source = {"path": "borrower profile (fact pack)"}, "source", [], "record"
    cam = _cam_label(ctx, "cam.rating.external_rating")
    if not rating and cam:
        rating, evidence, source = cam["value"], _cam_evidence(ctx, cam), "document"
    elif rating and cam and str(cam["value"]).split("/")[0].strip().upper() not in str(rating).upper():
        issues.append(f"The CAM states {cam['value']} (p{cam.get('page')}); the record shows {rating}")
    doc = (ctx.get("prefill_values") or {}).get("external_rating")
    if rating and doc and str(doc["value"]).split("/")[0].strip().upper() not in str(rating).upper():
        issues.append(f"Documents state {doc['value']} ({doc.get('document')} p{doc.get('page')}); the record shows {rating}")
    if not agency and rating:
        agency = next((a for a in ("CRISIL", "ICRA", "CARE", "India Ratings", "Acuite", "Brickwork", "Infomerics")
                       if a.lower() in str(rating).lower()), None)
    target = ["ratings", "external_ratings", {"find": {"subject": "borrower"}, "new": {
        "subject": "borrower", "party_name": ctx["app"].get("borrower_name"), "agency": None, "rating": None,
        "rating_type": "issuer", "term_class": "long_term", "grade": None, "date": ctx["today"], "instrument": None,
        "rationale": None, "prior_year": None, "origin": "agent"}}]
    return [_p("external_rating.borrower.rating", "External rating — borrower", rating, provenance=prov, source=source,
               registry=reg, evidence=evidence, target=target + ["rating"], issues=issues, run_id=ctx.get("run_id")),
            _p("external_rating.borrower.agency", "Rating agency", agency, provenance=prov, source=source,
               registry=reg, evidence=evidence, target=target + ["agency"], run_id=ctx.get("run_id"))]


def resolve_shareholding(ctx: dict) -> list[dict]:
    gp, reg = ctx["fact_pack"].get("group_profile") or {}, ctx["registry"]
    ev = {"path": "group profile — shareholding pattern (fact pack)"}
    return [_p(f"shareholding.pattern.{k}", label, gp.get(k), provenance="source", source="record", registry=reg,
               value_type="number", evidence=ev, target=["proposal", "shareholding", k], run_id=ctx.get("run_id"))
            for k, label in (("promoter_holding_pct", "Promoter holding (%)"),
                             ("institutional_holding_pct", "Institutional holding (%)"),
                             ("public_holding_pct", "Public holding (%)"))]


def resolve_banking(ctx: dict) -> list[dict]:
    reg, ei = ctx["registry"], ctx["fact_pack"].get("external_intelligence") or {}
    arrangement, number, evidence, prov, source = None, None, {}, "source", "record"
    cam = _cam_label(ctx, "cam.profile.banking_arrangement")
    if cam:
        text = str(cam["value"]).lower()
        arrangement = next((a for k, a in (("syndicat", "syndication"), ("consortium", "consortium"),
                                           ("multiple", "multiple_banking"), ("sole", "sole"), ("single", "sole"))
                            if k in text), None)
        m = re.search(r"(\d+)\s*(?:banks|lenders|members)", text)
        number = int(m.group(1)) if m else None
        evidence, source = _cam_evidence(ctx, cam), "document"
    elif ei.get("bureau_total_lenders"):
        number = int(ei["bureau_total_lenders"])
        arrangement = "sole" if number == 1 else "multiple_banking"
        evidence, prov = {"system": "commercial bureau — lenders reporting (demo data)",
                          "note": "multiple banking inferred from the number of lenders; confirm whether consortium"}, "external"
        source = "external"
    return [_p("banking.arrangement.type", "Banking arrangement", arrangement, provenance=prov, source=source,
               registry=reg, evidence=evidence, target=["proposal", "banking", "arrangement"], run_id=ctx.get("run_id")),
            _p("banking.arrangement.number_of_banks", "Number of banks / lenders", number, provenance=prov,
               source=source, registry=reg, value_type="number", evidence=evidence,
               target=["proposal", "banking", "number_of_banks"], run_id=ctx.get("run_id"))]


_PROJECT_TYPES = (("refinanc", "refinancing"), ("greenfield", "greenfield"), ("brownfield", "brownfield"),
                  ("expansion", "expansion"), ("capacity", "expansion"), ("new ", "greenfield"))   # explicit words first


def resolve_project(ctx: dict) -> list[dict]:
    app, fp, reg = ctx["app"], ctx["fact_pack"], ctx["registry"]
    fac = next((f for f in app.get("facilities") or [] if f.get("facility_type") in ("term_loan", "project_finance")), None)
    if not fac or not fac.get("purpose"):
        return []
    purpose = fac["purpose"]
    proj = fp.get("financial_projections") or {}
    years = proj.get("projected_years") or []
    m = re.search(r"\(([^)]{6,80})\)", purpose)
    name = (m.group(1) if m else purpose.split(" and ")[0])[:80].strip()
    loc = re.search(r"\bin ([A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+)?)", purpose)
    kind = next((t for k, t in _PROJECT_TYPES if k in purpose.lower()), None)
    viability = None
    if years:
        dscrs = [y.get("dscr") for y in years if isinstance(y.get("dscr"), (int, float))]
        if dscrs:
            viability = (f"Projected DSCR {min(dscrs):.2f}x – {max(dscrs):.2f}x over {years[0]['year']}–{years[-1]['year']} "
                         f"({proj.get('assumptions', {}).get('revenue_method') or 'projection engine'}; "
                         f"policy minimum {proj.get('assumptions', {}).get('min_dscr_policy', '—')}x)")
    dsra = (f"DSRA of ₹{_fmt(proj['dsra_requirement_cr'])} Cr (one period's debt service, projection engine)"
            if proj.get("dsra_requirement_cr") else None)
    target = ["projects", {"find": {"agent_key": "primary"}, "new": {
        **proj_mod.blank_project(0), "agent_key": "primary", "origin": "agent", "facility_ids": [fac["facility_id"]]}}]
    ev = {"path": f"facility {fac['facility_id']} purpose", "engine": "projection engine (fact pack)"}
    mk = lambda key, label, value, path, prov="derived": _p(
        f"projects.primary.{key}", label, value, provenance=prov, source="engine", registry=reg, evidence=ev,
        target=target + path, run_id=ctx.get("run_id"))
    return [mk("name", "Project name", name, ["name"], "source"),
            mk("purpose", "Project purpose", purpose, ["purpose"], "source"),
            mk("type", "Project type", kind, ["type"]),
            mk("location", "Project location", loc.group(1) if loc else None, ["location"]),
            mk("commercial_viability", "Commercial viability", viability, ["commercial_viability"]),
            mk("dsra", "DSRA", dsra, ["plan", "dsra"])]


_ES_CATEGORY = {"low": "C", "medium": "B", "high": "A"}


def resolve_esms(ctx: dict) -> list[dict]:
    env = ((ctx["fact_pack"].get("esg_regulatory") or {}).get("environmental") or {})
    reg, sector = ctx["registry"], (ctx["fact_pack"].get("case_summary") or {}).get("sector")
    risk = str(env.get("sector_risk") or "").lower()
    ev = {"engine": "sector E&S risk rule (" + (env.get("sector_risk_basis") or "rule on the borrower's sector") + ")"}
    from src.los.esms import ES_CHECKLIST, SECTOR_SCREENABLE
    labels = dict(ES_CHECKLIST)
    out = []
    for cid in SECTOR_SCREENABLE:                    # Annex 5-2: the activity items the sector rule can screen
        item = {"find": {"id": cid}, "new": {"id": cid, "label": labels[cid], "answer": None, "remarks": None,
                                              "source": None}}
        out += [_p(f"esms_screening.{cid}", f"Excluded activity — {labels[cid][:60]}", "No" if sector else None,
                   provenance="derived", source="engine", registry=reg, evidence=ev,
                   target=["esms", "checklist", item, "answer"], run_id=ctx.get("run_id")),
                _p(f"esms_screening.{cid}_remarks", f"Excluded activity — {labels[cid][:40]} (remarks)",
                   f"Not indicated for the {sector.replace('_', ' ')} sector (agent screening on the sector rule; "
                   "confirm the specific activity)" if sector else None, provenance="derived", source="engine",
                   registry=reg, evidence=ev, target=["esms", "checklist", item, "remarks"], run_id=ctx.get("run_id"))]
    return out + [_p("esms_screening.proposed_category", "E&S risk category (proposed)", _ES_CATEGORY.get(risk),
               provenance="derived", source="engine", registry=reg, evidence=ev,
               target=["esms", "proposed_category"], run_id=ctx.get("run_id")),
            _p("esms_screening.information_source", "ESMS information source",
               f"Sector rule: {sector.replace('_', ' ')} sector E&S risk {env['sector_risk']}" if risk and sector else None,
               provenance="derived", source="engine", registry=reg, evidence=ev,
               target=["esms", "information_source"], run_id=ctx.get("run_id"))]


def resolve_fees(ctx: dict) -> list[dict]:
    price, reg, out = ctx["fact_pack"].get("facility_pricing") or {}, ctx["registry"], []
    m = re.search(r"([0-9.]+)\s*%", str(price.get("processing_fee") or ""))
    if not m:
        return []
    pct = float(m.group(1))
    for f in ctx["app"].get("facilities") or []:
        amount = f.get("proposed_cr") or f.get("amount_cr")
        fid, key = f["facility_id"], f"processing_{f['facility_id'].lower().replace('-', '_')}"
        target = ["pricing", "fees", {"find": {"agent_key": key}, "new": {
            "fee_id": None, "agent_key": key, "origin": "agent", "facility_id": fid, "previously_approved": False,
            "nature": "Processing fee", "type": "one-time", "scope": "facility", "amount_cr": None, "pct": None,
            "milestone": "Upfront, before the first disbursement", "comments": "Bank rate card (indicative)",
            "total_cr": None}}]
        ev = {"engine": f"rate card: {price.get('processing_fee')} ({price.get('basis') or 'indicative'})"}
        out.append(_p(f"fees.{key}.pct", f"{fid} processing fee (%)", pct, provenance="template", source="template",
                      registry=reg, value_type="number", evidence=ev, target=target + ["pct"], run_id=ctx.get("run_id")))
        out.append(_p(f"fees.{key}.total_cr", f"{fid} processing fee (₹ Cr)",
                      round(amount * pct / 100, 4) if amount else None, provenance="template", source="template",
                      registry=reg, value_type="number", evidence=ev, target=target + ["total_cr"],
                      run_id=ctx.get("run_id")))
    return out


# ── R-P2: the AP sections ──────────────────────────────────────────────────────

def resolve_inter_firm(ctx: dict) -> list[dict]:
    from src.engines.benchmark_engine import SECTOR_BENCHMARKS, SUBSECTOR_BENCHMARK_MAP
    cs, reg = ctx["fact_pack"].get("case_summary") or {}, ctx["registry"]
    key = SUBSECTOR_BENCHMARK_MAP.get(cs.get("subsector") or "", cs.get("sector"))
    peers = SECTOR_BENCHMARKS.get(key or "")
    period, li = _latest_statement(ctx["company"])
    if not peers or not li:
        return []
    debt, ebitda, pat, rev = (li.get(k) for k in ("total_debt", "ebitda", "pat", "revenue_operating"))
    rows = [("borrower", ctx["app"].get("borrower_name") or "Borrower", {
        "revenue_cr": rev, "ebitda_cr": ebitda, "pat_cr": pat, "debt_cr": debt,
        "debt_to_ebitda": round(debt / ebitda, 2) if debt is not None and ebitda else None,
        "pat_pct": round(pat / rev * 100, 2) if pat is not None and rev else None}, "source",
             {"path": f"financial statement {period} (record)"}),
            ("peer_median", f"Sector peer median — {key.replace('_', ' ')} (benchmark pack v1)", {
                "debt_to_ebitda": peers["debt_to_ebitda"][1], "pat_pct": round(peers["net_profit_margin"][1] * 100, 2)},
             "derived", {"engine": "benchmark engine — sector peer cohort (benchmark_pack_v1)"}),
            ("peer_upper_quartile", f"Sector peer upper quartile — {key.replace('_', ' ')} (benchmark pack v1)", {
                "debt_to_ebitda": peers["debt_to_ebitda"][0], "pat_pct": round(peers["net_profit_margin"][2] * 100, 2)},
             "derived", {"engine": "benchmark engine — sector peer cohort (benchmark_pack_v1)"})]
    out = []
    for rkey, company, values, prov, ev in rows:
        target = ["proposal", "inter_firm", {"find": {"agent_key": rkey}, "new": {
            "agent_key": rkey, "origin": "agent", "company": company, "debt_cr": None, "revenue_cr": None,
            "ebitda_cr": None, "pat_cr": None, "debt_to_ebitda": None, "pat_pct": None, "pe": None,
            "market_cap_cr": None, "share_price": None}}]
        for col, value in values.items():
            if value is not None:
                out.append(_p(f"inter_firm.{rkey}.{col}", f"Inter-firm: {company[:40]} · {col.replace('_', ' ')}",
                              round(value, 2), provenance=prov, source="record" if rkey == "borrower" else "engine", registry=reg, value_type="number",
                              evidence=ev, target=target + [col], run_id=ctx.get("run_id")))
    return out


_PROJ_ROWS = (("revenue", "revenue_cr", "Revenue"), ("finance_cost", "interest_cr", "Finance cost"),
              ("pat", "pat_cr", "PAT"))


def resolve_cma_projection(ctx: dict) -> list[dict]:
    proj, reg = ctx["fact_pack"].get("financial_projections") or {}, ctx["registry"]
    if not proj.get("available"):
        return []
    basis = (proj.get("assumptions") or {}).get("revenue_method") or "projection engine"
    target = ["cma", "projections", {"find": {"subject": "borrower"}, "new": {
        "subject": "borrower", "rows": {}, "basis": f"Projection engine ({basis})", "origin": "agent"}}, "rows"]
    out = []
    for y in proj.get("projected_years") or []:
        for row_id, key, label in _PROJ_ROWS:
            v = y.get(key)
            out.append(_p(f"cma_projection.borrower.{y['year']}.{row_id}", f"{label} · {y['year']} (projected)",
                          round(v, 2) if isinstance(v, (int, float)) else v, provenance="derived", source="engine",
                          registry=reg, value_type="number",
                          evidence={"engine": f"projection engine — {y.get('basis') or basis}",
                                    "assumptions": proj.get("assumptions")},
                          target=target + [y["year"], row_id], run_id=ctx.get("run_id")))
    return out


# ── S10 (F-1, F-2): the bank's mandatory AP narratives and decision notes ─────

# The AP proposal narratives on the bank's screen beyond the eight we had (AP deck, slide 43)
BANK_NARRATIVES = {
    "market_enquiries": "Market enquiries on sponsor, promoter and borrower / corporate action details",
    "promoter_pledge": "Whether promoters' shares are pledged to our bank / other banks / FIs",
    "corporate_actions": "Corporate actions done / to be done / proposed (merger, demerger, restructuring, sale of undertakings)",
    "asset_quality_status": "Whether in SMA / NPA / restructured / financial difficulty / RFA, investigations or settlement",
    "committee_directions": "Whether all committee directions till date have been complied with",
    "past_proposals": "Whether the proposal was deferred / rejected in the past",
    "unhedged_exposure": "Unhedged exposures, extent of risk and risk-mitigation plan",
    "committee_reason": "Reason for the proposal being submitted to the committee",
    "justification": "Justification for the proposal",
}
# The decision tab's narratives (IP slide 76, AP slide 88)
DECISION_NOTES = {
    "policy_compliance": "Broad compliance with credit policy guidelines",
    "previous_relaxations": "Deviations / waivers / relaxations granted from the last review / sanction",
    "other_matters": "Any other matter requiring the committee's approval, with justification",
    "ip_observations": "Compliance with the observations of the in-principle approving authority",
}


def resolve_bank_narratives(ctx: dict) -> list[dict]:
    fp, reg, case, app = ctx["fact_pack"], ctx["registry"], ctx["case"], ctx["app"]
    rea = case.get("reassessment") or {}
    bg, out = ["proposal", "background"], []

    def add(key, value, eng, prov="derived", source="engine", evidence=None):
        out.append(_p(f"narrative.background.{key}", BANK_NARRATIVES[key], value, provenance=prov, source=source,
                      registry=reg, evidence=evidence or {"engine": eng}, target=bg + [key], run_id=ctx.get("run_id")))

    # market enquiries: the market signals on record (news and analyst items, with source and date)
    sig = [s for s in fp.get("market_signals") or [] if isinstance(s, dict) and s.get("headline")]
    add("market_enquiries", "\n".join(f"• {s['headline']} ({s.get('source') or 'source not stated'}, {s.get('date') or 'undated'})"
                                      for s in sig[:6]) or None, "market signals (reference data)", "external", "external",
        {"system": "market signals (reference data)", "items": len(sig)})
    # asset quality: CRILC facility classifications and the due-diligence checks
    rows = (fp.get("crilc_exposure") or {}).get("fund_based_facilities") or []
    quality = None
    if rows:
        flagged = [r for r in rows if str(r.get("classification") or "").lower() != "standard"
                   or str(r.get("sma_flag") or "none").lower() not in ("none", "", "null")]
        quality = (f"CRILC: {len(rows)} facility(ies) reported; " + (
            "all Standard with no SMA flag and nil DPD." if not flagged else
            "; ".join(f"{r.get('facility_type')}: {r.get('classification')}, SMA {r.get('sma_flag')}, DPD {r.get('dpd')}"
                      for r in flagged)))
    checks = [c for c in (app.get("due_diligence") or {}).get("checks") or []
              if c.get("id") in ("crilc", "cibil", "crif", "cfr", "ews") and c.get("status") not in (None, "not_started")]
    if checks:
        quality = (quality + " " if quality else "") + "Checks: " + "; ".join(
            f"{c.get('name')} {c.get('status')}" for c in checks) + "."
    add("asset_quality_status", quality, "CRILC exposure (reference data) and the due-diligence checks", "external", "external",
        {"system": "CRILC / bureau checks (demo data)"})
    # past proposals: the LOS's own history for this borrower
    history = ctx.get("entity_history")
    if history is not None:
        past = [h for h in history if h["status"] in ("REJECTED", "DROPPED", "WITHDRAWN") or h.get("deferrals")]
        text = ("No earlier proposal for this borrower in the LOS was rejected, dropped, withdrawn or deferred "
                f"({len(history)} earlier application(s) on record)." if not past else
                "\n".join(f"• {h['application_id']}: {h['status'].lower()}" + (f" — {h['reason']}" if h.get("reason") else "")
                          + (f"; deferred {len(h['deferrals'])} time(s)" if h.get("deferrals") else "") for h in past))
        add("past_proposals", text, "LOS application history", "source", "record", {"path": "LOS application history"})
    else:
        add("past_proposals", None, "LOS application history", "source", "record", {"path": "LOS application history"})
    # committee directions: the in-principle sanction and its minutes, to be confirmed
    ip = (app.get("sanctions") or {}).get("IP")
    add("committee_directions",
        (f"In-principle sanction by {ip['by_name']} on {ip['at'][:10]} for ₹{ip['sanctioned_cr']:,.2f} Cr"
         + (f"; minutes: {ip['minutes']}" if ip.get("minutes") else "")
         + ". Confirm that its directions and conditions have been complied with.") if ip else None,
        "IP sanction record", "source", "record", {"path": "IP sanction record"})
    # reason for the committee: the approval matrix
    auth = ctx.get("authority")
    add("committee_reason",
        (f"The proposed exposure of ₹{auth['amount_cr']:,.2f} Cr at risk grade {auth.get('risk_grade') or '—'} with "
         f"{auth.get('deviations', 0)} deviation(s) falls to the {auth['required']} under the approval matrix "
         "(demo matrix — the bank's delegation applies).") if auth else None,
        "approval authority (demo matrix)")
    # justification: the reassessment's decision and its supporting factors
    factors = [f"{x.get('factor')} — {x.get('evidence')}" for x in rea.get("key_supporting_factors") or [] if x.get("factor")]
    fr = rea.get("facility_recommendation") or {}
    add("justification",
        (f"Credit reassessment: {rea.get('decision_label')}"
         + (f"; recommended ₹{float(fr['recommended_cr']):,.2f} Cr" if fr.get("recommended_cr") not in (None, "") else "")
         + ".\n" + "\n".join(f"• {f}" for f in factors[:6])) if rea.get("decision_label") else None,
        "credit reassessment (M6)")
    # no source on record: left for a person (unavailable, never invented)
    for key in ("promoter_pledge", "corporate_actions", "unhedged_exposure"):
        add(key, None, "no source on record — for the RM to complete")
    return out


def resolve_decision_notes(ctx: dict) -> list[dict]:
    case, reg, app = ctx["case"], ctx["registry"], ctx["app"]
    out = []

    def add(key, value, ev, prov="derived", source="engine"):
        out.append(_p(f"decision_notes.{key}", DECISION_NOTES[key], value, provenance=prov, source=source, registry=reg,
                      evidence=ev, target=["decision_notes", key], run_id=ctx.get("run_id")))

    rules = case.get("tier1_decisions") or (((case.get("fact_pack") or {}).get("policy_decisions") or {})
                                            .get("tier1_hard_rules") or [])
    if rules:
        counts = {r: sum(1 for x in rules if x.get("result") == r) for r in ("pass", "fail", "not_verified")}
        pending = [x.get("rule_description") or x.get("description") or x.get("rule_code") or x.get("rule")
                   for x in rules if x.get("result") != "pass"]
        add("policy_compliance",
            f"Policy engine hard rules: {counts['pass']} passed, {counts['fail']} failed, {counts['not_verified']} not "
            "verified." + (" Open: " + "; ".join(pending[:6]) + "." if pending else " The proposal complies with the "
                           "credit-policy hard rules."), {"engine": "policy engine — tier-1 hard rules"})
    else:
        add("policy_compliance", None, {"engine": "policy engine — tier-1 hard rules"})
    history = ctx.get("entity_history")
    if history is not None:
        sanctioned = [h for h in history if h["status"] == "APPROVED"]
        add("previous_relaxations",
            "Fresh proposal: no earlier sanction of this borrower in the LOS, so no deviations, waivers or relaxations "
            "were granted before." if not sanctioned else None,
            {"path": "LOS application history"}, "source", "record")
    else:
        add("previous_relaxations", None, {"path": "LOS application history"}, "source", "record")
    add("other_matters", None, {"engine": "for the maker to complete"})
    ip = (app.get("sanctions") or {}).get("IP")
    if app.get("stage_id") not in ("PS", "IP"):
        add("ip_observations", (f"IP sanction ({ip['by_name']}, {ip['at'][:10]})"
                                + (f": {ip['minutes']}" if ip.get("minutes") else ": no observations recorded in the minutes")
                                + ". Compliance to be confirmed by the maker.") if ip else None,
            {"path": "IP sanction record"}, "source", "record")
    return out


SECURITY_NOTES = {
    "creation_status": "Status of security creation and perfection, with estimated timelines",
    "change_since_last_sanction": "Comments on change in security (primary / collateral / guarantees) from the last sanction",
    "security_trustee": "Whether the security is held by a security trustee",
}


def resolve_security_notes(ctx: dict) -> list[dict]:
    """F-9: the security remarks of the bank's AP screen, from the securities record, the external work
    parties (security trustee) and the LOS history."""
    app, reg = ctx["app"], ctx["registry"]
    secs = app.get("securities") or []
    status = None
    if secs:
        created = [s for s in secs if s.get("creation_status") == "created"]
        perfected = [s for s in secs if s.get("perfection_status") == "perfected"]
        status = (f"{len(created)} of {len(secs)} security(ies) created and {len(perfected)} perfected."
                  + (" To be created before the first disbursement (pre-disbursement condition)." if len(created) < len(secs) else ""))
    history = ctx.get("entity_history")
    change = ("Fresh proposal: no earlier sanction of this borrower in the LOS, so no change from a previous sanction."
              if history is not None and not any(h["status"] == "APPROVED" for h in history) else None)
    st = next((e for e in app.get("ewps") or [] if str(e.get("type") or e.get("role") or "").lower() in ("st", "security_trustee")), None)
    trustee = (f"Yes — {st.get('name') or st.get('consultant_name')} appointed as security trustee" if st else None)
    out = []
    for key, value, ev in (("creation_status", status, {"path": "securities record"}),
                           ("change_since_last_sanction", change, {"path": "LOS application history"}),
                           ("security_trustee", trustee, {"path": "external work parties (security trustee)"})):
        out.append(_p(f"security_notes.{key}", SECURITY_NOTES[key], value, provenance="source", source="record",
                      registry=reg, evidence=ev, target=["security_notes", key], run_id=ctx.get("run_id")))
    return out


# ── coverage: how much of the IP Note the agents prepared (R-P1 acceptance) ────

def _any(d) -> bool:
    return isinstance(d, dict) and any(v not in (None, "", [], {}) for v in d.values())


IP_SECTIONS = [
    ("sourcing", "Sourcing details", lambda a: bool((a.get("sourcing") or {}).get("accepted")) or bool(a.get("cam"))),
    ("entity", "Entity details", lambda a: bool((a.get("customer_identity") or {}).get("pan"))),
    ("facility", "Facility details", lambda a: bool(a.get("facilities"))),
    ("shareholding", "Shareholding & group",
     lambda a: _any((a.get("proposal") or {}).get("shareholding")) or len(a.get("related_parties") or []) > 1),
    ("checks", "Verification checks",
     lambda a: any(c.get("status") not in (None, "not_started", "pending")
                   for c in (a.get("due_diligence") or {}).get("checks") or [])),
    ("financials", "Financials (CMA)", lambda a: any(s.get("rows") for s in (a.get("cma") or {}).get("subjects") or [])),
    ("rating", "Risk rating",
     lambda a: any(r.get("rating") for r in (a.get("ratings") or {}).get("external_ratings") or [])
     or any(r.get("grade") for r in (a.get("ratings") or {}).get("internal_ratings") or [])),
    ("narratives", "Proposal narratives",
     lambda a: sum(1 for v in ((a.get("proposal") or {}).get("background") or {}).values() if v) >= 6),
    ("exposure", "Exposure",
     lambda a: any(((a.get("proposal") or {}).get("exposure") or {}).get(k) is not None
                   for k in ("sanctioned_cr", "outstanding_cr"))
     or (((a.get("proposal") or {}).get("exposure") or {}).get("loan") or {}).get("total_cr") is not None),
    ("banking", "Banking arrangement", lambda a: bool(((a.get("proposal") or {}).get("banking") or {}).get("arrangement"))),
    ("project", "Project", lambda a: bool(a.get("projects"))),
    ("esms", "ESMS screening",
     lambda a: bool((a.get("esms") or {}).get("proposed_category"))
     or any(i.get("answer") for i in (a.get("esms") or {}).get("checklist") or [])),
    ("security", "Security", lambda a: bool(a.get("securities"))),
    ("terms", "Key terms & conditions",
     lambda a: any(not r.get("removed") for r in (a.get("terms") or {}).get("conditions") or [])),
    ("pricing", "Pricing & fees", lambda a: bool((a.get("pricing") or {}).get("facilities") or (a.get("pricing") or {}).get("fees"))),
    ("documents", "Documentation", lambda a: bool(a.get("ip_note")) or any(d.get("versions") for d in a.get("documents") or [])),
]


def _applicable(sid: str, app: dict) -> bool:
    if sid == "project":           # a project is recorded for term loans and project finance
        return any(f.get("facility_type") in ("term_loan", "project_finance") for f in app.get("facilities") or [])
    return True


def ip_coverage(app: dict) -> dict:
    """The IP sections the agents prepared; a section that does not apply (a project for a working-capital
    facility) is shown as not applicable and left out of the count."""
    sections = [{"id": sid, "label": label, "applicable": _applicable(sid, app),
                 "filled": _applicable(sid, app) and bool(check(app))} for sid, label, check in IP_SECTIONS]
    applicable = [s for s in sections if s["applicable"]]
    return {"sections": sections, "filled": sum(1 for s in applicable if s["filled"]), "total": len(applicable)}


RESOLVERS = {"narrative_more": resolve_narrative_more, "external_rating": resolve_external_rating,
             "shareholding": resolve_shareholding, "banking": resolve_banking, "project": resolve_project,
             "esms": resolve_esms, "fees": resolve_fees, "inter_firm": resolve_inter_firm,
             "cma_projection": resolve_cma_projection, "tnc": terms_mod.resolve_terms,
             "bank_narratives": resolve_bank_narratives, "decision_notes": resolve_decision_notes,
             "security_notes": resolve_security_notes}
