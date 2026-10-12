"""Agent evaluation harness (M6.1) and the pipeline's per-agent diagnostics."""

import copy
import json

import pytest

from src.devtools import agent_harness as h

CASE = "ABCE001"   # fully specified demo borrower: no OCR, no network


@pytest.fixture(scope="module")
def all_agents():
    return h.run_case(CASE, agents="all", refresh_snapshot=True)


def by_agent(result):
    return {r["agent"]: r for r in result["reports"]}


def test_runs_one_agent_without_the_full_cam(all_agents):
    result = h.run_case(CASE, agents="financial_analysis", stop_after="financial_analysis")
    assert result["executed"] == ["data_ingestion", "pep_screening", "financial_analysis"]
    rep = result["reports"][0]
    assert rep["agent"] == "financial_analysis" and rep["status"] in ("PASS", "PARTIAL")
    assert rep["llm_invoked"] is False and rep["execution_mode"] == "deterministic"
    assert rep["duration_ms"] is not None and rep["structured_output"]["latest_ratios"]["type"] == "list[RatioResult] (27)"
    assert rep["downstream_observed"] is False            # stopped before any consumer


def test_snapshot_is_reused_and_invalidated(all_agents):
    assert all_agents["snapshot"]["source"] == "fresh"
    again = h.run_case(CASE, agents="validation", stop_after="validation")
    assert again["snapshot"]["source"] == "cache"
    company = copy.deepcopy(h.load_company(CASE))
    company["facility"].amount_requested_cr += 1          # the company record changed
    snap = h.get_snapshot(CASE, company)
    assert snap["meta"]["source"] == "fresh" and "changed" in snap["meta"]["stale_reason"]
    h.get_snapshot(CASE, h.load_company(CASE), refresh=True)   # restore for later tests


def test_downstream_consumption_is_observed_at_runtime(all_agents):
    fa = by_agent(all_agents)["financial_analysis"]["downstream"]
    assert set(fa["latest_ratios"]["read_by_at_runtime"]) == {"policy", "narrative"}
    # M6.2: the authoritative multi-period ratios and growth are consumed, not recomputed.
    assert set(fa["multi_period_ratios"]["read_by_at_runtime"]) == {"benchmark", "narrative"}
    assert fa["growth_metrics"]["read_by_at_runtime"] == ["narrative"]
    pep = by_agent(all_agents)["pep_screening"]["downstream"]
    assert pep["pep_result"]["read_by_at_runtime"] == ["narrative"]
    assert pep["adverse_headlines"]["consumed"] is False
    ing = by_agent(all_agents)["data_ingestion"]["downstream"]
    assert set(ing["bureau_data"]["read_by_at_runtime"]) == {"validation", "policy"}
    assert ing["mca_data"]["consumed"] is False


def test_every_agent_reports_the_required_fields(all_agents):
    required = {"agent", "case_id", "status", "started_at", "ended_at", "duration_ms", "execution_mode",
                "llm_invoked", "models", "prompt_version", "code_version", "input_summary", "raw_output",
                "structured_output", "evidence", "confidence", "warnings", "errors", "checks", "downstream",
                "llm_calls", "contract"}
    reports = by_agent(all_agents)
    assert list(reports) == ["data_ingestion", "pep_screening", "financial_analysis", "validation", "benchmark",
                             "policy", "narrative"]
    for rep in reports.values():
        assert required <= set(rep), rep["agent"]
        json.dumps(rep, default=str)                     # machine-readable
        assert h.render_report(rep).startswith(f"Agent: {rep['agent']}")


def test_narrative_plan_shows_lineage_without_calling_an_llm(all_agents):
    rep = by_agent(all_agents)["narrative"]
    assert rep["llm_invoked"] is False and rep["execution_mode"] == "plan (no LLM)"
    assert rep["prompt_version"]
    checks = {c["check"]: c for c in rep["checks"]}
    for name in ("ratio_analysis from financial_analysis", "Growth figures from financial_analysis",
                 "validation_exceptions from validation agent", "policy_decisions from policy agent",
                 "No fabricated external intelligence", "Prompts asking the LLM to compute", "Data provenance labelled"):
        assert checks[name]["status"] == "pass", (name, checks[name]["detail"])
    assert "synthetic demo" in checks["Data provenance labelled"]["detail"]
    plan = [p for p in rep["raw_output"]["section_plan"] if p["kind"] == "llm"]
    # No verified social-media data for the demo borrower: that section is skipped instead of fed mock data.
    assert len(plan) == 20 and all(p["prompt"].startswith("## Section:") for p in plan)
    assert {p["section"]: p["kind"] for p in rep["raw_output"]["section_plan"]}["social_media"] == "skipped"
    assert all('"_provenance"' in p["prompt"] for p in plan)


class FakeLLM:
    name = "fake"
    model = "fake-model"

    def generate(self, prompt, system_prompt="", temperature=0.1, max_tokens=4000):
        return "## 15. Peer Comparison & Benchmarking\n\nDebt/EBITDA is 9.99x against a peer median of 3.5x."

    def test_connection(self):
        return {"status": "ok"}


def test_selected_section_goes_to_the_llm_with_prompt_and_figure_check():
    result = h.run_case(CASE, agents="narrative", narrative_mode="llm", sections=["benchmarking"],
                        llm_factory=FakeLLM)
    rep = result["reports"][0]
    assert rep["llm_invoked"] and rep["llm_call_count"] == 1 and rep["models"] == ["fake:fake-model"]
    call = rep["llm_calls"][0]
    assert call["system_prompt"] and "## Section: 15. Peer Comparison" in call["prompt"]
    assert "api_key" not in json.dumps(call).lower()
    section = next(c for c in rep["checks"] if c["check"] == "Section benchmarking figures")
    assert section["status"] == "warn" and "9.99" in section["detail"]


def test_baseline_save_and_compare(all_agents):
    rep = by_agent(all_agents)["benchmark"]
    h.save_baseline(rep, "before")
    assert h.compare_with_baseline(rep, "before")["output_changed"] is False
    changed = copy.deepcopy(rep)
    changed["raw_output"]["worst_benchmarks"] = []
    diff = h.compare_with_baseline(changed, "before")
    assert diff["output_changed"] and any(c["field"] == "output: worst_benchmarks" for c in diff["changes"])
    with pytest.raises(FileNotFoundError):
        h.compare_with_baseline(rep, "missing")


def test_comparison_rows(all_agents):
    rows = h.comparison_rows(all_agents["reports"])
    assert [r["agent"] for r in rows][:2] == ["data_ingestion", "pep_screening"]
    assert {"case", "duration_ms", "llm_called", "output_bytes", "structured_output", "evidence", "errors",
            "warnings"} <= set(rows[0])
    assert "case" in h.render_comparison(rows)


def test_unknown_agent_is_rejected():
    with pytest.raises(ValueError, match="Unknown agent"):
        h.run_case(CASE, agents="credit_magic")


# ─── Pipeline diagnostics (production logging) ───────────────────────────────

def test_pipeline_log_distinguishes_execution_modes():
    from src.agents.pipeline import SuperAgent
    from src.data.company_catalog import seed_company_store

    agent = SuperAgent(llm_provider=None)
    agent.execute_pipeline(copy.deepcopy(seed_company_store()[CASE]), stores={"extraction": {}, "etb": {}})
    log = {e["agent_name"]: e["diagnostics"] for e in agent.pipeline_log}
    assert log["financial_analysis"]["execution_mode"] == "deterministic"
    assert log["financial_analysis"]["llm_invoked"] is False and log["financial_analysis"]["output_present"] is True
    assert log["narrative"]["execution_mode"] == "template" and log["narrative"]["fact_pack_ms"] >= 0
    assert log["data_ingestion"]["execution_mode"] in ("io", "io+cached")
    assert "web_crawl_news" in log["data_ingestion"]["empty_output_keys"]
    assert all(e["duration_ms"] >= 0 for e in agent.pipeline_log)


def test_diagnostics_api():
    from fastapi.testclient import TestClient

    from src.api.app import create_app
    from src.application.container import build_container

    http = TestClient(create_app(build_container()))
    agents = http.get("/api/diagnostics/agents").json()["agents"]
    assert [a["name"] for a in agents][0] == "data_ingestion" and len(agents) == 7
    body = http.post("/api/diagnostics/agents/run",
                     json={"agent": "policy", "cases": [CASE], "stop_after": "policy"}).json()
    rep = body["results"][0]["reports"][0]
    assert rep["agent"] == "policy" and "raw_output" not in rep
    assert body["comparison"][0]["case"] == CASE
