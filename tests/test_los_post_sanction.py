"""LOS Phase 5: conditions tracker, deviation register, disbursement checklist + tranche, IP → AP comparison."""

from datetime import datetime, timedelta

import pytest

from src.application.errors import ForbiddenError, InvalidRequestError
from src.data.company_catalog import seed_company_store
from src.los.post_sanction import STANDARD_CPS, build_comparison, build_conditions, condition_summary
from src.los.service import LosService, load_workflow
from src.los.store import LosStore
from tests.test_cam_composer import full_case
from tests.test_los_committee import BriefingFinalCam
from tests.test_los_risk_maker import FakeCases

NOW = datetime(2026, 10, 8, 12, 0, 0)


@pytest.fixture(scope="module")
def abce_case():
    return full_case(seed_company_store()["ABCE001"])


@pytest.fixture()
def svc(tmp_path, abce_case):
    cases = FakeCases(abce_case)
    cases.run("ABCE001", on_progress=lambda e: None)             # a credit case exists for ABCE
    service = LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow, seed_company_store(), clock=lambda: NOW,
                         cases=cases, final_cam=BriefingFinalCam(cases))
    service.seed_demo()
    return service


def _app(svc, entity):
    return next(a for a in svc.list() if a["entity_id"] == entity)


def _holder(svc, app_id):
    app = svc.get(app_id)
    return svc.sign_in(app["assignee_id"], app["step"]["role"])


def _abce_to(svc, target):
    app_id = _app(svc, "ABCE001")["application_id"]
    # walk from ip_risk_maker with the default holders (the seed helper records the assessment at Risk Maker steps)
    app = svc.store.get(app_id)
    start = svc.wf.step(app["step_id"]).index
    for _ in range(svc.wf.step(target).index - start):
        app = svc.store.get(app_id)
        step = svc.wf.step(app["step_id"])
        session = svc._system_session(step.role, app.get("assignee_id"))
        if step.id in ("ip_risk_maker", "ap_risk_maker"):
            app["credit_assessment"] = svc._seed_assessment_summary(app)
            svc.store.save(app)
        if step.id == "ap_risk_maker":
            # the AP submission gates: CMA recorded + pricing benchmark/spread (RUL-07)
            svc._seed_ap_workspace(app_id, svc.now() - timedelta(days=1))
        if step.id == "pos_maker":
            break
        action = {"maker": "submit", "checker": "approve", "committee": "sanction", "vp_review": "submit",
                  "allocation": "allocate"}[step.kind]
        svc.act(app_id, session, action, allocate_to=svc._default_assignee(step.allocates_to)
                if step.kind == "allocation" else None,
                sanctioned_amount_cr=(200 if step.id == "ap_sanction" else None),
                comment="Committee accepts ₹200 Cr with escrow." if step.id == "ap_sanction" else "")
    return app_id


# ─── Conditions ─────────────────────────────────────────────────────────────

def test_conditions_come_from_the_reassessment_plus_standard_documentation(abce_case):
    rows = build_conditions(abce_case, NOW)
    derived = [r for r in rows if r["provenance"] == "derived"]
    assert len([r for r in derived if r["type"] == "CP"]) == 7 and len([r for r in derived if r["type"] == "CS"]) == 5
    assert [r["text"] for r in rows if r["provenance"] == "template" and r["type"] == "CP"] == STANDARD_CPS
    assert all(r["due"] == "2027-01-06" for r in rows if r["type"] == "CS")           # sanction + 90 days
    assert build_conditions(None, NOW)[0]["provenance"] == "template"                 # no credit case: template only


def _consent_all(svc, app_id, maker):
    """Record the customer's sanction consent with every facility executed (gates the pos_maker submission)."""
    app = svc.store.get(app_id)
    return svc.record_consent(app_id, maker, acknowledged_by="Customer authorisation (test)",
                              consent_date=NOW.date().isoformat(),
                              facilities=[{"facility_id": f["facility_id"], "execution_status": "executed",
                                           "agreement_date": NOW.date().isoformat()}
                                          for f in (app.get("facilities") or [app.get("facility") or {}])])


def _issue_letter(svc, app_id, maker):
    """The Post-Sanction Maker issues the Sanction Letter (RUL-10 hard gate)."""
    return svc.generate_letter(app_id, maker, "sanction_letter")


def test_final_sanction_creates_the_tracker_and_a_pos_maker_must_clear_cps(svc):
    app_id = _abce_to(svc, "pos_maker")
    app = svc.get(app_id)
    assert app["step"]["id"] == "pos_maker" and app["sanctions"]["AP"]["sanctioned_cr"] == 200.0
    ps = svc.post_sanction(app_id, _holder(svc, app_id))
    assert ps["condition_summary"]["cp_total"] == 11 and ps["can_update_conditions"]
    maker = _holder(svc, app_id)
    _issue_letter(svc, app_id, maker)
    with pytest.raises(InvalidRequestError, match="sanction consent"):
        svc.act(app_id, maker, "submit")
    _consent_all(svc, app_id, maker)
    with pytest.raises(InvalidRequestError, match="condition precedent"):
        svc.act(app_id, maker, "submit")


def test_condition_updates_need_evidence_reasons_and_valid_dates(svc):
    app_id = _abce_to(svc, "pos_maker")
    maker = _holder(svc, app_id)
    with pytest.raises(InvalidRequestError, match="evidence or a note"):
        svc.update_conditions(app_id, maker, [{"id": "CP-01", "status": "satisfied"}])
    with pytest.raises(InvalidRequestError, match="reason"):
        svc.update_conditions(app_id, maker, [{"id": "CP-02", "status": "waived"}])
    with pytest.raises(InvalidRequestError, match="after today"):
        svc.update_conditions(app_id, maker, [{"id": "CP-03", "status": "deferred", "note": "x", "due": "2026-01-01"}])
    out = svc.update_conditions(app_id, maker, [
        {"id": "CP-01", "status": "satisfied", "evidence": "legal/escrow_agreement.pdf"},
        {"id": "CP-02", "status": "waived", "note": "Promoter guarantee in place"},
        {"id": "CP-03", "status": "deferred", "note": "Registry backlog", "due": "2026-11-30"}])
    cps = {c["id"]: c for c in out["conditions"]}
    assert cps["CP-01"]["status"] == "satisfied" and cps["CP-03"]["due"] == "2026-11-30"
    assert out["condition_summary"]["pending_approval"] == 2
    cats = [d["category"] for d in out["deviations"]]
    assert cats.count("Condition") == 2 and "Pending checker approval" in [d["status"] for d in out["deviations"]]
    assert svc.get(app_id)["events"][0]["action"] == "conditions_update"
    with pytest.raises(ForbiddenError):
        svc.update_conditions(app_id, svc.sign_in("u_rm1", "ps_maker"), [{"id": "CP-04", "status": "satisfied",
                                                                        "note": "x"}])


def _clear_cps(svc, app_id, maker):
    cps = [c for c in svc.post_sanction(app_id, maker)["conditions"] if c["type"] in ("CP", "CPS") and c["status"] == "open"]
    svc.update_conditions(app_id, maker, [{"id": c["id"], "status": "satisfied", "note": "Verified original"} for c in cps])


def _complete_disops(svc, app_id, maker):
    """Complete the seeded PNCR001 disbursement record: the two open SOP items and the memo review (RUL-13/14)."""
    svc.update_disops(app_id, maker, "sop", {"items": [
        {"id": "sop_treasury", "status": "in_compliance", "remarks": "Treasury coordinated the release"},
        {"id": "sop_legal", "status": "in_compliance", "remarks": "Legal verification complete"}]})
    svc.review_memo(app_id, maker, True, "Memo consistent with the operational record")


def _review(svc, app_id, session, stage):
    """Tick every read-only review checklist item of the checker / final approver (GAP-P0-16)."""
    app = svc.store.get(app_id)
    key = "checker_review" if stage == "checker" else "final_review"
    items = (app.get("disops") or {}).get(key) or []
    if not items:
        svc.update_dis_review(app_id, session, stage, [])          # initialise the checklist
        app = svc.store.get(app_id)
        items = (app.get("disops") or {}).get(key) or []
    svc.update_dis_review(app_id, session, stage, [i["id"] for i in items if not i.get("done")])


def test_checker_approval_approves_waivers_and_moves_to_disbursement(svc):
    app_id = _abce_to(svc, "pos_maker")
    maker = _holder(svc, app_id)
    _issue_letter(svc, app_id, maker)
    svc.update_conditions(app_id, maker, [{"id": "CP-02", "status": "waived", "note": "Promoter guarantee in place"}])
    _clear_cps(svc, app_id, maker)
    _consent_all(svc, app_id, maker)
    svc.act(app_id, maker, "submit")
    checker = _holder(svc, app_id)
    with pytest.raises(InvalidRequestError, match="mandatory"):
        svc.act(app_id, checker, "approve")
    v = svc.act(app_id, checker, "approve", comment="Post-sanction documentation verified")
    assert v["step"]["id"] == "dis_maker"
    ps = svc.post_sanction(app_id)
    waived = next(c for c in ps["conditions"] if c["id"] == "CP-02")
    assert waived["approval"]["by_name"] == checker["user"]["name"]
    assert next(d for d in ps["deviations"] if d["category"] == "Condition")["status"] == "Approved"


def test_open_cs_past_due_is_overdue():
    rows = build_conditions(None, NOW - timedelta(days=120))
    s = condition_summary(rows, NOW.date().isoformat())
    assert s["cs_overdue"] == 4 and s["cps_cleared"] is False     # 2 covenants + financial + non-financial


# ─── Deviations & IP → AP ───────────────────────────────────────────────────

def test_deviation_register_collects_policy_and_sanction_deviations(svc):
    app_id = _abce_to(svc, "pos_maker")
    devs = svc.post_sanction(app_id)["deviations"]
    cats = {d["category"] for d in devs}
    assert {"Policy", "Sanction", "IP → AP"} <= cats
    ap = next(d for d in devs if d["description"].startswith("Final sanction differs from the reassessed"))
    assert "₹200.00 Cr" in ap["detail"] and "escrow" in ap["detail"]


def test_ip_to_ap_comparison_highlights_changes(svc):
    app_id = _abce_to(svc, "pos_maker")
    cmp = svc.post_sanction(app_id)["comparison"]
    rows = {r["label"]: r for r in cmp["rows"]}
    assert rows["Sanctioned amount"]["ip"] == "₹185.00 Cr" and rows["Sanctioned amount"]["ap"] == "₹200.00 Cr"
    assert rows["Sanctioned amount"]["changed"] and not rows["Amount requested"]["changed"]
    assert "same credit run" in cmp["note"]                                  # IP and AP used the same run here


def test_comparison_needs_an_ip_sanction():
    assert build_comparison({"sanctions": {}})["available"] is False


# ─── Disbursement ───────────────────────────────────────────────────────────

def test_disbursement_needs_a_checklist_and_a_tranche_within_limit(svc):
    pncr = _app(svc, "PNCR001")
    app_id = pncr["application_id"]
    maker = _holder(svc, app_id)
    ps = svc.post_sanction(app_id, maker)
    dis = ps["disbursement"]
    assert dis["visible"] and dis["can_edit"] and dis["available_cr"] == dis["sanctioned_cr"]
    assert {i["id"]: i["done"] for i in dis["checklist"]}["cps_cleared"] is True          # seeded history
    _complete_disops(svc, app_id, maker)                                            # memo + SOP gate (RUL-13/14)
    with pytest.raises(InvalidRequestError, match="Record the disbursement tranche"):
        svc.act(app_id, maker, "submit")
    with pytest.raises(InvalidRequestError, match="within the undisbursed limit"):
        svc.request_tranche(app_id, maker, dis["sanctioned_cr"] + 1, "2026-10-10")
    svc.request_tranche(app_id, maker, 100, "2026-10-10", "First tranche — project capex")
    with pytest.raises(InvalidRequestError, match="checklist incomplete"):
        svc.act(app_id, maker, "submit")
    with pytest.raises(InvalidRequestError, match="checked by the system"):
        svc.update_checklist(app_id, maker, [{"id": "cps_cleared", "done": True}])
    manual = [i["id"] for i in dis["checklist"] if i["kind"] == "manual"]
    out = svc.update_checklist(app_id, maker, [{"id": i, "done": True} for i in manual])
    assert out["disbursement"]["complete"]
    svc.act(app_id, maker, "submit")
    checker = _holder(svc, app_id)
    _review(svc, app_id, checker, "checker")
    svc.act(app_id, checker, "approve")                                              # checker verifies the tranche
    svc.act(app_id, _holder(svc, app_id), "submit")                                  # Disbursement VP review endorses
    approver = _holder(svc, app_id)
    _review(svc, app_id, approver, "final")
    v = svc.act(app_id, approver, "approve")                                         # final approver releases
    assert v["status"] == "APPROVED"
    final = svc.post_sanction(app_id)["disbursement"]
    assert final["tranches"][0]["status"] == "approved" and final["disbursed_cr"] == 100.0
    assert final["available_cr"] == round(dis["sanctioned_cr"] - 100, 2)
    assert final["complete"]                                   # the disbursed tranche keeps its limit check


def test_returned_tranche_goes_back_to_requested(svc):
    app_id = _app(svc, "PNCR001")["application_id"]
    maker = _holder(svc, app_id)
    _complete_disops(svc, app_id, maker)
    svc.request_tranche(app_id, maker, 50, "2026-10-10")
    manual = [i["id"] for i in svc.post_sanction(app_id)["disbursement"]["checklist"] if i["kind"] == "manual"]
    svc.update_checklist(app_id, maker, [{"id": i, "done": True} for i in manual])
    svc.act(app_id, maker, "submit")
    checker = _holder(svc, app_id)
    _review(svc, app_id, checker, "checker")
    svc.act(app_id, checker, "approve")                                               # checker verifies the tranche
    assert svc.post_sanction(app_id)["disbursement"]["tranches"][0]["status"] == "verified"
    # The Disbursement VP Review reworks it (read-only gate: submit or return with a comment).
    with pytest.raises(InvalidRequestError, match="not available"):
        svc.act(app_id, _holder(svc, app_id), "reject", comment="no")
    svc.act(app_id, _holder(svc, app_id), "return", comment="Value date falls on a holiday")
    assert svc.post_sanction(app_id)["disbursement"]["tranches"][0]["status"] == "requested"
    assert svc.get(app_id)["step"]["id"] == "dis_maker"                                   # back to the maker


def test_api_post_sanction_endpoints():
    from fastapi.testclient import TestClient

    from src.api.app import create_app
    from src.application.container import build_container
    container = build_container()
    container.los.seed_demo(force=True)
    http = TestClient(create_app(container))
    token = http.post("/api/los/session", json={"user_id": "u_posm", "role": "pos_maker"}).json()["token"]
    h = {"X-LOS-Session": token}
    infy = next(a for a in http.get("/api/los/applications?q=INFY", headers=h).json()["applications"])
    base = f"/api/los/applications/{infy['application_id']}"
    ps = http.get(base + "/post-sanction", headers=h).json()
    assert ps["visible"] and ps["condition_summary"]["cp_total"] >= len(STANDARD_CPS)
    cp = next(c for c in ps["conditions"] if c["type"] == "CP")
    r = http.post(base + "/conditions", headers=h, json={"updates": [{"id": cp["id"], "status": "satisfied",
                                                                       "note": "Original verified"}]})
    assert r.status_code == 200
    assert http.post(base + "/disbursement/tranche", headers=h,
                     json={"amount_cr": 10, "value_date": "2026-10-10"}).status_code == 409
