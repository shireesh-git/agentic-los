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

A field with no extractor is simply asked in the chat. To have an agent fill it, add one line to
`from_engine` in `src/flow/datapoints.py`.

### Connect an online service (when the bank has a contract)

In `data_sources.yaml` → `sources`, set the source's `mode: api` and give it a `connector`. Put any key in
`.env.local` under the name in `requires_key`. Uploads and API responses produce the same record, so
nothing else changes.

Connectors already exist for GLEIF, OFAC/UN sanctions, GDELT and Probe42, so switching those on is a
configuration change. A new provider needs one connector function in `src/flow/acquire/connectors.py`
that returns the same record shape; the rest of the system does not change.

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
