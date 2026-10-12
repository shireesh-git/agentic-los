# CAM Intelligence Platform — Architecture & Data Reference

> **Version:** 2.1 | **Date:** 20-Mar-2026 | **Purpose:** Technical reference for developers, reviewers, and stakeholders explaining how data flows, JSONs are created, and what ML/LLM/logic powers each component.

---

## Table of Contents

1. [Platform Overview](#1-platform-overview)
2. [Data Generation — How JSONs & Documents Are Created](#2-data-generation)
3. [Document Extraction — How Data Is Parsed Back](#3-document-extraction)
4. [Engine Layer — Deterministic Logic (No ML)](#4-engine-layer)
5. [LLM & ML Usage — What AI Powers What](#5-llm--ml-usage)
6. [Agent Pipeline — Orchestration](#6-agent-pipeline)
7. [API Layer — Endpoints & Stores](#7-api-layer)
8. [End-to-End Data Flow Diagram](#8-end-to-end-data-flow)
9. [FAQ — Common Questions](#9-faq)

---

## 1. Platform Overview

The CAM Intelligence Platform is a **Credit Approval Memorandum (CAM)** automation system for corporate lending. It:

- Ingests company data (financial statements, KYC, bureau, ratings, GST, etc.)
- Runs **deterministic engines** to compute ratios, benchmarks, validations, risk scores, and fraud signals
- Runs **PEP/sanctions screening** against politically exposed persons, sanctions lists, and adverse media databases
- Performs **social media & digital intelligence** analysis (sentiment, reputation, ESG signals)
- Integrates **core banking analytics** for ETB customers (LOAN, BCLC, LIABILITY, FEES/COMMISSION)
- Assembles a structured **fact-pack JSON** with 28+ sections
- Renders a complete **CAM narrative** (template-based or LLM-generated, 19 sections)
- Provides a **Financial Advisor chat** powered by Ollama LLM
- Outputs: on-screen HTML report, downloadable PDF, one-page graphical memo

### Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, FastAPI, uvicorn |
| Frontend | Alpine.js 3.14, Chart.js 4.4, Tailwind-style dark theme |
| LLM | Ollama (Qwen2.5 32B) — local, no cloud dependency |
| PDF Generation | reportlab (output), pdfplumber (extraction) |
| Excel | openpyxl |
| OCR (optional) | pytesseract |
| Storage | In-memory dicts (POC) + file-based document storage |

---

## 2. Data Generation

### 2.1 Where Company Data Comes From

**Source files:**
- `src/data/synthetic_companies.py` — 4 handcrafted test companies
- `src/data/real_companies.py` — 12 companies inspired by real Indian corporates

Each company is a Python dict containing **canonical model dataclass objects**:

```
company_data = {
    "borrower":      Borrower,              # Company identity, sector, PAN, CIN
    "group":         GroupEntity,            # Parent/subsidiary structure
    "directors":     [DirectorPromoter],     # Board members, DIN, shareholding
    "financials":    {period: FinancialStatement},  # FY2022, FY2023, FY2024
    "provisional":   FinancialStatement,     # FY2025 projected (optional)
    "facility":      FacilityRequest,        # What the company is asking for
    "exposures":     [ExistingExposure],     # Current bank limits & utilization
    "collateral":    [Collateral],           # Security offered
    "market_signals": [MarketSignal],        # News, legal, regulatory events
    "conduct":       [ConductRecord],        # ETB only: monthly account behavior
    "covenants":     [CovenantRecord],       # ETB only: covenant compliance
}
```

### 2.2 The 19 Test Companies

| Entity ID | Company Name | Profile | Purpose |
|-----------|-------------|---------|---------|
| BMFG001 | Bharat Manufacturing Ltd | Listed, NTB, Clean | Baseline "good" company |
| PINF001 | Pioneer Infrastructure Ltd | Listed, NTB, Stressed | Intentional adverse data for testing |
| SPHR001 | Spectrum Pharma Pvt Ltd | Private, NTB, Group Risk | Tests group risk signals |
| OLOG001 | Omega Logistics Pvt Ltd | Private, ETB, Conduct Issues | Tests ETB behavioral flags |
| TSTL001 | Tata Steel Ltd | Listed, NTB | Large cap manufacturing |
| REIL001 | Reliance Industries Ltd | Listed, NTB | Conglomerate |
| INFY001 | Infosys Technologies Ltd | Listed, NTB, **Real Data** | IT sector — live NSE data, real financials, CRILC |
| ADPT001 | Adani Ports SEZ Ltd | Listed, NTB | Infrastructure |
| BJFN001 | Bajaj Finance Ltd | Listed, NTB | NBFC |
| CIPL001 | Cipla Pharmaceuticals Ltd | Listed, NTB | Pharma |
| DLFR001 | DLF Realty Ltd | Listed, ETB, Stressed | Real estate with ETB stress |
| JSWL001 | JSW Steel Ltd | Listed, NTB | Steel |
| MRUT001 | Maruti Suzuki India Ltd | Listed, NTB | Auto |
| TITN001 | Titan Company Ltd | Listed, NTB | Consumer |
| NTPC001 | NTPC Power Ltd | Listed, ETB, Stable | PSU with stable ETB |
| YESB001 | Yes Bank Ltd | Listed, ETB, Fraud Signals | Banking with governance concerns |
| APOL001 | Apollo Hospitals Enterprise Ltd | Listed, NTB, **Real Data** | Healthcare — live NSE data, real financials, CRILC |

### 2.3 How POC Documents (PDFs/XLSX/CSV) Are Generated

**Script:** `scripts/generate_poc_documents.py` (~1800 lines)

This script takes the company data and generates **realistic banking documents** for each company. Output goes to `storage/documents/{entity_id}/{category}/`.

**Document Categories & What Gets Generated:**

| Category | Documents | Format | Key Content |
|----------|----------|--------|-------------|
| **KYC** | PAN card, Certificate of Incorporation, Board Resolution, GST Registration | PDF, TXT | Company identity, registration details |
| **Financials** | Annual Report (3yr), Audited Financial Statements, Provisional FY2025, Debt Schedule, ITR Filing Status | PDF, XLSX | P&L, Balance Sheet, Cash Flow — all from `FinancialStatement.line_items` |
| **Bureau** | Bureau Auto-Fetch, Commercial Bureau Report, CRILC Auto-Fetch, CRILC Report | JSON | Credit score, DPD, SMA status, facility list |
| **Legal** | EPFO Auto-Fetch, EPFO Compliance | JSON | Employee count, compliance status |
| **Collateral** | Valuation Report | PDF | Property/asset valuation, FSV, market value |
| **Ratings** | Credit Rating JSON, Rating Report PDF, Rating Auto-Fetch | JSON, PDF | Agency, instrument, rating, outlook |
| **GST** | GSTIN Auto-Fetch, GSTIN Profile, GST Registration Certificate, GST Turnover, GST Turnover Auto-Fetch | JSON, PDF | GSTIN, turnover by FY, filing regularity |
| **MCA** | Charges Register, Company Master, Director Details, MCA Charges Auto-Fetch, MCA Directors Auto-Fetch, MCA Master Auto-Fetch, MCA Master Data | JSON | ROC data, charges, directors, disqualification status |
| **Banking** | Bank Statement FY2025 | PDF | Monthly transactions (ETB companies) |
| **Misc** | Market Auto-Fetch, Market Intelligence | JSON | News sentiment, reputation risk |

**Per-company document count:** ~13 base + extras for listed (exchange filing, governance report) + extras for ETB (4 CSV conduct files).

### 2.4 How a Specific JSON Document Is Created — Example

**Example: `commercial_bureau_report.json` for BMFG001**

```
Source function: mock_bureau_commercial_report(pan="AABCB1234F")
File: src/data/mock_external_apis.py

Returns:
{
  "source": "bureau_commercial",
  "record_type": "COMMERCIAL_BUREAU_REPORT",
  "entity_key": "AABCB1234F",         ← from borrower.pan
  "as_of_date": "2026-03-13",
  "payload_version": "2.0",
  "source_status": "valid",
  "payload": {
    "entity_name": "Bharat Manufacturing Ltd",
    "credit_score": 782,                ← int, hardcoded per company
    "score_band": "A",
    "total_exposure_cr": 685.0,
    "total_lenders": 4,
    "dpd_status": "Standard",
    "max_dpd_last_12m": 0,
    "worst_status_12m": "Standard",
    "suit_filed_amount_cr": 0.0,
    "wilful_defaulter": false,
    "enquiries_last_6m": 2,
    "facilities": [                     ← synthetic lender exposure breakdown
      {"lender": "SBI", "type": "CC", "limit_cr": 150.0, "outstanding_cr": 128.0, "dpd": 0},
      {"lender": "HDFC", "type": "TL", "limit_cr": 280.0, "outstanding_cr": 245.0, "dpd": 0},
      ...
    ]
  }
}
```

**Pattern followed by ALL mock APIs:** Standardized envelope `{source, record_type, entity_key, as_of_date, payload_version, source_status, payload}`. The `payload` contains data-source-specific fields. Different companies return different severity levels (BMFG001 = clean, PINF001 = stressed) to test validation edge cases.

### 2.5 How Financial Data Flows Into Documents

```
FinancialStatement.line_items = {
    "revenue_operating": 1850.0,    ← ₹ Crores
    "ebitda": 322.50,
    "pat": 141.47,
    "total_assets": 1950.0,
    "total_debt": 705.0,
    ...35 fields total
}
     │
     ▼
gen_annual_report(eid)              ← renders P&L, Balance Sheet, Cash Flow tables
gen_audited_financials(eid)         ← renders auditor's report + detailed statements
gen_provisional_financials_excel()  ← renders FY2025 projected numbers in XLSX
```

The document generators **read the same canonical model** and format it into realistic-looking documents with proper Indian financial statement formatting (₹ Crores, lakhs, GAAP terminology).

---

## 3. Document Extraction

### 3.1 How Extraction Works

**File:** `src/services/document_extractor.py` (~300 lines)

When the user clicks **"Run Extraction"** on the Document Extraction page, the system scans `storage/documents/{entity_id}/` and parses each file:

| File Type | Extraction Method | Library |
|-----------|------------------|---------|
| PDF | `extract_pdf()` → text per page + table extraction | pdfplumber |
| XLSX | `extract_excel()` → all sheets as row arrays | openpyxl |
| JSON | Direct Python `json.load()` | stdlib |
| CSV | `csv.DictReader()` | stdlib |
| TXT | Direct file read | stdlib |

### 3.2 Financial Extraction Logic

`extract_financials_from_pdf()` uses a **metric_map** dict to find financial values:

```python
metric_map = {
    "Revenue from Operations": "revenue",
    "EBITDA": "ebitda",
    "Profit After Tax": "pat",
    "Profit Before Tax": "pbt",
    "Total Assets": "total_assets",
    "Total Equity": "total_equity",
    "Total Debt": "total_debt",
    "Depreciation": "depreciation",
    "Finance Cost": "finance_cost",
    "Total Income": "total_income",
}
```

**Strategy:** First tries regex on extracted text (handles "Revenue from Operations    1,850.00" patterns). Falls back to table cell scanning via `_extract_from_table()`.

### 3.3 What the Extraction Page Shows (Screenshot 1)

The extraction page displays:
- **Audited** — Revenue, EBITDA, PBT, PAT, total assets, total equity, total debt, finance cost, depreciation, total income — extracted from the 3 years of audited financial PDFs
- **Annual Report** — Same fields from the annual report PDF (may have slightly different formatting)
- **Provisional Financials** — FY2025 projected vs FY2024 audited comparison
- **Credit Rating** — Agency, rating, outlook from rating JSON/PDF
- **Exchange Filing** — Nine-month revenue, total income, EBITDA, PBT, PAT from quarterly filings
- **GST Data** — GSTIN, total turnover from GST documents

### 3.4 Cross-Validation After Extraction

The validation engine compares extracted values across sources:
- **Audited Revenue** vs **Exchange Filing Revenue** — mismatch > 5% triggers exception
- **Audited Revenue** vs **GST Turnover** — mismatch > 10% triggers exception
- **Audited Debt** vs **Bureau Total Exposure** — mismatch > 20% triggers exception
- **Provisional** vs **Audited** — directional checks for material changes

---

## 4. Engine Layer

All engines are **100% deterministic** — no ML, no randomness, same input always produces same output.

### 4.1 Ratio Engine

**File:** `src/engines/ratio_engine.py` (~380 lines)

Computes **27 financial ratios** per period from `FinancialStatement.line_items`:

| Category | Ratios | Formula Highlights |
|----------|--------|-------------------|
| **Liquidity** | Current Ratio | Current Assets / Current Liabilities |
| **Leverage** | Debt/Equity, Debt/EBITDA, Debt/Tangible NW, Net Debt/EBITDA, TOL/TNW | Standard leverage formulas |
| **Coverage** | ICR, DSCR, Fixed Charge Coverage | EBITDA/Interest, (EBITDA×0.8)/(Interest+Principal), EBITDA/(Interest+Lease) |
| **Profitability** | NPM, EBITDA Margin, Cash Profit Margin, ROE, ROA, ROCE | Standard margin/return formulas |
| **Efficiency** | Asset Turnover, Debtor Days, Inventory Days, Payable Days, Working Capital Cycle | Days = (Item/Revenue)×365 |
| **Cash Flow** | OCF/Debt, FCFF, Capex/Depreciation | Cash flow adequacy measures |
| **Distress** | Altman Z-Score, Tangible Net Worth, Contingent Liability Ratio | Z = 1.2×A + 1.4×B + 3.3×C + 0.6×D + 1.0×E |

**Entry point:** `compute_all_ratios(financial_statement)` → `list[RatioResult]`

### 4.2 Benchmark Engine

**File:** `src/engines/benchmark_engine.py` (~200 lines)

Compares borrower ratios against **sector peer benchmarks** (P25, median, P75):

```
4 sectors × 15 metrics each:
  Manufacturing, Infrastructure, Pharma, Logistics

Classification:
  BETTER  → ratio in favorable zone (above P75 for "higher is better" / below P25 for "higher is worse")
  WITHIN  → between P25 and P75
  WORSE   → unfavorable zone
```

### 4.3 Validation Engine

**File:** `src/engines/validation_engine.py` (~650 lines)

Runs **30+ validation rules** across 7 categories:

| Category | # Rules | What It Checks |
|----------|---------|---------------|
| Structural | 3 | Balance sheet balances, PAT consistency, EBITDA consistency |
| Cross-Source | 4 | Revenue vs Exchange Filing (±5%), Revenue vs GST (±10%), Debt vs Bureau (±20%), Bureau DPD/SMA/NPA/Wilful |
| Analytical | 3 | Receivable spike (>30% vs <15% revenue growth), Negative OCF with revenue growth, 3yr consecutive margin decline |
| Temporal | 1 | Stale financials (>365 days old) |
| Policy | 1 | Mandatory documents for NTB (KYC, board resolution, 3yr audited, collateral) |
| Conduct (ETB) | 2 | Cheque returns, DPD, utilization, covenant breaches |
| Document-Extraction | 1 | Cross-checks extracted revenue across audited/provisional/exchange/GST docs |

**Output:** `list[ValidationException]` with severity: CRITICAL > HIGH > MEDIUM > LOW

### 4.4 Policy Engine

**File:** `src/engines/policy_engine.py` (~450 lines)

Three-tier **DMN-style** credit decision framework:

**Tier 1 — Hard Rules (Pass/Fail Gates):**
| Rule | Condition | Result |
|------|-----------|--------|
| HR_WILFUL_DEFAULTER | Bureau wilful_defaulter = true | FAIL → auto-decline |
| HR_COMPANY_ACTIVE | MCA status != "Active" | FAIL |
| HR_NO_CRITICAL_EXCEPTIONS | Any critical validation exception | FAIL |
| HR_KYC_COMPLETE | Missing mandatory KYC docs (NTB) | FAIL |
| HR_BUREAU_STATUS | SMA-2 or worse | FAIL |
| HR_MIN_VINTAGE | Company < 3 years old (NTB) | FAIL |
| HR_FRAUD_REGISTRY | On fraud registry | FAIL |
| HR_RBI_DEFAULTER | RBI defaulter list | FAIL |
| HR_SUIT_FILED | Suits > 25% of exposure | FAIL |

**Tier 2 — Risk Scoring (Composite 0-100):**

| Component | Weight | Base Score | Key Adjustments |
|-----------|--------|------------|----------------|
| Financial | 40% | 65 | ±leverage, ±coverage, ±profitability, ±liquidity, ±cash flow, ±Altman Z, ±benchmarks |
| Conduct | 25% | 75 (ETB) / 70 (NTB) | Penalties: cheque returns, DPD, high utilization, covenant breaches |
| Governance | 20% | 65 | ±credit rating (AAA +15 to B -15), ±outlook, ±board independence, ±promoter concentration |
| Market | 15% | 70 | ±positive/negative market signals by severity |

**Composite Score → Risk Grade:**
| Grade | Score Range | Meaning |
|-------|------------|---------|
| A | ≥ 80 | Low Risk |
| B | ≥ 65 | Moderate Risk |
| C | ≥ 50 | Medium Risk |
| D | ≥ 35 | High Risk |
| E | < 35 | Very High Risk |

**Tier 3 — Recommendation:**
| Condition | Recommendation |
|-----------|---------------|
| Any Tier-1 failure | DECLINE |
| Score ≥ 65, no high exceptions | APPROVE |
| Score 50-64 | APPROVE WITH CONDITIONS |
| Score 35-49 | REFER (to higher authority) |
| Score < 35 or multiple high exceptions | DECLINE |

### 4.5 Fraud Detection Engine

**File:** `src/engines/fraud_detection_engine.py` (~350 lines)

7-signal forensic analysis — **no ML models, all formula-based:**

| Signal | Weight | Method | Threshold |
|--------|--------|--------|-----------|
| **Beneish M-Score** | 25% | 8-variable manipulation model (DSRI, GMI, AQI, SGI, DEPI, SGAI, LVGI, TATA) | M > -1.78 = likely manipulator |
| **Benford's Law** | 10% | Chi-squared test on leading digits of financial line items | χ² > 21.67 = significant deviation |
| **Revenue Consistency** | 20% | Cross-source divergence (audited vs provisional vs exchange filing vs GST) | > 10% spread = flag |
| **Altman Z-Score** | 10% | Financial distress indicator (overlap with fraud) | Z < 1.81 = distress zone |
| **Governance Red Flags** | 15% | Multiple directorships, disqualified directors, concentrated shareholding | Weighted flags |
| **Document Anomaly** | 10% | Metadata forensic checks on submitted documents | Pattern-based rules |
| **Circular Transactions** | 10% | Evergreening signals, related-party circular flows | Ratio-based thresholds |

**Output:** FraudReport with composite_score (0-100), risk_grade: LOW (<25), MEDIUM (<45), HIGH (<65), CRITICAL (≥65)

### 4.6 Core Banking Engine

**File:** `src/engines/core_banking_engine.py` (~400 lines)

Analyzes **Existing-to-Bank** customer data across 4 core banking dimensions:

| Module | What It Analyzes |
|--------|------------------|
| **LOAN Analysis** | Active/closed loans, repayment patterns, DPD history, restructuring, total outstanding |
| **BCLC Analysis** | Bill collection/discounting, turnover adequacy, overdue patterns, limit utilization |
| **LIABILITY Analysis** | CASA, FD, total deposits, average balance trends, deposit stability score |
| **FEES/COMMISSION** | Fee income from LC/BG, forex, trade finance, cash management, trend analysis |

**Key Functions:**
- `analyze_core_banking(entity_id, core_banking_data, case_type)` → Full analysis dict
- `core_banking_risk_factor()` → Risk assessment from banking relationship
- `_compute_decision_impact()` → Decision impact summary for CAM recommendation

**Output:** Relationship depth score (0-100), risk factors, decision impact analysis, per-module breakdowns.

### 4.7 Social Media & Digital Intelligence Engine

**File:** `src/engines/social_media_engine.py` (~350 lines)

Analyzes company digital footprint across multiple channels:

| Channel | What It Analyzes |
|---------|------------------|
| **News Sentiment** | Recent news articles, sentiment (positive/negative/neutral), key themes |
| **Social Media** | Twitter/LinkedIn presence, follower trends, engagement metrics |
| **ESG Signals** | Environmental incidents, social controversies, governance concerns |
| **Reputation Risk** | Brand perception score, controversy index, peer comparison |

**Key Functions:**
- `analyze_social_media(entity_id, company_name, sector)` → Full digital intelligence report
- `social_media_risk_score()` → Composite reputation risk (LOW/MEDIUM/HIGH)
- `social_media_summary_for_cam()` → Formatted summary for CAM narrative

**Entity-specific data:** Pre-built intelligence for INFY001, DRRD001, IHCL001, YESB001, DLFR001.

### 4.8 ETB Analytics Engine

**File:** `src/services/etb_analytics.py` (~500 lines)

Behavioral analytics for **Existing-to-Bank** customers using monthly conduct data:

| Module | Weight | Analyzes |
|--------|--------|---------|
| Conduct Analysis | 30% | Monthly utilization %, cheque return rate, trend (H1 vs H2 comparison) |
| Repayment Analysis | 35% | On-time %, DPD days, consecutive delays, partial payments, recovery trend |
| Covenant Compliance | 20% | Breach rate, consecutive breaches, at-risk covenants |
| Utilization Pattern | 15% | Per-facility utilization, over-limit instances, drawing power |

**Composite → Risk Grade:** Low (≥80), Moderate (≥60), High (≥40), Very High (<40)

### 4.9 Document Downloader

**File:** `src/engines/document_downloader.py` (~500 lines)

Downloads and generates real financial documents for supported companies (INFY001, APOL001). Integrates **live NSE API data** with pre-verified multi-year financials.

| Document | Format | Source |
|----------|--------|--------|
| Audited Financial Statements (FY2022-FY2024) | PDF | Pre-verified real data |
| Annual Report FY2024 | PDF | Pre-verified real data |
| Provisional Financials FY2025 | XLSX | Pre-verified estimates |
| Quarterly Results Q3 FY2025 | PDF | Pre-verified real data |
| NSE Live Quote | JSON | **Live API** (`https://www.nseindia.com/api/quote-equity`) |
| Web-Scraped Financials | JSON | Consolidated real data |
| Metadata | JSON | Download timestamps, data freshness |

**Key function:** `download_company_documents(entity_id, force_refresh=False) → dict`
**Live data:** Market cap, 52-week high/low, PE ratio, book value, dividend yield from NSE.
**Storage:** `storage/documents/{entity_id}/financials/`, `storage/documents/{entity_id}/exchange/`

### 4.10 CRILC Report Generator

**File:** `src/engines/crilc_report_generator.py` (~250 lines)

Generates **RBI CRILC** (Central Repository of Information on Large Credits) PDF reports conforming to regulatory reporting standards.

| Data Section | Content |
|-------------|---------|
| Borrower Identification | CIN, PAN, entity name, sector |
| Aggregate Exposure | Total sanction (₹ Cr), outstanding, fund/non-fund split |
| Facility-wise Details | Lender, type, sanction, outstanding, DPD, asset class |
| SMA Classification | SMA-0, SMA-1, SMA-2 history (last 12 months) |
| Consortium Details | Lead arranger, member banks, shares |

**Key function:** `generate_crilc_report(entity_id) → dict` (contains `pdf_path`, `pdf_size_bytes`, `crilc_data`)
**INFY001:** ₹500 Cr sanction, ₹285 Cr outstanding, 4 lenders, Standard asset
**APOL001:** ₹775 Cr sanction, ₹570 Cr outstanding, 5 lenders, Standard asset

### 4.11 CAM Fact-Pack Builder

**File:** `src/engines/cam_fact_builder.py` (~700 lines)

**This is the central assembly point.** `build_cam_fact_pack(company_data)` calls ALL engines and assembles a **38-key JSON**:

```
fact_pack = {
    "meta":                     { generated_date, engine_versions, data_freshness },
    "case_summary":             { entity_id, company_name, sector, case_type, amount, tenor },
    "borrower_profile":         { full company details, vintage, listing, key financial highlights },
    "group_profile":            { parent, subsidiaries, entity_count, hierarchy_tree },
    "management_profile":       { directors, board composition, shareholding pattern },
    "corporate_hierarchy":      { parent/child organizational structure },
    "facility_details":         { type, amount, purpose, tenor, pricing_benchmark },
    "facility_pricing":         { pricing benchmarks, spread, fees },
    "existing_exposure":        { current facilities, utilization, total outstanding },
    "financial_summary":        { 3-4 year P&L, margins, growth rates },
    "ratio_analysis":           { all 27 ratios for all periods },
    "drawing_power":            { drawing power computation },
    "benchmark_summary":        { peer comparison results },
    "collateral_analysis":      { security breakdown, coverage ratios },
    "conduct_analysis":         { account conduct summary (ETB) },
    "covenant_history":         { compliance track record (ETB) },
    "external_intelligence":    { bureau, MCA, rating, CRILC data },
    "market_signals":           { news, sentiment, reputation risk },
    "web_crawl_news":           { live web-crawled industry news },
    "validation_exceptions":    { all validation findings by severity },
    "policy_decisions":         { tier1 gates, tier2 scores, tier3 recommendation },
    "document_extraction":      { extracted financial data from documents },
    "etb_behavioral_analytics": { ETB engine results },
    "credit_strengths":         { deterministically identified positive factors },
    "key_risks":                { deterministically identified risk factors },
    "cash_flow_repayment":      { cash flow adequacy, DSCR projections },
    "esg_regulatory":           { environmental, social, governance checks },
    "compliance_checks":        { regulatory compliance status },
    "charges_data":             { MCA charges register },
    "core_banking":             { raw core banking data (ETB) },
    "core_banking_analysis":    { LOAN, BCLC, LIABILITY, FEES breakdowns (ETB) },
    "social_media_analysis":    { digital intelligence, sentiment, reputation risk },
    "social_media_cam_summary": { formatted summary for narrative sections },
    "pep_screening":            { PEP hits, sanctions, adverse media findings },
    "crilc_exposure":           { CRILC aggregate exposure, facility details, SMA history },
    "quarterly_performance":    { quarterly financial trends },
    "industry_analysis":        { sector overview, competitive landscape },
    "data_sources":             { data provenance tracking },
}
```

### 4.12 CAM Renderer (Template)

**File:** `src/engines/cam_renderer.py` (~1130 lines)

Converts the fact-pack JSON into a **23-section Markdown CAM narrative** (template-based, deterministic):

1. Cover Page → 2. Table of Contents → 3. 360° Overview → 4. Executive Summary → 5. Borrower Profile → 6. Corporate Hierarchy → 7. Facility Details → 8. Financial Analysis → 9. Credit Strengths → 10. Key Risks → 11. Cash Flow & Repayment → 12. Benchmark Analysis → 13. Collateral Analysis → 14. Conduct Analysis → 15. Covenant History → 16. External Intelligence → 17. ESG & Regulatory → 18. Validation Summary → 19. Risk Assessment → 20. Recommendation → 21. Lending Decision → 22. Audit Trail → 23. Disclaimer

**Output:** ~22,000–33,000 characters of formatted Markdown per company, converted to HTML for on-screen display or fed to reportlab for PDF.

### 4.13 CAM LLM Renderer

**File:** `src/engines/cam_llm_renderer.py` (~600 lines)

LLM-powered narrative renderer producing **19-section** professional CAM document with enhanced writing quality:

| Section | Key Enhancement |
|---------|----------------|
| Executive Summary | Contextual narrative with embedded financial data |
| Borrower Profile | Industry positioning, competitive landscape |
| Industry Analysis | Sector trends, regulatory outlook, competitive dynamics |
| Financial Analysis | DuPont decomposition, cash conversion, working capital (500-700 words) |
| Facility Details | Purpose justification, pricing rationale, drawdown schedule |
| Security & Collateral | Valuation methodology, coverage adequacy, enforcement considerations |
| Risk Assessment | Comprehensive risk matrix with mitigation strategies |
| Compliance & PEP | PEP screening results, sanctions check, adverse media findings |
| **8A. Core Banking** | **NEW** — LOAN/BCLC/LIABILITY/FEES analysis, relationship depth score |
| **8B. Social Media** | **NEW** — Digital intelligence, sentiment analysis, reputation risk |
| Covenants | Financial/non-financial covenants with monitoring framework |
| Conduct Analysis | Account behavior patterns, DPD history |
| Benchmarking | Sector peer comparison with narrative context |
| Recommendation | Decision rationale with core banking, social media, PEP inputs |

**System Prompt:** Enhanced banking prose style — formal, evidence-based, no bullet points in narrative, 3-4 sentence paragraphs, specific numbers/dates.

**Prompts:** SYSTEM_PROMPT / CAM_SECTIONS in src/engines/cam_llm_renderer.py (21 sections; bump `PROMPT_VERSION` when changing them).

---

### 4.14 Credit Risk Observation Engine

**File:** `src/engines/observation_engine.py` — details and detector mapping in `docs/CREDIT_OBSERVATIONS.md`.

Runs after the 7-agent pipeline (in `build_case_result`) over that run's fact pack: 12 deterministic detectors (working capital, cash conversion, leverage, debt service, debtor / inventory days, margin, data reliability, peer benchmarks, policy deviation, liquidity, Altman Z) turn existing ratios, benchmarks, validation exceptions and policy results into structured `CreditObservation` records (`case["observations"]`). Thresholds: `config/rules.yaml → credit_observations`. It does not change the score, recommendation or CAM. Optional on-demand LLM wording (`src/services/observation_narrator.py`) explains an observation; it never detects, scores or calculates, and any figure not in the observation's facts rejects the response.

---

## 5. LLM & ML Usage

### 5.1 Summary: What Uses AI vs What Doesn't

| Component | AI? | Technology |
|-----------|-----|-----------|
| Financial Advisor Chat | **YES — LLM** | Ollama Qwen2.5 32B |
| CAM Narrative (optional) | **YES — LLM** (with template fallback) | Ollama Qwen2.5 32B |
| Ratio Engine | No | Deterministic formulas |
| Benchmark Engine | No | Rule-based comparison |
| Validation Engine | No | Rule-based checks |
| Policy Engine | No | DMN-style decision rules |
| Fraud Detection | No | Statistical formulas (Beneish, Benford, Altman) |
| ETB Analytics | No | Score-based behavioral analysis |
| Document Extraction | No | Regex + table parsing (pdfplumber) |
| CAM Fact Builder | No | Data assembly |
| CAM Renderer | No | Template-based rendering |
| Core Banking Engine | No | Score-based relationship analysis |
| Social Media Engine | No | Mock-data digital intelligence |
| PEP Screening | No | Database matching (deterministic) |
| Document Downloader | No | Live NSE API + pre-verified financial data |
| CRILC Report Generator | No | Deterministic PDF generation (reportlab) |

### 5.2 LLM Provider Framework

**File:** `src/core/llm_provider.py` (~200 lines)

Pluggable provider architecture — swap LLMs via `config/llm_providers.yaml` without code changes:

| Provider | Class | Transport | Status |
|----------|-------|-----------|--------|
| **Ollama (Local)** | `OllamaProvider` | POST `http://localhost:11434/api/generate` | **Active — qwen2.5:32b** |
| OpenAI | `OpenAIProvider` | OpenAI Python SDK | Available (needs API key) |
| Anthropic | `AnthropicProvider` | Anthropic Python SDK | Available (needs API key) |
| Azure OpenAI | `AzureOpenAIProvider` | Azure SDK | Available (needs endpoint+key) |
| Mock | `MockLLMProvider` | Returns template text | Fallback |

**Configuration (`config/llm_providers.yaml`):**
```yaml
active_provider: "ollama"
narrative:
  mode: "llm"                    # "template" for no LLM, "llm" for active provider
  temperature: 0.15
  max_tokens: 16000
  max_tokens_per_section: 2500
providers:
  ollama:
    model: "qwen2.5:32b"
    base_url: "http://localhost:11434"
    temperature: 0.15
    max_tokens: 16000
```

### 5.3 Financial Advisor Chat (LLM)

**File:** `src/services/analyst_chat.py` (~430 lines)

| Feature | Detail |
|---------|--------|
| **Model** | qwen2.5:32b via Ollama `/api/generate` |
| **Temperature** | 0.3 (low creativity, factual) |
| **Max tokens** | 500 per response |
| **Context** | Company fact-pack (financial_summary, ratios, strengths, risks, collateral, hierarchy, etc.) |
| **System prompt** | "Expert credit analyst and financial advisor" persona |
| **Session management** | In-memory per entity_id, max 20 messages |
| **Fallback** | If Ollama unavailable → keyword-based rule extraction |

**How context is built:**
```
build_context(case_data, extraction, etb_analysis) →
  - Financial Performance (revenue, EBITDA, PAT from fact_pack)
  - Key Financial Ratios (D/E, ICR, current ratio, etc.)
  - Credit Strengths (from fact_pack.credit_strengths)
  - Key Risks (from fact_pack.key_risks)
  - Collateral Coverage
  - Hierarchy Info
  - Cash Flow & Repayment
  - Conditions & Covenants
  - Validation Exceptions
  Truncated to MAX_CONTEXT_CHARS=6000
```

### 5.4 CAM Narrative Generation (Optional LLM)

When `narrative.mode: "llm"` in config, the `NarrativeAgent` in `src/agents/narrative_agent.py`:

1. Builds fact-pack JSON (deterministic)
2. Sends entire fact-pack as prompt to LLM: *"Generate a complete Credit Approval Memorandum from this fact-pack"*
3. System prompt enforces: use only facts from JSON, no hallucination, formal banking language
4. **Fallback:** If LLM returns < 100 chars or error → falls back to template renderer automatically

**In practice:** The template renderer (`cam_renderer.py`) produces higher quality, more consistent output than LLM. LLM mode is primarily for demonstration purposes.

### 5.5 What Is NOT ML

Some components use **statistical formulas** that look like ML but aren't:

| Component | Technique | Why It's Not ML |
|-----------|-----------|----------------|
| **Beneish M-Score** | 8-variable linear formula | Fixed coefficients discovered by research (1999), no training |
| **Benford's Law** | Chi-squared test on digit distribution | Pure statistics, no model |
| **Altman Z-Score** | 5-factor linear discriminant | Fixed formula (1968), no model fitting |
| **Risk Scoring** | Weighted component scoring | Manually defined weights and thresholds |

---

## 6. Agent Pipeline

**Files:** `src/agents/pipeline.py` (orchestrator) and one module per agent in `src/agents/`

`SuperAgent.execute_pipeline(company_data)` runs 7 sub-agents. Each agent declares
`requires` (agents that must succeed first — their results, or their changes to
`company_data`, are needed) and `waits_for` (agents whose result it uses if present).
With `pipeline.parallel_agents: true` (default, `config/settings.yaml`) an agent starts
as soon as those have finished, so independent agents run side by side; with `false` they
run one at a time in list order. The pipeline log is kept in list order either way.

```
data_ingestion ─┬─ financial_analysis ── benchmark ─┐
                └─ validation ──────────────────────┴─ policy ─┐
pep_screening ─────────────────────────────────────────────────┴─ narrative
```

| # | Agent | Critical | requires / waits_for | Does |
|---|-------|----------|----------------------|------|
| 1 | DataIngestionAgent | yes | — | DMS fetch, document extraction (cached per file), uploaded-financials overrides on `company_data`, authenticity fingerprints, ETB analytics, cached verified public records (Probe42) |
| 2 | PEPScreeningAgent | no | — | Directors against PEP/sanctions lists |
| 3 | FinancialAnalysisAgent | yes | requires ingestion | `ratio_engine` over all periods (ingestion may first replace financials from uploads) |
| 4 | ValidationAgent | yes | requires ingestion | Structural, cross-source and policy validations → exceptions |
| 5 | BenchmarkAgent | yes | requires financial analysis | Sector peer percentiles |
| 6 | PolicyAgent | yes | requires 3, 4, 5 | Tier 1 hard rules, tier 2 risk score, tier 3 recommendation |
| 7 | NarrativeAgent | yes | requires 3–6; waits_for PEP | Fact pack (reusing the PEP result) and CAM text: templates, or the LLM via `cam_llm_renderer` with prompts from `cam_sections.py` |

**Critical flag:** if a critical agent fails, the pipeline stops and the run is recorded as
failed (`GET /api/cases/{id}/runs`). PEP screening is the only non-critical agent; if it
fails, the narrative screens the directors itself.

**Narrative execution path** depends on the active LLM provider: on hosted providers up to
`narrative.max_parallel_sections` sections are written at once; Ollama writes one at a time
with one context size for the run. LLM-written sections are checkpointed as they finish, so a
failed run resumes. See the README section *Pipeline execution & performance*.

---

## 7. API Layer

**Files:** `src/api/main.py` (ASGI entry), `src/api/app.py` (app factory) and one router per
area in `src/api/routers/`; business logic is in `src/application/` services. Full list:
the README endpoint summary or `/docs` (OpenAPI) on a running server.

### 7.1 Key Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/companies` | GET | List companies (with identifiers, facility type, purpose) |
| `/api/companies` | POST | Add new company (JSON → canonical model) |
| `/api/cases/{eid}/run` | POST | Execute full pipeline for company |
| `/api/cases` | GET | List all analyzed cases |
| `/api/cases/{eid}` | GET | Get full case results |
| `/api/cases/{eid}/cam-html` | GET | CAM as styled HTML (iframe) |
| `/api/cases/{eid}/cam-pdf` | GET | CAM as downloadable PDF |
| `/api/cases/{eid}/one-pager` | GET | One-page graphical memo HTML |
| `/api/companies/{eid}/documents` | GET | List all documents for company |
| `/api/companies/{eid}/extract` | POST | Run document extraction |
| `/api/companies/{eid}/etb-analytics` | POST | Run ETB behavioral analysis |
| `/api/companies/{eid}/fraud-analysis` | POST | Run fraud detection |
| `/api/companies/{eid}/pep-screening` | GET | PEP/sanctions/adverse media screening |
| `/api/companies/{eid}/core-banking` | GET | Core banking analysis (LOAN, BCLC, LIABILITY, FEES) |
| `/api/companies/{eid}/social-media` | GET | Social media & digital intelligence |
| `/api/companies/{eid}/hierarchy` | GET | Corporate hierarchy tree |
| `/api/companies/{eid}/360` | GET | 360° company overview |
| `/api/companies/{eid}/fetch-documents` | POST | Download real financial documents (INFY001, APOL001) |
| `/api/companies/supported-downloads` | GET | List companies with real document downloads |
| `/api/companies/{eid}/crilc-pdf` | POST | Generate CRILC PDF report |
| `/api/companies/{eid}/crilc-pdf` | GET | Download generated CRILC PDF |
| `/api/chat/{eid}` | POST | Financial advisor chat message |
| `/api/chat/{eid}/history` | GET | Chat history |
| `/api/llm/providers` | GET | Available LLM providers |
| `/api/llm/test` | POST | Test LLM connectivity |
| `/api/cases/{eid}/observations` | GET | Credit risk observations + counts (`?run_id=` for an earlier run) |
| `/api/cases/{eid}/observations/{obs_id}` | PATCH | Analyst status / note |
| `/api/cases/{eid}/observations/explain` | POST | On-demand AI wording for observations |

### 7.2 In-Memory Stores

| Store | Key | Contents |
|-------|-----|----------|
| `company_store` | entity_id | Full canonical company data (Borrower, financials, facility, etc.) |
| `case_store` | entity_id | Pipeline results (risk_grade, cam_text, fact_pack, pipeline_log) |
| `extraction_store` | entity_id | Extracted financial data from documents |
| `etb_store` | entity_id | ETB analytics results |
| `fraud_store` | entity_id | Fraud detection results |

---

## 8. End-to-End Data Flow

```
                    SYNTHETIC + REAL DATA
                    ┌──────────┐
                    │ 19 test  │
                    │companies │
                    └────┬─────┘
                         │
           ┌─────────────┼─────────────┐
           ▼             ▼             ▼
    ┌────────────┐ ┌──────────┐ ┌────────────┐
    │ POC Docs   │ │ Mock APIs│ │ Company    │
    │ Generator  │ │ (11 fn)  │ │ Store      │
    │ 252 files  │ │          │ │ (in-memory)│
    └──────┬─────┘ └────┬─────┘ └──────┬─────┘
           │             │              │
           ▼             │              │
    ┌────────────┐       │              │
    │ Document   │       │              │
    │ Extraction │       │              │
    │ (pdfplumber│       │              │
    │  openpyxl) │       │              │
    └──────┬─────┘       │              │
           │             │              │
           ▼             ▼              ▼
    ┌─────────────────────────────────────────┐
    │           ENGINE LAYER                  │
    │                                         │
    │  Ratio     Benchmark    Validation      │
    │  Engine    Engine       Engine          │
    │  (27       (4 sectors   (30+ rules     │
    │  ratios)   ×15 metrics) 7 categories)  │
    │                                         │
    │  Policy    Fraud        ETB Analytics   │
    │  Engine    Detection    (conduct,       │
    │  (3 tiers) (7 signals)  repayment)     │
    │                                         │
    │  Core       Social      PEP/Sanctions   │
    │  Banking    Media       Screening       │
    │  Engine     Engine      (adverse media) │
    └──────────────────┬──────────────────────┘
                       │
                       ▼
    ┌─────────────────────────────────────────┐
    │      CAM FACT-PACK BUILDER              │
    │      28-section JSON assembly            │
    │      (all deterministic)                 │
    └──────────────────┬──────────────────────┘
                       │
              ┌────────┴────────┐
              ▼                 ▼
    ┌──────────────┐   ┌──────────────┐
    │ CAM Template │   │ LLM Narrative│
    │ Renderer     │   │ (Ollama)     │
    │ (Markdown)   │   │ (optional)   │
    └──────┬───────┘   └──────┬───────┘
           │                  │
           └────────┬─────────┘
                    ▼
    ┌─────────────────────────────────────────┐
    │           OUTPUT LAYER                  │
    │                                         │
    │  ┌───────────┐ ┌──────┐ ┌───────────┐  │
    │  │ HTML CAM  │ │ PDF  │ │ One-Page  │  │
    │  │ (iframe)  │ │      │ │ Memo      │  │
    │  └───────────┘ └──────┘ └───────────┘  │
    │                                         │
    │  ┌───────────┐ ┌──────────────────┐     │
    │  │ Financial │ │ Dashboard SPA    │     │
    │  │ Advisor   │ │ (Alpine.js)     │     │
    │  │ Chat(LLM) │ │                  │     │
    │  └───────────┘ └──────────────────┘     │
    └─────────────────────────────────────────┘
```

---

## 9. FAQ — Common Questions

### Q: "How is this JSON created?"

Every JSON in the document store follows ONE pattern:

1. **Source data** comes from `synthetic_companies.py` or `real_companies.py` (canonical Python dataclass objects)
2. **Mock APIs** (`mock_external_apis.py`) simulate external data sources (bureau, MCA, GST, etc.) and return standardized JSON envelopes
3. **Document generators** (`generate_poc_documents.py`) take source data and create realistic PDFs/XLSX
4. **The fact-pack JSON** is assembled by `cam_fact_builder.py` which calls ALL engines and packs 24 sections

### Q: "Where does the financial data in the extraction page come from?"

The extraction page shows data **parsed backwards from generated documents**:
- Audited financials → extracted from PDF using pdfplumber + regex
- Annual report → extracted from PDF
- Provisional → extracted from XLSX using openpyxl
- Credit rating → extracted from rating JSON/PDF
- Exchange filing → extracted from filing PDF
- GST → extracted from GST JSON/PDF

This is intentional — it simulates the real-world flow where a bank receives physical/digital documents and needs to extract structured data.

### Q: "What ML models are used?"

**No traditional ML models are used.** The platform is primarily rule-based/deterministic. LLM (Large Language Model) is used only for:
1. **Financial Advisor Chat** — Ollama Qwen2.5 32B
2. **Optional CAM narrative generation** — same LLM, with template fallback

Statistical formulas like Beneish M-Score, Benford's Law, and Altman Z-Score are NOT ML — they are fixed mathematical formulas from academic research.

### Q: "Can I switch to a different LLM?"

Yes. Edit `config/llm_providers.yaml`:
- Set `active_provider: "openai"` and provide `OPENAI_API_KEY` env var for GPT-4
- Set `active_provider: "anthropic"` and provide `ANTHROPIC_API_KEY` for Claude
- Set `active_provider: "mock"` for fully deterministic (no LLM calls at all)
- Current active: `qwen2.5:32b` (32B parameter model — significantly better narration quality than 8B)

### Q: "What happens if Ollama is down?"

- **Financial Advisor Chat** → Falls back to keyword-based rule extraction (searches fact-pack context for relevant data)
- **CAM Narrative** → Falls back to template renderer (`cam_renderer.py`) — produces identical output every time
- **All engines** → Unaffected, they never use LLM (including social_media_engine and core_banking_engine)

### Q: "How are risk scores calculated?"

Composite = 40% Financial + 25% Conduct + 20% Governance + 15% Market.
Each component starts at a base score (65-75) and gets adjustments based on ratio quality, benchmark position, conduct history, credit rating, board composition, and market signals. See Section 4.4 for full details.

### Q: "How does the fraud detection work without ML?"

It uses 7 research-backed forensic techniques:
- **Beneish M-Score** (1999) — 8-variable formula that identifies earnings manipulation
- **Benford's Law** — statistical test on digit distribution (natural data follows a specific pattern; fabricated data doesn't)
- **Altman Z-Score** (1968) — 5-factor distress predictor
- Cross-source revenue consistency checks
- Governance red flag scoring
- All are **deterministic formulas** — no model training, no neural networks.

---

---

## 10. Postman Collection — API Testing

The platform includes a comprehensive Postman collection for testing all API flows:

**Collection:** "CAM Platform — Full Suite v2" (ID: `ff23be57-feb6-4de9-9a47-4ac913cd70b7`)

### NTB (New-to-Bank) Flow — 15+ requests
1. Health Check → 2. List Companies → 3. CIN Lookup → 4. MCA Company Master → 5. MCA Directors → 6. Bureau Credit Report → 7. GST Turnover → 8. Credit Rating → 9. CRILC Report → 10. Exchange Filing → 11. Market Sentiment → 12. Web Crawl → 13. PEP Screening → 14. Social Media → 15. Fraud Detection → Run Pipeline → View CAM HTML → Download PDF → 360° View

### ETB (Existing-to-Bank) Flow — 13+ requests
1. Prior Case Result → 2. 360° Historical View → 3. Core Banking Analysis → 4. ETB Analytics → 5. Bureau Refresh → 6. Rating Migration → 7. Web Crawl → 8. PEP Screening → 9. Social Media → Run Pipeline → View CAM HTML → Download PDF

### Shared Endpoints
- Batch Run All Companies
- List All Analyzed Cases

**Collection Variables:**
| Variable | Default Value |
|----------|---------------|
| baseUrl | http://localhost:8001 |
| entity_id | INFY001 (NTB) |
| etb_entity_id | IHCL001 (ETB) |
| cin | L30007MH1946PLC004520 |

---

## 11. E2E Test Results — Real Data Pipeline

### 11.1 Test Summary (20-Mar-2026)

| Test | INFY001 (Infosys) | APOL001 (Apollo Hospitals) |
|------|-------------------|---------------------------|
| **Document Download** | 7 files, Live NSE (₹497,191 Cr mkt cap) | 7 files, Live NSE (₹104,855 Cr mkt cap) |
| **CRILC Report** | PDF 5,676 bytes, ₹500 Cr sanction | PDF 5,910 bytes, ₹775 Cr sanction |
| **Document Extraction** | 13 sources, real FY2022-FY2025 | 6 sources, real FY2022-FY2025 |
| **Fact Pack** | 38 keys | 38 keys |
| **Template CAM** | 28,426 chars, 19 sections | 29,584 chars, 19 sections |
| **Risk Score** | Grade A, Composite 86.3 | Grade B, Composite 73.5 |
| **LLM Pipeline** | All 7 agents OK, NarrativeAgent 1114.6s | All 7 agents OK (qwen2.5:32b) |

### 11.2 Real Data Sources

| Source | Technology | Data |
|--------|-----------|------|
| **NSE Live API** | `https://www.nseindia.com/api/quote-equity` | Market cap, 52-week range, PE, book value, dividend yield |
| **Pre-verified Financials** | Embedded in `document_downloader.py` | FY2022-FY2025 audited P&L, Balance Sheet, Cash Flow |
| **CRILC Synthetic** | `crilc_report_generator.py` | Fund/non-fund facilities, SMA history, consortium details |
| **Mock APIs** | `mock_external_apis.py` | Bureau, GST, MCA, Rating, Directors, Charges |

### 11.3 Key Verification Points

- **Financial data accuracy:** Revenue figures match Infosys/Apollo annual reports (FY2022-FY2024)
- **CRILC integration:** Aggregate exposure, facility breakdowns, and SMA classification appear in fact pack `crilc_exposure` key
- **Live market data:** NSE API returns real-time market cap, PE ratio, and 52-week price range
- **CAM quality:** Both CAMs contain cover page, TOC, financial analysis with DuPont decomposition, multi-year ratio trends, SWOT, risk matrix, and lending decision
- **Storage:** Documents stored at `storage/documents/{entity_id}/` organized by category (financials, exchange, bureau, banking)

---

*This document is auto-generated for the CAM Intelligence Platform POC. For code-level details, refer to the source files referenced throughout.*
