"""
Post sanction and disbursement (LOS Phase 5).

  conditions      the sanctioned conditions precedent (CP) and subsequent (CS):
                  from the credit reassessment (M6) where a credit case exists, plus
                  the bank's standard documentation conditions (labelled template).
                  Each is satisfied (with evidence), deferred (new due date) or
                  waived; deferrals and waivers are deviations the checker approves.
  deviations      one register: policy exceptions accepted at sanction, sanctions that
                  differ from the recommendation or the request, IP → AP changes and
                  condition waivers / deferrals, each with its approving authority.
  disbursement    a checklist (automatic checks + manual confirmations) and the
                  tranche, which may not exceed the undisbursed sanctioned limit.
  ip_vs_ap        what changed between the in-principle and the final sanction.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from src.engines.cam_composer import fmt

CS_DUE_DAYS = 90
CONDITION_STEPS = ("pos_maker", "dis_maker")          # where conditions are updated
CONDITION_STATUSES = ("open", "satisfied", "deferred", "waived", "non_compliant")

# Condition taxonomy (GAP-P0-14): pre-commitment, pre-disbursement, post-disbursement,
# conditions precedent to subsequent disbursement, financial/non-financial covenants,
# general and facility-specific conditions.
CONDITION_CATEGORIES = ("PC", "CP", "PD", "CPS", "FC", "NC", "GC", "FS")
MONITORING_FREQUENCIES = ("once", "quarterly", "half_yearly", "annual", "event_driven")

# Bank-standard documentation conditions (templates, not borrower-specific analysis).
STANDARD_CPS = [
    "Execution of the facility agreement and security documents in the bank's approved format",
    "Creation and perfection of security, with the charge registered with ROC and CERSAI",
    "Board resolution authorising the borrowing and the execution of documents",
    "Insurance of the charged assets with the bank's clause, for the full value",
]
STANDARD_CPS_SUBSEQUENT = [
    "No default outstanding on any existing facility at the time of a subsequent drawdown",
    "Updated annual financials and end-use certificate for the amount disbursed",
]
STANDARD_CSS = [
    "End-use certificate from the statutory auditor for the amount disbursed",
    "Audited financial statements within 180 days of each financial year-end",
]

# Disbursement checklist: automatic checks first, then manual confirmations.
CHECKLIST = [
    ("cps_cleared", "All conditions precedent satisfied, deferred or waived", "auto"),
    ("pos_approved", "Post-sanction documentation approved by the checker", "auto"),
    ("tranche_within_limit", "Tranche within the undisbursed sanctioned limit", "auto"),
    ("security_executed", "Security documents executed and stamped", "manual"),
    ("charge_registered", "Charge registered with ROC / CERSAI (registry not connected — confirm manually)", "manual"),
    ("limit_setup", "Limit set up in core banking (simulated — not connected)", "manual"),
    ("request_received", "Disbursement request and end-use undertaking received from the borrower", "manual"),
    ("insurance_assigned", "Insurance policy assigned in the bank's favour", "manual"),
]
MANUAL_ITEMS = {i for i, _, k in CHECKLIST if k == "manual"}


# ─── Conditions ─────────────────────────────────────────────────────────────

def build_conditions(case: Optional[dict], sanctioned_at: datetime) -> list[dict]:
    rea = (case or {}).get("reassessment") or {}
    due_cs = (sanctioned_at + timedelta(days=CS_DUE_DAYS)).date().isoformat()
    rows: list[tuple[str, str, str, str]] = []
    for x in rea.get("conditions_precedent") or []:
        rows.append(("CP", x["item"], "Credit reassessment (M6)", "derived"))
    for x in rea.get("conditions_subsequent") or []:
        rows.append(("FC" if x.get("type") == "financial" else "CS", x["item"], "Credit reassessment (M6)", "derived"))
    rows += [("CPS", t, "Bank standard documentation", "template") for t in STANDARD_CPS_SUBSEQUENT]
    rows += [("CP", t, "Bank standard documentation", "template") for t in STANDARD_CPS]
    rows += [("FC", "Maintain the financial covenants listed in Annexure III at the stipulated values",
              "Bank standard documentation", "template")]
    rows += [("NC", "Compliance with applicable regulations and reporting obligations",
              "Bank standard documentation", "template")]
    rows += [("CS", t, "Bank standard documentation", "template") for t in STANDARD_CSS]
    out, n = [], {"CP": 0, "PD": 0, "CPS": 0, "FC": 0, "NC": 0, "CS": 0, "PC": 0, "GC": 0, "FS": 0}
    for kind, text, source, prov in rows:
        n[kind] += 1
        out.append({"id": f"{kind}-{n[kind]:02d}", "type": kind,
                    "category": {"PC": "Pre-commitment condition", "CP": "Pre-disbursement condition",
                                 "PD": "Post-disbursement condition", "CPS": "Condition precedent to subsequent disbursement",
                                 "FC": "Financial covenant (Annexure III)", "NC": "Non-financial covenant",
                                 "CS": "Post-sanction covenant (subsequent)",
                                 "GC": "General condition", "FS": "Facility-specific condition"}[kind],
                    "text": text, "source": source, "provenance": prov,
                    "existing": False, "facility_id": None, "party": None, "stipulated_value": None,
                    "frequency": "once" if kind in ("CP", "CPS") else ("annual" if kind in ("FC", "CS") else "event_driven"),
                    "status": "open", "due": due_cs if kind in ("PD", "CS", "FC", "NC") else None,
                    "note": None, "evidence": None,
                    "approval": None, "updated_by": None, "updated_at": None, "history": []})
    return out


def condition_state(c: dict, today: str) -> str:
    """open / satisfied / deferred / waived, with open CS past their due date shown as overdue."""
    if c["status"] in ("open", "deferred") and c.get("due") and c["due"] < today:
        return "overdue"
    return c["status"]


# Recurring covenant monitoring (UAT-P2-11): FC/NC/CS/PD covenants are tested on their
# frequency; a failed test breaches the covenant (the condition goes non-compliant), a cure
# restores it, and untested covenants past their next due date raise a reminder.
FREQUENCY_INTERVALS_DAYS = {"once": None, "quarterly": 91, "half_yearly": 182, "annual": 365, "event_driven": None}
COVENANT_TYPES = ("FC", "NC", "CS", "PD")


def covenant_monitor(c: dict) -> dict:
    c.setdefault("monitoring", {"tests": [], "compliance": "untested", "next_due": None, "cure": None})
    return c["monitoring"]


def record_covenant_test(c: dict, at: str, result: str, by_name: str, remarks: str = "") -> dict:
    """Record a covenant test (pass/fail). A fail breaches the covenant; a pass after a
    breach is recorded as a cure. The next due date follows the covenant's frequency."""
    if result not in ("pass", "fail"):
        raise ValueError("A covenant test result must be pass or fail")
    mon = covenant_monitor(c)
    mon["tests"].append({"at": at, "result": result, "by_name": by_name, "remarks": (remarks or "").strip() or None})
    if result == "fail":
        mon["compliance"] = "breached"
        mon["cure"] = None
        c["status"] = "non_compliant"
    elif mon["compliance"] == "breached":
        mon["compliance"] = "cured"
        mon["cure"] = {"at": at, "by_name": by_name, "remarks": (remarks or "").strip() or None}
        c["status"] = "satisfied"
    else:
        mon["compliance"] = "compliant"
    interval = FREQUENCY_INTERVALS_DAYS.get(c.get("frequency"))
    mon["next_due"] = ((datetime.fromisoformat(at) + timedelta(days=interval)).date().isoformat()
                       if interval else None)
    return mon


def record_covenant_cure(c: dict, at: str, by_name: str, remarks: str = "") -> dict:
    """An explicit cure of a breached covenant (a passing test also cures)."""
    mon = covenant_monitor(c)
    if mon["compliance"] != "breached":
        raise ValueError("Only a breached covenant can be cured")
    mon["compliance"] = "cured"
    mon["cure"] = {"at": at, "by_name": by_name, "remarks": (remarks or "").strip() or None}
    mon["tests"].append({"at": at, "result": "cure", "by_name": by_name, "remarks": (remarks or "").strip() or None})
    c["status"] = "satisfied"
    return mon


def covenant_summary(conditions: list[dict], today: str) -> dict:
    """The monitoring view: per-covenant state, breaches, cures and due reminders."""
    rows = []
    for c in conditions:
        if c.get("type") not in COVENANT_TYPES:
            continue
        mon = c.get("monitoring") or {"tests": [], "compliance": "untested", "next_due": None, "cure": None}
        compliance = mon.get("compliance") or "untested"
        if compliance == "breached":
            state = "breached"
        elif mon.get("next_due") and mon["next_due"] < today and compliance in ("untested", "compliant"):
            state = "reminder_due"
        else:
            state = compliance
        rows.append({"id": c["id"], "type": c["type"], "text": c["text"],
                     "frequency": c.get("frequency"), "compliance": compliance, "state": state,
                     "last_tested": (mon["tests"][-1]["at"] if mon.get("tests") else None),
                     "next_due": mon.get("next_due"), "cure": mon.get("cure"),
                     "tests": len(mon.get("tests") or [])})
    return {"covenants": rows,
            "breached": [r["id"] for r in rows if r["state"] == "breached"],
            "reminders": [r["id"] for r in rows if r["state"] == "reminder_due"],
            "cured": [r["id"] for r in rows if r.get("cure")]}


def condition_summary(conditions: list[dict], today: str) -> dict:
    cps = [c for c in conditions if c["type"] in ("PC", "CP")]     # pre-commitment and pre-disbursement
    cps_sub = [c for c in conditions if c["type"] == "CPS"]
    css = [c for c in conditions if c["type"] in ("PD", "CS", "FC", "NC")]
    states = lambda rows: [condition_state(c, today) for c in rows]
    blocking = lambda rows: sum(1 for s in states(rows) if s in ("open", "non_compliant", "overdue"))
    return {"cp_total": len(cps), "cp_open": blocking(cps),
            "cps_total": len(cps_sub), "cps_open": blocking(cps_sub),
            "cs_total": len(css), "cs_open": blocking(css),
            "cs_overdue": states(css).count("overdue"),
            "pending_approval": sum(1 for c in conditions if c["status"] in ("deferred", "waived")
                                    and not (c.get("approval") or {}).get("by")),
            "cps_cleared": bool(cps) and not blocking(cps) and not blocking(cps_sub)}


# ─── Deviation register ─────────────────────────────────────────────────────

def build_deviations(app: dict, case: Optional[dict], committee_deviations: list[list]) -> list[dict]:
    sanctions = app.get("sanctions") or {}
    final = sanctions.get("AP") or sanctions.get("IP")
    authority = (f"{final['by_name']} ({'Committee sanction' if 'AP' in sanctions else 'IP Sanction Committee'}), "
                 f"{final['at'][:10]}") if final else None
    status = "Approved at sanction" if final else "For approval at sanction"
    rows = []

    def add(category, description, detail, auth, st, source):
        rows.append({"id": f"DV-{len(rows) + 1:02d}", "category": category, "description": description,
                     "detail": detail, "authority": auth, "status": st, "source": source})

    for d in committee_deviations:
        manual = "(manual)" in d[0]
        add("Manual" if manual else "Policy", d[0], f"{d[1]} — {d[2]}".strip(" —"), authority, status,
            "Raised at the IP / AP maker step" if manual else "Credit case (M2–M6)")
    for stage, s in sanctions.items():
        label = {"IP": "In-principle sanction", "AP": "Final sanction"}.get(stage, stage)
        auth = f"{s['by_name']}, {s['at'][:10]}"
        if s.get("deviates_from_recommendation"):
            add("Sanction", f"{label} differs from the reassessed recommendation",
                f"Sanctioned {fmt(s['sanctioned_cr'], 'cr')} vs recommended "
                f"{fmt(s['recommended_cr'], 'cr') if s.get('recommended_cr') else 'not supported'}"
                + (f" · minutes: {s['minutes']}" if s.get("minutes") else ""), auth, "Approved with minutes", "Sanction record")
        req = s.get("requested_cr")
        if req and s["sanctioned_cr"] < req - 1e-6:
            add("Sanction", f"{label} below the amount requested",
                f"Sanctioned {fmt(s['sanctioned_cr'], 'cr')} vs requested {fmt(req, 'cr')}", auth, "Recorded",
                "Sanction record")
    if "IP" in sanctions and "AP" in sanctions:
        ip, ap = sanctions["IP"], sanctions["AP"]
        if abs(ip["sanctioned_cr"] - ap["sanctioned_cr"]) > 1e-6:
            add("IP → AP", "Final sanction differs from the in-principle sanction",
                f"IP {fmt(ip['sanctioned_cr'], 'cr')} → AP {fmt(ap['sanctioned_cr'], 'cr')}",
                f"{ap['by_name']}, {ap['at'][:10]}", "Approved at sanction", "Sanction records")
    for c in app.get("conditions") or []:
        if c["status"] in ("deferred", "waived"):
            appr = c.get("approval") or {}
            add("Condition", f"{c['id']} {c['status']}: {c['text']}",
                (c.get("note") or "") + (f" · new due date {c['due']}" if c["status"] == "deferred" else ""),
                f"{appr['by_name']}, {appr['at'][:10]}" if appr.get("by") else "Post Sanction Checker",
                "Approved" if appr.get("by") else "Pending checker approval", "Conditions tracker")
    return rows


# ─── IP → AP comparison ─────────────────────────────────────────────────────

def build_comparison(app: dict) -> dict:
    sanctions = app.get("sanctions") or {}
    ip_s, ap_s = sanctions.get("IP"), sanctions.get("AP")
    if not ip_s:
        return {"available": False, "reason": "The in-principle sanction has not been recorded yet."}
    assessed = app.get("assessments") or {}
    ip_a, ap_a = assessed.get("IP") or {}, assessed.get("AP") or {}
    ip_f = ip_s.get("facility") or {}
    ap_f = (ap_s or {}).get("facility") or app.get("facility") or {}
    cr = lambda v: fmt(v, "cr") if v not in (None, "") else "—"
    txt = lambda v: str(v).replace("_", " ") if v not in (None, "") else "—"

    rows = [
        ("Proposal", "Amount requested", cr(ip_s.get("requested_cr")), cr((ap_s or {}).get("requested_cr") or app.get("amount_cr"))),
        ("Proposal", "Facility type", txt(ip_f.get("facility_type")), txt(ap_f.get("facility_type"))),
        ("Proposal", "Tenor (months)", txt(ip_f.get("tenor_months")), txt(ap_f.get("tenor_months"))),
        ("Proposal", "Purpose", txt(ip_f.get("purpose")), txt(ap_f.get("purpose"))),
        ("Assessment", "Credit run", txt((ip_a.get("run_id") or "")[:8]), txt((ap_a.get("run_id") or "")[:8])),
        ("Assessment", "Reassessed decision", txt(ip_a.get("decision_label")), txt(ap_a.get("decision_label"))),
        ("Assessment", "Recommended limit", cr(ip_a.get("recommended_cr")), cr(ap_a.get("recommended_cr"))),
        ("Assessment", "Risk grade", txt(ip_a.get("risk_grade")), txt(ap_a.get("risk_grade"))),
        ("Sanction", "Sanctioned amount", cr(ip_s.get("sanctioned_cr")), cr((ap_s or {}).get("sanctioned_cr"))),
        ("Sanction", "Sanctioned by", f"{ip_s['by_name']}, {ip_s['at'][:10]}",
         f"{ap_s['by_name']}, {ap_s['at'][:10]}" if ap_s else "—"),
    ]
    out = [{"group": g, "label": l, "ip": a, "ap": b, "changed": a != b and b != "—" and a != "—"} for g, l, a, b in rows]
    same_run = bool(ip_a.get("run_id")) and ip_a.get("run_id") == ap_a.get("run_id")
    return {"available": True, "final_sanctioned": bool(ap_s), "rows": out,
            "changes": sum(1 for r in out if r["changed"] and r["label"] != "Sanctioned by"),
            "note": ("The AP reassessment used the same credit run as the IP stage — no new information was "
                     "assessed." if same_run else None)}


# ─── Disbursement ───────────────────────────────────────────────────────────

def sanctioned_limit(app: dict) -> Optional[float]:
    s = (app.get("sanctions") or {}).get("AP") or (app.get("sanctions") or {}).get("IP")
    return s["sanctioned_cr"] if s else None


def build_disbursement(app: dict, cond_summary: dict, pos_approved: bool) -> dict:
    dis = app.get("disbursement") or {}
    limit = sanctioned_limit(app)
    tranches = dis.get("tranches") or []
    disbursed = sum(t["amount_cr"] for t in tranches if t["status"] in ("approved", "disbursed"))
    pending = next((t for t in tranches if t["status"] in ("requested", "verified")), None)
    available = round(limit - disbursed, 2) if limit is not None else None
    auto = {"cps_cleared": cond_summary.get("cps_cleared", False), "pos_approved": pos_approved,
            # a pending tranche is checked against the undisbursed limit; a disbursed one passed this check when recorded
            "tranche_within_limit": (pending["amount_cr"] <= available + 1e-6 if pending and available is not None
                                     else not pending and any(t["status"] in ("approved", "disbursed") for t in tranches))}
    manual = dis.get("checklist") or {}
    items = []
    for item_id, label, kind in CHECKLIST:
        if kind == "auto":
            items.append({"id": item_id, "label": label, "kind": kind, "done": auto[item_id], "by_name": "System",
                          "at": None, "note": None})
        else:
            m = manual.get(item_id) or {}
            items.append({"id": item_id, "label": label, "kind": kind, "done": bool(m.get("done")),
                          "by_name": m.get("by_name"), "at": m.get("at"), "note": m.get("note")})
    return {"sanctioned_cr": limit, "disbursed_cr": round(disbursed, 2), "available_cr": available,
            "tranches": tranches, "pending_tranche": pending, "checklist": items,
            "complete": all(i["done"] for i in items)}
