"""Multi-facility product, exposure and sanction model (Client One GAP-P0-04).

Each facility is a persistent application object with a distinct amount
lifecycle — proposed, sanctioned, committed, executed, disbursed, outstanding
and balance are *separate values*, never one number re-labelled:

    proposed   what the RM requested (creation/prefill);
    sanctioned what the committee sanctioned (facility-wise allocation);
    committed  the amount the customer may draw (equals sanctioned unless a
               partial-execution balance applies — P2-01 rule);
    executed   the facility-agreement execution (per-facility consent status);
    disbursed  tranches approved for release against this facility;
    outstanding funded amount still outstanding (disbursed in the demo, where
               there is no repayment feed);
    balance    committed - disbursed (the remaining sanctioned commitment).

Facilities also carry product attributes, pricing, repayment, operational IDs
and a change history so every change is attributable.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Optional

from src.application.errors import InvalidRequestError

FACILITY_NATURES = ("fund_based", "non_fund_based")
FACILITY_TYPES = ("working_capital", "cash_credit", "overdraft", "wcdl", "term_loan", "project_finance",
                  "letter_of_credit", "bank_guarantee", "loan_against_securities", "composite")
PROPOSAL_TYPES = ("Fresh", "Enhancement", "Renewal", "Restructure", "Review")
REPAYMENT_TYPES = ("annuity", "bullet", "quarterly_quarters", "half_yearly", "interest_only")
REPAYMENT_FREQUENCIES = ("monthly", "quarterly", "half_yearly", "annual")
BENCHMARKS = ("MCLR", "external_benchmark", "fixed", "nil")

PRICING_FIELDS = ("benchmark", "benchmark_rate", "spread", "interest_rate", "reset_frequency", "reset_date",
                  "penal_rate", "effective_rate")
REPAYMENT_FIELDS = ("repayment_type", "repayment_frequency", "moratorium_months")
OPS_FIELDS = ("total_limit_id", "fund_limit_id", "non_fund_limit_id", "limit_suffix", "loan_account",
              "next_review_date")


def blank_facility(index: int) -> dict:
    return {
        "facility_id": f"FAC-{index:03d}",
        "proposal_type": "Fresh", "facility_nature": "fund_based", "facility_type": "working_capital",
        "product_subtype": None, "amount_cr": None, "tenor_months": None, "purpose": None, "ad_hoc": False,
        # distinct amount lifecycle (GAP-P0-04)
        "proposed_cr": None, "sanctioned_cr": None, "committed_cr": None, "executed_cr": None,
        "disbursed_cr": 0.0, "outstanding_cr": 0.0, "balance_cr": None, "execution_status": None,
        # pricing / repayment per facility
        "pricing": {k: None for k in PRICING_FIELDS},
        "repayment": {k: None for k in REPAYMENT_FIELDS},
        # operational references
        "total_limit_id": None, "fund_limit_id": None, "non_fund_limit_id": None, "limit_suffix": None,
        "loan_account": None, "next_review_date": None,
        "linked_project_ids": [], "linked_security_ids": [], "linked_condition_ids": [],
        # the bank's IP facility fields (F-6); "secured" is derived from the securities record
        "parent_facility": None, "first_disbursement_date": None, "takeover": None,
        "change_history": [],
    }


def _num(value, name: str, index: int, required: bool = False):
    if value in (None, ""):
        if required:
            raise InvalidRequestError(f"Facility {index}: {name} is required")
        return None
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        raise InvalidRequestError(f"Facility {index}: {name} must be a number")


def _date(value, name: str, index: int):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip()).isoformat()
    except ValueError:
        raise InvalidRequestError(f"Facility {index}: {name} must be YYYY-MM-DD")


def normalise_facility(raw: dict, index: int, defaults: Optional[dict] = None) -> dict:
    """Validate one proposed facility (creation or edit) and return the canonical record."""
    merged = {**(defaults or {}), **{k: v for k, v in dict(raw or {}).items() if v not in (None, "")}}
    facility_type = str(merged.get("facility_type") or "").strip().lower()
    if facility_type not in FACILITY_TYPES:
        raise InvalidRequestError(f"Facility {index}: facility type must be one of {', '.join(FACILITY_TYPES)}")
    nature = str(merged.get("facility_nature") or "fund_based").strip().lower()
    if nature not in FACILITY_NATURES:
        raise InvalidRequestError(f"Facility {index}: facility nature must be fund_based or non_fund_based")
    proposal_type = str(merged.get("proposal_type") or "Fresh").strip()
    if proposal_type not in PROPOSAL_TYPES:
        raise InvalidRequestError(f"Facility {index}: proposal type must be one of {', '.join(PROPOSAL_TYPES)}")
    amount = _num(merged.get("amount_cr"), "proposed amount", index, required=True)
    if amount <= 0:
        raise InvalidRequestError(f"Facility {index}: proposed amount must be greater than zero")
    tenor = merged.get("tenor_months")
    if tenor not in (None, ""):
        try:
            tenor = int(tenor)
        except (TypeError, ValueError):
            raise InvalidRequestError(f"Facility {index}: tenor must be whole months")
        if tenor < 0:
            raise InvalidRequestError(f"Facility {index}: tenor must be at least 0")

    pricing = {}
    for key in PRICING_FIELDS:
        v = merged.get(key)
        if key in ("benchmark", "reset_frequency"):
            pricing[key] = str(v).strip() if v else None
        else:
            pricing[key] = _num(v, key, index)
    if pricing.get("benchmark") and pricing["benchmark"] not in BENCHMARKS:
        raise InvalidRequestError(f"Facility {index}: benchmark must be one of {', '.join(BENCHMARKS)}")
    if pricing.get("interest_rate") is not None and not (0 <= pricing["interest_rate"] <= 50):
        raise InvalidRequestError(f"Facility {index}: interest rate must be between 0 and 50")
    if pricing.get("spread") is not None and not (-10 <= pricing["spread"] <= 50):
        raise InvalidRequestError(f"Facility {index}: spread must be between -10 and 50")

    repayment = {}
    for key in REPAYMENT_FIELDS:
        v = merged.get(key)
        if key in ("repayment_type", "repayment_frequency"):
            repayment[key] = str(v).strip() if v else None
        else:
            repayment[key] = _num(v, key, index)
    if repayment.get("repayment_type") and repayment["repayment_type"] not in REPAYMENT_TYPES:
        raise InvalidRequestError(f"Facility {index}: repayment type must be one of {', '.join(REPAYMENT_TYPES)}")
    if repayment.get("repayment_frequency") and repayment["repayment_frequency"] not in REPAYMENT_FREQUENCIES:
        raise InvalidRequestError(f"Facility {index}: repayment frequency must be one of {', '.join(REPAYMENT_FREQUENCIES)}")

    rec = blank_facility(index)
    rec.update({
        "facility_id": str(merged.get("facility_id") or f"FAC-{index:03d}"),
        "proposal_type": proposal_type, "facility_nature": nature, "facility_type": facility_type,
        "product_subtype": (str(merged.get("product_subtype")).strip() or None) if merged.get("product_subtype") else None,
        "amount_cr": amount, "tenor_months": tenor,
        "purpose": (str(merged.get("purpose")).strip() or None) if merged.get("purpose") else None,
        "ad_hoc": bool(merged.get("ad_hoc", False)),
        "proposed_cr": amount,
        "pricing": pricing, "repayment": repayment,
        "total_limit_id": merged.get("total_limit_id") or None, "fund_limit_id": merged.get("fund_limit_id") or None,
        "non_fund_limit_id": merged.get("non_fund_limit_id") or None, "limit_suffix": merged.get("limit_suffix") or None,
        "loan_account": merged.get("loan_account") or None,
        "next_review_date": _date(merged.get("next_review_date"), "next review date", index),
        "parent_facility": _flag(merged.get("parent_facility")),
        "first_disbursement_date": _date(merged.get("first_disbursement_date"), "expected first disbursement date", index),
        "takeover": _flag(merged.get("takeover")),
    })
    # preserve any server-managed lifecycle/history values on edits
    for key in ("sanctioned_cr", "committed_cr", "executed_cr", "disbursed_cr", "outstanding_cr", "balance_cr",
                "execution_status", "linked_project_ids", "linked_security_ids", "linked_condition_ids",
                "change_history"):
        if key in merged:
            rec[key] = merged[key]
    return rec


def _flag(value) -> Optional[bool]:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("yes", "true", "1", "y")


def normalise_facilities(rows: list[dict], defaults: Optional[dict] = None) -> list[dict]:
    if not rows:
        raise InvalidRequestError("At least one proposed facility is required")
    if len(rows) > 20:
        raise InvalidRequestError("An application cannot contain more than 20 proposed facilities")
    out = [normalise_facility(row, i, defaults if i == 1 else None) for i, row in enumerate(rows, 1)]
    return out


def apply_sanction(facilities: list[dict], sanctioned_cr: Optional[float], at: str, by_name: str) -> None:
    """Allocate the sanctioned amount across facilities (pro-rata on the proposal) and
    open the committed commitment. Facility-wise recommendation/sanction is recorded."""
    total = round(sum(f["proposed_cr"] or 0 for f in facilities), 2)
    if sanctioned_cr is None:
        sanctioned_cr = total
    if sanctioned_cr < 0:
        raise InvalidRequestError("The sanctioned amount cannot be negative")
    if sanctioned_cr > total:
        raise InvalidRequestError(
            f"The sanctioned amount (₹{sanctioned_cr:,.2f} Cr) cannot exceed the proposed total (₹{total:,.2f} Cr)")
    for f in facilities:
        share = round((f["proposed_cr"] or 0) * sanctioned_cr / total, 2) if total else 0.0
        f["sanctioned_cr"] = share
        f["committed_cr"] = share
        f["disbursed_cr"] = 0.0
        f["outstanding_cr"] = 0.0
        f["balance_cr"] = share
        _history(f, at, by_name, f"sanctioned ₹{share:,.2f} Cr (committed)")
    _fix_rounding(facilities, sanctioned_cr)


def _fix_rounding(facilities: list[dict], sanctioned_cr: float) -> None:
    diff = round(sanctioned_cr - sum(f["sanctioned_cr"] or 0 for f in facilities), 2)
    if diff:
        target = max(facilities, key=lambda f: f["sanctioned_cr"] or 0)
        target["sanctioned_cr"] = round((target["sanctioned_cr"] or 0) + diff, 2)
        target["committed_cr"] = target["sanctioned_cr"]
        target["balance_cr"] = target["committed_cr"]


def apply_execution(facilities: list[dict], consent_facilities: list[dict], at: str, by_name: str) -> None:
    """Per-facility execution status from the recorded sanction consent (GAP-P0-13)."""
    by_id = {f["facility_id"]: f for f in consent_facilities}
    for f in facilities:
        row = by_id.get(f["facility_id"])
        if not row:
            continue
        status = row.get("execution_status")
        f["execution_status"] = status
        if status == "executed":
            f["executed_cr"] = f["committed_cr"]
        elif status == "partial":
            f["executed_cr"] = 0.0
        else:
            f["executed_cr"] = 0.0
        _history(f, at, by_name, f"facility execution: {status}")


def allocate_tranche(facilities: list[dict], facility_id: Optional[str], amount_cr: float, at: str) -> None:
    """A disbursement tranche approved for release moves through disbursed/outstanding/balance."""
    target = next((f for f in facilities if f["facility_id"] == facility_id), None)
    if target is None:
        if len(facilities) == 1:
            target = facilities[0]
        else:
            raise InvalidRequestError("A tranche must name the facility it is released against")
    available = round((target["committed_cr"] or 0) - (target["disbursed_cr"] or 0), 2)
    if amount_cr > available + 1e-6:
        raise InvalidRequestError(
            f"The tranche (₹{amount_cr:,.2f} Cr) exceeds the undisbursed balance of {target['facility_id']} "
            f"(₹{available:,.2f} Cr)")
    target["disbursed_cr"] = round((target["disbursed_cr"] or 0) + amount_cr, 2)
    target["outstanding_cr"] = target["disbursed_cr"]
    target["balance_cr"] = round((target["committed_cr"] or 0) - target["disbursed_cr"], 2)
    _history(target, at, "workflow", f"tranche of ₹{amount_cr:,.2f} Cr approved for release")


def _history(f: dict, at: str, by_name: str, change: str) -> None:
    f.setdefault("change_history", []).append({"at": at, "by": by_name, "change": change})


def facilities_view(app: dict) -> list[dict]:
    """Facilities with computed exposure split for the views/UI."""
    fund = round(sum((f.get("proposed_cr") or f.get("amount_cr") or 0) for f in app.get("facilities", []) if f.get("facility_nature") == "fund_based"), 2)
    non_fund = round(sum((f.get("proposed_cr") or f.get("amount_cr") or 0) for f in app.get("facilities", []) if f.get("facility_nature") == "non_fund_based"), 2)
    out = [dict(f) for f in app.get("facilities", [])]
    return out, {"total_cr": round(fund + non_fund, 2), "fund_based_cr": fund, "non_fund_based_cr": non_fund}


def change_facility(app: dict, facility_id: str, raw: dict, at: str, by_name: str) -> dict:
    """Edit a facility before sanction; the change is attributed and material after a decision."""
    f = next((x for x in app.get("facilities", []) if x["facility_id"] == facility_id), None)
    if not f:
        raise InvalidRequestError(f"Unknown facility: {facility_id}")
    before = {k: f.get(k) for k in ("amount_cr", "tenor_months", "facility_type", "facility_nature", "pricing", "repayment")}
    index = app["facilities"].index(f) + 1
    updated = normalise_facility({**f, **raw}, index)
    updated["facility_id"] = facility_id
    updated["change_history"] = f.get("change_history", [])
    changed = [k for k in before if before[k] != updated.get(k)]
    for k in changed:
        _history(updated, at, by_name, f"{k}: {before[k]!r} → {updated.get(k)!r}")
    app["facilities"][index - 1] = updated
    app["amount_cr"] = round(sum(x["proposed_cr"] or 0 for x in app["facilities"]), 2)
    app["facility"] = dict(app["facilities"][0])      # legacy primary mirror
    return updated
