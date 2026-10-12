"""LOS Phase 2b: Customer Info, Project Info, Pricing & RAROC, ESMS / ESDD tabs and analyst field review."""

import copy
from datetime import datetime

import pytest

from src.application.errors import ConflictError, ForbiddenError, InvalidRequestError
from src.data.company_catalog import seed_company_store
from src.los.risk_maker import build_risk_maker_view
from src.los.service import LosService, load_workflow
from src.los.store import LosStore
from tests.test_cam_composer import full_case
from tests.test_los_risk_maker import FakeCases, FakeFinalCam, _field, _section, _tab

NOW = datetime(2026, 10, 8, 12, 0, 0)


@pytest.fixture(scope="module")
def abce_case():
    return full_case(seed_company_store()["ABCE001"])


@pytest.fixture(scope="module")
def view(abce_case):
    return build_risk_maker_view(abce_case, abce_case["final_cam"],
                                 {"relationship_manager": "Ananya Rao", "other_applications": []})


# ─── New tabs ────────────────────────────────────────────────────────────────

def test_customer_info_uses_the_evidence_based_rules(view):
    tab = _tab(view, "customer")
    info, checks = _section(tab, "Customer information"), _section(tab, "KYC & verification")
    assert _field(info, "Name of applicant")["value"] == "ABC Engineering & Infrastructure Ltd."
    assert _field(info, "Relationship manager")["value"] == "Ananya Rao"
    for label in ("PAN verification (NSDL)", "CERSAI check", "CBS dedupe", "AML screening"):
        assert _field(checks, label)["provenance"] == "unavailable", label        # systems not connected
    assert _field(checks, "LOS dedupe")["value"] == "No other applications"
    assert _field(checks, "Politically exposed person")["value"].startswith("0 match(es)")


def test_pricing_and_raroc_are_a_labelled_demo(view):
    tab = _tab(view, "pricing")
    rate, rar = _section(tab, "Rate of interest"), _section(tab, "RAROC")
    assert _field(rate, "Spread for the risk grade")["value"] == "250 bps"           # grade D
    assert _field(rate, "Rate of interest")["value"] == "10.9%"                      # 8.40 + 2.50
    assert _field(rar, "Expected loss rate")["value"] == "4.5%"                      # 10% × 45%
    assert _field(rar, "RAROC")["value"] == "-10.8%"                                 # (10.9 − 7.2 − 4.5 − 0.5) / 12
    assert _field(rar, "Meets hurdle")["value"] == "No"
    demo = [f for s in tab["sections"] for f in s["fields"] if f["label"] != "Exposure priced"
            and not f["label"].endswith("(standard card)")]
    assert all(f["provenance"] == "synthetic_demo" for f in demo)


def test_esms_categorises_by_sector_rule_and_leaves_evidence_unavailable(view):
    tab = _tab(view, "esms")
    cat = _section(tab, "E&S categorisation")
    assert _field(cat, "E&S category")["value"] == "Category B" and _field(cat, "ESDD required")["value"] == "Yes"
    ev = _section(tab, "E&S evidence")
    assert _field(ev, "Environmental clearances")["provenance"] == "unavailable"
    assert _field(ev, "Labour disputes")["provenance"] == "unavailable"              # no assumed "False"


def test_project_info_does_not_invent_a_project_cost(view):
    fac = _section(_tab(view, "project"), "Facility and project")
    assert _field(fac, "Project cost")["provenance"] == "unavailable"
    assert _field(fac, "Means of finance")["provenance"] == "unavailable"


def test_field_ids_are_stable_and_unique(view, abce_case):
    ids = [f["id"] for t in view["tabs"] for s in t["sections"] for f in s.get("fields") or []]
    assert len(ids) == len(set(ids)) and "rating.internal_rating_mlra_demo_mapping.internal_risk_rating" in ids
    again = build_risk_maker_view(copy.deepcopy(abce_case), abce_case["final_cam"])
    assert ids == [f["id"] for t in again["tabs"] for s in t["sections"] for f in s.get("fields") or []]


# ─── Analyst review ──────────────────────────────────────────────────────────

@pytest.fixture()
def svc(tmp_path, abce_case):
    cases = FakeCases(abce_case)
    service = LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow, seed_company_store(), clock=lambda: NOW,
                         cases=cases, final_cam=FakeFinalCam(cases))
    service.seed_demo()
    return service


@pytest.fixture()
def assessed(svc):
    app = next(a for a in svc.list() if a["entity_id"] == "ABCE001")
    analyst = svc.sign_in(app["assignee_id"], "risk_analyst")
    svc.start_assessment(app["application_id"], analyst)
    svc.wait_for_assessment(app["application_id"], timeout=30)
    return app["application_id"], analyst


RATING = "rating.internal_rating_mlra_demo_mapping.internal_risk_rating"
GRADE = "rating.scoring_model_credit_intelligence_engine.risk_grade"


def _find(result, field_id):
    return next(f for t in result["view"]["tabs"] for s in t["sections"] for f in s.get("fields") or []
                if f["id"] == field_id)


def test_confirm_and_override_are_recorded_and_audited(svc, assessed):
    app_id, analyst = assessed
    out = svc.review_fields(app_id, analyst, [
        {"field_id": GRADE, "status": "confirmed"},
        {"field_id": RATING, "status": "overridden", "value": "IR-7", "reason": "Committee guidance for EPC sector"}])
    assert out["review_summary"]["confirmed"] == 1 and out["review_summary"]["overridden"] == 1
    rating = _find(out, RATING)
    assert rating["review"]["value"] == "IR-7" and rating["review"]["original"] == "IR-8 (High risk)"
    assert rating["value"] == "IR-8 (High risk)"                         # the engine value is never changed
    event = svc.get(app_id)["events"][0]
    assert event["action"] == "field_review" and "IR-8 (High risk) → IR-7" in event["comment"]
    tab = next(t for t in out["view"]["tabs"] if t["id"] == "rating")
    assert tab["review_counts"]["reviewed"] == 2


def test_override_needs_a_value_and_a_reason(svc, assessed):
    app_id, analyst = assessed
    with pytest.raises(InvalidRequestError, match="needs a value and a reason"):
        svc.review_fields(app_id, analyst, [{"field_id": RATING, "status": "overridden", "value": "IR-7"}])
    with pytest.raises(InvalidRequestError, match="Unknown field"):
        svc.review_fields(app_id, analyst, [{"field_id": "nope", "status": "confirmed"}])


def test_only_the_assigned_risk_maker_reviews(svc, assessed):
    app_id, _ = assessed
    reviewer = svc.sign_in("u_cvp", "risk_reviewer")
    assert svc.assessment(app_id, reviewer)["can_review"] is False
    with pytest.raises(ForbiddenError):
        svc.review_fields(app_id, reviewer, [{"field_id": GRADE, "status": "confirmed"}])
    apol = next(a for a in svc.list() if a["entity_id"] == "APOL001")
    with pytest.raises(ConflictError, match="Risk Maker step"):
        svc.review_fields(apol["application_id"], svc.sign_in("u_cc", "sanction_committee"),
                          [{"field_id": GRADE, "status": "confirmed"}])


def test_a_review_goes_stale_when_the_value_changes_and_can_be_cleared(svc, assessed):
    app_id, analyst = assessed
    svc.review_fields(app_id, analyst, [{"field_id": GRADE, "status": "confirmed"}])
    case = svc.cases.store["ABCE001"]
    case["fact_pack"]["policy_decisions"]["tier3_recommendation"]["risk_grade"] = "C"   # a re-run changes the grade
    out = svc.assessment(app_id, analyst)
    assert _find(out, GRADE)["review"]["stale"] is True and out["review_summary"]["stale"] == 1
    out = svc.review_fields(app_id, analyst, [{"field_id": GRADE, "status": "clear"}])
    assert "review" not in _find(out, GRADE) and out["review_summary"]["stale"] == 0


def test_reviews_need_an_assessment(svc):
    app = next(a for a in svc.list() if a["entity_id"] == "ABCE001")
    analyst = svc.sign_in(app["assignee_id"], "risk_analyst")
    with pytest.raises(ConflictError, match="Run the credit assessment"):
        svc.review_fields(app["application_id"], analyst, [{"field_id": GRADE, "status": "confirmed"}])
