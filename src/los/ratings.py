"""Production rating, group rating and RAROC controls (Client One GAP-P0-08).

Governed records rather than CAM-only text:

* external ratings per party (borrower, sponsor, promoter): agency, rating type,
  short/long-term class, grade, date, instrument and rationale, with the
  prior-year ("Save Risk") retrieval as a labelled demo fetch;
* internal rating per borrower/promoter/sponsor/SPV: current grade, score, date;
* group rating: a deterministic aggregation over the rated group entities,
  labelled demo — the bank-approved group methodology is confirmation-required;
* adverse-event review: date, downgrade notches, revised rating, comments;
* facility-wise RAROC with its *inputs* recorded, so a change of amount, tenor,
  rating or pricing marks it stale and forces recomputation (the one dependency
  Client One details); RAROC is not mandatory at IP sanction;
* CRP uploads: LPF Note, Rating Report, CRP Note, risk observations, with
  maker upload / checker review.

No PD/LGD/capital/cost-of-funds/RAROC formula is copied from the demo mapping
into "production" — the calculation shown is explicitly a labelled demo model
awaiting the bank-approved models (spec §22/P0-08, §28).
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Optional

from src.application.errors import InvalidRequestError

PARTY_SUBJECTS = ("borrower", "promoter", "sponsor", "spv")
RATING_CLASSES = ("long_term", "short_term", "not_applicable")
REVIEW_STATUSES = ("uploaded", "reviewed", "returned")

_GRADE_SCALE = ("AAA", "AA", "A", "BBB", "BB", "B", "C")


def _grade_index(grade: str) -> int:
    g = str(grade or "").strip().upper()
    for i, known in enumerate(_GRADE_SCALE):
        if g.startswith(known):
            return i
    return len(_GRADE_SCALE) - 1


def initial_ratings(app: dict, companies: dict) -> dict:
    """Seed the governed records: the borrower's external rating from the (demo)
    reference data; internal ratings pending; group rating computed from rated
    group entities."""
    company = companies.get(app.get("entity_id")) or {}
    borrower = company.get("borrower") or {}
    ext = None
    rating = getattr(borrower, "credit_rating", None)
    if rating:
        ext = {"agency": getattr(borrower, "rating_agency", None) or "CRISIL (demo reference)",
               "rating": str(rating), "rating_type": "issuer", "term_class": "long_term",
               "grade": str(rating).split("/")[0].strip(), "date": date.today().isoformat(),
               "instrument": None, "rationale": "Fetched from the in-app reference data (demo — Save Risk not connected)",
               "prior_year": {"agency": getattr(borrower, "rating_agency", None) or "CRISIL (demo reference)",
                              "rating": str(rating), "date": "prior year (demo fetch)",
                              "note": "Save Risk retrieval — demo data; the production source is not connected"}}
    entry = {"subject": "borrower", "party_name": app.get("borrower_name")}
    if ext:
        entry.update(ext)
    else:
        entry.update({"agency": None, "rating": None, "rating_type": None, "term_class": "long_term",
                      "grade": None, "date": None, "instrument": None,
                      "rationale": None, "prior_year": None})
    rec = {"external_ratings": [entry],
           "internal_ratings": [{"subject": "borrower", "party_name": app.get("borrower_name"),
                                 "grade": None, "score": None, "date": None, "note": None}],
           "group_rating": None, "adverse_events": [], "raroc": {}, "crp_notes": []}
    group = company.get("group")
    if group:
        rated = []
        for eid in getattr(group, "entities", None) or []:
            b = (companies.get(eid) or {}).get("borrower") or {}
            r = getattr(b, "credit_rating", None)
            if r:
                rated.append((eid, str(r)))
        if rated:
            worst = max(rated, key=lambda t: _grade_index(t[1]))
            rec["group_rating"] = {"group_name": getattr(group, "group_name", None),
                                   "basis": "Worst rated entity in the group (demo aggregation rule — the "
                                            "bank-approved group methodology is confirmation-required)",
                                   "grade": worst[1].split("/")[0].strip(), "rated_entities": list(rated),
                                   "calculated_at": date.today().isoformat()}
    return rec


def external_rating_entry(raw: dict, parties: list[dict]) -> dict:
    subject = str(raw.get("subject") or "").strip()
    if subject not in PARTY_SUBJECTS:
        raise InvalidRequestError(f"Rating subject must be one of {', '.join(PARTY_SUBJECTS)}")
    agency = str(raw.get("agency") or "").strip()
    rating = str(raw.get("rating") or "").strip()
    if not agency or not rating:
        raise InvalidRequestError("The rating agency and the rating are required")
    term = str(raw.get("term_class") or "long_term").strip()
    if term not in RATING_CLASSES:
        raise InvalidRequestError(f"Term class must be one of {', '.join(RATING_CLASSES)}")
    party_name = str(raw.get("party_name") or "").strip()
    if subject != "borrower" and not party_name:
        raise InvalidRequestError(f"The {subject} party name is required")
    return {"subject": subject, "party_name": party_name or None, "agency": agency, "rating": rating,
            "rating_type": (str(raw.get("rating_type") or "issuer").strip() or "issuer"),
            "term_class": term, "grade": (str(raw.get("grade") or rating.split("/")[0]).strip() or None),
            "date": str(raw.get("date") or date.today().isoformat()),
            "instrument": (str(raw.get("instrument") or "").strip() or None),
            "rationale": (str(raw.get("rationale") or "").strip() or None),
            # POS manual: key credit weaknesses / observations from the rating rationale (F-10)
            "credit_weaknesses": (str(raw.get("credit_weaknesses") or "").strip() or None),
            "outlook": (str(raw.get("outlook") or "").strip() or None)}


def internal_rating_entry(raw: dict) -> dict:
    subject = str(raw.get("subject") or "").strip()
    if subject not in PARTY_SUBJECTS:
        raise InvalidRequestError(f"Rating subject must be one of {', '.join(PARTY_SUBJECTS)}")
    grade = str(raw.get("grade") or "").strip()
    score = raw.get("score")
    if not grade and score in (None, ""):
        raise InvalidRequestError("The internal grade or score is required")
    if score not in (None, ""):
        try:
            score = round(float(score), 2)
        except (TypeError, ValueError):
            raise InvalidRequestError("The internal score must be a number")
    return {"subject": subject, "party_name": (str(raw.get("party_name") or "").strip() or None),
            "grade": grade or None, "score": score, "date": str(raw.get("date") or date.today().isoformat()),
            "note": (str(raw.get("note") or "").strip() or None)}


def adverse_event_entry(raw: dict) -> dict:
    trigger = str(raw.get("trigger") or "").strip()
    if not trigger:
        raise InvalidRequestError("The adverse-event trigger is required")
    notches = raw.get("downgrade_notches")
    if notches not in (None, ""):
        try:
            notches = int(notches)
        except (TypeError, ValueError):
            raise InvalidRequestError("Downgrade notches must be a whole number")
    return {"trigger": trigger, "review_date": str(raw.get("review_date") or date.today().isoformat()),
            "downgrade_notches": notches, "revised_rating": (str(raw.get("revised_rating") or "").strip() or None),
            "comments": (str(raw.get("comments") or "").strip() or None)}


def _facility(app: dict, facility_id: str) -> dict:
    f = next((x for x in app.get("facilities", []) if x["facility_id"] == facility_id), None)
    if not f:
        raise InvalidRequestError(f"Unknown facility: {facility_id}")
    return f


def raroc_input_hash(facility: dict, internal: Optional[dict]) -> str:
    blob = json.dumps({"amount": facility.get("proposed_cr"), "tenor": facility.get("tenor_months"),
                       "pricing": facility.get("pricing"), "repayment": facility.get("repayment"),
                       "rating": (internal or {}).get("grade")}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def compute_raroc(app: dict, facility_id: str, case: Optional[dict], at: str, by_name: str) -> dict:
    """Facility-wise RAROC from its recorded inputs (amount, tenor, pricing, internal
    rating and the assessment's PD/LGD). Labelled demo model — the bank-approved
    formulas are confirmation-required, so this is governance scaffolding, not a
    production model."""
    f = _facility(app, facility_id)
    pricing = f.get("pricing") or {}
    rea = (case or {}).get("reassessment") or {}
    risk = (case or {}).get("risk") or {}
    pd = risk.get("pd") or rea.get("pd")
    lgd = risk.get("lgd") or rea.get("lgd")
    amount = f.get("proposed_cr") or 0
    rate = pricing.get("interest_rate") or 0
    spread = pricing.get("spread") or 0
    tenor = max(f.get("tenor_months") or 0, 1) / 12
    internal = next((r for r in ((app.get("ratings") or {}).get("internal_ratings") or []) if r["subject"] == "borrower"), None)
    pd_v, lgd_v = (float(pd) if pd not in (None, "") else 0.05), (float(lgd) if lgd not in (None, "") else 0.45)
    el = pd_v * lgd_v * amount
    revenue = rate / 100 * amount * min(tenor, 1.0)
    capital = max(amount * 0.10, 0.001)
    cost_of_funds = 0.06 * amount * min(tenor, 1.0)
    target = 0.14 * capital
    raroc = round((revenue - cost_of_funds - el - target) / capital * 100, 2) if capital else 0.0
    entry = {"facility_id": facility_id, "title": f.get("facility_type"), "amount_cr": amount,
             "tenor_months": f.get("tenor_months"), "payment_frequency": (f.get("repayment") or {}).get("repayment_frequency"),
             "inputs": {"rate_pct": rate, "spread": spread, "pd": pd_v, "lgd": lgd_v,
                        "internal_grade": (internal or {}).get("grade"),
                        "expected_loss_cr": round(el, 3), "revenue_cr": round(revenue, 3),
                        "cost_of_funds_cr": round(cost_of_funds, 3), "capital_cr": round(capital, 3)},
             "raroc_pct": raroc + 0.0, "meets_hurdle": raroc >= 14.0,
             "input_hash": raroc_input_hash(f, internal), "model": "LOS demo RAROC model — bank-approved "
             "formulas require confirmation (spec §22/P0-08)",
             "computed_at": at, "computed_by": by_name}
    return entry


def stale_raroc(app: dict) -> list[str]:
    """GAP-P2-01/P2-02: the RAROC result is stale when its recorded inputs changed."""
    rec = (app.get("ratings") or {}).get("raroc") or {}
    internal = next((r for r in (app.get("ratings") or {}).get("internal_ratings") or []
                     if r["subject"] == "borrower"), None)
    stale = []
    for fid, entry in rec.items():
        f = next((x for x in app.get("facilities", []) if x["facility_id"] == fid), None)
        if f and entry.get("input_hash") and entry["input_hash"] != raroc_input_hash(f, internal):
            stale.append(fid)
    return stale


def crp_note_entry(raw: dict) -> dict:
    kind = str(raw.get("kind") or "").strip()
    if kind not in ("lpf_note", "rating_report", "crp_note", "risk_observations", "supporting_file"):
        raise InvalidRequestError(f"CRP note kind must be one of lpf_note, rating_report, crp_note, risk_observations, supporting_file")
    title = str(raw.get("title") or "").strip()
    file_name = str(raw.get("file_name") or "").strip()
    if not title and not file_name:
        raise InvalidRequestError("A title or an uploaded file name is required")
    return {"kind": kind, "title": title or None, "file_name": file_name or None, "status": "uploaded",
            "uploaded_by": None, "uploaded_at": None, "reviewed_by": None, "reviewed_at": None,
            "remarks": (str(raw.get("remarks") or "").strip() or None)}
