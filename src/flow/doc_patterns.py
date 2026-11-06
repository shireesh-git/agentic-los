"""Labelled-field patterns for reading values out of loan documents (used by the CAM intake agent,
src/flow/cam_intake.py): each field's regexes, value normalising and comparing, and the first labelled hit
in a document's pages with its page and snippet."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

_AMT = r"(?:₹|Rs\.?|INR|I)\s?([\d,]+(?:\.\d+)?)\s*(?:Cr|crore)"
_NUM = r"([\d,]+(?:\.\d+)?)"
MAX_PAGES = 12          # long filings (annual reports) are read for their opening pages only

# id, label, group, kind, patterns, application target
FIELDS: list[dict] = [
    {"id": "legal_name", "label": "Legal name", "group": "Borrower", "kind": "text",
     "patterns": [r"Legal Name:\s*(.+?)(?:\s+CIN:|\s+Incorporated:|$)",
                  r"Name of the (?:Borrower|Applicant):\s*(.+?)(?:\s+CIN:|\s+PAN:|\s+Constitution:|$)"]},
    {"id": "cin", "label": "CIN", "group": "Borrower", "kind": "id",
     "patterns": [r"CIN:\s*([LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6})"]},
    {"id": "pan", "label": "PAN", "group": "Borrower", "kind": "id",
     "patterns": [r"PAN:\s*([A-Z]{5}\d{4}[A-Z])"]},
    {"id": "gstin", "label": "GSTIN", "group": "Borrower", "kind": "id",
     "patterns": [r"GSTIN:?\s*(\d{2}[A-Z]{5}\d{4}[A-Z]\d[Z][A-Z\d])"]},
    {"id": "date_of_incorporation", "label": "Date of incorporation", "group": "Borrower", "kind": "date",
     "patterns": [r"Incorporated(?: on)?:\s*(\d{1,2}[-/ ][A-Za-z]{3}[-/ ]\d{4})"]},
    {"id": "registered_address", "label": "Registered office", "group": "Borrower", "kind": "text",
     "patterns": [r"Registered Office:\s*(.+?\d{6})"]},
    {"id": "listed_exchange", "label": "Listed on", "group": "Borrower", "kind": "text",
     "patterns": [r"Listed Exchange:\s*([A-Z, ]+?)(?:\s+Corporate|\s+[A-Z][a-z]|$)"]},
    {"id": "authorised_signatory", "label": "Authorised signatory", "group": "Borrower", "kind": "text",
     "patterns": [r"Board authori[sz]es\s+(.+?)\s+to execute"]},
    {"id": "facility_type", "label": "Facility type", "group": "Proposal", "kind": "facility", "target": "facility_type",
     "patterns": [r"Facility (?:Requested|type):\s*([a-z_]+)", r"for the proposed\s+([a-z_]+)\.",
                  r"(?:Facility|Nature of Facility|Facility Type) ?(?:Proposed)?:\s*((?:Working Capital|Term Loan|Project Finance)[A-Za-z ]*?)(?=\s+[A-Z][A-Za-z ]{2,30}:|\.|$)"]},
    {"id": "case_type", "label": "Case type", "group": "Proposal", "kind": "code", "target": "case_type",
     "patterns": [r"Case Type:\s*(ETB|NTB)"]},
    {"id": "amount_cr", "label": "Proposed amount (₹ Cr)", "group": "Proposal", "kind": "amount", "target": "amount_cr",
     "patterns": [r"Amount Requested:\s*" + _AMT, r"Requested limit under review:\s*" + _AMT,
                  r"Proposed (?:Limit|Amount):\s*" + _AMT]},
    {"id": "tenor_months", "label": "Tenor (months)", "group": "Proposal", "kind": "int", "target": "tenor_months",
     "patterns": [r"Tenor:\s*(\d+)\s*months"]},
    {"id": "purpose", "label": "Purpose", "group": "Proposal", "kind": "text", "target": "purpose",
     "patterns": [r"(?<!Primary )Purpose:\s*(.+?)(?:\s+Latest Financial|\s+Credit View|\.\s|\.$|$)",
                  r"Primary purpose(?: stated by management)?:\s*(.+?)(?:\.\s|\.$|$)"]},
    {"id": "revenue_cr", "label": "Revenue — latest year (₹ Cr)", "group": "Financials", "kind": "amount",
     "patterns": [r"Revenue from Operations\s+" + _NUM, r"Snapshot[^:]*:\s*Revenue\s+" + _AMT]},
    {"id": "ebitda_cr", "label": "EBITDA — latest year (₹ Cr)", "group": "Financials", "kind": "amount",
     "patterns": [r"\bEBITDA\s+" + _NUM + r"\s", r"Snapshot[^.]*?EBITDA\s+" + _AMT]},
    {"id": "pat_cr", "label": "PAT — latest year (₹ Cr)", "group": "Financials", "kind": "amount",
     "patterns": [r"Profit After Tax\s+" + _NUM, r"Snapshot[^.]*?PAT\s+" + _AMT]},
    {"id": "net_worth_cr", "label": "Net worth — latest year (₹ Cr)", "group": "Financials", "kind": "amount",
     "patterns": [r"Total Equity\s+" + _NUM]},
    {"id": "total_debt_cr", "label": "Total debt — latest year (₹ Cr)", "group": "Financials", "kind": "amount",
     "patterns": [r"Total Debt\s+" + _NUM, r"Snapshot[^.]*?Debt\s+" + _AMT]},
    {"id": "external_rating", "label": "External rating", "group": "Rating & security", "kind": "text",
     "patterns": [r"(?:Assigned / Referenced )?Rating:\s*([A-Z]+ [A-Z+\-]+(?:/[A-Za-z]+)?)"]},
    {"id": "collateral_mv_cr", "label": "Collateral market value (₹ Cr)", "group": "Rating & security", "kind": "amount",
     "patterns": [r"collateral market value assessed at\s*" + _AMT]},
    {"id": "collateral_fsv_cr", "label": "Collateral forced-sale value (₹ Cr)", "group": "Rating & security",
     "kind": "amount", "patterns": [r"forced-sale value of\s*" + _AMT]},
]

_FACILITY_CODES = (("working capital", "working_capital"), ("term loan", "term_loan"),
                   ("project financ", "project_finance"))


def _norm(kind: str, raw: str):
    raw = raw.strip().strip(".,;")
    if kind == "facility":                     # a CAM says "Working Capital Term Loan"; the form wants a code
        low = raw.lower().replace("_", " ")
        return next((code for words, code in _FACILITY_CODES if words in low), re.sub(r"[^a-z0-9]+", "_", low).strip("_"))
    if kind in ("amount", "int"):
        try:
            v = float(raw.replace(",", ""))
        except ValueError:
            return None
        return int(v) if kind == "int" else v
    if kind == "date":
        for fmt in ("%d-%b-%Y", "%d/%b/%Y", "%d %b %Y"):
            try:
                return datetime.strptime(raw, fmt).date().isoformat()
            except ValueError:
                pass
        return None
    return raw


def _snippet(text: str, start: int, end: int, pad: int = 60) -> str:
    s, e = max(0, start - pad), min(len(text), end + pad)
    return ("…" if s else "") + text[s:e].strip() + ("…" if e < len(text) else "")


def _first_hit(spec: dict, doc: dict) -> Optional[dict]:
    """The first labelled value for the field in the document (one per document)."""
    for pno, text in enumerate(doc["pages"][:MAX_PAGES], start=1):
        for rank, pat in enumerate(spec["patterns"]):
            m = re.search(pat, text)
            value = _norm(spec["kind"], m.group(1)) if m else None
            if value not in (None, ""):
                return {"value": value, "document": doc["document"], "category": doc["category"], "page": pno,
                        "snippet": _snippet(text, m.start(), m.end()), "method": "pattern", "rank": rank}
    return None
