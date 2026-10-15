"""S9: the IP / AP pre-fill agents (R-P1, R-P2) and terms & conditions authored at AP (G-F2)."""

import copy
from datetime import datetime

import pytest

from src.agentic.critic import check_evidence
from src.application.errors import ConflictError, ForbiddenError, InvalidRequestError
from src.data.company_catalog import seed_company_store
from src.los import esms as es
from src.los import prefill, reconcile
from src.los import terms as tm
from src.los.fields import model as fm
from src.los.fields.registry import FieldRegistry
from src.los.service import LosService, load_workflow
from src.los.store import LosStore
from tests.test_cam_composer import full_case
from tests.test_los_fields import RunCases, RunFinalCam

NOW = datetime(2026, 10, 8, 12, 0, 0)


@pytest.fixture(scope="module")
def abce():
    return seed_company_store()["ABCE001"]


@pytest.fixture(scope="module")
def case(abce):
    c = copy.deepcopy(full_case(abce))
    c["covenants_proposed"] = ["Minimum DSCR >= 1.20x", "Maximum Debt/Equity <= 2.5x",
                               "Quarterly financial submission within 45 days"]
    c["conditions"] = ["Requires Credit Committee approval",
                       "All HIGH/CRITICAL exceptions must be resolved before disbursement"]
    c.setdefault("reassessment", {}).update(
        recommended_mitigants=[{"item": "Personal guarantee of the promoter directors."}],
        conditions_precedent=[{"item": "Close investigation: data reliability."}],
        conditions_subsequent=[{"item": "Maintain DSCR of at least 1.25x", "type": "financial"}])
    return c


@pytest.fixture(scope="module")
def registry():
    return FieldRegistry.load()


def _app():
    return {"borrower_name": "ABC Engineering", "facility": {"purpose": "Capacity expansion (new plant in Pune)"},
            "facilities": [{"facility_id": "FAC-001", "facility_nature": "fund_based", "facility_type": "term_loan",
                            "amount_cr": 50.0, "proposed_cr": 50.0, "tenor_months": 60,
                            "purpose": "Capacity expansion (new plant in Pune)"}]}


def _ctx(case, company, registry, app=None):
    return {"case": case, "fact_pack": case["fact_pack"], "company": company, "registry": registry,
            "app": app or _app(), "today": "2026-10-08", "run_id": "run-1", "prefill_values": {}}


# ── the pre-fill agents ──────────────────────────────────────────────────────

def test_every_prefill_agent_proposes_registered_fields_with_evidence(case, abce, registry):
    ctx = _ctx(case, abce, registry)
    by_name = {name: fn(ctx) for name, fn in prefill.RESOLVERS.items()}
    for name, props in by_name.items():
        for p in props:
            assert p["domain"] in registry.domains, (name, p["field_id"])
            assert p["field_id"].startswith(p["domain"] + ".") and p["target"], p["field_id"]
            if p["provenance"] != "unavailable":
                assert check_evidence(p) == [], (p["field_id"], check_evidence(p))
    narratives = {p["field_id"].rsplit(".", 1)[1] for p in by_name["narrative_more"] if p["provenance"] != "unavailable"}
    assert {"corporate_governance", "weaknesses", "purpose"} <= narratives
    project = {p["field_id"]: p["value"] for p in by_name["project"]}
    assert project["projects.primary.name"] == "new plant in Pune"
    assert project["projects.primary.location"] == "Pune" and project["projects.primary.type"] == "expansion"
    # decision-driving proposals are individually verified, never bulk-confirmed
    for fid in ("external_rating.borrower.rating", "banking.arrangement.type", "esms_screening.es_wmd",
                "narrative.background.other_material_information"):
        assert registry.spec(fid).verify == "must_verify", fid


def test_a_missing_source_is_unavailable_never_invented(case, abce, registry):
    bare = copy.deepcopy(case)
    bare["fact_pack"]["external_intelligence"] = {}
    bare["fact_pack"]["group_profile"] = {}
    ctx = _ctx(bare, abce, registry)
    banking = {p["field_id"]: p for p in prefill.resolve_banking(ctx)}
    assert banking["banking.arrangement.type"]["provenance"] == "unavailable"
    assert all(p["provenance"] == "unavailable" for p in prefill.resolve_shareholding(ctx))


def test_the_bank_cam_supplies_the_banking_arrangement(case, abce, registry):
    app = {**_app(), "cam": {"document": "cam/x.pdf", "labels": {
        "cam.profile.banking_arrangement": {"value": "Consortium of 4 banks led by SBI", "page": 2, "snippet": "…"}}}}
    props = {p["field_id"]: p for p in prefill.resolve_banking(_ctx(case, abce, registry, app))}
    assert props["banking.arrangement.type"]["value"] == "consortium"
    assert props["banking.arrangement.number_of_banks"]["value"] == 4
    assert props["banking.arrangement.type"]["evidence"]["page"] == 2


def test_materialise_creates_projects_fees_terms_and_esms_items_with_their_ids(case, abce, registry):
    app = _app()
    app.update(pricing={"facilities": {}, "fees": []}, esms=es.initial_esms(None), projects=[])
    props = [p for fn in prefill.RESOLVERS.values() for p in fn(_ctx(case, abce, registry, app))]
    fields = {}
    fm.merge(fields, props, registry, "2026-10-08T12:00:00")
    reconcile.materialise(app, fields)
    assert app["projects"][0]["project_id"] == "PRJ-001" and app["projects"][0]["facility_ids"] == ["FAC-001"]
    fee = app["pricing"]["fees"][0]
    assert fee["fee_id"] == "APF-01" and fee["total_cr"] == round(50.0 * fee["pct"] / 100, 4)
    ids = [r["term_id"] for r in app["terms"]["conditions"]]
    assert ids[0] == "TC-001" and len(set(ids)) == len(ids)
    # the ESMS checklist keeps every documented item when the agent screened only one
    full = es.normalise_checklist([], app["esms"]["checklist"])
    assert len(full) == len(es.ES_CHECKLIST) and next(i for i in full if i["id"] == "es_wmd")["answer"] == "No"
    assert next(i for i in full if i["id"] == "es_forced_labour")["answer"] is None      # the entity's conduct: a person


# ── the T&C agent ────────────────────────────────────────────────────────────

def test_the_tnc_agent_drafts_by_category_with_stipulated_values(case):
    drafts = tm.drafts(case, _app())
    by = {}
    for kind, text, source, prov, extra in drafts:
        by.setdefault(kind, []).append((text, source, prov, extra))
    dscr = next(x for x in by["FC"] if "DSCR >= 1.20x" in x[0])
    assert dscr[3]["stipulated_value"] == "≥ 1.20x" and dscr[1] == tm.COVENANTS
    assert any("Quarterly financial submission" in x[0] and x[3]["frequency"] == "quarterly" for x in by["NC"])
    assert any("Personal guarantee" in x[0] for x in by["PC"])
    assert any("before disbursement" in x[0] for x in by["CP"])
    assert not any("Committee approval" in t for k in by for t, *_ in by[k]), "an approval route is not a condition"
    assert any("FAC-001" in x[0] for x in by["FS"]) and all(x[3].get("facility_id") == "FAC-001" for x in by["FS"])
    assert all(x[2] == "template" for x in by["CPS"])
    assert len({tm.slug(t) for _, t, *_ in drafts}) == len(drafts), "no condition is drafted twice"


def test_authored_terms_become_the_post_sanction_conditions():
    t = tm.initial_terms()
    t["conditions"] = [
        {**tm.blank_row("CP", "Board resolution"), "term_id": "TC-001", "source": tm.STANDARD, "provenance": "template"},
        {**tm.blank_row("FC", "Minimum DSCR 1.2x"), "term_id": "TC-002", "stipulated_value": "≥ 1.2x"},
        {**tm.blank_row("GC", "Dropped"), "term_id": "TC-003", "removed": True}]
    conds = tm.to_conditions(t, "2027-01-06")
    assert [c["id"] for c in conds] == ["CP-01", "FC-01"]
    assert conds[1]["stipulated_value"] == "≥ 1.2x" and conds[1]["due"] == "2027-01-06"
    assert conds[0]["source"].startswith("Authored at AP") and conds[0]["term_id"] == "TC-001"
    assert tm.submit_gate(tm.initial_terms(), {}).startswith("Author the terms")


# ── the service: authoring at the AP maker step ──────────────────────────────

@pytest.fixture()
def svc(tmp_path, case):
    cases = RunCases(case)
    service = LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow, seed_company_store(), clock=lambda: NOW,
                         cases=cases, final_cam=RunFinalCam(cases))
    service.seed_demo()
    return service


def _at_ap_note(svc):
    app = next(a for a in svc.list() if a["entity_id"] == "ABCE001")
    analyst = svc.sign_in(app["assignee_id"], "risk_analyst")
    svc.start_assessment(app["application_id"], analyst)
    svc.wait_for_assessment(app["application_id"], timeout=30)
    raw = svc._require(app["application_id"])
    raw.update(step_id="ap_note", stage_id="AP", assignee_id="u_rm1", status="IN_PROGRESS")
    svc.store.save(raw)
    svc.populate_fields(app["application_id"], force=True)
    return app["application_id"], svc.sign_in("u_rm1", "ps_maker")


def test_the_ap_maker_authors_the_terms_and_the_gate_holds_until_drafts_are_decided(svc):
    app_id, maker = _at_ap_note(svc)
    t = svc.terms(app_id, maker)
    assert t["editable"] and t["summary"]["from_agent"] >= 8 and t["gate"]
    with pytest.raises(InvalidRequestError, match="need your confirmation"):
        svc.act(app_id, maker, "submit", comment="AP note")
    agent_row = next(r for r in t["rows"] if r["origin"] == "agent")
    with pytest.raises(InvalidRequestError, match="reason"):
        svc.save_term(app_id, maker, {"action": "update", "term_id": agent_row["term_id"], "text": "Changed"})
    svc.save_term(app_id, maker, {"action": "update", "term_id": agent_row["term_id"], "text": "Changed wording",
                                  "reason": "Bank's standard wording"})
    edited = next(r for r in svc.terms(app_id, maker)["rows"] if r["term_id"] == agent_row["term_id"])
    assert edited["text"] == "Changed wording" and edited["field_status"] == "overridden"
    svc.save_term(app_id, maker, {"action": "add", "category": "FS", "facility_id": "FAC-001",
                                  "text": "DSRA of one quarter's debt service"})
    with pytest.raises(InvalidRequestError, match="reason"):
        svc.save_term(app_id, maker, {"action": "remove", "term_id": "TC-001"})
    svc.save_term(app_id, maker, {"action": "remove", "term_id": "TC-002", "reason": "Not applicable"})
    rows = svc.terms(app_id, maker)["rows"]
    svc.bulk_confirm(app_id, maker, [r["field_id"] for r in rows if r["field_status"] == "proposed" and not r["removed"]])
    t = svc.terms(app_id, maker)
    assert t["gate"] is None and t["summary"]["added_by_people"] == 1 and t["summary"]["removed"] == 1


def test_terms_are_authored_only_by_the_ap_maker_and_locked_after_sanction(svc):
    app_id, maker = _at_ap_note(svc)
    other = svc.sign_in("u_lpf", "lpf_vp")
    with pytest.raises(ForbiddenError):
        svc.save_term(app_id, other, {"action": "add", "category": "GC", "text": "x"})
    raw = svc._require(app_id)
    raw["terms"]["status"] = "sanctioned"
    svc.store.save(raw)
    with pytest.raises(ConflictError, match="locked"):
        svc.save_term(app_id, maker, {"action": "add", "category": "GC", "text": "x"})
