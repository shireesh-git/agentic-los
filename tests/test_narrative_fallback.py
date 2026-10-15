"""An unreachable LLM (no API key, no network) does not stop the credit case when
narrative.on_llm_unavailable is 'template': the CAM is rendered from the templates and labelled."""

import pytest

from src.agents.narrative_agent import NarrativeAgent
from src.core.config_manager import config
from src.data.company_catalog import seed_company_store
from tests.test_cam_composer import full_case


class OfflineLLM:
    name = "nvidia_nim"
    model = "offline-model"

    def test_connection(self):
        return {"status": "error", "provider": "openai",
                "message": "Missing credentials. Please pass an `api_key` or set the OPENAI_API_KEY environment variable."}

    def generate(self, *a, **k):  # never reached: the connection test fails first
        raise AssertionError("no call expected")


@pytest.fixture()
def agent(monkeypatch):
    company = seed_company_store()["ABCE001"]
    fact_pack = full_case(company)["fact_pack"]
    import src.engines.cam_fact_builder as builder
    monkeypatch.setattr(builder, "build_cam_fact_pack", lambda *a, **k: fact_pack)
    monkeypatch.setattr(NarrativeAgent, "_assessment", lambda self, ctx: None)
    a = NarrativeAgent(llm_provider=OfflineLLM())
    ctx = {"company_data": company, "results": {"pep_screening": {}, "financial_analysis": {}}}
    return a, ctx


def _narrative(monkeypatch, mode):
    settings = dict(config.get("llm_providers", "narrative"), mode="llm", on_llm_unavailable=mode)
    monkeypatch.setattr(config, "get_narrative_settings", lambda: settings)
    monkeypatch.setattr(NarrativeAgent, "_template_mode", lambda self: False)


def test_an_unreachable_llm_falls_back_to_the_templates_and_says_so(agent, monkeypatch):
    a, ctx = agent
    _narrative(monkeypatch, "template")
    out = a.run(ctx)
    assert out["narrative_mode"] == "template_fallback" and len(out["cam_text"]) > 1000
    assert "Missing credentials" in out["narrative_warning"] and a.diagnostics["execution_mode"] == "template_fallback"


def test_with_fail_configured_an_unreachable_llm_still_stops_the_case(agent, monkeypatch):
    a, ctx = agent
    _narrative(monkeypatch, "fail")
    with pytest.raises(RuntimeError, match="LLM connection failed"):
        a.run(ctx)
