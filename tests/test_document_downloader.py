import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.engines.document_downloader import get_real_financials, get_supported_companies


def test_supported_companies_include_current_catalog_companies():
    supported = {item["entity_id"]: item for item in get_supported_companies()}
    assert "INFY001" in supported
    assert supported["INFY001"]["source"] == "hardcoded_real"
    assert supported["INFY001"]["nse_symbol"] == "INFY"
    assert supported["INFY001"]["bse_code"] == "500209"

    assert "IHCL001" in supported
    assert supported["IHCL001"]["source"] == "canonical_registry"
    assert supported["IHCL001"]["nse_symbol"] == "INDHOTEL"
    assert supported["IHCL001"]["bse_code"] == "500850"


def test_get_real_financials_maps_current_real_company_fields():
    financials = get_real_financials("INFY001")
    assert financials is not None
    assert financials["FY2025"]["revenue_from_operations"] == 162981.00
    assert financials["FY2025"]["profit_after_tax"] == 27234.00
    assert financials["FY2025"]["total_debt"] == 5241.00
