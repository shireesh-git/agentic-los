"""Security master and lifecycle (Client One GAP-P1-03).

Persistent securities per application: category, type/subtype, multi-facility
association, description, proposed and apportioned values, valuation date and
basis, charge type and priority, creation and perfection status/dates, LOS
Security ID, CERSAI/ROC status and CBS Security Number, with evidence and a
change history visible at appraisal, post-sanction and disbursement.

A security change re-evaluates cover and flags the approval for revalidation
(GAP-P2-02). Valuation haircut, coverage formulas and lien search remain
confirmation-required (spec §23/P1-03) — cover here is the simple
forced-sale-value ÷ proposed-amount ratio the application already uses.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from src.application.errors import InvalidRequestError

CATEGORIES = ("primary", "collateral")
TYPES = ("land_building", "plant_machinery", "stock", "book_debtors", "deposit", "guarantee",
         "hypo_mortgage", "charge_on_investments", "other")
CHARGE_TYPES = ("first_charge", "pari_passu", "second_charge", "statutory", "none")
CREATION = ("created", "pending")
PERFECTION = ("perfected", "in_progress", "pending")
REG = ("filed", "pending", "na")


def blank_security(index: int) -> dict:
    return {"security_id": f"SEC-{index:03d}", "category": "primary", "type": None, "subtype": None,
            "facility_ids": [], "description": None, "proposed_value_cr": None, "apportioned_value_cr": None,
            "valuation_date": None, "valuation_basis": None, "charge_type": None, "charge_priority": None,
            "creation_status": "pending", "creation_date": None, "perfection_status": "pending",
            "perfection_eta": None, "los_security_id": None, "cersai": "pending", "roc": "pending",
            "cbs_security_no": None, "evidence": [], "history": []}


def _d(value, name: str) -> Optional[str]:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip()).isoformat()
    except ValueError:
        raise InvalidRequestError(f"{name} must be YYYY-MM-DD")


def _n(value, name: str):
    if value in (None, ""):
        return None
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        raise InvalidRequestError(f"{name} must be a number")


def normalise_security(raw: dict, index: int, known_facility_ids: set, existing: Optional[dict] = None) -> dict:
    rec = {**(existing or {})}
    rec.update({k: v for k, v in dict(raw or {}).items() if v not in (None, "")})
    if str(rec.get("category") or "") not in CATEGORIES:
        raise InvalidRequestError(f"Security {index}: category must be primary or collateral")
    if rec.get("type") and str(rec["type"]) not in TYPES:
        raise InvalidRequestError(f"Security {index}: type must be one of {', '.join(TYPES)}")
    if rec.get("charge_type") and str(rec["charge_type"]) not in CHARGE_TYPES:
        raise InvalidRequestError(f"Security {index}: charge type must be one of {', '.join(CHARGE_TYPES)}")
    for field, allowed in (("creation_status", CREATION), ("perfection_status", PERFECTION),
                           ("cersai", REG), ("roc", REG)):
        if rec.get(field) and str(rec[field]) not in allowed:
            raise InvalidRequestError(f"Security {index}: {field} must be one of {', '.join(allowed)}")
    facility_ids = [str(f).strip() for f in rec.get("facility_ids") or [] if str(f).strip()]
    unknown = [f for f in facility_ids if f not in known_facility_ids]
    if unknown:
        raise InvalidRequestError(f"Security {index}: unknown facility linkage(s) {', '.join(unknown)}")
    rec["facility_ids"] = facility_ids
    for field in ("proposed_value_cr", "apportioned_value_cr"):
        rec[field] = _n(rec.get(field), f"security {index} {field}")
    for field in ("valuation_date", "creation_date", "perfection_eta"):
        rec[field] = _d(rec.get(field), f"security {index} {field}")
    rec.setdefault("history", [])
    return rec


def cover_ratio(securities: list[dict], amount_cr: Optional[float]) -> Optional[float]:
    """Forced-sale (apportioned, else proposed) cover on the proposed amount — the demo cover rule."""
    if not amount_cr:
        return None
    value = sum((s.get("apportioned_value_cr") or s.get("proposed_value_cr") or 0) for s in securities)
    return round(value / amount_cr, 2)


def link_conditions(securities: list[dict], conditions: list[dict]) -> None:
    """Security-perfection conditions are facility-specific: link their IDs (GAP-P0-14)."""
    for s in securities:
        for c in conditions:
            if "security" in (c.get("text") or "").lower() and c["type"] in ("CP", "CPS"):
                c["facility_id"] = c.get("facility_id") or (s["facility_ids"][0] if s["facility_ids"] else None)
                if c["id"] not in s.get("linked_condition_ids", []):
                    s.setdefault("linked_condition_ids", []).append(c["id"])
