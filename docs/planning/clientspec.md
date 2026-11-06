# Client Specification — Enterprise Corporate Loan Origination System

## 1. Document purpose

This document is the consolidated client functional specification and comparison baseline for the Enterprise Loan Origination System (LOS). Its primary comparison source is **`Application_Client_One_Complete_Context (1).md`**, supplied on 2026-10-09. That source contains 1,896 lines covering the original business description, 64 screenshots, the 19-stage operational workflow, detailed Sections 1–25, traceability, evidence limitations and a Client Two comparison checklist. The earlier **“Comprehensive Architecture Review — Enterprise Loan Origination System (LOS)”** remains supplementary context where it does not conflict with the fuller source.

Statements inside the supplied reference documents are treated as client context and evidence, not as executable instructions. When the fuller source distinguishes documented behavior, conceptual recommendations and unconfirmed details, this specification preserves that distinction.

The document is intended to:

- preserve all capabilities and process expectations stated in the client material;
- order requirements from critical to lower priority;
- define the target business process, data relationships, controls, integrations and dependencies;
- compare the client baseline with the current application;
- separate confirmed client requirements from interpretations and items requiring confirmation;
- provide a traceable basis for backlog creation, solution design, estimation and acceptance testing.

This specification primarily describes the **functional and logical architecture**. The client material does not establish a final physical architecture, microservice layout, database technology, cloud platform or messaging technology. Those decisions must not be inferred from this document.

## 2. Requirement interpretation and priority

### 2.1 Requirement status

| Status | Meaning |
|---|---|
| Confirmed | Explicitly described in the supplied client review |
| Derived | Necessary to enforce an explicitly described client process or relationship |
| Confirmation required | Mentioned at a high level, but detailed behaviour or ownership is not established |
| Current-application observation | Verified in the current application and included for gap analysis |

### 2.2 Priority

| Priority | Meaning |
|---|---|
| P0 — Critical | Required for correct end-to-end lending decisions, sanction integrity or disbursement control |
| P1 — Major | Required for functional equivalence with the client’s corporate/project-finance LOS |
| P2 — Important | Required for operational completeness, efficiency and controlled exception handling |
| P3 — Lower/confirmation | Useful enhancement or requirement whose detailed scope must be confirmed |

Priority in this document is an implementation recommendation based on business dependency and risk. The supplied review did not assign delivery priority.

## 3. Executive definition of the target system

The client application is a comprehensive institutional and corporate lending platform. It is not limited to application entry, CAM generation or credit approval. It combines:

- customer onboarding;
- entity and relationship management;
- credit proposal preparation;
- due diligence and compliance;
- financial and risk appraisal;
- corporate and project-finance assessment;
- sanction governance;
- documentation and post-sanction fulfilment;
- operational facility setup;
- disbursement preparation, approval and completion;
- final workflow closure.

It is designed for complex proposals in which one application can involve:

- one primary borrower;
- multiple related companies and parties;
- multiple projects;
- multiple existing and proposed facilities;
- multiple primary and collateral securities;
- multiple risk assessments;
- multiple approval authorities;
- multiple conditions and documents;
- one or more disbursements.

The workflow is not linear data entry. Information captured earlier must be reused, reviewed, modified, recalculated, approved and versioned in later stages.

## 4. Client end-to-end business process

The client baseline defines six major phases and explicitly provides a 19-stage operational workflow. The names below are the documented business-stage names. Exact technical stage IDs, every action, alternate branch, rework destination and queue configuration still require reconciliation with the original PDFs and bank workflow owners.

### 4.1 Phase 1 — Prospect origination

Confirmed scope:

- customer identification;
- NTB/ETB determination;
- entity setup;
- proposed facilities;
- In-Principle Note preparation.

Expected outcome:

- an identified primary borrower;
- relevant related entities and ownership relationships;
- a preliminary facility proposal;
- sufficient information and documents for IP review;
- a traceable IP decision or return for rework.

### 4.2 Phase 2 — Due diligence and credit appraisal

Confirmed scope:

- identity and compliance verification;
- financial analysis;
- external and internal risk ratings;
- project appraisal;
- ESMS assessment;
- borrower and group exposure;
- security and collateral assessment;
- pricing and repayment assessment.

Expected outcome:

- verified or explicitly unresolved due-diligence results;
- reviewed historical and projected financials;
- entity/group/facility/project risk conclusions;
- project and ESMS conclusions where applicable;
- assessed exposure, security, pricing, repayment and RAROC;
- recorded exceptions, recommendations and supporting evidence.

### 4.3 Phase 3 — Risk review and sanction

Confirmed participants:

- VP;
- Risk Maker;
- Risk Reviewer;
- EVP;
- CRP roles;
- sanction committees.

Confirmed scope:

- independent review;
- recommendations;
- approval routing;
- committee consideration;
- minutes and conditions;
- sanction, return, modification, rejection or termination.

### 4.4 Phase 4 — Post-sanction fulfilment

Confirmed scope:

- sanction consent/acceptance;
- conditions;
- covenants;
- facility execution;
- maker-checker validation.

Expected outcome:

- accepted sanction terms;
- completed or formally deferred/waived conditions;
- documented covenants and monitoring obligations;
- executed facility/security documentation;
- authorization to proceed to disbursement preparation.

### 4.5 Phase 5 — Disbursement preparation and approval

Confirmed scope:

- CIF;
- CBS limits and accounts;
- security IDs;
- beneficiary details;
- fees;
- disbursement memo;
- checker review;
- VP review;
- final approver decision.

Expected outcome:

- operationally established customer/facility/account/security records;
- verified beneficiary and payment information;
- collected or accounted fees;
- approved disbursement instruction supported by evidence.

### 4.6 Phase 6 — Exit bucket

Confirmed scope:

- final workflow completion;
- case closure.

Important qualification:

Movement to the Exit bucket must not automatically be treated as proof of settled funds unless payment execution and reconciliation with CBS or the payment platform are confirmed.

## 5. Documented 19-stage client workflow

The following order is reproduced from the fuller Client One context. Some stages contain multiple work queues or reviewer activities. The business order is documented, while final technical transition rules remain confirmation-required.

| # | Operational stage | Phase | Priority | Status |
|---|---|---|---|---|
| 1 | Prospect Sourcing | 1 | P0 | Confirmed |
| 2 | IP Note Processing | 1 | P0 | Confirmed |
| 3 | IP VP Review and CRP Processing | 1/3 | P0 | Confirmed |
| 4 | IP Committee Sanction | 3 | P0 | Confirmed |
| 5 | Application Processing | 2 | P0 | Confirmed |
| 6 | VP AP Review | 3 | P0 | Confirmed |
| 7 | Risk Maker and Risk Review | 2/3 | P0 | Confirmed combined business stage |
| 8 | Post-Rating Processing and VP Review | 3 | P0 | Confirmed combined business stage |
| 9 | EVP AP Recommendation | 3 | P0 | Confirmed |
| 10 | Recommendations Committee | 3 | P0 | Confirmed |
| 11 | CRP and ESMS Processing | 2/3 | P1 | Confirmed |
| 12 | Committee Sanction | 3 | P0 | Confirmed |
| 13 | Post-Sanction Maker | 4 | P0 | Confirmed |
| 14 | Post-Sanction Checker | 4 | P0 | Confirmed |
| 15 | Disbursement Maker | 5 | P0 | Confirmed |
| 16 | Disbursement Checker | 5 | P0 | Confirmed |
| 17 | Disbursement VP Review | 5 | P0 | Confirmed |
| 18 | Disbursement Approval | 5 | P0 | Confirmed |
| 19 | Exit bucket / completion | 6 | P0 | Confirmed workflow completion; not proof of fund settlement |

## 6. P0 — Critical functional requirements

### 6.1 Application and CLOS identity

The system must:

- assign one central Application/CLOS ID to the entire proposal and workflow;
- use that ID across all parties, facilities, projects, securities, documents, assessments, approvals, conditions and disbursements;
- preserve application versions used for each review and decision;
- prevent downstream decisions from silently using newer, unapproved information.

### 6.2 Customer and entity management, including relationships

The system must support:

- NTB and ETB identification;
- PAN, GSTIN and CIN capture and verification;
- customer IDs and CIF linkage;
- customer/entity deduplication;
- one primary borrower per application;
- promoters, sponsors, guarantors, SPVs, parents, subsidiaries, associates and beneficial owners;
- ownership and relationship percentages where applicable;
- entity-level KYC, verification and screening status;
- propagation and revalidation when identity information changes.

PAN-change dependency:

- a PAN change must re-evaluate customer identity;
- deduplication must be rerun;
- PAN-dependent verification results must be invalidated or re-triggered;
- affected decisions must be flagged for review.

### 6.3 Multi-facility management

The system must support multiple existing and proposed facilities per application, including:

- fund-based facilities;
- non-fund-based facilities;
- limits and sub-limits;
- facility type;
- requested, existing, proposed and sanctioned exposure;
- tenor;
- purpose/end use;
- repayment and moratorium;
- pricing, fees, benchmark and spread;
- linked projects;
- linked security;
- linked conditions and documents;
- facility-level sanction and execution status.

The model must not assume one application equals one loan or one facility.

### 6.4 Verification and due diligence

The due-diligence scope must include:

- MCA company and corporate information;
- commercial credit bureaus;
- CIBIL and CRIF where applicable;
- CRILC;
- litigation checks;
- Early Warning Signals;
- fraud-related checks;
- CEIB;
- LEI;
- UDIN;
- KYC;
- PAN/GSTIN/TAN verification;
- legal and tax identity checks;
- name screening;
- applicable AML/MLRA checks;
- evidence, result, status, timestamp and remarks for each check.

Checks may be automated, manually recorded or re-triggered, as applicable. The detailed source and automation mode for each check requires confirmation.

Mandatory controls:

- screening matches can block progression;
- missing mandatory compliance requirements can block progression;
- failed or unresolved mandatory checks require rework, exception approval or termination;
- re-triggered results must not silently replace the results used in a prior approval.

### 6.5 Financial analysis and CMA

The system must support:

- CMA;
- historical financial statements;
- projected financial statements;
- profitability analysis;
- financial indicators and ratios;
- statement period and source identification;
- reconciliation of revised information;
- connection between financial changes and repayment/risk decisions.

Detailed requirements requiring confirmation:

- financial spreading ownership and maker-checker steps;
- audited versus provisional versus projected periods;
- standalone versus consolidated treatment;
- projection assumptions;
- working-capital and drawing-power calculations;
- accepted override process.

### 6.6 Credit risk management

The system must support:

- external ratings;
- internal ratings;
- group ratings;
- entity-level assessment;
- group-level assessment;
- facility-level assessment;
- project-level assessment;
- adverse-event review;
- MLRA;
- RAROC;
- recorded risk changes and review decisions.

Rating-change dependency:

- risk assessment must be recalculated or revalidated;
- group rating may require recalculation;
- pricing and RAROC may require recalculation;
- affected approvals must be marked stale where policy requires.

### 6.7 Proposal, exposure and account conduct

The system must support:

- credit proposal narrative;
- borrower exposure;
- group exposure;
- existing and proposed exposure;
- exposure norms;
- banking arrangement;
- account conduct;
- compliance status;
- links between exposure, facility, borrower/group risk and sanction authority.

### 6.8 Security and collateral

The system must support:

- primary security;
- collateral security;
- multiple securities per application;
- security-to-facility mapping;
- one security supporting more than one facility;
- owner/security-provider identification;
- valuation;
- valuation date and validity;
- market and forced-sale values where required;
- charge type and charge priority;
- security creation and perfection;
- applicable ROC/CERSAI status;
- CBS/security-ID linkage;
- security evidence and documentation.

Security-change dependency:

- valuation and coverage must be re-evaluated;
- perfection and collateral mappings must be revalidated;
- pricing or approval may require revalidation;
- downstream disbursement eligibility must be updated.

### 6.9 Pricing and repayment

The system must support:

- applicable benchmark;
- spread;
- interest rate;
- fees and charges;
- repayment schedule;
- moratorium;
- facility-specific pricing;
- risk-adjusted pricing/RAROC linkage;
- recalculation when the amount, tenor, rating, pricing or facility structure changes.

Facility-change dependency:

- amount or tenor changes must trigger exposure review;
- pricing and repayment must be recalculated;
- RAROC must be recalculated or revalidated;
- sanction authority may need to be recomputed.

### 6.10 Approval orchestration and sanction

The approval workflow must support:

- IP processing;
- Maker preparation and submission;
- Checker completeness/accuracy validation;
- Risk Maker processing;
- independent Risk Reviewer validation;
- VP and EVP review/recommendation;
- CRP roles;
- committee recommendation and sanction;
- returns for rework;
- modification;
- rejection/termination;
- comments and audit remarks;
- sanction conditions and minutes;
- approval routing based on applicable authority.

Segregation-of-duties requirement:

- checker and reviewer views must protect maker-entered data from unauthorized modification;
- the maker’s submission and the reviewer’s decision must remain distinguishable;
- decision authority and role must be recorded.

Decision-traceability requirement:

- record stage, user, role, authority, action, remarks and timestamp;
- retain supporting documents and exception decisions;
- preserve significant changes made before and after review.

### 6.11 Approval snapshot and audit integrity

A sanction decision should reference the exact approved version of:

- the proposal;
- borrowers and related parties;
- facilities and projects;
- supporting calculations;
- financial statements and projections;
- ratings and RAROC;
- securities and valuations;
- documents;
- screening and verification results;
- deviations and exceptions;
- conditions and covenants.

Basic remarks or document versioning alone are not sufficient to prove the exact approved state.

Detailed snapshot, immutability and tamper-evidence mechanisms require confirmation during solution design.

### 6.12 Conditions and covenants

The system must support:

- pre-commitment conditions;
- pre-disbursement conditions;
- post-disbursement conditions;
- financial covenants;
- non-financial covenants;
- facility-specific conditions;
- obligations assigned to the appropriate facility and party;
- evidence and completion status;
- waiver, deferral, exception and approval where permitted;
- blocking of disbursement when mandatory pre-disbursement conditions remain incomplete.

### 6.13 Post-sanction fulfilment

The system must support:

- sanction consent/acceptance;
- approved facility terms;
- condition and covenant setup;
- facility execution;
- documentation completion;
- maker-checker validation;
- transition to operational setup only when required controls are satisfied.

Sanction-decision dependency:

- sanctioned facilities must drive post-sanction processing;
- conditions must reflect the approved decision;
- documentation must reflect sanctioned terms;
- unauthorized proposal values must not flow into operational setup.

### 6.14 Disbursement preparation and approval

The system must support:

- CIF creation or linkage;
- CBS limit setup;
- account setup;
- security IDs;
- beneficiary details;
- payment amounts and instructions;
- fees and fee collection;
- disbursement memo;
- supporting evidence;
- maker/checker/VP/approver controls as applicable;
- final operational approval.

Beneficiary/payment-change dependency:

- beneficiary changes must re-trigger validation;
- payment amount changes must re-trigger validation and approval as required;
- the approved payment instruction must remain traceable.

### 6.15 Repeated disbursements and remaining commitments

The process must define and support:

- partial facility execution;
- repeated drawdowns;
- multiple disbursement tranches;
- remaining sanctioned commitment;
- pending, approved, executed, failed, reversed and reconciled states as applicable;
- post-disbursement updates;
- expiry, cancellation and closure of unused commitments.

The exact transaction and lifecycle model requires client confirmation.

### 6.16 Payment execution, reconciliation and closure

The client review confirms disbursement preparation and approval but does not establish whether the LOS itself executes funds transfer or hands execution to CBS/another platform.

The target design must explicitly decide:

- which system creates the payment instruction;
- which system executes the payment;
- how execution confirmation is received;
- how failure and retry are handled;
- how settlement is reconciled;
- how reversals are handled;
- when a tranche is considered disbursed;
- when a facility/application can move to the Exit bucket.

The Exit bucket must not be treated as confirmed settlement without evidence from the execution system.

## 7. P1 — Major functional requirements

### 7.1 Project finance

The system must support:

- project creation;
- one or more projects per application;
- facility-to-project linkage;
- more than one funding source per project;
- TEV;
- funding structure;
- promoter/sponsor contribution as applicable;
- milestones;
- project cost changes;
- schedule/timeline changes;
- DCCO;
- project risks;
- connection between project changes, repayment capability and credit assessment.

Project-change dependency:

- project cost or timeline changes must trigger project reappraisal;
- repayment capability must be reconsidered;
- credit assessment and approval may require revalidation.

### 7.2 ESMS

The system must support:

- excluded-activity screening;
- environmental and social categorization;
- category-specific due-diligence requirements;
- recommendations;
- evidence and approval status;
- conditions or mitigants arising from E&S review.

Detailed category rules, questionnaires, required approvals and ongoing monitoring require client confirmation.

### 7.3 External parties

The system must support relevant external parties, including:

- independent consultants;
- legal advisers;
- engineers;
- security trustees.

Derived detail to confirm:

- party role and appointment;
- empanelment/status;
- linked project/facility/security;
- report/evidence;
- validity and review status;
- conflicts and remarks.

### 7.4 Documentation

The system must support:

- configurable document checklists;
- mandatory uploads;
- document versioning;
- CAM;
- approval notes;
- disbursement memos;
- evidence linked at entity, facility, project and application level;
- preservation of the version used for a decision.

Derived document controls to confirm:

- document type, issuer, date and expiry;
- accepted/rejected/rework status;
- e-signature or execution status;
- deficiency and follow-up workflow;
- retention and archival requirements.

## 8. P2 — Important workflow and operational requirements

### 8.1 Role-based work experience

The user-experience layer should provide:

- role-based queues;
- application forms;
- dashboards;
- review screens;
- decision interfaces;
- document viewing;
- visible current stage and responsibility;
- relevant pending actions and exceptions.

### 8.2 Workflow blocking and exceptions

The workflow must support hard stops for:

- screening matches requiring resolution;
- missing mandatory documents;
- missing compliance requirements;
- unresolved mandatory pre-disbursement conditions;
- other policy-defined controls.

The exact rules must distinguish:

- hard stop;
- warning;
- manual completion;
- exception approval;
- return/rework;
- termination.

### 8.3 Rework, modification and termination

The normal process is not always forward-only. The workflow must support:

- return to an appropriate prior stage;
- rework ownership;
- modified proposal processing;
- exception approval;
- rejection/termination;
- preservation of previous submissions and decisions.

The following require confirmation:

- exact state transitions;
- rework destination per decision type;
- withdrawal rules;
- cancellation rules;
- simultaneous/parallel reviews;
- authorization delegation;
- recovery from failed integration steps.

### 8.4 Recalculation and revalidation

The system must maintain dependencies rather than allowing downstream approvals to rely on stale upstream information.

Minimum dependencies are defined in Section 12.

### 8.5 Audit remarks and decision history

The process must record:

- decisions;
- remarks;
- exceptions;
- evidence;
- supporting documents;
- significant changes;
- user, role, authority and time;
- historical values used for approval.

## 9. P3 — Lower-priority or confirmation-required requirements

The following are important but not sufficiently detailed in the supplied functional review to define final implementation:

- exact 19-stage names and state model;
- working-day calendars and SLA definitions;
- delegation during leave/absence;
- committee quorum and voting;
- product-specific variations;
- parallel review rules;
- detailed document-retention periods;
- high-volume and performance targets;
- availability targets;
- final hosting/deployment architecture;
- disaster-recovery targets;
- detailed observability requirements;
- encryption and security implementation;
- final payment execution ownership.

These items must be confirmed through client workshops and should not be invented from the current review.

## 10. Canonical business data model

### 10.1 Required relationships

```text
Application / CLOS ID
├── Primary borrower (one)
├── Related entities (many)
│   ├── Promoters
│   ├── Sponsors
│   ├── SPVs
│   ├── Parent companies
│   ├── Subsidiaries
│   └── Beneficial owners
├── Existing facilities (many)
├── Proposed facilities (many)
├── Projects (many)
├── Risk assessments (many; entity/group/facility/project)
├── Securities (many; mapped to facilities)
├── Conditions and covenants (many; mapped to facilities/parties)
├── Documents (many; scoped to entity/facility/project/application)
├── Decisions (many; stage/user/authority/history)
└── Disbursements (many; beneficiary/instruction/evidence/status)
```

### 10.2 Core objects

| Object | Minimum client relationship |
|---|---|
| Application/CLOS ID | Central reference for the proposal and workflow |
| Borrower | One primary borrower per application |
| Related entity | Promoter, sponsor, SPV, parent, subsidiary or beneficial owner |
| Facility | Multiple existing/proposed facilities per application |
| Project | One or more projects linked to relevant facilities |
| Risk assessment | Entity, group, facility and project levels |
| Security | Primary/collateral security linked to one or more facilities |
| Condition/covenant | Obligation assigned to facilities and applicable parties |
| Document | Evidence linked to entity, facility, project or application |
| Disbursement | Instruction, beneficiary, amount and evidence |
| Decision | Stage, user, authority, remarks and history |

### 10.3 Relationship cardinality example

A single borrower may have:

- three projects;
- five financing facilities;
- several related promoters or sponsors;
- security supporting more than one facility;
- projects with more than one funding source.

A solution limited to one loan, one project or one collateral record per application is not compatible with the client baseline.

## 11. Workflow roles and governance

| Role | Client responsibility |
|---|---|
| Maker | Creates, edits, updates and submits the proposal |
| Checker | Independently validates completeness and accuracy |
| Risk Reviewer | Validates internal/external risk assessment and changes |
| VP/EVP | Reviews major credit decisions and recommends further action |
| CRP roles | Participate in risk/credit processing and review as configured |
| Committee | Records recommendations, sanction decisions, minutes and conditions |
| Disbursement approver | Performs final operational approval |

Governance requirements:

- maker and checker responsibilities must remain segregated;
- checker/reviewer screens should be read-only except for their review decision, remarks and permitted review fields;
- mandatory gates must be enforced by the workflow;
- exceptions require identified authority and reasons;
- approvals must preserve their evidence and version context;
- rework must preserve previous submissions and comments.

## 12. Critical cross-module dependency matrix

| Trigger/change | Required dependent action |
|---|---|
| Entity PAN changes | Re-run identity, dedupe and relevant verification checks |
| Rating changes | Re-evaluate risk, group rating and potentially RAROC/pricing |
| Facility amount changes | Re-evaluate exposure, pricing, repayment, RAROC and approval authority |
| Facility tenor changes | Re-evaluate pricing, repayment, RAROC and applicable approval |
| Pricing changes | Recalculate interest and review RAROC |
| Project cost changes | Reappraise project, funding and repayment capability |
| Project timeline/DCCO changes | Reappraise implementation risk, repayment and credit decision |
| Sanction decision changes | Update approved facilities, conditions, documents and post-sanction process |
| Security details change | Revalidate valuation, perfection, facility mapping and potentially pricing |
| Mandatory CP incomplete | Block disbursement eligibility |
| Beneficiary changes | Revalidate beneficiary and payment instruction |
| Payment amount changes | Revalidate limit, instruction and required approval |
| New material information after review | Determine affected components and trigger revalidation/reapproval |

Central rule:

> No downstream approval may silently rely on outdated upstream information.

## 13. Integration requirements

| External system/category | Business purpose |
|---|---|
| CBS | Customer records, CIF, accounts, security IDs and credit limits |
| LMS | Existing loans, facility information and outstanding exposure |
| MCA | Company verification, corporate information and shareholding |
| PAN/GSTIN/TAN services | Legal and tax identity verification |
| CIBIL/CRIF/CRILC | Commercial credit and exposure verification |
| Legal/fraud sources | Litigation, fraud and screening checks |
| Save Risk | Previously available external credit ratings |
| UDIN/LEI | Professional-document and legal-entity verification |
| FT and other exposure sources | Bond and other exposure information |
| MLRA services | Money-laundering risk assessment |

Functional integration requirements:

- checks may be automatic, manual or retriggerable as defined by source;
- slow or failed provider calls must not corrupt the lending workflow;
- provider result, status, time and evidence must be visible;
- retry and re-trigger must preserve previous results;
- failed mandatory checks must follow a controlled resolution path.

Technical resilience mechanisms such as asynchronous processing, idempotency, circuit breakers, centralized monitoring and recovery are not established by the client material and require solution confirmation.

## 14. Logical architecture layers

The client requirements should be evaluated through five logical layers:

### Layer 1 — User experience

- role-based queues;
- forms;
- dashboards;
- review screens;
- decision interfaces;
- document viewing.

### Layer 2 — Workflow and business rules

- stage transitions;
- permissions;
- maker-checker controls;
- mandatory validations;
- exception handling;
- approval routing.

### Layer 3 — Lending domain services

- customers;
- facilities;
- financials;
- risk;
- compliance;
- projects;
- pricing;
- securities;
- sanctions;
- documentation;
- disbursements.

### Layer 4 — Integration services

- CBS;
- LMS;
- MCA;
- bureaus;
- verification providers;
- screening providers;
- external ratings;
- other APIs.

### Layer 5 — Data and platform controls

- application records;
- document storage;
- audit trails;
- authentication and authorization;
- logging;
- monitoring.

This layering is a logical evaluation model, not a requirement to implement microservices.

## 15. Current application functional alignment

> **Reconciliation note — 2026-10-10:** this section preserves the at-clone baseline for auditability. Items completed during remediation are struck through and followed by their current status; unstruck limitations remain genuine client-confirmation, optional refinement or production-scope items.

### 15.1 Capabilities currently covered well

- high-level journey from prospect sourcing to disbursement approval;
- ~~five stages and 23 role-based workflow steps;~~ **Expanded to five stages and 25 role-based steps.**
- Maker, Checker, Risk, EVP and Committee participation;
- submit, approve, return, reject, allocation, reassignment and escalation;
- IP Note generation;
- credit assessment/CAM pipeline;
- Risk Maker workspace;
- committee pack;
- sanction decision and minutes for deviations;
- IP-to-AP comparison;
- field confirmation/override and stale-review indicators;
- condition precedent/subsequent tracker;
- waiver/deferral with checker approval;
- deviation register;
- term sheet and sanction-letter versions;
- disbursement checklist and tranche record;
- SLA, queues, MIS and application audit events;
- document prefill with source page and confidence;
- deterministic fallback when AI is not configured.

### 15.2 P0 current-application gaps

#### GAP-P0-01 — Application model

Historical state at clone:

- ~~one borrower/entity reference and one facility object per LOS application;~~ **Fixed: persistent multi-party and multi-facility application model.**
- ~~credit case and document resolution are primarily borrower/entity based.~~ **Fixed: application-scoped governed records and documents.**

Required:

- ~~application-centric multi-party, multi-facility, multi-project and multi-security model;~~ **Implemented.**
- ~~application/version-scoped CAM runs and documents.~~ **Implemented.**

#### GAP-P0-02 — Approval workflow fragmentation

Historical state at clone:

- ~~the CAM authority-matrix workflow and the 23-step LOS workflow are separate processes;~~ **Fixed through the integrated 25-step LOS decision/authority route.**
- ~~the client-required authority model does not drive a single authoritative end-to-end route.~~ **Demo route implemented; the bank-approved authority matrix remains confirmation-required.**

Required:

- ~~one integrated approval state and decision history;~~ **Implemented.**
- ~~dynamic authority routing from exposure, risk, product and deviations.~~ **Implemented with a clearly labelled demo matrix.**

#### GAP-P0-03 — Approval snapshot

Historical state at clone:

- ~~assessment summaries and a facility snapshot are stored;~~ **Superseded by governed approval snapshots.**
- ~~the complete proposal, documents, screenings and calculations are not bound into one immutable approval package.~~ **Fixed for demo through a content-hashed 14-domain package; physical database immutability remains production scope.**

Required:

- ~~exact approval-version package and material-change revalidation.~~ **Implemented.**

#### GAP-P0-04 — Verification workflow

Historical state at clone:

- ~~numerous disconnected verification structures/endpoints exist;~~ **Consolidated.**
- several sources remain mock, synthetic, unavailable or manually confirmed;
- ~~there is no single complete client-aligned due-diligence status workspace.~~ **Fixed: all 15 checks share a governed workspace and lifecycle.**

Required:

- ~~consolidated check inventory, hard stops, match resolution, re-trigger and exception approval.~~ **Implemented, including 90-day controls and party evidence.**

#### GAP-P0-05 — Financial/CMA workflow

Historical state at clone:

- historical financial analysis, ratios, observations, stress and repayment assessment exist;
- ~~full CMA preparation, financial spreading approval and projection-governance flow are not complete.~~ **Fixed with governed CMA entry, reconciliation and maker-checker review.**

Required:

- ~~governed financial spreading/CMA process with source, version, reconciliation and review.~~ **Implemented; the authoritative bank template/formulas remain confirmation-required.**

#### GAP-P0-06 — Bank risk/pricing models

Historical state at clone:

- ~~risk, pricing, PD/LGD and RAROC were view-only/demo outputs;~~ **Expanded into governed rating, pricing and RAROC records.**
- key values are demo/synthetic rather than approved bank models.

Required:

- ~~governed internal rating, exposure, pricing, fees, repayment and RAROC capabilities.~~ **Implemented with labelled demo calculations.**

#### GAP-P0-07 — Security lifecycle

Historical state at clone:

- ~~collateral, values and cover are only displayed;~~ **Fixed through the governed security master and cover calculation.**
- ~~charge registration and CBS limit setup are only manually confirmed.~~ **Fixed for demo through charge/perfection lifecycle and the CBS Security Number gate.**

Required:

- ~~facility-security mapping, valuation history, charge priority, creation/perfection and CBS/security-ID linkage.~~ **Implemented.**

#### GAP-P0-08 — Post-sanction operational setup

Historical state at clone:

- ~~conditions, letter and checklist exist only as partial records;~~ **Expanded into governed fulfilment records.**
- ~~CIF, account, limit, security ID, beneficiary and fee processes are not full transactional workflows.~~ **Implemented for the self-contained demo.**

Required:

- ~~controlled operational setup with evidence and maker-checker status.~~ **Implemented.**

#### GAP-P0-09 — Repeated disbursements and closure

Historical state at clone:

- ~~tranche records can be stored without a repeat cycle;~~ **Fixed with audited subsequent-tranche re-entry.**
- ~~the workflow completes when the first tranche reaches final approval;~~ **Fixed: approved cases can re-enter at Disbursement Maker for a later tranche.**
- ~~approval is treated as “disbursed” without separate execution/reconciliation evidence.~~ **Fixed: state is `approved` and Exit means workflow approval, not settlement.**

Required:

- ~~complete the documented disbursement-approval record, Exit transition and demo repeat-drawdown cycle;~~ **Implemented.** Execution confirmation and reconciliation remain outside LOS/demo scope unless confirmed by the client.

#### GAP-P0-10 — Dependency enforcement

Historical state at clone:

- ~~only some stale field reviews and IP/AP comparison are implemented;~~ **Expanded with governed dependency invalidations.**
- ~~the dependency matrix is not enforced across identity, facility, pricing, project, security, beneficiary and sanction changes.~~ **Core demo dependencies are enforced; client-specific numeric thresholds remain confirmation-required.**

Required:

- ~~rule-driven invalidation, recalculation and reapproval.~~ **Implemented for documented demo triggers.**

### 15.3 P1 current-application gaps

#### GAP-P1-01 — Project-finance lifecycle

~~Project information exists only in assessment views, without a complete transactional sub-process.~~ **Fixed through project creation, funding/facility linkage, TEV, cost, DCCO, risks and change-driven reappraisal. A separate milestone schedule remains optional.**

#### GAP-P1-02 — ESMS workflow

~~ESMS/ESDD is presented only in the assessment and requires workflow expansion.~~ **Fixed through excluded-activity gates, categorization, evidence, remarks and approval-note controls.**

#### GAP-P1-03 — External parties

~~There is no complete application module for consultants, legal advisers, engineers and security trustees.~~ **Fixed through the linked External Work-Party register.**

#### GAP-P1-04 — Conditions and covenant lifecycle

~~CP/CS tracking lacks facility/party ownership, recurring tests, breach/cure handling and ongoing monitoring.~~ **Fixed 2026-10-10.**

#### GAP-P1-05 — Document lifecycle

~~Uploads, categories, prefill and generated-letter versions lack client-aligned checklists, scope, execution and evidence approval.~~ **Checklist, scope, execution and evidence review are implemented; time-based document expiry and authoritative templates remain open.**

### 15.4 P2/P3 current-application gaps

- ~~exact 19-stage equivalence requires screen-by-screen mapping;~~ **Mapped to the 25 technical queues; final client sign-off remains required.**
- parallel reviews and delegation require definition;
- ~~withdrawal, drop/modification and specific rework routing require implementation;~~ **Implemented 2026-10-10; exact bank vocabulary remains confirmation-required.**
- ~~business calendars and stage SLAs require implementation;~~ **Working-day demo calendar, reminders and escalation implemented; final bank calendar/SLA sign-off remains required.**
- payment execution ownership requires confirmation;
- ~~post-disbursement covenant monitoring and final Exit semantics require implementation;~~ **Implemented for demo; final client sign-off remains required.**

## 16. Target future-state flow

```text
Prospect
→ NTB/ETB and entity verification
→ Dedupe, ownership and related-party setup
→ Multi-facility/project/security proposal
→ IP Note and preliminary decision
→ Parallel due diligence
→ Financial/CMA appraisal
→ Rating, exposure and project/ESMS assessment
→ Security, pricing, repayment and RAROC
→ Risk Maker and independent review
→ VP/EVP/CRP and dynamic committee routing
→ Immutable sanction package
→ Customer consent and documentation
→ Conditions, covenants and security perfection
→ CIF/account/limit/security-ID/beneficiary/fee setup
→ Drawdown request
→ Eligibility, Maker, Checker, VP and Approver
→ Final disbursement approval
→ Exit bucket / documented workflow completion
→ Optional downstream execution, confirmation, reconciliation or repeat drawdown only when client scope is confirmed
```

Exception loops must be available for:

- failed verification;
- missing documents;
- policy deviations;
- modified facilities;
- revised financials;
- rating or pricing changes;
- project cost/timeline changes;
- security changes;
- incomplete conditions;
- beneficiary/payment changes;
- new material information;
- failed operational integration or, if included in confirmed scope, failed payment execution.

## 17. Functional acceptance checklist

### P0 acceptance

- [x] ~~One CLOS application can contain multiple facilities.~~
- [x] ~~One application can contain multiple related entities and parties.~~
- [x] ~~Projects and securities can be mapped to applicable facilities.~~
- [x] ~~Documents can be scoped to application, entity, facility and project.~~
- [x] ~~Due-diligence checks show evidence, status, time and resolution.~~
- [x] ~~Mandatory failed/missing checks enforce the configured gate.~~
- [x] ~~CMA, historical and projected financials follow a reviewed process.~~
- [x] ~~Rating, exposure, pricing, repayment and RAROC changes trigger governed staleness/material-change review.~~
- [x] ~~Required sanction authority is calculated from the labelled demo rules.~~
- [x] ~~Maker, checker, reviewer and committee decisions are segregated and traceable.~~
- [x] ~~A sanction references a version-bound, hashed approved information package.~~ Physical database immutability remains outside demo scope.
- [x] ~~Conditions are linked to facilities and responsible parties.~~
- [x] ~~CIF, accounts, limits, security IDs, beneficiaries and fees have controlled statuses.~~
- [x] ~~Conditions precedent to subsequent disbursement are captured.~~ ~~Repeat-tranche re-entry is explicitly excluded until its state model is confirmed.~~ **A governed demo re-entry cycle was implemented 2026-10-10; the client's exact later-drawdown state model remains confirmation-required.**
- [x] ~~Sanctioned, committed, approved/disbursed and balance concepts remain distinct according to the confirmed scope.~~
- [x] ~~Final approval and Exit are not presented as proof of payment execution or settlement.~~
- [x] ~~Exit/closure occurs only according to confirmed closure rules.~~

### P1 acceptance

- [x] ~~Multiple projects can be created and linked to funding/facilities.~~
- [x] ~~TEV, project cost, project status, DCCO and governed changes are tracked.~~ A separate milestone schedule remains open if required.
- [x] ~~ESMS categorization, evidence, recommendations and conditions are governed.~~
- [x] ~~Security valuation, priority, creation and perfection are tracked.~~
- [x] ~~External parties and their reports are linked to the proposal.~~
- [x] ~~Recurring covenants and post-disbursement obligations are monitored.~~ **Implemented 2026-10-10 with frequency, breach, cure and overdue-reminder controls.**
- [x] ~~Document checklist, version, review and execution status are supported.~~ Time-based document expiry remains open.

### P2/P3 acceptance or confirmation

- [x] ~~Official 19-stage business stages are reconciled to the 25 technical queues in Section 26.~~
- [ ] Rework, withdrawal, cancellation and termination rules are signed off.
- [ ] Parallel review and delegation rules are signed off.
- [ ] SLA calendars and escalation rules are signed off.
- [ ] Payment execution ownership and reconciliation rules are signed off.
- [ ] Retention, performance, availability and recovery requirements are signed off.

## 18. Client-confirmation register

The following must be resolved before detailed design is treated as final:

1. What are the official names and exact transitions of all 19 operational stages?
2. Which stages may run concurrently?
3. Where does each return/rework action go?
4. What are the withdrawal, cancellation, modification and termination rules?
5. How is approval delegation handled?
6. Which module is the source of truth for fields repeated across stages?
7. What constitutes a material change requiring reapproval?
8. What exactly is included in the immutable approval snapshot?
9. How are partial sanctions represented per facility?
10. How many simultaneous or sequential drawdowns are supported?
11. How are remaining commitments, cancellations and expiries handled?
12. Does LOS execute payment, or does CBS/a payment platform execute it?
13. What acknowledgements constitute successful disbursement?
14. How is settlement reconciled and how are reversals handled?
15. When exactly may an application move to the Exit bucket?
16. Which due-diligence checks are automated, manual or retriggerable?
17. What are the official authority and deviation matrices?
18. What are the product-specific document and condition checklists?
19. What are the official ESMS categories and approval requirements?
20. What are the applicable post-disbursement covenant-monitoring requirements?
21. What performance, volume, availability, recovery, retention and observability targets apply?

## 19. Evaluation dimensions for future comparison

Any proposed application or architecture must be compared against this baseline for:

| Dimension | Evaluation requirement |
|---|---|
| Functional completeness | Fully covered, partially covered or absent client capabilities |
| Workflow equivalence | Stages, authorities, decisions, rework and exception scenarios |
| Data-model compatibility | Borrower, entity, project, facility, security and disbursement relationships |
| Business-rule coverage | Validations, calculations, hard stops and exception authorization |
| Integration coverage | Required external interfaces and missing connections |
| Technical suitability | Ability of components and stores to support the functional process |
| Security/compliance | Role controls, evidence, approvals and audit requirements |
| Scalability/extensibility | Volume growth, new products and future workflow changes |
| Implementation gaps | Missing components, dependencies and changes required |
| Overall recommendation | Equivalent, simpler, complementary or suitable replacement |

Comparisons must distinguish confirmed gaps from assumptions and client-confirmation items. An unmentioned feature must not automatically be classified as absent without validation.

## 20. Recommended implementation order

### Release foundation — P0

1. Application-centric canonical model.
2. Parties, multiple facilities, projects and securities.
3. Application/version-scoped documents and CAM runs.
4. Unified workflow and approval authority calculation.
5. Due-diligence inventory and mandatory gates.
6. Immutable approval package and material-change controls.
7. Post-sanction operational objects.
8. Complete documented disbursement approval and Exit lifecycle; add repeated drawdown, execution and reconciliation only after scope confirmation.

### Business completion — P1

1. Full CMA and projection governance.
2. Bank rating, exposure, pricing, repayment and RAROC.
3. Project-finance and TEV lifecycle.
4. ESMS workflow.
5. Security perfection and monitoring.
6. External-party management.
7. Covenant and document lifecycle.

### Operational refinement — P2

1. Parallel reviews and advanced rework.
2. Delegation and workload routing.
3. Product-specific workflow variants.
4. Advanced MIS and exception monitoring.
5. Post-disbursement monitoring and closure.

### Confirmation/design — P3

1. Final non-functional targets.
2. Final physical architecture.
3. Final availability and recovery design.
4. Final retention and archival rules.

---

## 21. Detailed Client One versus current-application review

### 21.1 Review snapshot

This comparison was refreshed on 2026-10-09 against:

- client baseline: `D:\Downloads\Application_Client_One_Complete_Context (1).md`;
- current code revision: `ad5a204b7d2d9847d1d167d512432b7d6f58fb6a`;
- live application: port `8004`, `/los` returned HTTP 200 and `/api/health` returned `healthy`;
- live API surface: 35 `/api/los` paths;
- configured LOS workflow: five stage groups containing 24 technical steps, including the verified Disbursement VP Review gate;
- focused LOS verification: 83 tests passed and two failed. The failures were in the sourcing/prefill and copilot paths: the prefill endpoint returned 409 when the expected IHCL document corpus was absent, and the corresponding copilot action assertion did not match.

This is a functional comparison, not a claim that the client source represents a production-tested system. The client source itself states that it was synthesized from user text and 64 screenshots, that the original three PDFs were unavailable, and that some screenshot content was blurred or cropped.

### 21.2 Status definitions used in this comparison

| Status | Meaning |
|---|---|
| Supported | A usable workflow, data object and control are implemented in the current LOS path |
| Partially supported | Some data, display, engine output or workflow exists, but client scope, controls, cardinality or integration are incomplete |
| Missing | No corresponding application-level workflow/data object/API/UI was found |
| Demo/synthetic | Present only through demo mappings, seeded data, mock services or manual confirmation; not production-equivalent |
| Not verified | Source detail is unconfirmed, or current behavior cannot be established from code, UI, API and tests reviewed |

An item is not classified as supported merely because a label appears in a CAM, fixture, sample company, generated document or configuration file. Support requires an appropriate business workflow and persistent state.

### 21.3 Executive comparison

| Client capability | Current application | Status | Main gap |
|---|---|---|---|
| Corporate/institutional origination through Exit | 25-step Prospect → IP → AP → Post-Sanction → Disbursement → Exit flow | **Demo supported** | ~~Withdrawal/modification/drop and reason-specific alternate routes remain open~~ **Implemented 2026-10-10.** |
| One borrower with many related parties | Persistent application parties with roles, identity, ownership and audited edit | **Demo supported** | ~~Party-level evidence grids and extended relationship/address fields remain open~~ **Implemented 2026-10-10.** |
| Multiple facilities and projects | Persistent multi-facility and multi-project records with linkages and lifecycle controls | **Demo supported** | Client-specific reapproval thresholds remain open |
| Prospect Sourcing | Identity/dedupe, NTB/ETB, CBS demo result, facilities, parties, discussion and governed decision | **Demo supported** | ~~Entity-incorporated flag remains open~~ **Implemented 2026-10-10.** Rich-text editing remains an optional UI refinement. |
| IP Note | Preliminary note, queue/assignee, parties/facilities and labelled enrichment adapters | **Demo supported** | ~~LPFG Analyst/Senior Analyst fields and extended IP classification/address fields remain open~~ **Implemented 2026-10-10.** |
| Fifteen due-diligence modules | Governed checks with API/manual demo lifecycle, history, comments, exceptions and gates | **Demo supported** | ~~90-day ageing and party-level evidence remain open~~ **Implemented 2026-10-10.** |
| Financial analysis and CMA | Entity-wise period entry, value class, formulas, review, reconciliation and download | **Demo supported** | Exact authoritative template/formula set is unavailable |
| Rating and RAROC | External/internal/group ratings, adverse events, facility RAROC and stale-input rule | **Demo supported** | Uses an explicitly labelled demo model |
| Proposal/exposure and annexures | Structured proposal, banking, exposure, conduct and annexure governance records | **Demo supported** | Exact downloadable annexure layouts remain open |
| Project assessment | Persistent project, TEV, cost/finance, plan, risk register and change/reappraisal workflow | **Demo supported** | Numeric reapproval thresholds remain open |
| ESMS/ESDD | Governed questionnaire, remarks gate, classification, ESDD and approval note | **Demo supported** | Exact bank questionnaire/policy is unavailable |
| Terms, conditions and covenants | Full taxonomy, evidence/status, checker control and subsequent-tranche gate | **Demo supported** | ~~Recurring reminder/breach/cure automation remains open~~ **Implemented 2026-10-10.** |
| Security management | Security master, multi-facility linkage, valuation, charge/perfection and CBS reference gate | **Demo supported** | Haircut/lien-search policy remains open |
| Pricing, fees and repayment | Governed facility pricing, fees, tentative schedule and final terms | **Demo supported** | Uses labelled demo values |
| External Work-Party management | Persistent linked EWP register with contacts, phase, request, report and status | **Demo supported** | Portal/contracts/fee workflow is outside the current demo |
| Document management | Stage checklist, logical versions, review statuses, generated outputs and hard gates | **Demo supported** | Some exact downloadable report/annexure templates remain open |
| Approval and sanction | Distinct reviews/committees, demo authority, deviations, snapshots and material-change gate | **Demo supported** | Client-approved authority matrix is unavailable |
| Post-sanction | Consent, facility execution, conditions, documents and checker control | **Demo supported** | ~~Withdrawal/modification/drop vocabulary remains open~~ **Implemented 2026-10-10.** |
| Disbursement | Full operational record, memo/SOP gates and Checker/VP/Final reviews | **Demo supported** | ~~Repeat-tranche cycle after Exit remains open~~ **Implemented 2026-10-10.** Payment settlement remains outside LOS/demo scope. |
| External integrations | Registry of 22 labelled demo/not-connected adapters with evidence trail | **Demo supported** | Production connections are explicitly out of scope |
| Audit and provenance | Append-only events, record histories, document versions and approval snapshots | **Demo supported** | Physical tamper-evident archive is outside demo scope |

## 22. P0 — Critical missing and incomplete capabilities

> **Demo-scope decision — 2026-10-10:** the client will not provide external data, credentials or live APIs for this demonstration. A requirement that depends on CBS/LMS/regulatory/bureau/market sources is therefore complete for demo when the application provides a working, persistent simulated workflow, labels the source as `demo_data` or `not_connected`, never presents unavailable data as a clear result, and preserves auditable evidence. Production connectivity is out of scope for this demo and is not counted as a pending application defect.

### GAP-P0-01 — Application, borrower and related-party structure

**Status 2026-10-10:** related parties are application-owned records with add/edit (role, relationship, individual/non-individual, ownership percentage, PAN/CIN, sourced address, key-person role and party status), persisted in the application payload and visible in the UI and API. A PAN change recomputes the server-side identity, re-runs deduplication and invalidates the PAN-dependent KYC/GSTIN checks with the reason recorded. Ownership and group-role changes raise governed dependency invalidations. Every workspace mutation is attributed in the audit trail with from/to step. Party-level KYC, bureau, name-screening, rating, financial, document and expiring exception evidence is implemented and coverage is visible per party.

Client One requires one primary borrower and multiple associated entities, including promoters, sponsors, SPVs, parents, subsidiaries, group concerns, joint ventures, collaborators, beneficial owners and key persons.

Current application evidence: the API and service persist one primary borrower, multiple related parties and multiple facilities. Related parties are application-owned workflow records rather than CAM-only names.

Required change:

1. ~~Add `ApplicationParty` as a persistent application object.~~ **Fixed 2026-10-09:** related parties are persisted in the application payload with stable `RP-###` identifiers; the primary borrower remains the application's principal entity.
2. ~~Support party roles: primary borrower, promoter, sponsor, guarantor, SPV, parent, subsidiary, associate, group concern, joint venture, collaborator, beneficial owner and key person.~~ **Fixed 2026-10-09:** the creation UI and API support all listed associated-party roles; the primary borrower is selected separately.
3. ~~Capture individual/non-individual type, legal identity, ownership percentage, relationship, sourced addresses, key-person role and party status.~~ **Fixed 2026-10-10.**
4. ~~Support adding and editing parties during IP Note Processing with auditable changes.~~ **Fixed 2026-10-09.**
5. ~~Maintain party-level KYC, bureau, screening, rating, financial, document and exception records.~~ **Fixed 2026-10-10.**
6. ~~Re-evaluate applicable checks when PAN, ownership or group relationship changes.~~ **Fixed 2026-10-10:** identity/dedupe and PAN-dependent checks are invalidated; ownership/group-role changes raise governed stale-conclusion invalidations.
7. ~~Distinguish application parties from reference-only names extracted into a CAM.~~ **Fixed 2026-10-09:** entered parties are stored as application records rather than CAM-only display values.

Acceptance evidence:

- ~~one application can persist multiple parties and expose them through UI and API;~~ **Fixed 2026-10-09.**
- ~~every party evidence record identifies its subject party;~~ **Fixed 2026-10-10.**
- ~~ownership changes are persisted, audited and raise relationship-change invalidation;~~ **Fixed 2026-10-10.**

Completed-slice evidence: `src/api/routers/los.py`, `src/los/service.py`, `src/los/party_evidence.py`, `src/ui/templates/los/new.html`, `src/ui/templates/los/application.html`, `tests/test_los_workflow.py`, `tests/test_los_governance.py` and `tests/test_los_uat_p1.py`. Parties are application-owned records with extended details, party-level evidence, PAN-change re-evaluation, group/ownership dependency invalidations and audited changes.

### GAP-P0-02 — Prospect Sourcing parity

Current application supports selecting an existing platform borrower, viewing a stored customer-identity/deduplication snapshot, capturing a prospect discussion, and entering multiple proposed facilities plus priority. ~~It still does not provide the complete Client One sourcing form.~~ **The documented sourcing fields are demo-complete; exact undisclosed layouts remain confirmation-required.** Production-connected identity verification is outside demo scope.

Add the following documented sourcing behavior:

- ~~New Work Item creation in Prospect Sourcing;~~ **Verified 2026-10-10.**
- ~~entity incorporated flag;~~ **Implemented 2026-10-10.**
- ~~date of incorporation;~~ **Fixed 2026-10-09:** displayed from the borrower master and stored in the application identity snapshot.
- ~~PAN and name as per PAN;~~ **Fixed 2026-10-09:** resolved from borrower/reference data, displayed before creation and stored server-side.
- ~~NTB/ETB determination and existing-customer verification;~~ **Fixed 2026-10-09 for the demo data source:** the UI and API show NTB/ETB and the labelled demo core-banking search result. A production CBS adapter remains open under GAP-P0-17.
- ~~existing Customer ID selection;~~ **Fixed 2026-10-10 (UAT-P0-4):** the selected Customer ID is validated server-side against the available core-banking (demo data) results for the borrower; a CIF that is not on the book — or any existing-CIF selection for a new-to-bank borrower — is rejected at creation.
- ~~CBS customer-information fetch for the demo;~~ **Demo-complete 2026-10-10:** the persistent simulated result is explicitly labelled `Core banking (demo data)`; production connectivity is outside demo scope.
- ~~constitution of entity;~~ **Fixed 2026-10-09:** displayed and persisted in the customer-identity snapshot.
- ~~CIN format validation for private/public companies;~~ **Demo-complete 2026-10-10.**
- ~~PAN-linked GSTIN display and format verification;~~ **Demo-complete 2026-10-10.**
- ~~PAN-based LOS deduplication against customer and proposal records;~~ **Fixed 2026-10-09:** the server checks stored applications by entity, PAN and CIN, excludes the application being viewed, and returns match reasons and application details.
- ~~multiple proposed facilities using add/remove controls;~~ **Fixed 2026-10-09:** the New Application UI supports repeatable facility cards and removal before draft creation.
- ~~product type, facility nature, facility type, proposed amount/limit, tenor in months, ad hoc flag and applicable facility attributes;~~ **Verified 2026-10-10.**
- ~~project type, funding type, brief project details and prospect discussion capture;~~ **Fixed 2026-10-09:** the New Application form persists project type, funding type, a brief description, detailed discussion and initial sourcing remarks. Rich-text formatting is not implemented and remains a UI refinement.
- ~~decision and mandatory/conditional remarks;~~ **Fixed 2026-10-10 (UAT-P0-4):** the sourcing decision is mandatory, mandatory remarks are required with every decision, conditional remarks are required when the decision is Defer, and the UI enforces the same rules client-side.
- ~~documented `Submit → IP Note Processing` transition.~~ **Verified 2026-10-10.**

~~The current extra `LPF VP Review` immediately after Prospect Sourcing must be reconciled with the Client One business flow rather than silently retained or removed.~~ **Resolved 2026-10-09:** Prospect Submit goes directly to IP Note Processing; the LPF VP review follows the IP Note as the documented IP review gate.

**Status 2026-10-10 (GAP-P0-02):** the Customer Identity & Deduplication and Prospect Discussion slices are implemented and demo-complete: NTB/ETB, PAN/CIN/GSTIN with status, entity-incorporated flag, labelled core-banking search, stored identity snapshot, entity/PAN/CIN deduplication, repeatable facility cards, facility attributes, prospect discussion, mandatory sourcing decision/remarks and validated Customer ID selection. Rich-text editing remains an optional UI refinement, not a demo blocker.

### GAP-P0-03 — IP Note Processing parity

**Status 2026-10-09, updated 2026-10-10:** the IP Note is generated from the persisted prospect-sourcing record (project type/funding/discussion, parties, facilities) and is presented as a preliminary appraisal distinct from the final CAM; the queue shows CLOS ID, stage and the assigned maker. ~~LPFG Analyst/Senior Analyst assignment fields remain open~~ **Implemented 2026-10-10.** Named enrichment fetches (capital markets, MCA, TAN, IRAC) are represented by the labelled integration registry (GAP-P0-17), not as connected production sources.

The application generates an IP Note, carries the Prospect Sourcing record into it and provides the configured IP review/risk/committee workflow. Named external enrichments are represented by the labelled demo adapter registry.

Add:

- ~~Queue Management lookup using CLOS ID/registration number and stage;~~ **Verified 2026-10-10.**
- ~~LPFG Analyst and Senior Analyst assignment fields;~~ **Implemented 2026-10-10.**
- ~~auto-population of Prospect Sourcing data into the IP Note;~~ **Verified 2026-10-10.**
- ~~add/open/edit entity actions for individual and non-individual parties;~~ **Verified 2026-10-10.**
- entity-specific applicability flags and mandatory fields;
- ~~capital-market, MCA, litigation and TAN demo-source actions/evidence;~~ **Demo-complete 2026-10-10 via the labelled adapter registry.**
- industry, group, activity classification and harmonized sector;
- IRAC classification auto-population;
- ~~borrower/promoter/sponsor group association;~~ **Verified through application parties and rating subjects.**
- address and address-source capture with permitted modification;
- key persons and roles;
- ~~re-use, editing and expansion of proposed facilities;~~ **Verified 2026-10-10.**
- ~~existing-loan retrieval and exposure evidence from the labelled demo LMS source;~~ **Demo-complete 2026-10-10.** Controlled correction remains available through governed facility/disbursement records.
- ~~existing/proposed exposure consolidation;~~ **Verified in the proposal/exposure workspace.**
- shareholding through MCA, beneficial owners and connected entities;
- ~~auto-populated prospect discussion;~~ **Verified 2026-10-10.**
- ~~preservation of IP Note as preliminary appraisal rather than a duplicate of the final CAM.~~ **Verified 2026-10-10.**

### GAP-P0-04 — Multi-facility product, exposure and sanction model

The pre-2026-10-09 application stored one `facility` dictionary and one application-level amount. It now stores a `facilities` collection with the distinct amount lifecycle (see the status below); a single `facility` key is retained only as the primary/legacy convenience view.

Add:

- ~~multiple facilities per application;~~ **Fixed 2026-10-09:** persisted through the API and SQLite application payload with stable `FAC-###` identifiers.
- ~~fund-based/non-fund-based nature;~~ **Fixed 2026-10-09.**
- ~~product/facility type and subtype;~~ **Verified 2026-10-10.**
- ~~ad hoc indicator;~~ **Fixed 2026-10-09.**
- ~~proposed, sanctioned, committed, executed, disbursed, outstanding and balance amounts as distinct values;~~ **Fixed 2026-10-09:** all seven values are separate facility fields, updated only by the governed events (sanction allocation, consent execution, tranche release) — never by a single editable amount.
- ~~tenor, purpose, pricing, repayment, conditions, documents, projects and securities per facility;~~ **Fixed 2026-10-09:** per-facility pricing/repayment/operational fields are persisted and edited through the Facilities workspace with attribution.
- ~~total, fund-based and non-fund-based Limit IDs;~~ **Fixed 2026-10-09:** `total_limit_id` and `fund_limit_id` are captured per facility and carried into the disbursement record.
- ~~next review/renewal date;~~ **Fixed 2026-10-09.**
- ~~facility-level change history and approval attribution;~~ **Fixed 2026-10-09:** every edit appends an attributed change entry (who, when, which fields); after sanction, a facility edit is refused — it must go through the modification flow and raises a material-change flag.
- ~~existing LMS loan records and consolidated exposure;~~ **Demo-complete 2026-10-10 through labelled LMS/exposure records.**

Do not represent multiple facilities as text inside a single CAM section.

**Status 2026-10-10 (GAP-P0-04): Demo-complete.** The facility lifecycle, per-facility attributes, limit IDs, loan accounts/limit suffix, next-review date, labelled LMS/exposure record and attributed change history are implemented. Production LMS connectivity is outside demo scope.

### GAP-P0-05 — Governed due-diligence workspace and common behavior

The client requires checks across IP Note and Application Processing, with initiation, status, last-trigger time, evidence/report, user comments, view/retrigger actions and correct handling of manual versus API checks.

The pre-2026-10-09 application had separate external-data endpoints and assessment outputs but no consolidated application-level check inventory. It now has the governed fifteen-check workspace (see the status below).

Add common `VerificationCheck` behavior:

- check type and subject party;
- applicability and reason;
- ~~execution mode: API or manual;~~ **Verified 2026-10-10.** Hybrid mode is not required by the supplied demo cases.
- ~~initiated/triggered state distinct from business result;~~ **Verified 2026-10-10.**
- ~~request/result time and source;~~ **Verified 2026-10-10.**
- ~~pending, failed, unavailable, clear, matched and time-expired exception/re-screen states as applicable;~~ **Verified 2026-10-10.**
- ~~last trigger date/time;~~ **Verified 2026-10-10.**
- ~~retry/retrigger and error details;~~ **Verified 2026-10-10.**
- ~~generated due-diligence report, per-check uploaded evidence and document-registry evidence linkage;~~ **Verified for demo 2026-10-10.**
- ~~user comments;~~ **Verified 2026-10-10, including database persistence and audit event.**
- ~~Compliance VP review/exception where applicable;~~ **Verified 2026-10-10.**
- ~~expiry/ageing and 90-day re-screen rules;~~ **Verified 2026-10-10.**
- ~~exception authority, re-screen invalidation, exception history and time-based exception expiry;~~ **Verified 2026-10-10.**
- ~~audit history that preserves all prior runs.~~ **Verified 2026-10-10.**

**Status 2026-10-10 (GAP-P0-05 and GAP-P0-06 together): Demo-complete.** The governed due-diligence workspace implements all 15 named checks with API/manual demo execution, run history, persistent comments, audit events, Compliance-VP exceptions and submission gates. Re-running a check invalidates its previous exception. A mandatory `unavailable` result blocks until Compliance VP approval under the active `vp_approval` demo policy and is never presented as clear. UAT 2026-10-10 completed the two remaining items: the **90-day re-screening control** (an overdue 90-day name-screening/MLRA re-screen blocks progression until re-run) and **time-based exception expiry** (a Compliance VP exception lapses 90 days after it is granted, re-blocking the check, with dashboard reminders and escalations), and **party-level evidence** linking each related party separately to KYC, bureau checks, name screening, ratings, financial records, documents and exceptions. A true hard-block policy for `unavailable` remains a one-line configuration switch (`UNAVAILABLE_MANDATORY_POLICY`) pending the client's confirmation.

### GAP-P0-06 — Fifteen due-diligence modules

| Client check | Current application evidence | Status | Missing work |
|---|---|---|---|
| MCA | Governed API-mode check, demo registry result, history/comments and DD report | Demo supported | ~~Party-level evidence remains open~~ **Implemented 2026-10-10;** production source is outside demo scope |
| CIBIL Commercial | Governed API-mode check with demo bureau evidence, history/comments/retrigger | Demo supported | Formal CMR fields can be added if client supplies the exact layout |
| CRIF | Explicit governed check; unavailable demo provider state is controlled | Demo supported | Live score/report is outside demo scope |
| CRILC | Governed mandatory manual record with status, date/history, comments and exception control | Demo supported | ~~Per-check attachment remains open~~ **Implemented 2026-10-10** |
| Legal Litigation | Explicit API-mode party/application check with status, detail, time and retrigger | Demo supported | Detailed case grid can be added if required |
| EWS | Explicit API-mode account-conduct check with status/detail/history/comments | Demo supported | ~~Detailed trigger grid remains open~~ **Implemented 2026-10-10** |
| Central Fraud Registry | Governed manual record with status/history/comments | Demo supported | ~~Per-check document attachment remains open~~ **Implemented 2026-10-10** |
| CEIB | Governed manual record plus generated/registry output representation | Demo supported | Exact Proforma A template is unavailable |
| GSTIN | Explicit API-mode verification with stored GSTIN/status/history | Demo supported | ~~Party-level evidence remains open~~ **Implemented 2026-10-10** |
| LEI | Explicit API-mode check with clear/unavailable lifecycle and history | Demo supported | ~~Detailed expiry/report grid remains open~~ **Implemented 2026-10-10** |
| Enhanced Due Diligence (EDD) | Governed manual record with narrative evidence/comments | Demo supported | Exact client indicator questionnaire remains open |
| UDIN | Governed manual record and generated/registry output representation | Demo supported | Exact OTP/provider response form is unavailable |
| KYC | Governed mandatory manual check plus document registry/evidence controls | Demo supported | ~~Party-level document evidence remains open~~ **Implemented 2026-10-10** |
| Name Screening | Demo PEP/sanctions screening, retrigger history, blocking and Compliance VP exception | Demo supported | ~~90-day timer remains open~~ **Implemented 2026-10-10** |
| MLRA | Governed mandatory manual check and labelled demo risk evidence | Demo supported | Bank-approved scoring model is unavailable and not invented |

Mandatory controls to add:

- ~~exact/probable name-screening match blocks progression at governed submission gates;~~ **Verified 2026-10-10.**
- ~~only a recorded Compliance VP exception can release that block;~~ **Verified 2026-10-10.**
- ~~mandatory rescreen after the documented 90-day threshold;~~ **Implemented 2026-10-10 with dashboard reminder/escalation.**
- ~~external/API failure remains an operational error, not a negative or clear business result;~~ **Verified 2026-10-10.**
- ~~check changes after approval trigger material-change review through the approval snapshot.~~ **Verified 2026-10-10.**

### GAP-P0-07 — Entity-wise financial analysis and CMA

Current strengths include historical multi-period financials, ratio calculations, growth, projections, stress testing, repayment analysis and document extraction. Client parity remains incomplete.

Add:

- ~~financial analysis selectable for borrower, promoter, sponsor, SPV and parent;~~ **Verified 2026-10-10.**
- ~~CMA entry/review in ₹ crores;~~ **Verified 2026-10-10.**
- ~~historical actual and projected financial years;~~ **Verified through audited/provisional/projected period records.**
- Revenue, Income, Expenses and the complete authoritative CMA row set once original templates are provided;
- ~~subject/value-class applicability controls;~~ **Verified 2026-10-10.**
- ~~save, review and CMA download;~~ **Verified 2026-10-10.**
- rich-text analyst comments;
- ~~calculated highlights including depreciation, finance cost, PBT, PAT, margins and cash accruals;~~ **Verified 2026-10-10.**
- ~~source, period, version and entity on every value;~~ **Verified 2026-10-10.**
- ~~maker-checker review for manual entry/override;~~ **Verified 2026-10-10.**
- ~~reconciliation and comparison after revised financials;~~ **Verified 2026-10-10.**
- ~~explicit separation of audited, provisional and projected values.~~ **Verified 2026-10-10.**

**Status 2026-10-09 (GAP-P0-07):** the CMA workspace (`src/los/cma.py`) is implemented: subject-wise (borrower/promoter/sponsor/SPV/parent) entry in ₹ crores per period, audited/provisional/projected value class, the documented row set (revenue, income, expenses, depreciation, finance cost, PBT, PAT, cash accruals) with transparently computed margins, maker-checker review, reconciliation against the assessment's historical financials and a CMA download output. AP submission is gated on a recorded CMA. The complete authoritative template (extra rows, years, rounding, tolerances, upload schema) remains confirmation-required and is labelled as such in the workspace.

### GAP-P0-08 — Production rating, group rating and RAROC controls

Current `risk_maker.py` explicitly labels internal MLRA, PD, LGD, expected loss, pricing and RAROC values as synthetic demo mappings. They are not bank-approved models.

Add:

- ~~external rating for borrower, sponsor and promoter;~~ **Verified 2026-10-10.**
- ~~Save Risk prior-year retrieval for eligible parties;~~ **Demo-complete with a labelled prior-year retrieval.**
- ~~instrument-wise rating agency, rating type, short/long-term class, grade, date, instrument and rationale;~~ **Verified 2026-10-10.**
- ~~internal rating per borrower/promoter/sponsor/SPV;~~ **Verified 2026-10-10.**
- ~~current grade, score and date;~~ **Verified 2026-10-10.**
- ~~group-rating calculation;~~ **Demo-complete with a labelled aggregation rule.**
- ~~adverse-event/trigger review, review date, downgrade notches, revised rating and comments;~~ **Verified 2026-10-10.**
- ~~facility-wise RAROC using recorded demo-model inputs;~~ **Verified 2026-10-10.**
- ~~explicit facility title/nature/amount, tenor, payment frequency and result;~~ **Verified 2026-10-10.**
- ~~governed prerequisite linkage to facility, internal rating, external rating and pricing;~~ **Verified 2026-10-10.**
- ~~alert and mandatory recomputation when a relevant input changes after calculation;~~ **Verified 2026-10-10.**
- ~~documented preliminary-stage exception: RAROC is not mandatory at IP sanction;~~ **Verified 2026-10-10.**
- ~~CRP upload/review of LPF Note, Rating Report, CRP Note, risk observations and supporting files.~~ **Verified 2026-10-10.**

**Status 2026-10-10 (GAP-P0-08): Demo-complete.** All documented rating/RAROC workflow fields and stale-input controls are implemented. The model is explicitly labelled as a demo calculation; a bank-approved PD/LGD/capital methodology is unavailable and is not required for this self-contained demo.

### GAP-P0-09 — Proposal, exposure, banking and conduct workspace

Add structured, editable and reviewable sections for:

All items in this list are implemented as governed demo records; exact annexure layouts remain unavailable:

- ~~proposal summary, purpose, tenure, pricing and security;~~
- ~~borrower and business background;~~
- ~~industry outlook and marketing arrangements;~~
- ~~corporate governance;~~
- ~~strengths, weaknesses, key risks and other material information;~~
- ~~bond and loan exposure;~~ **Demo-source fetch.**
- ~~sector-wise and state-wise exposure;~~
- ~~sanctioned, disbursed, outstanding and LMS committed exposure;~~
- LEF and EPM norms once their formal meanings/rules are confirmed;
- ~~Fetch Bond Exposure and Fetch Loan Exposure actions;~~
- ~~exposure-limit breach alert and governed exception path;~~
- ~~multiple-banking/consortium arrangement, lead bank, number of banks, institution share and borrower/sponsor/promoter banking details;~~
- ~~hard rule that a syndication case uses Consortium arrangement;~~
- ~~preceding 12-month account conduct under Annexure IX: limits, outstanding, irregularity, peak irregularity, instances, irregular days, financial difficulty and remarks;~~
- ~~Annexure XI regulatory/internal compliance and non-compliance justification;~~
- ~~inter-firm comparison: debt, revenue, EBITDA, PAT, Debt/EBITDA, PAT%, P/E, market capitalization and share price;~~
- ~~write-off/compromise losses or haircuts;~~
- ~~connected-lending relationships;~~
- ~~Annexure VI for pending audit/monitoring non-compliance;~~
- ~~Annexure XIII for due-diligence information;~~
- ~~Annexure XIV for loans, advances, investments and possible fund diversion;~~
- ~~applicable ESG, listed-company, insurance and other conditions.~~

**Status 2026-10-09 (GAP-P0-09):** `src/los/proposal.py` implements the workspace: proposal summary/background, banking arrangement (with the hard rule that a syndication case must use Consortium), bond/loan exposure with labelled demo fetch (FT not connected yields `unavailable`, never a fake result), sanctioned/disbursed/outstanding/LMS-committed values, LEF/EPM norms (formal meanings confirmation-required, labelled), breach alert with the governed exception path, and the preceding-12-month conduct rows (limit, outstanding, irregularity, peak, instances, days, financial difficulty, remarks). The annexure sections (XI, VI, XIII, XIV, inter-firm, write-offs, connected lending) are represented as structured, labelled governance fields. The full annexure templates remain confirmation-required.

### GAP-P0-10 — Client-aligned approval workflow

Current application has 25 configured technical steps (PS 1 → IP 8 → AP 10 → POS 2 → DIS 4) under PS, IP, AP, POS and DIS. It provides roles, assignment, allocation, reassign, escalation, SLA flags, audit events and maker/checker/committee actions, including a dedicated Disbursement VP Review gate. ~~It remains only partially aligned with the documented 19-stage client process.~~ **The 19 business stages are mapped to the 25 technical queues; exact bank role names and exceptional routes remain confirmation-required.**

Required workflow corrections:

1. ~~Map every configured queue to the documented 19 business stages.~~ **Verified in Section 26.**
2. ~~Reconcile the current extra Prospect Sourcing review with `Prospect Submit → IP Note Processing`.~~ **Resolved.**
3. ~~Add or explicitly map IP VP Review and CRP Processing.~~ **Verified.**
4. ~~Keep IP Committee Sanction distinct from final Committee Sanction.~~ **Verified.**
5. ~~Preserve distinct Risk Maker and independent Risk Review activities.~~ **Verified.**
6. ~~Add Post-Rating VP Review if it is not represented by an existing queue.~~ **Verified: `ap_rating_vp`.**
7. ~~Add Recommendations Committee as a distinct governance decision.~~ **Verified: `ap_recommend`.**
8. ~~Add CRP and ESMS Processing before Committee Sanction.~~ **Verified.**
9. ~~Add Disbursement VP Review between Checker and Final Approval.~~ **Fixed 2026-10-09:** `dis_vp_review` is a distinct read-only gate between `dis_checker` and `dis_approver`, assigned to the `dis_vp` role, with Submit and return-to-Maker rework behavior and audit events.
10. ~~Implement the documented stage-specific actions and remarks, rather than mapping everything to generic approve/return/reject.~~ **Verified.**
11. ~~Preserve read-only behavior at Post-Sanction Checker, Disbursement Checker, Disbursement VP and Final Approver.~~ **Verified.**
12. ~~Record committee matters, confirmation/ratification, significant changes, latest-material-information date and policy deviations at applicable reviews.~~ **Verified for demo; latest-material-information date added 2026-10-10.**

**Status 2026-10-09, updated 2026-10-10 (GAP-P0-10):** the workflow is the 25-step `config/los_workflow.yaml` (PS 1 → IP 8 → AP 10 → POS 2 → DIS 4) with 18 roles: the IP Committee Sanction is distinct from the final Committee Sanction; Risk Maker and Risk Review are distinct; the Recommendations Committee is a distinct governance decision; CRP and ESMS processing sit before Committee Sanction; Post-Rating VP Review exists; and the Disbursement VP Review is the separate read-only approval step with Submit/Rework (including significant-changes capture in the audit trail). Stage-specific actions (submit/approve/sanction/allocate, checker read-only approval, committee sanction) are implemented rather than generic approve/return. ~~Client-specific rework destinations, withdrawal/modification/drop and alternate routes remain open~~ **Implemented 2026-10-10 as audited, reason-mandatory actions; exact bank vocabulary remains confirmation-required.**

### GAP-P0-11 — Approval authority, decision evidence and change control

The pre-2026-10-09 application had a separate amount/risk approval matrix for the CAM workflow and a fixed LOS route. The two now share one decision/authority service for the LOS route (labelled demo matrix — the client's approved matrix is confirmation-required); see the status below.

Add:

- ~~one decision/authority service used by LOS routing;~~ **Verified.**
- ~~documented preliminary and final demo authorities;~~ **Verified and labelled as demo.**
- ~~policy-deviation identification, type, description, source, justification and decision;~~ **Verified.**
- previous waiver and authority-observation history;
- ~~recommendation and sanction as distinct decisions;~~ **Verified.**
- ~~committee minutes and recommendation details;~~ **Verified for demo.**
- ~~traceable proposed, recommended, sanctioned and subsequently modified values;~~ **Verified.**
- ~~material-change review after every relevant governed update;~~ **Verified.**
- ~~binding of the decision to the exact application, party, facility, project, financial, rating, security, check and document versions reviewed.~~ **Verified through approval snapshots.**

**Status 2026-10-09 (GAP-P0-11):** `src/los/authority.py` provides the preliminary/final authority determination (amount band, grade, deviations) — explicitly a labelled demo matrix; the client's approved matrix is confirmation-required (§28) and is never presented as the bank's. Deviations are captured with type/description/justification/decision. Recommendation and sanction are distinct decisions; committee minutes are mandatory when the sanction differs from the recommendation. Every decision binds an approval snapshot (`src/los/snapshot.py`): 14 governed domains (parties, facilities, securities, projects, CMA, ratings, proposal, pricing, ESMS, EWP, conditions, checks, documents, identity) with per-domain and content hashes. A governed change after the snapshot raises the material-change review, which must be recorded (accept/return with remarks) before the next post-sanction approval; the conditions domain is excluded from the gate because condition work is tracked by the condition tracker with checker approval.

### GAP-P0-12 — Document management and mandatory output gates

Current LOS document upload is PDF-only. It now maintains a logical document with automatic versioning (a second upload of the same name becomes `name-2.pdf` — nothing is overwritten) instead of rejecting the duplicate; generated term sheets and sanction letters have immutable issue versions.

Add:

- ~~entity, application, facility and project document scope;~~ **Verified.** Relationship scope is represented by the application/party context.
- ~~document category, checklist requirement and status;~~ **Verified.**
- ~~mandatory and pending tracking per stage/product;~~ **Verified.**
- ~~multiple uploads under one logical document name;~~ **Verified.**
- ~~explicit document version history;~~ **Verified.**
- ~~report/check evidence linkage;~~ **Verified for the demo registry.**
- ~~reviewed/accepted/rejected/rework status and reviewer;~~ **Verified.**
- ~~generated CAM, Executive Summary, Customer Due Diligence/Due Diligence Report, ESMS Approval Note and Disbursement Memo;~~ **Verified.**
- IP Note, CMA download, MCA/bureau/check reports, CRILC/CFR evidence, Proforma A, UDIN response, KYC evidence, LPF/Rating/CRP notes, TEV report and committee minutes;
- ~~Sanction Letter upload/review gate before post-sanction progression;~~ **Verified.**
- ~~Disbursement Memo generation/review gate before disbursement progression;~~ **Verified.**
- ~~Drawdown Request, Drawdown Schedule Report and applicable annexure references;~~ **Verified for demo.**
- ~~security, financial, covenant and compliance evidence.~~ **Verified through the document registry and governed workspaces.**

**Status 2026-10-09 (GAP-P0-12):** `src/los/docreg.py` implements the document registry: stage-wise mandatory checklist (PS/IP/AP/POS/DIS, conditional rows — valuation only when securities exist, TEV only when projects exist), multiple uploads under one logical document with automatic versioning (`name-2.pdf`, never overwriting), evidence linkage to checks, reviewed/unreviewed/missing status with reviewer and remarks, auto-registration of generated artefacts (letters, consent, memo, CMA), and a stage gate that blocks progression while mandatory documents are open. The Sanction Letter and Disbursement Memo gates block post-sanction and disbursement progression respectively. Retention, e-signature, antivirus, formats/sizes and authoritative templates remain confirmation-required.

### GAP-P0-13 — Post-sanction fulfilment

Current application now carries the full condition taxonomy with satisfy/defer/waive/reopen, checker approval for deferral/waiver, generated sanction letters and Maker/Checker steps (see the status below). The pre-2026-10-09 build supported only CP/CS.

Add:

- ~~Post-Sanction Maker queue lookup by CLOS ID/registration number;~~ **Verified.**
- ~~update/review of external rating, weaknesses and observations through the governed workspaces;~~ **Verified for demo.**
- ~~pre-commitment, pre-disbursement, post-disbursement, financial covenant, non-financial covenant and facility-specific sections;~~ **Verified.**
- ~~compliance status, supporting documents and remarks;~~ **Verified.**
- ~~mandatory Sanction Letter upload and reviewed status enforced as a hard gate;~~ **Verified.**
- ~~customer sanction consent/acceptance;~~ **Verified.**
- ~~per-facility execution status;~~ **Verified.**
- ~~Facility Agreement Date;~~ **Verified.**
- ~~sanctioned amount, committed amount and calculated balance;~~ **Verified.**
- ~~partial execution handling;~~ **Verified.**
- ~~maker decisions: Application Withdrawn, Modification Proposed and Submit;~~ **Implemented 2026-10-10.**
- ~~committee information, remarks and significant changes;~~ **Verified.**
- ~~read-only checker decisions: Recommend for Disbursement, Recommend for Modification, Rework and Drop;~~ **Implemented 2026-10-10.**
**Status 2026-10-09, updated 2026-10-10 (GAP-P0-13):** post-sanction fulfilment is implemented: the Post-Sanction Maker must record the customer's sanction consent/acceptance, per-facility execution status and Facility Agreement Date (which drives the executed amount in the facility lifecycle) and generate the Sanction Letter before submission; the checker's read-only decisions and mandatory remarks, committee information and significant-changes capture are enforced. ~~Withdrawn/Modification Proposed and Drop/Recommend-for-Modification actions remain open~~ **Implemented 2026-10-10 with mandatory reasons and audit evidence.**

### GAP-P0-14 — Conditions and covenant lifecycle

Expand the current CP/CS tracker to distinguish:

- ~~pre-commitment conditions;~~
- ~~pre-disbursement conditions;~~
- ~~post-disbursement conditions;~~
- ~~conditions precedent to subsequent disbursement;~~
- ~~financial covenants under Annexure III;~~
- ~~non-financial covenants;~~
- ~~general conditions;~~
- ~~facility-specific conditions.~~ **All taxonomy items verified 2026-10-10.**

~~Required fields include existing/new flag, facility, applicable party, name/category/type, description, stipulated value, status, reason for non-compliance, evidence, remarks, monitoring/testing frequency and due date. Non-compliance must require reason and remarks. Subsequent-disbursement conditions must be available to Disbursement Maker.~~ **Verified 2026-10-10.**

Ongoing breach, cure, reminder, waiver and monitoring behavior beyond the documented fields requires client confirmation; it remains a recommended extension rather than a source-proven rule.

**Status 2026-10-09 (GAP-P0-14):** `src/los/post_sanction.py` now carries the full condition taxonomy (pre-commitment, pre-disbursement, post-disbursement, conditions precedent to subsequent disbursement, financial covenants, non-financial covenants, general conditions, facility-specific conditions) with facility linkage, applicable party, category/type, stipulated value, monitoring frequency, status (open/satisfied/deferred/waived/non_compliant), reason-for-non-compliance, evidence and remarks. Non-compliance requires a reason; CPS conditions gate subsequent tranche releases at the Disbursement Maker; deferral/waiver wait for Post-Sanction Checker approval.

### GAP-P0-15 — Disbursement Maker operational record

The pre-2026-10-09 implementation recorded only tranche amount, value date and purpose plus a small automatic/manual checklist. It now carries the full operational record (see the status below). The client requires the following before Maker submission:

- ~~completion of allowable missing post-sanction information;~~
- ~~external-rating retrigger record;~~
- ~~mandatory generated and reviewed Disbursement Memo;~~
- ~~CIF existence check;~~
- ~~NTB CIF creation and ETB CIF update;~~ **Recorded as labelled demo operations.**
- ~~Total Exposure, Fund-Based and Non-Fund-Based Limit IDs;~~
- ~~limit suffix and next review/renewal date;~~
- ~~applicable loan-account details;~~
- ~~all primary/collateral securities and Create CBS Security No. action;~~
- ~~CBS Security Number for every applicable security before disbursement;~~
- ~~multiple beneficiaries;~~
- ~~facility, beneficiary type/name, account number, bank, branch, IFSC, payment mode and amount;~~
- ~~fee collection: upfront/annual-review fee, gross, due, GST, total, receipt date, received, balance, pending due date and remarks;~~
- ~~non-fund charges, GST, deferred balance, collection frequency/due date and pending-recovery remarks;~~
- ~~final moratorium, tenure, instalment frequency, interest-payment details and repayment conditions;~~
- ~~benchmark, rate, spread, reset frequency/date, additional interest for non-perfection, effective rate, penal rate, start date and calculation parameters;~~
- ~~Annexure IV security fields: LOS Security ID, type, facility, description, creation/perfection status and dates, valuation date/value, CERSAI and ROC;~~
- ~~arrear existence, facility, type, amount, currency, due-since date and remarks;~~
- ~~Drawdown Request, Drawdown Schedule Report and applicable annexures;~~
- ~~Interim SOP checklist covering KYC, treasury coordination, legal verification and all other mandatory activities;~~
- ~~hard gate requiring every applicable mandatory SOP item to be In Compliance;~~
- ~~Maker decision, remarks, committee matters and confirmation information.~~ **All listed Disbursement Maker records are verified for the demo.**

**Status 2026-10-09 (GAP-P0-15):** `src/los/disops.py` implements the operational record: CIF existence, limits (total/fund), loan accounts, security references with the Create CBS Security No. hard gate, multiple beneficiaries (facility, type/name, account, bank, branch, IFSC, mode, amount), fee collection rows, non-fund charges, final repayment terms (moratorium, frequency, first DDI), interest terms (frequency, day in arrears, penal/additional interest), arrears (existence, facility, type, amount, currency, due-since, remarks), drawdown from approved tranches, and the Interim SOP checklist (KYC, treasury coordination, legal verification, beneficiaries, fees, security, insurance, limits) with the hard In-Compliance gate. The Disbursement Memo is generated from a content hash of the record, must be reviewed, and any post-generation change invalidates it until regenerated. The seeded PNCR001 demonstrates the record mid-completion (two SOP items open, memo unreviewed).

### GAP-P0-16 — Disbursement reviews and Exit semantics

Add distinct read-only stages for:

- ~~Disbursement Checker: complete-case accuracy, completeness, compliance and Disbursement Memo review; Submit/Rework and remarks;~~ **Verified.**
- ~~Distinct read-only Disbursement VP Review between Checker and Final Approver, with Submit and return-to-Maker rework, mandatory remarks and explicit significant-change capture;~~ **Verified 2026-10-10:** the UI labels the return action `Rework` at this step.
- ~~Final Disbursement Approval: review customer, documents, CIF, limits, accounts, security IDs/linkages, facility execution, beneficiaries, memo, Annexure I repayment, project, interest, Annexure IV security, arrears and annexures.~~ **Verified through the governed final checklist.**

The pre-2026-10-09 behavior set a tranche to `disbursed` and the application to `APPROVED` when the configured final checker approved. This has been redesigned (see the status below): tranches move to `approved` and the application exits to `Exit (approved)`, which does not imply confirmed fund settlement. Client One proves final approval and movement to the Exit bucket, not payment execution or beneficiary settlement.

**Status 2026-10-09, updated 2026-10-10 (GAP-P0-16 continued):** the Disbursement Checker and Final Disbursement Approval now each carry a read-only review checklist (11 and 7 items) that must be fully confirmed before `approve`; approval is blocked until the review is complete. Tranches move to `approved` (not `disbursed`) and the application exits to `Exit (approved)` — the state no longer implies fund settlement. ~~Repeated-tranche orchestration remains open~~ **Implemented 2026-10-10 as a governed, reason-mandatory re-entry at Disbursement Maker.** Payment execution, retry/reversal and reconciliation remain confirmation-required and outside demo scope.

### GAP-P0-17 — Real integration layer and source truth

The current app uses Postman/local mocks for many external APIs; Probe42 is enabled but reported unconfigured in the live health response; core banking and registry actions are often manual/simulated.

Demo parity requires governed, honestly labelled adapters for the applicable sources below. Production connectivity is outside the agreed demo scope:

| Source | Client use | Current state |
|---|---|---|
| CBS | Customer fetch, CIF, address/customer/account data, limits, accounts and security references | **Demo supported** — labelled customer and operational records |
| LMS | Existing loans, committed exposure and facility details | **Demo supported** — labelled in-app LMS/exposure evidence |
| MCA | Company/LLP, directors, charges and shareholding | **Demo supported** — governed adapter/check evidence |
| PAN/GSTIN/TAN | Identity and tax verification/dedupe | **Demo supported** — stored identity, validation and adapter evidence |
| CIBIL/CRIF | Bureau scores and reports | **Demo supported** — explicit checks; unavailable provider results remain controlled |
| CRILC | Manual large-credit check and evidence | **Demo supported** — governed manual check |
| Litigation/EWS/CFR/CEIB | Legal, warning, fraud and intelligence checks | **Demo supported** — governed API/manual checks |
| LEI/UDIN | Identifier validity and document verification | **Demo supported** — governed checks and output registry |
| Name screening/AML/MLRA | Screening, exception and AML rating | **Demo supported** — screening, blocking and VP exception workflow |
| Save Risk | Prior external ratings | **Demo supported** — labelled prior-year retrieval |
| FT | Bond exposure | **Demo supported** — honest unavailable state; no fabricated result |
| Capital-markets source | IP entity enrichment | **Demo supported** — adapter registry/evidence state |

**Status 2026-10-10 (GAP-P0-17): Demo-complete.** The registry provides 22 governed adapters with honest `demo_data`/`not_connected` states and invocation evidence. No live external APIs or client data will be supplied; credentials, production contracts and provider SLAs are therefore outside demo scope.

## 23. P1 — Major parity gaps

### GAP-P1-01 — Project Assessment module

The application now provides a persistent, multi-project assessment module linked to facilities; the older presentation-only project tab is no longer the governing record.

Add:

- ~~multiple projects per application and facility linkage;~~
- ~~Project ID, name, type, funding type, purpose, refinancing applicability and NIP/NMP classification;~~
- ~~description, location/address, state and current performance;~~
- ~~TEV details, consultant/agency and report;~~
- ~~total project cost, financing arrangement, means of finance, commercial viability and tied-up loans;~~
- ~~repayment schedule, DSRA, disbursement plan, group-project status, shareholder agreements, escrow/TRA, state support, consultant inputs, equity infusion, standby arrangements and promoter capability;~~
- ~~risk register for pre-construction, sponsor/group, funding and other applicable risks;~~
- ~~risk description, allocated party, residual comments and Low/Medium/High level;~~
- ~~project stage/status, appraised versus incurred cost, original versus infused finance, original/revised DCCO, repayment shift, scope change, overrun and financing/repayment impact.~~ **All listed project records are verified 2026-10-10.**

Reapproval thresholds for DCCO, cost and scope changes remain confirmation-required.

**Status 2026-10-09 (GAP-P1-01):** `src/los/projects.py` implements the project module: multiple projects per application with facility linkage, project ID/name/type/funding type/purpose, TEV (total, consultant, report), cost (total, promoter contribution), means-of-finance plan, original DCCO, the risk register (description, level Low/Medium/High, category pre-construction/sponsor/funding/other, allocated party, residual comments) and a change log (cost/DCCO/scope with previous/current, reason and repayment impact). A cost/DCCO/scope change flags the project for reappraisal. DCCO/cost/scope reapproval thresholds remain confirmation-required.

### GAP-P1-02 — ESMS/ESDD governed process

The governed ESMS workspace now replaces the older display-only sector derivation.

Add:

- ~~screening date;~~
- ~~NaBFID excluded-activities checklist;~~
- ~~Yes/No/Not Available response;~~
- ~~mandatory remarks for Yes or Not Available;~~
- ~~project/entity E&S risk category;~~
- ~~CPCB category, coastal-zone impact, resettlement, environmental impact and E&S litigation;~~
- ~~information source and user remarks;~~
- ~~proposed category, introduction, proposal summary and company E&S risk assessment;~~
- ~~ESDD requirement/applicability;~~
- ~~additional ESMS conditions;~~
- ~~committee recommendation;~~
- ~~structured evidence and follow-up conditions;~~
- ~~ESMS Approval Note.~~ **All listed ESMS demo records and the AP gate are verified 2026-10-10.**

Exact categories, policy logic and questionnaires require the authoritative bank policy.

**Status 2026-10-09 (GAP-P1-02):** `src/los/esms.py` implements the governed screen: screening date, the NaBFID excluded-activities checklist (exploration, coastal, resettlement, environmental, litigation) with Yes/No/Not Available answers and mandatory remarks for Yes/Not Available, E&S risk category (A/B/C), CPCB category, coastal-zone impact, resettlement, environmental impact, E&S litigation, information source and remarks, ESDD applicability and committee recommendation fields, and the generated ESMS Approval Note. The ESMS gate blocks AP submission once screening has started (or projects exist) until it is complete. Exact policy logic and the full questionnaire remain confirmation-required and are labelled as a documented field set.

### GAP-P1-03 — Security master and lifecycle

Current collateral analysis supports primary/collateral labels, descriptions, market/forced-sale values, valuation dates, cover calculations and some charge text. Operational charge and CBS steps are manually confirmed.

Add persistent securities with:

- ~~security category, type and subtype;~~
- ~~facility linkage and multi-facility association where permitted;~~
- ~~description, apportioned value and proposed value;~~
- ~~valuation date and basis;~~
- ~~charge type and priority;~~
- ~~creation status/date;~~
- ~~perfection status and estimated timeline;~~
- ~~LOS Security ID;~~
- ~~CERSAI availability and ROC filing status;~~
- ~~CBS Security Number creation/linkage;~~
- ~~evidence and history visible at appraisal, post-sanction and disbursement.~~ **All listed security lifecycle records are verified 2026-10-10.**

Section 12.2 field details, valuation haircut, coverage formula, apportionment, lien search and document templates are not recoverable from the supplied screenshots and must remain open.

**Status 2026-10-09 (GAP-P1-03):** `src/los/securities.py` implements the security master: category/type/subtype, multi-facility linkage, description, apportioned and proposed values, valuation date/basis, charge type/priority, creation status, perfection status/timeline, and change history. Cover ratio is computed from apportioned value against linked facility amounts; the CBS Security Number lives in the disbursement record with its hard gate. Valuation haircut, coverage formula, apportionment rules, lien search and templates remain open.

### GAP-P1-04 — Fees, pricing and repayment

Add governed facility-level workflows for:

- ~~previously approved fees;~~
- ~~fee nature/type, common/facility scope, amount, percentage, milestone, comments and calculated total;~~
- ~~benchmark type/rate;~~
- ~~recommended and proposed spread;~~
- ~~recommended and proposed interest rate;~~
- ~~borrower risk rating;~~
- ~~comparison with other banks and justification;~~
- ~~mandatory benchmark type and proposed spread for applicable facilities;~~
- ~~pricing-change alert and RAROC review/recalculation;~~
- ~~tentative term-loan schedule: amount, tenor, pricing, repayment type/frequency, moratorium, repayment period and acceptability comments;~~
- ~~clear separation between tentative appraisal schedule and final disbursement terms.~~ **All listed pricing/fee/schedule records are verified 2026-10-10.**

The present demo MCLR, spread grid, cost of funds and hurdle RAROC must not become production defaults.

**Status 2026-10-09 (GAP-P1-04):** `src/los/pricing.py` implements the governed pricing workspace: benchmark type/rate, recommended and proposed spread/rate, borrower risk rating, other-banks comparison and justification, the mandatory benchmark+spread rule (RUL-07) enforced at AP submission, the pricing-change alert with mandatory RAROC recomputation, fee records (nature/type, scope, amount, milestone, invoice, status) and the tentative term-loan schedule kept explicitly distinct from the final disbursement terms. Demo values remain labelled and are never production defaults.

### GAP-P1-05 — External Work-Party management

The application-level EWP register is implemented. Verified items:

- ~~LIA;~~
- ~~LIE;~~
- ~~Security Trustee;~~
- ~~ESDD provider;~~
- ~~Legal Loan Counsel;~~
- ~~consultant name, contact number, email, phase and request ID;~~
- ~~linkage to application/project/facility/security and related report/document;~~
- ~~appointment, validity, review and status.~~ **All listed EWP register fields are verified 2026-10-10.**

Assignment workflow, contracts, fees, portal access, deliverable statuses and the source-specific meanings of LIA/LIE remain confirmation-required.

**Status 2026-10-09 (GAP-P1-05):** `src/los/ewp.py` implements the external work-party register: LIA, LIE, Security Trustee, ESDD provider and Legal Loan Counsel with name, contact number, email, phase and status, validated against the application's project/facility/security linkages. Assignment workflow, contracts, fees and portal access remain confirmation-required.

### GAP-P1-06 — Generated document and annexure completeness

Preserve the current CAM, IP Note, term sheet and sanction-letter strengths, then add the complete client output inventory:

- ~~Executive Summary;~~ **Generated and registered.**
- ~~Customer Due Diligence/Due Diligence Report;~~ **Generated and registered.**
- ~~ESMS Approval Note;~~ **Generated and registered.**
- ~~Disbursement Memo;~~ **Generated, hash-bound, reviewed and registered.**
- ~~CMA download;~~ **Generated and registered.**
- MCA, CIBIL and CRIF reports;
- CRILC and fraud evidence;
- CEIB Proforma A;
- UDIN response;
- ~~LPF Note, Rating Report and CRP Note registry/upload workflow;~~ **Verified for demo.**
- ~~TEV report registry/upload workflow;~~ **Verified for demo.**
- ~~committee minutes;~~ **Generated and registered.**
- Drawdown Request and Schedule;
- Annexure I Repayment Schedule;
- Annexure III Financial Covenants;
- Annexure IV Security Details;
- Annexures VI, IX, XI, XIII and XIV.

Exact template content is not in the client source and must be obtained before development acceptance.

**Status 2026-10-09 (GAP-P1-06):** the generated-output service produces the Executive Summary, Customer Due Diligence/Due Diligence Report, ESMS Approval Note, Disbursement Memo, CMA download and committee minutes as labelled demo artefacts (each registered in the document registry with versions); MCA/bureau reports, CEIB Proforma A, UDIN response, LPF/Rating/CRP notes and the annexure outputs are represented through the registry and the labelled adapter evidence. Exact template content remains to be obtained from the client.

## 24. P2 — Important controls and operating-model gaps

### GAP-P2-01 — Stage-specific mandatory rules

Implement an explicit rule catalog for:

- ~~PAN/LOS deduplication;~~
- identity checks by constitution/applicability;
- name-screening 90-day ageing and Compliance VP exception;
- ~~exposure breach alerts;~~
- ~~RAROC input staleness;~~
- ~~ESMS Yes/Not Available remarks;~~
- ~~pricing benchmark/spread mandatory rule;~~
- ~~syndication-to-Consortium rule;~~
- ~~non-complied condition reason/remarks;~~
- ~~Sanction Letter gate;~~
- ~~partial-execution balance calculation;~~
- ~~CBS Security Number gate;~~
- ~~Disbursement Memo gate;~~
- ~~Interim SOP compliance gate;~~
- ~~mandatory Post-Sanction Checker remarks;~~
- ~~final approval to Exit transition.~~ **All struck-through rules are implemented in the live rule catalog.**

~~Each implemented rule needs applicability, triggering event, severity, blocking behavior, exception authority, reset behavior and audit metadata.~~ **Verified in `RUL-01…RUL-20`; 90-day re-screening and time-based exception expiry implemented 2026-10-10.**

**Status 2026-10-09, updated 2026-10-10 (GAP-P2-01):** `src/los/rules.py` implements the explicit rule catalog (RUL-01…RUL-20) covering every listed rule — PAN/LOS dedupe, name-screening block with Compliance-VP exception, exposure breach, RAROC staleness, ESMS remarks, pricing benchmark/spread, syndication-to-Consortium, non-complied condition reason, Sanction Letter gate, partial-execution balance, CBS Security Number gate, Disbursement Memo gate, Interim SOP gate, Post-Sanction Checker remarks and final approval to Exit — each with applicability, trigger, severity (block/advisory), blocking behavior, exception authority, reset behavior and audit metadata. The catalog exposes a live status per application and is visible in the UI and API. ~~The 90-day name-screening timer is not implemented~~ **Implemented 2026-10-10 with blocking, reminders and escalation.**

### GAP-P2-02 — Dependency and stale-data management

~~Current field reviews can be marked stale when a credit assessment changes, but there is no complete dependency graph.~~ **Core identity, ownership/group, facility/pricing, borrower-rating, project, security, document/check and approval dependencies are implemented; client-specific numeric thresholds remain confirmation-required.**

Add dependency links and revalidation for:

- ~~PAN/group-relationship change → dedupe, applicable verifications and stale-conclusion invalidation;~~ **Verified 2026-10-10.**
- ~~facility amount/tenor/pricing → RAROC staleness and approval material-change review;~~ **Verified. Direct exposure/repayment recalculation thresholds remain open.**
- ~~rating → pricing, RAROC and authority review;~~ **Verified 2026-10-10 through borrower-rating dependency invalidation.**
- ~~project cost/DCCO/scope → reappraisal and approval review;~~ **Verified. Numeric thresholds remain open.**
- ~~security/value/charge → cover re-evaluation and approval material-change review;~~ **Verified. Pricing effects remain open.**
- ~~sanctioned terms → letter, execution, conditions and operational setup;~~ **Verified.**
- ~~beneficiary/payment data → final disbursement review;~~ **Verified through the memo hash and final review.**
- ~~document/check version → approval material-change assessment.~~ **Verified through approval snapshots.**

Only the RAROC change/recompute rule is explicitly detailed by Client One. Other dependency thresholds and reapproval effects must be validated with business owners.

**Status 2026-10-09 (GAP-P2-02):** a dependency matrix (13 documented triggers) is published with the rule catalog, and the implemented invalidations are: PAN/group change → identity recompute, dedupe re-run and KYC/GSTIN invalidation; facility/pricing change → RAROC staleness and mandatory recompute; governed record change after the approval snapshot → material-change review gate; project change → reappraisal flag; security value change → cover re-evaluation. Thresholds beyond these (reapproval bands, ageing) remain to be validated with business owners.

### GAP-P2-03 — Role, queue and permission matrix

Current roles are demo identities and role checks. Produce an approved matrix for:

- ~~Prospect/IP Analyst;~~
- LPFG Analyst and Senior Analyst;
- ~~VP AP Reviewer;~~
- ~~Risk Maker and Risk Reviewer;~~
- ~~Post-Rating Processor/VP;~~
- ~~EVP;~~
- CRP/CRAC reviewers;
- ~~Recommendations and Sanction Committees;~~
- ~~Compliance VP;~~
- ~~Post-Sanction Maker/Checker;~~
- ~~Disbursement Maker/Checker/VP/Final Approver;~~
- ~~administrator/support roles.~~ **All struck-through demo roles and their queues are verified.**

For each, define queue visibility, read/write fields, decisions, reassignment, delegation, evidence access and segregation-of-duties constraints. Authentication and enterprise IAM are outside the confirmed Client One source but are necessary production design items.

**Status 2026-10-09 (GAP-P2-03):** the 18 demo roles are implemented with queue visibility, per-step actions and segregation of duties (makers cannot act at checker/committee steps; Compliance VP is the only exception authority; the Disbursement VP Review is read-only). The approved matrix with delegation, field-level permissions and enterprise IAM remains confirmation-required (§28) and is presented as the demo role model, not the bank's.

### GAP-P2-04 — Audit and evidence completeness

Preserve the current append-only LOS event table and extend it to record:

- ~~original and changed values for governed workspace records;~~ **Verified through field histories/events.**
- ~~actor, acting role and decision authority;~~ **Verified. Delegation remains open.**
- ~~source record and version;~~ **Verified for governed documents/checks/snapshots.**
- ~~document/check/calculation version;~~ **Verified.**
- ~~assignment and queue movement;~~ **Verified.**
- ~~exception decision, re-screen invalidation history and time-based expiry;~~ **Verified 2026-10-10.**
- ~~maker/checker/committee decision and remarks;~~ **Verified.**
- ~~material-change determination;~~ **Verified.**
- ~~exact governed-domain versions viewed at approval.~~ **Verified through the approval snapshot hashes.**

Physical immutability, retention, archive and tamper-evidence design remain solution decisions.

**Status 2026-10-09 (GAP-P2-04):** the append-only event table records original and changed values (facility change history, condition updates, document versions), actor and acting role, from/to step, decisions with remarks, material-change determinations, exception approvals, and the approval snapshot binding the exact domain versions reviewed at each sanction. Physical immutability, retention and tamper-evidence design remain solution decisions.

### GAP-P2-05 — SLA, rework and exception operations

The current app calculates calendar-day SLA from static step values and supports reassignment/escalation. Add or confirm:

- ~~working-day calendars and holidays;~~ **Implemented 2026-10-10 with labelled demo holidays and weekend exclusion.**
- ~~queue-level and stage-level calendar-day SLA;~~ **Verified.**
- ~~configured rework destinations for implemented actions;~~ **Verified. Reason-specific routing implemented 2026-10-10 (UAT-P0-1).**
- ~~withdrawal, modification, drop and termination behavior;~~ **Implemented 2026-10-10 (UAT-P0-1).**
- delegation/substitution during absence;
- parallel review if required;
- integration timeout/poll/retry behavior;
- ~~exception ageing, reminders and escalation;~~ **Implemented 2026-10-10 (UAT-P0-2).**
- ~~MIS for breaches, pending checks/documents/conditions and approvals.~~ **Verified.**

**Status 2026-10-09, updated 2026-10-10 (GAP-P2-05):** the MIS (`src/los/mis.py`) reports breaches, pending checks, documents, conditions and approvals across the 25-step workflow. UAT 2026-10-10: SLA is now measured in **working days** against a labelled demo holiday calendar (weekends + listed holidays excluded), with **ageing escalation** (a breach aged beyond 2 days flags `escalated`); the MIS and dashboard surface breaches and escalations separately. The alternate workflow decisions — **Application Withdrawn, Modification Proposed, Drop/termination, Recommend for Modification** — are now distinct, audited workflow actions, and **reason-specific rework destinations** are supported (a checker/committee may rework to a specific earlier step). Remaining (not implemented, labelled open): delegation/substitution, parallel review and integration timeout/poll/retry behavior.

### 24.1 Demo-pending implementation register — 2026-10-10

**Status 2026-10-10 (UAT):** every item in this register is now implemented in the self-contained demo and covered by tests (`tests/test_los_uat_p1.py`). External production APIs, credentials and client data remain excluded by the demo-scope decision above.

| Priority | Pending demo change | Resolution 2026-10-10 |
|---|---|---|
| P0 | Withdrawal, Modification Proposed, Drop and reason-specific rework destinations | **Done (UAT-P0-1).** Distinct audited actions: `withdraw` and `drop` end the application (WITHDRAWN / DROPPED, reason mandatory); `propose_modification` (post-sanction maker) and `recommend_modification` (read-only checker) re-enter credit reassessment with a recorded request; `return` accepts a specific earlier rework destination. |
| P0 | 90-day name-screening re-screen timer and time-based exception expiry | **Done (UAT-P0-2).** A 90-day re-screen of name-screening/MLRA blocks progression once overdue; a Compliance VP exception lapses 90 days after it is granted (an expired exception re-blocks the check). Dashboard Screening Alerts raise reminders (due ≤ 14 days) and escalations (overdue / lapsed). |
| P0 | Party-level subject/evidence linkage | **Done (UAT-P0-3).** Each related party carries its own governed evidence: KYC, CIBIL/CRIF, name screening (auto-linked from the application screening for individuals), a rating reference, a financial-record reference, document references and a Compliance-VP exception that lapses on re-record. Coverage is shown per party. |
| P1 | Relationship, sourced address, key-person role and party status | **Done (UAT-P1-4).** Captured at creation and in party maintenance, with party-status validation. |
| P1 | Entity-incorporated flag and latest-material-information date | **Done (UAT-P1-5).** Governed entity fields with attribution; the date is validated (not in the future). |
| P1 | LPFG Analyst/Senior Analyst assignment and CRAC vocabulary | **Done (UAT-P1-6).** Explicit assignment fields plus a labelled CRAC recommendation vocabulary (the client's exact committee labels remain confirmation-required). |
| P1 | Downloadable MCA/CIBIL/CRIF, CEIB Proforma A, UDIN and Annexure I/III/IV/VI/IX/XI/XIII/XIV outputs | **Done (UAT-P1-7).** Each is a separate, self-contained downloadable HTML output (labelled demo artefacts); annexures are labelled templates, not fabricated content. |
| P1 | Per-check evidence upload and detailed EWS/LEI/UDIN grids | **Done (UAT-P1-8).** Evidence references attach to a check (also registered in the document registry); EWS and LEI expose detailed grids and UDIN has a recordable verification grid that drives the check result. |
| P2 | Working-day/holiday SLA calendars, reminders and ageing escalation | **Done (UAT-P2-9).** Working-day SLA against a labelled holiday calendar; breaches aged beyond the threshold escalate and are surfaced in the MIS and dashboard. |
| P2 | Ownership/group/rating dependency invalidations | **Done (UAT-P2-10).** Ownership changes, group-structure (role) changes and borrower-rating changes raise governed invalidations that flag the affected conclusions as stale until resolved with a note. Client-specific numeric reapproval thresholds remain confirmation-required. |
| P2 | Recurring covenant breach/cure/reminder monitoring | **Done (UAT-P2-11).** FC/NC/CS/PD covenants are tested on their frequency; a failed test makes the condition non-compliant, a passing test (or explicit cure) restores it, and untested covenants past their next due date raise reminders. |
| P2 | Repeat-tranche re-entry after Exit | **Done (UAT-P2-12).** A governed, audited re-open at the Disbursement Maker for a subsequent drawdown cycle (reason mandatory), with the usual DIS gates applying to the new tranche. |

The following are **not demo blockers**: production CBS/LMS/bureau/regulatory connections, enterprise IAM, physical immutable archive, payment settlement/reconciliation, authoritative bank formulas and exact legal templates. They require information the client will not provide and must remain visibly labelled as simulated, configurable or out of scope.

## 25. Client requirements currently supported and to preserve

The remediation should retain these useful current capabilities:

- persistent CLOS application identifier and stage/step/assignee state;
- role-based queues, allocation, reassign and escalation;
- maker/checker/committee segregation and audit events;
- prospect document upload and human-controlled document prefill;
- source page, snippet, confidence, conflict and edit-reason provenance;
- generated IP Note;
- historical financials, ratios, projections, stress testing and repayment assessment;
- deterministic policy results and traceable AI-assisted CAM content;
- Risk Maker tabs and field confirm/override review;
- committee decision pack, unresolved-risk/deviation view and comments;
- sanction amount validation and mandatory minutes when sanction differs from recommendation;
- versioned term sheets and sanction letters;
- CP/CS satisfy, defer, waive and reopen controls;
- checker approval for condition deferral/waiver;
- IP-versus-AP comparison and deviation register;
- sanctioned-limit and tranche amount validation;
- disbursement checklist and remaining-limit calculation;
- MIS, audit API and generated CAM/PDF outputs;
- complementary challenge, investigation, observation, stress, repayment and AI-assistance features.

These verified strengths form the reusable demo baseline; the remaining client-visible changes are listed in Section 24.1.

## 26. Client One stage-to-current-workflow mapping

| # | Client One stage | Closest current step(s) | Alignment | Required action |
|---|---|---|---|---|
| 1 | Prospect Sourcing | `ps_maker` | **Demo supported** | ~~Entity-incorporated flag remains a small form extension~~ **Implemented 2026-10-10** |
| 2 | IP Note Processing | `ip_note` | **Demo supported** | ~~LPFG Analyst/Senior Analyst fields remain open~~ **Implemented 2026-10-10** |
| 3 | IP VP Review and CRP Processing | `ip_note_review`, `ip_crp_evp`, `ip_crp_vp`, `ip_risk_maker` | **Demo supported** | Exact client queue ownership can be confirmed during demo feedback |
| 4 | IP Committee Sanction | `ip_sanction` | **Demo supported** | None for demo |
| 5 | Application Processing | `ap_note` and governed workspaces | **Demo supported** | None for demo |
| 6 | VP AP Review | `ap_review` | **Demo supported** | ~~Dedicated latest-information date remains open~~ **Implemented 2026-10-10** |
| 7 | Risk Maker and Risk Review | `ap_risk_maker`, `ap_risk_review` | **Demo supported** | Uses labelled demo risk models |
| 8 | Post-Rating Processing and VP Review | `ap_post_rating`, `ap_rating_vp` | **Demo supported** | None for demo |
| 9 | EVP AP Recommendation | `ap_evp` | **Demo supported** | None for demo |
| 10 | Recommendations Committee | `ap_recommend` | **Demo supported** | Exact CRAC vocabulary can be confirmed during demo feedback |
| 11 | CRP and ESMS Processing | `ap_crp_vp` plus governed ESMS/CRP workspaces before sanction | **Demo supported** | Implemented as governed workspaces rather than another duplicate queue |
| 12 | Committee Sanction | `ap_sanction` | **Demo supported** | Uses labelled demo authority matrix |
| 13 | Post-Sanction Maker | `pos_maker` | **Demo supported** | ~~Withdrawal/modification actions remain open~~ **Implemented 2026-10-10** |
| 14 | Post-Sanction Checker | `pos_checker` | **Demo supported** | ~~Drop/Recommend-for-Modification vocabulary remains open~~ **Implemented 2026-10-10** |
| 15 | Disbursement Maker | `dis_maker` | **Demo supported** | None for the first-tranche demo |
| 16 | Disbursement Checker | `dis_checker` | **Demo supported** | None for demo |
| 17 | Disbursement VP Review | `dis_vp_review` | **Demo supported** | Rework label and significant-change capture verified |
| 18 | Disbursement Approval | `dis_approver` | **Demo supported** | None for demo |
| 19 | Exit bucket/completion | `Exit (approved)` | **Demo supported** | Correctly does not claim fund settlement |

## 27. Traceability to every Client One source chapter

| Client source chapter | Requirement captured in this specification | Current alignment |
|---|---|---|
| 1 Evidence/scope/terminology | Sections 1, 2 and 21 | Evidence caveats preserved |
| 2 Purpose/product/supported lending | Sections 3, 6 and 22 | Demo supported |
| 3 Nineteen operational stages | Sections 4, 5 and 26 | Demo supported through 25 mapped technical queues |
| 4 Prospect Sourcing | GAP-P0-02 | Demo supported; entity flag and validation refinements implemented 2026-10-10; rich text is optional |
| 5 IP Note Processing | GAP-P0-03 | Demo supported; LPFG assignments and extended party fields implemented 2026-10-10 |
| 6 Fifteen verification checks | GAP-P0-05 and GAP-P0-06 | Demo supported; 90-day re-screen, exception expiry and party-level evidence implemented 2026-10-10 |
| 7 Financial Analysis | GAP-P0-07 | Demo supported |
| 8 Risk-Rating Framework | GAP-P0-08 | Demo supported with labelled model |
| 9 Proposal and Exposure | GAP-P0-09 | Demo supported |
| 10 Project Assessment | GAP-P1-01 | Demo supported |
| 11 ESMS | GAP-P1-02 | Demo supported |
| 12 Terms/Conditions/Covenants | GAP-P0-14 | Demo supported |
| 13 Security Management | GAP-P1-03 | Demo supported |
| 14 Pricing/Fees/Repayment | GAP-P1-04 | Demo supported |
| 15 External Work-Party | GAP-P1-05 | Demo supported |
| 16 Documentation | GAP-P0-12 and GAP-P1-06 | Demo supported; the named extra outputs/templates are generated 2026-10-10 |
| 17 Application/Sanction Workflow | GAP-P0-10 and GAP-P0-11 | Demo supported; alternate decisions and rework destinations implemented 2026-10-10 |
| 18 Post-Sanction | GAP-P0-13 | Demo supported; alternate decisions and covenant monitoring implemented 2026-10-10 |
| 19 Disbursement Maker | GAP-P0-15 | Demo supported |
| 20 Checker/VP/Final Approval | GAP-P0-16 | Demo supported |
| 21 Integrations | GAP-P0-17 | Demo supported; production APIs out of scope |
| 22 Business Controls | GAP-P2-01 | Demo supported; 90-day timer and exception expiry implemented 2026-10-10 |
| 23 Roles/Responsibilities | GAP-P2-03 | Demo supported; a few named role/delegation refinements open |
| 24 Conceptual Data Architecture | Sections 10 and 22 | Demo cardinality supported |
| 25 Cross-Module Dependencies | GAP-P2-02 | Core dependencies supported; policy thresholds open |
| 26 Document/Output Inventory | GAP-P1-06 | Core generated outputs supported; the named extra templates are generated 2026-10-10 |
| 27 Known source gaps | Sections 28 and 29 | Preserved as confirmation items |
| 28 Client Two comparison checklist | Sections 21–27 | Fully used for comparison structure |
| 29 Glossary | Existing terminology plus Section 29 | Terms retained; internal expansions not invented |

## 28. Items that must not be presented as confirmed Client One requirements

The supplied context does not verify the following. They can be retained as recommendations or future requirements only after client confirmation:

1. Complete original PDF content beyond the screenshots.
2. Complete Security Summary Section 12.2.
3. Exact CMA, ratio, exposure, group-rating, RAROC and MLRA formulas.
4. Exact credit limits, policy thresholds and delegated-authority matrix.
5. Full state/action matrix, exceptional branches and rework destinations.
6. Complete UI layouts, field types, dropdown masters and applicability matrix.
7. API schemas, providers, authentication, frequency, uptime and retry guarantees.
8. Relationship constraints beyond the documented multiplicities.
9. Every waiver, deviation and non-compliance escalation rule.
10. Final document templates, e-signing, retention and legal enforceability.
11. Client One's physical technology stack, database, services, hosting and network.
12. Client One authentication, encryption, cyber controls, disaster recovery and audit-storage design.
13. Production performance and volume targets.
14. LOS execution of money transfer.
15. Payment settlement acknowledgement, retry, reversal or reconciliation ownership.
16. Exit bucket meaning beyond documented workflow completion.
17. Formal expansions of LPFG, CRP/CRAC, FT, LIA/LIE and EPM.
18. Exact later-drawdown re-entry workflow.

### 28.1 Source corrections to earlier recommendations

- Payment execution, execution acknowledgement and reconciliation remain valuable target controls but are not proven Client One parity requirements.
- Exit means documented workflow completion after final approval; it must not be described as verified beneficiary settlement.
- Immutable approval packaging is a strong audit recommendation. Client One supports traceability of changes and decision evidence, but the physical snapshot mechanism is not demonstrated.
- Dynamic authority logic, committee quorum/voting and delegation details require the authoritative bank matrix; they must not be invented from the screenshots.
- Repeated drawdowns are suggested by subsequent-disbursement conditions, but the complete repeat-cycle state machine is not documented.

## 29. Updated implementation order

### Release 1 — Correct the domain foundation

1. ~~Application-party, multi-facility, multi-project and security data model.~~ **Demo-complete.**
2. ~~Prospect Sourcing and IP Note core data capture.~~ **Demo-complete; extended fields implemented 2026-10-10.**
3. ~~Application-scoped document/check/version model.~~ **Demo-complete.**
4. ~~Backward-compatible primary `facility` view for existing one-facility records.~~ **Demo-complete.**

### Release 2 — Complete mandatory appraisal controls

1. ~~Fifteen-check due-diligence workspace, evidence, 90-day ageing and hard stops.~~ **Demo-complete 2026-10-10.**
2. ~~Entity-wise CMA and financial review.~~ **Demo-complete.**
3. ~~Rating/group-rating/RAROC governance with labelled demo model.~~ **Demo-complete.**
4. ~~Proposal, exposure, conduct, annexure data and labelled downloadable demo outputs.~~ **Demo-complete 2026-10-10; authoritative client templates remain confirmation-required.**
5. ~~Project Assessment and ESMS.~~ **Demo-complete.**
6. ~~Security, pricing, fee and repayment masters.~~ **Demo-complete.**

### Release 3 — Align sanction governance

1. ~~Nineteen-stage mapping to the 25 technical queues, including alternate decisions and targeted rework.~~ **Verified 2026-10-10.**
2. ~~Recommendations Committee, CRP/ESMS and VP stages.~~ **Demo-complete.**
3. ~~Unified authority routing and deviation handling.~~ **Demo-complete with labelled matrix.**
4. ~~Version-bound decision evidence and material-change processing.~~ **Demo-complete.**
5. ~~Mandatory outputs and document gates.~~ **Demo-complete.**

### Release 4 — Complete fulfilment and disbursement approval

1. ~~Sanction consent and facility execution.~~ **Demo-complete.**
2. ~~Complete condition/covenant taxonomy.~~ **Demo-complete.**
3. ~~CIF, limits, accounts and CBS security references.~~ **Demo-complete with labelled simulated operations.**
4. ~~Beneficiary, fee, interest, arrears, repayment and annexure records.~~ **Demo-complete.**
5. ~~Disbursement Memo, SOP gate, Checker, VP and Final Approval.~~ **Demo-complete.**
6. ~~Accurate Exit/approval semantics.~~ **Demo-complete.**

### Release 5 — Production integrations and operating controls — outside demo scope

1. Production CBS, LMS and authoritative regulatory/provider adapters.
2. Production error/retry monitoring beyond the demo evidence trail.
3. Enterprise IAM/RBAC, working-day SLA and delegation; ~~operational MIS~~ **demo-complete.**
4. Performance, resilience, retention, security and recovery requirements after client confirmation.

## 30. Completion criteria for Client One functional parity

Client One parity may be claimed only when:

- ~~every row in Section 27 has Demo-supported status or an explicitly recorded open refinement;~~
- ~~one application can manage multiple documented parties, facilities and projects;~~
- ~~all 15 checks have governed manual/API demo lifecycle behavior and evidence;~~
- ~~CMA, ratings, RAROC, exposure, project, ESMS, terms, security and pricing are governed source records rather than CAM-only text;~~
- ~~all documented alternate actions are implemented;~~ **Verified 2026-10-10.** Exact bank role names remain confirmation-required and are not represented as confirmed.
- ~~required core documents and hard-stop rules are enforced;~~
- ~~post-sanction and Disbursement Maker core fields are complete;~~
- ~~CIF/limit/account/security references and beneficiaries are persistently recorded;~~
- ~~Disbursement Checker, VP and Final Approval are distinct and auditable;~~
- ~~Exit is represented accurately as workflow completion;~~
- ~~mock, synthetic, unavailable and manually confirmed data are never presented as real production integrations;~~
- ~~all production-only/confirmation-required items are explicitly excluded from demo scope in Sections 22, 24.1 and 28.~~

---

This file is the master functional baseline for client-specification and current-application comparison. Changes to confirmed requirements should be made only when supported by additional client material or a recorded client decision.
