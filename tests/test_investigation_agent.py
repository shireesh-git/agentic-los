"""Investigation Agent: routing, priority, evidence, sync with analyst work, the demo borrower, request phrasing."""

import copy
import json
from pathlib import Path

import pytest

from src.agents.investigation_agent import InvestigationAgent, sync_investigations
from src.engines.observation_engine import detect_observations

FIXTURE = Path(__file__).parent / "fixtures" / "abce001_expected_investigations.json"


@pytest.fixture(scope="module")
def demo_observations():
    from src.data.company_catalog import seed_company_store
    from src.engines.cam_fact_builder import build_cam_fact_pack
    fp = build_cam_fact_pack(copy.deepcopy(seed_company_store()["ABCE001"]))
    return detect_observations(fp, "ABCE001", created_at="2026-10-07T00:00:00")


def plan(observations):
    return InvestigationAgent().plan(observations, "ABCE001", created_at="2026-10-07T00:00:00")


def by_type(tasks):
    return {t["investigation_type"]: t for t in tasks}


def with_status(observations, rule_id, status=None, severity=None):
    obs = copy.deepcopy(observations)
    for o in obs:
        if o["trigger"]["rule_id"] == rule_id:
            if status:
                o["status"] = status
            if severity:
                o["severity"] = severity
    return obs


# ─── Demo borrower ───────────────────────────────────────────────────────────

def test_demo_borrower_gets_the_designed_investigations(demo_observations):
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
    tasks = plan(demo_observations)
    assert [t["investigation_id"] for t in tasks] == [e["investigation_id"] for e in expected["expected"]]
    for t, e in zip(tasks, expected["expected"]):
        assert t["priority"] == e["priority"], t["investigation_id"]
        assert t["observation_id"] == e["observation_id"]
        assert t["related_observation_ids"] == e["related"]
        assert [ev["item"] for ev in t["required_evidence"]] == e["evidence"]
        assert t["status"] == "OPEN" and t["case_id"] == "ABCE001"
        assert t["reason"] and t["agent_reasoning"] and t["title"]
    assert [o["observation_id"] for o in InvestigationAgent().unrouted(demo_observations)] == expected["unrouted"]


def test_reasons_quote_the_observation_figures(demo_observations):
    tasks = by_type(plan(demo_observations))
    assert "52.1%" in tasks["RECEIVABLE_DETERIORATION"]["reason"] and "18.2%" in tasks["RECEIVABLE_DETERIORATION"]["reason"]
    assert "+1.5%" in tasks["EARNINGS_TO_CASH"]["reason"] and "-76.3%" in tasks["EARNINGS_TO_CASH"]["reason"]
    assert "4.1x" in tasks["LEVERAGE"]["reason"]
    assert "1.19x" in tasks["DEBT_SERVICING"]["reason"] and "1.2x" in tasks["DEBT_SERVICING"]["reason"]
    ageing = tasks["RECEIVABLE_DETERIORATION"]["required_evidence"][0]["description"]
    assert "₹587.00 Cr" in ageing   # reconciles to the reported receivables
    gst = tasks["DATA_RELIABILITY"]["required_evidence"][0]["description"]
    assert "GSTR-1" in gst and "2080.00 (audited)" in gst and "1835.00 (GST)" in gst
    dscr = tasks["POLICY_EXCEPTION"]["required_evidence"][0]["description"]
    assert "DSRA" in dscr and "1.19" in dscr


def test_agent_reasoning_explains_priority(demo_observations):
    tasks = by_type(plan(demo_observations))
    assert any("2 observations point to the same issue" in s for s in tasks["RECEIVABLE_DETERIORATION"]["agent_reasoning"])
    assert any("cannot rely on the case" in s for s in tasks["DATA_RELIABILITY"]["agent_reasoning"])
    assert any("Base priority P3" in s for s in tasks["INVENTORY_BUILDUP"]["agent_reasoning"])


def test_deterministic(demo_observations):
    assert plan(copy.deepcopy(demo_observations)) == plan(copy.deepcopy(demo_observations))


# ─── Routing rules ───────────────────────────────────────────────────────────

def test_closed_observations_open_no_task(demo_observations):
    for status in ("EXPLAINED", "ACCEPTED", "DISMISSED"):
        tasks = by_type(plan(with_status(demo_observations, "LEVERAGE_INCREASE", status)))
        assert "LEVERAGE" not in tasks


def test_low_severity_needs_an_explicit_request(demo_observations):
    low = with_status(demo_observations, "INVENTORY_BUILDUP", severity="LOW")
    assert "INVENTORY_BUILDUP" not in by_type(plan(low))
    flagged = with_status(low, "INVENTORY_BUILDUP", status="INVESTIGATION_REQUIRED")
    assert by_type(plan(flagged))["INVENTORY_BUILDUP"]["priority"] == "P3"


def test_receivable_task_survives_when_one_of_its_observations_is_dismissed(demo_observations):
    obs = with_status(demo_observations, "WC_DETERIORATION", "DISMISSED")
    task = by_type(plan(obs))["RECEIVABLE_DETERIORATION"]
    assert task["observation_id"] == "OBS-ABCE001-RECEIVABLE_COLLECTION"
    assert task["related_observation_ids"] == [] and task["priority"] == "P2"   # no longer corroborated


def test_critical_observation_is_p1_and_failed_hard_rule_is_listed(demo_observations):
    obs = copy.deepcopy(demo_observations)
    pol = next(o for o in obs if o["trigger"]["rule_id"] == "POLICY_DEVIATION")
    pol["severity"] = "CRITICAL"
    pol["trigger"]["observed"]["failed_hard_rules"] = ["HR_BUREAU_STATUS"]
    task = by_type(plan(obs))["POLICY_EXCEPTION"]
    assert task["priority"] == "P1"
    assert task["required_evidence"][0]["item"] == "Hard rule HR_BUREAU_STATUS — resolution"


def test_no_observations_no_tasks():
    assert plan([]) == []


# ─── Sync with analyst work ──────────────────────────────────────────────────

def test_sync_keeps_analyst_work_and_drops_unneeded_open_tasks(demo_observations):
    stored = plan(demo_observations)
    tasks = {t["investigation_type"]: t for t in stored}
    tasks["LEVERAGE"]["status"] = "IN_PROGRESS"
    tasks["LEVERAGE"]["review"] = {"note": "Debt schedule received"}
    tasks["DEBT_SERVICING"]["status"] = "RESOLVED"

    # The analyst then dismisses the observations behind three tasks.
    obs = demo_observations
    for rule in ("LEVERAGE_INCREASE", "INVENTORY_BUILDUP", "DEBT_SERVICING_PRESSURE"):
        obs = with_status(obs, rule, "DISMISSED")
    merged = by_type(sync_investigations(plan(obs), stored))

    assert merged["LEVERAGE"]["status"] == "IN_PROGRESS"                 # work started: kept
    assert merged["LEVERAGE"]["review"]["note"] == "Debt schedule received"
    assert merged["DEBT_SERVICING"]["status"] == "RESOLVED"              # finished: kept
    assert "INVENTORY_BUILDUP" not in merged                             # still OPEN: dropped
    assert merged["RECEIVABLE_DETERIORATION"]["status"] == "OPEN"


def test_sync_is_stable(demo_observations):
    stored = plan(demo_observations)
    assert sync_investigations(plan(demo_observations), stored) == stored


# ─── LLM phrasing: wording only, figures guarded ─────────────────────────────

class FakeLLM:
    name = "fake"
    model = "fake-model"

    def __init__(self, reply):
        self.reply = reply

    def generate(self, prompt, system_prompt="", temperature=0.1, max_tokens=4000):
        assert "Do NOT add, drop or change the documents requested" in system_prompt
        return self.reply


def test_phrase_request_accepts_given_figures_and_rejects_invented_ones(demo_observations):
    from src.services.investigation_narrator import phrase_request

    task = by_type(plan(demo_observations))["RECEIVABLE_DETERIORATION"]
    good = json.dumps({"request_text": "Dear Finance Team, receivables grew 52.1% against revenue growth of 18.2%. "
                                       "Please share: 1. Debtor ageing schedule 2. Top-10 customer exposure."})
    assert phrase_request(task, FakeLLM(good), "ABC")["text"].startswith("Dear Finance Team")

    bad = json.dumps({"request_text": "Dear Finance Team, receivables now exceed 140 days on average; please share "
                                      "the debtor ageing schedule and top customer list."})
    with pytest.raises(ValueError, match="figures not in the task"):
        phrase_request(task, FakeLLM(bad), "ABC")
    with pytest.raises(ValueError):
        phrase_request(task, FakeLLM("Please send the documents."), "ABC")


def test_phrase_request_may_quote_amounts_with_thousands_separators(demo_observations):
    from src.services.investigation_narrator import phrase_request

    task = by_type(plan(demo_observations))["LEVERAGE"]
    reply = json.dumps({"request_text": "Dear Finance Team, please share a lender-wise debt schedule reconciled to "
                                        "total debt of Rs 1,100.00 Cr, and the repayment schedule."})
    assert "1,100.00" in phrase_request(task, FakeLLM(reply), "ABC")["text"]
