Yes — this can be designed cleanly, and the right answer is **not** “LLM does everything.”

For your use case, the winning pattern is:

**deterministic data pipeline + policy/rules engine + benchmark engine + controlled LLM orchestration + analyst copilot**

That is the only way to get:

* **same input → same output**
* **auditability**
* **ETB + NTB support**
* **regulatory defensibility**
* **chat-based analyst responses**
* **CAM auto-generation**

For Indian corporates, your source strategy should reflect the fact that **listed** entities have exchange/SEBI-driven disclosure obligations, while **private/unlisted** entities rely much more on MCA filings, lender-provided documents, bureau/commercial credit data, and internal bank records. SEBI’s LODR regulations remain the core disclosure framework for listed entities; NSE exposes corporate filings, financial results, annual reports, BRSR, governance, ratings, and default-payment related disclosures; MCA’s Master Data Services V3 supports company/LLP and director/designated partner lookup; RBI’s KYC Direction governs onboarding/KYC obligations; and RBI requires CICs to provide comprehensive CIRs that include all available modules for a borrower. ([Securities and Exchange Board of India][1])

## 1. What the solution should do

Your platform should do 6 things end to end:

1. **Ingest**

   * financial statements
   * annual reports
   * stock exchange disclosures
   * MCA/company master data
   * bureau/commercial credit reports
   * internal ETB banking data
   * market/news/social/media signals
   * analyst-uploaded documents

2. **Validate**

   * document-to-document mismatches
   * borrower-submitted vs MCA mismatch
   * listed disclosure vs annual report mismatch
   * internal banking behavior vs declared turnover mismatch
   * ratio consistency checks
   * stale filing checks
   * missing schedule/note checks

3. **Transform**

   * OCR/extract/tabularize
   * normalize line items to a canonical chart of accounts
   * map industry-specific metrics
   * build borrower, group, facility, collateral, and conduct features

4. **Benchmark**

   * compare to sector peers
   * compare to size band
   * compare to rating bucket
   * compare to prior-period trend
   * compare ETB behavior against internal peer cohorts

5. **Decide / Recommend**

   * run deterministic policy rules
   * compute risk flags
   * produce credit recommendation inputs
   * generate exception list
   * propose CAM sections

6. **Explain**

   * generate CAM
   * answer analyst queries in chat
   * show citations back to source docs
   * keep full audit trail of how every number was produced

---

## 2. Design principle: what LLM should do vs should not do

This is the most important architecture choice.

### LLM should do

* document orchestration
* section drafting
* narrative synthesis
* analyst Q&A
* workflow routing
* ambiguity detection
* evidence summarization

### LLM should not be source of truth for

* numeric extraction from financial statements
* ratio calculation
* policy decisioning
* eligibility logic
* benchmark calculation
* mismatch detection
* final recommendation scoring

Those must be **deterministic services**.

So the model is:

**LLM = coordinator + narrator**
**Deterministic services = truth engine**

---

## 3. Target architecture

```text
                    ┌─────────────────────────────┐
                    │  Analyst / RM / Credit Chat │
                    └──────────────┬──────────────┘
                                   │
                         ┌─────────▼─────────┐
                         │ LLM Orchestrator  │
                         │ (workflow brain)  │
                         └─────────┬─────────┘
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        │                          │                          │
┌───────▼────────┐       ┌────────▼────────┐       ┌────────▼────────┐
│ Ingestion Hub   │       │ Validation Hub  │       │ CAM Composer    │
│ docs/APIs/files │       │ rules/checks    │       │ narrative layer │
└───────┬────────┘       └────────┬────────┘       └────────┬────────┘
        │                         │                         │
┌───────▼───────────────────────────────────────────────────▼──────────┐
│                   Canonical Lending Data Model                        │
│ borrower | group | financials | facilities | collateral | conduct    │
│ market | filings | social/news | benchmarks | exceptions | audit      │
└───────┬───────────────────────────────────────────────────┬───────────┘
        │                                                   │
┌───────▼────────┐  ┌───────────────┐  ┌────────────────┐  ┌───────────▼──────┐
│ Extraction     │  │ Rules Engine  │  │ Benchmark Eng. │  │ Risk/Scoring Eng. │
│ parser/OCR/XBRL│  │ sector policy │  │ peer compare   │  │ PD/rating flags   │
└────────────────┘  └───────────────┘  └────────────────┘  └───────────────────┘
```

---

## 4. Source model: public listed vs private/unlisted

## A. Public listed corporates

For listed companies, your primary sources should be:

* stock exchange filings
* quarterly/annual financial results
* annual reports
* corporate announcements
* BRSR / BRSR Core
* credit rating disclosures
* debt default / payment disclosures
* corporate governance filings
* MCA master and corporate structure

NSE explicitly exposes corporate filings, annual reports, BRSR, credit rating details, default payment details, governance, and financial results/XBRL-related access points. Listed entities are governed by SEBI’s LODR regulations, and BRSR Core has a SEBI framework for assurance and value-chain ESG disclosures. ([NSE India][2])

## B. Private / unlisted corporates

For private companies, primary sources are:

* borrower-uploaded audited financials
* provisional financials / MIS
* bank statements
* GST / tax / statutory docs where available to lender
* bureau/commercial credit reports
* MCA master/company search
* director/promoter data
* charge/filing data
* internal banking and conduct data for ETB

MCA Master Data Services V3 supports company/LLP lookup and directors/designated partners lookup, which makes it a core enrichment source for unlisted entities too. RBI’s KYC direction remains relevant for onboarding, and comprehensive CIRs from CICs are important for the borrower view. ([Ministry of Corporate Affairs][3])

## C. Social / media / market data

Use these as **secondary intelligence**, not accounting truth:

* news sentiment
* promoter/director controversy signals
* market sentiment
* analyst commentary
* social media trend anomalies
* employee and supply-chain chatter where legally permissible

This layer should produce:

* **reputational risk indicators**
* **early warning indicators**
* **event flags**

It should **never overwrite regulatory or filed financial data**.

---

## 5. Core platform modules

## Module 1 — Document ingestion

Inputs:

* PDF
* scanned PDF
* Excel
* Word
* XBRL
* API response
* email attachments
* SFTP drops
* portal uploads

Subcomponents:

* file registry
* document classifier
* OCR service
* table extractor
* XBRL parser
* statement parser
* metadata extractor
* version controller

Output:

* document ID
* source type
* source priority
* filing period
* extracted sections
* confidence score
* immutable hash

### Determinism requirement

Store:

* file hash
* parser version
* OCR version
* extraction model version
* prompt version if LLM used for non-critical tagging

That gives reproducibility.

---

## Module 2 — Canonical data model

You need a **single normalized schema** so every source lands in the same structure.

### Suggested entities

* `borrower`
* `group_entity`
* `director_promoter`
* `financial_statement`
* `financial_line_item`
* `facility_request`
* `existing_exposure`
* `collateral`
* `market_signal`
* `social_signal`
* `regulatory_filing`
* `validation_exception`
* `benchmark_result`
* `cam_section`
* `source_evidence`
* `audit_event`

### Canonical line item mapping example

All incoming variants should map to a standard chart:

* revenue from operations
* EBITDA
* EBIT
* PAT
* net worth
* total debt
* current assets
* current liabilities
* inventory
* trade receivables
* trade payables
* operating cash flow
* capex
* DSCR inputs

Without this layer, benchmarking and ruleing will break.

---

## Module 3 — Validation engine

This is one of the strongest product differentiators.

Validation should happen at 5 levels.

### A. Structural validation

* pages missing
* auditor report missing
* schedules missing
* annual report year mismatch
* balance sheet not balancing
* notes referenced but absent

### B. Cross-source validation

* borrower-submitted revenue vs exchange filing revenue
* submitted shareholding vs MCA/director records
* submitted debt vs bureau/commercial exposure
* annual report debt vs charge/loan disclosures
* ETB declared turnover vs internal account turnover trend

### C. Analytical validation

* current year ratios mathematically inconsistent
* PAT impossible given tax/EBIT values
* sudden receivable spike with no revenue context
* EBITDA margin outlier vs peer set
* negative operating cash flow despite growth narrative

### D. Temporal validation

* stale filing
* outdated bureau report
* provisional older than latest declared period
* market event after last CAM refresh

### E. Policy validation

* missing mandatory doc for NTB
* required KYC fields absent
* unverified promoter data
* restricted sector trigger
* leverage threshold breach
* concentration limit breach

### Validation output

Every failed check should create:

* `exception_code`
* `severity`
* `source_doc_ref`
* `impacted_metric`
* `resolution_status`

This is where analyst productivity explodes.

---

## 6. Industry benchmark engine

This is not just “compare to industry average.”

You need a multi-axis benchmark engine.

### Benchmark dimensions

* sector
* subsector
* listed vs unlisted
* company size band
* geography
* operating model
* rating band
* facility type
* public peers vs private peer cohort
* borrower historical trend

### Benchmark types

* profitability
* leverage
* liquidity
* working-capital cycle
* growth
* cash generation
* capex intensity
* debtor days / inventory days / payable days
* market valuation proxies for listed
* governance / ESG overlays for listed

### Output example

```json
{
  "metric": "debt_to_ebitda",
  "borrower_value": 4.8,
  "peer_median": 3.2,
  "peer_p75": 4.1,
  "status": "worse_than_peer",
  "severity": "high"
}
```

### Sector packs

Build sector packs for:

* manufacturing
* EPC
* infrastructure
* real estate
* NBFC
* logistics
* pharma
* IT/services
* trading
* commodity businesses

Each sector pack defines:

* mandatory metrics
* preferred ratios
* stress parameters
* narrative template
* red flags
* benchmark cohorts

---

## 7. CAM generation engine

CAM should be generated in **two passes**.

## Pass 1 — Deterministic CAM skeleton

Auto-create a factual JSON structure:

```json
{
  "borrower_profile": {...},
  "group_profile": {...},
  "facility_summary": {...},
  "financial_analysis": {...},
  "conduct_analysis": {...},
  "market_intelligence": {...},
  "validation_exceptions": [...],
  "benchmark_summary": {...},
  "risk_flags": [...],
  "recommended_conditions": [...]
}
```

This must be generated only from deterministic services.

## Pass 2 — LLM narrative rendering

LLM converts the approved factual JSON into:

* executive summary
* borrower background
* industry outlook
* management assessment
* financial commentary
* risk analysis
* covenant recommendations
* approval rationale / decline rationale

### Golden rule

LLM can only write from:

* approved factual JSON
* cited source snippets
* benchmark results
* rule outputs

It should not invent facts.

---

## 8. Deterministic design: same document = same result

You explicitly asked for that. Good requirement.

To achieve it:

### Must-have controls

* temperature = 0 for any LLM transformation that remains
* fixed prompt templates with versioning
* canonical source priority order
* document hash-based caching
* parser version pinning
* model version pinning
* chunking rules fixed
* source-to-field mapping rules fixed
* narrative output schema fixed

### Best practice split

**Critical numeric extraction**
Use:

* XBRL parser
* table parser
* regex/anchor-based extractor
* rules-based statement mapper

**LLM only for**

* classifying sections
* mapping ambiguous labels to canonical labels under review
* narrative creation
* user Q&A

### Source priority example

For listed company revenue:

1. exchange-filed XBRL/financial result
2. annual report audited statement
3. borrower-uploaded statement
4. management presentation
5. analyst note
6. media/social

This prevents nondeterministic conflicts.

---

## 9. LLM orchestration design

Use LLM as a **planner/router**, not calculator.

### Suggested agents

#### 1. Intake agent

* classify case
* detect ETB or NTB
* identify borrower type: listed/unlisted/group/SPV
* identify facility type
* produce required document checklist

#### 2. Retrieval agent

* fetch internal ETB data
* fetch public disclosures
* fetch MCA enrichments
* fetch bureau/commercial profile
* fetch market/news/social data

#### 3. Validation agent

* trigger deterministic checks
* cluster exceptions
* summarize what is missing/mismatched

#### 4. Benchmark agent

* select sector pack
* select peer cohort
* run benchmark service

#### 5. CAM agent

* assemble approved factual dataset
* request narrative generation
* attach evidence citations

#### 6. Analyst chat agent

* answer questions only from approved evidence graph
* never answer from raw model memory
* cite source paragraph/table/cell

---

## 10. Analyst chat design

This should behave like a **credit analyst copilot**, not a generic chatbot.

### Analyst should be able to ask:

* why did revenue decline in FY24?
* show mismatch between annual report and uploaded provisional
* compare debtor days to peer median
* what are the top 5 red flags?
* what changed vs last CAM?
* why was this case rated lower than peer?
* show all unresolved exceptions
* explain recommendation for covenant package

### Chat response should always return

* answer
* evidence list
* affected metrics
* confidence
* links to source docs and pages
* deterministic calculation trace where numeric

### Do not allow

* free hallucinated answers
* hidden chain-of-thought
* uncited recommendations

---

## 11. ETB vs NTB flow design

## NTB flow

NTB is enrichment-heavy.

### NTB sequence

1. proposal intake
2. KYC / onboarding
3. document checklist generation
4. MCA / bureau / market / exchange enrichment
5. document extraction
6. cross-source validation
7. benchmark selection
8. policy/rules run
9. CAM draft
10. analyst review
11. approval workflow

### NTB special rules

* mandatory external validation
* deeper promoter/group checks
* mandatory mismatch resolution
* stronger document sufficiency checks
* lower reliance on behavioral banking data

---

## ETB flow

ETB is conduct-heavy.

### ETB sequence

1. identify customer and group
2. fetch internal banking data
3. fetch existing facilities/utilization/conduct
4. fetch latest financial and external validations
5. compare declared position vs actual account conduct
6. benchmark against prior internal performance
7. run enhancement/renewal/review rules
8. CAM refresh
9. analyst review
10. approval workflow

### ETB special rules

* internal transaction behavior matters a lot
* covenant compliance history matters
* utilization patterns matter
* delays, returns, overdue behavior matter
* relationship profitability and wallet share can be added

### Net effect

NTB answers: **“Can we trust and onboard this borrower?”**
ETB answers: **“Given what we know from actual behavior, should we continue/increase/reshape exposure?”**

---

## 12. Data products you should build

Build these as reusable services, not one-off scripts.

### Service 1 — Company intelligence service

* MCA
* directors
* group mapping
* listed/unlisted classification
* filings timeline

### Service 2 — Financial extraction service

* financial statement extraction
* note parsing
* line item normalization
* ratio computation

### Service 3 — Validation service

* mismatch detection
* analytical checks
* stale data checks
* exception generation

### Service 4 — Benchmark service

* peer selection
* industry pack logic
* z-score / percentile / trend flags

### Service 5 — Conduct intelligence service

* ETB account behavior
* limit utilization
* repayment trends
* covenant status

### Service 6 — CAM composer

* structured CAM JSON
* narrative rendering
* versioned output

### Service 7 — Analyst copilot

* retrieval-grounded chat
* citation-backed explanations
* recommendation traceability

---

## 13. Suggested storage design

### Operational store

Postgres

* cases
* borrowers
* documents
* extracted fields
* validation results
* benchmarks
* CAM versions
* audit logs

### Object store

S3 / Azure Blob / GCS

* source PDFs
* OCR JSON
* table extracts
* generated CAM outputs

### Search / retrieval index

OpenSearch / pgvector / both

* clause retrieval
* source chunk retrieval
* analyst Q&A grounding

### Graph layer

Neo4j or graph tables

* promoter-director-company-group relationships
* exposure links
* cross-holding structures

---

## 14. Suggested decision policy stack

Use **3-tier decision logic**.

### Tier 1 — hard rules

* KYC complete?
* mandatory docs present?
* restricted sector?
* legal entity valid?
* filing stale?
* critical mismatch unresolved?

### Tier 2 — scoring / model layer

* financial risk score
* conduct score
* governance/reputation score
* benchmark deviation score

### Tier 3 — recommendation assembly

* approve / conditional / refer / decline
* covenant package
* collateral asks
* monitoring conditions
* exception note

LLM should only narrate Tier 3 after Tier 1 and Tier 2 are locked.

---

## 15. What social/media should contribute

Do not let social data pollute the accounting engine.

Use it for:

* promoter sentiment deterioration
* labor unrest signal
* customer backlash
* regulatory attention signal
* management communication inconsistency
* event timeline enrichment

Store it in a separate risk bucket:

`reputation_event_score`

and show it as:

* supportive evidence
* early warning
* watchlist factor

not as audited truth.

---

## 16. Recommended implementation phases

## Phase 1 — deterministic CAM factory

Build first:

* document ingestion
* financial extraction
* canonical model
* validation engine
* ratio engine
* basic sector benchmark
* structured CAM JSON
* narrative rendering

This alone gives massive value.

## Phase 2 — ETB intelligence

Add:

* internal account conduct
* utilization analysis
* covenant history
* ETB-only score overlays

## Phase 3 — listed company intelligence

Add:

* exchange filings ingestion
* annual report/XBRL ingestion
* BRSR / governance overlays
* event timeline

## Phase 4 — analyst copilot

Add:

* chat Q&A
* evidence-grounded retrieval
* case comparison
* explainability views

## Phase 5 — alternative intelligence

Add:

* media/news/social signals
* reputation event graph
* early warning triggers

---

## 17. My blunt recommendation on product shape

Do **not** sell this as “an LLM that generates CAM.”

Sell it as:

**Credit Intelligence & CAM Orchestration Platform**

with 4 promises:

* **ingest all evidence**
* **validate and normalize deterministically**
* **benchmark against sector and peer set**
* **generate auditable CAM with analyst copilot**

That framing is much stronger for banks.

---

## 18. Recommended final product modules

Your product can be packaged as:

### A. Ingestion Studio

upload, classify, parse, map

### B. Validation Workbench

mismatch detection, exception queue, analyst resolution

### C. Credit Intelligence Engine

financials, conduct, benchmarks, market signals

### D. CAM Studio

draft memo, edit, compare versions, approval pack

### E. Analyst Copilot

chat, explain, trace, query

### F. Admin / Policy Console

sector packs, rules, benchmark configs, templates

---

## 19. One-line architecture summary

**Use LLM to orchestrate and explain; use deterministic engines to extract, validate, benchmark, and decide.**

That is the correct architecture for your solution.

If you want, next I’ll turn this into a **full product architecture pack** with:

* component diagram
* ETB/NTB workflow
* source catalog
* data model
* agent design
* API contracts
* CAM JSON schema
* implementation roadmap for MVP and enterprise version.

[1]: https://www.sebi.gov.in/legal/regulations/jul-2024/securities-and-exchange-board-of-india-listing-obligations-and-disclosure-requirements-regulations-2015-last-amended-on-july-10-2024-_84817.html "SEBI | Securities and Exchange Board of India (Listing Obligations and Disclosure Requirements) Regulations, 2015  [Last amended on July 10, 2024]"
[2]: https://www.nseindia.com/companies-listing/corporate-filings-application "
    Corporate Filings- Equity, Debt, MF, SME- NSE India
"
[3]: https://www.mca.gov.in/content/mca/global/hi/mca/master-data/MDS.html "मास्टर डेटा सेवाएँ V3"


Yes. For your solution, define the document model separately for **NTB** and **ETB**, then treat Postman as a **mock external-source layer** for MCA, bureau, market, exchange filings, etc. That lets you design the platform now and swap real APIs later without changing the core workflow. RBI KYC rules govern onboarding/KYC, MCA provides company master lookup services, and for listed entities NSE exposes annual reports, financial results, governance, BRSR, ratings, and default-payment related filings. ([Reserve Bank of India][1])

## 1) Document sets you need

Think in 3 buckets:

1. **Mandatory borrower-submitted documents**
2. **Externally fetched/reference documents**
3. **Bank-internal ETB documents/data**

---

## 2) NTB document checklist

NTB is heavier because you do not yet trust the borrower relationship history. RBI KYC requirements make onboarding documents unavoidable, while MCA and external filings become critical validation sources. ([Reserve Bank of India][1])

### A. Entity / KYC / constitutional documents

These are the base onboarding documents for NTB.

| Document                       | Mandatory   |               Primary source | Used for                        |
| ------------------------------ | ----------- | ---------------------------: | ------------------------------- |
| Certificate of Incorporation   | Yes         |               Borrower / MCA | legal existence                 |
| PAN of company                 | Yes         |                     Borrower | tax identity / key lookup       |
| CIN                            | Yes         |               MCA / borrower | company matching                |
| GST registration               | Usually yes |                     Borrower | tax identity / turnover support |
| MOA                            | Yes         |    Borrower / MCA filing set | objects / permitted business    |
| AOA                            | Yes         |    Borrower / MCA filing set | governance / borrowing powers   |
| Registered office proof        | Yes         |               Borrower / MCA | address validation              |
| Board resolution for borrowing | Yes         |                     Borrower | authority to borrow             |
| Authorized signatory proof     | Yes         |                     Borrower | execution control               |
| UBO / shareholding declaration | Yes         |                     Borrower | ownership and control           |
| Director / promoter KYC        | Yes         | Borrower / MCA director data | management validation           |

### B. Promoter / director / group documents

| Document                         | Mandatory          | Primary source | Used for              |
| -------------------------------- | ------------------ | -------------: | --------------------- |
| PAN of promoters/directors       | Yes                |       Borrower | KYC / linking         |
| Aadhaar / OVD as applicable      | As per bank policy |       Borrower | KYC                   |
| DIN details                      | Yes                |            MCA | director validation   |
| Net worth statements             | Usually yes        |       Borrower | sponsor strength      |
| Personal ITR / income proof      | Often required     |       Borrower | promoter capacity     |
| Group structure chart            | Yes                |       Borrower | group exposure        |
| List of associate/group entities | Yes                | Borrower / MCA | related-party mapping |

### C. Financial documents

| Document                                 | Mandatory           |            Primary source | Used for                        |
| ---------------------------------------- | ------------------- | ------------------------: | ------------------------------- |
| Audited financial statements for 3 years | Yes                 |                  Borrower | core financial analysis         |
| Latest provisional / management accounts | Usually yes         |                  Borrower | current performance             |
| Schedules and notes to accounts          | Yes                 |                  Borrower | validation and deep analysis    |
| Auditor report                           | Yes                 |                  Borrower | qualification / emphasis checks |
| Cash-flow statement                      | Yes if available    |                  Borrower | DSCR / cash generation          |
| Consolidated financials                  | If group applicable |                  Borrower | group risk                      |
| Segment reporting                        | If applicable       | Borrower / listed filings | business risk                   |

### D. Banking / debt / exposure documents

| Document                                      | Mandatory  |           Primary source | Used for                |
| --------------------------------------------- | ---------- | -----------------------: | ----------------------- |
| Bank statements 6–12 months                   | Yes        |                 Borrower | cash-flow behavior      |
| Existing sanction letters                     | Yes        |                 Borrower | debt terms              |
| Repayment schedule of existing debt           | Yes        |                 Borrower | debt servicing          |
| Working capital statements / stock statements | If WC case |                 Borrower | drawing power / cycle   |
| List of banking arrangements                  | Yes        |                 Borrower | lender exposure mapping |
| Details of contingent liabilities             | Yes        | Borrower / annual report | off-balance risk        |

### E. Business / operational documents

| Document                                | Mandatory              | Primary source | Used for               |
| --------------------------------------- | ---------------------- | -------------: | ---------------------- |
| Detailed loan request note              | Yes                    |  Borrower / RM | purpose and structure  |
| Business profile / company presentation | Yes                    |       Borrower | business understanding |
| Project report / TEV / DPR              | For term/project loans |       Borrower | project viability      |
| Order book / customer contracts         | Sector dependent       |       Borrower | revenue visibility     |
| Top supplier / customer list            | Usually yes            |       Borrower | concentration risk     |
| Capex plan / utilization plan           | If capex case          |       Borrower | end-use                |
| CMA data / projected financials         | Usually yes            |       Borrower | forward analysis       |

### F. Collateral / security documents

| Document                        | Mandatory if secured |        Primary source | Used for         |
| ------------------------------- | -------------------- | --------------------: | ---------------- |
| Title deed / ownership proof    | Yes                  |              Borrower | ownership        |
| Search report / legal opinion   | Yes                  |                Lawyer | enforceability   |
| Valuation report                | Yes                  |                Valuer | collateral value |
| Encumbrance details             | Yes                  | Legal / public record | clean title      |
| Insurance copy                  | Often required       |              Borrower | asset protection |
| NOC / permissions if applicable | Case based           |              Borrower | legal clearance  |

### G. External validation/reference documents for NTB

These may come via API later, but for now mock them in Postman.

| External doc/data                   | Source type                            | Why needed                                  |
| ----------------------------------- | -------------------------------------- | ------------------------------------------- |
| Company master                      | MCA                                    | company identity, status, registered office |
| Director master / signatory mapping | MCA                                    | control and linkage                         |
| Charges / filing history            | MCA                                    | prior borrowings / security clues           |
| Commercial bureau report            | CIC / bureau                           | exposure, delinquency, lender view          |
| Credit rating report                | Rating agency / exchange               | external risk opinion                       |
| Listed financial results            | NSE/BSE                                | validation of submitted numbers             |
| Annual report                       | Exchange / company website             | audited reference                           |
| Governance filings                  | NSE/BSE                                | listed-company governance checks            |
| BRSR / sustainability report        | NSE/BSE for applicable listed entities | ESG / governance context                    |
| Default-payment / debt disclosures  | NSE                                    | stress indicators                           |

NSE’s corporate filing sections explicitly include annual reports, financial results, BRSR, corporate governance, credit rating details, and default-payment details for listed entities. ([NSE India][2])

---

## 3) ETB document checklist

ETB is lighter on onboarding because the bank already has customer records and behavior history, though KYC updates may still be needed depending on status/change. RBI’s KYC framework and 2025 FAQ/update context support the distinction between onboarding and updates. ([Reserve Bank of India][1])

### A. ETB mandatory refresh documents

| Document                                    | Mandatory               |      Primary source | Used for                |
| ------------------------------------------- | ----------------------- | ------------------: | ----------------------- |
| Latest audited financials                   | Yes                     |            Borrower | annual review / renewal |
| Latest provisional financials               | Usually yes             |            Borrower | current health          |
| Latest GST / sales evidence if needed       | Often                   |  Borrower / fetched | revenue validation      |
| Updated sanction request / enhancement note | Yes                     |       RM / borrower | case objective          |
| Latest stock/book debt statements           | If WC                   | Borrower / internal | WC renewal              |
| Updated debt schedule                       | Yes                     | Borrower / internal | leverage                |
| Fresh collateral valuation / legal review   | As per policy / vintage |     Valuer / lawyer | security adequacy       |
| Updated group exposure declaration          | Usually yes             |            Borrower | group risk              |
| Updated board resolution if required        | Case based              |            Borrower | authority               |
| KYC update documents                        | Only if due / changed   |     Bank + borrower | compliance              |

### B. ETB internal bank data — these are critical

This is where ETB is materially different.

| Internal ETB record           | Source                 | Used for                        |
| ----------------------------- | ---------------------- | ------------------------------- |
| Existing account conduct      | Core banking           | behavior analysis               |
| Repayment history             | Loan management system | delinquency / discipline        |
| Limit utilization history     | LOS/LMS                | WC usage pattern                |
| Cheque return / bounce data   | Core banking           | stress signal                   |
| Covenant compliance history   | Credit monitoring      | post-sanction discipline        |
| Past CAMs / review memos      | DMS / credit system    | change analysis                 |
| Exception approvals / waivers | Credit system          | policy deviations               |
| Profitability / wallet share  | Internal MIS           | relationship context            |
| Transaction turnover trends   | Core banking           | ETB conduct vs declared revenue |

### C. ETB external refresh/reference documents

Even for ETB, you still need periodic external checks.

| External doc/data                | Source type              | Why needed                 |
| -------------------------------- | ------------------------ | -------------------------- |
| Fresh MCA company status         | MCA                      | ensure no status changes   |
| Fresh bureau/commercial report   | CIC / bureau             | new external liabilities   |
| Updated listed filings if listed | NSE/BSE                  | validate latest financials |
| Market/news/event scan           | public sources           | event-driven risk          |
| Latest rating action             | rating agency / exchange | downgrade signal           |

---

## 4) Difference between NTB and ETB in one view

| Area                    | NTB                             | ETB                                         |
| ----------------------- | ------------------------------- | ------------------------------------------- |
| KYC package             | Full                            | refresh / delta only                        |
| Company onboarding docs | Full set                        | mostly existing, update only                |
| External validation     | heavy                           | medium but still necessary                  |
| Internal conduct data   | absent                          | major input                                 |
| Prior banking behavior  | unavailable                     | highly valuable                             |
| CAM emphasis            | trust + onboarding + validation | behavior + renewal/enhancement + exceptions |

---

## 5) Listed vs unlisted document additions

### For listed corporates

Add these as standard reference inputs because listed disclosures are richer and independently filed.

| Document/data                                         | Source                  |
| ----------------------------------------------------- | ----------------------- |
| Quarterly financial results                           | NSE/BSE                 |
| Annual report                                         | NSE/BSE / company site  |
| XBRL financials where available                       | exchange                |
| Corporate governance filings                          | NSE/BSE                 |
| Credit rating disclosures                             | NSE                     |
| Default payment details / debt servicing disclosures  | NSE                     |
| BRSR / BRSR Core related disclosures where applicable | NSE/BSE / annual report |

SEBI’s listed-entity disclosure framework and NSE’s corporate filing utilities support these document classes for listed names. ([Securities and Exchange Board of India][3])

### For unlisted/private corporates

Depend more on these:

| Document/data                           | Source                         |
| --------------------------------------- | ------------------------------ |
| Borrower-submitted audited financials   | borrower                       |
| MCA master and director records         | MCA                            |
| Charge / filing history                 | MCA                            |
| Bureau/commercial report                | CIC / bureau                   |
| Bank statements                         | borrower                       |
| GST / tax proofs as available to lender | borrower / consent-based fetch |
| Group structure and promoter net worth  | borrower                       |

MCA’s master-data services are especially important for private/unlisted entities because they give company/LLP and director lookup capability. ([Ministry of Corporate Affairs][4])

---

## 6) How to handle “no external API now — Postman as source”

This is the correct temporary design.

Do **not** wire your platform directly to MCA/NSE/bureau-specific logic at first. Instead create an **External Source Adapter Layer** and expose every source through your own standard contract. Postman mocks can stand in behind those contracts until real integrations exist.

### Recommended mock sources in Postman

Create one mock endpoint per source family:

* `/external/mca/company-master`
* `/external/mca/director-master`
* `/external/mca/charges`
* `/external/bureau/commercial-report`
* `/external/exchange/financial-results`
* `/external/exchange/annual-report-metadata`
* `/external/exchange/governance-filings`
* `/external/market/news-sentiment`
* `/external/social/reputation-signals`
* `/external/gst/turnover-summary`
* `/external/rating/latest-action`

### Your internal platform should only know this:

```json
{
  "source": "mca",
  "record_type": "company_master",
  "entity_id": "PAN/CIN",
  "as_of_date": "2026-03-13",
  "payload": {...},
  "source_status": "success",
  "evidence_id": "SRC12345"
}
```

That way:

* today: Postman mock returns payload
* later: real API returns same payload shape

No core workflow changes.

---

## 7) Minimum MVP document scope

If you want the fastest usable MVP for CAM automation, start with this subset.

### NTB MVP documents

* PAN
* Certificate of Incorporation
* CIN
* MOA/AOA
* Board resolution
* 3 years audited financials
* latest provisional
* bank statements
* existing debt schedule
* group structure
* promoter/director KYC
* collateral docs
* project note / request note
* MCA company + director + charges mock
* bureau mock
* listed filings mock if listed

### ETB MVP documents

* latest audited financials
* latest provisional
* request/enhancement note
* stock statements if WC
* updated debt schedule
* fresh collateral valuation if needed
* KYC update if changed
* internal conduct history
* prior CAM/review memo
* exception/covenant history
* MCA refresh mock
* bureau refresh mock
* listed filing refresh mock if listed

---

## 8) Best way to configure this in your product

Create a **document policy matrix**:

| Case Type | Borrower Type | Facility Type | Mandatory docs | Optional docs | External checks                      |
| --------- | ------------- | ------------- | -------------- | ------------- | ------------------------------------ |
| NTB       | Listed        | WC            | config-driven  | config-driven | MCA + exchange + bureau              |
| NTB       | Unlisted      | TL            | config-driven  | config-driven | MCA + bureau                         |
| ETB       | Listed        | Renewal       | config-driven  | config-driven | internal + exchange + bureau refresh |
| ETB       | Unlisted      | Enhancement   | config-driven  | config-driven | internal + MCA + bureau refresh      |

This is the right design because document requirements will vary by:

* ETB vs NTB
* listed vs unlisted
* working capital vs term loan vs project finance
* secured vs unsecured
* sector policy

---

## 9) My recommendation for your architecture

Build these 4 stores:

1. **Document Registry**
   what was submitted/uploaded

2. **Evidence Registry**
   what came from external/mock sources

3. **Validation Registry**
   mismatches, stale data, unresolved exceptions

4. **CAM Assembly Store**
   the approved factual dataset used by the LLM

That will keep the system deterministic and audit-friendly.

---

## 10) Direct answer

For **NTB**, collect the full onboarding, constitutional, financial, banking, business, collateral, and external-validation document set.

For **ETB**, collect updated financial and request documents, but rely heavily on internal conduct, previous CAMs, covenant history, utilization, and repayment behavior, with only delta KYC and refresh external checks.

And yes, **Postman can absolutely behave as your external source layer** for now — that is the right way to de-risk the architecture before real API integrations.

Next, I can turn this into a **product-ready document matrix in Excel/CSV format** with columns like:
`case_type, borrower_type, facility_type, document_name, mandatory_flag, source_type, validation_rule, mock_api_endpoint`.

[1]: https://www.rbi.org.in/CommonPerson/english/scripts/notification.aspx?id=2607&utm_source=chatgpt.com "Know Your Customer (KYC) Direction, 2016"
[2]: https://www.nseindia.com/companies-listing/corporate-filings-annual-reports?utm_source=chatgpt.com "Corporate Filings Annual Reports - Equity, SME"
[3]: https://www.sebi.gov.in/sebi_data/faqfiles/apr-2025/1745399101865.pdf?utm_source=chatgpt.com "FAQs for LODR Regulations"
[4]: https://www.mca.gov.in/content/mca/global/hi/mca/master-data/MDS.html?utm_source=chatgpt.com "https://www.mca.gov.in/content/mca/global/hi/mca/m..."


Yes — **you can define this as a multi-agent system**, but the **best design is not a swarm of free-running agents**. For CAM, the strongest architecture is a **supervisor-led graph** where agents orchestrate work, while all financial extraction, validations, calculations, and policy checks run in deterministic services. LangGraph is explicitly designed for **stateful, durable, human-in-the-loop agent workflows**, and Temporal is built around **durable workflow execution with deterministic replay**, which is exactly what you want for reproducible credit processing. OpenAI’s Structured Outputs are useful for forcing the LLM to emit fixed JSON schemas instead of free text. ([LangChain Docs][1])

## Best design

Use a **3-layer design**:

**Layer 1: deterministic truth layer**

* document ingestion
* OCR / table extraction
* XBRL / statement parsing
* canonical financial mapping
* cross-source validation
* benchmark engine
* rules / policy engine
* CAM facts JSON

**Layer 2: orchestration layer**

* supervisor agent
* ETB/NTB routing
* listed/unlisted routing
* task sequencing
* retry / timeout / human-review routing

**Layer 3: analyst experience layer**

* CAM generator
* analyst copilot chat
* exception workbench
* evidence explorer
* approval pack

That split is the right design because RBI KYC obligations and external evidence checks are mandatory process controls, while listed-company evidence is materially richer via NSE corporate filings such as annual reports, financial results, governance disclosures, ratings, and default-payment details; MCA master data is a core source for company/director lookup. ([Reserve Bank of India][2])

## Recommended multi-agent pattern

Do **not** create 15 autonomous agents.
Use **1 supervisor + 5 specialist agents + deterministic tools**.

### 1. Supervisor agent

Owns the case state and decides:

* ETB or NTB
* listed or unlisted
* working capital / term loan / project / renewal
* what evidence is mandatory
* whether the case can proceed or must pause for missing data

### 2. Intake and source agent

* classifies incoming documents
* calls Postman mock endpoints
* fetches MCA / bureau / exchange / market payloads
* creates source registry entries

### 3. Validation agent

* runs mismatch checks
* identifies stale filings
* compares borrower-submitted data with MCA / exchange / bureau / internal conduct
* raises exceptions

### 4. Benchmark agent

* selects sector pack
* selects peer cohort
* applies industry benchmarks
* produces benchmark deltas and outlier flags

### 5. CAM assembly agent

* consumes only approved factual JSON
* drafts CAM sections
* produces memo variants
* attaches citations and exception summaries

### 6. Analyst copilot agent

* answers queries only from evidence graph
* cites documents, pages, fields, and calculation traces
* does not invent numbers

LangGraph’s subgraphs and checkpointed state make this pattern natural, while Temporal gives you durable execution, retries, and replay-safe workflow control for production processing. ([LangChain Docs][3])

## Best implementation approach

The best implementation is:

**LangGraph for agent graph**
**Temporal for durable business workflow**
**Python for AI/data services**
**Java for bank-grade deterministic rule services if your org is Java-heavy**

That hybrid is stronger than trying to make LangGraph do everything or trying to make Temporal do all agent reasoning.

### Why this split works

* **LangGraph** is strong for stateful multi-agent reasoning, subgraphs, memory, and human-in-the-loop review. ([LangChain Docs][1])
* **Temporal** is strong for long-running, replayable, fault-tolerant workflows and deterministic execution semantics. ([docs.temporal.io][4])
* **Structured Outputs** help force the model to emit exact schemas for CAM facts, validation summaries, and analyst response envelopes. ([OpenAI][5])

## My recommended tech stack

### Core backend

* **Python FastAPI** for orchestration APIs, document services, and agent tooling
* **LangGraph** for multi-agent orchestration
* **Temporal** for durable workflows
* **PostgreSQL** as system of record
* **Redis** for short-lived caching / rate / session support
* **Object storage** for files and parsed artifacts
* **Kafka** if you want event streaming between ingestion, validation, and monitoring services

Kafka’s official docs position it as an event-streaming platform for high-performance pipelines and mission-critical applications, which fits ingestion/event propagation well. PostgreSQL supports native full-text search and GIN indexes, which are useful for evidence retrieval and internal search even before you add vector search. ([Apache Kafka][6])

### AI / LLM layer

* **OpenAI Responses API with Structured Outputs** for controlled JSON generation
* embeddings/vector retrieval only for analyst Q&A and evidence lookup
* temperature 0 for all production CAM drafting and structured transforms

### Document and parsing layer

* OCR service
* table extraction service
* XBRL parser for listed entities
* deterministic statement mapper
* canonical line-item normalization engine

### Rules and analytics

* policy engine
* benchmark engine
* ratio engine
* validation engine
* exception engine

### UI

* React frontend
* analyst workbench
* evidence diff viewer
* CAM studio
* chat copilot
* workflow state timeline

## Best data design

Use **four stores**, not one.

### 1. Source registry

Stores every source artifact:

* borrower upload
* Postman mock response
* internal ETB data
* exchange filing
* MCA payload

### 2. Canonical lending model

Stores normalized entities:

* borrower
* group
* promoters/directors
* financial statements
* facilities
* collateral
* conduct
* market signals
* validation exceptions
* benchmark results

### 3. Evidence graph

Maps every CAM sentence or answer back to:

* document
* page
* table
* source payload
* calculation step

### 4. Audit log

Stores:

* model version
* parser version
* prompt version
* rule version
* workflow version
* who approved what

That is what makes the system deterministic, explainable, and regulator-friendly.

## ETB and NTB in multi-agent design

This should be a **first-class route** in the supervisor graph.

### NTB path

* full KYC/doc checklist
* MCA and bureau mandatory
* stronger cross-source validation
* lower trust in borrower-submitted facts
* heavier promoter/group checks

### ETB path

* internal conduct and limit utilization mandatory
* prior CAM and covenant history included
* delta-KYC
* renewal/enhancement logic
* stronger behavioral overlays

RBI’s KYC framework supports the distinction between onboarding requirements and ongoing KYC updates, while MCA/NSE sources support the external reference layer for unlisted and listed names respectively. ([Reserve Bank of India][2])

## How Postman fits right now

Yes — use **Postman as your external source simulation layer**.

Do it through an **adapter pattern**:

* `source-mca`
* `source-bureau`
* `source-exchange`
* `source-market`
* `source-social`
* `source-regulatory`

Each adapter returns the same internal schema whether the backend is:

* Postman mock today
* real API tomorrow
* file drop next month

That keeps the rest of the system unchanged.

## Recommended implementation blueprint

### Phase 1: deterministic CAM factory

Build first:

* document registry
* source adapters with Postman
* parser / OCR / table extraction
* canonical financial mapper
* validation engine
* benchmark engine
* CAM facts JSON
* CAM draft generation

### Phase 2: ETB intelligence

Add:

* internal conduct feeds
* covenant history
* utilization trends
* prior CAM comparison

### Phase 3: analyst copilot

Add:

* evidence-grounded chat
* query tracing
* exception explainability
* change analysis vs prior CAM

### Phase 4: production hardening

Add:

* Temporal retries / replay
* Kafka eventing
* observability
* human approvals
* version governance

## My blunt recommendation

For your case, the **best design** is:

**Supervisor-led multi-agent graph + deterministic financial/rules services + evidence graph + controlled LLM output**

Not:

* one giant agent
* pure RAG chatbot
* pure workflow engine
* pure LLM memo writer

## Final stack recommendation

If you want the strongest practical stack for your product:

* **Frontend:** React
* **API layer:** FastAPI
* **Agent orchestration:** LangGraph
* **Durable workflow/orchestration:** Temporal
* **Database:** PostgreSQL
* **Cache:** Redis
* **Object store:** S3/Azure Blob/GCS
* **Event backbone:** Kafka
* **LLM:** OpenAI Responses API + Structured Outputs
* **Search:** PostgreSQL FTS first, vector search where needed
* **Mock integrations:** Postman adapters
* **Observability:** OpenTelemetry + Prometheus/Grafana

That is the stack I would choose for a serious bank-grade CAM intelligence platform. ([OpenAI][5])

Next, I can convert this into a **full component architecture with agent-by-agent responsibilities, APIs, DB schema, and ETB/NTB sequence diagrams**.

[1]: https://docs.langchain.com/oss/python/langgraph/overview?utm_source=chatgpt.com "LangGraph overview - Docs by LangChain"
[2]: https://www.rbi.org.in/CommonPerson/english/scripts/notification.aspx?id=2607&utm_source=chatgpt.com "Reserve Bank of India (Know Your Customer (KYC ..."
[3]: https://docs.langchain.com/oss/python/langgraph/use-subgraphs?utm_source=chatgpt.com "Subgraphs - Docs by LangChain"
[4]: https://docs.temporal.io/workflows?utm_source=chatgpt.com "Temporal Workflow | Temporal Platform Documentation"
[5]: https://openai.com/index/introducing-structured-outputs-in-the-api/?utm_source=chatgpt.com "Introducing Structured Outputs in the API"
[6]: https://kafka.apache.org/?utm_source=chatgpt.com "Apache Kafka"


Yes. For your CAM platform, **deterministic algorithm** should mean:

**same inputs + same source priority + same rules/version + same workflow = same outputs**

Not just same LLM prompt.

The best design is to make the system deterministic at **five levels**: workflow, extraction, normalization, validation, and memo generation. Temporal explicitly requires deterministic workflow behavior for replay, DMN is meant for precise business-rule specification, and OpenAI Structured Outputs is useful for forcing fixed JSON schemas rather than free-form text. ([Temporal Docs][1])

## 1) The deterministic core is not one algorithm

It is a **pipeline of deterministic algorithms**:

1. **File fingerprinting**
2. **Source-priority merge**
3. **Canonical line-item mapping**
4. **Validation rule execution**
5. **Benchmark calculation**
6. **Decision-table evaluation**
7. **CAM fact-pack generation**
8. **Schema-bound narrative rendering**

That is the right shape for credit memo automation because it separates numeric truth from narrative generation. ([OMG][2])

## 2) Best deterministic design for your use case

### A. Workflow determinism

Use **Temporal** for the case workflow itself:

* intake
* fetch sources
* parse docs
* run validations
* run benchmark
* generate fact pack
* generate CAM
* route to analyst review

Temporal records workflow history and requires deterministic replay, which is exactly what you want for regulated credit processing. ([Temporal Docs][1])

### B. Decision determinism

Use **DMN decision tables** for:

* ETB vs NTB branching
* listed vs unlisted branching
* mandatory document policy
* sector policy pack
* approval matrix
* risk flag logic
* exception severity

DMN exists specifically for precise, repeatable business decisions and business rules. ([OMG][2])

### C. Extraction determinism

Use parser-first extraction:

* XBRL parser where available
* PDF text parser
* table extractor
* OCR only when needed

Apache Tika is a stable document parsing toolkit for extracting text and metadata from many file types, which is useful as a deterministic first-pass parser. ([tika.apache.org][3])

### D. Output determinism

Use **Structured Outputs** for any LLM-produced JSON:

* CAM facts
* exception summary
* benchmark narrative
* analyst response envelope

That prevents schema drift and invalid output shapes. ([OpenAI Developers][4])

---

## 3) The actual deterministic algorithms you should implement

## Algorithm 1: file identity and version lock

For every input file and external payload, store:

* `sha256(file_bytes)`
* parser version
* OCR version
* mapping version
* rule-pack version
* benchmark-pack version
* prompt version
* workflow version

This makes every run reproducible. If any version changes, output may change by design; otherwise it should not.

### Output

```json
{
  "artifact_hash": "sha256...",
  "parser_version": "fin-parser-1.3.2",
  "rule_pack_version": "sector-mfg-v4",
  "workflow_version": "cam-flow-v7"
}
```

## Algorithm 2: source-priority conflict resolver

When the same field comes from multiple sources, do **not** let the LLM decide. Use a fixed source precedence.

Example for listed company revenue:

1. exchange/XBRL
2. audited annual report
3. borrower-uploaded audited statement
4. provisional/MIS
5. management presentation
6. news/social

Example for private company debt:

1. audited statements
2. bureau/commercial report
3. MCA charge-related data
4. borrower declaration
5. media/news

### Deterministic rule

```text
selected_value(field) = first non-null value from ordered trusted sources
```

If two trusted sources differ beyond tolerance, create exception instead of guessing.

## Algorithm 3: canonical line-item mapping

Incoming financial labels vary a lot. Map them to a fixed internal chart of accounts using a versioned mapping dictionary.

Example:

* “Revenue from operations”
* “Net sales”
* “Operating income”

All map to:

* `revenue_operating`

### Deterministic mapping order

1. exact label match
2. normalized label match
3. section-aware rule
4. approved synonym dictionary
5. unresolved → analyst queue

Do **not** use free LLM guessing as the default. Use LLM only as a fallback suggestion, never as final truth.

## Algorithm 4: ratio engine

All ratios must be pure deterministic functions.

Examples:

* `debt_to_ebitda = total_debt / ebitda`
* `current_ratio = current_assets / current_liabilities`
* `icr = ebit / finance_cost`
* `dscr = cash_available_for_debt_service / debt_service`

Rules:

* fixed rounding policy
* fixed null-handling policy
* divide-by-zero policy
* consolidated vs standalone precedence rule
* fiscal-period alignment rule

### Example

```text
if denominator == 0:
   return NULL and raise EXC_RATIO_DIV_ZERO
else:
   return round(numerator / denominator, 2)
```

## Algorithm 5: validation engine

This is rule-driven and deterministic.

### Types of validations

* structural
* cross-source
* mathematical
* temporal
* policy
* sector-specific

### Example checks

* balance sheet balances
* PAT consistency
* debt mismatch between uploaded report and bureau
* director mismatch vs MCA
* stale annual filing
* missing mandatory document for NTB

### Deterministic result

Each validation produces:

* code
* severity
* expected value
* observed value
* evidence source
* case status impact

## Algorithm 6: benchmark engine

Industry benchmarking should be statistical, not narrative.

Use:

* median
* percentile band
* z-score where sample size is adequate
* trend comparison against own history
* peer-bucket comparison by sector/subsector/size/listed status

### Example

```text
benchmark_delta = borrower_metric - peer_median
status =
   if borrower_metric > p75 then "worse_than_peer"
   elif borrower_metric < p25 then "better_than_peer"
   else "within_band"
```

This is deterministic if:

* peer cohort rules are fixed
* peer dataset snapshot is versioned
* percentile method is fixed

## Algorithm 7: policy and recommendation engine

This should be **decision tables**, not prompt logic.

Examples:

* mandatory docs by case type
* exception severity
* committee routing
* sector red flags
* covenant recommendations
* ETB enhancement logic
* NTB onboarding blocks

DMN is the right fit here because decision tables are executable and auditable. ([OMG][2])

## Algorithm 8: CAM fact-pack builder

Before LLM writes anything, build a deterministic JSON fact pack.

Example:

```json
{
  "case_type": "NTB",
  "borrower_type": "listed",
  "sector": "manufacturing",
  "financial_summary": {...},
  "validation_exceptions": [...],
  "benchmark_summary": {...},
  "policy_outcome": {...},
  "recommendation_inputs": {...}
}
```

The LLM then only turns this into memo language.

## Algorithm 9: schema-bound memo rendering

Use LLM with:

* temperature 0
* fixed prompt template
* fixed section order
* Structured Outputs for intermediate JSON
* citations only from approved evidence

Structured Outputs helps ensure JSON responses conform to schema rather than drifting structurally. ([OpenAI Developers][4])

---

## 4) Best implementation pattern

### Deterministic stack

* **Temporal**: workflow determinism and replay
* **DMN engine**: decision logic
* **PostgreSQL**: facts, versions, audit
* **Apache Tika + table parser**: document extraction baseline
* **Python services**: extraction, validation, benchmark
* **OpenAI Structured Outputs**: schema-bound memo and chat responses
* **LangGraph** only if you want multi-agent coordination on top, but not for numeric truth

That split gives you both **repeatability** and **flexibility**. ([Temporal Docs][1])

---

## 5) What you must freeze to guarantee same result

You will only get true determinism if these are frozen:

* source payload snapshot
* document bytes/hash
* source precedence policy
* parser version
* OCR version
* canonical mapping version
* rule-pack version
* benchmark dataset version
* workflow version
* prompt version
* model version

If any one changes, output can change. That is acceptable, but it must be version-visible.

---

## 6) ETB and NTB deterministic branching

Use a decision table like this:

### Entry decision

Inputs:

* `customer_relationship`
* `listed_status`
* `facility_type`
* `secured_flag`
* `sector`
* `renewal_or_new`

Outputs:

* `case_flow`
* `mandatory_docs_pack`
* `validation_pack`
* `benchmark_pack`
* `approval_matrix`

### Example

```text
if customer_relationship = ETB and renewal_or_new = renewal
   then use ETB_RENEWAL_PACK

if customer_relationship = NTB and listed_status = listed
   then use NTB_LISTED_PACK
```

This is deterministic, transparent, and easy to govern.

---

## 7) My blunt recommendation

For your solution, the **best deterministic algorithm strategy** is:

**Temporal workflow + DMN decision tables + versioned parser/mapping engine + statistical benchmark engine + Structured-Output LLM only for final language**

Do **not** try to make the LLM itself be deterministic truth engine.
That will fail under audit.

### The right split

* **Deterministic engines** decide facts
* **LLM** explains facts

That is the architecture I would use for a serious bank-grade CAM platform.

Next, I can turn this into a **full deterministic algorithm blueprint** with:

* decision-table examples
* DB schema
* versioning model
* ETB/NTB pseudo-code
* sample fact-pack JSON
* CAM generation flow.

[1]: https://docs.temporal.io/workflows?utm_source=chatgpt.com "Temporal Workflow | Temporal Platform Documentation"
[2]: https://www.omg.org/dmn/?utm_source=chatgpt.com "Decision Model and Notation™ (DMN™)"
[3]: https://tika.apache.org/?utm_source=chatgpt.com "Apache Tika – Apache Tika"
[4]: https://developers.openai.com/api/docs/guides/structured-outputs/?utm_source=chatgpt.com "Structured model outputs | OpenAI API"



Yes. For a **complete POC**, you should **not wait for real external APIs**.
You can build it in 3 source buckets:

1. **real public documents** for listed companies
2. **synthetic / masked documents** for private and NTB scenarios
3. **Postman mock APIs** for MCA, bureau, market, social, regulatory enrichments

That is the fastest and cleanest path.

## 1. Best POC data strategy

Use this rule:

**Listed corporate POC = mostly real public-source data**
**Private corporate POC = borrower-uploaded docs + mocked external responses**
**ETB POC = internal-bank sample data + mocked external refresh**
**NTB POC = full doc pack + mocked external checks**

This works because public listed companies in India already have a lot of usable material on NSE, including annual reports, financial results, governance filings, ratings, default-payment details, and BRSR-related disclosures. MCA also provides company master lookup services, and RBI KYC directions remain the base reference for onboarding/KYC design. ([NSE India][1])

---

## 2. Where to get data for the POC

### A. Listed company data — use real public sources

For listed companies, use real documents from:

* **NSE corporate filings**
* **Annual reports**
* **Quarterly / annual financial results**
* **Corporate governance filings**
* **Credit rating details**
* **Default payment details**
* **BRSR / sustainability filings**

NSE explicitly exposes these filing categories on its corporate filings pages. ([NSE India][1])

### B. MCA / company master data

For company identity and enrichment, use:

* company master
* CIN
* company status
* registered office
* directors / designated partners
* charge-related / filing-related mock payloads

MCA master-data services are the right official reference point for company/LLP and director lookup, and data.gov.in also lists company master data fields like CIN, company status, registration date, state, and capital information. ([Data.gov.in][2])

### C. KYC / onboarding reference

For POC document requirements and flow design, use RBI KYC directions as the policy baseline. RBI’s KYC Master Direction is the right official source for onboarding and updation logic, and RBI’s 2025 FAQ/update context supports lighter refresh logic for existing relationships. ([Reserve Bank of India][3])

### D. Sustainability / governance overlays for listed entities

For listed corporates, if you want governance / ESG overlays in CAM, use BRSR/BRSR Core references from NSE and SEBI. ([NSE India][1])

---

## 3. What documents you need for a complete POC

## Case 1: NTB listed corporate

Use **real public documents + borrower pack + mock external APIs**.

### Borrower / uploaded docs

* loan request note
* audited financial statements for 3 years
* latest provisional financials
* bank statements
* existing debt schedule
* board resolution
* shareholding / group structure
* collateral docs if secured
* project report / utilization note if term loan

### Public real docs

* annual reports from NSE
* quarterly / annual financial results from NSE
* governance filings
* rating disclosures
* default-payment details if available
* BRSR if applicable

### Mock external APIs in Postman

* MCA company master
* MCA directors
* MCA charges
* bureau commercial report
* GST turnover summary
* market/news sentiment
* social / reputational flags

---

## Case 2: NTB private / unlisted corporate

For private companies, you will not get the same richness from exchanges, so do this:

### Use real or masked borrower docs

* certificate of incorporation
* PAN
* GST certificate
* MOA / AOA
* audited financial statements
* provisional financials
* bank statements
* debt schedule
* stock statements if WC
* promoter KYC
* net worth statement
* group structure
* collateral docs

### Use mock external APIs

* MCA company master
* MCA directors
* MCA charges
* bureau commercial report
* regulatory watchlist response
* market / media / social signal response

For POC, this is enough. You do **not** need live production integrations.

---

## Case 3: ETB listed corporate

Use:

### Internal ETB sample data

* account conduct
* facility utilization
* repayment history
* covenant compliance history
* previous CAM / annual review memo
* exception history
* transaction turnover trend

### Updated borrower docs

* latest audited financials
* latest provisional financials
* updated debt schedule
* fresh request note / enhancement note
* updated collateral valuation if required

### Public real docs

* NSE filings
* annual report
* latest results
* rating action
* governance updates

### Mock external APIs

* MCA refresh
* bureau refresh
* market/news/sentiment refresh

---

## Case 4: ETB private / unlisted corporate

Use:

### Internal ETB sample data

* account conduct
* limit utilization
* repayment behavior
* prior CAM
* covenant and exception history

### Borrower docs

* latest audited financials
* provisional financials
* updated debt schedule
* stock statements
* request note
* updated collateral docs if applicable

### Mock external APIs

* MCA
* bureau
* GST summary
* market/social risk flags

---

## 4. What should be real vs mocked in the POC

This is the best split.

| Source type                                | POC approach               |
| ------------------------------------------ | -------------------------- |
| Annual reports                             | Real                       |
| NSE financial results                      | Real                       |
| NSE governance / ratings / default details | Real                       |
| Borrower-uploaded financials               | Real, masked, or synthetic |
| MCA responses                              | Mock in Postman            |
| Bureau/commercial credit report            | Mock in Postman            |
| GST summary                                | Mock in Postman            |
| Social/media sentiment                     | Mock in Postman first      |
| Internal ETB account conduct               | Synthetic but realistic    |

Why this is the right move: it gives you **real document ingestion and real validation logic**, while keeping hard-to-access external integrations simulated.

---

## 5. How many companies/documents you need for a strong POC

Do not overbuild.
For a serious demo, this is enough:

### Recommended POC corpus

* **2 listed corporates**

  * 1 strong borrower
  * 1 stressed / exception-heavy borrower
* **2 private corporates**

  * 1 NTB
  * 1 ETB
* **1 group-structure case**

  * to show promoter/director/company linkage
* **1 sector-variant case**

  * for example manufacturing vs real estate vs infra

### Documents per case

At minimum:

* 3 years financials
* latest provisional
* request note
* debt schedule
* bank statement sample
* one or two public reference docs if listed
* 4–6 mock external payloads

That gives enough complexity for:

* extraction
* mismatch detection
* benchmarking
* ETB/NTB branching
* CAM generation
* analyst chat

---

## 6. How to build the document set fast

## Option A — fastest and best

Use real public listed-company documents.

### Download from NSE

* annual reports
* financial results
* governance
* ratings
* default payment details
* BRSR where available

These are already exposed in NSE corporate filings sections. ([NSE India][1])

## Option B — private company POC

Create **synthetic but realistic** documents.

Best practice:

* use a standard audited financial statement template
* create 3-year trend
* create provisional with one mismatch
* create debt schedule
* create group structure
* create one collateral pack
* create one promoter KYC pack

This is actually better for demo because you can force edge cases.

## Option C — ETB internal data

Create internal sample tables:

* account_turnover_monthly.csv
* facility_utilization_daily.csv
* repayment_history.csv
* covenant_tracker.csv
* prior_cam_summary.json
* exception_history.csv

These need not be real customer data. Synthetic is safer.

---

## 7. What Postman should simulate

Your Postman layer should behave like the future external integration fabric.

Create endpoints like:

```text
POST /external/mca/company-master
POST /external/mca/directors
POST /external/mca/charges
POST /external/bureau/commercial-report
POST /external/gst/turnover-summary
POST /external/exchange/financial-summary
POST /external/market/news-sentiment
POST /external/social/reputation-signals
POST /external/regulatory/watchlist
```

Each should return versioned payloads like:

```json
{
  "source": "mca",
  "record_type": "company_master",
  "entity_key": "PAN/CIN",
  "as_of_date": "2026-03-13",
  "payload_version": "v1",
  "payload": {
    "company_name": "ABC Industries Limited",
    "cin": "U12345DL2010PLC000001",
    "status": "Active",
    "registered_state": "Delhi"
  }
}
```

This is exactly how you future-proof the solution.

---

## 8. Best POC document matrix

Use this as your operating model.

| Case         | Real docs                                      | Synthetic docs                                      | Mock APIs                                  |
| ------------ | ---------------------------------------------- | --------------------------------------------------- | ------------------------------------------ |
| NTB Listed   | NSE annual report, results, governance, rating | request note, projected financials, collateral docs | MCA, bureau, GST, market, social           |
| NTB Unlisted | borrower financials if available               | full KYC, financial pack, debt schedule, collateral | MCA, bureau, GST, market, social           |
| ETB Listed   | latest NSE filings + previous internal docs    | internal conduct if not real                        | MCA refresh, bureau refresh, market/social |
| ETB Unlisted | borrower update docs                           | internal conduct, prior CAM, covenant history       | MCA, bureau, GST, market/social            |

---

## 9. Best POC demo scenarios

You need scenarios, not just documents.

### Scenario 1 — clean listed NTB

* numbers match
* strong benchmark
* CAM generated smoothly

### Scenario 2 — listed NTB with mismatch

* annual report revenue ≠ borrower-uploaded provisional
* system raises validation exception
* CAM reflects unresolved exception

### Scenario 3 — ETB enhancement case

* good financials
* poor utilization trend
* covenant breach
* system recommends conditional approval

### Scenario 4 — private NTB with promoter/group risk

* MCA/director mock shows related entity stress
* social/news mock shows reputational flag
* system adds caution in CAM

That is enough for an enterprise-grade demo.

---

## 10. My recommendation for complete POC package

Build these folders:

```text
/poc-data
  /listed_company_1
    annual_report.pdf
    financial_results.pdf
    governance.pdf
    rating_details.pdf
    request_note.docx
    projected_financials.xlsx

  /listed_company_2
  /private_ntb_1
  /private_etb_1

/mock-api
  mca_company_master.json
  mca_directors.json
  mca_charges.json
  bureau_report.json
  gst_summary.json
  market_sentiment.json
  social_flags.json

/internal-etb
  account_conduct.csv
  utilization.csv
  covenant_history.csv
  prior_cam.json
```

This gives you enough to show:

* ingestion
* validation
* benchmark
* deterministic transformation
* CAM generation
* analyst chat

---

## 11. Direct answer

For a **complete POC**, get data this way:

* **Listed corporates:** use real NSE filings and annual reports
* **Private corporates:** use synthetic/masked borrower document packs
* **MCA, bureau, GST, market, social, regulatory:** simulate using Postman
* **ETB:** create realistic internal conduct and prior-credit-history sample data
* **NTB:** use full onboarding and external-validation style document pack

That is the best design because it proves the platform end to end without waiting for production integrations.

I can next turn this into a **POC source-and-document checklist in Excel/CSV format** with columns for:
`case_type, source_name, document_name, real_or_mock, mandatory_flag, file_format, validation_rule, api_mock_name`.

[1]: https://www.nseindia.com/companies-listing/corporate-filings-annual-reports?utm_source=chatgpt.com "Corporate Filings Annual Reports - Equity, SME"
[2]: https://www.data.gov.in/catalog/company-master-data?utm_source=chatgpt.com "Company Master Data"
[3]: https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=11566&utm_source=chatgpt.com "Master Direction on KYC"
Yes. For a **complete POC**, you should **not wait for real external APIs**.
You can build it in 3 source buckets:

1. **real public documents** for listed companies
2. **synthetic / masked documents** for private and NTB scenarios
3. **Postman mock APIs** for MCA, bureau, market, social, regulatory enrichments

That is the fastest and cleanest path.

## 1. Best POC data strategy

Use this rule:

**Listed corporate POC = mostly real public-source data**
**Private corporate POC = borrower-uploaded docs + mocked external responses**
**ETB POC = internal-bank sample data + mocked external refresh**
**NTB POC = full doc pack + mocked external checks**

This works because public listed companies in India already have a lot of usable material on NSE, including annual reports, financial results, governance filings, ratings, default-payment details, and BRSR-related disclosures. MCA also provides company master lookup services, and RBI KYC directions remain the base reference for onboarding/KYC design. ([NSE India][1])

---

## 2. Where to get data for the POC

### A. Listed company data — use real public sources

For listed companies, use real documents from:

* **NSE corporate filings**
* **Annual reports**
* **Quarterly / annual financial results**
* **Corporate governance filings**
* **Credit rating details**
* **Default payment details**
* **BRSR / sustainability filings**

NSE explicitly exposes these filing categories on its corporate filings pages. ([NSE India][1])

### B. MCA / company master data

For company identity and enrichment, use:

* company master
* CIN
* company status
* registered office
* directors / designated partners
* charge-related / filing-related mock payloads

MCA master-data services are the right official reference point for company/LLP and director lookup, and data.gov.in also lists company master data fields like CIN, company status, registration date, state, and capital information. ([Data.gov.in][2])

### C. KYC / onboarding reference

For POC document requirements and flow design, use RBI KYC directions as the policy baseline. RBI’s KYC Master Direction is the right official source for onboarding and updation logic, and RBI’s 2025 FAQ/update context supports lighter refresh logic for existing relationships. ([Reserve Bank of India][3])

### D. Sustainability / governance overlays for listed entities

For listed corporates, if you want governance / ESG overlays in CAM, use BRSR/BRSR Core references from NSE and SEBI. ([NSE India][1])

---

## 3. What documents you need for a complete POC

## Case 1: NTB listed corporate

Use **real public documents + borrower pack + mock external APIs**.

### Borrower / uploaded docs

* loan request note
* audited financial statements for 3 years
* latest provisional financials
* bank statements
* existing debt schedule
* board resolution
* shareholding / group structure
* collateral docs if secured
* project report / utilization note if term loan

### Public real docs

* annual reports from NSE
* quarterly / annual financial results from NSE
* governance filings
* rating disclosures
* default-payment details if available
* BRSR if applicable

### Mock external APIs in Postman

* MCA company master
* MCA directors
* MCA charges
* bureau commercial report
* GST turnover summary
* market/news sentiment
* social / reputational flags

---

## Case 2: NTB private / unlisted corporate

For private companies, you will not get the same richness from exchanges, so do this:

### Use real or masked borrower docs

* certificate of incorporation
* PAN
* GST certificate
* MOA / AOA
* audited financial statements
* provisional financials
* bank statements
* debt schedule
* stock statements if WC
* promoter KYC
* net worth statement
* group structure
* collateral docs

### Use mock external APIs

* MCA company master
* MCA directors
* MCA charges
* bureau commercial report
* regulatory watchlist response
* market / media / social signal response

For POC, this is enough. You do **not** need live production integrations.

---

## Case 3: ETB listed corporate

Use:

### Internal ETB sample data

* account conduct
* facility utilization
* repayment history
* covenant compliance history
* previous CAM / annual review memo
* exception history
* transaction turnover trend

### Updated borrower docs

* latest audited financials
* latest provisional financials
* updated debt schedule
* fresh request note / enhancement note
* updated collateral valuation if required

### Public real docs

* NSE filings
* annual report
* latest results
* rating action
* governance updates

### Mock external APIs

* MCA refresh
* bureau refresh
* market/news/sentiment refresh

---

## Case 4: ETB private / unlisted corporate

Use:

### Internal ETB sample data

* account conduct
* limit utilization
* repayment behavior
* prior CAM
* covenant and exception history

### Borrower docs

* latest audited financials
* provisional financials
* updated debt schedule
* stock statements
* request note
* updated collateral docs if applicable

### Mock external APIs

* MCA
* bureau
* GST summary
* market/social risk flags

---

## 4. What should be real vs mocked in the POC

This is the best split.

| Source type                                | POC approach               |
| ------------------------------------------ | -------------------------- |
| Annual reports                             | Real                       |
| NSE financial results                      | Real                       |
| NSE governance / ratings / default details | Real                       |
| Borrower-uploaded financials               | Real, masked, or synthetic |
| MCA responses                              | Mock in Postman            |
| Bureau/commercial credit report            | Mock in Postman            |
| GST summary                                | Mock in Postman            |
| Social/media sentiment                     | Mock in Postman first      |
| Internal ETB account conduct               | Synthetic but realistic    |

Why this is the right move: it gives you **real document ingestion and real validation logic**, while keeping hard-to-access external integrations simulated.

---

## 5. How many companies/documents you need for a strong POC

Do not overbuild.
For a serious demo, this is enough:

### Recommended POC corpus

* **2 listed corporates**

  * 1 strong borrower
  * 1 stressed / exception-heavy borrower
* **2 private corporates**

  * 1 NTB
  * 1 ETB
* **1 group-structure case**

  * to show promoter/director/company linkage
* **1 sector-variant case**

  * for example manufacturing vs real estate vs infra

### Documents per case

At minimum:

* 3 years financials
* latest provisional
* request note
* debt schedule
* bank statement sample
* one or two public reference docs if listed
* 4–6 mock external payloads

That gives enough complexity for:

* extraction
* mismatch detection
* benchmarking
* ETB/NTB branching
* CAM generation
* analyst chat

---

## 6. How to build the document set fast

## Option A — fastest and best

Use real public listed-company documents.

### Download from NSE

* annual reports
* financial results
* governance
* ratings
* default payment details
* BRSR where available

These are already exposed in NSE corporate filings sections. ([NSE India][1])

## Option B — private company POC

Create **synthetic but realistic** documents.

Best practice:

* use a standard audited financial statement template
* create 3-year trend
* create provisional with one mismatch
* create debt schedule
* create group structure
* create one collateral pack
* create one promoter KYC pack

This is actually better for demo because you can force edge cases.

## Option C — ETB internal data

Create internal sample tables:

* account_turnover_monthly.csv
* facility_utilization_daily.csv
* repayment_history.csv
* covenant_tracker.csv
* prior_cam_summary.json
* exception_history.csv

These need not be real customer data. Synthetic is safer.

---

## 7. What Postman should simulate

Your Postman layer should behave like the future external integration fabric.

Create endpoints like:

```text
POST /external/mca/company-master
POST /external/mca/directors
POST /external/mca/charges
POST /external/bureau/commercial-report
POST /external/gst/turnover-summary
POST /external/exchange/financial-summary
POST /external/market/news-sentiment
POST /external/social/reputation-signals
POST /external/regulatory/watchlist
```

Each should return versioned payloads like:

```json
{
  "source": "mca",
  "record_type": "company_master",
  "entity_key": "PAN/CIN",
  "as_of_date": "2026-03-13",
  "payload_version": "v1",
  "payload": {
    "company_name": "ABC Industries Limited",
    "cin": "U12345DL2010PLC000001",
    "status": "Active",
    "registered_state": "Delhi"
  }
}
```

This is exactly how you future-proof the solution.

---

## 8. Best POC document matrix

Use this as your operating model.

| Case         | Real docs                                      | Synthetic docs                                      | Mock APIs                                  |
| ------------ | ---------------------------------------------- | --------------------------------------------------- | ------------------------------------------ |
| NTB Listed   | NSE annual report, results, governance, rating | request note, projected financials, collateral docs | MCA, bureau, GST, market, social           |
| NTB Unlisted | borrower financials if available               | full KYC, financial pack, debt schedule, collateral | MCA, bureau, GST, market, social           |
| ETB Listed   | latest NSE filings + previous internal docs    | internal conduct if not real                        | MCA refresh, bureau refresh, market/social |
| ETB Unlisted | borrower update docs                           | internal conduct, prior CAM, covenant history       | MCA, bureau, GST, market/social            |

---

## 9. Best POC demo scenarios

You need scenarios, not just documents.

### Scenario 1 — clean listed NTB

* numbers match
* strong benchmark
* CAM generated smoothly

### Scenario 2 — listed NTB with mismatch

* annual report revenue ≠ borrower-uploaded provisional
* system raises validation exception
* CAM reflects unresolved exception

### Scenario 3 — ETB enhancement case

* good financials
* poor utilization trend
* covenant breach
* system recommends conditional approval

### Scenario 4 — private NTB with promoter/group risk

* MCA/director mock shows related entity stress
* social/news mock shows reputational flag
* system adds caution in CAM

That is enough for an enterprise-grade demo.

---

## 10. My recommendation for complete POC package

Build these folders:

```text
/poc-data
  /listed_company_1
    annual_report.pdf
    financial_results.pdf
    governance.pdf
    rating_details.pdf
    request_note.docx
    projected_financials.xlsx

  /listed_company_2
  /private_ntb_1
  /private_etb_1

/mock-api
  mca_company_master.json
  mca_directors.json
  mca_charges.json
  bureau_report.json
  gst_summary.json
  market_sentiment.json
  social_flags.json

/internal-etb
  account_conduct.csv
  utilization.csv
  covenant_history.csv
  prior_cam.json
```

This gives you enough to show:

* ingestion
* validation
* benchmark
* deterministic transformation
* CAM generation
* analyst chat

---

## 11. Direct answer

For a **complete POC**, get data this way:

* **Listed corporates:** use real NSE filings and annual reports
* **Private corporates:** use synthetic/masked borrower document packs
* **MCA, bureau, GST, market, social, regulatory:** simulate using Postman
* **ETB:** create realistic internal conduct and prior-credit-history sample data
* **NTB:** use full onboarding and external-validation style document pack

That is the best design because it proves the platform end to end without waiting for production integrations.

I can next turn this into a **POC source-and-document checklist in Excel/CSV format** with columns for:
`case_type, source_name, document_name, real_or_mock, mandatory_flag, file_format, validation_rule, api_mock_name`.

[1]: https://www.nseindia.com/companies-listing/corporate-filings-annual-reports?utm_source=chatgpt.com "Corporate Filings Annual Reports - Equity, SME"
[2]: https://www.data.gov.in/catalog/company-master-data?utm_source=chatgpt.com "Company Master Data"
[3]: https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=11566&utm_source=chatgpt.com "Master Direction on KYC"
Yes. For a **complete POC**, you should **not wait for real external APIs**.
You can build it in 3 source buckets:

1. **real public documents** for listed companies
2. **synthetic / masked documents** for private and NTB scenarios
3. **Postman mock APIs** for MCA, bureau, market, social, regulatory enrichments

That is the fastest and cleanest path.

## 1. Best POC data strategy

Use this rule:

**Listed corporate POC = mostly real public-source data**
**Private corporate POC = borrower-uploaded docs + mocked external responses**
**ETB POC = internal-bank sample data + mocked external refresh**
**NTB POC = full doc pack + mocked external checks**

This works because public listed companies in India already have a lot of usable material on NSE, including annual reports, financial results, governance filings, ratings, default-payment details, and BRSR-related disclosures. MCA also provides company master lookup services, and RBI KYC directions remain the base reference for onboarding/KYC design. ([NSE India][1])

---

## 2. Where to get data for the POC

### A. Listed company data — use real public sources

For listed companies, use real documents from:

* **NSE corporate filings**
* **Annual reports**
* **Quarterly / annual financial results**
* **Corporate governance filings**
* **Credit rating details**
* **Default payment details**
* **BRSR / sustainability filings**

NSE explicitly exposes these filing categories on its corporate filings pages. ([NSE India][1])

### B. MCA / company master data

For company identity and enrichment, use:

* company master
* CIN
* company status
* registered office
* directors / designated partners
* charge-related / filing-related mock payloads

MCA master-data services are the right official reference point for company/LLP and director lookup, and data.gov.in also lists company master data fields like CIN, company status, registration date, state, and capital information. ([Data.gov.in][2])

### C. KYC / onboarding reference

For POC document requirements and flow design, use RBI KYC directions as the policy baseline. RBI’s KYC Master Direction is the right official source for onboarding and updation logic, and RBI’s 2025 FAQ/update context supports lighter refresh logic for existing relationships. ([Reserve Bank of India][3])

### D. Sustainability / governance overlays for listed entities

For listed corporates, if you want governance / ESG overlays in CAM, use BRSR/BRSR Core references from NSE and SEBI. ([NSE India][1])

---

## 3. What documents you need for a complete POC

## Case 1: NTB listed corporate

Use **real public documents + borrower pack + mock external APIs**.

### Borrower / uploaded docs

* loan request note
* audited financial statements for 3 years
* latest provisional financials
* bank statements
* existing debt schedule
* board resolution
* shareholding / group structure
* collateral docs if secured
* project report / utilization note if term loan

### Public real docs

* annual reports from NSE
* quarterly / annual financial results from NSE
* governance filings
* rating disclosures
* default-payment details if available
* BRSR if applicable

### Mock external APIs in Postman

* MCA company master
* MCA directors
* MCA charges
* bureau commercial report
* GST turnover summary
* market/news sentiment
* social / reputational flags

---

## Case 2: NTB private / unlisted corporate

For private companies, you will not get the same richness from exchanges, so do this:

### Use real or masked borrower docs

* certificate of incorporation
* PAN
* GST certificate
* MOA / AOA
* audited financial statements
* provisional financials
* bank statements
* debt schedule
* stock statements if WC
* promoter KYC
* net worth statement
* group structure
* collateral docs

### Use mock external APIs

* MCA company master
* MCA directors
* MCA charges
* bureau commercial report
* regulatory watchlist response
* market / media / social signal response

For POC, this is enough. You do **not** need live production integrations.

---

## Case 3: ETB listed corporate

Use:

### Internal ETB sample data

* account conduct
* facility utilization
* repayment history
* covenant compliance history
* previous CAM / annual review memo
* exception history
* transaction turnover trend

### Updated borrower docs

* latest audited financials
* latest provisional financials
* updated debt schedule
* fresh request note / enhancement note
* updated collateral valuation if required

### Public real docs

* NSE filings
* annual report
* latest results
* rating action
* governance updates

### Mock external APIs

* MCA refresh
* bureau refresh
* market/news/sentiment refresh

---

## Case 4: ETB private / unlisted corporate

Use:

### Internal ETB sample data

* account conduct
* limit utilization
* repayment behavior
* prior CAM
* covenant and exception history

### Borrower docs

* latest audited financials
* provisional financials
* updated debt schedule
* stock statements
* request note
* updated collateral docs if applicable

### Mock external APIs

* MCA
* bureau
* GST summary
* market/social risk flags

---

## 4. What should be real vs mocked in the POC

This is the best split.

| Source type                                | POC approach               |
| ------------------------------------------ | -------------------------- |
| Annual reports                             | Real                       |
| NSE financial results                      | Real                       |
| NSE governance / ratings / default details | Real                       |
| Borrower-uploaded financials               | Real, masked, or synthetic |
| MCA responses                              | Mock in Postman            |
| Bureau/commercial credit report            | Mock in Postman            |
| GST summary                                | Mock in Postman            |
| Social/media sentiment                     | Mock in Postman first      |
| Internal ETB account conduct               | Synthetic but realistic    |

Why this is the right move: it gives you **real document ingestion and real validation logic**, while keeping hard-to-access external integrations simulated.

---

## 5. How many companies/documents you need for a strong POC

Do not overbuild.
For a serious demo, this is enough:

### Recommended POC corpus

* **2 listed corporates**

  * 1 strong borrower
  * 1 stressed / exception-heavy borrower
* **2 private corporates**

  * 1 NTB
  * 1 ETB
* **1 group-structure case**

  * to show promoter/director/company linkage
* **1 sector-variant case**

  * for example manufacturing vs real estate vs infra

### Documents per case

At minimum:

* 3 years financials
* latest provisional
* request note
* debt schedule
* bank statement sample
* one or two public reference docs if listed
* 4–6 mock external payloads

That gives enough complexity for:

* extraction
* mismatch detection
* benchmarking
* ETB/NTB branching
* CAM generation
* analyst chat

---

## 6. How to build the document set fast

## Option A — fastest and best

Use real public listed-company documents.

### Download from NSE

* annual reports
* financial results
* governance
* ratings
* default payment details
* BRSR where available

These are already exposed in NSE corporate filings sections. ([NSE India][1])

## Option B — private company POC

Create **synthetic but realistic** documents.

Best practice:

* use a standard audited financial statement template
* create 3-year trend
* create provisional with one mismatch
* create debt schedule
* create group structure
* create one collateral pack
* create one promoter KYC pack

This is actually better for demo because you can force edge cases.

## Option C — ETB internal data

Create internal sample tables:

* account_turnover_monthly.csv
* facility_utilization_daily.csv
* repayment_history.csv
* covenant_tracker.csv
* prior_cam_summary.json
* exception_history.csv

These need not be real customer data. Synthetic is safer.

---

## 7. What Postman should simulate

Your Postman layer should behave like the future external integration fabric.

Create endpoints like:

```text
POST /external/mca/company-master
POST /external/mca/directors
POST /external/mca/charges
POST /external/bureau/commercial-report
POST /external/gst/turnover-summary
POST /external/exchange/financial-summary
POST /external/market/news-sentiment
POST /external/social/reputation-signals
POST /external/regulatory/watchlist
```

Each should return versioned payloads like:

```json
{
  "source": "mca",
  "record_type": "company_master",
  "entity_key": "PAN/CIN",
  "as_of_date": "2026-03-13",
  "payload_version": "v1",
  "payload": {
    "company_name": "ABC Industries Limited",
    "cin": "U12345DL2010PLC000001",
    "status": "Active",
    "registered_state": "Delhi"
  }
}
```

This is exactly how you future-proof the solution.

---

## 8. Best POC document matrix

Use this as your operating model.

| Case         | Real docs                                      | Synthetic docs                                      | Mock APIs                                  |
| ------------ | ---------------------------------------------- | --------------------------------------------------- | ------------------------------------------ |
| NTB Listed   | NSE annual report, results, governance, rating | request note, projected financials, collateral docs | MCA, bureau, GST, market, social           |
| NTB Unlisted | borrower financials if available               | full KYC, financial pack, debt schedule, collateral | MCA, bureau, GST, market, social           |
| ETB Listed   | latest NSE filings + previous internal docs    | internal conduct if not real                        | MCA refresh, bureau refresh, market/social |
| ETB Unlisted | borrower update docs                           | internal conduct, prior CAM, covenant history       | MCA, bureau, GST, market/social            |

---

## 9. Best POC demo scenarios

You need scenarios, not just documents.

### Scenario 1 — clean listed NTB

* numbers match
* strong benchmark
* CAM generated smoothly

### Scenario 2 — listed NTB with mismatch

* annual report revenue ≠ borrower-uploaded provisional
* system raises validation exception
* CAM reflects unresolved exception

### Scenario 3 — ETB enhancement case

* good financials
* poor utilization trend
* covenant breach
* system recommends conditional approval

### Scenario 4 — private NTB with promoter/group risk

* MCA/director mock shows related entity stress
* social/news mock shows reputational flag
* system adds caution in CAM

That is enough for an enterprise-grade demo.

---

## 10. My recommendation for complete POC package

Build these folders:

```text
/poc-data
  /listed_company_1
    annual_report.pdf
    financial_results.pdf
    governance.pdf
    rating_details.pdf
    request_note.docx
    projected_financials.xlsx

  /listed_company_2
  /private_ntb_1
  /private_etb_1

/mock-api
  mca_company_master.json
  mca_directors.json
  mca_charges.json
  bureau_report.json
  gst_summary.json
  market_sentiment.json
  social_flags.json

/internal-etb
  account_conduct.csv
  utilization.csv
  covenant_history.csv
  prior_cam.json
```

This gives you enough to show:

* ingestion
* validation
* benchmark
* deterministic transformation
* CAM generation
* analyst chat

---

## 11. Direct answer

For a **complete POC**, get data this way:

* **Listed corporates:** use real NSE filings and annual reports
* **Private corporates:** use synthetic/masked borrower document packs
* **MCA, bureau, GST, market, social, regulatory:** simulate using Postman
* **ETB:** create realistic internal conduct and prior-credit-history sample data
* **NTB:** use full onboarding and external-validation style document pack

That is the best design because it proves the platform end to end without waiting for production integrations.

I can next turn this into a **POC source-and-document checklist in Excel/CSV format** with columns for:
`case_type, source_name, document_name, real_or_mock, mandatory_flag, file_format, validation_rule, api_mock_name`.

[1]: https://www.nseindia.com/companies-listing/corporate-filings-annual-reports?utm_source=chatgpt.com "Corporate Filings Annual Reports - Equity, SME"
[2]: https://www.data.gov.in/catalog/company-master-data?utm_source=chatgpt.com "Company Master Data"
[3]: https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=11566&utm_source=chatgpt.com "Master Direction on KYC"


Yes. For your POC, the system should have **two big things**:

* **configuration** = what can be changed without code
* **rules** = what the system evaluates deterministically

For this product, the best design is:

**config-driven platform + versioned rule packs + deterministic workflow**

That is the right shape because:

* KYC/onboarding and periodic KYC updates need configurable handling across NTB and ETB. ([Reserve Bank of India][1])
* MCA master/director lookup is a core enrichment source and should be pluggable. ([Ministry of Corporate Affairs][2])
* Listed-company evidence sources such as annual reports, governance filings, ratings, and default-payment details should be source-configured, not hardcoded. ([NSE India][3])
* Deterministic replay is essential if you want same input to produce same case-processing path. Temporal explicitly requires deterministic workflow behavior for replay. ([Temporal Docs][4])

# 1. What configuration the system should have

Think of config in **10 layers**.

## A. Case configuration

This decides which flow to run.

Example:

* ETB / NTB
* listed / unlisted
* working capital / term loan / project finance / renewal / enhancement
* secured / unsecured
* sector / subsector
* entity type: company / LLP / group / SPV

Example config:

```json
{
  "case_type": "NTB",
  "borrower_type": "listed",
  "facility_type": "working_capital",
  "secured_flag": true,
  "sector": "manufacturing",
  "subsector": "auto_components"
}
```

## B. Source configuration

This tells the system where data comes from.

Example:

* borrower upload
* internal ETB systems
* Postman mock MCA
* Postman mock bureau
* Postman mock GST
* Postman mock market/social
* NSE document fetch

Example:

```json
{
  "source_name": "mca_company_master",
  "mode": "postman_mock",
  "priority": 1,
  "timeout_ms": 5000,
  "retry_count": 2,
  "active": true
}
```

## C. Document policy configuration

This controls mandatory vs optional docs.

Example:

* NTB listed WC case needs:

  * audited financials
  * latest provisional
  * board resolution
  * debt schedule
  * bank statements
  * exchange filings reference
* ETB renewal may need:

  * latest audited financials
  * provisional
  * internal conduct data
  * prior CAM
  * covenant history

Example:

```json
{
  "policy_pack": "NTB_LISTED_WC_V1",
  "mandatory_docs": [
    "audited_financials_3y",
    "latest_provisional",
    "board_resolution",
    "debt_schedule",
    "bank_statements_12m"
  ],
  "optional_docs": [
    "project_note",
    "customer_contracts"
  ]
}
```

## D. Source priority configuration

This is critical for determinism.

Example for revenue:

1. exchange filing
2. annual report
3. borrower uploaded audited
4. provisional
5. MIS
6. media/social

Example:

```json
{
  "field": "revenue_operating",
  "priority_order": [
    "exchange_filing",
    "annual_report",
    "uploaded_audited_fs",
    "uploaded_provisional",
    "management_mis"
  ],
  "mismatch_tolerance_pct": 2.0
}
```

## E. Extraction configuration

This controls parsing behavior.

Example:

* parser type
* OCR fallback allowed or not
* table extraction strategy
* line item mapping dictionary version
* rounding policy
* financial period alignment rule

## F. Validation configuration

This controls which checks run.

Example packs:

* structural validation
* cross-source validation
* accounting validation
* stale-data validation
* ETB conduct validation
* listed-governance validation
* sector overlay validation

## G. Benchmark configuration

This controls peer comparison.

Example:

* sector
* subsector
* listed/unlisted
* turnover band
* geography
* rating band
* peer sample minimum size
* percentile method

Example:

```json
{
  "benchmark_pack": "MFG_MIDCORP_LISTED_V2",
  "peer_filters": {
    "sector": "manufacturing",
    "size_band": "500cr_to_2000cr",
    "listed_status": "listed"
  },
  "metrics": ["ebitda_margin", "debt_to_ebitda", "current_ratio"]
}
```

## H. Rule-pack configuration

This controls what deterministic rules are applied.

Example packs:

* global credit policy
* ETB renewal rules
* NTB onboarding rules
* sector pack: manufacturing
* sector pack: real estate
* product pack: WC
* product pack: term loan

## I. LLM configuration

LLM must be tightly controlled.

Example:

* model name
* temperature = 0
* prompt version
* allowed tools
* output schema version
* citation requirement
* banned unsupported claims

Example:

```json
{
  "model": "gpt-5.4",
  "temperature": 0,
  "prompt_version": "cam_writer_v3",
  "schema_version": "cam_facts_v2",
  "citations_required": true
}
```

## J. Workflow/governance configuration

This controls approvals and human review.

Example:

* auto-stop on critical mismatch
* analyst review required if unresolved exceptions > 0
* approval matrix by amount/rating/sector
* version lock requirement for final CAM

---

# 2. What rules the system should have

Rules should be grouped into **8 families**.

## 1. Intake and case-routing rules

These decide which path to run.

Examples:

* if existing customer and renewal → ETB renewal flow
* if new customer and no internal conduct history → NTB flow
* if listed company → listed evidence pack
* if project finance → project-finance benchmark pack

Example:

```text
IF relationship_type = "ETB" AND request_type = "renewal"
THEN workflow = "ETB_RENEWAL"
```

## 2. Document sufficiency rules

These check if the case can proceed.

Examples:

* NTB must have audited financials
* secured case must have collateral docs
* board resolution mandatory above threshold
* ETB enhancement must include latest debt schedule

Example:

```text
IF case_type = "NTB" AND audited_financials_3y is missing
THEN block_case
```

## 3. Source validation rules

These compare submitted data vs external/reference data.

Examples:

* company PAN ↔ MCA mismatch
* directors in board resolution ↔ MCA directors mismatch
* uploaded revenue ↔ listed filing mismatch
* declared debt ↔ bureau debt mismatch

Example:

```text
IF abs(uploaded_revenue - exchange_revenue) / exchange_revenue > 0.02
THEN create_exception("REV_MISMATCH")
```

## 4. Financial calculation rules

These are pure deterministic formulas.

Examples:

* EBITDA
* Debt/EBITDA
* Current Ratio
* Interest Coverage
* DSCR
* Working Capital Cycle
* FOIR-style internal coverage rules if used

These must never be LLM-based.

## 5. Policy/risk rules

These are bank policy checks.

Examples:

* leverage threshold breach
* minimum DSCR
* negative net worth
* stale audited financials
* sector restricted
* promoter adverse signal
* group concentration threshold

Example:

```text
IF debt_to_ebitda > 5
THEN risk_flag = "HIGH_LEVERAGE"
```

## 6. ETB-specific rules

These are behavior-based.

Examples:

* average utilization > 95% for 6 months
* cheque return count exceeds threshold
* covenant breaches unresolved
* repayment delay trend worsening
* transaction turnover inconsistent with declared operations

Example:

```text
IF cheque_return_count_6m > 5
THEN create_exception("POOR_ACCOUNT_CONDUCT")
```

## 7. NTB-specific rules

These are onboarding-heavy.

Examples:

* full KYC must exist
* MCA status must be active
* bureau mandatory
* promoter/group checks mandatory
* no approval until critical mismatches resolved

Example:

```text
IF case_type = "NTB" AND mca_status != "Active"
THEN block_case
```

## 8. CAM generation rules

These control what memo says and how.

Examples:

* only approved facts can enter CAM
* all metrics must cite source
* unresolved critical exceptions must appear in risk section
* sector template decides section order
* recommendation section must reflect rule outputs, not model guess

Example:

```text
IF unresolved_critical_exceptions > 0
THEN recommendation_status = "REFER_WITH_EXCEPTIONS"
```

---

# 3. Best design for rules

The best design is:

**global rules + case rules + sector rules + product rules + source rules + CAM rules**

So your rule stack becomes:

```text
Global Credit Policy
    +
ETB / NTB Policy Pack
    +
Listed / Unlisted Pack
    +
Sector Pack
    +
Facility Pack
    +
Validation Pack
    +
CAM Narrative Pack
```

This is much better than one giant rules file.

---

# 4. Best way to implement configuration and rules

## Recommended implementation model

### In database / config tables

Store configs in tables like:

* `workflow_config`
* `document_policy`
* `source_registry`
* `source_priority_rules`
* `validation_rule_pack`
* `benchmark_pack`
* `sector_policy_pack`
* `facility_policy_pack`
* `cam_template_pack`
* `llm_prompt_pack`
* `approval_matrix`

### In rules engine / decision tables

Store business logic as versioned rules:

* `decision_table_case_routing`
* `decision_table_doc_sufficiency`
* `decision_table_validation_severity`
* `decision_table_policy_outcome`
* `decision_table_cam_recommendation`

This is where DMN-style decision tables are useful in practice.

---

# 5. Minimum configuration tables for your POC

For your POC, keep it simple. Start with these 12 tables:

1. `case_master`
2. `document_registry`
3. `source_registry`
4. `source_payload_snapshot`
5. `field_priority_rule`
6. `document_policy_rule`
7. `validation_rule`
8. `benchmark_pack`
9. `sector_pack`
10. `facility_pack`
11. `cam_template_pack`
12. `audit_version_registry`

That is enough for a real POC.

---

# 6. Example system configuration for one case

## Example: NTB listed manufacturing working-capital case

### Configuration

```json
{
  "case_type": "NTB",
  "borrower_type": "listed",
  "sector": "manufacturing",
  "facility_type": "working_capital",
  "doc_policy_pack": "NTB_LISTED_WC_V1",
  "validation_pack": "NTB_LISTED_FIN_V1",
  "benchmark_pack": "MFG_LISTED_MIDCORP_V1",
  "cam_template_pack": "CAM_LISTED_WC_V1",
  "source_pack": [
    "borrower_upload",
    "exchange_filing",
    "mca_mock",
    "bureau_mock",
    "market_mock"
  ]
}
```

### Rules fired

* audited financials mandatory
* exchange revenue preferred over uploaded revenue
* MCA status must be active
* bureau mandatory
* leverage threshold check
* current ratio check
* working-capital-cycle benchmark check
* unresolved mismatch must go into CAM risk section

---

# 7. What should be configurable vs hardcoded

## Configurable

* document checklist
* source endpoints
* source priority
* validation thresholds
* benchmark cohorts
* sector packs
* facility packs
* approval routing
* prompt/template versions

## Hardcoded only if absolutely core

* hash generation
* audit event creation
* immutable evidence linking
* deterministic rounding utility
* workflow identity model

Everything else should be config-driven.

---

# 8. My blunt recommendation

For your system, do **not** build just “agents.”

Build this:

**Config Console + Rule Packs + Deterministic Engines + LLM Orchestrator**

That is the real product.

### Product modules

* **Source Config Console**
* **Document Policy Console**
* **Validation Rule Console**
* **Benchmark Pack Console**
* **Sector Policy Console**
* **CAM Template Console**
* **Approval Matrix Console**
* **Audit & Version Console**

That will make the platform enterprise-ready.

---

# 9. Direct answer

Your system should have configuration for:

* case type
* borrower type
* source adapters
* document policy
* source priority
* extraction settings
* validation packs
* benchmark packs
* sector/facility policy packs
* LLM templates
* approval workflow
* version/audit control

And your rules should cover:

* routing
* document sufficiency
* source mismatch
* financial calculations
* policy thresholds
* ETB behavior
* NTB onboarding
* sector overlays
* CAM generation and recommendation

That is the best design.

I can next turn this into a **full configuration matrix + rules catalog** in a product-ready spreadsheet structure.

[1]: https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=11566&utm_source=chatgpt.com "Master Direction on KYC"
[2]: https://www.mca.gov.in/content/mca/global/hi/mca/master-data/MDS.html?utm_source=chatgpt.com "https://www.mca.gov.in/content/mca/global/hi/mca/m..."
[3]: https://www.nseindia.com/companies-listing/corporate-filings-annual-reports?utm_source=chatgpt.com "Corporate Filings Annual Reports - Equity, SME"
[4]: https://docs.temporal.io/workflows?utm_source=chatgpt.com "Temporal Workflow | Temporal Platform Documentation"
 along with user



 Customer 360 

 For a customer 360-degree view in your corporate lending/CAM system, you should gather data points in 12 blocks. Below is the full data-point inventory with sources for both listed and unlisted corporates, and for ETB + NTB.

This is the right structure for underwriting, validation, benchmarking, and CAM generation.

1. Borrower identity and legal profile

This is the master identity layer.

Data point	Source
Legal entity name	Borrower docs, MCA
CIN / LLPIN	MCA
PAN	Borrower
GSTIN	Borrower / GST-related fetch if available
Incorporation date	MCA, annual report
Company status (active/inactive)	MCA
Registered office	MCA, annual report, borrower docs
Corporate office / plant locations	annual report, borrower presentation
Legal form (Ltd/Pvt/LLP)	MCA
Listed / unlisted status	NSE/BSE, borrower
Sector / subsector	annual report, exchange filings, internal classification
Parent / subsidiary / associate mapping	annual report, borrower group chart, MCA
UBO / beneficial ownership	borrower declaration, KYC pack

RBI’s KYC Master Direction governs customer due diligence and ongoing KYC updates, while MCA Master Data Services support company/LLP and director lookup.

2. Promoter, director, and management view

This is the control-and-governance layer.

Data point	Source
Promoter names	annual report, borrower docs
Directors / DIN details	MCA, annual report
Key management personnel	annual report, borrower presentation
Board composition	annual report, governance filings
Director changes	MCA, exchange governance filings
Shareholding pattern	annual report, exchange filings
Group companies	annual report, borrower group chart, MCA
Related-party relationships	annual report, notes to accounts
Auditor name	annual report
Auditor qualifications / emphasis	audit report in annual report
Board committees / governance	governance filings, annual report

For listed companies, SEBI LODR and NSE governance/filing pages are primary disclosure sources for governance, annual reports, and related reporting.

3. KYC, AML, compliance, and onboarding

This is especially important for NTB.

Data point	Source
KYC completion status	bank onboarding workflow
Authorized signatories	board resolution, borrower docs
Board resolution for borrowing	borrower
Registered-address proof	borrower, MCA
Promoter/director ID proofs	borrower KYC pack
Beneficial owner declaration	borrower
Re-KYC / periodic update status	bank KYC workflow
AML / sanctions / PEP flags	compliance tools / mock source for POC
FATCA / CRS if applicable	borrower compliance pack

RBI requires customer due diligence and periodic updating of KYC records depending on customer risk category.

4. Facility request and current relationship

This shows what the customer wants and what the bank already has.

Data point	Source
ETB / NTB flag	internal bank system
Relationship vintage	internal CRM/CBS
Requested facility type	RM input, request note
Requested amount	RM input, request note
Purpose of loan	request note, project report
Existing facilities with bank	internal LMS / LOS
Sanctioned vs utilized	internal LMS / CBS
Pricing / tenor / repayment structure	sanction system
Non-fund-based exposure	internal LMS
Group exposure with bank	internal credit system
Prior sanctions / renewals / restructures	internal credit records
5. Financial statements and core financial data

This is the most important block.

Data point	Source
3-year audited financials	borrower, annual report
Latest provisional financials	borrower
Standalone vs consolidated	annual report, borrower
Balance sheet line items	financial statements
P&L line items	financial statements
Cash-flow line items	financial statements
Notes to accounts	annual report / audited FS
Segment data	annual report
Projections / CMA data	borrower
Quarterly results for listed entities	NSE/BSE filings
Annual report financial disclosures	annual report, exchange filings

NSE provides financial results and annual reports for listed entities, which are useful for validation against borrower-submitted packs.

6. Derived financial metrics and analytics

These are calculated, but still part of the 360 view.

Data point	Source
Revenue growth	derived from financials
EBITDA / EBITDA margin	derived from financials
PAT / PAT margin	derived from financials
Net worth	derived from financials
Total debt	derived from financials, debt schedule
Debt / EBITDA	derived
Debt / Equity	derived
Current ratio	derived
Quick ratio	derived
Interest coverage	derived
DSCR	derived
ROCE / ROE	derived
Inventory days	derived
Receivable days	derived
Payable days	derived
Working capital cycle	derived
Operating cash flow	derived
Capex intensity	derived
Projection vs actual variance	borrower projections + actuals
7. Banking, debt, and exposure view

This is the lender view of obligations.

Data point	Source
Existing lenders	borrower debt schedule, bureau/mock bureau
Total external borrowing	borrower, bureau, annual report
Term loan details	borrower, sanction letters
Working capital limits	borrower, internal systems
Repayment schedule	borrower, internal LMS
Contingent liabilities	annual report, borrower
Charges / security created	MCA, borrower docs
Debt maturity profile	borrower, annual report
Fund-based / non-fund-based split	borrower, internal records

NSE also provides credit-rating and debt-related disclosure categories for listed entities, useful for cross-checking exposure context.

8. ETB conduct and behavioral view

This is critical for ETB and one of the biggest differentiators from NTB.

Data point	Source
Account turnover trend	internal CBS
Average utilization	internal LMS/CBS
Excess / limit breach history	internal systems
Repayment behavior	internal LMS
Overdues / delays	internal LMS
Cheque returns / bounce counts	internal CBS
Covenant compliance history	internal monitoring
Stock statement submission behavior	internal monitoring
Drawing power history	internal WC system
Exception / waiver history	internal credit system
Prior CAM / review memo	document repository
Relationship profitability / wallet share	internal MIS
9. Market, industry, and benchmark view

This is peer-relative intelligence.

Data point	Source
Sector	annual report, borrower, internal taxonomy
Subsector	annual report, internal taxonomy
Industry outlook	internal research / mock market feed
Peer cohort	internal benchmark engine
Peer median margins	benchmark dataset
Peer leverage levels	benchmark dataset
Peer liquidity levels	benchmark dataset
Borrower vs peer percentile	benchmark engine
Borrower vs prior-year trend	internal analytics
Sector concentration risk	internal portfolio system
10. External intelligence, ratings, and reputation

This is the outside-in risk layer.

Data point	Source
External credit rating	CRA report, NSE debt/credit rating filings
Rating history	CRA reports, exchange filings
Rating outlook	CRA reports
Key rating drivers	CRA reports
News sentiment	mock market/news feed
Adverse media flags	mock market/news feed
Promoter reputation flags	mock social/news feed
Regulatory or default-related event flags	exchange disclosures
BRSR / ESG disclosures for listed entities	annual report, NSE/BSE filings
Governance red flags	annual report, governance filings

NSE’s filing pages explicitly include annual reports, corporate governance, credit-rating details, default-payment details, and BRSR-related disclosures. SEBI’s BRSR framework specifies general disclosure fields such as CIN, registered office, website, listed exchanges, and capital details.

11. Collateral and security view

This is the downside-protection layer.

Data point	Source
Collateral type	borrower, valuation report
Asset ownership	title docs, borrower
Security value	valuation report
LTV	derived
Security coverage ratio	derived
Legal enforceability	legal opinion
Insurance status	borrower / insurer copy
Charge creation status	borrower, MCA, internal legal tracking
Guarantors	borrower, legal docs
Corporate guarantee / personal guarantee	legal docs
12. Validation, exceptions, and auditability

This is the block that makes the 360 view decision-grade.

Data point	Source
Submitted vs MCA mismatch	borrower + MCA
Submitted vs exchange mismatch	borrower + NSE/BSE
Submitted vs bureau mismatch	borrower + bureau/mock bureau
Financial statement math inconsistency	internal validation engine
Stale filing flag	internal validation engine + filing dates
Missing mandatory document flag	document policy engine
Unresolved analyst exception	analyst workflow
Source priority chosen value	canonical merge engine
Last refresh date	system metadata
Parser / rule / benchmark version	audit/version store
CAM version history	CAM repository
Best 360-degree summary card on top

At the top of the customer 360 view, show these first:

borrower name

ETB / NTB

listed / unlisted

sector / subsector

requested amount and facility

internal/external rating snapshot

top 5 risk flags

unresolved exceptions count

conduct summary

recommendation status

Minimum source map by customer type
For listed corporates

Use:

borrower documents

annual report

NSE/BSE filings

governance filings

CRA disclosures

MCA

internal ETB systems if applicable

For unlisted/private corporates

Use:

borrower documents

MCA

bureau/mock bureau

internal ETB systems if applicable

market/news/social mock feeds

For ETB

Add heavily:

account conduct

utilization

repayment history

prior CAMs

covenant history

exception history

For NTB

Add heavily:

KYC pack

onboarding docs

MCA enrichment

bureau

external validation

My recommendation

Design the 360 view as a credit decision cockpit, not a CRM page. It should combine:

identity

financials

exposure

conduct

governance

benchmark

external intelligence

collateral

validation exceptions

CAM-ready outputs

That is the right shape for your product.

