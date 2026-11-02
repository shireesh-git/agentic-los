"""
Reusable product templates, the three demo institution profiles, the administrator page
and the guided demo scenarios.

  * product templates (config/product_templates/*.yaml): config, not code — fields, amount /
    tenor gates, checks, documents, workflow modules, approval route and output templates;
  * two-sided compatibility between a product and the institution profile that runs it;
  * per-application product + profile: each application keeps both for its whole life;
  * the three demo profiles (DFI / corporate bank / NBFC-MSME) with deterministic seeded
    demo applications (one success, one exception) each;
  * administration: administrator-only profile switching and controlled demo-data resets,
    all audit-logged;
  * guided demo scenarios for the portal walkthrough.
"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from src.application.errors import ForbiddenError, InvalidRequestError, NotFoundError
from src.data.company_catalog import seed_company_store
from src.los import authority, profiles, products as prodmod
from src.los.service import LosService, load_workflow
from src.los.store import LosStore

NOW = datetime(2026, 10, 8, 12, 0, 0)


@pytest.fixture()
def profiles_restored():
    yield
    profiles._runtime_active = None


@pytest.fixture()
def svc(tmp_path, profiles_restored):
    return LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow, seed_company_store(),
                      clock=lambda: NOW)


def make_session(svc, user_id="u_rm1", role="ps_maker"):
    return svc.sign_in(user_id, role)


def new_app(svc, session, entity_id, facilities, **kw):
    body = dict(sourcing_decision={"decision": "Refer for in-principle",
                                   "mandatory_remarks": "test", "conditional_remarks": "none"})
    body.update(kw)
    return svc.create(session, entity_id=entity_id, facilities=facilities, **body)


# ── 1. product templates: loading, validation, compatibility ─────────────────

def test_all_four_product_templates_load():
    ids = prodmod.list_product_ids()
    assert ids == ["msme_loan", "project_finance", "term_loan", "working_capital"]
    for pid in ids:
        p = prodmod.get_product(pid)
        assert p["product"]["id"] == pid
        assert p["product"]["name"] and p["product"]["category"]


def test_unknown_product_template_is_rejected():
    with pytest.raises(prodmod.ProductError) as e:
        prodmod.get_product("credit_line")
    assert "term_loan" in str(e.value)                      # the error lists what exists


def test_product_profile_compatibility_is_two_sided():
    corporate = profiles.get_profile("corporate")
    msme = profiles.get_profile("msme_lender")
    assert prodmod.is_compatible(prodmod.get_product("msme_loan"), msme)
    assert not prodmod.is_compatible(prodmod.get_product("msme_loan"), corporate)
    assert prodmod.profile_products(msme) == ["msme_loan"]
    assert "msme_loan" not in prodmod.profile_products(corporate)
    # profiles without a fixed product set run every product
    assert "msme_loan" in prodmod.profile_products(profiles.get_profile("client_one"))


def test_resolve_product_combines_profile_and_product():
    msme = profiles.get_profile("msme_lender")
    r = prodmod.resolve_product("msme_loan", msme)
    assert r["amount"] == {"min_cr": 0.25, "max_cr": 50, "currency": "₹ Cr"}
    check_ids = {c["id"] for c in r["checks"]}
    assert {"gstin", "cibil", "name_screening"} <= check_ids
    assert "CMA (prepared in the CMA workspace)" not in r["documents"]["AP"]
    assert "GST summary (last 12 months)" in r["documents"]["AP"]
    assert any("MSME Credit Committee" in a for _, a in r["approval"]["final"])
    with pytest.raises(InvalidRequestError):
        prodmod.resolve_product("msme_loan", profiles.get_profile("corporate"))


# ── 2. product gates at creation ──────────────────────────────────────────────

def test_product_template_gates_reject_out_of_policy_facilities(svc):
    s = make_session(svc)
    wc = prodmod.get_product("working_capital")
    with pytest.raises(InvalidRequestError) as e:
        svc.create(s, entity_id="BLUE001", product="working_capital",
                   facilities=[{"facility_type": "cash_credit", "amount_cr": 90,
                                "tenor_months": 60, "purpose": "test"}],
                   sourcing_decision={"decision": "Refer for in-principle", "mandatory_remarks": "x"})
    assert "at most 24 months" in str(e.value)
    with pytest.raises(InvalidRequestError) as e:
        prodmod.validate_creation(wc, [{"facility_type": "term_loan", "amount_cr": 90,
                                        "tenor_months": 12, "purpose": "x"}])
    assert "not a" in str(e.value) and "Working Capital" in str(e.value)
    with pytest.raises(InvalidRequestError) as e:
        prodmod.validate_creation(wc, [{"facility_type": "cash_credit", "amount_cr": 0.5,
                                        "tenor_months": 12, "purpose": "x",
                                        "facility_nature": "fund_based"}])
    assert "minimum" in str(e.value)
    with pytest.raises(InvalidRequestError):
        prodmod.validate_creation(wc, [{"facility_type": "cash_credit", "amount_cr": 90,
                                        "tenor_months": 12, "purpose": "   "}])
    # the corrected proposal passes
    prodmod.validate_creation(wc, [{"facility_type": "cash_credit", "amount_cr": 90,
                                    "tenor_months": 12, "purpose": "test",
                                    "facility_nature": "fund_based"}])


def test_product_inferred_from_facility_types_when_profile_runs_products(svc):
    profiles.set_active_profile("dfi")
    s = make_session(svc)
    app = new_app(svc, s, "KAVG001",
                  [{"facility_type": "project_finance", "amount_cr": 650, "tenor_months": 96,
                    "purpose": "300 MW solar plant"}])
    assert app["product"] == "project_finance"
    assert app["profile"] == "dfi"


def test_legacy_profile_applies_no_product_gates(svc):
    s = make_session(svc)
    app = new_app(svc, s, "ABCE001",
                  [{"facility_type": "working_capital", "amount_cr": 200, "tenor_months": 12,
                    "purpose": "test"}])
    assert app["product"] is None                           # client_one: no fixed product set
    assert app["profile"] == "client_one"


def test_explicit_product_must_be_compatible(svc):
    s = make_session(svc)
    with pytest.raises(InvalidRequestError):
        new_app(svc, s, "BLUE001",
                [{"facility_type": "cash_credit", "amount_cr": 90, "tenor_months": 12,
                  "purpose": "test"}], product="msme_loan")


def test_unknown_product_id_is_a_client_error(svc):
    s = make_session(svc)
    with pytest.raises(NotFoundError):
        new_app(svc, s, "BLUE001",
                [{"facility_type": "cash_credit", "amount_cr": 90, "tenor_months": 12,
                  "purpose": "test"}], product="credit_line")


# ── 3. the application keeps its product and profile for life ─────────────────

def test_applications_keep_their_profile_and_product_after_a_switch(svc):
    profiles.set_active_profile("dfi")
    s = make_session(svc)
    app = new_app(svc, s, "KAVG001",
                  [{"facility_type": "project_finance", "amount_cr": 650, "tenor_months": 96,
                    "purpose": "solar"}])
    profiles.set_active_profile("corporate")               # a later switch…
    got = svc.store.get(app["application_id"])
    assert got["profile"] == "dfi" and got["product"] == "project_finance"
    # …and the journey / checks of the stored profile still govern it
    svc._wf(app).step(app["step_id"])
    assert svc._profile(app)["profile"]["id"] == "dfi"
    # the product's document checklist still drives the registry
    names = [d["name"] for d in got["documents"]]
    assert "Indicative project cost statement" in names


def test_product_authority_overrides_the_profile_matrix(svc):
    profiles.set_active_profile("dfi")
    s = make_session(svc)
    app = new_app(svc, s, "KAVG001",
                  [{"facility_type": "project_finance", "amount_cr": 650, "tenor_months": 96,
                    "purpose": "solar"}])
    r = authority.required_authority(app["amount_cr"], None, app=app)
    assert r["required"] == "Project Sanction Committee (preliminary) with EVP note"
    assert "product template" in r["basis"]
    # a term loan under the same profile uses the profile's matrix instead
    app2 = new_app(svc, s, "SAPT001",
                   [{"facility_type": "term_loan", "amount_cr": 120, "tenor_months": 60,
                     "purpose": "rolling stock"}])
    r2 = authority.required_authority(app2["amount_cr"], None, app=app2)
    assert r2["required"] == "Project Sanctioning Committee (preliminary)"


def test_product_documents_and_checks_apply_to_the_application(svc):
    profiles.set_active_profile("msme_lender")
    s = make_session(svc)
    app = new_app(svc, s, "KARI001",
                  [{"facility_type": "term_loan", "amount_cr": 12, "tenor_months": 36,
                    "purpose": "capacity expansion"}])
    assert app["product"] == "msme_loan"
    names = [d["name"] for d in app["documents"]]
    assert "CMA (prepared in the CMA workspace)" not in names
    assert "GST summary (last 12 months)" in names
    assert "Bank statements (last 6 months)" in names
    ids = {c["id"] for c in app["due_diligence"]["checks"]}
    assert {"gstin", "cibil", "name_screening"} <= ids


# ── 4. the three demo institution profiles and their seeded demos ─────────────

DEMO_PROFILES = {
    "dfi":        [("KAVG001", "ap_risk_maker", "project_finance"), ("SAPT001", "ip_note", "term_loan")],
    "corporate":  [
        ("APOL001", "ps_maker", "term_loan"),
        ("BLUE001", "ip_note", "working_capital"),
        ("INFY001", "ip_risk_maker", "term_loan"),
        ("SAPT001", "ip_sanction", "term_loan"),
        ("KAVG001", "ap_risk_maker", "term_loan"),
        ("IHCL001", "ap_recommend", "term_loan"),
        ("ABCE001", "ap_es_maker", "term_loan"),
        ("DECC001", "ap_dmd", "term_loan"),
        ("MFL001", "ap_sanction", "term_loan"),
        ("MRF001", "pos_maker", "term_loan"),
        ("PNCR001", "pos_checker", "term_loan"),
        ("KARI001", "dis_maker", "term_loan"),
    ],
    "msme_lender": [("KARI001", "ap_risk_maker", "msme_loan"), ("NIRM001", "ip_note", "msme_loan")],
}


@pytest.mark.parametrize("pid,expected", DEMO_PROFILES.items(), ids=list(DEMO_PROFILES))
def test_demo_profile_seeds_deterministic_applications(svc, pid, expected):
    n = svc.seed_profile_apps(pid, force=True)
    assert n == len(expected)
    apps = {a["entity_id"]: a for a in svc.store.list() if a.get("profile") == pid}
    assert set(apps) == {e for e, _, _ in expected}
    for entity, step_id, product in expected:
        a = apps[entity]
        assert a["step_id"] == step_id
        assert a["product"] == product
        assert a["is_demo"] is True
        assert a["borrower_name"]                             # the fictional borrower is on record
    # idempotent: nothing is recreated without force
    assert svc.seed_profile_apps(pid) == 0
    # deterministic reseed: force=True replaces, same entities end up at the same steps
    svc.seed_profile_apps(pid, force=True)
    again = {a["entity_id"]: a["step_id"] for a in svc.store.list() if a.get("profile") == pid}
    assert again == {e: s for e, s, _ in expected}


def test_demo_borrowers_are_fictional():
    companies = seed_company_store()
    for eid in ("KAVG001", "SAPT001", "BLUE001", "DECC001", "KARI001", "NIRM001"):
        b = companies[eid]["borrower"]
        assert companies[eid].get("data_provider") == "fictional_demo"
        assert b.company_name and b.cin and b.pan


# ── 5. administration: guards, switching, resets, audit ───────────────────────

def test_administration_is_administrator_only(svc):
    with pytest.raises(ForbiddenError):
        svc.admin_overview(make_session(svc))                # a relationship manager
    with pytest.raises(ForbiddenError):
        svc.admin_switch_profile(make_session(svc), "dfi")
    with pytest.raises(ForbiddenError):
        svc.admin_reset_demo(make_session(svc))


def test_base_profile_cannot_be_activated(svc):
    admin = make_session(svc, "u_admin", "los_admin")
    with pytest.raises(InvalidRequestError) as e:
        svc.admin_switch_profile(admin, "base")
    assert "skeleton" in str(e.value)


def test_admin_switch_and_reseed_is_audit_logged(svc):
    admin = make_session(svc, "u_admin", "los_admin")
    r = svc.admin_switch_profile(admin, "dfi", reseed=True)
    assert r["active_profile"] == "dfi" and r["demo_applications_created"] == 2
    events = [e for e in svc.store.events() if e["action"] == "active_profile_changed"]
    assert events and events[-1]["application_id"] == "SYSTEM"
    assert events[-1]["detail"]["profile_id"] == "dfi" and events[-1]["detail"]["reseed"] is True


def test_demo_reset_removes_only_seeded_applications_and_reseeds(svc):
    admin = make_session(svc, "u_admin", "los_admin")
    svc.admin_switch_profile(admin, "dfi", reseed=True)
    rm = make_session(svc)
    user_app = new_app(svc, rm, "KAVG001",
                       [{"facility_type": "project_finance", "amount_cr": 700, "tenor_months": 90,
                         "purpose": "user-created"}])
    r = svc.admin_reset_demo(admin, "active_profile")
    assert r["removed"] == 2 and r["recreated"] == 2
    apps = svc.store.list()
    assert user_app["application_id"] in {a["application_id"] for a in apps}   # user work survives
    demos = [a for a in apps if a.get("profile") == "dfi" and a.get("is_demo")]
    assert {a["entity_id"] for a in demos} == {"KAVG001", "SAPT001"}
    with pytest.raises(InvalidRequestError):
        svc.admin_reset_demo(admin, "everything")


def test_guided_demo_scenarios_cover_the_required_six(tmp_path):
    svc = LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow, seed_company_store(),
                     clock=lambda: NOW)
    all_scen = svc.demo_scenarios(profile_id="all")["scenarios"]
    ids = {s["id"] for s in all_scen}
    assert {"dfi_project_finance", "corporate_working_capital", "nbfc_msme",
            "rework_send_back", "approval_escalation", "validation_failure_correction"} <= ids
    for s in all_scen:
        assert s["title"] and s["story"] and s["steps"]
        for st in s["steps"]:
            assert st["role"] and st["stage"] and st["action"] and st["expected"] and st["next"]
    dfi = svc.demo_scenarios(profile_id="dfi")["scenarios"]
    assert {s["id"] for s in dfi} == {"dfi_project_finance", "rework_send_back"}
    corp = svc.demo_scenarios(profile_id="corporate")["scenarios"]
    assert {s["id"] for s in corp} == {
        "corporate_working_capital", "rework_send_back", "approval_escalation",
        "validation_failure_correction", "corporate_risk_showcase",
        "corporate_preliminary_committee", "corporate_esms_showcase",
        "corporate_final_committee", "corporate_post_sanction_showcase",
        "corporate_disbursement_showcase",
    }


# ── 6. the HTTP surface ───────────────────────────────────────────────────────

@pytest.fixture()
def client(profiles_restored):
    from src.api.app import create_app
    app = create_app()
    yield TestClient(app), app.state.container
    profiles._runtime_active = None


def test_http_products_and_admin_guards(client):
    http, container = client
    r = http.get("/api/los/products")
    assert r.status_code == 200
    assert {p["id"] for p in r.json()["products"]} == {
        "msme_loan", "project_finance", "term_loan", "working_capital"}
    r = http.get("/api/los/products/project_finance")
    assert r.status_code == 200 and r.json()["name"] == "Project Finance"
    assert r.json()["approval"]["final"][-1][0] == "unlimited"      # JSON-safe open band
    r = http.get("/api/los/products/msme_loan", params={"profile_id": "corporate"})
    assert r.status_code == 400

    assert http.get("/api/los/admin/overview").status_code == 403   # not signed in
    token = http.post("/api/los/session", json={"user_id": "u_rm1", "role": "ps_maker"}).json()["token"]
    assert http.get("/api/los/admin/overview", headers={"X-LOS-Session": token}).status_code == 403
    admin = http.post("/api/los/session", json={"user_id": "u_admin", "role": "los_admin"}).json()
    H = {"X-LOS-Session": admin["token"]}
    ov = http.get("/api/los/admin/overview", headers=H)
    assert ov.status_code == 200
    assert ov.json()["active_profile"] == "client_one"
    assert [p["id"] for p in ov.json()["profiles"]] == [
        "base", "client_one", "client_two", "corporate", "dfi", "msme_lender"]
    assert ov.json()["profiles"][0]["selectable"] is False          # base is not selectable

    assert http.post("/api/los/profiles/active", json={"profile_id": "dfi"}).status_code == 403
    r = http.post("/api/los/profiles/active", headers=H, json={"profile_id": "msme_lender",
                                                               "reseed": True})
    assert r.status_code == 200 and r.json()["demo_applications_created"] == 2
    assert http.get("/api/los/branding").json()["branding"]["short_name"] == "MMF"
    scen = http.get("/api/los/demo-scenarios").json()["scenarios"]
    assert {s["id"] for s in scen} == {"nbfc_msme", "rework_send_back"}
    audit = http.get("/api/los/admin/audit", headers=H).json()["events"]
    assert any(e["action"] == "active_profile_changed" for e in audit)
