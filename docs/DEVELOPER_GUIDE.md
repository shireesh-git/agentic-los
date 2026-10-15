# Developer Guide — Agentic Corporate LOS

> How the code is organised, how the data is stored, and how to extend it: a new field,
> resolver or workflow step. For the picture first, read
> [TECHNICAL_ARCHITECTURE.html](TECHNICAL_ARCHITECTURE.html) (architecture) and
> [FUNCTIONAL_GUIDE.html](FUNCTIONAL_GUIDE.html) (process). Endpoints are in
> [LOS_API_REFERENCE.md](LOS_API_REFERENCE.md).

---

## 1. Run, test, configure

```bash
python -m venv .venv && .venv\Scripts\activate          # Windows (source .venv/bin/activate elsewhere)
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env.local                                # API keys; never committed
python run.py                                             # http://localhost:8001/los  (CAM workspace at /)
```

- The port is `server.port` in `config/settings.yaml`. Uvicorn reload is off because it hangs on
  Windows, so restart after code changes.
- On first start the demo pipeline is seeded with seven applications. **Administration → Reset
  demo** (as *LOS Administrator*) re-seeds it.
- Run `python scripts/make_demo_documents.py demo_documents` to write the fictional prospect's
  document set used by [POC_DEMO_SCRIPT.md](POC_DEMO_SCRIPT.md).

```bash
python -m pytest tests -q                                    # everything, offline (~7 min)
python -m pytest tests/test_poc_golden_and_e2e.py            # golden extraction set + new prospect → Exit
python -m tests.characterization.snapshot --write            # accept intended CAM-pipeline changes
python -m tests.characterization.api_contract --write        # accept intended API changes
```

Tests run against a temporary copy of `config/` and `storage/`, with the mock LLM and with
external sources disabled (`tests/conftest.py`). They never touch your database or call a
provider. Don't point `pytest` at `scripts/`.

| File | What it configures |
|---|---|
| `config/los_workflow.yaml` | Groups, roles, demo users, stages, steps, SLAs, per-step `actions`, `labels`, `decision_fields`, `remarks_required` |
| `config/los_fields.yaml` | Field registry: domains and where they are verified, resolvers, pre-tick threshold, confidence by provenance, per-field `verify` policy |
| `config/llm_providers.yaml` | `active_provider`; per provider: model, `max_parallel_llm`, `vision`, retries; CAM narrative settings |
| `config/settings.yaml` | `server.port`, `pipeline.parallel_agents`, `agentic.max_workers` |
| `config/rules.yaml` | Policy thresholds (IP Note pre-screen, CAM policy engine) |
| `config/approval.yaml` | Delegation-of-powers matrix (placeholder values) |
| `.env.local` | API keys (`NVIDIA_NIM_API_KEY`, `ANTHROPIC_API_KEY`, …) |

Set `active_provider: mock` to run with no LLM; every feature falls back to its deterministic
behaviour. Scanned pages are read only by a provider with `vision: true`.

If the configured provider cannot be reached (no key in `.env.local`, no network), the CAM narrative
falls back to the templates when `narrative.on_llm_unavailable: template` (the default). The case is
labelled `narrative_mode: template_fallback`, and the LOS shows the reason in amber on the agents card.
Set `on_llm_unavailable: fail` to stop the credit case instead.

## 2. Code layout

```
src/agentic/                 the agent framework (no LOS knowledge)
├── graph.py                 AgentGraph, Node, GraphRun: DAG scheduler, fan-out, join, LLM cap, events
├── critic.py                check_figures, check_evidence, CriticAgent
├── tools.py                 ToolRegistry: typed, permissioned (read/propose/external), audited tools
├── runtime.py               LLMAgent: reason → parallel tool calls → observe (built and tested; not yet used by a flow)
└── schema.py                JSON-schema validation and JSON extraction for structured output

src/los/
├── service.py               LosService: the façade the API calls. Sessions, permissions, workflow actions,
│                            gates, preparation jobs (_prepare*), population and merge, verify, prospects,
│                            post-sanction, disbursement, letters, copilot, MIS
├── workflow.py              Workflow model, transitions (incl. defer / reactivate / drop / withdraw), SLA
├── store.py                 LosStore: SQLite persistence for applications and the audit trail
├── intake.py                Document intake agent: per-document reading (vision for scans), per-document
│                            patterns, structured AI fallback with a verbatim check, corroboration
├── later_intake.py          Field sets for Post Sanction and Disbursement intake
├── sourcing.py              Sourcing field specs and the prefill model (used by intake)
├── reconcile.py             Reconciliation agents per domain + materialise (fields → workspaces)
├── fields/
│   ├── registry.py          FieldRegistry (config/los_fields.yaml)
│   ├── model.py             FieldValue: merge, apply_action (confirm/override/keep/reopen), queue, stats
│   ├── population.py        run_population: resolvers in parallel → critic per domain
│   ├── resolvers.py         risk_maker_proposals (credit case → Risk Maker fields)
│   └── metrics.py           agent_metrics for the MIS
├── risk_maker.py · committee.py · ip_note.py · post_sanction.py · letters.py · copilot.py · mis.py
│                            builders: pure functions of their inputs
└── cma.py · securities.py · proposal.py · pricing.py · ratings.py · disops.py · …
                             the governed workspaces (validation and shape of each)

src/agents/pipeline.py       the 7-agent CAM pipeline, run on AgentGraph
src/application/             CaseService (runs with verified overrides), CompanyService (register_prospect),
                             container.py (wiring; seeds the demo pipeline)
src/core/llm_provider.py     providers, generate_structured, images, per-provider semaphore
src/devtools/demo_documents.py   the fictional demo document set and its golden values
src/api/routers/los.py       HTTP → LosService (no business logic)
src/ui/templates/los/*.html, src/ui/static/js/los/los.js   one Alpine component, presentation only
```

**Layering rules**
- Routers only translate HTTP into service calls.
- `LosService` owns state changes, permissions, locks and audit.
- Builders, resolvers and reconciliation agents are pure functions of their context and
  return proposals. They never write the application.
- All model calls go through `src/core/llm_provider.py`.

## 3. Data model

### 3.1 Tables

| Table | Content |
|---|---|
| `los_applications` | One row per application: id, entity, status, stage, step, assignee and the full application JSON |
| `los_events` | Append-only audit trail: `event_id`, application, time, actor (with `agent` for agent work), role, action, from/to step, status, comment, `detail_json` |
| `los_sequence` | Per-year counter for application ids `LOS-YYYY-NNNNN` |
| `case_runs`, `companies` | CAM platform: credit-case runs and the borrower catalogue (prospects built from documents have `source: los_prospect`) |

`LosStore.save(app, event)` writes the application and its event in one transaction.

### 3.2 The application document (main keys)

| Key | Written by | Meaning |
|---|---|---|
| `application_id`, `entity_id`, `borrower_name`, `sector`, `facilities` | create / create_prospect | Identity and proposal |
| `stage_id`, `step_id`, `status`, `assignee_id`, `step_entered_at`, `escalated` | act / reassign / escalate | Workflow position. Status: DRAFT, IN_PROGRESS, UNDER_REVIEW, RETURNED, DEFERRED, APPROVED (exit), REJECTED, DROPPED, WITHDRAWN |
| `fields` | merge / verify | The field store: `{field_id: FieldValue}` (§4) |
| `fields_meta` | population | Last population: resolvers, timings, failures, registry version |
| `agent_writes` | materialise | Workspace paths an agent wrote, so a person's own entry is never replaced |
| `credit_assessment` | preparation / assessment | The **pinned** credit case: `run_id`, decision, grade, recommended |
| `assessments.IP/AP`, `sanctions.IP/AP` | submit / sanction | Per-stage snapshots |
| `decisions` | act | Decision fields captured with an action (material-information date, significant changes, minutes) |
| `deferrals` | defer / reactivate | Deferred-until date, who, why; SLA paused while deferred |
| `due_diligence` | checks | The fifteen checks with history, comments and exceptions |
| `sourcing.prefill`, `later_intake.post_sanction`, `later_intake.disbursement` | intake | What the intake agent read, with sources |
| `cma`, `securities`, `parties`, `exposure`, `ratings`, `pricing`, `proposal`, … | workspaces | Governed workspaces (agents materialise into them) |
| `conditions`, `consent`, `disbursement`, `disops`, `letters` | POS / DIS | Post-sanction and disbursement records |

`LosService._view()` adds computed fields for the UI: step details, SLA state, available
actions with labels, and decision fields.

## 4. The field store (Populate → Verify → Lock)

A **proposal** (from any resolver) is:

```python
{"field_id": "cma.financials.revenue.FY2025", "domain": "cma", "label": "Revenue (FY2025)",
 "value": 312.4, "provenance": "source", "confidence": 0.95,
 "sources": [{"kind": "document", "document": "audited_financials_fy2025.pdf", "page": 1}],
 "target": ["cma", "subjects", {"find": {...}, "new": {...}}, "rows", ...],   # where it materialises
 "value_type": "number", "issues": []}
```

The rules (`fields/model.py`):

- **Merge.** `merge(fields, proposals, registry, at)` runs under `LosService._app_lock(app_id)`.
  - A new field becomes `proposed` (or `unavailable` when there is no value).
  - A decided field (`confirmed` / `overridden`) keeps its decision.
  - A different new proposal turns a decided field into `conflict`.
- **Actions.** `apply_action` supports four actions:
  - `confirm`
  - `override` (needs a value and a reason)
  - `keep` (resolve a conflict in favour of the decision; needs a reason)
  - `reopen`
- **Queue.** `queue(fields, registry, step_id)` lists the open items for the step's domains, ranked:
  - conflicts first, then `must_verify` fields, issues and low confidence;
  - each item has a `why`;
  - items with confidence ≥ `pretick_confidence`, no issues and the `bulk` policy are pre-ticked.
- **Materialise.** `reconcile.materialise` writes each field's current value into its workspace
  `target`. It records the path in `agent_writes` and skips paths a person wrote.
- **Mirroring.** `LosService._mirror_entries` handles forms a person saves directly (consent,
  tranche, beneficiaries):
  - each saved value is compared with the proposal, numerically when both are numbers;
  - an equal value is recorded as `confirmed`, a different one as `overridden`.

## 5. Agents and graphs

### 5.1 `AgentGraph`

```python
from src.agentic.graph import AgentGraph, Node

graph = AgentGraph([
    Node("documents", fan_out=lambda ctx: paths, run_item=read_one, item_key=str),
    Node("patterns", fan_out=docs_of, run_item=extract, requires=("documents",)),
    Node("ai_fallback", run=ai_fallback, requires=("documents",), waits_for=("patterns",), lane="llm"),
], name="intake", on_start=..., on_result=...)
run = graph.run(ctx)        # run.data(name), run.results, run.log(), run.duration_ms, run.max_concurrency
```

- **`requires`** must complete successfully first. If it fails, the node is skipped.
- **`waits_for`** waits for the other node and uses its result if present.
- **Fan-out** children are joined by `item_key`. A custom `join(ctx, pairs)` can reduce them.
- **Concurrency.** The pool is bounded by `agentic.max_workers`. LLM calls are additionally
  capped per provider by `max_parallel_llm`.

### 5.2 Preparation per step (`LosService._prepare`)

| Step | Graph | Lanes |
|---|---|---|
| `ps_maker` | `prospect-prep` | identity & dedupe ‖ API checks (fan-out) ‖ document intake |
| `ip_note`, `ap_note`, `ip_risk_maker`, `ap_risk_maker` | `appraisal-prep` | credit case (pinned or new run) ‖ API checks (DD steps) → populate (resolvers ‖ → critic per domain) → materialise → IP Note draft (IP Note only) |
| `pos_maker`, `dis_maker` | later-stage intake | intake on the stage's field set (`later_intake.STAGES`) |

- Preparation runs in a background thread; `wait_for_preparation(app_id)` blocks in tests.
- Job state and lanes are in memory. The outcome is the `application_prepared` event.

### 5.3 Adding things

**A field policy.** Add the field id under `fields:` in `config/los_fields.yaml`, e.g.
`{verify: must_verify}`. Fields not listed take the domain defaults.

**A reconciliation agent (new domain).**
1. Write `resolve_<domain>(ctx) -> list[proposal]` in `src/los/reconcile.py`. Use `_p(...)` to
   build proposals, each with a `target` path.
2. Add it to `RESOLVERS` and `DOMAINS`.
3. In `config/los_fields.yaml`, add the domain under `domains:` with its `verify_at` steps, and
   list it under `resolvers.reconciliation.domains`.
4. Add a test in `tests/test_los_reconcile.py`. `test_registry_policies_name_real_fields`
   checks that every listed field is one a resolver produces.

**An intake field.** Add a spec `{"id", "label", "group", "kind", "patterns": [...]}`:
- for Prospect Sourcing, in `src/los/sourcing.py` (`FIELDS`);
- for Post Sanction or Disbursement, in `src/los/later_intake.py`.

Add the expected value to `GOLDEN` in `src/devtools/demo_documents.py` (and the text to the
demo document) so the golden-set test measures it.

**A workflow step or action.** Edit `config/los_workflow.yaml`:
- `actions` must be allowed for the step kind (`workflow.ALLOWED_BY_KIND`);
- `labels` give the bank's wording;
- `decision_fields` items are `{id, label, type, required}` with a type from `DECISION_FIELD_TYPES`.

Gates live in `LosService.act`.

**A tool for an LLM agent.** Register it with `@registry.tool(name, description, parameters,
permission="read")`; `LLMAgent(AgentSpec(..., tools=[...]), llm, registry)` can then call it.
Calls are schema-checked and audited. Only `read` and `propose` tools should be given to
agents.

## 6. Workflow engine

| Step kind | Default actions | Effect |
|---|---|---|
| maker | submit (+ `defer`, `drop`, `withdraw`, `propose_modification` where configured) | Next step / on hold / closed |
| checker | approve · return · reject (+ `recommend_modification` where configured) | Next step · back to the stage's maker · terminal REJECTED |
| vp_review | submit · return (shown as *Rework*) | Next step · back to the maker |
| allocation | allocate | Next step, assigned to the chosen user |
| committee | sanction · return · reject | Next step with a sanction record · back · terminal |

- `remarks_required: all` makes a remark mandatory for every decision.
- A deferred application shows only `reactivate` and its SLA is paused.
- Only `reject` clears the assignee.
- Reviewers are read-only: `_workspace_may(review=True)` refuses edit endpoints at checker, VP and
  committee steps.

| Gate | Step |
|---|---|
| Mandatory due-diligence checks complete (or excepted) | PS, IP Note, Risk Makers |
| IP Note generated, no blocking DD, IP-stage documents on file | IP Note |
| Credit assessment recorded | Risk Makers |
| Consent recorded, no CP open, material changes reviewed | Post Sanction Maker |
| Tranche recorded, checklist complete | Disbursement Maker |
| Minutes when the sanction differs from the recommendation; amount ≤ request | Committees |

## 7. Credit engine (CAM) integration

| LOS need | Component |
|---|---|
| Credit case for an application | `CaseService.run(entity_id, on_progress, overrides=None)`, run once in preparation and **pinned** by `run_id` |
| Feedback re-run | Verified CMA / collateral overrides → `apply_verified_overrides` on a copy of the company → new run, re-populate |
| Prospect from documents | `CompanyService.register_prospect` (no placeholders; statements from the audited financials) |
| Risk Maker fields | `risk_maker.build_risk_maker_view` → `resolvers.risk_maker_proposals` |
| Committee pack, conditions | the reassessment (M6), policy decisions, stress test, composed CAM |
| AI committee brief | `FinalCamService.interpret` (figure-checked) |

The CAM engine's own diagnostics harness runs one pipeline agent on a cached case:

```bash
python scripts/test_agent.py --list
python scripts/test_agent.py --case MFL001 --agent financial_analysis
```

## 8. Deployment

- **Docker** (`docker-compose up --build`). The image holds `src/`, `config/`, `scripts/` and
  `run.py`. `storage/`, `output/` and `runtime-db/` are mounted volumes.
- **Cloud Run.** `scripts/deploy_gcp_camdemo.ps1`.
- **Single process.** Sessions and job state are in memory, so run one replica.

## 9. Further reading

- [ROADMAP.md](ROADMAP.md): what remains after the POC.
- [cam-engine/](cam-engine/): CAM engine references: datapoint source matrix, credit observations,
  the agent harness (`scripts/test_agent.py`) and the CAM workspace screen wiring.
- [planning/](planning/): the gap analyses the POC was planned from.
