"""
Test documents for the new-prospect journey: Dixon Technologies (India) Limited.

  python test-documents/dixon_technologies/prepare.py [--no-download]

Real public documents (downloaded once, politely, into ./public — see README.md):
  * annual_report_fy2026.pdf / annual_report_fy2025.pdf   BSE filings (audited standalone statements)
  * icra_rationale_2026-01-06.pdf                         ICRA rating rationale

Demo documents (generated into ./demo, clearly marked as UAT demo data): the documents a bank
would obtain from non-public sources — MCA master data printout, KYC pack, commercial bureau
report, bank statement, GST returns summary. Every figure in them is either taken from the public
sources (identifiers, directors, bankers, rated limits, reported revenue) or derived from them
(GST turnover and bank credits consistent with reported revenue); facility-wise bureau splits and
monthly figures are illustrative.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

PUBLIC = {
    "annual_report_fy2026.pdf": "https://www.bseindia.com/xml-data/corpfiling/AttachHis/5ef88e3c-352d-4223-a8ec-bdd7d3aa31c1.pdf",
    "annual_report_fy2025.pdf": "https://www.bseindia.com/xml-data/corpfiling/AttachHis/7eabc370-b827-435c-9dd2-8a70553a8062.pdf",
    "icra_rationale_2026-01-06.pdf": "https://www.icra.in/Rating/GetRationalReportFilePdf?id=140153",
}

NAME = "DIXON TECHNOLOGIES (INDIA) LIMITED"
CIN = "L32101UP1993PLC066581"
PAN = "AAACD3641D"
GSTIN = "09AAACD3641D1Z2"
ADDRESS = "B-14 & 15, Phase-II, Noida, Gautam Buddha Nagar, Uttar Pradesh 201305"
DEMO = "UAT DEMO DATA — prepared for testing from public disclosures; not issued by the named authority."


def download(force: bool = False) -> None:
    from src.flow.acquire.polite import PoliteClient
    out = HERE / "public"
    out.mkdir(exist_ok=True)
    client = PoliteClient(ROOT / "storage" / "cache" / "acquire",
                          user_agent="CorporateCreditOrigination-UAT/1.0 (test data, one-time download)",
                          min_interval=5, timeout=300, respect_robots=False)
    for name, url in PUBLIC.items():
        target = out / name
        if target.exists() and not force:
            print(f"have  {name}")
            continue
        r = client.get(url, cache_hours=24 * 365, accept="application/pdf")
        target.write_bytes(r.content)
        print(f"saved {name} ({len(r.content) / 1e6:.1f} MB{' from cache' if r.from_cache else ''})")


# ── demo documents ───────────────────────────────────────────────────────────

def _pdf(path: Path, title: str, subtitle: str, blocks: list) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape

    ss = getSampleStyleSheet()
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm, title=title)
    flow = [Paragraph(f"<b>{escape(title)}</b>", ss["Title"]), Paragraph(escape(subtitle), ss["Normal"]),
            Paragraph(f"<font color='#b45309'>{DEMO}</font>", ss["Italic"]), Spacer(1, 6 * mm)]
    for b in blocks:
        if isinstance(b, str):
            flow.append(Paragraph(escape(b), ss["Heading3"] if b.isupper() else ss["Normal"]))
        elif isinstance(b, dict):                          # label: value form
            for k, v in b.items():
                flow.append(Paragraph(escape(f"{k}: {v}"), ss["Normal"]))
            flow.append(Spacer(1, 4 * mm))
        else:                                              # table: [header, *rows]
            t = Table(b, repeatRows=1)
            t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                                   ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0"))]))
            flow += [t, Spacer(1, 5 * mm)]
    doc.build(flow)


DIRECTORS = [("00025431", "SUNIL VACHANI", "Whole-time Director (Executive Chairman, Promoter)"),
             ("00781436", "ATUL B LALL", "Managing Director (Vice Chairman)"),
             ("09685338", "SAURABH GUPTA", "Whole-time Director (Chief Financial Officer)"),
             ("02581704", "MANOJ MAHESHWARI", "Director (Non-executive, Non-independent)"),
             ("02790744", "RAKESH MOHAN", "Independent Director"),
             ("02139552", "GEETA MATHUR", "Independent Director"),
             ("—", "KENG TSUNG KUO", "Independent Director"),
             ("—", "ARUN SETH", "Independent Director")]

BUREAU = [("ICICI Bank Limited", "CC", 150.00, 0.00), ("ICICI Bank Limited", "LC/BG", 520.00, 168.40),
          ("HDFC Bank Limited", "CC", 125.00, 0.00), ("HDFC Bank Limited", "LC/BG", 450.00, 142.10),
          ("State Bank of India", "CC", 100.00, 0.00), ("State Bank of India", "LC/BG", 380.00, 121.75),
          ("Citibank N.A.", "WCDL", 80.00, 0.00), ("Citibank N.A.", "LC/BG", 230.00, 74.20),
          ("JPMorgan Chase Bank N.A.", "WCDL", 40.00, 0.00), ("JPMorgan Chase Bank N.A.", "LC/BG", 150.00, 48.30),
          ("SMBC India", "WCDL", 40.00, 0.00), ("SMBC India", "LC/BG", 150.00, 51.65)]

# Apr–Sep 2026: H1 FY2027 standalone sales (Q1 ₹1,080 Cr, Q2 ₹1,593 Cr, exchange filings) plus GST
BANK = [("Apr-2026", 405.20, 398.65), ("May-2026", 420.60, 425.10), ("Jun-2026", 448.50, 441.95),
        ("Jul-2026", 560.30, 552.80), ("Aug-2026", 618.70, 612.45), ("Sep-2026", 700.90, 694.30)]

# FY2025-26 GSTR-3B taxable value by month; total ₹3,862.40 Cr vs reported revenue ₹3,930.48 Cr
# (PLI incentives and other operating income are not GST supplies)
GST = [("Apr-2025", 352.10), ("May-2025", 341.75), ("Jun-2025", 338.90), ("Jul-2025", 402.30), ("Aug-2025", 398.15),
       ("Sep-2025", 412.60), ("Oct-2025", 268.40), ("Nov-2025", 251.20), ("Dec-2025", 252.35), ("Jan-2026", 270.95),
       ("Feb-2026", 281.40), ("Mar-2026", 292.30)]


def make_demo(out: Path = HERE / "demo") -> Path:
    _pdf(out / "mca" / "mca_master_data.pdf", "Company Master Data", "Ministry of Corporate Affairs — MCA21 "
         "(printout format)", [
             {"CIN": CIN, "Company Name": NAME, "ROC Code": "RoC-Kanpur", "Registration Number": "066581",
              "Company Category": "Company limited by Shares", "Company SubCategory": "Non-govt company",
              "Class of Company": "Public", "Paid up Capital (Rs)": "12,16,00,000",
              "Date of Incorporation": "15/01/1993", "Registered Address": ADDRESS,
              "Email Id": "investorrelations@dixoninfo.com", "Whether Listed or not": "Listed",
              "Date of last AGM": "28/09/2026", "Date of Balance Sheet": "31/03/2026",
              "Company Status (for efiling)": "Active",
              "Main division of business activity (NIC)": "26 - Manufacture of computer, electronic and "
                                                          "optical products"},
             "DIRECTORS / SIGNATORY DETAILS",
             [["DIN", "Name", "Designation"], *[list(d) for d in DIRECTORS]],
             "INDEX OF CHARGES (illustrative)",
             [["Charge ID", "Charge Holder", "Amount (Rs Cr)", "Date of Creation", "Status"],
              ["100512345", "ICICI Bank Limited (security trustee, working capital consortium)", "2,415.00",
               "14/08/2024", "Open"]],
             "Paid-up capital and directors per the FY2025-26 annual report; DIN shown as — where the annual "
             "report does not state it."])
    _pdf(out / "kyc" / "kyc_pack.pdf", "KYC Verification Pack", f"{NAME}", [
        {"Company Name": NAME, "PAN": PAN, "CIN": CIN, "GSTIN": GSTIN,
         "Certificate of Incorporation": "15/01/1993, Registrar of Companies, Kanpur",
         "Registered Office": ADDRESS, "Constitution": "Public limited company (listed on BSE and NSE)",
         "KYC Status": "Verified", "Verified On": "30/10/2026", "Customer Risk Category": "Low"},
        "AUTHORISED SIGNATORIES",
        [["Name", "Designation", "ID Verified", "Status"],
         ["Saurabh Gupta", "Director & Chief Financial Officer", "PAN, Aadhaar (masked)", "Verified"],
         ["Ashish Kumar", "Group Company Secretary", "PAN, Passport", "Verified"]],
        "BENEFICIAL OWNERSHIP",
        [["Beneficial Owner", "Holding", "Basis"],
         ["Sunil Vachani (with promoter group)", "28.50%", "SEBI shareholding pattern, Sep-2026"]]])
    _pdf(out / "bureau" / "commercial_bureau_report.pdf", "Commercial Credit Information Report",
         "Company Credit Report (CMR) format", [
             {"Bureau": "TransUnion CIBIL (format)", "Report Date": "28/10/2026", "Borrower Name": NAME, "PAN": PAN,
              "CMR Rank": "CMR-2", "Rank Description": "Low risk of default (CMR-1 lowest risk, CMR-10 highest)",
              "Wilful Defaulter": "No", "Suit Filed (Rs Cr)": "0.00", "Enquiries in last 6 months": "2",
              "Worst Status in 12 months": "Standard"},
             "CREDIT FACILITIES",
             [["Lender", "Facility", "Sanctioned (Rs Cr)", "Outstanding (Rs Cr)", "Overdue (Rs Cr)", "DPD",
               "Classification"],
              *[[l, t, f"{s:,.2f}", f"{o:,.2f}", "0.00", "0", "Standard"] for l, t, s, o in BUREAU]],
             "Sanctioned limits per lender are illustrative; the totals match the bank limits rated by ICRA "
             "(fund-based Rs 535 Cr, non-fund based Rs 1,880 Cr). Fund-based outstanding is nil, as in the "
             "audited balance sheet (no borrowings from banks at 31-Mar-2026)."])
    _pdf(out / "banking" / "bank_statement_apr_sep_2026.pdf", "Statement of Account — Monthly Summary",
         "ICICI Bank Limited, Corporate Banking Branch, Noida", [
             {"Bank": "ICICI Bank Limited", "Account Holder": NAME, "Account Type": "Current account (collection)",
              "Account Number": "XXXXXXXX4721", "Statement Period": "01/04/2026 to 30/09/2026"},
             "MONTHLY SUMMARY",
             [["Month", "Opening (Rs Cr)", "Credits (Rs Cr)", "Debits (Rs Cr)", "Closing (Rs Cr)", "No. of credits",
               "Returns"],
              *_bank_rows()],
             "Monthly credits are consistent with H1 FY2027 standalone sales (exchange filings) including GST."])
    _pdf(out / "gst" / "gst_returns_fy2025_26.pdf", "GST Returns Summary — GSTR-3B", "Goods and Services Tax "
         "Network (summary format)", [
             {"GSTIN": GSTIN, "Legal Name": NAME, "Status": "Active", "Date of Registration": "01/07/2017",
              "Nature of Business": "Factory / Manufacturing, Supplier of Services",
              "Aggregate turnover FY 2025-26 (PAN level, Rs Cr)": "3,862.40",
              "Aggregate turnover FY 2024-25 (PAN level, Rs Cr)": "5,318.20"},
             "GSTR-3B FILINGS FY 2025-26",
             [["Return period", "Taxable value (Rs Cr)", "Tax paid (Rs Cr)", "Filed on", "Status"],
              *[[m, f"{v:,.2f}", f"{v * 0.18:,.2f}", _filed(m), "Filed on time"] for m, v in GST]]])
    return out


def _bank_rows() -> list:
    rows, bal = [], 21.63
    counts = (412, 431, 446, 498, 521, 563)
    for (m, cr, dr), n in zip(BANK, counts):
        close = round(bal + cr - dr, 2)
        rows.append([m, f"{bal:,.2f}", f"{cr:,.2f}", f"{dr:,.2f}", f"{close:,.2f}", str(n), "0"])
        bal = close
    return rows


def _filed(month: str) -> str:
    import calendar
    mon, year = month.split("-")
    i = list(calendar.month_abbr).index(mon) % 12 + 1
    y = int(year) + (1 if i == 1 else 0)
    return f"20/{i:02d}/{y}"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-download", action="store_true")
    a = ap.parse_args()
    if not a.no_download:
        download()
    make_demo()
    print("demo documents in", HERE / "demo")
