"""
Later-stage document intake: the fields the intake agent reads for Post Sanction and Disbursement.

    post_sanction   the signed sanction letter (acceptance) and the facility agreement (execution)
    disbursement    the drawdown request (amount, value date, beneficiary account)

The same agent and corroboration as Prospect Sourcing (src/los/intake.py), with these field
sets. The values pre-fill the Post-Sanction and Disbursement forms; the maker verifies them by
saving the form, and the field store records each as confirmed (unchanged) or overridden (edited).
"""

from __future__ import annotations

from src.los.sourcing import _AMT

_DATE = r"(\d{1,2}[-/ ][A-Za-z]{3}[-/ ]\d{4})"

POST_SANCTION_FIELDS: list[dict] = [
    {"id": "sanction_reference", "label": "Sanction letter reference", "group": "Sanction acceptance", "kind": "text",
     "patterns": [r"Sanction (?:Letter )?Ref(?:erence)?(?: No\.?)?:\s*([A-Z0-9][A-Z0-9/\-]{3,40})"]},
    {"id": "accepted_by", "label": "Accepted by (borrower signatory)", "group": "Sanction acceptance", "kind": "text",
     "patterns": [r"Accepted (?:for and on behalf of [^:]+ )?by:\s*(.+?)(?:\s+Designation|\s+Date|,|$)"]},
    {"id": "acceptance_date", "label": "Date of acceptance", "group": "Sanction acceptance", "kind": "date",
     "patterns": [r"Date of acceptance:\s*" + _DATE]},
    {"id": "sanctioned_amount_cr", "label": "Sanctioned amount accepted (₹ Cr)", "group": "Sanction acceptance",
     "kind": "amount", "patterns": [r"Sanctioned (?:Amount|Limit):\s*" + _AMT]},
    {"id": "agreement_date", "label": "Facility agreement date", "group": "Facility execution", "kind": "date",
     "patterns": [r"(?:Agreement dated|Date of execution|executed on):?\s*" + _DATE]},
    {"id": "agreement_amount_cr", "label": "Facility amount in the agreement (₹ Cr)", "group": "Facility execution",
     "kind": "amount", "patterns": [r"(?:Facility|Loan) Amount:\s*" + _AMT]},
]

DISBURSEMENT_FIELDS: list[dict] = [
    {"id": "drawdown_amount_cr", "label": "Drawdown amount requested (₹ Cr)", "group": "Drawdown request",
     "kind": "amount", "patterns": [r"(?:Drawdown|Disbursement) Amount(?: requested)?:\s*" + _AMT]},
    {"id": "value_date", "label": "Value date", "group": "Drawdown request", "kind": "date",
     "patterns": [r"Value Date:\s*" + _DATE]},
    {"id": "drawdown_purpose", "label": "Purpose of the drawdown", "group": "Drawdown request", "kind": "text",
     "patterns": [r"Purpose of (?:the )?(?:drawdown|disbursement):\s*(.+?)(?:\.\s|\.$|$)"]},
    {"id": "beneficiary_name", "label": "Beneficiary name", "group": "Beneficiary", "kind": "text",
     "patterns": [r"Beneficiary(?: Name)?:\s*(.+?)(?:\s+(?:Account|A/c|Bank|IFSC)|$)"]},
    {"id": "account_number", "label": "Beneficiary account number", "group": "Beneficiary", "kind": "id",
     "patterns": [r"(?:Account (?:No\.?|Number)|A/c No\.?):\s*(\d{9,18})"]},
    {"id": "ifsc", "label": "IFSC", "group": "Beneficiary", "kind": "id",
     "patterns": [r"IFSC(?: Code)?:\s*([A-Z]{4}0[A-Z0-9]{6})"]},
]

STAGES = {"pos_maker": ("post_sanction", POST_SANCTION_FIELDS), "dis_maker": ("disbursement", DISBURSEMENT_FIELDS)}
STAGES_BY_DOMAIN = {domain: specs for domain, specs in STAGES.values()}


def values(prefill: dict) -> dict:
    """{field id: value} of what was found (for pre-filling a form)."""
    return {f["id"]: f["value"] for f in (prefill or {}).get("fields") or [] if f.get("value") not in (None, "")}
