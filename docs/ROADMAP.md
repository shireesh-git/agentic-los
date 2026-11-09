# Roadmap

What is built, what comes next, and the known limits of the proof of concept. The reasoning behind the
order is in [DATA_CAM_DIFFERENTIATION_REVIEW.md](DATA_CAM_DIFFERENTIATION_REVIEW.md). Every item is
judged by the **differentiating capability** it gives a bank, not by how closely it copies today's
process.

## Built

| Area | What it does |
|---|---|
| Agentic LOS | Five roles, one chain, a chat on every screen; configurable stages, fields and conditions |
| CAM engine | 7 analysis agents; a streamlined CAM (Decision Summary built from data + 8 sections) in about 30 s; selective re-run of only the sections a change affects |
| Data acquisition | 5 parallel agents, API first (GLEIF, OFAC/UN sanctions, GDELT live; Probe42 ready for a key), document fallback, cross-source verification |
| Phase 1 differentiators | Credit metrics with policy bands; per-figure confidence; sustainable limit and the structure that passes; earnings quality; revenue truth; early-warning indicators at origination; deviation register; Credit Challenge Agent with suggested actions; Copilot next steps |
| Governance | Written justification to go against the engine; audit trail report; every value sourced; outcome analytics (decisions against the engine, rework, SLA) |

## Next: Phase 2, timed to regulation

| ID | Item | Why it matters |
|---|---|---|
| D6 | **Expected credit loss at origination**: PD, LGD, EAD, stage, ECL — **built 2026-11-09** (demo master scale in rules.yaml → ecl) | RBI's ECL directions apply from 1 April 2027 |
| D7 | **Risk-based pricing (RAROC)**: minimum price against the hurdle rate | Pricing becomes a calculation, not free text |
| L2 | **AI governance pack (RBI FREE-AI)**: per-CAM AI-use log, model card, bias checks — **built 2026-11-09** (proposal menu → AI Governance Pack; config/ai_governance.yaml) | Makes the AI acceptable to a regulated bank |
| C3 | **Change-only CAM** for renewals and re-runs; role views of one CAM | Reviewers read only what changed |
| D8 | Working-capital assessment (turnover / MPBF / cash budget); term-loan IRR and break-even | Standard appraisal, automated end to end |
| D9 | Related-party, group exposure (Large Exposures Framework) and unhedged forex checks | Compliance |
| P1 | **Back-test on past CAMs**: run the engine on the bank's historical cases (sanctioned and later defaulted) and show where its verdict and challenges would have flagged them | How a bank decides to buy |
| P2 | **Credit policy → rules agent**: reads the bank's credit policy and delegation of powers, drafts `rules.yaml` / `approval.yaml` for a person to approve | Onboarding a bank in days |
| P3 | **Notes-to-accounts reader**: auditor qualifications, emphasis of matter, CARO remarks, contingent liabilities, related-party notes | Where many problems hide; rarely read |
| P4 | **Borrower document agent**: a borrower link; the agent asks for missing documents, reads them, chases gaps, fills fields | The RM stops chasing paperwork |
| P5 | Agent accuracy harness: fixed case set, field-extraction accuracy, figures-check rate, drift per model (hygiene) | Model-risk teams ask for it; feeds L2 |
| P6 | Sanction terms as structured, checkable covenants (enabler for L3) | Monitoring needs rules, not text |

## Then: Phase 3, connect real data

| ID | Item |
|---|---|
| D10 | Commercial bureau (CIC / Probe42), RBI defaulter lists, insolvency (NCLT) cases, ECGC caution list. Makes the "not verifiable" hard rules checkable |
| D11 | MCA charges and director checks; promoter share pledges |
| D12 | Account Aggregator / ULI consent-based bank and GST data; customer and supplier concentration from GST invoices |
| D13 | Core banking and CRILC feeds for existing customers' conduct (the engines exist) |
| D14 | **Promoter and group network**: directors' other companies, their defaults and charges, shared addresses and auditors; connected borrowers and fraud rings (builds on D11) |
| D15 | NeSL (information utility) default records; consortium data: lead bank's CAM and other lenders' terms |
| D16 | Core banking / loan system push at disbursement: limits and terms set up without retyping (hygiene) |
| D17 | India-hosted or on-prem model option (data residency; critical for public-sector banks) |

## Later: Phase 4, beyond origination

| ID | Item |
|---|---|
| L3 | Covenant and early-warning monitoring after disbursement, driven by the CAM |
| L4 | Portfolio-aware origination: sector caps, concentration, effect on the book's expected loss |
| L5 | Credit-committee pack with likely questions answered from the record |
| L6 | **Learning loop**: decisions, overrides and challenges compared with each loan's outcome; which challenges predicted stress; thresholds retuned |
| L7 | **Renewal autopilot**: the annual renewal prepared from monitoring data and new financials, showing only what changed (C3 + L3) |
| L8 | Early resolution: on SMA, the agent drafts restructuring / resolution options |

## Known limits of the proof of concept

- **Infrastructure:** SQLite, one server process, background threads; no message queue.
- **Sign-in:** demo sign-in with no passwords; no single sign-on or entitlements.
- **Disbursement:** simulated; no payment system is called.
- **Demo data:**
  - most catalogue borrowers have no bureau, GST or bank data on record, so those checks show
    "not verifiable";
  - the CRILC and social-media blocks in the engine are demo data and are labelled as such.
- **Policy values:** the delegation of powers (`config/approval.yaml`) and the policy limits
  (`config/rules.yaml`) are placeholders until the bank supplies its own.
