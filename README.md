# Agentic Corporate Lending: LOS + CAM engine

When a company asks a bank for a loan, officers collect information, write a credit report (the **CAM**)
and pass the proposal from desk to desk until the money is released. This system does the collecting,
the arithmetic and the first draft with **AI agents**, and makes every risk visible. **People still make
every decision.**

| | Address | What it is |
|---|---|---|
| **Loan origination (LOS)** | `http://localhost:8001/los` | Five officers, one chain, a chat assistant on every screen |
| **CAM workspace** | `http://localhost:8001/` | The credit engine on its own, for in-depth analysis |

## What makes it different

- **It fills in the data and shows where every figure came from.** About 40 of a proposal's 46 fields
  fill themselves from online services, uploaded documents or calculations. Each figure shows its
  source and how sure the system is of it (*confidence*).
- **It tells you how much can safely be lent.** The *sustainable limit* applies every policy ratio to
  the borrower's figures. Where a smaller amount or a longer tenor would pass, it offers that change
  in one click.
- **It checks whether the numbers can be trusted:**
  - *revenue truth*: GST and bank data against the accounts;
  - *earnings quality*: is the profit operating and cash-backed?
  - *early-warning indicators* at origination.
- **It argues against the proposal.** A *Credit Challenge Agent* lists what is wrong, why it matters and
  what to do, with buttons that act. The chat answers "What should I do next?" with concrete steps.
- **Policy is enforced, not just recorded:**
  - every policy breach is a *deviation* that needs a mitigant and the Sanctioning Authority's approval;
  - going against the engine's verdict needs a written justification;
  - a failed hard rule blocks sanction.
- **The CAM is short and decision-first.** The first page is a Decision Summary built from data, not
  AI wording, followed by 8 sections. It takes about 30 seconds to write, and a re-run rewrites only the
  sections a change affects.
- **Everything is auditable.** There is a one-click audit trail. Analytics show outcomes, rework and
  the decisions that went against the engine.

## Documentation

| If you are… | Read |
|---|---|
| New to lending systems or to this product | [User guide](docs/USER_GUIDE.md): what it does, who does what, step by step, glossary |
| Presenting it | [Demo script](docs/DEMO_SCRIPT.md): three 10-minute journeys |
| Asking "where does this number come from?" | [Data points and sources](docs/DATA_POINTS_AND_SOURCES.md): every field, API, uploaded file and formula |
| Configuring it for a bank | [Configuration](docs/CONFIGURATION.md): stages, fields, policy limits, data sources, AI model |
| A developer | [Developer guide](docs/DEVELOPER_GUIDE.md) · [API reference](docs/API_REFERENCE.md) |
| Planning what is next | [Roadmap](docs/ROADMAP.md) · [Differentiation review](docs/DATA_CAM_DIFFERENTIATION_REVIEW.md) · [Testing fix list](docs/FLOW_FIX_LIST.md) |

Reference notes on the credit engine are in [docs/cam-engine/](docs/cam-engine/). Earlier analyses are
archived in [docs/planning/](docs/planning/).

## Run it

You need Python 3.12.

```bash
python -m venv .venv
.venv\Scripts\activate                 # Windows   (macOS / Linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env.local           # put API keys here; this file is never committed
python run.py                          # then open http://localhost:8001/los
```

Sign in by picking a workspace; there is no password in this demo. Without an AI key, set
`active_provider: mock` in `config/llm_providers.yaml`. Everything still works, with template text.

**AI model:** NVIDIA NIM by default (`NVIDIA_NIM_API_KEY` in `.env.local`). Anthropic, OpenAI, Azure
OpenAI, Vertex AI Gemini and a local Ollama model are also supported. See
[Configuration](docs/CONFIGURATION.md#switch-the-ai-model).

**Docker:** `docker-compose up --build`. **Google Cloud Run:** `scripts/deploy_gcp.sh`, run in Cloud Shell (Gemini on Vertex AI; see the script header).

## Tests

```bash
python -m pytest tests -q        # about 320 tests, offline, about 4 minutes
```

Tests use a temporary copy of the configuration and data, and a mock AI. They never call a website or
touch your database.

## Project layout

```
src/flow/        The LOS: proposals, fields, risk & challenges, chat, reports (acquire/ = data agents)
src/agents/      The credit engine's agents (7-step pipeline, challenge, investigation, reassessment)
src/engines/     Fixed calculations: ratios, policy, quality, projections, stress, the CAM sections
src/api/         Web API (routers/flow.py = the LOS)
src/ui/          Screens (flow.html = the LOS, index.html = the CAM workspace)
config/          Everything a bank configures (flow.yaml, data_sources.yaml, rules.yaml, …)
storage/         Borrowers' document packs        test-documents/  Test prospect documents
tests/           Automated tests                  docs/            Documentation
```

## License

Proprietary. All rights reserved.
