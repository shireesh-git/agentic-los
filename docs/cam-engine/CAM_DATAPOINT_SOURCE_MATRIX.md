# CAM Datapoint Source Matrix

## 1. Purpose

This document defines, in code-level terms, where the CAM gets its data from, which datapoints are real vs synthetic/derived, which Probe42 v2 APIs are used, which uploaded/downloaded documents are parsed locally, and which CAM sections consume each source.

The intent is to make three things explicit:

1. What can be produced offline without any external API call.
2. What comes from Probe42 v2 MCP.
3. What is still synthetic, templated, or internally mocked and should not be presented as hard source truth.


## 2. Source Classes

| Source Class | Meaning | External network call required | Current implementation |
| --- | --- | --- | --- |
| Local document extraction | Uploaded or downloaded files parsed locally from disk | No | PyMuPDF, pytesseract, pdfplumber, openpyxl |
| Probe42 v2 MCP | Company KYC, ratings, legal, charges, freshness, and optional compliance/network data | Yes | Lean profile is default; cached per entity |
| Internal / ETB systems | Core banking, conduct, reciprocity, CRILC-like internal views | No for mock; Yes in real bank integration | Currently mock/internal generator unless ETB connectors are added |
| Synthetic / derived | Deterministic templates, heuristics, formulas, or canned content | No | Used where no live source exists yet |


## 3. Local OCR and Document Extraction

### 3.1 Runtime stack

The document extraction path is local-only. It does not call any external OCR API.

| Component | Role | Needed for | Network call |
| --- | --- | --- | --- |
| `PyMuPDF` / `fitz` | Primary PDF text, table, metadata, fingerprint extraction | Annual reports, audited financials, downloaded reports, PDF authenticity | No |
| `pytesseract` | Python bridge to Tesseract | OCR fallback for image/scanned PDF pages | No |
| `Tesseract OCR` binary | Actual OCR engine | Scanned PDFs with weak or no text layer | No |
| `pdfplumber` | Native PDF fallback and metadata analysis | Native text extraction when PyMuPDF path is not used | No |
| `openpyxl` | Excel parsing | Debt schedules, provisional financials, structured sheets | No |

### 3.2 Local extraction behavior

| Stage | What it does | Primary code path | Output |
| --- | --- | --- | --- |
| Document fingerprinting | SHA-256 hash plus PDF metadata | `src/engines/document_ocr_engine.py` | Verification and authenticity signals |
| PDF text extraction | Page text, tables, OCR-page counts, quality score | `extract_text_pymupdf()` | Text and tables for CAM and RAG |
| OCR fallback | Renders page image and runs Tesseract if native text is weak | `_ocr_page()` | OCR text for scanned pages |
| Generic PDF fallback | Native text and tables with `pdfplumber` | `src/services/ocr_service.py` and `src/services/document_extractor.py` | Alternate extraction path |
| Excel extraction | Structured sheet parsing | `src/services/document_extractor.py` | Financial and debt schedule fields |

### 3.3 Local OCR status expected by the app

The intended local-only path is:

1. `PyMuPDF` handles PDF text and metadata.
2. `pytesseract` plus local `tesseract.exe` handles scanned pages.
3. No OCR SaaS, no external API, no cloud document AI.

If `fitz` or Tesseract are missing:

- PDF metadata verification degrades.
- Scanned annual reports and image PDFs become lower quality.
- The CAM can still run, but extracted datapoints and authenticity signals are weaker.


## 4. Probe42 v2 API Matrix

### 4.1 Current default: lean profile

The default cached Probe pull is the `lean` profile. It is the cost-optimized path for onboarding and CAM generation.

| Probe42 tool | Default profile | Main datapoints | Fact-pack / company target | CAM sections |
| --- | --- | --- | --- | --- |
| `search_companies_by_name_starts_with` | Preview only | Name match, CIN candidate | Resolve preview only | Smart onboard preview |
| `get_base_details_by_identifier` | Yes | Legal name, CIN, status, incorporation, address | `borrower_profile`, `external_intelligence.mca_status` | 1, 2, 8 |
| `get_kyc_by_identifier` | Yes | PAN, listing status, industry, directors, GST count, employee range, Probe score | `borrower_profile`, `management_profile`, `probe_summary`, `external_data` | 1, 2, 7, 8 |
| `get_credit_ratings_by_identifier` | Yes | Agency, rating, outlook, action | `borrower_profile`, `external_intelligence.rating_action`, `market_signals` | 1, 2, 7 |
| `get_legal_history_by_identifier` | Yes | Case list, status, severity | `market_signals`, `key_risks`, `external_data.legal_cases` | 3, 7, 8, 12, chat |
| `get_open_charges_by_identifier` | Yes | Charge holders, charge amounts, encumbrance signals | `existing_exposure`, bureau proxy exposure, `external_data.open_charges` | 6, 7 |
| `get_data_status` | Yes | Freshness dates by Probe module | `probe_summary.data_status`, `data_sources` appendix | Data Sources appendix, audit trail |

### 4.2 Optional / not in the default lean path

These are available in Probe42 v2 but intentionally not called in the default cost-optimized path.

| Probe42 tool | Default profile | Why excluded by default | If enabled, feeds |
| --- | --- | --- | --- |
| `get_gst_details_by_identifier` | No | Paid call; default CAM can proceed without it | Section 8, GST compliance corroboration |
| `get_epfo_details_by_identifier` | No | Paid call; employee/compliance can be approximated from KYC | Section 2, ESG/regulatory, employee validation |
| `get_suit_filed_cases_by_identifier` | No | Paid call; `legal_history` already gives primary litigation signal | Section 7 and deeper litigation review |
| `get_director_network_by_din` | No | High call multiplier because it expands per director | Section 2 group/management depth, group mapping |

### 4.3 Probe42 source policy

| Policy | Current behavior |
| --- | --- |
| Resolve preview | Cache first, then free search, then cheap base-details when needed |
| Full onboarding | One lean Probe bundle per entity/profile |
| Repeat reads | Serve from `storage/cache/probe42` |
| Stale Probe JSON files in document store | Removed before saving a fresh bundle |
| Probe provider label in CAM | `probe42_mcp_v2` |


## 5. Uploaded / Downloaded Document Matrix

### 5.1 Identity, legal, and request documents

| Document | Main datapoints | Source class | Fact-pack keys | CAM sections |
| --- | --- | --- | --- | --- |
| `certificate_of_incorporation.pdf` | Legal name, incorporation confirmation | Local document | Supports borrower identity | 2, Annexure A |
| `pan_card.pdf` | PAN confirmation | Local document | Supports borrower identity | 2, 8, Annexure A |
| `gst_registration_certificate.pdf` | GSTIN confirmation | Local document | Supports GST identity | 2, 8, Annexure A |
| `board_resolution_borrowing.pdf` | Borrowing authority | Local document | Compliance support | 5, 8, Annexure A |
| `request_note.pdf` | Facility purpose, request framing | Local document | `case_summary`, facility context | 5, 12 |

### 5.2 Financial documents

| Document | Main datapoints | Source class | Fact-pack keys | CAM sections |
| --- | --- | --- | --- | --- |
| `audited_financial_statements.pdf` | Revenue, EBITDA, PAT, debt, assets, equity, working capital items | Local OCR / extraction | `financial_summary`, `ratio_analysis`, `cash_flow_repayment` | 1, 4, 7, 11, 12 |
| `annual_report_fy2024.pdf` | Financials, narrative cues, governance text, segment data if present | Local OCR / extraction | `financial_summary`, `downloaded_annual_reports`, `borrower_profile` support | 2, 3, 4, 7, appendix |
| Downloaded annual reports in `downloaded document/CAM/` | Same as above, but pulled into OCR pipeline automatically | Local OCR / extraction | `downloaded_annual_reports`, RAG context | 2, 3, 4, appendix |
| `provisional_financials_fy2025.xlsx` | Latest run-rate financials | Local Excel extraction | `provisional`, trend support | 1, 4, 11, 12 |
| `debt_schedule.xlsx` | Lender-wise facilities, maturities, debt structure | Local Excel extraction | `existing_exposure`, repayment context | 5, 6, 7, 10, 12 |

### 5.3 Collateral, banking, and conduct documents

| Document | Main datapoints | Source class | Fact-pack keys | CAM sections |
| --- | --- | --- | --- | --- |
| `valuation_report.pdf` | Market value, FSV, collateral description | Local document | `collateral_analysis` | 6, 12 |
| `bank_statement_6m.pdf` | Turnover behavior, balance pattern, anomalies | Local document | Conduct support and extraction context | 10, ETB review |
| `existing_facility_details.pdf` | Existing banking lines and terms | Local document | Existing exposure support | 5, 10 |
| `sanction_letter.pdf` | Pricing, tenor, covenants, structure | Local document | Facility/covenant support | 5, 9, 10 |

### 5.4 Rating, GST, and market documents

| Document | Main datapoints | Source class | Fact-pack keys | CAM sections |
| --- | --- | --- | --- | --- |
| `credit_rating_report.pdf` | Rating, outlook, action, rationale | Local OCR / extraction | `borrower_profile`, `external_intelligence.rating_action` support | 1, 2, 7 |
| `gstr1_summary.pdf` | Sales and filing pattern | Local OCR / extraction | GST corroboration | 8, 11 |
| `gstr3b_summary.pdf` | Tax filing timeliness and turnover clues | Local OCR / extraction | GST corroboration | 8, 11 |
| `quarterly_results_q3fy2025.pdf` | Listed-company quarterly performance | Local OCR / extraction | Quarterly and trend support | 3, 4, Annexure B |
| `corporate_governance_report.pdf` | Governance disclosures | Local OCR / extraction | Governance support | 2, 7, 8 |
| `nse_live_quote.json` | Market snapshot for listed borrowers | Local file | Market context | 3, 7 |

### 5.5 Bureau and CRILC documents

| Document | Main datapoints | Source class | Fact-pack keys | CAM sections |
| --- | --- | --- | --- | --- |
| `commercial_bureau_report.pdf` | Bureau score, DPD, lender count, exposure | Local document | `external_intelligence`, risk signals | 7, 10, 12 |
| `crilc_report.pdf` | Aggregate exposure and stress flags | Local/internal mock document | `crilc_exposure`, `external_intelligence` | 7, 10, 12 |


## 6. Fact-Pack to CAM Section Mapping

This is the main consumption map from deterministic fact-pack keys into rendered CAM sections.

| CAM section | Primary fact-pack keys | Main source classes | Synthetic / derived notes |
| --- | --- | --- | --- |
| 1. Executive Summary | `case_summary`, `borrower_profile`, `financial_summary`, `policy_decisions`, `validation_exceptions` | Probe, documents, deterministic engines | Recommendation is derived, not directly sourced |
| 2. Borrower Profile | `borrower_profile`, `management_profile`, `group_profile`, `corporate_hierarchy`, `external_intelligence` | Probe base/KYC, KYC docs, hierarchy logic | Shareholding defaults to zero unless explicitly populated |
| 3. Industry and Business Analysis | `industry_analysis`, `web_crawl_news`, `market_signals`, `credit_strengths`, `key_risks` | Sector templates, web/news, Probe market/legal signals, annual reports | Industry overview and competitor set are synthetic templates |
| 4. Financial Analysis | `financial_summary`, `ratio_analysis`, `cash_flow_repayment`, `quarterly_performance` | Audited/provisional docs, Excel, deterministic ratio engine | Quarterly view is currently derived from annuals when not available |
| 5. Credit Facility Details | `facility_details`, `facility_pricing`, `drawing_power` | Request note, sanction data, deterministic pricing template | Pricing and end-use breakup are templated unless replaced by bank policy feeds |
| 6. Security and Collateral | `collateral_analysis`, `charges_data`, `existing_exposure` | Valuation report, open charges, debt schedule | `charges_data` currently uses local MCA mock path, not Probe |
| 7. Risk Assessment and Internal Rating | `policy_decisions`, `validation_exceptions`, `external_intelligence`, `market_signals`, `key_risks` | Probe, bureau, deterministic scoring, documents | Internal rating is derived from policy engine |
| 8. Compliance and Regulatory Checks | `compliance_checks`, `external_intelligence`, `pep_screening`, `esg_regulatory` | Probe, KYC docs, bureau, PEP service | Compliance checks are still light and partly templated |
| 8A. Core Banking Position | `core_banking`, `core_banking_analysis` | Internal ETB systems or mock data | Not Probe; currently mock/internal unless integrated |
| 8B. Social Media and Digital Intelligence | `social_media_analysis`, `social_media_cam_summary` | Internal social-media engine | Not Probe; currently internal intelligence path |
| 9. Terms, Conditions and Covenants | `covenant_history`, `policy_decisions`, `facility_details` | Sanction context, policy engine | Proposed covenants are derived outputs |
| 10. Account Conduct and Relationship Review | `conduct_analysis`, `existing_exposure`, `crilc_exposure`, `core_banking` | Bank statements, bureau, CRILC, ETB systems | NTB cases naturally have less real conduct data |
| 11. Peer Comparison and Benchmarking | `benchmark_summary`, `ratio_analysis`, `financial_summary` | Extracted financials plus benchmark engine | Benchmarks are deterministic pack data |
| 12. Recommendation and Approving Authority | `policy_decisions`, `credit_strengths`, `key_risks`, `collateral_analysis`, `cash_flow_repayment` | All prior sources plus policy engine | This is fully derived from prior fact-pack inputs |
| Annexure A. Document Checklist | Document store inventory | Local filesystem | Purely deterministic inventory |
| Annexure B. Quarterly Performance | `quarterly_performance` | Quarterly filings if present; else derived from annuals | Synthetic if no actual quarterly source exists |
| Data Sources appendix | `data_sources` | Probe, documents, internal systems | Explicit provenance summary |


## 7. Synthetic, Templated, or Derived Areas

These should be treated as deterministic helper outputs, not as raw sourced truth.

| Fact-pack area | Current source | Classification | Notes |
| --- | --- | --- | --- |
| `industry_analysis` | `_SECTOR_INDUSTRY` sector template map | Synthetic template | Competitors, growth drivers, headwinds are hardcoded sector packs |
| `facility_pricing` | `_build_facility_pricing()` | Synthetic template | Uses default pricing and fee assumptions |
| `quarterly_performance` | Renderer builds from annual numbers if needed | Derived synthetic | Replace with real quarterly filings for accuracy |
| `drawing_power` | Formula from receivables, inventory, payables | Derived | Useful for indicative WC assessment only |
| `web_crawl_news` fallback | Sector-specific canned articles if no crawl data | Synthetic fallback | Real crawl should replace this |
| `charges_data` | Local MCA mock function | Internal mock | Not currently sourced from Probe |
| `crilc_exposure` | Local CRILC mock plus generator | Internal mock / derived | Probe does not provide internal CRILC |
| `group_profile` shareholding percentages | Dataclass defaults | Synthetic default | Promoter/institutional/public holding remain zero unless fed |
| `social_media_analysis` | Internal engine | Internal synthetic/intelligence | Not a Probe42 feed |
| Estimated Probe financials | `_estimate_financials_from_probe()` | Derived | Used when no audited/provisional financials are parsed |


## 8. Probe vs Document Responsibility

### 8.1 Best use of Probe42

Use Probe42 for:

- company identity and status
- directors and KYC
- ratings
- legal signals
- open charges
- freshness and provenance

### 8.2 Best use of documents

Use uploaded/downloaded documents for:

- actual financial statements
- debt schedule and lender structure
- sanction terms
- valuation and collateral
- quarterly results
- governance disclosures
- board approvals

### 8.3 What should never be silently treated as "real" unless integrated

- pricing assumptions
- quarterly breakdown derived from annuals
- shareholding values left at defaults
- internal CRILC or ETB conduct when only mock data is present
- sector competitor packs and templated news


## 9. Recommended operating mode

### 9.1 Default CAM mode

Use:

- Probe42 `lean` profile
- local OCR for documents
- deterministic policy/risk engines
- chat over the cached fact pack and Probe snapshot

This gives the lowest Probe cost while preserving a complete end-to-end CAM flow.

### 9.2 Credit-ready CAM mode

For a stronger non-synthetic CAM, require:

- audited financial statements
- provisional latest financials
- debt schedule
- valuation report
- sanction/facility documents for ETB or renewal cases
- board resolution

Optional Probe upgrades beyond `lean`:

- GST details
- EPFO details
- director network
- suit-filed cases


## 10. Current implementation summary

| Area | Current truth source |
| --- | --- |
| Borrower identity | Probe42 base + KYC, backed by KYC documents |
| Directors | Probe42 KYC directors |
| Ratings | Probe42 rating API plus rating PDF where available |
| Litigation | Probe42 legal history |
| Open charges | Probe42 open charges |
| Financial ratios | Deterministic engine over extracted financial statements or estimated Probe financials |
| Recommendation | Deterministic policy engine |
| CAM narrative | Deterministic renderer over fact-pack |
| Chat | Fact-pack plus cached Probe snapshot |


## 11. Practical reading of this matrix

If a datapoint is needed for sanction defense:

- first prefer uploaded/downloaded source documents,
- then Probe42 where the data is public and current,
- then deterministic derived fields,
- and finally treat synthetic/template content as clearly secondary support only.
