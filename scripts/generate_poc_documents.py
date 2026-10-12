#!/usr/bin/env python3
"""
POC Document Generator — Production-Grade
==========================================
Generates realistic PDFs, Excel, and CSV documents for 4 case types:
  BMFG001 — Listed NTB (clean)
  PINF001 — Listed NTB with intentional mismatches
  SPHR001 — Private NTB (synthetic pack)
  OLOG001 — Private ETB (synthetic + internal conduct)

Uses: reportlab (PDF), openpyxl (Excel), csv (standard library)
"""

import csv
import json
import os
import sys
from datetime import date, datetime
from io import BytesIO
from pathlib import Path

# reportlab imports
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

# openpyxl imports
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill, numbers

_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
STORAGE = _root / "storage" / "documents"

# ─── Custom Styles ───────────────────────────────────────────────────────────

def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle(name='TitleCover', parent=ss['Title'],
                          fontSize=22, spaceAfter=20, alignment=TA_CENTER,
                          textColor=colors.HexColor('#1a3a6a')))
    ss.add(ParagraphStyle(name='SubTitle', parent=ss['Heading2'],
                          fontSize=14, spaceAfter=12, alignment=TA_CENTER,
                          textColor=colors.HexColor('#444444')))
    ss.add(ParagraphStyle(name='SectionHead', parent=ss['Heading2'],
                          fontSize=13, spaceBefore=16, spaceAfter=8,
                          textColor=colors.HexColor('#1a3a6a'),
                          borderWidth=1, borderColor=colors.HexColor('#1a3a6a'),
                          borderPadding=4))
    ss.add(ParagraphStyle(name='BodyNarrative', parent=ss['Normal'],
                          fontSize=10, leading=14, spaceAfter=8))
    ss.add(ParagraphStyle(name='SmallNote', parent=ss['Normal'],
                          fontSize=8, textColor=colors.gray))
    ss.add(ParagraphStyle(name='TableHeader', parent=ss['Normal'],
                          fontSize=9, textColor=colors.white, alignment=TA_CENTER))
    return ss


def _table_style():
    return TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a3a6a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f4fa')]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ])


# ═══════════════════════════════════════════════════════════════════════════════
#  Company Financial Data (3 years)
# ═══════════════════════════════════════════════════════════════════════════════

COMPANY_DATA = {
    "BMFG001": {
        "name": "Bharat Manufacturing Group Ltd",
        "cin": "L29100MH2008PLC123456",
        "pan": "AABCB1234F",
        "gstin": "27AABCB1234F1Z5",
        "sector": "Manufacturing — Auto Components",
        "listed": True, "exchange": "BSE (532001) / NSE (BHARATMFG)",
        "incorporated": "14-Mar-2008",
        "registered": "Plot 45, MIDC Chakan, Pune, Maharashtra 410501",
        "auth_cap": 200.0, "paid_up": 125.0,
        "rating": "CRISIL A+/Stable",
        "directors": [
            ("Rajesh Kumar Mehta", "00123456", "Managing Director", "25.40%"),
            ("Sunita Rajesh Mehta", "00234567", "Whole-Time Director", "18.20%"),
            ("Anand Prakash Joshi", "01345678", "Independent Director", "0.00%"),
            ("Kavita Sundaram", "02456789", "Independent Director", "0.00%"),
        ],
        "auditor": "M/s Sharma & Associates, Chartered Accountants",
        "employees": 1850,
        # FY2024, FY2023, FY2022

        "revenue": [1850.00, 1620.00, 1385.00],
        "other_income": [12.50, 9.80, 7.20],
        "raw_material": [962.00, 858.60, 748.90],
        "employee_cost": [203.50, 178.20, 152.35],
        "other_expenses": [248.50, 218.70, 190.25],
        "ebitda": [448.50, 374.30, 300.70],
        "depreciation": [93.00, 82.50, 71.00],
        "ebit": [355.50, 291.80, 229.70],
        "finance_cost": [67.00, 59.80, 52.40],
        "pbt": [288.50, 232.00, 177.30],
        "tax": [72.13, 58.00, 44.33],
        "pat": [216.37, 174.00, 132.97],
        # Balance sheet
        "total_assets": [1710.00, 1480.00, 1265.00],
        "fixed_assets": [780.00, 690.00, 595.00],
        "current_assets": [620.00, 530.00, 445.00],
        "investments": [310.00, 260.00, 225.00],
        "total_equity": [685.00, 580.00, 490.00],
        "long_term_debt": [480.00, 420.00, 370.00],
        "short_term_debt": [225.00, 200.00, 175.00],
        "current_liabilities": [385.00, 340.00, 295.00],
        "trade_receivables": [220.00, 195.00, 170.00],
        "inventory": [185.00, 162.00, 140.00],
        "cash_equivalents": [95.00, 78.00, 62.00],
        "trade_payables": [148.00, 132.00, 115.00],
        "total_debt": [705.00, 620.00, 545.00],
        # Cash flow
        "ocf": [310.00, 262.00, 205.00],
        "capex": [-165.00, -145.00, -120.00],
        "fcff": [145.00, 117.00, 85.00],
        # Provisional FY2025 (clean — matches trend)
        "prov_revenue": 2065.00,
        "prov_ebitda": 506.00,
        "prov_pat": 248.00,
        # Exchange filing Q3FY2025 (clean — proportional)
        "exchange_revenue_q3": 1535.00,  # ~9m = 74% of annual
        # GST aggregate FY2024
        "gst_turnover_fy2024": 1845.00,  # within 5% of audited
    },

    "PINF001": {
        "name": "Pinnacle Infrastructure Projects Ltd",
        "cin": "U45200DL2010PLC234567",
        "pan": "AADCP5678G",
        "gstin": "07AADCP5678G1H3",
        "sector": "Infrastructure — Road & Bridges",
        "listed": True, "exchange": "BSE (533015) / NSE (PININFRA)",
        "incorporated": "22-Jul-2010",
        "registered": "Tower B, Jasola Business District, New Delhi 110025",
        "auth_cap": 500.0, "paid_up": 280.0,
        "rating": "CARE BBB-/Watch Negative",
        "directors": [
            ("Vikram Singh Chauhan", "03567890", "Chairman & MD", "42.10%"),
            ("Rakesh Bhatia", "04678901", "Executive Director", "12.30%"),
            ("Priya Menon", "05789012", "Independent Director", "0.00%"),
            ("Deepak Srinivasan", "06890123", "Nominee Director — IDBI", "0.00%"),
        ],
        "auditor": "M/s Kapoor Mehta & Co, Chartered Accountants",
        "employees": 3200,
        "revenue": [1200.00, 1050.00, 880.00],
        "other_income": [8.50, 6.20, 5.00],
        "raw_material": [588.00, 520.80, 440.00],
        "employee_cost": [132.00, 115.50, 96.80],
        "other_expenses": [192.00, 168.00, 140.80],
        "ebitda": [296.50, 251.90, 207.40],
        "depreciation": [108.00, 94.50, 79.20],
        "ebit": [188.50, 157.40, 128.20],
        "finance_cost": [144.00, 126.00, 105.60],
        "pbt": [44.50, 31.40, 22.60],
        "tax": [11.13, 7.85, 5.65],
        "pat": [33.37, 23.55, 16.95],
        "total_assets": [3850.00, 3400.00, 2900.00],
        "fixed_assets": [2350.00, 2080.00, 1780.00],
        "current_assets": [980.00, 870.00, 740.00],
        "investments": [520.00, 450.00, 380.00],
        "total_equity": [780.00, 750.00, 730.00],
        "long_term_debt": [1950.00, 1700.00, 1420.00],
        "short_term_debt": [650.00, 540.00, 420.00],
        "current_liabilities": [570.00, 510.00, 450.00],
        "trade_receivables": [450.00, 395.00, 335.00],
        "inventory": [280.00, 248.00, 210.00],
        "cash_equivalents": [42.00, 35.00, 28.00],
        "trade_payables": [310.00, 275.00, 230.00],
        "total_debt": [2600.00, 2240.00, 1840.00],
        "ocf": [185.00, 152.00, 118.00],
        "capex": [-380.00, -350.00, -310.00],
        "fcff": [-195.00, -198.00, -192.00],
        # ── INTENTIONAL MISMATCHES for validation testing ──
        "prov_revenue": 1350.00,       # !! 12.5% higher than audited FY2024
        "prov_ebitda": 345.00,         # !! inflated
        "prov_pat": 52.00,            # !! inflated
        "exchange_revenue_q3": 880.00,  # 9m  → annualized ~1173 (LOWER than audited 1200)
        "gst_turnover_fy2024": 1250.00, # !! 4.2% higher than audited
    },

    "SPHR001": {
        "name": "Sunrise Pharmaceuticals Pvt Ltd",
        "cin": "U24200GJ2012PTC345678",
        "pan": "AAPCS9012H",
        "gstin": "24AAPCS9012H1Z8",
        "sector": "Pharmaceuticals — API Manufacturing",
        "listed": False, "exchange": None,
        "incorporated": "05-Sep-2012",
        "registered": "Survey No 142, GIDC Ankleshwar, Gujarat 393002",
        "auth_cap": 50.0, "paid_up": 35.0,
        "rating": "ICRA A-/Stable",
        "directors": [
            ("Dr. Hemant Patel", "07901234", "Managing Director", "52.00%"),
            ("Neha Hemant Patel", "08012345", "Whole-Time Director", "23.00%"),
            ("Suresh Desai", "09123456", "Director", "15.00%"),
        ],
        "auditor": "M/s Desai Shah & Associates, Chartered Accountants",
        "employees": 680,
        "revenue": [420.00, 365.00, 310.00],
        "other_income": [3.50, 2.80, 2.20],
        "raw_material": [168.00, 149.65, 130.20],
        "employee_cost": [54.60, 47.45, 40.30],
        "other_expenses": [67.20, 58.40, 49.60],
        "ebitda": [133.70, 112.30, 92.10],
        "depreciation": [29.40, 25.55, 21.70],
        "ebit": [104.30, 86.75, 70.40],
        "finance_cost": [22.00, 19.50, 17.10],
        "pbt": [82.30, 67.25, 53.30],
        "tax": [20.58, 16.81, 13.33],
        "pat": [61.72, 50.44, 39.97],
        "total_assets": [680.00, 585.00, 495.00],
        "fixed_assets": [320.00, 278.00, 238.00],
        "current_assets": [255.00, 218.00, 185.00],
        "investments": [105.00, 89.00, 72.00],
        "total_equity": [285.00, 240.00, 200.00],
        "long_term_debt": [180.00, 165.00, 148.00],
        "short_term_debt": [85.00, 72.00, 60.00],
        "current_liabilities": [215.00, 180.00, 147.00],
        "trade_receivables": [95.00, 82.00, 70.00],
        "inventory": [85.00, 73.00, 62.00],
        "cash_equivalents": [32.00, 28.00, 22.00],
        "trade_payables": [65.00, 56.00, 48.00],
        "total_debt": [265.00, 237.00, 208.00],
        "ocf": [92.00, 75.00, 58.00],
        "capex": [-62.00, -55.00, -48.00],
        "fcff": [30.00, 20.00, 10.00],
        "prov_revenue": 475.00,
        "prov_ebitda": 152.00,
        "prov_pat": 72.00,
        "exchange_revenue_q3": None,  # Unlisted
        "gst_turnover_fy2024": 418.00,
    },

    "OLOG001": {
        "name": "Omega Logistics & Supply Chain Pvt Ltd",
        "cin": "U63000KA2015PTC456789",
        "pan": "AAFCO3456J",
        "gstin": "29AAFCO3456J1Z2",
        "sector": "Logistics — 3PL / Warehousing",
        "listed": False, "exchange": None,
        "incorporated": "18-Jan-2015",
        "registered": "No 28, Whitefield Main Road, Bangalore, Karnataka 560066",
        "auth_cap": 25.0, "paid_up": 15.0,
        "rating": "CARE BBB/Stable",
        "directors": [
            ("Arjun Reddy", "10234567", "Managing Director", "38.00%"),
            ("Meera Krishnan", "11345678", "Director — Operations", "22.00%"),
            ("Finance First Fund", "N/A", "Nominee Director — PE", "25.00%"),
        ],
        "auditor": "M/s Narayana & Co, Chartered Accountants",
        "employees": 520,
        "revenue": [320.00, 275.00, 230.00],
        "other_income": [2.80, 2.20, 1.80],
        "raw_material": [0.00, 0.00, 0.00],  # services company
        "employee_cost": [83.20, 71.50, 59.80],
        "other_expenses": [172.80, 148.50, 124.20],
        "ebitda": [66.80, 57.20, 47.80],
        "depreciation": [24.00, 20.63, 17.25],
        "ebit": [42.80, 36.57, 30.55],
        "finance_cost": [18.50, 16.00, 13.80],
        "pbt": [24.30, 20.57, 16.75],
        "tax": [6.08, 5.14, 4.19],
        "pat": [18.22, 15.43, 12.56],
        "total_assets": [480.00, 415.00, 350.00],
        "fixed_assets": [240.00, 208.00, 175.00],
        "current_assets": [165.00, 142.00, 118.00],
        "investments": [75.00, 65.00, 57.00],
        "total_equity": [155.00, 140.00, 128.00],
        "long_term_debt": [165.00, 142.00, 115.00],
        "short_term_debt": [65.00, 52.00, 40.00],
        "current_liabilities": [160.00, 133.00, 107.00],
        "trade_receivables": [72.00, 62.00, 52.00],
        "inventory": [18.00, 15.00, 12.00],
        "cash_equivalents": [22.00, 18.00, 15.00],
        "trade_payables": [48.00, 42.00, 35.00],
        "total_debt": [230.00, 194.00, 155.00],
        "ocf": [45.00, 38.00, 30.00],
        "capex": [-52.00, -48.00, -42.00],
        "fcff": [-7.00, -10.00, -12.00],
        "prov_revenue": 358.00,
        "prov_ebitda": 75.00,
        "prov_pat": 22.00,
        "exchange_revenue_q3": None,
        "gst_turnover_fy2024": 318.00,
    },
}

# ETB Conduct Data for OLOG001 only
ETB_CONDUCT = {
    "account_conduct": [
        {"month": "Apr-2024", "avg_balance_cr": 3.20, "credit_turnover_cr": 28.50, "debit_turnover_cr": 27.80, "cheque_returns": 0, "limit": 50.00, "utilized": 42.00},
        {"month": "May-2024", "avg_balance_cr": 2.80, "credit_turnover_cr": 26.20, "debit_turnover_cr": 25.90, "cheque_returns": 1, "limit": 50.00, "utilized": 44.50},
        {"month": "Jun-2024", "avg_balance_cr": 2.50, "credit_turnover_cr": 24.80, "debit_turnover_cr": 25.10, "cheque_returns": 0, "limit": 50.00, "utilized": 46.20},
        {"month": "Jul-2024", "avg_balance_cr": 1.90, "credit_turnover_cr": 22.50, "debit_turnover_cr": 23.80, "cheque_returns": 2, "limit": 50.00, "utilized": 47.80},
        {"month": "Aug-2024", "avg_balance_cr": 1.50, "credit_turnover_cr": 21.00, "debit_turnover_cr": 22.50, "cheque_returns": 1, "limit": 50.00, "utilized": 48.50},
        {"month": "Sep-2024", "avg_balance_cr": 2.10, "credit_turnover_cr": 27.00, "debit_turnover_cr": 26.50, "cheque_returns": 0, "limit": 50.00, "utilized": 45.00},
        {"month": "Oct-2024", "avg_balance_cr": 1.80, "credit_turnover_cr": 25.50, "debit_turnover_cr": 26.20, "cheque_returns": 3, "limit": 50.00, "utilized": 47.00},
        {"month": "Nov-2024", "avg_balance_cr": 1.20, "credit_turnover_cr": 23.80, "debit_turnover_cr": 25.00, "cheque_returns": 2, "limit": 50.00, "utilized": 49.00},
        {"month": "Dec-2024", "avg_balance_cr": 0.80, "credit_turnover_cr": 20.50, "debit_turnover_cr": 22.80, "cheque_returns": 4, "limit": 50.00, "utilized": 49.50},
        {"month": "Jan-2025", "avg_balance_cr": 1.50, "credit_turnover_cr": 26.00, "debit_turnover_cr": 25.50, "cheque_returns": 1, "limit": 50.00, "utilized": 47.50},
        {"month": "Feb-2025", "avg_balance_cr": 2.00, "credit_turnover_cr": 28.00, "debit_turnover_cr": 27.20, "cheque_returns": 0, "limit": 50.00, "utilized": 46.00},
        {"month": "Mar-2025", "avg_balance_cr": 2.30, "credit_turnover_cr": 30.00, "debit_turnover_cr": 29.00, "cheque_returns": 1, "limit": 50.00, "utilized": 44.50},
    ],
    "repayment_history": [
        {"month": "Apr-2024", "installment_due_cr": 2.50, "paid_cr": 2.50, "paid_date": "05-Apr-2024", "status": "OnTime"},
        {"month": "May-2024", "installment_due_cr": 2.50, "paid_cr": 2.50, "paid_date": "08-May-2024", "status": "OnTime"},
        {"month": "Jun-2024", "installment_due_cr": 2.50, "paid_cr": 2.50, "paid_date": "05-Jun-2024", "status": "OnTime"},
        {"month": "Jul-2024", "installment_due_cr": 2.50, "paid_cr": 2.00, "paid_date": "15-Jul-2024", "status": "PartialDelay"},
        {"month": "Aug-2024", "installment_due_cr": 2.50, "paid_cr": 3.00, "paid_date": "22-Aug-2024", "status": "Delay15"},
        {"month": "Sep-2024", "installment_due_cr": 2.50, "paid_cr": 2.50, "paid_date": "10-Sep-2024", "status": "OnTime"},
        {"month": "Oct-2024", "installment_due_cr": 2.50, "paid_cr": 2.50, "paid_date": "28-Oct-2024", "status": "Delay20"},
        {"month": "Nov-2024", "installment_due_cr": 2.50, "paid_cr": 2.00, "paid_date": "05-Dec-2024", "status": "Delay35"},
        {"month": "Dec-2024", "installment_due_cr": 2.50, "paid_cr": 3.00, "paid_date": "08-Jan-2025", "status": "Delay38"},
        {"month": "Jan-2025", "installment_due_cr": 2.50, "paid_cr": 2.50, "paid_date": "10-Jan-2025", "status": "OnTime"},
        {"month": "Feb-2025", "installment_due_cr": 2.50, "paid_cr": 2.50, "paid_date": "07-Feb-2025", "status": "OnTime"},
        {"month": "Mar-2025", "installment_due_cr": 2.50, "paid_cr": 2.50, "paid_date": "05-Mar-2025", "status": "OnTime"},
    ],
    "covenant_tracker": [
        {"period": "Q1-FY2024", "covenant": "DSCR >= 1.20x", "required": "1.20", "actual": "1.35", "status": "Compliant"},
        {"period": "Q2-FY2024", "covenant": "DSCR >= 1.20x", "required": "1.20", "actual": "1.28", "status": "Compliant"},
        {"period": "Q3-FY2024", "covenant": "DSCR >= 1.20x", "required": "1.20", "actual": "1.15", "status": "Breach"},
        {"period": "Q4-FY2024", "covenant": "DSCR >= 1.20x", "required": "1.20", "actual": "1.10", "status": "Breach"},
        {"period": "Q1-FY2025", "covenant": "DSCR >= 1.20x", "required": "1.20", "actual": "1.22", "status": "Compliant"},
        {"period": "Q2-FY2025", "covenant": "DSCR >= 1.20x", "required": "1.20", "actual": "1.18", "status": "Breach"},
        {"period": "Q1-FY2024", "covenant": "D/E <= 2.00x", "required": "2.00", "actual": "1.38", "status": "Compliant"},
        {"period": "Q2-FY2024", "covenant": "D/E <= 2.00x", "required": "2.00", "actual": "1.42", "status": "Compliant"},
        {"period": "Q3-FY2024", "covenant": "D/E <= 2.00x", "required": "2.00", "actual": "1.48", "status": "Compliant"},
        {"period": "Q4-FY2024", "covenant": "D/E <= 2.00x", "required": "2.00", "actual": "1.48", "status": "Compliant"},
        {"period": "Q1-FY2025", "covenant": "Current Ratio >= 1.10x", "required": "1.10", "actual": "1.05", "status": "Breach"},
        {"period": "Q2-FY2025", "covenant": "Current Ratio >= 1.10x", "required": "1.10", "actual": "1.08", "status": "Breach"},
    ],
    "loan_utilization": [
        {"date": "01-Apr-2024", "facility": "CC", "limit_cr": 50.00, "utilized_cr": 42.00, "drawing_power_cr": 48.00},
        {"date": "01-May-2024", "facility": "CC", "limit_cr": 50.00, "utilized_cr": 44.50, "drawing_power_cr": 47.50},
        {"date": "01-Jun-2024", "facility": "CC", "limit_cr": 50.00, "utilized_cr": 46.20, "drawing_power_cr": 47.00},
        {"date": "01-Jul-2024", "facility": "CC", "limit_cr": 50.00, "utilized_cr": 47.80, "drawing_power_cr": 46.50},
        {"date": "01-Aug-2024", "facility": "CC", "limit_cr": 50.00, "utilized_cr": 48.50, "drawing_power_cr": 46.00},
        {"date": "01-Sep-2024", "facility": "CC", "limit_cr": 50.00, "utilized_cr": 45.00, "drawing_power_cr": 47.00},
        {"date": "01-Oct-2024", "facility": "CC", "limit_cr": 50.00, "utilized_cr": 47.00, "drawing_power_cr": 46.50},
        {"date": "01-Nov-2024", "facility": "CC", "limit_cr": 50.00, "utilized_cr": 49.00, "drawing_power_cr": 46.00},
        {"date": "01-Dec-2024", "facility": "CC", "limit_cr": 50.00, "utilized_cr": 49.50, "drawing_power_cr": 45.50},
        {"date": "01-Jan-2025", "facility": "CC", "limit_cr": 50.00, "utilized_cr": 47.50, "drawing_power_cr": 46.50},
        {"date": "01-Feb-2025", "facility": "CC", "limit_cr": 50.00, "utilized_cr": 46.00, "drawing_power_cr": 47.00},
        {"date": "01-Mar-2025", "facility": "CC", "limit_cr": 50.00, "utilized_cr": 44.50, "drawing_power_cr": 48.00},
        {"date": "01-Apr-2024", "facility": "TL", "limit_cr": 85.00, "utilized_cr": 78.00, "drawing_power_cr": 85.00},
        {"date": "01-Jul-2024", "facility": "TL", "limit_cr": 85.00, "utilized_cr": 70.50, "drawing_power_cr": 85.00},
        {"date": "01-Oct-2024", "facility": "TL", "limit_cr": 85.00, "utilized_cr": 63.00, "drawing_power_cr": 85.00},
        {"date": "01-Jan-2025", "facility": "TL", "limit_cr": 85.00, "utilized_cr": 55.50, "drawing_power_cr": 85.00},
    ],
}

# ═══════════════════════════════════════════════════════════════════════════════
#  Auto-populate COMPANY_DATA for 12 real Indian companies
# ═══════════════════════════════════════════════════════════════════════════════

from src.data.real_companies import REAL_COMPANIES
from src.models.canonical_model import BorrowerType

_GSTIN_MAP = {
    "TSTL001": "27AAACT1234A1Z8", "REIL001": "27AAACR2345B1Z6",
    "INFY001": "29AAACI3456C1Z4", "ADPT001": "24AAACA4567D1Z2",
    "BJFN001": "27AABCB5678E1Z3", "CIPL001": "27AAACC6789F1Z1",
    "DLFR001": "06AAACD7890G1Z9", "JSWL001": "27AAACJ8901H1Z7",
    "MRUT001": "06AAACM9012J1Z5", "TITN001": "33AAACT0123K1Z3",
    "NTPC001": "07AAACN1234L1Z1", "YESB001": "27AAACY2345M1Z9",
}

_AUDITOR_MAP = {
    "TSTL001": "M/s Deloitte Haskins & Sells LLP",
    "REIL001": "M/s Chaturvedi & Shah LLP",
    "INFY001": "M/s BSR & Co LLP",
    "ADPT001": "M/s Shah Dhandharia & Co",
    "BJFN001": "M/s S R Batliboi & Associates LLP",
    "CIPL001": "M/s Walker Chandiok & Co LLP",
    "DLFR001": "M/s S R Batliboi & Co LLP",
    "JSWL001": "M/s Price Waterhouse Chartered Accountants LLP",
    "MRUT001": "M/s Deloitte Haskins & Sells LLP",
    "TITN001": "M/s BSR & Co LLP",
    "NTPC001": "M/s S S Kothari Mehta & Co",
    "YESB001": "M/s BSR & Associates LLP",
}

# Exchange filing Q3 revenue overrides for mismatch testing
_EXCHANGE_Q3_OVERRIDE = {
    "DLFR001": 4200.00,   # Much lower — signals stress
    "YESB001": 22500.00,  # Lower than clean annualization
}

def _convert_real_company(eid, rc):
    """Convert a real_companies.py entry to flat COMPANY_DATA format."""
    b = rc["borrower"]
    fins = rc["financials"]
    prov = rc["provisional"]
    dirs = rc["directors"]
    grp = rc.get("group")

    def _fy(key, default=0.0):
        return [
            fins["FY2024"].line_items.get(key, default),
            fins["FY2023"].line_items.get(key, default),
            fins["FY2022"].line_items.get(key, default),
        ]

    doc_dirs = []
    for d in dirs:
        holding = f"{grp.promoter_holding_pct:.2f}%" if d.is_promoter and grp else "0.00%"
        doc_dirs.append((d.name, d.din, d.designation, holding))

    is_listed = (b.borrower_type == BorrowerType.LISTED)
    incorporated = b.date_of_incorporation.strftime("%d-%b-%Y")
    exchange_str = f"BSE / NSE ({b.nse_symbol})" if b.nse_symbol else None
    rev_fy24 = fins["FY2024"].line_items.get("revenue_operating", 0)
    eq3 = _EXCHANGE_Q3_OVERRIDE.get(eid, rev_fy24 * 0.74) if is_listed else None
    gst = rev_fy24 * 0.995  # within 0.5% for clean

    return {
        "name": b.company_name, "cin": b.cin, "pan": b.pan,
        "gstin": _GSTIN_MAP.get(eid, f"99{b.pan}1Z5"),
        "sector": b.subsector or str(b.sector.value),
        "listed": is_listed, "exchange": exchange_str,
        "incorporated": incorporated,
        "registered": b.registered_address,
        "auth_cap": b.authorized_capital, "paid_up": b.paid_up_capital,
        "rating": b.credit_rating,
        "directors": doc_dirs,
        "auditor": _AUDITOR_MAP.get(eid, "M/s SRBC & Co LLP, Chartered Accountants"),
        "employees": b.employee_count or 1000,
        "revenue": _fy("revenue_operating"),
        "other_income": _fy("other_income"),
        "raw_material": _fy("raw_material_cost"),
        "employee_cost": _fy("employee_cost"),
        "other_expenses": _fy("other_expenses"),
        "ebitda": _fy("ebitda"),
        "depreciation": _fy("depreciation"),
        "ebit": _fy("ebit"),
        "finance_cost": _fy("finance_cost"),
        "pbt": _fy("pbt"),
        "tax": _fy("tax"),
        "pat": _fy("pat"),
        "total_assets": _fy("total_assets"),
        "fixed_assets": _fy("fixed_assets"),
        "current_assets": _fy("current_assets"),
        "investments": _fy("investments"),
        "total_equity": _fy("total_equity"),
        "long_term_debt": _fy("long_term_debt"),
        "short_term_debt": _fy("short_term_debt"),
        "current_liabilities": _fy("current_liabilities"),
        "trade_receivables": _fy("trade_receivables"),
        "inventory": _fy("inventory"),
        "cash_equivalents": _fy("cash_equivalents"),
        "trade_payables": _fy("trade_payables"),
        "total_debt": _fy("total_debt"),
        "ocf": _fy("ocf"),
        "capex": _fy("capex"),
        "fcff": _fy("fcff"),
        "prov_revenue": prov.line_items.get("revenue_operating", 0),
        "prov_ebitda": prov.line_items.get("ebitda", 0),
        "prov_pat": prov.line_items.get("pat", 0),
        "exchange_revenue_q3": eq3,
        "gst_turnover_fy2024": gst,
    }

for _eid, _rc in REAL_COMPANIES.items():
    COMPANY_DATA[_eid] = _convert_real_company(_eid, _rc)


# ═══════════════════════════════════════════════════════════════════════════════
#  ETB Conduct Data for real ETB companies (DLFR001, NTPC001, YESB001)
# ═══════════════════════════════════════════════════════════════════════════════

ETB_CONDUCT_ALL = {
    "OLOG001": ETB_CONDUCT,  # Original
    "DLFR001": {
        "account_conduct": [
            {"month": "Apr-2024", "avg_balance_cr": 4.50, "credit_turnover_cr": 52.00, "debit_turnover_cr": 51.20, "cheque_returns": 1, "limit": 1200.00, "utilized": 1080.00},
            {"month": "May-2024", "avg_balance_cr": 4.20, "credit_turnover_cr": 50.00, "debit_turnover_cr": 49.50, "cheque_returns": 2, "limit": 1200.00, "utilized": 1100.00},
            {"month": "Jun-2024", "avg_balance_cr": 3.80, "credit_turnover_cr": 48.00, "debit_turnover_cr": 49.00, "cheque_returns": 3, "limit": 1200.00, "utilized": 1110.00},
            {"month": "Jul-2024", "avg_balance_cr": 3.50, "credit_turnover_cr": 45.00, "debit_turnover_cr": 46.50, "cheque_returns": 2, "limit": 1200.00, "utilized": 1125.00},
            {"month": "Aug-2024", "avg_balance_cr": 3.00, "credit_turnover_cr": 42.00, "debit_turnover_cr": 44.00, "cheque_returns": 4, "limit": 1200.00, "utilized": 1140.00},
            {"month": "Sep-2024", "avg_balance_cr": 3.20, "credit_turnover_cr": 44.00, "debit_turnover_cr": 43.50, "cheque_returns": 3, "limit": 1200.00, "utilized": 1128.00},
            {"month": "Oct-2024", "avg_balance_cr": 2.80, "credit_turnover_cr": 40.00, "debit_turnover_cr": 42.00, "cheque_returns": 5, "limit": 1200.00, "utilized": 1152.00},
            {"month": "Nov-2024", "avg_balance_cr": 2.50, "credit_turnover_cr": 38.00, "debit_turnover_cr": 40.00, "cheque_returns": 6, "limit": 1200.00, "utilized": 1164.00},
            {"month": "Dec-2024", "avg_balance_cr": 2.10, "credit_turnover_cr": 35.00, "debit_turnover_cr": 38.00, "cheque_returns": 8, "limit": 1200.00, "utilized": 1176.00},
            {"month": "Jan-2025", "avg_balance_cr": 2.50, "credit_turnover_cr": 40.00, "debit_turnover_cr": 39.50, "cheque_returns": 5, "limit": 1200.00, "utilized": 1155.00},
            {"month": "Feb-2025", "avg_balance_cr": 2.80, "credit_turnover_cr": 42.00, "debit_turnover_cr": 41.00, "cheque_returns": 4, "limit": 1200.00, "utilized": 1140.00},
            {"month": "Mar-2025", "avg_balance_cr": 3.00, "credit_turnover_cr": 45.00, "debit_turnover_cr": 44.00, "cheque_returns": 3, "limit": 1200.00, "utilized": 1128.00},
        ],
        "repayment_history": [
            {"month": "Apr-2024", "installment_due_cr": 8.50, "paid_cr": 8.50, "paid_date": "05-Apr-2024", "status": "OnTime"},
            {"month": "May-2024", "installment_due_cr": 8.50, "paid_cr": 8.50, "paid_date": "10-May-2024", "status": "OnTime"},
            {"month": "Jun-2024", "installment_due_cr": 8.50, "paid_cr": 8.00, "paid_date": "18-Jun-2024", "status": "PartialDelay"},
            {"month": "Jul-2024", "installment_due_cr": 8.50, "paid_cr": 9.00, "paid_date": "22-Jul-2024", "status": "Delay12"},
            {"month": "Aug-2024", "installment_due_cr": 8.50, "paid_cr": 8.50, "paid_date": "28-Aug-2024", "status": "Delay18"},
            {"month": "Sep-2024", "installment_due_cr": 8.50, "paid_cr": 8.50, "paid_date": "08-Sep-2024", "status": "OnTime"},
            {"month": "Oct-2024", "installment_due_cr": 8.50, "paid_cr": 7.50, "paid_date": "25-Oct-2024", "status": "Delay15"},
            {"month": "Nov-2024", "installment_due_cr": 8.50, "paid_cr": 9.50, "paid_date": "10-Dec-2024", "status": "Delay40"},
            {"month": "Dec-2024", "installment_due_cr": 8.50, "paid_cr": 8.50, "paid_date": "15-Jan-2025", "status": "Delay45"},
            {"month": "Jan-2025", "installment_due_cr": 8.50, "paid_cr": 8.50, "paid_date": "12-Jan-2025", "status": "OnTime"},
            {"month": "Feb-2025", "installment_due_cr": 8.50, "paid_cr": 8.50, "paid_date": "08-Feb-2025", "status": "OnTime"},
            {"month": "Mar-2025", "installment_due_cr": 8.50, "paid_cr": 8.50, "paid_date": "05-Mar-2025", "status": "OnTime"},
        ],
        "covenant_tracker": [
            {"period": "Q1-FY2025", "covenant": "DSCR >= 1.20x", "required": "1.20", "actual": "1.18", "status": "Breach"},
            {"period": "Q2-FY2025", "covenant": "DSCR >= 1.20x", "required": "1.20", "actual": "1.12", "status": "Breach"},
            {"period": "Q3-FY2025", "covenant": "DSCR >= 1.20x", "required": "1.20", "actual": "1.08", "status": "Breach"},
            {"period": "Q4-FY2025", "covenant": "DSCR >= 1.20x", "required": "1.20", "actual": "1.05", "status": "Breach"},
            {"period": "Q1-FY2025", "covenant": "D/E <= 1.50x", "required": "1.50", "actual": "1.11", "status": "Compliant"},
            {"period": "Q3-FY2025", "covenant": "Max Cheque Returns <= 5/qtr", "required": "5", "actual": "11", "status": "Breach"},
        ],
        "loan_utilization": [
            {"date": "01-Apr-2024", "facility": "CC", "limit_cr": 1200.00, "utilized_cr": 1080.00, "drawing_power_cr": 1150.00},
            {"date": "01-Jul-2024", "facility": "CC", "limit_cr": 1200.00, "utilized_cr": 1125.00, "drawing_power_cr": 1120.00},
            {"date": "01-Oct-2024", "facility": "CC", "limit_cr": 1200.00, "utilized_cr": 1152.00, "drawing_power_cr": 1100.00},
            {"date": "01-Jan-2025", "facility": "CC", "limit_cr": 1200.00, "utilized_cr": 1155.00, "drawing_power_cr": 1090.00},
            {"date": "01-Apr-2024", "facility": "TL", "limit_cr": 800.00, "utilized_cr": 680.00, "drawing_power_cr": 800.00},
            {"date": "01-Jul-2024", "facility": "TL", "limit_cr": 800.00, "utilized_cr": 650.00, "drawing_power_cr": 800.00},
            {"date": "01-Oct-2024", "facility": "TL", "limit_cr": 800.00, "utilized_cr": 635.00, "drawing_power_cr": 800.00},
            {"date": "01-Jan-2025", "facility": "TL", "limit_cr": 800.00, "utilized_cr": 620.00, "drawing_power_cr": 800.00},
        ],
    },
    "NTPC001": {
        "account_conduct": [
            {"month": "Apr-2024", "avg_balance_cr": 85.00, "credit_turnover_cr": 4200.00, "debit_turnover_cr": 4150.00, "cheque_returns": 0, "limit": 3000.00, "utilized": 1850.00},
            {"month": "May-2024", "avg_balance_cr": 88.00, "credit_turnover_cr": 4300.00, "debit_turnover_cr": 4250.00, "cheque_returns": 0, "limit": 3000.00, "utilized": 1820.00},
            {"month": "Jun-2024", "avg_balance_cr": 90.00, "credit_turnover_cr": 4400.00, "debit_turnover_cr": 4350.00, "cheque_returns": 0, "limit": 3000.00, "utilized": 1800.00},
            {"month": "Jul-2024", "avg_balance_cr": 92.00, "credit_turnover_cr": 4500.00, "debit_turnover_cr": 4420.00, "cheque_returns": 0, "limit": 3000.00, "utilized": 1780.00},
            {"month": "Aug-2024", "avg_balance_cr": 87.00, "credit_turnover_cr": 4250.00, "debit_turnover_cr": 4200.00, "cheque_returns": 0, "limit": 3000.00, "utilized": 1860.00},
            {"month": "Sep-2024", "avg_balance_cr": 88.00, "credit_turnover_cr": 4350.00, "debit_turnover_cr": 4300.00, "cheque_returns": 0, "limit": 3000.00, "utilized": 1840.00},
            {"month": "Oct-2024", "avg_balance_cr": 91.00, "credit_turnover_cr": 4400.00, "debit_turnover_cr": 4380.00, "cheque_returns": 0, "limit": 3000.00, "utilized": 1810.00},
            {"month": "Nov-2024", "avg_balance_cr": 93.00, "credit_turnover_cr": 4500.00, "debit_turnover_cr": 4480.00, "cheque_returns": 0, "limit": 3000.00, "utilized": 1790.00},
            {"month": "Dec-2024", "avg_balance_cr": 89.00, "credit_turnover_cr": 4350.00, "debit_turnover_cr": 4320.00, "cheque_returns": 0, "limit": 3000.00, "utilized": 1830.00},
            {"month": "Jan-2025", "avg_balance_cr": 94.00, "credit_turnover_cr": 4550.00, "debit_turnover_cr": 4520.00, "cheque_returns": 0, "limit": 3000.00, "utilized": 1770.00},
            {"month": "Feb-2025", "avg_balance_cr": 96.00, "credit_turnover_cr": 4600.00, "debit_turnover_cr": 4570.00, "cheque_returns": 0, "limit": 3000.00, "utilized": 1750.00},
            {"month": "Mar-2025", "avg_balance_cr": 95.00, "credit_turnover_cr": 4600.00, "debit_turnover_cr": 4580.00, "cheque_returns": 0, "limit": 3000.00, "utilized": 1740.00},
        ],
        "repayment_history": [
            {"month": "Apr-2024", "installment_due_cr": 42.00, "paid_cr": 42.00, "paid_date": "03-Apr-2024", "status": "OnTime"},
            {"month": "May-2024", "installment_due_cr": 42.00, "paid_cr": 42.00, "paid_date": "02-May-2024", "status": "OnTime"},
            {"month": "Jun-2024", "installment_due_cr": 42.00, "paid_cr": 42.00, "paid_date": "04-Jun-2024", "status": "OnTime"},
            {"month": "Jul-2024", "installment_due_cr": 42.00, "paid_cr": 42.00, "paid_date": "03-Jul-2024", "status": "OnTime"},
            {"month": "Aug-2024", "installment_due_cr": 42.00, "paid_cr": 42.00, "paid_date": "05-Aug-2024", "status": "OnTime"},
            {"month": "Sep-2024", "installment_due_cr": 42.00, "paid_cr": 42.00, "paid_date": "03-Sep-2024", "status": "OnTime"},
            {"month": "Oct-2024", "installment_due_cr": 42.00, "paid_cr": 42.00, "paid_date": "02-Oct-2024", "status": "OnTime"},
            {"month": "Nov-2024", "installment_due_cr": 42.00, "paid_cr": 42.00, "paid_date": "04-Nov-2024", "status": "OnTime"},
            {"month": "Dec-2024", "installment_due_cr": 42.00, "paid_cr": 42.00, "paid_date": "03-Dec-2024", "status": "OnTime"},
            {"month": "Jan-2025", "installment_due_cr": 42.00, "paid_cr": 42.00, "paid_date": "02-Jan-2025", "status": "OnTime"},
            {"month": "Feb-2025", "installment_due_cr": 42.00, "paid_cr": 42.00, "paid_date": "04-Feb-2025", "status": "OnTime"},
            {"month": "Mar-2025", "installment_due_cr": 42.00, "paid_cr": 42.00, "paid_date": "03-Mar-2025", "status": "OnTime"},
        ],
        "covenant_tracker": [
            {"period": "Q1-FY2025", "covenant": "DSCR >= 1.30x", "required": "1.30", "actual": "1.55", "status": "Compliant"},
            {"period": "Q2-FY2025", "covenant": "DSCR >= 1.30x", "required": "1.30", "actual": "1.52", "status": "Compliant"},
            {"period": "Q3-FY2025", "covenant": "DSCR >= 1.30x", "required": "1.30", "actual": "1.50", "status": "Compliant"},
            {"period": "Q4-FY2025", "covenant": "DSCR >= 1.30x", "required": "1.30", "actual": "1.52", "status": "Compliant"},
            {"period": "Q1-FY2025", "covenant": "D/E <= 1.20x", "required": "1.20", "actual": "1.06", "status": "Compliant"},
            {"period": "Q4-FY2025", "covenant": "Fixed Asset Coverage >= 1.50x", "required": "1.50", "actual": "1.53", "status": "Compliant"},
        ],
        "loan_utilization": [
            {"date": "01-Apr-2024", "facility": "CC", "limit_cr": 3000.00, "utilized_cr": 1850.00, "drawing_power_cr": 2800.00},
            {"date": "01-Jul-2024", "facility": "CC", "limit_cr": 3000.00, "utilized_cr": 1780.00, "drawing_power_cr": 2820.00},
            {"date": "01-Oct-2024", "facility": "CC", "limit_cr": 3000.00, "utilized_cr": 1810.00, "drawing_power_cr": 2800.00},
            {"date": "01-Jan-2025", "facility": "CC", "limit_cr": 3000.00, "utilized_cr": 1770.00, "drawing_power_cr": 2850.00},
            {"date": "01-Apr-2024", "facility": "TL", "limit_cr": 5000.00, "utilized_cr": 3500.00, "drawing_power_cr": 5000.00},
            {"date": "01-Jul-2024", "facility": "TL", "limit_cr": 5000.00, "utilized_cr": 3350.00, "drawing_power_cr": 5000.00},
            {"date": "01-Oct-2024", "facility": "TL", "limit_cr": 5000.00, "utilized_cr": 3200.00, "drawing_power_cr": 5000.00},
            {"date": "01-Jan-2025", "facility": "TL", "limit_cr": 5000.00, "utilized_cr": 3050.00, "drawing_power_cr": 5000.00},
        ],
    },
    "YESB001": {
        "account_conduct": [
            {"month": "Apr-2024", "avg_balance_cr": 15.00, "credit_turnover_cr": 850.00, "debit_turnover_cr": 845.00, "cheque_returns": 2, "limit": 1000.00, "utilized": 900.00},
            {"month": "May-2024", "avg_balance_cr": 14.00, "credit_turnover_cr": 830.00, "debit_turnover_cr": 828.00, "cheque_returns": 2, "limit": 1000.00, "utilized": 908.00},
            {"month": "Jun-2024", "avg_balance_cr": 13.00, "credit_turnover_cr": 810.00, "debit_turnover_cr": 815.00, "cheque_returns": 3, "limit": 1000.00, "utilized": 915.00},
            {"month": "Jul-2024", "avg_balance_cr": 12.00, "credit_turnover_cr": 820.00, "debit_turnover_cr": 825.00, "cheque_returns": 4, "limit": 1000.00, "utilized": 920.00},
            {"month": "Aug-2024", "avg_balance_cr": 11.00, "credit_turnover_cr": 800.00, "debit_turnover_cr": 808.00, "cheque_returns": 4, "limit": 1000.00, "utilized": 928.00},
            {"month": "Sep-2024", "avg_balance_cr": 10.00, "credit_turnover_cr": 780.00, "debit_turnover_cr": 790.00, "cheque_returns": 5, "limit": 1000.00, "utilized": 935.00},
            {"month": "Oct-2024", "avg_balance_cr": 8.50, "credit_turnover_cr": 760.00, "debit_turnover_cr": 770.00, "cheque_returns": 7, "limit": 1000.00, "utilized": 942.00},
            {"month": "Nov-2024", "avg_balance_cr": 7.00, "credit_turnover_cr": 740.00, "debit_turnover_cr": 752.00, "cheque_returns": 8, "limit": 1000.00, "utilized": 950.00},
            {"month": "Dec-2024", "avg_balance_cr": 5.50, "credit_turnover_cr": 720.00, "debit_turnover_cr": 740.00, "cheque_returns": 10, "limit": 1000.00, "utilized": 960.00},
            {"month": "Jan-2025", "avg_balance_cr": 6.00, "credit_turnover_cr": 730.00, "debit_turnover_cr": 738.00, "cheque_returns": 8, "limit": 1000.00, "utilized": 955.00},
            {"month": "Feb-2025", "avg_balance_cr": 6.50, "credit_turnover_cr": 740.00, "debit_turnover_cr": 745.00, "cheque_returns": 7, "limit": 1000.00, "utilized": 948.00},
            {"month": "Mar-2025", "avg_balance_cr": 5.80, "credit_turnover_cr": 725.00, "debit_turnover_cr": 735.00, "cheque_returns": 12, "limit": 1000.00, "utilized": 958.00},
        ],
        "repayment_history": [
            {"month": "Apr-2024", "installment_due_cr": 22.00, "paid_cr": 22.00, "paid_date": "08-Apr-2024", "status": "OnTime"},
            {"month": "May-2024", "installment_due_cr": 22.00, "paid_cr": 22.00, "paid_date": "10-May-2024", "status": "OnTime"},
            {"month": "Jun-2024", "installment_due_cr": 22.00, "paid_cr": 20.00, "paid_date": "18-Jun-2024", "status": "PartialDelay"},
            {"month": "Jul-2024", "installment_due_cr": 22.00, "paid_cr": 24.00, "paid_date": "22-Jul-2024", "status": "Delay12"},
            {"month": "Aug-2024", "installment_due_cr": 22.00, "paid_cr": 22.00, "paid_date": "25-Aug-2024", "status": "Delay15"},
            {"month": "Sep-2024", "installment_due_cr": 22.00, "paid_cr": 22.00, "paid_date": "12-Sep-2024", "status": "OnTime"},
            {"month": "Oct-2024", "installment_due_cr": 22.00, "paid_cr": 20.00, "paid_date": "28-Oct-2024", "status": "Delay18"},
            {"month": "Nov-2024", "installment_due_cr": 22.00, "paid_cr": 24.00, "paid_date": "15-Dec-2024", "status": "Delay45"},
            {"month": "Dec-2024", "installment_due_cr": 22.00, "paid_cr": 22.00, "paid_date": "18-Jan-2025", "status": "Delay48"},
            {"month": "Jan-2025", "installment_due_cr": 22.00, "paid_cr": 22.00, "paid_date": "15-Jan-2025", "status": "OnTime"},
            {"month": "Feb-2025", "installment_due_cr": 22.00, "paid_cr": 22.00, "paid_date": "10-Feb-2025", "status": "OnTime"},
            {"month": "Mar-2025", "installment_due_cr": 22.00, "paid_cr": 18.00, "paid_date": "28-Mar-2025", "status": "Delay18"},
        ],
        "covenant_tracker": [
            {"period": "Q1-FY2025", "covenant": "Capital Adequacy >= 15%", "required": "15.0", "actual": "17.8", "status": "Compliant"},
            {"period": "Q2-FY2025", "covenant": "Capital Adequacy >= 15%", "required": "15.0", "actual": "17.4", "status": "Compliant"},
            {"period": "Q3-FY2025", "covenant": "GNPA Ratio <= 3.0%", "required": "3.0", "actual": "2.8", "status": "Compliant"},
            {"period": "Q4-FY2025", "covenant": "GNPA Ratio <= 3.0%", "required": "3.0", "actual": "3.5", "status": "Breach"},
            {"period": "Q4-FY2025", "covenant": "Max Cheque Returns <= 5/qtr", "required": "5", "actual": "12", "status": "Breach"},
        ],
        "loan_utilization": [
            {"date": "01-Apr-2024", "facility": "CC", "limit_cr": 1000.00, "utilized_cr": 900.00, "drawing_power_cr": 950.00},
            {"date": "01-Jul-2024", "facility": "CC", "limit_cr": 1000.00, "utilized_cr": 920.00, "drawing_power_cr": 940.00},
            {"date": "01-Oct-2024", "facility": "CC", "limit_cr": 1000.00, "utilized_cr": 942.00, "drawing_power_cr": 930.00},
            {"date": "01-Jan-2025", "facility": "CC", "limit_cr": 1000.00, "utilized_cr": 955.00, "drawing_power_cr": 920.00},
            {"date": "01-Apr-2024", "facility": "TL", "limit_cr": 2500.00, "utilized_cr": 2400.00, "drawing_power_cr": 2500.00},
            {"date": "01-Jul-2024", "facility": "TL", "limit_cr": 2500.00, "utilized_cr": 2380.00, "drawing_power_cr": 2500.00},
            {"date": "01-Oct-2024", "facility": "TL", "limit_cr": 2500.00, "utilized_cr": 2360.00, "drawing_power_cr": 2500.00},
            {"date": "01-Jan-2025", "facility": "TL", "limit_cr": 2500.00, "utilized_cr": 2350.00, "drawing_power_cr": 2500.00},
        ],
    },
}

FISCAL_YEARS = ["FY2024", "FY2023", "FY2022"]


# ═══════════════════════════════════════════════════════════════════════════════
#  PDF Generators
# ═══════════════════════════════════════════════════════════════════════════════

def _pdf_buf(build_fn, **kwargs):
    """Generate PDF into a BytesIO buffer."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            topMargin=20*mm, bottomMargin=20*mm,
                            leftMargin=18*mm, rightMargin=18*mm)
    ss = _styles()
    story = build_fn(ss, **kwargs)
    doc.build(story)
    return buf.getvalue()


def _fmt(v):
    """Format number with commas."""
    if isinstance(v, float):
        return f"{v:,.2f}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


def _pct(new, old):
    if old == 0:
        return "N/A"
    return f"{((new - old) / abs(old)) * 100:.1f}%"


# ────────────────────────────────────────────────────────────────────
#  1. Annual Report PDF
# ────────────────────────────────────────────────────────────────────

def gen_annual_report(eid):
    d = COMPANY_DATA[eid]
    return _pdf_buf(_build_annual_report, d=d, eid=eid)


def _build_annual_report(ss, d, eid):
    s = []
    s.append(Spacer(1, 30*mm))
    s.append(Paragraph(d["name"], ss['TitleCover']))
    s.append(Paragraph(f"Annual Report FY2024", ss['SubTitle']))
    s.append(Spacer(1, 10*mm))
    s.append(Paragraph(f"CIN: {d['cin']}", ss['SubTitle']))
    s.append(Paragraph(f"Registered Office: {d['registered']}", ss['BodyNarrative']))
    s.append(Spacer(1, 5*mm))
    s.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#1a3a6a')))
    s.append(Spacer(1, 5*mm))
    s.append(Paragraph(f"PAN: {d['pan']}  |  GSTIN: {d['gstin']}", ss['BodyNarrative']))
    if d["listed"]:
        s.append(Paragraph(f"Listed on: {d['exchange']}", ss['BodyNarrative']))
    s.append(Paragraph(f"Credit Rating: {d['rating']}", ss['BodyNarrative']))
    s.append(Paragraph(f"Statutory Auditor: {d['auditor']}", ss['BodyNarrative']))
    s.append(Paragraph(f"No. of Employees: {d['employees']}", ss['BodyNarrative']))
    s.append(PageBreak())

    # Directors' Report
    s.append(Paragraph("DIRECTORS' REPORT", ss['SectionHead']))
    s.append(Paragraph(
        f"To the Members of {d['name']},<br/><br/>"
        f"Your Directors have pleasure in presenting the Annual Report together with the "
        f"Audited Financial Statements for the financial year ended March 31, 2024.<br/><br/>"
        f"<b>Financial Performance</b><br/>"
        f"Revenue from operations increased to ₹{_fmt(d['revenue'][0])} Cr from ₹{_fmt(d['revenue'][1])} Cr "
        f"in the previous year, registering a growth of {_pct(d['revenue'][0], d['revenue'][1])}. "
        f"EBITDA stood at ₹{_fmt(d['ebitda'][0])} Cr ({_fmt(d['ebitda'][0]/d['revenue'][0]*100)}% margin) "
        f"compared to ₹{_fmt(d['ebitda'][1])} Cr in FY2023. "
        f"Net profit after tax was ₹{_fmt(d['pat'][0])} Cr vs ₹{_fmt(d['pat'][1])} Cr.<br/><br/>"
        f"<b>Industry Overview</b><br/>"
        f"The company operates in the {d['sector']} segment which witnessed steady growth during FY2024. "
        f"Management remains optimistic about future prospects driven by strong order pipeline and "
        f"capacity expansion initiatives."
        , ss['BodyNarrative']))
    s.append(Spacer(1, 5*mm))

    # Board of Directors table
    s.append(Paragraph("BOARD OF DIRECTORS", ss['SectionHead']))
    tdata = [["Name", "DIN", "Designation", "Shareholding"]]
    for name, din, desig, hold in d["directors"]:
        tdata.append([name, din, desig, hold])
    t = Table(tdata, colWidths=[55*mm, 30*mm, 50*mm, 30*mm])
    t.setStyle(_table_style())
    s.append(t)
    s.append(PageBreak())

    # Financial Highlights
    s.append(Paragraph("FINANCIAL HIGHLIGHTS (₹ Crore)", ss['SectionHead']))
    fin_data = [["Particulars", "FY2024", "FY2023", "FY2022", "Growth YoY"]]
    rows = [
        ("Revenue from Operations", d["revenue"]),
        ("EBITDA", d["ebitda"]),
        ("EBITDA Margin (%)", [d["ebitda"][i]/d["revenue"][i]*100 for i in range(3)]),
        ("Profit After Tax", d["pat"]),
        ("Total Assets", d["total_assets"]),
        ("Net Worth", d["total_equity"]),
        ("Total Debt", d["total_debt"]),
    ]
    for label, vals in rows:
        growth = _pct(vals[0], vals[1])
        fin_data.append([label, _fmt(vals[0]), _fmt(vals[1]), _fmt(vals[2]), growth])
    t = Table(fin_data, colWidths=[50*mm, 30*mm, 30*mm, 30*mm, 25*mm])
    t.setStyle(_table_style())
    s.append(t)
    s.append(Spacer(1, 8*mm))

    # Key Ratios
    rev = d["revenue"]
    ebitda = d["ebitda"]
    pat = d["pat"]
    equity = d["total_equity"]
    debt = d["total_debt"]
    assets = d["total_assets"]
    ca = d["current_assets"]
    cl = d["current_liabilities"]
    fc = d["finance_cost"]
    ebit = d["ebit"]

    def _safe_div(a, b, mult=1):
        return f"{a/b*mult:.2f}" if b else "N/A"

    s.append(Paragraph("KEY FINANCIAL RATIOS", ss['SectionHead']))
    rat_data = [["Ratio", "FY2024", "FY2023", "FY2022"]]
    rat_data.append(["Current Ratio (x)", _safe_div(ca[0], cl[0]), _safe_div(ca[1], cl[1]), _safe_div(ca[2], cl[2])])
    rat_data.append(["Debt/Equity (x)", _safe_div(debt[0], equity[0]), _safe_div(debt[1], equity[1]), _safe_div(debt[2], equity[2])])
    rat_data.append(["Interest Coverage (x)", _safe_div(ebit[0], fc[0]), _safe_div(ebit[1], fc[1]), _safe_div(ebit[2], fc[2])])
    rat_data.append(["ROE (%)", _safe_div(pat[0], equity[0], 100), _safe_div(pat[1], equity[1], 100), _safe_div(pat[2], equity[2], 100)])
    rat_data.append(["Net Profit Margin (%)", _safe_div(pat[0], rev[0], 100), _safe_div(pat[1], rev[1], 100), _safe_div(pat[2], rev[2], 100)])
    t = Table(rat_data, colWidths=[50*mm, 30*mm, 30*mm, 30*mm])
    t.setStyle(_table_style())
    s.append(t)
    s.append(PageBreak())

    # Detailed Balance Sheet
    s.append(Paragraph("BALANCE SHEET AS AT MARCH 31 (₹ Crore)", ss['SectionHead']))
    bs_data = [["Particulars", "FY2024", "FY2023", "FY2022"]]
    bs_data.append(["EQUITY AND LIABILITIES", "", "", ""])
    bs_data.append(["Shareholders' Equity", _fmt(equity[0]), _fmt(equity[1]), _fmt(equity[2])])
    bs_data.append(["Long-term Borrowings", _fmt(d["long_term_debt"][0]), _fmt(d["long_term_debt"][1]), _fmt(d["long_term_debt"][2])])
    bs_data.append(["Short-term Borrowings", _fmt(d["short_term_debt"][0]), _fmt(d["short_term_debt"][1]), _fmt(d["short_term_debt"][2])])
    bs_data.append(["Current Liabilities & Provisions", _fmt(cl[0]), _fmt(cl[1]), _fmt(cl[2])])
    bs_total = [equity[i]+d["long_term_debt"][i]+cl[i] for i in range(3)]
    bs_data.append(["TOTAL", _fmt(bs_total[0]), _fmt(bs_total[1]), _fmt(bs_total[2])])
    bs_data.append(["", "", "", ""])
    bs_data.append(["ASSETS", "", "", ""])
    bs_data.append(["Fixed Assets (Net)", _fmt(d["fixed_assets"][0]), _fmt(d["fixed_assets"][1]), _fmt(d["fixed_assets"][2])])
    bs_data.append(["Investments", _fmt(d["investments"][0]), _fmt(d["investments"][1]), _fmt(d["investments"][2])])
    bs_data.append(["Current Assets", _fmt(ca[0]), _fmt(ca[1]), _fmt(ca[2])])
    bs_data.append(["  - Inventory", _fmt(d["inventory"][0]), _fmt(d["inventory"][1]), _fmt(d["inventory"][2])])
    bs_data.append(["  - Trade Receivables", _fmt(d["trade_receivables"][0]), _fmt(d["trade_receivables"][1]), _fmt(d["trade_receivables"][2])])
    bs_data.append(["  - Cash & Equivalents", _fmt(d["cash_equivalents"][0]), _fmt(d["cash_equivalents"][1]), _fmt(d["cash_equivalents"][2])])
    bs_data.append(["TOTAL ASSETS", _fmt(assets[0]), _fmt(assets[1]), _fmt(assets[2])])
    t = Table(bs_data, colWidths=[55*mm, 30*mm, 30*mm, 30*mm])
    t.setStyle(_table_style())
    s.append(t)
    s.append(Spacer(1, 8*mm))

    # P&L
    s.append(Paragraph("STATEMENT OF PROFIT AND LOSS (₹ Crore)", ss['SectionHead']))
    pl_data = [["Particulars", "FY2024", "FY2023", "FY2022"]]
    pl_data.append(["Revenue from Operations", _fmt(rev[0]), _fmt(rev[1]), _fmt(rev[2])])
    pl_data.append(["Other Income", _fmt(d["other_income"][0]), _fmt(d["other_income"][1]), _fmt(d["other_income"][2])])
    pl_data.append(["Total Income", _fmt(rev[0]+d["other_income"][0]), _fmt(rev[1]+d["other_income"][1]), _fmt(rev[2]+d["other_income"][2])])
    if d["raw_material"][0] > 0:
        pl_data.append(["Raw Material Cost", _fmt(d["raw_material"][0]), _fmt(d["raw_material"][1]), _fmt(d["raw_material"][2])])
    pl_data.append(["Employee Benefit Expense", _fmt(d["employee_cost"][0]), _fmt(d["employee_cost"][1]), _fmt(d["employee_cost"][2])])
    pl_data.append(["Other Expenses", _fmt(d["other_expenses"][0]), _fmt(d["other_expenses"][1]), _fmt(d["other_expenses"][2])])
    pl_data.append(["EBITDA", _fmt(ebitda[0]), _fmt(ebitda[1]), _fmt(ebitda[2])])
    pl_data.append(["Depreciation & Amortisation", _fmt(d["depreciation"][0]), _fmt(d["depreciation"][1]), _fmt(d["depreciation"][2])])
    pl_data.append(["Finance Costs", _fmt(fc[0]), _fmt(fc[1]), _fmt(fc[2])])
    pl_data.append(["Profit Before Tax", _fmt(d["pbt"][0]), _fmt(d["pbt"][1]), _fmt(d["pbt"][2])])
    pl_data.append(["Tax Expense", _fmt(d["tax"][0]), _fmt(d["tax"][1]), _fmt(d["tax"][2])])
    pl_data.append(["Profit After Tax", _fmt(pat[0]), _fmt(pat[1]), _fmt(pat[2])])
    t = Table(pl_data, colWidths=[55*mm, 30*mm, 30*mm, 30*mm])
    t.setStyle(_table_style())
    s.append(t)
    s.append(PageBreak())

    # Cash Flow
    s.append(Paragraph("CASH FLOW STATEMENT (₹ Crore)", ss['SectionHead']))
    cf_data = [["Particulars", "FY2024", "FY2023", "FY2022"]]
    cf_data.append(["Cash from Operations", _fmt(d["ocf"][0]), _fmt(d["ocf"][1]), _fmt(d["ocf"][2])])
    cf_data.append(["Capital Expenditure", _fmt(d["capex"][0]), _fmt(d["capex"][1]), _fmt(d["capex"][2])])
    cf_data.append(["Free Cash Flow to Firm", _fmt(d["fcff"][0]), _fmt(d["fcff"][1]), _fmt(d["fcff"][2])])
    t = Table(cf_data, colWidths=[55*mm, 30*mm, 30*mm, 30*mm])
    t.setStyle(_table_style())
    s.append(t)

    # Auditor notes
    s.append(Spacer(1, 10*mm))
    s.append(Paragraph("INDEPENDENT AUDITOR'S REPORT", ss['SectionHead']))
    s.append(Paragraph(
        f"We have audited the accompanying standalone financial statements of {d['name']} "
        f"('the Company'), which comprise the Balance Sheet as at March 31, 2024, "
        f"the Statement of Profit and Loss, the Cash Flow Statement for the year then ended, "
        f"and notes to the financial statements.<br/><br/>"
        f"<b>Opinion</b><br/>"
        f"In our opinion, the aforesaid standalone financial statements give a true and fair view "
        f"of the state of affairs of the Company as at March 31, 2024, and its profit and cash flows "
        f"for the year then ended in accordance with the Indian Accounting Standards (Ind AS) "
        f"and other accounting principles generally accepted in India.<br/><br/>"
        f"For {d['auditor']}<br/>"
        f"Place: {d['registered'].split(',')[-2].strip()}<br/>"
        f"Date: May 15, 2024"
        , ss['BodyNarrative']))

    s.append(Spacer(1, 10*mm))
    s.append(Paragraph("— End of Annual Report —", ss['SmallNote']))
    return s


# ────────────────────────────────────────────────────────────────────
#  2. Audited Financial Statement PDF (standalone 3-year)
# ────────────────────────────────────────────────────────────────────

def gen_audited_financials(eid):
    d = COMPANY_DATA[eid]
    return _pdf_buf(_build_audited_financials, d=d)


def _build_audited_financials(ss, d):
    s = []
    s.append(Paragraph(d["name"], ss['TitleCover']))
    s.append(Paragraph("Audited Financial Statements — FY2022 to FY2024", ss['SubTitle']))
    s.append(Paragraph(f"CIN: {d['cin']}  |  PAN: {d['pan']}", ss['BodyNarrative']))
    s.append(HRFlowable(width="100%", thickness=1, color=colors.gray))
    s.append(Spacer(1, 5*mm))

    # Same P&L + BS as annual report but in standalone format
    rev, ebitda, pat = d["revenue"], d["ebitda"], d["pat"]
    s.append(Paragraph("PROFIT & LOSS ACCOUNT (₹ Crore)", ss['SectionHead']))
    pl_data = [["Particulars", "FY2024", "FY2023", "FY2022"]]
    items = [
        ("Revenue from Operations", d["revenue"]),
        ("Other Income", d["other_income"]),
        ("Total Income", [d["revenue"][i]+d["other_income"][i] for i in range(3)]),
    ]
    if d["raw_material"][0] > 0:
        items.append(("Cost of Materials Consumed", d["raw_material"]))
    items += [
        ("Employee Benefit Expense", d["employee_cost"]),
        ("Other Expenses", d["other_expenses"]),
        ("EBITDA", d["ebitda"]),
        ("Depreciation", d["depreciation"]),
        ("EBIT", d["ebit"]),
        ("Finance Costs", d["finance_cost"]),
        ("Profit Before Tax", d["pbt"]),
        ("Tax Expense", d["tax"]),
        ("Profit After Tax", d["pat"]),
    ]
    for label, vals in items:
        pl_data.append([label, _fmt(vals[0]), _fmt(vals[1]), _fmt(vals[2])])
    t = Table(pl_data, colWidths=[55*mm, 30*mm, 30*mm, 30*mm])
    t.setStyle(_table_style())
    s.append(t)
    s.append(PageBreak())

    s.append(Paragraph("BALANCE SHEET (₹ Crore)", ss['SectionHead']))
    bs = [["Particulars", "FY2024", "FY2023", "FY2022"]]
    for label, key in [
        ("Fixed Assets (Net Block)", "fixed_assets"),
        ("Investments", "investments"),
        ("Trade Receivables", "trade_receivables"),
        ("Inventory", "inventory"),
        ("Cash & Bank Balances", "cash_equivalents"),
        ("Other Current Assets", None),
        ("Total Current Assets", "current_assets"),
        ("TOTAL ASSETS", "total_assets"),
        ("", None),
        ("Shareholders' Equity", "total_equity"),
        ("Long-term Debt", "long_term_debt"),
        ("Short-term Borrowings", "short_term_debt"),
        ("Trade Payables", "trade_payables"),
        ("Other Current Liabilities", None),
        ("Total Current Liabilities", "current_liabilities"),
    ]:
        if key:
            vals = d[key]
            bs.append([label, _fmt(vals[0]), _fmt(vals[1]), _fmt(vals[2])])
        elif label:
            oca = [d["current_assets"][i] - d["trade_receivables"][i] - d["inventory"][i] - d["cash_equivalents"][i] for i in range(3)]
            ocl = [d["current_liabilities"][i] - d["trade_payables"][i] - d["short_term_debt"][i] for i in range(3)]
            if "Other Current Assets" in label:
                bs.append([label, _fmt(oca[0]), _fmt(oca[1]), _fmt(oca[2])])
            else:
                bs.append([label, _fmt(ocl[0]), _fmt(ocl[1]), _fmt(ocl[2])])
        else:
            bs.append(["", "", "", ""])
    t = Table(bs, colWidths=[55*mm, 30*mm, 30*mm, 30*mm])
    t.setStyle(_table_style())
    s.append(t)
    s.append(Spacer(1, 10*mm))
    s.append(Paragraph(f"As per our report of even date — {d['auditor']}", ss['SmallNote']))
    return s


# ────────────────────────────────────────────────────────────────────
#  3. Exchange Filing — Quarterly Results (Listed only)
# ────────────────────────────────────────────────────────────────────

def gen_exchange_filing(eid):
    d = COMPANY_DATA[eid]
    if not d["listed"]:
        return None
    return _pdf_buf(_build_exchange_filing, d=d)


def _build_exchange_filing(ss, d):
    s = []
    s.append(Paragraph("BOMBAY STOCK EXCHANGE / NSE INDIA", ss['SubTitle']))
    s.append(Paragraph("Statement of Financial Results for Quarter and Nine Months Ended December 31, 2024", ss['SubTitle']))
    s.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#1a3a6a')))
    s.append(Spacer(1, 3*mm))
    s.append(Paragraph(f"<b>{d['name']}</b><br/>CIN: {d['cin']}", ss['BodyNarrative']))
    s.append(Spacer(1, 5*mm))

    q3_rev = d["exchange_revenue_q3"]
    q3_ebitda = q3_rev * (d["ebitda"][0] / d["revenue"][0]) * 0.95  # slightly different margin
    q3_pat = q3_rev * (d["pat"][0] / d["revenue"][0]) * 0.93

    s.append(Paragraph("FINANCIAL RESULTS (₹ Crore) — Standalone, Unaudited", ss['SectionHead']))
    data = [["Particulars", "Q3 FY2025\n(Oct-Dec)", "9M FY2025\n(Apr-Dec)", "FY2024\n(Audited)"]]
    q3_only_rev = q3_rev * 0.36  # roughly Q3 portion
    data.append(["Revenue from Operations", _fmt(q3_only_rev), _fmt(q3_rev), _fmt(d["revenue"][0])])
    data.append(["Total Income", _fmt(q3_only_rev*1.005), _fmt(q3_rev*1.005), _fmt(d["revenue"][0]+d["other_income"][0])])
    data.append(["Total Expenses", _fmt(q3_only_rev*0.76), _fmt(q3_rev*0.76), _fmt(d["revenue"][0]-d["ebitda"][0]+d["other_income"][0])])
    data.append(["EBITDA", _fmt(q3_only_rev*0.24), _fmt(q3_ebitda), _fmt(d["ebitda"][0])])
    data.append(["Profit Before Tax", _fmt(q3_only_rev*0.15), _fmt(q3_rev*0.155), _fmt(d["pbt"][0])])
    data.append(["Profit After Tax", _fmt(q3_only_rev*0.11), _fmt(q3_pat), _fmt(d["pat"][0])])
    t = Table(data, colWidths=[50*mm, 35*mm, 35*mm, 35*mm])
    t.setStyle(_table_style())
    s.append(t)
    s.append(Spacer(1, 8*mm))

    s.append(Paragraph(
        "Notes:<br/>"
        "1. The above results have been reviewed by the Audit Committee and approved by the Board of Directors.<br/>"
        "2. These results have been prepared in accordance with Ind AS 34.<br/>"
        "3. The statutory auditors have carried out a limited review of the above unaudited financial results.<br/>"
        f"4. Date: January 28, 2025<br/>"
        f"5. Place: {d['registered'].split(',')[-2].strip()}"
        , ss['BodyNarrative']))
    return s


# ────────────────────────────────────────────────────────────────────
#  4. Corporate Governance Report (Listed only)
# ────────────────────────────────────────────────────────────────────

def gen_governance_report(eid):
    d = COMPANY_DATA[eid]
    if not d["listed"]:
        return None
    return _pdf_buf(_build_governance_report, d=d)


def _build_governance_report(ss, d):
    s = []
    s.append(Paragraph(d["name"], ss['TitleCover']))
    s.append(Paragraph("Report on Corporate Governance — FY2024", ss['SubTitle']))
    s.append(HRFlowable(width="100%", thickness=1, color=colors.gray))
    s.append(Spacer(1, 5*mm))

    s.append(Paragraph("1. BOARD COMPOSITION", ss['SectionHead']))
    tdata = [["Name", "DIN", "Category", "Meetings\nAttended", "Shareholding"]]
    meetings = [6, 5, 6, 4, 5, 6]  # enough for any director count
    for i, (name, din, desig, hold) in enumerate(d["directors"]):
        cat = "Executive / Promoter" if "MD" in desig or "Whole" in desig or "CMD" in desig else "Non-Executive Independent"
        tdata.append([name, din, cat, f"{meetings[i % len(meetings)]}/6", hold])
    t = Table(tdata, colWidths=[45*mm, 25*mm, 40*mm, 20*mm, 25*mm])
    t.setStyle(_table_style())
    s.append(t)
    s.append(Spacer(1, 5*mm))

    s.append(Paragraph("2. AUDIT COMMITTEE", ss['SectionHead']))
    # Use last 2 directors safely
    ac_chair = d['directors'][min(2, len(d['directors'])-1)][0]
    ac_mem1 = d['directors'][min(3, len(d['directors'])-1)][0] if len(d['directors']) > 1 else ac_chair
    ac_mem2 = d['directors'][min(1, len(d['directors'])-1)][0]
    s.append(Paragraph(
        f"The Audit Committee comprises {ac_chair} (Chairperson), "
        f"{ac_mem1}, and {ac_mem2}. "
        f"The committee met 4 times during FY2024.", ss['BodyNarrative']))

    s.append(Paragraph("3. RELATED PARTY TRANSACTIONS", ss['SectionHead']))
    s.append(Paragraph(
        "All related party transactions during the year were at arm's length basis and in the "
        "ordinary course of business. There were no materially significant related party transactions "
        "that may have potential conflict with the interests of the Company.", ss['BodyNarrative']))

    s.append(Paragraph("4. COMPLIANCE STATUS", ss['SectionHead']))
    comp_data = [["Regulation", "Status", "Details"]]
    comp_data.append(["SEBI LODR Reg 17 — Board Composition", "Compliant", "50% independent directors"])
    comp_data.append(["SEBI LODR Reg 18 — Audit Committee", "Compliant", "All members financially literate"])
    comp_data.append(["SEBI LODR Reg 27 — Corp Governance", "Compliant", "Quarterly reports filed"])
    comp_data.append(["Companies Act Sec 177 — Vigil Mechanism", "Compliant", "Whistleblower policy active"])
    t = Table(comp_data, colWidths=[55*mm, 25*mm, 65*mm])
    t.setStyle(_table_style())
    s.append(t)
    return s


# ────────────────────────────────────────────────────────────────────
#  5. Credit Rating Report PDF
# ────────────────────────────────────────────────────────────────────

def gen_rating_report(eid):
    d = COMPANY_DATA[eid]
    return _pdf_buf(_build_rating_report, d=d)


def _build_rating_report(ss, d):
    s = []
    agency = d["rating"].split()[0]
    rating = d["rating"].replace(agency + " ", "")

    s.append(Paragraph(f"{agency}", ss['TitleCover']))
    s.append(Paragraph("RATING RATIONALE", ss['SubTitle']))
    s.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#1a3a6a')))
    s.append(Spacer(1, 5*mm))

    s.append(Paragraph(f"<b>Entity:</b> {d['name']}", ss['BodyNarrative']))
    s.append(Paragraph(f"<b>Rating:</b> {rating}", ss['BodyNarrative']))
    s.append(Paragraph(f"<b>Date:</b> November 15, 2024", ss['BodyNarrative']))
    s.append(Spacer(1, 5*mm))

    rate_data = [["Instrument", "Size (₹ Cr)", "Rating"]]
    rate_data.append(["Long-term Bank Facilities", _fmt(d["long_term_debt"][0]), rating])
    rate_data.append(["Short-term Bank Facilities", _fmt(d["short_term_debt"][0]), rating.replace("+", "1+").replace("-", "1") if "A" in rating else "A3"])
    t = Table(rate_data, colWidths=[55*mm, 30*mm, 50*mm])
    t.setStyle(_table_style())
    s.append(t)
    s.append(Spacer(1, 8*mm))

    is_strong = "A" in rating and "BBB" not in rating
    s.append(Paragraph("RATING DRIVERS", ss['SectionHead']))
    if is_strong:
        s.append(Paragraph(
            "<b>Key Strengths:</b><br/>"
            "• Established market position with strong revenue growth trajectory<br/>"
            "• Healthy EBITDA margins demonstrating operational efficiency<br/>"
            "• Adequate debt coverage metrics with comfortable interest coverage<br/>"
            "• Experienced management team with long track record<br/><br/>"
            "<b>Key Weaknesses / Rating Sensitivities:</b><br/>"
            "• Working capital intensive operations requiring continued bank support<br/>"
            "• Concentration risk in domestic market<br/>"
            "• Rating upgrade linked to sustained revenue above current levels with margin stability<br/>"
            "• Rating downgrade may occur if D/E exceeds 1.5x or ICR falls below 3.0x",
            ss['BodyNarrative']))
    else:
        s.append(Paragraph(
            "<b>Key Strengths:</b><br/>"
            "• Presence in essential infrastructure segment with government spending support<br/>"
            "• Established execution capability in project delivery<br/><br/>"
            "<b>Key Weaknesses / Rating Sensitivities:</b><br/>"
            "• High leverage with debt/equity above sector comfort levels<br/>"
            "• Thin profitability with PAT margins under pressure<br/>"
            "• Negative free cash flow requiring continued external funding<br/>"
            "• Working capital elongation leading to liquidity stress<br/>"
            "• Watch Negative reflects risk of further deterioration if cash flows don't improve<br/>"
            "• Rating downgrade if D/E exceeds 4.0x or ICR falls below 1.0x",
            ss['BodyNarrative']))

    s.append(Spacer(1, 8*mm))
    s.append(Paragraph("FINANCIAL SUMMARY", ss['SectionHead']))
    fin = [["Parameter", "FY2024", "FY2023"]]
    fin.append(["Revenue (₹ Cr)", _fmt(d["revenue"][0]), _fmt(d["revenue"][1])])
    def _sd(a, b, m=1): return f"{a/b*m:.1f}" if b else "N/A"
    def _sd2(a, b, m=1): return f"{a/b*m:.2f}" if b else "N/A"
    fin.append(["EBITDA Margin (%)", _sd(d['ebitda'][0], d['revenue'][0], 100), _sd(d['ebitda'][1], d['revenue'][1], 100)])
    fin.append(["PAT Margin (%)", _sd(d['pat'][0], d['revenue'][0], 100), _sd(d['pat'][1], d['revenue'][1], 100)])
    fin.append(["Debt/Equity (x)", _sd2(d['total_debt'][0], d['total_equity'][0]), _sd2(d['total_debt'][1], d['total_equity'][1])])
    fin.append(["Interest Coverage (x)", _sd2(d['ebit'][0], d['finance_cost'][0]), _sd2(d['ebit'][1], d['finance_cost'][1])])
    t = Table(fin, colWidths=[45*mm, 35*mm, 35*mm])
    t.setStyle(_table_style())
    s.append(t)
    s.append(Spacer(1, 10*mm))
    s.append(Paragraph(f"Analyst: Rating Team, {agency}<br/>Disclaimer: This rating is not a recommendation to buy, sell or hold.", ss['SmallNote']))
    return s


# ────────────────────────────────────────────────────────────────────
#  6. Certificate of Incorporation (Private companies)
# ────────────────────────────────────────────────────────────────────

def gen_certificate_of_incorporation(eid):
    d = COMPANY_DATA[eid]
    return _pdf_buf(_build_coi, d=d)


def _build_coi(ss, d):
    s = []
    s.append(Spacer(1, 20*mm))
    s.append(Paragraph("MINISTRY OF CORPORATE AFFAIRS", ss['TitleCover']))
    s.append(Paragraph("GOVERNMENT OF INDIA", ss['SubTitle']))
    s.append(HRFlowable(width="100%", thickness=3, color=colors.HexColor('#1a3a6a')))
    s.append(Spacer(1, 15*mm))
    s.append(Paragraph("CERTIFICATE OF INCORPORATION", ss['TitleCover']))
    s.append(Spacer(1, 10*mm))
    company_type = "Public Limited Company" if d["listed"] else "Private Limited Company"
    s.append(Paragraph(f"I hereby certify that <b>{d['name']}</b> is this day incorporated "
                        f"under the Companies Act, 2013 as a {company_type} and that the "
                        f"company is limited by shares.", ss['BodyNarrative']))
    s.append(Spacer(1, 8*mm))
    s.append(Paragraph(f"<b>Corporate Identity Number (CIN):</b> {d['cin']}", ss['BodyNarrative']))
    s.append(Paragraph(f"<b>PAN:</b> {d['pan']}", ss['BodyNarrative']))
    s.append(Paragraph(f"<b>Date of Incorporation:</b> {d['incorporated']}", ss['BodyNarrative']))
    s.append(Paragraph(f"<b>Registered Office:</b> {d['registered']}", ss['BodyNarrative']))
    s.append(Paragraph(f"<b>Authorized Capital:</b> ₹{_fmt(d['auth_cap'])} Crore", ss['BodyNarrative']))
    s.append(Paragraph(f"<b>Paid-up Capital:</b> ₹{_fmt(d['paid_up'])} Crore", ss['BodyNarrative']))
    s.append(Spacer(1, 15*mm))
    s.append(Paragraph("Given under my hand at the office of the Registrar of Companies, "
                        f"{d['registered'].split(',')[-2].strip()}", ss['BodyNarrative']))
    s.append(Spacer(1, 10*mm))
    s.append(Paragraph("_________________________<br/>Registrar of Companies", ss['BodyNarrative']))
    return s


# ────────────────────────────────────────────────────────────────────
#  7. Board Resolution PDF
# ────────────────────────────────────────────────────────────────────

def gen_board_resolution(eid):
    d = COMPANY_DATA[eid]
    return _pdf_buf(_build_board_resolution, d=d, eid=eid)


def _build_board_resolution(ss, d, eid):
    s = []
    s.append(Paragraph(d["name"], ss['TitleCover']))
    s.append(Paragraph("CERTIFIED TRUE COPY OF BOARD RESOLUTION", ss['SubTitle']))
    s.append(HRFlowable(width="100%", thickness=1, color=colors.gray))
    s.append(Spacer(1, 8*mm))
    amounts = {"BMFG001": 150, "PINF001": 500, "SPHR001": 75, "OLOG001": 100}
    amt = amounts.get(eid, 100)
    s.append(Paragraph(
        f"At the meeting of the Board of Directors of {d['name']} held on "
        f"February 15, 2025 at the Registered Office of the Company, the following "
        f"resolution was passed with unanimous consent of all directors present:<br/><br/>"
        f"<b>RESOLVED THAT</b> the Company hereby authorizes {d['directors'][0][0]}, "
        f"{d['directors'][0][2]}, to apply for and avail banking facilities aggregating "
        f"to ₹{amt} Crore from scheduled commercial banks on such terms and conditions "
        f"as may be mutually agreed upon.<br/><br/>"
        f"<b>RESOLVED FURTHER THAT</b> {d['directors'][0][0]} be and is hereby authorized "
        f"to sign, execute and deliver all documents, applications, agreements, undertakings "
        f"and other papers as may be required for availing the said facilities.<br/><br/>"
        f"<b>RESOLVED FURTHER THAT</b> the Company authorizes creation of charge/hypothecation "
        f"on the assets of the Company as security for the facilities sanctioned."
        , ss['BodyNarrative']))
    s.append(Spacer(1, 15*mm))
    s.append(Paragraph(f"For {d['name']}", ss['BodyNarrative']))
    s.append(Spacer(1, 8*mm))
    s.append(Paragraph(f"_________________________<br/>{d['directors'][0][0]}<br/>{d['directors'][0][2]}<br/>DIN: {d['directors'][0][1]}", ss['BodyNarrative']))
    return s


# ────────────────────────────────────────────────────────────────────
#  8. Bank Statement PDF (ETB & Private)
# ────────────────────────────────────────────────────────────────────

def gen_bank_statement(eid):
    d = COMPANY_DATA[eid]
    return _pdf_buf(_build_bank_statement, d=d, eid=eid)


def _build_bank_statement(ss, d, eid):
    s = []
    s.append(Paragraph("STATE BANK OF INDIA", ss['TitleCover']))
    s.append(Paragraph("ACCOUNT STATEMENT", ss['SubTitle']))
    s.append(HRFlowable(width="100%", thickness=1, color=colors.gray))
    s.append(Spacer(1, 3*mm))
    s.append(Paragraph(f"Account Holder: {d['name']}", ss['BodyNarrative']))
    s.append(Paragraph(f"Account No: 3841{eid[-4:]}00125  |  Type: Current Account", ss['BodyNarrative']))
    s.append(Paragraph(f"Branch: {d['registered'].split(',')[-2].strip()} Main Branch", ss['BodyNarrative']))
    s.append(Paragraph("Period: April 2024 to March 2025", ss['BodyNarrative']))
    s.append(Spacer(1, 5*mm))

    # Generate monthly transactions
    months = ["Apr-24","May-24","Jun-24","Jul-24","Aug-24","Sep-24",
              "Oct-24","Nov-24","Dec-24","Jan-25","Feb-25","Mar-25"]
    monthly_rev = d["revenue"][0] / 12
    data = [["Date", "Description", "Debit (₹ Cr)", "Credit (₹ Cr)", "Balance (₹ Cr)"]]
    balance = d["cash_equivalents"][0] * 0.3  # opening balance
    for i, m in enumerate(months):
        # Credit: collections
        cr = monthly_rev * (0.85 + (i % 3) * 0.05)
        balance += cr
        data.append([f"15-{m}", "Customer Collections", "", _fmt(cr), _fmt(balance)])
        # Debit: supplier payments
        dr = monthly_rev * (0.65 + (i % 2) * 0.1)
        balance -= dr
        data.append([f"25-{m}", "Supplier Payments", _fmt(dr), "", _fmt(balance)])
        # Debit: salary
        sal = d["employee_cost"][0] / 12
        balance -= sal
        data.append([f"28-{m}", "Salary & Wages", _fmt(sal), "", _fmt(balance)])
    data.append(["31-Mar-25", "Closing Balance", "", "", _fmt(balance)])
    t = Table(data, colWidths=[22*mm, 50*mm, 25*mm, 25*mm, 25*mm])
    t.setStyle(_table_style())
    s.append(t)
    s.append(Spacer(1, 5*mm))
    s.append(Paragraph("This is a computer-generated statement and does not require signature.", ss['SmallNote']))
    return s


# ═══════════════════════════════════════════════════════════════════════════════
#  Excel Generators
# ═══════════════════════════════════════════════════════════════════════════════

def _excel_header_fill():
    return PatternFill(start_color="1A3A6A", end_color="1A3A6A", fill_type="solid")

def _excel_header_font():
    return Font(bold=True, color="FFFFFF", size=10)

def _excel_data_font():
    return Font(size=10)

def _excel_border():
    thin = Side(style='thin', color='CCCCCC')
    return Border(top=thin, bottom=thin, left=thin, right=thin)


def gen_provisional_financials_excel(eid):
    """Provisional / projected financials in Excel format."""
    d = COMPANY_DATA[eid]
    wb = Workbook()

    # P&L Sheet
    ws = wb.active
    ws.title = "Provisional P&L"
    headers = ["Particulars", "FY2024 (Audited)", "FY2025 (Provisional)", "Growth %"]
    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=c, value=h)
        cell.font = _excel_header_font()
        cell.fill = _excel_header_fill()
        cell.border = _excel_border()
        cell.alignment = Alignment(horizontal='center')

    prov_rev = d["prov_revenue"]
    prov_ebitda = d["prov_ebitda"]
    prov_pat = d["prov_pat"]
    rows_data = [
        ("Revenue from Operations", d["revenue"][0], prov_rev),
        ("EBITDA", d["ebitda"][0], prov_ebitda),
        ("EBITDA Margin (%)", d["ebitda"][0]/d["revenue"][0]*100, prov_ebitda/prov_rev*100),
        ("Depreciation", d["depreciation"][0], d["depreciation"][0]*1.08),
        ("Finance Cost", d["finance_cost"][0], d["finance_cost"][0]*1.05),
        ("Profit Before Tax", d["pbt"][0], prov_ebitda - d["depreciation"][0]*1.08 - d["finance_cost"][0]*1.05),
        ("Tax Expense", d["tax"][0], (prov_ebitda - d["depreciation"][0]*1.08 - d["finance_cost"][0]*1.05)*0.25),
        ("Profit After Tax", d["pat"][0], prov_pat),
    ]
    for r, (label, fy24, fy25) in enumerate(rows_data, 2):
        ws.cell(row=r, column=1, value=label).font = _excel_data_font()
        ws.cell(row=r, column=2, value=round(fy24, 2)).number_format = '#,##0.00'
        ws.cell(row=r, column=3, value=round(fy25, 2)).number_format = '#,##0.00'
        growth = ((fy25 - fy24) / abs(fy24) * 100) if fy24 != 0 else 0
        ws.cell(row=r, column=4, value=round(growth, 1)).number_format = '0.0"%"'
        for c in range(1, 5):
            ws.cell(row=r, column=c).border = _excel_border()

    ws.column_dimensions['A'].width = 30
    ws.column_dimensions['B'].width = 20
    ws.column_dimensions['C'].width = 22
    ws.column_dimensions['D'].width = 12

    # BS Sheet
    ws2 = wb.create_sheet("Provisional BS")
    headers2 = ["Particulars", "FY2024 (Audited)", "FY2025 (Projected)"]
    for c, h in enumerate(headers2, 1):
        cell = ws2.cell(row=1, column=c, value=h)
        cell.font = _excel_header_font()
        cell.fill = _excel_header_fill()
        cell.border = _excel_border()

    growth_factor = prov_rev / d["revenue"][0]
    bs_proj = [
        ("Total Assets", d["total_assets"][0], d["total_assets"][0] * growth_factor * 0.98),
        ("Fixed Assets", d["fixed_assets"][0], d["fixed_assets"][0] * 1.10),
        ("Current Assets", d["current_assets"][0], d["current_assets"][0] * growth_factor),
        ("Shareholders' Equity", d["total_equity"][0], d["total_equity"][0] + prov_pat),
        ("Long-term Debt", d["long_term_debt"][0], d["long_term_debt"][0] * 1.05),
        ("Short-term Debt", d["short_term_debt"][0], d["short_term_debt"][0] * 1.08),
        ("Current Liabilities", d["current_liabilities"][0], d["current_liabilities"][0] * growth_factor * 0.95),
    ]
    for r, (label, fy24, fy25) in enumerate(bs_proj, 2):
        ws2.cell(row=r, column=1, value=label).font = _excel_data_font()
        ws2.cell(row=r, column=2, value=round(fy24, 2)).number_format = '#,##0.00'
        ws2.cell(row=r, column=3, value=round(fy25, 2)).number_format = '#,##0.00'
        for c in range(1, 4):
            ws2.cell(row=r, column=c).border = _excel_border()
    ws2.column_dimensions['A'].width = 25
    ws2.column_dimensions['B'].width = 20
    ws2.column_dimensions['C'].width = 22

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def gen_debt_schedule_excel(eid):
    """Debt schedule — facility-wise breakdown."""
    d = COMPANY_DATA[eid]
    wb = Workbook()
    ws = wb.active
    ws.title = "Debt Schedule"

    headers = ["Lender", "Facility", "Sanctioned (₹ Cr)", "Outstanding (₹ Cr)",
               "Rate (%)", "Tenure", "Security", "Repayment"]
    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=c, value=h)
        cell.font = _excel_header_font()
        cell.fill = _excel_header_fill()
        cell.border = _excel_border()

    ltd = d["long_term_debt"][0]
    std = d["short_term_debt"][0]
    facilities = [
        ("State Bank of India", "Term Loan", ltd*0.4, ltd*0.35, 9.50, "7 years", "First charge on fixed assets", "Monthly EMI"),
        ("HDFC Bank", "Working Capital", std*0.45, std*0.40, 9.25, "1 year (renewable)", "Hypothecation of stock/debtors", "On demand"),
        ("ICICI Bank", "Term Loan", ltd*0.3, ltd*0.28, 9.75, "5 years", "Second charge on fixed assets", "Quarterly"),
        ("Bank of Baroda", "CC/OD", std*0.55, std*0.50, 10.00, "1 year (renewable)", "Hypothecation of stock", "On demand"),
        ("Axis Bank", "WCDL", ltd*0.15, ltd*0.12, 9.00, "1 year", "Corporate guarantee", "Bullet"),
    ]
    for r, (lender, fac, sanc, out, rate, ten, sec, rep) in enumerate(facilities, 2):
        vals = [lender, fac, round(sanc, 2), round(out, 2), rate, ten, sec, rep]
        for c, v in enumerate(vals, 1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.font = _excel_data_font()
            cell.border = _excel_border()
            if isinstance(v, float):
                cell.number_format = '#,##0.00'

    # Totals
    r_total = len(facilities) + 2
    ws.cell(row=r_total, column=1, value="TOTAL").font = Font(bold=True, size=10)
    ws.cell(row=r_total, column=3, value=round(sum(f[2] for f in facilities), 2)).font = Font(bold=True, size=10)
    ws.cell(row=r_total, column=3).number_format = '#,##0.00'
    ws.cell(row=r_total, column=4, value=round(sum(f[3] for f in facilities), 2)).font = Font(bold=True, size=10)
    ws.cell(row=r_total, column=4).number_format = '#,##0.00'

    for c in range(1, 9):
        ws.column_dimensions[chr(64+c)].width = 18 if c <= 2 else 15
    ws.column_dimensions['G'].width = 30
    ws.column_dimensions['H'].width = 15

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ═══════════════════════════════════════════════════════════════════════════════
#  CSV Generators (ETB Internal Data)
# ═══════════════════════════════════════════════════════════════════════════════

def gen_account_conduct_csv(conduct_data=None):
    cd = conduct_data or ETB_CONDUCT
    buf = BytesIO()
    writer = csv.DictWriter(
        _TextIOWrapper(buf),
        fieldnames=["month", "avg_balance_cr", "credit_turnover_cr", "debit_turnover_cr",
                     "cheque_returns", "limit_cr", "utilized_cr", "utilization_pct"])
    writer.writeheader()
    for row in cd["account_conduct"]:
        writer.writerow({
            "month": row["month"],
            "avg_balance_cr": row["avg_balance_cr"],
            "credit_turnover_cr": row["credit_turnover_cr"],
            "debit_turnover_cr": row["debit_turnover_cr"],
            "cheque_returns": row["cheque_returns"],
            "limit_cr": row["limit"],
            "utilized_cr": row["utilized"],
            "utilization_pct": round(row["utilized"] / row["limit"] * 100, 1),
        })
    return buf.getvalue()


def gen_repayment_history_csv(conduct_data=None):
    cd = conduct_data or ETB_CONDUCT
    buf = BytesIO()
    writer = csv.DictWriter(
        _TextIOWrapper(buf),
        fieldnames=["month", "installment_due_cr", "paid_cr", "paid_date", "status", "dpd"])
    writer.writeheader()
    for row in cd["repayment_history"]:
        dpd = 0
        if "Delay" in row["status"]:
            dpd = int(''.join(c for c in row["status"] if c.isdigit()) or '0')
        writer.writerow({
            "month": row["month"],
            "installment_due_cr": row["installment_due_cr"],
            "paid_cr": row["paid_cr"],
            "paid_date": row["paid_date"],
            "status": row["status"],
            "dpd": dpd,
        })
    return buf.getvalue()


def gen_covenant_tracker_csv(conduct_data=None):
    cd = conduct_data or ETB_CONDUCT
    buf = BytesIO()
    writer = csv.DictWriter(
        _TextIOWrapper(buf),
        fieldnames=["period", "covenant", "required", "actual", "status"])
    writer.writeheader()
    for row in cd["covenant_tracker"]:
        writer.writerow(row)
    return buf.getvalue()


def gen_loan_utilization_csv(conduct_data=None):
    cd = conduct_data or ETB_CONDUCT
    buf = BytesIO()
    writer = csv.DictWriter(
        _TextIOWrapper(buf),
        fieldnames=["date", "facility", "limit_cr", "utilized_cr", "drawing_power_cr", "utilization_pct"])
    writer.writeheader()
    for row in cd["loan_utilization"]:
        writer.writerow({
            **row,
            "utilization_pct": round(row["utilized_cr"] / row["limit_cr"] * 100, 1),
        })
    return buf.getvalue()


class _TextIOWrapper:
    """Wrapper to make BytesIO work with csv.writer."""
    def __init__(self, buf):
        self._buf = buf
    def write(self, s):
        self._buf.write(s.encode('utf-8'))


# ═══════════════════════════════════════════════════════════════════════════════
#  GST Returns PDF
# ═══════════════════════════════════════════════════════════════════════════════

def gen_gst_certificate(eid):
    d = COMPANY_DATA[eid]
    return _pdf_buf(_build_gst_cert, d=d)


def _build_gst_cert(ss, d):
    s = []
    s.append(Paragraph("GOODS AND SERVICES TAX NETWORK", ss['TitleCover']))
    s.append(Paragraph("GST Registration Certificate", ss['SubTitle']))
    s.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#1a3a6a')))
    s.append(Spacer(1, 5*mm))
    s.append(Paragraph(f"<b>GSTIN:</b> {d['gstin']}", ss['BodyNarrative']))
    s.append(Paragraph(f"<b>Legal Name:</b> {d['name']}", ss['BodyNarrative']))
    s.append(Paragraph(f"<b>Trade Name:</b> {d['name']}", ss['BodyNarrative']))
    s.append(Paragraph(f"<b>PAN:</b> {d['pan']}", ss['BodyNarrative']))
    s.append(Paragraph(f"<b>Constitution:</b> {'Public Limited' if d['listed'] else 'Private Limited'} Company", ss['BodyNarrative']))
    s.append(Paragraph(f"<b>Principal Place of Business:</b> {d['registered']}", ss['BodyNarrative']))
    s.append(Paragraph(f"<b>Date of Registration:</b> July 01, 2017", ss['BodyNarrative']))
    s.append(Paragraph(f"<b>Status:</b> Active", ss['BodyNarrative']))
    s.append(Spacer(1, 8*mm))

    gst_fy24 = d["gst_turnover_fy2024"]
    s.append(Paragraph("GST RETURN FILING SUMMARY — FY2024", ss['SectionHead']))
    gst_data = [["Month", "GSTR-1 Filed", "GSTR-3B Filed", "Taxable Value (₹ Cr)", "Tax Paid (₹ Cr)"]]
    months = ["Apr-23","May-23","Jun-23","Jul-23","Aug-23","Sep-23",
              "Oct-23","Nov-23","Dec-23","Jan-24","Feb-24","Mar-24"]
    monthly_base = gst_fy24 / 12
    for i, m in enumerate(months):
        val = monthly_base * (0.92 + (i % 3) * 0.04)
        tax = val * 0.18
        gst_data.append([m, "Yes", "Yes", _fmt(val), _fmt(tax)])
    gst_data.append(["TOTAL FY2024", "", "", _fmt(gst_fy24), _fmt(gst_fy24*0.18)])
    t = Table(gst_data, colWidths=[22*mm, 22*mm, 22*mm, 35*mm, 30*mm])
    t.setStyle(_table_style())
    s.append(t)
    return s


# ═══════════════════════════════════════════════════════════════════════════════
#  PAN Card PDF
# ═══════════════════════════════════════════════════════════════════════════════

def gen_pan_card(eid):
    d = COMPANY_DATA[eid]
    return _pdf_buf(_build_pan_card, d=d)


def _build_pan_card(ss, d):
    s = []
    s.append(Spacer(1, 30*mm))
    s.append(Paragraph("INCOME TAX DEPARTMENT", ss['TitleCover']))
    s.append(Paragraph("GOVERNMENT OF INDIA", ss['SubTitle']))
    s.append(Spacer(1, 10*mm))
    s.append(Paragraph("PERMANENT ACCOUNT NUMBER CARD", ss['SubTitle']))
    s.append(Spacer(1, 10*mm))
    s.append(HRFlowable(width="60%", thickness=2, color=colors.HexColor('#1a3a6a')))
    s.append(Spacer(1, 8*mm))
    s.append(Paragraph(f"<b>PAN:</b> {d['pan']}", ss['BodyNarrative']))
    s.append(Paragraph(f"<b>Name:</b> {d['name']}", ss['BodyNarrative']))
    s.append(Paragraph(f"<b>Status:</b> Company", ss['BodyNarrative']))
    s.append(Paragraph(f"<b>Date of Incorporation:</b> {d['incorporated']}", ss['BodyNarrative']))
    s.append(Spacer(1, 15*mm))
    s.append(Paragraph("This is a digitally generated PAN verification for banking purposes.", ss['SmallNote']))
    return s


# ═══════════════════════════════════════════════════════════════════════════════
#  Request Note / Project Report (Word-style PDF)
# ═══════════════════════════════════════════════════════════════════════════════

def gen_request_note(eid):
    d = COMPANY_DATA[eid]
    return _pdf_buf(_build_request_note, d=d, eid=eid)


def _build_request_note(ss, d, eid):
    amounts = {"BMFG001": 150, "PINF001": 500, "SPHR001": 75, "OLOG001": 100}
    purposes = {
        "BMFG001": "augmentation of working capital limits and capex for new auto-component line",
        "PINF001": "project finance for highway construction — NH-48 Phase III expansion",
        "SPHR001": "working capital for bulk drug API manufacturing expansion",
        "OLOG001": "working capital enhancement and fleet modernization",
    }
    amt = amounts.get(eid, 100)
    purpose = purposes.get(eid, "general corporate purpose")

    s = []
    s.append(Paragraph(d["name"], ss['TitleCover']))
    s.append(Paragraph("REQUEST NOTE FOR BANKING FACILITIES", ss['SubTitle']))
    s.append(HRFlowable(width="100%", thickness=1, color=colors.gray))
    s.append(Spacer(1, 5*mm))
    s.append(Paragraph(
        f"<b>Date:</b> February 20, 2025<br/>"
        f"<b>To:</b> The General Manager — Corporate Credit<br/>"
        f"<b>Subject:</b> Application for credit facility of ₹{amt} Crore<br/><br/>"
        f"Dear Sir/Madam,<br/><br/>"
        f"We, {d['name']} (CIN: {d['cin']}), hereby submit our application for "
        f"banking facilities aggregating to ₹{amt} Crore for the purpose of {purpose}.<br/><br/>"
        f"<b>1. COMPANY BACKGROUND</b><br/>"
        f"Incorporated on {d['incorporated']}, the Company is engaged in {d['sector']}. "
        f"The Company has a proven track record of {2025 - int(d['incorporated'].split('-')[-1])} years "
        f"with {d['employees']} employees. Current credit rating is {d['rating']}.<br/><br/>"
        f"<b>2. FACILITY DETAILS</b><br/>"
        f"Total Facilities Requested: ₹{amt} Crore<br/>"
        , ss['BodyNarrative']))

    fac_data = [["Facility", "Amount (₹ Cr)", "Purpose", "Security"]]
    if eid in ("BMFG001", "SPHR001"):
        fac_data.append(["Working Capital (CC/OD)", str(int(amt*0.6)), "Working capital needs", "Hyp. of stock & debtors"])
        fac_data.append(["Term Loan", str(int(amt*0.4)), "Capex", "First charge on assets"])
    elif eid == "PINF001":
        fac_data.append(["Project Finance TL", str(int(amt*0.7)), "Highway project", "Project assets + BG"])
        fac_data.append(["BG Facility", str(int(amt*0.2)), "Performance guarantees", "Counter-guarantee"])
        fac_data.append(["Working Capital", str(int(amt*0.1)), "Bridge financing", "Receivables"])
    else:
        fac_data.append(["CC/OD Enhancement", str(int(amt*0.5)), "WC enhancement", "Hyp. of receivables"])
        fac_data.append(["Term Loan", str(int(amt*0.3)), "Fleet purchase", "Hypothecation of vehicles"])
        fac_data.append(["LC/BG Facility", str(int(amt*0.2)), "Vendor payments", "Cash margin 10%"])
    t = Table(fac_data, colWidths=[35*mm, 25*mm, 45*mm, 45*mm])
    t.setStyle(_table_style())
    s.append(t)

    s.append(Spacer(1, 5*mm))
    s.append(Paragraph(
        f"<b>3. FINANCIAL PERFORMANCE</b><br/>"
        f"Revenue grew from ₹{_fmt(d['revenue'][2])} Cr (FY2022) to ₹{_fmt(d['revenue'][0])} Cr (FY2024), "
        f"a CAGR of {((d['revenue'][0]/max(d['revenue'][2],0.01))**0.5 - 1)*100:.1f}%. "
        f"EBITDA margin maintained at {d['ebitda'][0]/max(d['revenue'][0],0.01)*100:.1f}%.<br/><br/>"
        f"<b>4. REPAYMENT CAPACITY</b><br/>"
        f"DSCR of {(d['ebit'][0]+d['depreciation'][0])/max(d['finance_cost'][0]+d['long_term_debt'][0]*0.15, 0.01):.2f}x "
        f"demonstrates adequate repayment headroom. "
        f"Interest coverage ratio stands at {d['ebit'][0]/max(d['finance_cost'][0], 0.01):.2f}x.<br/><br/>"
        f"We request your good office to process this proposal at the earliest.<br/><br/>"
        f"Thanking you,<br/>"
        f"For {d['name']}<br/><br/>"
        f"{d['directors'][0][0]}<br/>{d['directors'][0][2]}"
        , ss['BodyNarrative']))
    return s


# ═══════════════════════════════════════════════════════════════════════════════
#  Collateral Valuation Report
# ═══════════════════════════════════════════════════════════════════════════════

def gen_collateral_report(eid):
    d = COMPANY_DATA[eid]
    return _pdf_buf(_build_collateral_report, d=d, eid=eid)


def _build_collateral_report(ss, d, eid):
    s = []
    s.append(Paragraph("APPROVED VALUER REPORT", ss['TitleCover']))
    s.append(Paragraph(f"Property & Asset Valuation — {d['name']}", ss['SubTitle']))
    s.append(HRFlowable(width="100%", thickness=1, color=colors.gray))
    s.append(Spacer(1, 5*mm))

    s.append(Paragraph(f"<b>Date of Valuation:</b> January 10, 2025", ss['BodyNarrative']))
    s.append(Paragraph(f"<b>Valuer:</b> M/s ProValue Assessors (IBBI Reg: IBBI/RV/123456)", ss['BodyNarrative']))
    s.append(Spacer(1, 5*mm))

    fixed = d["fixed_assets"][0]
    col_data = [["Asset Description", "Location", "Market Value (₹ Cr)", "Forced Sale Value (₹ Cr)", "Encumbrance"]]

    if eid == "BMFG001":
        col_data.append(["Factory Land & Building (5 acres)", "MIDC Chakan, Pune", f"{fixed*0.35:.0f}", f"{fixed*0.35*0.7:.0f}", "First Charge — SBI"])
        col_data.append(["Plant & Machinery", "MIDC Chakan, Pune", f"{fixed*0.45:.0f}", f"{fixed*0.45*0.6:.0f}", "First Charge — SBI"])
        col_data.append(["Office Premises", "Baner, Pune", f"{fixed*0.10:.0f}", f"{fixed*0.10*0.75:.0f}", "Unencumbered"])
    elif eid == "PINF001":
        col_data.append(["Project Site — NH-48 Phase III", "Gujarat-Rajasthan", f"{fixed*0.50:.0f}", f"{fixed*0.50*0.5:.0f}", "Project lien"])
        col_data.append(["Heavy Equipment Fleet", "Various sites", f"{fixed*0.30:.0f}", f"{fixed*0.30*0.55:.0f}", "Hyp. — IDBI"])
        col_data.append(["Corporate Office", "Jasola, Delhi", f"{fixed*0.12:.0f}", f"{fixed*0.12*0.75:.0f}", "Second Charge"])
    elif eid == "SPHR001":
        col_data.append(["API Manufacturing Plant", "GIDC Ankleshwar", f"{fixed*0.55:.0f}", f"{fixed*0.55*0.65:.0f}", "First Charge — BOB"])
        col_data.append(["R&D Lab Equipment", "GIDC Ankleshwar", f"{fixed*0.25:.0f}", f"{fixed*0.25*0.5:.0f}", "Hyp. — ICICI"])
        col_data.append(["Promoter Personal Property", "Ahmedabad", "18.00", "12.60", "Offered as collateral"])
    else:
        col_data.append(["Warehouse Complex (3 units)", "Whitefield, Bangalore", f"{fixed*0.40:.0f}", f"{fixed*0.40*0.65:.0f}", "First Charge — SBI"])
        col_data.append(["Fleet — 45 Trucks", "Various locations", f"{fixed*0.35:.0f}", f"{fixed*0.35*0.5:.0f}", "Hyp. — Axis Bank"])
        col_data.append(["Sorting & Logistics Hub", "Hosur, TN", f"{fixed*0.15:.0f}", f"{fixed*0.15*0.60:.0f}", "Unencumbered"])

    t = Table(col_data, colWidths=[40*mm, 32*mm, 28*mm, 30*mm, 28*mm])
    t.setStyle(_table_style())
    s.append(t)

    s.append(Spacer(1, 8*mm))
    # Total
    mv_total = fixed * 0.90
    fsv_total = fixed * 0.58
    s.append(Paragraph(f"<b>Total Market Value:</b> ₹{mv_total:.0f} Crore", ss['BodyNarrative']))
    s.append(Paragraph(f"<b>Total Forced Sale Value:</b> ₹{fsv_total:.0f} Crore", ss['BodyNarrative']))
    s.append(Paragraph(f"<b>FSV/MV Ratio:</b> {fsv_total/mv_total*100:.0f}%", ss['BodyNarrative']))
    s.append(Spacer(1, 10*mm))
    s.append(Paragraph("Certified that the above valuation has been carried out as per guidelines issued by "
                        "the Indian Banks' Association and RBI. The valuer has no conflict of interest.", ss['SmallNote']))
    return s


# ═══════════════════════════════════════════════════════════════════════════════
#  Main — Generate all documents
# ═══════════════════════════════════════════════════════════════════════════════

def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def _write(folder, filename, data):
    if data is None:
        return False
    filepath = folder / filename
    mode = 'wb' if isinstance(data, bytes) else 'w'
    with open(filepath, mode) as f:
        f.write(data)
    print(f"  ✓ {filename} ({len(data):,} bytes)")
    return True


def generate_all():
    print("=" * 70)
    print("CAM Intelligence Platform — POC Document Generator")
    print("=" * 70)
    total = 0

    for eid, d in COMPANY_DATA.items():
        print(f"\n{'─' * 50}")
        print(f"📁 {eid} — {d['name']}")
        print(f"   Type: {'Listed' if d['listed'] else 'Private'} | Sector: {d['sector']}")
        print(f"{'─' * 50}")

        base = STORAGE / eid
        # Create category subdirectories
        for cat in ["kyc", "financials", "bureau", "legal", "collateral",
                     "ratings", "gst", "mca", "banking", "misc",
                     "exchange", "etb_internal", "request"]:
            _ensure_dir(base / cat)

        # ── KYC Documents ──
        count = 0
        count += _write(base / "kyc", "pan_card.pdf", gen_pan_card(eid))
        count += _write(base / "kyc", "certificate_of_incorporation.pdf", gen_certificate_of_incorporation(eid))
        count += _write(base / "kyc", "board_resolution_borrowing.pdf", gen_board_resolution(eid))

        # ── Financial Documents ──
        count += _write(base / "financials", "annual_report_fy2024.pdf", gen_annual_report(eid))
        count += _write(base / "financials", "audited_financial_statements.pdf", gen_audited_financials(eid))
        count += _write(base / "financials", "provisional_financials_fy2025.xlsx", gen_provisional_financials_excel(eid))
        count += _write(base / "financials", "debt_schedule.xlsx", gen_debt_schedule_excel(eid))

        # ── Rating Report ──
        count += _write(base / "ratings", "credit_rating_report.pdf", gen_rating_report(eid))

        # ── GST Documents ──
        count += _write(base / "gst", "gst_registration_certificate.pdf", gen_gst_certificate(eid))

        # ── Collateral ──
        count += _write(base / "collateral", "valuation_report.pdf", gen_collateral_report(eid))

        # ── Banking ──
        count += _write(base / "banking", "bank_statement_fy2025.pdf", gen_bank_statement(eid))

        # ── Request Note ──
        count += _write(base / "request", "request_note.pdf", gen_request_note(eid))

        # ── Exchange Filings (Listed only) ──
        if d["listed"]:
            ex_data = gen_exchange_filing(eid)
            count += _write(base / "exchange", "quarterly_results_q3fy2025.pdf", ex_data)
            gov_data = gen_governance_report(eid)
            count += _write(base / "exchange", "corporate_governance_report.pdf", gov_data)

        # ── ETB Internal Data (for ETB companies) ──
        if eid in ETB_CONDUCT_ALL:
            cd = ETB_CONDUCT_ALL[eid]
            count += _write(base / "etb_internal", "account_conduct.csv", gen_account_conduct_csv(cd))
            count += _write(base / "etb_internal", "repayment_history.csv", gen_repayment_history_csv(cd))
            count += _write(base / "etb_internal", "covenant_tracker.csv", gen_covenant_tracker_csv(cd))
            count += _write(base / "etb_internal", "loan_utilization.csv", gen_loan_utilization_csv(cd))

        # ── Mock API response JSONs (for reference) ──
        _write(base / "mca", "mca_master_data.json", json.dumps({
            "source": "MCA", "cin": d["cin"], "company_name": d["name"],
            "status": "Active", "category": "Company limited by shares",
            "paid_up_capital_cr": d["paid_up"],
            "date_of_incorporation": d["incorporated"],
            "registered_office": d["registered"],
        }, indent=2).encode())
        count += 1

        total += count
        print(f"  → {count} documents generated")

    print(f"\n{'=' * 70}")
    print(f"Total: {total} documents generated across {len(COMPANY_DATA)} companies")
    print(f"Storage: {STORAGE}")
    print(f"{'=' * 70}")

    # Summary matrix
    print("\n📊 DOCUMENT MATRIX:")
    print(f"{'Document':<40} {'BMFG001':^8} {'PINF001':^8} {'SPHR001':^8} {'OLOG001':^8}")
    print("─" * 72)
    docs = [
        ("PAN Card (PDF)", True, True, True, True),
        ("Certificate of Incorporation (PDF)", True, True, True, True),
        ("Board Resolution (PDF)", True, True, True, True),
        ("Annual Report (PDF)", True, True, True, True),
        ("Audited Financials (PDF)", True, True, True, True),
        ("Provisional Financials (Excel)", True, True, True, True),
        ("Debt Schedule (Excel)", True, True, True, True),
        ("Credit Rating Report (PDF)", True, True, True, True),
        ("GST Certificate + Returns (PDF)", True, True, True, True),
        ("Collateral Valuation (PDF)", True, True, True, True),
        ("Bank Statement (PDF)", True, True, True, True),
        ("Request Note (PDF)", True, True, True, True),
        ("Exchange Filing Q3 (PDF)", True, True, False, False),
        ("Corporate Governance (PDF)", True, True, False, False),
        ("Account Conduct (CSV)", False, False, False, True),
        ("Repayment History (CSV)", False, False, False, True),
        ("Covenant Tracker (CSV)", False, False, False, True),
        ("Loan Utilization (CSV)", False, False, False, True),
    ]
    for doc_name, b, p, s, o in docs:
        print(f"{doc_name:<40} {'  ✓':^8} {'  ✓' if p else '  —':^8} {'  ✓' if s else '  —':^8} {'  ✓' if o else '  —':^8}")

    print(f"\n⚠️  PINF001 has INTENTIONAL MISMATCHES for validation testing:")
    print(f"   Audited Revenue:     ₹1,200.00 Cr")
    print(f"   Provisional Revenue: ₹1,350.00 Cr (+12.5%)")
    print(f"   Exchange Q3 (ann.):  ~₹1,173.00 Cr (-2.3%)")
    print(f"   GST Turnover:        ₹1,250.00 Cr (+4.2%)")


if __name__ == "__main__":
    generate_all()
