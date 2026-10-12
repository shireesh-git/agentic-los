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
| POST | `/applications/{id}/actions` | `{action, comment?, allocate_to?, sanctioned_amount_cr?, significant_changes?}` | Updated view. Actions: `submit`, `approve`, `return`, `reject`, `allocate`, `sanction`. `significant_changes` is recorded at the Disbursement VP Review |
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
TOKEN=$(curl -s -X POST localhost:8002/api/los/session -H 'Content-Type: application/json' \
  -d '{"user_id":"u_rm1","role":"ps_maker"}' | jq -r .token)
curl -s "localhost:8002/api/los/applications?mine=true" -H "X-LOS-Session: $TOKEN"
curl -s -X POST localhost:8002/api/los/applications/LOS-2026-00002/copilot/run \
  -H "X-LOS-Session: $TOKEN" -H 'Content-Type: application/json' -d '{"tool":"run_prefill"}'
```
