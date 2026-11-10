"""Back-test on past proposals (roadmap P1): point in time, real engine, scorecard."""

import pytest

from src.flow import backtest as bt


def test_scorecard_counts_caught_missed_and_false_alarms():
    rows = [{"borrower": "A", "outcome": "stressed", "flagged": True, "fired": {"limit_above": True}},
            {"borrower": "B", "outcome": "npa", "flagged": False, "fired": {}},
            {"borrower": "C", "outcome": "performing", "flagged": True, "fired": {"limit_above": True}},
            {"borrower": "D", "outcome": "performing", "flagged": False, "fired": {}},
            {"borrower": "E", "outcome": "performing", "error": "no statements"}]
    s = bt.scorecard(rows)
    assert (s["bad"], s["caught"], s["missed"], s["good"], s["false_alarms"], s["errors"]) == (2, 1, ["B"], 2, 1, 1)
    lim = next(x for x in s["by_signal"] if x["id"] == "limit_above")
    assert (lim["on_bad"], lim["on_good"], lim["precision_pct"]) == (1, 1, 50)


@pytest.fixture(scope="module")
def companies():
    from src.application.container import build_container
    return build_container().flow.companies


def test_a_case_runs_on_the_record_as_it_stood(companies):
    from src.services.persistence import persistence

    def runs():
        with persistence._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM case_runs").fetchone()[0]

    before = runs()
    r = bt.run_case({"entity_id": "MFL001", "as_of": "FY2024", "outcome": "stressed", "amount_cr": 120}, companies)
    assert not r.get("error"), r.get("error")
    assert r["periods"] == ["FY2023", "FY2024"]                     # no FY2025 figures
    assert r["flagged"] and r["fired"]["decline"] and r["why"]
    assert runs() == before                                           # nothing saved to the live runs
    # the live borrower record is untouched
    assert "FY2025" in companies["MFL001"]["financials"] and companies["MFL001"]["facility"].amount_requested_cr != 0


def test_the_notes_reader_reads_only_reports_up_to_the_as_of_year(tmp_path):
    from src.engines import notes_reader as nr
    for y in (2023, 2024, 2025):
        (tmp_path / f"annual_report_fy{y}.pdf").write_bytes(b"%PDF")
    assert nr.find_report(tmp_path, 2024).name == "annual_report_fy2024.pdf"
    assert nr.find_report(tmp_path).name == "annual_report_fy2025.pdf"
