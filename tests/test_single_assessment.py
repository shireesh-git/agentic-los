"""The case record and the CAM come from one credit assessment."""

import copy

import pytest

import src.engines.cam_fact_builder as fact_builder
from src.agents.pipeline import SuperAgent
from src.core.llm_provider import MockLLMProvider


@pytest.fixture(scope="module")
def pipeline_context():
    from src.data.company_catalog import seed_company_store

    company = copy.deepcopy(seed_company_store()["PNCR001"])  # infra borrower: sector metrics matter
    return SuperAgent(llm_provider=MockLLMProvider()).execute_pipeline(
        company, stores={"extraction": {}, "etb": {}})


def test_cam_states_the_case_decision(pipeline_context):
    policy = pipeline_context["results"]["policy"]
    fact_pack = pipeline_context["results"]["narrative"]["fact_pack"]
    cam_decision = fact_pack["policy_decisions"]["tier3_recommendation"]

    assert cam_decision["recommendation"] == policy["recommendation"].recommendation.value
    assert cam_decision["risk_grade"] == policy["risk_score"].risk_grade
    assert cam_decision["composite_score"] == policy["risk_score"].composite_score
    assert cam_decision["conditions"] == policy["recommendation"].conditions
    assert cam_decision["collateral_requirement"] == policy["recommendation"].collateral_requirement


def test_fact_pack_does_not_recompute_when_given_an_assessment(pipeline_context, monkeypatch):
    def _fail(_):
        raise AssertionError("assessment recomputed")

    monkeypatch.setattr(fact_builder, "assess_credit", _fail)
    from src.agents.narrative_agent import NarrativeAgent

    assessment = NarrativeAgent._assessment(pipeline_context)
    fact_builder.build_cam_fact_pack(pipeline_context["company_data"], assessment=assessment)
