# Agentic Corporate LOS + CAM Intelligence Platform

> A proof-of-concept corporate-lending platform. An **agentic Loan Origination System (LOS)**
> takes a credit proposal from prospect sourcing to disbursement. AI agents populate it from
> the borrower's documents and the **CAM credit-intelligence engine**; people verify by
> exception and take every decision.

| | URL | What it is |
|---|---|---|
| **Corporate LOS** | `http://localhost:8001/los` | Workflow, agents, verification, decisions, documents, MIS |
| CAM workspace | `http://localhost:8001/` | The credit-intelligence engine: pipeline, CAM, analytics |

## Documentation

| Reader | Start here |
|---|---|
| Bank SME: credit, risk, operations | [**Functional Guide**](docs/FUNCTIONAL_GUIDE.html): the process flow, who does what, what agents prepare, what you verify |
| User / trainer | [**Journey Walkthrough**](docs/JOURNEY_WALKTHROUGH.html): one loan step by step: sign in, what to click and enter, where it goes next |
| Enterprise architect | [**Technical Architecture**](docs/TECHNICAL_ARCHITECTURE.html): multi-agent parallel execution, populate → verify → lock, LLM layer, governance, path to production |
| Architect / developer | [**Agent Orchestration**](docs/AGENT_ORCHESTRATION.html): what triggers the agents, the master agents, who hands off to whom, how a run ends |
| Presenter | [POC Demo Script](docs/POC_DEMO_SCRIPT.md): a new prospect from documents to Exit, step by step |
| Developer | [Developer Guide](docs/DEVELOPER_GUIDE.md) (code, data model, extending) · [LOS API Reference](docs/LOS_API_REFERENCE.md) |
| Programme | [POC Build Plan](docs/POC_BUILD_PLAN.md) (sprints S1–S6, all built) · [Roadmap](docs/ROADMAP.md) (what remains) |
| Requirements | [clientspec.md](clientspec.md): the client specification baseline (GAP ids referenced in code and tests) |

Background: [docs/planning/](docs/planning/) holds the gap analyses behind the POC, and [docs/cam-engine/](docs/cam-engine/) holds
reference notes on the CAM engine (datapoint sources, credit observations, the agent harness and the CAM workspace screens).
Open the `.html` guides directly in a browser; they need no server or internet connection.

## What the LOS does

- **Five stages, 31 steps:** Prospect Sourcing → In-Principle → Application Processing → Post
  Sanction → Disbursement, with maker–checker controls, SLAs and an append-only audit trail.
- **Agents populate.** A preparation agent runs at each maker step, in parallel lanes:
  - document intake (per document, with vision for scanned pages);
  - due-diligence checks (per check);
  - the credit case (the CAM pipeline);
  - reconciliation agents, one per workspace (CMA, parties, securities, exposure, rating, pricing,
    conduct, narrative);
  - later-stage intake (signed sanction letter, facility agreement, drawdown request).
- **People verify by exception.** Every value carries document, page and confidence. A verify
  queue pre-ticks high-confidence values for a bulk confirm, and flags conflicts,
  decision-driving fields and AI drafts for individual review. Overrides re-run the credit case.
- **People decide.** No agent can submit, approve, return, sanction or disburse. A remark is
  required on every decision.
- **Measured.** The Management MIS shows the share of fields auto-populated, verified and
  accepted unchanged, and the values nobody had to type.

## Run it

```bash
python -m venv .venv && .venv\Scripts\activate     # Windows (source .venv/bin/activate elsewhere)
pip install -r requirements.txt
cp .env.example .env.local                          # API keys; never committed
python run.py                                       # http://localhost:8001/los
```

- The port is `server.port` in `config/settings.yaml`. Uvicorn reload is off because it hangs on
  Windows, so restart after code changes.
- On first start the demo pipeline is seeded with seven applications.
- Sign-in is a demo picker (group → user → role) with no passwords.
- **Administration → Reset demo** (as *LOS Administrator*) re-seeds the pipeline.

For the POC journey, write the fictional prospect's documents and follow the
[demo script](docs/POC_DEMO_SCRIPT.md):

```bash
python scripts/make_demo_documents.py demo_documents
```

### LLM provider

All AI calls go through `config/llm_providers.yaml` (`active_provider`).

| Provider | Setup | Notes |
|---|---|---|
| `nvidia_nim` (default) | `NVIDIA_NIM_API_KEY` in `.env.local` | OpenAI-compatible endpoint; `vision: false` |
| `anthropic`, `gemini`, `openai`, `azure` | Key in `.env.local` | Set `vision: true` with a vision model to read scanned pages |
| `ollama` | `ollama pull qwen2.5:3b` | Local, CPU. One request at a time (`max_parallel_llm: 1`); a full CAM is slow |
| `mock` | — | No AI. Every feature falls back to deterministic behaviour; used by the tests |

`max_parallel_llm` caps concurrent calls per provider, and `agentic.max_workers` in
`settings.yaml` bounds the agent thread pool.

### Docker / Cloud Run

```bash
docker-compose up --build                  # storage/, output/, runtime-db/ are mounted volumes
.\scripts\deploy_gcp_camdemo.ps1           # Google Cloud Run
```

## Tests

```bash
python -m pytest tests -q                                   # all tests (~520), offline, ~7 min
python -m pytest tests/test_poc_golden_and_e2e.py           # golden extraction set + new prospect → Exit
python -m tests.characterization.snapshot --write           # accept intended CAM-pipeline changes
python -m tests.characterization.api_contract --write       # accept intended API changes
```

Tests run on a temporary copy of `config/` and `storage/` with the mock LLM
(`tests/conftest.py`). They never touch your database or call external services.

## Project structure

```
src/
├── agentic/        Agent framework: AgentGraph (parallel DAG), critic, tool registry, LLM agent runtime
├── los/            Corporate LOS: service, workflow, intake and reconciliation agents, field store (fields/),
│                   workspaces, builders (IP Note, committee pack, letters, MIS, copilot)
├── agents/         The 7-agent CAM pipeline (on AgentGraph)
├── engines/        Deterministic engines: ratios, policy, stress, fraud, reassessment, document OCR
├── application/    Use-case services (CaseService, CompanyService, …) and the composition root
├── api/            FastAPI app and routers (/api/los/*, /api/cases/*, …)
├── core/           Configuration, LLM providers, runtime paths
├── services/       Persistence (SQLite), document store, extraction, integrations
├── rendering/      CAM markdown / HTML / PDF
├── devtools/       Demo document set and golden values
└── ui/             Alpine.js front ends (LOS at /los, CAM workspace at /)
config/             los_workflow.yaml · los_fields.yaml · llm_providers.yaml · settings.yaml · rules.yaml · …
scripts/            make_demo_documents.py · test_agent.py (CAM agent harness) · deployment · data generation
tests/              Unit, LOS, agentic, golden and end-to-end tests; characterization snapshots
docs/               Functional and technical guides, developer guide, API, POC plan, demo script, roadmap
```

## CAM Intelligence Platform

This is the credit engine underneath the LOS, and it can also be used on its own at `/`.

- **Inputs:** financial statements, KYC, bureau, MCA, GST, market and exchange data.
- **Analysis:** 14 deterministic engines (ratios, benchmarks, policy, fraud signals, PEP screening,
  stress, reassessment), run as a 7-agent pipeline on the same `AgentGraph`.
- **Output:** a 21-section CAM with LLM narrative (figure-checked), PDF and one-pager export.
- **Workflow:** maker–checker approvals against a delegation matrix.

The seeded catalogue has six companies with document packs: APOL001, INFY001, IHCL001, MFL001,
MRF001 and PNCR001. ABCE001 is a synthetic borrower. New prospects can also be created in the
LOS from their documents.

Each LLM-written CAM section is checkpointed, so a re-run after a failure reuses the finished
sections. Prompts live in `src/engines/cam_sections.py`; bump `PROMPT_VERSION` when you change
them. To check the CAM without waiting for the LLM, set `narrative.mode: template` or
`active_provider: mock`.

## License

Proprietary. All rights reserved.
