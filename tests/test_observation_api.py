"""Credit observations through the HTTP API: list (with back-fill), review, AI wording."""

import copy
import json

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.application.container import build_container

ENTITY = "ABCE001"


@pytest.fixture(scope="module")
def demo_fact_pack():
    from src.data.company_catalog import seed_company_store
    from src.engines.cam_fact_builder import build_cam_fact_pack
    return build_cam_fact_pack(copy.deepcopy(seed_company_store()[ENTITY]))


@pytest.fixture()
def client(demo_fact_pack):
    container = build_container()
    # A case recorded before observations existed: no "observations" key, so the API back-fills it.
    case = {"run_id": "obs-run-1", "entity_id": ENTITY, "company_name": "ABC Engineering & Infrastructure Ltd.",
            "recommendation": "decline", "risk_grade": "D", "requested_amount_cr": 250,
            "run_at": "2026-10-07T10:00:00", "fact_pack": demo_fact_pack}
    container.state.cases[ENTITY] = case
    container.persistence.save_case_run(case)
    yield TestClient(create_app(container)), container
    container.state.cases.pop(ENTITY, None)
    container.persistence.delete_company(ENTITY)   # leave no partial case for later tests


def url(path=""):
    return f"/api/cases/{ENTITY}/observations{path}"


def test_list_backfills_and_counts(client):
    http, container = client
    body = http.get(url()).json()
    assert body["is_latest_run"] is True
    assert body["summary"]["total"] == 12
    assert body["summary"]["by_severity"] == {"CRITICAL": 0, "HIGH": 8, "MEDIUM": 3, "LOW": 1, "INFO": 0}
    # Back-filled observations are stored with the run.
    stored = container.persistence.get_case_run("obs-run-1")
    assert len(stored["observations"]) == 12


def test_review_status_and_note_persist(client):
    http, container = client
    oid = f"OBS-{ENTITY}-WC_DETERIORATION"
    r = http.patch(url(f"/{oid}"), json={"status": "INVESTIGATION_REQUIRED", "note": "Ageing requested"})
    assert r.status_code == 200
    assert r.json()["observation"]["status"] == "INVESTIGATION_REQUIRED"
    assert r.json()["observation"]["review"]["note"] == "Ageing requested"
    # Note-only update keeps the status; severity never changes through review.
    r = http.patch(url(f"/{oid}"), json={"note": "Ageing received; 18% over 180 days"})
    assert r.json()["observation"]["status"] == "INVESTIGATION_REQUIRED"
    assert r.json()["observation"]["severity"] == "HIGH"
    stored = container.persistence.get_case_run("obs-run-1")
    saved = next(o for o in stored["observations"] if o["observation_id"] == oid)
    assert saved["review"]["note"] == "Ageing received; 18% over 180 days"


def test_review_rejects_bad_input(client):
    http, _ = client
    assert http.patch(url(f"/OBS-{ENTITY}-WC_DETERIORATION"), json={"status": "CLOSED"}).status_code == 422
    assert http.patch(url("/OBS-NOPE"), json={"status": "ACCEPTED"}).status_code == 404
    assert http.get("/api/cases/NOCASE999/observations").status_code == 404


def test_explain_needs_a_real_provider(client):
    http, _ = client  # tests run with the mock provider
    assert http.post(url("/explain"), json={}).status_code == 409


class FakeLLM:
    name = "fake"
    model = "fake-model"

    def generate(self, prompt, system_prompt="", temperature=0.1, max_tokens=4000):
        facts = json.loads(prompt.split("Observation facts (JSON):\n", 1)[1].split("\n\nWrite", 1)[0])
        if facts["title"] == "Margin Compression":
            # An invented figure: must be rejected, keeping the rule-based text.
            return json.dumps({"summary": "Margin fell 3.7 points.", "detailed_explanation": "Costs rose.",
                               "recommended_investigation": []})
        return json.dumps({"summary": f"{facts['title']} needs committee attention.",
                           "detailed_explanation": facts["engine_summary"],
                           "recommended_investigation": ["Obtain supporting schedules."]})


def test_explain_adds_wording_without_changing_detection(client):
    http, container = client
    before = http.get(url()).json()["observations"]
    container.observations.llm_factory = FakeLLM
    body = http.post(url("/explain"), json={}).json()

    statuses = {oid: r["status"] for oid, r in body["results"].items()}
    assert statuses.pop(f"OBS-{ENTITY}-MARGIN_COMPRESSION") == "rejected"
    assert set(statuses.values()) == {"ok"}

    after = {o["observation_id"]: o for o in body["observations"]}
    for o in before:
        a = after[o["observation_id"]]
        for field in ("severity", "metrics", "trigger", "summary", "detailed_explanation", "recommended_investigation"):
            assert a[field] == o[field], (o["observation_id"], field)
    assert after[f"OBS-{ENTITY}-MARGIN_COMPRESSION"]["ai_explanation"] is None
    assert after[f"OBS-{ENTITY}-WC_DETERIORATION"]["ai_explanation"]["model"] == "fake-model"


def test_existing_case_endpoints_unaffected(client):
    http, _ = client
    case = http.get(f"/api/cases/{ENTITY}").json()
    assert case["recommendation"] == "decline"
