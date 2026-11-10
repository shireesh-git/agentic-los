"""Notes-to-accounts reader (roadmap P3): sections located, rules reading, grounding, sanity checks, flow."""

from src.engines import notes_reader as nr

PAGES = [
    "Directors' report. The company has a good year.",
    "INDEPENDENT AUDITOR'S REPORT To the Members. Opinion. In our opinion the standalone financial statements give a "
    "true and fair view. Emphasis of Matter: a. We draw attention to Note 30 regarding penal interest on GOI loans "
    "which is pending waiver by the Government of India.",
    "Key Audit Matters. Recognition of subsidy income. The auditor evaluates management's use of the going concern "
    "basis of accounting.",
    "Annexure A to the Independent Auditor's Report. Companies (Auditor's Report) Order, 2020 (CARO). (ix) (a) The "
    "Company has defaulted in repayment of loans to the Government of India amounting to Rs 120 crore. (b) The Company "
    "has not been declared a wilful defaulter by any bank. (xi) (a) No fraud by the Company has been noticed or reported.",
    "Balance Sheet as at 31 March 2025 ...",
    "Note 41 Contingent liabilities. Claims against the company not acknowledged as debts Rs 53 crore.",
    "Report on internal financial controls. Qualified Opinion. Material weaknesses in internal financial controls "
    "over financial reporting were identified in the purchase department.",
]


def test_sections_are_located():
    s = nr.locate(PAGES)
    assert s["auditor"][0] == 1 and 3 in s["caro"] and s["contingent"] == [5]
    assert 6 in s.get("caro", []) + s.get("flagged", [])                   # the controls report is read too


def test_rules_read_the_standard_wording():
    r = nr.read_by_rules(PAGES, nr.locate(PAGES))
    by = {f["topic"]: f for f in r["findings"]}
    assert by["caro_default"]["severity"] == "high" and by["caro_default"]["page"] == 4
    assert by["caro_wilful_defaulter"]["severity"] == "info"               # "has not been declared"
    assert by["caro_fraud"]["severity"] == "info"                          # "No fraud ... noticed"
    assert by["emphasis_of_matter"]["severity"] == "medium" and "penal interest" in by["emphasis_of_matter"]["quote"].lower()
    # the qualified opinion is on internal financial controls, not on the accounts
    assert by["ifc_opinion"]["severity"] == "medium" and r["opinion"] == "unmodified"
    assert "going_concern" not in by                                       # the auditor's boilerplate is not a finding


def test_findings_whose_quote_is_not_on_the_page_are_dropped():
    model = {"opinion": "unmodified", "findings": [
        {"topic": "caro_default", "severity": "high", "finding": "Default to GOI", "page": 4,
         "quote": "The Company has defaulted in repayment of loans to the Government of India"},
        {"topic": "caro_default", "severity": "high", "finding": "Default named on the wrong page", "page": 2,
         "quote": "The Company has defaulted in repayment of loans to the Government of India"},
        {"topic": "going_concern", "severity": "high", "finding": "Invented", "page": 3,
         "quote": "There is a material uncertainty related to going concern"}]}
    kept, dropped = nr.ground(model, PAGES, set(range(len(PAGES))))
    assert dropped == 1 and [f["page"] for f in kept] == [4, 4]           # the misplaced one moves to its page


def test_a_red_flag_must_be_borne_out_by_its_own_quote():
    f = {"topic": "caro_default", "severity": "high", "finding": "Default", "page": 4,
         "quote": "(b) The Company has not been declared a wilful defaulter by any bank"}
    assert nr._sane(f, PAGES)["topic"] == "caro_default"                   # "defaulter" contains "default"
    f2 = {**f, "quote": "No fraud by the Company has been noticed or reported"}
    assert nr._sane(f2, PAGES)["severity"] == "low"
    f3 = {"topic": "audit_opinion", "severity": "high", "finding": "Qualified", "page": 7,
          "quote": "Qualified Opinion. Material weaknesses in internal financial controls"}
    assert nr._sane(f3, PAGES)["topic"] == "ifc_opinion"


def test_the_flow_turns_red_flags_into_a_challenge():
    from src.flow import risk as rk
    notes = {"available": True, "document": "annual_report_fy2025.pdf", "opinion": "unmodified", "red_flags": 1,
             "findings": [{"topic": "caro_default", "label": "CARO: default to lenders", "severity": "high",
                           "finding": "Default to GOI", "quote": "has defaulted", "page": 4}]}
    engine = {"fact_pack": {"notes_to_accounts": notes}, "recommendation": "approve", "challenges": []}
    assert rk.assess(engine)["notes"]["red_flags"] == 1
    ch = rk.challenges(engine)[0]
    assert ch["rule_id"] == "NOTES_RED_FLAGS" and ch["severity"] == "HIGH" and "p.4" in ch["what"]
    assert {a["kind"] for a in ch["actions"]} == {"send_back", "justify", "reject"}
