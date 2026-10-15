"""The POC journey for an EXISTING borrower (Apollo Hospitals, APOL001, in the catalogue):
New Application → Existing borrower → Prospect Sourcing → … → Exit, with the agents preparing each
maker step from the borrower's documents on file and the credit engine."""

from tests.test_poc_golden_and_e2e import DEC, _holder


def test_an_existing_borrower_from_the_catalogue_to_exit():
    from src.application.container import build_container
    from tests.test_los_post_sanction import _clear_cps, _review
    from tests.test_los_workflow import _clear_dd, es_work

    svc = build_container().los
    rm = svc.sign_in("u_rm1", "ps_maker")

    # New Application → Existing borrower → Apollo: identity & dedup panel
    ident = svc.borrower_identity("APOL001")
    print("\nidentity:", {k: ident.get(k) for k in ("ntb_etb", "pan", "cin", "constitution")})
    print("duplicates:", [(m["application_id"], m["step"]) for m in ident["los_duplicates"]["matches"]])

    app = svc.create(rm, entity_id="APOL001", sourcing_decision=DEC,
                     facilities=[{"facility_type": "term_loan", "facility_nature": "fund_based", "amount_cr": 100,
                                  "tenor_months": 60, "purpose": "Hospital expansion (POC existing borrower)"}])
    app_id = app["application_id"]
    assert svc.get(app_id)["step"]["id"] == "ps_maker"

    # Prospect Sourcing: no automatic preparation for a catalogue borrower; the RM clicks Prepare with agents
    assert svc.wait_for_preparation(app_id) == {}
    svc.prepare_application(app_id, rm, wait=True)
    job = svc.wait_for_preparation(app_id)
    print("PS lanes:", [(x["lane"], x["status"]) for x in job["lanes"]], "state:", job["state"])
    assert job["state"] == "done", job.get("error")
    prefill = svc.sourcing(app_id, rm)["prefill"]
    found = {f["id"]: f["value"] for f in prefill["fields"] if f.get("value") not in (None, "")}
    print(f"PS intake: {len(found)} of {len(prefill['fields'])} sourcing fields read from Apollo's documents")
    high = [f["id"] for f in prefill["fields"] if f["band"] == "high"]
    svc.apply_prefill(app_id, rm, [{"field_id": f} for f in high])
    _clear_dd(svc, app_id, rm)
    svc.act(app_id, rm, "submit", comment="Sourcing complete; refer for in-principle")

    # IP Note → … → final sanction
    for _ in range(40):
        a = svc.get(app_id)
        if a["step"]["id"] == "pos_maker":
            break
        step, s = svc.wf.step(a["step"]["id"]), _holder(svc, app_id)
        if step.id in ("ip_note", "ap_note", "ip_risk_maker", "ap_risk_maker"):
            svc.prepare_application(app_id, s, wait=True)
            job = svc.wait_for_preparation(app_id)
            assert job["state"] == "done", (step.id, job.get("error"))
            v = svc.assessment(app_id, s)["verify"]
            print(f"{step.id}: lanes {[x['lane'] for x in job['lanes']]}; step queue {len(v['queue'])}, "
                  f"step stats {v['step_stats']}")
            pre = [i["field_id"] for i in v["queue"] if i.get("preticked")]
            if pre:
                svc.bulk_confirm(app_id, s, pre)
        if step.id == "ip_note":
            cov = svc.get(app_id)["prefill_coverage"]
            print(f"IP Note pre-filled: {cov['filled']} of {cov['total']} sections; missing",
                  [x["label"] for x in cov["sections"] if not x["filled"]])
            assert cov["filled"] >= 14, cov                       # R-P1 acceptance
        if step.id == "ap_note":
            # G-F2: the AP maker authors the T&C — the agent's drafts confirmed, plus one of their own
            t = svc.terms(app_id, s)
            print("T&C drafted:", t["summary"]["by_category"], "awaiting:", t["summary"]["awaiting_confirmation"])
            assert t["editable"] and t["summary"]["from_agent"] >= 10
            assert {"CP", "FC", "FS"} <= {k for k, n in t["summary"]["by_category"].items() if n}
            fc = [r for r in t["rows"] if r["category"] == "FC" and r.get("stipulated_value")]
            assert fc, "financial covenants carry their stipulated value"
            svc.bulk_confirm(app_id, s, [r["field_id"] for r in t["rows"] if r["field_status"] == "proposed"])
            svc.save_term(app_id, s, {"action": "add", "category": "GC",
                                      "text": "Quarterly hospital occupancy report to be submitted (POC)"})
            assert svc.terms(app_id, s)["gate"] is None
            # the ESMS screen the agent started (project + excluded-activity proposal) is completed by the maker
            esms = svc.get(app_id)["esms"]
            print("ESMS agent:", {k: esms.get(k) for k in ("proposed_category", "information_source")},
                  [(i["id"], i.get("answer")) for i in esms.get("checklist") or []])
            assert esms.get("proposed_category") and any(i.get("answer") for i in esms["checklist"])
            svc.update_esms(app_id, s, {"screening_date": svc.now().date().isoformat(), "category": esms["proposed_category"],
                                        "checklist": [{"id": i, "answer": "No", "remarks": "Screened (POC)"}
                                                      for i, _ in __import__("src.los.esms", fromlist=["x"]).ES_CHECKLIST]})
        if step.id == "ap_risk_maker":
            # R-P2: RAROC is computed by the agent once the rating grade and the rate are verified
            fields = svc.get(app_id)["fields"]
            inputs = ["internal_rating.borrower.grade"] + [k for k in fields if k.startswith("facility_pricing.")
                                                           and k.endswith((".proposed_rate", ".proposed_spread_bps"))]
            svc.verify_fields(app_id, s, [{"field_id": k, "action": "confirm"} for k in inputs
                                          if fields[k]["status"] == "proposed"])
            raroc = svc.get(app_id)["ratings"]["raroc"]
            print("RAROC (agent):", {k: (v["raroc_pct"], v["computed_by"]) for k, v in raroc.items()})
            assert raroc and all(v.get("origin") == "agent" for v in raroc.values())
        if step.id == "ip_note":
            svc._seed_stage_docs(app_id, "IP", svc.now())
        action = {"maker": "submit", "checker": "approve", "committee": "sanction", "vp_review": "submit",
                  "allocation": "allocate"}[step.kind]
        es_work(svc, app_id, s, step.id)                 # the ES steps (G-W2)
        required = {f["id"]: svc.now().date().isoformat() for f in step.decision_fields if f.get("required")}
        svc.act(app_id, s, action, comment=f"{step.name}: {action} (POC existing borrower)", decision_data=required,
                allocate_to=svc._default_assignee(step.allocates_to) if step.kind == "allocation" else None,
                sanctioned_amount_cr=svc.get(app_id)["amount_cr"]
                if step.kind == "committee" and step.id.endswith("sanction") else None)
    assert svc.get(app_id)["step"]["id"] == "pos_maker"
    ca = svc.get(app_id)["credit_assessment"]
    print("credit case:", {k: ca.get(k) for k in ("run_id", "decision", "risk_grade", "requested_cr", "recommended_cr")})
    # the case assesses THIS application's request (₹100 Cr), not the facility on Apollo's catalogue record (₹750 Cr)
    assert ca.get("requested_cr") == 100, ca
    # G-F2: the conditions tracked after sanction are the T&C authored at AP, not regenerated
    conds, terms = svc.get(app_id)["conditions"], svc.terms(app_id, rm)
    assert terms["status"] == "sanctioned" and len(conds) == terms["summary"]["total"]
    assert all(c.get("term_id") for c in conds) and any("occupancy" in c["text"] for c in conds)

    # Post Sanction: no signed letter on file for Apollo, so preparation reads nothing; the maker keys consent
    maker = _holder(svc, app_id)
    svc.prepare_application(app_id, maker, wait=True)
    job = svc.wait_for_preparation(app_id)
    print("POS prep:", job["state"], "suggested:", svc.post_sanction(app_id, maker)["suggested"])
    svc.generate_letter(app_id, maker, "sanction_letter")
    svc.record_consent(app_id, maker, acknowledged_by="Apollo authorised signatory", consent_date=svc.now().date().isoformat(),
                       facilities=[{"facility_id": f["facility_id"], "execution_status": "executed",
                                    "agreement_date": svc.now().date().isoformat()} for f in svc.get(app_id)["facilities"]])
    _clear_cps(svc, app_id, maker)
    svc._seed_stage_docs(app_id, "POS", svc.now())
    try:                                                   # changes since the sanction, if any, are reviewed
        svc.review_material_changes(app_id, maker, "accept", "Reviewed (POC existing borrower)")
    except Exception as exc:
        print("material changes:", exc)
    svc.act(app_id, maker, "submit", comment="Consent, execution and conditions precedent in place")
    svc.act(app_id, _holder(svc, app_id), "approve", comment="Post-sanction record verified")

    # Disbursement: the carry-forward agent (R-P3) proposes the operational record from the sanctioned record
    maker = _holder(svc, app_id)
    svc.prepare_application(app_id, maker, wait=True)
    job = svc.wait_for_preparation(app_id)
    assert job["state"] == "done", job.get("error")
    assert "carry_forward" in [x["lane"] for x in job["lanes"]]
    view = svc.get(app_id, maker)
    d, fac = view["disops"], view["facilities"][0]
    print("carried:", d["interest_terms"], d["repayment_final"], [(f["nature"], f["gross_cr"]) for f in d["fees"]],
          [r["security_id"] for r in d["security_refs"]], job["summary"]["carry_forward"]["filled"])
    assert d["interest_terms"]["rate"] == fac["pricing"]["interest_rate"] and d["interest_terms"]["benchmark"]
    assert d["repayment_final"]["tenor_months"] == fac["tenor_months"]
    assert {f["nature"] for f in d["fees"]} == {"processing"}                     # the fee approved at AP
    assert [r["security_id"] for r in d["security_refs"]] == [x["security_id"] for x in view["securities"]]
    queue = svc.assessment(app_id, maker)["verify"]["queue"]
    assert any(i["field_id"].startswith("dis_carry.") for i in queue)
    # the maker saves the interest terms with one change: recorded against the agent's proposals
    terms = {k: v for k, v in d["interest_terms"].items() if v is not None}
    svc.update_disops(app_id, maker, "interest_terms", {**terms, "reset_frequency": "annual"})
    fields = svc._require(app_id)["fields"]
    assert fields["dis_carry.interest.rate"]["status"] == "confirmed"
    assert fields["dis_carry.interest.benchmark"]["status"] == "confirmed"
    svc._seed_disbursement_record(app_id, svc.now())
    svc.update_disops(app_id, maker, "beneficiaries", {"rows": [{
        "name": "Apollo Hospitals Enterprise Ltd", "account_no": "004512300011111", "ifsc": "DEMO0001234", "bank": "Demo Bank"}]})
    svc.request_tranche(app_id, maker, 40, svc.now().date().isoformat(), "First drawdown")
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

    assert final["status"] == "APPROVED"
    fields = svc.get(app_id)["fields"]
    domains = sorted({r["domain"] for r in fields.values() if r["status"] != "unavailable"})
    print("domains populated:", domains)
    overridden = {k: (r["proposal"]["value"], r["value"]) for k, r in fields.items() if r["status"] == "overridden"
                  and not k.startswith("dis_carry.")}       # the demo seed replaces the disbursement record
    print("overridden:", overridden)
    assert not overridden, "nothing was corrected; typed values where the agent read nothing are not overrides"
    print("agents headline:", svc.mis()["agents"]["headline"])
    agents = svc.mis()["agents"]
    assert agents["carry_forward"]["populated"] >= 10 and agents["terms"]["populated"] >= 10     # S9 / S10 in the MIS
    assert {"sourcing", "cma", "narrative", "parties", "securities"} <= set(domains), domains
