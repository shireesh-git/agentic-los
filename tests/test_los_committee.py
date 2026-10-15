"""LOS Phase 3: review & committee pack, AI committee brief, assessment gate and structured sanction."""

from datetime import datetime

import pytest

from src.application.errors import ConflictError, ForbiddenError, InvalidRequestError
from src.data.company_catalog import seed_company_store
from src.los.committee import build_committee_pack
from src.los.service import LosService, load_workflow
from src.los.store import LosStore
from tests.test_cam_composer import full_case
from tests.test_los_risk_maker import FakeCases, FakeFinalCam

NOW = datetime(2026, 10, 8, 12, 0, 0)


@pytest.fixture(scope="module")
def abce_case():
    return full_case(seed_company_store()["ABCE001"])


class BriefingFinalCam(FakeFinalCam):
    """FakeFinalCam that can also 'interpret' sections (stands in for the guarded LLM narrator)."""

    def interpret(self, entity_id, section_ids):
        final = self.cases.get(entity_id)["final_cam"]
        for s in final["sections"]:
            if s["id"] in section_ids:
                s["ai_interpretation"] = {"text": f"Brief for {s['id']}.", "model": "test-llm", "provenance": "ai"}
        return {"results": {sid: {"status": "ok"} for sid in section_ids}, "final_cam": final}


@pytest.fixture()
def svc(tmp_path, abce_case):
    cases = FakeCases(abce_case)
    service = LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow, seed_company_store(), clock=lambda: NOW,
                         cases=cases, final_cam=BriefingFinalCam(cases))
    service.seed_demo()
    return service


def _abce(svc):
    return next(a for a in svc.list() if a["entity_id"] == "ABCE001")


def _to_committee(svc, override=True):
    """Risk Maker assesses (and overrides one field), reviewer, Post Rating VP and EVP approve → Sanction Committee."""
    app = _abce(svc)
    app_id = app["application_id"]
    maker = svc.sign_in(app["assignee_id"], "risk_analyst")
    svc.start_assessment(app_id, maker)
    svc.wait_for_assessment(app_id, timeout=30)
    if override:
        svc.review_fields(app_id, maker, [{"field_id": "rating.internal_rating_mlra_demo_mapping.internal_risk_rating",
                                           "status": "overridden", "value": "IR-7", "reason": "Order-book visibility"}])
    svc.act(app_id, maker, "submit", comment="Assessment complete; receivable ageing requested.")
    reviewer = svc.sign_in("u_cvp", "risk_reviewer")
    svc.act(app_id, reviewer, "approve", comment="Agree with the reduced limit.")
    svc.act(app_id, svc.sign_in("u_cvp", "crp_vp"), "approve", comment="Post-rating review: rating confirmed.")   # G-W1
    evp = svc.sign_in("u_evp", "evp_recommender")
    svc.act(app_id, evp, "approve", comment="Recommend ₹185 Cr with conditions.")
    return app_id, svc.sign_in("u_cc", "sanction_committee")


# ─── Pack builder ────────────────────────────────────────────────────────────

def test_pack_is_built_from_the_case_and_the_application(abce_case):
    app = {"entity_id": "ABCE001", "field_reviews": {"rating.x.internal_risk_rating": {
        "status": "overridden", "label": "Internal risk rating", "original": "IR-8 (High risk)", "value": "IR-7",
        "reason": "Order-book visibility", "by_name": "Neha Kulkarni", "at": "2026-10-08T12:00:00"}}}
    pack = build_committee_pack(abce_case, abce_case["final_cam"], app, [])
    h = pack["headline"]
    assert (h["decision"], h["requested_cr"], h["recommended_cr"]) == ("REDUCED_MODIFIED", 250.0, 185)
    assert pack["overrides"][0]["value"] == "IR-7" and pack["overrides"][0]["tab"] == "rating"
    assert len(pack["conditions"]["precedent"]) == 7 and len(pack["conditions"]["subsequent"]) == 5
    assert any(d[0].startswith("Policy limit: DSCR") for d in pack["deviations"])
    assert len(pack["trail"]["steps"]) == 9 and pack["recommended_sanction_cr"] == 185
    assert len(pack["risks"]) >= 5 and pack["brief"]["executive_summary"] is None


def test_no_assessment_means_no_pack():
    assert build_committee_pack(None, None, {"entity_id": "X"}, [])["available"] is False


# ─── Gate, flow, brief, sanction ─────────────────────────────────────────────

def test_risk_maker_cannot_submit_without_an_assessment(svc):
    app = _abce(svc)
    maker = svc.sign_in(app["assignee_id"], "risk_analyst")
    with pytest.raises(InvalidRequestError, match="Run the credit assessment"):
        svc.act(app["application_id"], maker, "submit", comment="application_id (test)")


def test_committee_sees_the_pack_with_overrides_and_comments(svc):
    app_id, committee = _to_committee(svc)
    pack = svc.committee_pack(app_id, committee)
    assert pack["at_committee_step"] and pack["can_brief"]
    assert [o["value"] for o in pack["overrides"]] == ["IR-7"] and pack["review_status"]["overridden"] == 1
    said = [c["comment"] for c in pack["comments"]]
    assert "Agree with the reduced limit." in said and "Recommend ₹185 Cr with conditions." in said
    assert svc.committee_pack(app_id, svc.sign_in("u_rm1", "ps_maker"))["can_brief"] is False


def test_committee_brief_is_ai_labelled_and_audited(svc):
    app_id, committee = _to_committee(svc, override=False)
    pack = svc.committee_brief(app_id, committee)
    assert pack["brief"]["executive_summary"]["provenance"] == "ai"
    assert pack["brief"]["final_recommendation"]["text"] == "Brief for final_recommendation."
    assert svc.get(app_id)["events"][0]["action"] == "committee_brief"
    with pytest.raises(ForbiddenError):
        svc.committee_brief(app_id, svc.sign_in("u_evp", "evp_recommender"))     # not the EVP's step any more


def test_sanction_defaults_to_the_recommendation_and_moves_to_application_processing(svc):
    app_id, committee = _to_committee(svc)
    v = svc.act(app_id, committee, "sanction", comment="Sanctioned as recommended.")
    assert v["step"]["id"] == "ap_note"
    s = v["sanctions"]["IP"]
    assert (s["sanctioned_cr"], s["recommended_cr"], s["deviates_from_recommendation"]) == (185.0, 185, False)
    assert svc.get(app_id)["events"][0]["detail"]["sanction"]["sanctioned_cr"] == 185.0


def test_a_different_amount_needs_minutes_and_cannot_exceed_the_request(svc):
    app_id, committee = _to_committee(svc)
    # no remarks: refused (every decision records remarks; a different amount needs the minutes)
    with pytest.raises(InvalidRequestError, match="comment is required|Minutes are required"):
        svc.act(app_id, committee, "sanction", sanctioned_amount_cr=200)
    with pytest.raises(InvalidRequestError, match="cannot exceed"):
        svc.act(app_id, committee, "sanction", sanctioned_amount_cr=300, comment="Higher")
    v = svc.act(app_id, committee, "sanction", sanctioned_amount_cr=200, comment="Committee accepts ₹200 Cr with an "
                                                                                    "additional escrow condition.")
    assert v["sanctions"]["IP"]["sanctioned_cr"] == 200.0 and v["sanctions"]["IP"]["deviates_from_recommendation"]


def test_brief_only_at_review_and_committee_steps(svc):
    app = _abce(svc)
    with pytest.raises(ConflictError, match="review and committee steps"):
        svc.committee_brief(app["application_id"], svc.sign_in(app["assignee_id"], "risk_analyst"))


def test_api_pack_endpoint(tmp_path):
    from fastapi.testclient import TestClient

    from src.api.app import create_app
    from src.application.container import build_container
    container = build_container()
    container.los.seed_demo(force=True)
    http = TestClient(create_app(container))
    token = http.post("/api/los/session", json={"user_id": "u_cc", "role": "sanction_committee"}).json()["token"]
    h = {"X-LOS-Session": token}
    apol = next(a for a in http.get("/api/los/applications?q=APOL", headers=h).json()["applications"])
    pack = http.get(f"/api/los/applications/{apol['application_id']}/committee-pack", headers=h).json()
    assert pack["at_committee_step"] is True and "available" in pack
    r = http.post(f"/api/los/applications/{apol['application_id']}/committee-brief", headers=h)
    assert r.status_code in (409, 200)                     # 409 with the mock LLM (tests never call a real model)
