"""Governance workspaces (clientspec GAP-P0-03…P2-05): facility amount lifecycle,
approval snapshot & material changes, authority, CMA, proposal/exposure, projects,
ESMS, securities, pricing, EWP, ratings/RAROC, document registry, disbursement
operational record, mandatory rule catalog and the integration registry.
"""

from datetime import datetime, timedelta

import pytest

from src.application.errors import ConflictError, ForbiddenError, InvalidRequestError
from src.data.company_catalog import seed_company_store
from src.los.service import LosService, load_workflow
from src.los.store import LosStore
from src.services.document_store import DocumentStore

NOW = datetime(2026, 10, 8, 12, 0, 0)


@pytest.fixture()
def svc(tmp_path):
    docs_root = tmp_path / "docs"
    return LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow, seed_company_store(), clock=lambda: NOW,
                      documents_root=docs_root, doc_store=DocumentStore(docs_root))


def sign(svc, user, role):
    return svc.sign_in(user, role)


def _ps(svc, entity="MFL001", **kw):
    rm = sign(svc, "u_rm1", "ps_maker")
    kw.setdefault("sourcing_decision", {"decision": "Refer for in-principle",
                                         "mandatory_remarks": "Test — refer to in-principle"})
    return svc.create(rm, entity_id=entity, **kw)


def _ps_session(svc, app_id):
    app = svc.get(app_id)
    return sign(svc, app["assignee_id"], app["step"]["role"])


# ─── Facility amount lifecycle (GAP-P0-04) ──────────────────────────────────

def test_facility_amounts_are_distinct_lifecycle_values(svc):
    app = _ps(svc, facilities=[
        {"facility_type": "term_loan", "amount_cr": 120, "tenor_months": 36, "benchmark": "MCLR",
         "spread": 0.85, "interest_rate": 12.4, "repayment_type": "quarterly_quarters",
         "repayment_frequency": "quarterly", "moratorium_months": 6,
         "total_limit_id": "LMT-1", "fund_limit_id": "LMT-2", "next_review_date": "2027-03-31"},
        {"facility_type": "letter_of_credit", "facility_nature": "non_fund_based", "amount_cr": 30},
    ])
    a = svc.get(app["application_id"])
    assert a["amount_cr"] == 150 and len(a["facilities"]) == 2
    f1 = a["facilities"][0]
    assert f1["proposed_cr"] == 120 and f1["pricing"]["benchmark"] == "MCLR" and f1["pricing"]["spread"] == 0.85
    assert f1["repayment"]["repayment_type"] == "quarterly_quarters" and f1["next_review_date"] == "2027-03-31"
    assert a["exposure_split"] == {"total_cr": 150.0, "fund_based_cr": 120.0, "non_fund_based_cr": 30.0}
    # sanctioned / committed / executed / disbursed / balance are separate values
    for key in ("sanctioned_cr", "committed_cr", "executed_cr", "disbursed_cr", "outstanding_cr", "balance_cr"):
        assert key in f1
    assert f1["change_history"] == []
    # editing a facility is attributed in its change history
    out = svc.update_facility(app["application_id"], _ps_session(svc, app["application_id"]), "FAC-001",
                              {"amount_cr": 130})
    assert out["facilities"][0]["proposed_cr"] == 130 and out["amount_cr"] == 160
    assert any("amount_cr" in h["change"] for h in out["facilities"][0]["change_history"])


def test_facility_validation_rejects_bad_types_and_negative_amounts(svc):
    rm = sign(svc, "u_rm1", "ps_maker")
    with pytest.raises(InvalidRequestError, match="facility type"):
        svc.create(rm, entity_id="MFL001", facilities=[{"facility_type": "not_a_type", "amount_cr": 10}])
    with pytest.raises(InvalidRequestError, match="greater than zero"):
        svc.create(rm, entity_id="MFL001", facilities=[{"facility_type": "term_loan", "amount_cr": -5}])
    with pytest.raises(InvalidRequestError, match="benchmark"):
        svc.create(rm, entity_id="MFL001",
                   facilities=[{"facility_type": "term_loan", "amount_cr": 10, "benchmark": "NOPE"}])


# ─── Approval snapshot, authority & material changes (GAP-P0-11, P2-02) ─────

def test_sanction_records_authority_and_snapshot_and_material_change_blocks(svc):
    from src.los.ip_note import build_ip_note
    from tests.test_cam_composer import full_case
    from tests.test_los_risk_maker import FakeCases
    from tests.test_los_committee import BriefingFinalCam
    from tests.test_los_workflow import _clear_dd
    cases = FakeCases(full_case(seed_company_store()["ABCE001"]))
    cases.run("ABCE001", on_progress=lambda e: None)
    svc.cases, svc.final_cam = cases, BriefingFinalCam(cases)
    app = _ps(svc, "ABCE001")
    app_id = app["application_id"]
    _clear_dd(svc, app_id, sign(svc, "u_rm1", "ps_maker"))
    start = svc.wf.step(app["step_id"]).index
    for _ in range(svc.wf.step("pos_maker").index - start):
        app = svc.store.get(app_id)
        step = svc.wf.step(app["step_id"])
        session = svc._system_session(step.role, app.get("assignee_id"))
        if step.id == "ip_note":
            app["ip_note"] = build_ip_note(app, svc.companies.get(app["entity_id"]), now=svc.now()) | {"seeded": True}
            svc.store.save(app)
        if step.id in ("ip_risk_maker", "ap_risk_maker"):
            app["credit_assessment"] = svc._seed_assessment_summary(app)
            svc.store.save(app)
        if step.id == "ap_risk_maker":
            svc._seed_ap_workspace(app_id, NOW - timedelta(days=1))
        if step.id == "pos_maker":
            break
        action = {"maker": "submit", "checker": "approve", "committee": "sanction", "vp_review": "submit",
                  "allocation": "allocate"}[step.kind]
        svc.act(app_id, session, action,
                allocate_to=svc._default_assignee(step.allocates_to) if step.kind == "allocation" else None,
                sanctioned_amount_cr=(200 if step.id == "ap_sanction" else None),
                comment="Committee accepts ₹200 Cr with escrow." if step.id == "ap_sanction" else "")
    view = svc.get(app_id)
    assert set(view["snapshots"]) == {"IP", "sanction"}
    sanction = view["sanctions"]["AP"]
    assert sanction["authority"]["required"].startswith("Credit Sanction Committee")     # ₹200 Cr band
    assert "demo" in sanction["authority"]["basis"].lower()                             # labelled, not bank matrix
    # facility-wise sanction allocation: distinct sanctioned/committed values, summing to the sanction
    sanctioned = view["facilities"]
    assert sum(f["sanctioned_cr"] for f in sanctioned) == 200.0
    assert all(f["committed_cr"] == f["sanctioned_cr"] for f in sanctioned)
    assert view["material_changes"] == []
    # facilities cannot be re-cut after sanction; a governed record change is material
    maker = sign(svc, view["assignee_id"], "pos_maker")
    with pytest.raises(ConflictError, match="after sanction"):
        svc.update_facility(app_id, maker, "FAC-001", {"amount_cr": 140})
    # complete the post-sanction prerequisites so the material-change gate is the one that blocks
    svc.record_consent(app_id, maker, acknowledged_by="Director, the Borrower", consent_date="2026-10-07",
                       facilities=[{"facility_id": f["facility_id"], "execution_status": "executed",
                                    "agreement_date": "2026-10-07"} for f in svc.store.get(app_id)["facilities"]])
    from tests.test_los_post_sanction import _issue_letter
    _issue_letter(svc, app_id, maker)
    conds = [c["id"] for c in svc.store.get(app_id).get("conditions") or [] if c["id"].startswith("CP-")]
    svc.update_conditions(app_id, maker, [{"id": i, "status": "satisfied", "evidence": "verified"} for i in conds])
    svc.record_rating(app_id, maker, "internal", {"subject": "borrower", "grade": "A2", "date": "2026-10-08"})
    assert "ratings" in svc.get(app_id)["material_changes"]
    with pytest.raises(InvalidRequestError, match="Material change"):
        svc.act(app_id, maker, "submit")
    # the review (accept with remarks) releases the gate
    svc.review_material_changes(app_id, maker, "accept", "Post-sanction internal rating recorded; no amount change")
    out = svc.review_material_changes(app_id, maker, "reject", "no further change")
    assert out["material_change_gate"] is None


def test_material_change_requires_remarks(svc):
    app = _ps(svc)
    with pytest.raises(InvalidRequestError, match="Remarks are required"):
        svc.review_material_changes(app["application_id"], _ps_session(svc, app["application_id"]), "accept", "")


# ─── CMA (GAP-P0-07) ────────────────────────────────────────────────────────

def test_cma_records_rows_with_source_period_version_and_maker_checker_review(svc):
    app = _ps(svc)
    rm = _ps_session(svc, app["application_id"])
    svc.record_cma(app["application_id"], rm, "borrower",
                   {"FY2024": {"revenue": 100.0, "pat": 8.0, "pbt": 10.0, "cash_accruals": 12.0},
                    "FY2025": {"revenue": 120.0, "pat": 9.0}}, "audited")
    out = svc.get(app["application_id"])
    subj = out["cma"]["subjects"][0]
    assert subj["subject"] == "borrower" and subj["row_count"] == 6 and subj["periods"] == ["FY2024", "FY2025"]
    assert out["cma"]["review_status"] == "submitted"
    # the CMA download appears in the document registry as a generated version
    docs = svc.documents(app["application_id"])
    assert any(d["name"].startswith("CMA") and d["versions"] for d in docs["documents"])
    # reviewer approves
    svc.review_cma(app["application_id"], rm, True, "CMA reviewed")
    assert svc.get(app["application_id"])["cma"]["review_status"] == "approved"
    # a later entry re-opens the review
    svc.record_cma(app["application_id"], rm, "promoter", {"FY2025": {"revenue": 50.0}}, "provisional")
    assert svc.get(app["application_id"])["cma"]["review_status"] == "submitted"
    with pytest.raises(InvalidRequestError, match="subject"):
        svc.record_cma(app["application_id"], rm, "customer", {"FY2025": {"revenue": 1.0}})


def test_ap_risk_maker_submission_requires_the_cma(svc):
    from src.los.ip_note import build_ip_note
    from tests.test_cam_composer import full_case
    from tests.test_los_risk_maker import FakeCases
    from tests.test_los_committee import BriefingFinalCam
    from tests.test_los_workflow import _clear_dd
    cases = FakeCases(full_case(seed_company_store()["ABCE001"]))
    cases.run("ABCE001", on_progress=lambda e: None)
    svc.cases, svc.final_cam = cases, BriefingFinalCam(cases)
    app = _ps(svc, "ABCE001")
    app_id = app["application_id"]
    _clear_dd(svc, app_id, sign(svc, "u_rm1", "ps_maker"))
    # advance to ap_risk_maker without recording the CMA
    start = svc.wf.step(app["step_id"]).index
    while svc.store.get(app_id)["step_id"] != "ap_risk_maker":
        app = svc.store.get(app_id)
        step = svc.wf.step(app["step_id"])
        session = svc._system_session(step.role, app.get("assignee_id"))
        if step.id == "ip_note":
            app["ip_note"] = build_ip_note(app, svc.companies.get(app["entity_id"]), now=svc.now()) | {"seeded": True}
            svc.store.save(app)
        if step.id == "ip_risk_maker":
            app["credit_assessment"] = svc._seed_assessment_summary(app)
            svc.store.save(app)
        action = {"maker": "submit", "checker": "approve", "committee": "sanction", "vp_review": "submit",
                  "allocation": "allocate"}[step.kind]
        svc.act(app_id, session, action,
                allocate_to=svc._default_assignee(step.allocates_to) if step.kind == "allocation" else None)
    app = svc.store.get(app_id)
    step = svc.wf.step(app["step_id"])
    session = svc._system_session(step.role, app.get("assignee_id"))
    app["credit_assessment"] = svc._seed_assessment_summary(app)
    svc.store.save(app)
    with pytest.raises(InvalidRequestError, match="CMA"):
        svc.act(app_id, session, "submit")
    svc.record_cma(app_id, session, "borrower", {"FY2024": {"revenue": 100.0, "pat": 8.0}})
    with pytest.raises(InvalidRequestError, match="benchmark|spread"):
        svc.act(app_id, session, "submit")
    svc._seed_ap_workspace(app_id, NOW - timedelta(days=1))
    svc.act(app_id, session, "submit")


# ─── Proposal / exposure / banking / conduct (GAP-P0-09) ────────────────────

def test_proposal_workspace_fetches_and_hard_rules(svc):
    app = _ps(svc, "PNCR001")
    app_id = app["application_id"]
    rm = _ps_session(svc, app_id)
    # a syndication case must use a Consortium arrangement (the documented hard rule, RUL-08)
    with pytest.raises(InvalidRequestError, match="Consortium"):
        svc.update_proposal(app_id, rm, "banking", {"arrangement": "syndication", "number_of_banks": 1})
    svc.update_proposal(app_id, rm, "banking",
                        {"arrangement": "consortium", "lead_bank": "Demo Bank", "number_of_banks": 3,
                         "banks": [{"name": "Demo Bank", "share_pct": 40, "role": "lead"},
                                   {"name": "Second Bank", "share_pct": 35},
                                   {"name": "Third Bank", "share_pct": 25}]})
    out = svc.fetch_exposure(app_id, rm, "loan")
    assert out["proposal"]["exposure"]["loan"]["source"].endswith("(demo data)")
    out = svc.fetch_exposure(app_id, rm, "bond")
    assert out["proposal"]["exposure"]["bond"]["status"] == "unavailable"     # FT not connected: never fake a result
    svc.update_proposal(app_id, rm, "exposure",
                        {"sanctioned_cr": 500, "outstanding_cr": 200,
                         "norms": {"lef": 400}, "breach_alert": "Outstanding above LEF norm"})
    out = svc.get(app_id)
    assert any(r["id"] == "RUL-04" and r["status"] == "failed" for r in out["rules_failed"])
    svc.update_proposal(app_id, rm, "exposure",
                        {"breach_alert": "Outstanding above LEF norm",
                         "exception": {"description": "ETB transition", "justification": "Board-approved transition",
                                       "decided_by": "u_compvp", "decided_at": "2026-10-08"}})
    assert not any(r["id"] == "RUL-04" for r in svc.get(app_id)["rules_failed"])
    svc.update_proposal(app_id, rm, "conduct", {"rows": [
        {"month": "2026-09", "limit_cr": 100, "outstanding_cr": 90, "status": "irregular",
         "irregularity": "cheque return", "peak_irregularity_cr": 25, "instances": 2, "irregular_days": 9,
         "financial_difficulty": False, "remarks": "cleared"}]})
    assert svc.get(app_id)["proposal"]["conduct"]["rows"][0]["instances"] == 2


# ─── Projects (GAP-P1-01) ───────────────────────────────────────────────────

def test_projects_with_risk_register_and_change_flag(svc):
    app = _ps(svc, "PNCR001")
    app_id = app["application_id"]
    rm = _ps_session(svc, app_id)
    svc.save_project(app_id, rm, {"name": "Greenfield capacity expansion", "type": "greenfield",
                                  "funding_type": "Project finance", "purpose": "new line",
                                  "facility_ids": ["FAC-001"], "state": "UP",
                                  "tev": {"total_cr": 250, "consultant": "Demo Consultant", "report": "TEV-001"},
                                  "cost": {"total_cr": 240, "promoter_contribution_cr": 48},
                                  "plan": {"original_dcco": "2027-06-30"},
                                  "risks": [{"description": "delayed clearances", "level": "High",
                                             "category": "pre_construction", "allocated_party": "Promoter"}]})
    out = svc.get(app_id)
    assert out["projects"][0]["project_id"] == "PRJ-001"
    assert out["projects_status"]["high_risks"] == ["delayed clearances"]
    svc.record_project_change(app_id, rm, "PRJ-001", {"field": "dcco", "previous": "2027-06-30",
                                                       "current": "2027-12-31", "reason": "clearance delay",
                                                       "impact_on_repayment": "repayment shifts by 6 months"})
    out = svc.get(app_id)
    assert out["projects"][0]["status"] == "reappraisal_required"
    assert out["projects"][0]["changes"][0]["status"] == "flagged for reappraisal"
    with pytest.raises(InvalidRequestError, match="level"):
        svc.save_project(app_id, rm, {"name": "Second", "risks": [{"description": "x", "level": "Extreme"}]})


# ─── ESMS (GAP-P1-02) ───────────────────────────────────────────────────────

def test_esms_requires_remarks_for_yes_or_not_available_and_categories(svc):
    app = _ps(svc)
    rm = _ps_session(svc, app["application_id"])
    with pytest.raises(InvalidRequestError, match="mandatory for a 'Yes'"):
        svc.update_esms(app["application_id"], rm, {"checklist": [{"id": "es_exploration", "answer": "Yes"}]})
    out = svc.update_esms(app["application_id"], rm, {"screening_date": "2026-10-08", "category": "C",
                                                      "checklist": [
            {"id": "es_exploration", "answer": "No"}, {"id": "es_coastal", "answer": "No"},
            {"id": "es_resettlement", "answer": "Not Available", "remarks": "survey not available"},
            {"id": "es_environmental", "answer": "No"}, {"id": "es_litigation", "answer": "No"}]})
    assert out["esms_status"] == "complete"
    gate = svc.rules_view(app["application_id"])["rules"]
    assert next(r for r in gate if r["id"] == "RUL-06")["status"] in ("passed", "not_applicable")   # PS stage: evaluated from AP


# ─── Securities (GAP-P1-03) ─────────────────────────────────────────────────

def test_securities_cover_multi_facility_and_history(svc):
    app = _ps(svc, facilities=[{"facility_type": "term_loan", "amount_cr": 100},
                               {"facility_type": "cash_credit", "amount_cr": 50}])
    app_id = app["application_id"]
    rm = _ps_session(svc, app_id)
    svc.save_security(app_id, rm, {"category": "primary", "type": "land_building",
                                   "facility_ids": ["FAC-001", "FAC-002"],
                                   "proposed_value_cr": 150, "apportioned_value_cr": 150,
                                   "valuation_date": "2026-09-30", "valuation_basis": "chartered valuer",
                                   "charge_type": "first_charge", "creation_status": "created",
                                   "perfection_status": "in_progress"})
    out = svc.get(app_id)
    assert out["security_cover"] == 1.0
    svc.save_security(app_id, rm, {"security_id": "SEC-001", "apportioned_value_cr": 120})
    out = svc.get(app_id)
    assert out["security_cover"] == 0.8
    assert any("apportioned_value_cr" in h["change"] for h in out["securities"][0]["history"])
    with pytest.raises(InvalidRequestError, match="unknown facility linkage"):
        svc.save_security(app_id, rm, {"category": "collateral", "type": "guarantee", "facility_ids": ["FAC-099"]})


# ─── Pricing / fees / RAROC (GAP-P0-08, P1-04) ──────────────────────────────

def test_pricing_gate_and_raroc_staleness(svc):
    app = _ps(svc, "ABCE001", facilities=[{"facility_type": "term_loan", "amount_cr": 100, "tenor_months": 12}])
    app_id = app["application_id"]
    rm = _ps_session(svc, app_id)
    assert svc.get(app_id)["pricing_gate"]                      # no benchmark/spread yet
    svc.record_pricing(app_id, rm, {"facility_id": "FAC-001", "proposed_benchmark": "MCLR",
                                    "proposed_spread_bps": 85, "proposed_rate": 12.4,
                                    "other_banks_comparison": "Peer banks at 12.2–12.6",
                                    "justification": "grade and security support the spread"})
    assert not svc.get(app_id)["pricing_gate"]
    svc.compute_raroc(app_id, rm, "FAC-001")
    raroc = svc.get(app_id)["ratings"]
    assert raroc and "FAC-001" in (svc.store.get(app_id)["ratings"]["raroc"])
    entry = svc.store.get(app_id)["ratings"]["raroc"]["FAC-001"]
    assert entry["meets_hurdle"] in (True, False) and "demo" in entry["model"].lower()
    # a pricing change after computation makes the RAROC stale
    svc.update_facility(app_id, rm, "FAC-001", {"amount_cr": 110})
    assert svc.get(app_id)["raroc_stale"] == ["FAC-001"]
    svc.compute_raroc(app_id, rm, "FAC-001")
    assert svc.get(app_id)["raroc_stale"] == []
    svc.record_fee(app_id, rm, {"facility_id": "FAC-001", "nature": "upfront", "type": "Arrangement",
                                "scope": "facility", "amount_cr": 0.5, "milestone": "execution"})
    assert svc.get(app_id)["pricing"]["facilities"]
    svc.record_tentative_schedule(app_id, rm, {"facility_ids": ["FAC-001"], "amount_cr": 100, "tenor_months": 12,
                                               "pricing": "MCLR + 85 bps", "repayment_frequency": "quarterly",
                                               "acceptability_comments": "acceptable"})
    assert svc.get(app_id)["pricing"]["tentative_schedules"][0]["note"].startswith("Tentative")


# ─── EWP (GAP-P1-05) ────────────────────────────────────────────────────────

def test_external_work_parties(svc):
    app = _ps(svc)
    rm = _ps_session(svc, app["application_id"])
    out = svc.save_ewp(app["application_id"], rm, {"role": "LIA", "name": "Demo Legal Advisors",
                                                   "contact_number": "9810000000", "email": "lia@demo.in",
                                                   "phase": "documentation", "status": "appointed"})
    assert out["ewps"][0]["ewp_id"] == "EWP-001"
    with pytest.raises(InvalidRequestError, match="role"):
        svc.save_ewp(app["application_id"], rm, {"role": "Accountant", "name": "x"})
    with pytest.raises(InvalidRequestError, match="email"):
        svc.save_ewp(app["application_id"], rm, {"role": "LIE", "name": "x", "email": "nope"})


# ─── Ratings & CRP notes (GAP-P0-08) ────────────────────────────────────────

def test_ratings_group_and_crp_note_review(svc):
    app = _ps(svc, "IHCL001")
    app_id = app["application_id"]
    rm = _ps_session(svc, app_id)
    # the borrower's external rating is fetched from the (demo) reference data; group rating is aggregated
    ratings = svc.get(app_id)["ratings"]
    assert ratings["external_ratings"][0]["agency"] and ratings["external_ratings"][0]["prior_year"]["note"].startswith("Save Risk")
    assert ratings["group_rating"]["basis"].startswith("Worst rated entity")
    svc.record_rating(app_id, rm, "internal", {"subject": "borrower", "grade": "A2", "score": 62.5,
                                                "date": "2026-10-08"})
    svc.record_rating(app_id, rm, "adverse_event", {"trigger": "quarterly results miss", "review_date": "2026-10-08",
                                                    "downgrade_notches": 1, "revised_rating": "AA-",
                                                    "comments": "watchlisted"})
    svc.save_crp_note(app_id, rm, {"kind": "lpf_note", "title": "LPF Note — Q3", "file_name": "lpf.pdf"})
    note = svc.get(app_id)["ratings"]["crp_notes"][0]
    assert note["status"] == "uploaded"
    svc.save_crp_note(app_id, rm, {"kind": "lpf_note", "title": "LPF Note — Q3", "remarks": "consistent"}, review=True)
    assert svc.get(app_id)["ratings"]["crp_notes"][0]["status"] == "reviewed"
    with pytest.raises(InvalidRequestError, match="agency"):
        svc.record_rating(app_id, rm, "external", {"subject": "borrower", "rating": "AA"})


# ─── Document registry & gates (GAP-P0-12) ──────────────────────────────────

def test_document_registry_versions_and_stage_gate(svc):
    from src.services.document_store import DocumentStore
    app = _ps(svc)
    app_id = app["application_id"]
    rm = _ps_session(svc, app_id)
    docs = svc.documents(app_id)
    ps_docs = [d for d in docs["mandatory_now"]]
    assert ps_docs and docs["gate"]
    doc = next(d for d in docs["documents"] if d["name"].startswith("KYC"))
    with pytest.raises(InvalidRequestError, match="at least one version"):
        svc.review_document(app_id, rm, doc["doc_id"], "reviewed")
    svc.upload_document(app_id, rm, "kyc", "pan.pdf", b"%PDF-1.4 test", link_to=doc["doc_id"])
    docs = svc.documents(app_id)
    doc = next(d for d in docs["documents"] if d["doc_id"] == doc["doc_id"])
    assert doc["status"] == "uploaded" and len(doc["versions"]) == 1
    svc.review_document(app_id, rm, doc["doc_id"], "reviewed", "POI verified")
    doc = next(d for d in svc.documents(app_id)["documents"] if d["doc_id"] == doc["doc_id"])
    assert doc["status"] == "reviewed" and doc["reviewer"]
    assert "KYC" not in (svc.documents(app_id)["gate"] or "")


# ─── Disbursement operational record (GAP-P0-15) ────────────────────────────

def test_disops_memo_sop_and_cbs_security_gates(svc):
    svc.seed_demo()
    pncr = next(a for a in svc.list() if a["entity_id"] == "PNCR001")
    app_id = pncr["application_id"]
    maker = sign(svc, svc.get(app_id)["assignee_id"], "dis_maker")
    # the seeded record is complete except the memo review and two SOP items
    gate = svc.post_sanction(app_id)["disops"]["maker_gate"]
    assert gate and "Interim SOP" in gate
    with pytest.raises(InvalidRequestError, match="IFSC"):
        svc.update_disops(app_id, maker, "beneficiaries", {"rows": [
            {"facility_id": "FAC-001", "type": "borrower", "name": "X", "account_no": "1",
             "bank": "B", "ifsc": "BAD", "payment_mode": "NEFT"}]})
    svc.update_disops(app_id, maker, "sop", {"items": [
        {"id": "sop_treasury", "status": "in_compliance", "remarks": "coordinated"},
        {"id": "sop_legal", "status": "in_compliance", "remarks": "verified"}]})
    svc.generate_memo(app_id, maker)
    memo = svc.store.get(app_id)["disops"]["memo"]
    assert memo["reviewed"] is False and memo["content_hash"]
    # a change after generation invalidates the memo
    svc.update_disops(app_id, maker, "arrears", {"exists": True, "rows": [
        {"facility_id": "FAC-001", "type": "interest", "amount_cr": 1.5, "currency": "INR",
         "due_since": "2026-09-30", "remarks": "cleared with interest"}]})
    with pytest.raises(InvalidRequestError, match="regenerate"):
        svc.review_memo(app_id, maker, True, "ok")
    svc.generate_memo(app_id, maker)
    svc.review_memo(app_id, maker, True, "consistent")
    assert svc.post_sanction(app_id)["disops"]["maker_gate"] is None
    # the CBS security number gate is declared in the rule catalog
    rules = svc.rules_view(app_id)["rules"]
    assert next(r for r in rules if r["id"] == "RUL-12")["status"] == "passed"


def test_dis_review_checklists_gate_checker_and_final_approver(svc):
    svc.seed_demo()
    pncr = next(a for a in svc.list() if a["entity_id"] == "PNCR001")
    app_id = pncr["application_id"]
    maker = sign(svc, svc.get(app_id)["assignee_id"], "dis_maker")
    svc.update_disops(app_id, maker, "sop", {"items": [
        {"id": "sop_treasury", "status": "in_compliance", "remarks": "coordinated"},
        {"id": "sop_legal", "status": "in_compliance", "remarks": "verified"}]})
    svc.generate_memo(app_id, maker)
    svc.review_memo(app_id, maker, True, "consistent")
    svc.request_tranche(app_id, maker, 10, "2026-10-10")
    manual = [i["id"] for i in svc.post_sanction(app_id)["disbursement"]["checklist"] if i["kind"] == "manual"]
    svc.update_checklist(app_id, maker, [{"id": i, "done": True} for i in manual])
    svc.act(app_id, maker, "submit")
    checker = sign(svc, svc.get(app_id)["assignee_id"], "dis_checker")
    with pytest.raises(InvalidRequestError, match="review is not complete"):
        svc.act(app_id, checker, "approve", comment="checking")
    svc.update_dis_review(app_id, checker, "checker",
                          [f"R-{i:02d}" for i in range(1, 12)])
    svc.act(app_id, checker, "approve", comment="complete and accurate")
    with pytest.raises(ForbiddenError):
        svc.update_dis_review(app_id, checker, "final", [])


# ─── Mandatory rule catalog & integrations (GAP-P2-01, P0-17) ───────────────

def test_rule_catalog_and_integration_registry(svc):
    svc.seed_demo()
    ihcl = next(a for a in svc.list() if a["entity_id"] == "IHCL001")
    rules = svc.rules_view(ihcl["application_id"])
    ids = {r["id"] for r in rules["rules"]}
    assert {"RUL-01", "RUL-02", "RUL-05", "RUL-10", "RUL-13", "RUL-14", "RUL-17"} <= ids
    assert all(r["severity"] == "block" for r in rules["rules"] if r["id"] in ("RUL-12", "RUL-13", "RUL-14"))
    assert any("PAN" in d["trigger"] for d in rules["dependencies"])
    integ = svc.integrations()
    by_key = {a["key"]: a for a in integ["adapters"]}
    assert by_key["cbs"]["state"] == "demo_data" and by_key["cbs"]["production_connected"] is False
    assert by_key["ft"]["state"] == "not_connected"
    assert "demo" in by_key["cbs"]["label"].lower() or "demo" in integ["note"].lower()


def test_pan_change_invalidates_identity_and_dependent_checks(svc):
    app = _ps(svc, "IHCL001")
    app_id = app["application_id"]
    rm = _ps_session(svc, app_id)
    svc.save_party(app_id, rm, {"name": "Promoter One", "role": "promoter", "pan": "ABCDE1234F"})
    svc.record_check(app_id, rm, "kyc", "clear", "POI/POA verified")
    out = svc.save_party(app_id, rm, {"party_id": "RP-001", "name": "Promoter One", "role": "promoter",
                                      "pan": "ABCDE9999F"})
    kyc = next(c for c in svc.store.get(app_id)["due_diligence"]["checks"] if c["id"] == "kyc")
    assert kyc["status"] == "pending" and kyc["invalidated_reason"].startswith("PAN changed")
    assert any("PAN" in e.get("comment") for e in out["events"][:1])
