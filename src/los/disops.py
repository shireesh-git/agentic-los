"""Disbursement Maker operational record (Client One GAP-P0-15) and the read-only
review checklists of the Disbursement Checker and Final Approver (GAP-P0-16).

Everything the client requires *before* the Maker submits is a governed record
here: CIF, exposure and limit IDs, loan accounts, operational security references,
beneficiaries, fee collection, non-fund charges, final repayment terms, interest
terms, arrears, drawdown request, the Interim SOP checklist and the generated,
reviewed Disbursement Memo. Demo operational systems are not connected: CIF/limit/
security numbers are recorded references (labelled demo), never presented as
production CBS writes.
"""

from __future__ import annotations

import hashlib
import re
from typing import Optional

from src.application.errors import InvalidRequestError

# ─── CIF ─────────────────────────────────────────────────────────────────────

CIF_STATUSES = ("exists", "created", "updated")


def normalise_cif(raw: dict) -> dict:
    status = str(raw.get("status") or "").strip()
    if status not in CIF_STATUSES:
        raise InvalidRequestError(f"CIF status must be one of {', '.join(CIF_STATUSES)}")
    cif_no = str(raw.get("cif_no") or "").strip()
    if not cif_no:
        raise InvalidRequestError("The CIF number is required")
    return {"status": status, "cif_no": cif_no, "note": (str(raw.get("note") or "").strip() or None)}


# ─── Limits, loan accounts ───────────────────────────────────────────────────

def normalise_limits(rows: list[dict]) -> list[dict]:
    out = []
    for i, raw in enumerate(rows or []):
        limit_id = str(raw.get("limit_id") or "").strip()
        if not limit_id:
            raise InvalidRequestError(f"Limit {i + 1}: the limit ID is required")
        kind = str(raw.get("kind") or "fund").strip()
        if kind not in ("total", "fund", "non_fund"):
            raise InvalidRequestError(f"Limit {i + 1}: kind must be total, fund or non_fund")
        out.append({"facility_id": raw.get("facility_id") or None, "kind": kind, "limit_id": limit_id,
                    "suffix": (str(raw.get("suffix") or "").strip() or None),
                    "next_review_date": _iso_date(raw.get("next_review_date"), f"limit {i + 1}")})
    return out


def normalise_loan_accounts(rows: list[dict]) -> list[dict]:
    out = []
    for i, raw in enumerate(rows or []):
        account = str(raw.get("account_no") or "").strip()
        if not account:
            raise InvalidRequestError(f"Loan account {i + 1}: the account number is required")
        out.append({"facility_id": raw.get("facility_id") or None, "account_no": account,
                    "status": str(raw.get("status") or "active").strip() or "active"})
    return out


# ─── Operational security references ─────────────────────────────────────────

def normalise_security_refs(rows: list[dict]) -> list[dict]:
    out = []
    for i, raw in enumerate(rows or []):
        sid = str(raw.get("security_id") or "").strip()
        if not sid:
            raise InvalidRequestError(f"Security reference {i + 1}: security_id is required")
        creation = str(raw.get("creation_status") or "pending").strip()
        if creation not in ("created", "pending"):
            raise InvalidRequestError(f"Security {i + 1}: creation status must be created or pending")
        perfection = str(raw.get("perfection_status") or "pending").strip()
        if perfection not in ("perfected", "in_progress", "pending"):
            raise InvalidRequestError(f"Security {i + 1}: perfection status must be perfected, in_progress or pending")
        cersai = str(raw.get("cersai") or "pending").strip()
        roc = str(raw.get("roc") or "pending").strip()
        if cersai not in ("filed", "pending", "na") or roc not in ("filed", "pending", "na"):
            raise InvalidRequestError(f"Security {i + 1}: CERSAI/ROC must be filed, pending or na")
        out.append({"security_id": sid, "los_security_id": (str(raw.get("los_security_id") or "").strip() or None),
                    "type": (str(raw.get("type") or "").strip() or None),
                    "facility_id": raw.get("facility_id") or None,
                    "description": (str(raw.get("description") or "").strip() or None),
                    "creation_status": creation, "creation_date": _iso_date(raw.get("creation_date"), f"security {i + 1}"),
                    "perfection_status": perfection,
                    "perfection_eta": _iso_date(raw.get("perfection_eta"), f"security {i + 1}"),
                    "valuation_date": _iso_date(raw.get("valuation_date"), f"security {i + 1}"),
                    "valuation_cr": _num(raw.get("valuation_cr"), f"security {i + 1} valuation"),
                    "cersai": cersai, "roc": roc,
                    "cbs_security_no": (str(raw.get("cbs_security_no") or "").strip() or None)})
    return out


def security_gate(security_refs: list[dict]) -> Optional[str]:
    """GAP-P2-01: every applicable security must carry a CBS Security Number before disbursement."""
    missing = [s["security_id"] for s in security_refs if not s.get("cbs_security_no")]
    return f"Create the CBS Security Number for: {', '.join(missing)}" if missing else None


# ─── Beneficiaries ───────────────────────────────────────────────────────────

IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
PAYMENT_MODES = ("NEFT", "RTGS", "IMPS", "cheque", "electronic")


def normalise_beneficiaries(rows: list[dict]) -> list[dict]:
    if not rows:
        raise InvalidRequestError("At least one beneficiary is required")
    out = []
    for i, raw in enumerate(rows or [], 1):
        name = str(raw.get("name") or "").strip()
        account = str(raw.get("account_no") or "").strip()
        bank = str(raw.get("bank") or "").strip()
        branch = str(raw.get("branch") or "").strip()
        ifsc = str(raw.get("ifsc") or "").strip().upper()
        if not name or not account or not bank or not ifsc:
            raise InvalidRequestError(f"Beneficiary {i}: name, account number, bank and IFSC are required")
        if not IFSC_RE.match(ifsc):
            raise InvalidRequestError(f"Beneficiary {i}: the IFSC ({ifsc}) is not in the standard format")
        mode = str(raw.get("payment_mode") or "NEFT").strip().upper()
        if mode not in PAYMENT_MODES:
            raise InvalidRequestError(f"Beneficiary {i}: payment mode must be one of {', '.join(PAYMENT_MODES)}")
        amount = _num(raw.get("amount_cr"), f"beneficiary {i} amount")
        if amount is not None and amount <= 0:
            raise InvalidRequestError(f"Beneficiary {i}: the amount must be greater than zero")
        out.append({"beneficiary_id": f"BEN-{i:02d}", "facility_id": raw.get("facility_id") or None,
                    "type": (str(raw.get("type") or "borrower").strip() or "borrower"), "name": name,
                    "account_no": account, "bank": bank, "branch": branch or None, "ifsc": ifsc,
                    "payment_mode": mode, "amount_cr": amount})
    return out


# ─── Fees ────────────────────────────────────────────────────────────────────

FEE_NATURES = ("upfront", "annual_review", "processing", "stamp_duty", "other")


def normalise_fees(rows: list[dict]) -> list[dict]:
    out = []
    for i, raw in enumerate(rows or [], 1):
        nature = str(raw.get("nature") or "").strip()
        if nature not in FEE_NATURES:
            raise InvalidRequestError(f"Fee {i}: nature must be one of {', '.join(FEE_NATURES)}")
        scope = str(raw.get("scope") or "facility").strip()
        if scope not in ("common", "facility"):
            raise InvalidRequestError(f"Fee {i}: scope must be common or facility")
        amount = _num(raw.get("amount_cr"), f"fee {i} amount")
        pct = _num(raw.get("pct"), f"fee {i} percentage")
        if amount is None and pct is None:
            raise InvalidRequestError(f"Fee {i}: an amount or a percentage is required")
        gross = _num(raw.get("gross_cr"), f"fee {i} gross")
        gst = _num(raw.get("gst_cr"), f"fee {i} GST") or 0.0
        total = _num(raw.get("total_cr"), f"fee {i} total")
        if total is None:
            total = round((gross or 0) + gst, 2) if gross is not None else None
        received = _num(raw.get("received_cr"), f"fee {i} received")
        due = _num(raw.get("due_cr"), f"fee {i} due")
        balance = _num(raw.get("balance_cr"), f"fee {i} balance")
        if balance is None and total is not None and received is not None:
            balance = round(total - received, 2)
        out.append({"fee_id": f"FEE-{i:02d}", "facility_id": raw.get("facility_id") if scope == "facility" else None,
                    "nature": nature, "type": (str(raw.get("type") or "").strip() or None), "scope": scope,
                    "amount_cr": amount, "pct": pct,
                    "milestone": (str(raw.get("milestone") or "").strip() or None),
                    "comments": (str(raw.get("comments") or "").strip() or None),
                    "gross_cr": gross, "due_cr": due, "gst_cr": gst, "total_cr": total,
                    "receipt_date": _iso_date(raw.get("receipt_date"), f"fee {i}"),
                    "received_cr": received, "balance_cr": balance,
                    "pending_due_date": _iso_date(raw.get("pending_due_date"), f"fee {i}"),
                    "remarks": (str(raw.get("remarks") or "").strip() or None)})
    return out


def normalise_non_fund_charges(raw: dict) -> dict:
    return {"charges": [{"description": str(c.get("description") or "").strip(),
                         "amount_cr": _num(c.get("amount_cr"), "non-fund charge")}
                        for c in raw.get("charges") or [] if str(c.get("description") or "").strip()],
            "gst_cr": _num(raw.get("gst_cr"), "non-fund GST"),
            "deferred_balance_cr": _num(raw.get("deferred_balance_cr"), "deferred balance"),
            "collection_frequency": (str(raw.get("collection_frequency") or "").strip() or None),
            "due_date": _iso_date(raw.get("due_date"), "non-fund charges"),
            "pending_recovery_remarks": (str(raw.get("pending_recovery_remarks") or "").strip() or None)}


# ─── Final repayment & interest terms ────────────────────────────────────────

def normalise_repayment_final(raw: dict) -> dict:
    tenor = _num(raw.get("tenor_months"), "final tenor")
    moratorium = _num(raw.get("moratorium_months"), "final moratorium")
    freq = str(raw.get("instalment_frequency") or "").strip()
    if not freq:
        raise InvalidRequestError("The final instalment frequency is required")
    return {"moratorium_months": moratorium, "tenor_months": tenor, "instalment_frequency": freq,
            "interest_payment_details": (str(raw.get("interest_payment_details") or "").strip() or None),
            "repayment_conditions": (str(raw.get("repayment_conditions") or "").strip() or None)}


def normalise_interest_terms(raw: dict) -> dict:
    benchmark = str(raw.get("benchmark") or "").strip()
    rate = _num(raw.get("rate"), "interest rate")
    if not benchmark or rate is None:
        raise InvalidRequestError("The benchmark and the interest rate are required")
    return {"benchmark": benchmark, "rate": rate, "spread": _num(raw.get("spread"), "spread"),
            "reset_frequency": (str(raw.get("reset_frequency") or "").strip() or None),
            "reset_date": _iso_date(raw.get("reset_date"), "reset date"),
            "additional_interest_non_perfection": _num(raw.get("additional_interest_non_perfection"),
                                                       "additional interest for non-perfection"),
            "effective_rate": _num(raw.get("effective_rate"), "effective rate"),
            "penal_rate": _num(raw.get("penal_rate"), "penal rate"),
            "start_date": _iso_date(raw.get("start_date"), "start date"),
            "calculation_parameters": (str(raw.get("calculation_parameters") or "").strip() or None)}


# ─── Arrears ─────────────────────────────────────────────────────────────────

def normalise_arrears(raw: dict) -> dict:
    exists = bool(raw.get("exists"))
    rows = []
    if exists:
        for i, a in enumerate(raw.get("rows") or [], 1):
            amount = _num(a.get("amount_cr"), f"arrear {i} amount")
            if not str(a.get("type") or "").strip() or amount is None:
                raise InvalidRequestError(f"Arrear {i}: type and amount are required")
            rows.append({"facility_id": a.get("facility_id") or None, "type": str(a["type"]).strip(),
                         "amount_cr": amount, "currency": str(a.get("currency") or "INR").strip() or "INR",
                         "due_since": _iso_date(a.get("due_since"), f"arrear {i}"),
                         "remarks": (str(a.get("remarks") or "").strip() or None)})
    return {"exists": exists, "rows": rows}


# ─── Drawdown request ────────────────────────────────────────────────────────

def normalise_drawdown(raw: dict) -> dict:
    return {"request_ref": (str(raw.get("request_ref") or "").strip() or None),
            "request_date": _iso_date(raw.get("request_date"), "drawdown request"),
            "schedule": [{"tranche": i + 1, "amount_cr": _num(s.get("amount_cr"), f"drawdown {i + 1}"),
                          "date": _iso_date(s.get("date"), f"drawdown {i + 1}")}
                         for i, s in enumerate(raw.get("schedule") or [])],
            "annexures": [str(a).strip() for a in raw.get("annexures") or [] if str(a).strip()]}


# ─── Interim SOP checklist ───────────────────────────────────────────────────

SOP_ITEMS = [
    ("sop_kyc", "KYC records current, complete and in compliance"),
    ("sop_treasury", "Treasury coordination for the release is complete"),
    ("sop_legal", "Legal verification of the credit and security documents is complete"),
    ("sop_beneficiary", "Beneficiary details verified against the signed mandate"),
    ("sop_fees", "Fees collected or the recovery plan is in place"),
    ("sop_security", "Security creation/perfection status verified against the security record"),
    ("sop_insurance", "Insurance policies issued/assigned as required"),
    ("sop_limits", "Limits and loan accounts verified in core banking (demo — confirm manually)"),
]
SOP_STATUSES = ("in_compliance", "not_in_compliance", "not_applicable")


def initial_sop() -> list[dict]:
    return [{"id": i, "label": label, "status": "not_in_compliance", "remarks": None, "by_name": None, "at": None}
            for i, label in SOP_ITEMS]


def normalise_sop(items: list[dict], current: list[dict]) -> list[dict]:
    by_id = {i["id"]: dict(i) for i in current}
    for raw in items or []:
        item = by_id.get(str(raw.get("id") or ""))
        if not item:
            raise InvalidRequestError(f"Unknown SOP item: {raw.get('id')}")
        status = str(raw.get("status") or "").strip()
        if status not in SOP_STATUSES:
            raise InvalidRequestError(f"SOP item {item['id']}: status must be one of {', '.join(SOP_STATUSES)}")
        remarks = (str(raw.get("remarks") or "").strip() or None)
        if status == "not_in_compliance" and not remarks:
            raise InvalidRequestError(f"SOP item {item['id']}: a remark is required when not in compliance")
        item.update(status=status, remarks=remarks)
    return list(by_id.values())


def sop_gate(sop: list[dict]) -> Optional[str]:
    """GAP-P2-01: every applicable mandatory SOP item must be In Compliance before Maker submission."""
    open_items = [i["label"] for i in sop if i["status"] == "not_in_compliance"]
    return "The Interim SOP is not complete: " + "; ".join(open_items) if open_items else None


# ─── Disbursement Memo ───────────────────────────────────────────────────────

def memo_hash(disops: dict) -> str:
    import json
    return hashlib.sha256(json.dumps({k: disops.get(k) for k in
                                      ("cif", "limits", "loan_accounts", "security_refs", "beneficiaries",
                                       "fees", "non_fund_charges", "repayment_final", "interest_terms",
                                       "arrears", "drawdown")}, sort_keys=True).encode()).hexdigest()[:16]


def disops_view(app: dict) -> dict:
    disops = app.get("disops") or {}
    securities = app.get("securities") or []
    refs = disops.get("security_refs") or []
    applicable = [s for s in securities]
    view = {
        "present": bool(disops),
        "cif": disops.get("cif"),
        "exposure": disops.get("exposure"),
        "limits": disops.get("limits") or [],
        "loan_accounts": disops.get("loan_accounts") or [],
        "security_refs": refs,
        "security_gate": security_gate(refs) if applicable else None,
        "beneficiaries": disops.get("beneficiaries") or [],
        "fees": disops.get("fees") or [],
        "non_fund_charges": disops.get("non_fund_charges"),
        "repayment_final": disops.get("repayment_final"),
        "interest_terms": disops.get("interest_terms"),
        "arrears": disops.get("arrears"),
        "drawdown": disops.get("drawdown"),
        "sop": disops.get("sop") or [],
        "sop_gate": sop_gate(disops.get("sop") or []),
        "memo": disops.get("memo"),
        "missing_info": disops.get("missing_info") or [],
        "external_rating_retrigger": disops.get("external_rating_retrigger"),
        # the review checklists exist from the start, so the reviewer sees what to verify
        "checker_review": disops.get("checker_review") or initial_review(CHECKER_REVIEW_ITEMS),
        "final_review": disops.get("final_review") or initial_review(FINAL_REVIEW_ITEMS),
        "note": "CIF, limit, loan-account and CBS security references are recorded operational data "
                "(demo — core banking is not connected); they are evidence for the approval, not CBS writes.",
    }
    return view


def maker_gate(app: dict) -> Optional[str]:
    """Everything required before the Disbursement Maker can submit (GAP-P0-15, rules P2-01)."""
    view = disops_view(app)
    missing = []
    if not view["cif"]:
        missing.append("the CIF record (existence check; create for NTB, update for ETB)")
    if not view["limits"]:
        missing.append("the exposure and limit IDs (total / fund-based / non-fund-based)")
    if not view["loan_accounts"]:
        missing.append("the applicable loan accounts")
    if view["security_gate"]:
        missing.append(view["security_gate"])
    if not view["beneficiaries"]:
        missing.append("the beneficiaries (facility, account, bank, branch, IFSC, mode, amount)")
    if not view["fees"] and not view["non_fund_charges"]:
        missing.append("the fee collection record (or the non-fund charges record)")
    if not view["repayment_final"]:
        missing.append("the final moratorium, tenure, instalment frequency and interest-payment details")
    if not view["interest_terms"]:
        missing.append("the interest terms (benchmark, rate, spread, reset, penal and effective rates)")
    if not view["arrears"]:
        missing.append("the arrears record (declare existence, or none)")
    if not view["drawdown"]:
        missing.append("the Drawdown Request / schedule")
    if view["sop_gate"]:
        missing.append(view["sop_gate"])
    memo = view["memo"]
    if not memo or not memo.get("reviewed"):
        missing.append("the generated and reviewed Disbursement Memo")
    return ("The disbursement record is incomplete — complete: " + "; ".join(missing)) if missing else None


# ─── Read-only review checklists (Checker / Final Approver) ─────────────────

CHECKER_REVIEW_ITEMS = [
    "Customer and borrower record complete and accurate",
    "Documents on file match the sanctioned terms",
    "CIF, limits and loan accounts are consistent with the record above",
    "Security IDs and linkages verified (Annexure IV)",
    "Facility execution and agreement dates verified",
    "Beneficiaries and payment instructions verified against the mandate",
    "Disbursement Memo reviewed and consistent with the record",
    "Annexure I repayment schedule consistent with the final terms",
    "Interest terms (benchmark, reset, penal) verified",
    "Arrears disclosed and explained",
    "Applicable annexures present",
]
FINAL_REVIEW_ITEMS = [
    "Customer and documents reviewed",
    "CIF, limits, accounts and security IDs/linkages reviewed",
    "Facility execution verified",
    "Beneficiaries and memo verified",
    "Annexure I repayment, interest and project details verified",
    "Annexure IV security details verified",
    "Arrears and annexures verified",
]


def initial_review(labels: list[str]) -> list[dict]:
    return [{"id": f"R-{i:02d}", "label": label, "done": False} for i, label in enumerate(labels, 1)]


def normalise_review(items: list[str], current: Optional[list[dict]]) -> list[dict]:
    out = current or [{"id": f"R-{i:02d}", "label": label, "done": False} for i, label in enumerate(items, 1)]
    return out


def review_gate(review: Optional[list[dict]], stage: str) -> Optional[str]:
    if not review:
        labels = CHECKER_REVIEW_ITEMS if stage.startswith("Disbursement Checker") else FINAL_REVIEW_ITEMS
        return (f"The {stage} review is not complete: " + "; ".join(labels[:3]) + "…")
    pending = [r["label"] for r in review if not r["done"]]
    if pending:
        return f"The {stage} review is not complete: " + "; ".join(pending[:3]) + ("…" if len(pending) > 3 else "")
    return None


# ─── helpers ─────────────────────────────────────────────────────────────────

def _num(value, name: str):
    if value in (None, ""):
        return None
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        raise InvalidRequestError(f"{name} must be a number")


def _iso_date(value, name: str):
    if not value:
        return None
    try:
        from datetime import date
        return date.fromisoformat(str(value).strip()).isoformat()
    except ValueError:
        raise InvalidRequestError(f"{name} must be YYYY-MM-DD")
