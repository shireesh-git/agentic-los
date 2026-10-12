"""External Work-Party management (Client One GAP-P1-05).

The documented EWP roles — LIA, LIE, Security Trustee, ESDD provider, Legal
Loan Counsel — as persistent, linked records: name, contact, email, phase,
request ID, linkage to application / project / facility / security, the
related report/document and a status. Appointment/validity/review semantics
and the source-specific meanings of LIA/LIE are confirmation-required, so they
are captured as fields with the label, never as invented rules.
"""

from __future__ import annotations

from typing import Optional

from src.application.errors import InvalidRequestError

EWP_ROLES = ("LIA", "LIE", "Security Trustee", "ESDD Provider", "Legal Loan Counsel")
EWP_STATUSES = ("requested", "appointed", "engaged", "report_submitted", "completed", "on_hold")


def blank_ewp(index: int) -> dict:
    return {"ewp_id": f"EWP-{index:03d}", "role": None, "name": None, "contact_number": None,
            "email": None, "phase": None, "request_id": None,
            "application_id": None, "project_ids": [], "facility_ids": [], "security_ids": [],
            "report_document": None, "status": "requested", "appointment_note": None,
            "validity": None, "review": None, "remarks": None}


def normalise_ewp(raw: dict, index: int, known: dict, existing: Optional[dict] = None) -> dict:
    rec = {**(existing or {})}
    rec.update({k: v for k, v in dict(raw or {}).items() if v not in (None, "")})
    if str(rec.get("role") or "") not in EWP_ROLES:
        raise InvalidRequestError(f"EWP {index}: role must be one of {', '.join(EWP_ROLES)}")
    if not str(rec.get("name") or "").strip():
        raise InvalidRequestError(f"EWP {index}: the party name is required")
    if rec.get("email"):
        email = str(rec["email"]).strip()
        if "@" not in email or "." not in email.split("@")[-1]:
            raise InvalidRequestError(f"EWP {index}: the email {email} is not valid")
    for key, pool in (("project_ids", known.get("projects", set())),
                      ("facility_ids", known.get("facilities", set())),
                      ("security_ids", known.get("securities", set()))):
        ids = [str(x).strip() for x in rec.get(key) or [] if str(x).strip()]
        unknown = [x for x in ids if x not in pool]
        if unknown:
            raise InvalidRequestError(f"EWP {index}: unknown {key.replace('_ids', '')} reference(s) {', '.join(unknown)}")
        rec[key] = ids
    if rec.get("status") and str(rec["status"]) not in EWP_STATUSES:
        raise InvalidRequestError(f"EWP {index}: status must be one of {', '.join(EWP_STATUSES)}")
    return rec
