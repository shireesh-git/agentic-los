"""One proposal's lifecycle (withdraw, archive, delete, never the borrower's other proposals) and
clarifications inside a stage (the proposal stays where it is; its SLA clock pauses)."""

from datetime import datetime, timedelta

import pytest

from src.application.container import build_container
from src.application.errors import ConflictError, ForbiddenError

E = "INFY001"


@pytest.fixture(scope="module")
def svc():
    flow = build_container().flow
    flow.reset({"user": {"id": "test"}}, E)
    yield flow
    flow.reset({"user": {"id": "test"}}, E)


def _at_underwriting(svc, rm):
    case = svc.create(rm, entity_id=E)
    case = svc.store.get(case["case_id"])
    svc._enter(case, "credit_risk")
    svc.store.save(case)
    return case["case_id"]


def test_clarification_keeps_the_stage_and_pauses_the_clock(svc):
    rm, cro = svc.sign_in("f_rm"), svc.sign_in("f_cro")
    cid = _at_underwriting(svc, rm)
    v = svc.view(cid, cro)
    assert [t["stage"] for t in v["query_targets"]] == ["rm"]

    t0 = datetime.now()
    svc.now = lambda: t0
    svc.raise_query(cid, cro, "Is the promoter guarantee in place for the term loan?")
    svc.now = lambda: t0 + timedelta(hours=5)                       # five hours waiting on the RM
    case = svc.store.get(cid)
    assert case["stage"] == "credit_risk" and svc._ageing(case)[0] == pytest.approx(0, abs=0.01)
    # Credit cannot approve with its question open; the RM sees the proposal in their queue
    assert any("Clarification Q1" in b for b in svc.blockers(case))
    assert cid in [r["case_id"] for r in svc.queue(rm)["mine"]]
    with pytest.raises(ForbiddenError):
        svc.answer_query(cid, cro, "Q1", "self-answer")

    svc.answer_query(cid, rm, "Q1", "Yes — executed on 3 Nov, copy in Data Sources")
    svc.now = lambda: t0 + timedelta(hours=7)                       # two more hours at Credit
    case = svc.store.get(cid)
    assert case["stage"] == "credit_risk" and not case.get("paused_since")
    assert svc._ageing(case)[0] == pytest.approx(2, abs=0.01)
    assert not any("Clarification" in b for b in svc.blockers(case))
    assert cid not in [r["case_id"] for r in svc.queue(rm)["mine"]]
    q = svc.view(cid, cro)["queries"][0]
    assert q["status"] == "answered" and q["answered_by"] == "Ananya Rao"
    kinds = [e["kind"] for e in svc.store.events(cid)]
    assert "query_raise" in kinds and "query_answer" in kinds

    # an open question closes when the proposal is returned, and the paused time is kept on the stage
    svc.raise_query(cid, cro, "Second question")
    svc.now = lambda: t0 + timedelta(hours=8)
    svc.act(cid, cro, "send_back", "Need the guarantee deed")
    case = svc.store.get(cid)
    assert case["queries"][1]["status"] == "closed" and case["stage"] == "rm"
    assert case["stage_history"][-2]["clarification_seconds"] == pytest.approx(5 * 3600 + 3600, abs=5)
    svc.now = datetime.now


def test_withdraw_archive_delete_touch_one_proposal_only(svc):
    rm, cro = svc.sign_in("f_rm"), svc.sign_in("f_cro")
    first = svc.queue(rm)["all"][0]["case_id"]                      # the open one from the test above
    with pytest.raises(ForbiddenError):
        svc.withdraw(first, cro, "no")
    with pytest.raises(ConflictError):
        svc.archive(first, rm)
    svc.withdraw(first, rm, "Borrower no longer needs the facility")
    v = svc.view(first, rm)
    assert v["status"] == "withdrawn" and v["withdrawn"]["reason"].startswith("Borrower") and v["can_archive"]

    second = svc.create(rm, entity_id=E)["case_id"]                 # the borrower is free for a new proposal
    svc.archive(first, rm)
    rows = {r["case_id"]: r for r in svc.queue(rm)["all"]}
    assert rows[first]["archived"] and rows[first]["status"] == "withdrawn" and second in rows

    svc.delete_case(first, rm)
    ids = [r["case_id"] for r in svc.queue(rm)["all"]]
    assert first not in ids and second in ids and not svc.store.events(first)

    case = svc.store.get(second)
    case["sanction"] = {"limit_cr": 1.0}
    svc.store.save(case)
    with pytest.raises(ConflictError):
        svc.delete_case(second, rm)
