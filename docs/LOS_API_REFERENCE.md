# Corporate LOS — API Reference

> All LOS endpoints are under `/api/los`. Except `GET /directory` and `POST /session`,
> every call needs the session token in the `X-LOS-Session` header.
> Router: `src/api/routers/los.py` → `LosService` (`src/los/service.py`).

**Errors** (JSON `{"detail": "..."}`): `400` invalid request (validation or gate) · `403`
not signed in, wrong role or not the assignee · `404` not found · `409` conflict (wrong
step, not yet available, already exists) · `500` operation failed.

## Session and directory

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/directory` | — | Groups, roles and demo users (sign-in screen, allocation pickers) |
| POST | `/session` | `{user_id, role}` | Session with `token`, user, active role and group |
| GET | `/session` | — | The current session |
| POST | `/session/role` | `{role}` | Switch the active role (the user must hold it) |
| DELETE | `/session` | — | Sign out |

## Pipeline

| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET | `/dashboard` | — | KPIs and stage counts |
| GET | `/applications` | `?status=&stage=&mine=&q=` | Applications (views) matching the filters; `mine=true` is the active role's queue |
| POST | `/applications` | `{entity_id, facility? , facilities?, related_parties?, priority?, prospect_discussion?, sourcing_decision?, customer_id_selection?}` | New draft (RM only). Identity and deduplication are computed server-side and stored with the application |
| GET | `/applications/{id}` | — | Application view: step, SLA, rail, available actions, events, customer identity, prospect discussion, due-diligence state |
| POST | `/applications/{id}/actions` | `{action, comment, allocate_to?, sanctioned_amount_cr?, significant_changes?, rework_to?, decision_data?, deferred_until?}` | Updated view. Actions per step come from `los_workflow.yaml`: `submit`, `approve`, `return`, `reject`, `allocate`, `sanction`, `defer`, `reactivate`, `drop`, `withdraw`, `propose_modification`, `recommend_modification`. A `comment` is required for every action (`remarks_required: all`). `decision_data` carries the step's decision fields (e.g. `material_information_date`); `deferred_until` is required for `defer` |
| POST | `/applications/{id}/reassign` | `{user_id, comment?}` | Updated view |
| POST | `/applications/{id}/escalate` | `{comment}` | Updated view |
| GET | `/borrowers` | — | Borrowers a new application can be opened for |
| GET | `/borrowers/{entity_id}/identity` | — | Customer identity & deduplication: NTB/ETB, Customer ID/CIF, PAN, name as per PAN, CIN, GSTIN, date of incorporation, constitution, CBS customer search and potential existing LOS applications |
| GET | `/audit` | `?limit=200` | Latest events across all applications |
| POST | `/demo/reset` | — | Re-seed the demo pipeline (`los_admin` only) |

## Prospect sourcing (Phase 4)

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/applications/{id}/sourcing` | — | Documents on file, upload categories, the prefill with accepted values, `can_edit` |
| POST | `/applications/{id}/documents` | multipart: `file` (PDF), `category` | Sourcing view; 409 if the file already exists |
| POST | `/applications/{id}/prefill` | — | Runs the prefill; sourcing view with proposed fields (value, confidence, band, status, sources, alternatives) |
| POST | `/applications/{id}/prefill/apply` | `{items: [{field_id, status: accepted\|clear, value?, reason?}]}` | Sourcing view; edited values need a reason |

## New prospect from documents (agents)

A prospect that is not yet in the borrower catalogue is sourced from its documents.

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/prospects/documents` | multipart: `file` (PDF), `category`, `staging_id?` | The staging set (a new `staging_id` on the first upload) |
| POST | `/prospects/{staging_id}/read` | — | The intake agent's reading: proposed `identity` and `facility` (each with value, confidence, status, source, alternatives), the full `prefill` (including unread scanned pages), duplicate `matches` and the `sectors` list |
| POST | `/prospects` | `{staging_id, identity, facilities, related_parties?, priority?, prospect_discussion?, sourcing_decision, confirm_not_duplicate?}` | Registers the borrower (no placeholder identifiers), creates the application, moves the documents and starts the preparation agent. 409 on a possible duplicate unless `confirm_not_duplicate` |

## Start from a CAM (S8)

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/borrowers/{entity_id}/cam` | — | `workspace`: the latest CAM in the CAM workspace (run, decision, grade, the facility it assessed) or null; `can_generate` |
| POST | `/applications` | … + `cam: {mode: workspace\|document\|generate, run_id?, staging_id?}` | Creates the draft and starts the preparation agent. *workspace* links the CAM and fills the IP fields; *document* takes a CAM staged with category `cam` and read with `/prospects/{id}/read` (a CAM with another company's PAN or CIN gets 409); *generate* adds a credit-case lane at PS |
| POST | `/prospects` | … + `cam: {mode: document\|generate}` | The same for a new prospect (the CAM is among its staged documents) |
| POST | `/prospects/{staging_id}/read` | — | Also returns `cam`: the CAM intake agent's reading (sections with heading, page and preview; labelled values) |

`GET /mis` → `agents.cam`: applications started from a CAM by mode, fields read from uploaded CAMs, accepted unchanged.

## Agents: preparation and the field store

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/applications/{id}/prepare` | — | Starts the preparation agent for the current step (PS, IP Note, AP Note, Risk Makers, POS / DIS Makers; step holder). Progress, with parallel lanes, is in `GET /assessment` → `prep` |
| GET | `/applications/{id}/assessment` | — | Also returns `pin` (the pinned credit run), `verify` (queue, stats, step stats), `can_verify`, `prep` (job state and lanes) and `can_prepare` |
| POST | `/applications/{id}/fields/verify` | `{decisions: [{field_id, action: confirm\|override\|keep\|reopen, value?, reason}]}` | Refreshed workspace. `override` needs a value and a reason; `keep` (resolve a conflict in favour of the decision) needs a reason. A CMA or collateral override re-runs the credit case |
| POST | `/applications/{id}/fields/bulk-confirm` | `{field_ids?}` | Confirms the given fields, or every pre-ticked field in the queue; `must_verify` fields are never included |
| GET | `/applications/{id}/post-sanction` | — | Also returns `suggested` (`post_sanction` / `disbursement` values the intake agent read) and `intake` |
| GET | `/mis` | — | Also returns `agents`: `headline` (fields, populated %, verified %, accepted unchanged %, overridden, open conflicts, values not keyed), `domains` and `activity` (preparations, average time, population runs, feedback re-runs, prospects from documents) |

## Governed workspaces

Edit endpoints for the workspaces the reconciliation agents populate. Reviewer steps (checker,
VP, committee) are read-only and get 403.

`POST /applications/{id}/` followed by: `parties`, `parties/{party_id}/evidence`, `entity`,
`facilities/{facility_id}`, `securities`, `projects`, `projects/{project_id}/change`, `esms`,
`ewps`, `ratings`, `raroc`, `crp-notes`, `cma`, `cma/review`, `proposal`,
`proposal/fetch-exposure`, `pricing`, `pricing/fees`, `pricing/schedule`, `covenants`, `disops`,
`disops/memo`, `disops/memo/review`, `disops/review`, `documents/review`,
`material-changes/review`, `invalidations/{id}/resolve`, `ip-note/assignments`,
`due-diligence/evidence`, `due-diligence/grid`, `disbursement/subsequent-tranche`,
`outputs/{kind}`.

Read endpoints: `GET /applications/{id}/documents`, `/snapshot`, `/rules`, `/outputs/{kind}.html`,
and `GET /integrations`. Request bodies are defined in `src/api/routers/los.py`.

## Terms & conditions authored at AP (S9)

| Method | Path | What it does |
|---|---|---|
| GET | `/applications/{id}/terms` | The T&C by category, each with its field status (`proposed`, `confirmed`, `overridden`), source and evidence; `summary`, `editable` and `gate` (what still blocks *Submit appraisal*) |
| POST | `/applications/{id}/terms` | `payload: {action: add \| update \| remove \| restore, term_id?, category, text, facility_id?, stipulated_value?, frequency?, reason?}`. Only at Application Note Processing. Changing the wording of an agent's draft needs a `reason` (recorded as a field override); removing needs a `reason` |

Drafts are confirmed with `POST /applications/{id}/fields/bulk-confirm` (`field_ids` from the
`terms` rows). At final sanction the T&C are locked and become the post-sanction conditions
(`conditions[].term_id` links each one back).

## Decision tab (S7)

| Method | Path | What it does |
|---|---|---|
| GET | `/applications/{id}/decision` | The computed sanctioning committee, automatic deviations (credit case) and manual deviations, the decision records of every step, and the remarks history (decisions and Compliance exceptions, in order, in the bank's wording) |
| POST | `/applications/{id}/deviations` | `payload: {type, description, justification}` adds a manual deviation; `{action: remove, id, reason}` removes one. At the IP / AP Note and Risk Maker steps. Manual deviations count towards the committee, appear in the committee pack and in the post-sanction deviation register |

| POST | `/applications/{id}/decision-notes` | `payload: {key, text}`: the decision-tab narratives (`policy_compliance`, `previous_relaxations`, `other_matters`, `ip_observations`), drafted by the agents where a source exists |

## Field gaps from the reference screens (S10)

| Method | Path | What it does |
|---|---|---|
| POST | `/applications/{id}/unit-visits` | Unit Visit Details: `{date_of_visit, place, address_visited, officials: [{name, designation}], observation, remarks}`, or `{action: remove, visit_id}`. At the AP makers |
| POST | `/applications/{id}/sourcing-details` | Received date, source, sourcing branch, owners, Sol ID, sub-sub-sector, LPFG analysts. Defaulted from the creating session; edited at PS and the IP Note |
| POST | `/applications/{id}/security-notes` | The AP security remarks (creation status, change since the last sanction, security trustee), drafted by an agent |
| POST | `/applications/{id}/proposal` | `section: background` now takes the bank's nine AP narratives too (market enquiries, pledged shares, corporate actions, SMA / NPA status, committee directions, past proposals, unhedged exposure, reason for committee, justification); at the IP / AP Note and Risk Maker steps |

The Disbursement Maker's preparation also runs the **carry-forward agent**: the job summary has a
`carry_forward` block (proposals, values filled), and its fields are in the verify queue (`dis_carry`).
Saving `disops` sections `interest_terms`, `repayment_final`, `fees` or `security_refs` records the
maker's values against the proposals.

`GET /applications/{id}` also returns `decision_fields` (with the bank's `label`) and
`decision_defaults`: the AP decision record carried forward from the previous step of the stage.

`GET /applications/{id}` also returns:
- `blockers`: `[{message, where}]`, the gates that stop the step's forward action now. These are
  the same checks `POST …/actions` applies; `where` names the page section that fixes each one.
- `prefill_coverage`: the IP Note sections the agents filled, with `applicable` and `filled` per section.
- `terms_summary`: counts by category, and the drafts awaiting confirmation.

## Governed due-diligence workspace (GAP-P0-05/06)

Available at the Prospect Sourcing, IP Note and Risk Maker steps. A pending, failed or
unexcepted *mandatory* check blocks the `submit` action.

| Method | Path | Body | Notes |
|---|---|---|---|
| GET | `/applications/{id}/due-diligence` | — | The fifteen checks (status, detail, source, error, last trigger, triggering user, retrigger history, comments, exception), summary, `blocking`, `can_edit` |
| POST | `/applications/{id}/due-diligence/run` | — | Runs every API check without a clear result (step holder) |
| POST | `/applications/{id}/due-diligence/trigger` | `{check_id}` | Runs/re-runs one API check; the earlier result is kept in its history |
| POST | `/applications/{id}/due-diligence/record` | `{check_id, result: clear\|matched\|failed, remarks?}` | Records one manual check; a non-clear result needs a remark |
| POST | `/applications/{id}/due-diligence/comment` | `{check_id, remarks}` | Adds a comment to a check |
| POST | `/applications/{id}/due-diligence/exception` | `{check_id, remarks}` | **Compliance VP only**: the recorded exception that releases a mandatory match/failure |

## IP Note (Phase 4)

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/applications/{id}/ip-note` | — | The stored note, or a preview; `can_generate` |
| POST | `/applications/{id}/ip-note` | `{with_ai: true}` | Generates and stores the note (IP Note step holder) |
| GET | `/applications/{id}/ip-note.html` | — | Printable HTML |

## Credit assessment and review (Phases 2–3)

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/applications/{id}/assessment` | — | Job status, recorded summary, review summary and the 9-tab Risk Maker view |
| POST | `/applications/{id}/assessment` | — | Starts the credit-intelligence pipeline in the background (Risk Maker step holder) |
| POST | `/applications/{id}/field-reviews` | `{reviews: [{field_id, status: confirmed\|overridden\|clear, value?, reason?}]}` | Updated assessment view |
| GET | `/applications/{id}/committee-pack` | — | Review and committee pack; `can_brief`, `at_committee_step` |
| POST | `/applications/{id}/committee-brief` | — | Generates the AI brief (review and committee steps); 409 on the mock provider |

## Post sanction and disbursement (Phase 5)

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/applications/{id}/post-sanction` | — | Conditions with state, condition summary, deviation register, IP → AP comparison, disbursement (checklist, tranches, limits) and the recorded **consent** |
| POST | `/applications/{id}/post-sanction/consent` | `{acknowledged_by, consent_date, remarks?, facilities: [{facility_id, execution_status: executed\|partial\|not_executed, agreement_date?}]}` | The customer's sanction consent and per-facility execution (POS Maker); gates the submission. Executed facilities need the agreement date |
| POST | `/applications/{id}/conditions` | `{updates: [{id, status: satisfied\|deferred\|waived\|open, note?, evidence?, due?}]}` | Post-sanction view |
| POST | `/applications/{id}/disbursement/checklist` | `{items: [{id, done, note?}]}` | Post-sanction view (manual items only) |
| POST | `/applications/{id}/disbursement/tranche` | `{amount_cr, value_date, purpose?}` | Post-sanction view; replaces a pending tranche |

## Letters and MIS (Phase 7)

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/applications/{id}/letters` | — | For `term_sheet` and `sanction_letter`: availability, `can_generate`, versions, latest |
| POST | `/applications/{id}/letters/{kind}` | — | Issues a new version (RM for the term sheet, Post Sanction Maker for the sanction letter) |
| GET | `/applications/{id}/letters/{kind}.html` | `?version=` | Printable HTML of the latest or a given version |
| GET | `/mis` | — | Management MIS: headline, pipeline, ageing, turnaround, SLA breaches by role, decisions, sanctions, conditions, copilot |

## Copilot (Phase 6)

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/copilot/digest` | — | The signed-in user's queue, SLA breaches first, with the top proposal each |
| GET | `/applications/{id}/copilot` | — | Ranked actions, `is_holder`, `ai_available`, available tools, recent Q&A |
| POST | `/applications/{id}/copilot/run` | `{tool}` | Runs a tool for the step holder; tools: `run_prefill`, `accept_high_confidence`, `run_due_diligence`, `generate_ip_note`, `start_assessment`, `committee_brief`, `issue_sanction_letter` |
| POST | `/applications/{id}/copilot/draft` | `{kind: return_note\|document_request}` | `{text, note}`; nothing is sent |
| POST | `/applications/{id}/copilot/ask` | `{question}` | `{answer, mode: ai\|lookup, provenance, note, fields_used}` |

## Example: sign in and act

```bash
TOKEN=$(curl -s -X POST localhost:8001/api/los/session -H 'Content-Type: application/json' \
  -d '{"user_id":"u_rm1","role":"ps_maker"}' | jq -r .token)
curl -s "localhost:8001/api/los/applications?mine=true" -H "X-LOS-Session: $TOKEN"
curl -s -X POST localhost:8001/api/los/applications/LOS-2026-00002/copilot/run \
  -H "X-LOS-Session: $TOKEN" -H 'Content-Type: application/json' -d '{"tool":"run_prefill"}'
```
