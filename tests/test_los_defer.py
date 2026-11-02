"""R2: governed deferral — maximum period, mandatory reasons, overdue tracking, reactivation."""

from datetime import datetime, timedelta

import pytest

import tests.conftest  # noqa: F401

from src.application.errors import InvalidRequestError
from src.data.company_catalog import seed_company_store
from src.los.service import LosService, load_workflow
from src.los.store import LosStore

NOW = datetime(2026, 10, 12, 12, 0, 0)
SOURCING = {"decision": "Refer for in-principle", "mandatory_remarks": "defer test"}


def make_service(tmp_path, clock=NOW):
    return LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow, seed_company_store(),
                      clock=lambda: clock)


def new_app(svc):
    return svc.create(svc._system_session("ps_maker"), entity_id="MRF001", profile="client_one",
                      sourcing_decision=SOURCING)


def test_defer_requires_a_reason(tmp_path):
    svc = make_service(tmp_path)
    app = new_app(svc)
    rm = svc._system_session("ps_maker", app["assignee_id"])
    with pytest.raises(InvalidRequestError, match="comment is required to defer"):
        svc.act(app["application_id"], rm, "defer", deferred_until="2026-11-15")


def test_defer_cannot_exceed_the_institution_maximum(tmp_path):
    svc = make_service(tmp_path)
    app = new_app(svc)
    rm = svc._system_session("ps_maker", app["assignee_id"])
    # base profile: 180 days
    ok = (NOW.date() + timedelta(days=179)).isoformat()
    bad = (NOW.date() + timedelta(days=181)).isoformat()
    v = svc.act(app["application_id"], rm, "defer", comment="Awaiting audited accounts",
                deferred_until=ok)
    assert v["status"] == "DEFERRED" and v["deferral"]["until"] == ok
    assert v["deferral_days"] == 179
    # a fresh case deferred beyond the maximum — refused with the corrective message
    app2 = new_app(svc)
    rm2 = svc._system_session("ps_maker", app2["assignee_id"])
    with pytest.raises(InvalidRequestError, match="maximum period of 180"):
        svc.act(app2["application_id"], rm2, "defer", comment="extend", deferred_until=bad)


def test_reactivation_needs_a_reason_and_records_overdue(tmp_path):
    svc = make_service(tmp_path)
    app = new_app(svc)
    sid = app["application_id"]
    rm = svc._system_session("ps_maker", app["assignee_id"])
    svc.act(sid, rm, "defer", comment="Awaiting audited accounts", deferred_until="2026-10-13")
    # no reason — refused
    with pytest.raises(InvalidRequestError, match="comment is required to reactivate"):
        svc.act(sid, rm, "reactivate")
    # the clock moves past the deferral date: reactivation records how late it is
    late = NOW + timedelta(days=25)
    svc2 = make_service(tmp_path, clock=late)
    v = svc2.act(sid, rm, "reactivate", comment="Accounts received after the audit delay")
    assert v["status"] != "DEFERRED"
    d = v["deferrals"][-1]
    assert d["reactivated_by"] and d["reactivation_remarks"].startswith("Accounts received")
    assert d["reactivated_overdue_days"] == 24


def test_deferral_reminder_state_in_the_view(tmp_path):
    svc = make_service(tmp_path)
    app = new_app(svc)
    sid = app["application_id"]
    rm = svc._system_session("ps_maker", app["assignee_id"])
    svc.act(sid, rm, "defer", comment="Awaiting board calendar", deferred_until="2026-10-20")
    v = svc.get(sid, rm)
    assert v["deferral"]["until"] == "2026-10-20" and v["deferral_days"] == 8
    # past the date: the view shows the case as overdue for reactivation
    svc2 = make_service(tmp_path, clock=NOW + timedelta(days=12))
    v2 = svc2.get(sid, rm)
    assert v2["deferral_days"] == -4
