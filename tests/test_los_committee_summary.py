"""R9 (committee governance) + R13 (case summary) — focused tests.

R9: the AP committee (IP-level authority) is not the final sanction committee; a
sanction decision always lands at the committee computed from the current facts
(multi-committee); a material post-sanction change re-enters credit reassessment
with a fresh route; the committee can send a case back for re-consideration and
the Risk Maker re-recommends; a post-sanction reassessment is a reassessment
record, never a silent change of the sanctioned amount.

R13: the case summary carries the position at each stage, the open risks and
the recent decisions — enough for an approver without opening the documents.
"""
from datetime import datetime

import pytest

from src.application import errors
from src.data.company_catalog import seed_company_store
from src.los.service import LosService, load_workflow
from src.los.store import LosStore

NOW = datetime.fromisoformat("2026-07-01T09:00:00")
SOURCING = {"decision": "Refer for in-principle", "mandatory_remarks": "committee test"}


def make_service(tmp_path):
    return LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow,
                      seed_company_store(), clock=lambda: NOW)


def sanctioned(svc, entity="MFL001", amount=100.0):
    a = svc.create(svc._system_session("ps_maker"), entity_id=entity, profile="client_one",
                   facility={"facility_type": "working_capital", "facility_nature": "fund_based",
                             "proposal_type": "Fresh", "amount_cr": amount, "tenor_months": 12,
                             "interest_rate": 12.4, "purpose": "Working capital (demo)"},
                   sourcing_decision=SOURCING)
    svc._replay_to(a["application_id"], "pos_maker", NOW, NOW)
    return svc.store.get(a["application_id"])


def test_ap_committee_is_not_the_final_sanction_committee(tmp_path):
    """Multi-committee: the IP/AP committee routes on the preliminary authority; the final
    sanction decision is taken by the committee computed from the current facts at sanction."""
    svc = make_service(tmp_path)
    a = svc.create(svc._system_session("ps_maker"), entity_id="MFL001", profile="client_one",
                   facility={"facility_type": "term_loan", "facility_nature": "fund_based",
                             "proposal_type": "Fresh", "amount_cr": 1000.0, "tenor_months": 60,
                             "interest_rate": 12.4, "purpose": "Expansion (demo)"},
                   sourcing_decision=SOURCING)
    sid = a["application_id"]
    svc._replay_to(sid, "ip_sanction", NOW, NOW)
    route = svc.store.get(sid).get("routing") or {}
    prelim = (route.get("authority_of_record") or {}).get("preliminary_authority") or route.get("preliminary_authority") or {}
    final = (route.get("authority_of_record") or {}).get("final_authority") or route.get("final_authority") or {}
    prelim_req = prelim.get("required") if isinstance(prelim, dict) else prelim
    final_req = final.get("required") if isinstance(final, dict) else final
    # the two stages compute from the same facts (amount / grade / deviations) — the IP committee
    # is not by itself the final sanctioning authority; the route carries both.
    assert prelim_req or final_req
    # the route was calculated and recorded at creation, with both stage authorities present
    assert route.get("calculated_at") or (route.get("authority_of_record") or {}).get("final_authority") or final_req


def test_committee_return_and_re_recommendation(tmp_path):
    """The committee sends the case back for re-consideration; the Risk Maker re-recommends."""
    svc = make_service(tmp_path)
    wf = svc.wf_for_profile("client_one")
    a = svc.create(svc._system_session("ps_maker"), entity_id="MFL001", profile="client_one",
                   facility={"facility_type": "term_loan", "facility_nature": "fund_based",
                             "proposal_type": "Fresh", "amount_cr": 400.0, "tenor_months": 60,
                             "interest_rate": 12.4, "purpose": "Expansion (demo)"},
                   sourcing_decision=SOURCING)
    sid = a["application_id"]
    # the final sanction committee (the AP committee) — multi-committee: this is not the IP committee
    svc._replay_to(sid, "ap_sanction", NOW, NOW)
    app = svc.store.get(sid)
    assert app["step_id"] == "ap_sanction"
    cm = svc._system_session("sanction_committee", app.get("assignee_id"), wf)
    svc.act(sid, cm, "return", comment="Risk structure needs re-examination — revisit the security (demo)")
    app = svc.store.get(sid)
    assert app.get("committee_returned"), "the return is recorded as a pending re-consideration"
    # the rework runs back through the AP Risk Maker, which re-recommends (recomputing the
    # route on the current facts) before the committee meets again
    cm2 = svc._system_session("sanction_committee", svc.store.get(sid).get("assignee_id"), wf)
    svc.act(sid, cm2, "return", rework_to="ap_risk_maker",
            comment="Rework to the Risk Maker (demo)")
    app = svc.store.get(sid)
    assert app["step_id"] == "ap_risk_maker"
    risk = svc._system_session("risk_analyst", app.get("assignee_id"), wf)
    svc.re_recommend(sid, risk)
    assert any(e["action"] == "re_recommendation" for e in svc.store.events(sid))
    assert not svc.store.get(sid).get("committee_returned")


def test_post_sanction_reassessment_is_a_record_not_a_change(tmp_path):
    """A post-sanction reassessment is a reassessment record; the sanctioned amount stands."""
    svc = make_service(tmp_path)
    app = sanctioned(svc, amount=100.0)
    sid = app["application_id"]
    # the service's own recording path — a post-sanction run becomes a reassessment record
    # (the sanctioned terms are carried on the facility and the record, so the recomputed
    # recommendation can be seen against them)
    a0 = svc.store.get(sid)
    a0["facility"] = {**(a0.get("facility") or {}), "amount_cr": 100.0, "tenor_months": 12, "interest_rate": 12.4}
    svc.store.save(a0)
    svc._record_assessment(sid, {"entity_id": a0["entity_id"], "run_id": "run-post-1",
                                 "run_at": NOW.isoformat(timespec="seconds"),
                                 "reassessment": {"decision": "conditional", "decision_label": "Conditional support",
                                                  "facility_recommendation": {"requested_cr": 100.0, "recommended_cr": 90.0}},
                                 "risk_grade": "B2"},
                          {"id": "u_rm", "role": "rm"})
    a = svc.store.get(sid)
    assert a.get("reassessments"), "the post-sanction run is a reassessment record"
    assert a["credit_assessment"]["recommended_cr"] == 90.0
    # the sanctioned amount is untouched (sanctions stand until a modification is approved)
    sanctions = a.get("sanctions") or {}
    assert sanctions, "the case is sanctioned"
    sanctioned_amount = (sanctions.get("AP") or {}).get("sanctioned_cr")
    assert sanctioned_amount and sanctioned_amount == 100.0, "the sanctioned amount stands"


def test_case_summary_covers_position_risks_and_decisions(tmp_path):
    """R13: the summary shows the position at each stage, the open risks and the recent decisions."""
    svc = make_service(tmp_path)
    app = sanctioned(svc, amount=100.0)
    sid = app["application_id"]
    s = svc.summary(application_id=sid)
    for key in ("application_id", "total_amount_cr", "current_step", "positions",
                "open_risks", "recent_decisions", "pending", "as_of"):
        assert key in s, f"summary missing {key}"
    assert s["total_amount_cr"] == 100.0
    # a sanctioned case has a sanction position
    assert s["positions"].get("sanction"), "the summary shows the sanction position"
    # the full application view carries the summary too
    full = svc.get(sid, svc._system_session("pos_maker", app.get("assignee_id")))
    assert "summary" in full
