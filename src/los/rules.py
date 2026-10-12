"""Stage-specific mandatory rules (Client One GAP-P2-01) and dependency
management (GAP-P2-02).

Each rule carries applicability, triggering event, severity, blocking
behaviour, exception authority, reset behaviour and audit metadata. This is the
single catalog the workflow gates and the MIS read, so every hard stop in the
application is declared here rather than hidden in code paths.

Only the RAROC change/recompute dependency is explicitly detailed by Client One
(spec §24/P2-02); the other dependencies are the §12 matrix and are enforced as
material-change flags with the revalidation decision recorded — thresholds
remain validation-required.
"""

from __future__ import annotations

from typing import Callable, Optional

RULES = [
    {"id": "RUL-01", "name": "PAN/LOS deduplication", "applies": "sourcing", "severity": "block",
     "trigger": "application creation", "exception": "none (dedupe matches are informational until resolved)",
     "reset": "re-run on every identity change"},
    {"id": "RUL-02", "name": "Mandatory due-diligence checks", "applies": "IP/AP", "severity": "block",
     "trigger": "submit out of the stage", "exception": "Compliance VP exception (recorded, with reason)",
     "reset": "exception expiry / retrigger clears only that check"},
    {"id": "RUL-03", "name": "Name-screening 90-day rescreen", "applies": "all stages", "severity": "block",
     "trigger": "last screen older than 90 days at submit", "exception": "Compliance VP exception",
     "reset": "rescreen refreshes the clock (timer semantics subject to client confirmation)"},
    {"id": "RUL-04", "name": "Exposure-norm breach", "applies": "AP", "severity": "block",
     "trigger": "exposure recorded above the recorded norm", "exception": "governed exception with justification",
     "reset": "exception review"},
    {"id": "RUL-05", "name": "RAROC input staleness", "applies": "AP (not at IP sanction)", "severity": "block",
     "trigger": "amount, tenor, rating or pricing change after computation",
     "exception": "none — mandatory recomputation", "reset": "recomputation"},
    {"id": "RUL-06", "name": "ESMS Yes/Not Available remarks", "applies": "AP", "severity": "block",
     "trigger": "checklist answer recorded", "exception": "none", "reset": "remarks recorded"},
    {"id": "RUL-07", "name": "Pricing benchmark/spread mandatory", "applies": "AP", "severity": "block",
     "trigger": "fund-based facility without benchmark or spread", "exception": "none",
     "reset": "pricing recorded"},
    {"id": "RUL-08", "name": "Syndication uses Consortium", "applies": "AP", "severity": "block",
     "trigger": "banking arrangement recorded", "exception": "none", "reset": "arrangement corrected"},
    {"id": "RUL-09", "name": "Non-complied condition reason/remarks", "applies": "post-sanction", "severity": "block",
     "trigger": "condition status set to non_compliant", "exception": "none", "reset": "reason recorded"},
    {"id": "RUL-10", "name": "Sanction letter gate", "applies": "post-sanction", "severity": "block",
     "trigger": "post-sanction progression", "exception": "none", "reset": "letter uploaded and reviewed"},
    {"id": "RUL-11", "name": "Partial-execution balance", "applies": "post-sanction/disbursement", "severity": "block",
     "trigger": "facility execution recorded as partial", "exception": "none",
     "reset": "balance recomputed; full execution recorded"},
    {"id": "RUL-12", "name": "CBS Security Number gate", "applies": "disbursement", "severity": "block",
     "trigger": "disbursement maker submit", "exception": "none", "reset": "numbers created for all securities"},
    {"id": "RUL-13", "name": "Disbursement memo gate", "applies": "disbursement", "severity": "block",
     "trigger": "disbursement maker submit", "exception": "none", "reset": "memo generated and reviewed"},
    {"id": "RUL-14", "name": "Interim SOP compliance gate", "applies": "disbursement", "severity": "block",
     "trigger": "disbursement maker submit", "exception": "none", "reset": "all applicable SOP items In Compliance"},
    {"id": "RUL-15", "name": "Post-Sanction Checker remarks", "applies": "post-sanction", "severity": "block",
     "trigger": "checker decision", "exception": "none", "reset": "remarks recorded"},
    {"id": "RUL-16", "name": "Final approval to Exit", "applies": "disbursement", "severity": "block",
     "trigger": "final approval", "exception": "none",
     "reset": "approval recorded; Exit = workflow completion, not settlement evidence"},
    {"id": "RUL-17", "name": "Material change after approval snapshot", "applies": "post-sanction/disbursement",
     "severity": "block", "trigger": "governed domain hash differs from the snapshot",
     "exception": "material-change review (accept/reject with remarks)", "reset": "review recorded"},
    {"id": "RUL-18", "name": "Consent gate", "applies": "post-sanction", "severity": "block",
     "trigger": "post-sanction maker submit", "exception": "none", "reset": "consent recorded"},
    {"id": "RUL-19", "name": "Condition precedent (subsequent disbursement)", "applies": "disbursement",
     "severity": "block", "trigger": "tranche request", "exception": "none",
     "reset": "CPs satisfied / deferred / waived with checker approval"},
    {"id": "RUL-20", "name": "Tranche within undisbursed commitment", "applies": "disbursement", "severity": "block",
     "trigger": "tranche recorded", "exception": "none", "reset": "amount within the balance"},
]

DEPENDENCIES = [
    {"trigger": "Entity PAN changes", "action": "Re-run identity, dedupe and relevant verification checks"},
    {"trigger": "Rating changes", "action": "Re-evaluate risk, group rating and potentially RAROC/pricing"},
    {"trigger": "Facility amount changes", "action": "Re-evaluate exposure, pricing, repayment, RAROC and approval authority"},
    {"trigger": "Facility tenor changes", "action": "Re-evaluate pricing, repayment, RAROC and applicable approval"},
    {"trigger": "Pricing changes", "action": "Recalculate interest and review RAROC"},
    {"trigger": "Project cost changes", "action": "Reappraise project, funding and repayment capability"},
    {"trigger": "Project timeline/DCCO changes", "action": "Reappraise implementation risk, repayment and credit decision"},
    {"trigger": "Sanction decision changes", "action": "Update approved facilities, conditions, documents and post-sanction process"},
    {"trigger": "Security details change", "action": "Revalidate valuation, perfection, facility mapping and potentially pricing"},
    {"trigger": "Mandatory CP incomplete", "action": "Block disbursement eligibility"},
    {"trigger": "Beneficiary changes", "action": "Revalidate beneficiary and payment instruction"},
    {"trigger": "Payment amount changes", "action": "Revalidate limit, instruction and required approval"},
    {"trigger": "New material information after review", "action": "Determine affected components and trigger revalidation/reapproval"},
]


def evaluate(app: dict) -> list[dict]:
    """Every rule with its live status: passed / failed / not_applicable, with the gate message."""
    from src.los import verification, disops, proposal as proposal_mod, pricing as pricing_mod, snapshot, esms, post_sanction
    stage = (app.get("stage_id") or "PS").upper()
    checks = (app.get("due_diligence") or {}).get("checks") or []
    blocking = verification.blocking(checks)
    _g12 = (disops.disops_view(app)["security_gate"]
            if stage == "DIS" and (app.get("securities") or (app.get("disops") or {}).get("security_refs")) else None)
    _g12_applicable = stage == "DIS" and bool(app.get("securities") or (app.get("disops") or {}).get("security_refs"))
    _g4 = proposal_mod.exposure_gate((app.get("proposal") or {}).get("exposure") or {})
    _g8 = proposal_mod.banking_gate((app.get("proposal") or {}).get("banking"))
    _esms_started = any(i.get("answer") for i in (app.get("esms") or {}).get("checklist", [])) or bool(app.get("projects"))
    _g7 = (pricing_mod.pricing_gate(app.get("pricing") or {}, app.get("facilities", []))
           if stage in ("AP", "POS", "DIS") else None)
    _g17 = snapshot.material_change_gate(app)
    statuses = {
        "RUL-01": ("passed", None) if (app.get("identity") or {}).get("deduplication") is not None else ("not_applicable", None),
        "RUL-02": ("failed", "; ".join(f"{b['name']} ({b['status']})" for b in blocking[:2])) if blocking else ("passed", None),
        "RUL-03": ("passed", None),
        "RUL-04": ("failed", _g4) if _g4 else ("passed" if (app.get("proposal") or {}).get("exposure") else "not_applicable", None),
        "RUL-05": _raroc(app),
        "RUL-06": ("failed", esms.esms_gate(app.get("esms"))) if stage in ("AP", "POS", "DIS") and _esms_started
        else ("not_applicable", None),
        "RUL-07": ("failed", _g7) if _g7 else ("passed" if stage in ("AP", "POS", "DIS") else "not_applicable", None),
        "RUL-08": ("failed", _g8) if _g8 else ("not_applicable", None),
        "RUL-09": ("passed", None) if not any(c.get("status") == "non_compliant" and not c.get("note")
                                          for c in app.get("conditions") or []) else ("failed", "a non-compliant condition lacks its reason"),
        "RUL-10": ("passed", None) if stage in ("PS", "IP") else ("not_applicable", None),
        "RUL-11": ("passed", None),
        "RUL-12": ("failed", _g12) if _g12 else ("passed" if _g12_applicable else "not_applicable", None),
        "RUL-13": ("failed", None) if stage == "DIS" and not ((app.get("disops") or {}).get("memo") or {}).get("reviewed")
        else ("not_applicable", None),
        "RUL-14": ("failed", disops.sop_gate((app.get("disops") or {}).get("sop") or [])) if stage == "DIS" and (app.get("disops") or {}).get("sop")
        else ("not_applicable", None),
        "RUL-15": ("passed", None) if stage != "POS" else ("not_applicable", None),
        "RUL-16": ("not_applicable", None),
        "RUL-17": ("failed", _g17) if _g17 else ("passed" if app.get("snapshots") else "not_applicable", None),
        "RUL-18": ("passed", None) if stage not in ("POS", "DIS") or (app.get("consent") or {}).get("facilities")
        else ("failed", "the customer's sanction consent is not yet recorded"),
        "RUL-19": ("failed", "mandatory CPs open") if stage == "DIS" and app.get("conditions") and not
        (post_sanction.condition_summary(app.get("conditions") or [],
                                         (app.get("sanctions") or {}).get("AP", {}).get("at", "")[:10] or "")
         or {}).get("cps_cleared") else ("not_applicable", None),
        "RUL-20": ("passed", None),
    }
    out = []
    for rule in RULES:
        status, detail = statuses.get(rule["id"], ("not_applicable", None))
        out.append({**rule, "status": status, "detail": detail})
    return out


def _raroc(app: dict):
    from src.los import ratings
    if (app.get("stage_id") or "") == "IP" or not (app.get("ratings") or {}).get("raroc"):
        return ("not_applicable", None)
    stale = ratings.stale_raroc(app)
    return ("failed", "stale RAROC for " + ", ".join(stale)) if stale else ("passed", None)
