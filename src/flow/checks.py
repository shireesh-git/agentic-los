"""Mandatory checks, brought forward to proposal initiation (fix list E2, E5).

The policy engine's hard rules decide pass / fail / not verified. Six of them depend on external data
(bureau, MCA, RBI / CIC lists, court records); this module

    precheck   runs those six as soon as a proposal is initiated (or the prospect's data agents finish), from
               the borrower's public-record data, or its demo file while the APIs are not connected, so a gap
               or a failure reaches the RM first instead of surfacing at Sanction
    from_engine the same checks (and the engine's other hard rules) from a CAM engine run
    view       each check in plain words: what it is, the result, where the answer came from, what evidence
               would clear it, and any verification or justification an officer recorded

Rule codes (HR_…) never reach the screen or the Copilot; ``plain`` gives the name to show.
"""

from __future__ import annotations

import re
from typing import Optional

# code → (short name, what passing means, evidence that decides it)
RULES = {
    "HR_WILFUL_DEFAULTER": ("Wilful defaulter check", "Not on the RBI / CIC wilful-defaulter list",
                            "Commercial bureau report, or a CIC wilful-defaulter list search"),
    "HR_COMPANY_ACTIVE": ("Company status (MCA)", "Company is Active in MCA records",
                          "MCA company master (MCA21 / Probe42)"),
    "HR_BUREAU_STATUS": ("Bureau status", "Not SMA-2 or worse with any lender",
                         "Commercial bureau report (CIBIL CMR / CRIF) or CRILC"),
    "HR_FRAUD_REGISTRY": ("Fraud registry check", "Not reported as fraud (RBI CFMC)",
                          "RBI CFMC fraud registry search"),
    "HR_RBI_DEFAULTER": ("RBI defaulter list check", "Not on the RBI defaulter list",
                         "RBI defaulter list search"),
    "HR_SUIT_FILED": ("Suits filed check", "Suits filed below 25% of total exposure",
                      "Suit-filed accounts and NCLT case search"),
    "HR_KYC_COMPLETE": ("KYC complete", "KYC pack on file", "PAN, certificate of incorporation, signatory KYC"),
    "HR_MIN_VINTAGE": ("Minimum vintage", "Company at least 3 years old", "Date of incorporation (MCA)"),
    "HR_NO_CRITICAL_EXCEPTIONS": ("No critical data exceptions", "No unresolved critical data exceptions",
                                  "Resolve the critical exceptions raised by the CAM engine"),
}
FIELD_PLAIN = {"dpd_status": "account status with other lenders (SMA / days past due)",
               "wilful_defaulter": "wilful-defaulter list result", "fraud_flag": "fraud registry result",
               "rbi_defaulter_list": "RBI defaulter list result", "suit_filed_amount_cr": "suits filed"}
DATA_CHECKS = ("HR_WILFUL_DEFAULTER", "HR_COMPANY_ACTIVE", "HR_BUREAU_STATUS", "HR_FRAUD_REGISTRY",
               "HR_RBI_DEFAULTER", "HR_SUIT_FILED")
STATUS = {"pass": "Clear", "fail": "Failed", "not_verified": "Not verified"}


def plain(code: Optional[str], fallback: str = "") -> str:
    return RULES.get(code or "", (None,))[0] or fallback or (code or "").replace("HR_", "").replace("_", " ").title()


def item(code: str, result: str, detail: str = "", demo: bool = False) -> dict:
    name, meaning, evidence = RULES.get(code, (plain(code), "", ""))
    detail = detail or ""
    source = ""
    if "(source: " in detail:
        detail, _, source = detail.partition(" (source: ")
        source = source.rstrip(")")
    # the engine's wording for missing evidence, in plain words
    missing = re.match(r"Bureau report does not state '(\w+)'", detail)
    if missing:
        detail = f"The data on record does not show the {FIELD_PLAIN.get(missing.group(1), missing.group(1))}"
    elif detail.startswith("No bureau report available"):
        detail = "No bureau report on record"
    elif detail.startswith("MCA company status not available"):
        detail = "No MCA company record on file"
    return {"code": code, "label": name, "meaning": meaning, "status": result, "status_label": STATUS.get(result, result),
            "detail": detail, "source": source, "demo": demo or "demo" in source.lower(), "evidence": evidence}


def precheck(company: dict, *, demo_enabled: bool) -> Optional[dict]:
    """The six data checks for a borrower, from its external data (or demo file). None when there is no
    borrower record to check."""
    from src.data import demo_registry
    from src.engines.policy_engine import tier1_hard_rules

    borrower, facility = company.get("borrower"), company.get("facility")
    if borrower is None or facility is None:
        return None
    ext = dict(company.get("external_data") or {})
    used_demo = False
    if demo_enabled:
        demo = demo_registry.external_data(getattr(borrower, "entity_id", None), getattr(borrower, "cin", None))
        for k, v in demo.items():
            if not (ext.get(k) or {}).get("payload"):
                ext[k] = v
                used_demo = True
    mca_env = ext.get("mca_data") or {}
    decisions = tier1_hard_rules(borrower, facility, [], ext.get("bureau_data") or {},
                                 mca_status=(mca_env.get("payload") or {}).get("status"),
                                 mca_demo=(mca_env.get("provenance") or {}).get("via") == "demo_file")
    items = [item(d.rule_code, d.result, d.details) for d in decisions if d.rule_code in DATA_CHECKS]
    return {"items": items, "basis": "initiation", "demo": used_demo or any(i["demo"] for i in items)}


def from_engine(engine: Optional[dict]) -> Optional[dict]:
    """The checks as the CAM engine decided them (all hard rules, data checks first)."""
    if not engine:
        return None
    rules = ((engine.get("fact_pack") or {}).get("policy_decisions") or {}).get("tier1_hard_rules") or []
    if not rules:
        return None
    items = [item(r.get("rule"), r.get("result"), r.get("details") or "") for r in rules]
    items.sort(key=lambda i: (i["code"] not in DATA_CHECKS, i["status"] == "pass"))
    return {"items": items, "basis": "cam_engine", "demo": any(i["demo"] for i in items)}


def view(checks: Optional[dict], notes: Optional[dict]) -> Optional[dict]:
    """Checks for the screen, with the notes officers recorded against open ones."""
    if not checks:
        return None
    notes = notes or {}
    items = []
    for i in checks.get("items") or []:
        n = notes.get(i["code"])
        items.append({**i, "note": n, "open": i["status"] != "pass" and not n})
    return {"items": items, "basis": checks.get("basis"), "demo": checks.get("demo"),
            "total": len(items), "clear": sum(1 for i in items if i["status"] == "pass"),
            "failed": [i for i in items if i["status"] == "fail"],
            "not_verified": [i for i in items if i["status"] == "not_verified"],
            "open": sum(1 for i in items if i["open"])}
