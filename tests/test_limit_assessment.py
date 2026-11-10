"""Limit assessment (roadmap D8): turnover method, MPBF method II, operating cycle, non-fund, break-even."""

import pytest

from src.engines import limit_assessment as la

FY = {"FY2024": {"revenue_operating": 1000.0},
      "FY2025": {"revenue_operating": 1100.0, "current_assets": 400.0, "current_liabilities": 300.0,
                 "short_term_debt": 100.0, "inventory": 150.0, "trade_receivables": 110.0, "trade_payables": 60.0,
                 "raw_material_cost": 600.0, "other_expenses": 100.0, "employee_cost": 100.0,
                 "finance_cost": 20.0, "depreciation": 30.0}}


def test_small_limit_uses_the_turnover_method():
    r = la.assess(periods=FY, product="working_capital", requested_cr=4, projected_revenue_cr=20)
    assert r["method"] == "turnover" and r["assessed_cr"] == pytest.approx(4.0)       # 20% of ₹20 Cr turnover
    assert r["available_cr"] == 0 and r["within"] is False                           # ₹100 Cr already with other banks


def test_mpbf_method_two_on_projected_figures():
    # growth 10% (FY2025 over FY2024): CA 440, OCL (300 − 100) × 1.1 = 220, gap 220,
    # margin = max(25% of 440 = 110, NWC (400 − 300) × 1.1 = 110) = 110 → MPBF 110; less 100 with other banks → 10
    r = la.assess(periods=FY, product="working_capital", sector="manufacturing", requested_cr=50)
    assert r["method"] == "mpbf" and r["growth_pct"] == pytest.approx(10.0)
    assert r["assessed_cr"] == pytest.approx(110.0) and r["available_cr"] == pytest.approx(10.0)
    assert r["within"] is False and r["gap_cr"] == pytest.approx(40.0)
    assert {a["method"] for a in r["alternatives"]} == {"turnover", "operating_cycle"}
    assert any("other banks" in a for a in r["assumptions"])


def test_an_existing_borrowers_own_limit_is_not_counted_as_other_banks():
    r = la.assess(periods=FY, product="working_capital", requested_cr=50, case_type="ETB", existing_limit_cr=100)
    assert r["other_banks_cr"] == 0 and r["available_cr"] == pytest.approx(110.0) and r["within"] is True


def test_service_sectors_use_the_operating_cycle():
    # cycle = (150 + 110 − 60) / 1100 × 365 = 66.4 days; need = 1210 × 66.4 / 365 = 220; banks 75% = 165
    r = la.assess(periods=FY, product="working_capital", sector="it_services", requested_cr=50)
    assert r["method"] == "operating_cycle" and r["assessed_cr"] == pytest.approx(165.0, abs=0.1)


def test_guarantees_and_letters_of_credit_are_not_guessed():
    r = la.assess(periods=FY, product="working_capital", purpose="Non-fund based working capital (BG/LC)", requested_cr=50)
    assert r["kind"] == "non_fund" and r["available_cr"] is None and "pipeline" in r["basis"]


def test_term_loans_get_break_even_and_margin_of_safety():
    # variable = 600 + 50 = 650 → contribution 40.9%; fixed = 100 + 50 + 20 + 30 = 200 → break-even 488.9
    r = la.assess(periods=FY, product="term_loan", requested_cr=300)
    assert r["kind"] == "term" and r["break_even_cr"] == pytest.approx(488.89, abs=0.01)
    assert r["margin_of_safety_pct"] == pytest.approx(55.6, abs=0.1) and "IRR" in r["irr_note"]


def test_the_flow_shows_the_assessment_and_challenges_a_request_above_it():
    from src.flow import risk as rk
    engine = {"fact_pack": {"limit_assessment": la.assess(periods=FY, product="working_capital", requested_cr=50)},
              "recommendation": "approve", "challenges": []}
    assert rk.assess(engine)["limit"]["available_cr"] == pytest.approx(10.0)
    ch = rk.challenges(engine)
    assert ch[0]["rule_id"] == "LIMIT_ABOVE_ASSESSED" and ch[0]["severity"] == "HIGH"
    act = next(a for a in ch[0]["actions"] if a["kind"] == "reduce_amount")
    assert act["value"] == pytest.approx(10.0) and act["field"] == "recommended_cr"
