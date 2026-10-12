"""Credit Risk Observation engine: detectors, configuration, the demo borrower, AI wording guard."""

import copy
import json
from pathlib import Path

import pytest

from src.engines import observation_engine
from src.engines.observation_engine import detect_observations, observation_config, summarize

FIXTURE = Path(__file__).parent / "fixtures" / "abce001_expected_observations.json"


# ─── Minimal fact packs ──────────────────────────────────────────────────────

def fact_pack(prev=None, curr=None, ratios_prev=None, ratios_curr=None, benchmarks=None,
              exceptions=None, tier1=None):
    """Two periods (FY2024 -> FY2025) of the fact-pack sections the engine reads."""
    base = {"revenue_cr": 1000.0, "ebitda_cr": 150.0, "ebitda_margin_pct": 15.0, "total_debt_cr": 400.0,
            "operating_cash_flow_cr": 120.0, "trade_receivables_cr": 200.0, "inventory_cr": 80.0,
            "current_assets_cr": 500.0, "current_liabilities_cr": 350.0}
    base_ratios = {"debt_to_ebitda": 2.67, "dscr": 1.8, "interest_coverage_ratio": 4.0, "debtor_days": 73.0,
                   "inventory_days": 29.2, "current_ratio": 1.43, "altman_z_score": 3.4, "debt_to_equity": 0.8,
                   "tol_tnw": 1.2, "return_on_equity": 0.15}
    return {
        "financial_summary": {"periods": {"FY2024": {**base, **(prev or {})}, "FY2025": {**base, **(curr or {})}}},
        "ratio_analysis": {
            "FY2024": {k: {"value": v} for k, v in {**base_ratios, **(ratios_prev or {})}.items()},
            "FY2025": {k: {"value": v} for k, v in {**base_ratios, **(ratios_curr or {})}.items()},
        },
        "benchmark_summary": {"sector": "manufacturing", "period": "FY2025", "benchmarks": benchmarks or []},
        "validation_exceptions": exceptions or [],
        "policy_decisions": {"tier1_hard_rules": tier1 or []},
        "policy_thresholds": {"min_dscr": 1.20, "max_debt_to_equity": 2.5, "min_current_ratio": 1.25,
                              "min_interest_coverage": 2.0, "max_debt_to_ebitda": 4.0, "min_ebitda_margin_pct": 10,
                              "max_tol_tnw": 4.0, "min_roe_pct": 12, "max_debtor_days": 90},
    }


def found(fp, rule_id):
    """The observation for ``rule_id`` (or None)."""
    obs = detect_observations(fp, "T001", created_at="2026-01-01T00:00:00")
    return next((o for o in obs if o["trigger"]["rule_id"] == rule_id), None)


def severity(fp, rule_id):
    o = found(fp, rule_id)
    return o["severity"] if o else None


def test_healthy_borrower_has_no_observations():
    assert detect_observations(fact_pack(), "T001") == []


def test_empty_fact_pack_is_safe():
    assert detect_observations({}, "T001") == []
    assert detect_observations({"financial_summary": {"periods": {"FY2025": {}}}}, "T001") == []


# ─── One case per detector: triggers, severity, and a near miss ──────────────

@pytest.mark.parametrize("prev, curr, expected", [
    ({"trade_receivables_cr": 200}, {"revenue_cr": 1100, "trade_receivables_cr": 300}, "HIGH"),    # +50% vs +10%
    ({"trade_receivables_cr": 200}, {"revenue_cr": 1100, "trade_receivables_cr": 262}, "MEDIUM"),  # +31% vs +10%
    ({"trade_receivables_cr": 200}, {"revenue_cr": 1100, "trade_receivables_cr": 230}, None),      # +15% vs +10%
])
def test_working_capital_deterioration(prev, curr, expected):
    assert severity(fact_pack(prev, curr), "WC_DETERIORATION") == expected


@pytest.mark.parametrize("curr, expected", [
    ({"ebitda_cr": 160, "operating_cash_flow_cr": 60}, "MEDIUM"),   # EBITDA up, OCF -50%, 37.5% conversion
    ({"ebitda_cr": 160, "operating_cash_flow_cr": 30}, "HIGH"),     # 18.8% conversion
    ({"ebitda_cr": 160, "operating_cash_flow_cr": -10}, "HIGH"),    # negative OCF
    ({"ebitda_cr": 160, "operating_cash_flow_cr": 115}, None),      # small dip, 72% conversion
])
def test_earnings_cash_conversion(curr, expected):
    assert severity(fact_pack(curr=curr), "EARNINGS_CASH_CONVERSION") == expected


def test_leverage_increase_above_policy_is_high():
    fp = fact_pack(curr={"total_debt_cr": 650, "ebitda_cr": 155}, ratios_curr={"debt_to_ebitda": 4.19})
    o = found(fp, "LEVERAGE_INCREASE")
    assert o["severity"] == "HIGH"
    assert o["trigger"]["observed"]["debt_to_ebitda_change"] == 1.52


def test_leverage_increase_within_policy_is_medium_and_stable_debt_is_quiet():
    assert severity(fact_pack(curr={"total_debt_cr": 480}, ratios_curr={"debt_to_ebitda": 3.2}),
                    "LEVERAGE_INCREASE") == "MEDIUM"
    assert severity(fact_pack(curr={"total_debt_cr": 420}, ratios_curr={"debt_to_ebitda": 2.8}),
                    "LEVERAGE_INCREASE") is None


@pytest.mark.parametrize("ratios_curr, expected", [
    ({"dscr": 1.10}, "HIGH"),                                     # below 1.20
    ({"dscr": 0.90}, "CRITICAL"),                                 # cash does not cover debt service
    ({"interest_coverage_ratio": 1.8}, "HIGH"),                   # ICR below 2.0
    ({"dscr": 1.30}, "MEDIUM"),                                   # within 10% of 1.20 and falling
    ({"dscr": 1.70}, None),
])
def test_debt_servicing_pressure(ratios_curr, expected):
    assert severity(fact_pack(ratios_curr=ratios_curr), "DEBT_SERVICING_PRESSURE") == expected


@pytest.mark.parametrize("prev_days, curr_days, expected", [
    (73, 95, "HIGH"),      # +22 days and above 90
    (60, 80, "MEDIUM"),    # +20 days
    (85, 95, "LOW"),       # only above the policy maximum
    (73, 78, None),
    (0, 69, None),         # prior year not reported: no comparison
])
def test_receivable_collection(prev_days, curr_days, expected):
    fp = fact_pack(ratios_prev={"debtor_days": prev_days}, ratios_curr={"debtor_days": curr_days})
    assert severity(fp, "RECEIVABLE_COLLECTION") == expected


@pytest.mark.parametrize("prev_days, curr_days, expected", [
    (20, 40, "MEDIUM"),    # +20 days, +100%
    (20, 55, "HIGH"),      # +35 days
    (80, 96, None),        # +16 days but only +20%
    (70, 80, None),        # +10 days
])
def test_inventory_buildup(prev_days, curr_days, expected):
    fp = fact_pack(ratios_prev={"inventory_days": prev_days}, ratios_curr={"inventory_days": curr_days})
    assert severity(fp, "INVENTORY_BUILDUP") == expected


@pytest.mark.parametrize("prev_m, curr_m, expected", [
    (15.0, 12.5, "MEDIUM"),   # 250 bps
    (15.0, 10.5, "HIGH"),     # 450 bps
    (12.0, 9.5, "HIGH"),      # 250 bps and below the 10% policy floor
    (15.0, 14.0, None),       # 100 bps
])
def test_margin_compression(prev_m, curr_m, expected):
    fp = fact_pack({"ebitda_margin_pct": prev_m}, {"ebitda_margin_pct": curr_m})
    assert severity(fp, "MARGIN_COMPRESSION") == expected


def test_data_reliability_maps_exception_severity_and_ignores_credit_alerts():
    gst = {"code": "XSRC_GST_REVENUE_MISMATCH", "severity": "high", "description": "GST gap",
           "metric": "revenue_operating", "expected": "900", "observed": "1000"}
    bs = {"code": "STRUCT_BS_MISMATCH", "severity": "critical", "description": "BS does not balance"}
    dpd = {"code": "XSRC_BUREAU_DPD_ALERT", "severity": "critical", "description": "SMA-2"}
    margin = {"code": "ANAL_MARGIN_DECLINE", "severity": "medium", "description": "3-year decline"}
    assert severity(fact_pack(exceptions=[gst]), "DATA_RELIABILITY") == "HIGH"
    assert severity(fact_pack(exceptions=[gst, bs]), "DATA_RELIABILITY") == "CRITICAL"
    assert severity(fact_pack(exceptions=[dpd, margin]), "DATA_RELIABILITY") is None
    o = found(fact_pack(exceptions=[gst]), "DATA_RELIABILITY")
    assert [e["ref"] for e in o["evidence_references"]] == ["XSRC_GST_REVENUE_MISMATCH"]


def _bm(metric, sev):
    return {"metric": metric, "borrower": 1.0, "peer_p25": 1.1, "peer_median": 1.3, "peer_p75": 1.6,
            "status": "worse_than_peer", "severity": sev}


@pytest.mark.parametrize("rows, expected", [
    ([_bm("dscr", "high"), _bm("current_ratio", "high")], "HIGH"),
    ([_bm("dscr", "high")], "MEDIUM"),
    ([_bm("dscr", "medium"), _bm("current_ratio", "medium"), _bm("ebitda_margin", "medium")], "MEDIUM"),
    ([_bm("dscr", "medium"), _bm("current_ratio", "medium")], None),
])
def test_sector_underperformance(rows, expected):
    assert severity(fact_pack(benchmarks=rows), "SECTOR_UNDERPERFORMANCE") == expected


def test_policy_deviation():
    fail = [{"rule": "HR_BUREAU_STATUS", "result": "fail", "details": "SMA-2"}]
    assert severity(fact_pack(tier1=fail), "POLICY_DEVIATION") == "CRITICAL"
    one = found(fact_pack(ratios_curr={"debt_to_equity": 2.8}), "POLICY_DEVIATION")
    assert one["severity"] == "MEDIUM"
    assert [b["threshold_key"] for b in one["trigger"]["observed"]["breaches"]] == ["max_debt_to_equity"]
    three = fact_pack(ratios_curr={"debt_to_equity": 2.8, "tol_tnw": 4.5, "return_on_equity": 0.08})
    assert severity(three, "POLICY_DEVIATION") == "HIGH"
    assert severity(fact_pack(curr={"ebitda_margin_pct": 9.0}, prev={"ebitda_margin_pct": 9.5}),
                    "POLICY_DEVIATION") == "MEDIUM"


@pytest.mark.parametrize("prev_cr, curr_cr, expected", [
    (1.43, 0.95, "HIGH"),
    (1.43, 1.20, "MEDIUM"),
    (2.00, 1.75, "LOW"),
    (1.50, 1.45, None),
])
def test_liquidity_stress(prev_cr, curr_cr, expected):
    fp = fact_pack(ratios_prev={"current_ratio": prev_cr}, ratios_curr={"current_ratio": curr_cr})
    assert severity(fp, "LIQUIDITY_STRESS") == expected


def test_liquidity_wording_follows_the_direction_of_the_move():
    fp = fact_pack(ratios_prev={"current_ratio": 0.90}, ratios_curr={"current_ratio": 0.91})
    o = found(fp, "LIQUIDITY_STRESS")
    assert o["severity"] == "HIGH" and o["summary"].startswith("Current ratio moved from 0.90x to 0.91x")


@pytest.mark.parametrize("prev_z, curr_z, expected", [
    (2.5, 1.5, "HIGH"),
    (3.2, 2.8, "LOW"),
    (2.9, 2.5, "LOW"),   # grey zone, fell by 0.4
    (3.5, 3.4, None),
    (2.6, 2.5, None),    # grey zone, small move
])
def test_financial_distress(prev_z, curr_z, expected):
    fp = fact_pack(ratios_prev={"altman_z_score": prev_z}, ratios_curr={"altman_z_score": curr_z})
    assert severity(fp, "FINANCIAL_DISTRESS") == expected


# ─── Structure, configuration, robustness ────────────────────────────────────

def test_observation_shape_and_ordering():
    fp = fact_pack(curr={"revenue_cr": 1100, "trade_receivables_cr": 300, "ebitda_margin_pct": 12.5},
                   ratios_curr={"dscr": 0.9})
    obs = detect_observations(fp, "T001", created_at="2026-01-01T00:00:00")
    assert [o["severity"] for o in obs] == sorted((o["severity"] for o in obs),
                                                  key=["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"].index)
    required = {"observation_id", "case_id", "category", "title", "severity", "status", "summary",
                "detailed_explanation", "metrics", "period_comparison", "trigger", "evidence_references",
                "recommended_investigation", "source_type", "generated_by", "created_at"}
    for o in obs:
        assert required <= set(o)
        assert o["status"] == "NEW"
        assert o["case_id"] == "T001" and o["observation_id"].startswith("OBS-T001-")
        assert o["generated_by"] == observation_engine.GENERATED_BY
        assert o["ai_explanation"] is None


def test_deterministic():
    fp = fact_pack(curr={"revenue_cr": 1100, "trade_receivables_cr": 300}, ratios_curr={"dscr": 1.1})
    first = detect_observations(copy.deepcopy(fp), "T001", created_at="2026-01-01T00:00:00")
    second = detect_observations(copy.deepcopy(fp), "T001", created_at="2026-01-01T00:00:00")
    assert first == second


def test_thresholds_come_from_config():
    fp = fact_pack(curr={"revenue_cr": 1100, "trade_receivables_cr": 262})   # gap ~21 pp
    settings = copy.deepcopy(observation_config())
    assert settings["working_capital_deterioration"]["min_growth_gap_pp"] == 20
    assert any(o["trigger"]["rule_id"] == "WC_DETERIORATION" for o in detect_observations(fp, "T", settings=settings))
    settings["working_capital_deterioration"]["min_growth_gap_pp"] = 25
    assert not any(o["trigger"]["rule_id"] == "WC_DETERIORATION" for o in detect_observations(fp, "T", settings=settings))
    settings["working_capital_deterioration"] = {"enabled": False, "min_growth_gap_pp": 0}
    assert not any(o["trigger"]["rule_id"] == "WC_DETERIORATION" for o in detect_observations(fp, "T", settings=settings))


def test_a_failing_detector_does_not_block_the_others(monkeypatch):
    def boom(_facts):
        raise KeyError("broken input")
    detectors = [("margin_compression", boom)] + [d for d in observation_engine.DETECTORS if d[0] != "margin_compression"]
    monkeypatch.setattr(observation_engine, "DETECTORS", detectors)
    fp = fact_pack(curr={"ebitda_margin_pct": 10.5}, ratios_curr={"dscr": 1.1})
    rules = {o["trigger"]["rule_id"] for o in detect_observations(fp, "T001")}
    assert "DEBT_SERVICING_PRESSURE" in rules and "MARGIN_COMPRESSION" not in rules


def test_summary_counts():
    fp = fact_pack(curr={"revenue_cr": 1100, "trade_receivables_cr": 300}, ratios_curr={"dscr": 0.9})
    s = summarize(detect_observations(fp, "T001"))
    assert s["total"] == sum(s["by_severity"].values()) == sum(s["by_status"].values())
    assert s["by_severity"]["CRITICAL"] == 1 and s["by_status"]["NEW"] == s["total"]


# ─── Demo borrower: ABC Engineering & Infrastructure Ltd. ────────────────────

@pytest.fixture(scope="module")
def demo_fact_pack():
    from src.data.company_catalog import seed_company_store
    from src.engines.cam_fact_builder import build_cam_fact_pack
    company = copy.deepcopy(seed_company_store()["ABCE001"])
    return build_cam_fact_pack(company)


def test_demo_borrower_triggers_the_designed_observations(demo_fact_pack):
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
    obs = detect_observations(demo_fact_pack, "ABCE001", created_at="2026-10-07T00:00:00")
    by_rule = {o["trigger"]["rule_id"]: o for o in obs}

    assert set(by_rule) == {e["rule_id"] for e in expected["expected"]}
    for e in expected["expected"]:
        o = by_rule[e["rule_id"]]
        assert o["severity"] == e["severity"], e["rule_id"]
        for key, value in (e.get("observed") or {}).items():
            assert o["trigger"]["observed"][key] == value, (e["rule_id"], key)
        if "evidence_refs" in e:
            assert [r["ref"] for r in o["evidence_references"]] == e["evidence_refs"]
        if "breached_thresholds" in e:
            assert [b["threshold_key"] for b in o["trigger"]["observed"]["breaches"]] == e["breached_thresholds"]
        if o["period_comparison"]:
            assert (o["period_comparison"]["from_period"], o["period_comparison"]["to_period"]) == \
                   (expected["comparison"]["from_period"], expected["comparison"]["to_period"])


def test_demo_borrower_statements_are_internally_consistent():
    """Every identity holds in every year; the only deliberate conflict is the FY2026 GST turnover."""
    from src.data.demo_companies import ABC_ENGG_EXTERNAL_DATA, ABC_ENGG_FINANCIALS
    from src.engines.validation_engine import (
        validate_balance_sheet_balances, validate_ebitda_consistency, validate_pat_consistency,
    )

    prev = None
    for period, fs in sorted(ABC_ENGG_FINANCIALS.items()):
        li = fs.line_items
        assert not (validate_balance_sheet_balances(fs) + validate_pat_consistency(fs) + validate_ebitda_consistency(fs))
        assert li["total_assets"] == pytest.approx(li["total_equity"] + li["long_term_debt"] + li["current_liabilities"])
        assert li["total_debt"] == pytest.approx(li["long_term_debt"] + li["short_term_debt"])
        assert li["current_assets"] == pytest.approx(li["inventory"] + li["trade_receivables"]
                                                     + li["cash_equivalents"] + li["other_current_assets"])
        assert li["current_liabilities"] == pytest.approx(li["trade_payables"] + li["short_term_debt"]
                                                          + li["other_current_liabilities"])
        assert li["ebit"] == pytest.approx(li["ebitda"] - li["depreciation"])
        assert li["pbt"] == pytest.approx(li["ebit"] - li["finance_cost"])
        if prev:
            assert li["total_equity"] == pytest.approx(prev["total_equity"] + li["pat"] - li["dividend_paid"])
            assert li["cash_equivalents"] == pytest.approx(prev["cash_equivalents"] + li["operating_cash_flow"]
                                                           + li["investing_cash_flow"] + li["financing_cash_flow"])
        prev = li

    gst = ABC_ENGG_EXTERNAL_DATA["gst_data"]["payload"]
    assert abs(gst["aggregate_turnover_fy2025_cr"] / ABC_ENGG_FINANCIALS["FY2025"].get("revenue_operating") - 1) < 0.10
    assert abs(gst["aggregate_turnover_fy2026_cr"] / ABC_ENGG_FINANCIALS["FY2026"].get("revenue_operating") - 1) > 0.10


def test_case_record_carries_observations(demo_fact_pack):
    from src.application.case_service import build_case_result
    from src.data.company_catalog import seed_company_store

    company = seed_company_store()["ABCE001"]
    case = build_case_result("ABCE001", company, {"results": {"narrative": {"fact_pack": demo_fact_pack}}}, [])
    assert len(case["observations"]) == 12
    assert all(o["created_at"] == case["run_at"] for o in case["observations"])


# ─── AI wording: explanation only, figures guarded ───────────────────────────

class FakeLLM:
    name = "fake"
    model = "fake-model"

    def __init__(self, reply):
        self.reply = reply
        self.prompts = []

    def generate(self, prompt, system_prompt="", temperature=0.1, max_tokens=4000):
        self.prompts.append((system_prompt, prompt))
        return self.reply


def _obs():
    fp = fact_pack(prev={"trade_receivables_cr": 200}, curr={"revenue_cr": 1100, "trade_receivables_cr": 300})
    return found(fp, "WC_DETERIORATION")


def test_ai_explanation_uses_only_given_figures():
    from src.services.observation_narrator import explain_observation

    reply = json.dumps({"summary": "Receivables rose 50.0% against revenue growth of 10.0%.",
                        "detailed_explanation": "Receivables moved from Rs 200.00 Cr to Rs 300.00 Cr. "
                                                "This ties up working capital and needs explanation.",
                        "recommended_investigation": ["Obtain debtor ageing.", "Review top debtors."]})
    llm = FakeLLM(reply)
    result = explain_observation(_obs(), llm, "Test Co")
    assert result["summary"].startswith("Receivables rose")
    assert result["model"] == "fake-model"
    system_prompt, prompt = llm.prompts[0]
    assert "Do NOT decide whether the risk exists" in system_prompt
    assert '"growth_gap_pp": 40.0' in prompt   # the engine's facts are what the model sees


def test_ai_explanation_may_quote_a_decline_as_a_magnitude():
    """The engine stores a fall as -50.0; "fell 50.0%" is the same figure, not an invented one."""
    from src.services.observation_narrator import explain_observation

    fp = fact_pack(curr={"ebitda_cr": 160, "operating_cash_flow_cr": 60})
    obs = found(fp, "EARNINGS_CASH_CONVERSION")
    assert obs["trigger"]["observed"]["ocf_growth_pct"] == -50.0
    reply = json.dumps({"summary": "Operating cash flow fell 50.0% while EBITDA rose.",
                        "detailed_explanation": "Cash conversion is weak.", "recommended_investigation": []})
    assert explain_observation(obs, FakeLLM(reply), "Test Co")["summary"].startswith("Operating cash flow fell")


@pytest.mark.parametrize("reply, reason", [
    (json.dumps({"summary": "Receivables rose 64.3% this year.", "detailed_explanation": "Material.",
                 "recommended_investigation": []}), "figures not in the observation"),
    ("Receivables look stretched.", "JSON"),
    (json.dumps({"summary": "", "detailed_explanation": ""}), "missing"),
])
def test_ai_explanation_is_rejected_when_unusable(reply, reason):
    from src.services.observation_narrator import explain_observation, explain_observations

    with pytest.raises(ValueError, match=reason):
        explain_observation(_obs(), FakeLLM(reply), "Test Co")
    results = explain_observations([_obs()], FakeLLM(reply), "Test Co")
    assert list(results.values())[0]["status"] == "rejected"
