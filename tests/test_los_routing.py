"""R1 authority-driven workflow routing: the calculated authority controls the route."""

from datetime import datetime

import pytest

import tests.conftest  # noqa: F401

from src.data.company_catalog import seed_company_store
from src.los.service import LosService, load_workflow
from src.los.store import LosStore
from src.application.errors import ForbiddenError, InvalidRequestError

NOW = datetime(2026, 10, 12, 12, 0, 0)
SOURCING = {"decision": "Refer for in-principle", "mandatory_remarks": "routing test"}


@pytest.fixture(autouse=True)
def _restore_profile():
    """The routing tests switch the runtime-active profile; restore it for the other suites."""
    yield
    from src.los import profiles
    profiles._runtime_active = None


def make_service(tmp_path):
    return LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow, seed_company_store(),
                      clock=lambda: NOW)


def switch(svc, profile_id):
    svc.set_active_profile(svc._system_session("los_admin"), profile_id)


def new_app(svc, entity_id, profile, product=None, **kw):
    kw.setdefault("sourcing_decision", SOURCING)
    return svc.create(svc._system_session("ps_maker"), entity_id=entity_id, profile=profile,
                      product=product, **kw)


def prep_history(svc, sid):
    """Seed the governed workspaces the journey requires (DD, stage docs, AP workspace,
    material-information date) so a replay walk is not gated on them."""
    svc._seed_due_diligence(sid, NOW)
    for stage in ("PS", "IP", "AP"):
        svc._seed_stage_docs(sid, stage, NOW)
    svc._seed_ap_workspace(sid, NOW)
    app = svc.store.get(sid)
    app.setdefault("entity", {})["latest_material_information_date"] = NOW.date().isoformat()
    svc.store.save(app)
    # R9: governed institutions — the walks below cross the sanction committees, whose
    # decisions require the meeting record (attendance, minutes, approving vote); seed it
    # under the step's role, the way the replay walk seeds it
    if (svc._profile(svc.store.get(sid)).get("committee_governance") or {}).get("enabled"):
        wf = svc.wf_for_profile(svc.store.get(sid).get("profile"))
        svc._seed_committee_meeting(sid, svc._system_session("sanction_committee", None, wf), "ip_sanction", NOW)
        svc._seed_committee_meeting(sid, svc._system_session("sanction_committee", None, wf), "ap_sanction", NOW)

def walk(svc, sid, target):
    """Drive the case step by step to ``target`` with the step's own role, recording the
    decision fields each step needs (a real route, not a seed)."""
    from src.los.service import build_ip_note
    wf = svc.wf_for_profile(svc.store.get(sid).get("profile") or svc.active_profile())
    guard = 0
    while True:
        app = svc.store.get(sid)
        if app["step_id"] in (None, target):
            break
        step = wf.step(app["step_id"])
        session = svc._system_session(step.role, app.get("assignee_id"), wf)
        action = {"maker": "submit", "checker": "approve", "committee": "sanction",
                  "vp_review": "submit", "allocation": "allocate"}[step.kind]
        allocate_to = svc._default_assignee(step.allocates_to, wf) if step.kind == "allocation" else None
        if step.id == "ip_risk_maker":
            app["credit_assessment"] = svc._seed_assessment_summary(app)
            # a demo grade: the route follows the *recorded* assessment (650 Cr / A → with EVP note at IP)
            app["credit_assessment"]["risk_grade"] = "A"
            svc.store.save(app)
            svc._recompute_routing(app, {"id": "demo", "role": step.role},
                                   "route recalculated after the credit reassessment")
        if step.id == "ip_note" and not app.get("ip_note"):
            app["ip_note"] = build_ip_note(app, svc.companies.get(app["entity_id"]), now=NOW) | {"seeded": True}
            svc.store.save(app)
        if step.kind == "committee" and (svc._profile(app).get("committee_governance") or {}).get("enabled"):
            # R9: the governed committee's decision carries its meeting record (seeded, as the
            # replay walk does) — attendance, minutes, a fully approving vote
            svc._seed_committee_meeting(sid, session, step.id, NOW)
            app = svc.store.get(sid)
        esms_state = app.get("esms") or {}
        if step.kind in ("maker", "checker", "vp_review") and esms_state and not esms_state.get("category"):
            from src.los import esms as es
            esms_state = es.initial_esms(app) | esms_state
            esms_state["checklist"] = es.normalise_checklist(None, esms_state.get("checklist"))
            for item in esms_state["checklist"]:
                item["answer"] = "No"
                item["remarks"] = "Screened on the route walk (demo)"
                item["source"] = "Demo walk"
            esms_state.update(category="B", screening_date=NOW.date().isoformat(),
                              information_source="Demo walk", status="complete")
            app["esms"] = esms_state
            svc.store.save(app)
        if step.id == "ap_evp" and (app.get("esms") or {}).get("category"):
            # the E&S approval note is the gate into final review
            from src.los import docreg as dreg
            dreg.register_generated(app.setdefault("documents", []), name="ESMS Approval Note",
                                     kind="esms_approval_note", by_name="Demo walk", at=NOW.isoformat(timespec="seconds"))
            svc.store.save(app)
        decision_data = {f["id"]: (NOW.date().isoformat() if "date" in f["id"] else "Seeded (demo)")
                         for f in step.decision_fields if f.get("required")}
        # the concurrences the route requires at this committee, recorded by their own roles
        # before the decision (as in the real workflow: the note is signed, then the committee meets)
        app = svc.store.get(sid)
        for c in svc._concurrences_needed(app, step.id):
            role = svc.CONCURRENCE_ROLES[c["id"]]
            user = next((u["id"] for u in wf.users if u.get("role") == role), app.get("assignee_id"))
            svc.record_concurrence(sid, svc._system_session(role, user),
                                   {"concurrence_id": c["id"], "remarks": f"{c['label']} (demo)"})
        svc.act(sid, session, action, at=NOW, allocate_to=allocate_to,
                comment="Route-driven walk (demo)", decision_data=decision_data)
        guard += 1
        assert guard < 40, "route walk did not converge"
    return svc.get(sid, svc._system_session("los_admin"))


def test_route_recorded_with_basis_at_creation(tmp_path):
    svc = make_service(tmp_path)
    switch(svc, "dfi")
    app = new_app(svc, "SAPT001", "dfi", product="term_loan")
    route = app["routing"]
    assert route["profile"] == "dfi" and route["product"] == "term_loan"
    assert route["inputs"]["amount_cr"] == 120.0
    # the ES process is product-gated to project finance in the DFI profile → excluded with the basis
    excluded = {e["step"] for e in route["excluded"]}
    assert {"ap_es_maker", "ap_es_prep", "ap_es_review", "ap_es_recommend"} <= excluded
    basis = {e["step"]: e["basis"] for e in route["excluded"]}[ "ap_es_maker"]
    assert "term_loan" in basis
    # a decision step is always included
    assert any(i["step"] == "ap_sanction" for i in route["included"])
    # authority from the DFI matrix (120 ≤ 250 → base band)
    assert route["final_authority"]["required"] == "Project Sanctioning Committee"
    assert app["routing_history"][0]["note"] == "route calculated at creation"
    # client_one default behaviour: no gated steps → nothing excluded
    switch(svc, "client_one")
    app2 = new_app(svc, "MRF001", "client_one")
    assert app2["routing"]["excluded"] == []
    switch(svc, "dfi")


def test_route_skips_excluded_steps_in_the_journey(tmp_path):
    svc = make_service(tmp_path)
    switch(svc, "dfi")
    app = new_app(svc, "SAPT001", "dfi", product="term_loan")
    # walk the case forward through the ES window — the excluded ES steps must be skipped by the route
    prep_history(svc, app["application_id"])
    walk(svc, app["application_id"], "ap_dmd")
    events = svc.store.events(app["application_id"], limit=500)
    skipped = [e for e in events if e["action"] == "step_skipped"]
    assert {e["from_step"] for e in skipped} == {"ap_es_maker", "ap_es_prep", "ap_es_review", "ap_es_recommend"}
    assert all(e["detail"]["basis"] for e in skipped)
    # the PF case walks the ES steps normally
    pf = new_app(svc, "KAVG001", "dfi", product="project_finance")
    prep_history(svc, pf["application_id"])
    walk(svc, pf["application_id"], "ap_dmd")
    pf_events = svc.store.events(pf["application_id"], limit=500)
    assert not [e for e in pf_events if e["action"] == "step_skipped" and e["from_step"] == "ap_es_maker"]


def test_concurrence_gate_blocks_sanction_until_recorded(tmp_path):
    svc = make_service(tmp_path)
    switch(svc, "dfi")
    # 650 Cr → final band 'with MD note' → the executive_note concurrence is required at ap_sanction
    app = new_app(svc, "KAVG001", "dfi", product="project_finance")
    sid = app["application_id"]
    prep_history(svc, sid)
    walk(svc, sid, "ap_sanction")
    app = svc.get(sid, svc._system_session("los_admin"))
    ids = [c["id"] for c in app["routing"]["final_concurrences"]]
    assert "executive_note" in ids
    sc = svc._system_session("sanction_committee", app["assignee_id"])
    with pytest.raises(InvalidRequestError) as e:
        svc.act(sid, sc, "sanction", comment="minutes", sanctioned_amount_cr=650)
    assert "executive credit note" in str(e.value).lower() or "concurrence" in str(e.value).lower()
    # a non-DMD role cannot record the DMD concurrence
    with pytest.raises(ForbiddenError):
        svc.record_concurrence(sid, svc._system_session("crp_vp", "u_cvp"),
                               {"concurrence_id": "executive_note", "remarks": "x"})
    dmd = svc._system_session("dmd")
    svc.record_concurrence(sid, dmd, {"concurrence_id": "executive_note",
                                      "remarks": "MD concurred to the project sanction (demo)"})
    app = svc.get(sid, dmd)
    assert app["concurrences"][-1]["id"] == "executive_note"
    out = svc.act(sid, sc, "sanction", comment="minutes (demo)", sanctioned_amount_cr=650)
    assert out["step_id"] is None or out["stage_id"] == "POS"     # sanctioned, journey continues
    sc_evts = [e for e in svc.store.events(sid) if e["action"] == "sanction"]   # newest first
    assert sc_evts
    # the final sanction was recorded under the final authority (executive-note band)
    det = sc_evts[0]["detail"]["sanction"]["authority"]
    assert det["required"].startswith("Project Finance Committee with executive note")


def test_material_change_requires_reapproval(tmp_path):
    svc = make_service(tmp_path)
    switch(svc, "dfi")
    app = new_app(svc, "SAPT001", "dfi", product="term_loan")      # 120 Cr → base band
    sid = app["application_id"]
    prep_history(svc, sid)
    # a deviation recorded once the appraisal stage has started moves the *final* authority —
    # the route that will be the authority of record for the sanction must be reapproved
    walk(svc, sid, "ap_note")
    wf = svc.wf_for_profile("dfi")
    rm = svc._system_session(wf.step(app["step_id"]).role, app.get("assignee_id"))
    # record a policy deviation: the route recalculates and records the change
    svc.save_deviation(sid, rm, {"type": "tenor", "description": "tenor above policy for the sector",
                                 "justification": "concession asset profile (demo)"})
    app = svc.get(sid, rm)
    assert app["routing"]["material_change"] is True
    assert app["routing"]["reapproval_required"] is True
    evts = [e for e in svc.store.events(sid) if e["action"] == "route_changed"]
    assert evts and evts[-1]["detail"]["material"] is True
    # the sanction committee must acknowledge the changed route before the next sanction
    svc._replay_to(sid, "ap_sanction", NOW, NOW)
    app = svc.get(sid, svc._system_session("los_admin"))
    sc = svc._system_session("sanction_committee", app["assignee_id"])
    with pytest.raises(InvalidRequestError) as e:
        svc.act(sid, sc, "sanction", comment="minutes", sanctioned_amount_cr=120)
    assert "reapproval" in str(e.value).lower() or "material" in str(e.value).lower()
    svc.acknowledge_route(sid, sc, "Route change reviewed: deviation escalated per the DFI matrix (demo)")
    app = svc.get(sid, sc)
    assert app["routing"]["reapproval_required"] is False
    assert app["routing_ack"]["by_name"]
    svc.act(sid, sc, "sanction", comment="minutes after reapproval (demo)", sanctioned_amount_cr=120)
    # a non-material change (no authority move) does NOT flag reapproval
    app = svc.get(sid, sc)
    assert app["routing"]["reapproval_required"] is False
