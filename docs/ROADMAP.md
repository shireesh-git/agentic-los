# Roadmap — after the POC

> What remains once the proof of concept is complete (sprints S1–S6, see
> [POC_BUILD_PLAN.md](POC_BUILD_PLAN.md)). This list consolidates the open items from the three
> planning documents behind the POC, now in [planning/](planning/):
> - the bank-alignment gap analysis (ids A-, B-, C-);
> - the process gap backlog (G-);
> - the auto-population technical gaps (T-).
>
> Those documents keep the full detail and rationale.

## 0. Current round: alignment with the bank's reference journey

The next round (S7–S10) is defined in
[planning/REFERENCE_JOURNEY_GAP_ASSESSMENT.md](planning/REFERENCE_JOURNEY_GAP_ASSESSMENT.md).
It covers the CAM as an input, IP and AP pre-fill, a carry-forward agent for POS and DIS,
the missing workflow steps, decision records, and T&C authoring at AP. It supersedes the
overlapping items below.

| Sprint | Scope | Status |
|---|---|---|
| S8 | CAM as an input (workspace CAM, bank CAM upload, generate at sourcing) | Built |
| S9 | IP / AP pre-fill, T&C authored at AP and carried to post sanction, RAROC agent | Built |
| S7 | Workflow steps (IP Post Rating VP, ES stages, DMD), decision wording, Decision tab, AP decision record; field-level pass (R-0) | Built — the bank confirms the ES / DMD order |
| S10 | Carry-forward agent for DIS; field gaps F-1 to F-6, F-9, F-10 ([field list](planning/REFERENCE_FIELD_LIST.md)); MIS | Built |
| Next | F-7 / F-8 (entity identifiers, group tables); the bank's sample CAM, ES / DMD order, pricing model and approval matrix | Bank input |

## 1. Next: the bank's own document set

The POC journey has run end to end on a **fictional** document set (*Zeta Foods Private
Limited*).

1. Run it on one real borrower's documents from the pilot bank.
2. Record what a person reads from them as the golden values (`src/devtools/demo_documents.py` →
   `GOLDEN`).
3. Extend the intake patterns where the bank's formats differ.
4. Turn on a provider with `vision: true` (or install OCR) so scanned pages are read.

## 2. Known POC limits (agentic layer)

| Item | Today | Next step |
|---|---|---|
| Feedback re-runs | Only CMA and collateral overrides re-run the credit case | All engine inputs, with dependency-aware partial recompute (T-03) |
| Proposal narrative | Deterministic drafts from confirmed facts | LLM drafts through the critic, kept `must_verify` (T-08) |
| CMA gate | Satisfied by agent-written rows before they are verified | Require the CMA domain to be verified before the Risk Maker submits |
| Duplicate entries | An agent row and a person's manual row for the same item can both appear | Match on natural keys before materialising |
| Duplicate acknowledgement (G-09) | Enforced when a prospect is created from documents | Also on the catalogue path and as a PS submit gate |
| Copilot | Rule-based planner | `LLMAgent` runtime with read-only tools and the critic |
| Scanned pages | Read only with a vision-capable provider | OCR fallback; per-document-type extractors (T-09) |
| Jobs | In-process threads; job state in memory (T-13) | Durable queue; resumable graphs |

## 3. Functional parity still open

| Id | Gap |
|---|---|
| G-06 / C-3 | Conditional, authority-driven approval routing. The authority is computed and shown, but the chain is fixed |
| G-08 / C-7 | Full Prospect Sourcing fields and discussion log: subsector, branch, currency, participants, status, infra-finance qualification |
| G-11 / C-9 | Check applicability by constitution and entity type; validity periods with forced retrigger |
| G-12 | E&S excluded-activity exception approval |
| G-13 / C-10 | Facility hierarchy: parent facilities and sublimits; takeover and reimbursement attributes |
| G-14 / C-11 | Modification route variants (who re-approves which change) |
| G-01 (rest) | Defer reminders and a maximum deferral period |
| C-13 | Confirm the AP queue order and the RM / risk-analyst split with the bank |

## 4. Production foundation

| Id | Item |
|---|---|
| A-1, A-2 | Real authentication (SSO / AD), role and branch access, delegation administration |
| A-3 | Production database with migrations; FieldValue as its own table |
| A-4 | Multi-instance deployment and a durable job queue |
| A-5 | Tamper-evident audit (hash chain / WORM) and retention |
| A-6 | Encryption, PII masking, secrets vault, VAPT, document antivirus |
| A-7 | Observability: tracing per graph run, LLM cost and latency, extraction-accuracy dashboards; availability and DR targets |
| A-8 | LLM governance: approved hosting (data residency), prompt and response logging, model-risk sign-off |

## 5. Integrations and bank models

| Id | Item |
|---|---|
| B-1 | CBS customer lookup (dedupe / ETB) and exposure fetch |
| B-2 | Verification providers: MCA, PAN / GSTIN, CIBIL / CRIF / CRILC, CFR, CEIB, LEI, UDIN, name screening. Planned as typed tools in the tool registry, or over MCP |
| B-3 | CBS writes: CIF, limit and account creation, security IDs; CERSAI / ROC |
| B-4 | Payment initiation hand-off and status back to the LOS |
| B-5 | Bank models: internal rating (PD/LGD), group rating, RAROC, pricing grid, CMA formulae, authority and deviation matrices |
| B-6 | The bank's templates: CAM, IP Note, term sheet, sanction letter, disbursement memo |
| B-7 | DMS integration |

## 6. Questions for the bank

1. What is the queue order and owner (RM or risk analyst) in Application Processing?
2. When are CRP review, ESMS / CRP processing and DMD steps required?
3. Defer: who may defer, at which stages, for how long, and who reactivates?
4. What do Drop, Decline, Reject and Withdraw each mean, and is each reported separately?
5. Modification: which changes need full re-appraisal?
6. What are the check validity periods and the applicability matrix?
7. Payment execution: inside the LOS, in CBS or elsewhere? What does *Exit* certify?
8. In-flight cases: migrate them, or let them finish in the old LOS?
