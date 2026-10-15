"""
Reconciliation agents: populate the governed workspaces from the credit case, the
borrower record and the documents — one agent per domain, run in parallel.

    cma               entity-wise CMA rows per period, from the statements the engines ran on;
                      the latest year is reconciled against the figures read from the documents
    parties           directors and group entities (management profile, corporate hierarchy)
    securities        the collateral the case assessed (type, value, valuation date, charge)
    exposure          existing and bureau exposure
    internal_rating   the engine's risk grade (a labelled demo mapping to the bank's scale)
    facility_pricing  benchmark and spread per facility from the demo grid (labelled synthetic)
    conduct           account conduct of an existing customer
    narrative         proposal background: business, industry outlook, strengths, key risks

Every value is a field-store proposal with its evidence and a ``target`` (where it lives in
the application). ``materialise`` writes the field store's *current* value — the person's
decision when there is one, else the proposal — into the workspace, but never over a value a
person entered in the workspace directly. An override therefore flows back into the workspace.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from src.engines.data_provenance import NOT_AVAILABLE
from src.los import cma as cma_mod
from src.los import securities as sec_mod
from src.los.fields.registry import FieldRegistry

DOMAINS = ("cma", "parties", "securities", "exposure", "internal_rating", "facility_pricing", "conduct", "narrative")

# Demo pricing grid (the bank's pricing model is not connected; mirrors the Risk Maker demo grid).
_DEMO_BENCHMARK, _DEMO_BENCHMARK_RATE = "1-year MCLR", 8.40
_DEMO_SPREAD_BPS = {"A": 75, "B": 125, "C": 175, "D": 250, "E": 350}
_PRIMARY = re.compile(r"current asset|stock|book debt|receivable|hypothecation|inventory|plant|machinery|project", re.I)
_TYPE_MAP = (("land", "land_building"), ("building", "land_building"), ("plant", "plant_machinery"),
             ("machinery", "plant_machinery"), ("stock", "stock"), ("inventory", "stock"), ("current asset", "stock"),
             ("book debt", "book_debtors"), ("receivable", "book_debtors"), ("deposit", "deposit"),
             ("guarantee", "guarantee"))


def _slug(text: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text or "").lower()).strip("_")[:40] or "x"


def _p(fid: str, label: str, value, *, provenance: str, source: str, evidence: dict, target: list,
       confidence: Optional[float] = None, registry: FieldRegistry, value_type: str = "text",
       issues: Optional[list] = None, run_id: Optional[str] = None) -> dict:
    missing = value in (None, "", [], {})
    return {"field_id": fid, "domain": fid.split(".", 1)[0], "label": label,
            "value": NOT_AVAILABLE if missing else value, "provenance": "unavailable" if missing else provenance,
            "source": source, "evidence": evidence, "target": target, "value_type": value_type,
            "confidence": 0.0 if missing else (registry.confidence_for(provenance) if confidence is None else confidence),
            "issues": list(issues or []), "resolver": "reconciliation", "run_id": run_id}


# ── resolvers (pure: case / company / app snapshot → proposals) ─────────────────

def resolve_cma(ctx: dict) -> list[dict]:
    company, reg, prefill = ctx["company"], ctx["registry"], ctx.get("prefill_values") or {}
    fins = company.get("financials") or {}
    if not fins:                                    # the statements the case summarised (fewer rows)
        summary = (ctx["fact_pack"].get("financial_summary") or {}).get("periods") or {}
        fins = {p: {"source": v.get("data_source") or "financial summary",
                    "line_items": {"revenue_operating": v.get("revenue_cr"), "pat": v.get("pat_cr")}}
                for p, v in summary.items()}
    periods = sorted(fins)[-3:]
    subject = {"find": {"subject": "borrower"}, "new": {"subject": "borrower", "rows": {}, "versions": [], "origin": "agent"}}
    out = []
    for period in periods:
        fs = fins[period]
        li = (fs.get("line_items") if isinstance(fs, dict) else getattr(fs, "line_items", {})) or {}
        source = (fs.get("source") if isinstance(fs, dict) else getattr(fs, "source", "")) or "statement"
        dep, fin, pbt, pat = li.get("depreciation"), li.get("finance_cost"), li.get("pbt"), li.get("pat")
        expenses = sum(li.get(k) or 0 for k in ("raw_material_cost", "employee_cost", "other_expenses")) or None
        rows = {"revenue": li.get("revenue_operating"), "income": li.get("total_income"), "expenses": expenses,
                "depreciation": dep, "finance_cost": fin, "pbt": pbt, "pat": pat,
                "cash_accruals": (pat + dep) if pat is not None and dep is not None else None}
        for row_id, label in cma_mod.CMA_ROWS:
            value = rows.get(row_id)
            issues = []
            doc = prefill.get({"revenue": "revenue_cr", "pat": "pat_cr"}.get(row_id, ""))
            if period == periods[-1] and doc and value and abs(float(doc["value"]) - value) > max(1.0, 0.02 * value):
                issues.append(f"Documents state {doc['value']:,.2f} Cr ({doc.get('document')} p{doc.get('page')}) "
                              f"vs {value:,.2f} Cr in the {source} statement")
            out.append(_p(f"cma.borrower.{period}.{row_id}", f"{label} · {period}",
                          round(value, 2) if isinstance(value, (int, float)) else value,
                          provenance="source", source="record", registry=reg, value_type="number", issues=issues,
                          evidence={"path": f"financial statement {period} ({source})",
                                    "line_items": sorted(k for k in ("revenue_operating", "total_income", "pbt", "pat") if li.get(k) is not None)},
                          target=["cma", "subjects", subject, "rows", period, row_id], run_id=ctx.get("run_id")))
    return out


def resolve_parties(ctx: dict) -> list[dict]:
    fp, reg = ctx["fact_pack"], ctx["registry"]
    out = []
    for d in (fp.get("management_profile") or {}).get("directors") or []:
        if not d.get("name"):
            continue
        key = f"din_{d['din']}" if d.get("din") else _slug(d["name"])
        role = "promoter" if d.get("is_promoter") else "director"
        out.append(_p(f"parties.{key}.name", f"{role.title()}: {d['name']}", d["name"], provenance="source",
                      source="record", registry=reg, evidence={"path": d.get("source") or "management profile"},
                      target=["related_parties", {"find": {"agent_key": key}, "new": {
                          "agent_key": key, "name": d["name"], "role": role, "party_type": "individual",
                          "ownership_pct": None, "pan": None, "cin": None,
                          "relationship": f"{d.get('designation') or role.title()}" + (f" · DIN {d['din']}" if d.get("din") else ""),
                          "sourced_address": None, "key_person_role": d.get("designation"), "party_status": "active",
                          "verification_status": "pending", "origin": "agent"}}, "name"], run_id=ctx.get("run_id")))

    def walk(nodes):
        for n in nodes or []:
            if n.get("relationship") != "self" and n.get("company_name"):
                rel = str(n.get("relationship") or "group_company").lower()
                role = rel if rel in ("subsidiary", "associate", "parent", "joint_venture") else "group_company"
                key = _slug(n["company_name"])
                out.append(_p(f"parties.{key}.name", f"{role.replace('_', ' ').title()}: {n['company_name']}",
                              n["company_name"], provenance="source", source="record", registry=reg,
                              evidence={"path": "corporate hierarchy"},
                              target=["related_parties", {"find": {"agent_key": key}, "new": {
                                  "agent_key": key, "name": n["company_name"], "role": role,
                                  "party_type": "non_individual", "ownership_pct": n.get("holding_pct"),
                                  "pan": n.get("pan"), "cin": n.get("cin"), "relationship": rel.replace("_", " "),
                                  "sourced_address": None, "key_person_role": None, "party_status": "active",
                                  "verification_status": "pending", "origin": "agent"}}, "name"], run_id=ctx.get("run_id")))
            walk(n.get("children"))

    walk((fp.get("corporate_hierarchy") or {}).get("hierarchy_tree"))
    return out


def resolve_securities(ctx: dict) -> list[dict]:
    fp, reg, app = ctx["fact_pack"], ctx["registry"], ctx["app"]
    facility_ids = [f["facility_id"] for f in app.get("facilities") or []]
    prefill = (ctx.get("prefill_values") or {}).get("collateral_mv_cr")
    items = (fp.get("collateral_analysis") or {}).get("collaterals") or []
    total = sum(float(x.get("market_value_cr") or 0) for x in items)
    out = []
    for x in items:
        text = f"{x.get('type')} {x.get('description')}"
        typ = next((t for k, t in _TYPE_MAP if k in text.lower()), None)
        enc = str(x.get("encumbrance") or "").lower()
        key = _slug(x.get("description") or x.get("type"))
        issues = ([f"Documents state a total market value of {prefill['value']:,.2f} Cr ({prefill.get('document')}) "
                   f"vs {total:,.2f} Cr assessed"] if prefill and abs(float(prefill["value"]) - total) > max(1.0, 0.02 * total)
                  else [])
        out.append(_p(f"securities.{key}.proposed_value_cr", f"Security value: {x.get('description') or x.get('type')}",
                      x.get("market_value_cr"), provenance="source", source="record", registry=reg, value_type="number",
                      issues=issues, evidence={"path": "collateral analysis (valuation " + str(x.get("valuation_date")) + ")"},
                      target=["securities", {"find": {"agent_key": key}, "new": {
                          **sec_mod.blank_security(0), "agent_key": key, "origin": "agent",
                          "category": "primary" if _PRIMARY.search(text) else "collateral", "type": typ,
                          "description": x.get("description"), "facility_ids": facility_ids,
                          "valuation_date": x.get("valuation_date"), "valuation_basis": "market value (assessed)",
                          "charge_type": {"pari-passu": "pari_passu", "pari_passu": "pari_passu", "first": "first_charge",
                                          "second": "second_charge"}.get(enc)}}, "proposed_value_cr"],
                      run_id=ctx.get("run_id")))
    return out


def resolve_exposure(ctx: dict) -> list[dict]:
    fp, reg, company = ctx["fact_pack"], ctx["registry"], ctx["company"]
    ei = fp.get("external_intelligence") or {}
    existing = company.get("existing_exposure") or []
    sanctioned = round(sum(float(getattr(e, "sanctioned_limit_cr", 0) or 0) for e in existing), 2) if existing else None
    outstanding = round(sum(float(getattr(e, "outstanding_cr", 0) or 0) for e in existing), 2) if existing else None
    bank_path = "core-banking existing exposure (demo data)"
    if not existing and (ctx["app"].get("customer_identity") or {}).get("ntb_etb") == "NTB":
        sanctioned, outstanding = 0.0, 0.0                 # new to bank: nil with the bank is a fact, not a gap
        bank_path = "core banking: new-to-bank customer, no accounts with the bank (demo data)"
    base = ["proposal", "exposure"]
    return [
        _p("exposure.bureau.total_cr", "Bureau-reported total exposure (₹ Cr)", ei.get("bureau_total_exposure_cr"),
           provenance="external", source="external", registry=reg, value_type="number",
           evidence={"system": "commercial bureau (demo data)", "lenders": ei.get("bureau_total_lenders")},
           target=base + ["loan", "total_cr"], run_id=ctx.get("run_id")),
        _p("exposure.bank.sanctioned_cr", "Existing sanctioned limits with the bank (₹ Cr)", sanctioned,
           provenance="source", source="record", registry=reg, value_type="number",
           evidence={"path": bank_path}, target=base + ["sanctioned_cr"],
           run_id=ctx.get("run_id")),
        _p("exposure.bank.outstanding_cr", "Existing outstanding with the bank (₹ Cr)", outstanding,
           provenance="source", source="record", registry=reg, value_type="number",
           evidence={"path": bank_path}, target=base + ["outstanding_cr"],
           run_id=ctx.get("run_id")),
    ]


def _grade(ctx: dict) -> Optional[str]:
    pol = (ctx["fact_pack"].get("policy_decisions") or {}).get("tier3_recommendation") or {}
    return pol.get("risk_grade") or ctx["case"].get("risk_grade")


def resolve_internal_rating(ctx: dict) -> list[dict]:
    grade, reg = _grade(ctx), ctx["registry"]
    pol = (ctx["fact_pack"].get("policy_decisions") or {}).get("tier3_recommendation") or {}
    return [_p("internal_rating.borrower.grade", "Internal rating — borrower (engine grade)", grade,
               provenance="synthetic_demo", source="engine", registry=reg,
               evidence={"engine": "policy engine tier 2 (demo mapping; the bank's MLRA model is not connected)",
                         "composite_score": pol.get("composite_score")},
               target=["ratings", "internal_ratings", {"find": {"subject": "borrower"}, "new": {
                   "subject": "borrower", "party_name": ctx["app"].get("borrower_name"), "grade": None,
                   "score": pol.get("composite_score"), "date": ctx["today"],
                   "note": "Proposed by the reconciliation agent from the engine grade (demo mapping)",
                   "origin": "agent"}}, "grade"], run_id=ctx.get("run_id"))]


def resolve_facility_pricing(ctx: dict) -> list[dict]:
    grade, reg, out = _grade(ctx), ctx["registry"], []
    spread = _DEMO_SPREAD_BPS.get(grade)
    for f in ctx["app"].get("facilities") or []:
        if f.get("facility_nature") != "fund_based":
            continue
        fid = f["facility_id"]
        ev = {"engine": f"demo pricing grid by risk grade ({grade or '—'}); the bank's pricing model is not connected"}
        tgt = ["pricing", "facilities", fid]
        out.append(_p(f"facility_pricing.{fid}.proposed_benchmark", f"{fid} benchmark", _DEMO_BENCHMARK,
                      provenance="synthetic_demo", source="engine", registry=reg, evidence=ev,
                      target=tgt + ["proposed_benchmark"], run_id=ctx.get("run_id")))
        out.append(_p(f"facility_pricing.{fid}.proposed_spread_bps", f"{fid} spread (bps)", spread,
                      provenance="synthetic_demo", source="engine", registry=reg, evidence=ev, value_type="number",
                      target=tgt + ["proposed_spread_bps"], run_id=ctx.get("run_id")))
        out.append(_p(f"facility_pricing.{fid}.proposed_rate", f"{fid} rate of interest (%)",
                      round(_DEMO_BENCHMARK_RATE + spread / 100, 2) if spread is not None else None,
                      provenance="synthetic_demo", source="engine", registry=reg, evidence=ev, value_type="number",
                      target=tgt + ["proposed_rate"], run_id=ctx.get("run_id")))
    return out


def resolve_conduct(ctx: dict) -> list[dict]:
    reg, out = ctx["registry"], []
    for r in (ctx["company"].get("conduct") or [])[-12:]:
        period = getattr(r, "period", None)
        if not period:
            continue
        irregular = (getattr(r, "overdue_instances", 0) or 0) > 0 or (getattr(r, "cheque_returns", 0) or 0) > 0
        status = "irregular" if irregular else "regular"
        out.append(_p(f"conduct.{_slug(period)}.status", f"Account conduct {period}", status, provenance="source",
                      source="record", registry=reg,
                      evidence={"path": "core-banking conduct (demo data)",
                                "utilisation_pct": getattr(r, "limit_utilization_pct", None),
                                "overdue_instances": getattr(r, "overdue_instances", None),
                                "max_overdue_days": getattr(r, "max_overdue_days", None)},
                      target=["proposal", "conduct", "rows", {"find": {"month": period}, "new": {
                          "month": period, "limit_cr": None, "outstanding_cr": None,
                          "irregularity": "overdue / cheque returns" if irregular else None, "peak_irregularity_cr": None,
                          "instances": getattr(r, "overdue_instances", None),
                          "irregular_days": getattr(r, "max_overdue_days", None), "financial_difficulty": False,
                          "remarks": "Proposed from core-banking conduct (demo data)", "status": status,
                          "origin": "agent"}}, "status"], run_id=ctx.get("run_id")))
    return out


def resolve_narrative(ctx: dict) -> list[dict]:
    fp, reg = ctx["fact_pack"], ctx["registry"]
    bp, ind = fp.get("borrower_profile") or {}, fp.get("industry_analysis") or {}
    cs = fp.get("case_summary") or {}
    business = " ".join(x for x in [
        f"{bp.get('company_name')} is a {str(cs.get('borrower_type') or 'corporate').replace('_', ' ')} borrower"
        + (f" incorporated on {bp['date_of_incorporation']}" if bp.get("date_of_incorporation") else "")
        + (f", registered in {bp['registered_state']}" if bp.get("registered_state") else "") + ".",
        f"Sector: {str(cs.get('sector') or '').replace('_', ' ')}." if cs.get("sector") else "",
        f"External rating {bp['credit_rating']}." if bp.get("credit_rating") else ""] if x)
    drivers = ind.get("growth_drivers") or []
    outlook = " ".join(x for x in [ind.get("industry_overview"),
                                   ("Growth drivers: " + "; ".join(map(str, drivers[:4])) + ".") if drivers else ""] if x)
    strengths = "\n".join(f"• {s.get('detail')}" for s in fp.get("credit_strengths") or [] if s.get("detail"))
    risks = "\n".join(f"• {r.get('detail')} ({r.get('severity')})" for r in fp.get("key_risks") or [] if r.get("detail"))
    facts = json.dumps({k: fp.get(k) for k in ("borrower_profile", "credit_strengths", "key_risks", "case_summary")},
                       default=str)[:6000]
    base = ["proposal", "background"]
    mk = lambda key, label, text, eng: _p(f"narrative.background.{key}", label, text or None, provenance="derived",
                                          source="ai_draft" if ctx.get("ai_text") else "engine", registry=reg,
                                          evidence={"engine": eng, "facts": facts}, target=base + [key],
                                          run_id=ctx.get("run_id"))
    return [mk("borrower_and_business", "Borrower and business", business, "borrower profile (fact pack)"),
            mk("industry_outlook", "Industry outlook", outlook, "industry analysis (fact pack)"),
            mk("strengths", "Strengths", strengths, "credit strengths (fact pack)"),
            mk("key_risks", "Key risks", risks, "key risks (fact pack)")]


RESOLVERS = {"cma": resolve_cma, "parties": resolve_parties, "securities": resolve_securities,
             "exposure": resolve_exposure, "internal_rating": resolve_internal_rating,
             "facility_pricing": resolve_facility_pricing, "conduct": resolve_conduct, "narrative": resolve_narrative}


# ── materialise: field-store values into the workspaces ────────────────────────

def _path_key(target: list) -> str:
    return json.dumps([seg["find"] if isinstance(seg, dict) else seg for seg in target], sort_keys=True, default=str)


def _coerce(value, value_type: str):
    if value_type == "number" and value not in (None, ""):
        try:
            return round(float(str(value).replace(",", "")), 4)
        except ValueError:
            return value
    return value


def _seq_ids(container: list, item: dict, target: list) -> None:
    """New agent list items get the workspace's own sequential id."""
    if target and target[0] == "related_parties":
        item["party_id"] = f"RP-{len(container) + 1:03d}"
    elif target and target[0] == "securities":
        item["security_id"] = f"SEC-{len(container) + 1:03d}"
    elif target and target[0] == "projects":
        item["project_id"] = f"PRJ-{len(container) + 1:03d}"
    elif target[:2] == ["pricing", "fees"]:
        item["fee_id"] = f"APF-{len(container) + 1:02d}"
    elif target[:2] == ["disops", "fees"]:
        item["fee_id"] = f"FEE-{len(container) + 1:02d}"
    elif target[:2] == ["terms", "conditions"]:
        from src.los.terms import next_id
        item["term_id"] = next_id(container)


def _resolve_parent(app: dict, target: list, create: bool):
    """Walk to the container of the leaf; list items are found by their ``find`` keys and
    created from ``new`` when ``create``. Returns (parent, leaf key) or (None, None)."""
    node = app
    for i, seg in enumerate(target[:-1]):
        nxt = target[i + 1]
        if isinstance(seg, dict):                      # list item
            item = next((x for x in node if all(x.get(k) == v for k, v in seg["find"].items())), None)
            if item is None:
                if not create:
                    return None, None
                item = json.loads(json.dumps(seg["new"]))
                _seq_ids(node, item, target)
                node.append(item)
            node = item
            continue
        if seg not in node or node[seg] is None:
            if not create:
                return None, None
            node[seg] = [] if isinstance(nxt, dict) else {}
        node = node[seg]
    return node, target[-1]


def materialise(app: dict, fields: dict, field_ids: Optional[list] = None) -> dict:
    """Write each workspace field's current value (decided, else proposed) into the application.
    A slot holding a value the agents did not write is a person's entry: it is never overwritten."""
    owned = app.setdefault("agent_writes", {})
    written, skipped = 0, 0
    for fid, rec in fields.items():
        if field_ids is not None and fid not in field_ids:
            continue
        prop = rec.get("proposal") or {}
        target = prop.get("target")
        if not target or (rec.get("value") in (None, "", NOT_AVAILABLE) and not rec.get("decision")):
            continue
        value = _coerce(rec.get("value"), prop.get("value_type") or "text")
        if value == NOT_AVAILABLE:
            continue
        key = _path_key(target)
        parent, leaf = _resolve_parent(app, target, create=True)
        if parent is None:
            continue
        current = parent.get(leaf) if isinstance(parent, dict) else None
        if (current not in (None, "", [], {}) and key not in owned and current != value
                and not rec.get("decision")):
            skipped += 1                                # a person's own entry in the workspace
            continue                                    # (a decision in the field store does replace it)
        if current != value:
            parent[leaf] = value
            written += 1
        owned[key] = {"field_id": fid, "status": rec.get("status")}
    return {"written": written, "kept_person_entries": skipped}
