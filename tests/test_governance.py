"""AI governance pack (roadmap L2)."""

from src.flow import governance


def _case(**kw):
    base = {"case_id": "LOS-1", "borrower_name": "Infosys Limited", "status": "open",
            "cam": {"mode": "generate", "narrative_mode": "llm", "model": "gemini-3.8-flash", "llm_calls": 8,
                    "sections_written": 8, "sections_reused": 0,
                    "figure_check": {"sections_checked": 8, "rewritten": ["Financial Performance"],
                                     "flagged": [{"section": "conduct", "title": "Conduct & Compliance",
                                                  "figures": ["3,625.00", "1,750.00"]}], "models": ["gemini-3.8-flash"]}},
            "chat": [{"from": "agent", "kind": "answer", "provenance": "ai", "text": "Risks: …"},
                     {"from": "agent", "kind": "answer", "provenance": "lookup",
                      "text": "From the record … (The AI answer was rejected (quoted figures not in the record))"}],
            "decisions": [{"at": "2026-11-09T10:00:00", "stage_label": "Origination", "by": "Ananya Rao",
                           "action": "approve", "comment": "Submitted"}],
            "changes": [], "against": [], "responses": {}, "deviations": [],
            "checks": {"items": [{"code": "HR_BUREAU_STATUS", "label": "Bureau status", "status": "not_verified",
                                  "status_label": "Not verified", "source": "", "evidence": "bureau report",
                                  "demo": True}], "demo": True},
            "check_notes": {"HR_BUREAU_STATUS": {"kind": "verified", "note": "CIBIL CMR seen", "by": "Rahul Mehta",
                                                 "role": "Underwriting", "at": "2026-11-09"}}}
    return {**base, **kw}


def test_pack_records_ai_use_figure_check_people_data_and_fairness():
    p = governance.build(_case(), [], "2026-11-09 12:00")
    assert p["cam"]["figure_check"]["flagged"][0]["figures"] == ["3,625.00", "1,750.00"]
    assert p["copilot"] == {"answers": 2, "ai": 1, "rejected": 1, "record_lookup": 1}
    assert p["people"]["decisions"][0]["by"] == "Ananya Rao"
    assert p["people"]["check_notes"][0]["by"] == "Rahul Mehta" and p["data"]["checks_demo"]
    assert p["fairness"]["found"] == [] and "No protected attribute" in p["fairness"]["result"]
    ia = {q["question"]: q["answer"] for q in p["impact_assessment"]}
    assert "Ananya Rao" in ia["What decision does the AI influence, and who makes it?"]
    assert "2 figure(s) in 1 section(s) to verify" in ia["How are AI errors caught?"]
    assert p["model_card"]["ai_does_not"] and p["deployment"]["prompt_version"]
    page = governance.html(p)
    assert "AI Governance Pack" in page and "3,625.00" in page and "Rahul Mehta" in page


def test_template_cam_says_no_ai_narrative():
    case = _case(cam={"mode": "generate", "narrative_mode": "template"})
    page = governance.html(governance.build(case, [], "now"))
    assert "not written by AI" in page
