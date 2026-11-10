"""A Credit Appraisal Memorandum for H.G. Infra Engineering Limited in a typical bank's own format — prepared outside
the LOS, to test the "Ingest Bank CAM" journey (the CAM intake agent reads it into the credit data fields).

    python test-documents/hg_infra/bank_cam.py        → demo/bank_cam/HGIEL_CAM_demo_bank.pdf

Figures are the company's audited standalone statements (FY2024–FY2026, annual reports) and its published ratings
(CARE AA (Negative), 3 Sep 2026; ICRA AA- / A1+). The bank, its internal rating, the proposal, the assessment and the
terms are a demo prepared for testing ("Demo Bank Ltd." is fictional). Marked UAT DEMO on every page.
"""

from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "demo" / "bank_cam" / "HGIEL_CAM_demo_bank.pdf"
MARK = "UAT DEMO — bank-format CAM prepared for testing from public disclosures; Demo Bank Ltd. is fictional."

# ₹ crore, audited standalone (FY2026 report ₹ in million ÷ 10)
FY = {"FY2024": dict(rev=5121.74, ebitda=834.57, pat=545.49, nw=2318.49, debt=451.21, ca=2577.72, cl=1628.10, fin=96.4),
      "FY2025": dict(rev=6051.88, ebitda=965.94, pat=577.12, nw=2884.78, debt=1067.92, ca=3649.61, cl=2700.41, fin=135.9),
      "FY2026": dict(rev=5666.68, ebitda=762.41, pat=389.14, nw=3258.89, debt=1627.44, ca=4547.78, cl=3881.19, fin=178.50)}


def _rows():
    head = ["Particulars (Rs Cr)"] + list(FY)
    lines = [("Revenue from operations", "rev"), ("EBITDA", "ebitda"), ("Profit after tax", "pat"),
             ("Tangible net worth", "nw"), ("Total borrowings", "debt"), ("Current assets", "ca"),
             ("Current liabilities", "cl"), ("Finance cost", "fin")]
    rows = [head] + [[label] + [f"{FY[y][k]:,.2f}" for y in FY] for label, k in lines]
    rows.append(["EBITDA margin (%)"] + [f"{100 * FY[y]['ebitda'] / FY[y]['rev']:.1f}" for y in FY])
    rows.append(["Current ratio (x)"] + [f"{FY[y]['ca'] / FY[y]['cl']:.2f}" for y in FY])
    rows.append(["Debt / EBITDA (x)"] + [f"{FY[y]['debt'] / FY[y]['ebitda']:.2f}" for y in FY])
    rows.append(["Interest cover (x)"] + [f"{FY[y]['ebitda'] / FY[y]['fin']:.2f}" for y in FY])
    return rows


SECTIONS = [
    ("1. PROPOSAL SUMMARY", [
        {"Borrower": "H.G. Infra Engineering Limited", "CIN": "L45201RJ2003PLC018049",
         "Constitution": "Public limited company (listed on BSE and NSE)",
         "Sector": "Infrastructure", "Sub-sector": "Road and highway EPC, HAM projects, solar EPC",
         "Banking Arrangement": "Consortium (led by State Bank of India; Demo Bank to join as a new member)",
         "Proposal": "New fund-based working capital limit (cash credit / WCDL) — new to bank",
         "Amount Requested": "Rs 250.00 Cr", "Recommended Limit: Rs 200.00 Cr": "",
         "Tenor": "12 months, renewable", "Pricing": "1-year MCLR + 0.75% (9.15% p.a.), payable monthly",
         "Internal Rating": "DB-4 (moderate risk) on Demo Bank's 1–10 scale",
         "External Rating": "CARE AA (Negative) / ICRA AA- (Positive); ICRA A1+ for short-term facilities"}]),
    ("2. BACKGROUND OF THE COMPANY", [
        "H.G. Infra Engineering Limited (HGIEL), incorporated in 2003 and headquartered in Jodhpur, Rajasthan, is an "
        "EPC contractor for national and state highways, expressways, bridges and railway works, and has diversified "
        "into hybrid annuity model (HAM) road projects and solar EPC. Revenue was Rs 5,666.68 Cr in FY2026 against "
        "Rs 6,051.88 Cr in FY2025, the first decline in five years, after the cancellation of two large MSRTC EPC "
        "projects and slower commencement of new orders. The order book stood at about Rs 10,147 Cr (about 1.8x FY2026 "
        "revenue)."]),
    ("3. PROMOTERS AND MANAGEMENT", [
        "The company is promoted by Mr. Harendra Singh (Chairman & Managing Director), with over three decades in road "
        "construction; the promoter group holds about 72%. The board has four independent directors. The statutory "
        "auditors issued an unmodified opinion on the FY2026 standalone statements with an Emphasis of Matter on search "
        "proceedings by the Central Bureau of Investigation; management states there is no impact on the financial "
        "statements at this stage."]),
    ("4. INDUSTRY OUTLOOK", [
        "Road construction remains a government capital-expenditure priority, but award activity under HAM slowed in "
        "FY2026 and competitive intensity has compressed EPC margins. Working-capital cycles in the sector have "
        "lengthened on delayed change-of-scope payments and unbilled revenue on HAM projects."]),
    ("5. FINANCIAL PERFORMANCE", [_rows,
        "EBITDA margin fell from 16.0% in FY2025 to 13.5% in FY2026 and, per CARE, to 8.8% in Q1 FY2027. Gross current "
        "asset days rose from 218 to 277; borrowings rose to Rs 1,627 Cr as current assets were funded with short-term "
        "debt. Leverage remains moderate (debt / EBITDA 2.1x; tangible net worth Rs 3,259 Cr)."]),
    ("6. ASSESSMENT OF WORKING CAPITAL", [
        [["Particulars (Rs Cr)", "FY2027 projected"], ["Projected turnover", "5,200.00"],
         ["Total current assets", "5,700.00"], ["Other current liabilities", "2,225.00"],
         ["Working capital gap", "3,475.00"], ["Margin (25% of current assets)", "1,425.00"],
         ["Maximum permissible bank finance (method II)", "2,050.00"],
         ["Existing fund-based limits (consortium)", "1,800.00"], ["Proposed share of Demo Bank", "200.00"],
         ["Total fund-based limits after proposal", "2,000.00"]],
        "The total fund-based limits of Rs 2,000 Cr are within the MPBF of Rs 2,050 Cr assessed on the projected "
        "balance sheet, which assumes realisation of Rs 800–1,000 Cr from completed projects in FY2027."]),
    ("7. KEY RISKS AND MITIGANTS", [
        "Stretched working capital: GCA days of 277; mitigated by HAM monetisation (Rs 1,384 Cr SPA with Neo Infra Income "
        "Opportunities Fund, Rs 659 Cr received) and stock and book-debt statements with a 90-day receivable cut-off.",
        "Declining profitability: margins of 8.8% in Q1 FY2027; mitigated by an order book of 1.8x revenue and the "
        "completion of the legacy solar project; a minimum EBITDA margin covenant is proposed.",
        "Regulatory / legal: CBI search proceedings (auditors' emphasis of matter); mitigated by an undertaking to report "
        "any development within 7 days and a material-adverse-change clause.",
        "Rating outlook: CARE revised the outlook to Negative; a rating trigger of CARE A+ is proposed."]),
    ("8. STRENGTHS", ["Two decades of execution track record; geographically diversified order book; moderate leverage; "
                      "track record of asset monetisation."]),
    ("9. WEAKNESSES", ["Elongated working-capital cycle; margin pressure; concentration on government counterparties; "
                       "large equity commitments of Rs 785 Cr to HAM projects in FY2027."]),
    ("10. SECURITY", ["First pari passu charge on the current assets of the company (stocks, book debts, unbilled revenue) "
                      "with the consortium; second pari passu charge on the movable fixed assets; personal guarantee of "
                      "Mr. Harendra Singh."]),
    ("11. TERMS AND CONDITIONS", ["Drawing power on stock and book debts under 90 days, with 25% margin; quarterly "
                                 "stock audit; joining the consortium inter-se agreement; submission of quarterly "
                                 "unaudited results within 45 days."]),
    ("12. COVENANTS", ["TOL/TNW not above 1.25x; debt / EBITDA not above 2.5x; current ratio not below 1.10x; minimum "
                       "EBITDA margin 9% tested half-yearly; external rating not below CARE A+."]),
    ("13. DEVIATIONS", ["Current ratio of 1.17x against the bank's policy minimum of 1.25x — deviation sought; mitigated "
                        "by the monetisation proceeds expected in FY2027."]),
    ("14. RECOMMENDATION", ["Recommended for sanction: a fund-based working capital limit of Rs 200.00 Cr (cash credit / "
                            "WCDL) as a new member of the SBI-led consortium, at 1-year MCLR + 0.75%, on the security, "
                            "terms and covenants above, with the deviation on the current ratio approved."]),
]


def build(out: Path = OUT) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape

    ss = getSampleStyleSheet()
    out.parent.mkdir(parents=True, exist_ok=True)

    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#b45309"))
        canvas.drawString(16 * mm, 8 * mm, MARK)
        canvas.drawRightString(194 * mm, 8 * mm, f"Demo Bank Ltd. · Credit Appraisal Memorandum · page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(str(out), pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm,
                            bottomMargin=16 * mm, title="Credit Appraisal Memorandum — H.G. Infra Engineering Limited")
    flow = [Paragraph("<b>DEMO BANK LTD. — CORPORATE CREDIT DEPARTMENT</b>", ss["Normal"]),
            Paragraph("<b>CREDIT APPRAISAL MEMORANDUM</b>", ss["Title"]),
            Paragraph("H.G. Infra Engineering Limited · Proposal no. DB/CCG/2026/1187 · 28 October 2026", ss["Normal"]),
            Paragraph(f"<font color='#b45309'>{MARK}</font>", ss["Italic"]), Spacer(1, 6 * mm)]
    for heading, blocks in SECTIONS:
        flow.append(Paragraph(escape(heading), ss["Heading3"]))
        for b in blocks:
            if callable(b):
                b = b()
            if isinstance(b, str):
                flow.append(Paragraph(escape(b), ss["Normal"]))
                flow.append(Spacer(1, 2 * mm))
            elif isinstance(b, dict):
                for k, v in b.items():
                    flow.append(Paragraph(escape(f"{k}: {v}" if v else k), ss["Normal"]))
                flow.append(Spacer(1, 3 * mm))
            else:
                t = Table(b, repeatRows=1)
                t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                                       ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0"))]))
                flow += [t, Spacer(1, 4 * mm)]
    flow += [Spacer(1, 6 * mm), Paragraph("Prepared by: Relationship Manager, Corporate Banking · Reviewed by: Credit "
                                          "Officer, Corporate Credit Department (UAT demo names withheld)", ss["Italic"])]
    doc.build(flow, onFirstPage=on_page, onLaterPages=on_page)
    return out


if __name__ == "__main__":
    print("wrote", build())
