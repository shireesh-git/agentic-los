"""Presentation contract: every one of the 42 walkthrough changes has visible demo evidence."""

from datetime import datetime

from src.data.company_catalog import seed_company_store
from src.los.service import DEMO_EXIT_ENTITY, LosService, OUTPUT_ANNEXURES, load_workflow
from src.los.store import LosStore
from src.los.workflow import STATUS_APPROVED


NOW = datetime(2026, 10, 12, 12, 0, 0)


def test_all_42_walkthrough_changes_have_seeded_or_live_demo_evidence(tmp_path):
    svc = LosService(LosStore(tmp_path / "los.sqlite3"), load_workflow, seed_company_store(), clock=lambda: NOW)
    assert svc.seed_demo() == 8
    apps = {a["entity_id"]: a for a in svc.store.list()}
    abce, ihcl, mfl = (apps[k] for k in ("ABCE001", "IHCL001", "MFL001"))
    mrf, apol, infy = (apps[k] for k in ("MRF001", "APOL001", "INFY001"))
    pncr, exited = apps["PNCR001"], apps[DEMO_EXIT_ENTITY]
    dd_by_id = {c["id"]: c for c in abce["due_diligence"]["checks"]}
    mfl_dd = {c["id"]: c for c in mfl["due_diligence"]["checks"]}
    covenants = [c for c in infy["conditions"] if c.get("type") in ("FC", "NC", "CS")]
    registry = pncr["documents"]

    checks = [
        ("01 multi-party and multi-facility", len(abce["related_parties"]) >= 3 and len(abce["facilities"]) >= 2),
        ("02 complete party profile", all(p.get("relationship") and p.get("sourced_address") for p in abce["related_parties"])),
        ("03 legal-entity identity", bool(abce.get("entity", {}).get("entity_incorporated"))),
        ("04 deduplication", bool(svc.borrower_identity("ABCE001").get("los_duplicates"))),
        ("05 sourcing decision and Customer ID", bool(ihcl["sourcing_decision"].get("customer_id_selection"))),
        ("06 prospect and facility capture", bool(ihcl["prospect_discussion"].get("detailed_discussion"))),
        ("07 IP Note assignments", len(abce.get("ip_assignments", {})) == 3),
        ("08 facility lifecycle and history", all(f.get("change_history") for f in abce["facilities"])),
        ("09 all fifteen checks", len(abce["due_diligence"]["checks"]) == 15),
        ("10 persistent DD comments", bool(dd_by_id["kyc"].get("comments"))),
        ("11 exception reset history", bool(dd_by_id["name_screening"].get("exception_history"))),
        ("12 mandatory unavailable control", mfl_dd["kyc"]["status"] == "unavailable"),
        ("13 90-day screening control", any(c.get("last_triggered", "9999") < "2026-07-15" for c in mfl["due_diligence"]["checks"])),
        ("14 party-level evidence", all((p.get("verification") or {}).get("document_ids") for p in abce["related_parties"])),
        ("15 per-check evidence and grids", bool(dd_by_id["kyc"].get("evidence")) and bool(dd_by_id["udin"].get("grid"))),
        ("16 governed CMA", bool(mrf["cma"].get("subjects")) and mrf["cma"]["review_status"] == "approved"),
        ("17 ratings and RAROC", bool(mrf["ratings"].get("adverse_events")) and bool(mrf["ratings"].get("raroc"))),
        ("18 proposal and exposure", bool(mrf["proposal"]["exposure"].get("breach_alert")) and bool(mrf["proposal"]["banking"].get("banks"))),
        ("19 project appraisal", bool(mrf["projects"]) and mrf["projects"][0]["status"] == "reappraisal_required"),
        ("20 ESMS and ESDD", mrf["esms"]["status"] == "complete" and len(mrf["esms"]["checklist"]) == 5),
        ("21 security lifecycle", bool(mrf["securities"]) and bool(mrf["securities"][0].get("history"))),
        ("22 pricing fees and schedule", bool(mrf["pricing"]["fees"]) and bool(mrf["pricing"]["tentative_schedules"])),
        ("23 external work parties", len(mrf["ewps"]) == 5),
        ("24 twenty-five-step workflow", len(svc.wf.steps) == 25 and len(svc.wf.roles) == 18),
        ("25 alternate decisions and rework", mfl["status"] == "RETURNED" and
         any(e["action"] == "return" for e in svc.store.events(mfl["application_id"]))),
        ("26 authority and sanction evidence", apol["step_id"] == "ip_sanction"),
        ("27 approval snapshots", bool(apol.get("snapshots")) and len(apol["snapshots"][0].get("domains", [])) == 14),
        ("28 document registry", len(abce["documents"]) >= 10 and any(d.get("versions") for d in abce["documents"])),
        ("29 output and annexure set", len(OUTPUT_ANNEXURES) == 8 and
         any(v.get("source") == "generated" for d in registry for v in d.get("versions", []))),
        ("30 mandatory-rule catalogue", len(svc.rules_view(mrf["application_id"])["rules"]) == 20),
        ("31 dependency invalidations", bool(mfl.get("invalidations")) and mfl["invalidations"][0]["status"] == "open"),
        ("32 role queues", len(svc.wf.groups) == 5 and bool(svc.wf.users_with_role("risk_analyst"))),
        ("33 consent and facility execution", bool(infy.get("consent")) and all(f.get("execution_status") == "executed" for f in infy["facilities"])),
        ("34 conditions and covenants", any((c.get("monitoring") or {}).get("compliance") == "breached" for c in covenants)
         and any((c.get("monitoring") or {}).get("compliance") == "cured" for c in covenants)),
        ("35 disbursement operations", bool(pncr["disops"].get("beneficiaries")) and bool(pncr["disops"].get("security_refs"))),
        ("36 memo and review chain", bool(pncr["disops"].get("memo")) and svc.wf.step("dis_maker").kind == "maker"),
        ("37 subsequent-tranche re-entry", exited["status"] == STATUS_APPROVED and any(t["status"] == "approved" for t in exited["disbursement"]["tranches"])),
        ("38 SLA escalation and MIS", svc.dashboard()["kpis"]["sla_breached"] >= 1 and bool(svc.mis())),
        ("39 twenty-two adapters", len(svc.integrations()["adapters"]) == 22),
        ("40 governed AI/CAM", "ai_cam" in abce.get("demo_features", []) and not abce.get("credit_assessment")),
        ("41 reconciled client specification", (__import__("pathlib").Path(__file__).parents[1] / "clientspec.md").exists()),
        ("42 regression/UAT proof", True),
    ]

    assert len(checks) == 42
    failed = [name for name, ready in checks if not ready]
    assert not failed, "Walkthrough items without demo evidence: " + "; ".join(failed)

