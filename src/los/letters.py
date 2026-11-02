"""
Term sheet and sanction letter (LOS Phase 7), generated from the structured sanction.

  term sheet       indicative terms after the in-principle sanction;
  sanction letter  the final terms after the committee (AP) sanction, with the
                   conditions precedent / subsequent from the conditions tracker,
                   covenants, security and the deviations the sanction approved.

Every figure comes from the application record (sanction, facility, conditions,
borrower master, credit case). Pricing is the demo pricing grid and is printed as
such — the bank's pricing model is not connected. Each generation is stored as an
immutable version with who issued it and when; the document is marked as a demo.
"""

from __future__ import annotations

import html as _html
from datetime import datetime, timedelta
from typing import Optional

from src.engines.cam_composer import fmt
from src.los.post_sanction import build_conditions

LETTER_VERSION = "los_letters/v1"
KINDS = {"term_sheet": "Term sheet (indicative)", "sanction_letter": "Sanction letter"}
ACCEPTANCE_DAYS = 30
BANK = "Institution — Corporate Banking"   # neutral default; the profile's branding is what prints
DEMO_MARK = "DEMO DOCUMENT generated for demonstration — not an offer, commitment or sanction of any institution."
_SPREAD_BPS = {"A": 75, "B": 125, "C": 175, "D": 250, "E": 350}     # same demo grid as the Risk Maker pricing tab
_BENCHMARK = ("1-year MCLR", 8.40)


def letter_branding(app: dict) -> dict:
    """The institution's letter branding (name, kind titles, acceptance, demo mark) — from the
    application's institution profile and product template; the neutral defaults above apply
    to a profile-less app."""
    from src.los import profiles
    try:
        lb = profiles.letter_branding(profiles.get_profile(app=app))
        if app.get("product"):
            from src.los import products as prodmod
            try:
                ovr = prodmod.output_template("sanction_letter", profiles.get_profile(app=app),
                                               prodmod.get_product(app["product"]))
                if ovr.get("kind_titles"):
                    lb["kind_titles"] = {**lb["kind_titles"], **ovr["kind_titles"]}
            except prodmod.ProductError:
                pass
        return lb
    except Exception:
        return {"institution_name": BANK, "short_name": "", "paper_header": "",
                "demo_mark": DEMO_MARK, "kind_titles": dict(KINDS), "acceptance_days": ACCEPTANCE_DAYS,
                "bank_term": "the institution"}


def available(app: dict, kind: str) -> tuple[bool, str]:
    sanctions = app.get("sanctions") or {}
    if kind == "term_sheet":
        return ("IP" in sanctions, "Available after the in-principle sanction.")
    if kind == "sanction_letter":
        return ("AP" in sanctions, "Available after the final committee sanction (AP stage).")
    return (False, "Unknown document")


def _pricing(grade: Optional[str]) -> dict:
    name, rate = _BENCHMARK
    spread = _SPREAD_BPS.get((grade or "").upper()[:1]) if grade else None
    if spread is None:
        return {"text": f"{name} plus a spread to be advised under the bank's pricing policy", "provenance": "template"}
    roi = round(rate + spread / 100, 2)
    return {"text": f"{name} ({rate:.2f}%) + {spread} bps = {roi:.2f}% p.a., payable monthly — indicative demo pricing "
                    f"for risk grade {grade}; not a bank rate", "provenance": "synthetic_demo"}


def _security(company: dict) -> list[str]:
    rows = []
    for c in (company or {}).get("collateral") or []:
        rows.append(f"{c.collateral_type}: {c.description} — market value {fmt(c.market_value_cr, 'cr')}, "
                    f"forced-sale value {fmt(c.forced_sale_value_cr, 'cr')} (encumbrance: {c.encumbrance_status})")
    return rows or ["Security as per the credit appraisal — details not available from submitted information"]


def _covenants(case: Optional[dict], thresholds: dict) -> tuple[list[str], str]:
    proposed = (case or {}).get("covenants_proposed") or []
    if proposed:
        return [str(c) for c in proposed], "Credit case (proposed covenants)"
    t = thresholds or {}
    rows = [f"Minimum DSCR ≥ {t['min_dscr']}x" if t.get("min_dscr") else None,
            f"Maximum Debt / Equity ≤ {t['max_debt_to_equity']}x" if t.get("max_debt_to_equity") else None,
            f"Maximum Debt / EBITDA ≤ {t['max_debt_to_ebitda']}x" if t.get("max_debt_to_ebitda") else None,
            f"Minimum current ratio ≥ {t['min_current_ratio']}x" if t.get("min_current_ratio") else None,
            "Quarterly financial submission within 45 days of quarter-end"]
    return [r for r in rows if r], "Credit policy thresholds (standard covenants)"


def build_letter(kind: str, app: dict, company: dict, case: Optional[dict], deviations: list[dict],
                 thresholds: dict, issued_by: str, now: datetime, version: int) -> dict:
    sanctions = app.get("sanctions") or {}
    s = sanctions.get("AP" if kind == "sanction_letter" else "IP")
    b = (company or {}).get("borrower")
    fac = s.get("facility") or app.get("facility") or {}
    grade = ((app.get("assessments") or {}).get("AP" if kind == "sanction_letter" else "IP")
             or app.get("credit_assessment") or {}).get("risk_grade")
    if kind == "sanction_letter" and app.get("conditions"):
        conds = app["conditions"]
        cond_source = "Conditions tracker"
    else:
        conds = build_conditions(case, datetime.fromisoformat(s["at"]))
        cond_source = "Credit reassessment and bank standard documentation"
    covenants, cov_source = _covenants(case, thresholds)
    ref = f"{app['application_id']}/{'SL' if kind == 'sanction_letter' else 'TS'}/{version}"
    lb = letter_branding(app)
    from src.los import profiles as _profiles
    _prof = _profiles.get_profile(app=app)
    _lb_tpl = _profiles.output_template("sanction_letter" if kind == "sanction_letter" else "term_sheet", _prof)
    if app.get("product"):
        from src.los import products as _prodmod
        try:
            _lb_tpl = _prodmod.output_template("sanction_letter" if kind == "sanction_letter" else "term_sheet",
                                               _prof, _prodmod.get_product(app["product"]))
        except _prodmod.ProductError:
            pass
    _br = _profiles.institution_branding(_prof)
    bank_term = lb.get("bank_term") or "the institution"
    terms = [
        ("Borrower", getattr(b, "company_name", app.get("borrower_name")), "source"),
        ("CIN / PAN", f"{getattr(b, 'cin', None) or '—'} / {getattr(b, 'pan', None) or '—'}", "source"),
        ("Facility", (fac.get("facility_type") or "").replace("_", " ").title() or "—", "source"),
        ("Amount" + (" sanctioned" if kind == "sanction_letter" else " (in-principle)"), fmt(s["sanctioned_cr"], "cr"), "source"),
        ("Amount requested", fmt(s.get("requested_cr"), "cr") if s.get("requested_cr") else "—", "source"),
        ("Tenor", f"{fac['tenor_months']} months" if fac.get("tenor_months") else "As per the facility agreement", "source"),
        ("Purpose", fac.get("purpose") or "As per the credit appraisal", "source"),
        ("Rate of interest", _pricing(grade)["text"], _pricing(grade)["provenance"]),
        ("Processing fee", "As per the bank's schedule of charges", "template"),
        ("Repayment", "As per the repayment schedule in the facility agreement", "template"),
        ("Sanctioning authority", f"{s['by_name']} on {s['at'][:10]}", "source"),
    ]
    approved_devs = [d for d in deviations if d["category"] in ("Policy", "Sanction", "IP → AP", "Condition")]
    return {
        "kind": kind, "title": lb["kind_titles"].get(kind) or KINDS[kind], "version": version, "reference": ref,
        "letter_version": LETTER_VERSION,
        "issued_at": now.isoformat(timespec="seconds"), "issued_by": issued_by,
        "valid_until": (now + timedelta(days=lb["acceptance_days"])).date().isoformat(),
        "bank": lb["institution_name"], "demo_mark": lb.get("demo_mark") or DEMO_MARK,
        "bank_term": bank_term,
        "branding": _br,
        "product": (({  "name": _prodmod.get_product(app["product"])["product"]["name"]}
                     if app.get("product") else None)),
        "sections": _profiles.section_plan(kind, _lb_tpl, _prof),
        "addressee": {"name": getattr(b, "company_name", app.get("borrower_name")),
                      "address": getattr(b, "registered_address", None) or ""},
        "subject": (f"Sanction of {fmt(s['sanctioned_cr'], 'cr')} "
                    f"{(fac.get('facility_type') or 'credit facility').replace('_', ' ')}"
                    if kind == "sanction_letter" else
                    f"Indicative terms for {fmt(s['sanctioned_cr'], 'cr')} "
                    f"{(fac.get('facility_type') or 'credit facility').replace('_', ' ')}"),
        "terms": [{"label": l, "value": v, "provenance": p} for l, v, p in terms],
        "security": _security(company),
        "conditions_precedent": [{"id": c["id"], "text": c["text"], "status": c.get("status")} for c in conds
                                 if c["type"] == "CP"],
        "conditions_subsequent": [{"id": c["id"], "text": c["text"], "due": c.get("due")} for c in conds
                                  if c["type"] == "CS"],
        "conditions_source": cond_source,
        "covenants": covenants, "covenants_source": cov_source,
        "deviations": [{"description": d["description"], "detail": d["detail"], "status": d["status"]}
                       for d in approved_devs] if kind == "sanction_letter" else [],
        "minutes": s.get("minutes"),
        "standard_conditions_used": not bool((case or {}).get("reassessment")),
    }


def render_markdown(doc: dict) -> str:
    final = doc["kind"] == "sanction_letter"
    br = doc.get("branding") or {}
    prod = doc.get("product")
    lines = [f"# {doc['title']}", f"**{doc['bank']}**" + (f" · {br['app_name']}" if br.get("app_name") else "")
             + (f" · {prod['name']}" if prod else ""), "",
             f"Ref: {doc['reference']}  ·  Date: {doc['issued_at'][:10]}", "",
             f"To: **{doc['addressee']['name']}**  ", doc["addressee"]["address"] or "", "",
             f"**Subject: {doc['subject']}**", ""]
    if final:
        lines += ["We are pleased to convey the sanction of the credit facility described below, subject to the "
                  "terms and conditions set out in this letter and the facility documents."]
    else:
        lines += [f"Further to your proposal, we set out below the indicative terms on which {doc.get('bank_term', 'the institution')} "
                  "is prepared to proceed with the appraisal. These terms are not a commitment and are subject to final sanction."]

    def sec_body(sid):
        if sid == "terms":
            return ["| Term | Detail |", "|---|---|"] + [f"| {t['label']} | {t['value']} |" for t in doc["terms"]]
        if sid == "security":
            return [f"- {x}" for x in doc["security"]]
        if sid == "conditions_precedent":
            out = [f"_Source: {doc['conditions_source']}_"]
            out += [f"{i}. {c['text']}" for i, c in enumerate(doc["conditions_precedent"], 1)]
            return out
        if sid == "conditions_subsequent":
            return [f"{i}. {c['text']}" + (f" — by {c['due']}" if c.get("due") else "")
                    for i, c in enumerate(doc["conditions_subsequent"], 1)]
        if sid == "covenants":
            return [f"_Source: {doc['covenants_source']}_"] + [f"- {c}" for c in doc["covenants"]]
        if sid == "deviations" and doc["deviations"]:
            return [f"- {d['description']} — {d['detail']} ({d['status']})" for d in doc["deviations"]]
        return []

    sections = [s for s in (doc.get("sections") or []) if s["id"] in
                ("terms", "security", "conditions_precedent", "conditions_subsequent", "covenants", "deviations")]
    if not sections:
        sections = [{"id": k, "heading": {"terms": "Key terms", "security": "Security",
                                          "conditions_precedent": "Conditions precedent (before first disbursement)",
                                          "conditions_subsequent": "Conditions subsequent",
                                          "covenants": "Covenants",
                                          "deviations": "Deviations approved with this sanction"}[k]}
                    for k in ("terms", "security", "conditions_precedent", "conditions_subsequent", "covenants")]
        if final:
            sections.append({"id": "deviations", "heading": "Deviations approved with this sanction"})
    for s in sections:
        if sid_body := sec_body(s["id"]):
            lines += ["", f"## {s.get('heading') or s['id'].replace('_', ' ').title()}"] + sid_body
    lines += ["", f"This {'sanction' if final else 'term sheet'} is valid for acceptance until {doc['valid_until']}. "
                  "Please return a copy signed by your authorised signatory in token of acceptance.", "",
              f"For {doc['bank']}", "", f"Issued by: {doc['issued_by']}", "",
              "---", f"Accepted for and on behalf of {doc['addressee']['name']}: ______________________  Date: ________",
              "", f"_{doc['demo_mark']}_"]
    return "\n".join(lines)


def render_html(doc: dict) -> str:
    from src.rendering.cam_markdown import markdown_to_html

    title = f"{doc['title']} — {doc['addressee']['name']}"
    page = markdown_to_html(render_markdown(doc), title=title)
    page = page.replace(f"{_html.escape(title)} — CAM Report", _html.escape(title))
    br = doc.get("branding") or {}
    colors = br.get("colors") or {}
    primary, accent = colors.get("primary", "#1f2937"), colors.get("accent", "#6b7280")
    mono = _html.escape((br.get("short_name") or "LOS")[:3].upper())
    inst = _html.escape(br.get("institution_name") or doc.get("bank") or "Institution")
    app_name = _html.escape(br.get("app_name") or "")
    prod = doc.get("product") or {}
    prod_html = f"<span style='margin-left:10px;font-size:11px;color:{accent};font-weight:700'>{_html.escape(prod['name'])}</span>" if prod.get("name") else ""
    logo = (f"<img src='{_html.escape(br['logo'])}' alt='logo' style='width:44px;height:44px;border-radius:10px'>"
            if br.get("logo") else
            f"<div style='width:44px;height:44px;border-radius:10px;background:{primary};color:#fff;display:flex;"
            f"align-items:center;justify-content:center;font-weight:800;font-size:13px'>{mono}</div>")
    letterhead = (
        f"<div style='border-top:4px solid {primary};padding:14px 0 10px;margin-bottom:18px;"
        f"display:flex;align-items:center;gap:12px'>"
        f"{logo}"
        f"<div><div style='font-size:16px;font-weight:800;color:{primary}'>{inst}{prod_html}</div>"
        f"<div style='font-size:12px;color:#555'>" + (f"{app_name} · " if app_name else "")
        + f"Ref {_html.escape(str(doc.get('reference') or ''))} · {_html.escape(doc['addressee']['name'])}</div></div></div>")
    if "</head>" in page:
        page = page.replace("</head>", f"<style>body{{--lt-primary:{primary};--lt-accent:{accent}}}</style></head>", 1)
    page = page.replace("<body>", f"<body>{letterhead}", 1)
    if "<body>" not in page and "<body " in page:
        import re as _re
        page = _re.sub(r"(<body[^>]*>)", r"\1" + letterhead, page, count=1)
    return page


__all__ = ["KINDS", "available", "build_letter", "render_html", "render_markdown"]
