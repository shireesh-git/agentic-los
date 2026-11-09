"""Expected credit loss at origination (roadmap D6)."""

import pytest

from src.engines.ecl_engine import DEFAULTS, ecl


def _ecl(**kw):
    base = dict(grade="A", amount_cr=500.0, tenor_months=12, product="working_capital", fsv_cr=0.0,
                bureau_status="Standard", max_dpd=0, cfg=DEFAULTS)
    return ecl(**{**base, **kw})


def test_stage_1_is_twelve_month_pd_times_lgd_times_ead():
    r = _ecl(fsv_cr=125.0)
    assert r["stage"] == 1 and r["pd"] == 0.0025 and r["ead_cr"] == 375.0          # 500 × CCF 0.75
    assert r["lgd"] == pytest.approx(0.65 * (1 - 125 / 375), abs=1e-4)
    assert r["ecl_cr"] == pytest.approx(0.0025 * r["lgd"] * 375, abs=0.01) and r["demo"]


@pytest.mark.parametrize("status, dpd, stage", [("SMA-1", 0, 2), ("SMA-2", 0, 2), ("Standard", 45, 2),
                                                ("Substandard", 0, 3), ("Standard", 120, 3)])
def test_stage_follows_bureau_status_and_days_past_due(status, dpd, stage):
    assert _ecl(bureau_status=status, max_dpd=dpd)["stage"] == stage


def test_stage_2_uses_lifetime_pd_and_stage_3_is_impaired():
    two = _ecl(grade="B", tenor_months=36, bureau_status="SMA-1")
    assert two["pd"] == pytest.approx(1 - (1 - 0.0075) ** 3, abs=1e-6) and two["pd_horizon"] == "lifetime"
    assert _ecl(bureau_status="Substandard")["pd"] == 1.0


def test_full_security_floors_lgd_and_term_loans_have_no_conversion_discount():
    r = _ecl(product="term_loan", fsv_cr=900.0)
    assert r["ead_cr"] == 500.0 and r["lgd"] == 0.25


def test_no_grade_means_not_available():
    assert _ecl(grade=None)["available"] is False
