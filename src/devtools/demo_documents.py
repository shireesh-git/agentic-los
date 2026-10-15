"""
The POC demo document set: a fictional new-to-bank prospect, "Zeta Foods Private Limited",
with every document the agentic journey reads, and the values each one should yield
(the golden set the extraction is measured against).

    request/request_letter.pdf                 Prospect Sourcing: the facility request
    kyc/certificate_of_incorporation.pdf       identity (CIN, incorporation, registered office)
    kyc/pan_card_scan.pdf                      identity (PAN) — a SCAN with no text layer:
                                               read only by a vision model (or OCR)
    financials/audited_financials_fy2025.pdf   the statements the credit case is built on
    legal/signed_sanction_letter.pdf           Post Sanction: acceptance
    legal/facility_agreement.pdf               Post Sanction: execution
    request/drawdown_request.pdf               Disbursement: the drawdown and the beneficiary
    cam/credit_appraisal_memo.pdf              (optional) the bank's CAM, to start from a CAM

Everything here is fictional demo data. For the bank's own pilot, replace the set with the
borrower's real documents and the golden values with what a person read from them.
"""

from __future__ import annotations

from pathlib import Path

COMPANY = "Zeta Foods Private Limited"

DOCUMENTS: dict[str, dict] = {
    "request/request_letter.pdf": {"pages": [
        "To: The Relationship Manager\nSubject: Request for a working capital limit\n"
        "Facility Requested: working_capital\nCase Type: NTB\nAmount Requested: Rs 45 Cr\nTenor: 12 months\n"
        "Purpose: Working capital for the Pune plant expansion\n"
        "Latest Financial Snapshot (FY2025): Revenue Rs 312 Cr, EBITDA Rs 41 Cr, PAT Rs 17 Cr, Debt Rs 96 Cr."]},
    "kyc/certificate_of_incorporation.pdf": {"pages": [
        "Ministry of Corporate Affairs - Certificate of Incorporation",
        f"Legal Name: {COMPANY} CIN: U15400MH2015PTC123456\nIncorporated: 12-Mar-2015\n"
        "Registered Office: Plot 7, MIDC Andheri East, Mumbai 400093"]},
    "kyc/pan_card_scan.pdf": {"scanned": True, "pages": [
        f"INCOME TAX DEPARTMENT\nPAN: AAACZ1234Q\nName: {COMPANY.upper()}"]},
    "financials/audited_financials_fy2025.pdf": {"pages": [
        f"{COMPANY.upper()}\nAudited Standalone Financial Statements for the year ended 31 March 2025 (Rs in Crores)\n"
        "Statement of Profit and Loss\nRevenue from Operations 312.40\nOther Income 4.10\nTotal Income 316.50\n"
        "EBITDA 41.20\nDepreciation 9.80\nFinance Cost 8.90\nProfit Before Tax 22.50\nTax Expense 5.70\n"
        "Profit After Tax 16.80\nBalance Sheet\nTotal Assets 268.00\nTotal Equity 118.00\nTotal Debt 96.00\n"
        "Current Assets 142.00\nCurrent Liabilities 88.00"]},
    "legal/signed_sanction_letter.pdf": {"pages": [
        "Sanction Letter Ref No.: CBK/CORP/2026/0457\n"
        f"Borrower: {COMPANY}\nSanctioned Amount: Rs 45 Cr (working capital, 12 months)\n"
        "We accept the terms and conditions of this sanction.\n"
        "Accepted for and on behalf of the Borrower by: Rohan Desai, Director\nDate of acceptance: 05-Nov-2026"]},
    "legal/facility_agreement.pdf": {"pages": [
        f"WORKING CAPITAL FACILITY AGREEMENT between {COMPANY} and the Bank\n"
        "Facility Amount: Rs 45 Cr\nAgreement dated: 10-Nov-2026\nExecuted by the authorised signatories of both parties."]},
    "request/drawdown_request.pdf": {"pages": [
        "Drawdown Request No. 1\nDrawdown Amount requested: Rs 20 Cr\nValue Date: 20-Nov-2026\n"
        "Purpose of drawdown: Raw material procurement for the Pune plant.\n"
        "Beneficiary Name: Zeta Foods Private Limited Account No.: 004512300098765 Bank: Demo Bank\n"
        "IFSC Code: DEMO0001234"]},
}

# The bank's own Credit Appraisal Memorandum for the same prospect (format of a typical bank CAM:
# a header of labelled values, then numbered sections). Kept apart from DOCUMENTS: it is the
# optional "start from a CAM" input (write_set(include_cam=True)), so the document-only journey
# stays as it was.
CAM_DOCUMENTS: dict[str, dict] = {
    "cam/credit_appraisal_memo.pdf": {"pages": [
        "CREDIT APPRAISAL MEMORANDUM\nIn-Principle Proposal\n"
        f"Name of the Borrower: {COMPANY}\nCIN: U15400MH2015PTC123456\nPAN: AAACZ1234Q\n"
        "Constitution: Private Limited Company\nRegistered Office: Plot 7, MIDC Andheri East, Mumbai 400093\n"
        "Sector: Food Processing\nSub-sector: Packaged foods\nCase Type: NTB\n"
        "Facility Type: Working Capital Term Loan\nProposed Limit: Rs 45 Cr\nTenor: 12 months\n"
        "Purpose: Working capital for the Pune plant expansion.\nBanking Arrangement: Sole\n"
        "External Rating: CRISIL BBB+/Stable\nInternal Rating (indicative): NB-4\nRecommended Limit: Rs 45 Cr\n"
        "Pricing: 1-year MCLR + 125 bps (ROI 9.65% p.a.)",
        "1. Borrower and Business Background\n"
        f"{COMPANY}, incorporated in 2015, makes packaged snacks and ready-to-cook foods at its plant in Pune and "
        "sells them through 1,800 distributors across western India. The promoters have run the business since "
        "incorporation and hold 100% of the equity.\n"
        "2. Industry Outlook\n"
        "Packaged foods have grown steadily on urban demand and wider modern-trade reach. Input-cost swings in "
        "edible oil and grains are the main pressure on margins across the industry.\n"
        "3. Marketing Arrangement\n"
        "Sales are made through distributors on 30-day credit and through two national modern-trade chains; "
        "no single customer accounts for more than 12% of revenue.\n"
        "4. Corporate Governance and Management\n"
        "A five-member board with two independent directors; statutory audit by a mid-tier firm with "
        "unqualified opinions for the last three years.",
        "5. Financial Highlights (Rs Crore)\nFY2025 audited\nRevenue from Operations 312.40\nEBITDA 41.20\n"
        "Profit After Tax 16.80\nTotal Equity 118.00\nTotal Debt 96.00\n"
        "6. Key Strengths\n- Established distribution network in western India.\n"
        "- Consistent profitability with EBITDA margins of about 13%.\n"
        "7. Key Weaknesses\n- Regional concentration of sales.\n- Moderate scale against national competitors.\n"
        "8. Key Risks and Mitigants\n- Raw-material price volatility, mitigated by quarterly price revisions.\n"
        "- Working-capital intensity, mitigated by the proposed limit and receivables monitoring.",
        "9. Security\nPrimary: hypothecation of stocks and book debts. Collateral: equitable mortgage of the "
        "Pune plant land and building, market value Rs 62 Cr.\n"
        "10. Key Terms and Conditions\n- Drawing power against stocks and receivables, reviewed monthly.\n"
        "- Personal guarantees of the promoter directors.\n"
        "11. Covenants\n- DSCR of at least 1.25x, tested annually.\n- Total debt to EBITDA not above 3.0x.\n"
        "12. Deviations from Policy\nNone.\n"
        "13. Recommendation\nRecommended for in-principle sanction of a working capital limit of Rs 45 Cr for "
        "12 months, subject to the terms above."]},
}

# What a person reads from the documents above (the golden set). Values are as the extractor
# normalises them: amounts in ₹ crore, dates ISO.
GOLDEN = {
    "sourcing": {"legal_name": COMPANY, "cin": "U15400MH2015PTC123456", "pan": "AAACZ1234Q",
                 "date_of_incorporation": "2015-03-12", "registered_address": "Plot 7, MIDC Andheri East, Mumbai 400093",
                 "facility_type": "working_capital", "case_type": "NTB", "amount_cr": 45.0, "tenor_months": 12,
                 "purpose": "Working capital for the Pune plant expansion"},
    "post_sanction": {"sanction_reference": "CBK/CORP/2026/0457", "accepted_by": "Rohan Desai",
                      "acceptance_date": "2026-11-05", "sanctioned_amount_cr": 45.0, "agreement_date": "2026-11-10",
                      "agreement_amount_cr": 45.0},
    "disbursement": {"drawdown_amount_cr": 20.0, "value_date": "2026-11-20",
                     "drawdown_purpose": "Raw material procurement for the Pune plant",
                     "beneficiary_name": COMPANY, "account_number": "004512300098765", "ifsc": "DEMO0001234"},
    "audited_financials": {"revenue": 312.4, "pat": 16.8, "ebitda": 41.2},
    # what the CAM intake agent should read from the CAM (beyond the identity and facility above)
    "cam": {"sections": ["borrower_and_business", "industry_outlook", "marketing_arrangements", "corporate_governance",
                         "strengths", "weaknesses", "key_risks", "financial_highlights", "security", "key_terms",
                         "covenants", "deviations", "recommendation"],
            "labels": {"cam.profile.sector": "Food Processing", "cam.profile.subsector": "Packaged foods",
                       "cam.profile.constitution": "Private Limited Company", "cam.profile.banking_arrangement": "Sole",
                       "cam.rating.internal_rating": "NB-4", "cam.rating.external_rating": "CRISIL BBB+/Stable",
                       "cam.proposal.recommended_cr": 45.0, "cam.financials.revenue_cr": 312.4,
                       "cam.financials.ebitda_cr": 41.2, "cam.financials.pat_cr": 16.8,
                       "cam.financials.net_worth_cr": 118.0, "cam.financials.total_debt_cr": 96.0},
            "sourcing": {"legal_name": COMPANY, "cin": "U15400MH2015PTC123456", "pan": "AAACZ1234Q",
                         "facility_type": "working_capital", "amount_cr": 45.0, "tenor_months": 12,
                         "purpose": "Working capital for the Pune plant expansion"}},
}
# Fields only a vision model (or OCR) can read: on a scanned page with no text layer.
NEEDS_VISION = {("sourcing", "pan")}


def write_pdf(path: Path, pages: list[str], scanned: bool = False) -> None:
    import fitz  # PyMuPDF

    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    for text in pages:
        if scanned:                     # the page is an image of the text: no text layer to read
            src = fitz.open()
            p = src.new_page()
            p.insert_textbox(fitz.Rect(40, 40, 560, 800), text, fontsize=11)
            page = doc.new_page()
            page.insert_image(page.rect, pixmap=p.get_pixmap(dpi=100))
        else:
            page = doc.new_page()
            page.insert_textbox(fitz.Rect(40, 40, 560, 800), text, fontsize=10)
    doc.save(path)
    doc.close()


def write_set(root: Path, only: tuple[str, ...] = (), include_cam: bool = False) -> list[Path]:
    """Write the demo documents under ``root`` (category/name.pdf); ``only``: a subset of names;
    ``include_cam``: also the bank-format CAM (cam/credit_appraisal_memo.pdf)."""
    out = []
    for rel, spec in {**DOCUMENTS, **(CAM_DOCUMENTS if include_cam else {})}.items():
        if only and rel not in only:
            continue
        path = Path(root) / rel
        write_pdf(path, spec["pages"], scanned=spec.get("scanned", False))
        out.append(path)
    return out
