"""Test packs for new-to-bank prospects: real public documents plus demo documents that agree with them.

Each borrower folder has a ``prepare.py`` with a SPEC (identifiers, directors, figures from its audited statements,
rated facilities) and calls ``prepare(SPEC, here)``:

    public/   the borrower's real annual reports and rating rationale, downloaded once (politely) from BSE / the
              rating agency (not committed: see .gitignore)
    demo/     the documents a bank obtains from non-public sources, generated to agree with the public figures and
              marked "UAT DEMO DATA" on every page:
                  mca/mca_master_data.pdf             identifiers, capital, directors (DINs masked), charges
                  kyc/kyc_pack.pdf                     PAN / GSTIN (masked demo values), signatories, ownership
                  bureau/commercial_bureau_report.pdf  lenders and limits that add up to the reported borrowings
                  banking/bank_statement_apr_sep_2026.pdf   monthly credits consistent with revenue (incl. GST)
                  gst/gst_returns_fy2025_26.pdf        taxable value consistent with reported revenue

Scrubbing: the company's name, CIN and registered office are public and kept, so the identity agents can verify
them. Directors' DINs, the company PAN and GSTIN, account numbers and contact details are replaced with demo values
(DINs 99xxxxxx, PAN AAACZ…, accounts XXXX…), consistent across the documents.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEMO = "UAT DEMO DATA — prepared for testing from public disclosures; identifiers masked; not issued by the named authority."
MONTHS_H1 = ["Apr-2026", "May-2026", "Jun-2026", "Jul-2026", "Aug-2026", "Sep-2026"]
MONTHS_FY = ["Apr-2025", "May-2025", "Jun-2025", "Jul-2025", "Aug-2025", "Sep-2025", "Oct-2025", "Nov-2025",
             "Dec-2025", "Jan-2026", "Feb-2026", "Mar-2026"]


def download(spec: dict, here: Path, force: bool = False) -> None:
    from src.flow.acquire.polite import PoliteClient
    out = here / "public"
    out.mkdir(exist_ok=True)
    client = PoliteClient(ROOT / "storage" / "cache" / "acquire",
                          user_agent="CorporateCreditOrigination-UAT/1.0 (test data, one-time download)",
                          min_interval=5, timeout=300, respect_robots=False)
    for name, url in spec["public"].items():
        target = out / name
        if target.exists() and not force:
            print(f"have  {name}")
            continue
        r = client.get(url, cache_hours=24 * 365, accept="application/pdf")
        target.write_bytes(r.content)
        print(f"saved {name} ({len(r.content) / 1e6:.1f} MB)")


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
        elif isinstance(b, dict):
            for k, v in b.items():
                flow.append(Paragraph(escape(f"{k}: {v}"), ss["Normal"]))
            flow.append(Spacer(1, 4 * mm))
        else:
            t = Table(b, repeatRows=1)
            t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                                   ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0"))]))
            flow += [t, Spacer(1, 5 * mm)]
    doc.build(flow)


def _split(total: float, weights: list[float]) -> list[float]:
    s = sum(weights)
    vals = [round(total * w / s, 2) for w in weights]
    vals[-1] = round(total - sum(vals[:-1]), 2)
    return vals


def _filed(month: str) -> str:
    import calendar
    mon, year = month.split("-")
    i = list(calendar.month_abbr).index(mon) % 12 + 1
    return f"20/{i:02d}/{int(year) + (1 if i == 1 else 0)}"


def make_demo(s: dict, out: Path) -> Path:
    name, cin = s["name"], s["cin"]
    _pdf(out / "mca" / "mca_master_data.pdf", "Company Master Data", "Ministry of Corporate Affairs — MCA21 (printout format)", [
        {"CIN": cin, "Company Name": name, "ROC Code": s["roc"], "Company Category": "Company limited by Shares",
         "Company SubCategory": "Non-govt company", "Class of Company": "Public",
         "Paid up Capital (Rs Cr)": f"{s['share_capital_cr']:,.2f}", "Date of Incorporation": s["incorporated"],
         "Registered Address": s["address"], "Email Id": "investor.relations@example-demo.in",
         "Whether Listed or not": "Listed", "Date of last AGM": s["agm"], "Date of Balance Sheet": "31/03/2026",
         "Company Status (for efiling)": "Active", "Main division of business activity (NIC)": s["nic"]},
        "DIRECTORS / SIGNATORY DETAILS",
        [["DIN (masked)", "Name", "Designation"], *[[f"99{i:06d}", n, d] for i, (n, d) in enumerate(s["directors"], 1)]],
        "INDEX OF CHARGES (illustrative)",
        [["Charge ID", "Charge Holder", "Amount (Rs Cr)", "Date of Creation", "Status"],
         *[[f"1009{i:05d}", l, f"{amt:,.2f}", dt, "Open"] for i, (l, amt, dt) in enumerate(s["charges"], 1)]],
        "Name, CIN, registered office, paid-up capital and directors per the FY2025-26 annual report; DINs masked."])
    _pdf(out / "kyc" / "kyc_pack.pdf", "KYC Verification Pack", name, [
        {"Company Name": name, "PAN (masked demo)": s["pan"], "CIN": cin, "GSTIN (masked demo)": s["gstin"],
         "Certificate of Incorporation": f"{s['incorporated']}, {s['roc']}", "Registered Office": s["address"],
         "Constitution": "Public limited company (listed on BSE and NSE)", "KYC Status": "Verified",
         "Verified On": "30/10/2026", "Customer Risk Category": s.get("kyc_risk", "Low")},
        "AUTHORISED SIGNATORIES",
        [["Name", "Designation", "ID Verified", "Status"], *[[n, d, "PAN, Aadhaar (masked)", "Verified"] for n, d in s["signatories"]]],
        "BENEFICIAL OWNERSHIP",
        [["Beneficial Owner", "Holding", "Basis"], [s["promoter"], f"{s['promoter_pct']:.2f}%", "SEBI shareholding pattern, Sep-2026"]]])
    rows = [[l, t, f"{sn:,.2f}", f"{o:,.2f}", f"{od:,.2f}", str(dpd), cls] for l, t, sn, o, od, dpd, cls in s["bureau"]]
    b = s["bureau_head"]
    _pdf(out / "bureau" / "commercial_bureau_report.pdf", "Commercial Credit Information Report",
         "Company Credit Report (CMR) format", [
             {"Bureau": "TransUnion CIBIL (format)", "Report Date": "28/10/2026", "Borrower Name": name, "PAN": s["pan"],
              "CMR Rank": b["cmr"], "Rank Description": "CMR-1 lowest risk, CMR-10 highest",
              "Wilful Defaulter": "No", "Suit Filed (Rs Cr)": "0.00", "Enquiries in last 6 months": str(b.get("enquiries", 2)),
              "Worst Status in 12 months": b.get("worst", "Standard")},
             "CREDIT FACILITIES",
             [["Lender", "Facility", "Sanctioned (Rs Cr)", "Outstanding (Rs Cr)", "Overdue (Rs Cr)", "DPD", "Classification"], *rows],
             s["bureau_note"]])
    g = s["growth"]
    h1 = s["revenue_cr"] * (1 + g) / 2 * (1 + s["gst_rate"])
    credits = _split(h1, s.get("h1_weights", [1, 1, 1, 1.05, 1.05, 1.1]))
    bal, brows = s.get("opening_balance_cr", 25.0), []
    for m, cr in zip(MONTHS_H1, credits):
        dr = round(cr * 0.99, 2)
        close = round(bal + cr - dr, 2)
        brows.append([m, f"{bal:,.2f}", f"{cr:,.2f}", f"{dr:,.2f}", f"{close:,.2f}", str(int(cr * 1.3) + 180), "0"])
        bal = close
    _pdf(out / "banking" / "bank_statement_apr_sep_2026.pdf", "Statement of Account — Monthly Summary", s["bank_branch"], [
        {"Bank": s["bank_name"], "Account Holder": name, "Account Type": "Current account (collection)",
         "Account Number": "XXXXXXXX" + s.get("acct_last4", "4410"), "Statement Period": "01/04/2026 to 30/09/2026"},
        "MONTHLY SUMMARY",
        [["Month", "Opening (Rs Cr)", "Credits (Rs Cr)", "Debits (Rs Cr)", "Closing (Rs Cr)", "No. of credits", "Returns"], *brows],
        f"Monthly credits are consistent with FY2026 revenue of Rs {s['revenue_cr']:,.2f} Cr grown at {g * 100:.0f}% "
        f"for H1 FY2027, including GST at about {s['gst_rate'] * 100:.0f}%."])
    taxable = round(s["revenue_cr"] * s["gst_share"], 2)
    gst = _split(taxable, s.get("gst_weights", [1] * 12))
    _pdf(out / "gst" / "gst_returns_fy2025_26.pdf", "GST Returns Summary — GSTR-3B", "Goods and Services Tax Network (summary format)", [
        {"GSTIN": s["gstin"], "Legal Name": name, "Status": "Active", "Date of Registration": "01/07/2017",
         "Nature of Business": s["gst_nature"],
         "Aggregate turnover FY 2025-26 (PAN level, Rs Cr)": f"{taxable:,.2f}",
         "Aggregate turnover FY 2024-25 (PAN level, Rs Cr)": f"{s['revenue_prev_cr'] * s['gst_share']:,.2f}"},
        "GSTR-3B FILINGS FY 2025-26",
        [["Return period", "Taxable value (Rs Cr)", "Tax paid (Rs Cr)", "Filed on", "Status"],
         *[[m, f"{v:,.2f}", f"{v * s['gst_rate']:,.2f}", _filed(m), "Filed on time"] for m, v in zip(MONTHS_FY, gst)]],
        s["gst_note"]])
    return out


def make_registry(s: dict) -> Path:
    """storage/demo_registry/<CIN>.json: the regulatory-list results (wilful defaulter, RBI defaulter, CFMC fraud, suits,
    NCLT) a bank gets from the bureau / registry APIs, which are not connected — consistent with the bureau report."""
    import json
    fund = [r for r in s["bureau"] if r[1] not in ("BG", "LC", "LC/BG")]
    rec = {"entity_id": s["cin"], "cin": s["cin"], "company_name": s["name"].title(), "as_of": "2026-10-28",
           "note": "DEMO DATA: stands in for the bureau, MCA and regulatory-list APIs that are not connected; consistent "
                   "with the demo bureau report in the test pack. Not a real report on this company.",
           "bureau": {"cmr_rank": s["bureau_head"]["cmr"], "dpd_status": s["bureau_head"].get("worst", "Standard"),
                      "max_dpd_last_12m": 0, "worst_status_12m": s["bureau_head"].get("worst", "Standard"),
                      "total_exposure_cr": round(sum(r[2] for r in s["bureau"]), 2),
                      "total_outstanding_cr": round(sum(r[3] for r in fund), 2),
                      "total_lenders": len({r[0] for r in s["bureau"]})},
           "mca": {"company_name": s["name"].title(), "cin": s["cin"], "status": "Active", "company_class": "Public, listed"},
           "registries": {"wilful_defaulter": False, "rbi_defaulter_list": False, "fraud_flag": False,
                          "suit_filed_amount_cr": 0.0, "suits": [], "nclt_cases": []}}
    path = ROOT / "storage" / "demo_registry" / f"{s['cin']}.json"
    path.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    return path


def prepare(spec: dict, here: Path, download_public: bool = True) -> None:
    if download_public:
        download(spec, here)
    out = make_demo(spec, here / "demo")
    print("demo documents in", out)
    print("demo registry record", make_registry(spec))
