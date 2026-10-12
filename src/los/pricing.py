"""Pricing, fees and repayment governance (Client One GAP-P1-04).

Per-facility governed pricing: recommended vs proposed benchmark rate, spread
and interest rate, borrower risk rating, comparison with other banks and
justification, the mandatory benchmark-type/spread rule (GAP-P2-01), a pricing
change alert that forces RAROC review/recalculation, previously-approved fee
records with milestones, and the *tentative* term-loan schedule — kept
explicitly separate from the final disbursement terms recorded at
disbursement (GAP-P0-15).

The demo MCLR/spread grid/cost-of-funds/hurdle must not become production
defaults (spec §23/P1-04) — the recommended values here are entered and
attributed, not copied from a demo grid.
"""

from __future__ import annotations

from typing import Optional

from src.application.errors import InvalidRequestError


def initial_pricing(app: dict = None) -> dict:
    return {"facilities": {}, "fees": [], "other_banks_comparison": None, "justification": None,
            "tentative_schedules": [], "change_alert": None}


def normalise_pricing_entry(raw: dict, facility: dict) -> dict:
    entry = {}
    for key in ("recommended_benchmark", "proposed_benchmark", "recommended_rate", "proposed_rate",
                "recommended_spread_bps", "proposed_spread_bps", "borrower_risk_rating", "comparison"):
        v = raw.get(key)
        if key.endswith(("_rate", "_spread_bps", "_benchmark")) and not key.endswith("mark") and "benchmark" not in key:
            entry[key] = _n(v, f"{facility['facility_id']} {key}")
        elif "benchmark" in key:
            entry[key] = (str(v).strip() or None) if v else None
        else:
            entry[key] = (str(v).strip() or None) if v else None
    return entry


def pricing_gate(pricing: dict, facilities: list[dict]) -> Optional[str]:
    """GAP-P2-01: the benchmark type and proposed spread are mandatory for applicable facilities."""
    missing = []
    for f in facilities:
        if f.get("facility_nature") != "fund_based":
            continue
        entry = pricing.get("facilities", {}).get(f["facility_id"]) or {}
        fp = f.get("pricing") or {}
        if not (fp.get("benchmark") or entry.get("proposed_benchmark")):
            missing.append(f"{f['facility_id']}: benchmark type")
        if fp.get("spread") is None and entry.get("proposed_spread_bps") is None:
            missing.append(f"{f['facility_id']}: proposed spread")
    return ("Pricing is incomplete — set: " + "; ".join(missing)) if missing else None


def pricing_change_alert(app: dict, pricing: dict) -> Optional[str]:
    """A pricing change after the approval snapshot flags RAROC for review (GAP-P0-08/P2-02)."""
    snaps = [s for s in (app.get("snapshots") or []) if s.get("ref") == "sanction"]
    if not snaps:
        return None
    snap = max(snaps, key=lambda s: s.get("seq", 0))
    changed = []
    for f in app.get("facilities", []):
        old = (snap.get("packages", {}).get("facilities") or {}).get(f["facility_id"], {}).get("pricing") or {}
        new = f.get("pricing") or {}
        if old and new and old != new:
            changed.append(f["facility_id"])
    if changed:
        return ("Pricing changed after sanction for " + ", ".join(changed) +
                " — review and recompute RAROC before proceeding")
    return None


def normalise_fee(raw: dict, index: int) -> dict:
    nature = str(raw.get("nature") or "").strip()
    if not nature:
        raise InvalidRequestError(f"Fee {index}: the fee nature is required")
    scope = str(raw.get("scope") or "facility").strip()
    amount = _n(raw.get("amount_cr"), f"fee {index} amount")
    pct = _n(raw.get("pct"), f"fee {index} percentage")
    total = _n(raw.get("total_cr"), f"fee {index} total")
    if amount is None and pct is None and total is None:
        raise InvalidRequestError(f"Fee {index}: an amount, a percentage or a calculated total is required")
    return {"fee_id": f"APF-{index:02d}", "facility_id": raw.get("facility_id") if scope == "facility" else None,
            "previously_approved": bool(raw.get("previously_approved")),
            "nature": nature, "type": (str(raw.get("type") or "").strip() or None), "scope": scope,
            "amount_cr": amount, "pct": pct,
            "milestone": (str(raw.get("milestone") or "").strip() or None),
            "comments": (str(raw.get("comments") or "").strip() or None), "total_cr": total}


def normalise_tentative_schedule(raw: dict, index: int, known_facilities: set) -> list[dict]:
    """The tentative appraisal schedule — clearly *not* the final disbursement terms."""
    facility_ids = [str(x).strip() for x in raw.get("facility_ids") or [] if str(x).strip()]
    unknown = [x for x in facility_ids if x not in known_facilities]
    if unknown:
        raise InvalidRequestError(f"Tentative schedule {index}: unknown facility reference(s) {', '.join(unknown)}")
    return [{"schedule_id": f"TNS-{index:02d}", "facility_ids": facility_ids,
             "amount_cr": _n(raw.get("amount_cr"), f"tentative schedule {index} amount"),
             "tenor_months": _i(raw.get("tenor_months"), f"tentative schedule {index} tenor"),
             "pricing": (str(raw.get("pricing") or "").strip() or None),
             "repayment_type": (str(raw.get("repayment_type") or "").strip() or None),
             "repayment_frequency": (str(raw.get("repayment_frequency") or "").strip() or None),
             "moratorium_months": _i(raw.get("moratorium_months"), f"tentative schedule {index} moratorium"),
             "repayment_period": (str(raw.get("repayment_period") or "").strip() or None),
             "acceptability_comments": (str(raw.get("acceptability_comments") or "").strip() or None),
             "note": "Tentative appraisal schedule — the final terms are recorded at disbursement"}]


def _n(value, name: str):
    if value in (None, ""):
        return None
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        raise InvalidRequestError(f"{name} must be a number")


def _i(value, name: str):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise InvalidRequestError(f"{name} must be a whole number")
