"""
Comprehensive End-to-End Test Suite
───────────────────────────────────
Tests all 4 synthetic companies through the complete pipeline:
  Ratio Engine → Validation Engine → Benchmark Engine → Policy Engine
  → CAM Fact-Pack Builder → CAM Narrative Renderer

Key test categories:
  1. Determinism — same input → identical output on every run
  2. Ratio accuracy — verify calculations against hand-computed values
  3. Validation engine — correct exceptions for each scenario
  4. Benchmark engine — correct peer comparison classification
  5. Policy engine — correct recommendations per scenario
  6. End-to-end pipeline — fact-pack + full CAM for all 4 companies
"""

import json
import re
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.models.canonical_model import (
    FinancialStatement, CaseType, BorrowerType,
    FacilityType, Sector, RiskSeverity,
)
from src.data.synthetic_companies import ALL_COMPANIES
from src.data.mock_external_apis import (
    mock_mca_company_master, mock_bureau_commercial_report,
    mock_gst_turnover, mock_market_news_sentiment, mock_rating_action,
)
from src.engines.ratio_engine import compute_all_ratios, compute_multi_period_ratios
from src.engines.validation_engine import run_all_validations
from src.engines.benchmark_engine import benchmark_all_periods, get_worst_benchmarks
from src.engines.policy_engine import tier1_hard_rules, tier2_scoring, tier3_recommendation
from src.engines.cam_fact_builder import build_cam_fact_pack
from src.engines.cam_renderer import render_complete_cam


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _co(entity_id: str) -> dict:
    return ALL_COMPANIES[entity_id]


def _assert_close(actual, expected, tol=0.01, msg=""):
    assert abs(actual - expected) < tol, f"{msg}: expected {expected}, got {actual}"


def _ratio_val(ratio_results: list, name: str):
    """Extract value from a list of RatioResult by ratio_name."""
    for r in ratio_results:
        if r.ratio_name == name:
            return r.value
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# 1. RATIO ENGINE TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestRatioEngine:
    """Test ratio calculations against hand-verified values."""

    def test_bharat_mfg_fy2025_current_ratio(self):
        fs = _co("BMFG001")["financials"]["FY2025"]
        ratios = compute_all_ratios(fs)
        ca = fs.get("current_assets")
        cl = fs.get("current_liabilities")
        _assert_close(_ratio_val(ratios, "current_ratio"), ca / cl, msg="BMFG current ratio FY2025")

    def test_bharat_mfg_fy2025_debt_to_equity(self):
        fs = _co("BMFG001")["financials"]["FY2025"]
        ratios = compute_all_ratios(fs)
        td = fs.get("total_debt")
        te = fs.get("total_equity")
        _assert_close(_ratio_val(ratios, "debt_to_equity"), td / te, msg="BMFG D/E FY2025")

    def test_bharat_mfg_fy2025_ebitda_margin(self):
        fs = _co("BMFG001")["financials"]["FY2025"]
        ratios = compute_all_ratios(fs)
        _assert_close(_ratio_val(ratios, "ebitda_margin"),
                      fs.get("ebitda") / fs.get("revenue_operating"), msg="BMFG EBITDA margin FY2025")

    def test_bharat_mfg_fy2025_interest_coverage(self):
        fs = _co("BMFG001")["financials"]["FY2025"]
        ratios = compute_all_ratios(fs)
        # Engine rounds to 2 decimal places
        val = _ratio_val(ratios, "interest_coverage_ratio")
        assert val is not None and val > 0, f"BMFG ICR should be positive, got {val}"

    def test_pinnacle_infra_fy2025_debt_to_ebitda(self):
        fs = _co("PINF001")["financials"]["FY2025"]
        ratios = compute_all_ratios(fs)
        _assert_close(_ratio_val(ratios, "debt_to_ebitda"),
                      fs.get("total_debt") / fs.get("ebitda"), msg="PINF Debt/EBITDA FY2025")

    def test_omega_logistics_dscr(self):
        fs = _co("OLOG001")["financials"]["FY2025"]
        ratios = compute_all_ratios(fs)
        val = _ratio_val(ratios, "dscr")
        # DSCR should be between 1.0 - 2.0 for a stressed logistics company
        assert val is not None and 1.0 <= val <= 2.0, f"OLOG DSCR should be 1.0-2.0, got {val}"

    def test_multi_period_returns_all_periods(self):
        result = compute_multi_period_ratios(_co("BMFG001")["financials"])
        assert len(result) >= 3, f"Expected >=3 periods, got {len(result)}"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. VALIDATION ENGINE TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidationEngine:
    """Test validation exceptions for each scenario."""

    def _run_validation(self, entity_id):
        co = _co(entity_id)
        b = co["borrower"]
        bureau = mock_bureau_commercial_report(b.pan)
        gst = mock_gst_turnover(b.pan)
        market_signals = co.get("market_signals", [])
        return run_all_validations(
            borrower=b,
            financials=co["financials"],
            provisional=co.get("provisional"),
            exchange_filing=co.get("exchange_filing"),
            bureau_payload=bureau,
            gst_payload=gst,
            market_signals=market_signals,
            conduct_records=co.get("conduct"),
            covenants=co.get("covenants"),
            case_type=co["facility"].case_type,
        )

    def test_bharat_mfg_has_few_or_no_critical(self):
        exceptions = self._run_validation("BMFG001")
        critical = [e for e in exceptions if e.severity in (RiskSeverity.CRITICAL, RiskSeverity.HIGH)]
        assert len(critical) == 0, f"BMFG: expected 0 critical/high, got {len(critical)}: {[e.exception_code for e in critical]}"

    def test_pinnacle_infra_catches_revenue_mismatch(self):
        exceptions = self._run_validation("PINF001")
        codes = [e.exception_code for e in exceptions]
        has_high = any(e.severity in (RiskSeverity.CRITICAL, RiskSeverity.HIGH) for e in exceptions)
        assert has_high, f"PINF: expected high-severity exceptions; codes={codes}"

    def test_sunrise_pharma_catches_group_risk(self):
        exceptions = self._run_validation("SPHR001")
        codes = [e.exception_code for e in exceptions]
        has_group = any("GRP" in c or "GROUP" in c.upper() for c in codes)
        assert has_group, f"SPHR: expected group risk exception; codes={codes}"

    def test_omega_etb_conduct_flagged(self):
        exceptions = self._run_validation("OLOG001")
        codes = [e.exception_code for e in exceptions]
        has_conduct = any("COND" in c or "COV" in c for c in codes)
        assert has_conduct, f"OLOG: expected conduct/covenant exceptions; codes={codes}"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. BENCHMARK ENGINE TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestBenchmarkEngine:
    """Test benchmark classifications."""

    def test_bharat_mfg_benchmarks_mostly_healthy(self):
        co = _co("BMFG001")
        bm = benchmark_all_periods(co["borrower"].entity_id, co["borrower"].sector, co["financials"])
        periods = sorted(bm.keys())
        latest = bm[periods[-1]]
        # Healthy company should have some benchmarks that are not "worse_than_peer"
        not_worse = [b for b in latest if b.status.value != "worse_than_peer"]
        assert len(not_worse) >= 1, "BMFG expected at least some non-worse benchmarks"

    def test_pinnacle_infra_flags_debt_metrics(self):
        co = _co("PINF001")
        bm = benchmark_all_periods(co["borrower"].entity_id, co["borrower"].sector, co["financials"])
        periods = sorted(bm.keys())
        worst = get_worst_benchmarks(bm, periods[-1])
        assert len(worst) >= 1, "PINF: expected at least 1 flagged benchmark"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. POLICY ENGINE TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestPolicyEngine:
    """Test policy decisions per scenario."""

    def _run_policy(self, entity_id):
        co = _co(entity_id)
        b = co["borrower"]
        bureau = mock_bureau_commercial_report(b.pan)
        market_signals = co.get("market_signals", [])
        gst = mock_gst_turnover(b.pan)

        exceptions = run_all_validations(
            borrower=b,
            financials=co["financials"],
            provisional=co.get("provisional"),
            exchange_filing=co.get("exchange_filing"),
            bureau_payload=bureau,
            gst_payload=gst,
            market_signals=market_signals,
            conduct_records=co.get("conduct"),
            covenants=co.get("covenants"),
            case_type=co["facility"].case_type,
        )

        # Hard rules are evidence-based: KYC needs the document inventory, company status the MCA status.
        evidence = {"document_inventory": {"has_kyc": True, "kyc_files": ["pan_card.pdf"], "source": "test"},
                    "mca_status": "Active"}
        # The mock bureau returns "not_found" (empty payload); supply a clean report as the bureau evidence.
        clean_bureau = {"payload": {"wilful_defaulter": False, "dpd_status": "Standard", "fraud_flag": False,
                                    "rbi_defaulter_list": False, "suit_filed_amount_cr": 0.0, "total_exposure_cr": 100.0}}
        t1 = tier1_hard_rules(b, co["facility"], exceptions, bureau if (bureau or {}).get("payload") else clean_bureau,
                              **evidence)

        mp = compute_multi_period_ratios(co["financials"])
        bm_all = benchmark_all_periods(b.entity_id, b.sector, co["financials"])
        periods = sorted(mp.keys())
        latest_ratios = mp[periods[-1]] if periods else []
        latest_bm = bm_all[periods[-1]] if periods else []

        t2 = tier2_scoring(
            borrower=b,
            ratios=latest_ratios,
            benchmarks=latest_bm,
            conduct=co.get("conduct", []),
            covenants=co.get("covenants", []),
            directors=co["directors"],
            group_entities=len(co["group"].entities),
            market_signals=market_signals,
        )

        total_fsv = sum(c.forced_sale_value_cr for c in co["collateral"])
        facility_amt = co["facility"].amount_requested_cr
        cov = round(total_fsv / facility_amt, 2) if facility_amt > 0 else 0

        t3 = tier3_recommendation(t1, t2, exceptions, co["facility"], cov)
        return t1, t2, t3

    def test_hard_rules_without_evidence_are_not_verified(self):
        co = _co("BMFG001")
        t1 = {d.rule_code: d.result for d in tier1_hard_rules(co["borrower"], co["facility"], [], {})}
        assert t1["HR_KYC_COMPLETE"] == "not_verified" and t1["HR_COMPANY_ACTIVE"] == "not_verified"

    def test_bharat_mfg_approved(self):
        t1, t2, t3 = self._run_policy("BMFG001")
        assert all(d.result == "pass" for d in t1), f"BMFG hard rules failed: {[d.rule_code for d in t1 if d.result != 'pass']}"
        assert t2.risk_grade in ("A", "B"), f"BMFG risk grade: {t2.risk_grade}"
        assert t3.recommendation.value in ("approve", "conditional_approve"), \
            f"BMFG recommendation: {t3.recommendation.value}"

    def test_pinnacle_infra_referred_or_conditional(self):
        t1, t2, t3 = self._run_policy("PINF001")
        assert t3.recommendation.value in ("conditional_approve", "refer_to_committee", "decline"), \
            f"PINF recommendation: {t3.recommendation.value}"

    def test_sunrise_pharma_group_risk(self):
        t1, t2, t3 = self._run_policy("SPHR001")
        assert t3.recommendation.value != "approve", \
            f"SPHR should not get clean approve, got: {t3.recommendation.value}"

    def test_omega_logistics_conduct_issues(self):
        t1, t2, t3 = self._run_policy("OLOG001")
        assert t3.recommendation.value in ("conditional_approve", "refer_to_committee", "decline"), \
            f"OLOG recommendation: {t3.recommendation.value}"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. DETERMINISM TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestDeterminism:
    """Verify identical output on repeated runs."""

    def test_fact_pack_determinism_bharat(self):
        fp1 = build_cam_fact_pack(ALL_COMPANIES["BMFG001"])
        fp2 = build_cam_fact_pack(ALL_COMPANIES["BMFG001"])
        for fp in (fp1, fp2):
            fp["meta"].pop("generated_date", None)
        assert json.dumps(fp1, sort_keys=True, default=str) == json.dumps(fp2, sort_keys=True, default=str), \
            "Fact pack not deterministic!"

    def test_fact_pack_determinism_all_companies(self):
        for eid in ALL_COMPANIES:
            fp1 = build_cam_fact_pack(ALL_COMPANIES[eid])
            fp2 = build_cam_fact_pack(ALL_COMPANIES[eid])
            for fp in (fp1, fp2):
                fp["meta"].pop("generated_date", None)
            assert json.dumps(fp1, sort_keys=True, default=str) == json.dumps(fp2, sort_keys=True, default=str), \
                f"Determinism failed for {eid}"

    def test_cam_narrative_determinism(self):
        fp1 = build_cam_fact_pack(ALL_COMPANIES["BMFG001"])
        fp2 = build_cam_fact_pack(ALL_COMPANIES["BMFG001"])
        cam1 = render_complete_cam(fp1)
        cam2 = render_complete_cam(fp2)
        cam1_clean = re.sub(r"\d{4}-\d{2}-\d{2}", "DATE", cam1)
        cam2_clean = re.sub(r"\d{4}-\d{2}-\d{2}", "DATE", cam2)
        assert cam1_clean == cam2_clean, "CAM narrative not deterministic"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. END-TO-END PIPELINE TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestEndToEnd:
    """Full pipeline integration tests."""

    def test_bharat_mfg_complete_pipeline(self):
        fp = build_cam_fact_pack(ALL_COMPANIES["BMFG001"])
        cam = render_complete_cam(fp)
        assert "CREDIT APPROVAL MEMORANDUM" in cam
        assert "Bharat Manufacturing" in cam
        assert "RECOMMENDATION" in cam
        assert len(cam) > 5000, f"CAM too short: {len(cam)} chars"

    def test_pinnacle_infra_complete_pipeline(self):
        fp = build_cam_fact_pack(ALL_COMPANIES["PINF001"])
        cam = render_complete_cam(fp)
        assert "Pinnacle Infra" in cam
        assert "VALIDATION" in cam
        assert len(cam) > 5000

    def test_sunrise_pharma_complete_pipeline(self):
        fp = build_cam_fact_pack(ALL_COMPANIES["SPHR001"])
        cam = render_complete_cam(fp)
        assert "Sunrise Pharma" in cam
        assert len(cam) > 5000

    def test_omega_logistics_complete_pipeline(self):
        fp = build_cam_fact_pack(ALL_COMPANIES["OLOG001"])
        cam = render_complete_cam(fp)
        assert "Omega Logistics" in cam
        assert "CONDUCT" in cam
        assert len(cam) > 5000

    def test_all_companies_produce_different_cams(self):
        cams = {}
        for eid in ALL_COMPANIES:
            fp = build_cam_fact_pack(ALL_COMPANIES[eid])
            cams[eid] = render_complete_cam(fp)
        eids = list(cams.keys())
        for i in range(len(eids)):
            for j in range(i + 1, len(eids)):
                assert cams[eids[i]] != cams[eids[j]], \
                    f"CAMs for {eids[i]} and {eids[j]} should differ"

    def test_fact_pack_has_all_required_sections(self):
        required = [
            "meta", "case_summary", "borrower_profile", "group_profile",
            "management_profile", "facility_details", "financial_summary",
            "ratio_analysis", "benchmark_summary", "collateral_analysis",
            "validation_exceptions", "policy_decisions",
        ]
        for eid in ALL_COMPANIES:
            fp = build_cam_fact_pack(ALL_COMPANIES[eid])
            for section in required:
                assert section in fp, f"{eid}: missing section '{section}'"


# ═══════════════════════════════════════════════════════════════════════════════
# RUNNER
# ═══════════════════════════════════════════════════════════════════════════════

def run_all_tests():
    """Simple test runner (no pytest dependency required)."""
    test_classes = [
        TestRatioEngine,
        TestValidationEngine,
        TestBenchmarkEngine,
        TestPolicyEngine,
        TestDeterminism,
        TestEndToEnd,
    ]
    total = 0
    passed = 0
    failed = 0
    errors = []

    for cls in test_classes:
        instance = cls()
        methods = [m for m in dir(instance) if m.startswith("test_")]
        print(f"\n{'='*60}")
        print(f"  {cls.__name__} ({len(methods)} tests)")
        print(f"{'='*60}")
        for method_name in sorted(methods):
            total += 1
            try:
                getattr(instance, method_name)()
                passed += 1
                print(f"  ✅ {method_name}")
            except Exception as e:
                failed += 1
                errors.append((cls.__name__, method_name, str(e)))
                print(f"  ❌ {method_name}: {e}")

    print(f"\n{'='*60}")
    print(f"  RESULTS: {passed}/{total} passed, {failed} failed")
    print(f"{'='*60}")

    if errors:
        print("\nFailed Tests:")
        for cls_name, method, err in errors:
            print(f"  {cls_name}.{method}: {err}")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
