"""Round 9 feedback (Adani Ports): choose-don't-type answers, "CMR-1" read as 1, one challenge per decision."""

from src.flow import datapoints as dpx
from src.flow import risk as rk


def test_a_hyphen_after_letters_is_not_a_minus_sign():
    num = {"type": "number", "label": "Rank"}
    assert dpx.parse_value(num, "CMR-1") == 1 and dpx.parse_value(num, "-3") == -3
    assert dpx.parse_value({"type": "amount", "label": "x"}, "₹ -12.5 Cr") == -12.5


def test_copilot_offers_answers_to_choose(tmp_path):
    from src.application.container import build_container
    svc = build_container().flow
    by_id = {sp["id"]: sp for sp in dpx.specs()}
    assert svc._options(by_id["bureau_score"])[0] == "CMR-1" and by_id["bureau_score"]["type"] == "text"
    cov = svc._options(by_id["covenants"])
    assert len(cov) == 1 and "DSCR ≥ 1.20x" in cov[0]                           # from rules.yaml, not code
    assert "Infrastructure" in svc._options(by_id["sector"]) and "IT services" in svc._options(by_id["sector"])
    for fid in ("tenor_months", "purpose", "pricing", "security", "marketing_arrangements"):
        assert svc._options(by_id[fid]), fid


def test_one_card_per_decision():
    inv = lambda i, t: {"investigation_id": i, "investigation_type": t, "title": t, "reason": "r",  # noqa: E731
                        "required_evidence": [{"item": t, "description": "d"}]}
    engine = {"fact_pack": {}, "investigations": [inv("I1", "DEBT_SERVICING"), inv("I2", "POLICY_EXCEPTION"),
                                                   inv("I3", "DATA_RELIABILITY")],
              "challenges": [
                  {"challenge_id": "C-REP", "rule_id": "REPAYMENT_CAPACITY", "title": "Cash flow", "severity": "HIGH"},
                  {"challenge_id": "C-POL", "rule_id": "POLICY_EXCEPTIONS", "title": "Outside policy",
                   "severity": "HIGH"},
                  {"challenge_id": "C-INV", "rule_id": "UNRESOLVED_INVESTIGATIONS", "title": "Open questions",
                   "severity": "MEDIUM", "linked_investigation_ids": ["I1", "I2", "I3"]}]}
    ch = rk.challenges(engine)
    assert [c["id"] for c in ch] == ["C-REP", "C-INV"]                     # breaches → Deviation Register
    assert ch[1]["asks"] == ["DATA_RELIABILITY: d"]                         # only what no other card asks
    engine["investigations"] = engine["investigations"][:2]
    assert [c["id"] for c in rk.challenges(engine)] == ["C-REP"]            # nothing left of its own


def test_other_policy_breaches_reach_the_register():
    engine = {"fact_pack": {"ratio_analysis": {"FY2026": {}}},
              "observations": [{"trigger": {"rule_id": "POLICY_DEVIATION", "observed": {"breaches": [
                  {"metric": "dscr", "label": "DSCR", "value": 0.8, "limit": 1.2, "limit_type": "min",
                   "threshold_key": "min_dscr"},
                  {"metric": "return_on_equity", "label": "Return on equity", "value": 2.9, "limit": 12,
                   "limit_type": "min", "threshold_key": "min_roe_pct"}]}}}]}
    other = rk.assess(engine)["other_breaches"]
    assert [b["id"] for b in other] == ["return_on_equity"] and other[0]["unit"] == "%"


def test_every_borrower_has_a_demo_registry_file_built_from_its_record():
    from src.data import borrowers, demo_registry
    for eid in borrowers.ids():
        rec = borrowers.load(eid)
        assert demo_registry.path_for(eid) or (rec.get("external_data") or {}).get("bureau_data"), eid
    rec = borrowers.load("OLOG001")                                   # 32 days overdue in its conduct → SMA-1
    d = demo_registry.from_record(rec, {"BBB": {"cmr_rank": "CMR-4", "credit_score": 720}}, "2026-11-16")
    assert d["bureau"]["dpd_status"] == "SMA-1" and d["bureau"]["cmr_rank"] == "CMR-4"
    assert d["mca"]["company_name"] == rec["borrower"].company_name and "DEMO DATA" in d["note"]
