"""Entity-wise financial analysis and CMA workspace (Client One GAP-P0-07).

The CMA is a governed, editable record per entity (borrower, promoter, sponsor,
SPV or parent): rows in ₹ crores with a source, period and version on every
value, an explicit audited / provisional / projected separation, a
maker–checker review (entry by the maker, approval by a reviewer), download
(HTML) and reconciliation after revised financials.

The exact authoritative row set, formula set, number of years, rounding and
tolerances are confirmation-required (spec §22/P0-07: "Do not invent the
complete CMA formula set") — the rows implemented here are the fields the
client documents (revenue, income, expenses, depreciation, finance cost, PBT,
PAT, margins, cash accruals) computed transparently from the entered values.
"""

from __future__ import annotations

from typing import Optional

from src.application.errors import InvalidRequestError

CMA_SUBJECTS = ("borrower", "promoter", "sponsor", "spv", "parent")
VALUE_CLASSES = ("audited", "provisional", "projected")
REVIEW_STATUSES = ("draft", "submitted", "approved", "returned")

# The documented CMA rows — kept deliberately close to what the client lists.
CMA_ROWS = [
    ("revenue", "Revenue (₹ Cr)"),
    ("income", "Income (₹ Cr)"),
    ("expenses", "Expenses (₹ Cr)"),
    ("depreciation", "Depreciation (₹ Cr)"),
    ("finance_cost", "Finance Cost (₹ Cr)"),
    ("pbt", "PBT (₹ Cr)"),
    ("pat", "PAT (₹ Cr)"),
    ("cash_accruals", "Cash Accruals (₹ Cr)"),
]
DERIVED = {  # computed transparently from entered rows; never stored as entries
    "ebitda_margin_pct": "PBT + Depreciation + Finance Cost vs Revenue",
    "pat_margin_pct": "PAT vs Revenue",
    "cash_accruals_pct": "Cash Accruals vs Revenue",
}


def initial_cma(app: dict = None) -> dict:
    """The CMA workspace starts empty; the maker records entity-wise rows."""
    return {"subjects": [], "comments": "", "review_status": "draft", "review_by": None, "review_at": None}


def normalise_rows(rows: dict, subject: str) -> dict:
    """rows: {period: {row_id: value}}; every value must be a number in ₹ crores."""
    import re as _re
    out = {}
    for period, vals in dict(rows or {}).items():
        period = str(period).strip()
        if not _re.match(r"^(FY)?\d{4}(-\d{2,4})?$", period, _re.I):
            raise InvalidRequestError(f"{subject}: the period '{period}' is not a recognisable year")
        out[period] = {}
        for row_id, label in CMA_ROWS:
            v = (vals or {}).get(row_id)
            if v in (None, ""):
                continue
            try:
                out[period][row_id] = round(float(v), 4)
            except (TypeError, ValueError):
                raise InvalidRequestError(f"{subject} {period}: {label} must be a number (₹ crores)")
    return out


def highlights(period_rows: dict) -> dict:
    def num(key):
        v = period_rows.get(key)
        return v if v not in (None, "") else None

    revenue, pbt, pat, dep, fc = (num(k) for k in ("revenue", "pbt", "pat", "depreciation", "finance_cost"))
    out = {}
    if revenue:
        ebitda = None
        if pbt is not None:
            ebitda = pbt + (dep or 0) + (fc or 0)
            out["ebitda_margin_pct"] = round(ebitda / revenue * 100, 2)
        if pat is not None:
            out["pat_margin_pct"] = round(pat / revenue * 100, 2)
        if period_rows.get("cash_accruals") is not None:
            out["cash_accruals_pct"] = round(period_rows["cash_accruals"] / revenue * 100, 2)
    return out


def cma_view(app: dict) -> dict:
    cma = app.get("cma") or {"subjects": [], "comments": "", "review_status": "draft"}
    subjects = []
    for s in cma.get("subjects") or []:
        rows = s.get("rows") or {}
        subjects.append({**s,
                         "row_count": sum(len(v) for v in rows.values()),
                         "periods": sorted(rows.keys())})
    return {**{k: cma.get(k) for k in ("comments", "review_status", "review_by", "review_at")},
            "subjects": subjects,
            "note": "Values carry source, period and version per entry; the row set and formulas shown are "
                    "the documented fields only — the complete authoritative CMA template is "
                    "confirmation-required (spec §22/P0-07)."}


def reconciliation(app: dict) -> list[dict]:
    """Compare the latest CMA period against the assessment's historical financials (GAP-P0-07)."""
    case = app.get("assessment_case") or {}
    fin = case.get("financials") or {}
    hist = {str(p.get("year")): p for p in fin.get("historical") or []}
    out = []
    for s in (app.get("cma") or {}).get("subjects") or []:
        rows = s.get("rows") or {}
        for period, vals in rows.items():
            h = hist.get(period)
            if not h:
                continue
            key = {"revenue": "revenue_cr", "pat": "pat_cr"}.get(next(iter(vals), ""))
            for row_id, hkey in (("revenue", "revenue_cr"), ("pat", "pat_cr"), ("pbt", "pbt_cr")):
                v, hv = vals.get(row_id), h.get(hkey)
                if v is None or hv in (None, ""):
                    continue
                if abs(v - float(hv)) > 0.01:
                    out.append({"subject": s["subject"], "period": period, "row": row_id,
                                "cma_value": v, "historical_value": hv,
                                "note": "CMA differs from the financials used by the assessment — "
                                        "reconcile or re-run the assessment"})
    return out
