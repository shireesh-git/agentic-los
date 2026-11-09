# Developer guide

How the code is organised, how a request flows through it, and how to extend it. For what the
system does in business terms, read the [user guide](USER_GUIDE.md) first.

---

## 1. Run and test

```bash
python -m venv .venv && .venv\Scripts\activate      # Windows; source .venv/bin/activate elsewhere
pip install -r requirements.txt
copy .env.example .env.local                         # API keys (never committed)
python run.py                                        # http://localhost:8001/los
python -m pytest tests -q                            # ~320 tests, offline, about 4 minutes
```

- **Tests run offline.** They use a temporary copy of `config/` and `storage/` and the mock AI
  (`tests/conftest.py`), and set `CAM_NETWORK_OFFLINE=1`, so no test calls a website or touches your
  database.
- **Server reload is off** (it hangs on Windows), so restart after a code change.
- **Snapshots:** after an *intended* change to the credit engine's output or the API, accept it with
  `python -m tests.characterization.snapshot --write` or `python -m tests.characterization.api_contract --write`,
  then review the diff.

---

## 2. Architecture in one picture

```
 Browser ──► /los (src/ui/templates/flow.html + static/js/flow/flow.js, Alpine.js)
                │  JSON over /api/flow/*  (src/api/routers/flow.py)
                ▼
         FlowService (src/flow/service.py) ── the LOS: stages, fields, chat, gates, reports
           │        │            │                 │
           │        │            │                 └─ FlowStore (SQLite: one JSON per proposal + event log)
           │        │            └─ risk.py: engine verdict, challenges + actions, deviation plan, Copilot steps
           │        └─ acquire/: 5 data agents in parallel (AgentGraph) + polite API client + document readers
           ▼
     Credit engine (src/agents/pipeline.py: 7 agents on AgentGraph)
       ingestion → PEP screening → financial analysis → validation → benchmark → policy → narrative
           │
           └─ fact pack (src/engines/cam_fact_builder.py + quality_engine.py) ─► CAM (cam_llm_renderer.py)
```

The **CAM workspace** at `/` (`src/ui/templates/index.html`, routers `cases`, `cam`, `observations`, …)
is the credit engine's own UI and API. The LOS uses the engine through the same application services,
not over HTTP.

---

## 3. Code layout

| Folder | What lives there |
|---|---|
| `src/flow/` | **The LOS.** `service.py` (the proposal life cycle), `datapoints.py` (fields: extraction from the engine, bands, confidence), `risk.py` (risk strip, challenges with actions, Copilot plan, amount check), `reports.py` (audit pack, TAT & analytics, Decision Summary), `camjob.py` (CAM progress), `copilot.py` (answers checked against the record), `cam_intake.py` + `doc_patterns.py` (reading an uploaded bank CAM), `store.py` |
| `src/flow/acquire/` | **New-prospect data acquisition.** `agents.py` (planner, 5 agents, verification), `connectors.py` (GLEIF, sanctions, GDELT, Probe42), `polite.py` (rate-limited, cached HTTP), `readers.py` (statement reader and document readers), `mapper.py` (records → borrower data) |
| `src/agents/` | The credit engine's 7 pipeline agents, plus the challenge, investigation and reassessment agents |
| `src/engines/` | Deterministic engines: ratios, validation, benchmarks, policy, observations, projections, stress, repayment, fraud signals, **quality** (debt capacity, earnings quality, revenue truth, early-warning), CAM fact pack, CAM sections and renderers |
| `src/agentic/` | `graph.py` (`AgentGraph`: parallel DAG with fan-out) and `schema.py` (structured AI output) |
| `src/application/` | Use-case services and the composition root `container.py` (builds everything once) |
| `src/api/` | FastAPI app, routers (`flow.py` = the LOS API; the rest = credit engine / CAM workspace) |
| `src/core/` | Configuration loader, AI providers (`llm_provider.py`), runtime paths |
| `src/services/` | Persistence, document store and extraction, OCR, PEP screening, Probe42 client |
| `src/rendering/` | CAM as markdown / HTML / PDF |
| `src/data/` | The borrower catalogue (real public companies and synthetic ones) |
| `src/devtools/` | Agent harness (`scripts/test_agent.py`) and demo document sets |
| `src/ui/` | `templates/flow.html` + `static/js/flow` + `static/css/flow.css` (the LOS); `index.html` + `pages/` + `static/js/modules` (CAM workspace) |
| `config/` | Everything a bank configures; see [CONFIGURATION.md](CONFIGURATION.md) |
| `tests/` | Unit and end-to-end tests; `test_flow*.py` cover the LOS; `characterization/` holds snapshots |

---

## 4. How a proposal moves

1. **Initiate.** `FlowService.create` makes the proposal document, enters the first stage, and logs a
   `created` event. A prospect also starts the acquisition agents (`_start_acquire`).
2. **Generate the CAM.** `generate_cam` runs the credit engine in a background job (`camjob.py`, live
   progress). When it finishes, `_cam_done`:
   - fills the fields (`datapoints.from_engine`);
   - builds the risk strip and challenges (`risk.assess`, `risk.challenges`);
   - builds the deviation register (`_build_register`).
3. **Act.** `act(approve | reject | send_back)` checks the stage's **gates**
   (`blockers`, configured per stage). It requires a written justification when the engine said Decline
   or a hard rule failed (`_justify`), and moves the proposal on. Every step is an event in the log.
4. **Chat.** `chat` handles pending questions, "change X to Y" edits, "what should I do next" (→
   `risk.plan`) and amount questions (→ `risk.amount_text`). Anything else goes to `copilot.ask`, whose
   figures are checked against the record.
5. **Download.** `cam_file` renders the CAM PDF with the live Decision Summary
   (`reports.decision_summary`) and embeds a data sheet, so the PDF can be read back exactly.

A proposal is **one JSON document** (`flow_cases.payload`). Its main keys:

| Key | What it holds |
|---|---|
| `dp` | The field values, each with `value`, `source` (incl. `confidence`) and `status` |
| `risk` | The engine verdict, ratios, capacity and quality |
| `against` | The challenges |
| `responses` | The answers to challenges |
| `register` | The deviations |
| `deviations` | The proceed-justifications |
| `changes` | Underwriting overrides |
| `chat` | The conversation |
| `conditions`, `sanction`, `drawdown`, `release` | Post-sanction work |
| `acquisition` | Prospect data sources |

---

## 5. The CAM

- **Sections:** `src/engines/cam_sections.py`. `CAM_SECTIONS_STREAMLINED` is the default: a Decision
  Summary plus 8 sections. `CAM_SECTIONS` is the classic 21-section layout. Choose one with
  `narrative.cam_structure`.
- **Fallback when the AI is unavailable:** a merged section without AI is rendered from the classic
  sections' templates, listed in `merge`.
- **Fixed tables:** `tables` appends deterministic tables after the AI text
  (`cam_quality_sections.py`), so decisive figures are exact.
- **Prompt changes:** bump `PROMPT_VERSION` when you change an instruction. Sections are checkpointed by
  their inputs, so a re-run rewrites only the sections whose data changed.
- **Number guard:** every figure the AI writes is checked against the data it was given. An unsupported
  figure is logged, and a routed (smaller) model's section is rewritten by the main model.

---

## 6. Extending

| To add… | Do this |
|---|---|
| A field | One line in `config/flow.yaml` → `datapoints`; to auto-fill it, one `put(...)` in `datapoints.from_engine` |
| An approval stage | `config/flow.yaml` → `stages` (+ a user); see [CONFIGURATION.md](CONFIGURATION.md) |
| A data source | `config/data_sources.yaml` → `sources`; a connector in `acquire/connectors.py` if it has an API; a reader in `acquire/readers.py` for its document |
| A calculated metric | A function in `src/engines/quality_engine.py` (add it to `build`), a field in `flow.yaml`, a `put` in `from_engine` |
| A challenge action | `_PLAYBOOK` in `src/flow/risk.py` |
| A gate | A branch in `FlowService.blockers` and its name in a stage's `gates` |

Keep the rules that make the system trustworthy:
- every value carries its source;
- every figure comes from data or a fixed formula, never from the AI;
- missing data is "not on record", never a pass;
- agents propose, and people decide.

---

## 7. Deployment

- **Docker:** `docker-compose up --build`. The volumes are `storage/`, `output/` and `runtime-db/`.
- **Google Cloud Run:** `scripts/deploy_gcp.sh` (run in Cloud Shell). Sets `LLM_ACTIVE_PROVIDER=vertex_ai_gemini`; the NVIDIA key is kept in Secret Manager so switching back is one env change. Demo data resets to the baked snapshot when the instance restarts.
- **Database:** SQLite (`runtime-db/cam_platform.sqlite3`). For production, replace it with a managed
  database. The store is a small class in `src/flow/store.py`.
