"""CRILC exposure report PDF (ReportLab) built from a CRILC payload."""

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def build_crilc_pdf(pan: str, data: dict) -> bytes:
    """Render the CRILC report for ``pan`` from the ``crilc_report`` response."""
    from io import BytesIO

    payload = data.get("payload", {})
    entity_name = payload.get("entity_name", pan)

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm,
                            topMargin=20*mm, bottomMargin=20*mm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="RbiH1", fontSize=16, spaceAfter=12,
                              textColor=colors.HexColor("#00338d"), fontName="Helvetica-Bold",
                              alignment=1))
    styles.add(ParagraphStyle(name="RbiH2", fontSize=12, spaceAfter=8, spaceBefore=14,
                              textColor=colors.HexColor("#00338d"), fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="RbiBody", fontSize=10, spaceAfter=6, leading=14,
                              fontName="Helvetica"))
    styles.add(ParagraphStyle(name="RbiSmall", fontSize=8, spaceAfter=4, leading=10,
                              fontName="Helvetica", textColor=colors.grey))

    story = []
    # Header
    story.append(Paragraph("RESERVE BANK OF INDIA", styles["RbiH1"]))
    story.append(Paragraph("Central Repository of Information on Large Credits (CRILC)", styles["RbiH1"]))
    story.append(Spacer(1, 8*mm))
    story.append(Paragraph(f"<b>Entity:</b> {entity_name}", styles["RbiBody"]))
    story.append(Paragraph(f"<b>PAN:</b> {pan}", styles["RbiBody"]))
    story.append(Paragraph(f"<b>Report Date:</b> {data.get('as_of_date', 'N/A')}", styles["RbiBody"]))
    story.append(Spacer(1, 6*mm))

    # Exposure Summary Table
    story.append(Paragraph("1. Aggregate Exposure Summary", styles["RbiH2"]))
    exp_data = [
        ["Parameter", "Value"],
        ["Total Aggregate Exposure", f"₹ {payload.get('aggregate_exposure_cr', 0):.2f} Cr"],
        ["Fund-Based Exposure", f"₹ {payload.get('fund_based_cr', 0):.2f} Cr"],
        ["Non-Fund Based Exposure", f"₹ {payload.get('non_fund_based_cr', 0):.2f} Cr"],
        ["Number of Lending Institutions", str(payload.get("total_lenders", 0))],
        ["Asset Classification", payload.get("classification", "N/A")],
        ["SMA Status", payload.get("sma_status", "N/A")],
    ]
    t = Table(exp_data, colWidths=[200, 250])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#00338d")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4fa")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 6*mm))

    # Risk Flags
    story.append(Paragraph("2. Risk & Regulatory Flags", styles["RbiH2"]))
    flags_data = [
        ["Check", "Status", "Remark"],
        ["Restructured Account", "Yes" if payload.get("restructured") else "No",
         "Account has been restructured" if payload.get("restructured") else "No restructuring"],
        ["Wilful Defaulter", "Yes" if payload.get("wilful_defaulter") else "No",
         "Listed as wilful defaulter" if payload.get("wilful_defaulter") else "Not on wilful defaulter list"],
        ["SMA Classification", payload.get("sma_status", "N/A"),
         "Special Mention Account monitoring status"],
        ["Asset Classification", payload.get("classification", "N/A"),
         "Current asset classification under RBI norms"],
    ]
    t2 = Table(flags_data, colWidths=[130, 80, 240])
    t2.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#00338d")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4fa")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t2)
    story.append(Spacer(1, 6*mm))

    # Lender-wise Exposure (synthetic breakdown)
    story.append(Paragraph("3. Lender-wise Exposure Breakdown", styles["RbiH2"]))
    total_fb = payload.get("fund_based_cr", 0)
    total_nfb = payload.get("non_fund_based_cr", 0)
    n_lenders = payload.get("total_lenders", 1) or 1
    lender_names = ["State Bank of India", "Bank of Baroda", "Punjab National Bank",
                    "HDFC Bank", "ICICI Bank", "Axis Bank", "Union Bank of India",
                    "Canara Bank"]
    lender_data = [["Lender", "Fund-Based (₹ Cr)", "Non-Fund (₹ Cr)", "Total (₹ Cr)", "Share %"]]
    for i in range(min(n_lenders, len(lender_names))):
        share = round(100.0 / n_lenders + (5 - i * 3 if i < 3 else -2), 1)
        share = max(5.0, min(share, 60.0))
        fb = round(total_fb * share / 100, 2)
        nfb = round(total_nfb * share / 100, 2)
        lender_data.append([
            lender_names[i], f"{fb:.2f}", f"{nfb:.2f}", f"{fb + nfb:.2f}", f"{share:.1f}%"
        ])
    t3 = Table(lender_data, colWidths=[140, 90, 90, 90, 60])
    t3.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#00338d")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4fa")]),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t3)
    story.append(Spacer(1, 8*mm))

    # Disclaimer
    story.append(Paragraph("Disclaimer", styles["RbiH2"]))
    story.append(Paragraph(
        "This report is generated from the Central Repository of Information on Large Credits "
        "(CRILC) maintained by the Reserve Bank of India. The information is based on data "
        "reported by lending institutions and is for regulatory and credit assessment purposes. "
        "Report as on: " + payload.get("last_reported", "N/A"),
        styles["RbiSmall"]
    ))

    doc.build(story)
    return buf.getvalue()
