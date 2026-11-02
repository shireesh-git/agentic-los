"""R7: governed modifications of sanctioned terms — materiality, re-entry route, disbursement block."""

from datetime import datetime, timedelta

import pytest

import tests.conftest  # noqa: F401

from src.application.errors import ConflictError, ForbiddenError, InvalidRequestError
from src.data.company_catalog import seed_company_store
from src.los.service import LosService, load_workflow
from src.los.store import LosStore

NOW = datetime(2026, 10, 12, 12, 0, 0)
SOURCING = {"decision": "Refer for in-principle", "mandatory_remarks": "modification test"}


def make_service(tmp_path):
    return LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow, seed_company_store(),
                      clock=lambda: NOW)


def sanctioned(svc, entity="MFL001", amount=100.0):
    app = svc.create(svc._system_session("ps_maker"), entity_id=entity, profile="client_one",
                     facility={"facility_type": "working_capital", "facility_nature": "fund_based",
                               "proposal_type": "Fresh", "amount_cr": amount, "tenor_months": 12,
                               "interest_rate": 12.4, "purpose": "Working capital (demo)"},
                     sourcing_decision=SOURCING)
    sid = app["application_id"]
    svc._replay_to(sid, "pos_maker", NOW, NOW)
    return svc.get(sid, svc._system_session("los_admin"))


def run_pos(svc, sid, wf, to="pos_checker"):
    """Satisfy the conditions, issue the letter, record consent + execution, and drive the case
    to ``to`` (the Post-Sanction Checker by default; the Disbursement Maker for tranche tests)."""
    a0 = svc.store.get(sid)
    if a0.get("step_id") == "pos_maker":
        for c in a0.get("conditions") or []:
            if c["type"] in ("PC", "CP", "CPS"):
                c.update(status="satisfied", note="Satisfied (demo)")
        svc.store.save(a0)
        posm = svc._system_session("pos_maker", a0.get("assignee_id"), wf)
        svc.generate_letter(sid, posm, "sanction_letter")
        posm = svc._system_session("pos_maker", svc.store.get(sid).get("assignee_id"), wf)
        svc.upload_signed_letter(sid, posm, "sanction_letter", "signed-copy-test.pdf", b"%PDF-1.4 test")
        facs = [f["facility_id"] for f in (svc.store.get(sid).get("facilities") or [])]
        svc.record_consent(sid, posm, acknowledged_by="Customer (demo)", consent_date=NOW.date().isoformat(),
                           remarks="Sanction accepted (demo)",
                           facilities=[{"facility_id": fid, "execution_status": "executed",
                                         "agreement_date": NOW.date().isoformat()} for fid in facs])
    while True:
        a = svc.store.get(sid)
        if a["step_id"] == to:
            return svc._system_session(wf.step(a["step_id"]).role, a.get("assignee_id"), wf)
        step = wf.step(a["step_id"])
        session = svc._system_session(step.role, a.get("assignee_id"), wf)
        action = {"maker": "submit", "checker": "approve", "committee": "sanction",
                  "vp_review": "submit", "allocation": "allocate"}[step.kind]
        dd = {f["id"]: (NOW.date().isoformat() if "date" in f["id"] else "None (demo)")
              for f in step.decision_fields if f.get("required")}
        svc.act(sid, session, action, comment=f"{step.name}: driven (demo)", decision_data=dd)


def test_material_modification_reenters_credit_reassessment(tmp_path):
    svc = make_service(tmp_path)
    app = sanctioned(svc, amount=100.0)
    sid = app["application_id"]
    pos = svc._system_session("pos_maker", app["assignee_id"])
    # +30% is above the 10% materiality threshold
    v = svc.propose_modification_request(sid, pos, {"amount_cr": 130, "reason": "Business growth (demo)"})
    mod = v["modifications"][-1]
    assert mod["material"] is True and mod["target_step"] == "ap_risk_maker"
    assert mod["changes"] == [{"field": "amount_cr", "before": 100.0, "after": 130.0}]
    assert any("amount" in m for m in mod["material_basis"])
    # only one open modification at a time
    with pytest.raises(ConflictError, match="still open"):
        svc.propose_modification_request(sid, pos, {"amount_cr": 140})
    # the case moves to the Post-Sanction Checker, which recommends and decides the modification
    wf = svc.wf_for_profile("client_one")
    # the sanctioned letter is issued, consent recorded, and the case moves to the checker
    checker = run_pos(svc, sid, wf)
    assert checker["role"] == "pos_checker"
    with pytest.raises(ConflictError, match="not been recommended"):
        svc.decide_modification_request(sid, checker, {"outcome": "approve", "minutes": "x"})
    v = svc.recommend_modification_request(sid, checker, {"decision": "recommend", "remarks": "Support the increase (demo)"})
    assert v["modifications"][-1]["recommended"]["decision"] == "recommend"
    v = svc.decide_modification_request(sid, checker, {"outcome": "approve", "minutes": "Increase approved (demo)"})
    mod = v["modifications"][-1]
    assert mod["status"] == "approved" and mod["decision"]["minutes"]
    # the new amount is applied, the case re-enters credit reassessment and the route is recalculated
    assert v["amount_cr"] == 130.0
    assert v["step_id"] == "ap_risk_maker"
    assert v["modification_reentry"]["modification_id"] == mod["modification_id"]


def test_minor_modification_is_decided_without_rerun(tmp_path):
    svc = make_service(tmp_path)
    app = sanctioned(svc, amount=100.0)
    sid = app["application_id"]
    pos = svc._system_session("pos_maker", app["assignee_id"])
    # +5% is within the 10% threshold; the rate change is configured as minor
    v = svc.propose_modification_request(sid, pos, {"amount_cr": 105, "interest_rate": 12.4,
                                                    "reason": "Rate re-pricing (demo)"})
    mod = v["modifications"][-1]
    assert mod["material"] is False and mod["target_step"] == "ap_evp"
    wf = svc.wf_for_profile("client_one")
    checker = run_pos(svc, sid, wf)
    svc.recommend_modification_request(sid, checker, {"decision": "recommend", "remarks": "Re-pricing (demo)"})
    v = svc.decide_modification_request(sid, checker, {"outcome": "approve", "minutes": "Re-pricing approved (demo)"})
    assert v["amount_cr"] == 105.0
    # a minor approval does NOT re-enter credit reassessment — the journey position is kept
    assert v["step_id"] != "ap_risk_maker"


def test_open_modification_blocks_disbursement(tmp_path):
    svc = make_service(tmp_path)
    app = sanctioned(svc, amount=100.0)
    sid = app["application_id"]
    pos = svc._system_session("pos_maker", app["assignee_id"])
    svc.propose_modification_request(sid, pos, {"amount_cr": 130, "reason": "Growth (demo)"})
    # the case moves on; the Post-Sanction Checker rejects the modification
    wf = svc.wf_for_profile("client_one")
    checker = run_pos(svc, sid, wf)
    svc.recommend_modification_request(sid, checker, {"decision": "reject", "remarks": "Not supportable (demo)"})
    a = svc.store.get(sid)
    assert a["modifications"][-1]["status"] == "rejected"
    dis = run_pos(svc, sid, wf, to="dis_maker")
    svc.request_tranche(sid, dis, 50.0, (NOW + timedelta(days=3)).date().isoformat())
    # (a second tranche request while a modification is open is refused)
    # and the block fires while a modification is open (proposed from the Disbursement Maker)
    svc.propose_modification_request(sid, dis, {"amount_cr": 130, "reason": "Growth round 2 (demo)"})
    with pytest.raises(ConflictError, match="Modification"):
        svc.request_tranche(sid, dis, 10.0, (NOW + timedelta(days=3)).date().isoformat())


def test_modification_terms_cannot_be_negative_or_unchanged(tmp_path):
    svc = make_service(tmp_path)
    app = sanctioned(svc, amount=100.0)
    sid = app["application_id"]
    pos = svc._system_session("pos_maker", app["assignee_id"])
    with pytest.raises(InvalidRequestError, match="positive"):
        svc.propose_modification_request(sid, pos, {"amount_cr": -5})
    with pytest.raises(InvalidRequestError, match="at least one"):
        svc.propose_modification_request(sid, pos, {"amount_cr": 100})
