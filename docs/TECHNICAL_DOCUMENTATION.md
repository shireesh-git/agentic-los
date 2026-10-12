# Technical Documentation

> CAM Intelligence Platform — Implementation Details & Developer Guide

## 1. Source Code Organization

### 1.1 Module Map

```
src/
├── api/
│   ├── main.py               # ASGI entry point (src.api.main:app)
│   ├── app.py                # create_app(): middleware, static files, routers, error mapping
│   ├── dependencies.py       # FastAPI dependency providers
│   └── routers/              # 11 routers, one per area (85+ routes incl. SSE run-stream)
├── application/              # Use-case services: company, case, cam, approval, document workspace
│   ├── container.py          # Composition root (wires state + services)
│   └── errors.py             # Application errors → HTTP status codes
├── agents/
│   ├── base_agent.py         # Agent contract (requires / waits_for / critical / run)
│   ├── pipeline.py           # Orchestrator (SuperAgent): runs the 7 agents, independent ones in parallel
│   ├── ingestion_agent.py, screening_agent.py, analysis_agents.py, narrative_agent.py
│   ├── financial_overrides.py # RM-uploaded figures override the public baseline
│   └── dashboard_360_agent.py # 360° company view aggregator
├── rendering/                # CAM markdown→HTML, CAM PDF, CRILC PDF
├── engines/
│   ├── credit_assessment.py  # Single definition: validation → benchmarks → policy decision
│   ├── approval_policy.py    # Delegation-of-powers matrix + workflow state machine
│   ├── ratio_engine.py       # 20+ financial ratio computations
│   ├── benchmark_engine.py   # Sector benchmarking with RAG classification
│   ├── validation_engine.py  # Cross-document data validation
│   ├── policy_engine.py      # Credit policy rule evaluation
│   ├── fraud_detection_engine.py  # Multi-signal fraud analysis
│   ├── etb_analytics_engine.py    # ETB behavior analysis
│   ├── cam_fact_builder.py   # Fact pack assembly (38 keys)
│   ├── cam_renderer.py       # LEGACY v1 template renderer (tests only)
│   ├── cam_renderer_v2.py    # Template CAM renderer used by the app (with annexures)
│   ├── cam_llm_renderer.py   # LLM narrative: sections in parallel on hosted LLMs, checkpointed
│   ├── cam_sections.py       # CAM prompts: SYSTEM_PROMPT, CAM_SECTIONS, PROMPT_VERSION
│   ├── cam_one_pager.py      # Executive summary one-pager
│   ├── core_banking_engine.py # Core banking analytics
│   ├── social_media_engine.py # Social/digital intelligence
│   ├── document_downloader.py # NSE/BSE document fetcher
│   ├── document_ocr_engine.py # OCR (PyMuPDF + Gemini Vision)
│   └── crilc_report_generator.py # RBI CRILC report PDF
├── models/
│   └── canonical_model.py    # Dataclass-based canonical data model
├── services/
│   ├── analyst_chat.py       # LLM-powered financial advisor chat
│   ├── company_onboarding.py # CIN/PAN company onboarding workflow
│   ├── corporate_hierarchy.py # Group structure service
│   ├── dms_service.py        # Document management service
│   ├── document_classifier.py # 13-category document classifier
│   ├── document_extractor.py # PDF/Excel/JSON/CSV extraction
│   ├── document_operations.py # File I/O operations
│   ├── document_store.py     # Document metadata store
│   ├── external_systems.py   # External API integration layer
│   ├── ocr_service.py        # OCR service abstraction
│   ├── pep_service.py        # PEP/sanctions/adverse media screening
│   ├── persistence.py        # SQLite persistence (cases, runs, checkpoints, workflow)
│   ├── cam_checkpoints.py    # Per-section CAM checkpoints (resume after failure)
│   ├── probe_mcp_client.py   # External data provider client
│   ├── probe_service.py      # Data provider orchestration
│   └── web_crawl_service.py  # News/web intelligence
├── data/
│   ├── company_catalog.py    # Company registry and seeding
│   ├── synthetic_companies.py # 4 synthetic test companies
│   ├── real_companies.py     # 18 real Indian corporate profiles
│   ├── sector_kpis.py        # Sector-specific KPI definitions
│   └── mock_external_apis.py # API response stubs
├── core/                     # Configuration, logging, utilities
└── ui/
    ├── templates/
    │   └── index.html        # Alpine.js SPA (single-page)
    └── static/js/
        ├── app.js            # camApp(): shared state, start-up, navigation, API helper
        └── modules/          # One file per page (summary, journey, pipeline, case-detail,
                              #   documents, reports, approvals, settings) + formatters
```

### 1.2 Key Entry Points

| Entry Point | File | Purpose |
|-------------|------|---------|
| Application start | `run.py` | Configures and starts uvicorn server |
| HTTP API | `src/api/routers/` | Endpoints, one router per area |
| Pipeline trigger | `CaseService.run()` → `SuperAgent.execute_pipeline()` | Full CAM generation |
| Company seed | `company_catalog.py` → `seed_company_store()` | Loads test companies |

## 2. Canonical Data Model

All data flows through dataclass objects defined in `src/models/canonical_model.py`:

### 2.1 Primary Entities

```python
@dataclass
class Borrower:
    entity_id: str          # e.g., "INFY001"
    company_name: str
    cin: str                # Corporate Identity Number
    pan: str
    sector: str
    incorporation_date: str
    listing_status: str     # "listed" | "unlisted"
    nse_symbol: str
    bse_code: str
    isin: str
    registered_address: str
    # ... additional fields

@dataclass
class FinancialStatement:
    period: str             # e.g., "FY2024"
    period_type: str        # "audited" | "provisional"
    line_items: dict        # 35+ standardised financial line items
    # Key line items: revenue_operating, ebitda, pat, total_assets,
    # total_debt, net_worth, current_assets, current_liabilities,
    # operating_cash_flow, capex, depreciation, interest_expense, etc.

@dataclass
class FacilityRequest:
    facility_type: str      # "TERM_LOAN" | "WORKING_CAPITAL" | "BG" | "LC"
    amount_cr: float        # Requested amount in ₹ Crores
    tenor_months: int
    purpose: str
    security_offered: str
```

### 2.2 Financial Line Items (Standardized)

All financial statements use a canonical set of 35+ line items in ₹ Crores:

| Category | Key Fields |
|----------|-----------|
| Revenue | `revenue_operating`, `other_income`, `total_revenue` |
| Expenses | `cogs`, `employee_cost`, `other_expenses`, `total_expenses` |
| Profitability | `ebitda`, `ebit`, `pbt`, `pat`, `comprehensive_income` |
| Balance Sheet | `total_assets`, `net_worth`, `total_debt`, `goodwill` |
| Working Capital | `current_assets`, `current_liabilities`, `inventory`, `receivables`, `payables` |
| Cash Flow | `operating_cash_flow`, `investing_cash_flow`, `financing_cash_flow`, `capex` |
| Debt | `long_term_debt`, `short_term_debt`, `interest_expense` |
| Equity | `share_capital`, `reserves`, `minority_interest` |

## 3. Engine Implementation Details

### 3.1 Ratio Engine (`ratio_engine.py`)

**Input:** `FinancialStatement` objects (3-year historical + optional provisional)

**Process:**
1. Extract line items from each period
2. Compute ratios using standardized formulas
3. Calculate YoY trend and direction
4. Assign RAG status based on sector thresholds

**Output:** Dictionary of `RatioResult` objects with:
- `value`: Computed ratio value
- `trend`: "improving" | "stable" | "deteriorating"
- `yoy_change`: Percentage change from prior period
- `rag_status`: "green" | "amber" | "red"

### 3.2 CAM Fact Builder (`cam_fact_builder.py`)

**Input:** Complete company data + engine outputs

**Process:**
1. `build_cam_fact_pack()` orchestrates assembly of 38 fact-pack keys
2. Each key is built by a specialized builder function:
   - `_build_cover_data()` — Company identity & metadata
   - `_build_financial_summary()` — 3-year financial tables with trends
   - `_build_ratio_analysis()` — Ratio results with RAG classification
   - `_build_industry_analysis()` — 10-sector revenue segmentation + SWOT
   - `_build_quarterly_performance()` — Q1-Q4 with seasonal weighting
   - `_build_compliance_checks()` — 6-7 compliance items with severity
3. Revenue segments auto-compute `revenue_cr` from GST turnover data
4. All monetary values normalized to ₹ Crores

**Output:** JSON-serializable fact pack dictionary

### 3.3 CAM LLM Renderer (`cam_llm_renderer.py`)

**Input:** Fact pack JSON + LLM provider configuration

**Process:**
1. For each of 14 LLM sections:
   - Take the section prompt from SYSTEM_PROMPT / CAM_SECTIONS in src/engines/cam_llm_renderer.py
   - Inject relevant fact-pack data as context
   - Call LLM with `max_tokens_per_section=2500`, `temperature=0.15`
   - Stream response via SSE for real-time UI updates
2. Merge LLM sections with 7 template-rendered sections
3. Apply section numbering and cross-references

**LLM Configuration:**
- `max_tokens`: 16000 (total)
- `max_tokens_per_section`: 2500
- `temperature`: 0.15 (low creativity for factual accuracy)

## 4. API Implementation

### 4.1 Pipeline SSE Endpoint

The pipeline endpoint (`POST /api/cases/{id}/run`) uses Server-Sent Events for real-time progress:

```
Event Stream:
  → pipeline_start       {total_stages: 7}
  → agent_start          {agent: "DataGatherAgent", stage: 1}
  → agent_progress       {message: "Fetching MCA data..."}
  → agent_complete       {agent: "DataGatherAgent", duration_ms: 1500}
  → section_start        {section: "Executive Summary", index: 3}
  → section_complete     {section: "Executive Summary", duration_ms: 4200}
  → ...
  → pipeline_complete    {recommendation, risk_grade, composite_score}
```

### 4.2 In-Memory Stores

The application uses in-memory dictionaries for fast access (POC-grade):

| Store | Key | Value | Purpose |
|-------|-----|-------|---------|
| `company_store` | entity_id | Company data dict | Active company data |
| `case_store` | entity_id | Case run results | Latest pipeline output |
| `extraction_store` | entity_id | Extraction results | Document extraction cache |
| `etb_store` | entity_id | ETB analysis | ETB analytics cache |
| `fraud_store` | entity_id | Fraud analysis | Fraud detection cache |

### 4.3 Persistence Layer (`persistence.py`)

SQLite database (`runtime-db/cam_platform.sqlite3`) with 4 tables:

```sql
-- Company registry
CREATE TABLE companies (
    entity_id TEXT PRIMARY KEY,
    company_name TEXT,
    catalog_source TEXT,
    is_seeded BOOLEAN,
    payload_json TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- CAM run history
CREATE TABLE case_runs (
    run_id TEXT PRIMARY KEY,
    entity_id TEXT,
    company_name TEXT,
    recommendation TEXT,
    risk_grade TEXT,
    composite_score REAL,
    run_at TIMESTAMP,
    payload_json TEXT
);

-- Section-level comments
CREATE TABLE case_comments (
    run_id TEXT,
    section_id TEXT,
    comment_text TEXT,
    updated_at TIMESTAMP
);

-- User management (future)
CREATE TABLE app_users (
    user_id TEXT PRIMARY KEY,
    username TEXT,
    role TEXT,
    created_at TIMESTAMP
);
```

## 5. Frontend Architecture

### 5.1 Alpine.js SPA

The frontend is a single-page application using Alpine.js with no build step:

- **Template:** `src/ui/templates/index.html` (shell) plus one file per page in `src/ui/templates/pages/`, inlined by `render_spa()` when the page is served; Alpine.js directives
- **Logic:** `src/ui/static/js/app.js` — shared state, start-up, navigation and the API
  helper. Page code lives in `src/ui/static/js/modules/*.js`; each file defines a function
  returning methods that `camApp()` merges into the single Alpine component, so `this` in a
  module is the whole component. The page loads the modules before `app.js`.
- **Data loading:** the URL hash drives page loads (`navigate()` → `onHash()` → `loadPage()`).
  Company/case lists fetched in the last 10 s are reused while navigating; actions that
  change data reload them.
- **Forms:** mandatory fields use `<label class="required">` (red label and asterisk).
  Borrower, amount and purpose on the CAM Journey are dropdowns fed by `GET /api/companies`.
- **Styling:** light theme with CSS custom properties (`dashboard.css`)

### 5.2 Key Pages

| Page | Route (SPA) | Description |
|------|-------------|-------------|
| Summary | `#summary` | Executive portfolio view: headline numbers, risk / status / sector breakdowns, proposals needing attention; a row opens a side-panel preview |
| Cases | `#cases` | Every borrower with grade, score, system view, status and last run; search; run / re-run |
| Borrower workspace | `#case/{id}/{tab}` | Sticky header (amount, grade, score, status, authority, run picker) and tabs: Overview, CAM, One-pager, 360° view, Risk checks, Documents, Ask AI, Decision, Runs |
| Run CAM | `#pipeline` | Run the pipeline for a borrower and follow each step live (SSE) |
| Approvals | `#approvals` | Cases waiting for a chosen authority level |
| CAM Journey | `#onboard` | Guided creation of a new case (opened from *+ Create New CAM*) |
| Settings | `#settings` | LLM, engines, benchmarks, policy rules |

### 5.3 Real-time Updates

Pipeline progress is rendered via SSE `EventSource`:

```javascript
const source = new EventSource(`/api/cases/${entityId}/run`);
source.addEventListener('section_complete', (e) => {
    const data = JSON.parse(e.data);
    camBuildSections.push({ name: data.section, status: 'done' });
});
```

## 6. Configuration System

### 6.1 YAML Configuration Files

| File | Purpose | Hot-reload |
|------|---------|-----------|
| `config/settings.yaml` | Global settings (port, debug, storage paths) | Yes |
| `config/llm_providers.yaml` | LLM provider configs (model, endpoint, keys) | Yes |
| `config/benchmarks.yaml` | Sector benchmark thresholds | Yes |
| `config/rules.yaml` | Policy rules and validation triggers | Yes |
| `config/external_apis.yaml` | External API endpoints and timeouts | Yes |

### 6.2 LLM Provider Configuration

```yaml
providers:
  vertex_ai_gemini:
    model: gemini-2.0-flash
    location: us-central1
    max_tokens: 16000
    temperature: 0.15
  ollama:
    model: qwen2.5:32b
    endpoint: http://localhost:11434
    max_tokens: 16000
  mock:
    # Template-based, no LLM calls
```

## 7. Testing

### 7.1 Test Structure

```
tests/                          # pytest, offline (mock LLM, Probe42 off, temp copies of config/storage)
├── conftest.py                 # Isolates runtime paths before any src import
├── characterization/           # Golden snapshots: pipeline output per company + API contract
├── test_pipeline.py            # Engine-level tests on synthetic companies
├── test_single_assessment.py   # Case record and CAM share one credit decision
├── test_cam_checkpoints.py     # Section checkpoints / resume after a failed run
├── test_approval_policy.py     # Delegation matrix and workflow transitions
├── test_approval_api.py        # Maker-checker flow through the API
├── test_persistence_runs.py    # Run tracking, checkpoints, run-scoped edits
├── test_llm_provider.py        # Ollama context sizing, reasoning cleanup
└── test_document_downloader.py # Document download tests

scripts/
└── test_e2e_full.py            # Manual E2E against a running server (all screens)
```

### 7.2 Test Coverage

| Test Category | Count | Status |
|--------------|-------|--------|
| Unit tests (pytest) | 26 | All passing |
| API endpoint tests | 29 | All passing |
| Pipeline E2E (synthetic) | 4 companies | All passing |
| Pipeline E2E (real data) | 2 companies (INFY001, APOL001) | All passing |
| LLM pipeline E2E | 1 company (INFY001) | Passing |

### 7.3 Postman Collections

API testing collections in `postman/`:

| Collection | Purpose |
|-----------|---------|
| CAM Full Suite | Complete API test suite (34+ requests) |
| CAM NTB Flow | New-to-bank onboarding flow |
| CAM ETB Flow | Existing-to-bank flow |
| CAM External Data | External API mock testing |

## 8. Deployment

### 8.1 Docker Image

```dockerfile
# Multi-stage build, python:3.11-slim
# Non-root user: camuser
# Exposed port: 8000
# Health check: GET /api/health
```

### 8.2 Google Cloud Run

- **Region:** asia-south1
- **Memory:** 2 GiB
- **CPU:** 2 vCPU
- **Timeout:** 300s
- **Min instances:** 0 (scale to zero)
- **Max instances:** 2
- **Storage:** GCS Cloud Storage FUSE volume at `/app/runtime-db`
- **LLM:** Vertex AI with Application Default Credentials
- **Model location:** us-central1 (Gemini 2.0 Flash not available in asia-south1)

### 8.3 Environment Variables

| Variable | Purpose | Required |
|----------|---------|----------|
| `GOOGLE_CLOUD_PROJECT` | GCP project ID | Production |
| `GOOGLE_API_KEY` | Gemini API key (local dev fallback) | Local dev |
| `CAM_PORT` | Server port override | Optional |
| `CAM_DEBUG` | Debug mode | Optional |

## 9. Known Limitations (POC)

- In-memory stores are not horizontally scalable (single instance)
- SQLite is not suitable for concurrent multi-user production
- Document storage is file-system based (not object storage)
- No authentication/authorization in current implementation
- LLM responses may vary across runs (controlled via low temperature)
- External API integration uses mock/reference data for most sources
