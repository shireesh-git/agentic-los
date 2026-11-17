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


def test_every_borrower_passes_the_test_data_validation():
    """scripts/validate_test_data.py: CIN / PAN format and incorporation year, demo registry and demo documents
    naming the borrower only, no invented news / filings / KPIs, no personal data on directors. (The checks
    against the annual reports run where the reports are fetched; tests run without them.)"""
    import importlib.util
    from pathlib import Path
    from src.data import borrowers
    spec = importlib.util.spec_from_file_location("v", Path(__file__).resolve().parents[1] / "scripts" / "validate_test_data.py")
    v = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v)
    problems = {e: [m for lvl, m in v.check(e, borrowers.load(e)) if lvl == "error"] for e in borrowers.ids()}
    assert not {e: p for e, p in problems.items() if p}
    for e in borrowers.ids():
        rec = borrowers.load(e)
        if rec.get("latest_statement_source"):
            assert not rec.get("market_signals"), e                    # news is live, never stored
            assert not rec.get("sector_kpis") or rec["sector_kpis"].get("document"), e   # only with its source
            assert all(d.net_worth_cr is None and d.pan is None for d in rec.get("directors") or []), e


def test_bank_records_follow_the_real_figures_and_stay_clean():
    """src/data/demo_bank_book.py: sizes from the audited borrowings, within the bank's appetite; a real company's
    conduct is clean and its covenants are tested on its real ratios."""
    from src.core.config_manager import config
    from src.data import borrowers, demo_bank_book
    cfg = dict(config.get("data_sources", "demo_data", "bank_book", default={}))
    cfg["tier1_capital_cr"] = 8000
    policy = config.get("rules", "policy_thresholds", default={})
    assert not demo_bank_book.build(borrowers.load("ADPT001"), cfg, policy)["existing_exposure"]   # new to the bank
    rec = borrowers.load("NTPC001")                                       # an existing customer
    out = demo_bank_book.build(rec, cfg, policy)
    assert out["core_banking"]["bclc"]["single_borrower_limit_pct"] <= 10.0 + 1e-6
    assert all(c["max_overdue_days"] == 0 and c["cheque_returns"] == 0 for c in out["conduct"])
    li = rec["financials"][max(rec["financials"])].line_items
    cr = next(c for c in out["covenants"] if c["covenant_type"] == "Current ratio")
    assert cr["actual_value"] == f"{li['current_assets'] / li['current_liabilities']:.2f}"
    assert cr["compliance_status"] == ("compliant" if li["current_assets"] / li["current_liabilities"] >= 1.25 else "breached")
    assert out["crilc"]["aggregate_exposure"]["total_exposure_outstanding"] == round(li["long_term_debt"] + li["short_term_debt"], 2)
    assert out["charges"]["charges"] and "DEMO DATA" in out["charges"]["note"]


def test_live_news_is_screened_labelled_and_never_saved():
    from src.engines.data_provenance import classify_fact_pack
    from src.flow.acquire import mapper
    env = {"source": "gdelt", "payload": {"articles": [
        {"title": "Acme Ltd fined by regulator", "url": "u1", "source": "x.com", "date": "2026-10-01", "adverse": True,
         "adverse_reason": "regulatory action"},
        {"title": "Acme Ltd opens a plant", "url": "u2", "source": "y.com", "date": "2026-09-01", "adverse": False}]},
        "provenance": {"fetched_at": "2026-11-17T00:00:00"}}
    signals, crawl, market = mapper.news_into("ACME001", env)
    assert [s.source_name for s in signals] == ["GDELT"] and crawl["verified"] and market["payload"]["adverse_articles"] == 1
    fp = {"market_signals": [{"source": "GDELT", "headline": "x"}], "web_crawl_news": crawl,
          "existing_exposure": [{"x": 1}], "external_intelligence": {"bureau": {"a": 1}}}
    prov = classify_fact_pack(fp, {"external_data": {"bureau_data": {"provenance": {"via": "demo_file"}}}})
    assert prov["market_signals"]["class"] == "external" and prov["web_crawl_news"]["class"] == "source"
    assert prov["existing_exposure"]["class"] == "synthetic_demo"          # the bank's own records: demo, not source
    assert prov["external_intelligence"]["class"] == "synthetic_demo"      # a demo registry file, not a live API


def test_the_cam_run_passes_live_news_only_for_that_run(monkeypatch):
    from src.application.container import build_container
    svc = build_container().flow
    seen = {}

    class Acq:
        def live_news(self, name, eid):
            return {"market_signals": [], "web_crawl_news": {"articles": []}, "market_data": {}}

    monkeypatch.setattr(svc, "acquirer", Acq())
    monkeypatch.setattr(svc.cases, "run", lambda eid, on_progress=None, overrides=None: seen.update(o=overrides) or ({}, []))
    svc._run_engine("INFY001", {"facility": {}}, None)
    assert "live_news" in seen["o"] and "market_signals" not in (svc.companies.get("INFY001") or {}) or \
        not (svc.companies.get("INFY001") or {}).get("market_signals")
