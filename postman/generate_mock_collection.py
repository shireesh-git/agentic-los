#!/usr/bin/env python3
"""
Generate Postman Collection for CAM External Data Source Mock Server.

Produces a Postman v2.1.0 collection with per-company mock responses
for all external APIs. Import into Postman → Create Mock Server →
point the app at the mock URL.

Usage:
    cd postman && python generate_mock_collection.py

Outputs:
    CAM_ExternalData_MockServer.postman_collection.json
    CAM_ExternalData.postman_environment.json
"""

import json
import uuid
from pathlib import Path
from copy import deepcopy

# ═══════════════════════════════════════════════════════════════════════════════
# COMPANY REGISTRY — All 16 companies with data needed for mock API responses
# ═══════════════════════════════════════════════════════════════════════════════

COMPANIES = [
    # ── Synthetic ──
    {
        "eid": "BMFG001", "name": "Bharat Manufacturing Ltd",
        "cin": "L29100MH2008PLC185432", "pan": "AABCB1234F",
        "gstin": "27AABCB1234F1Z5", "state": "Maharashtra",
        "class": "Public", "category": "Limited by Shares",
        "listing": "Listed", "exchange": "BSE, NSE",
        "incorp": "2008-04-15", "office": "Plot 45, MIDC Industrial Area, Pune 411018",
        "email": "info@bharatmanufacturing.com", "nic": "2819",
        "nic_desc": "Manufacturing of machinery and equipment",
        "auth_cap": 10_000_000_000, "paid_cap": 6_250_000_000,
        "isin": "INE999A01020", "nse_sym": "BMFG", "bse_code": "532100",
        "bureau_score": 782, "score_band": "A+", "exposure_cr": 685.0,
        "dpd_status": "Standard", "lenders": 6, "max_dpd_12m": 0,
        "rating_agency": "CRISIL", "lt_rating": "A+", "st_rating": "A1",
        "outlook": "Stable", "last_action": "Reaffirmed",
        "sentiment": "positive", "sent_score": 0.68, "rep_risk": "low",
        "gst_to_fy24": 680.0, "gst_to_fy23": 610.0,
        "sector_label": "Manufacturing — Machinery & Equipment",
        "promoter_pct": 62.3, "mkt_cap_cr": 2800.0,
        "directors": [
            {"din": "00112233", "name": "Rajesh K. Mehta", "desig": "Managing Director", "appt": "2008-04-15", "share": 28.5},
            {"din": "00112234", "name": "Sunita R. Mehta", "desig": "Whole-time Director", "appt": "2010-07-01", "share": 18.2},
            {"din": "00112235", "name": "Amit Deshmukh", "desig": "Independent Director", "appt": "2018-09-15", "share": 0},
        ],
        "charges": [
            {"holder": "State Bank of India", "amount_cr": 250.0, "created": "2020-06-15", "status": "Open"},
            {"holder": "HDFC Bank", "amount_cr": 150.0, "created": "2021-03-10", "status": "Open"},
        ],
        "bureau_facilities": [
            {"lender": "SBI", "type": "Term Loan", "limit_cr": 200.0, "outstanding_cr": 128.0, "dpd": 0},
            {"lender": "HDFC Bank", "type": "CC/OD", "limit_cr": 150.0, "outstanding_cr": 98.0, "dpd": 0},
            {"lender": "ICICI Bank", "type": "Working Capital", "limit_cr": 100.0, "outstanding_cr": 72.0, "dpd": 0},
        ],
        "news": [
            {"title": "Bharat Manufacturing wins ₹200 Cr defence contract", "source": "Economic Times", "dt": "2026-02-10", "sent": "positive"},
            {"title": "MIDC expansion plan to boost capacity 40%", "source": "Business Standard", "dt": "2026-01-15", "sent": "positive"},
        ],
    },
    {
        "eid": "PINF001", "name": "Pinnacle Infra Projects Ltd",
        "cin": "L45200DL2005PLC134567", "pan": "AABCP5678G",
        "gstin": "07AABCP5678G1Z8", "state": "Delhi",
        "class": "Public", "category": "Limited by Shares",
        "listing": "Listed", "exchange": "NSE",
        "incorp": "2005-08-22", "office": "502, Nehru Place, New Delhi 110019",
        "email": "corp@pinnacleinfra.com", "nic": "4210",
        "nic_desc": "Construction of roads and railways",
        "auth_cap": 20_000_000_000, "paid_cap": 12_500_000_000,
        "isin": "INE998A01020", "nse_sym": "PINF", "bse_code": None,
        "bureau_score": 738, "score_band": "A", "exposure_cr": 1850.0,
        "dpd_status": "Standard", "lenders": 8, "max_dpd_12m": 7,
        "rating_agency": "ICRA", "lt_rating": "A", "st_rating": "A1",
        "outlook": "Stable", "last_action": "Assigned",
        "sentiment": "neutral", "sent_score": 0.42, "rep_risk": "medium",
        "gst_to_fy24": 1480.0, "gst_to_fy23": 1320.0,
        "sector_label": "Infrastructure — Roads & Railways",
        "promoter_pct": 55.1, "mkt_cap_cr": 5200.0,
        "directors": [
            {"din": "00223344", "name": "Vikram Singh", "desig": "Chairman & MD", "appt": "2005-08-22", "share": 42.0},
            {"din": "00223345", "name": "Priya Sharma", "desig": "CFO", "appt": "2015-04-01", "share": 2.1},
        ],
        "charges": [
            {"holder": "Punjab National Bank", "amount_cr": 800.0, "created": "2019-01-20", "status": "Open"},
        ],
        "bureau_facilities": [
            {"lender": "PNB", "type": "Term Loan", "limit_cr": 500.0, "outstanding_cr": 380.0, "dpd": 0},
            {"lender": "Canara Bank", "type": "BG", "limit_cr": 350.0, "outstanding_cr": 280.0, "dpd": 0},
        ],
        "news": [
            {"title": "Pinnacle bags ₹1,200 Cr highway project in UP", "source": "Mint", "dt": "2026-01-28", "sent": "positive"},
        ],
    },
    {
        "eid": "SPHR001", "name": "Sunrise Pharma Pvt Ltd",
        "cin": "U24230GJ2012PTC068945", "pan": "AABCS9012H",
        "gstin": "24AABCS9012H1Z2", "state": "Gujarat",
        "class": "Private", "category": "Limited by Shares",
        "listing": "Unlisted", "exchange": None,
        "incorp": "2012-06-10", "office": "Survey 45, Taluka Savli, Vadodara 391520",
        "email": "finance@sunrisepharma.in", "nic": "2100",
        "nic_desc": "Manufacture of pharmaceuticals and medicinal chemical products",
        "auth_cap": 500_000_000, "paid_cap": 180_000_000,
        "isin": None, "nse_sym": None, "bse_code": None,
        "bureau_score": 695, "score_band": "BBB+", "exposure_cr": 85.0,
        "dpd_status": "Standard", "lenders": 3, "max_dpd_12m": 12,
        "rating_agency": "CARE", "lt_rating": "BBB+", "st_rating": "A3+",
        "outlook": "Stable", "last_action": "Reaffirmed",
        "sentiment": "neutral", "sent_score": 0.35, "rep_risk": "low",
        "gst_to_fy24": 145.0, "gst_to_fy23": 128.0,
        "sector_label": "Pharma — Formulations",
        "promoter_pct": 100.0, "mkt_cap_cr": None,
        "directors": [
            {"din": "00334455", "name": "Harsh Patel", "desig": "Managing Director", "appt": "2012-06-10", "share": 60.0},
            {"din": "00334456", "name": "Meena Patel", "desig": "Director", "appt": "2012-06-10", "share": 40.0},
        ],
        "charges": [
            {"holder": "Bank of Baroda", "amount_cr": 45.0, "created": "2020-09-01", "status": "Open"},
        ],
        "bureau_facilities": [
            {"lender": "Bank of Baroda", "type": "CC/OD", "limit_cr": 50.0, "outstanding_cr": 38.0, "dpd": 0},
            {"lender": "Union Bank", "type": "Term Loan", "limit_cr": 35.0, "outstanding_cr": 22.0, "dpd": 12},
        ],
        "news": [
            {"title": "Gujarat pharma SME exports rise 15% YoY", "source": "Financial Express", "dt": "2026-02-05", "sent": "positive"},
        ],
    },
    {
        "eid": "OLOG001", "name": "Omega Logistics Pvt Ltd",
        "cin": "U63090KA2010PTC052345", "pan": "AABCO3456J",
        "gstin": "29AABCO3456J1Z1", "state": "Karnataka",
        "class": "Private", "category": "Limited by Shares",
        "listing": "Unlisted", "exchange": None,
        "incorp": "2010-01-15", "office": "78, Peenya Industrial Area, Bengaluru 560058",
        "email": "ops@omegalogistics.in", "nic": "5229",
        "nic_desc": "Other transportation support activities",
        "auth_cap": 200_000_000, "paid_cap": 95_000_000,
        "isin": None, "nse_sym": None, "bse_code": None,
        "bureau_score": 710, "score_band": "A-", "exposure_cr": 62.0,
        "dpd_status": "Standard", "lenders": 2, "max_dpd_12m": 5,
        "rating_agency": None, "lt_rating": "NR", "st_rating": "NR",
        "outlook": None, "last_action": None,
        "sentiment": "neutral", "sent_score": 0.30, "rep_risk": "low",
        "gst_to_fy24": 110.0, "gst_to_fy23": 95.0,
        "sector_label": "Logistics — Freight & Warehousing",
        "promoter_pct": 100.0, "mkt_cap_cr": None,
        "directors": [
            {"din": "00445566", "name": "Ravi Kumar N.", "desig": "Managing Director", "appt": "2010-01-15", "share": 70.0},
            {"din": "00445567", "name": "Lakshmi R.", "desig": "Director", "appt": "2012-04-01", "share": 30.0},
        ],
        "charges": [],
        "bureau_facilities": [
            {"lender": "Kotak Mahindra Bank", "type": "Term Loan", "limit_cr": 30.0, "outstanding_cr": 18.0, "dpd": 0},
        ],
        "news": [],
    },

    # ── Real-Inspired ──
    {
        "eid": "TSTL001", "name": "Tara Steels Industries Ltd",
        "cin": "L27100MH1907PLC000260", "pan": "AAACT1234A",
        "gstin": "27AAACT1234A1Z8", "state": "Maharashtra",
        "class": "Public", "category": "Limited by Shares",
        "listing": "Listed", "exchange": "BSE, NSE",
        "incorp": "1907-08-26", "office": "Bombay House, 24 Homi Mody Street, Mumbai 400001",
        "email": "investor@tarasteels.com", "nic": "2710",
        "nic_desc": "Manufacture of basic iron and steel",
        "auth_cap": 15_000_000_000, "paid_cap": 12_187_415_880,
        "isin": "INE081A01020", "nse_sym": "TARASTEEL", "bse_code": "500470",
        "bureau_score": 795, "score_band": "AA", "exposure_cr": 42500.0,
        "dpd_status": "Standard", "lenders": 18, "max_dpd_12m": 0,
        "rating_agency": "CRISIL", "lt_rating": "AA", "st_rating": "A1+",
        "outlook": "Stable", "last_action": "Reaffirmed",
        "sentiment": "positive", "sent_score": 0.72, "rep_risk": "low",
        "gst_to_fy24": 24500.0, "gst_to_fy23": 22100.0,
        "sector_label": "Steel — Integrated Manufacturer",
        "promoter_pct": 33.9, "mkt_cap_cr": 185000.0,
        "directors": [
            {"din": "00004009", "name": "Natarajan C.", "desig": "Chairman", "appt": "2017-02-21", "share": 0},
            {"din": "03083605", "name": "T.V. Narendran", "desig": "CEO & MD", "appt": "2013-09-19", "share": 0.01},
            {"din": "06639356", "name": "Koushik Chatterjee", "desig": "ED & CFO", "appt": "2013-11-07", "share": 0.005},
            {"din": "00014615", "name": "Deepak Kapoor", "desig": "Independent Director", "appt": "2015-10-09", "share": 0},
        ],
        "charges": [
            {"holder": "SBI Consortium", "amount_cr": 15000.0, "created": "2018-04-10", "status": "Open"},
            {"holder": "LIC of India", "amount_cr": 5000.0, "created": "2020-01-15", "status": "Open"},
            {"holder": "ICICI Bank", "amount_cr": 3000.0, "created": "2021-07-20", "status": "Open"},
        ],
        "bureau_facilities": [
            {"lender": "SBI", "type": "Term Loan", "limit_cr": 12000.0, "outstanding_cr": 9800.0, "dpd": 0},
            {"lender": "ICICI Bank", "type": "Working Capital", "limit_cr": 5000.0, "outstanding_cr": 3200.0, "dpd": 0},
            {"lender": "HDFC Bank", "type": "NCD", "limit_cr": 8000.0, "outstanding_cr": 7500.0, "dpd": 0},
            {"lender": "Axis Bank", "type": "CC/OD", "limit_cr": 3000.0, "outstanding_cr": 2100.0, "dpd": 0},
            {"lender": "PNB", "type": "Term Loan", "limit_cr": 4000.0, "outstanding_cr": 3500.0, "dpd": 0},
        ],
        "news": [
            {"title": "Tara Steels commissions 5 MTPA Kalinganagar expansion", "source": "Economic Times", "dt": "2026-02-15", "sent": "positive"},
            {"title": "CRISIL reaffirms AA/Stable; deleveraging ahead of schedule", "source": "CRISIL PR", "dt": "2025-11-12", "sent": "positive"},
            {"title": "Steel demand outlook strong for FY27 — CRISIL", "source": "Mint", "dt": "2026-01-20", "sent": "positive"},
        ],
    },
    {
        "eid": "REIL001", "name": "Reliable Energy Industries Ltd",
        "cin": "L17110MH1973PLC019786", "pan": "AAACR2345B",
        "gstin": "27AAACR2345B1Z6", "state": "Maharashtra",
        "class": "Public", "category": "Limited by Shares",
        "listing": "Listed", "exchange": "BSE, NSE",
        "incorp": "1973-05-08", "office": "Maker Chambers IV, Nariman Point, Mumbai 400021",
        "email": "investor@reliableenergy.com", "nic": "1920",
        "nic_desc": "Manufacture of refined petroleum products",
        "auth_cap": 150_000_000_000, "paid_cap": 67_660_000_000,
        "isin": "INE002A01018", "nse_sym": "RELENER", "bse_code": "500325",
        "bureau_score": 820, "score_band": "AAA", "exposure_cr": 185000.0,
        "dpd_status": "Standard", "lenders": 28, "max_dpd_12m": 0,
        "rating_agency": "CRISIL", "lt_rating": "AAA", "st_rating": "A1+",
        "outlook": "Stable", "last_action": "Reaffirmed",
        "sentiment": "positive", "sent_score": 0.78, "rep_risk": "low",
        "gst_to_fy24": 280000.0, "gst_to_fy23": 265000.0,
        "sector_label": "Energy — Petroleum Refining & Petrochemicals",
        "promoter_pct": 50.3, "mkt_cap_cr": 1950000.0,
        "directors": [
            {"din": "00001695", "name": "Mukesh D. Ambani (inspired)", "desig": "Chairman & MD", "appt": "2002-07-01", "share": 0},
            {"din": "00001696", "name": "Nikhil Meswani (inspired)", "desig": "Executive Director", "appt": "1986-12-18", "share": 0},
        ],
        "charges": [
            {"holder": "SBI Consortium", "amount_cr": 45000.0, "created": "2017-03-15", "status": "Open"},
            {"holder": "Axis Bank", "amount_cr": 25000.0, "created": "2019-08-20", "status": "Open"},
        ],
        "bureau_facilities": [
            {"lender": "SBI", "type": "Term Loan", "limit_cr": 35000.0, "outstanding_cr": 28000.0, "dpd": 0},
            {"lender": "ICICI", "type": "NCD", "limit_cr": 25000.0, "outstanding_cr": 22000.0, "dpd": 0},
            {"lender": "Axis Bank", "type": "Working Capital", "limit_cr": 15000.0, "outstanding_cr": 9500.0, "dpd": 0},
        ],
        "news": [
            {"title": "Reliable Energy green hydrogen plant on track for 2027 commissioning", "source": "ET Energy", "dt": "2026-02-18", "sent": "positive"},
            {"title": "Jio Platforms revenue crosses ₹1 Lakh Crore — telecom arm strong", "source": "Mint", "dt": "2026-01-25", "sent": "positive"},
        ],
    },
    {
        "eid": "INFY001", "name": "Infotech Systems Ltd",
        "cin": "L85110KA1981PLC013115", "pan": "AAACI3456C",
        "gstin": "29AAACI3456C1Z4", "state": "Karnataka",
        "class": "Public", "category": "Limited by Shares",
        "listing": "Listed", "exchange": "BSE, NSE",
        "incorp": "1981-07-02", "office": "Electronics City, Hosur Road, Bengaluru 560100",
        "email": "investor@infotechsystems.com", "nic": "6202",
        "nic_desc": "Computer consultancy and computer facilities management activities",
        "auth_cap": 24_000_000_000, "paid_cap": 21_420_000_000,
        "isin": "INE009A01021", "nse_sym": "INFOTECH", "bse_code": "500209",
        "bureau_score": 835, "score_band": "AAA", "exposure_cr": 2500.0,
        "dpd_status": "Standard", "lenders": 3, "max_dpd_12m": 0,
        "rating_agency": "CRISIL", "lt_rating": "AAA", "st_rating": "A1+",
        "outlook": "Stable", "last_action": "Reaffirmed",
        "sentiment": "positive", "sent_score": 0.81, "rep_risk": "low",
        "gst_to_fy24": 55000.0, "gst_to_fy23": 50200.0,
        "sector_label": "IT Services — Software Consulting",
        "promoter_pct": 14.8, "mkt_cap_cr": 620000.0,
        "directors": [
            {"din": "07218338", "name": "Salil S. Parekh (inspired)", "desig": "CEO & MD", "appt": "2018-01-02", "share": 0.02},
            {"din": "08058610", "name": "Nilanjan Roy (inspired)", "desig": "CFO", "appt": "2019-04-01", "share": 0},
        ],
        "charges": [],
        "bureau_facilities": [
            {"lender": "HSBC", "type": "Working Capital", "limit_cr": 1500.0, "outstanding_cr": 800.0, "dpd": 0},
        ],
        "news": [
            {"title": "Infotech Systems bags $2B deal with global bank", "source": "ET Tech", "dt": "2026-03-02", "sent": "positive"},
            {"title": "Q3 FY26: Revenue up 6.2% QoQ; margin guidance raised", "source": "CNBC-TV18", "dt": "2026-01-11", "sent": "positive"},
        ],
    },
    {
        "eid": "ADPT001", "name": "Advik Ports & SEZ Ltd",
        "cin": "L63090GJ1998PLC034182", "pan": "AAACA4567D",
        "gstin": "24AAACA4567D1Z2", "state": "Gujarat",
        "class": "Public", "category": "Limited by Shares",
        "listing": "Listed", "exchange": "BSE, NSE",
        "incorp": "1998-05-26", "office": "Adani House, Near Mithakhali, Ahmedabad 380009",
        "email": "ir@advikports.com", "nic": "5222",
        "nic_desc": "Service activities incidental to water transportation",
        "auth_cap": 22_680_000_000, "paid_cap": 20_420_000_000,
        "isin": "INE742F01042", "nse_sym": "ADVIKPORT", "bse_code": "532921",
        "bureau_score": 770, "score_band": "AA-", "exposure_cr": 28500.0,
        "dpd_status": "Standard", "lenders": 14, "max_dpd_12m": 0,
        "rating_agency": "ICRA", "lt_rating": "AA-", "st_rating": "A1+",
        "outlook": "Positive", "last_action": "Upgraded",
        "sentiment": "positive", "sent_score": 0.62, "rep_risk": "medium",
        "gst_to_fy24": 18500.0, "gst_to_fy23": 16200.0,
        "sector_label": "Infrastructure — Ports & Logistics",
        "promoter_pct": 65.9, "mkt_cap_cr": 245000.0,
        "directors": [
            {"din": "00006273", "name": "Karan Shah (inspired)", "desig": "CEO & Whole-time Director", "appt": "2016-01-02", "share": 0},
        ],
        "charges": [
            {"holder": "SBI Consortium", "amount_cr": 12000.0, "created": "2019-05-10", "status": "Open"},
        ],
        "bureau_facilities": [
            {"lender": "SBI", "type": "Term Loan", "limit_cr": 8000.0, "outstanding_cr": 6500.0, "dpd": 0},
            {"lender": "Axis Bank", "type": "NCD", "limit_cr": 5000.0, "outstanding_cr": 4800.0, "dpd": 0},
        ],
        "news": [
            {"title": "Advik Ports cargo volume up 18% YoY at Mundra", "source": "Shipping Times", "dt": "2026-02-20", "sent": "positive"},
        ],
    },
    {
        "eid": "BJFN001", "name": "Bajrang Finance Ltd",
        "cin": "L65910MH1987PLC042961", "pan": "AABCB5678E",
        "gstin": "27AABCB5678E1Z3", "state": "Maharashtra",
        "class": "Public", "category": "Limited by Shares",
        "listing": "Listed", "exchange": "BSE, NSE",
        "incorp": "1987-03-25", "office": "Akurdi, Pune 411035",
        "email": "investor@bajrangfinance.com", "nic": "6492",
        "nic_desc": "Other credit granting (NBFC activities)",
        "auth_cap": 10_000_000_000, "paid_cap": 6_042_000_000,
        "isin": "INE296A01024", "nse_sym": "BAJFIN", "bse_code": "500034",
        "bureau_score": 805, "score_band": "AA+", "exposure_cr": 95000.0,
        "dpd_status": "Standard", "lenders": 22, "max_dpd_12m": 0,
        "rating_agency": "CRISIL", "lt_rating": "AA+", "st_rating": "A1+",
        "outlook": "Stable", "last_action": "Reaffirmed",
        "sentiment": "positive", "sent_score": 0.75, "rep_risk": "low",
        "gst_to_fy24": 42000.0, "gst_to_fy23": 35500.0,
        "sector_label": "NBFC — Consumer & SME Lending",
        "promoter_pct": 54.8, "mkt_cap_cr": 520000.0,
        "directors": [
            {"din": "00018262", "name": "Rajeev Jain (inspired)", "desig": "Managing Director", "appt": "2015-04-01", "share": 0.8},
        ],
        "charges": [
            {"holder": "RBI-regulated NCD Trustees", "amount_cr": 35000.0, "created": "2021-06-01", "status": "Open"},
        ],
        "bureau_facilities": [
            {"lender": "SBI", "type": "Term Loan", "limit_cr": 15000.0, "outstanding_cr": 12000.0, "dpd": 0},
            {"lender": "HDFC Bank", "type": "NCD", "limit_cr": 20000.0, "outstanding_cr": 18500.0, "dpd": 0},
        ],
        "news": [
            {"title": "Bajrang Finance AUM crosses ₹3.5 Lakh Crore mark", "source": "Mint", "dt": "2026-02-12", "sent": "positive"},
        ],
    },
    {
        "eid": "CIPL001", "name": "Ciplex Pharmaceuticals Ltd",
        "cin": "L24239MH1935PLC002380", "pan": "AAACC6789F",
        "gstin": "27AAACC6789F1Z1", "state": "Maharashtra",
        "class": "Public", "category": "Limited by Shares",
        "listing": "Listed", "exchange": "BSE, NSE",
        "incorp": "1935-08-22", "office": "Ciplex House, Peninsula Business Park, Mumbai 400013",
        "email": "investor@ciplex.com", "nic": "2100",
        "nic_desc": "Manufacture of pharmaceuticals and bio-tech products",
        "auth_cap": 4_000_000_000, "paid_cap": 1_614_000_000,
        "isin": "INE059A01026", "nse_sym": "CIPLEX", "bse_code": "500087",
        "bureau_score": 790, "score_band": "AA", "exposure_cr": 4200.0,
        "dpd_status": "Standard", "lenders": 5, "max_dpd_12m": 0,
        "rating_agency": "CRISIL", "lt_rating": "AA", "st_rating": "A1+",
        "outlook": "Stable", "last_action": "Reaffirmed",
        "sentiment": "positive", "sent_score": 0.70, "rep_risk": "low",
        "gst_to_fy24": 12800.0, "gst_to_fy23": 11500.0,
        "sector_label": "Pharma — Generics & APIs",
        "promoter_pct": 33.5, "mkt_cap_cr": 95000.0,
        "directors": [
            {"din": "00007657", "name": "Umang Vohra (inspired)", "desig": "MD & CEO", "appt": "2016-09-01", "share": 0},
        ],
        "charges": [
            {"holder": "Citibank", "amount_cr": 2000.0, "created": "2022-01-15", "status": "Open"},
        ],
        "bureau_facilities": [
            {"lender": "Citibank", "type": "Working Capital", "limit_cr": 2000.0, "outstanding_cr": 1200.0, "dpd": 0},
            {"lender": "HSBC", "type": "Term Loan", "limit_cr": 1500.0, "outstanding_cr": 900.0, "dpd": 0},
        ],
        "news": [
            {"title": "Ciplex launches 5 new biosimilars in US market", "source": "Pharma Biz", "dt": "2026-02-08", "sent": "positive"},
        ],
    },
    {
        "eid": "DLFR001", "name": "Delhi Land & Realty Ltd",
        "cin": "L70101HR1963PLC002484", "pan": "AAACD7890G",
        "gstin": "06AAACD7890G1Z9", "state": "Haryana",
        "class": "Public", "category": "Limited by Shares",
        "listing": "Listed", "exchange": "BSE, NSE",
        "incorp": "1963-03-19", "office": "Shopping Mall, Arjun Marg, DLF Phase 1, Gurugram 122002",
        "email": "ir@delhiland.com", "nic": "4100",
        "nic_desc": "Construction of buildings — Real Estate",
        "auth_cap": 18_000_000_000, "paid_cap": 4_950_000_000,
        "isin": "INE271C01023", "nse_sym": "DLAND", "bse_code": "532868",
        "bureau_score": 680, "score_band": "BBB", "exposure_cr": 22000.0,
        "dpd_status": "SMA-1", "lenders": 12, "max_dpd_12m": 45,
        "rating_agency": "ICRA", "lt_rating": "BBB", "st_rating": "A3+",
        "outlook": "Negative", "last_action": "Downgraded",
        "sentiment": "negative", "sent_score": -0.35, "rep_risk": "high",
        "gst_to_fy24": 6200.0, "gst_to_fy23": 7100.0,
        "sector_label": "Real Estate — Commercial & Residential",
        "promoter_pct": 74.1, "mkt_cap_cr": 42000.0,
        "directors": [
            {"din": "00009900", "name": "Rajiv Singh (inspired)", "desig": "Chairman", "appt": "1999-03-10", "share": 0},
        ],
        "charges": [
            {"holder": "SBI", "amount_cr": 8000.0, "created": "2016-05-20", "status": "Open"},
            {"holder": "HDFC Ltd", "amount_cr": 6000.0, "created": "2018-09-15", "status": "Open"},
        ],
        "bureau_facilities": [
            {"lender": "SBI", "type": "Term Loan", "limit_cr": 5000.0, "outstanding_cr": 4500.0, "dpd": 30},
            {"lender": "HDFC Ltd", "type": "Construction Finance", "limit_cr": 6000.0, "outstanding_cr": 5800.0, "dpd": 15},
            {"lender": "PNB", "type": "CC/OD", "limit_cr": 2000.0, "outstanding_cr": 1900.0, "dpd": 45},
        ],
        "news": [
            {"title": "Delhi Land faces NCLT notice for delayed possession", "source": "Moneycontrol", "dt": "2026-03-05", "sent": "negative"},
            {"title": "Debt restructuring plan under discussion with lenders", "source": "ET Realty", "dt": "2026-02-20", "sent": "negative"},
            {"title": "Gurugram project sales disappoint amid realty slowdown", "source": "LiveMint", "dt": "2026-01-18", "sent": "negative"},
        ],
    },
    {
        "eid": "JSWL001", "name": "JSW Alloys & Steel Ltd",
        "cin": "L27102MH1994PLC083190", "pan": "AAACJ8901H",
        "gstin": "27AAACJ8901H1Z7", "state": "Maharashtra",
        "class": "Public", "category": "Limited by Shares",
        "listing": "Listed", "exchange": "BSE, NSE",
        "incorp": "1994-03-15", "office": "JSW Centre, Bandra Kurla Complex, Mumbai 400051",
        "email": "investor@jswalloys.com", "nic": "2710",
        "nic_desc": "Manufacture of basic iron and steel",
        "auth_cap": 10_000_000_000, "paid_cap": 4_860_000_000,
        "isin": "INE019A01020", "nse_sym": "JSWALLOY", "bse_code": "500228",
        "bureau_score": 765, "score_band": "AA-", "exposure_cr": 35000.0,
        "dpd_status": "Standard", "lenders": 15, "max_dpd_12m": 0,
        "rating_agency": "CRISIL", "lt_rating": "AA-", "st_rating": "A1+",
        "outlook": "Stable", "last_action": "Reaffirmed",
        "sentiment": "positive", "sent_score": 0.58, "rep_risk": "low",
        "gst_to_fy24": 48000.0, "gst_to_fy23": 42500.0,
        "sector_label": "Steel — Flat Products",
        "promoter_pct": 44.8, "mkt_cap_cr": 175000.0,
        "directors": [
            {"din": "00015689", "name": "Sajjan Jindal (inspired)", "desig": "Chairman & MD", "appt": "1994-03-15", "share": 0},
        ],
        "charges": [
            {"holder": "SBI Consortium", "amount_cr": 18000.0, "created": "2020-02-14", "status": "Open"},
        ],
        "bureau_facilities": [
            {"lender": "SBI", "type": "Term Loan", "limit_cr": 10000.0, "outstanding_cr": 8200.0, "dpd": 0},
            {"lender": "Axis Bank", "type": "Working Capital", "limit_cr": 5000.0, "outstanding_cr": 3800.0, "dpd": 0},
        ],
        "news": [
            {"title": "JSW Alloys capacity expansion at Bellary on track", "source": "MetalWorld", "dt": "2026-02-05", "sent": "positive"},
        ],
    },
    {
        "eid": "MRUT001", "name": "Maruti Auto Industries Ltd",
        "cin": "L34103HR1981PLC013258", "pan": "AAACM9012J",
        "gstin": "06AAACM9012J1Z5", "state": "Haryana",
        "class": "Public", "category": "Limited by Shares",
        "listing": "Listed", "exchange": "BSE, NSE",
        "incorp": "1981-02-24", "office": "Plot 1, Nelson Mandela Road, New Delhi 110070",
        "email": "investor@marutiauto.co.in", "nic": "2910",
        "nic_desc": "Manufacture of motor vehicles",
        "auth_cap": 15_000_000_000, "paid_cap": 15_100_000_000,
        "isin": "INE585B01010", "nse_sym": "MARUTI", "bse_code": "532500",
        "bureau_score": 840, "score_band": "AAA", "exposure_cr": 1200.0,
        "dpd_status": "Standard", "lenders": 2, "max_dpd_12m": 0,
        "rating_agency": "CRISIL", "lt_rating": "AAA", "st_rating": "A1+",
        "outlook": "Stable", "last_action": "Reaffirmed",
        "sentiment": "positive", "sent_score": 0.82, "rep_risk": "low",
        "gst_to_fy24": 65000.0, "gst_to_fy23": 58500.0,
        "sector_label": "Automobile — Passenger Vehicles",
        "promoter_pct": 56.5, "mkt_cap_cr": 380000.0,
        "directors": [
            {"din": "00103928", "name": "R C Bhargava (inspired)", "desig": "Chairman", "appt": "2002-06-27", "share": 0},
            {"din": "02262452", "name": "Hisashi Takeuchi (inspired)", "desig": "MD & CEO", "appt": "2022-04-01", "share": 0},
        ],
        "charges": [],
        "bureau_facilities": [
            {"lender": "Citibank", "type": "Working Capital", "limit_cr": 800.0, "outstanding_cr": 400.0, "dpd": 0},
        ],
        "news": [
            {"title": "Maruti Auto posts record monthly sales – 1.73L units in Feb 2026", "source": "Autocar India", "dt": "2026-03-01", "sent": "positive"},
            {"title": "EV push: Maruti to invest ₹18,000 Cr in Gujarat EV plant", "source": "ET Auto", "dt": "2026-02-15", "sent": "positive"},
        ],
    },
    {
        "eid": "TITN001", "name": "Titan Luxe Retail Ltd",
        "cin": "L74999TN1984PLC010491", "pan": "AAACT0123K",
        "gstin": "33AAACT0123K1Z3", "state": "Tamil Nadu",
        "class": "Public", "category": "Limited by Shares",
        "listing": "Listed", "exchange": "BSE, NSE",
        "incorp": "1984-06-04", "office": "Integrity, 3 Brigade Road, Bengaluru 560025",
        "email": "investor@titanluxe.com", "nic": "3212",
        "nic_desc": "Manufacture of jewellery and related articles",
        "auth_cap": 4_000_000_000, "paid_cap": 1_776_000_000,
        "isin": "INE280A01028", "nse_sym": "TITANLUXE", "bse_code": "500114",
        "bureau_score": 798, "score_band": "AA", "exposure_cr": 5500.0,
        "dpd_status": "Standard", "lenders": 4, "max_dpd_12m": 0,
        "rating_agency": "CRISIL", "lt_rating": "AA+", "st_rating": "A1+",
        "outlook": "Stable", "last_action": "Upgraded",
        "sentiment": "positive", "sent_score": 0.74, "rep_risk": "low",
        "gst_to_fy24": 38000.0, "gst_to_fy23": 33500.0,
        "sector_label": "Retail — Watches, Jewellery & Eyewear",
        "promoter_pct": 52.9, "mkt_cap_cr": 290000.0,
        "directors": [
            {"din": "00031051", "name": "CK Venkataraman (inspired)", "desig": "MD", "appt": "2019-10-01", "share": 0.01},
        ],
        "charges": [
            {"holder": "Standard Chartered", "amount_cr": 2500.0, "created": "2022-05-10", "status": "Open"},
        ],
        "bureau_facilities": [
            {"lender": "Standard Chartered", "type": "Working Capital", "limit_cr": 2500.0, "outstanding_cr": 1800.0, "dpd": 0},
            {"lender": "HDFC Bank", "type": "CC/OD", "limit_cr": 1500.0, "outstanding_cr": 900.0, "dpd": 0},
        ],
        "news": [
            {"title": "Titan Luxe Q3 jewellery division grows 25% YoY", "source": "ET Retail", "dt": "2026-02-10", "sent": "positive"},
        ],
    },
    {
        "eid": "NTPC001", "name": "National Thermal Power Corp Ltd",
        "cin": "L40101DL1975GOI007966", "pan": "AAACN1234L",
        "gstin": "07AAACN1234L1Z1", "state": "Delhi",
        "class": "Public", "category": "Limited by Shares",
        "listing": "Listed", "exchange": "BSE, NSE",
        "incorp": "1975-11-07", "office": "NTPC Bhawan, Scope Complex, New Delhi 110003",
        "email": "investorrelations@ntpc.co.in", "nic": "3510",
        "nic_desc": "Electric power generation and distribution",
        "auth_cap": 100_000_000_000, "paid_cap": 97_000_000_000,
        "isin": "INE733E01010", "nse_sym": "NTPC", "bse_code": "532555",
        "bureau_score": 810, "score_band": "AAA", "exposure_cr": 125000.0,
        "dpd_status": "Standard", "lenders": 20, "max_dpd_12m": 0,
        "rating_agency": "CRISIL", "lt_rating": "AAA", "st_rating": "A1+",
        "outlook": "Stable", "last_action": "Reaffirmed",
        "sentiment": "positive", "sent_score": 0.65, "rep_risk": "low",
        "gst_to_fy24": 85000.0, "gst_to_fy23": 78000.0,
        "sector_label": "Power — Thermal & Renewable",
        "promoter_pct": 51.1, "mkt_cap_cr": 350000.0,
        "directors": [
            {"din": "08126560", "name": "Gurdeep Singh (inspired)", "desig": "CMD", "appt": "2016-02-04", "share": 0},
        ],
        "charges": [
            {"holder": "SBI Consortium", "amount_cr": 45000.0, "created": "2015-07-20", "status": "Open"},
            {"holder": "LIC", "amount_cr": 20000.0, "created": "2018-03-15", "status": "Open"},
        ],
        "bureau_facilities": [
            {"lender": "SBI", "type": "Term Loan", "limit_cr": 25000.0, "outstanding_cr": 20000.0, "dpd": 0},
            {"lender": "PFC", "type": "Term Loan", "limit_cr": 18000.0, "outstanding_cr": 15000.0, "dpd": 0},
            {"lender": "LIC", "type": "NCD", "limit_cr": 20000.0, "outstanding_cr": 18500.0, "dpd": 0},
        ],
        "news": [
            {"title": "NTPC commissions 1 GW solar park in Rajasthan", "source": "Renewable Now", "dt": "2026-02-25", "sent": "positive"},
            {"title": "NTPC Green Energy IPO oversubscribed 8x", "source": "ET Markets", "dt": "2026-01-30", "sent": "positive"},
        ],
    },
    {
        "eid": "YESB001", "name": "Yashwant Commercial Bank Ltd",
        "cin": "L65190MH2003PLC143249", "pan": "AAACY2345M",
        "gstin": "27AAACY2345M1Z9", "state": "Maharashtra",
        "class": "Public", "category": "Limited by Shares",
        "listing": "Listed", "exchange": "BSE, NSE",
        "incorp": "2003-11-21", "office": "Nehru Centre, Worli, Mumbai 400018",
        "email": "investor@yashwantbank.in", "nic": "6419",
        "nic_desc": "Other monetary intermediation (Banking)",
        "auth_cap": 11_000_000_000, "paid_cap": 6_313_000_000,
        "isin": "INE528G01035", "nse_sym": "YESBANK", "bse_code": "532648",
        "bureau_score": 640, "score_band": "BBB-", "exposure_cr": 45000.0,
        "dpd_status": "SMA-0", "lenders": 10, "max_dpd_12m": 22,
        "rating_agency": "ICRA", "lt_rating": "BBB-", "st_rating": "A3",
        "outlook": "Watch", "last_action": "Downgraded",
        "sentiment": "negative", "sent_score": -0.28, "rep_risk": "high",
        "gst_to_fy24": 8500.0, "gst_to_fy23": 7200.0,
        "sector_label": "Banking — Private Sector",
        "promoter_pct": 0.0, "mkt_cap_cr": 35000.0,
        "directors": [
            {"din": "09308922", "name": "Prashant Kumar (inspired)", "desig": "MD & CEO", "appt": "2020-03-14", "share": 0},
        ],
        "charges": [
            {"holder": "RBI Consortium", "amount_cr": 15000.0, "created": "2020-03-15", "status": "Open"},
        ],
        "bureau_facilities": [
            {"lender": "SBI", "type": "Equity Infusion", "limit_cr": 10000.0, "outstanding_cr": 10000.0, "dpd": 0},
            {"lender": "LIC", "type": "Term Deposit", "limit_cr": 5000.0, "outstanding_cr": 5000.0, "dpd": 0},
        ],
        "news": [
            {"title": "Yashwant Bank NPA ratio improves to 2.1% — recovery gains", "source": "Moneycontrol", "dt": "2026-02-28", "sent": "positive"},
            {"title": "SEBI examining Yashwant Bank promoter transactions from 2019", "source": "ET BFSI", "dt": "2026-01-10", "sent": "negative"},
            {"title": "RBI extends monitoring period for Yashwant Bank — growth caps remain", "source": "Business Standard", "dt": "2026-03-08", "sent": "negative"},
        ],
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# RESPONSE GENERATORS — Build realistic API response bodies
# ═══════════════════════════════════════════════════════════════════════════════

def _uid():
    return str(uuid.uuid4())

def _mca_master(c):
    return {
        "api_version": "3.0",
        "source": "mca_v3",
        "timestamp": "2026-03-18T10:00:00Z",
        "status": "success",
        "data": {
            "cin": c["cin"],
            "company_name": c["name"].upper(),
            "company_status": "Active",
            "roc_code": f"ROC-{c['state'][:6]}".replace(" ", ""),
            "registration_number": c["cin"][-6:],
            "company_category": c["category"],
            "company_sub_category": "Non-govt company",
            "class_of_company": c["class"],
            "authorized_capital_inr": c["auth_cap"],
            "paid_up_capital_inr": c["paid_cap"],
            "date_of_incorporation": c["incorp"],
            "registered_address": c["office"],
            "email": c["email"],
            "listing_status": c["listing"],
            "listed_stock_exchange": c.get("exchange", "N/A"),
            "last_agm_date": "2025-09-15",
            "last_balance_sheet_date": "2025-03-31",
            "nic_code": c["nic"],
            "activity_description": c["nic_desc"],
            "number_of_members": 35000 if c["listing"] == "Listed" else 50,
            "whether_under_CIRP": "No",
            "compliance_status": {
                "annual_return_filed": True,
                "balance_sheet_filed": True,
                "last_filing_date": "2025-10-30",
            },
        },
    }


def _mca_directors(c):
    dirs = []
    for d in c.get("directors", []):
        dirs.append({
            "din": d["din"],
            "name": d["name"],
            "designation": d["desig"],
            "date_of_appointment": d["appt"],
            "date_of_cessation": None,
            "shareholding_pct": d.get("share", 0),
            "nationality": "Indian",
            "status": "Active",
        })
    return {
        "api_version": "3.0",
        "source": "mca_v3",
        "timestamp": "2026-03-18T10:00:00Z",
        "status": "success",
        "data": {"cin": c["cin"], "company_name": c["name"], "directors": dirs},
    }


def _mca_charges(c):
    charges = []
    for i, ch in enumerate(c.get("charges", []), 1):
        charges.append({
            "charge_id": f"CHG-{c['cin'][-6:]}-{i:03d}",
            "charge_holder": ch["holder"],
            "amount_inr": ch["amount_cr"] * 1e7,
            "date_of_creation": ch["created"],
            "date_of_modification": None,
            "status": ch["status"],
            "assets_under_charge": "Movable and immovable properties",
        })
    return {
        "api_version": "3.0",
        "source": "mca_v3",
        "timestamp": "2026-03-18T10:00:00Z",
        "status": "success",
        "data": {"cin": c["cin"], "active_charges": len(charges), "charges": charges},
    }


def _bureau_report(c):
    return {
        "api_version": "2.0",
        "source": "cibil_commercial",
        "report_date": "2026-03-18",
        "status": "success",
        "data": {
            "pan": c["pan"],
            "entity_name": c["name"],
            "commercial_score": c["bureau_score"],
            "score_band": c["score_band"],
            "total_exposure_cr": c["exposure_cr"],
            "total_active_lenders": c["lenders"],
            "max_dpd_last_12m": c["max_dpd_12m"],
            "current_dpd_status": c["dpd_status"],
            "wilful_defaulter": False,
            "suit_filed_status": "No Suit Filed" if c["max_dpd_12m"] < 90 else "Suit Filed",
            "crilc_sma_status": "SMA-0" if c["max_dpd_12m"] == 0 else f"SMA-{min(c['max_dpd_12m'] // 30 + 1, 2)}",
            "enquiries_last_6m": max(1, c["lenders"] // 3),
            "credit_facilities": [
                {
                    "lender": f["lender"],
                    "facility_type": f["type"],
                    "sanction_limit_cr": f["limit_cr"],
                    "outstanding_cr": f["outstanding_cr"],
                    "overdue_cr": round(f["outstanding_cr"] * 0.01, 2) if f["dpd"] > 0 else 0,
                    "dpd_days": f["dpd"],
                    "classification": "Standard" if f["dpd"] < 30 else "SMA-1" if f["dpd"] < 60 else "SMA-2",
                    "account_status": "Regular",
                    "sanction_date": "2021-04-01",
                    "last_payment_date": "2026-03-01",
                }
                for f in c.get("bureau_facilities", [])
            ],
        },
    }


def _gst_turnover(c):
    return {
        "api_version": "1.0",
        "source": "gstn",
        "timestamp": "2026-03-18T10:00:00Z",
        "status": "success",
        "data": {
            "pan": c["pan"],
            "gstin": c["gstin"],
            "trade_name": c["name"].upper(),
            "legal_name": c["name"].upper(),
            "registration_date": "2017-07-01",
            "gstin_status": "Active",
            "business_type": "Regular",
            "constitution_of_business": f"{c['class']} Limited Company",
            "principal_place_of_business": f"{c['state']}, India",
            "aggregate_turnover": {
                "FY2024": {"turnover_cr": c["gst_to_fy24"], "filing_status": "Filed"},
                "FY2023": {"turnover_cr": c["gst_to_fy23"], "filing_status": "Filed"},
            },
            "filing_history": [
                {"return_type": "GSTR-3B", "period": "Feb-2026", "status": "Filed", "date_of_filing": "2026-03-15"},
                {"return_type": "GSTR-1", "period": "Feb-2026", "status": "Filed", "date_of_filing": "2026-03-11"},
                {"return_type": "GSTR-3B", "period": "Jan-2026", "status": "Filed", "date_of_filing": "2026-02-18"},
                {"return_type": "GSTR-1", "period": "Jan-2026", "status": "Filed", "date_of_filing": "2026-02-11"},
            ],
            "compliance_rating": "Good" if c["gst_to_fy24"] else "Not Rated",
        },
    }


def _rating(c):
    if not c.get("rating_agency"):
        return {
            "api_version": "1.0", "source": "rating_agency",
            "status": "not_rated",
            "data": {"entity_id": c["eid"], "entity_name": c["name"], "status": "Not Rated"},
        }
    return {
        "api_version": "1.0",
        "source": "rating_agency",
        "timestamp": "2026-03-18T10:00:00Z",
        "status": "success",
        "data": {
            "entity_id": c["eid"],
            "entity_name": c["name"],
            "agency": c["rating_agency"],
            "long_term_rating": c["lt_rating"],
            "short_term_rating": c["st_rating"],
            "outlook": c["outlook"],
            "last_action": c["last_action"],
            "action_date": "2025-11-15",
            "instruments_rated": [
                {"type": "Long Term Bank Facilities", "amount_cr": c["exposure_cr"] * 0.6, "rating": f"{c['rating_agency']} {c['lt_rating']}/{c['outlook']}"},
                {"type": "Short Term Bank Facilities", "amount_cr": c["exposure_cr"] * 0.2, "rating": f"{c['rating_agency']} {c['st_rating']}"},
            ],
            "key_rating_drivers": {
                "strengths": [f"Established position in {c['sector_label']}", "Adequate financial profile"],
                "weaknesses": ["Exposure to cyclical demand patterns"] if c.get("outlook") != "Negative"
                             else ["Stretched liquidity", "Declining profitability", "High leverage"],
            },
            "rating_history": [
                {"date": "2025-11-15", "action": c["last_action"], "lt_rating": c["lt_rating"], "outlook": c["outlook"]},
                {"date": "2024-11-10", "action": "Reaffirmed", "lt_rating": c["lt_rating"], "outlook": "Stable"},
            ],
        },
    }


def _market_sentiment(c):
    articles = []
    for n in c.get("news", []):
        articles.append({
            "title": n["title"],
            "source": n["source"],
            "published_date": n["dt"],
            "sentiment": n["sent"],
            "relevance_score": 0.92,
        })
    return {
        "api_version": "1.0",
        "source": "market_intelligence",
        "timestamp": "2026-03-18T10:00:00Z",
        "status": "success",
        "data": {
            "entity_id": c["eid"],
            "entity_name": c["name"],
            "overall_sentiment": c["sentiment"],
            "sentiment_score": c["sent_score"],
            "analysis_period": "90_days",
            "total_articles": len(articles) + 5,
            "articles": articles,
            "themes": ["capacity_expansion", "financial_performance"] if c["sentiment"] == "positive"
                      else ["regulatory_concern", "debt_pressure"] if c["sentiment"] == "negative"
                      else ["steady_operations"],
            "esg_flags": ["regulatory_scrutiny"] if c["rep_risk"] == "high" else [],
            "litigation_count": 5 if c["rep_risk"] == "high" else 1,
            "reputation_risk_score": c["rep_risk"],
        },
    }


def _exchange_filing(c):
    if c["listing"] != "Listed" or not c.get("isin"):
        return None
    return {
        "api_version": "1.0",
        "source": "bse_nse",
        "timestamp": "2026-03-18T10:00:00Z",
        "status": "success",
        "data": {
            "isin": c["isin"],
            "company_name": c["name"],
            "nse_symbol": c.get("nse_sym"),
            "bse_code": c.get("bse_code"),
            "market_cap_cr": c.get("mkt_cap_cr", 0),
            "promoter_holding_pct": c["promoter_pct"],
            "institutional_holding_pct": round(100 - c["promoter_pct"] - 18.5, 1),
            "public_holding_pct": 18.5,
            "recent_filings": [
                {"type": "Quarterly Results", "date": "2026-02-14", "description": "Q3 FY2026 Financial Results"},
                {"type": "Board Meeting", "date": "2026-01-20", "description": "Meeting to consider quarterly results"},
                {"type": "Shareholding Pattern", "date": "2025-12-31", "description": "Q3 FY2026 Shareholding"},
            ],
            "corporate_actions": [
                {"type": "Dividend", "record_date": "2025-07-15", "amount_per_share": 5.0},
            ],
        },
    }


def _dms_documents(c):
    """Document management system — what's available, what's missing."""
    docs = [
        {"doc_id": f"DOC-{c['eid']}-001", "type": "mca_auto_fetch", "filename": f"{c['eid']}_mca_master.json",
         "upload_date": "2026-03-18", "source": "auto_scrape", "status": "available", "ocr_status": "n/a"},
        {"doc_id": f"DOC-{c['eid']}-002", "type": "bureau_report", "filename": f"{c['eid']}_cibil_report.json",
         "upload_date": "2026-03-18", "source": "api_fetch", "status": "available", "ocr_status": "n/a"},
        {"doc_id": f"DOC-{c['eid']}-003", "type": "gst_returns", "filename": f"{c['eid']}_gst_returns.json",
         "upload_date": "2026-03-18", "source": "api_fetch", "status": "available", "ocr_status": "n/a"},
    ]
    missing = []
    # Audited financials — these need to be uploaded by RM
    if c["listing"] == "Listed":
        docs.append({"doc_id": f"DOC-{c['eid']}-010", "type": "audited_financial_fy2024",
                      "filename": f"{c['eid']}_annual_report_fy2024.pdf",
                      "upload_date": "2025-08-15", "source": "web_scrape_roc",
                      "status": "available", "ocr_status": "completed"})
        docs.append({"doc_id": f"DOC-{c['eid']}-011", "type": "audited_financial_fy2023",
                      "filename": f"{c['eid']}_annual_report_fy2023.pdf",
                      "upload_date": "2024-09-01", "source": "web_scrape_roc",
                      "status": "available", "ocr_status": "completed"})
    else:
        missing.extend(["audited_financial_fy2024", "audited_financial_fy2023"])

    missing.append("provisional_fy2025")
    missing.append("board_resolution")
    missing.append("cma_projection")

    return {
        "api_version": "1.0",
        "source": "document_management",
        "status": "success",
        "data": {
            "entity_id": c["eid"],
            "entity_name": c["name"],
            "available_documents": docs,
            "missing_documents": missing,
            "total_available": len(docs),
            "total_required": len(docs) + len(missing),
            "completion_pct": round(len(docs) / (len(docs) + len(missing)) * 100, 1),
            "rm_action_required": len(missing) > 0,
            "last_updated": "2026-03-18T10:00:00Z",
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# POSTMAN COLLECTION BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

def make_example(name, method, path_parts, response_body, status_code=200, status_text="OK"):
    """Build a Postman saved example (response)."""
    raw_url = "{{mockUrl}}/" + "/".join(path_parts)
    return {
        "id": _uid(),
        "name": name,
        "originalRequest": {
            "method": method,
            "header": [{"key": "Content-Type", "value": "application/json"}],
            "url": {
                "raw": raw_url,
                "host": ["{{mockUrl}}"],
                "path": path_parts,
            },
        },
        "status": status_text,
        "code": status_code,
        "_postman_previewlanguage": "json",
        "header": [
            {"key": "Content-Type", "value": "application/json"},
            {"key": "X-Mock-Source", "value": "CAM-Platform-Mock"},
        ],
        "body": json.dumps(response_body, indent=2),
    }


def make_request(name, method, path_template, path_variable_key, examples):
    """Build a Postman request item with multiple response examples."""
    raw = "{{mockUrl}}/" + path_template
    return {
        "id": _uid(),
        "name": name,
        "request": {
            "method": method,
            "header": [{"key": "Content-Type", "value": "application/json"}],
            "url": {
                "raw": raw,
                "host": ["{{mockUrl}}"],
                "path": path_template.split("/"),
                "variable": [{"key": path_variable_key, "value": "", "description": f"Lookup key ({path_variable_key})"}] if path_variable_key else [],
            },
        },
        "response": examples,
    }


def make_folder(name, description, items):
    return {
        "id": _uid(),
        "name": name,
        "description": description,
        "item": items,
    }


def build_collection():
    """Build the complete Postman collection."""

    # ── MCA Company Master ──
    mca_master_examples = []
    for c in COMPANIES:
        mca_master_examples.append(make_example(
            f"{c['eid']} — {c['name']}",
            "GET", ["v3", "mca", "company", c["cin"]],
            _mca_master(c),
        ))
    mca_master_examples.append(make_example(
        "CIN Not Found", "GET", ["v3", "mca", "company", "INVALID_CIN"],
        {"api_version": "3.0", "source": "mca_v3", "status": "not_found", "data": {}}, 404, "Not Found",
    ))

    # ── MCA Directors ──
    mca_dir_examples = []
    for c in COMPANIES:
        mca_dir_examples.append(make_example(
            f"{c['eid']} — Directors",
            "GET", ["v3", "mca", "directors", c["cin"]],
            _mca_directors(c),
        ))

    # ── MCA Charges ──
    mca_charges_examples = []
    for c in COMPANIES:
        mca_charges_examples.append(make_example(
            f"{c['eid']} — Charges",
            "GET", ["v3", "mca", "charges", c["cin"]],
            _mca_charges(c),
        ))

    mca_folder = make_folder(
        "🏛️ MCA — Ministry of Corporate Affairs",
        "Simulates MCA V3 APIs — Company Master, Directors, Charges Register.\nLookup by CIN (Corporate Identification Number).",
        [
            make_request("Company Master", "GET", "v3/mca/company/:cin", "cin", mca_master_examples),
            make_request("Directors & KMPs", "GET", "v3/mca/directors/:cin", "cin", mca_dir_examples),
            make_request("Charges Register", "GET", "v3/mca/charges/:cin", "cin", mca_charges_examples),
        ],
    )

    # ── Bureau ──
    bureau_examples = []
    for c in COMPANIES:
        bureau_examples.append(make_example(
            f"{c['eid']} — Bureau Report",
            "GET", ["v2", "bureau", "commercial", c["pan"]],
            _bureau_report(c),
        ))

    bureau_folder = make_folder(
        "📊 Commercial Bureau (CIBIL)",
        "Simulates CIBIL/Experian commercial credit bureau API.\nLookup by PAN.",
        [make_request("Commercial Credit Report", "GET", "v2/bureau/commercial/:pan", "pan", bureau_examples)],
    )

    # ── GST ──
    gst_examples = []
    for c in COMPANIES:
        gst_examples.append(make_example(
            f"{c['eid']} — GST Turnover",
            "GET", ["v1", "gstn", "turnover", c["pan"]],
            _gst_turnover(c),
        ))

    gst_folder = make_folder(
        "🧾 GSTN — GST Network",
        "Simulates GSTN API — registration details, filing history, aggregate turnover.\nLookup by PAN or GSTIN.",
        [make_request("GST Registration & Turnover", "GET", "v1/gstn/turnover/:pan", "pan", gst_examples)],
    )

    # ── Rating ──
    rating_examples = []
    for c in COMPANIES:
        rating_examples.append(make_example(
            f"{c['eid']} — Rating ({c['lt_rating']})",
            "GET", ["v1", "rating", c["eid"]],
            _rating(c),
        ))

    rating_folder = make_folder(
        "⭐ Credit Rating Agencies",
        "Simulates CRISIL/ICRA/CARE rating agency APIs.\nLookup by entity_id.",
        [make_request("Latest Rating Action", "GET", "v1/rating/:entity_id", "entity_id", rating_examples)],
    )

    # ── Market / News ──
    market_examples = []
    for c in COMPANIES:
        market_examples.append(make_example(
            f"{c['eid']} — {c['sentiment'].title()} Sentiment",
            "GET", ["v1", "market", "sentiment", c["eid"]],
            _market_sentiment(c),
        ))

    market_folder = make_folder(
        "📰 Market Intelligence & News",
        "Simulates market intelligence API — news sentiment, ESG flags, litigation.\nLookup by entity_id.",
        [make_request("News & Sentiment Analysis", "GET", "v1/market/sentiment/:entity_id", "entity_id", market_examples)],
    )

    # ── Exchange Filings ──
    exchange_examples = []
    for c in COMPANIES:
        ef = _exchange_filing(c)
        if ef:
            exchange_examples.append(make_example(
                f"{c['eid']} — Exchange Filing",
                "GET", ["v1", "exchange", "filings", c["isin"]],
                ef,
            ))

    exchange_folder = make_folder(
        "📈 Exchange Filings (BSE/NSE)",
        "Simulates BSE/NSE corporate filing APIs — shareholding, announcements.\nLookup by ISIN. Listed companies only.",
        [make_request("Corporate Filings", "GET", "v1/exchange/filings/:isin", "isin", exchange_examples)],
    )

    # ── Document Management ──
    dms_examples = []
    for c in COMPANIES:
        dms_examples.append(make_example(
            f"{c['eid']} — Documents",
            "GET", ["v1", "dms", "documents", c["eid"]],
            _dms_documents(c),
        ))

    dms_folder = make_folder(
        "📁 Document Management Store",
        "Internal document management — lists available & missing documents.\n"
        "Shows what was auto-fetched vs what RM needs to upload (audited financials, provisionals, board resolutions).\n"
        "Lookup by entity_id.",
        [
            make_request("List Documents", "GET", "v1/dms/documents/:entity_id", "entity_id", dms_examples),
            make_request("Upload Document", "POST", "v1/dms/upload", None, [
                make_example(
                    "Upload Financial Statement",
                    "POST", ["v1", "dms", "upload"],
                    {"status": "accepted", "doc_id": "DOC-NEW-001",
                     "message": "Document queued for OCR processing", "ocr_estimated_seconds": 30},
                    202, "Accepted",
                ),
            ]),
        ],
    )

    # ── Onboarding Flow ──
    # A composite request that demonstrates the full RM workflow
    onboard_examples = []
    for c in [COMPANIES[4], COMPANIES[6], COMPANIES[10]]:  # TSTL, INFY, DLFR — good, great, stressed
        onboard_examples.append(make_example(
            f"{c['eid']} — CIN Lookup Result",
            "POST", ["v1", "onboard", "cin-lookup"],
            {
                "status": "found",
                "cin": c["cin"],
                "entity_id": c["eid"],
                "company_name": c["name"],
                "data_fetched": {
                    "mca_company_master": "success",
                    "mca_directors": "success",
                    "mca_charges": "success",
                    "bureau_report": "success",
                    "gst_turnover": "success",
                    "credit_rating": "success" if c.get("rating_agency") else "not_rated",
                    "market_sentiment": "success",
                    "exchange_filings": "success" if c["listing"] == "Listed" else "n/a",
                },
                "documents_available": 5 if c["listing"] == "Listed" else 3,
                "documents_missing": ["provisional_fy2025", "board_resolution", "cma_projection"],
                "rm_action_required": True,
                "message": f"Company {c['name']} identified. Auto-fetched public data from MCA, Bureau, GST, Rating, Market. "
                           f"RM needs to upload: Provisional FY2025 financials, Board Resolution, CMA Projection.",
            },
        ))

    onboard_folder = make_folder(
        "🚀 RM Onboarding Workflow",
        "Complete RM workflow:\n"
        "1. RM enters CIN → System auto-fetches all public data (MCA, Bureau, GST, Rating, News)\n"
        "2. System shows RM what data was found and what's missing\n"
        "3. RM uploads missing documents (audited financials, provisionals, board resolution)\n"
        "4. System runs OCR on uploaded PDFs → extracts financial data\n"
        "5. Pipeline runs with complete data → generates CAM\n\n"
        "The CIN-Lookup endpoint triggers all external API calls and returns a summary.",
        [
            make_request("CIN Lookup (Start Onboarding)", "POST", "v1/onboard/cin-lookup", None, onboard_examples),
        ],
    )

    # ── Assemble collection ──
    collection = {
        "info": {
            "_postman_id": _uid(),
            "name": "CAM Platform — External Data Source APIs",
            "description": (
                "Mock server for all external data sources consumed by the CAM Intelligence Platform.\n\n"
                "**Data Sources Covered:**\n"
                "- 🏛️ MCA (Ministry of Corporate Affairs) — Company Master, Directors, Charges\n"
                "- 📊 CIBIL Commercial Bureau — Credit Report\n"
                "- 🧾 GSTN — GST Registration & Turnover\n"
                "- ⭐ Credit Rating (CRISIL/ICRA/CARE)\n"
                "- 📰 Market Intelligence & News Sentiment\n"
                "- 📈 BSE/NSE Exchange Filings\n"
                "- 📁 Document Management Store\n\n"
                "**Coverage:** 16 companies (4 synthetic + 12 real-inspired)\n\n"
                "**How to use:**\n"
                "1. Import this collection into Postman\n"
                "2. Create a Mock Server from this collection\n"
                "3. Copy the Mock Server URL\n"
                "4. Set `CAM_MOCK_URL` environment variable to the URL\n"
                "5. The CAM app will call the mock server for all external data\n\n"
                "**To modify data:** Open any request → Examples tab → Edit the response JSON → Save.\n"
                "The mock server reflects changes immediately."
            ),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": [
            onboard_folder,
            mca_folder,
            bureau_folder,
            gst_folder,
            rating_folder,
            market_folder,
            exchange_folder,
            dms_folder,
        ],
        "variable": [
            {"key": "mockUrl", "value": "{{mockServerUrl}}", "type": "string"},
        ],
    }

    return collection


def build_environment():
    """Build Postman environment with all company identifiers."""
    values = [
        {"key": "mockServerUrl", "value": "https://your-mock-server-id.mock.pstmn.io", "enabled": True, "type": "default"},
        {"key": "localAppUrl", "value": "http://localhost:8001", "enabled": True, "type": "default"},
    ]
    for c in COMPANIES:
        values.append({"key": f"cin_{c['eid']}", "value": c["cin"], "enabled": True, "type": "default"})
        values.append({"key": f"pan_{c['eid']}", "value": c["pan"], "enabled": True, "type": "default"})
        values.append({"key": f"gstin_{c['eid']}", "value": c["gstin"], "enabled": True, "type": "default"})
        if c.get("isin"):
            values.append({"key": f"isin_{c['eid']}", "value": c["isin"], "enabled": True, "type": "default"})

    return {
        "id": str(uuid.uuid4()),
        "name": "CAM External Data — Company Identifiers",
        "values": values,
        "_postman_variable_scope": "environment",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    out_dir = Path(__file__).parent

    # Generate collection
    collection = build_collection()
    col_path = out_dir / "CAM_ExternalData_MockServer.postman_collection.json"
    col_path.write_text(json.dumps(collection, indent=2), encoding="utf-8")
    print(f"✅ Collection: {col_path}  ({col_path.stat().st_size / 1024:.0f} KB)")

    # Count examples
    total_examples = 0
    for folder in collection["item"]:
        for req in folder.get("item", []):
            total_examples += len(req.get("response", []))
    print(f"   {len(collection['item'])} folders, {total_examples} mock responses")

    # Generate environment
    env = build_environment()
    env_path = out_dir / "CAM_ExternalData.postman_environment.json"
    env_path.write_text(json.dumps(env, indent=2), encoding="utf-8")
    print(f"✅ Environment: {env_path}  ({env_path.stat().st_size / 1024:.0f} KB)")

    # Print company summary
    print(f"\n📋 Companies covered: {len(COMPANIES)}")
    for c in COMPANIES:
        listed = "📈" if c["listing"] == "Listed" else "🔒"
        rating = c["lt_rating"] if c.get("lt_rating") != "NR" else "—"
        print(f"   {listed} {c['eid']}  {c['name']:<40s}  CIN={c['cin']}  Rating={rating}")

    print("\n🚀 Next steps:")
    print("   1. Import collection into Postman")
    print("   2. Create Mock Server from collection (Postman → ... → Mock Server)")
    print("   3. Copy Mock Server URL → paste into config/external_apis.yaml")
    print("   4. Set CAM_MOCK_MODE=http (environment variable)")
    print("   5. Start app: python -m uvicorn main:app --port 8001")
