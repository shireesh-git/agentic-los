"""
Terms & conditions authored before sanction (G-F2), pre-filled by the T&C agent (R-P2).

The AP maker authors the T&C the committee sanctions: pre-commitment, pre-disbursement,
post-disbursement, conditions precedent to subsequent disbursement, financial covenants
(Annexure III), non-financial covenants, general and facility-specific conditions.

    agent      ``resolve_terms`` drafts them from the credit case: the reassessment's (M6)
               conditions precedent / subsequent and mitigants, the proposed covenants with
               their stipulated values, the policy engine's conditions, one end-use condition
               per facility, and the bank's standard documentation conditions (labelled
               template). Each is a field-store proposal verified at the AP maker step.
    people     add their own conditions, edit an agent's text (an override with a reason),
               change category / facility / stipulated value / frequency, remove one (with a
               reason) or restore it.
    sanction   at final sanction the T&C are locked and become the post-sanction conditions
               tracker (``to_conditions``) — the conditions tracked after sanction are the ones
               authored and approved at AP, not regenerated.
"""

from __future__ import annotations

import re
from typing import Optional

from src.application.errors import InvalidRequestError

DOMAIN = "tnc"
CATEGORIES = {
    "PC": "Pre-commitment condition", "CP": "Pre-disbursement condition", "PD": "Post-disbursement condition",
    "CPS": "Condition precedent to subsequent disbursement", "FC": "Financial covenant (Annexure III)",
    "NC": "Non-financial covenant", "CS": "Post-sanction covenant (subsequent)", "GC": "General condition",
    "FS": "Facility-specific condition",
}
FREQUENCIES = ("once", "quarterly", "half_yearly", "annual", "event_driven")
AUTHOR_STEPS = ("ap_note",)                           # where the T&C are authored (the AP maker)
DRAFT_STAGES = ("IP", "AP")

M6 = "Credit reassessment (M6)"
COVENANTS = "Proposed covenants (credit case)"
POLICY = "Policy engine conditions"
APPLICATION = "The application's facilities"
STANDARD = "Bank standard documentation"

# Bank-standard documentation conditions (templates, not borrower-specific analysis).
STANDARD_TERMS = [
    ("CP", "Execution of the facility agreement and security documents in the bank's approved format"),
    ("CP", "Creation and perfection of security, with the charge registered with ROC and CERSAI"),
    ("CP", "Board resolution authorising the borrowing and the execution of documents"),
    ("CP", "Insurance of the charged assets with the bank's clause, for the full value"),
    ("CPS", "No default outstanding on any existing facility at the time of a subsequent drawdown"),
    ("CPS", "Updated annual financials and end-use certificate for the amount disbursed"),
    ("CS", "End-use certificate from the statutory auditor for the amount disbursed"),
    ("CS", "Audited financial statements within 180 days of each financial year-end"),
    ("NC", "Compliance with applicable regulations and reporting obligations"),
]
_RATIO = re.compile(r"(current ratio|debt\s*/\s*equity|dscr|interest cover\w*|tol\s*/\s*tnw|debt\s*/\s*ebitda|"
                    r"fixed asset cover\w*|security cover\w*)", re.I)
_STIPULATION = re.compile(r"(>=|<=|≥|≤|>|<|minimum|maximum|at least|not exceeding)\s*([0-9.]+\s*x?)", re.I)


def slug(text) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text or "").lower()).strip("_")[:48] or "x"


def initial_terms() -> dict:
    return {"conditions": [], "status": "draft", "locked_at": None, "locked_by": None}


def blank_row(category: str, text: str, **extra) -> dict:
    return {"term_id": None, "agent_key": None, "category": category, "text": text, "facility_id": None,
            "party": None, "stipulated_value": None, "frequency": default_frequency(category),
            "source": None, "provenance": None, "origin": "person", "removed": False,
            "removed_reason": None, "history": [], **extra}


def default_frequency(category: str) -> str:
    return "once" if category in ("PC", "CP", "CPS") else ("annual" if category in ("FC", "CS") else "event_driven")


def _stipulation(text: str) -> Optional[str]:
    m = _STIPULATION.search(text or "")
    if not m:
        return None
    op = {"minimum": "≥", "at least": "≥", "maximum": "≤", "not exceeding": "≤", ">=": "≥", "<=": "≤"}.get(
        m.group(1).lower(), m.group(1))
    return f"{op} {m.group(2).strip()}"


def _covenant_category(text: str) -> str:
    return "FC" if _RATIO.search(text or "") else "NC"


def _covenant_frequency(text: str) -> str:
    t = (text or "").lower()
    return "quarterly" if "quarter" in t else ("half_yearly" if "half" in t else
                                               ("annual" if _RATIO.search(t) else "event_driven"))


def _policy_category(text: str) -> Optional[str]:
    t = (text or "").lower()
    if "committee approval" in t or t.startswith("requires "):
        return None                                   # an approval route, not a borrower condition
    if "before disbursement" in t:
        return "CP"
    if "before sanction" in t:
        return "PC"
    return "GC"


# ── the T&C agent ──────────────────────────────────────────────────────────────

def drafts(case: Optional[dict], app: dict) -> list[dict]:
    """(category, text, source, provenance, extra) drafted from the credit case and the application."""
    case = case or {}
    rea = case.get("reassessment") or {}
    out: list[tuple] = []
    for x in rea.get("recommended_mitigants") or []:
        if x.get("item"):
            out.append(("PC", x["item"], M6, "derived", {}))
    for x in rea.get("conditions_precedent") or []:
        if x.get("item"):
            out.append(("CP", x["item"], M6, "derived", {}))
    for x in rea.get("conditions_subsequent") or []:
        if x.get("item"):
            kind = "FC" if x.get("type") == "financial" else "PD"
            out.append((kind, x["item"], M6, "derived", {"stipulated_value": _stipulation(x["item"])}))
    for text in case.get("covenants_proposed") or []:
        kind = _covenant_category(text)
        out.append((kind, text, COVENANTS, "derived",
                    {"stipulated_value": _stipulation(text) if kind == "FC" else None,
                     "frequency": _covenant_frequency(text)}))
    for text in case.get("conditions") or []:
        kind = _policy_category(text)
        if kind:
            out.append((kind, text, POLICY, "derived", {}))
    for f in app.get("facilities") or []:
        if f.get("purpose"):
            label = str(f.get("facility_type") or "facility").replace("_", " ")
            out.append(("FS", f"End use of the {label} ({f['facility_id']}) restricted to: {f['purpose']}",
                        APPLICATION, "source", {"facility_id": f["facility_id"]}))
        if f.get("facility_type") in ("term_loan", "project_finance") and f.get("tenor_months"):
            out.append(("FS", f"Repayment of {f['facility_id']} within the sanctioned tenor of {f['tenor_months']} months "
                              "as per the repayment schedule (Annexure I)",
                        APPLICATION, "source", {"facility_id": f["facility_id"], "frequency": "quarterly"}))
    for kind, text in STANDARD_TERMS:
        out.append((kind, text, STANDARD, "template", {}))
    seen, unique = set(), []
    for row in out:                                   # the same condition from two sources is drafted once
        key = slug(row[1])
        if key not in seen:
            seen.add(key)
            unique.append(row)
    return unique


def resolve_terms(ctx: dict) -> list[dict]:
    """Field-store proposals, one per drafted condition (the text is the verified value)."""
    from src.los.reconcile import _p                  # the shared proposal shape
    reg, out = ctx["registry"], []
    for kind, text, source, prov, extra in drafts(ctx["case"], ctx["app"]):
        key = slug(f"{kind} {text}")
        row = blank_row(kind, None, agent_key=key, source=source, provenance=prov, origin="agent")
        row.update({k: v for k, v in extra.items() if v is not None})
        out.append(_p(f"{DOMAIN}.{key}.text", f"{CATEGORIES[kind]}: {text[:70]}", text, provenance=prov,
                      source="template" if prov == "template" else "engine", registry=reg,
                      evidence={"engine": source, "category": CATEGORIES[kind]},
                      target=["terms", "conditions", {"find": {"agent_key": key}, "new": row}, "text"],
                      run_id=ctx.get("run_id")))
    return out


# ── people's authoring ─────────────────────────────────────────────────────────

def normalise_row(raw: dict, facilities: set, current: Optional[dict] = None) -> dict:
    row = dict(current or blank_row("GC", None))
    category = str(raw.get("category") or row.get("category") or "").strip()
    if category not in CATEGORIES:
        raise InvalidRequestError(f"Category must be one of {', '.join(CATEGORIES)}")
    text = str(raw["text"]).strip() if raw.get("text") is not None else row.get("text")
    if not text:
        raise InvalidRequestError("The condition text is required")
    facility_id = raw.get("facility_id", row.get("facility_id")) or None
    if facility_id and facility_id not in facilities:
        raise InvalidRequestError(f"Unknown facility {facility_id}")
    if category == "FS" and not facility_id:
        raise InvalidRequestError("A facility-specific condition names its facility")
    frequency = str(raw.get("frequency") or row.get("frequency") or default_frequency(category)).strip()
    if frequency not in FREQUENCIES:
        raise InvalidRequestError(f"Frequency must be one of {', '.join(FREQUENCIES)}")
    stip = raw.get("stipulated_value", row.get("stipulated_value"))
    row.update(category=category, text=text, facility_id=facility_id, frequency=frequency,
               stipulated_value=(str(stip).strip() or None) if stip not in (None, "") else None,
               party=(str(raw.get("party") or row.get("party") or "").strip() or None))
    return row


def next_id(rows: list[dict]) -> str:
    n = max([int(r["term_id"].split("-")[1]) for r in rows if str(r.get("term_id") or "").startswith("TC-")] or [0])
    return f"TC-{n + 1:03d}"


def summary(terms: Optional[dict], fields: Optional[dict] = None) -> dict:
    rows = [r for r in (terms or {}).get("conditions") or [] if not r.get("removed")]
    fields = fields or {}
    pending = [r for r in rows if r.get("origin") == "agent" and
               (fields.get(f"{DOMAIN}.{r['agent_key']}.text") or {}).get("status") in ("proposed", "conflict")]
    return {"total": len(rows), "removed": sum(1 for r in (terms or {}).get("conditions") or [] if r.get("removed")),
            "by_category": {k: sum(1 for r in rows if r["category"] == k) for k in CATEGORIES},
            "from_agent": sum(1 for r in rows if r.get("origin") == "agent"),
            "added_by_people": sum(1 for r in rows if r.get("origin") == "person"),
            "awaiting_confirmation": len(pending), "status": (terms or {}).get("status", "draft")}


def submit_gate(terms: Optional[dict], fields: Optional[dict]) -> Optional[str]:
    """The AP maker submits with the T&C authored and every agent draft confirmed, edited or removed."""
    s = summary(terms, fields)
    if not s["total"]:
        return "Author the terms & conditions (Terms & conditions tab) before submitting the appraisal"
    if s["awaiting_confirmation"]:
        return (f"{s['awaiting_confirmation']} drafted term(s) & condition(s) still need your confirmation — "
                "confirm, edit or remove them in the Terms & conditions tab")
    return None


# ── sanction: the authored T&C become the post-sanction conditions tracker ─────

def to_conditions(terms: dict, due_cs: str) -> list[dict]:
    out, n = [], {k: 0 for k in CATEGORIES}
    for r in terms.get("conditions") or []:
        if r.get("removed") or not r.get("text"):
            continue
        kind = r["category"]
        n[kind] += 1
        out.append({"id": f"{kind}-{n[kind]:02d}", "type": kind, "category": CATEGORIES[kind], "text": r["text"],
                    "source": f"Authored at AP ({r.get('source') or 'added by the AP maker'})",
                    "provenance": r.get("provenance") or "person", "term_id": r.get("term_id"),
                    "existing": False, "facility_id": r.get("facility_id"), "party": r.get("party"),
                    "stipulated_value": r.get("stipulated_value"), "frequency": r.get("frequency") or default_frequency(kind),
                    "status": "open", "due": due_cs if kind in ("PD", "CS", "FC", "NC") else None,
                    "note": None, "evidence": None, "approval": None, "updated_by": None, "updated_at": None,
                    "history": []})
    return out
