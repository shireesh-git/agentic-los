"""LOS Phase 7: term sheet and sanction letter generation, and the management MIS."""

from datetime import datetime

import pytest

from src.application.errors import ConflictError, ForbiddenError, NotFoundError
from src.data.company_catalog import seed_company_store
from src.los import letters as lt
from src.los.mis import step_visits
from src.los.service import LosService, load_workflow
from src.los.store import LosStore
from tests.test_cam_composer import full_case
from tests.test_los_committee import BriefingFinalCam
from tests.test_los_risk_maker import FakeCases

NOW = datetime(2026, 10, 8, 12, 0, 0)


@pytest.fixture(scope="module")
def abce_case():
    return full_case(seed_company_store()["ABCE001"])


@pytest.fixture()
def svc(tmp_path, abce_case):
    cases = FakeCases(abce_case)
    service = LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow, seed_company_store(), clock=lambda: NOW,
                         cases=cases, final_cam=BriefingFinalCam(cases))
    service.seed_demo()
    return service


def _app(svc, entity):
    return next(a for a in svc.list() if a["entity_id"] == entity)


# ─── Letters ────────────────────────────────────────────────────────────────

def test_availability_follows_the_sanctions(svc):
    by = lambda e: {l["kind"]: l for l in svc.letters(_app(svc, e)["application_id"])["letters"]}
    assert not by("IHCL001")["term_sheet"]["available"]                       # not sanctioned yet
    assert not by("APOL001")["term_sheet"]["available"]                       # awaiting the IP committee
    assert by("MRF001")["term_sheet"]["available"] and not by("MRF001")["sanction_letter"]["available"]
    assert by("INFY001")["sanction_letter"]["available"]


def test_sanction_letter_is_built_from_the_record_and_versioned(svc):
    app_id = _app(svc, "INFY001")["application_id"]
    pos = svc.sign_in("u_posm", "pos_maker")
    svc.update_conditions(app_id, pos, [{"id": "CP-01", "status": "waived", "note": "Board resolution on file"}])
    out = svc.generate_letter(app_id, pos, "sanction_letter")
    sl = next(l for l in out["letters"] if l["kind"] == "sanction_letter")
    doc = sl["latest"]
    terms = {t["label"]: t["value"] for t in doc["terms"]}
    sanction = svc.get(app_id)["sanctions"]["AP"]
    assert terms["Amount sanctioned"] == f"₹{sanction['sanctioned_cr']:,.2f} Cr"
    assert doc["reference"] == f"{app_id}/SL/1" and doc["conditions_source"] == "Conditions tracker"
    assert [c["text"] for c in doc["conditions_precedent"]] == [c["text"] for c in svc.get(app_id)["conditions"]
                                                                if c["type"] == "CP"]
    assert any(d["description"].startswith("CP-01 waived") for d in doc["deviations"])
    assert lt.DEMO_MARK in lt.render_markdown(doc) and "CAM Report" not in svc.letter_html(app_id, "sanction_letter")
    svc.generate_letter(app_id, pos, "sanction_letter")
    sl = next(l for l in svc.letters(app_id, pos)["letters"] if l["kind"] == "sanction_letter")
    assert [v["version"] for v in sl["versions"]] == [2, 1]
    assert f"{app_id}/SL/1" in svc.letter_html(app_id, "sanction_letter", version=1)
    assert svc.get(app_id)["events"][0]["action"] == "letter_issued"


def test_only_the_issuing_role_and_only_after_sanction(svc):
    infy = _app(svc, "INFY001")["application_id"]
    with pytest.raises(ForbiddenError, match="Post Sanction Maker"):
        svc.generate_letter(infy, svc.sign_in("u_rm1", "ps_maker"), "sanction_letter")
    with pytest.raises(ConflictError, match="final committee sanction"):
        svc.generate_letter(_app(svc, "MRF001")["application_id"], svc.sign_in("u_posm", "pos_maker"),
                            "sanction_letter")
    with pytest.raises(NotFoundError):
        svc.letter_html(infy, "sanction_letter")
    ts = svc.generate_letter(_app(svc, "MRF001")["application_id"], svc.sign_in("u_rm1", "ps_maker"), "term_sheet")
    assert next(l for l in ts["letters"] if l["kind"] == "term_sheet")["latest"]["title"] == "Term sheet (indicative)"


def test_pricing_is_labelled_demo_and_covenants_prefer_the_case(abce_case):
    assert lt._pricing("B")["provenance"] == "synthetic_demo" and "9.65%" in lt._pricing("B")["text"]
    assert lt._pricing(None)["provenance"] == "template" and "to be advised" in lt._pricing(None)["text"]
    cov, src = lt._covenants({"covenants_proposed": ["Minimum DSCR >= 1.20x"]}, {})
    assert cov == ["Minimum DSCR >= 1.20x"] and src.startswith("Credit case")
    cov, src = lt._covenants(None, {"min_dscr": 1.2, "max_debt_to_equity": 2.5})
    assert "Minimum DSCR ≥ 1.2x" in cov and src.startswith("Credit policy")


def test_copilot_proposes_and_issues_the_sanction_letter(svc):
    app_id = _app(svc, "INFY001")["application_id"]
    pos = svc.sign_in("u_posm", "pos_maker")
    assert any(a["tool"] == "issue_sanction_letter" for a in svc.copilot(app_id, pos)["actions"])
    svc.copilot_run(app_id, pos, "issue_sanction_letter")
    assert not any(a["tool"] == "issue_sanction_letter" for a in svc.copilot(app_id, pos)["actions"])


# ─── MIS ────────────────────────────────────────────────────────────────────

def test_step_visits_measure_time_between_moves(svc):
    wf = svc.wf
    events = [{"action": "create", "to_step": "ps_maker", "at": "2026-10-01T10:00:00", "event_id": 1},
              {"action": "submit", "from_step": "ps_maker", "to_step": "ip_note", "at": "2026-10-04T10:00:00", "event_id": 2},
              {"action": "copilot_ask", "from_step": "ip_note", "to_step": "ip_note", "at": "2026-10-05T10:00:00", "event_id": 3},
              {"action": "return", "from_step": "ip_note", "to_step": "ps_maker", "at": "2026-10-06T22:00:00", "event_id": 4}]
    v = step_visits({}, events, wf)
    assert [(x["step"], round(x["days"], 1), x["within_sla"]) for x in v] == [
        ("ps_maker", 3.0, wf.step("ps_maker").sla_days >= 3), ("ip_note", 2.5, wf.step("ip_note").sla_days >= 2.5)]


def test_mis_summarises_the_seeded_pipeline(svc):
    m = svc.mis()
    h = m["headline"]
    active = [a for a in svc.list() if a["status"] not in ("APPROVED", "REJECTED", "WITHDRAWN", "DROPPED")]
    assert h["active"] == 7 and h["pipeline_cr"] == round(sum(a["amount_cr"] for a in active), 2)
    # UAT-P2-9: SLA is measured in working days, so the seeded pipeline shows one live breach (PNCR001)
    assert h["live_breaches"] == sum(b["count"] for b in m["breaches_by_role"]) >= 1
    review = next(d for d in m["decisions"] if d["step"] == "CRP VP Risk Review")
    assert review["returned"] == 1 and review["return_rate_pct"] > 0               # MFL's seeded return
    assert 0 < h["sla_compliance_pct"] <= 100 and h["first_time_right_pct"] < 100
    assert sum(a["count"] for a in m["ageing"]) == 7 and m["tat_stages"]
    app_id = _app(svc, "APOL001")["application_id"]
    svc.copilot_ask(app_id, svc.sign_in("u_cc", "sanction_committee"), "What is the tenor?")
    assert svc.mis()["copilot"] == {"tasks_run": 0, "questions": 1, "applications": 1}


def test_api_letters_and_mis():
    from fastapi.testclient import TestClient

    from src.api.app import create_app
    from src.application.container import build_container
    container = build_container()
    container.los.seed_demo(force=True)
    http = TestClient(create_app(container))
    token = http.post("/api/los/session", json={"user_id": "u_posm", "role": "pos_maker"}).json()["token"]
    h = {"X-LOS-Session": token}
    assert http.get("/api/los/mis", headers=h).json()["headline"]["active"] == 7
    infy = next(a for a in http.get("/api/los/applications?q=INFY", headers=h).json()["applications"])
    base = f"/api/los/applications/{infy['application_id']}/letters"
    assert http.get(base + "/sanction_letter.html", headers=h).status_code == 404
    assert http.post(base + "/sanction_letter", headers=h).status_code == 200
    page = http.get(base + "/sanction_letter.html", headers=h).text
    assert "Sanction letter" in page and "DEMO DOCUMENT" in page
    assert http.post(base + "/poem", headers=h).status_code == 400
