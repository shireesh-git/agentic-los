"""
Institution Profile Framework (generic POC): one neutral application, many institutions.

  1. profile loading, merging and validation (base + institution file);
  2. neutral vocabulary & branding — labels, role names and branding come from the profile;
  3. configuration-driven journey — shortened / reordered / extended without new code paths;
  4. optional modules (ESMS, DMD, ES chain, CMA, consortium, committees) per profile;
  5. configurable due-diligence check catalogue — applicable set, mandatory set, exception authority;
  6. document checklists by profile and product;
  7. delegation & approval matrix by amount, grade, product and deviations;
  8. profile-based output templates (CAM, IP note, committee pack, sanction letter).

The default profile (client_one) reproduces the legacy behaviour exactly — the other
tests in this package prove that — so they run against it unchanged.
"""

from datetime import datetime
from pathlib import Path

import pytest
import yaml

from src.data.company_catalog import seed_company_store
from src.los import authority as auth_mod
from src.los import docreg as dreg
from src.los import profiles
from src.los import verification as dd
from src.los.service import LosService, load_workflow
from src.los.store import LosStore
from src.los.workflow import Workflow

NOW = datetime(2026, 10, 8, 12, 0, 0)


@pytest.fixture()
def profiles_restored():
    """Restore the runtime-active profile override after tests that switch it."""
    yield
    profiles._runtime_active = None


# ── 1. profile loading, merging and validation ──────────────────────────────

def test_profiles_are_discovered_and_base_is_neutral():
    view = profiles.profiles_view()
    assert {"base", "client_one", "client_two"} <= {p["id"] for p in view["profiles"]}
    assert view["default"] == "client_one"                      # the legacy default, unchanged
    base = profiles.get_profile("base")
    assert "Demo Bank" not in base["branding"]["institution_name"]
    assert base["profile"]["id"] == "base"


def test_profile_merges_over_base():
    p2 = profiles.get_profile("client_two")
    assert p2["branding"]["institution_name"] == "Meridian Bank Ltd — Institutional Credit"
    # base-provided sections that client_two does not override survive the merge
    assert p2["modules"]["esms"]["enabled"] is True             # ESMS stays on for client two
    assert p2["documents"]["by_stage"]["PS"]                    # base checklist inherited


def test_unknown_profile_is_rejected(profiles_restored):
    with pytest.raises(profiles.ProfileError, match="Unknown institution profile"):
        profiles.load_profile("no_such_bank")
    with pytest.raises(profiles.ProfileError):
        profiles.profile_summary("no_such_bank")


def test_invalid_profile_fails_validation(tmp_path):
    d = tmp_path / "institution_profiles"
    d.mkdir()
    base_src = Path(profiles._profile_dir()) / "base.yaml"
    (d / "base.yaml").write_text(base_src.read_text(encoding="utf-8"), encoding="utf-8")
    (d / "bad.yaml").write_text(
        "profile: {id: bad, name: Bad}\n"
        "branding: {institution_name: Bad Bank}\n"
        "checks: {applicable: [mca, not_a_check]}\n", encoding="utf-8")
    import os
    old = os.environ.get("CAM_CONFIG_DIR")
    os.environ["CAM_CONFIG_DIR"] = str(tmp_path)
    try:
        with pytest.raises(profiles.ProfileError, match="unknown check"):
            profiles.load_profile("bad")
    finally:
        if old is None:
            os.environ.pop("CAM_CONFIG_DIR", None)
        else:
            os.environ["CAM_CONFIG_DIR"] = old
        profiles._cache.clear()


# ── 2. neutral vocabulary & branding from the profile ───────────────────────

def test_branding_and_role_names_come_from_the_profile(profiles_restored):
    b1 = profiles.branding(profiles.get_profile("client_one"))
    b2 = profiles.branding(profiles.get_profile("client_two"))
    assert b1["institution_name"] == "Demo Bank Ltd — Corporate Banking Group"
    assert b1["colors"]["primary"] == "#003366"
    assert b2["institution_name"] == "Meridian Bank Ltd — Institutional Credit"
    assert b2["colors"]["primary"] == "#123c2e"

    cfg2 = profiles.workflow_config("client_two")
    assert cfg2["roles"]["crp_evp"] == "Head of Credit (EVP)"        # renamed by the profile
    assert cfg2["roles"]["dmd"] == "Executive Approval Officer"
    cfg1 = profiles.workflow_config("client_one")
    assert cfg1["roles"]["dmd"] == "Deputy Managing Director (DMD)"  # legacy wording under client one


def test_decision_field_labels_come_from_the_profile():
    l1 = profiles.decision_field_labels(profiles.get_profile("client_one"))
    l2 = profiles.decision_field_labels(profiles.get_profile("client_two"))
    assert l1["ceac_recommendation"] == "CEAC recommendation"
    assert l2["ceac_recommendation"] == "Committee recommendation"
    assert l1["committee_matters"] == "Any other matter to be highlighted to Committee"
    assert l2["committee_matters"] == "Matters for the committee's attention"
    # every decision field has the institution's wording (neutral catalogue as the floor)
    assert set(l2) >= set(profiles.DECISION_FIELDS)


def test_stage_and_step_names_come_from_the_profile():
    cfg2 = profiles.workflow_config("client_two")
    stages = {st["id"]: st["name"] for st in cfg2["stages"]}
    assert stages["IP"] == "In-Principle Assessment"                 # profile label
    assert stages["AP"] == "Application & Sanction Processing"
    step = next(s for s in cfg2["stages"] if s["id"] == "IP" for s in s["steps"] if s["id"] == "ip_note")
    assert step["name"] == "In-Principle Assessment Note"


# ── 3. configuration-driven journey (shortened without a new code path) ─────

def test_client_one_journey_is_unchanged():
    wf = Workflow.from_config(profiles.workflow_config("client_one"),
                              decision_field_labels=profiles.decision_field_labels(profiles.get_profile("client_one")))
    assert len(wf.steps) == 31
    ids = [s.id for s in wf.steps]
    assert "ap_dmd" in ids and "ap_recommend" in ids and "ap_es_prep" in ids


def test_client_two_journey_is_shortened():
    cfg = profiles.workflow_config("client_two")
    ids = [s["id"] for st in cfg["stages"] for s in st["steps"]]
    assert len(ids) == 29                                            # 31 − DMD − Recommendations Committee
    assert "ap_dmd" not in ids and "ap_recommend" not in ids
    assert "ap_sanction" in ids                                      # the final sanction stays
    # the workflow builds and transitions on the shorter journey
    wf = Workflow.from_config(cfg, decision_field_labels=profiles.decision_field_labels(profiles.get_profile("client_two")))
    assert len(wf.steps) == 29
    idx = {s.id: s.index for s in wf.steps}
    assert idx["ap_es_recommend"] + 1 == idx["ap_sanction"]          # ES now hands straight to the committee


def test_journey_can_be_reordered_or_rolled_back_in_config():
    # reorder is a plain configuration value: swap two consecutive client-two steps and validate
    cfg = profiles.workflow_config("client_two")
    ids = [s["id"] for st in cfg["stages"] for s in st["steps"]]
    i = ids.index("ap_post_rating")
    reordered = ids[:i] + [ids[i + 1], ids[i]] + ids[i + 2:]
    p2 = profiles.get_profile("client_two")
    p2["workflow"]["reorder"] = reordered
    try:
        from src.los.profiles import _validate
        _validate("client_two", p2)                      # an explicit order of the enabled steps is legal
    finally:
        p2.pop("workflow", None)


def test_load_workflow_uses_the_active_profile(profiles_restored):
    wf_default = load_workflow()
    assert "ap_dmd" in [s.id for s in wf_default.steps]
    profiles.set_active_profile("client_two")
    wf_two = load_workflow()
    assert [s.id for s in wf_two.steps if s.id in ("ap_dmd", "ap_recommend")] == []
    profiles.set_active_profile(profiles.default_profile_id())


# ── 4. optional modules per profile ─────────────────────────────────────────

def test_modules_are_configurable(profiles_restored):
    m1 = profiles.modules(profiles.get_profile("client_one"))
    assert all(m["enabled"] for m in m1.values())
    m2 = profiles.modules(profiles.get_profile("client_two"))
    assert m2["dmd"]["enabled"] is False
    assert m2["committee_recommendations"]["enabled"] is False
    assert m2["consortium"]["enabled"] is False
    assert m2["esms"]["enabled"] is True and m2["cma"]["enabled"] is True
    assert m2["dmd"]["steps"] == ["ap_dmd"]
    assert profiles.module_enabled(profiles.get_profile("client_one"), "dmd") is True
    assert profiles.module_enabled(profiles.get_profile("client_two"), "dmd") is False


def test_es_chain_can_be_switched_off_by_profile():
    # a profile turns the whole ES chain off: the steps leave the journey
    p1 = profiles.get_profile("client_one")
    saved = p1["modules"]["esms"]
    p1["modules"]["esms"] = {"enabled": False, "steps": ["ap_es_maker", "ap_es_prep", "ap_es_review", "ap_es_recommend"]}
    try:
        from src.los.profiles import _profile_disabled_steps
        disabled = _profile_disabled_steps(p1)
        assert {"ap_es_maker", "ap_es_prep", "ap_es_review", "ap_es_recommend"} <= disabled
    finally:
        p1["modules"]["esms"] = saved


# ── 5. configurable due-diligence check catalogue ───────────────────────────

def test_check_catalogue_selection_and_mandatory_flags():
    cat1 = profiles.check_catalog(profiles.get_profile("client_one"))
    assert [c["id"] for c in cat1] == [c["id"] for c in dd.CHECKS]   # the full catalogue
    assert {c["id"] for c in cat1 if c["mandatory"]} == {"mca", "crilc", "kyc", "name_screening", "mlra"}

    cat2 = profiles.check_catalog(profiles.get_profile("client_two"))
    assert [c["id"] for c in cat2] == ["mca", "crilc", "litigation", "ews", "gstin", "lei", "kyc", "name_screening", "mlra"]
    assert {c["id"] for c in cat2 if c["mandatory"]} == {"mca", "crilc", "kyc", "name_screening", "mlra"}
    assert next(c for c in cat2 if c["id"] == "name_screening")["name"] == "PEP / sanctions screening"


def test_exception_authority_comes_from_the_profile():
    e1 = profiles.exception_authority(profiles.get_profile("client_one"))
    e2 = profiles.exception_authority(profiles.get_profile("client_two"))
    assert e1 == {"role": "compliance_vp", "name": "Compliance VP"}
    assert e2["role"] == "compliance_vp" and e2["name"] == "Compliance & Regulatory Officer"


def test_check_policy_comes_from_the_profile():
    pol2 = profiles.check_policy(profiles.get_profile("client_two"))
    assert (pol2["rescreen_days"], pol2["exception_ttl_days"]) == (60, 60)
    # the screening review honours the profile's clock
    check = {"id": "name_screening", "name": "x", "status": "clear",
             "last_triggered": NOW.replace(day=1).isoformat()}
    st60 = dd.rescreen_state(check, NOW.replace(day=10, hour=0), rescreen_days=60)
    st90 = dd.rescreen_state(check, NOW.replace(day=10, hour=0), rescreen_days=90)
    assert st60["state"] == "current" and st90["state"] == "current"
    st60_late = dd.rescreen_state(check, NOW.replace(month=12, day=5), rescreen_days=60)
    assert st60_late["state"] == "overdue"


def test_initial_checks_follow_the_profile_catalogue():
    init2 = dd.initial_checks(profiles.check_catalog(profiles.get_profile("client_two")))
    assert [c["id"] for c in init2] == ["mca", "crilc", "litigation", "ews", "gstin", "lei", "kyc", "name_screening", "mlra"]
    assert all(c["status"] == "pending" for c in init2)


# ── 6. document checklists by profile and product ───────────────────────────

def test_document_checklist_by_profile():
    base = {n for n, _ in dreg.CHECKLIST["POS"]}
    c2 = profiles.document_checklist(profiles.get_profile("client_two"))
    assert "Insurance policy (with bank clause)" not in {e["name"] for e in c2["POS"]}
    assert "Tax clearance certificate" in {e["name"] for e in c2["AP"]}
    # client one keeps the documented base checklist
    c1 = profiles.document_checklist(profiles.get_profile("client_one"))
    assert {e["name"] for e in c1["POS"]} == base


def test_document_checklist_by_product():
    p2 = profiles.get_profile("client_two")
    pf = profiles.product_checklist(p2, "project_finance")
    assert "Project appraisal report" in {e["name"] for e in pf["AP"]}
    assert "Technology evaluation report" in {e["name"] for e in pf["AP"]}
    wc = profiles.product_checklist(p2, "working_capital")
    assert "Project appraisal report" not in {e["name"] for e in wc["AP"]}


def test_required_documents_evaluates_conditions_and_product():
    app = {"stage_id": "AP", "securities": [{"id": 1}], "projects": [],
           "facilities": [{"facility_type": "project_finance"}]}
    names = profiles.required_documents(app, profiles.get_profile("client_two"))
    assert "CMA (prepared in the CMA workspace)" in names
    assert "Valuation report for the proposed security" in names
    assert "TEV report (where project finance is proposed)" not in names       # no projects
    assert "Project appraisal report" in names                                 # product add
    no_sec = dict(app, securities=[])
    assert "Valuation report for the proposed security" not in profiles.required_documents(no_sec, profiles.get_profile("client_two"))


def test_stage_gate_uses_the_application_profile():
    app = {"stage_id": "PS", "securities": [], "projects": [], "facilities": [{"facility_type": "working_capital"}],
           "profile": "client_two",
           "documents": dreg.initial_registry(profiles.product_checklist(
               profiles.get_profile("client_two"), "working_capital"))}
    gate = dreg.stage_gate(app)
    assert gate and "KYC evidence" in gate                                    # nothing reviewed yet
    for d in app["documents"]:
        d["versions"].append({"v": 1, "file_name": "x.pdf", "uploaded_by": "t", "at": "2026-10-01", "source": "upload"})
        d["status"] = "reviewed"
    assert dreg.stage_gate(app) is None


# ── 7. delegation & approval matrix ─────────────────────────────────────────

def test_authority_matrix_by_amount_grade_and_deviations():
    r = auth_mod.required_authority(50, "B", 2, final=True, app={"facilities": [{"facility_type": "working_capital"}], "profile": "client_one"})
    assert r["required"] == "Credit Sanction Committee (sub-investment-grade reviewer concurrence) " \
                            "(with 2 recorded policy deviation(s) and minutes)"
    r_big = auth_mod.required_authority(800, "AA", 0, final=True, app={"facilities": [{"facility_type": "working_capital"}]})
    assert r_big["required"] == "Credit Sanction Committee with executive credit note and board intimation"
    r_pre = auth_mod.required_authority(250, "AAA", 0, final=False, app={"facilities": [{"facility_type": "working_capital"}]})
    assert r_pre["required"] == "IP Sanction Committee (preliminary) with EVP note"


def test_authority_matrix_by_profile():
    app = {"facilities": [{"facility_type": "working_capital"}], "profile": "client_two"}
    r = auth_mod.required_authority(200, "AA", 0, final=True, app=app)
    assert r["required"] == "Credit Committee with executive note"   # client two's own matrix (150/400 bands)
    r_small = auth_mod.required_authority(50, "AA", 0, final=True, app=app)
    assert r_small["required"] == "Credit Committee"


def test_authority_matrix_by_product():
    app = {"facilities": [{"facility_type": "project_finance"}], "profile": "client_two"}
    r = auth_mod.required_authority(100, "AA", 0, final=True, app=app)
    assert r["required"] == "Project Finance Committee with executive note"   # product route wins (75/250 bands)
    r1 = auth_mod.required_authority(100, "AA", 0, final=True, app={"facilities": [{"facility_type": "project_finance"}],
                                                                    "profile": "client_one"})
    assert r1["required"].startswith("Credit Sanction Committee")             # no product route under client one


def test_matrix_validation_rejects_unordered_rows(tmp_path):
    d = tmp_path / "institution_profiles"
    d.mkdir()
    (d / "base.yaml").write_text(
        (Path(__file__).resolve().parents[1] / "config" / "institution_profiles" / "base.yaml").read_text(encoding="utf-8"),
        encoding="utf-8")
    (d / "bad.yaml").write_text(
        "profile: {id: bad, name: Bad}\n"
        "branding: {institution_name: Bad Bank}\n"
        "approval:\n  final:\n    - {max_amount: 500, authority: B}\n    - {max_amount: 100, authority: A}\n",
        encoding="utf-8")
    import os
    old = os.environ.get("CAM_CONFIG_DIR")
    os.environ["CAM_CONFIG_DIR"] = str(tmp_path)
    profiles._cache.clear()
    try:
        with pytest.raises(profiles.ProfileError, match="ordered from lowest to highest"):
            profiles.load_profile("bad")
    finally:
        if old is None:
            os.environ.pop("CAM_CONFIG_DIR", None)
        else:
            os.environ["CAM_CONFIG_DIR"] = old
        profiles._cache.clear()


# ── 8. profile-based output templates ───────────────────────────────────────

def test_letter_templates_come_from_the_profile():
    lb1 = profiles.letter_branding(profiles.get_profile("client_one"))
    lb2 = profiles.letter_branding(profiles.get_profile("client_two"))
    assert lb1["institution_name"] == "Demo Bank Ltd — Corporate Banking Group"
    assert lb1["acceptance_days"] == 30
    assert lb1["kind_titles"]["sanction_letter"] == "Sanction letter"
    assert lb1["bank_term"] == "the Bank"
    assert lb2["kind_titles"]["sanction_letter"] == "Letter of Sanction"
    assert lb2["acceptance_days"] == 15
    assert lb2["bank_term"] == "the Institution"
    assert "Meridian" in lb2["demo_mark"]


def test_ip_note_title_comes_from_the_profile():
    t1 = profiles.output_template("ip_note", profiles.get_profile("client_one"))["title_prefix"]
    t2 = profiles.output_template("ip_note", profiles.get_profile("client_two"))["title_prefix"]
    assert t1 == "In-Principle Note"
    assert t2 == "In-Principle Assessment Note"


def test_cam_and_committee_pack_templates():
    cam2 = profiles.output_template("cam", profiles.get_profile("client_two"))
    pack2 = profiles.output_template("committee_pack", profiles.get_profile("client_two"))
    assert cam2["title"] == "Credit Assessment Memorandum"
    assert pack2["title"] == "Committee Submission Pack"


def test_letter_build_uses_the_application_profile():
    from src.los import letters as lt
    doc = lt.build_letter(
        "sanction_letter",
        {"application_id": "LOS-T-001", "profile": "client_two",
         "sanctions": {"AP": {"at": "2026-10-01T10:00:00", "by_name": "Committee", "sanctioned_cr": 50.0,
                              "facility": {"facility_type": "term_loan", "tenor_months": 24}}},
         "conditions": [], "credit_assessment": {"risk_grade": "B"}},
        {"borrower": type("B", (), {"company_name": "Acme Ltd", "cin": "U1234KA2020PTC000001", "pan": "AABCA1234A",
                                    "registered_address": "Mumbai"})()},
        None, [], {}, "Post Sanction Maker", NOW, 1)
    assert doc["bank"] == "Meridian Bank Ltd — Institutional Credit"
    assert doc["title"] == "Letter of Sanction"
    from datetime import timedelta
    assert doc["valid_until"] == (NOW + timedelta(days=15)).date().isoformat()   # profile's 15-day acceptance
    md = lt.render_markdown(doc)
    assert "For Meridian Bank Ltd — Institutional Credit" in md
    assert "Meridian Bank demonstration" in md                          # the profile's demo mark
    assert "CAM Report" not in md


# ── end-to-end: a service running under the client two profile ──────────────

def test_service_runs_under_a_non_default_profile(profiles_restored, tmp_path):
    profiles.set_active_profile("client_two")
    svc = LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow, seed_company_store(),
                     clock=lambda: NOW)
    # the sign-in directory carries the profile's branding and role names
    directory = svc.directory()
    assert directory["branding"]["short_name"] == "Meridian Bank"
    assert directory["profile"]["id"] == "client_two"
    assert directory["roles"]["crp_evp"] == "Head of Credit (EVP)"

    # the journey the service runs on has no DMD / Recommendations Committee steps
    assert [s.id for s in svc.wf.steps if s.id in ("ap_dmd", "ap_recommend")] == []

    # an application created now runs under client two: its checks and documents follow the profile
    session = svc.sign_in("u_rm1", "ps_maker")
    app = svc.create(session, entity_id="ABCE001",
                     facilities=[{"facility_type": "project_finance", "amount_cr": 100.0,
                                  "tenor_months": 36, "purpose": "capex"}],
                     sourcing_decision={"decision": "Refer for in-principle", "mandatory_remarks": "strong account",
                                        "conditional_remarks": "none"})
    got = svc.get(app["application_id"], session)
    assert got["profile"] == "client_two"
    check_ids = [c["id"] for c in got["due_diligence"]["checks"]]
    assert "crif" not in check_ids and "udin" not in check_ids                 # client two's slimmer catalogue
    doc_names = {d["name"] for d in got["documents"]}
    assert "Tax clearance certificate" in doc_names
    assert "Project appraisal report" in doc_names
    assert "Insurance policy (with bank clause)" not in doc_names              # removed by the profile

    # the committee routing for this product follows the profile's matrix
    svc2_view = svc.decision_view(app["application_id"], session)
    assert "Project Finance Committee" in svc2_view["committee"]["required"]

    # switching back leaves the existing application under its own profile
    profiles.set_active_profile(profiles.default_profile_id())
    assert svc.get(app["application_id"], session)["profile"] == "client_two"
    profiles.set_active_profile("client_two")


def test_create_with_an_explicit_profile_and_unknown_profile(profiles_restored, tmp_path):
    svc = LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow, seed_company_store(), clock=lambda: NOW)
    session = svc.sign_in("u_rm1", "ps_maker")
    body = dict(sourcing_decision={"decision": "Refer for in-principle", "mandatory_remarks": "ok",
                                   "conditional_remarks": "none"})
    app = svc.create(session, entity_id="ABCE001", profile="client_two",
                     facilities=[{"facility_type": "working_capital", "amount_cr": 20.0, "tenor_months": 12}],
                     **body)
    assert svc.get(app["application_id"], session)["profile"] == "client_two"
    from src.application.errors import NotFoundError
    with pytest.raises(NotFoundError, match="Unknown institution profile 'ghost_bank'"):
        svc.create(session, entity_id="ABCE001", profile="ghost_bank",
                   facilities=[{"facility_type": "working_capital", "amount_cr": 20.0, "tenor_months": 12}],
                   **body)
    # the failed create left no application behind
    assert not [a for a in svc.list() if a["entity_id"] == "ABCE001" and a.get("sourcing", {})
                and a["sourcing"].get("sourcing_decision", {}).get("mandatory_remarks") == "ok"
                and a["profile"] == "ghost_bank"]


def test_api_surface_for_profiles():
    """The profile API endpoints resolve, list, detail and switch profiles."""
    view = profiles.profiles_view()
    assert view["active"] and all(p["id"] for p in view["profiles"])
    detail = profiles.profile_summary("client_two", full=True)
    assert detail["branding"]["short_name"] == "Meridian Bank"
    assert detail["checks"]["exception_authority"]["name"] == "Compliance & Regulatory Officer"
    assert "ap_dmd" not in [s["id"] for st in detail["workflow"]["stages"] for s in st["steps"]]
    assert detail["approval"]["final"][0]["max_amount"] == 150
    with pytest.raises(profiles.ProfileError):
        profiles.profile_summary("ghost_bank")
