"""Test pack: Transport Corporation of India Limited (logistics; new-to-bank prospect).

    python test-documents/tci_logistics/prepare.py [--no-download]

Figures from the audited standalone statements in the FY2025-26 annual report (₹ in million in the report, ₹ crore
here); rating from CARE's press release of 30 September 2026. See ../prospect_pack.py for what is real and what is demo.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from prospect_pack import prepare  # noqa: E402

SPEC = {
    "public": {
        "annual_report_fy2026.pdf": "https://www.bseindia.com/xml-data/corpfiling/AttachHis/b9136e34-805b-4011-aeab-c83001c6dfa4.pdf",
        "annual_report_fy2025.pdf": "https://www.bseindia.com/xml-data/corpfiling/AttachHis/a016167c-e50b-4897-9e61-5dd6fa820927.pdf",
        "care_rationale_2026-09.pdf": "https://www.careratings.com/upload/CompanyFiles/PR/202609140959_Transport_Corporation_Of_India_limited.pdf",
    },
    "name": "TRANSPORT CORPORATION OF INDIA LIMITED",
    "cin": "L70109TG1995PLC019116",
    "pan": "AAACZ9101T", "gstin": "36AAACZ9101T1ZQ",           # masked demo values
    "roc": "RoC-Hyderabad", "incorporated": "28/04/1995", "agm": "30/07/2026",
    "address": "Flat Nos. 306 & 307, 1-8-201 to 203, 3rd Floor, Ashoka Bhoopal Chambers, S.P. Road, Secunderabad, "
               "Telangana 500003",
    "nic": "49 - Land transport and transport via pipelines; 52 - Warehousing and support activities for transportation",
    "share_capital_cr": 15.35,
    "directors": [("D. P. AGARWAL", "Chairman & Managing Director (Promoter)"), ("VINEET AGARWAL", "Managing Director"),
                  ("CHANDER AGARWAL", "Non-executive Director"), ("URMILA AGARWAL", "Non-executive Director"),
                  ("RAVIKANT UPPAL", "Independent Director"), ("VIKRAMPATI SINGHANIA", "Independent Director"),
                  ("GITA NAYYAR", "Independent Director")],
    "signatories": [("Ashish Kumar Tiwari", "Group Chief Financial Officer"), ("Hansa Sharma", "Company Secretary")],
    "promoter": "D. P. Agarwal (with promoter group)", "promoter_pct": 69.0,
    "charges": [("HDFC Bank Limited (term loan, vehicles)", 75.00, "12/06/2025"),
                ("State Bank of India (working capital, hypothecation of receivables)", 100.00, "03/09/2024")],
    # outstanding adds up to standalone borrowings at 31-Mar-2026: long-term ₹119.37 Cr, short-term ₹42.48 Cr
    "bureau": [("HDFC Bank Limited", "TL", 75.00, 69.37, 0, 0, "Standard"),
               ("ICICI Bank Limited", "TL", 55.00, 50.00, 0, 0, "Standard"),
               ("State Bank of India", "CC", 100.00, 22.48, 0, 0, "Standard"),
               ("Kotak Mahindra Bank Limited", "WCDL", 70.00, 20.00, 0, 0, "Standard")],
    "bureau_head": {"cmr": "CMR-2", "enquiries": 1},
    "bureau_note": "Sanctioned limits add up to the Rs 300 Cr long-term bank facilities rated CARE AA+ (Stable) on "
                   "30-Sep-2026; outstanding adds up to the audited borrowings at 31-Mar-2026 (Rs 161.85 Cr). The split by "
                   "lender is illustrative.",
    "revenue_cr": 4224.82, "revenue_prev_cr": 3935.90, "growth": 0.073,
    "gst_rate": 0.12, "gst_share": 0.97,
    "gst_nature": "Supplier of Services (goods transport agency, warehousing, coastal shipping)",
    "gst_note": "Taxable value is about 97% of reported revenue: part of the coastal shipping and export logistics revenue "
                "is zero-rated or outside GST.",
    "bank_name": "State Bank of India", "bank_branch": "State Bank of India, Corporate Accounts Group, Secunderabad",
    "acct_last4": "7712", "opening_balance_cr": 38.4,
}

if __name__ == "__main__":
    prepare(SPEC, HERE, download_public="--no-download" not in sys.argv)
