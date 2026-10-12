"""ESMS/ESDD governed process (Client One GAP-P1-02).

Screening date, the NaBFID excluded-activities checklist (Yes/No/Not
Available, with mandatory remarks for Yes or Not Available), the project /
entity E&S risk category, CPCB category, coastal-zone impact, resettlement,
environmental impact and E&S litigation, source and remarks, the proposed
category and E&S risk assessment, ESDD applicability, additional ESMS
conditions, the committee recommendation, structured evidence and the
generated ESMS Approval Note.

The exact categories, policy logic and questionnaires require the authoritative
bank policy (spec §23/P1-02) — the checklist items are the documented screen
fields and the gate enforces only the documented hard rule (remarks on
Yes / Not Available answers).
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from src.application.errors import InvalidRequestError

ANSWERS = ("Yes", "No", "Not Available")
ES_CATEGORIES = ("A", "B", "C")          # documented E&S risk category classes
GATES = ("no_esdd", "esdd_required", "excluded")

ES_CHECKLIST = [
    ("es_exploration", "The activity is not an excluded activity under the NaBFID list"),
    ("es_coastal", "The project is not within a restricted coastal regulatory zone (or impact assessed)"),
    ("es_resettlement", "No large-scale forced resettlement, or a resettlement plan is in place"),
    ("es_environmental", "Environmental impact assessed with a mitigation plan where required"),
    ("es_litigation", "No material pending E&S litigation"),
]


def initial_esms(app: dict) -> dict:
    return {"screening_date": None, "checklist": [], "category": None, "cpcb_category": None,
            "coastal_zone_impact": None, "resettlement": None, "environmental_impact": None,
            "es_litigation": None, "information_source": None, "remarks": None,
            "proposed_category": None, "introduction": None, "proposal_summary": None,
            "company_es_risk_assessment": None, "esdd": None, "additional_conditions": [],
            "committee_recommendation": None, "evidence": [], "status": "not_started"}


def normalise_checklist(items: list[dict], current: list[dict]) -> list[dict]:
    by_id = {i["id"]: dict(i) for i in current or []}
    if not by_id:
        by_id = {i: {"id": i, "label": label, "answer": None, "remarks": None, "source": None}
                 for i, label in ES_CHECKLIST}
    for raw in items or []:
        item = by_id.get(str(raw.get("id") or ""))
        if not item:
            raise InvalidRequestError(f"Unknown ESMS item: {raw.get('id')}")
        answer = str(raw.get("answer") or "").strip()
        if answer and answer not in ANSWERS:
            raise InvalidRequestError(f"ESMS item {item['id']}: answer must be Yes, No or Not Available")
        remarks = (str(raw.get("remarks") or "").strip() or None)
        if answer in ("Yes", "Not Available") and not remarks:
            raise InvalidRequestError(
                f"ESMS item {item['id']}: a remark is mandatory for a '{answer}' answer (GAP-P2-01)")
        item.update(answer=answer or None, remarks=remarks, source=(str(raw.get("source") or "").strip() or None))
    return list(by_id.values())


def esms_gate(esms: dict) -> Optional[str]:
    """GAP-P2-01: ESMS Yes/Not Available remarks are mandatory; an excluded answer blocks."""
    if not esms:
        return "ESMS screening has not been started"
    if not esms.get("screening_date"):
        return "The ESMS screening date is required"
    open_items = [i["label"] for i in esms.get("checklist", []) if not i.get("answer")]
    if open_items:
        return "The excluded-activity checklist is not complete: " + "; ".join(open_items[:3]) + \
               ("…" if len(open_items) > 3 else "")
    if esms.get("category") not in ES_CATEGORIES:
        return "The E&S risk category (A, B or C) is required"
    if esms["category"] == "A" and not esms.get("esdd"):
        return "A Category-A assessment requires the ESDD applicability decision"
    return None


def approval_note(app: dict, esms: dict) -> str:
    """The generated ESMS Approval Note (GAP-P1-06)."""
    from src.engines.cam_composer import fmt
    rows = "".join(
        f"<tr><td>{i['label']}</td><td>{i.get('answer') or '—'}</td>"
        f"<td>{i.get('remarks') or i.get('source') or '—'}</td></tr>"
        for i in esms.get("checklist", []))
    return f"""
    <h2>ESMS Approval Note — {app.get('borrower_name')}</h2>
    <p><b>CLOS {app.get('application_id')}</b> · screening date {esms.get('screening_date') or '—'} ·
    E&amp;S risk category <b>{esms.get('category') or '—'}</b>{' · CPCB ' + esms['cpcb_category'] if esms.get('cpcb_category') else ''}</p>
    <table><tr><th>Excluded-activity screen</th><th>Answer</th><th>Remarks / source</th></tr>{rows}</table>
    <p><b>ESDD:</b> {esms.get('esdd') or '—'}</p>
    <p><b>Assessment:</b> {esms.get('company_es_risk_assessment') or '—'}</p>
    <p><b>Additional ESMS conditions:</b> {'; '.join(esms.get('additional_conditions') or []) or 'None'}</p>
    <p><b>Committee recommendation:</b> {esms.get('committee_recommendation') or '—'}</p>
    <p class="note">Generated by the LOS from the recorded ESMS screen. Category logic and the full
    questionnaire require the authoritative bank policy (spec §23/P1-02).</p>"""
