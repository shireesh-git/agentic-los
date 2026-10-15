"""Sprint 4: reconciliation agents populate the governed workspaces; the preparation agent at the
IP Note / Risk Maker steps; financial statements for a new prospect come from its documents."""

import copy
from datetime import datetime

import fitz
import pytest

from src.agentic.critic import check_evidence
from src.data.company_catalog import seed_company_store
from src.engines.data_provenance import NOT_AVAILABLE
from src.los import reconcile
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
    return full_case(abce)


@pytest.fixture(scope="module")
def registry():
    return FieldRegistry.load()


def _ctx(case, company, registry, app=None, prefill=None):
    return {"case": case, "fact_pack": case["fact_pack"], "company": company, "registry": registry,
            "app": app or {"borrower_name": "ABC", "facilities": [{"facility_id": "FAC-001", "facility_nature": "fund_based"}]},
            "today": "2026-10-08", "run_id": "run-1", "prefill_values": prefill or {}}


# ── resolvers ────────────────────────────────────────────────────────────────

def test_each_domain_proposes_with_evidence_and_a_target(case, abce, registry):
    ctx = _ctx(case, abce, registry)
    by_domain = {name: fn(ctx) for name, fn in reconcile.RESOLVERS.items()}
    assert by_domain["cma"] and by_domain["parties"] and by_domain["securities"] and by_domain["narrative"]
    for name, props in by_domain.items():
        for p in props:
            assert p["field_id"].startswith(p["domain"] + ".") and p["target"], p["field_id"]
            if p["provenance"] != "unavailable":
                assert check_evidence(p) == [], (p["field_id"], check_evidence(p))
    latest = sorted(abce["financials"])[-1]
    rev = next(p for p in by_domain["cma"] if p["field_id"] == f"cma.borrower.{latest}.revenue")
    assert rev["value"] == round(abce["financials"][latest].line_items["revenue_operating"], 2)
    directors = [p for p in by_domain["parties"] if p["field_id"].startswith("parties.din_")]
    assert directors and all(p["target"][1]["new"]["party_type"] == "individual" for p in directors)
    assert all(p["provenance"] == "synthetic_demo" for p in by_domain["facility_pricing"])   # labelled demo


def test_cma_reconciles_the_latest_year_against_the_documents(case, abce, registry):
    latest = sorted(abce["financials"])[-1]
    revenue = abce["financials"][latest].line_items["revenue_operating"]
    ctx = _ctx(case, abce, registry, prefill={"revenue_cr": {"value": revenue * 1.2, "document": "request/a.pdf", "page": 1}})
    rev = next(p for p in reconcile.resolve_cma(ctx) if p["field_id"] == f"cma.borrower.{latest}.revenue")
    assert rev["issues"] and "request/a.pdf" in rev["issues"][0]          # a conflict for a person to resolve


# ── materialise ──────────────────────────────────────────────────────────────

def _fields(case, abce, registry, app):
    fields = {}
    props = [p for fn in reconcile.RESOLVERS.values() for p in fn(_ctx(case, abce, registry, app))]
    fm.merge(fields, props, registry, "2026-10-08T12:00:00")
    return fields


def test_materialise_fills_the_workspaces_and_never_overwrites_a_person(case, abce, registry):
    app = {"borrower_name": "ABC", "facilities": [{"facility_id": "FAC-001", "facility_nature": "fund_based"}],
           "cma": {"subjects": []}, "related_parties": [], "securities": [], "ratings": {"internal_ratings": []},
           "pricing": {"facilities": {}}, "proposal": {"background": {"strengths": "Written by the RM."},
                                                      "exposure": {}, "conduct": {"rows": []}}}
    fields = _fields(case, abce, registry, app)
    out = reconcile.materialise(app, fields)
    assert out["written"] > 20 and out["kept_person_entries"] == 1
    assert app["proposal"]["background"]["strengths"] == "Written by the RM."     # the person's text stands
    assert app["proposal"]["background"]["key_risks"]
    subj = app["cma"]["subjects"][0]
    assert subj["subject"] == "borrower" and subj["origin"] == "agent" and len(subj["rows"]) >= 1
    assert [s["security_id"] for s in app["securities"]] == ["SEC-001", "SEC-002"]
    assert app["related_parties"][0]["party_id"] == "RP-001" and app["related_parties"][0]["origin"] == "agent"
    assert app["pricing"]["facilities"]["FAC-001"]["proposed_benchmark"] == "1-year MCLR"
    assert reconcile.materialise(app, fields)["written"] == 0                      # idempotent
    # an override in the field store flows back into the workspace — even over a person's entry
    fid = "narrative.background.strengths"
    fm.apply_action(fields[fid], "override", by={"id": "u", "name": "U"}, at="t", registry=registry,
                    value="Agreed strengths text", reason="edited")
    reconcile.materialise(app, fields, [fid])
    assert app["proposal"]["background"]["strengths"] == "Agreed strengths text"


# ── service ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def svc(tmp_path, case):
    cases = RunCases(case)
    service = LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow, seed_company_store(), clock=lambda: NOW,
                         cases=cases, final_cam=RunFinalCam(cases))
    service.seed_demo()
    return service


def test_assessment_populates_the_workspaces(svc):
    app = next(a for a in svc.list() if a["entity_id"] == "ABCE001")
    analyst = svc.sign_in(app["assignee_id"], "risk_analyst")
    svc.start_assessment(app["application_id"], analyst)
    job = svc.wait_for_assessment(app["application_id"], timeout=30)
    assert job["populated"]["workspaces"]["written"] > 20
    got = svc.get(app["application_id"])
    assert any(s.get("origin") == "agent" for s in got["cma"]["subjects"])
    assert any(s.get("origin") == "agent" for s in got["securities"])
    assert got["proposal"]["background"]["key_risks"]
    q = svc.assessment(app["application_id"], analyst)["verify"]["queue"]
    assert {"cma", "facility_pricing"} <= {i["domain"] for i in q}            # verified at the Risk Maker step
    assert "parties" not in {i["domain"] for i in q}                          # verified at the IP Note step


def test_preparation_agent_at_the_risk_maker_runs_the_case_and_populates(svc):
    app = next(a for a in svc.list() if a["entity_id"] == "ABCE001")
    analyst = svc.sign_in(app["assignee_id"], "risk_analyst")
    svc.prepare_application(app["application_id"], analyst, wait=True)
    job = svc.wait_for_preparation(app["application_id"])
    assert job["state"] == "done", job.get("error")
    assert job["summary"]["credit_case_ran"] is True and job["summary"]["run_id"] == "run-1"
    assert {lane["lane"] for lane in job["lanes"]} >= {"credit_case", "checks", "populate"}
    events = [e["action"] for e in svc.get(app["application_id"])["events"]]
    assert events[0] == "application_prepared" and "assessment" in events and "fields_populated" in events
    svc.prepare_application(app["application_id"], analyst, wait=True)       # again: the pinned case is reused
    assert svc.wait_for_preparation(app["application_id"])["summary"]["credit_case_ran"] is False


def test_preparation_at_the_ip_note_drafts_the_note(svc):
    app = next(a for a in svc.list() if a["entity_id"] == "ABCE001")
    rec = svc._require(app["application_id"])
    rec.update(step_id="ip_note", stage_id="IP", assignee_id="u_rm1", status="IN_PROGRESS")
    svc.store.save(rec, svc._event(rec, "test_setup", actor={"id": None, "role": "test"}))
    rm = svc.sign_in("u_rm1", "ps_maker")
    svc.prepare_application(app["application_id"], rm, wait=True)
    job = svc.wait_for_preparation(app["application_id"])
    assert job["state"] == "done", job.get("error")
    assert {lane["lane"]: lane["status"] for lane in job["lanes"]}["ip_note"] == "completed"
    got = svc.get(app["application_id"], rm)
    assert got["ip_note"] and got["related_parties"]
    q = svc.assessment(app["application_id"], rm)["verify"]["queue"]
    assert {"parties", "narrative"} <= {i["domain"] for i in q}               # the RM verifies these here


# ── new prospects: financial statements from the documents ───────────────────

AUDITED = ("Audited Standalone Financial Statements for the year ended 31 March 2025 (Rs in Crores)\n"
           "Revenue from Operations 312.40\nOther Income 4.10\nTotal Income 316.50\nEBITDA 41.20\n"
           "Depreciation 9.80\nFinance Cost 8.90\nProfit Before Tax 22.50\nProfit After Tax 16.80\n"
           "Total Assets 268.00\nTotal Equity 118.00\nTotal Debt 96.00")


def test_revenue_is_never_pooled_with_total_income(tmp_path):
    from src.engines.document_ocr_engine import extract_financials_enhanced
    path = tmp_path / "audited.pdf"
    doc = fitz.open()
    doc.new_page().insert_textbox(fitz.Rect(40, 40, 560, 800), AUDITED, fontsize=10)
    doc.save(path)
    data = extract_financials_enhanced(path)["data"]
    assert data["revenue"] == [312.4]                       # not 316.50 (Total Income)


def test_a_prospect_without_statements_stops_with_what_is_needed():
    from src.agents.pipeline import SuperAgent
    from src.application.company_service import build_prospect_company
    from src.core.llm_provider import MockLLMProvider

    company = build_prospect_company("NOFIN001", {"company_name": "No Fin Ltd", "sector": "manufacturing"},
                                     {"facility_type": "working_capital", "amount_cr": 10})
    with pytest.raises(RuntimeError, match="upload the audited financial statements"):
        SuperAgent(llm_provider=MockLLMProvider()).execute_pipeline(copy.deepcopy(company),
                                                                    stores={"extraction": {}, "etb": {}})


def test_a_prospect_statement_takes_the_year_of_its_document():
    from src.agents.financial_overrides import apply_uploaded_financial_overrides
    from src.application.company_service import build_prospect_company

    company = build_prospect_company("ZETA001", {"company_name": "Zeta", "sector": "manufacturing"},
                                     {"facility_type": "working_capital", "amount_cr": 45})
    extraction = {"financials": {"audited": {"revenue": [312.4], "pat": [16.8], "total_income": [316.5]}},
                  "selected_documents": {"audited_financials": "financials/audited_financials_fy2025.pdf"}}
    apply_uploaded_financial_overrides(company, extraction)
    assert list(company["financials"]) == ["FY2025"]
    fs = company["financials"]["FY2025"]
    assert fs.line_items["revenue_operating"] == 312.4 and str(fs.as_of_date) == "2025-03-31"
    assert NOT_AVAILABLE not in str(fs.line_items)
