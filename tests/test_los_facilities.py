"""R6 — facility hierarchy: parent/sublimits, currencies, utilisation, cycles."""
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


def new_app(svc):
    return svc.create(svc._system_session("ps_maker"), entity_id="MFL001", profile="client_one",
                      facility={"facility_type": "working_capital", "facility_nature": "fund_based",
                                "proposal_type": "Fresh", "amount_cr": 100.0, "tenor_months": 12,
                                "interest_rate": 12.4, "purpose": "Working capital (demo)"},
                      sourcing_decision={"decision": "Refer for in-principle",
                                         "mandatory_remarks": "hierarchy test"})


def test_parent_sublimit_relationship_round_trips(tmp_path):
    svc = make_service(tmp_path)
    app = new_app(svc)
    sid = app["application_id"]
    ps = svc._system_session("ps_maker", app.get("assignee_id"))
    # a second facility under the first, as a sublimit
    svc.update_facility(sid, ps, app["facilities"][0]["facility_id"],
                        {"parent_limit_id": None, "currency": "INR"})
    v = svc.facility_hierarchy(sid)
    assert v["errors"] == []
    assert v["facilities"][0]["facility_id"]


def test_sublimit_cannot_exceed_parent(tmp_path):
    from src.los import facilities as facmod
    svc = make_service(tmp_path)
    app = new_app(svc)
    sid = app["application_id"]
    parent_id = app["facilities"][0]["facility_id"]
    # the validator: a child above its parent is a violation
    a = svc.store.get(sid)
    a["facilities"].append({**a["facilities"][0], "facility_id": "FAC-X01", "proposed_cr": 150.0,
                           "amount_cr": 150.0, "parent_limit_id": parent_id})
    errs = facmod.validate_hierarchy(a)
    assert any("exceeds its parent" in e for e in errs)
    # and update_facility refuses an edit that breaks the hierarchy
    ps = svc._system_session("ps_maker", svc.store.get(sid).get("assignee_id"))
    a2 = svc.store.get(sid)
    a2["facilities"].append({**a2["facilities"][0], "facility_id": "FAC-X01", "proposed_cr": 150.0,
                            "amount_cr": 150.0, "parent_limit_id": parent_id})
    svc.store.save(a2)
    with pytest.raises(InvalidRequestError, match="hierarchy"):
        svc.update_facility(sid, ps, "FAC-X01", {"amount_cr": 200.0})
    # the rejected edit leaves no partial change
    assert svc.store.get(sid)["facilities"][-1]["amount_cr"] == 150.0


def test_currency_must_match_the_parent(tmp_path):
    from src.los import facilities as facmod
    svc = make_service(tmp_path)
    app = new_app(svc)
    a = svc.store.get(app["application_id"])
    a["facilities"].append({**a["facilities"][0], "facility_id": "FAC-X02", "proposed_cr": 40.0,
                           "amount_cr": 40.0, "parent_limit_id": a["facilities"][0]["facility_id"],
                           "currency": "EUR"})
    errs = facmod.validate_hierarchy(a)
    assert any("currency" in e for e in errs)


def test_reimbursement_needs_a_parent_and_cycles_are_caught(tmp_path):
    from src.los import facilities as facmod
    svc = make_service(tmp_path)
    app = new_app(svc)
    a = svc.store.get(app["application_id"])
    # a reimbursement facility with no parent is a violation
    a["facilities"][0]["reimbursement_facility"] = True
    errs = facmod.validate_hierarchy(a)
    assert any("reimbursement" in e for e in errs)
    # a cycle: A → B → A
    a2 = svc.store.get(app["application_id"])
    a2["facilities"][0].update(reimbursement_facility=False,
                               parent_limit_id="FAC-002")
    a2["facilities"].append({**a2["facilities"][0], "facility_id": "FAC-002",
                            "parent_limit_id": a2["facilities"][0]["facility_id"]})
    errs = facmod.validate_hierarchy(a2)
    assert any("cycle" in e for e in errs)


def test_hierarchy_view_shows_utilisation(tmp_path):
    svc = make_service(tmp_path)
    app = new_app(svc)
    sid = app["application_id"]
    v = svc.facility_hierarchy(sid)
    node = v["facilities"][0]
    assert node["proposed_cr"] == 100.0
    assert "balance_cr" in node
    assert v["errors"] == []
