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
| D6 | **Expected credit loss at origination**: PD, LGD, EAD, stage, ECL | RBI's ECL directions apply from 1 April 2027 |
| D7 | **Risk-based pricing (RAROC)**: minimum price against the hurdle rate | Pricing becomes a calculation, not free text |
| L2 | **AI governance pack (RBI FREE-AI)**: per-CAM AI-use log, model card, bias checks | Makes the AI acceptable to a regulated bank |
| C3 | **Change-only CAM** for renewals and re-runs; role views of one CAM | Reviewers read only what changed |
| D8 | Working-capital assessment (turnover / MPBF / cash budget); term-loan IRR and break-even | Standard appraisal, automated end to end |
| D9 | Related-party, group exposure (Large Exposures Framework) and unhedged forex checks | Compliance |

## Then: Phase 3, connect real data

| ID | Item |
|---|---|
| D10 | Commercial bureau (CIC / Probe42), RBI defaulter lists, insolvency (NCLT) cases, ECGC caution list. Makes the "not verifiable" hard rules checkable |
| D11 | MCA charges and director checks; promoter share pledges |
| D12 | Account Aggregator / ULI consent-based bank and GST data; customer and supplier concentration from GST invoices |
| D13 | Core banking and CRILC feeds for existing customers' conduct (the engines exist) |

## Later: Phase 4, beyond origination

| ID | Item |
|---|---|
| L3 | Covenant and early-warning monitoring after disbursement, driven by the CAM |
| L4 | Portfolio-aware origination: sector caps, concentration, effect on the book's expected loss |
| L5 | Credit-committee pack with likely questions answered from the record |

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
