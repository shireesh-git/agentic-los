"""Statement units (lakhs vs crores) and the 9-month column of exchange results tables."""

from pathlib import Path

import pytest

from src.engines.document_ocr_engine import detect_statement_unit
from src.services.document_extractor import _nine_month_revenue

DOCS = Path(__file__).resolve().parents[1] / "storage" / "documents"


@pytest.mark.parametrize("text, unit", [
    ("(₹ in Lakhs)", "lakhs"),
    ("(` In lakhs)", "lakhs"),                 # rupee glyph extracted as a backtick
    ("Rs. in Lacs", "lakhs"),
    ("(Figures in i crores)", "crores"),       # rupee glyph extracted as an 'i'
    ("(Amount in ₹ crores)", "crores"),
    ("India will spend ` 10 lakh crore", None),     # narrative, not a caption
    ("GST collections of ` 1.87 lakhs Cr", None),
    ("investment in 3 lakh crore projects", None),
    ("", None),
])
def test_detect_statement_unit(text, unit):
    assert detect_statement_unit(text) == unit


def test_unit_is_the_most_frequent_caption():
    text = "(₹ in Lakhs) … (₹ in Lakhs) … Highlights (₹ in crores) … (₹ in Lakhs)"
    assert detect_statement_unit(text) == "lakhs"


def test_nine_month_revenue_reads_the_9m_column_not_the_quarter():
    text = ("Financial Results for Q3 FY2025 (Oct-Dec 2024)\nParticulars (₹ Cr)\nQ3 FY2025\n9M FY2025\n"
            "Revenue from Operations\n1,782.04\n5,346.12\nTotal Income\n1,908.14\n5,724.42\n")
    assert _nine_month_revenue(text) == 5346.12
    assert _nine_month_revenue("Particulars\nQ3 FY2025\nRevenue from Operations\n1,782.04") is None


@pytest.mark.skipif(not (DOCS / "PNCR001").exists(), reason="demo documents not present")
def test_real_documents():
    from src.engines.document_ocr_engine import extract_text_pymupdf
    from src.services.document_extractor import extract_exchange_filing_from_pdf

    text = extract_text_pymupdf(DOCS / "PNCR001" / "financials" / "audited_financial_statements.pdf")["text"]
    assert detect_statement_unit(text) == "lakhs"
    ihcl = extract_exchange_filing_from_pdf(DOCS / "IHCL001" / "exchange" / "quarterly_results_q3fy2025.pdf")
    assert ihcl["data"]["nine_month_revenue"] == 5346.12
