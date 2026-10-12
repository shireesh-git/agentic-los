"""
CRILC Report Generator
======================
Generates synthetic CRILC (Central Repository of Information on Large Credits)
reports as realistic PDF files.

CRILC reports are submitted by banks to RBI and contain:
  - Fund-based exposure (term loans, working capital, cash credit)
  - Non-fund-based exposure (BG, LC, derivatives)
  - DPD (Days Past Due) information
  - Asset classification (Standard/SMA/NPA)
  - SMA-0, SMA-1, SMA-2 flags
"""

import logging
from datetime import date, datetime
from pathlib import Path

from src.core.runtime_paths import DOCUMENTS_ROOT
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable, PageBreak,
)

logger = logging.getLogger(__name__)

# ─── CRILC Data Templates ────────────────────────────────────────────────────

CRILC_DATA: dict[str, dict] = {
    "INFY001": {
        "borrower_name": "Infosys Limited",
        "cin": "L85110KA1981PLC013115",
        "pan": "AAACI3456C",
        "sector": "Information Technology",
        "group": "Infosys Group",
        "credit_rating": "CRISIL AAA / Stable",
        "reporting_date": "31-Mar-2025",
        "reporting_bank": "State Bank of India",
        "bank_code": "SBI001",
        "fund_based": [
            {
                "facility_type": "Working Capital — Cash Credit",
                "sanction_limit_cr": 200.00,
                "outstanding_cr": 85.00,
                "dpd": 0,
                "classification": "Standard",
                "sma_flag": "None",
                "security": "First charge on current assets",
            },
            {
                "facility_type": "Working Capital — WCDL",
                "sanction_limit_cr": 150.00,
                "outstanding_cr": 120.00,
                "dpd": 0,
                "classification": "Standard",
                "sma_flag": "None",
                "security": "Pari-passu charge on current assets",
            },
        ],
        "non_fund_based": [
            {
                "facility_type": "Bank Guarantee — Performance",
                "sanction_limit_cr": 100.00,
                "outstanding_cr": 62.00,
                "dpd": 0,
                "classification": "Standard",
                "invoked": "No",
            },
            {
                "facility_type": "Letter of Credit — Inland",
                "sanction_limit_cr": 50.00,
                "outstanding_cr": 18.00,
                "dpd": 0,
                "classification": "Standard",
                "invoked": "No",
            },
        ],
        "aggregate_exposure": {
            "total_fund_based_sanction": 350.00,
            "total_fund_based_outstanding": 205.00,
            "total_non_fund_based_sanction": 150.00,
            "total_non_fund_based_outstanding": 80.00,
            "total_exposure_sanction": 500.00,
            "total_exposure_outstanding": 285.00,
        },
        "sma_history": [
            {"month": "Mar-2025", "sma_0": 0, "sma_1": 0, "sma_2": 0, "classification": "Standard"},
            {"month": "Feb-2025", "sma_0": 0, "sma_1": 0, "sma_2": 0, "classification": "Standard"},
            {"month": "Jan-2025", "sma_0": 0, "sma_1": 0, "sma_2": 0, "classification": "Standard"},
            {"month": "Dec-2024", "sma_0": 0, "sma_1": 0, "sma_2": 0, "classification": "Standard"},
            {"month": "Nov-2024", "sma_0": 0, "sma_1": 0, "sma_2": 0, "classification": "Standard"},
            {"month": "Oct-2024", "sma_0": 0, "sma_1": 0, "sma_2": 0, "classification": "Standard"},
        ],
    },
    "APOL001": {
        "borrower_name": "Apollo Hospitals Enterprise Limited",
        "cin": "L85110TN1979PLC008035",
        "pan": "AAACA1234K",
        "sector": "Healthcare",
        "group": "Apollo Group",
        "credit_rating": "ICRA AA+ / Stable",
        "reporting_date": "31-Mar-2025",
        "reporting_bank": "State Bank of India",
        "bank_code": "SBI001",
        "fund_based": [
            {
                "facility_type": "Term Loan — Hospital Capex",
                "sanction_limit_cr": 400.00,
                "outstanding_cr": 320.00,
                "dpd": 0,
                "classification": "Standard",
                "sma_flag": "None",
                "security": "First charge on movable/immovable assets of Apollo Health City, Hyderabad",
            },
            {
                "facility_type": "Working Capital — Cash Credit",
                "sanction_limit_cr": 150.00,
                "outstanding_cr": 95.00,
                "dpd": 0,
                "classification": "Standard",
                "sma_flag": "None",
                "security": "First charge on current assets (hypothecation)",
            },
            {
                "facility_type": "Working Capital — WCDL",
                "sanction_limit_cr": 100.00,
                "outstanding_cr": 78.00,
                "dpd": 0,
                "classification": "Standard",
                "sma_flag": "None",
                "security": "Pari-passu charge on current assets",
            },
        ],
        "non_fund_based": [
            {
                "facility_type": "Bank Guarantee — Performance",
                "sanction_limit_cr": 75.00,
                "outstanding_cr": 42.00,
                "dpd": 0,
                "classification": "Standard",
                "invoked": "No",
            },
            {
                "facility_type": "Letter of Credit — Import (Medical Equipment)",
                "sanction_limit_cr": 50.00,
                "outstanding_cr": 35.00,
                "dpd": 0,
                "classification": "Standard",
                "invoked": "No",
            },
        ],
        "aggregate_exposure": {
            "total_fund_based_sanction": 650.00,
            "total_fund_based_outstanding": 493.00,
            "total_non_fund_based_sanction": 125.00,
            "total_non_fund_based_outstanding": 77.00,
            "total_exposure_sanction": 775.00,
            "total_exposure_outstanding": 570.00,
        },
        "sma_history": [
            {"month": "Mar-2025", "sma_0": 0, "sma_1": 0, "sma_2": 0, "classification": "Standard"},
            {"month": "Feb-2025", "sma_0": 0, "sma_1": 0, "sma_2": 0, "classification": "Standard"},
            {"month": "Jan-2025", "sma_0": 0, "sma_1": 0, "sma_2": 0, "classification": "Standard"},
            {"month": "Dec-2024", "sma_0": 0, "sma_1": 0, "sma_2": 0, "classification": "Standard"},
            {"month": "Nov-2024", "sma_0": 0, "sma_1": 0, "sma_2": 0, "classification": "Standard"},
            {"month": "Oct-2024", "sma_0": 0, "sma_1": 0, "sma_2": 0, "classification": "Standard"},
        ],
    },
}


def generate_crilc_report(entity_id: str) -> dict:
    """
    Generate a synthetic CRILC report PDF for the given entity.

    Returns dict with status, file path, and summary.
    """
    if entity_id not in CRILC_DATA:
        return {
            "status": "error",
            "entity_id": entity_id,
            "message": f"No CRILC data configured for {entity_id}. "
                       f"Supported: {list(CRILC_DATA.keys())}",
        }

    data = CRILC_DATA[entity_id]
    storage_root = DOCUMENTS_ROOT / entity_id
    output_dir = storage_root / "bureau"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "crilc_report.pdf"

    _build_crilc_pdf(data, output_file)

    return {
        "status": "success",
        "entity_id": entity_id,
        "file": str(output_file),
        "relative_path": f"bureau/crilc_report.pdf",
        "summary": {
            "borrower": data["borrower_name"],
            "total_exposure_sanction": data["aggregate_exposure"]["total_exposure_sanction"],
            "total_exposure_outstanding": data["aggregate_exposure"]["total_exposure_outstanding"],
            "classification": "Standard",
            "sma_flag": "None",
        },
    }


def _build_crilc_pdf(data: dict, output_file: Path):
    """Build the actual CRILC PDF document."""

    doc = SimpleDocTemplate(
        str(output_file),
        pagesize=landscape(A4),
        topMargin=1.5 * cm,
        bottomMargin=1.2 * cm,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("CTitle", parent=styles["Title"], fontSize=14, spaceAfter=6, textColor=colors.HexColor("#1a365d"))
    subtitle_style = ParagraphStyle("CSub", parent=styles["Normal"], fontSize=10, alignment=1, spaceAfter=4)
    section_style = ParagraphStyle("CSect", parent=styles["Heading3"], fontSize=11, spaceBefore=10, textColor=colors.HexColor("#2d3748"))
    note_style = ParagraphStyle("CNote", parent=styles["Normal"], fontSize=7, textColor=colors.grey)
    small_style = ParagraphStyle("CSmall", parent=styles["Normal"], fontSize=8, leading=10)

    elements = []

    # Header
    elements.append(Paragraph("RESERVE BANK OF INDIA", title_style))
    elements.append(Paragraph("<b>CENTRAL REPOSITORY OF INFORMATION ON LARGE CREDITS (CRILC)</b>", subtitle_style))
    elements.append(Paragraph("Report generated as per RBI Circular DBS.No.OSMOS.9862/33.01.001/2013-14", note_style))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1a365d")))
    elements.append(Spacer(1, 0.4 * cm))

    # Borrower Information
    elements.append(Paragraph("Section A: Borrower Information", section_style))
    info_data = [
        ["Borrower Name", data["borrower_name"], "CIN", data["cin"]],
        ["PAN", data["pan"], "Sector", data["sector"]],
        ["Group", data["group"], "Credit Rating", data["credit_rating"]],
        ["Reporting Date", data["reporting_date"], "Reporting Bank", data["reporting_bank"]],
    ]
    info_tbl = Table(info_data, colWidths=[4 * cm, 8 * cm, 4 * cm, 8 * cm])
    info_tbl.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#edf2f7")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#edf2f7")),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(info_tbl)
    elements.append(Spacer(1, 0.4 * cm))

    # Fund-Based Exposure
    elements.append(Paragraph("Section B: Fund-Based Exposure", section_style))
    fb_header = ["Facility Type", "Sanction Limit (₹ Cr)", "Outstanding (₹ Cr)", "DPD", "Classification", "SMA Flag", "Security"]
    fb_data = [fb_header]
    for fb in data["fund_based"]:
        fb_data.append([
            fb["facility_type"],
            f"{fb['sanction_limit_cr']:,.2f}",
            f"{fb['outstanding_cr']:,.2f}",
            str(fb["dpd"]),
            fb["classification"],
            fb["sma_flag"],
            Paragraph(fb.get("security", "—"), small_style),
        ])

    fb_tbl = Table(fb_data, colWidths=[5 * cm, 3 * cm, 3 * cm, 1.5 * cm, 2.5 * cm, 2 * cm, 7 * cm])
    fb_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2d3748")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("ALIGN", (1, 0), (3, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7fafc")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(fb_tbl)
    elements.append(Spacer(1, 0.3 * cm))

    # Non-Fund Based Exposure
    elements.append(Paragraph("Section C: Non-Fund Based Exposure", section_style))
    nfb_header = ["Facility Type", "Sanction Limit (₹ Cr)", "Outstanding (₹ Cr)", "DPD", "Classification", "Invoked"]
    nfb_data = [nfb_header]
    for nfb in data["non_fund_based"]:
        nfb_data.append([
            nfb["facility_type"],
            f"{nfb['sanction_limit_cr']:,.2f}",
            f"{nfb['outstanding_cr']:,.2f}",
            str(nfb["dpd"]),
            nfb["classification"],
            nfb["invoked"],
        ])

    nfb_tbl = Table(nfb_data, colWidths=[6 * cm, 3.5 * cm, 3.5 * cm, 2 * cm, 3 * cm, 2 * cm])
    nfb_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2d3748")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("ALIGN", (1, 0), (3, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7fafc")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(nfb_tbl)

    elements.append(PageBreak())

    # Aggregate Exposure Summary
    elements.append(Paragraph("Section D: Aggregate Exposure Summary", section_style))
    agg = data["aggregate_exposure"]
    agg_data = [
        ["Category", "Sanction (₹ Cr)", "Outstanding (₹ Cr)", "Utilization %"],
        ["Fund-Based", f"{agg['total_fund_based_sanction']:,.2f}", f"{agg['total_fund_based_outstanding']:,.2f}",
         f"{(agg['total_fund_based_outstanding']/agg['total_fund_based_sanction']*100):.1f}%"],
        ["Non-Fund Based", f"{agg['total_non_fund_based_sanction']:,.2f}", f"{agg['total_non_fund_based_outstanding']:,.2f}",
         f"{(agg['total_non_fund_based_outstanding']/agg['total_non_fund_based_sanction']*100):.1f}%"],
        ["TOTAL", f"{agg['total_exposure_sanction']:,.2f}", f"{agg['total_exposure_outstanding']:,.2f}",
         f"{(agg['total_exposure_outstanding']/agg['total_exposure_sanction']*100):.1f}%"],
    ]
    agg_tbl = Table(agg_data, colWidths=[5 * cm, 4 * cm, 4 * cm, 3 * cm])
    agg_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a365d")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#edf2f7")),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e0")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(agg_tbl)
    elements.append(Spacer(1, 0.5 * cm))

    # SMA History
    elements.append(Paragraph("Section E: SMA Monitoring History (Last 6 Months)", section_style))
    sma_header = ["Month", "SMA-0 (1-30 DPD)", "SMA-1 (31-60 DPD)", "SMA-2 (61-90 DPD)", "Asset Classification"]
    sma_data = [sma_header]
    for s in data["sma_history"]:
        sma_data.append([
            s["month"],
            "Yes" if s["sma_0"] else "No",
            "Yes" if s["sma_1"] else "No",
            "Yes" if s["sma_2"] else "No",
            s["classification"],
        ])
    sma_tbl = Table(sma_data, colWidths=[4 * cm, 4 * cm, 4 * cm, 4 * cm, 4 * cm])
    sma_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2d3748")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7fafc")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(sma_tbl)

    elements.append(Spacer(1, 1 * cm))
    elements.append(Paragraph(
        "This report is generated from the Central Repository of Information on Large Credits (CRILC) system "
        "maintained by the Reserve Bank of India as per the extant guidelines. The data reflects the position "
        "as on the reporting date. Banks are required to report all borrower exposures of ₹5 crore and above.",
        note_style,
    ))
    elements.append(Spacer(1, 0.3 * cm))
    elements.append(Paragraph(
        f"Report generated on: {datetime.now().strftime('%d-%b-%Y %H:%M')} | "
        f"Reference: CRILC/{data['bank_code']}/{data['cin']}/{data['reporting_date'].replace('-','')}",
        note_style,
    ))

    doc.build(elements)
    logger.info(f"Generated CRILC report: {output_file}")


def get_crilc_data(entity_id: str) -> dict | None:
    """Get CRILC data for an entity (for direct consumption by fact builder)."""
    return CRILC_DATA.get(entity_id)
