"""Corporate LOS (Phase 1): workflow definition, transitions, permissions, SLA, audit, demo seed and API."""

from datetime import datetime, timedelta

import pytest

from src.application.errors import ForbiddenError, InvalidRequestError
from src.data.company_catalog import seed_company_store
from src.los.service import DEMO_EXIT_ENTITY, DEMO_SEED, LosService, load_workflow
from src.los.store import LosStore
from src.los.workflow import Workflow, WorkflowError, sla_state, transition

NOW = datetime(2026, 10, 8, 12, 0, 0)


@pytest.fixture(scope="module")
def wf() -> Workflow:
    return load_workflow()


@pytest.fixture()
def svc(tmp_path):
    return LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow, seed_company_store(), clock=lambda: NOW)


def sign(svc, user, role):
    return svc.sign_in(user, role)

# UAT-P0-4: the sourcing decision is mandatory for every (non-seeded) creation.
DEC = {"decision": "Refer for in-principle", "mandatory_remarks": "Test — refer to in-principle"}


# ─── Workflow definition and transitions ────────────────────────────────────

def test_definition_matches_the_demo_lifecycle(wf):
    assert [s["id"] for s in wf.stages] == ["PS", "IP", "AP", "POS", "DIS"]
    assert len(wf.groups) == 5 and len(wf.roles) == 23 and len(wf.steps) == 31
    assert [s.id for s in wf.steps if s.stage_id == "PS"] == ["ps_maker"]
    assert [s.id for s in wf.steps if s.stage_id == "AP"] == [
        "ap_note", "ap_review", "ap_crp_vp", "ap_risk_maker", "ap_risk_review",
        "ap_post_rating", "ap_rating_vp", "ap_evp", "ap_recommend",
        "ap_es_maker", "ap_es_prep", "ap_es_review", "ap_es_recommend", "ap_dmd", "ap_sanction"]   # G-W2 / G-W3
    assert wf.step("ap_rating_vp").kind == "checker" and wf.step("ap_rating_vp").role == "crp_vp"
    assert (wf.step("ap_recommend").kind, wf.step("ap_recommend").role) == (
        "committee", "recommendations_committee")
    ip = [s.name for s in wf.steps if s.stage_id == "IP"]
    assert ip[0] == "IP Note Processing" and ip[-1] == "IP Sanction Committee" and "Risk Maker (Credit Assessment)" in ip
    assert ip.index("Post Rating VP Review") == ip.index("CRP VP Risk Review") + 1                 # G-W1
    assert wf.first_step.id == "ps_maker" and wf.steps[-1].id == "dis_approver"
    assert [s.id for s in wf.steps if s.stage_id == "DIS"] == ["dis_maker", "dis_checker", "dis_vp_review", "dis_approver"]


def test_disbursement_vp_review_is_a_submit_rework_gate(wf):
    vp = wf.step("dis_vp_review")
    assert (vp.role, vp.kind, vp.sla_days) == ("dis_vp", "vp_review", 1)
    assert wf.actions_for(vp) == ("submit", "return")
    fwd = transition(wf, vp, "submit", comment="endorsed")
    assert (fwd.step_id, fwd.status) == ("dis_approver", "UNDER_REVIEW")
    back = transition(wf, vp, "return", comment="rework")
    assert (back.step_id, back.status) == ("dis_maker", "RETURNED")      # back to the stage's maker
    with pytest.raises(WorkflowError, match="not available"):
        transition(wf, vp, "reject", comment="no")
    with pytest.raises(WorkflowError, match="comment is required"):
        transition(wf, vp, "return")


def test_definition_is_validated():
    with pytest.raises(WorkflowError):
        Workflow.from_config({})
    bad = {"roles": {"a": "A"}, "users": [{"id": "u", "roles": ["a"]}],
           "stages": [{"id": "S", "name": "S", "steps": [{"id": "x", "name": "X", "role": "b", "kind": "maker"}]}]}
    with pytest.raises(WorkflowError, match="unknown role"):
        Workflow.from_config(bad)


def test_transitions(wf):
    risk_review = wf.step("ip_risk_review")
    assert transition(wf, wf.step("ps_maker"), "submit", comment="ok").step_id == "ip_note"
    back = transition(wf, risk_review, "return", comment="rework")
    assert (back.step_id, back.status) == ("ip_risk_maker", "RETURNED")
    assert transition(wf, wf.step("ap_recommend"), "sanction", comment="ok").step_id == "ap_es_maker"
    assert transition(wf, wf.step("ap_dmd"), "approve", comment="ok").step_id == "ap_sanction"
    # rework routes: within the ES process to ES Preparation; DMD and the committee as before
    assert transition(wf, wf.step("ap_es_review"), "return", comment="x").step_id == "ap_es_prep"
    assert transition(wf, wf.step("ap_sanction"), "return", comment="x").step_id == "ap_post_rating"
    assert transition(wf, wf.step("ip_sanction"), "sanction", comment="ok").step_id == "ap_note"      # next stage
    done = transition(wf, wf.step("dis_approver"), "approve", comment="approved")
    assert done.step_id is None and done.status == "APPROVED"
    assert transition(wf, risk_review, "reject", comment="no").status == "REJECTED"
    with pytest.raises(WorkflowError, match="comment is required"):
        transition(wf, risk_review, "return")
    with pytest.raises(WorkflowError, match="not available"):
        transition(wf, wf.step("ps_maker"), "approve")
    with pytest.raises(WorkflowError, match="no further actions"):
        transition(wf, risk_review, "approve", current_status="REJECTED")


def test_allocation_requires_a_holder_of_the_next_role(wf):
    step = wf.step("ip_crp_vp")
    out = transition(wf, step, "allocate", allocate_to="u_ra2")
    assert (out.step_id, out.assign_user) == ("ip_risk_maker", "u_ra2")
    with pytest.raises(WorkflowError, match="does not hold"):
        transition(wf, step, "allocate", allocate_to="u_rm1")


def test_sla(wf):
    # UAT-P2-9: SLA is measured in working days (weekends + holidays excluded).
    step = wf.step("ip_risk_maker")                                   # 7-working-day SLA
    s = sla_state(NOW - timedelta(days=12), step, NOW)                 # entered Sat 26-Sep
    assert s["breached"] and s["days_remaining"] == -1.0               # due Wed 07-Oct 12:00
    assert not sla_state(NOW - timedelta(days=1), step, NOW)["breached"]


def test_sla_uses_working_days_and_holidays():
    from src.los.workflow import add_working_days, HOLIDAYS, is_working_day
    # Friday + 1 working day skips the weekend
    d = datetime(2026, 10, 16, 12, 0, 0)                               # a Friday
    assert add_working_days(d, 1) == datetime(2026, 10, 19, 12, 0, 0)  # Monday
    # 2026-10-20 is a listed holiday (demo calendar)
    assert "2026-10-20" in HOLIDAYS and not is_working_day(datetime(2026, 10, 20))
    assert add_working_days(datetime(2026, 10, 19, 12, 0, 0), 1) == datetime(2026, 10, 21, 12, 0, 0)


def test_sla_ageing_escalation(wf):
    step = wf.step("ip_risk_maker")
    # breached and aged beyond the 2-day threshold -> escalated
    s = sla_state(NOW - timedelta(days=14), step, NOW)
    assert s["breached"] and s["escalated"] and s["age_days"] == 2.0
    # a fresh breach (aged below the threshold) is breached but not yet escalated
    s2 = sla_state(NOW - timedelta(days=12), step, NOW)
    assert s2["breached"] and not s2["escalated"] and s2["age_days"] == 1.0


# ─── Service: create, act, permissions, audit ───────────────────────────────

def es_work(svc, app_id, session, step_id):
    """The Environmental & Social steps as their holders work them (G-W2): the CRP ES Maker completes the
    ESMS screen with the category; ES Preparation generates the ESMS Approval Note."""
    from src.los.esms import ES_CHECKLIST
    if step_id == "ap_es_maker":
        esms = svc.get(app_id).get("esms") or {}
        category = esms.get("category") or esms.get("proposed_category") or "C"
        svc.update_esms(app_id, session, {"screening_date": svc.now().date().isoformat(), "category": category,
                                          **({"esdd": "ESDD required (test)"} if category == "A" else {}),
                                          "checklist": [{"id": i, "answer": "No", "remarks": "Screened (test)"}
                                                        for i, _ in ES_CHECKLIST]})
    if step_id == "ap_es_prep":
        svc.generate_output(app_id, session, "esms_approval_note")


def _clear_dd(svc, app_id, rm):
    """Run the API checks, record the manual ones as clear and release any match with a Compliance VP exception."""
    svc.run_due_diligence(app_id, rm)
    compvp = sign(svc, "u_compvp", "compliance_vp")
    for _ in range(3):
        d = svc.due_diligence(app_id, rm)
        todo = [c["id"] for c in d["checks"] if c["mode"] == "manual" and c["status"] == "pending"]
        for cid in todo:
            svc.record_check(app_id, rm, cid, "clear", "Verified (test)")
        bad = [c["id"] for c in svc.due_diligence(app_id, rm)["checks"]
               if c["status"] in ("matched", "failed") and not c.get("exception")]
        for cid in bad:
            svc.exception_check(app_id, compvp, cid, "Exception approved (test)")
        if not svc.due_diligence(app_id, rm)["blocking"]:
            return d
    raise AssertionError("due diligence never became clear")


def test_maker_checker_flow_with_audit(svc):
    rm = sign(svc, "u_rm1", "ps_maker")
    app = svc.create(rm, entity_id="ABCE001", sourcing_decision=DEC)
    assert app["application_id"].startswith("LOS-2026-") and app["status"] == "DRAFT"
    assert app["amount_cr"] == 250.0 and app["facility"]["facility_type"] == "working_capital"
    with pytest.raises(InvalidRequestError, match="mandatory due-diligence"):
        svc.act(app["application_id"], rm, "submit", comment="application_id (test)")
    _clear_dd(svc, app["application_id"], rm)
    v = svc.act(app["application_id"], rm, "submit", comment="application_id (test)")
    assert (v["step"]["id"], v["assignee_id"]) == ("ip_note", "u_rm1")       # the sourcing RM keeps the IP Note
    rm2 = rm
    with pytest.raises(InvalidRequestError, match="not available"):
        svc.act(app["application_id"], rm2, "approve", comment="application_id (test)")
    svc.generate_ip_note(app["application_id"], rm2)
    svc._seed_stage_docs(app["application_id"], "IP", svc.now())        # the IP Note gate's documents
    v = svc.act(app["application_id"], rm2, "submit", comment="application_id (test)")
    assert (v["step"]["id"], v["status"], v["assignee_id"]) == ("ip_note_review", "UNDER_REVIEW", "u_lpf")
    vp = sign(svc, "u_lpf", "lpf_vp")
    assert svc.get(app["application_id"], vp)["actions"] == ["approve", "return", "reject", "recommend_modification", "drop"]
    v = svc.act(app["application_id"], vp, "return", comment="Add the group structure")
    assert (v["step"]["id"], v["status"], v["assignee_id"]) == ("ip_note", "RETURNED", "u_rm1")   # back to its maker
    assert [e["action"] for e in v["events"][:4]] == ["return", "submit", "ip_note", "submit"]
    assert {"dd_trigger", "dd_record", "dd_exception"} <= {e["action"] for e in v["events"]}
    assert v["events"][0]["comment"] == "Add the group structure" and v["events"][0]["actor_name"] == "Vivek Iyer"


def test_application_persists_multiple_facilities_and_related_parties(svc):
    rm = sign(svc, "u_rm1", "ps_maker")
    app = svc.create(
        rm,
        entity_id="ABCE001",
        facilities=[
            {"proposal_type": "Fresh", "facility_nature": "fund_based", "facility_type": "term_loan",
             "amount_cr": 100, "tenor_months": 60, "purpose": "Plant expansion"},
            {"proposal_type": "Fresh", "facility_nature": "non_fund_based", "facility_type": "bank_guarantee",
             "amount_cr": 25, "tenor_months": 24, "purpose": "Performance guarantee"},
        ],
        sourcing_decision=DEC,
        related_parties=[
            {"name": "ABC Holdings Limited", "role": "promoter", "party_type": "non_individual",
             "ownership_pct": 55, "pan": "ABCDE1234F"},
            {"name": "Asha Mehta", "role": "guarantor", "party_type": "individual"},
        ],
    )
    assert app["amount_cr"] == 125.0
    assert [f["facility_id"] for f in app["facilities"]] == ["FAC-001", "FAC-002"]
    assert app["facility"]["facility_type"] == "term_loan"       # backward-compatible primary facility
    assert [p["party_id"] for p in app["related_parties"]] == ["RP-001", "RP-002"]
    assert all(p["verification_status"] == "pending" for p in app["related_parties"])
    view = svc.get(app["application_id"], rm)
    assert len(view["facilities"]) == 2 and len(view["related_parties"]) == 2
    assert view["events"][0]["detail"]["total_amount_cr"] == 125.0


def test_multi_facility_and_related_party_validation(svc):
    rm = sign(svc, "u_rm1", "ps_maker")
    with pytest.raises(InvalidRequestError, match="proposed amount must be greater than zero"):
        svc.create(rm, entity_id="ABCE001", facilities=[{"facility_type": "term_loan", "amount_cr": 0}])
    with pytest.raises(InvalidRequestError, match="ownership must be between 0 and 100"):
        svc.create(rm, entity_id="ABCE001", facilities=[{"facility_type": "term_loan", "amount_cr": 10}],
                   related_parties=[{"name": "Invalid Owner", "role": "promoter", "ownership_pct": 101}])


def test_borrower_identity_and_deduplication(svc):
    svc.seed_demo()                                                    # there are existing applications to dedupe against
    ihcl = svc.borrower_identity("IHCL001")                           # existing (ETB) customer
    assert ihcl["ntb_etb"] == "ETB" and ihcl["customer_id"] == "CIF-IHCL001"
    assert ihcl["pan"] == "AAACT5678H" and ihcl["name_as_per_pan"] == "The Indian Hotels Company Limited"
    assert ihcl["cin"] and ihcl["date_of_incorporation"] == "1902-10-01" and ihcl["constitution"] == "listed"
    assert ihcl["cbs"]["status"] == "found" and "outstanding" in ihcl["cbs"]["detail"]
    assert [m["application_id"] for m in ihcl["los_duplicates"]["matches"]] == [a["application_id"]
                                                                               for a in svc.list() if a["entity_id"] == "IHCL001"]
    pn = svc.borrower_identity("PNCR001")                             # new-to-bank; GSTIN from the reference table
    assert pn["ntb_etb"] == "NTB" and pn["customer_id"] is None and pn["cbs"]["status"] == "not_found"
    assert pn["gstin"] == "09AABCP1234R1Z6" and pn["name_as_per_pan"] == "PNC Infratech Limited"
    mfl = svc.borrower_identity("MFL001")                             # NTB borrower
    assert mfl["ntb_etb"] == "NTB" and mfl["customer_id"] is None and mfl["cbs"]["status"] == "not_found"
    assert svc.get(next(a["application_id"] for a in svc.list() if a["entity_id"] == "MFL001"))[
        "customer_identity"]["ntb_etb"] == "NTB"


def test_new_application_stores_identity_and_prospect_discussion(svc):
    rm = sign(svc, "u_rm1", "ps_maker")
    app = svc.create(rm, entity_id="MFL001", sourcing_decision=DEC,
                     prospect_discussion={"project_type": "Corporate", "funding_type": "Term loan",
                                          "brief_description": "Fertiliser plant modernisation",
                                          "detailed_discussion": "RM discussed a 36-month term loan…",
                                          "initial_remarks": "Long-standing relationship; KYC current"})
    assert app["customer_identity"]["ntb_etb"] == "NTB" and app["customer_identity"]["pan"] == "AAACM1234A"
    assert app["customer_identity"]["cbs"]["status"] == "not_found" and not app["customer_identity"]["los_duplicates"]["matches"]
    assert app["prospect_discussion"]["project_type"] == "Corporate"
    assert app["prospect_discussion"]["initial_remarks"].endswith("KYC current")
    # A second application for the same customer is flagged as a potential duplicate (entity and PAN).
    app2 = svc.create(rm, entity_id="MFL001", sourcing_decision=DEC)
    matches = app2["customer_identity"]["los_duplicates"]["matches"]
    assert len(matches) == 1 and matches[0]["application_id"] == app["application_id"]
    assert set(matches[0]["matched_on"]) == {"same customer (entity)", "same PAN", "same CIN"}
    # The live view of the first application points at the second one.
    live = svc.get(app["application_id"])["customer_identity"]["los_duplicates"]["matches"]
    assert [m["application_id"] for m in live] == [app2["application_id"]]
    # The create audit event carries both snapshots.
    create_event = next(e for e in svc.get(app["application_id"])["events"] if e["action"] == "create")
    assert create_event["detail"]["prospect_discussion"]["project_type"] == "Corporate"
    assert create_event["detail"]["customer_identity"]["pan"] == "AAACM1234A"


def test_prospect_discussion_lengths_are_validated(svc):
    rm = sign(svc, "u_rm1", "ps_maker")
    with pytest.raises(InvalidRequestError, match="limited to 500 characters"):
        svc.create(rm, entity_id="MFL001", prospect_discussion={"brief_description": "x" * 501})
    app = svc.create(rm, entity_id="MFL001", sourcing_decision=DEC, prospect_discussion={})
    assert app["prospect_discussion"] == {"project_type": None, "funding_type": None, "brief_description": None,
                                          "detailed_discussion": None, "initial_remarks": None}


def test_assignee_guard_and_reassign(svc):
    rm1, rm2 = sign(svc, "u_rm1", "ps_maker"), sign(svc, "u_rm2", "ps_maker")
    app = svc.create(rm1, entity_id="APOL001", sourcing_decision=DEC)
    with pytest.raises(ForbiddenError, match="Assigned to Ananya Rao"):
        svc.act(app["application_id"], rm2, "submit", comment="application_id (test)")
    v = svc.reassign(app["application_id"], rm1, "u_rm2")
    assert v["assignee_id"] == "u_rm2" and v["events"][0]["action"] == "reassign"
    with pytest.raises(InvalidRequestError, match="does not hold"):
        svc.reassign(app["application_id"], rm1, "u_ra1")
    _clear_dd(svc, app["application_id"], rm2)
    assert svc.act(app["application_id"], rm2, "submit", comment="application_id (test)")["step"]["id"] == "ip_note"


def test_only_the_first_role_creates_and_roles_must_be_held(svc):
    with pytest.raises(ForbiddenError, match="can create applications"):
        svc.create(sign(svc, "u_ra1", "risk_analyst"), entity_id="ABCE001")
    with pytest.raises(ForbiddenError, match="does not hold the role"):
        svc.sign_in("u_ra1", "sanction_committee")
    s = sign(svc, "u_cvp", "crp_vp")
    assert svc.switch_role(s["token"], "risk_reviewer")["role"] == "risk_reviewer"
    with pytest.raises(ForbiddenError):
        svc.session("nope")


def test_reject_is_terminal_and_escalation_is_flagged(svc):
    rm = sign(svc, "u_rm1", "ps_maker")
    app = svc.create(rm, entity_id="MFL001", sourcing_decision=DEC)
    _clear_dd(svc, app["application_id"], rm)
    svc.act(app["application_id"], rm, "submit", comment="application_id (test)")
    rm2 = rm                                                             # the sourcing RM keeps the IP Note
    svc.generate_ip_note(app["application_id"], rm2)
    svc._seed_stage_docs(app["application_id"], "IP", svc.now())        # the IP Note gate's documents
    svc.act(app["application_id"], rm2, "submit", comment="application_id (test)")
    vp = sign(svc, "u_lpf", "lpf_vp")
    v = svc.escalate(app["application_id"], vp, "Large exposure")
    assert v["escalated"] is True
    v = svc.act(app["application_id"], vp, "reject", comment="Outside appetite")
    assert v["status"] == "REJECTED" and v["actions"] == []
    ip_stage = next(s for s in v["rail"] if s["id"] == "IP")
    assert ip_stage["steps"][1]["state"] == "rejected"
    with pytest.raises(Exception):
        svc.act(app["application_id"], vp, "approve", comment="application_id (test)")


def test_due_diligence_is_governed_and_the_vp_exception_is_the_only_release(svc):
    rm = sign(svc, "u_rm1", "ps_maker")
    app = svc.create(rm, entity_id="IHCL001", sourcing_decision=DEC)
    app_id = app["application_id"]
    d = svc.due_diligence(app_id, rm)
    assert len(d["checks"]) == 15 and d["can_edit"] is True
    assert any(c["id"] == "mlra" and c["mode"] == "manual" and c["mandatory"] for c in d["checks"])
    # Running only the API checks is not enough: the mandatory manual checks keep the gate closed.
    d = svc.run_due_diligence(app_id, rm)
    assert any(c["status"] == "pending" and c["mandatory"] for c in d["checks"])
    with pytest.raises(InvalidRequestError, match="mandatory due-diligence"):
        svc.act(app_id, rm, "submit", comment="submit (test)")
    # Name screening of IHCL matches a PEP record — a mandatory match.
    pep = next(c for c in svc.due_diligence(app_id, rm)["checks"] if c["id"] == "name_screening")
    assert pep["status"] == "matched" and pep["mandatory"]
    # An exception needs the Compliance VP and a reason.
    with pytest.raises(ForbiddenError, match="Compliance VP"):
        svc.exception_check(app_id, rm, "name_screening", "ignore it")
    compvp = sign(svc, "u_compvp", "compliance_vp")
    with pytest.raises(InvalidRequestError, match="reason"):
        svc.exception_check(app_id, compvp, "name_screening", "")
    svc.exception_check(app_id, compvp, "name_screening", "Verified against the MHA list — close associate, low risk")
    svc.record_check(app_id, rm, "mlra", "clear", "MLRA completed — low risk")
    _clear_dd(svc, app_id, rm)
    assert svc.due_diligence(app_id, rm)["blocking"] == []
    # Every outcome is in the check history (retrigger preserved) and the audit trail.
    svc.trigger_check(app_id, rm, "mca")
    mca = next(c for c in svc.due_diligence(app_id, rm)["checks"] if c["id"] == "mca")
    assert len(mca["history"]) >= 2
    actions = [e["action"] for e in svc.get(app_id)["events"]]
    assert "dd_trigger" in actions and "dd_record" in actions and "dd_exception" in actions


def test_sourcing_decision_and_customer_id_selection_are_stored(svc):
    rm = sign(svc, "u_rm1", "ps_maker")
    # UAT-P0-4: decision and the applicable remarks are mandatory; the Customer ID must match a
    # result from the available core-banking (demo data) search.
    with pytest.raises(InvalidRequestError, match="Sourcing decision must be one of"):
        svc.create(rm, entity_id="ABCE001", sourcing_decision={"decision": "Maybe"})
    with pytest.raises(InvalidRequestError, match="sourcing decision is required"):
        svc.create(rm, entity_id="ABCE001")
    with pytest.raises(InvalidRequestError, match="Mandatory remarks are required"):
        svc.create(rm, entity_id="ABCE001", sourcing_decision={"decision": "Refer for in-principle"})
    with pytest.raises(InvalidRequestError, match="conditional remarks"):
        svc.create(rm, entity_id="ABCE001",
                   sourcing_decision={"decision": "Defer", "mandatory_remarks": "see remarks"})
    # ABCE001 is new-to-bank: any existing-CIF selection is rejected (only 'new' is valid).
    with pytest.raises(InvalidRequestError, match="not among the available core-banking"):
        svc.create(rm, entity_id="ABCE001", sourcing_decision=DEC, customer_id_selection="CIF-99999")
    # IHCL001 is on the core-banking book (ETB): its CIF is the only selectable result.
    with pytest.raises(InvalidRequestError, match="not among the available core-banking"):
        svc.create(rm, entity_id="IHCL001", sourcing_decision=DEC, customer_id_selection="CIF-99999")
    app = svc.create(rm, entity_id="IHCL001",
                     sourcing_decision={"decision": "Refer for in-principle",
                                        "mandatory_remarks": "CIN verified against MCA",
                                        "conditional_remarks": "GST to be verified at onboarding"},
                     customer_id_selection="CIF-IHCL001")
    assert app["sourcing_decision"]["decision"] == "Refer for in-principle"
    assert app["sourcing_decision"]["customer_id_selection"] == "CIF-IHCL001"
    ident = svc.borrower_identity("IHCL001")
    assert {o["value"] for o in ident["customer_id_options"]} == {"CIF-IHCL001", "new"}
    assert ident["cin_status"] == "valid" and ident["gstin_status"] in ("valid", "missing")


# ─── Demo seed and dashboard ────────────────────────────────────────────────

def test_demo_seed_places_each_borrower_and_keeps_a_coherent_history(svc):
    assert svc.seed_demo() == len(DEMO_SEED) + 1 and svc.seed_demo() == 0       # stages + Exit showcase
    apps = {a["entity_id"]: a for a in svc.list()}
    for entity_id, target, flag, _, _, _ in DEMO_SEED:
        assert apps[entity_id]["step"]["id"] == target, entity_id
    assert apps["ABCE001"]["assignee_id"] in ("u_ra1", "u_ra2") and apps["ABCE001"]["status"] == "IN_PROGRESS"
    assert apps["MFL001"]["status"] == "RETURNED" and apps["PNCR001"]["escalated"] is True
    assert apps["IHCL001"]["status"] == "DRAFT"
    assert apps[DEMO_EXIT_ENTITY]["status"] == "APPROVED" and apps[DEMO_EXIT_ENTITY]["step"] is None
    for a in apps.values():
        events = list(reversed(svc.get(a["application_id"])["events"]))
        times = [e["at"] for e in events]
        assert times == sorted(times), a["entity_id"]                           # chronological
        assert events[0]["action"] == "create"
    d = svc.dashboard()["kpis"]
    # UAT-P2-9: SLA is now measured in working days (a longer span than calendar days), so the
    # seeded idle periods breach fewer steps; PNCR001 is deliberately left idle at dis_maker.
    assert d["total"] == 8 and d["sla_breached"] >= 1 and d["pending_committee"] == 1
    assert apps["PNCR001"]["sla"]["breached"]
    assert d["sanctioned_mtd"] + d["active"] >= 8


def test_my_queue_follows_the_active_role(svc):
    svc.seed_demo()
    committee = sign(svc, "u_cc", "sanction_committee")
    queue = svc.list(committee, mine=True)
    assert [a["entity_id"] for a in queue] == ["APOL001"] and queue[0]["actions"] == ["sanction", "return", "reject", "drop"]
    assert svc.dashboard(committee)["kpis"]["my_queue"] == 1


# ─── API ────────────────────────────────────────────────────────────────────

@pytest.fixture()
def http():
    from fastapi.testclient import TestClient

    from src.api.app import create_app
    from src.application.container import build_container
    container = build_container()
    container.los.seed_demo(force=True)
    return TestClient(create_app(container))


def test_api_end_to_end(http):
    assert http.get("/los").status_code == 200 and "losApp()" in http.get("/los").text
    directory = http.get("/api/los/directory").json()
    assert len(directory["groups"]) == 5 and "No password" not in directory["note"]
    assert http.get("/api/los/dashboard").status_code == 403                     # not signed in
    token = http.post("/api/los/session", json={"user_id": "u_rm1", "role": "ps_maker"}).json()["token"]
    h = {"X-LOS-Session": token}
    assert http.get("/api/los/dashboard", headers=h).json()["kpis"]["total"] == 8
    created = http.post("/api/los/applications", headers=h, json={"entity_id": "MFL001", "facility": {"amount_cr": 90},
        "sourcing_decision": {"decision": "Refer for in-principle", "mandatory_remarks": "e2e test — refer"}})
    app_id = created.json()["application_id"]
    assert created.json()["amount_cr"] == 90.0
    assert http.post(f"/api/los/applications/{app_id}/actions", headers=h, json={"action": "submit", "comment": "test"}).status_code == 400
    assert http.post(f"/api/los/applications/{app_id}/due-diligence/run", headers=h).status_code == 200
    d = http.get(f"/api/los/applications/{app_id}/due-diligence", headers=h).json()
    for c in d["checks"]:
        if c["mode"] == "manual":
            assert http.post(f"/api/los/applications/{app_id}/due-diligence/record", headers=h,
                             json={"check_id": c["id"], "result": "clear", "remarks": "ok"}).status_code == 200
    r = http.post(f"/api/los/applications/{app_id}/actions", headers=h, json={"action": "submit", "comment": "test"})
    assert r.json()["step"]["id"] == "ip_note"
    r = http.post(f"/api/los/applications/{app_id}/actions", headers=h, json={"action": "approve", "comment": "test"})
    assert r.status_code == 400                                                 # u_rm1 keeps the IP Note; approve is not a maker action
    assert any(e["application_id"] == app_id for e in http.get("/api/los/audit", headers=h).json()["events"])
    assert http.post("/api/los/demo/reset", headers=h).status_code == 403             # admin only


def test_api_creates_multi_facility_related_party_application(http):
    token = http.post("/api/los/session", json={"user_id": "u_rm1", "role": "ps_maker"}).json()["token"]
    h = {"X-LOS-Session": token}
    payload = {
        "entity_id": "ABCE001",
        "sourcing_decision": {"decision": "Refer for in-principle",
                              "mandatory_remarks": "API test — refer to in-principle"},
        "facilities": [
            {"facility_nature": "fund_based", "facility_type": "term_loan", "amount_cr": 80,
             "tenor_months": 48, "purpose": "Capacity addition"},
            {"facility_nature": "non_fund_based", "facility_type": "letter_of_credit", "amount_cr": 20,
             "tenor_months": 12, "purpose": "Equipment imports"},
        ],
        "related_parties": [
            {"name": "ABC Promoters Private Limited", "role": "promoter", "party_type": "non_individual",
             "ownership_pct": 60, "pan": "ABCDE1234F"},
        ],
    }
    response = http.post("/api/los/applications", headers=h, json=payload)
    assert response.status_code == 200
    created = response.json()
    assert created["amount_cr"] == 100.0 and len(created["facilities"]) == 2
    assert created["related_parties"][0]["role"] == "promoter"
    assert "+ Add Facility" in http.get("/los").text and "+ Add Related Party" in http.get("/los").text


def test_seed_note_clears_when_the_application_moves_on(svc):
    svc.seed_demo()
    abce = next(a for a in svc.list() if a["entity_id"] == "ABCE001")
    assert abce["demo_note"]
    analyst = sign(svc, abce["assignee_id"], "risk_analyst")
    moved = svc.act(abce["application_id"], analyst, "submit", comment="application_id (test)")
    assert moved["step"]["id"] == "ip_risk_review" and "demo_note" not in moved
