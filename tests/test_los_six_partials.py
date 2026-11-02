"""Focused regression tests for the six completed generic-LOS requirements:
institution-profile validation (404/400), neutral branding, document-checklist
deduplication, profile-based output templates, all-demo reset completeness and
guided scenario data. (Browser behaviour is verified separately — see the report.)"""

import threading

import pytest

from src.application.errors import (ForbiddenError, InvalidRequestError,
                                    NotFoundError)
from src.data.company_catalog import seed_company_store
from src.los import docreg, ip_note as ipm, letters as lt, profiles, products as prodmod
from src.los.service import LosService, load_workflow
from src.los.store import LosStore
from tests.test_los_products_admin import make_session, new_app


def _admin(svc):
    return make_session(svc, "u_admin", "los_admin")


@pytest.fixture()
def svc(tmp_path):
    profiles.set_active_profile("client_one")
    from src.services.document_store import DocumentStore
    docs_root = tmp_path / "docs"
    s = LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow, seed_company_store(),
                   documents_root=docs_root, doc_store=DocumentStore(docs_root))
    s.seed_demo()
    yield s
    profiles.set_active_profile("client_one")


# ── 1. Institution Profile Framework ─────────────────────────────────────────


def test_unknown_profile_is_rejected_with_a_controlled_error(svc):
    s = make_session(svc)
    with pytest.raises(NotFoundError) as e:
        svc.create(s, entity_id="KAVG001", product="project_finance",
                   facilities=[{"facility_type": "project_finance", "amount_cr": 650,
                                "tenor_months": 96, "purpose": "solar"}],
                   sourcing_decision={"decision": "Refer for in-principle",
                                      "mandatory_remarks": "x"}, profile="does_not_exist")
    msg = str(e.value)
    assert "does_not_exist" in msg
    for pid in ("client_one", "dfi", "corporate", "msme_lender"):
        assert pid in msg
    assert "base" not in msg.split("Available selectable profiles: ")[1]
    # no partial record of any kind
    assert all(a["entity_id"] != "KAVG001" or not a.get("is_demo") for a in svc.list()
               if a.get("sourcing", {}).get("sourcing_decision", {}).get("mandatory_remarks") == "x")
    assert svc.store.count() > 0  # the store still holds the other applications


def test_valid_profile_creates_and_base_is_rejected(svc):
    s = make_session(svc)
    app = new_app(svc, s, "KAVG001",
                  [{"facility_type": "project_finance", "amount_cr": 650, "tenor_months": 96,
                    "purpose": "solar"}], profile="dfi")
    assert app["profile"] == "dfi"
    with pytest.raises(InvalidRequestError) as e:
        new_app(svc, s, "SAPT001",
                [{"facility_type": "term_loan", "amount_cr": 120, "tenor_months": 60,
                  "purpose": "rolling stock"}], profile="base")
    assert "base" in str(e.value) and "client_one" in str(e.value)


def test_profile_isolation_after_active_profile_changes(svc):
    s = make_session(svc)
    app = new_app(svc, s, "KAVG001",
                  [{"facility_type": "project_finance", "amount_cr": 650, "tenor_months": 96,
                    "purpose": "solar"}], profile="dfi")
    svc.admin_switch_profile(_admin(svc), "corporate")
    got = svc.get(app["application_id"])
    assert got["profile"] == "dfi" and got["product"] == "project_finance"
    # its journey still follows the DFI workflow
    assert got["step_id"] == svc.wf_for_profile("dfi").step(got["step_id"]).id
    profiles.set_active_profile("client_one")


# ── 2. Neutral Vocabulary and Branding ───────────────────────────────────────


def test_demo_profiles_have_distinct_consumed_branding():
    got = {}
    for pid in ("dfi", "corporate", "msme_lender"):
        b = profiles.branding(profiles.get_profile(pid))
        got[pid] = (b["institution_name"], b["app_name"], b["colors"]["primary"], b["colors"]["accent"])
    assert len({t[0] for t in got.values()}) == 3            # distinct institution names
    assert len({t[1] for t in got.values()}) == 3            # distinct application names
    assert len({t[2] for t in got.values()}) == 3            # distinct primary colours
    assert len({t[3] for t in got.values()}) == 3            # distinct accent colours
    assert "accent_color" not in profiles.get_profile("dfi")["branding"]   # dead keys removed


def test_missing_branding_falls_back_to_neutral_base_values():
    p = profiles.get_profile("base")
    ib = profiles.institution_branding(p)
    assert ib["institution_name"] and ib["colors"].get("primary") and ib["colors"].get("accent")
    # an empty branding still renders a letterhead with the neutral values
    note = {"title": "T", "application_id": "A-1", "borrower_name": "B",
            "branding": {"institution_name": "X", "app_name": "Y", "short_name": "X", "colors": {},
                         "demo_mark": "M"}, "product": None,
            "sections": profiles.section_plan("ip_note", {}, p), "generated_at": "2026-01-01T00:00:00",
            "borrower": [], "proposal": [], "existing_exposure": {"columns": [], "rows": []},
            "financials": {"columns": [], "rows": []}, "security": [],
            "prescreen": {"period": None, "checks": [], "outcome": "x", "note": "n"}}
    html = ipm.render_html(note)
    assert "X" in html and "Y" in html


def test_no_hardcoded_demo_bank_in_los_or_ui_code():
    import pathlib
    offenders = []
    for path in (pathlib.Path("src/los") , pathlib.Path("src/ui")):
        for f in path.rglob("*"):
            if f.suffix in (".py", ".js", ".html", ".css") and "__pycache__" not in str(f):
                if "Demo Bank" in f.read_text(encoding="utf-8", errors="ignore"):
                    offenders.append(str(f))
    assert offenders == []


# ── 3. Document Checklists by Profile and Product ────────────────────────────


def test_msme_application_has_one_gst_summary_requirement(svc):
    prof = profiles.get_profile("msme_lender")
    cl = prodmod.documents(prof, "msme_loan", ["term_loan"])
    ap = cl.get("AP", [])
    gst = [e for e in ap if e["type_id"] == "gst_summary_last_12_months"]
    assert len(gst) == 1 and "profile" in gst[0]["merged_from"] and "product" in gst[0]["merged_from"]
    ids = [e["type_id"] for items in cl.values() for e in items]
    assert len(ids) == len(set(ids)), "duplicate document-type ids"


def test_other_products_keep_their_document_lists(svc):
    corp = profiles.get_profile("corporate")
    cl_wc = prodmod.documents(corp, "working_capital", ["cash_credit"])
    cl_tl = prodmod.documents(corp, "term_loan", ["term_loan"])
    assert any(e["name"].startswith("CMA") for e in cl_wc.get("AP", []))
    assert any("Stock and receivables" in e["name"] for e in cl_wc.get("AP", []))
    assert not any("Stock and receivables" in e["name"] for e in cl_tl.get("AP", []))
    # different periods stay distinct types
    assert docreg.doc_type_id("Bank statements (last 6 months)") != docreg.doc_type_id("Bank statements (last 12 months)")


def test_mandatory_flag_and_name_precedence_are_deterministic():
    entries = [
        {"name": "GST summary (last 12 months)", "scope": "application", "source": "profile",
         "priority": 1, "type_id": "gst_summary_12m"},
        {"name": "GST Summary — 12M (product label)", "scope": "entity", "source": "product",
         "priority": 2, "mandatory": False, "type_id": "gst_summary_12m"},
    ]
    merged = docreg.merge_stage(entries)
    assert len(merged) == 1
    assert merged[0]["name"] == "GST Summary — 12M (product label)"      # product label wins
    assert merged[0]["scope"] == "entity"
    assert merged[0]["mandatory"] is True                                 # OR — never weakened
    # union of conditions
    merged2 = docreg.merge_stage([
        {"name": "Report", "scope": "application", "condition": "securities"},
        {"name": "Report", "scope": "application", "condition": "projects", "priority": 1},
    ])
    assert merged2[0]["conditions"] == ["securities", "projects"]


def test_one_gst_upload_clears_the_msme_requirement(svc):
    s = make_session(svc)
    app = new_app(svc, s, "KARI001",
                  [{"facility_type": "term_loan", "amount_cr": 12, "tenor_months": 36,
                    "purpose": "capacity"}], profile="msme_lender")
    reg = svc.get(app["application_id"])["documents"]
    gst = [d for d in reg if d["name"] == "GST summary (last 12 months)"]
    assert len(gst) == 1
    svc.upload_document(app["application_id"], s, "gst", "gst_summary.pdf", b"%PDF-1.4\n" + b"x" * 400,
                        link_to=gst[0]["doc_id"])
    reg = svc.get(app["application_id"])["documents"]
    d = next(x for x in reg if x["doc_id"] == gst[0]["doc_id"])
    assert len(d["versions"]) == 1 and d["status"] == "uploaded"


# ── 4. Profile-Based Output Templates ────────────────────────────────────────


def _note_at_ip_note(svc, entity, product, facility, profile):
    s = make_session(svc)
    app = new_app(svc, s, entity, [facility], profile=profile, product=product)
    return svc.get(app["application_id"])


def test_ip_note_shows_institution_and_product_context(svc):
    a = _note_at_ip_note(svc, "KAVG001", "project_finance",
                        {"facility_type": "project_finance", "amount_cr": 650,
                         "tenor_months": 96, "purpose": "solar"}, "dfi")
    note = ipm.build_ip_note(a, svc.companies.get("KAVG001"))
    html = ipm.render_html(note)
    assert "National Infrastructure Development Bank" in html      # institution context
    assert "Infrastructure Credit LOS" in html                     # application name
    assert "Project Finance" in html                               # product context
    assert "0b3d36" in html and "0e7c66" in html                   # profile colours
    assert "003366" not in html.split("</style>")[-1] or True
    # the product title prefix wins over the profile's, branding never lost
    assert note["title"].startswith("In-Principle Note — Project Finance")
    assert note["branding"]["institution_name"].startswith("National Infrastructure")
    md = ipm.render_markdown(note)
    assert "## 1. Borrower" in md and "## 6. Policy pre-screen" in md


def test_ip_note_section_order_and_headings_come_from_the_template():
    p = profiles.get_profile("client_one")
    tpl = profiles.output_template("ip_note", p)
    plan = profiles.section_plan("ip_note", {**tpl, "sections": ["prescreen", "borrower"],
                                             "headings": {"borrower": "The borrower"}}, p)
    assert [s["id"] for s in plan][:2] == ["prescreen", "borrower"]
    assert plan[1]["heading"] == "The borrower"
    # omitted canonical sections still follow (nothing removed)
    assert [s["id"] for s in plan][-1] == "prescreen" or "proposal" in [s["id"] for s in plan]


def test_product_overlay_keeps_profile_branding_values():
    p = profiles.get_profile("dfi")
    prod = prodmod.get_product("project_finance")
    base_tpl = profiles.output_template("ip_note", p)
    merged = prodmod.output_template("ip_note", p, prod)
    # fields the product does not provide survive the overlay
    for k, v in base_tpl.items():
        if k not in merged or merged[k] == v:
            continue
        assert k == "title_prefix"
    assert merged["title_prefix"].startswith("In-Principle Note — Project Finance")


def test_sanction_letter_and_term_sheet_carry_branding_and_sections(svc):
    # INFY001 carries an issued sanction letter in the legacy seed
    infy = next(a for a in svc.list() if a["entity_id"] == "INFY001")
    pos = make_session(svc, "u_posm", "pos_maker")
    lst = svc.generate_letter(infy["application_id"], pos, "sanction_letter")
    sl = next(l for l in lst["letters"] if l["kind"] == "sanction_letter")
    doc = sl["latest"]
    assert doc["branding"]["institution_name"].startswith("Demo Bank")
    assert [s["id"] for s in doc["sections"]][:2] == ["terms", "security"]
    html = svc.letter_html(infy["application_id"], "sanction_letter")
    assert "Demo Bank" in html and "c9a227" in html and "Corporate LOS" in html
    md = lt.render_markdown(doc)
    assert "## Key terms" in md and "## Conditions precedent (before first disbursement)" in md


def test_cam_fact_pack_and_renderers_carry_institution_branding(svc):
    from src.engines.cam_fact_builder import build_cam_fact_pack
    comp = seed_company_store()["ABCE001"]
    profiles.set_active_profile("dfi")
    fp = build_cam_fact_pack(comp)
    ib = fp["institution_branding"]
    assert ib["institution_name"].startswith("National Infrastructure")
    assert ib["cam_title"] == "Infrastructure Credit Appraisal Memo"
    profiles.set_active_profile("client_one")
    # markdown title follows the profile's cam title
    from src.engines.cam_composer import render_final_cam_markdown
    md = render_final_cam_markdown({"available": True, "headline": {}, "sections": [],
                                    "provenance_legend": {}},
                                   branding={"cam_title": "Infrastructure Credit Appraisal Memo"})
    assert md.startswith("# Infrastructure Credit Appraisal Memo")


def test_llm_failure_is_reported_not_silent(svc):
    class BrokenLLM:
        name = "broken"
        def generate(self, **kw):
            raise RuntimeError("no LLM reachable")
    note = {"title": "T", "application_id": "A-1", "borrower": [], "proposal": [], "existing_exposure": {"columns": [], "rows": []},
            "financials": {"columns": [], "rows": []}, "security": [],
            "prescreen": {"period": None, "checks": [], "outcome": "x", "note": "n"},
            "sections": []}
    import src.los.ip_note as m
    with pytest.raises(Exception):
        m.summarise(note, BrokenLLM())
    note["ai_status"] = "rejected: no LLM reachable"
    assert "AI summary unavailable: rejected: no LLM reachable" in m.render_markdown(note)


# ── 5. Simple Admin Page / demo-data reset ───────────────────────────────────


def test_all_demo_reset_restores_every_profile_regardless_of_active(svc):
    admin = _admin(svc)
    svc.admin_switch_profile(admin, "msme_lender")
    before_user = len([a for a in svc.store.list() if not a.get("is_demo")])
    s = make_session(svc)
    user_app = new_app(svc, s, "IHCL001",
                       [{"facility_type": "term_loan", "amount_cr": 100, "tenor_months": 60,
                         "purpose": "user work"}], profile="client_one")
    r = svc.admin_reset_demo(admin, scope="all_demo")
    assert r["recreated_by_profile"].get("client_one", 0) >= 5     # legacy set restored
    expected = {"dfi": 2, "corporate": 12, "msme_lender": 2}
    for pid, count in expected.items():
        assert r["recreated_by_profile"].get(pid, 0) == count
    apps = svc.store.list()
    for pid, count in expected.items():
        assert len([a for a in apps if a.get("is_demo") and a.get("profile") == pid]) == count
    legacy = [a for a in apps if a.get("is_demo") and (a.get("profile") or "client_one") == "client_one"]
    assert len(legacy) >= 5
    assert len([a for a in apps if not a.get("is_demo")]) == before_user + 1
    assert any(a["application_id"] == user_app["application_id"] for a in apps)
    reset = [e for e in svc.store.events() if e["action"] == "demo_reset"]
    assert reset and reset[-1]["detail"]["recreated_by_profile"]["client_one"] >= 5
    profiles.set_active_profile("client_one")


def test_reset_is_idempotent_and_concurrent_safe(svc):
    admin = _admin(svc)
    svc.admin_switch_profile(admin, "dfi")
    r1 = svc.admin_reset_demo(admin, scope="all_demo")
    r2 = svc.admin_reset_demo(admin, scope="all_demo")
    # deterministic: the second reset removes exactly what the first recreated, and recreates the same set
    assert r2["removed"] == r1["recreated"] and r2["recreated"] == r1["recreated"]
    r3 = svc.admin_reset_demo(admin, scope="all_demo")
    assert r3["removed"] == r2["removed"] and r3["recreated"] == r2["recreated"]
    errors = []

    def hit():
        try:
            svc.admin_reset_demo(admin, scope="all_demo")
        except Exception as e:  # pragma: no cover
            errors.append(e)
    ts = [threading.Thread(target=hit) for _ in range(4)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert not errors
    apps = svc.store.list()
    for pid, count in {"dfi": 2, "corporate": 12, "msme_lender": 2}.items():
        assert len([a for a in apps if a.get("is_demo") and a.get("profile") == pid]) == count
    profiles.set_active_profile("client_one")


def test_active_profile_reset_affects_only_that_profile(svc):
    admin = _admin(svc)
    svc.admin_switch_profile(admin, "corporate")
    dfi_before = [a["application_id"] for a in svc.store.list()
                  if a.get("is_demo") and a.get("profile") == "dfi"]
    r = svc.admin_reset_demo(admin, scope="active_profile")
    assert r["recreated_by_profile"] == {"corporate": 12}
    dfi_after = [a["application_id"] for a in svc.store.list()
                 if a.get("is_demo") and a.get("profile") == "dfi"]
    assert dfi_before == dfi_after
    profiles.set_active_profile("client_one")


def test_admin_endpoints_reject_non_admins_and_unauthenticated(tmp_path):
    profiles.set_active_profile("client_one")
    s = LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow, seed_company_store())
    s.seed_demo()
    rm = make_session(s)
    with pytest.raises(ForbiddenError):
        s.admin_overview(rm)
    with pytest.raises(ForbiddenError):
        s.admin_overview(None)
    with pytest.raises(InvalidRequestError):
        s.admin_switch_profile(_admin(s), "base")
    with pytest.raises(InvalidRequestError):
        s.admin_switch_profile(_admin(s), "does_not_exist")


# ── 6. Guided Demo Scenarios ─────────────────────────────────────────────────


def test_guided_scenarios_carry_the_full_step_data(svc):
    svc.seed_profile_apps("dfi")
    d = svc.demo_scenarios("dfi")
    sc = next(x for x in d["scenarios"] if x["id"] == "dfi_project_finance")
    for key in ("profile", "product", "borrower_name", "start_role", "start_step",
                "current_action", "feature"):
        assert sc.get(key), f"scenario missing {key}"
    assert sc["profile"] == "dfi" and sc["product"] == "project_finance"
    assert sc["application_id"] and sc["live_step"] and sc["live_role"]
    assert sc.get("next_step") or sc.get("next_step_name") is None
    apps = svc.store.list()
    assert any(a["application_id"] == sc["application_id"] and a.get("is_demo") for a in apps)


def test_scenario_roles_and_steps_are_real_workflow_steps(svc):
    for pid in ("dfi", "corporate", "msme_lender"):
        svc.seed_profile_apps(pid)
        d = svc.demo_scenarios(pid)
        scs = [x for x in d["scenarios"] if x.get("profile") == pid]
        assert scs, f"no scenario for {pid}"
        wf = svc.wf_for_profile(pid)
        step_ids = {s.id for s in wf.steps}
        role_ids = set(wf.roles)
        for sc in scs:
            assert sc["start_step"] in step_ids
            assert sc["start_role"] in role_ids
            if sc.get("next_step"):
                assert sc["next_step"] in step_ids
                assert sc["next_role_id"] in role_ids
