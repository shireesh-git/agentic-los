"""Fix list round 8: delete several proposals from the queue at once, and load a new-to-bank prospect's UAT test
pack (test-documents/<borrower>/) in one click instead of uploading each document."""

import pytest

from src.application.container import build_container
from src.flow import test_packs

TCI_CIN = "L70109TG1995PLC019116"


@pytest.fixture(scope="module")
def svc():
    flow = build_container().flow
    for e in ("INFY001", "MFL001"):
        flow.reset({"user": {"id": "test"}}, e)
    yield flow
    for e in ("INFY001", "MFL001"):
        flow.reset({"user": {"id": "test"}}, e)


def test_the_rm_deletes_several_proposals_and_a_sanctioned_one_is_kept(svc):
    rm = svc.sign_in("f_rm")
    a = svc.create(rm, entity_id="INFY001")["case_id"]
    b = svc.create(rm, entity_id="MFL001")["case_id"]
    case = svc._require(b)
    case["sanction"] = {"limit_cr": 10}
    svc._save(case)
    rows = {r["case_id"]: r for r in svc.queue(rm)["all"]}
    assert rows[a]["deletable"] and not rows[b]["deletable"]
    r = svc.delete_cases([a, b, "LOS-NOPE"], rm)
    assert r["deleted"] == [a]
    assert {k["case_id"] for k in r["kept"]} == {b, "LOS-NOPE"}
    assert "kept for the record" in next(k["reason"] for k in r["kept"] if k["case_id"] == b)
    with pytest.raises(Exception):                               # only the RM housekeeps the queue
        svc.delete_cases([b], svc.sign_in("f_cro"))


def _pack(root, name="ACME LOGISTICS LIMITED", cin="L12345MH2000PLC000001"):
    d = root / "acme"
    (d / "demo" / "bureau").mkdir(parents=True)
    (d / "public").mkdir()
    (d / "prepare.py").write_text(f'SPEC = {{"public": {{"annual_report_fy2026.pdf": "https://x/a.pdf"}},\n'
                                  f'        "name": "{name}",\n        "cin": "{cin}"}}\n', encoding="utf-8")
    (d / "demo" / "bureau" / "commercial_bureau_report.pdf").write_bytes(b"%PDF-1.4 demo")
    (d / "public" / "annual_report_fy2026.pdf").write_bytes(b"%PDF-1.4 ar")
    (d / "public" / "care_rationale_2026-09.pdf").write_bytes(b"%PDF-1.4 r")
    return d


def test_a_pack_is_found_by_cin_or_by_name_and_filed_by_category(tmp_path):
    _pack(tmp_path)
    [p] = test_packs.packs(tmp_path)
    assert p["cin"] == "L12345MH2000PLC000001" and p["public"] == {"annual_report_fy2026.pdf": "https://x/a.pdf"}
    assert test_packs.find(tmp_path, "L12345MH2000PLC000001", "anything")["id"] == "acme"
    assert test_packs.find(tmp_path, None, "Acme Logistics Ltd")["id"] == "acme"
    assert test_packs.find(tmp_path, "L99999MH2000PLC000009", "Acme Logistics Ltd") is None   # CIN disagrees
    out = tmp_path / "docs"
    assert sorted(test_packs.copy_into(p, out)) == ["bureau/commercial_bureau_report.pdf",
                                                    "financials/annual_report_fy2026.pdf",
                                                    "ratings/care_rationale_2026-09.pdf"]
    assert (out / "financials" / "annual_report_fy2026.pdf").exists()


def test_the_real_packs_are_all_recognised():
    from src.core.runtime_paths import PROJECT_ROOT
    cins = {p["cin"] for p in test_packs.packs(PROJECT_ROOT / "test-documents")}
    assert TCI_CIN in cins and "L32101UP1993PLC066581" in cins


def test_the_rm_loads_the_test_pack_into_a_prospect(svc, tmp_path, monkeypatch):
    rm = svc.sign_in("f_rm")
    cid = svc.create(rm, entity_id="INFY001")["case_id"]
    case = svc._require(cid)
    case.update(is_prospect=True, borrower_name="Transport Corporation of India Ltd", prospect={"cin": TCI_CIN},
                acquisition={"state": "done", "sources": {}})
    svc._save(case)
    assert svc.view(cid, rm)["test_pack"]["id"] == "tci_logistics"
    started = []
    monkeypatch.setattr(svc, "documents_root", tmp_path)
    monkeypatch.setattr(svc, "_start_acquire", lambda case_id, only=None: started.append(case_id))
    svc.load_test_pack(cid, rm)
    assert started == [cid]
    assert (tmp_path / "INFY001" / "bureau" / "commercial_bureau_report.pdf").exists()
    assert "Test pack loaded" in svc._require(cid)["chat"][-1]["text"]
    svc.reset(rm, "INFY001")


def test_a_challenge_says_what_is_decided_and_names_the_open_question():
    from src.flow import risk as rk
    engine = {"challenges": [{"rule_id": "UNRESOLVED_INVESTIGATIONS", "title": "Key questions are still open",
                              "severity": "HIGH", "challenge": "1 investigation(s) … still open",
                              "linked_investigation_ids": ["INV-1"], "required_response": ["Close or waive"]}],
              "investigations": [{"investigation_id": "INV-1", "title": "Data reliability",
                                  "reason": "Debt differs: 161.85 (audited) vs 300.00 (bureau).",
                                  "required_evidence": [{"item": "Lender balance confirmations",
                                                         "description": "From each lender at the balance-sheet date"}]}]}
    [c] = rk.challenges(engine)
    assert "161.85" in c["what"] and c["asks"] == ["Lender balance confirmations: From each lender at the balance-sheet date"]
    assert c["decision"].startswith("Figures the proposal relies on")
    labels = [a["label"] for a in c["actions"]]
    assert labels == ["Ask the RM for evidence", "Accept the risk, with justification", "Decline the proposal"]


def test_a_known_borrower_cannot_be_initiated_again_as_a_prospect(svc):
    rm = svc.sign_in("f_rm")
    with pytest.raises(Exception, match="already a borrower on record"):
        svc.create(rm, prospect={"company_name": "Infosys Ltd", "sector": "it_services"},
                   facility={"product": "working_capital", "amount_cr": 10})


def test_fields_the_agents_could_not_fill_are_asked_and_editable_unless_calculated():
    from src.flow import datapoints as dpx
    by = {s["id"]: s for s in dpx.specs()}
    for f in ("bureau_score", "crilc_sma", "marketing_arrangements", "collateral_fsv_cr"):
        assert not by[f].get("agent_only") and by[f].get("ask")
    assert by["margin_of_safety_pct"]["computed"] and "break-even" in by["margin_of_safety_pct"]["unavailable"]
    assert by["recommended_cr"]["label"] == "Recommended for sanction (₹ Cr)" and by["recommended_cr"]["help"]


def test_an_uncalculated_figure_can_be_entered_with_a_reason_and_a_non_applicable_one_says_so(svc):
    rm = svc.sign_in("f_rm")
    svc.reset(rm, "INFY001")
    cid = svc.create(rm, entity_id="INFY001", facility={"product": "working_capital", "amount_cr": 500})["case_id"]
    case = svc._require(cid)
    case["cam"] = {"state": "ready", "mode": "upload"}
    case["dp"] = {"assessed_limit_cr": {"value": None, "status": "missing"},
                  "sustainable_limit_cr": {"value": 434.0, "status": "filled", "source": {"kind": "engine"}}}
    svc._save(case)
    pts = {p["id"]: p for g in svc.view(cid, rm)["groups"] for p in g["points"]}
    assert pts["assessed_limit_cr"]["can_edit"] and pts["assessed_limit_cr"]["needs_reason"]
    assert pts["margin_of_safety_pct"]["status"] == "not_applicable" and not pts["margin_of_safety_pct"]["can_edit"]
    assert not pts["sustainable_limit_cr"]["can_edit"]                  # the engine calculated it
    with pytest.raises(Exception, match="how you arrived"):
        svc.set_datapoint(cid, rm, "assessed_limit_cr", 420, "")
    svc.set_datapoint(cid, rm, "assessed_limit_cr", 420, "Guarantee pipeline from the borrower: 14 contracts, ₹420 Cr")
    with pytest.raises(Exception, match="calculated by the CAM engine"):
        svc.set_datapoint(cid, rm, "sustainable_limit_cr", 500, "x")
    pts = {p["id"]: p for g in svc.view(cid, rm)["groups"] for p in g["points"]}
    assert pts["assessed_limit_cr"]["value"] == 420 and pts["assessed_limit_cr"]["source"]["kind"] == "person"
    assert "margin_of_safety_pct" not in {f["id"] for f in svc.view(cid, rm)["incomplete"]}
    svc.reset(rm, "INFY001")


@pytest.mark.parametrize("eid", ["TSTL001", "MFL001", "OLOG001", "DLFR001"])
def test_every_borrower_with_data_is_offered_and_its_cam_generates(svc, eid):
    rm = svc.sign_in("f_rm")
    assert eid in {b["entity_id"] for b in svc.borrowers()} and len(svc.borrowers()) >= 21
    svc.reset(rm, eid)
    cid = svc.create(rm, entity_id=eid)["case_id"]
    assert not svc._require(cid)["is_prospect"]
    svc.generate_cam(cid, rm)
    case = svc.wait_for_cam(cid, timeout=300)
    assert case["cam"]["state"] == "ready", case["cam"]
    v = svc.view(cid, rm)
    assert v["counts"]["filled"] >= 25 and v["graph"]
    svc.reset(rm, eid)
