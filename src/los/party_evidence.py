"""
Party-level evidence (Client One UAT-P0-3).

Each related party is linked, separately from the application-level checks, to:

  * KYC (identity & address evidence references),
  * bureau checks (CIBIL / CRIF party results),
  * name screening (PEP / sanctions, per individual),
  * ratings (a reference to the party's rating record),
  * financial records (a reference to the CMA subject),
  * documents (references to registry entries), and
  * exceptions (a Compliance VP release, which lapses on re-record — same
    governance as the application-level checks).

Everything is stored with the party record in the application payload, is
attributed (who, when) and validated: a non-clear result needs a remark, and
only the Compliance VP can record an exception. Re-recording a section
invalidates a previously approved exception (it covered the previous result
only). Demo data is explicitly labelled.
"""

from __future__ import annotations

from typing import Optional

STATUSES = ("pending", "clear", "matched", "failed", "unavailable")
_LINK_SECTIONS = ("kyc", "cibil", "crif", "name_screening")


def initial_verification() -> dict:
    return {
        "kyc": {"status": "pending", "evidence": [], "remarks": None, "by_name": None, "at": None},
        "bureau": {
            "cibil": {"status": "pending", "remarks": None, "by_name": None, "at": None},
            "crif": {"status": "pending", "remarks": None, "by_name": None, "at": None},
        },
        "name_screening": {"status": "pending", "hits": None, "remarks": None, "by_name": None, "at": None},
        "rating_ref": None,          # a party rating record (subject/party_name) in the ratings workspace
        "financial_ref": None,       # a CMA subject
        "document_ids": [],          # document-registry names / references
        "exception": None,
    }


def _stamp(status: str, remarks: Optional[str], by_name: str, at: str, extra: Optional[dict] = None) -> dict:
    rec = {"status": status, "remarks": remarks, "by_name": by_name, "at": at}
    if extra:
        rec.update(extra)
    return rec


def apply_update(party: dict, payload: dict, by_name: str, at: str, *, vp: bool) -> list[str]:
    """Apply a governed update to one party's evidence. Returns the sections changed.
    Raises ValueError with a client message for invalid input."""
    v = party.setdefault("verification", initial_verification())
    changed = []

    # KYC
    if "kyc_status" in payload:
        status = str(payload["kyc_status"] or "").strip()
        if status not in STATUSES:
            raise ValueError(f"KYC status must be one of {', '.join(STATUSES)}")
        remarks = (payload.get("kyc_remarks") or "").strip() or None
        if status in ("matched", "failed") and not remarks:
            raise ValueError("A remark (reason) is required for a matched or failed KYC result")
        if v.get("exception") and "kyc_status" in payload and status != (v["kyc"].get("status")):
            v["exception_history"] = v.get("exception_history", [])
            v["exception_history"].append({**v["exception"], "invalidated_at": at,
                                           "reason": "KYC re-recorded — the approved exception covered the previous result only"})
            v["exception"] = None
        evidence = payload.get("kyc_evidence")
        if evidence is not None:
            refs = [str(x).strip() for x in evidence if str(x).strip()]
            if len(refs) > 20:
                raise ValueError("At most 20 evidence references per party KYC record")
        else:
            refs = v["kyc"].get("evidence", [])
        v["kyc"] = _stamp(status, remarks, by_name, at, {"evidence": refs})
        changed.append("kyc")

    # Bureau: CIBIL / CRIF
    for key, field in (("cibil", "cibil_status"), ("crif", "crif_status")):
        if field in payload:
            status = str(payload[field] or "").strip()
            if status not in STATUSES:
                raise ValueError(f"{key.upper()} status must be one of {', '.join(STATUSES)}")
            remarks = (payload.get(field.replace("_status", "_remarks")) or "").strip() or None
            if status in ("matched", "failed") and not remarks:
                raise ValueError(f"A remark (reason) is required for a matched or failed {key.upper()} result")
            v.setdefault("bureau", {})[key] = _stamp(status, remarks, by_name, at)
            changed.append(key)

    # Name screening
    if "screening_status" in payload:
        status = str(payload["screening_status"] or "").strip()
        if status not in STATUSES:
            raise ValueError(f"Name-screening status must be one of {', '.join(STATUSES)}")
        remarks = (payload.get("screening_remarks") or "").strip() or None
        if status in ("matched", "failed") and not remarks:
            raise ValueError("A remark (reason) is required for a matched or failed name-screening result")
        hits = payload.get("screening_hits")
        hits = int(hits) if hits not in (None, "") else None
        if hits is not None and hits < 0:
            raise ValueError("Name-screening hits cannot be negative")
        v["name_screening"] = _stamp(status, remarks, by_name, at, {"hits": hits})
        changed.append("name_screening")

    # References
    if "rating_ref" in payload:
        v["rating_ref"] = (str(payload["rating_ref"]).strip() or None)
        changed.append("rating_ref")
    if "financial_ref" in payload:
        v["financial_ref"] = (str(payload["financial_ref"]).strip() or None)
        changed.append("financial_ref")
    if "document_ids" in payload:
        refs = [str(x).strip() for x in (payload["document_ids"] or []) if str(x).strip()]
        if len(refs) > 25:
            raise ValueError("At most 25 document references per party")
        v["document_ids"] = refs
        changed.append("document_ids")

    # Exception (Compliance VP only)
    if payload.get("exception_reason") not in (None, ""):
        if not vp:
            raise ValueError("Only the Compliance VP can record a party-level exception")
        if not any(s["status"] in ("matched", "failed", "unavailable") for s in (
                v["kyc"], v.get("bureau", {}).get("cibil", {}), v.get("bureau", {}).get("crif", {}),
                v["name_screening"])):
            raise ValueError("A party-level exception applies to a matched, failed or unavailable party result")
        v["exception"] = {"by_name": by_name, "at": at, "reason": str(payload["exception_reason"]).strip()}
        changed.append("exception")

    return changed


def coverage(party: dict) -> dict:
    """Per-party evidence coverage: which of the required links are in place."""
    v = party.get("verification") or {}
    bureau = v.get("bureau") or {}
    done = {
        "kyc": (v.get("kyc") or {}).get("status") in ("clear",),
        "bureau": all((bureau.get(k) or {}).get("status") in ("clear", "unavailable") for k in ("cibil", "crif"))
                  and any((bureau.get(k) or {}).get("status") not in ("pending",) for k in ("cibil", "crif")),
        "name_screening": (v.get("name_screening") or {}).get("status") in ("clear",),
        "rating": bool(v.get("rating_ref")),
        "financials": bool(v.get("financial_ref")),
        "documents": bool(v.get("document_ids")),
    }
    open_items = [k for k, ok in done.items() if not ok]
    return {"complete": not open_items, "open": open_items, "exception": bool(v.get("exception"))}
