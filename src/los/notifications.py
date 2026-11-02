"""R19 — case notifications, derived from the application record.

`derive_notifications(app, now)` is a pure function: it reads the stored state
(assignments, rework, deferrals, SLA, conditions, covenants, modifications,
documents, sanctions, pending approvals) and the application's own event log
and returns the set of notifications that are true *now*. The service stores
the derived set plus the recorded-event notifications, so `notifications_for`
is stable between calls and acknowledgements persist.

Nothing is sent externally: this is the in-case bell and the audit record.
"""
from __future__ import annotations

from datetime import datetime, timedelta

PREFIX = "NTF-"
SLA_WARNING_DAYS = 1          # a step at SLA + this many days is "due soon / breached"


def _date(s):
    try:
        return datetime.fromisoformat(str(s)[:10]).date()
    except (ValueError, TypeError):
        return None


def derive_notifications(app: dict, now: datetime, events: list[dict] | None = None) -> list[dict]:
    """The notifications true for ``app`` at ``now`` (stable ids per item)."""
    out: list[dict] = []
    today = now.date()

    def add(kind: str, detail: str, *, severity: str = "info", ref: str = "",
            step: str = "", due: str = "", overdue: bool = False, at: str = now.isoformat(timespec="seconds")):
        out.append({"kind": kind, "detail": detail, "severity": severity, "ref": ref,
                    "step": step, "due": due, "overdue": overdue, "at": at})

    step_id = app.get("step_id")
    wf = None
    # ── assignment / rework / pending approval (from the event log) ────────
    for e in events or []:
        a = e.get("action")
        if a == "assign" or (e.get("to_step") and e.get("to_step") != e.get("from_step")
                             and a in ("submit", "approve", "sanction")):
            add("assigned", f"Assigned to {e.get('to_step') or ''}".strip(),
                ref=e.get("to_step") or "", step=e.get("to_step") or "", at=e.get("at") or "")
        elif a == "return":
            add("rework", f"Rework requested at {e.get('from_step') or ''}",
                severity="warning", step=e.get("from_step") or "", at=e.get("at") or "")
    # ── the current pending approval ───────────────────────────────────────
    if app.get("status") not in ("approved", "rejected", "withdrawn", "dropped") and step_id:
        add("pending_approval", f"Waiting at {step_id}", ref=step_id, step=step_id)
    # ── SLA: how long the case has sat on its current step ─────────────────
    entered = _date(app.get("step_entered_at"))
    if entered and app.get("status") not in ("deferred",) and step_id:
        age = (today - entered).days
        if age > 10:
            add("sla_breach", f"On {step_id} for {age} days", severity="warning",
                step=step_id, at=app.get("step_entered_at") or "")
    # ── deferrals: due / overdue ───────────────────────────────────────────
    for d in app.get("deferrals") or []:
        until = _date(d.get("until"))
        if until and d.get("reactivated_at") is None:
            if until < today:
                add("defer_due", f"Deferral overdue since {until.isoformat()}", severity="warning",
                    ref=d.get("at", ""), due=until.isoformat(), overdue=True, at=d.get("at") or "")
            else:
                add("defer_due", f"Deferral ends {until.isoformat()}", ref=d.get("at") or "",
                    due=until.isoformat(), at=d.get("at") or "")
    # ── conditions: open with a due date ───────────────────────────────────
    for c in app.get("conditions") or []:
        if c.get("status") in ("open", "partially_met", "in_progress"):
            due = _date(c.get("due_date"))
            if due:
                if due < today:
                    add("condition_due", f"{c.get('condition_id') or c.get('type')}: due {due.isoformat()} (overdue)",
                        severity="warning", ref=c.get("condition_id") or "", due=due.isoformat(), overdue=True)
                elif (due - today).days <= 14:
                    add("condition_due", f"{c.get('condition_id') or c.get('type')}: due {due.isoformat()}",
                        ref=c.get("condition_id") or "", due=due.isoformat())
    # ── covenants: breached / watch ────────────────────────────────────────
    for c in app.get("covenants") or []:
        latest = (c.get("monitoring") or [{}])[-1]
        if latest.get("status") == "breached" or c.get("status") == "breached":
            add("covenant_breach", (c.get("description") or c.get("covenant_id") or "")[:140],
                severity="critical", ref=c.get("covenant_id") or "",
                at=(latest.get("at") or "")[:10])
    # ── modifications open ─────────────────────────────────────────────────
    for m in app.get("modifications") or []:
        if m.get("status") == "open":
            add("modification_open", f"Modification {m.get('modification_id') or ''} is open",
                severity="warning", ref=m.get("modification_id") or "", at=m.get("at") or "")
    # ── documents: a version rejected / review needed ─────────────────────
    for d in app.get("documents") or []:
        if d.get("status") in ("rejected", "changes_requested"):
            add("document_rejected", f"{d.get('name')}: {d.get('status')}", severity="warning",
                ref=d.get("name") or "")
    # ── recorded events that notify by themselves ──────────────────────────
    for e in events or []:
        a = e.get("action")
        if a == "exception_rejected":
            add("exception_rejected", (e.get("comment") or "E&S exception rejected")[:140],
                severity="critical", at=e.get("at") or "")
        elif a == "check_expired":
            add("check_expired", (e.get("comment") or "A due-diligence check has expired")[:140],
                severity="warning", at=e.get("at") or "")
        elif a == "letter_validity" and e.get("detail", {}).get("expiring"):
            add("letter_expiry", "The sanction letter's validity is running out",
                severity="warning", at=e.get("at") or "")

    # stable ids + dedupe
    seen: set[str] = set()
    for i, n in enumerate(out):
        nid = f"{PREFIX}{n['kind']}:{n.get('ref') or n.get('step') or ''}:{n.get('due') or ''}:{n.get('at') or i}"
        if nid in seen:
            out[i] = None
        seen.add(nid)
    out = [n for n in out if n]
    for i, n in enumerate(out):
        n["id"] = f"{PREFIX}{i:03d}"
    return out


def merge(svc, app: dict) -> list[dict]:
    """Derive the notifications for the app and fold the stored acknowledgements back in."""
    events = svc.store.events(app["application_id"], limit=100000, asc=True)
    derived = derive_notifications(app, svc.now(), events)
    stored = app.get("notifications") or []
    acks = {n.get("id"): n for n in stored if n.get("acknowledged_by")}
    out = []
    for n in derived:
        prior = next((s for s in stored if s.get("kind") == n["kind"]
                      and (s.get("ref") or "") == (n.get("ref") or "")
                      and (s.get("step") or "") == (n.get("step") or "")), None)
        if prior:
            n["id"] = prior.get("id") or n["id"]
            if prior.get("acknowledged_by"):
                n["acknowledged_by"] = prior["acknowledged_by"]
                n["acknowledged_at"] = prior.get("acknowledged_at")
        out.append(n)
    app["notifications"] = out
    return out
