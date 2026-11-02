"""R11 — automatic policy-deviation detection from the profile's `deviation_rules`.

Pure function of (app, profile): each rule that the application's facts breach
produces a deviation record with the rule reference, the expected vs the actual
value, a severity, and the authority the deviation requires. The natural key is
the rule reference + the compared values, so re-detection is idempotent (a
recorded deviation is matched, not duplicated).
"""
from __future__ import annotations

import hashlib
from typing import Optional


def _natural_key(rule_ref: str, actual) -> str:
    return hashlib.sha1(f"{rule_ref}:{actual!r}".encode("utf-8")).hexdigest()[:16]


def detect_policy_deviations(app: dict, profile: dict) -> list[dict]:
    """The policy deviations the application's facts trigger under ``profile``'s rules."""
    rules = (profile or {}).get("deviation_rules") or {}
    facs = app.get("facilities") or [app.get("facility") or {}]
    amount = float(app.get("amount_cr") or sum(float(f.get("amount_cr") or 0) for f in facs))
    max_tenor = max((int(f.get("tenor_months") or 0) for f in facs), default=0)
    grade = str((app.get("credit_assessment") or {}).get("risk_grade") or
                (app.get("ratings") or {}).get("risk_grade") or "").strip()
    sector = (app.get("sector") or (app.get("borrower") or {}).get("sector") or "").strip().lower()
    out: list[dict] = []

    def add(rule_ref: str, dtype: str, expected, actual, severity: str, summary: str):
        out.append({"deviation_id": f"DEV-{_natural_key(rule_ref, actual)}",
                    "rule_ref": rule_ref, "type": dtype,
                    "expected": str(expected), "actual": str(actual),
                    "severity": severity, "summary": summary,
                    "required_authority": _authority_for(severity), "status": "open",
                    "natural_key": _natural_key(rule_ref, actual)})

    # tenor
    tenor_max = rules.get("tenor_months_max")
    if tenor_max and max_tenor > int(tenor_max):
        major = rules.get("tenor_months_major")
        sev = "major" if (major and max_tenor > int(major)) else "minor"
        add("tenor_months_max", "tenor", f"≤ {tenor_max} months", f"{max_tenor} months", sev,
            f"Tenor of {max_tenor} months exceeds the policy maximum of {tenor_max} months")
    # amount
    amt_max = rules.get("amount_cr_max")
    if amt_max and amount > float(amt_max):
        add("amount_cr_max", "exposure", f"≤ ₹{amt_max:,.0f} Cr", f"₹{amount:,.2f} Cr", "major",
            f"Proposed amount ₹{amount:,.2f} Cr exceeds the policy maximum of ₹{amt_max:,.0f} Cr")
    # grade
    sig = rules.get("sub_investment_grade") or []
    if sig and grade and any(grade.upper().startswith(g.upper()) for g in sig):
        add("sub_investment_grade", "policy", f"investment grade (not in {', '.join(sig)})",
            f"{grade}", "major", f"Risk grade {grade} is sub-investment grade")
    # sector watch
    watch = rules.get("sector_watch") or []
    if watch and sector and any(w.lower() in sector for w in watch):
        add("sector_watch", "policy", f"not a watch sector ({', '.join(watch)})", sector, "minor",
            f"Sector '{sector}' is on the policy watch list")
    return out


def _authority_for(severity: str) -> str:
    return {"minor": "Committee with recorded minutes",
            "major": "Committee + reviewer concurrence with minutes",
            "critical": "Board-level approval with minutes"}.get(severity, "Committee with recorded minutes")


def merge(app: dict, detected: list[dict], by_name: str, at: str) -> list[dict]:
    """Fold the detected deviations into the application's `policy_deviation_items`
    (natural-key dedupe: an existing item with the same natural_key is kept, not duplicated)."""
    items = app.setdefault("policy_deviation_items", [])
    existing = {i.get("natural_key"): i for i in items}
    added = []
    for d in detected:
        if d["natural_key"] in existing:
            continue
        items.append({**d, "raised_by": by_name, "raised_at": at, "source": "policy_rule"})
        added.append(d)
    return added
