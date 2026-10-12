"""Deterministic projections quoted by CAM section 16."""

import pytest

from src.engines.projection_engine import build_projections

SUMMARY = {"periods": {
    "FY2024": {"revenue_cr": 1100, "ebitda_margin_pct": 20, "pat_margin_pct": 10, "total_debt_cr": 300},
    "FY2025": {"revenue_cr": 1210, "ebitda_margin_pct": 20, "pat_margin_pct": 10, "total_debt_cr": 400},
}}
FACILITY = {"amount_requested_cr": 100, "tenor_months": 60}
PRICING = {"interest_rate": "MCLR + 0.80% = 9.20% p.a."}


def test_cagr_projection_and_quoted_rate():
    result = build_projections(SUMMARY, FACILITY, PRICING, {}, min_dscr=1.20)
    assert result["available"]
    assert result["assumptions"]["interest_rate_pct"] == 9.2
    assert result["assumptions"]["applied_revenue_cagr_pct"] == pytest.approx(10.0)
    years = result["projected_years"]
    assert [y["year"] for y in years] == ["FY2026", "FY2027", "FY2028"]
    assert years[0]["revenue_cr"] == pytest.approx(1331.0)
    assert years[0]["ebitda_cr"] == pytest.approx(266.2)
    assert [s["scenario"] for s in result["stress_tests"]][0] == "Base case"


def test_guidance_overrides_cagr():
    kpis = {"development_projections": {"projected_revenue_fy26_cr": 1500}}
    years = build_projections(SUMMARY, FACILITY, PRICING, kpis, min_dscr=1.20)["projected_years"]
    assert years[0]["revenue_cr"] == 1500 and years[0]["basis"] == "Company guidance"
    assert years[1]["basis"] == "Guidance + CAGR"


def test_cagr_is_capped():
    hot = {"periods": {"FY2024": {"revenue_cr": 100}, "FY2025": {"revenue_cr": 300}}}
    assert build_projections(hot, FACILITY, {}, {}, 1.2)["assumptions"]["applied_revenue_cagr_pct"] == 25.0


def test_needs_two_periods():
    single = {"periods": {"FY2025": {"revenue_cr": 100}}}
    assert build_projections(single, FACILITY, {}, {}, 1.2)["available"] is False


def test_assessment_uses_policy_threshold():
    result = build_projections(SUMMARY, FACILITY, PRICING, {}, min_dscr=99)
    assert all(y["assessment"] != "Adequate" for y in result["projected_years"])
