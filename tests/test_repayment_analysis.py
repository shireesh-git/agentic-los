"""Cash Flow & Repayment Analysis: the demo borrower, grading, sources, API, AI explanation guard."""

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.engines.observation_engine import detect_observations
from src.engines.repayment_analysis import analyse_repayment

FIXTURE = Path(__file__).parent / "fixtures" / "abce001_expected_repayment.json"
ENTITY = "ABCE001"


@pytest.fixture(scope="module")
def demo():
    from src.data.company_catalog import seed_company_store
    from src.engines.cam_fact_builder import build_cam_fact_pack
    fp = build_cam_fact_pack(copy.deepcopy(seed_company_store()[ENTITY]))
    return fp, detect_observations(fp, ENTITY, created_at="2026-10-07T00:00:00")


def assess(fp, obs=None):
    return analyse_repayment(fp, ENTITY, obs, created_at="2026-10-07T00:00:00")


# ─── Demo borrower ───────────────────────────────────────────────────────────

def test_demo_borrower_repayment_story(demo):
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
    r = assess(*demo)
    assert r["repayment_capacity"] == expected["repayment_capacity"]
    assert r["capacity_by_period"] == expected["capacity_by_period"]
    assert r["repayment_risk"] == expected["repayment_risk"]
    for key, value in expected["primary"].items():
        assert r["primary_repayment_source"][key] == value
    sec = r["secondary_repayment_source"]
    assert (sec["source"], sec["adequacy"]) == (expected["secondary"]["source"], expected["secondary"]["adequacy"])
    assert sec["metrics"]["fsv_cover"] == expected["secondary"]["fsv_cover"]
    assert sec["metrics"]["hard_security_cover"] == expected["secondary"]["hard_security_cover"]
    latest = {m["metric"]: m["latest"] for m in r["key_metrics"]}
    assert {k: latest[k] for k in expected["latest_metrics"]} == expected["latest_metrics"]
    assert [c["concern"] for c in r["concerns"]] == expected["concerns"]
    assert [p["factor"] for p in r["positive_factors"]] == expected["positive_factors"]


def test_figures_come_from_the_existing_engines(demo):
    fp, obs = demo
    r = assess(fp, obs)
    by = {m["metric"]: m for m in r["key_metrics"]}
    for period in r["periods"]:
        assert by["dscr"]["by_period"][period] == fp["ratio_analysis"][period]["dscr"]["value"]
        assert by["debt_to_ebitda"]["by_period"][period] == fp["ratio_analysis"][period]["debt_to_ebitda"]["value"]
        assert by["ebitda_cr"]["by_period"][period] == fp["financial_summary"]["periods"][period]["ebitda_cr"]
        assert by["finance_cost_cr"]["by_period"][period] == fp["cash_flow_repayment"]["periods"][period]["finance_cost_cr"]
        assert by["free_cash_flow_cr"]["by_period"][period] == fp["cash_flow_repayment"]["periods"][period]["free_cash_flow_cr"]
    assert by["dscr"]["source"] == "ratio_engine" and by["dscr"]["policy"] == 1.2


def test_concerns_link_to_observations(demo):
    r = assess(*demo)
    links = {c["concern"]: c["linked_observation_id"] for c in r["concerns"]}
    assert links["DSCR deterioration"] == "OBS-ABCE001-DEBT_SERVICING_PRESSURE"
    assert links["Operating cash flow declining despite EBITDA growth"] == "OBS-ABCE001-EARNINGS_CASH_CONVERSION"


def test_summary_tells_the_deterioration(demo):
    s = assess(*demo)["summary"]
    assert s.startswith("Repayment capacity moved from STRONG in FY2025 to STRESSED in FY2026")
    assert "₹45.00 Cr" in s and "₹88.00 Cr" in s and "0.51x" in s and "1.19x" in s


def test_deterministic(demo):
    assert assess(*copy.deepcopy(demo)) == assess(*copy.deepcopy(demo))


# ─── Grading ─────────────────────────────────────────────────────────────────

def test_previous_year_alone_is_strong(demo):
    fp, _ = copy.deepcopy(demo)
    for section in ("ratio_analysis",):
        fp[section].pop("FY2026")
    fp["financial_summary"]["periods"].pop("FY2026")
    fp["cash_flow_repayment"]["periods"].pop("FY2026")
    r = assess(fp, [])
    assert r["period"] == "FY2025" and r["repayment_capacity"] == "STRONG"
    assert r["concerns"] == [] or all(c["severity"] != "HIGH" for c in r["concerns"])


def test_moderate_when_only_a_few_measures_are_weak(demo):
    fp, _ = copy.deepcopy(demo)
    fp["ratio_analysis"]["FY2026"] = copy.deepcopy(fp["ratio_analysis"]["FY2025"])
    fp["financial_summary"]["periods"]["FY2026"] = copy.deepcopy(fp["financial_summary"]["periods"]["FY2025"])
    fp["cash_flow_repayment"]["periods"]["FY2026"] = copy.deepcopy(fp["cash_flow_repayment"]["periods"]["FY2025"])
    fp["ratio_analysis"]["FY2026"]["dscr"]["value"] = 1.1        # weak, nothing critical
    assert assess(fp, [])["repayment_capacity"] == "MODERATE"


def test_bands_come_from_config(demo):
    fp, obs = demo
    lenient = {"bands": {"ocf_to_ebitda_pct": [70, 50, 10], "ocf_to_interest": [3.0, 1.5, 0.5]}}
    r = analyse_repayment(fp, ENTITY, obs, settings=lenient)
    by = {m["metric"]: m["grade"] for m in r["key_metrics"]}
    assert by["ocf_to_ebitda_pct"] == "weak" and by["ocf_to_interest"] == "weak"


def test_no_security_is_an_inadequate_fallback_and_raises_risk(demo):
    fp, obs = copy.deepcopy(demo)
    fp["collateral_analysis"] = {}
    r = assess(fp, obs)
    assert r["secondary_repayment_source"]["adequacy"] == "INADEQUATE"
    assert r["repayment_risk"] == "VERY_HIGH"


def test_empty_fact_pack():
    assert analyse_repayment({}, ENTITY, [])["available"] is False


# ─── API ─────────────────────────────────────────────────────────────────────

@pytest.fixture()
def client(demo):
    from src.api.app import create_app
    from src.application.container import build_container

    container = build_container()
    case = {"run_id": "rpy-run-1", "entity_id": ENTITY, "company_name": "ABC Engineering & Infrastructure Ltd.",
            "recommendation": "decline", "risk_grade": "D", "requested_amount_cr": 250,
            "run_at": "2026-10-07T10:00:00", "fact_pack": demo[0]}
    container.state.cases[ENTITY] = case
    container.persistence.save_case_run(case)
    yield TestClient(create_app(container)), container
    container.state.cases.pop(ENTITY, None)
    container.persistence.delete_company(ENTITY)   # leave no partial case for later tests


class FakeLLM:
    name = "fake"
    model = "fake-model"

    def __init__(self, narrative):
        self.narrative = narrative

    def generate(self, prompt, system_prompt="", temperature=0.1, max_tokens=4000):
        assert "do NOT change or second-guess the capacity or risk grades" in system_prompt
        return json.dumps({"narrative": self.narrative, "primary_source": "Operating cash flow is the primary source.",
                           "secondary_source": "Security is the fallback."})


def test_api_returns_and_stores_the_assessment(client):
    http, container = client
    body = http.get(f"/api/cases/{ENTITY}/repayment").json()
    assert body["is_latest_run"] and body["assessment"]["repayment_capacity"] == "STRESSED"
    assert container.persistence.get_case_run("rpy-run-1")["repayment_analysis"]["repayment_risk"] == "HIGH"
    assert http.post(f"/api/cases/{ENTITY}/repayment/explain").status_code == 409   # mock provider in tests


def test_ai_explanation_keeps_grades_and_rejects_invented_figures(client):
    http, container = client
    container.repayment.llm_factory = lambda: FakeLLM(
        "Operating cash flow fell to Rs 45.00 Cr against interest of Rs 88.00 Cr, while DSCR fell to 1.19x.")
    body = http.post(f"/api/cases/{ENTITY}/repayment/explain").json()
    assert body["status"] == "ok"
    assert body["assessment"]["repayment_capacity"] == "STRESSED"
    assert body["assessment"]["ai_explanation"]["model"] == "fake-model"
    # Stored, and kept while the assessment is unchanged.
    assert http.get(f"/api/cases/{ENTITY}/repayment").json()["assessment"]["ai_explanation"] is not None

    container.repayment.llm_factory = lambda: FakeLLM("DSCR is likely to fall to 0.87x next year.")
    body = http.post(f"/api/cases/{ENTITY}/repayment/explain").json()
    assert body["status"] == "rejected" and "0.87" in body["reason"]
