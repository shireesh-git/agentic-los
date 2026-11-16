"""The demo-document generator reads each listed borrower's data file (round 8: no data tables in code)."""

from src.engines.document_downloader import get_real_financials, get_supported_companies


def test_supported_companies_are_the_listed_borrowers_on_record():
    supported = {item["entity_id"]: item for item in get_supported_companies()}
    assert supported["INFY001"]["source"] == "borrower_record"
    assert (supported["INFY001"]["nse_symbol"], supported["INFY001"]["bse_code"]) == ("INFY", "500209")
    assert (supported["IHCL001"]["nse_symbol"], supported["IHCL001"]["bse_code"]) == ("INDHOTEL", "500850")
    assert "BJFN001" not in supported and "YESB001" not in supported


def test_financials_come_from_the_audited_statements_on_record():
    fin = get_real_financials("INFY001")
    assert fin["FY2026"]["revenue_from_operations"] == 148819.0       # standalone, FY2026 annual report
    assert set(fin) >= {"FY2024", "FY2025", "FY2026"}
