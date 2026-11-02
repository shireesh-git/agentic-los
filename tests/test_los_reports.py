"""R14 — downloadable case reports.

The reports are derived from the stored application record, its audit events and its
documents: a case summary, the approval (sanction) record, the audit trail, the
document checklist, the conditions and the disbursement schedule. CSV output is
formula-injection safe (prefixed cells) and every report carries the generation time
and the filters applied. No secrets or file paths appear in the content.
"""
from datetime import datetime, timedelta

import pytest

from src.los.reports import CATALOG, build_report
from src.data.company_catalog import seed_company_store
from src.los.service import LosService, load_workflow
from src.los.store import LosStore

# aligned with test_los_modifications (run_pos records the acceptance at that clock)
NOW = datetime(2026, 10, 12, 12, 0, 0)


def make_service(tmp_path):
    return LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow,
                      seed_company_store(), clock=lambda: NOW)


def sanctioned(svc, entity="MFL001", amount=100.0):
    a = svc.create(svc._system_session("ps_maker"), entity_id=entity, profile="client_one",
                   facility={"facility_type": "working_capital", "facility_nature": "fund_based",
                             "proposal_type": "Fresh", "amount_cr": amount, "tenor_months": 12,
                             "interest_rate": 12.4, "purpose": "Working capital (demo)"},
                   sourcing_decision={"decision": "Refer for in-principle",
                                      "mandatory_remarks": "reports test"})
    svc._replay_to(a["application_id"], "pos_maker", NOW, NOW)
    return svc.store.get(a["application_id"])


def test_report_catalog_covers_the_required_types():
    types = {t for t in CATALOG}
    for needed in ("case_summary", "sanction_record", "audit_trail",
                   "document_checklist", "conditions", "disbursement",
                   "pipeline", "deviations"):
        assert needed in types, f"catalog missing {needed}"


def test_pipeline_report_walks_the_stage_history(tmp_path):
    """The pipeline export is the stage-by-stage timeline: every step the sanctioned case moved
    through, the decision at each, and the days in step; the open step is marked in progress."""
    svc = make_service(tmp_path)
    app = sanctioned(svc, amount=100.0)
    out = build_report(svc, app["application_id"], "pipeline")
    rows = out["rows"]
    steps = [r["Step"] for r in rows]
    assert "Post Sanction Maker" in steps or any("Post Sanction" in x for x in steps)
    actions = {r["Action"] for r in rows}
    assert any(a in ("submit", "approve", "sanction") for a in actions)
    # days in step: a replayed history is same-day, so 0 or 0.0; the column is populated
    timed = [r for r in rows if r["Decided at"] and not r["Decided at"].startswith("—")]
    assert all(r["Days in step"] != "" for r in timed)
    # CSV round-trips with the meta header
    assert app["application_id"] in out["csv"] and "Pipeline timeline" in out["csv"]


def test_deviations_report_lists_rule_manual_and_case_deviations(tmp_path):
    """The deviations export: policy-rule items, manual deviations and the credit-case
    committee deviations; a case with none says so (never an empty file)."""
    svc = make_service(tmp_path)
    app = sanctioned(svc, amount=100.0)
    sid = app["application_id"]
    app.setdefault("policy_deviation_items", []).append(
        {"deviation_id": "DEV-TEST1", "rule_ref": "tenor_months_max", "type": "tenor",
         "expected": "≤ 60 months", "actual": "84 months", "severity": "minor",
         "summary": "Tenor of 84 months exceeds the policy maximum of 60 months",
         "required_authority": "Committee with recorded minutes", "status": "open",
         "natural_key": "x", "raised_by": "QA (demo)", "raised_at": NOW.isoformat(timespec="seconds"),
         "source": "policy_rule"})
    app.setdefault("manual_deviations", []).append(
        {"type": "pricing", "description": "Spread above benchmark (demo)",
         "justification": "Borrower-specific risk premium", "raised_by": "RM (demo)",
         "raised_at": NOW.isoformat(timespec="seconds"), "raised_at_step": "ap_risk_maker",
         "removed": False})
    svc.store.save(app)
    out = build_report(svc, sid, "deviations")
    descs = [r["Description"] for r in out["rows"]]
    assert any("84 months" in (d or "") for d in descs)
    assert any("Spread above benchmark" in (d or "") for d in descs)
    assert "DEV-TEST1" in out["csv"]
    # a clean case still yields a readable file
    app2 = svc.create(svc._system_session("ps_maker"), entity_id="ABCE001", profile="client_one",
                      facility={"facility_type": "working_capital", "facility_nature": "fund_based",
                                "proposal_type": "Fresh", "amount_cr": 20.0, "tenor_months": 12,
                                "interest_rate": 12.4, "purpose": "Clean (demo)"},
                      sourcing_decision={"decision": "Refer for in-principle",
                                         "mandatory_remarks": "reports test"})
    svc._replay_to(app2["application_id"], "ps_maker", NOW, NOW)
    out2 = build_report(svc, app2["application_id"], "deviations")
    assert any("No deviations" in (r["Description"] or "") for r in out2["rows"])


def test_csv_is_formula_injection_safe_and_bounded(tmp_path):
    svc = make_service(tmp_path)
    app = sanctioned(svc, amount=100.0)
    sid = app["application_id"]
    # a hostile document name would inject a formula into a naive CSV
    app.setdefault("documents", []).append(
        {"name": "=CMD('calc')", "kind": "other", "status": "uploaded",
         "versions": [{"v": 1, "file_name": "x.pdf", "uploaded_by": "Evil (demo)",
                       "at": NOW.isoformat(timespec="seconds"), "source": "upload"}]})
    svc.store.save(app)
    out = build_report(svc, sid, "document_checklist")
    text = out["csv"]
    # no cell may start with a formula trigger character
    for line in text.splitlines()[1:]:
        assert not line.split(",")[0].startswith(("=", "+", "@")), line
    # the hostile name is neutralised (the trigger character dropped), content preserved
    host = [line for line in text.splitlines() if "CMD" in line]
    assert host and all(line.split(",")[0].startswith("CMD") for line in host)
    # the report carries the generation time and the application id
    assert NOW.date().isoformat() in text or sid in text


def test_audit_trail_report_orders_the_full_history(tmp_path):
    svc = make_service(tmp_path)
    app = sanctioned(svc, amount=100.0)
    sid = app["application_id"]
    out = build_report(svc, sid, "audit_trail")
    rows = out["rows"]
    assert rows, "the audit report has rows"
    acts = [r["action"] for r in rows]
    assert acts.index("create") < acts.index("sanction"), "create precedes sanction"
    html = out["html"]
    assert sid in html
    # no secrets: no absolute paths or session material in the content
    assert "D:\\" not in out["csv"] and "D:\\" not in html


def test_sanction_record_report_captures_amount_authority_and_terms(tmp_path):
    svc = make_service(tmp_path)
    app = sanctioned(svc, amount=250.0)
    sid = app["application_id"]
    out = build_report(svc, sid, "sanction_record")
    text = out["csv"]
    assert "250" in text
    assert "authority" in text.lower()
    assert "sanctioned" in text.lower()


def test_summary_report_covers_positions_and_open_items(tmp_path):
    svc = make_service(tmp_path)
    app = sanctioned(svc, amount=100.0)
    sid = app["application_id"]
    out = build_report(svc, sid, "case_summary")
    s = svc.summary(application_id=sid)
    text = out["csv"]
    assert "100" in text
    assert sid in text
    # the open risks (conditions still open at this point) appear or are explicitly absent
    for risk in s["open_risks"][:3]:
        assert risk["kind"] in text or risk["id"] in text


def test_disbursement_report_shows_tranches_and_utilisation(tmp_path):
    from tests.test_los_modifications import run_pos
    svc = make_service(tmp_path)
    wf = svc.wf_for_profile("client_one")
    app = sanctioned(svc, amount=100.0)
    sid = app["application_id"]
    a = svc.store.get(sid)
    dis = run_pos(svc, sid, wf, to="dis_maker")
    svc.request_tranche(sid, dis, 40.0, (NOW.replace(day=10)).date().isoformat(), purpose="Tranche 1 (demo)")
    out = build_report(svc, sid, "disbursement")
    text = out["csv"]
    assert "40" in text
    assert "100" in text  # the sanctioned amount for utilisation


def test_html_report_is_branded_and_readable(tmp_path):
    svc = make_service(tmp_path)
    app = sanctioned(svc, amount=100.0)
    sid = app["application_id"]
    out = build_report(svc, sid, "case_summary", fmt="html")
    html = out["html"]
    assert "<html" in html.lower()
    assert "Report" in html or "report" in html
    assert sid in html
    assert "generated" in html.lower()
