"""Credit Challenge Agent: the demo borrower, each rule's trigger, analyst handling, AI wording guard."""

import copy
import json
from pathlib import Path

import pytest

from src.agents.challenge_agent import CreditChallengeAgent, sync_challenges
from src.agents.investigation_agent import InvestigationAgent
from src.engines.observation_engine import detect_observations

FIXTURE = Path(__file__).parent / "fixtures" / "abce001_expected_challenges.json"


@pytest.fixture(scope="module")
def demo():
    """(fact pack, observations, investigations) for ABC Engineering, as a pipeline run produces them."""
    from src.data.company_catalog import seed_company_store
    from src.engines.cam_fact_builder import build_cam_fact_pack
    fp = build_cam_fact_pack(copy.deepcopy(seed_company_store()["ABCE001"]))
    obs = detect_observations(fp, "ABCE001", created_at="2026-10-07T00:00:00")
    tasks = InvestigationAgent().plan(obs, "ABCE001", created_at="2026-10-07T00:00:00")
    return fp, obs, tasks


def run(fp, obs, tasks):
    return CreditChallengeAgent().challenge(fp, obs, tasks, "ABCE001", created_at="2026-10-07T00:00:00")


def by_rule(challenges):
    return {c["rule_id"]: c for c in challenges}


def metric(ch, name):
    return next(m["value"] for m in ch["supporting_metrics"] if m["metric"] == name)


# ─── Demo borrower ───────────────────────────────────────────────────────────

def test_demo_borrower_gets_the_designed_challenges(demo):
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
    challenges = run(*demo)
    assert [c["challenge_id"] for c in challenges] == [e["challenge_id"] for e in expected["expected"]]
    for c, e in zip(challenges, expected["expected"]):
        assert (c["category"], c["severity"], c["status"]) == (e["category"], e["severity"], "OPEN")
        for name, value in e["metrics"].items():
            assert metric(c, name) == value, (c["challenge_id"], name)
        assert c["proposal_reference"] == expected["proposal"]
        assert c["challenge"] and c["rationale"] and c["required_response"] and c["agent_reasoning"]


def test_headline_challenge_matches_the_brief(demo):
    """Receivables vs revenue, and an ask explained by deterioration rather than growth."""
    ch = by_rule(run(*demo))["FACILITY_AMOUNT_CYCLE"]
    for figure in ("52.1%", "18.2%", "₹299.00 Cr", "₹251.20 Cr", "₹47.80 Cr", "54.54", "98.62", "₹250.00 Cr"):
        assert figure in ch["challenge"]
    assert any("debtor and inventory ageing" in r for r in ch["required_response"])
    assert ch["linked_investigation_ids"] == ["INV-ABCE001-RECEIVABLE_DETERIORATION", "INV-ABCE001-INVENTORY_BUILDUP"]


def test_no_challenge_makes_a_decision(demo):
    text = " ".join(c["challenge"] + c["rationale"] + " ".join(c["required_response"]) for c in run(*demo)).lower()
    # Describing who may approve a deviation is fine; deciding the facility is not.
    for phrase in ("recommend", "should be approved", "should be declined", "decline the", "reject", "not be sanctioned"):
        assert phrase not in text


def test_deterministic(demo):
    assert run(*copy.deepcopy(demo)) == run(*copy.deepcopy(demo))


# ─── Rules respond to the analysis ───────────────────────────────────────────

def test_resolving_investigations_changes_the_challenges(demo):
    fp, obs, tasks = copy.deepcopy(demo)
    for t in tasks:
        if t["priority"] == "P1":
            t["status"] = "RESOLVED"
    rules = by_rule(run(fp, obs, tasks))
    assert "UNRESOLVED_INVESTIGATIONS" not in rules
    assert rules["WORKING_CAPITAL_DP"]["severity"] == "MEDIUM"   # receivable investigation closed


def test_dismissed_observations_no_longer_support_a_challenge(demo):
    fp, obs, tasks = copy.deepcopy(demo)
    for o in obs:
        if o["trigger"]["rule_id"] == "POLICY_DEVIATION":
            o["status"] = "DISMISSED"
    assert "POLICY_EXCEPTIONS" not in by_rule(run(fp, obs, tasks))


def test_facility_amount_needs_a_lengthening_cycle(demo):
    fp, obs, tasks = copy.deepcopy(demo)
    latest = fp["ratio_analysis"]["FY2026"]["working_capital_cycle"]
    latest["value"] = fp["ratio_analysis"]["FY2025"]["working_capital_cycle"]["value"] + 5
    assert "FACILITY_AMOUNT_CYCLE" not in by_rule(run(fp, obs, tasks))


def test_facility_amount_challenges_the_enhancement_not_the_whole_limit(demo):
    fp, obs, tasks = copy.deepcopy(demo)
    fp["facility_details"].update({"existing_limit_cr": 200.0, "proposed_limit_cr": 300.0})
    ch = by_rule(run(fp, obs, tasks))["FACILITY_AMOUNT_CYCLE"]
    assert metric(ch, "requested_limit_cr") == 100.0
    assert ch["proposal_reference"] == "Working Capital limit enhancement ₹200.00 Cr → ₹300.00 Cr"


def test_term_loan_gets_no_working_capital_challenges(demo):
    fp, obs, tasks = copy.deepcopy(demo)
    fp["facility_details"]["facility_type"] = "term_loan"
    fp["drawing_power"] = {}
    rules = by_rule(run(fp, obs, tasks))
    assert "FACILITY_AMOUNT_CYCLE" not in rules and "WORKING_CAPITAL_DP" not in rules
    assert "REPAYMENT_CAPACITY" in rules


def test_repayment_capacity_critical_below_one(demo):
    fp, obs, tasks = copy.deepcopy(demo)
    fp["ratio_analysis"]["FY2026"]["dscr"]["value"] = 0.9
    assert by_rule(run(fp, obs, tasks))["REPAYMENT_CAPACITY"]["severity"] == "CRITICAL"


def test_healthy_case_is_not_challenged(demo):
    fp, _, _ = copy.deepcopy(demo)
    fp["ratio_analysis"]["FY2026"] = copy.deepcopy(fp["ratio_analysis"]["FY2025"])
    fp["financial_summary"]["periods"]["FY2026"] = copy.deepcopy(fp["financial_summary"]["periods"]["FY2025"])
    fp["cash_flow_repayment"]["periods"]["FY2026"] = copy.deepcopy(fp["cash_flow_repayment"]["periods"]["FY2025"])
    fp["drawing_power"] = {}
    assert run(fp, [], []) == []


def test_rules_can_be_switched_off(demo):
    settings = {"leverage": {"enabled": False}}
    found = CreditChallengeAgent().challenge(*demo, "ABCE001", settings=settings)
    assert "LEVERAGE" not in by_rule(found)


# ─── Analyst handling ────────────────────────────────────────────────────────

def test_sync_keeps_analyst_handling(demo):
    stored = run(*demo)
    rules = by_rule(stored)
    rules["LEVERAGE"]["status"] = "ACCEPTED"
    rules["LEVERAGE"]["review"] = {"response": "Promoter infusion of equity agreed"}
    fp, obs, tasks = copy.deepcopy(demo)
    for t in tasks:
        t["status"] = "RESOLVED"
    merged = by_rule(sync_challenges(run(fp, obs, tasks), stored))
    assert merged["LEVERAGE"]["status"] == "ACCEPTED"
    assert merged["LEVERAGE"]["review"]["response"] == "Promoter infusion of equity agreed"
    assert "UNRESOLVED_INVESTIGATIONS" not in merged       # trigger gone while still OPEN: dropped
    assert sync_challenges(run(*demo), run(*demo)) == run(*demo)


# ─── AI wording: wording only, figures guarded ───────────────────────────────

class FakeLLM:
    name = "fake"
    model = "fake-model"

    def __init__(self, reply):
        self.reply = reply

    def generate(self, prompt, system_prompt="", temperature=0.1, max_tokens=4000):
        assert "Do NOT approve, decline, recommend" in system_prompt
        return self.reply


def test_wording_accepts_given_figures_and_rejects_invented_ones(demo):
    from src.services.challenge_narrator import word_challenge

    ch = by_rule(run(*demo))["FACILITY_AMOUNT_CYCLE"]
    good = json.dumps({"challenge": "Receivables rose 52.1% on revenue growth of 18.2%; ₹251.20 Cr of the working-capital "
                                    "increase reflects a slower cycle. Why does the bank fund that?",
                       "rationale": "The limit could be absorbed by doubtful receivables."})
    assert word_challenge(ch, FakeLLM(good), "ABC")["challenge"].startswith("Receivables rose")
    bad = json.dumps({"challenge": "About 60% of receivables are overdue.", "rationale": "Material risk."})
    with pytest.raises(ValueError, match="figures not in the challenge"):
        word_challenge(ch, FakeLLM(bad), "ABC")
