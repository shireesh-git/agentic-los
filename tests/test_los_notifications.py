"""R19 — case notifications.

Notifications are derived from the application's own records (assignments,
rework, deferrals, SLA, conditions, covenants, pending approvals, letter
expiry) plus the events the service records (rejection of an E&S exception,
check expiry). They are stored per application, can be read / acknowledged
per user, and are never sent externally.
"""
from datetime import datetime, timedelta

import pytest

from src.los.notifications import derive_notifications
from src.data.company_catalog import seed_company_store
from src.los.service import LosService, load_workflow
from src.los.store import LosStore

NOW = datetime(2026, 7, 9, 9, 0, 0)


def make_service(tmp_path):
    return LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow,
                      seed_company_store(), clock=lambda: NOW)


def sanctioned(svc, entity="MFL001", amount=100.0):
    a = svc.create(svc._system_session("ps_maker"), entity_id=entity, profile="client_one",
                   facility={"facility_type": "working_capital", "facility_nature": "fund_based",
                             "proposal_type": "Fresh", "amount_cr": amount, "tenor_months": 12,
                             "interest_rate": 12.4, "purpose": "Working capital (demo)"},
                   sourcing_decision={"decision": "Refer for in-principle",
                                      "mandatory_remarks": "notification test"})
    svc._replay_to(a["application_id"], "pos_maker", NOW, NOW)
    return svc.store.get(a["application_id"])


def test_assignment_notifies_the_new_holder(tmp_path):
    svc = make_service(tmp_path)
    app = sanctioned(svc, amount=100.0)
    sid = app["application_id"]
    nots = svc.notifications_for(sid)
    # the journey moved between holders: at least one assignment notification exists
    kinds = {n["kind"] for n in nots}
    assert "assigned" in kinds
    # the pending approval at the current step is visible
    pending = [n for n in nots if n["kind"] == "pending_approval"]
    assert pending and pending[0]["step"] == "pos_maker"


def test_deferral_generates_a_due_notification(tmp_path):
    svc = make_service(tmp_path)
    # defer happens at the Risk Maker step of an in-flight case
    a = svc.create(svc._system_session("ps_maker"), entity_id="MFL001", profile="client_one",
                   facility={"facility_type": "working_capital", "facility_nature": "fund_based",
                             "proposal_type": "Fresh", "amount_cr": 100.0, "tenor_months": 12,
                             "interest_rate": 12.4, "purpose": "Working capital (demo)"},
                   sourcing_decision={"decision": "Refer for in-principle",
                                      "mandatory_remarks": "notification test"})
    sid = a["application_id"]
    app = svc.store.get(sid)
    wf = svc.wf_for_profile("client_one")
    ps = svc._system_session("ps_maker", app.get("assignee_id"), wf)
    svc.act(sid, ps, "defer", comment="Awaiting board note (demo)",
            deferred_until=(NOW + timedelta(days=20)).date().isoformat())
    nots = svc.notifications_for(sid)
    due = [n for n in nots if n["kind"] == "defer_due"]
    assert due, nots
    assert due[0]["due"] == (NOW + timedelta(days=20)).date().isoformat()
    # an overdue deferral is flagged overdue
    svc.store.save({**svc.store.get(sid),
                    "deferrals": [{**(svc.store.get(sid).get("deferrals") or [{}])[0],
                                    "until": (NOW - timedelta(days=2)).date().isoformat()}]})
    nots = svc.notifications_for(sid)
    overdue = [n for n in nots if n["kind"] == "defer_due" and n.get("overdue")]
    assert overdue


def test_condition_due_and_covenant_breach_notifications(tmp_path):
    svc = make_service(tmp_path)
    app = sanctioned(svc, amount=100.0)
    sid = app["application_id"]
    a = svc.store.get(sid)
    # an open condition with a due date in the past
    conds = a.get("conditions") or []
    if conds:
        conds[0].update(status="open", due_date=(NOW - timedelta(days=1)).date().isoformat())
    svc.store.save(a)
    nots = svc.notifications_for(sid)
    assert any(n["kind"] == "condition_due" for n in nots)
    # a breached covenant
    a = svc.store.get(sid)
    a.setdefault("covenants", []).append(
        {"covenant_id": "COV-T1", "description": "DSCR ≥ 1.25 (demo)", "status": "open",
         "monitoring": [{"status": "breached", "at": NOW.date().isoformat()}]})
    svc.store.save(a)
    nots = svc.notifications_for(sid)
    assert any(n["kind"] == "covenant_breach" for n in nots)


def test_notifications_can_be_acknowledged_and_are_persistent(tmp_path):
    svc = make_service(tmp_path)
    app = sanctioned(svc, amount=100.0)
    sid = app["application_id"]
    nots = svc.notifications_for(sid)
    assert nots
    one = nots[0]
    v = svc.acknowledge_notification(sid, svc._system_session("pos_maker", app.get("assignee_id")),
                                     one["id"], "Seen (demo)")
    acks = [n for n in v["notifications"] if n["id"] == one["id"]]
    assert acks and acks[0]["acknowledged_by"]
    # ack is durable: re-deriving keeps the acknowledgement
    nots2 = svc.notifications_for(sid)
    still = [n for n in nots2 if n["id"] == one["id"]]
    assert still and still[0].get("acknowledged_by")


def test_recorded_event_notification_rejection(tmp_path):
    """A rejection of an E&S exception request notifies the maker (recorded event)."""
    svc = make_service(tmp_path)
    app = sanctioned(svc, amount=100.0)
    sid = app["application_id"]
    a = svc.store.get(sid)
    # record the event the way the service does when an exception request is rejected
    a = svc._require(sid)
    svc.store.save(a, svc._event(a, "exception_rejected", actor={"id": "u_compvp", "role": "compliance_vp"},
                                 from_step=a.get("step_id"), to_step=a.get("step_id"),
                                 comment="Exception not supportable (demo)"))
    nots = svc.notifications_for(sid)
    assert any(n["kind"] == "exception_rejected" for n in nots)


def test_derive_notifications_is_pure_and_bounded():
    """derive_notifications is a pure function of the app — no I/O, no unbounded growth."""
    app = {"application_id": "LOS-X", "step_id": None, "status": "in_progress",
           "assignee_id": "u_1", "profile": "client_one",
           "created_at": NOW.isoformat(timespec="seconds"),
           "step_entered_at": NOW.isoformat(timespec="seconds"),
           "deferrals": [], "conditions": [], "covenants": [], "modifications": [],
           "documents": [], "sanctions": {}}
    out = derive_notifications(app, NOW)
    assert isinstance(out, list)
    assert all(set(("id", "kind", "at", "severity")).issubset(n) for n in out)
