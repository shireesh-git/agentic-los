# LOS Modernisation — Gap Analysis and Phased Build Plan

> **Status:** working draft v0.1 (2026-10-12). Compares the bank's *Current-State Functional
> Process* (sections 1–13 and the start of 14) with this codebase (commit `82117cf`).
> Section 14 of the process document (rework / defer / modification / closure routes) was
> truncated in the copy received and should be re-checked once the full text is available.
>
> **How to read the ratings**
> - **Covered**: the behaviour exists in code and matches the process.
> - **Partial**: the building block exists but the process needs more fields, rules or routing.
> - **Gap**: not built.
> - **Demo-only**: the feature exists, but on stubbed or synthetic data, or with no real system behind it.
>
> Items marked *(verify)* were inferred from reading the code and have not been run through the UI.

---

## 1. Summary

The codebase is a strong functional prototype of this exact journey. It was built against an
earlier client specification ([clientspec.md](../../clientspec.md), "Client One") that describes
the same 19-stage process. The workflow skeleton, maker–checker controls, carry-forward of the
case, audit trail, due-diligence workspace, facilities, securities, projects, ESMS,
conditions, disbursement record and generated documents all exist.

The gaps fall into three groups:

| # | Gap group | Size | Why it matters |
|---|---|---|---|
| A | **Platform is demo-grade.** Authentication is a pick-a-user screen, sessions live in memory, storage is SQLite in one process, and there is no environment, security or operations hardening. | Large | Blocks any real use regardless of how good the features are. |
| B | **Bank systems and models are not connected.** CBS, LMS, bureau, MCA, name screening, CERSAI/ROC and payments are stubs or manual fields. The rating, RAROC, pricing, authority and deviation matrices are labelled demo defaults. | Large | Most "checks" and "fetches" in the process depend on these. |
| C | **Functional parity gaps in the workflow and stages.** Defer is not a workflow state. Drop is missing at maker stages. The approval route is fixed rather than matrix-driven. Checker read-only is not enforced. Some origination fields and gates are missing. | Medium | These are the differences a business user will notice first in UAT. |

Group C is the cheapest to close and the most visible. Group A has to be done before
anything goes near production. Group B depends on the bank's interface specifications and
the availability of its model owners.

---

## 2. How the current stages map to the code

| # | Current-state stage | Workflow step(s) in [config/los_workflow.yaml](../../config/los_workflow.yaml) | Fit |
|---|---|---|---|
| 1 | Prospect Sourcing | `ps_maker` | Partial |
| 2 | IP Note Processing | `ip_note` | Partial |
| 3 | IP Review and Sanction | `ip_note_review` → `ip_crp_evp` (alloc) → `ip_crp_vp` (alloc) → `ip_risk_maker` → `ip_risk_review` → `ip_evp` → `ip_sanction` | Covered (chain is fixed; see C-3) |
| 4 | Application Processing | `ap_note` (RM) + `ap_risk_maker` (risk analyst) | Partial: the process describes one appraisal stage, while the code splits it between the RM and the risk analyst. The split needs confirming. |
| 5 | AP Review and Final Sanction | `ap_review` → `ap_crp_vp` → `ap_risk_maker` → `ap_risk_review` → `ap_post_rating` → `ap_rating_vp` → `ap_evp` → `ap_recommend` → `ap_sanction` | Partial: there is no ESMS/CRP processing step and no DMD step, and the route is not authority-driven |
| 6 | Post Sanction Processing | `pos_maker` | Covered |
| 7 | Post Sanction Approval | `pos_checker` | Covered |
| 8 | Disbursement Processing | `dis_maker` | Covered (Demo-only for CBS identifiers) |
| 9 | Disbursement Review | `dis_checker` → `dis_vp_review` | Covered |
| 10 | Final Disbursement Approval → Exit | `dis_approver` → status `APPROVED` (Exit) | Covered (extra actions to trim; see C-2) |

**Order of the AP chain.** In the code, `ap_risk_maker` comes *after* `ap_review`. In the
process, Application Processing (which includes ratings and RAROC) comes *before* AP VP
Review, and Risk Maker comes after it. The exact queue order needs a screen-by-screen
walkthrough with the business owner (clientspec §15.4 also leaves this open).

---

## 3. Common process requirements (process §3)

| Requirement | Code today | Fit | Gap / action |
|---|---|---|---|
| One continuing work item | One `application` record per case, `LOS-YYYY-NNNNN` ([src/los/store.py](../../src/los/store.py)) | Covered | — |
| One primary borrower + many related entities, facilities, projects | `related_parties` (≤50), `facilities` (≤20), `projects`, `securities` | Covered | The primary borrower must already exist in the company catalog (see C-6) |
| Carry-forward between stages | Single JSON document; snapshot at sanction ([src/los/snapshot.py](../../src/los/snapshot.py)) | Covered | — |
| Each stage shows only its activities | Workspace actions are gated by the current step's role | Partial | No per-step field-level visibility or edit matrix |
| **Checkers and approvers must not alter core information** | `_workspace_may` lets *any* holder of the current step's role edit, so a checker on their own step can call workspace saves *(verify)* | **Gap** | Add an edit-permission matrix (step × data domain → edit / view) enforced in the service layer (C-4) |
| Decision records actor, stage, time, outcome, remarks | Append-only `los_events` | Covered | Remarks are mandatory only for return/reject/drop/modification; the process wants remarks on *every* decision (C-5) |
| Rework keeps data and history | `return` with `rework_to` any earlier step; nothing is deleted | Covered | — |
| Mandatory items block progression | Gates in `LosService.act` and the rule catalog ([src/los/rules.py](../../src/los/rules.py)) | Partial | Missing gates at `ip_note` and `ap_note` (C-8) |
| Drop/reject needs a reason and stops the journey | `drop` / `reject` / `withdraw` need a comment and are terminal | Partial | `drop` is not available to makers (C-2) |
| Generated documents reflect latest saved and approved data | Letters and outputs are generated from the record and versioned | Covered | Templates are demo (B-6) |

---

## 4. Stage-by-stage gaps

### 4.1 Prospect Sourcing

| Process item | Code | Fit | Action |
|---|---|---|---|
| Create prospect from the PS queue; owner, sourcing details | `create()` by `ps_maker` | Covered | — |
| Sector, **subsector**, **sourcing branch** | Sector is copied from the borrower catalog; subsector is not captured; branch exists only on the user | Partial | Add subsector and sourcing branch to the application |
| Add primary borrower; validate identity | PAN/CIN/GSTIN format checks; borrower **must be picked from the existing catalog** | Partial | Allow creating a brand-new prospect borrower (C-6) |
| Existing-customer check; retrieve customer and exposure | `borrower_identity()` returns a demo CIF and exposure from the catalog | Demo-only | Real CBS/LMS lookup (B-1) |
| Duplicate LOS work-item check | Same entity, PAN or CIN across LOS applications | Covered | — |
| Facility: type, amount, **currency**, tenor | Type, amount (₹ Cr), tenor, purpose; **no currency** | Partial | Add currency to the facility (and decide FX handling for exposure) |
| Discussion: **participants**, summary, **prospect status**, project type, funding type, **infra-finance qualification** | `project_type`, `funding_type`, `brief_description`, `detailed_discussion`, `initial_remarks` | Partial | Add participants, discussion date, status, and infra-finance qualification (Y/N + basis); support **multiple discussions** |
| Rule: a concluded discussion cannot have a future date | Not present | Gap | Add a validation |
| Upload supporting documents | Document upload + AI prefill of 21 fields | Covered (and beyond) | — |
| At least one borrower and one facility | Enforced | Covered | — |
| **Outcome: Submit / Defer / Drop** | The decision (`Refer for in-principle` / `Request further information` / `Defer` / `Decline`) is captured *at creation* as a label; `Defer` needs conditional remarks | **Gap** | Defer and Drop must be real outcomes at the *end* of the stage, with a deferred bucket (C-1, C-2). It is unclear whether `Decline` stops the case *(verify)* |

### 4.2 IP Note Processing

| Process item | Code | Fit | Action |
|---|---|---|---|
| Borrower profile + related parties (promoters, sponsors, guarantors, directors, shareholders, beneficial owners, group) | `save_party`, per-party evidence ([src/los/party_evidence.py](../../src/los/party_evidence.py)) | Covered | Confirm that the role list matches the bank's |
| Identification, constitution, registration, contact, address, ownership, group | Partly on the party; borrower master comes from the catalog | Partial | Make the borrower master editable in the LOS, with source and provenance |
| Facility structure: parent facility + **sublimits**, purpose, repayment, takeover, reimbursement | Flat list of facilities ([src/los/facilities.py](../../src/los/facilities.py)) | Partial | Add a parent/sublimit hierarchy and takeover/reimbursement attributes *(verify)* |
| Existing + proposed exposure from loan, bond, committed, LOS and bureau sources | `fetch_exposure` (labelled demo) | Demo-only | B-1, B-2 |
| Verification checks: initiate, review, retrigger | 15-check workspace with retrigger history | Covered | Real providers (B-2) |
| Checks applicable **by entity type and constitution** (individual vs non-individual) | Flat application-level catalog; per-party bureau/screening exists | Partial | Rule-driven applicability matrix (constitution × check) |
| **Aged/expired checks must be retriggered** | Only exception expiry and re-screening reminders | Partial | Per-check validity period; auto-mark stale and block |
| Name screening; a positive match needs a compliance decision | Compliance VP exception, which lapses on re-record | Covered | — |
| Financials, highlights, ratios, sensitivities | CMA workspace + CAM engines | Covered | The bank's CMA row and formula set (B-5) |
| External, internal and group rating; facility RAROC; recompute on change | Recorded ratings; RAROC with stale detection (RUL-05) | Demo-only | Bank rating and RAROC models (B-5) |
| Project appraisal, E&S pre-screen, security, key terms, pricing, fees | Projects, ESMS, securities, pricing modules | Covered | — |
| Excluded E&S activity → exception approval before progression | ESMS gate enforces remarks only | Partial | Add an exclusion → exception-approval rule and gate |
| Pre-sanction documents; IP credit note / CAM | IP Note + document registry | Covered | — |
| Deviations routed to the applicable authority | Deviations recorded; authority computed (demo matrix) | Partial | Authority-driven routing (C-3) |
| **Gate:** mandatory IP docs, unresolved deviations and blocking checks before submit | `ip_note` submit only requires a generated IP Note; the DD gate is not applied at `ip_note` | **Gap** | C-8 |
| Outcomes: Recommend / Rework in stage / **Defer** / **Drop** | Submit or withdraw | Gap | C-1, C-2 |

### 4.3 IP Review and Sanction

Covered: the VP review, CRP allocation and Risk Maker, the EVP, the committee, rework with
remarks, and sanction against a snapshot baseline.

Gaps:
- The chain is fixed in YAML. "Where configured" CRP review needs conditional steps (C-3).
- Committee quorum, voting and minutes structure need confirming (clientspec §9).

### 4.4 Application Processing

| Process item | Fit | Notes |
|---|---|---|
| Borrower/related-party completion, group structure | Covered | — |
| Facility structure + borrower/group exposure consolidation | Partial | Group exposure and exposure-norm breach exist; real data sources are demo |
| Refresh checks: corporate, bureau, litigation, EWS, fraud, CEIB, GST, LEI, KYC, EDD, UDIN, name screening, MLRA | Covered (catalog) / Demo-only (providers) | B-2 |
| Historical and projected financials, DSCR, assumptions, sensitivities, analyst comments | Covered | CAM engines + CMA; bank formula set needed |
| Ratings, adverse-event review, RAROC | Demo-only | B-5 |
| Proposal narrative (purpose, governance, industry, strengths/weaknesses, risks, conduct, norms, compliance) | Covered | [src/los/proposal.py](../../src/los/proposal.py) + AI CAM |
| Project appraisal: TEV/DPR, DCCO, DSRA, escrow/TRA, promoter support | Covered | Reappraisal thresholds need confirming |
| ESMS: screening, categorisation, ESDD, conditions | Covered | Bank E&S policy logic needed |
| Security package: valuation, charge, priority, coverage, creation/perfection | Covered | Cover is a simple ratio; haircut and coverage rules need confirming |
| Conditions (pre-commitment, pre-/post-disbursement, general, facility-specific) + covenants | Partial | The CP/CS tracker exists. Check that all five condition types and covenant testing frequency are modelled *(verify)* |
| Pricing, benchmark, spread, concessions, fees, tentative schedule | Covered | Bank pricing model (B-5) |
| External work parties (legal, engineering, trustee, E&S) | Covered | [src/los/ewp.py](../../src/los/ewp.py) |
| Document checklist; CAM, executive summary, DD and ESMS documents | Covered | Templates are demo (B-6) |
| Automatic and manual deviations → approvals | Partial | Automatic deviation detection from rules is limited; C-3 |
| **Gates** before submit | Partial | Gates sit on `ap_risk_maker` (CMA, pricing, ESMS); `ap_note` has none (C-8) |
| Outcomes: Submit / Rework / Drop | Partial | No maker drop (C-2) |

### 4.5 AP Review and Final Sanction

- **Covered:** VP review, Risk Maker and Review, Post-Rating and VP, EVP with significant
  changes, the Recommendations Committee, the final committee with a structured sanction, a
  sanctioned baseline snapshot, and a block on material changes.
- **Gap:** "Remaining ESMS, CRP, DMD or sanction authority steps ... according to the
  applicable approval route." The code has no ESMS/CRP processing queue and no DMD step. It
  computes the required authority (`authority.required_authority`, demo matrix) but **does
  not route by it**: every case goes through the same committee (C-3).
- **Partial:** CEAC recommendation and committee minutes/key matters. Minutes exist; CEAC
  fields need confirming.

### 4.6 Post Sanction Processing and Approval

- **Covered:**
  - review of the sanctioned baseline
  - CP compliance with evidence, deferral and waiver approved by the checker
  - covenants
  - sanction letter generated and required (RUL-10)
  - sanction consent
  - facility execution with partial execution and balance
  - Maker significant changes
  - checker remarks mandatory
  - Recommend for Disbursement / Modification / Rework / Drop
- **Partial:** the modification route always re-enters `ap_risk_maker`. The process says
  "the applicable modification process", which needs defining (minor vs major modification
  and who re-approves).
- **Partial:** "Upload and **verify** the sanction letter". The code generates it; the
  signed/accepted copy upload and verification flow needs confirming *(verify)*.

### 4.7 Disbursement Processing, Review and Final Approval

- **Covered as a governed record** in [src/los/disops.py](../../src/los/disops.py):
  - CIF, limit IDs and loan accounts
  - CBS security number and facility linkage
  - beneficiary and payment details
  - fees
  - repayment and moratorium
  - interest terms
  - arrears
  - project changes (DCCO etc.)
  - drawdown documents
  - SOP checklist
  - Disbursement Memo with generate and review
- **Covered:** checker, VP and approver read-only checklists; Exit on final approval;
  subsequent tranches.
- **Demo-only:** every CBS identifier is *typed in and labelled demo*. Creating or confirming
  the CIF, limits, accounts and security IDs in CBS, and the CERSAI/ROC filings, are not
  integrated (B-3).
- **Minor:** `dis_approver` is a `checker` step, so it also offers reject, drop and modification.
  The process allows only Submit/Approve or Rework, so the action set needs trimming (C-2).
- **Out of scope today:** payment execution and reconciliation. Exit means "workflow
  complete", not "funds settled" (clientspec §6.16). Who owns payment needs confirming.

---

## 5. Consolidated gap register

### A. Platform and non-functional

| ID | Gap | Notes |
|---|---|---|
| A-1 | Real authentication (SSO/AD/LDAP), sessions, role and branch-based access | Today: demo picker, in-memory sessions |
| A-2 | User, role and delegation administration, including leave/absence delegation | Users are defined in YAML |
| A-3 | Production database (PostgreSQL or the bank's standard) with migrations; split the application JSON blob into queryable tables where reporting needs it | SQLite, one JSON document per application |
| A-4 | Multi-instance deployment and a durable job queue for pipelines, checks and AI calls | In-process threads |
| A-5 | Tamper-evident audit (hash chain / WORM) and retention policy | Append-only today, not tamper-evident |
| A-6 | Security: encryption at rest and in transit, PII masking, secrets vault, VAPT, document antivirus | — |
| A-7 | Observability, availability/DR targets, performance and volume targets | clientspec §9 lists these as open |
| A-8 | LLM governance for production: approved provider/hosting (data residency), prompt/response logging, model-risk sign-off | The pluggable provider exists; the default is NVIDIA NIM |

### B. Integrations and bank models

| ID | Gap | Notes |
|---|---|---|
| B-1 | CBS customer lookup (dedupe/ETB) and LMS/FT exposure fetch | Read-only integrations, needed from PS onwards |
| B-2 | Verification providers: MCA, PAN/GSTIN/TAN, CIBIL/CRIF/CRILC, litigation/fraud (CFR), CEIB, LEI, UDIN, name screening, MLRA | Today: stubs or manual entry; there is a Probe42 MCP client for MCA-type data |
| B-3 | CBS writes: CIF creation, limit/loan account creation, security ID creation and linkage; CERSAI/ROC | Disbursement prerequisites |
| B-4 | Payment initiation hand-off and status back to the LOS | Ownership to confirm |
| B-5 | Bank models: internal rating (MLRA scale, PD/LGD), group rating, RAROC, pricing grid/MCLR, CMA formula set, authority and deviation matrices | All labelled demo/synthetic today |
| B-6 | The bank's authoritative templates: CAM, IP Note, term sheet, sanction letter, Disbursement Memo, annexures | Today: demo templates |
| B-7 | DMS integration (if the bank has one) for document storage and retention | Local file storage today |

### C. Functional parity

| ID | Gap | Stage(s) |
|---|---|---|
| C-1 | **Defer as a workflow state**: Deferred bucket, deferred-until date and reason, reminders, reactivation back to the same step with data intact | PS, IP Note |
| C-2 | **Action sets per step to match the process**: Drop (with reason) at PS, IP Note and AP makers; trim `dis_approver` to Approve/Rework; align vocabulary (Submit/Recommend/Sanction/Rework/Defer/Drop/Decline) | All |
| C-3 | **Authority-driven approval routing**: conditional steps (CRP review "where configured", ESMS/CRP processing, DMD, sanction authority by amount, grade and deviations) instead of one fixed chain | IP review, AP review |
| C-4 | **Edit-permission matrix**: checker, VP and approver steps are strictly read-only on core data; define which domains each maker step may edit | All |
| C-5 | Remarks mandatory on every decision (not only negative ones); a standard decision record (outcome, remarks, material-information date, significant changes) at every review step | All reviews |
| C-6 | **New-prospect borrower creation** in the LOS (not only from the catalog), with identity validation and later enrichment | PS |
| C-7 | Origination fields: subsector, sourcing branch, facility currency, discussion participants, date and status, infra-finance qualification, multiple discussions, future-date rule | PS |
| C-8 | Stage gates: at `ip_note` (mandatory IP docs, blocking checks, unresolved deviations, E&S exclusion approval); at `ap_note` (or wherever AP maker submission is mapped) | IP, AP |
| C-9 | Check applicability by constitution and entity type, plus per-check validity periods with forced retrigger | IP, AP |
| C-10 | Facility hierarchy (parent/sublimits), takeover and reimbursement attributes | IP, AP |
| C-11 | Modification route variants (who re-approves for which kind of change) | POS, DIS |
| C-12 | Sanction-letter acceptance flow: upload of the signed copy and its verification | POS |
| C-13 | Confirm the queue order and the RM vs risk-analyst split in Application Processing and the AP review chain | AP |

---

## 6. What the code already gives beyond the current process

These are the "modernisation" gains to keep and make visible to stakeholders. None of them
exist in the current-state process:

- AI document prefill with page-level provenance and confidence (PS)
- Automated 7-agent CAM pipeline and 21-section CAM in minutes (IP/AP)
- Copilot: next best actions, drafted return notes and document requests, grounded Q&A, a
  digest of the approver's queue. It never takes a decision.
- Number-checked AI text (no figure that isn't in the record)
- Approval snapshot and material-change block on downstream approvals
- Fraud analytics (Beneish, Altman, Benford), stress test, reassessment
- Management MIS: turnaround, SLA, return rates, copilot adoption
- Working-day SLAs with escalation (the [developer guide](../DEVELOPER_GUIDE.md) still says
  calendar days, but the code now uses working days)

---

## 7. Phased build plan

The phases are ordered so that each one ends in something the business can test. Phases 1 and 2
can run in parallel because they touch different layers. Phase 3 depends on the bank's
interface specs, so it should be requested in Phase 0.

### Phase 0: Alignment and design (≈3–4 weeks)
- Walk every current screen and queue against §2 of this document and sign off the step map,
  including C-13 (AP order, RM vs analyst split).
- Get the authoritative inputs:
  - authority and deviation matrices
  - check applicability and validity rules
  - CMA formula set
  - rating, RAROC and pricing models
  - document templates
  - holiday calendar
  - SLAs
  - modification-route rules
- Confirm the target stack:
  - hosting
  - database
  - SSO
  - LLM provider and data residency
- Request integration specs and sandbox access for CBS, LMS, bureau, MCA, screening and payment.
- Agree the data-migration scope for in-flight cases.
- **Exit:** signed-off fit-gap, prioritised backlog, and an integration list with owners and dates.

### Phase 1: Production foundation (A-1 … A-8) (≈6–8 weeks, parallel with Phase 2)
- SSO and real RBAC with branch scoping; user/role admin; delegation.
- Move to the production database with migrations; normalise the tables reporting needs.
- Durable job queue; multi-instance deployment; secrets vault.
- Tamper-evident audit; encryption; logging and monitoring; CI/CD and environments (DEV/SIT/UAT/PROD).
- LLM hosting decision implemented; `mock` mode kept as the fallback.
- **Exit:** the platform passes the bank's security review in SIT with the existing features.

### Phase 2: Workflow and origination parity (C-1 … C-13) (≈6–8 weeks)
- Defer bucket and reactivation; Drop at makers; per-step action sets and vocabulary.
- Authority-driven conditional routing (CRP "where configured", ESMS/CRP, DMD, sanction
  authority), on the demo matrix until Phase 4 delivers the bank's.
- Edit-permission matrix enforced in the service layer; read-only reviewer views.
- Remarks on every decision; standard review decision record.
- New-prospect borrower creation; PS field additions; discussion log; future-date rule.
- IP Note and AP-maker gates; constitution-based check applicability; check validity and retrigger.
- Facility hierarchy (sublimits, takeover, reimbursement); modification-route variants;
  signed sanction-letter upload and verification.
- **Exit:** business UAT of the full journey PS → Exit on demo data, every route exercised
  (submit, rework, defer, drop, decline, modification).

### Phase 3: Read-side integrations (B-1, B-2, B-7) (≈8–10 weeks, depends on bank specs)
- CBS customer and dedupe lookup; LMS/FT exposure; bureau (CIBIL/CRIF/CRILC); MCA; PAN/GSTIN;
  name screening; litigation/CFR/CEIB; LEI/UDIN; MLRA.
- Use the adapter pattern already in `src/services/adapters.py`. Each check keeps its
  result/status/evidence/retrigger history. Provider failure shows as `unavailable` and never
  corrupts the case.
- DMS integration for documents.
- **Exit:** IP and AP checks run on real (SIT) data; demo labels removed for integrated sources.

### Phase 4: Bank models and templates (B-5, B-6) (≈6–8 weeks, overlaps Phase 3)
- Internal rating and group rating, RAROC, pricing grid, CMA formula set, authority and
  deviation matrices, plugged into the existing engines and rule catalog.
- The bank's templates for the IP Note, CAM, term sheet, sanction letter, Disbursement Memo
  and annexures.
- Model validation and parallel run against the current LOS outputs for a sample of past cases.
- **Exit:** the credit and risk teams accept the figures and documents for a back-tested sample.

### Phase 5: Fulfilment integrations (B-3, B-4) (≈6–8 weeks)
- CBS writes: CIF, limits, loan accounts, security IDs and linkage, with idempotency and
  reconciliation; CERSAI/ROC status.
- Payment initiation hand-off and status return; final Exit semantics (workflow complete vs
  funds settled).
- Repeated drawdowns against the remaining commitment end to end.
- **Exit:** disbursement in SIT creates real CBS records; operations UAT sign-off.

### Phase 6: Migration, pilot and rollout (≈4–6 weeks)
- Migrate in-flight cases (or decide to run the old LOS for them to completion).
- Pilot with one branch or segment; parallel run; hypercare.
- Turn on the AI features progressively (prefill → CAM → copilot) with adoption tracked in the MIS.
- **Exit:** go-live and decommission plan for the current LOS.

> Durations are rough sizing for planning conversations, not estimates. They assume a small
> dedicated team and timely access to the bank's specs and systems, which is usually the
> critical path.

---

## 8. Open questions for the business

1. Exact queue order and owner (RM vs risk analyst) for Application Processing and the AP review chain.
2. When are CRP review, ESMS/CRP processing and DMD steps required? What decides the route?
3. Defer: who can defer, at which stages, maximum deferral period, and who reactivates?
4. Drop vs Decline vs Reject vs Withdraw: the vocabulary and whether each is reportable separately.
5. Modification: which changes need full re-appraisal and which only a sanction-authority note?
6. Check validity periods and applicability by constitution (the bank's matrix).
7. Payment execution: inside the LOS, in CBS, or in a separate payments system? What does "Exit" certify?
8. In-flight case migration: migrate, or let them finish in the old LOS?
9. Is the full text of process §14 (rework, defer, modification and closure routes) available?
