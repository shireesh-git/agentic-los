"""Credit Reassessment Agent: the demo borrower, each decision path, analyst statuses feeding back, API."""

import copy

import pytest
from fastapi.testclient import TestClient

from src.agents.reassessment_agent import reassess
from src.application.case_service import build_case_result

ENTITY = "ABCE001"


def full_case(company):
    """The case record a pipeline run would store (M1–M6 included)."""
    from src.engines.cam_fact_builder import build_cam_fact_pack
    fp = build_cam_fact_pack(copy.deepcopy(company))
    return build_case_result(ENTITY, company, {"results": {"narrative": {"fact_pack": fp}}}, [])


@pytest.fixture(scope="module")
def company():
    from src.data.company_catalog import seed_company_store
    return seed_company_store()[ENTITY]


@pytest.fixture(scope="module")
def case(company):
    return full_case(company)


def items(result, key):
    return [x["item"] for x in result[key]]


# ─── Demo borrower ───────────────────────────────────────────────────────────

def test_demo_proposal_is_reduced_and_restructured(case):
    r = case["reassessment"]
    fr = r["facility_recommendation"]
    assert r["decision"] == "REDUCED_MODIFIED"
    assert (fr["requested_cr"], fr["recommended_cr"], fr["change_cr"]) == (250.0, 185, -65.0)
    assert fr["structure"].startswith("Replacement of existing short-term lines")
    assert fr["sizing"]["binding_cap"] == "interest_cover"
    caps = {c["cap"]: c["amount_cr"] for c in fr["sizing"]["caps"]}
    assert caps == {"interest_cover": 187.5, "interest_cover_downside": -136.35, "eligible_drawing_power": 396.64}
    assert fr["sizing"]["leverage_headroom_cr"] == -28.0


def test_demo_reassessment_differs_from_the_policy_engine(case):
    r = case["reassessment"]
    fr = r["facility_recommendation"]
    assert fr["original_policy_recommendation"] == "decline" and fr["original_risk_grade"] == "D"
    assert fr["deviation_route_required"] is True
    assert any("Policy engine recommendation was 'decline'" in s for s in r["rationale"])


def test_demo_conditions_and_mitigants(case):
    r = case["reassessment"]
    cps = items(r, "conditions_precedent")
    assert "Interest-servicing reserve of ₹3.70 Cr" in cps[0]                       # 185 × 8% / 4
    assert any("No net increase in total borrowings" in c and "₹28.00 Cr above" in c for c in cps)
    assert any("forced-sale value of at least ₹72.50 Cr" in c for c in cps)        # 185 × 1.0 − 112.50
    assert sum(c.startswith("Close investigation") for c in cps) == 3              # the three open P1s
    assert any(c.startswith("Deviation approval") for c in cps)
    assert any("Debt/EBITDA covenant" in c for c in items(r, "conditions_subsequent"))
    assert any("book-debt margin raised to 40%" in m for m in items(r, "recommended_mitigants"))


def test_demo_links_and_dimensions(case):
    r = case["reassessment"]
    assert len(r["linked_observations"]) == 12 and len(r["linked_investigations"]) == 7
    assert len(r["linked_challenges"]) == 7
    assert [s["scenario"] for s in r["linked_stress_scenarios"]] == ["base", "downside", "severe"]
    dims = r["overall_credit_assessment"]["dimensions"]
    assert dims["repayment_capacity"]["status"] == "STRESSED"
    assert dims["stress_resilience"]["status"] == "FAILS SEVERE"
    assert dims["leverage"]["status"] == "OUTSIDE POLICY"
    assert dims["cash_flow"]["status"] == "NEGATIVE UNDER STRESS"
    assert r["overall_credit_assessment"]["risk_status_counts"] == {"RESOLVED": 0, "MITIGATED": 0, "UNRESOLVED": 12}


def test_figures_come_from_earlier_steps(case):
    r = case["reassessment"]
    metrics = {m["metric"]: m["value"] for m in r["supporting_metrics"]}
    stress = {s["scenario"]: s["stressed_metrics"] for s in case["stress_test"]["scenarios"]}
    assert metrics["base_dscr"] == stress["base"]["dscr"] == 1.19
    assert metrics["downside_dscr"] == stress["downside"]["dscr"]
    assert metrics["severe_interest_coverage_ratio"] == stress["severe"]["interest_coverage_ratio"]
    ebit, interest = stress["base"]["ebit_cr"], stress["base"]["finance_cost_cr"]
    assert metrics["interest_cover"] == round((ebit / 2.0 - interest) / 0.08, 2)


# ─── Analyst work feeds back ─────────────────────────────────────────────────

def test_resolving_investigations_changes_the_reassessment(case):
    c = copy.deepcopy(case)
    for t in c["investigations"]:
        t["status"] = "RESOLVED"
    r = reassess(c)
    assert not any(cp.startswith("Close investigation") for cp in items(r, "conditions_precedent"))
    counts = r["overall_credit_assessment"]["risk_status_counts"]
    assert counts["RESOLVED"] == 8 and counts["UNRESOLVED"] == 4       # observations without an investigation stay open
    assert all(u["type"] == "challenge" for u in r["unresolved_issues"])


def test_accepted_challenges_mitigate_risks(case):
    c = copy.deepcopy(case)
    for ch in c["challenges"]:
        if ch["rule_id"] == "LEVERAGE":
            ch["status"] = "ACCEPTED"
            ch["review"] = {"response": "Promoter equity infusion agreed"}
    r = reassess(c)
    reg = {x["title"]: x for x in r["risk_register"]}
    assert reg["Increasing Leverage Risk"]["status"] == "MITIGATED"
    assert any("Promoter equity infusion agreed" == f["evidence"] for f in r["key_supporting_factors"])


# ─── Decision paths ──────────────────────────────────────────────────────────

def test_failed_hard_rule_is_not_supported(case):
    c = copy.deepcopy(case)
    c["fact_pack"]["policy_decisions"]["tier1_hard_rules"][0]["result"] = "fail"
    r = reassess(c)
    assert r["decision"] == "NOT_SUPPORTED" and r["facility_recommendation"]["recommended_cr"] == 0.0


def test_base_dscr_below_one_is_not_supported(case):
    c = copy.deepcopy(case)
    c["stress_test"]["scenarios"][0]["stressed_metrics"]["dscr"] = 0.95
    assert reassess(c)["decision"] == "NOT_SUPPORTED"


def test_too_many_open_p1_investigations_defers(case):
    r = reassess(copy.deepcopy(case), settings={"defer_if_open_p1_at_least": 3})
    assert r["decision"] == "DEFERRED" and r["facility_recommendation"]["recommended_cr"] is None


def test_healthy_year_confirms_the_requested_amount(company):
    """FY2025 alone: full amount confirmed; conditions remain for the bureau-exposure gap and a downside breach."""
    healthy = copy.deepcopy(company)
    healthy["financials"].pop("FY2026")
    r = full_case(healthy)["reassessment"]
    assert r["decision"] == "SUPPORTED_WITH_CONDITIONS"
    assert r["facility_recommendation"]["recommended_cr"] == 250.0
    assert r["facility_recommendation"]["structure"] == "As proposed"


def test_clean_case_is_supported_without_conditions(company):
    healthy = copy.deepcopy(company)
    healthy["financials"].pop("FY2026")
    c = full_case(healthy)
    c["observations"], c["investigations"], c["challenges"] = [], [], []
    for s in c["stress_test"]["scenarios"][:2]:
        s["policy_breaches"] = []
    r = reassess(c)
    assert r["decision"] == "SUPPORTED" and r["conditions_precedent"] == []
    assert r["facility_recommendation"]["recommended_cr"] == 250.0


def test_unavailable_without_stress_results(case):
    c = copy.deepcopy(case)
    c.pop("stress_test")
    assert reassess(c)["available"] is False


# ─── API ─────────────────────────────────────────────────────────────────────

@pytest.fixture()
def client(case):
    from src.api.app import create_app
    from src.application.container import build_container

    container = build_container()
    stored = {k: v for k, v in copy.deepcopy(case).items() if k != "reassessment"}   # back-filled on read
    stored["run_id"] = "reas-run-1"
    container.state.cases[ENTITY] = stored
    container.persistence.save_case_run(stored)
    yield TestClient(create_app(container)), container
    container.state.cases.pop(ENTITY, None)
    container.persistence.delete_company(ENTITY)   # leave no partial case for later tests


def test_api_follows_investigation_status(client):
    http, container = client
    r = http.get(f"/api/cases/{ENTITY}/reassessment").json()["reassessment"]
    assert r["decision"] == "REDUCED_MODIFIED"
    assert container.persistence.get_case_run("reas-run-1")["reassessment"]["decision"] == "REDUCED_MODIFIED"
    http.patch(f"/api/cases/{ENTITY}/investigations/INV-{ENTITY}-DATA_RELIABILITY", json={"status": "RESOLVED"})
    cps = items(http.get(f"/api/cases/{ENTITY}/reassessment").json()["reassessment"], "conditions_precedent")
    assert "Close investigation: Data reliability — confirm the correct source." not in cps
    assert http.get("/api/cases/NOCASE999/reassessment").status_code == 404
