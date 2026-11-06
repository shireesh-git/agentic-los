# LOS API reference

The LOS screens use these endpoints. A bank system can call them too, for example a core-banking
integration or a portal. Base path: **`/api/flow`**. Requests and responses are JSON unless stated.
Code: [`src/api/routers/flow.py`](../src/api/routers/flow.py).

**Signing in.** Call `POST /session` with `{"user_id": "f_rm"}` (users are in `config/flow.yaml`). Send the
returned token in the `X-Flow-Session` header on every other call. File downloads in a browser may
pass it as `?session=` instead. Most calls that change a proposal return the **proposal view**: the same
JSON the screen shows.

## Directory, queue and analytics

| Method | Path | What it does |
|---|---|---|
| GET | `/directory` | Product name, users, stages (for the sign-in screen) |
| POST | `/session` | Sign in as a demo user → token |
| GET | `/borrowers` | Borrowers in the catalogue (for "Initiate Proposal") |
| GET | `/queue` | My work queue, the whole pipeline, and headline KPIs |
| GET | `/report` | TAT & productivity: outcomes, quality, stage times, run details |
| POST | `/reset` | Remove a borrower's proposals so the journey can start again: `{"entity_id"}` |

## A proposal

| Method | Path | What it does |
|---|---|---|
| POST | `/cases` | Initiate: `{"entity_id", "facility": {product, amount_cr, tenor_months, purpose}}`, or `{"prospect": {company_name, cin, pan, sector}, "facility": …}` |
| GET | `/cases/{id}` | The proposal view: fields with source, band and confidence; risk strip; challenges; deviation register; chat; actions with their blockers |
| GET | `/cases/{id}/timeline` | The event log |
| POST | `/cases/{id}/action` | `{"action": "approve" \| "reject" \| "send_back", "comment", "challenge"?}`. A comment is mandatory to reject or return, and as a justification when the engine said Decline |
| POST | `/cases/{id}/chat` | `{"message"}` to Credit Copilot |

## The CAM

| Method | Path | What it does |
|---|---|---|
| POST | `/cases/{id}/cam/generate` | Generate (or re-run) the CAM with the credit engine |
| GET | `/cases/{id}/cam/progress` | Live progress: phases, sections, %, time left |
| POST | `/cases/{id}/cam/upload` | Upload the bank's own CAM (multipart `file`) |
| GET | `/cases/{id}/cam.pdf` | The CAM as PDF, with the live Decision Summary and an embedded data sheet |

## Fields, challenges and deviations

| Method | Path | What it does |
|---|---|---|
| PUT | `/cases/{id}/datapoints/{field}` | Set or override a field: `{"value", "reason", "challenge"?}` (calculated fields are refused) |
| POST | `/cases/{id}/datapoints/{field}/skip` | Mark an optional field "not provided" |
| POST | `/cases/{id}/changes/{change}` | Sanctioning Authority: `{"decision": "accept" \| "dispute", "comment"}` on an Underwriting change |
| POST | `/cases/{id}/challenges/{challenge}` | Answer a risk challenge in writing: `{"kind": "justify", "note"}` |
| POST | `/cases/{id}/deviations/{deviation}` | `{"action": "propose", "mitigant", "justification"}` (Origination / Underwriting) or `{"action": "approve" \| "reject", "comment"}` (Sanctioning Authority) |

## New-prospect data sources

| Method | Path | What it does |
|---|---|---|
| POST | `/cases/{id}/sources/{source}/document` | Upload the document for a source that has no API (multipart `file`) |
| POST | `/cases/{id}/sources/refresh` | Re-run the data agents |
| GET | `/cases/{id}/sources/{source}` | The record a source produced (and, for financials, the statements read) |

## After sanction

| Method | Path | What it does |
|---|---|---|
| POST | `/cases/{id}/conditions/{condition}/document` | Upload a document for a condition (the agent checks it) |
| GET | `/cases/{id}/conditions/{condition}/document/{n}` | Download it |
| POST | `/cases/{id}/conditions/{condition}/confirm` | `{"note"}` to confirm, or `{"reopen": true}` |
| POST | `/cases/{id}/demo-documents` | Demo only: add executed documents for every condition |
| PUT | `/cases/{id}/drawdown` | Edit the release request: `{"amount_cr", "account", "value_date"}` |
| GET | `/cases/{id}/sanction-letter.html` | The drafted sanction letter |
| GET | `/cases/{id}/audit-pack.html`, `/audit-pack.json` | The audit trail report |

The credit engine and CAM workspace have their own endpoints (`/api/cases`, `/api/companies`, …). The
running app lists them all at **`/docs`** (interactive OpenAPI page).
