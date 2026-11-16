# Agentic Corporate Lending: LOS + CAM engine

When a company asks a bank for a loan, officers collect information, write a credit report (the **CAM**) and pass
the proposal from desk to desk until the money is released. This system does the collecting, the reading of
documents, the arithmetic and the first draft with **AI agents**, and makes every risk visible. **People still
make every decision.**

| | Address | What it is |
|---|---|---|
| **Loan origination (LOS)** | `http://localhost:8001/los` | Five officers, one chain, a chat assistant (Credit Copilot) on every screen |
| **CAM workspace** | `http://localhost:8001/` | The credit engine on its own, for in-depth analysis |

## What makes it different

- **Agents gather the data and show where every figure came from.** For a new-to-bank borrower, five agents fetch
  what online services provide (LEI, sanctions, news) and read the documents the RM supplies; the statements are
  read twice — by layout and by Gemini reading the pages — and must reconcile. Every figure carries its source.
- **It says how much can safely be lent:** the sustainable limit, the working-capital assessment, and the structure
  that would pass.
- **It checks whether the numbers can be trusted:** revenue against GST and bank data, earnings quality,
  early-warning flags, the auditor's report and notes to accounts.
- **It argues against the proposal:** each key risk challenge states the decision needed and the options (reduce,
  accept with justification, ask for evidence, decline).
- **It knows who the borrower is connected to:** a knowledge graph of directors, shareholders, group companies and
  lenders checks connected parties in stress, group exposure and links to the bank's own directors.
- **Policy is enforced and everything is auditable:** deviations need a mitigant and approval, going against the
  engine needs a written justification, and an audit trail report records who decided what.

## Run it

You need Python 3.12.

```bash
python -m venv .venv
.venv\Scripts\activate                       # Windows   (macOS / Linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env.local                 # API keys go here (GOOGLE_API_KEY for Gemini); never committed
python scripts/fetch_borrower_documents.py   # the borrowers' latest annual reports and results (~390 MB, once)
python run.py                                # then open http://localhost:8001/los
```

Sign in by picking a role; there is no password in this demo. The AI model is **Gemini** (`vertex_ai_gemini` in
`config/llm_providers.yaml`: an API key on a laptop, Vertex AI on Google Cloud). Without a key, set
`active_provider: mock` — everything still works, with template text.

**Google Cloud Run:** `bash scripts/deploy_gcp.sh` in Cloud Shell. **Docker:** `docker-compose up --build`.

## Tests

```bash
python -m pytest tests -q        # about 400 tests, offline, about 3 minutes
```

## Documentation

| If you are… | Read |
|---|---|
| Using or presenting it | [User guide](docs/USER_GUIDE.md): roles, the journey step by step, demo script, glossary |
| Configuring it for a bank | [Configuration](docs/CONFIGURATION.md): stages, fields, policy, data sources, borrowers, AI model |
| A developer | [Developer guide](docs/DEVELOPER_GUIDE.md): architecture, data, agents, tests, deployment, next steps |

## Project layout

```
src/flow/          The LOS: proposals, fields, risk & challenges, chat, knowledge graph (acquire/ = data agents)
src/agents/        The credit engine's agents (analysis pipeline, challenge, investigation, reassessment)
src/engines/       Fixed calculations: ratios, policy, quality, limits, projections, the CAM sections
src/api/, src/ui/  Web API and screens (flow.html = the LOS)
config/            Everything a bank configures (flow, rules, data sources, sectors, AI model …)
data/borrowers/    One data file per borrower on record — no borrower data lives in code
storage/documents/ Each borrower's documents: real public filings (fetched) and labelled demo documents
test-documents/    UAT test packs for new-to-bank prospects
scripts/           Fetch filings, read statements, refresh demo documents, deploy
tests/             Automated tests
```

## License

Proprietary. All rights reserved.
