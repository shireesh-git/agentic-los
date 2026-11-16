"""Credit knowledge graph (Wave 1, item 2) and the credit data mart (item 1)."""

from datetime import date

from src.flow import graph as kg
from src.models.canonical_model import Borrower, BorrowerType, DirectorPromoter, GroupEntity, Sector

CFG = {"bank": {"name": "Test Bank", "tier1_capital_cr": 1000},
       "limits": {"single_counterparty_pct": 20, "group_pct": 25, "warn_at_pct_of_limit": 85},
       "group_rules": {"min_holding_pct": 50, "common_promoter": True, "declared_group": True},
       "stress": {"classifications": ["SMA-2", "NPA"], "flags": ["wilful_defaulter"], "max_hops": 2},
       "bank_officials": [{"name": "Lata Iyer", "din": "00000009", "role": "Director, Test Bank"}],
       "significant_holding_pct": 10}


def _borrower(eid, name, cin):
    return Borrower(entity_id=eid, company_name=name, cin=cin, pan="AAAAA0000A", borrower_type=BorrowerType.UNLISTED,
                    sector=Sector.MANUFACTURING, subsector="", date_of_incorporation=date(2010, 1, 1),
                    registered_state="MH", registered_address="", authorized_capital=1, paid_up_capital=1)


def _companies():
    return {
        "A1": {"borrower": _borrower("A1", "Alpha Steel Ltd", "U27100MH2010PLC000001"),
               "directors": [DirectorPromoter(din="00000001", name="Ravi Shah", designation="Managing Director",
                                              entity_id="A1", is_promoter=True),
                             DirectorPromoter(din="00000009", name="Lata R. Iyer", designation="Independent Director",
                                              entity_id="A1")],
               "group": GroupEntity(group_id="G1", group_name="Alpha Group", parent_entity_id="A1",
                                    entities=["A1", "Alpha Wires Pvt Ltd"])},
        "B1": {"borrower": _borrower("B1", "Beta Foods Ltd", "U15400MH2012PLC000002"),
               "directors": [DirectorPromoter(din="99000001", name="Meena Rao", designation="Managing Director",
                                              entity_id="B1", is_promoter=True)]},
        "C1": {"borrower": _borrower("C1", "Gamma Agro Ltd", "U01100MH2014PLC000003"),
               "directors": [DirectorPromoter(din="99000001", name="Karan Mehta", designation="Managing Director",
                                              entity_id="C1", is_promoter=True)]},
    }


NETWORK = {
    "companies": [{"cin": "U45400MH2015PTC000004", "name": "Shah Infra Pvt Ltd", "classification": "SMA-2",
                   "source": "bureau (demo)"},
                  {"cin": "U27200MH2016PTC000005", "name": "Alpha Wires Pvt Ltd", "classification": "Standard"}],
    "directorships": [{"din": "00000001", "name": "Ravi Shah", "cin": "U45400MH2015PTC000004",
                       "designation": "Director", "promoter": True}],
    "holdings": [{"holder_cin": "U27100MH2010PLC000001", "held_cin": "U27200MH2016PTC000005", "pct": 60}],
    "our_book": [{"cin": "U27200MH2016PTC000005", "product": "Term loan", "sanctioned_cr": 200}],
}


def _cases():
    return [{"case_id": "P1", "entity_id": "A1", "status": "open", "facility": {"amount_cr": 100, "product": "WC"}},
            {"case_id": "P2", "entity_id": "A1", "status": "rejected", "facility": {"amount_cr": 900}},
            {"case_id": "P3", "entity_id": "B1", "status": "disbursed", "facility": {"amount_cr": 80},
             "sanction": {"limit_cr": 50}}]


def _graph():
    return kg.build(_companies(), _cases(), NETWORK, CFG, demo_enabled=True)


def test_a_director_on_a_stressed_company_is_found_with_its_path():
    r = kg.assess(_graph(), "A1", CFG)
    [s] = r["stressed"]
    assert s["name"] == "Shah Infra Pvt Ltd" and s["status"] == "SMA-2"
    assert "Ravi Shah (DIN 00000001)" in s["path"] and s["demo"]
    assert {c["code"]: c["status"] for c in kg.checks(r)}["KG_CONNECTED_STRESS"] == "fail"


def test_group_exposure_counts_holdings_declared_group_and_common_promoter_but_not_closed_proposals():
    r = kg.assess(_graph(), "A1", CFG)
    why = {m["name"]: m["why"] for m in r["group"]}
    assert why["Alpha Wires Pvt Ltd"].startswith(("60% holding", "declared group"))
    assert why["Shah Infra Pvt Ltd"].startswith("common promoter")
    x = r["exposure"]
    assert x["single_cr"] == 100                       # the rejected ₹900 Cr proposal does not count
    assert x["group_cr"] == 300 and x["group_limit_cr"] == 250 and x["group_used_pct"] == 120.0
    check = {c["code"]: c for c in kg.checks(r)}["KG_GROUP_EXPOSURE"]
    assert check["status"] == "fail" and check["detail"].startswith("Over the limit: exposure to its group")


def test_sanctioned_limit_counts_once_sanctioned():
    r = kg.assess(_graph(), "B1", CFG)
    assert r["exposure"]["single_cr"] == 50 and {c["code"]: c["status"] for c in kg.checks(r)}["KG_GROUP_EXPOSURE"] == "pass"


def test_the_banks_own_director_on_the_board_is_connected_lending():
    r = kg.assess(_graph(), "A1", CFG)
    [o] = r["officials"]
    assert o["name"].startswith("Lata") and o["role"] == "Director, Test Bank"
    assert {c["code"]: c["status"] for c in kg.checks(r)}["KG_CONNECTED_LENDING"] == "fail"


def test_a_masked_din_shared_by_two_people_does_not_connect_their_companies():
    g = _graph()
    b, c = kg.assess(g, "B1", CFG), kg.assess(g, "C1", CFG)
    assert [m["name"] for m in b["group"]] == ["Beta Foods Ltd"] and [m["name"] for m in c["group"]] == ["Gamma Agro Ltd"]
    assert not b["stressed"] and kg.checks(b)[0]["status"] == "pass"


def test_person_names_match_with_initials_but_not_on_surname_alone():
    assert kg.same_person("D. P. Agarwal", "D P AGARWAL")
    assert kg.same_person("Arvind Chitale", "Arvind B. Chitale")
    assert kg.same_person("Suresh K. Menon", "SURESH KUMAR MENON")
    assert not kg.same_person("D. P. Agarwal", "Urmila Agarwal")
    assert not kg.same_person("Vineet Agarwal", "Chander Agarwal")


def test_without_a_network_or_capital_the_checks_are_not_verified():
    g = kg.build({"B1": _companies()["B1"]}, [], None, {}, demo_enabled=False)
    by = {c["code"]: c["status"] for c in kg.checks(kg.assess(g, "B1", {}))}
    assert by["KG_GROUP_EXPOSURE"] == "not_verified"
    assert kg.checks(None)[0]["status"] == "not_verified"


def test_graph_checks_join_the_mandatory_checks():
    from src.flow import checks as chk
    base = {"items": [chk.item("HR_KYC_COMPLETE", "pass")], "basis": "initiation", "demo": False}
    merged = chk.merge(base, kg.checks(kg.assess(_graph(), "A1", CFG)))
    v = chk.view(merged, {"KG_CONNECTED_LENDING": {"kind": "justified", "note": "Director recused; board approval on file"}})
    assert v["total"] == 4 and len(v["failed"]) == 3 and v["open"] == 2       # one failure answered by a note
    assert chk.plain("KG_GROUP_EXPOSURE") == "Group exposure within limits"


def test_mart_snapshot_writes_every_table_locally(tmp_path):
    from src.application.container import build_container
    from src.core.mart import SCHEMA, Mart

    flow = build_container().flow
    m = Mart(flow, dataset=None, local_dir=tmp_path)
    res = m.sync(force=True)
    assert res["error"] is None and set(res["rows"]) == set(SCHEMA)
    assert res["rows"]["kg_nodes"] > 0 and (tmp_path / "kg_edges.jsonl").exists()
    assert m.sync() is None                                     # nothing changed: no second write
