"""R4 — the full prospect-sourcing field set, governed.

The RM records the complete sourcing picture: the request currency, the
infrastructure-qualification flag, the lead source, the prospect status and a
sequence of dated discussions (participants, status, notes) with a next
follow-up. Dates validate; the profile's `prospect:` block extends the allowed
lead sources; records append (an application keeps its discussion history).
The data carries forward to the IP Note so the appraisal starts from it.
"""
from datetime import datetime

import pytest

from src.application.errors import InvalidRequestError
from src.data.company_catalog import seed_company_store
from src.los.service import LosService, load_workflow
from src.los.store import LosStore

NOW = datetime(2026, 7, 9, 9, 0, 0)


def make_service(tmp_path):
    return LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow,
                      seed_company_store(), clock=lambda: NOW)


def new_app(svc, currency="INR"):
    return svc.create(svc._system_session("ps_maker"), entity_id="MFL001", profile="client_one",
                      facility={"facility_type": "working_capital", "facility_nature": "fund_based",
                                "proposal_type": "Fresh", "amount_cr": 50.0, "tenor_months": 12,
                                "interest_rate": 12.4, "purpose": "Working capital (demo)",
                                "currency": currency},
                      sourcing_decision={"decision": "Refer for in-principle",
                                         "mandatory_remarks": "prospect test"})


def test_full_field_set_round_trips(tmp_path):
    svc = make_service(tmp_path)
    app = new_app(svc, currency="EUR")
    sid = app["application_id"]
    v = svc.update_prospect(svc._system_session("ps_maker", app.get("assignee_id")), sid, {
        "request_currency": "EUR",
        "infra_qualified": True,
        "lead_source": "referral",
        "prospect_status": "engaged",
        "next_follow_up": "2026-07-20",
    })
    p = v["prospect"]
    assert p["request_currency"] == "EUR"
    assert p["infra_qualified"] is True
    assert p["lead_source"] == "referral"
    assert p["prospect_status"] == "engaged"
    assert p["next_follow_up"] == "2026-07-20"


def test_discussions_append_with_validation(tmp_path):
    svc = make_service(tmp_path)
    app = new_app(svc)
    sid = app["application_id"]
    ps = svc._system_session("ps_maker", app.get("assignee_id"))
    v = svc.add_prospect_discussion(ps, sid, {
        "date": "2026-07-01", "participants": "RM, CFO (demo)",
        "status": "positive", "notes": "Discussed the expansion capex (demo)"})
    assert v["prospect"]["discussions"][0]["status"] == "positive"
    # a second record keeps the first
    v = svc.add_prospect_discussion(ps, sid, {
        "date": "2026-07-05", "participants": "RM, CFO, CA (demo)",
        "status": "hold", "notes": "Awaiting board approval (demo)"})
    ds = v["prospect"]["discussions"]
    assert len(ds) == 2 and ds[0]["date"] == "2026-07-01" and ds[1]["status"] == "hold"
    # future dates are refused
    with pytest.raises(InvalidRequestError, match="in the future"):
        svc.add_prospect_discussion(ps, sid, {"date": "2027-01-01", "notes": "x"})
    # a date is required
    with pytest.raises(InvalidRequestError, match="date"):
        svc.add_prospect_discussion(ps, sid, {"notes": "no date"})


def test_invalid_values_are_rejected(tmp_path):
    svc = make_service(tmp_path)
    app = new_app(svc)
    sid = app["application_id"]
    ps = svc._system_session("ps_maker", app.get("assignee_id"))
    with pytest.raises(InvalidRequestError):
        svc.update_prospect(ps, sid, {"lead_source": "not_a_source"})
    with pytest.raises(InvalidRequestError):
        svc.update_prospect(ps, sid, {"prospect_status": "not_a_status"})
    with pytest.raises(InvalidRequestError):
        svc.update_prospect(ps, sid, {"next_follow_up": "not-a-date"})
    # the record is unchanged after the failures
    assert (svc.store.get(sid).get("prospect") or {}).get("lead_source") in (None,)


def test_only_the_sourcing_maker_edits_prospect_fields(tmp_path):
    from src.application.errors import ForbiddenError
    svc = make_service(tmp_path)
    app = new_app(svc)
    sid = app["application_id"]
    other = svc._system_session("lpf_vp", "u_lpf")
    with pytest.raises(ForbiddenError):
        svc.update_prospect(other, sid, {"prospect_status": "engaged"})


def test_prospect_carries_forward_to_the_ip_note(tmp_path):
    svc = make_service(tmp_path)
    app = new_app(svc)
    sid = app["application_id"]
    ps = svc._system_session("ps_maker", app.get("assignee_id"))
    svc.update_prospect(ps, sid, {"request_currency": "USD", "infra_qualified": False,
                                  "lead_source": "walk_in", "prospect_status": "engaged",
                                  "next_follow_up": "2026-07-18"})
    # the IP Note view includes the sourcing/prospect picture
    a = svc.store.get(sid)
    assert (a.get("prospect") or {}).get("lead_source") == "walk_in"
    # it is present in the application view used by the IP stage
    view = svc.get(sid, ps)
    assert view.get("prospect", {}).get("lead_source") == "walk_in"
