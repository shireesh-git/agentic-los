# Agentic Corporate LOS + CAM Intelligence Platform

> A demonstration corporate-lending platform: an **agentic Loan Origination System (LOS)**
> that takes a credit proposal from prospect sourcing to disbursement, built on the
> **CAM Intelligence Platform** that performs the credit analysis.

| | URL | What it is |
|---|---|---|
| **Corporate LOS** | `http://localhost:8002/los` | Workflow, decisions, documents and the copilot (this README's focus) |
| CAM workspace | `http://localhost:8002/` | The credit-intelligence engine: pipeline, CAM, analytics |

## Corporate LOS

The LOS runs five stages — **Prospect Sourcing → In-Principle → Application Processing →
Post Sanction → Disbursement** — through 25 maker-checker steps across five user groups,
including the Recommendations Committee, a Post-Rating VP review and the Disbursement VP
review (a read-only submit / rework gate).
with SLAs, an append-only audit trail and an agentic copilot.

| Capability | What it does |
|---|---|
| Configurable workflow | Groups, roles, users, stages, steps and SLAs in `config/los_workflow.yaml`; maker / checker / vp_review / allocation / committee steps; returns, rejects, reassignment, escalation |
| Governed due diligence | Fifteen-check workspace (8 API + 7 manual) with retrigger history, comments, Compliance VP exceptions and a submission gate |
| Document AI prefill | Reads the borrower's PDFs page by page and proposes 21 sourcing fields with document, page and confidence; conflicts flagged; RM accepts or edits |
| IP Note | Facts with provenance, financial snapshot, security cover, policy pre-screen; optional number-checked AI summary |
| Risk Maker workspace | Runs the CAM pipeline and presents it in 9 tabs; analyst confirm / override with reasons |
| Committee pack | Decision headline, overrides, risks, deviations, conditions, comments, AI brief; structured sanction with minutes |
| Post sanction | Conditions tracker (CP / CS, evidence, deferral, waiver, checker approval), deviation register, IP → AP comparison |
| Disbursement | Checklist (system checks + confirmations), tranche maker → checker → VP review → approver |
| Letters | Term sheet and sanction letter from the record; immutable versions |
| Copilot | Next best actions, runs preparatory tasks for the step holder, drafts return notes and document requests, answers questions from the record; never takes a decision |
| Management MIS | Pipeline, ageing, turnaround and SLA compliance, breaches by role, return rates, sanctions, copilot adoption |

**Principles:** people decide, AI proposes; every figure comes from the record and every AI
text is checked against it; every value shows its basis; every change is audited.

### Run it

```bash
python -m venv .venv && .venv\Scripts\activate     # Windows (source .venv/bin/activate elsewhere)
pip install -r requirements.txt
python run.py                                       # http://localhost:8002/los
```

The port is `server.port` in `config/settings.yaml`. Uvicorn reload is off (it hangs on
Windows), so restart after code changes. AI features use the provider in
`config/llm_providers.yaml` (NVIDIA NIM by default; set `active_provider: mock` to run
without an LLM — every feature falls back to its deterministic behaviour).

On first start the demo pipeline is seeded with seven applications at different stages;
**Administration → Reset demo** (as *LOS Administrator*) re-seeds it. Sign-in is a demo
picker (group → user → role); no passwords.

### Five-minute demo

1. **Ananya Rao (RM)** → IHCL001: complete the due-diligence workspace (*Run all API
   checks*; record the manual ones; the Compliance VP excepts the PEP match), then the
   copilot runs the document prefill; accept the high-confidence values; submit.
2. **Credit Committee Secretariat** → dashboard digest → APOL001 (SLA breached): decision pack;
   ask the copilot *"what are the main unresolved risks?"*; sanction.
3. **Farah Sheikh (POS Maker)** → INFY001: record the sanction consent and facility
   execution; waive a CP with a reason (deviation register); the copilot issues the
   sanction letter.
4. **Lakshmi Narayan (DIS Maker)** → PNCR001: record a tranche, complete the checklist; checker,
   Disbursement VP review and approver → *Exit (approved)*.
5. **Sunil Chopra (EVP)** → Management MIS.

The full walkthrough is in [LOS functional flow](docs/LOS_FUNCTIONAL_FLOW.md#6-demo-walkthrough).

### LOS documentation

| Document | Read it for |
|---|---|
| [LOS architecture](docs/LOS_ARCHITECTURE.md) | Components, data model, workflow engine, integration with the CAM engine, limits |
| [LOS functional flow](docs/LOS_FUNCTIONAL_FLOW.md) | Who does what at each stage, screens, gates, demo walkthrough |
| [LOS AI & governance](docs/LOS_AI_AND_GOVERNANCE.md) | Where AI is used, the copilot, figure checks, provenance, controls |
| [LOS API reference](docs/LOS_API_REFERENCE.md) | Every `/api/los` endpoint |

### LOS code map

```
src/los/          workflow · store · service · risk_maker · committee · sourcing · ip_note ·
                  post_sanction · letters · copilot · mis
src/api/routers/los.py         /api/los/* endpoints
config/los_workflow.yaml       groups, roles, demo users, stages, steps, SLAs
src/ui/templates/los.html      LOS shell (+ los/*.html pages); src/ui/static/js/los/los.js
tests/test_los_*.py            LOS tests (run with the whole suite)
```

---

## CAM Intelligence Platform

The credit-intelligence engine underneath the LOS. It ingests company data from multiple
sources, runs deterministic analytical engines, performs AI-powered narrative generation, and
produces a complete Credit Approval Memorandum — reducing analyst effort from days to minutes.

### Key Capabilities

- **Multi-source data ingestion** — Financial statements, KYC, bureau reports, MCA filings, GST data, market signals, NSE disclosures
- **14 analytical engines** — Ratio analysis, benchmarking, policy checks, fraud detection, ETB analytics, PEP/sanctions screening, social media intelligence
- **7-agent orchestration pipeline** — Deterministic super-agent coordinates sub-agents for data gathering, extraction, analysis, and CAM generation; agents that do not depend on each other run in parallel
- **AI-powered CAM generation** — 21-section CAM with LLM narrative commentary (14 AI sections + 7 template sections); on hosted LLMs several sections are written at once
- **Credit reassessment and composed CAM (M1–M7)** — Observations, investigations, challenges, repayment, stress test, reassessment and the 12-section banker CAM used by the LOS
- **Pluggable LLM** — switch between a local model (Ollama) and hosted models (NVIDIA NIM, Gemini, OpenAI, Anthropic, Azure) with one setting; each provider gets its own execution path (see [Pipeline execution & performance](#pipeline-execution--performance))
- **Maker-checker approvals** — Submit, approve, reject, return and recall against a delegation-of-powers matrix, with a decision history
- **Risk checks** — Fraud signals (Beneish, Altman, Benford) and PEP/sanctions screening per case
- **Financial Advisor chat** — Context-aware analyst copilot powered by LLM
- **Real-time progress tracking** — SSE-based pipeline progress with section-by-section completion
- **PDF & one-pager export** — Downloadable CAM report and executive summary memo

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, FastAPI, Uvicorn |
| Frontend | Alpine.js 3.14; one component split into page modules (`src/ui/static/js/modules/`) |
| LLM | Pluggable — Google Gemini (Vertex AI), Ollama (local), OpenAI, Anthropic, Azure |
| Database | SQLite (runtime persistence) |
| PDF | ReportLab (generation), pdfplumber (extraction) |
| OCR | PyMuPDF + Gemini Vision fallback |
| Deployment | Docker, Google Cloud Run, GCS Cloud Storage FUSE |

## Quick Start

### Prerequisites

- Python 3.11+
- An NVIDIA NIM API key (the configured LLM, `openai/gpt-oss-20b`) — or
  [Ollama](https://ollama.com) for a fully local setup; the provider is chosen by
  `active_provider` in `config/llm_providers.yaml`
- (Optional) Docker for containerized deployment

### Hosted LLM (NVIDIA NIM, default)

Put your key from [build.nvidia.com](https://build.nvidia.com) in `.env.local`:

```
NVIDIA_NIM_API_KEY=nvapi-...
```

`config/llm_providers.yaml` sets `active_provider: nvidia_nim`, which calls NIM's
OpenAI-compatible endpoint (`type: openai` with a `base_url`). CAM sections are written
`narrative.max_parallel_sections` at a time.

### Local LLM (Ollama + qwen2.5:3b)

```bash
ollama pull qwen2.5:3b      # ~1.9 GB, one-time
ollama serve                # if Ollama is not already running as a service
```

To run locally, set `active_provider: ollama` in `config/llm_providers.yaml`; it uses `model: qwen2.5:3b`, the
fastest of the tested local models (qwen2.5:3b, qwen2.5:7b, qwen3:8b, gemma4:e4b) on CPU.
For richer narrative at the cost of speed, switch to `qwen3:8b` and add `think: false` (qwen3
otherwise writes a long hidden reasoning pass before answering).

With qwen3:8b on a CPU-only laptop (16 GB RAM), a full CAM (14 LLM-written sections) was
measured at **35–50 minutes** before the Ollama optimizations below (one context size per
run, compact prompts, shorter output limits for table-led sections, keep-alive). qwen2.5:3b
should be roughly 2–3× faster — re-measure on your machine. Sections are written one at a time on Ollama. Each
section is saved as soon as it is written, so if a run fails part-way, running it again resumes
from the finished sections. Timeouts are set per section (`timeout_seconds`) and per chat reply
(`chat_timeout_seconds`).

For quick functional checks without waiting for the LLM, set `narrative.mode: template` in
the same file (or `active_provider: mock`); the CAM is then rendered from templates.

### Local Development

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\Activate.ps1 # Windows

# Install dependencies
pip install -r requirements.txt

# Local settings (API keys, Ollama host) — never committed
cp .env.example .env.local

# Run the server
python run.py
```

The application starts at **http://localhost:8001**

### Docker

```bash
docker-compose up --build
```

### Google Cloud Run

```powershell
.\scripts\deploy_gcp_camdemo.ps1
```

## Project Structure

```
├── src/
│   ├── api/
│   │   ├── main.py         # ASGI entry point (src.api.main:app)
│   │   ├── app.py          # create_app(): middleware, static files, routers, error mapping
│   │   ├── dependencies.py # FastAPI dependency providers
│   │   └── routers/        # One router per area: cases, cam, approvals, companies,
│   │                       #   onboarding, documents, analytics, external, chat, admin, system
│   ├── application/        # Use-case services between the API and the engines
│   │   ├── container.py    # Composition root: builds state and wires services
│   │   ├── state.py        # In-process caches (companies, cases, extractions, ...)
│   │   ├── company_service.py, case_service.py, cam_service.py,
│   │   ├── approval_service.py, document_workspace.py
│   │   └── errors.py       # Application errors → HTTP status codes
│   ├── los/                # Corporate LOS domain (see docs/LOS_ARCHITECTURE.md)
│   ├── agents/             # Pipeline orchestrator (pipeline.py) and one module per agent
│   ├── engines/            # Deterministic engines; credit_assessment.py is the single
│   │                       #   definition of validation → benchmarks → policy decision;
│   │                       #   cam_sections.py holds the CAM prompts, cam_llm_renderer.py
│   │                       #   writes them; cam_renderer.py is legacy (tests only)
│   ├── rendering/          # CAM markdown/HTML, CAM PDF, CRILC PDF
│   ├── models/             # Canonical data model (dataclasses)
│   ├── services/           # Integrations and persistence (SQLite, DMS, OCR, Probe42, chat)
│   ├── data/               # Company data (synthetic + real Indian corporates)
│   ├── core/               # Configuration, LLM providers, runtime paths
│   └── ui/                 # Alpine.js SPA: templates/index.html (shell) + templates/pages/ (one file per page), static/js/app.js (core
│                           #   state + navigation) and static/js/modules/ (one file per page)
├── config/                 # YAML configuration (benchmarks, rules, LLM providers, approval matrix)
├── scripts/                # Deployment, testing, and data generation scripts
├── tests/                  # Unit tests, plus characterization tests (tests/characterization)
├── postman/                # Postman collections for API testing
├── docs/                   # Architecture and technical documentation
├── documents/              # User documentation
├── storage/                # Document storage (runtime)
└── runtime-db/             # SQLite database (runtime)
```

### Layering rules

- `api/routers` only translate HTTP to service calls; no business logic.
- `application` services own state and orchestration; they raise `ApplicationError`
  subclasses, which `create_app` maps to HTTP status codes.
- `engines` are deterministic and stateless; `agents` call engines and pass results
  forward through the pipeline context.
- An agent declares `requires` (agents that must succeed first) and `waits_for` (agents
  whose result it uses if present). Agents running at the same time must not write to
  `company_data` keys another independent agent reads.
- All LLM calls — CAM sections and chat — go through `src/core/llm_provider.py`; nothing
  else talks to an LLM API directly.

### Pipeline reliability

- Every run is recorded in `pipeline_runs` (`GET /api/cases/{id}/runs`), including failures.
- Each LLM-written CAM section is checkpointed as soon as it is written. Re-running after a
  failure reuses finished sections whose inputs (data, prompt, model, settings) are unchanged.
- Prompts live in `src/engines/cam_sections.py`; bump `PROMPT_VERSION` there when they change.

### Pipeline execution & performance

Agents start as soon as their dependencies finish:

```
data_ingestion ─┬─ financial_analysis ── benchmark ─┐
                └─ validation ──────────────────────┴─ policy ─┐
pep_screening ─────────────────────────────────────────────────┴─ narrative
```

The LLM execution path follows `active_provider` in `config/llm_providers.yaml` (also
**Settings → LLM Provider**):

| | Ollama (local) | Hosted (Gemini, OpenAI, Anthropic, Azure) |
|---|---|---|
| CAM sections at once | 1 (`providers.ollama.max_parallel_sections`) | `narrative.max_parallel_sections` (4) |
| Context size | One `num_ctx` for the whole run, so the model loads once; chat reuses it | Not applicable |
| Model residency | `keep_alive` (15m) keeps it loaded between runs and chat | Not applicable |
| Timeout | Streamed: `timeout_seconds` is the longest silence allowed, so a slow but working section finishes | SDK timeouts |
| Model routing (optional) | Table-led sections on a smaller model (e.g. `qwen2.5:3b`), run first as one group, then unloaded | Same mechanism, e.g. a cheaper model |
| Rate limits / server errors | — | Retried with backoff (`max_retries`, default 4) |
| Connections | — | One client per provider, shared by parallel sections |

For every provider: section data is sent as compact JSON; `narrative.section_max_tokens`
caps output for short, table-led sections; and a section cut off at its limit is logged as
`<provider> output hit the N-token limit`. Raise that section's limit if this repeats.

| Setting | Where | Effect |
|---|---|---|
| `pipeline.parallel_agents` | `settings.yaml` | `false` runs agents one at a time |
| `narrative.max_parallel_sections` | `llm_providers.yaml` | Sections written at once (a provider may lower it) |
| `narrative.section_max_tokens` | `llm_providers.yaml` | Per-section output limits |
| `providers.ollama.keep_alive` | `llm_providers.yaml` | How long Ollama keeps the model loaded (`0` = unload) |
| `providers.<id>.max_retries` | `llm_providers.yaml` | Retries for hosted providers |
| `providers.<id>.model_routing` | `llm_providers.yaml` | `enabled`, `routes: {model: [section ids]}`, `verify_figures` |

**Model routing** (off by default). Sections listed under a route are written by that model;
the rest by the provider's `model`. Routed sections run first as one group, then that model is
unloaded, so a run switches model once and the two are never in memory together. With
`verify_figures`, every figure in a routed section must appear in the data it was given
(after rounding, or as a fraction shown in percent); otherwise the section is rewritten by
the main model, in its group. Each section's model is recorded in the progress events and the
CAM's generation metadata. Compare a few CAMs with routing on before relying on it.

Document extraction results are cached per file in `storage/cache/extractions/`, keyed by
the file's content hash, so unchanged documents are not read again after an upload or a
restart. Deleting that folder only costs one re-read.

### Tests

```bash
python -m pytest tests                                   # everything (~3 min, offline)
python -m tests.characterization.snapshot --write        # accept intended pipeline changes
python -m tests.characterization.api_contract --write    # accept intended API changes
```

Tests run against a temporary copy of `config/` and `storage/` with the mock LLM and Probe42
disabled (`tests/conftest.py`); they never touch your database or call external services.

## API Endpoints (Summary)

| Category | Endpoints | Description |
|----------|-----------|-------------|
| Summary | `GET /api/dashboard` | Executive summary: metrics and one row per proposal (`portfolio`) |
| Companies | `GET/POST/DELETE /api/companies` | Company CRUD & catalog |
| Cases | `GET/POST /api/cases/{id}` | CAM case management |
| Pipeline | `POST /api/cases/{id}/run`, `GET /api/cases/{id}/run-stream` | Run full CAM pipeline (blocking / SSE) |
| Run history | `GET /api/cases/{id}/runs` | Pipeline attempts, newest first: status, error, model, and for completed runs grade, score, recommendation, approval status, `is_current` |
| Earlier run's CAM | `GET /api/cases/{id}/cam`, `/cam-html`, `/cam-pdf`, `/one-pager`, `/comments`, `/cam-section-edits` with `?run_id=` | That run's CAM with its own comments and edits (read-only; without `run_id` = latest run) |
| Approvals | `GET /api/cases/{id}/workflow`, `POST /api/cases/{id}/workflow/{action}` | Maker-checker workflow (submit, recall, approve, reject, return) |
| Approval queue | `GET /api/approvals/queue?authority=…`, `GET /api/approvals/authority-matrix` | Cases awaiting an authority; delegation matrix |
| Documents | `GET/POST /api/companies/{id}/documents` | Document upload & management |
| Extraction | `POST /api/companies/{id}/extract` | Document data extraction |
| ETB Analytics | `POST/GET /api/companies/{id}/etb-analytics` | Existing-to-bank analysis |
| Chat | `POST /api/chat/{id}` | Financial advisor chat |
| Fraud | `POST/GET /api/companies/{id}/fraud-analysis` | Fraud detection analysis (UI: case detail → Risk Checks) |
| PEP screening | `GET /api/companies/{id}/pep-screening` | Directors against PEP/sanctions lists (UI: Risk Checks) |
| Document packs | `POST /api/companies/{id}/fetch-documents`, `GET /api/companies/supported-downloads` | Generate a company's document pack where supported |
| Verified data | `DELETE /api/companies/{id}/verified-public-data` | Remove the retained public-record snapshot |
| 360° View | `GET /api/companies/{id}/360` | Comprehensive entity view |
| Onboarding | `POST /api/onboard` | CIN/PAN-based company onboarding |
| Config | `GET/PUT /api/config/{section}` | Runtime configuration |
| LLM | `GET /api/llm/providers` | LLM provider management |
| Corporate LOS | `/api/los/*` | Sessions, applications, workflow actions, prefill, IP Note, assessment, committee, post-sanction, letters, copilot, MIS — see [LOS API reference](docs/LOS_API_REFERENCE.md) |

## Configuration

Configuration is managed via YAML files in `config/`:

- **settings.yaml** — Global platform settings, including `pipeline.parallel_agents`
- **llm_providers.yaml** — LLM provider configuration (Gemini, Ollama, OpenAI, etc.) and
  narrative settings: parallel sections, per-section output limits, Ollama keep-alive,
  retries (see [Pipeline execution & performance](#pipeline-execution--performance))
- **benchmarks.yaml** — Industry benchmark thresholds
- **rules.yaml** — Policy and validation rules
- **external_apis.yaml** — External data source configuration
- **los_workflow.yaml** — LOS groups, roles, demo users, stages, steps and SLAs (calendar days)
- **approval.yaml** — Delegation of powers (approval authority levels). The shipped values are
  placeholders; replace them with your bank's approved matrix.

Secrets and machine-specific settings go in `.env.local` (see `.env.example`).

## Test Companies

The catalog seeds 6 companies with full data and document packs: APOL001 (Apollo Hospitals), INFY001 (Infosys), IHCL001 (IHCL), MFL001 (Madras Fertilisers), MRF001 (MRF) and PNCR001 (PNC Infratech). They cover different sectors and outcomes from approve to decline. The LOS demo also uses ABCE001 (ABC Engineering & Infrastructure, a synthetic borrower). More companies can be added through onboarding (`POST /api/onboard`) or manual entry.

## Documentation

LOS: see [LOS documentation](#los-documentation) above. CAM platform:

- [Frontend ↔ Backend Integration](docs/FRONTEND_BACKEND_INTEGRATION.md) — Purpose of each screen, which control calls which endpoint, end-to-end flows
- [Architecture Reference](docs/ARCHITECTURE_REFERENCE.md) — Detailed technical architecture
- [Architecture Process Document](docs/ARCHITECTURE_PROCESS.md) — System design and data flow
- [Technical Documentation](docs/TECHNICAL_DOCUMENTATION.md) — Implementation details
- [Deployment & Storage Model](docs/DEPLOYMENT_STORAGE_MODEL.md) — Docker and cloud deployment
- [CAM Data-Point Source Matrix](docs/CAM_DATAPOINT_SOURCE_MATRIX.md) — Where each CAM field comes from
- [GCP Deployment Guide](documents/GCP_DEPLOYMENT.md) — Google Cloud Run setup
- [User Manual](documents/USER_MANUAL.md) — End-user guide

## License

Proprietary — All rights reserved.
