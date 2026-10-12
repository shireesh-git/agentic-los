"""Stress testing: base reconciles with the ratio engine, scenarios deteriorate, breaches, demo borrower, API."""

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.engines.ratio_engine import compute_all_ratios
from src.engines.stress_test_engine import run_stress_tests

FIXTURE = Path(__file__).parent / "fixtures" / "abce001_expected_stress.json"
ENTITY = "ABCE001"


@pytest.fixture(scope="module")
def demo():
    from src.data.company_catalog import seed_company_store
    from src.engines.cam_fact_builder import build_cam_fact_pack
    company = seed_company_store()[ENTITY]
    fs = company["financials"][sorted(company["financials"])[-1]]
    return company, fs, build_cam_fact_pack(copy.deepcopy(company))


def stress(fs, fp, settings=None):
    return run_stress_tests(fs, fp, ENTITY, created_at="2026-10-07T00:00:00", settings=settings)


def by_name(result):
    return {s["scenario"]: s for s in result["scenarios"]}


def test_demo_borrower_deteriorates_as_designed(demo):
    _, fs, fp = demo
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
    result = stress(fs, fp)
    assert result["period"] == expected["period"] and result["base_reconciles"]
    scenarios = by_name(result)
    for name, exp in expected["scenarios"].items():
        s = scenarios[name]
        assert s["severity"] == exp["severity"], name
        for key, value in exp["metrics"].items():
            assert s["stressed_metrics"][key] == value, (name, key)
        assert [b["metric"] for b in s["policy_breaches"]] == exp["breaches"], name
        assert s["new_breaches"] == exp["new_breaches"], name


def test_base_case_is_the_ratio_engine_unchanged(demo):
    _, fs, fp = demo
    base = by_name(stress(fs, fp))["base"]["stressed_metrics"]
    ratios = {r.ratio_name: r.value for r in compute_all_ratios(fs)}
    for key in ("dscr", "interest_coverage_ratio", "debt_to_ebitda", "current_ratio", "debtor_days", "inventory_days"):
        assert base[key] == ratios[key] == fp["ratio_analysis"][fs.period][key]["value"]


def test_stress_does_not_modify_the_statement(demo):
    _, fs, fp = demo
    before = copy.deepcopy(fs.line_items)
    stress(fs, fp)
    assert fs.line_items == before


def test_scenarios_get_progressively_worse(demo):
    _, fs, fp = demo
    s = by_name(stress(fs, fp))
    for key in ("ebitda_cr", "operating_cash_flow_cr", "dscr", "interest_coverage_ratio"):
        assert s["base"]["stressed_metrics"][key] > s["downside"]["stressed_metrics"][key] > s["severe"]["stressed_metrics"][key]
    for key in ("debt_to_ebitda", "total_debt_cr", "finance_cost_cr", "debtor_days"):
        assert s["base"]["stressed_metrics"][key] < s["downside"]["stressed_metrics"][key] < s["severe"]["stressed_metrics"][key]


def test_working_capital_stress_is_funded_by_debt(demo):
    _, fs, fp = demo
    severe = by_name(stress(fs, fp))["severe"]
    m = severe["stressed_metrics"]
    assert m["total_debt_cr"] == round(fs.get("total_debt") + m["additional_borrowing_cr"], 2)
    assert severe["working"]["stressed_interest_rate_pct"] == 9.5     # 8.0% + 150 bps
    assert any("extra working capital" in o for o in severe["key_observations"])


def test_assumptions_come_from_config(demo):
    _, fs, fp = demo
    mild = {"scenarios": {"downside": {"label": "Mild", "revenue_change_pct": -1, "margin_change_bps": 0,
                                       "debtor_days_change": 0, "inventory_days_change": 0, "rate_shock_bps": 0}}}
    s = by_name(stress(fs, fp, settings=mild))["downside"]
    assert s["label"] == "Mild" and s["assumptions"]["revenue_change_pct"] == -1
    assert s["stressed_metrics"]["revenue_cr"] == round(fs.get("revenue_operating") * 0.99, 2)


def test_a_healthy_borrower_without_breaches_is_low(demo):
    company, _, fp = demo
    fs = company["financials"]["FY2025"]
    fp = copy.deepcopy(fp)
    base = by_name(stress(fs, fp))["base"]
    assert base["policy_breaches"] == [] and base["severity"] == "LOW"


def test_unavailable_without_financials(demo):
    _, _, fp = demo
    assert stress(None, fp)["available"] is False


def test_no_recommendation_language(demo):
    _, fs, fp = demo
    text = json.dumps(stress(fs, fp)).lower()
    for word in ("recommend", "approve", "decline"):
        assert word not in text


# ─── API ─────────────────────────────────────────────────────────────────────

@pytest.fixture()
def client(demo):
    from src.api.app import create_app
    from src.application.container import build_container

    container = build_container()
    case = {"run_id": "stress-run-1", "entity_id": ENTITY, "company_name": "ABC Engineering & Infrastructure Ltd.",
            "recommendation": "decline", "risk_grade": "D", "requested_amount_cr": 250,
            "run_at": "2026-10-07T10:00:00", "fact_pack": demo[2]}
    container.state.cases[ENTITY] = case
    container.persistence.save_case_run(case)
    yield TestClient(create_app(container)), container
    container.state.cases.pop(ENTITY, None)
    container.persistence.delete_company(ENTITY)   # leave no partial case for later tests


def test_api_backfills_and_stores_the_result(client):
    http, container = client
    body = http.get(f"/api/cases/{ENTITY}/stress-test").json()
    result = body["stress_test"]
    assert body["is_latest_run"] and result["available"] and result["base_reconciles"]
    assert [s["severity"] for s in result["scenarios"]] == ["HIGH", "HIGH", "CRITICAL"]
    assert container.persistence.get_case_run("stress-run-1")["stress_test"]["period"] == "FY2026"
    assert http.get("/api/cases/NOCASE999/stress-test").status_code == 404


def test_case_record_carries_stress_results(demo):
    from src.application.case_service import build_case_result

    company, _, fp = demo
    case = build_case_result(ENTITY, company, {"results": {"narrative": {"fact_pack": fp}}}, [])
    assert case["stress_test"]["available"] and len(case["stress_test"]["scenarios"]) == 3
