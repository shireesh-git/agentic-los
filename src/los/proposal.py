"""Proposal, exposure, banking and conduct workspace (Client One GAP-P0-09).

Structured, editable, reviewable source-of-truth records (a CAM narrative never
replaces them): the proposal sections, exposure (bond/loan fetches labelled
demo, sector-wise and state-wise, sanctioned/disbursed/outstanding/committed,
norms with a breach alert and governed exception), the multiple-banking /
consortium arrangement (syndication must use Consortium — the one documented
hard rule), the preceding-12-month account conduct (Annexure IX), Annexure XI
regulatory/internal compliance, the inter-firm comparison, write-off losses,
connected lending, Annexure VI/XIII/XIV and applicable conditions.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from src.application.errors import InvalidRequestError

ARRANGEMENTS = ("sole", "consortium", "syndication")
CONDUCT_STATUSES = ("regular", "irregular")


def initial_proposal(app: dict, company: dict) -> dict:
    """Seed what can be honestly derived (existing exposure, market info) and leave
    the rest for the analyst to complete."""
    borrower = (company or {}).get("borrower") or {}
    sector = str(getattr(borrower, "sector", None) or "").strip() or None
    return {
        "summary": {"purpose": None, "tenure_months": app.get("facility", {}).get("tenor_months"),
                    "pricing_note": None, "security_note": None},
        "background": {"borrower_and_business": None, "industry_outlook": None,
                       "marketing_arrangements": None, "corporate_governance": None,
                       "strengths": None, "weaknesses": None, "key_risks": None,
                       "other_material_information": None},
        "exposure": {
            "bond": {"total_cr": None, "breakdown": None, "fetched_at": None, "fetched_by": None,
                     "source": None, "status": "not_fetched"},
            "loan": {"total_cr": None, "breakdown": None, "fetched_at": None, "fetched_by": None,
                     "source": None, "status": "not_fetched"},
            "sector_wise": [], "state_wise": [],
            "sanctioned_cr": None, "disbursed_cr": None, "outstanding_cr": None, "lms_committed_cr": None,
            "sector": sector, "state": None,
            "norms": {"lef": None, "epm": None,
                      "note": "LEF and EPM norms: formal meanings and rules are confirmation-required "
                              "(spec §22/P0-09); record them once the bank confirms."},
            "breach_alert": None, "exception": None,
        },
        "banking": {"arrangement": None, "lead_bank": None, "number_of_banks": None,
                    "institution_share_pct": None, "banks": [],
                    "details": {"borrower": None, "sponsor": None, "promoter": None}},
        "conduct": {"period": "preceding 12 months", "rows": []},
        "compliance": {"rows": [], "non_compliance_justification": None},
        "inter_firm": [],
        "write_off_losses": None, "connected_lending": None,
        "annexure_vi": None, "annexure_xiii": None, "annexure_xiv": None,
        "applicable_conditions": {"esg": None, "listed_company": None, "insurance": None, "other": None},
        "review_status": "draft", "review_by": None, "review_at": None,
        "note": "Fetch Bond/Loan Exposure uses the in-app (demo) reference data — production FT/LMS "
                "connectivity is GAP-P0-17.",
    }


def normalise_conduct(rows: list[dict]) -> list[dict]:
    out = []
    for i, r in enumerate(rows or [], 1):
        status = str(r.get("status") or "").strip()
        if status not in CONDUCT_STATUSES:
            raise InvalidRequestError(f"Conduct {i}: status must be regular or irregular")
        out.append({"month": (str(r.get("month") or "").strip() or None),
                    "limit_cr": _n(r.get("limit_cr"), f"conduct {i} limit"),
                    "outstanding_cr": _n(r.get("outstanding_cr"), f"conduct {i} outstanding"),
                    "irregularity": (str(r.get("irregularity") or "").strip() or None),
                    "peak_irregularity_cr": _n(r.get("peak_irregularity_cr"), f"conduct {i} peak"),
                    "instances": _i(r.get("instances"), f"conduct {i} instances"),
                    "irregular_days": _i(r.get("irregular_days"), f"conduct {i} days"),
                    "financial_difficulty": bool(r.get("financial_difficulty")),
                    "remarks": (str(r.get("remarks") or "").strip() or None), "status": status})
    return out


def normalise_banking(raw: dict) -> dict:
    arrangement = str(raw.get("arrangement") or "").strip()
    if arrangement not in ARRANGEMENTS:
        raise InvalidRequestError(f"Banking arrangement must be one of {', '.join(ARRANGEMENTS)}")
    banks = []
    for i, b in enumerate(raw.get("banks") or [], 1):
        name = str(b.get("name") or "").strip()
        if not name:
            raise InvalidRequestError(f"Bank {i}: the institution name is required")
        banks.append({"name": name, "share_pct": _n(b.get("share_pct"), f"bank {i} share"),
                      "role": (str(b.get("role") or "").strip() or None)})
    details = {k: (str(raw.get("details", {}).get(k) or "").strip() or None)
               if isinstance(raw.get("details"), dict) else (str(raw.get(k) or "").strip() or None)
               for k in ("borrower", "sponsor", "promoter")}
    return {"arrangement": arrangement, "lead_bank": (str(raw.get("lead_bank") or "").strip() or None),
            "number_of_banks": _i(raw.get("number_of_banks"), "number of banks") or (len(banks) or None),
            "institution_share_pct": _n(raw.get("institution_share_pct"), "institution share"),
            "banks": banks, "details": details}


def banking_gate(banking: Optional[dict]) -> Optional[str]:
    """GAP-P2-01: a syndication case uses a Consortium arrangement."""
    if banking and banking.get("arrangement") == "syndication" and banking.get("number_of_banks") in (None, 0, 1):
        return "A syndication case must use a Consortium arrangement with more than one participating bank"
    return None


def normalise_inter_firm(rows: list[dict]) -> list[dict]:
    out = []
    for i, r in enumerate(rows or [], 1):
        name = str(r.get("company") or "").strip()
        if not name:
            raise InvalidRequestError(f"Inter-firm row {i}: the company name is required")
        out.append({"company": name, "debt_cr": _n(r.get("debt_cr"), f"{name} debt"),
                    "revenue_cr": _n(r.get("revenue_cr"), f"{name} revenue"),
                    "ebitda_cr": _n(r.get("ebitda_cr"), f"{name} EBITDA"),
                    "pat_cr": _n(r.get("pat_cr"), f"{name} PAT"),
                    "debt_to_ebitda": _n(r.get("debt_to_ebitda"), f"{name} D/E"),
                    "pat_pct": _n(r.get("pat_pct"), f"{name} PAT%"),
                    "pe": _n(r.get("pe"), f"{name} P/E"),
                    "market_cap_cr": _n(r.get("market_cap_cr"), f"{name} market cap"),
                    "share_price": _n(r.get("share_price"), f"{name} share price")})
    return out


def normalise_exposure(raw: dict) -> dict:
    out = {}
    for key in ("sector_wise", "state_wise"):
        rows = []
        for r in raw.get(key) or []:
            label = str(r.get("label") or "").strip()
            if not label:
                raise InvalidRequestError(f"Exposure {key}: every row needs a label")
            rows.append({"label": label, "cr": _n(r.get("cr"), f"exposure {label}")})
        out[key] = rows
    for key in ("sanctioned_cr", "disbursed_cr", "outstanding_cr", "lms_committed_cr"):
        out[key] = _n(raw.get(key), f"exposure {key}")
    for key in ("sector", "state"):
        out[key] = (str(raw.get(key) or "").strip() or None)
    norms = raw.get("norms") or {}
    out["norms"] = {"lef": _n(norms.get("lef"), "LEF norm"), "epm": _n(norms.get("epm"), "EPM norm"),
                    "note": "LEF and EPM norms: formal meanings and rules are confirmation-required "
                            "(spec §22/P0-09)."}
    breach = str(raw.get("breach_alert") or "").strip() or None
    out["breach_alert"] = breach
    exc = raw.get("exception") or None
    out["exception"] = None if not exc else {
        "description": (str(exc.get("description") or "").strip() or None),
        "justification": (str(exc.get("justification") or "").strip() or None),
        "decided_by": exc.get("decided_by"), "decided_at": exc.get("decided_at")}
    return out


def exposure_gate(exposure: dict) -> Optional[str]:
    """GAP-P2-01: an exposure-limit breach must carry a governed exception."""
    if exposure.get("breach_alert") and not (exposure.get("exception") or {}).get("justification"):
        return "An exposure-norm breach is recorded — record the governed exception (description and justification)"
    return None


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
