"""
Document Downloader Engine
===========================
Web scraping engine that downloads real financial data from public sources
(BSE/NSE APIs, company websites) and generates proper financial documents
(PDFs, Excel) for CAM processing.

Flow:
  1. Try live API fetch (NSE quote, BSE financials)
  2. Fallback to pre-verified real data (from public annual reports)
  3. Generate audited financial PDFs, annual report PDFs, provisional Excel
  4. Store in storage/documents/{entity_id}/
  5. Existing extraction pipeline processes the documents

Supported companies: hardcoded real-data packs for Infosys and Apollo,
plus registry-derived synthetic packs for the listed real-company set.
"""

import json
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

import httpx
import openpyxl
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak,
    HRFlowable,
)
from src.core.runtime_paths import DOCUMENTS_ROOT
from src.services.document_operations import document_operations
from src.data.company_catalog import catalog_company_ids

logger = logging.getLogger(__name__)


WEB_COMPANY_ALIASES: dict[str, dict[str, Any]] = {
    "TSTL001": {
        "actual_company_name": "Tata Steel Limited",
        "wikipedia_title": "Tata Steel",
        "official_url": "https://www.tatasteel.com/",
        "bse_code": "500470",
        "auditor": "Walker Chandiok & Co LLP",
        "narrative": {
            "chairman_message": "Tata Steel remained focused on portfolio quality, downstream value addition, and balance-sheet discipline while navigating steel price cyclicality.",
            "mda_summary": "The business profile is supported by integrated steel operations, captive raw-material linkages, and a diversified customer mix across automotive, construction, and engineering segments.",
            "risk_factors": ["Steel price cyclicality", "Raw material and energy cost volatility", "Large project execution and deleveraging discipline"],
            "request_focus": "working capital support for steel operations and downstream product expansion",
        },
    },
    "REIL001": {
        "actual_company_name": "Reliance Industries Limited",
        "wikipedia_title": "Reliance Industries",
        "official_url": "https://www.ril.com/",
        "bse_code": "500325",
        "auditor": "DTS & Associates LLP",
        "narrative": {
            "chairman_message": "Reliance Industries continued to blend cashflow strength from its energy franchise with strategic investments across consumer, digital, and new-energy platforms.",
            "mda_summary": "The reference profile reflects a conglomerate with scale advantages, diversified cash-flow streams, and sustained capex intensity funded by a large balance sheet.",
            "risk_factors": ["Commodity-cycle exposure", "Execution risk on new-energy capex", "Regulatory and competitive intensity across consumer businesses"],
            "request_focus": "term funding for integrated manufacturing and energy transition capex",
        },
    },
    "INFY001": {
        "actual_company_name": "Infosys Limited",
        "wikipedia_title": "Infosys",
        "official_url": "https://www.infosys.com/",
    },
    "ADPT001": {
        "actual_company_name": "Adani Ports and Special Economic Zone Limited",
        "wikipedia_title": "Adani Ports & SEZ",
        "official_url": "https://www.adaniports.com/",
        "bse_code": "532921",
        "auditor": "Shah Dhandharia & Co LLP",
        "narrative": {
            "chairman_message": "Adani Ports remained focused on cargo diversification, logistics integration, and disciplined capacity creation across gateway and hinterland assets.",
            "mda_summary": "The operating model is anchored by port concessions, logistics connectivity, and scale benefits from cargo aggregation across containers, dry bulk, and liquid segments.",
            "risk_factors": ["Leverage linked to expansion cycle", "Regulatory scrutiny and concession compliance", "Trade-volume sensitivity"],
            "request_focus": "project and working-capital support for port-led logistics expansion",
        },
    },
    "BJFN001": {
        "actual_company_name": "Bajaj Finance Limited",
        "wikipedia_title": "Bajaj Finance",
        "official_url": "https://www.bajajfinserv.in/",
        "bse_code": "500034",
        "auditor": "KKC & Associates LLP",
        "narrative": {
            "chairman_message": "Bajaj Finance sustained portfolio growth with continued focus on asset quality, distribution productivity, and calibrated funding diversification.",
            "mda_summary": "The borrower profile reflects a large diversified NBFC with strong origination capabilities across consumer, SME, and commercial lending products.",
            "risk_factors": ["Regulatory tightening in unsecured lending", "Credit-cost normalization risk", "Funding-spread sensitivity"],
            "request_focus": "funding support for on-lending growth across granular retail and SME portfolios",
        },
    },
    "CIPL001": {
        "actual_company_name": "Cipla Limited",
        "wikipedia_title": "Cipla",
        "official_url": "https://www.cipla.com/",
        "bse_code": "500087",
        "auditor": "SRBC & Co LLP",
        "narrative": {
            "chairman_message": "Cipla continued to balance domestic branded growth with export market expansion and a measured specialty pipeline build-out.",
            "mda_summary": "The operating profile benefits from a diversified mix across chronic therapies, respiratory products, generics exports, and institutional markets.",
            "risk_factors": ["USFDA and global regulatory compliance", "Price erosion in export markets", "Working-capital intensity in pharma distribution"],
            "request_focus": "working-capital and capex support for pharma manufacturing and product pipeline expansion",
        },
    },
    "DLFR001": {
        "actual_company_name": "DLF Limited",
        "wikipedia_title": "DLF Limited",
        "official_url": "https://www.dlf.in/",
        "bse_code": "532868",
        "auditor": "S R Batliboi & Associates LLP",
        "narrative": {
            "chairman_message": "DLF focused on monetization of a premium residential pipeline while preserving liquidity and reducing net leverage through disciplined execution.",
            "mda_summary": "The profile combines annuity cash flows from commercial assets with cyclical residential development cash flows in key urban markets.",
            "risk_factors": ["Real-estate cycle volatility", "Project execution and approvals", "Interest-rate sensitivity"],
            "request_focus": "construction finance and working capital for staged real-estate development",
        },
    },
    "JSWL001": {
        "actual_company_name": "JSW Steel Limited",
        "wikipedia_title": "JSW Steel",
        "official_url": "https://www.jsw.in/steel",
        "bse_code": "500228",
        "auditor": "Deloitte Haskins & Sells LLP",
        "narrative": {
            "chairman_message": "JSW Steel remained geared to domestic infrastructure demand and capacity addition while managing raw-material and steel-price volatility.",
            "mda_summary": "Its business mix is supported by steel manufacturing scale, downstream diversification, and strong demand linkages to automotive and infrastructure sectors.",
            "risk_factors": ["Commodity-cycle exposure", "Capex execution risk", "Imported coking coal cost swings"],
            "request_focus": "term and working-capital support for steel capacity expansion and raw-material funding",
        },
    },
    "MRUT001": {
        "actual_company_name": "Maruti Suzuki India Limited",
        "wikipedia_title": "Maruti Suzuki",
        "official_url": "https://www.marutisuzuki.com/",
        "bse_code": "532500",
        "auditor": "BSR & Co LLP",
        "narrative": {
            "chairman_message": "Maruti Suzuki sustained category leadership through product refresh, network depth, and a favorable mix shift toward utility vehicles and exports.",
            "mda_summary": "The reference profile reflects a strong passenger-vehicle franchise with broad dealer reach, healthy balance sheet metrics, and disciplined working-capital management.",
            "risk_factors": ["Auto-demand cyclicality", "Commodity input cost swings", "Supply-chain and semiconductor availability"],
            "request_focus": "working capital for vehicle production, inventory, and supplier ecosystem support",
        },
    },
    "TITN001": {
        "actual_company_name": "Titan Company Limited",
        "wikipedia_title": "Titan Company",
        "official_url": "https://www.titancompany.in/",
        "bse_code": "500114",
        "auditor": "Price Waterhouse Chartered Accountants LLP",
        "narrative": {
            "chairman_message": "Titan continued to deepen its premium retail positioning through brand trust, product innovation, and disciplined expansion across jewellery, watches, and wearables.",
            "mda_summary": "The business profile is led by jewellery retail with strong brand equity, omnichannel distribution, and efficient inventory and gold-procurement management.",
            "risk_factors": ["Gold price volatility", "Consumer demand sensitivity", "Inventory and working-capital management"],
            "request_focus": "working-capital funding for inventory and network expansion in lifestyle retail",
        },
    },
    "NTPC001": {
        "actual_company_name": "NTPC Limited",
        "wikipedia_title": "NTPC Limited",
        "official_url": "https://www.ntpc.co.in/",
        "bse_code": "532555",
        "auditor": "M Kumar Jain & Co",
        "narrative": {
            "chairman_message": "NTPC continued to balance stable regulated thermal cash flows with a scaled renewable build-out and transmission-linked growth initiatives.",
            "mda_summary": "The operating model benefits from long-term PPAs, sovereign linkage perception, and predictable cash flows, partly offset by a capex-heavy transition agenda.",
            "risk_factors": ["Execution risk on renewable capacity addition", "Receivable concentration with state discoms", "Fuel-cost and policy transitions"],
            "request_focus": "term funding for power generation and renewable energy capacity expansion",
        },
    },
    "YESB001": {
        "actual_company_name": "Yes Bank Limited",
        "wikipedia_title": "Yes Bank",
        "official_url": "https://www.yesbank.in/",
        "bse_code": "532648",
        "auditor": "M S K A & Associates",
        "narrative": {
            "chairman_message": "Yes Bank remained focused on liability franchise rebuild, governance normalization, and asset quality stabilization after a prolonged stress cycle.",
            "mda_summary": "The synthetic borrower profile reflects recovery-stage banking metrics with improving funding stability but persistent scrutiny on governance and stressed assets.",
            "risk_factors": ["Governance and reputation overhang", "Asset quality and recovery execution", "Deposit franchise competitiveness"],
            "request_focus": "liquidity and refinancing support against a stabilized but closely monitored banking profile",
        },
    },
    "DRRD001": {
        "actual_company_name": "Dr. Reddy's Laboratories Limited",
        "wikipedia_title": "Dr. Reddy's Laboratories",
        "official_url": "https://www.drreddys.com/",
        "bse_code": "500124",
        "auditor": "S R Batliboi & Associates LLP",
        "narrative": {
            "chairman_message": "Dr. Reddy's sustained a balanced growth profile across generics, APIs, and specialty products while maintaining emphasis on compliance and portfolio quality.",
            "mda_summary": "The operating profile benefits from diversified geographies, R&D-led product flow, and a mix of domestic branded formulations and export-led generics businesses.",
            "risk_factors": ["Regulatory inspections and remediation risk", "Price erosion in generics", "R&D monetization risk"],
            "request_focus": "working-capital and capex support for pharma research, manufacturing, and export growth",
        },
    },
    "IHCL001": {
        "actual_company_name": "The Indian Hotels Company Limited",
        "wikipedia_title": "Indian Hotels Company Limited",
        "official_url": "https://www.ihcltata.com/",
        "bse_code": "500850",
        "auditor": "Deloitte Haskins & Sells LLP",
        "narrative": {
            "chairman_message": "IHCL advanced its asset-light strategy while capitalizing on strong domestic travel, premium positioning, and improving hospitality sector demand dynamics.",
            "mda_summary": "The operating model is supported by a leading hotel brand, management contract expansion, and a favorable leisure, MICE, and corporate travel mix.",
            "risk_factors": ["Travel-demand cyclicality", "Operating-cost inflation", "Execution on managed-property expansion"],
            "request_focus": "working-capital and selective capex support for hospitality network expansion",
        },
    },
    "APOL001": {
        "actual_company_name": "Apollo Hospitals Enterprise Limited",
        "wikipedia_title": "Apollo Hospitals",
        "official_url": "https://www.apollohospitals.com/",
        "bse_code": "508869",
        "auditor": "S.R. Batliboi & Associates LLP",
    },
}

# ─── Pre-verified Real Financial Data ────────────────────────────────────────
# Source: Public annual reports and BSE/NSE filings
# These serve as reliable fallback when live APIs are unavailable

REAL_FINANCIAL_DATA: dict[str, dict] = {
    "INFY001": {
        "company_name": "Infosys Limited",
        "cin": "L85110KA1981PLC013115",
        "bse_code": "500209",
        "nse_symbol": "INFY",
        "isin": "INE009A01021",
        "sector": "IT Services — Consulting & Software",
        "auditor": "Deloitte Haskins & Sells LLP",
        "financials": {
            "FY2025": {
                "period": "April 2024 — March 2025",
                "revenue_from_operations": 162981.00,
                "other_income": 5276.00,
                "total_income": 168257.00,
                "employee_benefit_expense": 95432.00,
                "cost_of_materials": 0.00,
                "depreciation_amortisation": 5629.00,
                "finance_cost": 843.00,
                "other_expenses": 24978.00,
                "ebitda": 42375.00,
                "profit_before_tax": 35424.00,
                "tax_expense": 8190.00,
                "profit_after_tax": 27234.00,
                "total_assets": 140807.00,
                "total_equity": 89120.00,
                "total_debt": 5241.00,
                "current_assets": 62340.00,
                "current_liabilities": 44280.00,
                "non_current_assets": 78467.00,
                "cash_and_equivalents": 32415.00,
                "trade_receivables": 28630.00,
                "inventory": 0.00,
                "trade_payables": 8920.00,
                "total_income_note": "Includes software services, products, and platform revenue",
            },
            "FY2024": {
                "period": "April 2023 — March 2024",
                "revenue_from_operations": 153670.00,
                "other_income": 5718.00,
                "total_income": 159388.00,
                "employee_benefit_expense": 89764.00,
                "cost_of_materials": 0.00,
                "depreciation_amortisation": 5186.00,
                "finance_cost": 742.00,
                "other_expenses": 23742.00,
                "ebitda": 39954.00,
                "profit_before_tax": 33583.00,
                "tax_expense": 7350.00,
                "profit_after_tax": 26233.00,
                "total_assets": 133365.00,
                "total_equity": 84273.00,
                "total_debt": 4024.00,
                "current_assets": 58620.00,
                "current_liabilities": 41830.00,
                "non_current_assets": 74745.00,
                "cash_and_equivalents": 29870.00,
                "trade_receivables": 26540.00,
                "inventory": 0.00,
                "trade_payables": 8150.00,
                "total_income_note": "Revenue growth of 8.6% YoY driven by large deal wins",
            },
            "FY2023": {
                "period": "April 2022 — March 2023",
                "revenue_from_operations": 146767.00,
                "other_income": 5878.00,
                "total_income": 152645.00,
                "employee_benefit_expense": 86204.00,
                "cost_of_materials": 0.00,
                "depreciation_amortisation": 4713.00,
                "finance_cost": 621.00,
                "other_expenses": 23751.00,
                "ebitda": 37358.00,
                "profit_before_tax": 30753.00,
                "tax_expense": 6645.00,
                "profit_after_tax": 24108.00,
                "total_assets": 126455.00,
                "total_equity": 79012.00,
                "total_debt": 3841.00,
                "current_assets": 54970.00,
                "current_liabilities": 39720.00,
                "non_current_assets": 71485.00,
                "cash_and_equivalents": 27340.00,
                "trade_receivables": 25110.00,
                "inventory": 0.00,
                "trade_payables": 7640.00,
                "total_income_note": "20.7% revenue growth YoY; record large deal TCV of $9.8B",
            },
            "FY2022": {
                "period": "April 2021 — March 2022",
                "revenue_from_operations": 121641.00,
                "other_income": 4856.00,
                "total_income": 126497.00,
                "employee_benefit_expense": 71320.00,
                "cost_of_materials": 0.00,
                "depreciation_amortisation": 4176.00,
                "finance_cost": 535.00,
                "other_expenses": 19239.00,
                "ebitda": 31227.00,
                "profit_before_tax": 26434.00,
                "tax_expense": 4324.00,
                "profit_after_tax": 22110.00,
                "total_assets": 119832.00,
                "total_equity": 74385.00,
                "total_debt": 3524.00,
                "current_assets": 52410.00,
                "current_liabilities": 37645.00,
                "non_current_assets": 67422.00,
                "cash_and_equivalents": 25780.00,
                "trade_receivables": 23490.00,
                "inventory": 0.00,
                "trade_payables": 7120.00,
                "total_income_note": "Strong growth of 19.7% YoY driven by digital transformation demand",
            },
        },
        "annual_report_highlights": {
            "FY2024": {
                "chairman_message": "Infosys delivered a strong performance in FY2024 with consolidated revenue of ₹1,53,670 crore, growing 8.6% year-on-year. Our large deal wins of $17.7 billion TCV demonstrate the confidence clients place in us. Operating margin remained healthy at 26.0% despite the macro headwinds. We returned ₹34,000 crore to shareholders through dividends and buybacks.",
                "key_highlights": [
                    "Revenue: ₹1,53,670 Cr (8.6% YoY growth)",
                    "Operating Margin: 26.0%",
                    "Large Deal TCV: $17.7 Billion",
                    "Employees: 317,240",
                    "Client base: 1,800+ active clients",
                    "Cash & equivalents: ₹29,870 Cr",
                    "Dividend per share: ₹38 (FY2024)",
                    "Digital revenue: 62.3% of total revenue",
                ],
                "mda_summary": "The global IT services market continued its resilient trajectory despite macroeconomic uncertainties. Clients are increasingly investing in AI-led transformation, cloud migration, and digital operations. Infosys' Topaz AI platform saw strong adoption with 280+ enterprise deployments. Key verticals — Financial Services (31.2%), Retail (15.8%), Communication (12.5%), and Manufacturing (10.1%) — all delivered positive growth. Headcount optimization through AI-driven productivity improved utilization to 83.4%.",
                "risk_factors": [
                    "Currency fluctuation risk (73% revenue in USD)",
                    "Client concentration: Top 10 clients = 24.3% revenue",
                    "Talent attrition: 12.3% LTM (improved from 14.6%)",
                    "Geopolitical uncertainties affecting discretionary spending",
                    "Regulatory compliance across 56 countries",
                ],
            },
        },
    },
    "APOL001": {
        "company_name": "Apollo Hospitals Enterprise Limited",
        "cin": "L85110TN1979PLC008035",
        "bse_code": "508869",
        "nse_symbol": "APOLLOHOSP",
        "isin": "INE437A01024",
        "sector": "Healthcare — Hospitals & Health Services",
        "auditor": "S.R. Batliboi & Associates LLP (EY Network)",
        "financials": {
            "FY2025": {
                "period": "April 2024 — March 2025",
                "revenue_from_operations": 21245.00,
                "other_income": 412.00,
                "total_income": 21657.00,
                "employee_benefit_expense": 5842.00,
                "cost_of_materials": 5463.00,
                "depreciation_amortisation": 1124.00,
                "finance_cost": 578.00,
                "other_expenses": 5359.00,
                "ebitda": 3609.00,
                "profit_before_tax": 2319.00,
                "tax_expense": 727.00,
                "profit_after_tax": 1592.00,
                "total_assets": 24300.00,
                "total_equity": 10800.00,
                "total_debt": 5900.00,
                "current_assets": 6200.00,
                "current_liabilities": 6850.00,
                "non_current_assets": 18100.00,
                "cash_and_equivalents": 1420.00,
                "trade_receivables": 2310.00,
                "inventory": 680.00,
                "trade_payables": 2940.00,
                "total_income_note": "11.5% revenue growth driven by hospital and pharmacy segments",
            },
            "FY2024": {
                "period": "April 2023 — March 2024",
                "revenue_from_operations": 19059.00,
                "other_income": 378.00,
                "total_income": 19437.00,
                "employee_benefit_expense": 5245.00,
                "cost_of_materials": 4989.00,
                "depreciation_amortisation": 1018.00,
                "finance_cost": 524.00,
                "other_expenses": 4927.00,
                "ebitda": 2898.00,
                "profit_before_tax": 1734.00,
                "tax_expense": 351.00,
                "profit_after_tax": 1383.00,
                "total_assets": 22100.00,
                "total_equity": 9500.00,
                "total_debt": 5200.00,
                "current_assets": 5680.00,
                "current_liabilities": 6320.00,
                "non_current_assets": 16420.00,
                "cash_and_equivalents": 1180.00,
                "trade_receivables": 2050.00,
                "inventory": 620.00,
                "trade_payables": 2640.00,
                "total_income_note": "14.7% revenue growth; hospital ARPOB improvement to ₹54,200/day",
            },
            "FY2023": {
                "period": "April 2022 — March 2023",
                "revenue_from_operations": 16612.00,
                "other_income": 325.00,
                "total_income": 16937.00,
                "employee_benefit_expense": 4572.00,
                "cost_of_materials": 4395.00,
                "depreciation_amortisation": 923.00,
                "finance_cost": 478.00,
                "other_expenses": 4236.00,
                "ebitda": 2451.00,
                "profit_before_tax": 1375.00,
                "tax_expense": 231.00,
                "profit_after_tax": 1144.00,
                "total_assets": 19800.00,
                "total_equity": 8200.00,
                "total_debt": 4800.00,
                "current_assets": 5120.00,
                "current_liabilities": 5740.00,
                "non_current_assets": 14680.00,
                "cash_and_equivalents": 980.00,
                "trade_receivables": 1810.00,
                "inventory": 565.00,
                "trade_payables": 2350.00,
                "total_income_note": "12.7% revenue growth; occupancy recovered to 67% across network",
            },
            "FY2022": {
                "period": "April 2021 — March 2022",
                "revenue_from_operations": 14738.00,
                "other_income": 287.00,
                "total_income": 15025.00,
                "employee_benefit_expense": 4028.00,
                "cost_of_materials": 3952.00,
                "depreciation_amortisation": 842.00,
                "finance_cost": 435.00,
                "other_expenses": 3805.00,
                "ebitda": 1918.00,
                "profit_before_tax": 1078.00,
                "tax_expense": 162.00,
                "profit_after_tax": 916.00,
                "total_assets": 18500.00,
                "total_equity": 7200.00,
                "total_debt": 4500.00,
                "current_assets": 4680.00,
                "current_liabilities": 5210.00,
                "non_current_assets": 13820.00,
                "cash_and_equivalents": 850.00,
                "trade_receivables": 1620.00,
                "inventory": 510.00,
                "trade_payables": 2120.00,
                "total_income_note": "Recovery from COVID; pharmacy business crossed ₹5,000Cr revenue",
            },
        },
        "annual_report_highlights": {
            "FY2024": {
                "chairman_message": "Apollo Hospitals delivered record performance in FY2024 with consolidated revenue of ₹19,059 crore, reflecting robust 14.7% year-on-year growth. Our hospital segment maintained ARPOB growth trajectory reaching ₹54,200 per day. The Apollo Health & Lifestyle division expanded to 4,200+ pharmacies. Digital health platform Apollo 24|7 crossed 100 million registered users.",
                "key_highlights": [
                    "Revenue: ₹19,059 Cr (14.7% YoY growth)",
                    "EBITDA Margin: 15.2%",
                    "Hospital ARPOB: ₹54,200/day",
                    "Bed capacity: 10,119 across 73 hospitals",
                    "Pharmacy network: 4,200+ stores",
                    "Apollo 24|7: 100M+ users, 25M+ tele-consultations",
                    "International revenue: 18% of hospital revenue",
                    "New hospitals: Launched in Pune, Kolkata (Phase 2)",
                ],
                "mda_summary": "The Indian healthcare industry is projected to reach $372 billion by 2026. Apollo's multi-pronged strategy encompasses tertiary care hospitals, pharmacies, primary care clinics, and digital health. Hospital occupancy improved to 68% with case mix shifting towards complex procedures (cardiology, oncology, organ transplantation). Apollo HealthCo (24|7 + pharmacy) contributed 30% of consolidated revenue with improving unit economics.",
                "risk_factors": [
                    "Regulatory risk: NPPA drug price controls",
                    "High capex for new hospital commissioning",
                    "Doctor availability and talent retention",
                    "Insurance claim settlement delays",
                    "Geographic concentration in South India (52% revenue)",
                ],
            },
        },
    },
}


def _latest_year_key(financials: dict[str, dict]) -> str:
    fiscal_years = sorted(financials.keys(), reverse=True)
    return fiscal_years[0] if fiscal_years else "FY2025"


def _extract_canonical_items(financial_statement: Any) -> dict[str, Any]:
    if financial_statement is None:
        return {}
    if hasattr(financial_statement, "line_items"):
        return dict(financial_statement.line_items or {})
    if isinstance(financial_statement, dict):
        return dict(financial_statement)
    return {}


def _canonical_to_download_financials(financials: dict[str, Any]) -> dict[str, dict[str, float]]:
    mapped: dict[str, dict[str, float]] = {}
    for period, statement in financials.items():
        if not str(period).startswith("FY"):
            continue
        items = _extract_canonical_items(statement)
        current_assets = float(items.get("current_assets", 0) or 0)
        total_assets = float(items.get("total_assets", 0) or 0)
        non_current_assets = float(items.get("non_current_assets", 0) or 0)
        if not non_current_assets and total_assets:
            non_current_assets = max(total_assets - current_assets, 0)
        revenue = float(items.get("revenue_from_operations", items.get("revenue_operating", 0)) or 0)
        other_income = float(items.get("other_income", 0) or 0)
        total_income = float(items.get("total_income", 0) or (revenue + other_income))
        mapped[period] = {
            "period": period,
            "revenue_from_operations": revenue,
            "other_income": other_income,
            "total_income": total_income,
            "employee_benefit_expense": float(items.get("employee_benefit_expense", items.get("employee_cost", 0)) or 0),
            "cost_of_materials": float(items.get("cost_of_materials", items.get("raw_material_cost", 0)) or 0),
            "depreciation_amortisation": float(items.get("depreciation_amortisation", items.get("depreciation", 0)) or 0),
            "finance_cost": float(items.get("finance_cost", 0) or 0),
            "other_expenses": float(items.get("other_expenses", 0) or 0),
            "ebitda": float(items.get("ebitda", 0) or 0),
            "profit_before_tax": float(items.get("profit_before_tax", items.get("pbt", 0)) or 0),
            "tax_expense": float(items.get("tax_expense", 0) or 0),
            "profit_after_tax": float(items.get("profit_after_tax", items.get("pat", 0)) or 0),
            "total_assets": total_assets,
            "total_equity": float(items.get("total_equity", 0) or 0),
            "total_debt": float(items.get("total_debt", 0) or 0),
            "current_assets": current_assets,
            "current_liabilities": float(items.get("current_liabilities", 0) or 0),
            "non_current_assets": non_current_assets,
            "cash_and_equivalents": float(items.get("cash_and_equivalents", items.get("cash_equivalents", 0)) or 0),
            "trade_receivables": float(items.get("trade_receivables", 0) or 0),
            "inventory": float(items.get("inventory", 0) or 0),
            "trade_payables": float(items.get("trade_payables", 0) or 0),
            "total_income_note": "Synthetic financial pack derived from canonical company dataset and aligned to public-company profile.",
        }
    return mapped


def _guess_auditor(company_name: str, sector: str) -> str:
    sector_key = (sector or "").lower()
    if "bank" in sector_key or "nbfc" in sector_key:
        return f"M/s S R Batliboi & Co. LLP, statutory auditors for {company_name}"
    if "pharma" in sector_key or "health" in sector_key:
        return f"M/s Deloitte Haskins & Sells LLP, statutory auditors for {company_name}"
    return f"M/s B S R & Associates LLP, statutory auditors for {company_name}"


def _format_crore(val: float) -> str:
    return f"₹{val:,.0f} Cr"


def _build_generated_highlights(company_record: dict, financials: dict[str, dict]) -> dict[str, dict[str, Any]]:
    borrower = company_record.get("borrower")
    profile_override = WEB_COMPANY_ALIASES.get(getattr(borrower, "entity_id", ""), {}).get("narrative", {})
    market_signals = company_record.get("market_signals") or []
    latest_year = _latest_year_key(financials)
    latest = financials.get(latest_year, {})
    revenue = float(latest.get("revenue_from_operations", 0) or 0)
    ebitda = float(latest.get("ebitda", 0) or 0)
    pat = float(latest.get("profit_after_tax", 0) or 0)
    total_debt = float(latest.get("total_debt", 0) or 0)
    total_equity = float(latest.get("total_equity", 0) or 0)
    ebitda_margin = (ebitda / revenue * 100) if revenue else 0
    debt_equity = (total_debt / total_equity) if total_equity else 0
    positives = [s for s in market_signals if getattr(s, "sentiment", "").lower() == "positive"]
    negatives = [s for s in market_signals if getattr(s, "sentiment", "").lower() == "negative"]
    key_highlights = [
        f"Revenue from operations: {_format_crore(revenue)}",
        f"EBITDA: {_format_crore(ebitda)} with margin of {ebitda_margin:.1f}%",
        f"Profit after tax: {_format_crore(pat)}",
        f"Debt / Equity: {debt_equity:.2f}x",
    ]
    if borrower and getattr(borrower, "credit_rating", None):
        key_highlights.append(f"External rating profile: {borrower.credit_rating}")
    if borrower and getattr(borrower, "employee_count", None):
        key_highlights.append(f"Employee base: {borrower.employee_count:,}")

    risk_factors = []
    for signal in negatives[:4]:
        risk_factors.append(getattr(signal, "headline", "Market volatility and sector execution risk"))
    if not risk_factors:
        risk_factors = profile_override.get("risk_factors") or [
            "Execution risk on growth capex and sector demand cycles",
            "Working-capital intensity and input-cost volatility",
            "Regulatory and compliance obligations associated with listed entities",
        ]

    chairman_message = profile_override.get("chairman_message") or (
        f"{borrower.company_name if borrower else company_record.get('company_name', 'The company')} delivered a broadly credible operating profile in {latest_year} "
        f"with revenue of {_format_crore(revenue)} and PAT of {_format_crore(pat)}. "
        f"This document set is synthetic, but grounded in the canonical borrower model and aligned with the real-world market profile of the reference company."
    )
    if positives:
        chairman_message += f" Recent positive developments include {getattr(positives[0], 'headline', 'improving business momentum').lower()}."

    mda_summary = profile_override.get("mda_summary") or (
        f"The borrower operates in {getattr(borrower, 'subsector', getattr(borrower, 'sector', 'its sector'))}. "
        f"The synthetic financial pack follows the internal canonical statements while preserving listed-company style disclosures, exchange filing summaries, and market context."
    )
    if positives:
        mda_summary += f" Market backdrop is supported by signals such as {getattr(positives[0], 'headline', '')}."

    return {
        "FY2024": {
            "chairman_message": chairman_message,
            "key_highlights": key_highlights,
            "mda_summary": mda_summary,
            "risk_factors": risk_factors,
        }
    }


def _extract_html_title(html: str) -> Optional[str]:
    match = re.search(r"<title>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return re.sub(r"\s+", " ", match.group(1)).strip()


def _extract_meta_description(html: str) -> Optional[str]:
    patterns = [
        r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']',
        r'<meta\s+content=["\']([^"\']+)["\']\s+name=["\']description["\']',
        r'<meta\s+property=["\']og:description["\']\s+content=["\']([^"\']+)["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if match:
            return re.sub(r"\s+", " ", match.group(1)).strip()
    return None


def _fetch_web_company_profile(entity_id: str, company_data: dict) -> dict[str, Any]:
    alias = WEB_COMPANY_ALIASES.get(entity_id, {})
    profile: dict[str, Any] = {
        "entity_id": entity_id,
        "actual_company_name": alias.get("actual_company_name", company_data["company_name"]),
        "sources": [],
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json,text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }
    with httpx.Client(timeout=15, headers=headers, follow_redirects=True) as client:
        wiki_title = alias.get("wikipedia_title")
        if wiki_title:
            wiki_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(wiki_title)}"
            try:
                response = client.get(wiki_url)
                if response.status_code == 200:
                    payload = response.json()
                    profile["wikipedia"] = {
                        "title": payload.get("title"),
                        "description": payload.get("description"),
                        "extract": payload.get("extract"),
                        "url": payload.get("content_urls", {}).get("desktop", {}).get("page"),
                    }
                    profile["sources"].append("wikipedia")
            except Exception as exc:
                profile["wikipedia_error"] = str(exc)

        official_url = alias.get("official_url")
        if official_url:
            try:
                response = client.get(official_url)
                if response.status_code == 200:
                    html = response.text
                    profile["official_website"] = {
                        "url": official_url,
                        "title": _extract_html_title(html),
                        "description": _extract_meta_description(html),
                    }
                    profile["sources"].append("official_website")
            except Exception as exc:
                profile["official_website_error"] = str(exc)
    return profile


def _merge_web_profile_into_highlights(company_data: dict, web_profile: dict[str, Any]) -> None:
    highlights = company_data.setdefault("annual_report_highlights", {}).setdefault("FY2024", {})
    wiki_extract = web_profile.get("wikipedia", {}).get("extract")
    official_desc = web_profile.get("official_website", {}).get("description")
    snippets = [snippet for snippet in [wiki_extract, official_desc] if snippet]
    if snippets:
        base_summary = highlights.get("mda_summary", "")
        highlights["mda_summary"] = (base_summary + " " + snippets[0]).strip()
    if snippets and not highlights.get("chairman_message", "").endswith("."):
        highlights["chairman_message"] = (highlights.get("chairman_message", "") + ".").strip()
    if snippets:
        highlights.setdefault("key_highlights", []).append(
            f"Web context: {snippets[0][:140]}{'...' if len(snippets[0]) > 140 else ''}"
        )


def _canonical_directors(company_record: dict) -> list[dict[str, Any]]:
    directors = []
    for director in company_record.get("directors") or []:
        directors.append({
            "name": getattr(director, "name", "Unknown Director"),
            "designation": getattr(director, "designation", "Director"),
            "din": getattr(director, "din", None),
            "is_promoter": getattr(director, "is_promoter", False),
        })
    return directors


def _canonical_collateral(company_record: dict) -> list[dict[str, Any]]:
    collaterals = []
    for item in company_record.get("collateral") or []:
        collaterals.append({
            "type": getattr(item, "collateral_type", "Collateral"),
            "description": getattr(item, "description", ""),
            "market_value_cr": float(getattr(item, "market_value_cr", 0) or 0),
            "forced_sale_value_cr": float(getattr(item, "forced_sale_value_cr", 0) or 0),
            "encumbrance_status": getattr(item, "encumbrance_status", "clear"),
        })
    return collaterals


def _canonical_facility(company_record: dict) -> dict[str, Any]:
    facility = company_record.get("facility")
    if not facility:
        return {}
    return {
        "facility_type": getattr(getattr(facility, "facility_type", None), "value", str(getattr(facility, "facility_type", ""))),
        "case_type": getattr(getattr(facility, "case_type", None), "value", str(getattr(facility, "case_type", ""))),
        "amount_requested_cr": float(getattr(facility, "amount_requested_cr", 0) or 0),
        "purpose": getattr(facility, "purpose", "General corporate purpose"),
        "tenor_months": getattr(facility, "tenor_months", None),
        "proposed_limit_cr": float(getattr(facility, "proposed_limit_cr", 0) or 0),
    }


def _get_canonical_company_record(entity_id: str) -> Optional[dict[str, Any]]:
    from src.data.real_companies import REAL_COMPANIES
    return REAL_COMPANIES.get(entity_id)


def _enrich_company_data(entity_id: str, company_data: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(company_data)
    canonical = _get_canonical_company_record(entity_id)
    profile = WEB_COMPANY_ALIASES.get(entity_id, {})
    borrower = canonical.get("borrower") if canonical else None

    if borrower:
        enriched.setdefault("cin", getattr(borrower, "cin", None))
        enriched.setdefault("pan", getattr(borrower, "pan", None))
        enriched.setdefault("isin", getattr(borrower, "isin", None))
        enriched.setdefault("registered_address", getattr(borrower, "registered_address", None))
        enriched.setdefault("incorporated_date", getattr(getattr(borrower, "date_of_incorporation", None), "strftime", lambda *_: None)("%d-%b-%Y"))
        enriched.setdefault("listed_exchange", getattr(borrower, "listed_exchange", None))
        enriched.setdefault("credit_rating", getattr(borrower, "credit_rating", None))
        enriched.setdefault("rating_agency", getattr(borrower, "rating_agency", None))
        enriched.setdefault("employee_count", getattr(borrower, "employee_count", None))
        enriched.setdefault("website", getattr(borrower, "website", None))
        enriched.setdefault("sector", getattr(borrower, "subsector", None) or getattr(getattr(borrower, "sector", None), "value", None))
        enriched["company_name"] = profile.get("actual_company_name", enriched.get("company_name") or borrower.company_name)
        enriched.setdefault("directors", _canonical_directors(canonical))
        enriched.setdefault("collateral_assets", _canonical_collateral(canonical))
        enriched.setdefault("facility_request", _canonical_facility(canonical))

    if profile.get("bse_code"):
        enriched["bse_code"] = profile["bse_code"]
    if profile.get("auditor"):
        enriched["auditor"] = profile["auditor"]
    return enriched


def _save_web_profile_data(entity_id: str, profile: dict[str, Any], output_dir: Path) -> Path:
    output_file = output_dir / "misc" / "company_profile_web.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": "web_profile_scrape",
        "entity_id": entity_id,
        "scraped_at": datetime.now().isoformat(),
        "profile": profile,
    }
    output_file.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    logger.info(f"Saved web company profile: {output_file}")
    return output_file


def _build_company_data_from_registry(entity_id: str) -> Optional[dict[str, Any]]:
    company_record = _get_canonical_company_record(entity_id)
    if not company_record:
        return None

    borrower = company_record.get("borrower")
    if borrower is None or not getattr(borrower, "nse_symbol", None):
        return None

    financials = _canonical_to_download_financials(company_record.get("financials") or {})
    if not financials:
        return None

    alias = WEB_COMPANY_ALIASES.get(entity_id, {})
    company_name = alias.get("actual_company_name", borrower.company_name)
    sector_label = getattr(borrower, "subsector", None) or getattr(getattr(borrower, "sector", None), "value", str(getattr(borrower, "sector", "")))
    return _enrich_company_data(entity_id, {
        "company_name": company_name,
        "cin": borrower.cin,
        "bse_code": None,
        "nse_symbol": borrower.nse_symbol,
        "isin": getattr(borrower, "isin", None),
        "sector": sector_label,
        "auditor": alias.get("auditor") or _guess_auditor(company_name, sector_label),
        "financials": financials,
        "annual_report_highlights": _build_generated_highlights(company_record, financials),
        "derived_from": "canonical_registry",
        "synthetic_source": {
            "entity_id": entity_id,
            "borrower_name": borrower.company_name,
            "website": getattr(borrower, "website", None),
            "rating": getattr(borrower, "credit_rating", None),
        },
    })


def _get_company_download_config(entity_id: str) -> Optional[dict[str, Any]]:
    if entity_id in REAL_FINANCIAL_DATA:
        return _enrich_company_data(entity_id, dict(REAL_FINANCIAL_DATA[entity_id]))
    return _build_company_data_from_registry(entity_id)


def _generate_simple_profile_pdf(title: str, subtitle: str, paragraphs: list[str], output_file: Path) -> Path:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(output_file), pagesize=A4, topMargin=2 * cm, bottomMargin=1.5 * cm, leftMargin=1.8 * cm, rightMargin=1.8 * cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("DocTitle", parent=styles["Title"], fontSize=17, spaceAfter=8)
    subtitle_style = ParagraphStyle("DocSub", parent=styles["Normal"], fontSize=10, alignment=1, textColor=colors.HexColor("#4a5568"), spaceAfter=10)
    body_style = ParagraphStyle("DocBody", parent=styles["Normal"], fontSize=10, leading=14, spaceAfter=8)

    elements = [Paragraph(title, title_style), Paragraph(subtitle, subtitle_style), HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cbd5e0")), Spacer(1, 0.4 * cm)]
    for paragraph in paragraphs:
        elements.append(Paragraph(paragraph, body_style))
    doc.build(elements)
    return output_file


def _generate_kyc_documents(entity_id: str, company_data: dict[str, Any], output_dir: Path) -> list[str]:
    facility = company_data.get("facility_request", {})
    first_director = (company_data.get("directors") or [{}])[0]
    kyc_dir = output_dir / "kyc"
    files = []
    files.append(str(_generate_simple_profile_pdf(
        company_data["company_name"],
        "Permanent Account Number verification copy",
        [
            f"<b>PAN:</b> {company_data.get('pan', 'N/A')}",
            f"<b>Legal Name:</b> {company_data['company_name']}",
            f"<b>CIN:</b> {company_data.get('cin', 'N/A')}",
            f"<b>Incorporated:</b> {company_data.get('incorporated_date', 'N/A')}",
            "This synthetic KYC artifact is generated for credit workflow testing and mirrors a standard bank-side PAN verification pack.",
        ],
        kyc_dir / "pan_card.pdf",
    ).relative_to(output_dir)))
    files.append(str(_generate_simple_profile_pdf(
        company_data["company_name"],
        "Certificate of incorporation summary",
        [
            f"<b>CIN:</b> {company_data.get('cin', 'N/A')}",
            f"<b>Registered Office:</b> {company_data.get('registered_address', 'N/A')}",
            f"<b>Listed Exchange:</b> {company_data.get('listed_exchange', 'BSE/NSE')}",
            f"<b>Corporate Website:</b> {company_data.get('website', 'N/A')}",
            "This synthetic document condenses key company-registration fields typically verified during onboarding.",
        ],
        kyc_dir / "certificate_of_incorporation.pdf",
    ).relative_to(output_dir)))
    files.append(str(_generate_simple_profile_pdf(
        company_data["company_name"],
        "Board resolution for borrowing powers",
        [
            f"The Board authorizes {first_director.get('name', 'the authorized signatory')} to execute and deliver all credit documents for the proposed {facility.get('facility_type', 'facility')}.",
            f"Requested limit under review: {_format_crore(facility.get('amount_requested_cr', 0) or 0)}.",
            f"Primary purpose stated by management: {facility.get('purpose', 'general corporate purpose')}.",
            "The resolution format is synthetic and intended to mimic a lender-collected authorization record.",
        ],
        kyc_dir / "board_resolution_borrowing.pdf",
    ).relative_to(output_dir)))
    return files


def _generate_rating_report(entity_id: str, company_data: dict[str, Any], output_dir: Path) -> str:
    narrative = WEB_COMPANY_ALIASES.get(entity_id, {}).get("narrative", {})
    rationale = narrative.get("mda_summary", "The rating rationale is aligned to the borrower's operating profile, leverage, and market standing.")
    paragraphs = [
        f"<b>Assigned / Referenced Rating:</b> {company_data.get('credit_rating', 'Not available')} ({company_data.get('rating_agency', 'External agency')})",
        f"<b>Analytical Positioning:</b> {rationale}",
        f"<b>Key Monitorables:</b> {', '.join(narrative.get('risk_factors', ['Cash flow resilience', 'Leverage trajectory', 'Sector conditions']))}",
    ]
    return str(_generate_simple_profile_pdf(
        company_data["company_name"],
        "Credit rating rationale summary",
        paragraphs,
        output_dir / "ratings" / "credit_rating_report.pdf",
    ).relative_to(output_dir))


def _generate_collateral_report(entity_id: str, company_data: dict[str, Any], output_dir: Path) -> str:
    collateral_assets = company_data.get("collateral_assets") or []
    paragraphs = []
    if collateral_assets:
        total_mv = sum(item.get("market_value_cr", 0) for item in collateral_assets)
        total_fsv = sum(item.get("forced_sale_value_cr", 0) for item in collateral_assets)
        paragraphs.append(f"Total collateral market value assessed at {_format_crore(total_mv)} with aggregate forced-sale value of {_format_crore(total_fsv)}.")
        for item in collateral_assets[:5]:
            paragraphs.append(
                f"<b>{item.get('type', 'Collateral')}:</b> {item.get('description', '')} | MV {_format_crore(item.get('market_value_cr', 0))} | FSV {_format_crore(item.get('forced_sale_value_cr', 0))} | Encumbrance: {item.get('encumbrance_status', 'clear')}"
            )
    else:
        paragraphs.append("No specific collateral rows were available in the canonical registry; this placeholder valuation note is retained for workflow completeness.")
    return str(_generate_simple_profile_pdf(
        company_data["company_name"],
        "Collateral valuation and security cover note",
        paragraphs,
        output_dir / "collateral" / "valuation_report.pdf",
    ).relative_to(output_dir))


def _generate_request_note(entity_id: str, company_data: dict[str, Any], output_dir: Path) -> str:
    facility = company_data.get("facility_request", {})
    latest_year = _latest_year_key(company_data.get("financials", {}))
    latest = company_data.get("financials", {}).get(latest_year, {})
    narrative = WEB_COMPANY_ALIASES.get(entity_id, {}).get("narrative", {})
    paragraphs = [
        f"<b>Facility Requested:</b> {facility.get('facility_type', 'Facility')} | <b>Case Type:</b> {facility.get('case_type', 'NTB')}",
        f"<b>Amount Requested:</b> {_format_crore(facility.get('amount_requested_cr', 0) or 0)} | <b>Tenor:</b> {facility.get('tenor_months', 'N/A')} months",
        f"<b>Purpose:</b> {facility.get('purpose') or narrative.get('request_focus', 'general corporate purposes')}",
        f"<b>Latest Financial Snapshot ({latest_year}):</b> Revenue {_format_crore(latest.get('revenue_from_operations', 0))}, EBITDA {_format_crore(latest.get('ebitda', 0))}, PAT {_format_crore(latest.get('profit_after_tax', 0))}, Debt {_format_crore(latest.get('total_debt', 0))}.",
        f"<b>Credit View:</b> {narrative.get('chairman_message', 'Management has represented a stable business trajectory with sector-aligned funding needs.')}",
    ]
    return str(_generate_simple_profile_pdf(
        company_data["company_name"],
        "Management request note for credit facilities",
        paragraphs,
        output_dir / "request" / "request_note.pdf",
    ).relative_to(output_dir))


def _generate_governance_report(entity_id: str, company_data: dict[str, Any], output_dir: Path) -> str:
    directors = company_data.get("directors") or []
    paragraphs = [f"<b>Listing:</b> {company_data.get('listed_exchange', 'BSE/NSE')} | NSE symbol {company_data.get('nse_symbol', 'N/A')} | BSE code {company_data.get('bse_code', 'N/A')}"]
    for director in directors[:6]:
        paragraphs.append(f"<b>{director.get('name')}</b> - {director.get('designation')} | DIN {director.get('din', 'N/A')} | Promoter: {'Yes' if director.get('is_promoter') else 'No'}")
    return str(_generate_simple_profile_pdf(
        company_data["company_name"],
        "Corporate governance snapshot",
        paragraphs,
        output_dir / "exchange" / "corporate_governance_report.pdf",
    ).relative_to(output_dir))


def _generate_gst_summaries(entity_id: str, company_data: dict[str, Any], output_dir: Path) -> list[str]:
    financials = company_data.get("financials", {})
    latest_year = _latest_year_key(financials)
    latest = financials.get(latest_year, {})
    revenue = float(latest.get("revenue_from_operations", 0) or 0)
    monthly_turnover = revenue / 12 if revenue else 0
    monthly_tax = monthly_turnover * 0.18
    paragraphs_3b = [
        f"Synthetic GST 3B summary prepared for {company_data['company_name']}.",
        f"Estimated monthly taxable turnover anchored to {latest_year} revenue run-rate: {_format_crore(monthly_turnover)}.",
        f"Indicative monthly GST liability at 18%: {_format_crore(monthly_tax)}.",
    ]
    paragraphs_1 = [
        f"Synthetic outward supplies summary for {company_data['company_name']}.",
        f"Average monthly outward taxable supplies estimated at {_format_crore(monthly_turnover)} based on the internal financial pack.",
        f"Primary registration references include PAN {company_data.get('pan', 'N/A')} and CIN {company_data.get('cin', 'N/A')}.",
    ]
    return [
        str(_generate_simple_profile_pdf(company_data["company_name"], "GST 3B filing summary", paragraphs_3b, output_dir / "gst" / "gstr3b_summary.pdf").relative_to(output_dir)),
        str(_generate_simple_profile_pdf(company_data["company_name"], "GST 1 outward supplies summary", paragraphs_1, output_dir / "gst" / "gstr1_summary.pdf").relative_to(output_dir)),
    ]


def _generate_bureau_documents(entity_id: str, company_data: dict[str, Any], output_dir: Path) -> list[str]:
    financials = company_data.get("financials", {})
    latest_year = _latest_year_key(financials)
    latest = financials.get(latest_year, {})
    debt = float(latest.get("total_debt", 0) or 0)
    equity = float(latest.get("total_equity", 0) or 0)
    bureau_paragraphs = [
        f"Synthetic bureau summary prepared for {company_data['company_name']} using canonical leverage and size indicators.",
        f"Latest total debt in {latest_year}: {_format_crore(debt)} against total equity of {_format_crore(equity)}.",
        f"The referenced external rating is {company_data.get('credit_rating', 'not available')}, used as a directional proxy for bureau positioning.",
    ]
    exposure_paragraphs = [
        f"Existing facility detail note for {company_data['company_name']}.",
        "Synthetic bureau output assumes a lender group exposure aligned with requested funding and leverage levels.",
        "This document supports extraction, validation, and CAM drafting workflows where lender-wise exposure detail is expected.",
    ]
    return [
        str(_generate_simple_profile_pdf(company_data["company_name"], "Commercial bureau summary", bureau_paragraphs, output_dir / "bureau" / "commercial_bureau_report.pdf").relative_to(output_dir)),
        str(_generate_simple_profile_pdf(company_data["company_name"], "Existing facility detail note", exposure_paragraphs, output_dir / "banking" / "existing_facility_details.pdf").relative_to(output_dir)),
    ]


def _generate_banking_documents(entity_id: str, company_data: dict[str, Any], output_dir: Path) -> list[str]:
    facility = company_data.get("facility_request", {})
    requested = float(facility.get("amount_requested_cr", 0) or 0)
    latest_year = _latest_year_key(company_data.get("financials", {}))
    latest = company_data.get("financials", {}).get(latest_year, {})
    balance = float(latest.get("cash_and_equivalents", 0) or 0)
    bank_statement_paragraphs = [
        f"Six-month banking summary for {company_data['company_name']} based on synthetic operating run-rate assumptions.",
        f"Indicative closing bank / liquid balance reference from {latest_year}: {_format_crore(balance)}.",
        "Monthly turnover is inferred from the generated financial pack and translated into a simplified conduct-style statement artifact.",
    ]
    sanction_paragraphs = [
        f"Illustrative sanction structure for {_format_crore(requested)} requested by {company_data['company_name']}.",
        f"Facility type: {facility.get('facility_type', 'Facility')} | Tenor: {facility.get('tenor_months', 'N/A')} months.",
        f"Primary purpose: {facility.get('purpose', 'general corporate purpose')}.",
    ]
    return [
        str(_generate_simple_profile_pdf(company_data["company_name"], "Bank statement summary - last 6 months", bank_statement_paragraphs, output_dir / "banking" / "bank_statement_6m.pdf").relative_to(output_dir)),
        str(_generate_simple_profile_pdf(company_data["company_name"], "Illustrative sanction letter summary", sanction_paragraphs, output_dir / "banking" / "sanction_letter.pdf").relative_to(output_dir)),
    ]


def generate_extended_company_documents(entity_id: str, company_data: dict[str, Any], output_dir: Path) -> list[str]:
    files = []
    files.extend(_generate_kyc_documents(entity_id, company_data, output_dir))
    files.append(_generate_rating_report(entity_id, company_data, output_dir))
    files.append(_generate_collateral_report(entity_id, company_data, output_dir))
    files.append(_generate_request_note(entity_id, company_data, output_dir))
    files.append(_generate_governance_report(entity_id, company_data, output_dir))
    files.extend(_generate_gst_summaries(entity_id, company_data, output_dir))
    files.extend(_generate_bureau_documents(entity_id, company_data, output_dir))
    files.extend(_generate_banking_documents(entity_id, company_data, output_dir))
    return files


def populate_supported_company_documents(force_refresh: bool = False) -> dict[str, Any]:
    storage_root = DOCUMENTS_ROOT
    started_at = datetime.now().isoformat()
    generated: list[dict[str, Any]] = []
    skipped: list[str] = []
    failed: list[dict[str, str]] = []

    for company in get_supported_companies():
        entity_id = company["entity_id"]
        entity_dir = storage_root / entity_id
        required_paths = [
            entity_dir / "financials" / "audited_financial_statements.pdf",
            entity_dir / "kyc" / "pan_card.pdf",
            entity_dir / "ratings" / "credit_rating_report.pdf",
            entity_dir / "collateral" / "valuation_report.pdf",
            entity_dir / "request" / "request_note.pdf",
        ]
        if not force_refresh and all(path.exists() for path in required_paths):
            skipped.append(entity_id)
            continue

        result = download_company_documents(entity_id, force_refresh=force_refresh)
        if result.get("status") == "success":
            generated.append({
                "entity_id": entity_id,
                "files_generated": len(result.get("files_generated", [])),
            })
        else:
            failed.append({"entity_id": entity_id, "message": result.get("message", "unknown error")})

    result = {
        "status": "success" if not failed else "partial",
        "generated": generated,
        "skipped": skipped,
        "failed": failed,
        "total_generated": len(generated),
        "total_skipped": len(skipped),
        "total_failed": len(failed),
    }
    document_operations.record({
        "operation_type": "bulk_company_generation",
        "status": result["status"],
        "started_at": started_at,
        "completed_at": datetime.now().isoformat(),
        "summary": f"Bulk generation: {result['total_generated']} generated, {result['total_skipped']} skipped, {result['total_failed']} failed",
        "details": {
            "generated": generated,
            "skipped": skipped,
            "failed": failed,
            "force_refresh": force_refresh,
        },
    })
    return result

# ─── NSE API Fetcher ──────────────────────────────────────────────────────────

class NSEFetcher:
    """Fetch live market data from NSE India API."""

    BASE_URL = "https://www.nseindia.com"
    API_URL = "https://www.nseindia.com/api"

    def __init__(self):
        self._client: Optional[httpx.Client] = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=15,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/json",
                    "Accept-Language": "en-US,en;q=0.9",
                },
                follow_redirects=True,
            )
            # Get session cookies
            try:
                self._client.get(self.BASE_URL)
            except Exception:
                pass
        return self._client

    def fetch_quote(self, symbol: str) -> Optional[dict]:
        """Fetch basic quote info from NSE."""
        try:
            client = self._get_client()
            r = client.get(f"{self.API_URL}/quote-equity?symbol={symbol}")
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            logger.warning(f"NSE quote fetch failed for {symbol}: {e}")
        return None

    def fetch_trade_info(self, symbol: str) -> Optional[dict]:
        """Fetch trade info including market cap."""
        try:
            client = self._get_client()
            r = client.get(f"{self.API_URL}/quote-equity?symbol={symbol}&section=trade_info")
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            logger.warning(f"NSE trade info fetch failed for {symbol}: {e}")
        return None

    def close(self):
        if self._client:
            self._client.close()
            self._client = None


# ─── PDF Generator ────────────────────────────────────────────────────────────

def _fmt_cr(val: float) -> str:
    """Format number in crores with Indian number system."""
    if val >= 100000:
        return f"{val:,.2f}"
    return f"{val:,.2f}"


def _generate_audited_financials_pdf(
    entity_id: str,
    company_name: str,
    financials: dict[str, dict],
    auditor: str,
    output_dir: Path,
) -> Path:
    """Generate a proper audited financial statements PDF with P&L and Balance Sheet."""

    output_file = output_dir / "financials" / "audited_financial_statements.pdf"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output_file),
        pagesize=A4,
        topMargin=2 * cm,
        bottomMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("Title2", parent=styles["Title"], fontSize=16, spaceAfter=6)
    subtitle_style = ParagraphStyle("Sub", parent=styles["Normal"], fontSize=11, alignment=1, spaceAfter=12)
    note_style = ParagraphStyle("Note", parent=styles["Normal"], fontSize=8, textColor=colors.grey)

    elements = []

    # Cover page
    elements.append(Spacer(1, 3 * cm))
    elements.append(Paragraph(company_name, title_style))
    elements.append(Paragraph(f"CIN: {REAL_FINANCIAL_DATA.get(entity_id, {}).get('cin', 'N/A')}", subtitle_style))
    elements.append(Spacer(1, 1 * cm))
    elements.append(Paragraph("<b>AUDITED CONSOLIDATED FINANCIAL STATEMENTS</b>", subtitle_style))

    years = sorted(financials.keys(), reverse=True)
    year_range = f"{years[-1]} to {years[0]}" if years else "N/A"
    elements.append(Paragraph(f"For the financial years {year_range}", subtitle_style))
    elements.append(Spacer(1, 2 * cm))
    elements.append(Paragraph(f"Statutory Auditor: {auditor}", subtitle_style))
    elements.append(Paragraph("(Figures in ₹ Crores unless stated otherwise)", note_style))
    elements.append(PageBreak())

    # Statement of Profit and Loss
    elements.append(Paragraph("<b>STATEMENT OF PROFIT AND LOSS</b>", title_style))
    elements.append(Paragraph("(Figures in ₹ Crores)", note_style))
    elements.append(Spacer(1, 0.5 * cm))

    header = ["Particulars"] + years
    pl_rows = [
        ("Revenue from Operations", "revenue_from_operations"),
        ("Other Income", "other_income"),
        ("Total Income", "total_income"),
        ("", None),
        ("Employee Benefit Expense", "employee_benefit_expense"),
        ("Cost of Materials Consumed", "cost_of_materials"),
        ("Depreciation & Amortisation", "depreciation_amortisation"),
        ("Finance Cost", "finance_cost"),
        ("Other Expenses", "other_expenses"),
        ("", None),
        ("EBITDA", "ebitda"),
        ("Profit Before Tax", "profit_before_tax"),
        ("Tax Expense", "tax_expense"),
        ("Profit After Tax", "profit_after_tax"),
    ]

    data = [header]
    for label, key in pl_rows:
        if key is None:
            data.append([""] * (len(years) + 1))
            continue
        row = [label]
        for yr in years:
            val = financials.get(yr, {}).get(key, 0)
            row.append(_fmt_cr(val) if val else "—")
        data.append(row)

    col_widths = [7 * cm] + [3.2 * cm] * len(years)
    tbl = Table(data, colWidths=col_widths)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a365d")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7fafc")]),
        ("FONTNAME", (0, -4), (0, -1), "Helvetica-Bold"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(tbl)
    elements.append(PageBreak())

    # Balance Sheet
    elements.append(Paragraph("<b>BALANCE SHEET</b>", title_style))
    elements.append(Paragraph("(Figures in ₹ Crores)", note_style))
    elements.append(Spacer(1, 0.5 * cm))

    bs_rows = [
        ("ASSETS", None),
        ("Non-Current Assets", "non_current_assets"),
        ("Current Assets", "current_assets"),
        ("  Cash & Cash Equivalents", "cash_and_equivalents"),
        ("  Trade Receivables", "trade_receivables"),
        ("  Inventory", "inventory"),
        ("Total Assets", "total_assets"),
        ("", None),
        ("EQUITY AND LIABILITIES", None),
        ("Total Equity", "total_equity"),
        ("Total Debt", "total_debt"),
        ("  Current Liabilities", "current_liabilities"),
        ("  Trade Payables", "trade_payables"),
    ]

    bs_data = [header]
    for label, key in bs_rows:
        if key is None:
            row = [Paragraph(f"<b>{label}</b>", styles["Normal"])] + [""] * len(years)
            bs_data.append(row)
            continue
        row = [label]
        for yr in years:
            val = financials.get(yr, {}).get(key, 0)
            row.append(_fmt_cr(val) if val else "—")
        bs_data.append(row)

    tbl2 = Table(bs_data, colWidths=col_widths)
    tbl2.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a365d")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7fafc")]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(tbl2)

    elements.append(Spacer(1, 1 * cm))
    elements.append(Paragraph(
        f"As per our report of even date attached.<br/>"
        f"For {auditor}<br/>"
        f"Chartered Accountants",
        note_style,
    ))

    doc.build(elements)
    logger.info(f"Generated audited financials PDF: {output_file}")
    return output_file


def _generate_annual_report_pdf(
    entity_id: str,
    company_data: dict,
    output_dir: Path,
) -> Path:
    """Generate a summary annual report PDF with chairman's message, highlights, MD&A."""

    output_file = output_dir / "financials" / "annual_report_fy2024.pdf"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output_file),
        pagesize=A4,
        topMargin=2 * cm,
        bottomMargin=1.5 * cm,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("ARTitle", parent=styles["Title"], fontSize=18, spaceAfter=12)
    heading_style = ParagraphStyle("ARHead", parent=styles["Heading2"], fontSize=14, spaceBefore=12)
    body_style = ParagraphStyle("ARBody", parent=styles["Normal"], fontSize=10, leading=14, spaceAfter=8)
    highlight_style = ParagraphStyle("ARHighlight", parent=styles["Normal"], fontSize=10, leftIndent=20)

    company_name = company_data["company_name"]
    highlights = company_data.get("annual_report_highlights", {}).get("FY2024", {})
    financials = company_data["financials"]

    elements = []

    # Cover
    elements.append(Spacer(1, 4 * cm))
    elements.append(Paragraph(company_name, title_style))
    elements.append(Paragraph("<b>Annual Report FY2024</b>", ParagraphStyle("", parent=styles["Title"], fontSize=14)))
    elements.append(Spacer(1, 1 * cm))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#1a365d")))
    elements.append(PageBreak())

    # Chairman's Message
    elements.append(Paragraph("Chairman's Message", heading_style))
    elements.append(Paragraph(
        highlights.get("chairman_message", "Financial year 2024 was a year of strong growth and strategic execution."),
        body_style,
    ))
    elements.append(Spacer(1, 0.5 * cm))

    # Key Highlights
    elements.append(Paragraph("Key Financial Highlights", heading_style))
    for h in highlights.get("key_highlights", []):
        elements.append(Paragraph(f"• {h}", highlight_style))
    elements.append(Spacer(1, 0.5 * cm))

    # Financial Summary Table
    elements.append(Paragraph("Financial Performance Summary", heading_style))
    years = sorted(financials.keys(), reverse=True)[:3]
    header = ["Particulars (₹ Cr)"] + years
    summary_items = [
        ("Revenue from Operations", "revenue_from_operations"),
        ("EBITDA", "ebitda"),
        ("Profit After Tax", "profit_after_tax"),
        ("Total Assets", "total_assets"),
        ("Total Equity", "total_equity"),
        ("Total Debt", "total_debt"),
    ]
    tbl_data = [header]
    for label, key in summary_items:
        row = [label]
        for yr in years:
            val = financials.get(yr, {}).get(key, 0)
            row.append(_fmt_cr(val))
        tbl_data.append(row)

    tbl = Table(tbl_data, colWidths=[6 * cm] + [3.5 * cm] * len(years))
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2d3748")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#edf2f7")]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    elements.append(tbl)
    elements.append(PageBreak())

    # Management Discussion & Analysis
    elements.append(Paragraph("Management Discussion & Analysis", heading_style))
    elements.append(Paragraph(
        highlights.get("mda_summary", "The company delivered strong results across all business segments."),
        body_style,
    ))
    elements.append(Spacer(1, 0.5 * cm))

    # Risk Factors
    elements.append(Paragraph("Key Risk Factors", heading_style))
    for r in highlights.get("risk_factors", []):
        elements.append(Paragraph(f"• {r}", highlight_style))

    doc.build(elements)
    logger.info(f"Generated annual report PDF: {output_file}")
    return output_file


def _generate_provisional_xlsx(
    entity_id: str,
    company_name: str,
    financials: dict[str, dict],
    output_dir: Path,
) -> Path:
    """Generate provisional financials Excel file matching extraction format."""

    output_file = output_dir / "financials" / "provisional_financials_fy2025.xlsx"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Provisional Financials"

    # Styles
    header_font = Font(name="Calibri", bold=True, size=11, color="FFFFFF")
    header_fill = PatternFill(start_color="1A365D", end_color="1A365D", fill_type="solid")
    bold_font = Font(name="Calibri", bold=True, size=10)
    normal_font = Font(name="Calibri", size=10)
    num_fmt = '#,##0.00'
    border = Border(
        left=Side(style="thin", color="E2E8F0"),
        right=Side(style="thin", color="E2E8F0"),
        top=Side(style="thin", color="E2E8F0"),
        bottom=Side(style="thin", color="E2E8F0"),
    )

    # Title
    ws.merge_cells("A1:D1")
    ws["A1"] = f"{company_name} — Provisional Financials"
    ws["A1"].font = Font(name="Calibri", bold=True, size=14)

    ws.merge_cells("A2:D2")
    ws["A2"] = "(Figures in ₹ Crores)"
    ws["A2"].font = Font(name="Calibri", italic=True, size=9, color="666666")

    # Headers
    years = sorted(financials.keys(), reverse=True)[:2]  # Latest 2 years for comparison
    headers = ["Particulars"] + [f"{yr} (Provisional)" if i == 0 else f"{yr} (Audited)" for i, yr in enumerate(years)]
    headers.append("Growth %")

    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    # Data rows
    items = [
        ("Revenue from Operations", "revenue_from_operations"),
        ("Other Income", "other_income"),
        ("Total Income", "total_income"),
        ("Employee Benefit Expense", "employee_benefit_expense"),
        ("Depreciation & Amortisation", "depreciation_amortisation"),
        ("Finance Cost", "finance_cost"),
        ("Other Expenses", "other_expenses"),
        ("EBITDA", "ebitda"),
        ("Profit Before Tax", "profit_before_tax"),
        ("Tax Expense", "tax_expense"),
        ("Profit After Tax", "profit_after_tax"),
        ("", None),
        ("Total Assets", "total_assets"),
        ("Total Equity", "total_equity"),
        ("Total Debt", "total_debt"),
    ]

    row_num = 5
    for label, key in items:
        if key is None:
            row_num += 1
            continue
        ws.cell(row=row_num, column=1, value=label).font = bold_font if label.startswith(("Revenue", "EBITDA", "Profit After", "Total")) else normal_font
        for col_idx, yr in enumerate(years, 2):
            val = financials.get(yr, {}).get(key, 0)
            cell = ws.cell(row=row_num, column=col_idx, value=val)
            cell.number_format = num_fmt
            cell.font = normal_font
            cell.border = border

        # Growth %
        if len(years) >= 2:
            curr = financials.get(years[0], {}).get(key, 0)
            prev = financials.get(years[1], {}).get(key, 0)
            if prev and prev != 0:
                growth = ((curr - prev) / abs(prev)) * 100
                cell = ws.cell(row=row_num, column=len(years) + 2, value=round(growth, 1))
                cell.number_format = '0.0"%"'
                cell.font = normal_font

        row_num += 1

    # Column widths
    ws.column_dimensions["A"].width = 30
    for col_letter in ["B", "C", "D"]:
        ws.column_dimensions[col_letter].width = 18

    wb.save(output_file)
    logger.info(f"Generated provisional Excel: {output_file}")
    return output_file


def _generate_exchange_filing_pdf(
    entity_id: str,
    company_name: str,
    financials: dict[str, dict],
    nse_symbol: str,
    output_dir: Path,
) -> Path:
    """Generate exchange filing (quarterly results) PDF."""

    output_file = output_dir / "exchange" / "quarterly_results_q3fy2025.pdf"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(str(output_file), pagesize=A4, topMargin=2*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()

    fy2025 = financials.get("FY2025", {})
    # Q3 approximation: ~25% of annual
    q3_revenue = round(fy2025.get("revenue_from_operations", 0) * 0.26, 2)
    q3_ebitda = round(fy2025.get("ebitda", 0) * 0.26, 2)
    q3_pat = round(fy2025.get("profit_after_tax", 0) * 0.26, 2)
    q3_total_income = round(fy2025.get("total_income", 0) * 0.26, 2)
    q3_pbt = round(fy2025.get("profit_before_tax", 0) * 0.26, 2)

    elements = [
        Paragraph(f"<b>{company_name}</b>", styles["Title"]),
        Paragraph(f"NSE: {nse_symbol} | Exchange Filing", styles["Normal"]),
        Spacer(1, 0.5*cm),
        Paragraph("<b>Unaudited Financial Results for Q3 FY2025 (Oct-Dec 2024)</b>", styles["Heading2"]),
        Spacer(1, 0.3*cm),
    ]

    tbl_data = [
        ["Particulars (₹ Cr)", "Q3 FY2025", "9M FY2025"],
        ["Revenue from Operations", _fmt_cr(q3_revenue), _fmt_cr(q3_revenue * 3)],
        ["Total Income", _fmt_cr(q3_total_income), _fmt_cr(q3_total_income * 3)],
        ["EBITDA", _fmt_cr(q3_ebitda), _fmt_cr(q3_ebitda * 3)],
        ["Profit Before Tax", _fmt_cr(q3_pbt), _fmt_cr(q3_pbt * 3)],
        ["Profit After Tax", _fmt_cr(q3_pat), _fmt_cr(q3_pat * 3)],
    ]

    tbl = Table(tbl_data, colWidths=[7*cm, 4*cm, 4*cm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a365d")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    elements.append(tbl)

    doc.build(elements)
    logger.info(f"Generated exchange filing PDF: {output_file}")
    return output_file


def _save_nse_market_data(entity_id: str, nse_data: dict, output_dir: Path) -> Path:
    """Save live NSE market data as JSON."""
    output_file = output_dir / "exchange" / "nse_live_quote.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    market_data = {
        "source": "NSE India API (Live)",
        "fetched_at": datetime.now().isoformat(),
        "entity_id": entity_id,
        "data": nse_data,
    }
    output_file.write_text(json.dumps(market_data, indent=2, default=str))
    logger.info(f"Saved NSE market data: {output_file}")
    return output_file


# ─── Main Download Orchestrator ───────────────────────────────────────────────

def download_company_documents(
    entity_id: str,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """
    Download/generate financial documents for a company from web sources.

    Strategy:
      1. Try live NSE API for market data
      2. Use pre-verified real financial data (from public annual reports)
      3. Generate proper PDF/Excel documents
      4. Store in storage/documents/{entity_id}/

    Returns:
        dict with download status, files generated, and any live data fetched.
    """

    company_data = _get_company_download_config(entity_id)
    if not company_data:
        return {
            "status": "error",
            "entity_id": entity_id,
            "message": f"No financial data configuration for {entity_id}. "
                       f"Supported: {[c['entity_id'] for c in get_supported_companies()]}",
        }

    company_name = company_data["company_name"]
    nse_symbol = company_data["nse_symbol"]
    auditor = company_data["auditor"]
    financials = company_data["financials"]

    storage_root = DOCUMENTS_ROOT / entity_id
    started_at = datetime.now().isoformat()

    result = {
        "status": "success",
        "entity_id": entity_id,
        "company_name": company_name,
        "source": "web_download",
        "files_generated": [],
        "live_data": {},
        "data_years": sorted(financials.keys()),
    }

    # Step 1: Try live NSE API fetch
    nse = NSEFetcher()
    try:
        quote = nse.fetch_quote(nse_symbol)
        if quote:
            result["live_data"]["nse_quote"] = {
                "symbol": quote.get("info", {}).get("symbol"),
                "company_name": quote.get("info", {}).get("companyName"),
                "industry": quote.get("info", {}).get("industry"),
                "isin": quote.get("info", {}).get("isin"),
                "listing_date": quote.get("info", {}).get("listingDate"),
            }
            _save_nse_market_data(entity_id, quote, storage_root)
            result["files_generated"].append("exchange/nse_live_quote.json")

        trade_info = nse.fetch_trade_info(nse_symbol)
        if trade_info:
            mkt = trade_info.get("marketDeptOrderBook", {}).get("tradeInfo", {})
            result["live_data"]["market"] = {
                "total_market_cap_cr": mkt.get("totalMarketCap"),
                "daily_volatility": mkt.get("cmDailyVolatility"),
                "annual_volatility": mkt.get("cmAnnualVolatility"),
            }
    except Exception as e:
        logger.warning(f"NSE live fetch failed for {nse_symbol}: {e}")
        result["live_data"]["nse_error"] = str(e)
    finally:
        nse.close()

    # Step 1b: Fetch lightweight web profile data for real-company alignment
    try:
        web_profile = _fetch_web_company_profile(entity_id, company_data)
        if web_profile.get("sources"):
            _merge_web_profile_into_highlights(company_data, web_profile)
            _save_web_profile_data(entity_id, web_profile, storage_root)
            result["web_profile"] = {
                "actual_company_name": web_profile.get("actual_company_name"),
                "sources": web_profile.get("sources"),
            }
            result["files_generated"].append("misc/company_profile_web.json")
    except Exception as e:
        logger.warning(f"Web profile fetch failed for {entity_id}: {e}")
        result["web_profile_error"] = str(e)

    # Step 2: Generate audited financial statements PDF (from real data)
    _generate_audited_financials_pdf(entity_id, company_name, financials, auditor, storage_root)
    result["files_generated"].append("financials/audited_financial_statements.pdf")

    # Step 3: Generate annual report PDF
    _generate_annual_report_pdf(entity_id, company_data, storage_root)
    result["files_generated"].append("financials/annual_report_fy2024.pdf")

    # Step 4: Generate provisional financials Excel
    _generate_provisional_xlsx(entity_id, company_name, financials, storage_root)
    result["files_generated"].append("financials/provisional_financials_fy2025.xlsx")

    # Step 5: Generate exchange filing PDF
    _generate_exchange_filing_pdf(entity_id, company_name, financials, nse_symbol, storage_root)
    result["files_generated"].append("exchange/quarterly_results_q3fy2025.pdf")

    # Step 5b: Generate extended KYC, rating, collateral, request, and governance documents
    result["files_generated"].extend(generate_extended_company_documents(entity_id, company_data, storage_root))

    # Step 6: Save financial data as JSON for direct consumption
    fin_json_path = storage_root / "financials" / "web_scraped_financials.json"
    fin_json_path.parent.mkdir(parents=True, exist_ok=True)
    fin_json_path.write_text(json.dumps({
        "source": "web_scrape" if entity_id in REAL_FINANCIAL_DATA else "synthetic_canonical_plus_web",
        "entity_id": entity_id,
        "company_name": company_name,
        "scraped_at": datetime.now().isoformat(),
        "nse_symbol": nse_symbol,
        "bse_code": company_data.get("bse_code"),
        "financials": financials,
        "synthetic_source": company_data.get("synthetic_source"),
    }, indent=2, default=str))
    result["files_generated"].append("financials/web_scraped_financials.json")

    # Update metadata.json
    metadata_path = storage_root / "metadata.json"
    metadata = {
        "entity_id": entity_id,
        "company_name": company_name,
        "data_source": "web_scraped_real_data" if entity_id in REAL_FINANCIAL_DATA else "synthetic_canonical_plus_web",
        "last_updated": datetime.now().isoformat(),
        "fiscal_years_available": sorted(financials.keys()),
        "documents": result["files_generated"],
        "nse_symbol": nse_symbol,
        "bse_code": company_data.get("bse_code"),
        "web_profile_sources": result.get("web_profile", {}).get("sources", []),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2))
    result["files_generated"].append("metadata.json")

    document_operations.record({
        "operation_type": "single_company_generation",
        "entity_id": entity_id,
        "status": result["status"],
        "started_at": started_at,
        "completed_at": datetime.now().isoformat(),
        "summary": f"Generated {len(result['files_generated'])} artifacts for {entity_id}",
        "details": {
            "company_name": company_name,
            "files_generated": result["files_generated"],
            "force_refresh": force_refresh,
            "source": result["source"],
        },
    })

    logger.info(f"Document download complete for {entity_id}: {len(result['files_generated'])} files")
    return result


def get_supported_companies() -> list[dict]:
    """Return list of companies that support web document download."""
    supported: list[dict[str, Any]] = []
    seen: set[str] = set()
    allowed_ids = set(catalog_company_ids())
    for eid in list(REAL_FINANCIAL_DATA.keys()) + list(WEB_COMPANY_ALIASES.keys()):
        if eid not in allowed_ids:
            continue
        if eid in seen:
            continue
        seen.add(eid)
        data = _get_company_download_config(eid)
        if not data:
            continue
        supported.append({
            "entity_id": eid,
            "company_name": data["company_name"],
            "nse_symbol": data["nse_symbol"],
            "bse_code": data.get("bse_code"),
            "years_available": sorted(data["financials"].keys()),
            "source": "hardcoded_real" if eid in REAL_FINANCIAL_DATA else "canonical_registry",
        })
    return supported


def get_real_financials(entity_id: str) -> Optional[dict]:
    """Get pre-verified real financial data for a company (direct access for fact builder)."""
    data = _get_company_download_config(entity_id)
    if not data:
        return None
    return data["financials"]
