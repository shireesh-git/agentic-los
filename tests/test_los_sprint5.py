"""Sprint 5: the process rules in the workflow (defer, drop, remarks, decision fields, read-only
reviewers, the IP Note gate) and the feedback loop (a verified value re-runs the credit case)."""

import copy
from datetime import datetime

import pytest

from src.agents.financial_overrides import apply_uploaded_financial_overrides, apply_verified_overrides
from src.application.errors import ForbiddenError, InvalidRequestError
from src.data.company_catalog import seed_company_store
from src.los.service import LosService, load_workflow
from src.los.store import LosStore
from src.los.workflow import STATUS_DEFERRED, STATUS_DROPPED
from tests.test_cam_composer import full_case
from tests.test_los_fields import RunCases, RunFinalCam

NOW = datetime(2026, 10, 8, 12, 0, 0)


@pytest.fixture(scope="module")
def abce():
    return seed_company_store()["ABCE001"]


class OverrideCases(RunCases):
    """Runs the (template) case on the borrower record with the run's verified overrides applied."""

    def __init__(self, case, company):
        super().__init__(case)
        self.company, self.seen = company, []

    def run(self, entity_id, on_progress=None, overrides=None):
        self.seen.append(overrides)
        company = copy.deepcopy(self.company)
        if overrides:
            apply_verified_overrides(company, overrides)
        self.case = full_case(company)
        return super().run(entity_id, on_progress)


@pytest.fixture()
def svc(tmp_path, abce):
    cases = OverrideCases(full_case(abce), abce)
    service = LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow, seed_company_store(), clock=lambda: NOW,
                         cases=cases, final_cam=RunFinalCam(cases))
    service.seed_demo()
    return service


def _app(svc, entity):
    return next(a for a in svc.list() if a["entity_id"] == entity)


def _rm(svc):
    app = _app(svc, "IHCL001")                                       # seeded at Prospect Sourcing
    return app["application_id"], svc.sign_in(app["assignee_id"], "ps_maker")


# ── workflow ─────────────────────────────────────────────────────────────────

def test_every_decision_records_remarks(svc):
    app_id, rm = _rm(svc)
    with pytest.raises(InvalidRequestError, match="comment is required to submit"):
        svc.act(app_id, rm, "submit")


def test_defer_holds_the_application_until_reactivated(svc):
    app_id, rm = _rm(svc)
    with pytest.raises(InvalidRequestError, match="date to take the application up again"):
        svc.act(app_id, rm, "defer", comment="Awaiting audited FY26 accounts")
    with pytest.raises(InvalidRequestError, match="in the future"):
        svc.act(app_id, rm, "defer", comment="x", deferred_until="2026-10-01")
    v = svc.act(app_id, rm, "defer", comment="Awaiting audited FY26 accounts", deferred_until="2026-11-15")
    assert v["status"] == STATUS_DEFERRED and v["step"]["id"] == "ps_maker"
    assert v["actions"] == ["reactivate"] and v["sla"] is None                # on hold: SLA paused
    assert v["deferral"]["until"] == "2026-11-15" and v["deferral"]["by_name"]
    assert v["assignee_id"] == rm["user"]["id"]                              # still the RM's case while on hold
    with pytest.raises(InvalidRequestError, match="deferred"):
        svc.act(app_id, rm, "submit", comment="x")
    v = svc.act(app_id, rm, "reactivate", comment="Accounts received")
    assert v["status"] != STATUS_DEFERRED and "submit" in v["actions"] and v["sla"]
    assert svc.get(app_id)["deferrals"][-1]["reactivated_by"]
    assert [e["action"] for e in svc.get(app_id)["events"][:2]] == ["reactivate", "defer"]


def test_a_maker_can_drop_with_a_reason(svc):
    app_id, rm = _rm(svc)
    v = svc.act(app_id, rm, "drop", comment="Prospect not pursued: pricing not acceptable")
    assert v["status"] == STATUS_DROPPED and v["terminated"]["reason"].startswith("Prospect not pursued")


def test_review_decision_fields_are_recorded_and_required_ones_enforced(svc):
    from tests.test_los_post_sanction import _abce_to, _holder
    app_id = _abce_to(svc, "ap_review")
    vp = _holder(svc, app_id)
    assert [f["id"] for f in svc.get(app_id, vp)["decision_fields"]][0] == "material_information_date"
    with pytest.raises(InvalidRequestError, match="Date of receipt of last material information is required"):
        svc.act(app_id, vp, "approve", comment="Appraisal reviewed")
    svc.act(app_id, vp, "approve", comment="Appraisal reviewed",
            decision_data={"material_information_date": "2026-09-30", "significant_changes": "Tenor 84 → 72 months",
                           "committee_matters": "None", "approval_purpose": "Fresh term loan"})
    d = svc.get(app_id)["decisions"][-1]
    assert (d["step"], d["material_information_date"], d["significant_changes"]) == \
        ("ap_review", "2026-09-30", "Tenor 84 → 72 months")
    assert svc.get(app_id)["events"][0]["detail"]["material_information_date"] == "2026-09-30"


def test_reviewers_are_read_only_on_the_proposal(svc):
    from tests.test_los_post_sanction import _abce_to, _holder
    app_id = _abce_to(svc, "ap_review")
    vp = _holder(svc, app_id)
    with pytest.raises(ForbiddenError, match="read-only"):
        svc.save_security(app_id, vp, {"category": "collateral", "type": "deposit", "proposed_value_cr": 5})
    with pytest.raises(ForbiddenError, match="read-only"):
        svc.update_proposal(app_id, vp, "summary", {"purpose": "changed by a reviewer"})


def test_ip_note_needs_its_documents_and_resolved_checks(svc):
    app = _app(svc, "ABCE001")
    rec = svc._require(app["application_id"])
    rec.update(step_id="ip_note", stage_id="IP", assignee_id="u_rm1", status="IN_PROGRESS", documents=[])
    svc.store.save(rec, svc._event(rec, "test_setup", actor={"id": None, "role": "test"}))
    rm = svc.sign_in("u_rm1", "ps_maker")
    svc.generate_ip_note(app["application_id"], rm, with_ai=False)
    with pytest.raises(InvalidRequestError, match="due-diligence|Mandatory documents"):
        svc.act(app["application_id"], rm, "submit", comment="IP proposal ready")


# ── feedback loop ────────────────────────────────────────────────────────────

def test_verified_overrides_win_over_extraction(abce):
    company = copy.deepcopy(abce)
    period = sorted(company["financials"])[-1]
    applied = apply_verified_overrides(company, {"financials": {period: {"revenue_operating": 1234.5}}})
    assert applied["financials"] == [f"{period}.revenue_operating"]
    extraction = {"financials": {"audited": {"revenue": [999.0], "pat": [10.0]}},
                  "selected_documents": {"audited_financials": f"financials/audited_{period.lower()}.pdf"}}
    apply_uploaded_financial_overrides(company, extraction)
    li = company["financials"][period].line_items
    assert li["revenue_operating"] == 1234.5                            # the person's value stands over the extraction


def test_an_overridden_revenue_reruns_the_case_for_this_application(svc, abce):
    app = _app(svc, "ABCE001")
    analyst = svc.sign_in(app["assignee_id"], "risk_analyst")
    svc.start_assessment(app["application_id"], analyst)
    svc.wait_for_assessment(app["application_id"], timeout=60)
    period = sorted(abce["financials"])[-1]
    fid = f"cma.borrower.{period}.revenue"
    old_revenue = svc.get(app["application_id"])["fields"][fid]["value"]
    svc.verify_fields(app["application_id"], analyst,
                      [{"field_id": fid, "action": "override", "value": str(round(old_revenue * 0.8, 2)),
                        "reason": "Audited revenue net of GST per the signed statements"}])
    job = svc.wait_for_assessment(app["application_id"], timeout=60)
    assert job["state"] == "done" and job["reason"].startswith("Re-running the credit case")
    assert svc.cases.seen[-1] == {"financials": {period: {"revenue_operating": round(old_revenue * 0.8, 2)}}}
    got = svc.get(app["application_id"])
    assert got["credit_assessment"]["run_id"] == "run-2"                 # the new run is pinned
    assert got["fields"][fid]["value"] == str(round(old_revenue * 0.8, 2))  # the person's value stands
    case = svc.cases.runs_by_id["run-2"]
    assert case["fact_pack"]["financial_summary"]["periods"][period]["revenue_cr"] == round(old_revenue * 0.8, 2)
    events = [e["action"] for e in got["events"]]
    assert events.index("fields_verified") > events.index("assessment")    # verified first, then re-run
