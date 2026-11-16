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
