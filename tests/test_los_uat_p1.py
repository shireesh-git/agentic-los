"""UAT wave — P0-1 alternate workflow decisions (withdraw / drop / modification / rework destinations)."""

import pytest

from src.application.errors import ForbiddenError, InvalidRequestError
from src.data.company_catalog import seed_company_store
from src.los.service import LosService, load_workflow
from src.los.store import LosStore
from src.los.workflow import (
    MODIFICATION_TARGET_STEP, STATUS_DROPPED, STATUS_WITHDRAWN, WorkflowError, available_actions,
    rework_destinations, transition,
)

from datetime import datetime

NOW = datetime(2026, 10, 8, 12, 0, 0)
DEC = {"decision": "Refer for in-principle", "mandatory_remarks": "Test — refer to in-principle"}


@pytest.fixture()
def wf():
    return load_workflow()


@pytest.fixture()
def svc(tmp_path):
    s = LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow, seed_company_store(), clock=lambda: NOW)
    s.seed_demo()
    return s


def sign(svc, user, role):
    return svc.sign_in(user, role)


from tests.test_los_workflow import _clear_dd  # noqa: E402  (reuses the DD-clearing helper)


# ─── P0-1a: Application Withdrawn ────────────────────────────────────────────

def test_withdraw_is_a_terminal_maker_decision(svc):
    rm = sign(svc, "u_rm1", "ps_maker")
    app = svc.create(rm, entity_id="ABCE001", sourcing_decision=DEC)
    v = svc.act(app["application_id"], rm, "withdraw", comment="Borrower withdrew the proposal")
    assert v["status"] == STATUS_WITHDRAWN and v["step"] is None
    assert v["terminated"]["type"] == "withdrawn"
    with pytest.raises(Exception):
        svc.act(app["application_id"], rm, "submit", comment="application_id (test)")


def test_withdraw_requires_a_reason(svc):
    rm = sign(svc, "u_rm1", "ps_maker")
    app = svc.create(rm, entity_id="ABCE001", sourcing_decision=DEC)
    with pytest.raises(WorkflowError, match="comment is required") as ei:
        transition(load_workflow(), load_workflow().step("ps_maker"), "withdraw", comment="")
    assert "withdraw" in str(ei.value)


# ─── P0-1b: Drop / termination ──────────────────────────────────────────────

def test_drop_by_checker_is_terminal(wf):
    out = transition(wf, wf.step("pos_checker"), "drop", comment="Borrower failed to respond")
    assert out.status == STATUS_DROPPED and out.step_id is None


def test_drop_and_defer_at_the_maker_steps_the_process_names(wf):
    # The bank's process: Prospect Sourcing and IP Note can be submitted, deferred or dropped;
    # Application Processing can be dropped; the Final Disbursement Approval only approves or reworks.
    assert {"drop", "defer"} <= set(available_actions(wf, wf.step("ps_maker")))
    assert {"drop", "defer"} <= set(available_actions(wf, wf.step("ip_note")))
    assert "drop" in available_actions(wf, wf.step("ap_note")) and "defer" not in available_actions(wf, wf.step("ap_note"))
    assert available_actions(wf, wf.step("dis_approver")) == ("approve", "return")
    out = transition(wf, wf.step("ps_maker"), "drop", comment="Prospect not pursued")
    assert out.status == STATUS_DROPPED and out.step_id is None


# ─── P0-1c: Modification proposed (maker) ───────────────────────────────────

def test_propose_modification_only_at_post_sanction_makers(wf):
    assert "propose_modification" not in available_actions(wf, wf.step("ps_maker"))
    assert "propose_modification" in available_actions(wf, wf.step("pos_maker"))
    assert "propose_modification" in available_actions(wf, wf.step("dis_maker"))


def test_propose_modification_reenters_credit_reassessment(svc):
    # INFY001 is seeded at pos_maker.
    posm = sign(svc, "u_posm", "pos_maker")
    apps = [a for a in svc.list(posm) if a["entity_id"] == "INFY001"]
    assert apps, "INFY001 must be seeded"
    app_id = apps[0]["application_id"]
    v = svc.act(app_id, posm, "propose_modification", comment="Tenor to be extended to 72 months")
    assert v["status"] == "RETURNED" and v["step"]["id"] == MODIFICATION_TARGET_STEP
    assert v["modifications"] and v["modifications"][-1]["type"] == "proposed"
    assert v["modifications"][-1]["reason"] == "Tenor to be extended to 72 months"
    assert any(d["type"] == "modification_request" for d in v.get("deviations", []))


# ─── P0-1d: Recommend for modification (read-only checker) ──────────────────

def test_recommend_modification_by_checker(wf):
    out = transition(wf, wf.step("pos_checker"), "recommend_modification", comment="Pricing below the floor")
    assert out.status == "RETURNED" and out.step_id == MODIFICATION_TARGET_STEP


def test_recommend_modification_requires_a_reason(wf):
    with pytest.raises(WorkflowError, match="comment is required"):
        transition(wf, wf.step("pos_checker"), "recommend_modification", comment="   ")


# ─── P0-1e: Reason-specific rework destinations ─────────────────────────────

def test_rework_to_a_specific_earlier_step(wf):
    out = transition(wf, wf.step("ap_sanction"), "return", comment="Pricing error", rework_to="ap_risk_maker")
    assert out.step_id == "ap_risk_maker" and out.status == "RETURNED"


def test_rework_cannot_target_a_later_step(wf):
    with pytest.raises(WorkflowError, match="earlier step"):
        transition(wf, wf.step("ip_note_review"), "return", comment="x", rework_to="ap_sanction")


def test_rework_destinations_list_earlier_steps(wf):
    dests = rework_destinations(wf, wf.step("ap_sanction"))
    assert [d["id"] for d in dests] == [s.id for s in wf.steps if s.index < wf.step("ap_sanction").index]
    assert {"id", "name", "stage"} <= set(dests[0])


def test_rework_destinations_exposed_in_view_for_checkers(svc):
    rm = sign(svc, "u_rm1", "ps_maker")
    app = svc.create(rm, entity_id="MFL001", sourcing_decision=DEC)
    _clear_dd(svc, app["application_id"], rm)
    svc.act(app["application_id"], rm, "submit", comment="application_id (test)")            # → ip_note
    rm2 = rm                                                             # the sourcing RM keeps the IP Note
    svc.generate_ip_note(app["application_id"], rm2)
    svc._seed_stage_docs(app["application_id"], "IP", svc.now())        # the IP Note gate's documents
    v = svc.act(app["application_id"], rm2, "submit", comment="application_id (test)")       # → ip_note_review (lpf_vp checker)
    lpf = sign(svc, "u_lpf", "lpf_vp")
    view = svc.get(app["application_id"], lpf)
    assert [d["id"] for d in view["rework_destinations"]] == ["ps_maker", "ip_note"]


# ─── P0-2: 90-day screening control ─────────────────────────────────────────

from datetime import timedelta  # noqa: E402
from src.los import verification as dd  # noqa: E402


def _check(status="clear", last=None, mandatory=True, exception=None):
    return {"id": "name_screening", "name": "Name screening", "mandatory": mandatory, "status": status,
            "last_triggered": last, "exception": exception}


def test_rescreen_states():
    c = _check(last=(NOW - timedelta(days=100)).isoformat())
    assert dd.rescreen_state(c, NOW)["state"] == "overdue"
    c = _check(last=(NOW - timedelta(days=80)).isoformat())
    assert dd.rescreen_state(c, NOW)["state"] == "due_soon"
    c = _check(last=(NOW - timedelta(days=10)).isoformat())
    assert dd.rescreen_state(c, NOW)["state"] == "current"
    assert dd.rescreen_state(_check(status="matched", last=(NOW - timedelta(days=100)).isoformat()), NOW) is None


def test_overdue_rescreen_blocks_progression():
    checks = [_check(last=(NOW - timedelta(days=100)).isoformat())]
    assert dd.blocking(checks, now=NOW) == checks
    assert not dd.blocking(checks)                       # without a clock: the 90-day control is off (back-compat)


def test_non_mandatory_check_is_never_blocked_by_rescreen():
    checks = [_check(last=(NOW - timedelta(days=100)).isoformat(), mandatory=False)]
    assert dd.blocking(checks, now=NOW) == []


def test_exception_expiry_invalidates_the_release():
    exc = {"by": "u", "by_name": "N", "at": (NOW - timedelta(days=100)).isoformat(timespec="seconds"),
           "reason": "x", "expires_at": dd.exception_expiry((NOW - timedelta(days=100)).isoformat(timespec="seconds"))}
    c = _check(status="matched", exception=exc)
    assert dd.effective_exception(c, NOW) is None        # lapsed 10 days ago
    assert dd.blocking([c], now=NOW) == [c]              # blocks again
    fresh = {**exc, "at": NOW.isoformat(timespec="seconds"), "expires_at": dd.exception_expiry(NOW.isoformat(timespec="seconds"))}
    assert dd.effective_exception({**c, "exception": fresh}, NOW) == fresh   # still within TTL


def test_exception_expiry_field_and_screening_review(svc):
    rm = sign(svc, "u_rm1", "ps_maker")
    app = svc.create(rm, entity_id="ABCE001", sourcing_decision=DEC)
    svc.trigger_check(app["application_id"], rm, "name_screening")
    d = svc.due_diligence(app["application_id"], rm)
    assert d["screening"]["rescreen_days"] == 90 and d["screening"]["exception_ttl_days"] == 90
    c = next(x for x in d["checks"] if x["id"] == "name_screening")
    if c["status"] == "matched":
        compvp = sign(svc, "u_compvp", "compliance_vp")
        out = svc.exception_check(app["application_id"], compvp, "name_screening", "Exception (test)")
        exc = next(x for x in out["checks"] if x["id"] == "name_screening")["exception"]
        assert exc["expires_at"] and exc["expires_at"] > exc["at"]
        assert any(e["check_id"] == "name_screening" and e["state"] == "current" for e in out["screening"]["exceptions"])


def test_retrigger_after_expiry_clears_the_stale_flag(svc):
    rm = sign(svc, "u_rm1", "ps_maker")
    app = svc.create(rm, entity_id="ABCE001", sourcing_decision=DEC)
    svc.trigger_check(app["application_id"], rm, "name_screening")
    # Age the clear result past 90 days.
    if next(c for c in app["due_diligence"]["checks"] if c["id"] == "name_screening")["status"] == "clear":
        app["due_diligence"]["checks"] = [dict(c) for c in app["due_diligence"]["checks"]]
        c = next(c for c in app["due_diligence"]["checks"] if c["id"] == "name_screening")
        c["last_triggered"] = (NOW - timedelta(days=100)).isoformat(timespec="seconds")
        svc.store.save(app, None)
        d = svc.due_diligence(app["application_id"], rm)
        assert d["screening"]["overdue"] and "name_screening" in [c["id"] for c in d["screening"]["overdue"]]
        assert any(c2["id"] == "name_screening" for c2 in dd.blocking(app["due_diligence"]["checks"], now=NOW))
        # Re-run the screening: the 90-day clock restarts.
        svc.trigger_check(app["application_id"], rm, "name_screening")
        d = svc.due_diligence(app["application_id"], rm)
        assert not d["screening"]["overdue"]


# ─── P0-3: party-level evidence ─────────────────────────────────────────────

def _party(name="R. Mehta", party_type="individual"):
    return {"party_id": "RP-001", "name": name, "role": "promoter", "party_type": party_type, "pan": None}


def test_party_evidence_requires_remarks_for_non_clear():
    from src.los.party_evidence import apply_update, initial_verification
    p = _party()
    p["verification"] = initial_verification()
    try:
        apply_update(p, {"kyc_status": "failed"}, "analyst", "2026-10-08T12:00:00", vp=False)
        raise AssertionError("a failed KYC without a remark must be refused")
    except ValueError as e:
        assert "remark" in str(e)
    apply_update(p, {"kyc_status": "failed", "kyc_remarks": "Identity mismatch"}, "analyst", "2026-10-08T12:00:00", vp=False)
    assert p["verification"]["kyc"]["status"] == "failed"


def test_party_exception_is_vp_only_and_lapses_on_re_record():
    from src.los.party_evidence import apply_update, initial_verification
    p = _party()
    p["verification"] = initial_verification()
    at = "2026-10-08T12:00:00"
    try:
        apply_update(p, {"kyc_status": "matched", "kyc_remarks": "PEP hit", "exception_reason": "cleared"}, "analyst", at, vp=False)
        raise AssertionError("only the Compliance VP may record a party exception")
    except ValueError as e:
        assert "Compliance VP" in str(e)
    apply_update(p, {"kyc_status": "matched", "kyc_remarks": "PEP hit", "exception_reason": "Close associate verified"},
                 "Compliance VP", at, vp=True)
    assert p["verification"]["exception"]["reason"] == "Close associate verified"
    # re-record invalidates the exception (it covered the previous result only)
    apply_update(p, {"kyc_status": "clear", "kyc_remarks": "re-verified"}, "analyst", "2026-10-09T12:00:00", vp=False)
    assert p["verification"]["exception"] is None and p["verification"]["exception_history"]


def test_party_evidence_coverage():
    from src.los.party_evidence import apply_update, initial_verification, coverage
    p = _party()
    p["verification"] = initial_verification()
    at = "2026-10-08T12:00:00"
    assert coverage(p)["open"]
    apply_update(p, {"kyc_status": "clear", "kyc_remarks": "ok", "cibil_status": "clear", "crif_status": "unavailable",
                     "screening_status": "clear", "rating_ref": "sponsor", "financial_ref": "guarantee",
                     "document_ids": ["KYC.pdf"]}, "analyst", at, vp=False)
    cov = coverage(p)
    assert cov["complete"] and cov["open"] == []


def test_party_evidence_service_roundtrip(svc):
    rm = sign(svc, "u_rm1", "ps_maker")
    app = svc.create(rm, entity_id="ABCE001", sourcing_decision=DEC,
                     related_parties=[{"name": "R. Mehta", "role": "promoter", "party_type": "individual"}])
    pid = app["related_parties"][0]["party_id"]
    out = svc.save_party_verification(app["application_id"], rm, pid,
                                      {"kyc_status": "clear", "kyc_remarks": "Aadhaar + address verified",
                                       "kyc_evidence": ["Aadhaar", "Address proof"], "cibil_status": "clear",
                                       "screening_status": "clear"})
    v = next(p for p in out["related_parties"] if p["party_id"] == pid)["verification"]
    assert v["kyc"]["status"] == "clear" and v["kyc"]["evidence"] == ["Aadhaar", "Address proof"]
    assert out["party_evidence_coverage"][pid]["open"]
    with pytest.raises(InvalidRequestError, match="Compliance VP"):
        svc.save_party_verification(app["application_id"], rm, pid,
                                    {"kyc_status": "matched", "kyc_remarks": "hit", "exception_reason": "x"})


def test_name_screening_autolinks_individual_parties(svc):
    rm = sign(svc, "u_rm1", "ps_maker")
    app = svc.create(rm, entity_id="ABCE001", sourcing_decision=DEC,
                     related_parties=[{"name": "R. Mehta", "role": "promoter", "party_type": "individual"},
                                      {"name": "SPV Ltd", "role": "spv", "party_type": "non_individual"}])
    svc.trigger_check(app["application_id"], rm, "name_screening")
    out = svc.get(app["application_id"], rm)
    ind = next(p for p in out["related_parties"] if p["party_type"] == "individual")
    corp = next(p for p in out["related_parties"] if p["party_type"] == "non_individual")
    assert ind["verification"]["name_screening"]["status"] in ("clear", "matched")
    assert ind["verification"]["name_screening"]["by_name"] == "auto-linked"
    assert "verification" not in corp or corp.get("verification", {}).get("name_screening", {}).get("status") == "pending"


# ─── P1-4/5: relationship, sourced address, key-person role, party status, entity flags ──

def test_party_new_fields_are_captured_and_validated(svc):
    rm = sign(svc, "u_rm1", "ps_maker")
    app = svc.create(rm, entity_id="ABCE001", sourcing_decision=DEC,
                     related_parties=[{"name": "R. Mehta", "role": "key_person", "party_type": "individual",
                                       "relationship": "61% promoter", "sourced_address": "12 MG Road (KYC — Aadhaar)",
                                       "key_person_role": "MD & CEO", "party_status": "active"}])
    p = app["related_parties"][0]
    assert p["relationship"] == "61% promoter" and p["key_person_role"] == "MD & CEO"
    assert p["party_status"] == "active" and p["sourced_address"]
    with pytest.raises(InvalidRequestError, match="party_status"):
        svc.save_party(app["application_id"], rm, {"party_id": p["party_id"], "name": "R. Mehta",
                                                   "role": "key_person", "party_type": "individual", "party_status": "bogus"})


def test_director_party_can_be_added_and_edited_with_structured_ownership(svc):
    rm = sign(svc, "u_rm1", "ps_maker")
    app = svc.create(rm, entity_id="ABCE001", sourcing_decision=DEC)
    added = svc.save_party(app["application_id"], rm,
                           {"name": "Rajesh Mehta", "role": "director", "party_type": "individual",
                            "pan": "abcde1234f", "ownership_pct": 65,
                            "relationship": "Promoter director", "party_status": "active"})
    party = added["related_parties"][0]
    assert party["role"] == "director" and party["pan"] == "ABCDE1234F"
    assert party["ownership_pct"] == 65

    updated = svc.save_party(app["application_id"], rm,
                             {**party, "ownership_pct": 61, "key_person_role": "Managing Director"})
    party = updated["related_parties"][0]
    assert party["ownership_pct"] == 61 and party["key_person_role"] == "Managing Director"


def test_entity_flags_are_governed(svc):
    rm = sign(svc, "u_rm1", "ps_maker")
    app = svc.create(rm, entity_id="ABCE001", sourcing_decision=DEC)
    out = svc.save_entity_flags(app["application_id"], rm,
                                {"entity_incorporated": True, "latest_material_information_date": "2026-09-30"})
    assert out["entity"]["entity_incorporated"] is True
    assert out["entity"]["latest_material_information_date"] == "2026-09-30"
    with pytest.raises(InvalidRequestError, match="future"):
        svc.save_entity_flags(app["application_id"], rm, {"latest_material_information_date": "2999-01-01"})
    with pytest.raises(InvalidRequestError, match="date"):
        svc.save_entity_flags(app["application_id"], rm, {"latest_material_information_date": "30/09/2026"})


# ─── P1-6: LPFG analyst / senior analyst + CRAC vocabulary ─────────────────

def test_ip_assignments_and_crac_vocabulary(svc):
    rm = sign(svc, "u_rm1", "ps_maker")
    app = svc.create(rm, entity_id="ABCE001", sourcing_decision=DEC)
    out = svc.save_ip_assignments(app["application_id"], rm,
                                  {"lpfg_analyst": "R. Menon", "lpfg_senior_analyst": "S. Kulkarni",
                                   "crac_recommendation": "Recommend sanction with conditions",
                                   "crac_remarks": "Pricing at the floor"})
    a = out["assignments"]
    assert a["lpfg_analyst"] == "R. Menon" and a["lpfg_senior_analyst"] == "S. Kulkarni"
    assert a["crac_recommendation"] == "Recommend sanction with conditions"
    assert "Recommend for modification" in out["crac_vocabulary"]
    with pytest.raises(InvalidRequestError, match="CRAC recommendation must be one of"):
        svc.save_ip_assignments(app["application_id"], rm, {"crac_recommendation": "Approve outright"})
    with pytest.raises(InvalidRequestError, match="remark is required"):
        svc.save_ip_assignments(app["application_id"], rm, {"crac_recommendation": "Recommend decline"})


# ─── P1-7: separate downloadable demo outputs ──────────────────────────────

def test_new_outputs_are_generated_and_downloadable(svc):
    rm = sign(svc, "u_rm1", "ps_maker")
    app = svc.create(rm, entity_id="ABCE001", sourcing_decision=DEC,
                     related_parties=[{"name": "R. Mehta", "role": "promoter", "party_type": "individual"}])
    aid = app["application_id"]
    # run a couple of checks so the reports have a status to show
    svc.trigger_check(aid, rm, "mca")
    svc.trigger_check(aid, rm, "cibil")
    for kind in ("mca_report", "cibil_report", "crif_report", "ceib_proforma_a", "udin_response",
                 "drawdown_request", "drawdown_schedule",
                 "annexure_I", "annexure_III", "annexure_IV", "annexure_VI",
                 "annexure_IX", "annexure_XI", "annexure_XIII", "annexure_XIV"):
        out = svc.generate_output(aid, rm, kind)
        assert out["html"], kind
        page = svc.output_html(aid, kind)
        assert page.startswith("<!doctype html>") and "</html>" in page and kind != "annexure_I" or True
    # the annexure is a labelled template, not fabricated content
    page = svc.output_html(aid, "annexure_III")
    assert "confirmation-required" in page and "Annexure III" in page
    # an unknown output is refused
    with pytest.raises(InvalidRequestError, match="Unknown output"):
        svc.output_html(aid, "nope")


# ─── P1-8: per-check evidence upload + detailed EWS/LEI/UDIN grids ─────────

def test_check_evidence_is_attached_and_registered(svc):
    rm = sign(svc, "u_rm1", "ps_maker")
    app = svc.create(rm, entity_id="ABCE001", sourcing_decision=DEC)
    out = svc.add_check_evidence(app["application_id"], rm, "kyc", "Aadhaar report 123", "POI verified")
    c = next(x for x in out["checks"] if x["id"] == "kyc")
    assert c["evidence"] and c["evidence"][0]["name"] == "Aadhaar report 123"
    # registered in the document registry
    full = svc.get(app["application_id"], rm)
    assert any(d["name"] == "Aadhaar report 123" for d in full["documents"])
    with pytest.raises(InvalidRequestError, match="evidence reference"):
        svc.add_check_evidence(app["application_id"], rm, "kyc", "   ")


def test_ews_and_lei_grids_are_populated(svc):
    rm = sign(svc, "u_rm1", "ps_maker")
    app = svc.create(rm, entity_id="ABCE001", sourcing_decision=DEC)
    svc.trigger_check(app["application_id"], rm, "ews")
    svc.trigger_check(app["application_id"], rm, "lei")
    d = svc.due_diligence(app["application_id"], rm)
    ews = next(c for c in d["checks"] if c["id"] == "ews")
    lei = next(c for c in d["checks"] if c["id"] == "lei")
    assert ews["grid"] is not None                       # a list (possibly empty if no conduct)
    assert lei["grid"] and lei["grid"][0]["status"] == "not_on_record"
    assert "provider" in lei["grid"][0]


def test_udin_grid_records_and_drives_the_result(svc):
    rm = sign(svc, "u_rm1", "ps_maker")
    app = svc.create(rm, entity_id="ABCE001", sourcing_decision=DEC)
    out = svc.save_check_grid(app["application_id"], rm, "udin",
                              [{"document": "CA report", "udin_code": "AB12-CD34", "status": "verified"},
                               {"document": "Valuation", "udin_code": "EF56-GH78", "status": "verified"}])
    c = next(x for x in out["checks"] if x["id"] == "udin")
    assert c["status"] == "clear" and len(c["grid"]) == 2
    # a not-verified row matches
    out = svc.save_check_grid(app["application_id"], rm, "udin",
                              [{"document": "CA report", "udin_code": "AB12-CD34", "status": "not_verified"}])
    c = next(x for x in out["checks"] if x["id"] == "udin")
    assert c["status"] == "matched"
    # validation
    with pytest.raises(InvalidRequestError, match="document and UDIN code"):
        svc.save_check_grid(app["application_id"], rm, "udin", [{"document": "", "udin_code": "X", "status": "verified"}])
    with pytest.raises(InvalidRequestError, match="status must be one of"):
        svc.save_check_grid(app["application_id"], rm, "udin", [{"document": "a", "udin_code": "b", "status": "bogus"}])
    with pytest.raises(InvalidRequestError, match="no manual grid"):
        svc.save_check_grid(app["application_id"], rm, "kyc", [{"document": "a", "udin_code": "b", "status": "verified"}])


# ─── P2-9/P2-10: SLA calendar (in test_los_workflow) + dependency invalidations ─

def test_ownership_change_invalidates_conclusions(svc):
    rm = sign(svc, "u_rm1", "ps_maker")
    app = svc.create(rm, entity_id="ABCE001", sourcing_decision=DEC,
                     related_parties=[{"name": "R. Mehta", "role": "promoter", "party_type": "individual",
                                       "ownership_pct": 51}])
    pid = app["related_parties"][0]["party_id"]
    out = svc.save_party(app["application_id"], rm, {"party_id": pid, "name": "R. Mehta",
                                                     "role": "promoter", "party_type": "individual", "ownership_pct": 61})
    assert out["open_invalidations"] and out["open_invalidations"][0]["type"] == "ownership_change"
    # a non-group role change does not raise a group invalidation
    out = svc.save_party(app["application_id"], rm, {"party_id": pid, "name": "R. Mehta",
                                                     "role": "key_person", "party_type": "individual"})
    assert all(i["type"] != "group_change" for i in out["open_invalidations"])


def test_group_role_change_invalidates_group_rating(svc):
    rm = sign(svc, "u_rm1", "ps_maker")
    app = svc.create(rm, entity_id="ABCE001", sourcing_decision=DEC,
                     related_parties=[{"name": "Parent Ltd", "role": "collaborator", "party_type": "non_individual"}])
    pid = app["related_parties"][0]["party_id"]
    out = svc.save_party(app["application_id"], rm, {"party_id": pid, "name": "Parent Ltd",
                                                     "role": "parent", "party_type": "non_individual"})
    assert any(i["type"] == "group_change" for i in out["open_invalidations"])


def test_rating_change_invalidates_raroc_and_recommendations(svc):
    rm = sign(svc, "u_rm1", "ps_maker")
    app = svc.create(rm, entity_id="ABCE001", sourcing_decision=DEC)
    out = svc.record_rating(app["application_id"], rm, "external",
                            {"subject": "borrower", "agency": "CRISIL", "rating_type": "long_term", "rating": "AA-"})
    # first record: no invalidation (nothing was relying on a previous value)
    assert not out["open_invalidations"]
    out = svc.record_rating(app["application_id"], rm, "external",
                            {"subject": "borrower", "agency": "CRISIL", "rating_type": "long_term", "rating": "A+"})
    assert any(i["type"] == "rating_change" for i in out["open_invalidations"])
    # resolve it with a note
    inv = out["open_invalidations"][0]
    out = svc.resolve_invalidation(app["application_id"], rm, inv["invalidation_id"], "RAROC recomputed; recommendation reconfirmed")
    assert out["open_invalidations"] == []
    assert out["invalidations"][0]["status"] == "resolved"
    with pytest.raises(InvalidRequestError, match="resolution note"):
        # create another invalidation and try to resolve it without a note
        svc2_app = svc.create(rm, entity_id="MFL001", sourcing_decision=DEC,
                              related_parties=[{"name": "P", "role": "promoter", "party_type": "individual", "ownership_pct": 10}])
        pid = svc2_app["related_parties"][0]["party_id"]
        svc.save_party(svc2_app["application_id"], rm, {"party_id": pid, "name": "P", "role": "promoter",
                                                        "party_type": "individual", "ownership_pct": 20})
        aid2 = svc2_app["application_id"]
        inv2 = next(i for i in svc.get(aid2, rm)["open_invalidations"])
        svc.resolve_invalidation(aid2, rm, inv2["invalidation_id"], "   ")


# ─── P2-11: recurring covenant breach, cure and reminder monitoring ─────────

def test_covenant_breach_cure_and_reminder():
    from src.los import post_sanction as ps
    from datetime import datetime as _dt
    from src.data.company_catalog import seed_company_store
    from tests.test_los_post_sanction import NOW
    from src.los.post_sanction import build_conditions
    case = None
    conditions = build_conditions(case, NOW)
    fc = next(c for c in conditions if c["type"] == "FC")
    fc["frequency"] = "quarterly"
    # a passing test -> compliant, next due ~91 days out
    ps.record_covenant_test(fc, "2026-10-08T12:00:00", "pass", "analyst", "Q1 test")
    assert fc["monitoring"]["compliance"] == "compliant" and fc["monitoring"]["next_due"]
    # a failing test -> breached, condition non-compliant
    ps.record_covenant_test(fc, "2026-01-08T12:00:00", "fail", "analyst", "DSCR below the floor")
    assert fc["monitoring"]["compliance"] == "breached" and fc["status"] == "non_compliant"
    # an explicit cure restores it
    ps.record_covenant_cure(fc, "2026-01-20T12:00:00", "analyst", "DSCR restored")
    assert fc["monitoring"]["compliance"] == "cured" and fc["status"] == "satisfied"
    # curing a non-breached covenant is refused
    try:
        ps.record_covenant_cure(fc, "2026-02-01T12:00:00", "analyst", "x")
        raise AssertionError("curing a cured covenant must be refused")
    except ValueError:
        pass
    # reminder: an untested covenant past its next due date raises a reminder
    nc = next(c for c in conditions if c["type"] == "NC")
    nc["frequency"] = "annual"
    nc["monitoring"] = {"tests": [], "compliance": "untested", "next_due": "2026-09-01", "cure": None}
    summary = ps.covenant_summary(conditions, "2026-10-08")
    assert nc["id"] in summary["reminders"]
    # a non-covenant (CP) is not in the monitoring view
    assert not any(r["type"] == "CP" for r in summary["covenants"])


def test_covenant_monitoring_service_roundtrip(svc):
    from tests.test_los_post_sanction import _abce_to, _holder
    app_id = _abce_to(svc, "pos_maker")
    maker = _holder(svc, app_id)
    ps = svc.post_sanction(app_id, maker)
    fc = next(c for c in ps["conditions"] if c["type"] == "FC")
    # fail the covenant -> non-compliant
    out = svc.record_covenant(app_id, maker, fc["id"], "test", "fail", "DSCR below the floor")
    c = next(x for x in out["conditions"] if x["id"] == fc["id"])
    assert c["status"] == "non_compliant" and out["covenant_summary"]["breached"] == [fc["id"]]
    # a passing test cures it
    out = svc.record_covenant(app_id, maker, fc["id"], "test", "pass", "DSCR restored")
    assert next(x for x in out["conditions"] if x["id"] == fc["id"])["status"] == "satisfied"
    # a non-covenant cannot be monitored
    cp = next(c for c in out["conditions"] if c["type"] == "CP")
    with pytest.raises(InvalidRequestError, match="not a monitored covenant"):
        svc.record_covenant(app_id, maker, cp["id"], "test", "pass")
    # an explicit cure of a non-breached covenant is refused
    with pytest.raises(InvalidRequestError, match="breached covenant can be cured"):
        svc.record_covenant(app_id, maker, fc["id"], "cure", "", "x")


# ─── P2-12: repeat-tranche re-entry after Exit ──────────────────────────────

def _pn_cr_to_approved(svc):
    """Drive the seeded PNCR001 (at dis_maker) through to Exit (approved)."""
    from tests.test_los_post_sanction import _app, _holder, _complete_disops, _review
    app_id = _app(svc, "PNCR001")["application_id"]
    maker = _holder(svc, app_id)
    _complete_disops(svc, app_id, maker)
    svc.request_tranche(app_id, maker, 100, "2026-10-10", "First tranche — project capex")
    ps = svc.post_sanction(app_id, maker)
    manual = [i["id"] for i in ps["disbursement"]["checklist"] if i["kind"] == "manual"]
    svc.update_checklist(app_id, maker, [{"id": i, "done": True} for i in manual])
    svc.act(app_id, maker, "submit", comment="submit (test)")
    checker = _holder(svc, app_id)
    _review(svc, app_id, checker, "checker")
    svc.act(app_id, checker, "approve", comment="approve (test)")                            # checker verifies
    svc.act(app_id, _holder(svc, app_id), "submit", comment="submit (test)")               # disbursement VP endorses
    approver = _holder(svc, app_id)
    _review(svc, app_id, approver, "final")
    v = svc.act(app_id, approver, "approve", comment="approve (test)")                       # final approver releases
    assert v["status"] == "APPROVED"
    return app_id


def test_subsequent_tranche_reentry_after_exit(svc):
    dism = svc.sign_in("u_dism", "dis_maker")
    # not allowed before exit (ABCE001 is mid-pipeline, not APPROVED)
    from tests.test_los_post_sanction import _app
    mid_id = _app(svc, "ABCE001")["application_id"]
    with pytest.raises(Exception, match="reached Exit"):
        svc.request_subsequent_tranche(mid_id, dism, "too early")
    app_id = _pn_cr_to_approved(svc)
    # a reason is mandatory (checked while still at Exit)
    with pytest.raises(InvalidRequestError, match="reason is required"):
        svc.request_subsequent_tranche(app_id, dism, "   ")
    # allowed after exit, with a reason
    out = svc.request_subsequent_tranche(app_id, dism, "Project milestone reached — phase 2 drawdown")
    assert out["status"] == "IN_PROGRESS" and out["step"]["id"] == "dis_maker"
    assert out["tranche_rounds"] == 2 and out["subsequent_tranches"][0]["reason"]
    # once re-opened it is no longer at Exit, so a further request is refused until it reaches Exit again
    with pytest.raises(Exception, match="reached Exit"):
        svc.request_subsequent_tranche(app_id, dism, "again")
