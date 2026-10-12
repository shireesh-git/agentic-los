"""Investigations through the HTTP API: generated from observations, analyst status, re-planning, phrasing."""

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
    # A case recorded before Steps 1-2: neither observations nor investigations are stored yet.
    case = {"run_id": "inv-run-1", "entity_id": ENTITY, "company_name": "ABC Engineering & Infrastructure Ltd.",
            "recommendation": "decline", "risk_grade": "D", "requested_amount_cr": 250,
            "run_at": "2026-10-07T10:00:00", "fact_pack": demo_fact_pack}
    container.state.cases[ENTITY] = case
    container.persistence.save_case_run(case)
    yield TestClient(create_app(container)), container
    container.state.cases.pop(ENTITY, None)
    container.persistence.delete_company(ENTITY)   # leave no partial case for later tests


def url(path=""):
    return f"/api/cases/{ENTITY}/investigations{path}"


def test_observations_automatically_create_investigations(client):
    http, container = client
    body = http.get(url()).json()
    assert body["summary"]["open"] == 7
    assert body["summary"]["open_by_priority"] == {"P1": 3, "P2": 3, "P3": 1}
    first = body["investigations"][0]
    assert body["observations"][first["observation_id"]]["title"] == "Working Capital Deterioration"
    assert len(container.persistence.get_case_run("inv-run-1")["investigations"]) == 7


def test_status_and_note_persist(client):
    http, container = client
    iid = f"INV-{ENTITY}-LEVERAGE"
    r = http.patch(url(f"/{iid}"), json={"status": "IN_PROGRESS", "note": "Debt schedule requested"})
    assert r.status_code == 200 and r.json()["investigation"]["status"] == "IN_PROGRESS"
    saved = next(t for t in container.persistence.get_case_run("inv-run-1")["investigations"]
                 if t["investigation_id"] == iid)
    assert saved["review"]["note"] == "Debt schedule requested"
    assert http.get(url()).json()["summary"]["by_status"]["IN_PROGRESS"] == 1


def test_dismissing_an_observation_re_plans_tasks(client):
    http, _ = client
    http.get(url())
    http.patch(f"/api/cases/{ENTITY}/observations/OBS-{ENTITY}-INVENTORY_BUILDUP", json={"status": "DISMISSED"})
    ids = [t["investigation_id"] for t in http.get(url()).json()["investigations"]]
    assert f"INV-{ENTITY}-INVENTORY_BUILDUP" not in ids and len(ids) == 6


def test_bad_input(client):
    http, _ = client
    assert http.patch(url(f"/INV-{ENTITY}-LEVERAGE"), json={"status": "CLOSED"}).status_code == 422
    assert http.patch(url("/INV-NOPE"), json={"status": "WAIVED"}).status_code == 404
    assert http.post(url("/phrase"), json={}).status_code == 409   # tests run with the mock provider


class FakeLLM:
    name = "fake"
    model = "fake-model"

    def generate(self, prompt, system_prompt="", temperature=0.1, max_tokens=4000):
        facts = json.loads(prompt.split("Investigation facts (JSON):\n", 1)[1].split("\n\nWrite", 1)[0])
        docs = " ".join(f"{i}. {d['item']}." for i, d in enumerate(facts["documents"], 1))
        return json.dumps({"request_text": f"Dear Finance Team, for our review of {facts['title']} please share: {docs}"})


def test_phrase_adds_request_text_without_changing_the_task(client):
    http, container = client
    before = {t["investigation_id"]: t for t in http.get(url()).json()["investigations"]}
    container.investigations.llm_factory = FakeLLM
    body = http.post(url("/phrase"), json={"investigation_ids": [f"INV-{ENTITY}-DATA_RELIABILITY"]}).json()
    assert body["results"] == {f"INV-{ENTITY}-DATA_RELIABILITY": {"status": "ok"}}
    after = {t["investigation_id"]: t for t in body["investigations"]}
    task = after[f"INV-{ENTITY}-DATA_RELIABILITY"]
    assert task["request_text"]["text"].startswith("Dear Finance Team")
    for field in ("priority", "reason", "required_evidence", "status", "observation_id"):
        assert task[field] == before[task["investigation_id"]][field]
