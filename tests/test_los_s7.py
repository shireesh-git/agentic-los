"""S7: the bank's workflow steps and decisions — Post Rating VP Review (G-W1), the ES stages (G-W2), DMD
approval (G-W3), the decision wording (G-W4), the decision tab (G-W5) and the AP decision record (G-W6)."""

import copy

import pytest

from src.application.errors import ForbiddenError, InvalidRequestError
from src.core.config_manager import config
from src.los.workflow import Workflow, WorkflowError, available_actions, action_label, transition
from tests.test_los_post_sanction import _abce_to, _holder, abce_case, svc  # noqa: F401 (fixtures)
from tests.test_los_workflow import es_work


@pytest.fixture(scope="module")
def cfg():
    return config.get("los_workflow")


@pytest.fixture(scope="module")
def wf(cfg):
    return Workflow.from_config(cfg)


# ── the steps (G-W1, G-W2, G-W3) ─────────────────────────────────────────────

def test_the_steps_follow_the_reference_order(wf):
    ids = [s.id for s in wf.steps]
    assert ids.index("ip_post_rating_vp") == ids.index("ip_risk_review") + 1
    assert ids[ids.index("ap_recommend"):ids.index("ap_sanction") + 1] == [
        "ap_recommend", "ap_es_maker", "ap_es_prep", "ap_es_review", "ap_es_recommend", "ap_dmd", "ap_sanction"]
    assert {wf.step(i).role for i in ("ap_es_maker", "ap_es_prep", "ap_es_review", "ap_es_recommend", "ap_dmd")} == {
        "es_maker", "es_preparer", "es_reviewer", "es_recommender", "dmd"}
    for role in ("es_maker", "es_preparer", "es_reviewer", "es_recommender", "dmd"):
        assert wf.users_with_role(role), role


def test_the_dmd_step_can_be_switched_off_for_the_pos_manual_order(cfg):
    alt = copy.deepcopy(cfg)
    ap = next(s for s in alt["stages"] if s["id"] == "AP")
    next(s for s in ap["steps"] if s["id"] == "ap_dmd")["enabled"] = False
    wf = Workflow.from_config(alt)
    assert "ap_dmd" not in [s.id for s in wf.steps]
    assert transition(wf, wf.step("ap_es_recommend"), "approve", comment="ok").step_id == "ap_sanction"


def test_returns_to_must_name_an_earlier_step(cfg):
    bad = copy.deepcopy(cfg)
    ap = next(s for s in bad["stages"] if s["id"] == "AP")
    next(s for s in ap["steps"] if s["id"] == "ap_review")["returns_to"] = "ap_sanction"
    with pytest.raises(WorkflowError, match="returns_to"):
        Workflow.from_config(bad)


# ── the bank's decision wording (G-W4) ───────────────────────────────────────

def test_decisions_use_the_bank_vocabulary(wf):
    assert available_actions(wf, wf.step("ip_note")) == ("submit", "defer", "drop")            # no withdraw
    assert available_actions(wf, wf.step("ap_recommend")) == ("sanction", "return")
    assert action_label(wf.step("ap_recommend"), "sanction") == "Recommend for sanction"
    assert available_actions(wf, wf.step("ap_evp")) == ("approve", "return")
    assert "drop" not in available_actions(wf, wf.step("pos_maker"))
    assert action_label(wf.step("pos_maker"), "withdraw") == "Application withdrawn"
    assert "reject" not in available_actions(wf, wf.step("pos_checker"))
    assert available_actions(wf, wf.step("ap_es_maker")) == available_actions(wf, wf.step("ap_es_prep")) == ("submit",)
    for sid in ("ap_review", "ap_risk_review", "ap_rating_vp", "ap_evp", "ap_es_review", "ap_dmd", "pos_checker",
                "dis_checker", "dis_approver"):
        assert action_label(wf.step(sid), "return") == "Rework", sid


# ── the AP decision record (G-W6) ────────────────────────────────────────────

def test_every_ap_maker_and_review_step_records_the_standard_decision_record(wf):
    record = ["material_information_date", "committee_matters", "confirmation_ratification", "approval_purpose",
              "significant_changes"]
    for sid in ("ap_note", "ap_review", "ap_risk_maker", "ap_risk_review", "ap_post_rating", "ap_rating_vp"):
        assert [f["id"] for f in wf.step(sid).decision_fields] == record, sid


def test_the_decision_record_is_carried_forward_and_required(svc):
    app_id = _abce_to(svc, "ap_note")
    rm = _holder(svc, app_id)
    view = svc.get(app_id, rm)
    assert [f["label"] for f in view["decision_fields"]][:2] == ["Date of receipt of last material information",
                                                                  "Any other matter to be highlighted to Committee"]
    with pytest.raises(InvalidRequestError, match="Date of receipt of last material information"):
        svc.act(app_id, rm, "submit", comment="AP note")
    svc.act(app_id, rm, "submit", comment="AP note", decision_data={
        "material_information_date": "2026-10-01", "committee_matters": "Tariff revision pending",
        "approval_purpose": "Fresh term loan", "significant_changes": "None since the IP sanction"})
    vp = _holder(svc, app_id)
    defaults = svc.get(app_id, vp)["decision_defaults"]
    assert defaults == {"material_information_date": "2026-10-01", "committee_matters": "Tariff revision pending",
                        "approval_purpose": "Fresh term loan", "significant_changes": "None since the IP sanction"}
    assert svc.get(app_id)["decisions"][-1]["committee_matters"] == "Tariff revision pending"


# ── the ES process (G-W2) and DMD approval (G-W3) ────────────────────────────

def test_the_es_process_gates_its_own_work(svc):
    app_id = _abce_to(svc, "ap_es_maker")
    es_maker = _holder(svc, app_id)
    assert es_maker["role"] == "es_maker"
    blockers = svc.get(app_id, es_maker)["blockers"]
    assert blockers and blockers[0]["where"] == "projects" and "E&S risk category" in blockers[0]["message"]
    with pytest.raises(InvalidRequestError, match="E&S risk category"):
        svc.act(app_id, es_maker, "submit", comment="ES maker")
    es_work(svc, app_id, es_maker, "ap_es_maker")
    svc.act(app_id, es_maker, "submit", comment="Categorised")
    prep = _holder(svc, app_id)
    with pytest.raises(InvalidRequestError, match="ESMS Approval Note"):
        svc.act(app_id, prep, "submit", comment="ES prepared")
    es_work(svc, app_id, prep, "ap_es_prep")
    svc.act(app_id, prep, "submit", comment="ES prepared")
    reviewer = _holder(svc, app_id)
    svc.act(app_id, reviewer, "return", comment="Add the resettlement remarks")                 # rework
    assert svc.get(app_id)["step"]["id"] == "ap_es_prep"
    svc.act(app_id, _holder(svc, app_id), "submit", comment="Remarks added")
    svc.act(app_id, _holder(svc, app_id), "approve", comment="Reviewed")
    rec = _holder(svc, app_id)
    with pytest.raises(InvalidRequestError, match="ES recommendation is required"):
        svc.act(app_id, rec, "approve", comment="ES recommendation")
    svc.act(app_id, rec, "approve", comment="ES recommendation",
            decision_data={"esms_recommendation": "Category B; standard E&S covenants"})
    dmd = _holder(svc, app_id)
    assert svc.get(app_id)["step"]["id"] == "ap_dmd" and dmd["role"] == "dmd"
    svc.act(app_id, dmd, "approve", comment="Approved for the committee")
    assert svc.get(app_id)["step"]["id"] == "ap_sanction"


# ── the decision tab (G-W5) ──────────────────────────────────────────────────

def test_the_decision_tab_computes_the_committee_and_takes_manual_deviations(svc):
    app_id = _abce_to(svc, "ap_note")
    rm = _holder(svc, app_id)
    view = svc.decision_view(app_id, rm)
    before = view["committee"]["deviations"]
    assert view["stage"] == "final" and view["can_add_deviation"] and "Credit Sanction Committee" in view["committee"]["required"]
    with pytest.raises(InvalidRequestError, match="justification"):
        svc.save_deviation(app_id, rm, {"type": "pricing", "description": "Spread below grid", "justification": ""})
    svc.save_deviation(app_id, rm, {"type": "pricing", "description": "Spread 25 bps below the grid",
                                    "justification": "Relationship pricing; full-banking mandate"})
    view = svc.decision_view(app_id, rm)
    assert view["committee"]["deviations"] == before + 1 and view["manual_deviations"][0]["id"] == "MDV-01"
    pack_devs = [d[0] for d in svc.committee_pack(app_id, rm)["deviations"]]
    assert any("Pricing (manual)" in d for d in pack_devs)
    svc.save_deviation(app_id, rm, {"action": "remove", "id": "MDV-01", "reason": "Pricing revised to grid"})
    assert svc.decision_view(app_id, rm)["committee"]["deviations"] == before
    # the remarks history: decisions in order, in the bank's wording, not workspace edits
    history = view["remarks_history"]
    assert history and history[0]["at"] <= history[-1]["at"]
    assert all(h["decision"] for h in history) and not any("Pricing" in (h["remarks"] or "") for h in history)
    # only the IP / AP makers add deviations
    vp = svc.sign_in("u_lpf", "lpf_vp")
    with pytest.raises(ForbiddenError):
        svc.save_deviation(app_id, vp, {"type": "other", "description": "x", "justification": "y"})
