"""LOS Phase 6: the copilot — next best actions, copilot-run tools, drafts, grounded Q&A and the queue digest."""

import json
from datetime import datetime

import pytest

from src.application.errors import ConflictError, ForbiddenError, InvalidRequestError
from src.data.company_catalog import seed_company_store
from src.los import copilot as cp
from src.los.service import LosService, load_workflow
from src.los.store import LosStore
from src.services.document_store import DocumentStore
from tests.test_cam_composer import full_case
from tests.test_los_committee import BriefingFinalCam, _to_committee
from tests.test_los_risk_maker import FakeCases
from tests.test_los_sourcing import docs_root  # noqa: F401  (fixture)

NOW = datetime(2026, 10, 8, 12, 0, 0)


class FakeLLM:
    name, model = "fake", "fake-llm"

    def __init__(self, reply):
        self.reply = reply

    def generate(self, prompt, system_prompt="", temperature=0.1, max_tokens=1000):
        return json.dumps(self.reply)


@pytest.fixture(scope="module")
def abce_case():
    return full_case(seed_company_store()["ABCE001"])


def _svc(tmp_path, docs_root, abce_case, llm=None):
    cases = FakeCases(abce_case)
    service = LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow, seed_company_store(), clock=lambda: NOW,
                         cases=cases, final_cam=BriefingFinalCam(cases), documents_root=docs_root,
                         doc_store=DocumentStore(docs_root), llm_factory=(lambda: llm) if llm else None)
    service.seed_demo()
    return service


@pytest.fixture()
def svc(tmp_path, docs_root, abce_case):
    return _svc(tmp_path, docs_root, abce_case)


def _app(svc, entity):
    return next(a for a in svc.list() if a["entity_id"] == entity)


def _holder(svc, app_id):
    app = svc.get(app_id)
    return svc.sign_in(app["assignee_id"], app["step"]["role"])


def _ids(out):
    return [a["id"] for a in out["actions"]]


# ─── Planner ────────────────────────────────────────────────────────────────

def test_planner_never_proposes_a_workflow_decision():
    base = {"step_id": "ps_maker", "step_name": "Prospect Sourcing", "step_kind": "maker", "is_holder": True,
            "status": "DRAFT", "documents": 5, "can_submit": True, "committee_steps": ()}
    acts = cp.next_actions(base)
    assert acts[0]["tool"] == "run_prefill" and all(a["tool"] in (None, *cp.TOOLS) for a in acts)
    ready = cp.next_actions(base | {"prefill": {"unaccepted_high": 0, "conflicts": [], "not_found": []}})
    assert ready[-1]["id"] == "ready" and "does not submit" in ready[-1]["why"]
    assert cp.next_actions(base | {"is_holder": False, "holder": "Ananya Rao"})[0]["id"] == "not_yours"


def test_planner_flags_sla_breach_first_and_returned_comment():
    s = {"step_id": "ip_note", "step_name": "IP Note Processing", "step_kind": "maker", "is_holder": True,
         "status": "RETURNED", "returned_comment": "Add the group exposure", "sla": {"breached": True,
         "days_remaining": -2.5, "sla_days": 3}, "committee_steps": ()}
    acts = cp.next_actions(s)
    assert [a["id"] for a in acts[:3]] == ["sla", "returned", "ip_note"] and "2.5 day(s)" in acts[0]["why"]


# ─── Tools run by the copilot ───────────────────────────────────────────────

def test_copilot_runs_the_sourcing_tools_for_the_holder_and_audits_it(svc):
    app_id = _app(svc, "IHCL001")["application_id"]
    rm = _holder(svc, app_id)
    first = svc.copilot(app_id, rm)
    assert first["actions"][0]["tool"] == "run_due_diligence" and first["is_holder"]     # the DD gate is the first job
    svc.copilot_run(app_id, rm, "run_due_diligence")                                     # runs the API checks
    for c in svc.due_diligence(app_id, rm)["checks"]:
        if c["mode"] == "manual":
            svc.record_check(app_id, rm, c["id"], "clear", "Verified (test)")
        elif c["status"] in ("matched", "failed") and not c.get("exception"):
            svc.exception_check(app_id, svc.sign_in("u_compvp", "compliance_vp"), c["id"], "Exception (test)")
    out = svc.copilot(app_id, rm)
    assert out["actions"][0]["tool"] == "run_prefill"
    out = svc.copilot_run(app_id, rm, "run_prefill")
    accept = next(a for a in out["actions"] if a["tool"] == "accept_high_confidence")
    assert accept["priority"] == "high"
    svc.copilot_run(app_id, rm, "accept_high_confidence")
    assert svc.get(app_id)["sourcing"]["accepted"] > 0
    recent = [e["action"] for e in svc.get(app_id)["events"]]
    assert "dd_trigger" in recent and "document_prefill" in recent and "prefill_apply" in recent
    with pytest.raises(ConflictError, match="no high-confidence"):
        svc.copilot_run(app_id, rm, "accept_high_confidence")


def test_copilot_acts_only_for_the_holder_and_only_with_known_tools(svc):
    app_id = _app(svc, "IHCL001")["application_id"]
    with pytest.raises(ForbiddenError, match="holding the step"):
        svc.copilot_run(app_id, svc.sign_in("u_cvp", "crp_vp"), "run_prefill")
    with pytest.raises(InvalidRequestError, match="cannot run 'submit'"):
        svc.copilot_run(app_id, _holder(svc, app_id), "submit")
    assert svc.copilot(app_id, svc.sign_in("u_cvp", "crp_vp"))["actions"][0]["id"] == "not_yours"


def test_risk_maker_and_committee_tools(svc):
    abce = _app(svc, "ABCE001")["application_id"]
    analyst = _holder(svc, abce)
    assert svc.copilot(abce, analyst)["actions"][0]["tool"] == "start_assessment"
    svc.copilot_run(abce, analyst, "start_assessment")
    svc.wait_for_assessment(abce, timeout=30)
    assert "review" in _ids(svc.copilot(abce, analyst))
    app_id, committee = _to_committee(svc)
    out = svc.copilot(app_id, committee)
    assert "brief" in _ids(out) and "overrides" in _ids(out)
    svc.copilot_run(app_id, committee, "committee_brief")
    assert "brief" not in _ids(svc.copilot(app_id, committee))


# ─── Drafts ─────────────────────────────────────────────────────────────────

def test_document_request_lists_missing_documents_and_fields(svc):
    app_id = _app(svc, "IHCL001")["application_id"]
    rm = _holder(svc, app_id)
    svc.run_prefill(app_id, rm)
    text = svc.copilot_draft(app_id, rm, "document_request")["text"]
    assert "GST registration certificate" in text and "Audited financial statements" in text
    assert "Document evidencing the GSTIN" in text and rm["user"]["name"] in text
    assert "PAN card" not in text                                          # on file


def test_return_note_lists_the_open_points(svc):
    app_id, committee = _to_committee(svc)
    text = svc.copilot_draft(app_id, committee, "return_note")["text"]
    assert text.startswith("Returned for the following") and "Address the unresolved risk" in text
    with pytest.raises(InvalidRequestError):
        svc.copilot_draft(app_id, committee, "poem")


# ─── Ask ────────────────────────────────────────────────────────────────────

def test_ask_without_an_llm_returns_matching_record_lines(svc):
    app_id = _app(svc, "APOL001")["application_id"]
    out = svc.copilot_ask(app_id, svc.sign_in("u_cc", "sanction_committee"), "What is the tenor and purpose?")
    assert out["mode"] == "lookup" and "tenor" in out["answer"].lower() and "mock" in out["note"]
    app = svc.get(app_id)
    assert app["events"][0]["action"] == "copilot_ask"
    assert svc.copilot(app_id)["history"][0]["question"] == "What is the tenor and purpose?"


def test_ai_answer_is_accepted_only_when_its_figures_are_in_the_record(tmp_path, docs_root, abce_case):
    good = _svc(tmp_path / "a", docs_root, abce_case, FakeLLM({"answer": "The tenor is 60 months.", "fields_used": []}))
    app_id = _app(good, "APOL001")["application_id"]
    tenor = good.get(app_id)["facility"]["tenor_months"]
    good.llm_factory = lambda: FakeLLM({"answer": f"The tenor is {tenor} months.", "fields_used": ["facility"]})
    out = good.copilot_ask(app_id, good.sign_in("u_cc", "sanction_committee"), "What is the tenor?")
    assert out["mode"] == "ai" and out["provenance"] == "ai" and str(tenor) in out["answer"]
    good.llm_factory = lambda: FakeLLM({"answer": "The tenor is 997 months.", "fields_used": []})
    out = good.copilot_ask(app_id, good.sign_in("u_cc", "sanction_committee"), "What is the tenor?")
    assert out["mode"] == "lookup" and "rejected" in out["note"] and "997" in out["note"]


# ─── Digest ─────────────────────────────────────────────────────────────────

def test_digest_puts_sla_breaches_first(svc):
    # UAT-P2-9: SLA is measured in working days, so the seeded dis_maker (PNCR001) is the breach
    d = svc.copilot_digest(svc.sign_in("u_dism", "dis_maker"))
    assert d["items"] and d["items"][0]["sla_breached"] and "past SLA" in d["summary"]
    assert svc.copilot_digest(svc.sign_in("u_admin", "los_admin"))["summary"] == "Nothing is waiting for you."


def test_api_copilot_endpoints():
    from fastapi.testclient import TestClient

    from src.api.app import create_app
    from src.application.container import build_container
    container = build_container()
    container.los.seed_demo(force=True)
    http = TestClient(create_app(container))
    token = http.post("/api/los/session", json={"user_id": "u_rm1", "role": "ps_maker"}).json()["token"]
    h = {"X-LOS-Session": token}
    assert http.get("/api/los/copilot/digest", headers=h).json()["items"]
    ihcl = next(a for a in http.get("/api/los/applications?q=IHCL", headers=h).json()["applications"])
    base = f"/api/los/applications/{ihcl['application_id']}/copilot"
    out = http.get(base, headers=h).json()
    assert out["actions"][0]["tool"] == "run_due_diligence" and out["ai_available"] is False
    assert http.post(base + "/run", headers=h, json={"tool": "approve"}).status_code == 400
    assert "Subject:" in http.post(base + "/draft", headers=h, json={"kind": "document_request"}).json()["text"]
    assert http.post(base + "/ask", headers=h, json={"question": "What is the amount?"}).json()["mode"] == "lookup"
