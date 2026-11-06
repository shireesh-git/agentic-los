# Data points and where they come from

This document lists **every piece of information** the system uses to decide on a loan, and **where each
one comes from**. No technical knowledge is needed to read it. For the terms used, see the
[glossary](USER_GUIDE.md#glossary).

---

## 1. How to read this document

A **data point** is one piece of information that a credit decision uses. Examples are the borrower's
revenue, its debt, or whether it appears on a sanctions list.

Every data point has three properties:

| Property | Question it answers | Shown on screen as |
|---|---|---|
| **Source** | Where did this come from? | A small link under the value (e.g. "AI · CAM §3", "Borrower master") |
| **How it was obtained** | Fetched from an online service, read from a document someone uploaded, calculated, or typed by an officer? | The tag next to it ("Auto-populated", "Provided", "Overridden") |
| **Confidence** | How sure are we? | "Confidence high · 90" with the reason on hover |

A figure is also judged against the bank's **policy limits** where one exists. The screen shows "Within",
"Close" or "Outside" next to it. This is kept separate from the source, so **green always means
good**, never just "filled in".

---

## 2. The six kinds of source

| Kind of source | What it means | Example | Confidence it starts with |
|---|---|---|---|
| **Live API** | An online service the agents call automatically | LEI registry (GLEIF), sanctions lists (OFAC, UN), news (GDELT) | High |
| **Uploaded file** | A document the Relationship Manager (RM) uploads when no online service is connected. An agent reads it | Annual report, bureau report, GST returns, bank statements | High for audited statements, lower for others |
| **Bank's document pack** | Files already on record for an existing borrower (stand-ins for the bank's own systems) | `storage/documents/<borrower>/…` | As the document |
| **Calculated** | Worked out by the credit engine from other figures, using fixed formulas (§6) | DSCR, sustainable limit, earnings quality | Slightly below the figures it uses |
| **Written by AI from data** | Text the AI writes **only** from the data above; every number it quotes is checked against the data | Business background, industry outlook | No confidence score (text) |
| **Entered by an officer** | A person typed or changed it | A corrected EBITDA, the banking arrangement | Medium (not independently verified) |

The AI **never invents a number**. It may only quote figures that exist in the data, and a CAM
section that quotes any other figure is flagged.

---

## 3. External data sources: APIs and the files that replace them

For a **new-to-bank prospect**, five agents work in parallel to collect this information. Each source is
**API first**. If the API is not connected, the agent asks the RM for one specific document and reads
it instead. An upload and an API response produce the same record, so connecting an API later needs
no other change. Configuration: [`config/data_sources.yaml`](../config/data_sources.yaml).

| # | Source | What it gives | Agent | Provider (API) | Status today | File the RM uploads instead |
|---|---|---|---|---|---|---|
| 1 | **LEI** | Legal name, registered address, CIN as registered, parent | Identity & Registry | GLEIF API (free, public) | **Live** | — |
| 2 | **MCA company master** | Company status, incorporation, capital, directors (DIN), charges | Identity & Registry | Probe42 (MCA21 data) | Ready; **inactive until `PROBE42_API_KEY` is set** | MCA master data printout |
| 3 | **Audited financial statements** | 3 years of profit & loss, balance sheet, cash flow | Financials | Licensed exchange-filings feed | Not connected | Last two annual reports (or audited statements) |
| 4 | **Commercial bureau** | Credit score / rank, lenders, facilities, overdues | Credit & Banking | CIBIL / CRIF commercial | Not connected | Bureau report (CIBIL CMR / CRIF) |
| 5 | **Bank statements** | Credits, debits, balances, cheque returns, limit use | Credit & Banking | Account Aggregator (Sahamati) | Not connected | Six months' statements of the main account |
| 6 | **GST** | Registration, filing status, turnover by year | Credit & Banking | GST Suvidha Provider (GSP) | Not connected | GST returns summary (GSTR-3B / GSTR-1) |
| 7 | **KYC** | PAN, certificate of incorporation, signatories | Compliance | CKYC (CERSAI) | Not connected | KYC pack |
| 8 | **Sanctions screening** | Company and directors against sanctions lists | Compliance | OFAC SDN + UN Security Council lists | **Live** (lists downloaded at most once a day, matched locally) | — |
| 9 | **External rating** | Rating, outlook, rationale, rated limits | Market & Reputation | Rating agency rationale (CRISIL / ICRA / CARE) | Not an API (agencies publish documents) | Latest rating rationale |
| 10 | **Adverse media** | Negative news about the company | Market & Reputation | GDELT news API (free) | **Live** (often rate-limited; then shown as "unavailable") | — |

**What a proposal needs** (from the same file):

| Requirement | Sources |
|---|---|
| Always | MCA, financials, bureau, KYC, sanctions |
| Recommended (the RM can skip) | LEI, rating, adverse media |
| Working capital / cash credit | + bank statements, GST |
| Term loan | + bank statements |
| **Minimum before the CAM can be generated** | MCA, financials, KYC, sanctions |

**How outbound calls behave.** The agents call online services politely, so the traffic never looks like
an attack:
- one request at a time per site, at least 3 seconds apart (6 seconds for GDELT);
- the site's `robots.txt` is respected;
- responses are cached, so a re-run does not call again;
- a failed call is retried once, and only for "busy" responses;
- a site that keeps failing is paused for 15 minutes.

**A verification agent** then cross-checks the sources:
- CIN agrees across MCA, LEI and KYC; PAN across KYC, GSTIN and bureau;
- the statements reconcile; the latest audited year is current;
- GST turnover and bank credits agree with revenue;
- the bureau's borrowings agree with the balance sheet.

**Example test data:** Dixon Technologies uses real public annual reports and an ICRA rationale, plus
generated documents marked "UAT DEMO DATA". See
[`test-documents/dixon_technologies/README.md`](../test-documents/dixon_technologies/README.md).

### Existing borrowers

For a borrower already in the catalogue, the information comes from its **document pack** in
`storage/documents/<borrower id>/`, one folder per kind of document:

| Folder | Typical files | Used for |
|---|---|---|
| `financials/` | Audited statements, annual reports, provisional results | All financial figures and ratios |
| `mca/` | Company master, directors, charges | Identity, management, charges |
| `kyc/` | KYC pack | KYC hard rule |
| `bureau/` | Commercial bureau report, CRILC report | Bureau score, overdues, existing lenders |
| `banking/` | Bank statements, existing facility details, earlier sanction letters | Account conduct, revenue truth |
| `gst/` | GST returns | GST compliance, revenue truth |
| `ratings/` | Rating rationale | External rating |
| `collateral/` | Valuation report | Security, forced-sale value, security cover |
| `exchange/` | Stock-exchange filings | Quarterly results |
| `legal/`, `request/`, `misc/` | Legal opinions, the loan request, other | Facility details, conditions |

The LOS catalogue has seven borrowers:
- six real listed companies with public documents: APOL001, INFY001, IHCL001, MFL001, MRF001 and PNCR001;
- one synthetic borrower: ABCE001.

The other folders under `storage/documents/` belong to synthetic borrowers used by the credit engine's
tests. A new prospect is added to the catalogue when it is initiated.

A data block with no source on record is shown as **"Not on record"** or **"Not verifiable"**. It is never
treated as a pass.

---

## 4. The credit data fields (what every officer sees)

These are the 46 fields on the proposal screen, grouped as they appear. Configuration:
[`config/flow.yaml`](../config/flow.yaml) → `datapoints`.

Legend:
- **Asked**: if no source fills it, Credit Copilot asks the RM in the chat.
- **Agent only**: never asked; empty means "not on record".
- **Calculated**: cannot be typed; change the underlying figure instead.
- **Band**: judged against a policy limit.

### Borrower

| Field | What it is | Source |
|---|---|---|
| Borrower name * | Registered name | Borrower master (MCA) / LEI / KYC |
| CIN | Company identification number | Borrower master; prospects: MCA or LEI |
| PAN | Tax identity | Borrower master / KYC pack |
| Sector, Sub-sector | Line of business | Borrower master |
| Constitution | Public / private / government company; listed or not | **Derived from the CIN**: L/U = listed / unlisted; PLC, PTC, GOI … = company class |
| Banking arrangement | Sole or multiple banking | **Lender count** from the bureau or CRILC. Otherwise **asked** |
| Business background | What the company does | Written by AI from the records (CAM §1) |
| Corporate governance | Management and board | Written by AI from the records (CAM §1) |

### Facility

| Field | What it is | Source |
|---|---|---|
| Product *, Amount requested *, Tenor, Purpose | The loan asked for | Entered by the RM when the proposal is opened. Changing one makes the CAM out of date |
| Recommended limit * | What the bank should lend | Credit engine's recommendation; Underwriting may override it with a reason |
| Pricing | Interest rate | The bank's rate card (credit engine) |

### Financials (latest audited year)

| Field | Source |
|---|---|
| Revenue *, EBITDA *, PAT *, Net worth *, Total debt * | Audited statements, read by the Financials agent (prospects) or from the document pack (existing borrowers). Every figure links to the statement |

### Credit metrics (all calculated, agent only)

| Field | What it tells you | Formula (§6) | Policy limit (band) |
|---|---|---|---|
| DSCR | Can cash flow pay the debt instalments? | (PAT + depreciation + finance cost) ÷ (finance cost + annual principal) | min 1.20x |
| Interest cover | How many times profit covers interest | EBIT ÷ finance cost | min 2.00x |
| Debt / EBITDA | Years of earnings needed to repay all debt | Total debt ÷ EBITDA | max 4.00x |
| Current ratio | Short-term assets against short-term dues | Current assets ÷ current liabilities | min 1.25x |
| TOL / TNW | Total outside liabilities against own funds | (Total debt + current liabilities) ÷ (net worth − intangibles) | max 4.00x |
| Debt / equity | Borrowing against own funds | Total debt ÷ net worth | max 2.50x |
| Sustainable limit | The largest loan every policy limit allows | §6.2 | must be ≥ recommended limit |
| Earnings quality | How much profit is operating and cash-backed | §6.3 | good ≥ 85 / 100 |
| Revenue truth score | Does independent data support the revenue? | §6.4 | good ≥ 85 / 100 |
| Early-warning flags | Warning signs found at origination | §6.5 | 0 good, 1 amber, 2+ red |
| Hard rules failed | Non-negotiable policy rules broken | Policy engine | 0 |
| Bureau score | Commercial credit score | Bureau report / API | — |
| CRILC SMA status | Stress reported by other banks to RBI | CRILC report | — |
| Collateral FSV | Forced-sale value of the security | Valuation report | — |
| Security cover | Security against the loan | FSV ÷ facility amount | min 1.00x |

### Risk & rating

| Field | Source |
|---|---|
| Internal rating * | Credit engine's rating scorecard (grade and score out of 100) |
| External rating | Borrower master / rating rationale |
| Strengths | Credit engine (strengths found in the figures) |
| Risks and mitigants | The Credit Challenge Agent's challenges, each with the officer's answer, then the engine's observations. Updates itself as challenges are answered |
| Industry outlook | Credit engine's industry analysis (agent only) |
| Marketing arrangements | Revenue segments, geography and clients from the industry analysis (agent only) |

### Security & terms

| Field | Source |
|---|---|
| Security * | Collateral analysis from the valuation report: assets, values, cover |
| Key terms and conditions | Conditions proposed by the credit engine |
| Covenants | Financial covenants proposed by the credit engine |

### Decision

| Field | Source |
|---|---|
| Deviations | The **deviation register**: every policy breach, its mitigant and who approved it (agent only) |
| Recommendation * | Credit engine's recommendation (Approve / Refer / Decline) with its reason |

\* = mandatory before the proposal can move on.

---

## 5. What the credit engine builds (the "fact pack")

When a CAM is generated, the credit engine assembles all the facts into one dataset, the **fact pack**.
The CAM and the fields above are written from it. Every block is labelled with its kind of source, and
the CAM states which is which.

| Area | Blocks | Source |
|---|---|---|
| Identity & group | borrower profile, group profile, corporate hierarchy, management profile | Borrower master / MCA |
| Facility | facility details, existing exposure, facility pricing, drawing power | Loan request, bank records, rate card, calculation |
| Financials | financial summary, ratio analysis (27 ratios × 3 years), quarterly performance, cash flow & repayment, projections, benchmark summary | Audited statements; calculation; sector peer benchmarks |
| **Size & quality (new)** | debt capacity, earnings quality, revenue truth, early-warning indicators | Calculation (§6) |
| Credit history & conduct | external intelligence (bureau, GST, MCA status), CRILC exposure, conduct analysis, covenant history, core banking | Bureau / CRILC / GST / bank statements (**empty when not on record**) |
| Compliance | compliance checks, PEP / sanctions screening, validation exceptions | Public records, sanctions lists, validation rules |
| Market | industry analysis, sector KPIs, market signals, ESG | Industry data; news where verified |
| Policy & decision | policy thresholds, policy decisions (hard rules, scores, recommendation), approving authority, credit strengths, key risks | The bank's rules (`config/rules.yaml`, `config/approval.yaml`) |
| Provenance | data sources, data provenance, document verification | How every block was obtained |

Some blocks are kept for completeness but carry **no live source** in this demo: social-media analysis,
site visit and infrastructure metrics. They are labelled "not available" and never presented as
verified. **Social media is no longer part of the CAM.**

---

## 6. Calculations: exactly how each figure is worked out

All calculations are **deterministic**: the same inputs always give the same result, and no AI is involved.
Code: [`src/engines/ratio_engine.py`](../src/engines/ratio_engine.py) and
[`src/engines/quality_engine.py`](../src/engines/quality_engine.py).

### 6.1 Policy limits

They come from [`config/rules.yaml`](../config/rules.yaml) → `policy_thresholds`, and the bank can edit them:

| Limit | Value |
|---|---|
| Minimum DSCR | 1.20x |
| Minimum interest cover | 2.00x |
| Maximum Debt / EBITDA | 4.00x |
| Minimum current ratio | 1.25x |
| Maximum TOL / TNW | 4.00x |
| Maximum debt / equity | 2.50x |
| Minimum EBITDA margin | 10% |
| Minimum return on equity | 12% |
| Maximum debtor days | 90 |

A ratio within 10% of its limit (on the safe side) is shown as **"Close to the limit"**.

### 6.2 Sustainable limit (how much can safely be lent)

Each policy limit is applied to the latest year's figures, at the projected interest rate, to find the
**largest new loan it allows**:

| Limit | Largest new loan it allows |
|---|---|
| Debt / EBITDA | max ratio × EBITDA − existing debt |
| Interest cover | (EBIT ÷ min cover − existing interest) ÷ interest rate |
| DSCR | (cash accruals ÷ min DSCR − existing debt service) ÷ (interest rate + yearly principal share) |
| TOL / TNW | max ratio × own funds − existing debt − current liabilities |
| Debt / equity | max ratio × net worth − existing debt |
| Drawing power (working capital only) | drawing power − existing working-capital limit |

The **sustainable limit** is the smallest of these. The limit that sets it is shown as **"bound by"**.
For term loans the same check runs at longer tenors (60, 84 and 120 months). If a longer tenor makes
the requested amount pass, the screen offers **"Extend tenor"**. Otherwise it offers **"Set limit"**. A limit
that is already broken at zero additional debt means **no amount or tenor can pass**: the proposal needs
equity, debt reduction or a policy deviation.

### 6.3 Earnings quality (score out of 100)

| Measure | Healthy | Watch | Concern |
|---|---|---|---|
| Other income as a share of pre-tax profit | ≤ 25% | 25–50% | > 50% |
| Cash conversion (operating cash flow ÷ EBITDA) | ≥ 60% | 30–60% | < 30% |
| Accruals ((PAT − operating cash flow) ÷ total assets) | ≤ 5% | 5–10% | > 10% |
| Receivables growth minus revenue growth | ≤ 15 points | 15–30 | > 30 |
| Exceptional items as a share of pre-tax profit | ≤ 10% | 10–25% | > 25% |

Score = 100, minus 10 for each "watch" and 25 for each "concern".

### 6.4 Revenue truth (score out of 100)

Audited revenue is compared with every independent source on record:

| Source | Agrees | Differs | Does not support |
|---|---|---|---|
| GST turnover (same year) | within 10% | 10–25% | > 25% |
| Bank credits, annualised (these include GST and non-sales receipts) | 0.75–1.35× revenue | 0.5–1.6× | outside |
| Provisional results / exchange filing (same year) | within 5% | 5–15% | > 15% |

Score = 100, minus 15 for each "differs" and 40 for each "does not support". With **no independent
source**, the result is **"Not verifiable"**, not a pass.

### 6.5 Early-warning indicators at origination

These are in the spirit of RBI's fraud-risk Master Directions (2024). Each indicator is **Flag**, **Clear**
or **Not checked**. "Not checked" means the data is missing, and a missing figure is never a flag.

| Indicator | Flag when |
|---|---|
| Default / delay in statutory dues | GST filings are not regular |
| Cheque / ECS returns | Any return in the bank statements |
| Overdues / SMA with other lenders | Bureau overdues or a CRILC SMA status |
| Revenue not supported | Revenue truth is "does not support" |
| Profit dependent on non-operating income | Other income > 50% of pre-tax profit |
| Negative operating cash flow two years running | Both of the last two years are negative |
| Delay in submission of financial statements | Latest audited year is out of date |
| Receivables growing well ahead of sales | > 30 points faster than revenue |
| Earnings manipulation (Beneish M-score) | M-score above −1.78 (only when every input is on record for both years) |
| Financial distress (Altman Z) | Z below 1.81 |
| Board independence below one-third | Fewer than 1 in 3 directors independent (only when independence is recorded) |

### 6.6 Confidence of each figure

| Source of the figure | Confidence |
|---|---|
| Audited statements | 90 (high). Revenue: +10 if GST / bank data agree, −10 if it differs, −35 if not supported, −5 if not cross-checked |
| Provisional results | 70 (medium) |
| Calculated metrics | 5 below the statements they use |
| Bureau / CRILC record | 90; demo data 40 |
| Collateral value as submitted | 65 |
| Read from the bank's own CAM (uploaded) | 70 |
| This platform's data sheet inside a downloaded CAM | 95 |
| Typed by an officer | 50 (30 if it differs from the audited statements) |

High = 80 or more, medium = 60–79, low = below 60.

---

## 7. After sanction: documents Credit Administration collects

From [`config/flow.yaml`](../config/flow.yaml) → `conditions`. An agent checks each uploaded document,
and CAD confirms what the agent cannot verify.

| Condition | When | Notes |
|---|---|---|
| Sanction letter accepted by the borrower | Before release | |
| Board resolution authorising the borrowing | Before release | |
| Facility agreement executed and stamped | Before release | |
| Security documents executed | Before release | |
| Legal vetting by panel advocate | Before release | Only above ₹100 Cr |
| Insurance of charged assets with bank clause | Before release | Only for physical security (property, plant, stock …) |
| KYC of borrower and signatories | Before release | Met automatically when KYC on record is current |
| Charge registration with ROC (CHG-1) and CERSAI | Within 30 days after release | |
