"""Test pack: KPI Green Energy Limited (renewable energy IPP and EPC; new-to-bank prospect).

    python test-documents/kpi_green_energy/prepare.py [--no-download]

Figures from the audited standalone statements in the FY2025-26 annual report (₹ in lakhs in the report, ₹ crore here).
See ../prospect_pack.py for what is real and what is demo.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from prospect_pack import prepare  # noqa: E402

SPEC = {
    "public": {
        "annual_report_fy2026.pdf": "https://www.bseindia.com/xml-data/corpfiling/AttachHis/d2c134fa-8162-4c91-a228-e448b9c356cb.pdf",
        "annual_report_fy2025.pdf": "https://www.bseindia.com/xml-data/corpfiling/AttachHis/bf32574e-c86b-49c1-9577-f4b59e3b3f88.pdf",
    },
    "name": "KPI GREEN ENERGY LIMITED",
    "cin": "L40102GJ2008PLC083302",
    "pan": "AAACZ4417K", "gstin": "24AAACZ4417K1ZB",           # masked demo values
    "roc": "RoC-Ahmedabad", "incorporated": "01/02/2008", "agm": "30/09/2026",
    "address": "'KP House', Near KP Circle, Opp. Ishwar Farm Junction BRTS, Canal Road, Bhatar, Surat, Gujarat 395017",
    "nic": "35105 - Electric power generation using solar energy",
    "share_capital_cr": 98.67,
    "directors": [("FARUK G. PATEL", "Chairman & Managing Director (Promoter)"),
                  ("MOHMED SOHIL Y. DABHOYA", "Whole-time Director"),
                  ("AFZAL HARUNBHAI MALKANI", "Non-executive Director"),
                  ("TEJPALSINGH BISHT", "Independent Director"), ("RAJESH SHRIVASTAVA", "Independent Director"),
                  ("SATYA GOPAL", "Independent Director"), ("SHARADCHANDRA B. PATIL", "Independent Director")],
    "signatories": [("Salim S. Yahoo", "Chief Financial Officer"), ("Krunal Bhatt", "Company Secretary")],
    "promoter": "Faruk G. Patel (with promoter group)", "promoter_pct": 48.5,
    "charges": [("State Bank of India (term loan, solar assets, security trustee)", 1500.00, "18/11/2025"),
                ("REC Limited (term loan, hybrid project assets)", 1200.00, "22/01/2026"),
                ("Bank of Baroda (cash credit, current assets)", 500.00, "05/07/2025")],
    # outstanding adds up to standalone borrowings at 31-Mar-2026: long-term ₹3,810.76 Cr, short-term ₹858.61 Cr
    "bureau": [("State Bank of India", "TL", 1500.00, 1320.40, 0, 0, "Standard"),
               ("REC Limited", "TL", 1200.00, 1105.20, 0, 0, "Standard"),
               ("Indian Renewable Energy Development Agency", "TL", 900.00, 812.30, 0, 0, "Standard"),
               ("Bank of Baroda", "TL", 650.00, 572.86, 0, 0, "Standard"),
               ("Bank of Baroda", "CC", 500.00, 458.61, 0, 0, "Standard"),
               ("Axis Bank Limited", "WCDL", 450.00, 400.00, 0, 0, "Standard")],
    "bureau_head": {"cmr": "CMR-4", "enquiries": 6},
    "bureau_note": "Outstanding adds up to the audited borrowings at 31-Mar-2026 (Rs 4,669.37 Cr: term loans Rs 3,810.76 Cr, "
                   "working capital Rs 858.61 Cr). Lenders and limits are illustrative. Six enquiries in six months reflect "
                   "fresh project debt being raised.",
    "revenue_cr": 1989.50, "revenue_prev_cr": 1592.00, "growth": 0.25,
    "gst_rate": 0.12, "gst_share": 0.62,
    "gst_nature": "Supplier of Services (solar EPC for captive customers); electricity sales (exempt)",
    "gst_note": "Taxable value is about 62% of reported revenue: sale of electricity by the independent power producer "
                "business is exempt from GST and is not in GSTR-3B.",
    "bank_name": "Bank of Baroda", "bank_branch": "Bank of Baroda, Corporate Financial Services Branch, Surat",
    "acct_last4": "3398", "opening_balance_cr": 61.2,
    "h1_weights": [1.1, 1.15, 0.95, 0.85, 0.9, 1.05],
}

if __name__ == "__main__":
    prepare(SPEC, HERE, download_public="--no-download" not in sys.argv)
