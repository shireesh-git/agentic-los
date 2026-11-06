"""The CAM engine's verdict on every screen, challenges that say what to do, Copilot next steps and the
justification gate (fix list F11–F14): unit tests on src/flow/risk.py, then Madras Fertilizers end to end —
the engine recommends Decline, so moving the proposal forward needs a written justification."""

import re

import pytest

from src.application.errors import InvalidRequestError
from src.application.container import build_container
from src.flow import risk as rk

E = "MFL001"


def _engine(**over):
    e = {"run_id": "R1", "recommendation": "decline", "risk_grade": "D", "composite_score": 45.8,
         "rationale": "Hard rule failures detected.", "requested_amount_cr": 240.0,
         "fact_pack": {
             "policy_thresholds": {"min_dscr": 1.2, "max_debt_to_ebitda": 4.0, "min_current_ratio": 1.25,
                                   "min_interest_coverage": 2.0, "max_tol_tnw": 4.0, "max_debt_to_equity": 2.5},
             "policy_decisions": {"tier1_hard_rules": [
                 {"rule": "HR_KYC_COMPLETE", "description": "KYC package must be complete", "result": "fail",
                  "details": "KYC documents not on file"},
                 {"rule": "HR_MIN_VINTAGE", "description": "At least 3 years old", "result": "pass"},
                 {"rule": "HR_BUREAU_STATUS", "description": "Bureau status", "result": "not_verified"}]},
             "ratio_analysis": {"FY2024": {"dscr": {"value": 2.0}},
                                "FY2025": {"dscr": {"value": 0.86}, "debt_to_ebitda": {"value": 7.67},
                                           "current_ratio": {"value": 1.3}, "tol_tnw": {"value": 3.61},
                                           "debt_to_equity": {"value": 1.75},
                                           "interest_coverage_ratio": {"value": 0.94}}},
             "facility_details": {"proposed_limit_cr": 240.0},
             "financial_projections": {"assumptions": {"debt_basis_cr": 585.0}},
             "cash_flow_repayment": {"periods": {"FY2025": {"ebitda_cr": 45.0}}}},
         "challenges": [
             {"challenge_id": "C-LEV", "rule_id": "LEVERAGE", "title": "Leverage above policy", "severity": "HIGH",
              "challenge": "Debt/EBITDA 7.67x.", "rationale": "More exposure raises loss given default. Linked x.",
              "required_response": ["Lender-wise debt schedule."]},
             {"challenge_id": "C-POL", "rule_id": "POLICY_EXCEPTIONS", "title": "Outside policy",
              "severity": "CRITICAL", "challenge": "2 hard rules failed.", "rationale": "Must be justified.",
              "required_response": ["Deviation note."]}]}
    e.update(over)
    return e


def test_assess_colours_by_policy():
    r = rk.assess(_engine())
    assert r["label"] == "Decline" and r["tone"] == "bad" and r["rating"] == "D" and r["period"] == "FY2025"
    st = {x["id"]: x["status"] for x in r["ratios"]}
    assert st["dscr"] == "bad" and st["debt_to_ebitda"] == "bad" and st["debt_to_equity"] == "good"
    assert st["current_ratio"] == "warn" and st["tol_tnw"] == "warn"           # within 10% of the limit
    assert [h["code"] for h in r["hard_rules"]["failed"]] == ["HR_KYC_COMPLETE"]
    assert len(r["hard_rules"]["not_verified"]) == 1 and r["breaches"] == 3
    assert rk.needs_justification(r) and not rk.needs_justification(rk.assess(_engine(
        recommendation="refer", fact_pack={**_engine()["fact_pack"], "policy_decisions": {}})))


def test_amount_advice():
    h = rk.amount_advice(_engine())
    assert h["debt_capacity_cr"] == 180.0 and h["existing_debt_cr"] == 345.0 and h["max_amount_cr"] == 0.0
    assert "no amount brings leverage within policy" in rk.amount_text(h)
    fp = _engine()["fact_pack"]
    smaller = rk.amount_advice(_engine(fact_pack={**fp, "cash_flow_repayment": {"periods": {"FY2025": {"ebitda_cr": 100.0}}}}))
    assert smaller["max_amount_cr"] == 55.0 and not smaller["fits"]               # 400 capacity − 345 existing
    assert "₹55.00 Cr" in rk.amount_text(smaller)


def test_challenges_most_severe_first_with_actions():
    ch = rk.challenges(_engine())
    assert [c["id"] for c in ch] == ["C-POL", "C-LEV"]                           # CRITICAL before HIGH
    lev = ch[1]
    assert [a["kind"] for a in lev["actions"]] == ["send_back", "justify", "reject"]   # no amount fits
    assert lev["why"] == "More exposure raises loss given default." and lev["amount_note"]
    assert "Lender-wise debt schedule" in lev["actions"][0]["prefill"]
    text, buttons = rk.plan("credit_risk", ["approve", "send_back", "reject"], rk.assess(_engine()), ch, {}, [], True)
    assert text.startswith("Next steps:\n1. Note the engine's verdict: Decline") and "write a justification" in text
    assert {b["kind"] for b in buttons} >= {"send_back", "approve"}
    done, _ = rk.plan("credit_risk", ["approve"], None, ch, {"C-POL": {}, "C-LEV": {}}, [], True)
    assert "Already answered" in done


@pytest.fixture(scope="module")
def svc():
    from src.services.persistence import persistence

    def runs():
        with persistence._connect() as conn:
            return ({r[0] for r in conn.execute("SELECT run_id FROM case_runs WHERE entity_id = ?", (E,))},
                    {r[0] for r in conn.execute("SELECT run_id FROM pipeline_runs WHERE entity_id = ?", (E,))})

    cases_before, attempts_before = runs()
    flow = build_container().flow
    flow.reset({"user": {"id": "test"}}, E)
    yield flow
    flow.reset({"user": {"id": "test"}}, E)
    cases_after, attempts_after = runs()
    with persistence._connect() as conn:
        conn.executemany("DELETE FROM case_runs WHERE run_id = ?", [(r,) for r in cases_after - cases_before])
        conn.executemany("DELETE FROM pipeline_runs WHERE run_id = ?", [(r,) for r in attempts_after - attempts_before])


def test_madras_decline_needs_justification(svc):
    rm, cro, sa = (svc.sign_in(u) for u in ("f_rm", "f_cro", "f_sa"))
    case = svc.create(rm, entity_id=E)
    cid = case["case_id"]
    svc.generate_cam(cid, rm)
    assert svc.wait_for_cam(cid, timeout=300)["cam"]["state"] == "ready"
    v = svc.view(cid, rm)
    assert v["risk"]["tone"] == "bad" and v["risk"]["label"] == "Decline"
    assert any(r["status"] == "bad" for r in v["risk"]["ratios"])
    assert v["against"] and all(a["actions"] for a in v["against"])
    assert v["actions"][0]["justify"]                                            # the action bar says why
    for sp in [p for g in v["groups"] for p in g["points"] if p["status"] == "missing"]:
        svc.skip_datapoint(cid, rm, sp["id"]) if not sp["required"] else svc.set_datapoint(cid, rm, sp["id"], "1")

    with pytest.raises(InvalidRequestError, match="justification"):
        svc.act(cid, rm, "approve")
    svc.act(cid, rm, "approve", "Promoter equity infusion of ₹100 Cr committed; KYC to follow")
    v = svc.view(cid, cro)
    assert v["deviations"][0]["by"] and "Decline" in " ".join(v["deviations"][0]["reasons"])
    notes = " ".join(m["text"] for m in v["chat"] if m.get("stage") == "credit_risk")
    assert "CAM engine verdict: Decline" in notes and "proceeded despite" in notes

    # Copilot: concrete next steps with buttons, and the amount check
    svc.chat(cid, cro, "What should I do next?")
    msg = svc.view(cid, cro)["chat"][-1]
    assert msg["text"].startswith("Next steps:") and msg.get("actions")
    svc.chat(cid, cro, "reading the risks, should I change the amount requested?")
    msg = svc.view(cid, cro)["chat"][-1]
    assert "Sustainable limit" in msg["text"] and "already outside" in msg["text"] and "DSCR" in msg["text"]

    # answer one challenge in writing, return for documents on another
    a0, a1 = v["against"][0]["id"], v["against"][1]["id"]
    with pytest.raises(InvalidRequestError):
        svc.respond(cid, cro, a0, "justify", "")
    svc.respond(cid, cro, a0, "justify", "Mitigant: DSRA of two quarters' interest")
    svc.act(cid, cro, "send_back", "Provide the lender-wise debt schedule", challenge=a1)
    v = svc.view(cid, rm)
    assert v["responses"][a0]["kind"] == "justify" and v["responses"][a1]["kind"] == "send_back"
    pack = svc.audit_pack(cid, rm)
    for text in ("CAM engine verdict and policy", "Proceeded against the engine", "Justification recorded",
                 "Returned for documents"):
        assert text in pack, text


def test_madras_deviation_register(svc):
    """L1: each policy breach is a deviation — Underwriting records the mitigant, the Sanctioning Authority
    approves it; a failed hard rule cannot be approved and keeps Sanction blocked."""
    rm, cro, sa = (svc.sign_in(u) for u in ("f_rm", "f_cro", "f_sa"))
    svc.reset({"user": {"id": "test"}}, E)
    cid = svc.create(rm, entity_id=E)["case_id"]
    svc.generate_cam(cid, rm)
    assert svc.wait_for_cam(cid, timeout=300)["cam"]["state"] == "ready"
    v = svc.view(cid, rm)
    reg = v["register"]
    ratios = [d for d in reg if d["kind"] == "threshold"]
    rules = [d for d in reg if d["kind"] == "hard_rule"]
    assert ratios and all(d["deviable"] for d in ratios) and rules and not any(d["deviable"] for d in rules)
    dev_text = next(p for g in v["groups"] for p in g["points"] if p["id"] == "deviations")["value"]
    assert "not deviable" in dev_text
    for sp in [p for g in v["groups"] for p in g["points"] if p["status"] == "missing"]:
        svc.skip_datapoint(cid, rm, sp["id"]) if not sp["required"] else svc.set_datapoint(cid, rm, sp["id"], "1")
    svc.act(cid, rm, "approve", "Equity infusion committed")
    with pytest.raises(Exception, match="mitigant"):
        svc.act(cid, cro, "approve", "Recommended with mitigants")
    for d in ratios:
        svc.deviation(cid, cro, d["id"], "propose", "Quarterly DSCR covenant; DSRA of two quarters", "Promoter support")
    svc.act(cid, cro, "approve", "Recommended with mitigants")
    v = svc.view(cid, sa)
    blockers = next(a for a in v["actions"] if a["id"] == "approve")["blockers"]
    assert any("not deviable" in b for b in blockers) and any("awaiting your approval" in b for b in blockers)
    with pytest.raises(Exception, match="not deviable"):
        svc.deviation(cid, sa, rules[0]["id"], "approve")
    for d in ratios:
        svc.deviation(cid, sa, d["id"], "approve")
    v = svc.view(cid, sa)
    blockers = next(a for a in v["actions"] if a["id"] == "approve")["blockers"]
    assert not any("awaiting" in b for b in blockers) and any("not deviable" in b for b in blockers)
    assert "Deviation register" in svc.audit_pack(cid, sa)


def test_quality_blocks_on_madras(svc):
    """D2–D4: sustainable limit, earnings quality, early-warning flags and confidence reach the fields."""
    rm = svc.sign_in("f_rm")
    case = next(c for c in svc.store.all() if c["entity_id"] == E and c["status"] == "open")
    v = svc.view(case["case_id"], rm)
    pts = {p["id"]: p for g in v["groups"] for p in g["points"]}
    assert pts["dscr"]["band"]["status"] == "bad" and pts["dscr"]["computed"]
    assert pts["sustainable_limit_cr"]["value"] == 0.0 and pts["sustainable_limit_cr"]["band"]["status"] == "bad"
    assert pts["ews_flags"]["value"] >= 2 and pts["earnings_quality"]["value"] < 85
    assert pts["revenue_cr"]["confidence"]["score"] <= 90 and "not cross-checked" in pts["revenue_cr"]["confidence"]["basis"]
    assert pts["revenue_truth"]["status"] == "unavailable" and pts["bureau_score"]["display"].startswith("Not on record")
    assert pts["constitution"]["value"].startswith("Government company (listed)")      # CIN …GOI…
    with pytest.raises(Exception, match="calculated"):
        svc.set_datapoint(case["case_id"], rm, "dscr", 1.5)


def test_streamlined_cam_with_live_decision_summary(svc):
    """C1/C2: the CAM has a Decision Summary and eight merged sections; the downloaded PDF's summary is the
    workflow's live one (deviation register, challenge answers, confidence)."""
    from src.flow import datapoints as dpx

    rm = svc.sign_in("f_rm")
    case = next(c for c in svc.store.all() if c["entity_id"] == E and c["status"] == "open")
    engine = svc.cases.get(E)
    heads = re.findall(r"^## (.+)$", engine["cam_text"], re.M)
    assert "DECISION SUMMARY" in heads and "8. SECURITY, COVENANTS, TERMS & RECOMMENDATION" in heads
    assert not any("SOCIAL MEDIA" in h.upper() for h in heads) and len([h for h in heads if h[:1].isdigit()]) == 8
    assert "Debt Capacity and Sustainable Limit" in engine["cam_text"] and "Early-Warning Indicators" in engine["cam_text"]
    pdf, _ = svc.cam_file(case["case_id"], rm)
    text = " ".join(dpx.page_texts(pdf, limit=6))
    for s in ("Deviation Register", "Confidence of Key Figures", "Key Risk Challenges and Their Answers",
              "no model-written text"):
        assert s in text, s
