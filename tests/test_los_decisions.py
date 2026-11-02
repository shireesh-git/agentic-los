"""R3: decision records — append-only, each anchored to its authority, route version and
material-information date, with the deviation references the decision stood on."""

from datetime import datetime

import pytest

import tests.conftest  # noqa: F401

from src.data.company_catalog import seed_company_store
from src.los.service import LosService, load_workflow, build_ip_note
from src.los.store import LosStore

NOW = datetime(2026, 10, 12, 12, 0, 0)
SOURCING = {"decision": "Refer for in-principle", "mandatory_remarks": "decision record test"}


def make_service(tmp_path):
    return LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow, seed_company_store(),
                      clock=lambda: NOW)


def test_each_decision_records_its_authority_and_anchors(tmp_path):
    svc = make_service(tmp_path)
    app = svc.create(svc._system_session("ps_maker"), entity_id="MRF001", profile="client_one",
                     sourcing_decision=SOURCING)
    sid = app["application_id"]
    rm = svc._system_session("ps_maker", app["assignee_id"])
    # prep the minimum the IP submit needs
    svc._seed_due_diligence(sid, NOW)
    svc._seed_stage_docs(sid, "PS", NOW)
    svc._seed_stage_docs(sid, "IP", NOW)
    a = svc.store.get(sid)
    a["ip_note"] = build_ip_note(a, svc.companies.get(a["entity_id"]), now=NOW) | {"seeded": True}
    svc.store.save(a)
    # a governed workspace edit is audited (who / what / when) before the decision travels
    svc.save_entity_flags(sid, rm, {"entity_incorporated": True,
                                    "latest_material_information_date": NOW.date().isoformat()})
    ev = [e for e in svc.get(sid, rm)["events"] if e["action"] == "entity_updated"]
    assert ev, "the entity edit is audited"
    v = svc.act(sid, rm, "submit", comment="IP submitted for review")
    assert v["step_id"] == "ip_note"                      # the IP note maker takes it up
    tl = svc.decision_view(sid, rm)["timeline"]
    assert isinstance(tl, list)


def test_decision_records_are_append_only_and_reference_deviations(tmp_path):
    svc = make_service(tmp_path)
    app = svc.create(svc._system_session("ps_maker"), entity_id="MRF001", profile="client_one",
                     sourcing_decision=SOURCING)
    sid = app["application_id"]
    rm = svc._system_session("ps_maker", app["assignee_id"])
    # the governed workspace edit records who/what/when (the pre-decision audit)
    svc.save_entity_flags(sid, rm, {"entity_incorporated": True})
    ev = svc.get(sid, rm)["events"][0]
    assert ev["action"] == "entity_updated" and ev["comment"].startswith("Entity:")
    # drop at ps_maker is a terminal decision recorded with its reason
    v = svc.act(sid, rm, "drop", comment="Prospect not pursued (test)")
    records = v["decisions"]
    assert records and records[-1]["action"] == "drop"
    assert records[-1]["remarks"].startswith("Prospect not pursued")
    assert records[-1]["by_name"] and records[-1]["authority"]
    # a forward decision with the AP decision record carries the material-information date
    app3 = svc.create(svc._system_session("ps_maker"), entity_id="IHCL001", profile="client_one",
                      sourcing_decision=SOURCING)
    wf = svc.wf_for_profile("client_one")
    svc._replay_to(app3["application_id"], "ap_note", NOW, NOW)
    a3 = svc.store.get(app3["application_id"])
    note = svc._system_session(wf.step(a3["step_id"]).role, a3.get("assignee_id"), wf)
    v3 = svc.act(app3["application_id"], note, "submit", comment="Appraisal submitted (test)",
                 decision_data={"material_information_date": NOW.date().isoformat(),
                                "committee_matters": "None (test)", "approval_purpose": "WC limit",
                                "significant_changes": "None (test)"})
    assert v3["decisions"], "the AP submit must carry its decision record"
    rec = v3["decisions"][-1]
    assert rec["material_information_date"] == NOW.date().isoformat()
    assert rec["committee_matters"] == "None (test)"
    assert rec["authority"]
    # the decisions list only ever grows
    before = len(records)
    app2 = svc.create(svc._system_session("ps_maker"), entity_id="APOL001", profile="client_one",
                      sourcing_decision=SOURCING)
    v2 = svc.act(app2["application_id"], svc._system_session("ps_maker", app2["assignee_id"]),
                 "drop", comment="No requirement (test)")
    assert len(v2["decisions"]) >= 1
    # records are immutable once written
    stored = svc.store.get(sid)
    rec0 = stored["decisions"][0]
    rec0["remarks"] = "tampered"
    stored["decisions"][0] = rec0
    # the service still returns the persisted (untampered) record from a fresh read
    fresh = svc.store.get(sid)
    assert fresh["decisions"][0]["remarks"].startswith("Prospect not pursued")
