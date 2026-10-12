"""Maker-checker approval workflow through the HTTP API."""

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.application.container import build_container

ENTITY = "MFL001"
RM = {"X-User-Id": "rm.asha", "X-User-Role": "relationship_manager"}
ZONAL = {"X-User-Id": "zonal.vikram", "X-User-Role": "zonal_credit_committee"}
BRANCH = {"X-User-Id": "branch.neha", "X-User-Role": "branch_credit_committee"}


@pytest.fixture()
def client():
    container = build_container()
    # A finished case without running the (slow) pipeline: 80 Cr, grade B, system says approve.
    case = {"run_id": "run-1", "entity_id": ENTITY, "company_name": "Test Co",
            "recommendation": "approve", "risk_grade": "B", "requested_amount_cr": 80}
    container.state.cases[ENTITY] = case
    container.persistence.save_case_run(case)
    container.persistence.reset_workflow(ENTITY, "run-1")
    yield TestClient(create_app(container)), container
    container.persistence.delete_company(ENTITY)


def act(client, action, headers, **body):
    return client.post(f"/api/cases/{ENTITY}/workflow/{action}", headers=headers, json=body)


def test_full_maker_checker_flow(client):
    http, container = client
    status = http.get(f"/api/cases/{ENTITY}/workflow").json()
    assert status["status"] == "draft"
    assert status["required_authority"]["id"] == "zonal_credit_committee"  # 80 Cr > branch limit

    assert act(http, "submit", RM, comments="Ready").json()["status"] == "submitted"

    queue = http.get("/api/approvals/queue", params={"authority": "zonal_credit_committee"}).json()
    assert [c["entity_id"] for c in queue["cases"]] == [ENTITY]
    assert http.get("/api/approvals/queue", params={"authority": "branch_credit_committee"}).json()["cases"] == []

    assert act(http, "approve", BRANCH).status_code == 403          # below required authority
    assert act(http, "return", ZONAL).status_code == 400            # comments required
    assert act(http, "return", ZONAL, comments="Add DSCR workings").json()["status"] == "returned_for_rework"

    assert act(http, "submit", RM).json()["status"] == "submitted"
    final = act(http, "approve", ZONAL, conditions=["Quarterly stock statements"]).json()
    assert final["status"] == "approved"
    assert [h["action"] for h in final["history"]] == ["submit", "return", "submit", "approve"]
    assert final["history"][-1]["conditions"] == ["Quarterly stock statements"]
    assert final["allowed_actions"] == []


def test_maker_cannot_approve_own_case(client):
    http, _ = client
    self_checker = {"X-User-Id": "rm.asha", "X-User-Role": "zonal_credit_committee"}
    act(http, "submit", RM)
    assert act(http, "approve", self_checker).status_code == 403


def test_only_submitter_can_recall_and_submitted_case_cannot_rerun(client):
    http, _ = client
    act(http, "submit", RM)
    other_rm = {"X-User-Id": "rm.other", "X-User-Role": "relationship_manager"}
    assert act(http, "recall", other_rm).status_code == 403
    assert http.post(f"/api/cases/{ENTITY}/run").status_code == 409
    assert act(http, "recall", RM).json()["status"] == "draft"


def test_actor_headers_required_and_invalid_transitions_rejected(client):
    http, _ = client
    assert act(http, "submit", {}).status_code == 403
    assert act(http, "approve", ZONAL).status_code == 409            # draft cannot be approved
    assert act(http, "launch", RM).status_code == 400
