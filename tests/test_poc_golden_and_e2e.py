"""Sprint 6: the extraction measured against the golden demo set, and the POC journey end to end —
a new-to-bank prospect from its documents to Exit, with the agents populating and people verifying."""

import pytest

from src.devtools.demo_documents import GOLDEN, NEEDS_VISION, write_set
from src.los import intake, later_intake

SETS = {"sourcing": None, "post_sanction": later_intake.POST_SANCTION_FIELDS,
        "disbursement": later_intake.DISBURSEMENT_FIELDS}


# ── golden set ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def demo_root(tmp_path_factory):
    root = tmp_path_factory.mktemp("demo_docs")
    write_set(root)
    return root


@pytest.mark.parametrize("domain", list(SETS))
def test_extraction_matches_the_golden_set(demo_root, domain):
    prefill = intake.run_intake(demo_root, {}, specs=SETS[domain])
    got = {f["id"]: f["value"] for f in prefill["fields"]}
    expected = {k: v for k, v in GOLDEN[domain].items() if (domain, k) not in NEEDS_VISION}
    wrong = {k: (got.get(k), v) for k, v in expected.items() if got.get(k) is not None and got.get(k) != v}
    missed = [k for k, v in expected.items() if got.get(k) is None]
    assert not wrong, f"wrong values (got, expected): {wrong}"                 # precision: 100%
    assert not missed, f"not found: {missed}"                                  # recall on text pages: 100%
    for k in expected:                                                         # every value cites its page
        f = next(x for x in prefill["fields"] if x["id"] == k)
        assert f["sources"] and f["sources"][0]["page"] >= 1


def test_the_scanned_pan_is_reported_not_guessed(demo_root):
    prefill = intake.run_intake(demo_root, {})
    assert next(f for f in prefill["fields"] if f["id"] == "pan")["status"] == "not_found"
    assert any("pan_card_scan.pdf" in p for p in prefill["intake"]["unread_pages"])


def test_audited_statements_are_read_with_the_right_revenue(demo_root):
    from src.engines.document_ocr_engine import extract_financials_enhanced
    data = extract_financials_enhanced(demo_root / "financials" / "audited_financials_fy2025.pdf")["data"]
    for key, value in GOLDEN["audited_financials"].items():
        assert data[key][0] == value, key


# ── the journey end to end ───────────────────────────────────────────────────

DEC = {"decision": "Refer for in-principle", "mandatory_remarks": "New prospect sourced from its documents (POC)."}


def _holder(svc, app_id):
    app = svc.get(app_id)
    return svc.sign_in(app["assignee_id"], app["step"]["role"])


def _upload(svc, session, app_id, root, rel):
    category, name = rel.split("/")
    svc.upload_document(app_id, session, category, name, (root / rel).read_bytes())


def ap_maker_authors_terms_and_esms(svc, app_id, s):
    """The AP maker step as a person works it: confirm the T&C agent's drafts, complete the ESMS screen
    the agents started (project / excluded-activity proposal)."""
    from src.los.esms import ES_CHECKLIST
    svc._seed_stage_docs(app_id, "AP", svc.now())          # the AP documents on file and reviewed (demo)
    t = svc.terms(app_id, s)
    pending = [r["field_id"] for r in t["rows"] if r["field_status"] == "proposed" and not r["removed"]]
    if pending:
        svc.bulk_confirm(app_id, s, pending)
    assert svc.terms(app_id, s)["gate"] is None
    esms = svc.get(app_id)["esms"] or {}
    if any(i.get("answer") for i in esms.get("checklist") or []) or svc.get(app_id)["projects"]:
        svc.update_esms(app_id, s, {"screening_date": svc.now().date().isoformat(),
                                    "category": esms.get("proposed_category") or "C",
                                    "checklist": [{"id": i, "answer": "No", "remarks": "Screened (POC)"}
                                                  for i, _ in ES_CHECKLIST]})
    return t


def cam_format(svc, entity_id):
    """The CAM engine's format: the composed CAM's sections and the CAM document's headings."""
    import re
    final = svc.final_cam.get(entity_id)["final_cam"]
    case = svc.cases.get(entity_id)
    headings = re.findall(r"^#{2} (?:\d+\.\s*)?(.+)$", case.get("cam_text") or "", re.M)
    return [x.get("id") or x.get("title") for x in final.get("sections") or []], len(headings)


def test_a_new_prospect_from_documents_to_exit(tmp_path):
    from src.application.container import build_container
    from tests.test_los_post_sanction import _clear_cps, _review
    from tests.test_los_workflow import _clear_dd, es_work

    svc = build_container().los
    root = tmp_path / "docs"
    write_set(root)
    rm = svc.sign_in("u_rm1", "ps_maker")

    # Prospect Sourcing: stage the documents, the intake agent proposes, the RM confirms and creates
    sid = None
    for rel in ("request/request_letter.pdf", "kyc/certificate_of_incorporation.pdf", "kyc/pan_card_scan.pdf",
                "financials/audited_financials_fy2025.pdf"):
        sid = svc.stage_document(rm, rel.split("/")[0], rel.split("/")[1], (root / rel).read_bytes(), sid)["staging_id"]
    read = svc.read_staged(rm, sid)
    ident = {k: read["identity"][k]["value"] for k in ("cin", "date_of_incorporation", "registered_address")}
    app = svc.create_prospect(rm, staging_id=sid, sourcing_decision=DEC, prepare=False,
                              identity={"company_name": read["identity"]["legal_name"]["value"], "pan": "AAACZ1234Q",
                                        "sector": "manufacturing", **ident},
                              facilities=[{"facility_type": read["facility"]["facility_type"]["value"],
                                           "amount_cr": read["facility"]["amount_cr"]["value"],
                                           "tenor_months": read["facility"]["tenor_months"]["value"],
                                           "purpose": read["facility"]["purpose"]["value"]}],
                              cam={"mode": "generate"})
    app_id = app["application_id"]
    svc.prepare_application(app_id, rm, wait=True)
    job = svc.wait_for_preparation(app_id)
    assert job["state"] == "done", job.get("error")
    # No CAM yet → the CAM engine generated it while Prospect Sourcing was prepared, in the same format
    # as an existing borrower's CAM (the same pipeline, the composed banker CAM)
    assert job["summary"].get("cam_generated"), job["summary"]
    entity = svc.get(app_id)["entity_id"]
    svc.cases.run("APOL001")
    new_sections, new_headings = cam_format(svc, entity)
    old_sections, old_headings = cam_format(svc, "APOL001")
    print("CAM sections (new / existing):", len(new_sections), len(old_sections), "headings:", new_headings, old_headings)
    assert new_sections == old_sections and new_headings == old_headings and new_headings >= 15
    high = [f["id"] for f in svc.sourcing(app_id, rm)["prefill"]["fields"] if f["band"] == "high"]
    svc.apply_prefill(app_id, rm, [{"field_id": f} for f in high])
    _clear_dd(svc, app_id, rm)
    svc.act(app_id, rm, "submit", comment="Sourcing complete; refer for in-principle")

    # IP Note → … → final sanction: the agents prepare each maker step; people decide
    for _ in range(40):
        a = svc.get(app_id)
        if a["step"]["id"] == "pos_maker":
            break
        step, s = svc.wf.step(a["step"]["id"]), _holder(svc, app_id)
        if step.id in ("ip_note", "ap_note", "ip_risk_maker", "ap_risk_maker"):
            svc.prepare_application(app_id, s, wait=True)
            job = svc.wait_for_preparation(app_id)
            assert job["state"] == "done", (step.id, job.get("error"))
            assert not job["summary"]["credit_case_ran"], "the CAM generated at sourcing is reused, not re-run"
        if step.id == "ip_note":
            cov = svc.get(app_id)["prefill_coverage"]
            print(f"IP Note pre-filled: {cov['filled']} of {cov['total']}; missing",
                  [x["label"] for x in cov["sections"] if x["applicable"] and not x["filled"]])
            # a new-to-bank prospect from four documents: no collateral or banking arrangement documented yet
            assert cov["filled"] >= cov["total"] - 2, cov
        if step.id == "ap_note":
            t = ap_maker_authors_terms_and_esms(svc, app_id, s)
            print("T&C drafted for the prospect:", t["summary"]["by_category"])
        if step.id == "ip_note":
            svc._seed_stage_docs(app_id, "IP", svc.now())           # the IP checklist documents (demo)
        if step.id == "ap_risk_maker" and not any(x.get("rows") for x in (svc.get(app_id).get("cma") or {}).get("subjects") or []):
            pytest.fail("the reconciliation agent should have written the CMA")
        action = {"maker": "submit", "checker": "approve", "committee": "sanction", "vp_review": "submit",
                  "allocation": "allocate"}[step.kind]
        es_work(svc, app_id, s, step.id)                 # the ES steps (G-W2)
        required = {f["id"]: svc.now().date().isoformat() for f in step.decision_fields if f.get("required")}
        svc.act(app_id, s, action, comment=f"{step.name}: {action} (POC e2e)", decision_data=required,
                allocate_to=svc._default_assignee(step.allocates_to) if step.kind == "allocation" else None,
                sanctioned_amount_cr=45 if step.kind == "committee" and step.id.endswith("sanction") else None)
    assert svc.get(app_id)["step"]["id"] == "pos_maker"
    conds = svc.get(app_id)["conditions"]
    assert conds and all(c.get("term_id") for c in conds), "the conditions are the T&C authored at AP"

    # Post Sanction: the signed letter and the agreement are read; the maker saves the pre-filled consent
    maker = _holder(svc, app_id)
    for rel in ("legal/signed_sanction_letter.pdf", "legal/facility_agreement.pdf"):
        _upload(svc, maker, app_id, root, rel)
    svc.prepare_application(app_id, maker, wait=True)
    assert svc.wait_for_preparation(app_id)["state"] == "done"
    sp = svc.post_sanction(app_id, maker)["suggested"]["post_sanction"]
    assert (sp["accepted_by"], sp["acceptance_date"], sp["agreement_date"]) == ("Rohan Desai", "2026-11-05", "2026-11-10")
    svc.generate_letter(app_id, maker, "sanction_letter")
    svc.record_consent(app_id, maker, acknowledged_by=sp["accepted_by"], consent_date=sp["acceptance_date"],
                       facilities=[{"facility_id": f["facility_id"], "execution_status": "executed",
                                    "agreement_date": sp["agreement_date"]} for f in svc.get(app_id)["facilities"]])
    _clear_cps(svc, app_id, maker)
    svc._seed_stage_docs(app_id, "POS", svc.now())
    # the documents added after sanction are a material change: the maker reviews it before submitting
    svc.review_material_changes(app_id, maker, "accept", "Post-sanction documents: the signed letter and the agreement")
    svc.act(app_id, maker, "submit", comment="Consent, execution and conditions precedent in place")
    svc.act(app_id, _holder(svc, app_id), "approve", comment="Post-sanction record verified")

    # Disbursement: the drawdown request is read; the maker saves the pre-filled tranche and beneficiary
    maker = _holder(svc, app_id)
    _upload(svc, maker, app_id, root, "request/drawdown_request.pdf")
    svc.prepare_application(app_id, maker, wait=True)
    assert svc.wait_for_preparation(app_id)["state"] == "done"
    sd = svc.post_sanction(app_id, maker)["suggested"]["disbursement"]
    svc._seed_disbursement_record(app_id, svc.now())                 # CIF / limits / CBS ids: demo, not integrated
    svc.update_disops(app_id, maker, "beneficiaries", {"rows": [{
        "name": sd["beneficiary_name"], "account_no": sd["account_number"], "ifsc": sd["ifsc"], "bank": "Demo Bank"}]})
    svc.request_tranche(app_id, maker, sd["drawdown_amount_cr"], sd["value_date"], sd["drawdown_purpose"])
    svc.update_disops(app_id, maker, "sop", {"items": [
        {"id": i["id"], "status": "in_compliance", "remarks": "Verified (POC)"}
        for i in (svc.get(app_id).get("disops") or {}).get("sop") or [] if i.get("status") != "in_compliance"]})
    svc.generate_memo(app_id, maker)
    svc.review_memo(app_id, maker, True, "Memo consistent with the record")
    svc._seed_stage_docs(app_id, "DIS", svc.now())
    dis = svc.post_sanction(app_id, maker)["disbursement"]
    svc.update_checklist(app_id, maker, [{"id": i["id"], "done": True} for i in dis["checklist"] if i["kind"] == "manual"])
    svc.act(app_id, maker, "submit", comment="Drawdown prepared")
    checker = _holder(svc, app_id)
    _review(svc, app_id, checker, "checker")
    svc.act(app_id, checker, "approve", comment="Tranche verified")
    svc.act(app_id, _holder(svc, app_id), "submit", comment="VP review: no significant changes")
    approver = _holder(svc, app_id)
    _review(svc, app_id, approver, "final")
    final = svc.act(app_id, approver, "approve", comment="Disbursement approved")

    # Exit, with the agents' work measured
    assert final["status"] == "APPROVED"
    fields = svc.get(app_id)["fields"]
    domains = {r["domain"] for r in fields.values() if r["status"] != "unavailable"}
    print("domains populated for the prospect:", sorted(domains))
    assert {"sourcing", "post_sanction", "disbursement", "cma", "narrative"} <= domains, sorted(domains)
    for k in ("accepted_by", "acceptance_date"):                             # saved as read: confirmed
        rec = fields[f"post_sanction.sanction_acceptance.{k}"]
        assert rec["status"] == "confirmed", (k, rec["value"], rec["proposal"]["value"], rec["history"])
    assert fields["disbursement.drawdown_request.drawdown_amount_cr"]["status"] == "confirmed"
    agents = svc.mis()["agents"]
    assert agents["headline"]["populated_pct"] > 50 and agents["headline"]["values_not_keyed"] >= 10
    assert agents["activity"]["prospects_from_documents"] >= 1 and agents["activity"]["preparations"] >= 5
