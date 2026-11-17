# Developer guide

How the code is organised, where data comes from, how to test, deploy and extend it, and what comes next. For what
the system does in business terms, read the [user guide](USER_GUIDE.md); for settings, [configuration](CONFIGURATION.md).

---

## 1. Run and test

```bash
python -m venv .venv && .venv\Scripts\activate      # Windows; source .venv/bin/activate elsewhere
pip install -r requirements.txt
copy .env.example .env.local                         # GOOGLE_API_KEY for Gemini (never committed)
python scripts/fetch_borrower_documents.py           # the listed borrowers' latest filings (not in git, ~390 MB)
python run.py                                        # http://localhost:8001/los
python -m pytest tests -q                            # ~400 tests, offline, ~3 minutes
```

- **Tests run offline** on a temporary copy of `config/` and `storage/` (without the fetched filings — a fresh clone
  has none) with the mock AI and `CAM_NETWORK_OFFLINE=1` (`tests/conftest.py`).
- **Server reload is off** (it hangs on Windows): restart after a code change.
- **Snapshots:** after an intended change to the engine's output or the API, accept it with
  `python -m tests.characterization.snapshot --write` / `python -m tests.characterization.api_contract --write`
  and review the diff.

---

## 2. Architecture

```
 Browser ──► /los (src/ui/templates/flow.html + static/js/flow/flow.js, Alpine.js)
                │  JSON over /api/flow/*  (src/api/routers/flow.py)
                ▼
         FlowService (src/flow/service.py) ── stages, fields, chat, gates, reports, CAM job
           │        │            │              │                 │
           │        │            │              │                 └─ FlowStore (SQLite: one JSON per proposal + events)
           │        │            │              └─ graph.py: knowledge graph (connections, group exposure)
           │        │            └─ risk.py: verdict, challenges + decision, deviation plan, Copilot steps
           │        └─ acquire/: 5 data agents in parallel + polite API client + document readers
           ▼
     Credit engine (src/agents/pipeline.py, 7 agents on AgentGraph)
       ingestion → PEP screening → financial analysis → validation → benchmark → policy → narrative
           │
           └─ fact pack (src/engines/cam_fact_builder.py, quality_engine.py) ─► CAM (cam_llm_renderer.py)

     Borrower records: data/borrowers/<ID>.json ── src/data/borrowers.py ──► the companies registry
     Credit data mart: src/core/mart.py ──► BigQuery (tables + property graph) or storage/mart/*.jsonl
```

The CAM workspace at `/` (`index.html`, routers `cases`, `cam`, `observations`, …) is the engine's own UI; the LOS
calls the engine through the same application services (`src/application/container.py` builds everything once).

| Folder | What lives there |
|---|---|
| `src/flow/` | The LOS: `service.py` (proposal life cycle), `datapoints.py` (fields, bands, confidence), `risk.py` (challenges, decision, Copilot plan), `graph.py` (knowledge graph), `checks.py` (mandatory checks), `test_packs.py`, `reports.py`, `copilot.py`, `cam_intake.py` (reading a bank CAM), `store.py` |
| `src/flow/acquire/` | New-to-bank data acquisition: `agents.py` (planner, 5 agents, verification), `connectors.py` (GLEIF, OFAC/UN, GDELT, Probe42), `polite.py`, `readers.py` (statements, rating, MCA, bureau, GST, bank, KYC), `mapper.py` |
| `src/agents/`, `src/engines/` | The credit engine: pipeline agents; ratios, validation, policy, quality, limit assessment, notes reader, projections, stress, CAM sections and renderers |
| `src/data/` | `borrowers.py` (data file ⇄ canonical records), `company_catalog.py` (the registry), `demo_registry.py` — **no borrower data** |
| `src/core/` | Configuration, AI providers (`llm_provider.py`), runtime paths, the mart |
| `src/services/` | Persistence, document store and extraction, OCR, PEP screening, Probe42 client, DMS |
| `config/` | Everything a bank configures — see [CONFIGURATION.md](CONFIGURATION.md) |
| `data/` | `borrowers/<ID>.json` (one record per borrower), `reference/pep_watchlist.json` (demo, fictional) |

---

## 3. Data: borrowers, documents, provenance

**No borrower data lives in code.** A borrower is `data/borrowers/<ID>.json`; `src/data/borrowers.py` turns it into
canonical records (`src/models/canonical_model.py`) using the dataclass type hints — plain JSON, ISO dates, enum
values. The app loads every file at start; a record saved in the database (a new-to-bank prospect, a manual entry)
is added but never replaces a data file. Reference data that is not about one borrower is configuration
(`sector_profiles.yaml`, `benchmarks.yaml`, `rules.yaml`) or `data/reference/`.

| Data | Real or demo | Source |
|---|---|---|
| Audited statements (FY2024–FY2026) | **Real** | Read from the annual reports by `scripts/read_fy2026_statements.py` (provenance in `latest_statement_source`) |
| External rating | **Real** | Read from the rating rationale on file |
| Name, CIN, registered office, auditor, board (DINs), shareholding | **Real** | Read from the annual report by `read_identity_from_reports.py` |
| Collateral, conduct, existing exposure, covenants, CRILC, KYC / GST / bank / bureau documents | Demo | Bank-internal; labelled demo on screen |
| Bureau / MCA / registry checks | Demo | `storage/demo_registry/<ID>.json` until the APIs are connected: written from the data file by `refresh_demo_documents.py` (MCA from the record, conduct classified as SMA, an indicative bureau rank from the external rating — `data_sources.yaml` → `bureau_by_rating`) |
| Five synthetic borrowers (ABC, Bharat, Omega, Pinnacle, Sunrise) | Demo | Fictional, internally consistent |

**Documents** are in `storage/documents/<ID>/<category>/`. The listed borrowers' FY2026 annual reports and quarterly
results are fetched (`config/borrower_documents.yaml`, `scripts/fetch_borrower_documents.py`, not committed); rating
rationales are committed (`scripts/save_rating_rationales.py`); demo documents are generated from the record
(`scripts/refresh_demo_documents.py`). New-to-bank test packs are in `test-documents/<borrower>/` (`prepare.py`
downloads the public reports and generates the demo documents).

**Refreshing a listed borrower** when a new annual report is out: add its URL to `borrower_documents.yaml` →
`fetch_borrower_documents.py` → `read_fy2026_statements.py <ID>` → `read_identity_from_reports.py <ID>` (CIN,
registered office, auditor, board with DINs, shareholding — each kept only if the report prints it) →
`refresh_demo_documents.py <ID>` → `validate_test_data.py` (every identity fact against the report) → run the tests
and accept the snapshot.

**What is never on a real borrower's record:** a PAN or GSTIN (not in any public filing; the bank takes it at
KYC), a director's personal net worth or PAN, news headlines (the live news feed provides them), quarterly figures or
operating KPIs without the document they come from. `validate_test_data.py` fails on any of these.

---

## 4. How a proposal moves

1. **Initiate.** `FlowService.create` makes the proposal and enters the first stage. A new-to-bank prospect gets
   `acquisition: pending`; nothing runs yet (one prospect record per company: same CIN or name → same record).
2. **Generate the CAM.** For a prospect, `generate_cam` first runs the data agents (`_request_cam` →
   `_start_acquire`); `_after_acquire` starts the CAM job once the minimum data is in (`_can_generate`), else says what
   is missing (and offers the test pack). The CAM job (`camjob.py`) runs the engine; `_cam_done` fills the fields,
   builds the risk view, challenges and deviation register. `upload_cam` ingests a bank CAM instead and runs the
   agents in the background.
3. **Act.** `act(approve | reject | send_back)` checks the stage's gates (`blockers`) and requires a written
   justification against a Decline or a failed hard rule. Every step is an event.
4. **Chat.** Pending questions, "change X to Y" edits, "what should I do next" (`risk.plan`), amount questions;
   anything else goes to `copilot.ask`, whose figures are checked against the record.

A proposal is one JSON document (`flow_cases.payload`): `dp` (fields with source and status), `risk`, `against`
(challenges), `responses`, `register` (deviations), `changes` (overrides), `chat`, `acquisition`, `conditions`,
`sanction`, `drawdown`, `release`.

---

## 5. Agents and readers

- **Data agents** (`acquire/agents.py`): Identity & Registry, Financials, Credit & Banking, Compliance, Market &
  Reputation run in parallel (`AgentGraph`). Each source is API first (`data_sources.yaml`), else the document the RM
  uploads, else the demo registry; a verification agent cross-checks CIN, PAN, statements, GST and bank against
  revenue, bureau against the balance sheet, sanctions and adverse media.
- **Statement reader** (`readers.read_financial_statements`): finds the standalone balance sheet, P&L and cash flow,
  reads them by layout, and has **Gemini read the same pages as a PDF** (`vision_statements`). Both readings must
  reconcile and be plausible; agreement → "layout, confirmed by AI"; disagreement → the page reading is used and the
  difference kept (`cross_check`); a field the page reading omitted is filled from the layout reading. The text-only
  AI reading is the last resort.
- **Knowledge graph** (`graph.py`): companies, people and lenders linked by directorships, holdings and lending;
  entity resolution by CIN / DIN / name (initials-aware, DIN-conflict guard); checks for connected parties in stress,
  group exposure against Tier 1 limits (`exposure.yaml`) and connected lending.
- **Credit data mart** (`src/core/mart.py`): proposals, fields, checks, challenges, deviations, events and the graph
  to BigQuery every minute when something changed (`MART_BQ_DATASET`), or JSON lines locally.

---

## 6. Extending

| To add… | Do this |
|---|---|
| A borrower | A file in `data/borrowers/` (copy one); its filings in `borrower_documents.yaml` |
| A field | One line in `config/flow.yaml` → `datapoints`; to auto-fill it, a `put(...)` in `datapoints.from_engine` |
| An approval stage | `config/flow.yaml` → `stages` (+ a user) |
| A data source | `config/data_sources.yaml`; a connector in `acquire/connectors.py`; a reader in `acquire/readers.py` |
| A calculated metric | A function in `src/engines/quality_engine.py`, a field in `flow.yaml`, a `put` in `from_engine` |
| A challenge's decision or options | `_DECISION` / `_PLAYBOOK` in `src/flow/risk.py` |

Keep the rules that make it trustworthy: every value carries its source; figures come from data or a fixed formula,
never from the AI; missing data is "not verified", never a pass; agents propose, people decide.

---

## 7. Deployment (Google Cloud Run)

From Cloud Shell, signed in with the project account: `git pull && bash scripts/deploy_gcp.sh`. The script fetches the
test packs' and borrowers' public filings, builds the image (which pre-reads every borrower's documents into the
extraction cache), deploys `kpmg-agentic-los` in `asia-south1` with Gemini on Vertex AI (global endpoint), the state
bucket (database and uploads copied every minute) and the BigQuery mart. Docker locally: `docker-compose up --build`.

---

## 8. Next steps

**For the bank build**
- **Document AI** (not enabled in the project): the Bank Statement Parser and OCR for scanned documents; the Custom
  Extractor if the bank wants managed per-field confidence and a human-review queue.
- **Lender statements:** a schema for banks and NBFCs (deposits, advances, CRAR, NPAs) and lender ratios in the CAM.
- **Benchmark** the readers (layout, Gemini on text, Gemini on pages, Document AI) against hand-checked figures.
- Real feeds: bureau (CIC / Probe42), MCA charges and director network, RBI defaulter lists, CRILC, Account
  Aggregator; a licensed PEP database; core banking push at disbursement.
- Production platform: managed database, single sign-on and entitlements, a message queue for the background jobs.

**Product roadmap** — risk-based pricing (RAROC); change-only CAM for renewals; credit policy → rules agent; borrower
document portal; covenant and early-warning monitoring after disbursement; portfolio-aware origination; a learning
loop from outcomes; Gemini Enterprise as the front end and Conversational Analytics on the mart.

**Known limits of the proof of concept:** SQLite and one server process; demo sign-in; disbursement simulated;
policy limits and delegation of powers (`rules.yaml`, `approval.yaml`) are placeholders until the bank supplies its
own.
