"""LOS Phase 2a: the credit assessment run from the Risk Maker step and its five read-only tabs."""

import copy
from datetime import datetime

import pytest

from src.application.errors import ConflictError, ForbiddenError
from src.data.company_catalog import seed_company_store
from src.los.risk_maker import build_risk_maker_view
from src.los.service import LosService, load_workflow
from src.los.store import LosStore
from tests.test_cam_composer import full_case

NOW = datetime(2026, 10, 8, 12, 0, 0)


@pytest.fixture(scope="module")
def abce_case():
    return full_case(seed_company_store()["ABCE001"])


def _tab(view, tab_id):
    return next(t for t in view["tabs"] if t["id"] == tab_id)


def _section(tab, title):
    return next(s for s in tab["sections"] if s["title"].startswith(title))


def _field(section, label):
    return next(f for f in section["fields"] if f["label"] == label)


# ─── View builder ────────────────────────────────────────────────────────────

def test_view_has_the_nine_risk_maker_tabs(abce_case):
    view = build_risk_maker_view(abce_case, abce_case["final_cam"])
    assert view["available"] and [t["title"] for t in view["tabs"]] == [
        "Customer Info", "Financial Statements", "Risk Rating", "Project Info", "Security & Collateral",
        "Terms & Covenants", "Pricing & RAROC", "ESMS / ESDD", "Decision Signoff"]
    h = view["headline"]
    assert (h["decision"], h["requested_cr"], h["recommended_cr"]) == ("REDUCED_MODIFIED", 250.0, 185)
    assert h["risk_grade"] == "D" and (h["observations"], h["investigations"], h["challenges"]) == (12, 7, 7)


def test_figures_come_from_the_engines(abce_case):
    view = build_risk_maker_view(abce_case, abce_case["final_cam"])
    fin = _tab(view, "financials")
    margin = next(r for r in _section(fin, "Key financials")["rows"] if r[0] == "EBITDA margin")
    assert margin[-1] == "12.9%"                                     # one margin, from the ratio engine
    dscr = next(r for r in _section(fin, "Key ratios")["rows"] if r[0] == "DSCR")
    assert dscr[-2:] == ["1.67x", "1.19x"] and _section(fin, "Key ratios")["provenance"] == "calculated"
    sec = _tab(view, "security")
    assert _field(_section(sec, "Security cover"), "Hard-security cover (excl. current assets)")["value"] == "0.45x"
    terms = _tab(view, "terms")
    kinds = [r[0] for r in _section(terms, "Terms and conditions")["rows"]]
    assert kinds.count("Condition precedent") == 7 and kinds.count("Condition subsequent") == 5


def test_bank_models_are_synthetic_and_labelled(abce_case):
    view = build_risk_maker_view(abce_case, abce_case["final_cam"])
    rating = _tab(view, "rating")
    mlra, loss = _section(rating, "Internal rating (MLRA)"), _section(rating, "Probability of default")
    assert all(f["provenance"] == "synthetic_demo" for f in mlra["fields"])
    assert _field(mlra, "Internal risk rating")["value"] == "IR-8 (High risk)"
    assert _field(loss, "Probability of default")["provenance"] == "synthetic_demo"
    assert _field(loss, "Expected loss")["value"] == "₹8.32 Cr"        # 185 × 10% × 45%, labelled demo
    assert "not connected" in mlra["note"]


def test_decision_signoff_maps_the_reassessment(abce_case):
    view = build_risk_maker_view(abce_case, abce_case["final_cam"])
    dec = _tab(view, "decision")
    assert _field(_section(dec, "Recommended decision"), "Decision")["value"].startswith("Conditionally Approved")
    lines = " ".join(_section(dec, "Final recommendation")["lines"])
    assert "binding cap:" not in lines and "interest-coverage test" in lines
    assert len(_section(dec, "Why this recommendation")["rows"]) == 9
    assert _field(_section(dec, "Approval note"), "Any deviations from policy")["value"] == "Yes"


def test_no_case_means_not_available():
    assert build_risk_maker_view(None)["available"] is False


# ─── Service: running the assessment from the step ───────────────────────────

class FakeCases:
    """Stands in for CaseService: 'runs' the pipeline by returning a prepared case."""

    def __init__(self, case):
        self.case, self.store, self.runs = case, {}, 0

    def get(self, entity_id):
        return self.store.get(entity_id)

    def run(self, entity_id, on_progress=None):
        self.runs += 1
        for i, name in enumerate(("data_ingestion", "pep_screening", "financial_analysis", "validation",
                                  "benchmark", "policy", "narrative"), start=1):
            on_progress({"type": "agent_start", "agent": name, "step": i, "total": 7})
            on_progress({"type": "agent_complete", "agent": name, "status": "completed"})
        case = copy.deepcopy(self.case)
        case.update(run_id="run-1", run_at="2026-10-08T12:00:00")
        self.store[entity_id] = case
        return case, []


class FakeFinalCam:
    def __init__(self, cases):
        self.cases = cases

    def get(self, entity_id):
        return {"final_cam": self.cases.get(entity_id)["final_cam"]}


@pytest.fixture()
def svc(tmp_path, abce_case):
    cases = FakeCases(abce_case)
    service = LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow, seed_company_store(), clock=lambda: NOW,
                         cases=cases, final_cam=FakeFinalCam(cases))
    service.seed_demo()
    return service


def _abce(svc):
    return next(a for a in svc.list() if a["entity_id"] == "ABCE001")


def test_risk_maker_runs_the_assessment_and_it_is_audited(svc):
    app = _abce(svc)
    analyst = svc.sign_in(app["assignee_id"], "risk_analyst")
    before = svc.assessment(app["application_id"], analyst)
    assert before["can_run"] and before["view"]["available"] is False
    svc.start_assessment(app["application_id"], analyst)
    job = svc.wait_for_assessment(app["application_id"], timeout=30)
    assert job["state"] == "done" and job["progress"] == 100 and job["run_id"] == "run-1"
    after = svc.assessment(app["application_id"], analyst)
    assert after["view"]["available"] and after["recorded"]["decision"] == "REDUCED_MODIFIED"
    actions = [e["action"] for e in svc.get(app["application_id"])["events"]]
    assert actions[:2] == ["assessment", "assessment_started"]


def test_only_the_risk_maker_can_run_it(svc):
    app = _abce(svc)
    reviewer = svc.sign_in("u_cvp", "risk_reviewer")
    assert svc.assessment(app["application_id"], reviewer)["can_run"] is False
    with pytest.raises(ForbiddenError):
        svc.start_assessment(app["application_id"], reviewer)
    apol = next(a for a in svc.list() if a["entity_id"] == "APOL001")             # at the sanction committee
    with pytest.raises(ConflictError, match="Risk Maker step"):
        svc.start_assessment(apol["application_id"], svc.sign_in("u_cc", "sanction_committee"))


def test_failed_run_is_recorded(svc):
    app = _abce(svc)
    analyst = svc.sign_in(app["assignee_id"], "risk_analyst")

    def boom(entity_id, on_progress=None):
        raise RuntimeError("pipeline unavailable")
    svc.cases.run = boom
    svc.start_assessment(app["application_id"], analyst)
    job = svc.wait_for_assessment(app["application_id"], timeout=30)
    assert job["state"] == "failed" and "pipeline unavailable" in job["error"]
    assert svc.get(app["application_id"])["events"][0]["action"] == "assessment_failed"
