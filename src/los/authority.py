"""Approval authority service (Client One GAP-P0-02 / P0-11).

One decision/authority service used by LOS routing: it computes the required
preliminary and final authority from the sanctioned amount, the risk grade,
the product mix and any policy deviations, and records the result with the
decision so the committee pack and the sanction record carry it.

The bank's *official* authority and deviation matrices are confirmation-required
(spec §18 item 17 and §28 item 4: "must not be invented from the screenshots").
The matrix here is an explicit, labelled demo default with the documented
preliminary/final split (IP Committee Sanction is preliminary; the final
Committee Sanction is binding) — not a claim about the bank's delegated
authority.
"""

from __future__ import annotations

from typing import Optional

# Labelled demo matrix (amount in ₹ Cr, risk grade, deviations).
PRELIMINARY_AUTHORITIES = (
    (200.0, "IP Sanction Committee (preliminary)"),
    (500.0, "IP Sanction Committee (preliminary) with EVP note"),
    (float("inf"), "IP Sanction Committee (preliminary) with EVP and CRP note"),
)
FINAL_AUTHORITIES = (
    (200.0, "Credit Sanction Committee"),
    (500.0, "Credit Sanction Committee with executive credit note"),
    (float("inf"), "Credit Sanction Committee with executive credit note and board intimation"),
)


def required_authority(amount_cr: Optional[float], risk_grade: Optional[str],
                       deviations: int = 0, final: bool = False) -> dict:
    amount = amount_cr or 0.0
    table = FINAL_AUTHORITIES if final else PRELIMINARY_AUTHORITIES
    authority = next(a for cap, a in table if amount <= cap)
    grade_risk = str(risk_grade or "").strip()
    if grade_risk and not grade_risk.startswith(("AAA", "AA")):
        authority += " (sub-investment-grade reviewer concurrence)"
    if deviations:
        authority += f" (with {deviations} recorded policy deviation(s) and minutes)"
    return {"amount_cr": amount, "risk_grade": grade_risk or None, "deviations": deviations,
            "required": authority, "basis": "labelled demo authority matrix — the bank-approved "
            "authority and deviation matrices are confirmation-required (spec §18/17, §28/4)"}


def deviation_entry(raw: dict) -> dict:
    """A policy deviation: type, description, source, justification and decision (GAP-P0-11)."""
    dev_type = str(raw.get("type") or "").strip()
    description = str(raw.get("description") or "").strip()
    justification = str(raw.get("justification") or "").strip()
    if not dev_type or not description:
        raise ValueError("a deviation needs its type and description")
    if not justification:
        raise ValueError("a policy deviation needs its justification")
    return {"type": dev_type, "description": description,
            "source": (str(raw.get("source") or "").strip() or None), "justification": justification,
            "decision": (str(raw.get("decision") or "pending").strip() or "pending"),
            "decided_by": raw.get("decided_by"), "decided_at": raw.get("decided_at")}
