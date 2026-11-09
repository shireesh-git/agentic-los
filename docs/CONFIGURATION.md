# Configuration

You can change almost everything a bank would want to change **without touching code**. Edit a file in
[`config/`](../config/) and restart the app (`python run.py`). Each file is plain text (YAML), with
comments explaining every setting.

| I want to change… | File | Section |
|---|---|---|
| The approval chain: stages, who acts, button labels, time targets | `flow.yaml` | `stages` |
| The demo users and role names | `flow.yaml` | `users`, `roles` |
| Which fields a proposal carries, and which are mandatory | `flow.yaml` | `groups`, `datapoints` |
| The documents CAD collects after sanction | `flow.yaml` | `conditions` |
| Whether a failed hard rule can be approved as a deviation | `flow.yaml` | `deviation_register` |
| The manual-process baseline in the TAT & Productivity report | `flow.yaml` | `baseline` |
| Which online services the agents call, or which document they ask for instead | `data_sources.yaml` | `sources` |
| What a proposal needs, by product | `data_sources.yaml` | `requirements` |
| How politely the agents call online services | `data_sources.yaml` | `network` |
| Policy limits (DSCR, Debt/EBITDA …) | `rules.yaml` | `policy_thresholds` |
| Hard rules, rating scorecard, recommendation bands | `rules.yaml` | `hard_rules`, `scoring`, `recommendation` |
| What the Credit Challenge Agent and observations look for | `rules.yaml` | `credit_challenges`, `credit_observations` |
| Stress-test scenarios | `rules.yaml` | `stress_testing` |
| Who may sanction what (delegation of powers) | `approval.yaml` | `authority_levels` |
| Sector peer benchmarks | `benchmarks.yaml` | `sectors` |
| Which AI model is used | `llm_providers.yaml` | `active_provider`, `providers` |
| CAM layout: streamlined or classic 21 sections | `llm_providers.yaml` | `narrative.cam_structure` |
| What happens when the AI cannot be reached | `llm_providers.yaml` | `narrative.on_llm_unavailable` |
| How many CAM sections are written at once | `llm_providers.yaml` | `narrative.max_parallel_sections` |
| Server port, scoring weights, validation tolerances | `settings.yaml` | `server`, `scoring`, `validation` |
| Demo external data server (CAM workspace) | `external_apis.yaml` | `mock_server` |

Secrets such as API keys go in **`.env.local`** (copy `.env.example`). That file is never committed.

---

## Common changes, step by step

### Add an approver to the chain

1. In `flow.yaml` → `stages`, add a stage in the right place: `id`, `role`, `label`, `actions` (`approve`,
   `reject`, `send_back`), `send_back_to` and `gates`.
2. Add a user with that role under `users`, and a name for the role under `roles`.
3. Restart. The stage tracker, the queue and the chat follow the new chain.

**Gates** are what must be true before the stage can approve:

| Gate | Meaning |
|---|---|
| `cam_ready`, `cam_current` | The CAM exists and is up to date |
| `required_answered` | Every mandatory field is filled |
| `deviations_proposed` | Every policy breach has a mitigant |
| `changes_accepted` | Every Underwriting change is agreed |
| `deviations_approved` | Every deviation is approved, and no hard rule failed |
| `conditions_met` | Conditions precedent are met |
| `drawdown_ready` | The release request is prepared |
| `release_checks` | Pre-disbursement checks pass |

### Add a field to the proposal

In `flow.yaml` → `datapoints`, add a line such as:

```yaml
- {id: promoter_pledge_pct, group: borrower, label: Promoter pledge (%), type: number, ask: "What share of promoter shares is pledged?"}
```

| Option | Effect |
|---|---|
| `type` | `text`, `longtext`, `amount` (₹ Cr), `number`, `ratio` (shown as 1.25x), `score` (out of 100) |
| `required: true` | The proposal cannot move on without it |
| `ask` | The question Credit Copilot asks when no agent fills it |
| `agent_only: true` | Never asked; empty shows "Not on record" |
| `computed: true` | Cannot be typed (a calculated figure) |
| `engine: true` | Changing it makes the CAM out of date |
| `band` | How it is judged, e.g. `{policy: min_dscr, way: min}` or `{max: 0}` |
| `unavailable` | The text shown when no source has it |
| `options` | The valid answers, offered as buttons in the chat and the field editor, e.g. `["Sole banking", "Multiple banking", "Consortium"]` |
| `hint` | Placeholder text for a typed answer, e.g. `"Type the pricing, e.g. MCLR + 0.80%"` |

A field with no extractor is simply asked in the chat. To have an agent fill it, add one line to
`from_engine` in `src/flow/datapoints.py`.

### Connect an online service (when the bank has a contract)

In `data_sources.yaml` → `sources`, set the source's `mode: api` and give it a `connector`. Put any key in
`.env.local` under the name in `requires_key`. Uploads and API responses produce the same record, so
nothing else changes.

Connectors already exist for GLEIF, OFAC/UN sanctions, GDELT and Probe42, so switching those on is a
configuration change. A new provider needs one connector function in `src/flow/acquire/connectors.py`
that returns the same record shape; the rest of the system does not change.

### Demo data for the checks (until the bureau and registry APIs are connected)

Six mandatory checks need a bureau report, the MCA company record and the RBI / CIC lists: wilful defaulter,
company active, bureau status, fraud registry, RBI defaulter and suits filed. They run when a proposal is
initiated. While those APIs are not connected, each borrower can have a demo file,
`storage/demo_registry/<entity id or CIN>.json`, with `bureau`, `mca` and `registries` sections. A source
marked `demo_file: true` in `data_sources.yaml` uses it before asking for a document. Every result from a demo
file is labelled "demo data" on screen, in the CAM and in Copilot answers.

To switch demo data off (for production), set `demo_data: {enabled: false}` in `data_sources.yaml`. The demo
borrowers show three cases: Infosys and most others pass all six; Madras Fertilizers fails "suits filed"; Indian
Hotels has no bureau report, so "bureau status" stays not verified.

### Expected credit loss (ECL) parameters

`rules.yaml` → `ecl`: the 12-month PD for each internal grade, the unsecured LGD and its floor for secured
exposure, the credit-conversion factor for each product, and the bureau statuses and days past due that make a
proposal stage 2 or 3. The values shipped are **demo values**. Replace them with the bank's validated models and
change `label` so the screens stop saying "demo".

### AI governance pack

`ai_governance.yaml` holds the model card, the protected attributes the fairness check looks for, and the
impact-assessment questions. Answers marked `from_record` are filled from each proposal; the bank completes the
others (owner, review date, grievance process).

### Keep the cloud demo's data (Cloud Run)

Set `CAM_STATE_BUCKET` and the app copies its database and uploaded files to that bucket every minute
(`CAM_STATE_SYNC_SECONDS`) and on shutdown, and restores them when it starts. `scripts/deploy_gcp.sh` creates
the bucket and sets this for you.

### Change a policy limit

Edit `rules.yaml` → `policy_thresholds`, e.g. `min_dscr: 1.25`. The following all follow the new limit:
- the risk strip and the credit-metric bands;
- the sustainable limit;
- the deviation register;
- the CAM.

### Switch the AI model

In `llm_providers.yaml`, set `active_provider` to one of `nvidia_nim` (default), `anthropic`, `openai`,
`azure_openai`, `vertex_ai_gemini`, `ollama` (local) or `mock`. `mock` means no AI: everything falls back to
deterministic text, and it is what the tests use. Put the provider's key in `.env.local`.
