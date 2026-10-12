"""Credit challenges through the HTTP API: generated from the analysis, analyst handling, AI wording."""

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
    # A case recorded before Steps 1-3: observations, investigations and challenges are all back-filled.
    case = {"run_id": "chl-run-1", "entity_id": ENTITY, "company_name": "ABC Engineering & Infrastructure Ltd.",
            "recommendation": "decline", "risk_grade": "D", "requested_amount_cr": 250,
            "run_at": "2026-10-07T10:00:00", "fact_pack": demo_fact_pack}
    container.state.cases[ENTITY] = case
    container.persistence.save_case_run(case)
    yield TestClient(create_app(container)), container
    container.state.cases.pop(ENTITY, None)
    container.persistence.delete_company(ENTITY)   # leave no partial case for later tests


def url(path=""):
    return f"/api/cases/{ENTITY}/challenges{path}"


def test_challenges_are_raised_and_counted(client):
    http, container = client
    body = http.get(url()).json()
    assert body["summary"]["open"] == 7
    assert body["summary"]["open_by_severity"] == {"CRITICAL": 0, "HIGH": 6, "MEDIUM": 1, "LOW": 0}
    first = body["challenges"][0]
    assert body["links"][first["linked_investigation_ids"][0]]["priority"] == "P1"
    assert len(container.persistence.get_case_run("chl-run-1")["challenges"]) == 7
    # The case recommendation is untouched.
    assert http.get(f"/api/cases/{ENTITY}").json()["recommendation"] == "decline"


def test_status_and_response_persist(client):
    http, container = client
    cid = f"CHL-{ENTITY}-LEVERAGE"
    r = http.patch(url(f"/{cid}"), json={"status": "ACCEPTED", "response": "Promoter equity of Rs 100 Cr committed"})
    assert r.status_code == 200 and r.json()["challenge"]["status"] == "ACCEPTED"
    saved = next(c for c in container.persistence.get_case_run("chl-run-1")["challenges"] if c["challenge_id"] == cid)
    assert saved["review"]["response"] == "Promoter equity of Rs 100 Cr committed"
    assert http.get(url()).json()["summary"]["by_status"]["ACCEPTED"] == 1


def test_resolving_p1_investigations_removes_the_open_investigations_challenge(client):
    http, _ = client
    http.get(url())
    for inv in ("RECEIVABLE_DETERIORATION", "DATA_RELIABILITY", "POLICY_EXCEPTION"):
        http.patch(f"/api/cases/{ENTITY}/investigations/INV-{ENTITY}-{inv}", json={"status": "RESOLVED"})
    ids = [c["challenge_id"] for c in http.get(url()).json()["challenges"]]
    assert f"CHL-{ENTITY}-UNRESOLVED_INVESTIGATIONS" not in ids and len(ids) == 6


def test_bad_input(client):
    http, _ = client
    assert http.patch(url(f"/CHL-{ENTITY}-LEVERAGE"), json={"status": "APPROVED"}).status_code == 422
    assert http.patch(url("/CHL-NOPE"), json={"status": "ADDRESSED"}).status_code == 404
    assert http.post(url("/word"), json={}).status_code == 409   # tests run with the mock provider


class FakeLLM:
    name = "fake"
    model = "fake-model"

    def generate(self, prompt, system_prompt="", temperature=0.1, max_tokens=4000):
        facts = json.loads(prompt.split("Challenge facts (JSON):\n", 1)[1].split("\n\nWrite", 1)[0])
        return json.dumps({"challenge": facts["engine_challenge"], "rationale": "This matters for the bank's exposure."})


def test_wording_leaves_the_challenge_unchanged(client):
    http, container = client
    before = {c["challenge_id"]: c for c in http.get(url()).json()["challenges"]}
    container.challenges.llm_factory = FakeLLM
    body = http.post(url("/word"), json={"challenge_ids": [f"CHL-{ENTITY}-FACILITY_AMOUNT_CYCLE"]}).json()
    assert body["results"] == {f"CHL-{ENTITY}-FACILITY_AMOUNT_CYCLE": {"status": "ok"}}
    after = next(c for c in body["challenges"] if c["challenge_id"] == f"CHL-{ENTITY}-FACILITY_AMOUNT_CYCLE")
    for field in ("challenge", "severity", "supporting_metrics", "required_response", "status"):
        assert after[field] == before[after["challenge_id"]][field]
    assert after["ai_wording"]["model"] == "fake-model"
