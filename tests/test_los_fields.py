"""Populate → Verify → Lock: field registry, FieldValue merge rules, verify actions, the
verify queue, the population graph and the credit case pinned to the application."""

import copy
from datetime import datetime

import pytest

from src.application.errors import ConflictError, ForbiddenError, InvalidRequestError, NotFoundError
from src.data.company_catalog import seed_company_store
from src.engines.data_provenance import NOT_AVAILABLE
from src.los.fields import model as fm
from src.los.fields.population import run_population
from src.los.fields.registry import FieldRegistry
from src.los.fields.resolvers import risk_maker_proposals
from src.los.risk_maker import build_risk_maker_view
from src.los.service import LosService, load_workflow
from src.los.store import LosStore
from tests.test_cam_composer import full_case
from tests.test_los_risk_maker import FakeCases, FakeFinalCam

NOW = datetime(2026, 10, 8, 12, 0, 0)
AT = "2026-10-08T12:00:00"
GRADE = "rating.scoring_model_credit_intelligence_engine.risk_grade"
RATING = "rating.internal_rating_mlra_demo_mapping.internal_risk_rating"
NAME = "customer.customer_information.name_of_applicant"
CIN = "customer.customer_information.cin"
ME = {"id": "u1", "name": "Neha"}


@pytest.fixture(scope="module")
def abce_case():
    return full_case(seed_company_store()["ABCE001"])


@pytest.fixture(scope="module")
def view(abce_case):
    return build_risk_maker_view(abce_case, abce_case["final_cam"], {"relationship_manager": "Ananya Rao"})


@pytest.fixture(scope="module")
def registry():
    return FieldRegistry.load()


def _p(fid, value, provenance="derived", confidence=0.9, **kw):
    return {"field_id": fid, "label": fid.rsplit(".", 1)[-1], "value": value, "provenance": provenance,
            "source": "engine", "evidence": {"engine": "test"}, "confidence": confidence, "resolver": "t", **kw}


# ── registry ─────────────────────────────────────────────────────────────────

def test_registry_policies_name_real_fields(registry, view, abce_case, tmp_path):
    abce = abce_case
    from src.los import intake
    from src.los.sourcing import FIELDS as SOURCING_FIELDS

    ids = {f["id"] for t in view["tabs"] for s in t["sections"] for f in s.get("fields") or []}
    ids |= {intake.field_id(f) for f in SOURCING_FIELDS}
    from src.los import reconcile
    ctx = {"case": abce, "fact_pack": abce["fact_pack"], "company": seed_company_store()["ABCE001"],
           "app": {"facilities": [{"facility_id": "FAC-001", "facility_nature": "fund_based"}], "borrower_name": "ABC"},
           "registry": registry, "today": "2026-10-08"}
    ids |= {p["field_id"] for fn in reconcile.RESOLVERS.values() for p in fn(ctx)}
    from src.los import prefill                                                  # the IP / AP pre-fill agents
    pctx = {**ctx, "case": abce, "prefill_values": {}, "app": {**ctx["app"], "facilities": [
        {"facility_id": "FAC-001", "facility_nature": "fund_based", "facility_type": "term_loan",
         "purpose": "Expansion (new plant in Pune)", "amount_cr": 10, "tenor_months": 60}]}}
    ids |= {p["field_id"] for fn in prefill.RESOLVERS.values() for p in fn(pctx)}
    from src.devtools.demo_documents import write_set
    from src.los import cam_intake
    write_set(tmp_path, only=("cam/credit_appraisal_memo.pdf",), include_cam=True)     # the CAM intake agent
    ids |= {p["field_id"] for p in cam_intake.proposals(cam_intake.read_cams(tmp_path))}
    listed = set(registry._fields)
    assert listed and listed <= ids, f"registry lists unknown field ids: {sorted(listed - ids)}"
    assert registry.spec(GRADE).verify == "must_verify" and registry.spec(NAME).verify == "bulk"
    assert "rating" in registry.domains_verified_at("ip_risk_maker")
    assert registry.domains_verified_at("ps_maker") == ["sourcing"]          # the intake agent's fields
    assert registry.domains_verified_at("pos_maker") == ["post_sanction"]    # the later-stage intake (S6)
    assert not registry.domains_verified_at("pos_checker")


def test_bad_policy_is_rejected():
    with pytest.raises(ValueError):
        FieldRegistry({"fields": {"x.y.z": {"verify": "maybe"}}})


# ── merge rules ──────────────────────────────────────────────────────────────

def test_merge_new_update_and_unavailable(registry):
    fields = {}
    s = fm.merge(fields, [_p(NAME, "ABC Ltd"), _p(CIN, NOT_AVAILABLE, "unavailable", 0)], registry, AT)
    assert s["new"] == 2 and fields[NAME]["status"] == "proposed" and fields[CIN]["status"] == "unavailable"
    s = fm.merge(fields, [_p(NAME, "ABC Limited")], registry, AT)
    assert s["updated"] == 1 and fields[NAME]["value"] == "ABC Limited"


def test_a_decided_value_is_never_overwritten_and_conflicts_resolve(registry):
    fields = {}
    fm.merge(fields, [_p(GRADE, "D")], registry, AT)
    fm.apply_action(fields[GRADE], "override", by=ME, at=AT, registry=registry, value="C", reason="peer data")
    s = fm.merge(fields, [_p(GRADE, "D")], registry, AT)            # same proposal: nothing changes
    assert s["unchanged"] == 1 and fields[GRADE]["value"] == "C" and fields[GRADE]["status"] == "overridden"
    s = fm.merge(fields, [_p(GRADE, "E")], registry, AT)            # the engine now says E
    assert s["conflicts"] == 1 and fields[GRADE]["status"] == "conflict" and fields[GRADE]["value"] == "C"
    s = fm.merge(fields, [_p(GRADE, "D")], registry, AT)            # back to what the person decided on
    assert s["resolved"] == 1 and fields[GRADE]["status"] == "overridden"


def test_verify_actions(registry):
    fields = {}
    fm.merge(fields, [_p(GRADE, "D"), _p(NAME, "ABC")], registry, AT)
    with pytest.raises(fm.FieldActionError, match="needs a value and a reason"):
        fm.apply_action(fields[GRADE], "override", by=ME, at=AT, registry=registry, value="C")
    with pytest.raises(fm.FieldActionError, match="no conflict"):
        fm.apply_action(fields[GRADE], "keep", by=ME, at=AT, registry=registry, reason="x")
    fm.apply_action(fields[GRADE], "confirm", by=ME, at=AT, registry=registry)
    assert fields[GRADE]["decision"]["basis"] == "D" and fields[GRADE]["decision"]["by_name"] == "Neha"
    fm.merge(fields, [_p(GRADE, "E")], registry, AT)
    with pytest.raises(fm.FieldActionError, match="needs a reason"):
        fm.apply_action(fields[GRADE], "keep", by=ME, at=AT, registry=registry)
    fm.apply_action(fields[GRADE], "keep", by=ME, at=AT, registry=registry, reason="E is a data error")
    assert fields[GRADE]["status"] == "overridden" and fields[GRADE]["value"] == "D"
    assert fields[GRADE]["decision"]["basis"] == "E"                # decided against the new proposal
    fm.apply_action(fields[GRADE], "reopen", by=ME, at=AT, registry=registry)
    assert fields[GRADE]["status"] == "proposed" and fields[GRADE]["value"] == "E"
    assert [h["event"] for h in fields[GRADE]["history"]][-3:] == ["conflict", "kept", "reopened"]


def test_queue_order_preticks_and_stats(registry):
    fields = {}
    fm.merge(fields, [_p(NAME, "ABC", "source", 0.95), _p(GRADE, "D", confidence=0.95),
                      _p(RATING, "IR-8", "synthetic_demo", 0.4),
                      _p("customer.customer_information.pan", "AAACX", "source", 0.95, issues=["no path"]),
                      _p(CIN, NOT_AVAILABLE, "unavailable", 0)], registry, AT)
    q = fm.queue(fields, registry, "ip_risk_maker")
    assert {i["field_id"] for i in q[:2]} == {GRADE, RATING}           # decision-driving first
    by_id = {i["field_id"]: i for i in q}
    assert CIN not in by_id                                           # nothing to verify on a gap
    assert by_id[NAME]["preticked"] and by_id[NAME]["bulk"]
    assert not by_id[GRADE]["preticked"] and not by_id[GRADE]["bulk"]           # must_verify
    assert not by_id["customer.customer_information.pan"]["preticked"]          # critic issue
    assert fm.queue(fields, registry, "ps_maker") == []                        # not verified at that step
    s = fm.stats(fields, registry)
    assert s["total"] == 5 and s["populated"] == 4 and s["populated_pct"] == 80.0 and s["preticked"] == 1


# ── population graph ─────────────────────────────────────────────────────────

def test_population_runs_resolvers_in_parallel_and_critic_checks(registry, view):
    def other(ctx):
        return [_p(NAME, "Someone else"), _p("customer.customer_information.cin", "U12345", source="record",
                                               evidence={})]

    result = run_population({"risk_maker": lambda ctx: risk_maker_proposals(view, registry),
                             "other": other}, registry)
    by_id = {p["field_id"]: p for p in result["proposals"]}
    assert by_id[NAME]["value"] == "ABC Engineering & Infrastructure Ltd."     # first resolver wins
    assert by_id[GRADE]["issues"] == [] and by_id[GRADE]["evidence"]["engine"]
    assert not result["failed"] and result["max_concurrency"] >= 2
    assert len(by_id) == len({f["id"] for t in view["tabs"] for s in t["sections"] for f in s.get("fields") or []})


# ── service: populate, verify, bulk confirm, pinning ─────────────────────────

class RunCases(FakeCases):
    """FakeCases that keeps every run, so an application can stay pinned to its own."""

    def __init__(self, case):
        super().__init__(case)
        self.runs_by_id = {}

    def run(self, entity_id, on_progress=None):
        self.runs += 1
        case = copy.deepcopy(self.case)
        case.update(run_id=f"run-{self.runs}", run_at="2026-10-08T12:00:00")
        self.store[entity_id] = self.runs_by_id[case["run_id"]] = case
        return case, []

    def get_run(self, entity_id, run_id):
        if run_id not in self.runs_by_id:
            raise NotFoundError(run_id)
        return self.runs_by_id[run_id]


class RunFinalCam(FakeFinalCam):
    def get(self, entity_id, run_id=None):
        case = self.cases.runs_by_id[run_id] if run_id else self.cases.get(entity_id)
        return {"final_cam": case["final_cam"]}


@pytest.fixture()
def svc(tmp_path, abce_case):
    cases = RunCases(abce_case)
    service = LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow, seed_company_store(), clock=lambda: NOW,
                         cases=cases, final_cam=RunFinalCam(cases))
    service.seed_demo()
    return service


@pytest.fixture()
def assessed(svc):
    app = next(a for a in svc.list() if a["entity_id"] == "ABCE001")
    analyst = svc.sign_in(app["assignee_id"], "risk_analyst")
    svc.start_assessment(app["application_id"], analyst)
    svc.wait_for_assessment(app["application_id"], timeout=30)
    return app["application_id"], analyst


def test_assessment_populates_and_queues(svc, assessed):
    app_id, analyst = assessed
    out = svc.assessment(app_id, analyst)
    v = out["verify"]
    assert out["can_verify"] and v["stats"]["total"] > 50 and v["stats"]["populated_pct"] > 50
    assert v["queue"] and v["queue"][0]["verify"] == "must_verify"
    assert v["meta"]["run_id"] == "run-1" and v["meta"]["resolvers"][0] == "risk_maker"
    assert {"reconcile_cma", "reconcile_parties", "reconcile_narrative"} <= set(v["meta"]["resolvers"])
    assert sum(1 for e in svc.get(app_id)["events"] if e["action"] == "fields_populated") == 1
    svc.assessment(app_id, analyst)                                   # viewing again does not re-populate
    assert sum(1 for e in svc.get(app_id)["events"] if e["action"] == "fields_populated") == 1


def test_bulk_confirm_preticked_and_refuse_must_verify(svc, assessed):
    app_id, analyst = assessed
    before = svc.assessment(app_id, analyst)["verify"]
    preticked = before["step_stats"]["preticked"]          # what this step verifies
    assert preticked > 0
    with pytest.raises(InvalidRequestError, match="individual decision"):
        svc.bulk_confirm(app_id, analyst, [GRADE])
    out = svc.bulk_confirm(app_id, analyst)
    s = out["verify"]["step_stats"]
    assert s["confirmed"] == preticked and s["preticked"] == 0
    assert 0 < out["review_summary"]["confirmed"] <= preticked          # the Risk Maker tabs see their share
    event = svc.get(app_id)["events"][0]
    assert event["action"] == "fields_bulk_confirmed" and len(event["detail"]["reviews"]) == preticked
    assert svc.get(app_id)["field_reviews"]                                    # committee pack mirror kept


def test_verify_override_and_permissions(svc, assessed):
    app_id, analyst = assessed
    out = svc.verify_fields(app_id, analyst, [{"field_id": RATING, "action": "override", "value": "IR-7",
                                               "reason": "Committee guidance"},
                                              {"field_id": GRADE, "action": "confirm"}])
    assert out["verify"]["stats"]["overridden"] == 1 and out["verify"]["stats"]["accepted_unchanged_pct"] == 50.0
    with pytest.raises(InvalidRequestError, match="needs a value and a reason"):
        svc.verify_fields(app_id, analyst, [{"field_id": RATING, "action": "override", "value": "IR-6"}])
    with pytest.raises(InvalidRequestError, match="Unknown field"):
        svc.verify_fields(app_id, analyst, [{"field_id": "nope", "action": "confirm"}])
    reviewer = svc.sign_in("u_cvp", "risk_reviewer")
    with pytest.raises(ForbiddenError):
        svc.verify_fields(app_id, reviewer, [{"field_id": GRADE, "action": "confirm"}])
    apol = next(a for a in svc.list() if a["entity_id"] == "APOL001")         # at the sanction committee
    with pytest.raises(ConflictError, match="No fields are verified"):
        svc.verify_fields(apol["application_id"], svc.sign_in("u_cc", "sanction_committee"),
                          [{"field_id": GRADE, "action": "confirm"}])


def test_rerun_raises_conflicts_instead_of_overwriting(svc, assessed, abce_case):
    app_id, analyst = assessed
    svc.verify_fields(app_id, analyst, [{"field_id": GRADE, "action": "confirm"}])
    changed = copy.deepcopy(abce_case)
    changed["fact_pack"]["policy_decisions"]["tier3_recommendation"]["risk_grade"] = "C"
    svc.cases.case = changed                                          # the next run sees different data
    svc.start_assessment(app_id, analyst)
    job = svc.wait_for_assessment(app_id, timeout=30)
    assert job["populated"]["conflicts"] >= 1 and job["populated"]["run_id"] == "run-2"
    out = svc.assessment(app_id, analyst)
    grade = svc.get(app_id)["fields"][GRADE]
    assert grade["status"] == "conflict" and grade["value"] == "D" and grade["proposal"]["value"] == "C"
    assert out["verify"]["queue"][0]["field_id"] == GRADE                      # conflicts come first
    out = svc.verify_fields(app_id, analyst, [{"field_id": GRADE, "action": "confirm"}])   # accept the new value
    assert svc.get(app_id)["fields"][GRADE]["value"] == "C"


def test_application_stays_on_its_pinned_run(svc, assessed, abce_case):
    app_id, analyst = assessed
    changed = copy.deepcopy(abce_case)
    changed["fact_pack"]["policy_decisions"]["tier3_recommendation"]["risk_grade"] = "C"
    svc.cases.case = changed
    svc.cases.run("ABCE001")                                          # another application re-runs the borrower
    out = svc.assessment(app_id, analyst)
    assert out["pin"] == {"pinned_run_id": "run-1", "shown_run_id": "run-1", "latest_run_id": "run-2",
                          "newer_run_available": True}
    grade = next(f for t in out["view"]["tabs"] for s in t["sections"] for f in s.get("fields") or [] if f["id"] == GRADE)
    assert grade["value"] == "D"                                       # still run-1's grade
    assert svc.get(app_id)["fields_meta"]["run_id"] == "run-1"
