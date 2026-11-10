"""Test pack: H.G. Infra Engineering Limited (road and solar EPC; new-to-bank prospect for the bank-CAM upload journey).

    python test-documents/hg_infra/prepare.py [--no-download]

Figures from the audited standalone statements in the FY2025-26 annual report (₹ in million in the report, ₹ crore
here); rating from CARE's press release of 3 September 2026 (CARE AA, outlook revised to Negative). See
../prospect_pack.py for what is real and what is demo. ``bank_cam.py`` writes the bank-format CAM for the upload test.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from prospect_pack import prepare  # noqa: E402

SPEC = {
    "public": {
        "annual_report_fy2026.pdf": "https://www.bseindia.com/xml-data/corpfiling/AttachHis/d0b13a40-41c3-44d7-b9c1-ee3795a00e8e.pdf",
        "annual_report_fy2025.pdf": "https://www.bseindia.com/xml-data/corpfiling/AttachHis/fbcf2afe-197c-464c-9ba9-864b6ce35050.pdf",
        "care_rationale_2026-09.pdf": "https://www.careratings.com/upload/CompanyFiles/PR/202609160921_H.G._Infra_Engineering_Limited.pdf",
    },
    "name": "H.G. INFRA ENGINEERING LIMITED",
    "cin": "L45201RJ2003PLC018049",
    "pan": "AAACZ6630H", "gstin": "08AAACZ6630H1ZK",           # masked demo values
    "roc": "RoC-Jaipur", "incorporated": "05/02/2003", "agm": "19/08/2026",
    "address": "14, Panchwati Colony, Ratanada, Jodhpur, Rajasthan 342001",
    "nic": "42101 - Construction and maintenance of roads, highways and bridges",
    "share_capital_cr": 65.17,
    "directors": [("HARENDRA SINGH", "Chairman & Managing Director (Promoter)"),
                  ("DEVENDRA BHUSHAN GUPTA", "Whole-time Director"), ("VIJENDRA SINGH CHOUDHARY", "Whole-time Director"),
                  ("ASHOK KUMAR THAKUR", "Independent Director"), ("MANJIT SINGH", "Independent Director"),
                  ("SHARADA SUNDER", "Independent Director"), ("MONICA WIDHANI", "Independent Director")],
    "signatories": [("Rajeev Mishra", "Chief Financial Officer"), ("Ankita Mehra", "Company Secretary")],
    "promoter": "Harendra Singh (with promoter group)", "promoter_pct": 71.8,
    "charges": [("State Bank of India (working capital consortium, security trustee)", 1800.00, "14/10/2025"),
                ("Kotak Mahindra Bank Limited (equipment term loan)", 90.00, "02/05/2025")],
    # outstanding adds up to standalone borrowings at 31-Mar-2026: short-term ₹1,564.40 Cr, long-term ₹63.04 Cr
    "bureau": [("State Bank of India", "CC", 600.00, 512.40, 0, 0, "Standard"),
               ("ICICI Bank Limited", "WCDL", 450.00, 401.00, 0, 0, "Standard"),
               ("Axis Bank Limited", "CC", 400.00, 352.00, 0, 0, "Standard"),
               ("HDFC Bank Limited", "WCDL", 350.00, 299.00, 0, 0, "Standard"),
               ("Kotak Mahindra Bank Limited", "TL", 90.00, 63.04, 0, 0, "Standard"),
               ("State Bank of India", "BG", 1400.00, 1186.50, 0, 0, "Standard")],
    "bureau_head": {"cmr": "CMR-3", "enquiries": 4},
    "bureau_note": "Fund-based outstanding adds up to the audited borrowings at 31-Mar-2026 (Rs 1,627.44 Cr); fund-based "
                   "utilisation is 87%. Lenders and limits are illustrative. CARE revised the outlook to Negative on "
                   "3-Sep-2026 on stretched current assets (277 GCA days) and lower margins.",
    "revenue_cr": 5666.68, "revenue_prev_cr": 6051.88, "growth": -0.15,
    "gst_rate": 0.18, "gst_share": 0.98,
    "gst_nature": "Supplier of Services (works contracts: roads, highways, solar EPC)",
    "gst_note": "Taxable value is about 98% of reported revenue (works contract services at 18%).",
    "bank_name": "State Bank of India", "bank_branch": "State Bank of India, Commercial Branch, Jodhpur",
    "acct_last4": "2056", "opening_balance_cr": 44.8,
    "h1_weights": [1.2, 1.1, 0.8, 0.7, 0.8, 1.0],
}

if __name__ == "__main__":
    prepare(SPEC, HERE, download_public="--no-download" not in sys.argv)
