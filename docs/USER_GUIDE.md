# User guide

What the system does, who does what, a proposal step by step, a demo script and a glossary. It assumes no
knowledge of lending systems; words in *italics* are in the [glossary](#glossary).

---

## 1. What this is

When a company asks a bank for a loan, the bank collects information about it, writes a *credit appraisal
memorandum (CAM)* recommending yes or no, passes the proposal through several officers, collects signed documents
and releases the money. This takes weeks, much of it copying figures between documents.

Here, **AI agents** — small programs that each do one job — collect the data, read the documents, do the arithmetic
and draft the CAM. **People still make every decision.** An agent never approves, declines or releases money.

| Part | Address | What it is |
|---|---|---|
| **Loan origination (LOS)** | `http://localhost:8001/los` | The screens the bank's officers work in, from opening a proposal to release |
| **CAM workspace** | `http://localhost:8001/` | The credit engine on its own, for in-depth analysis |

---

## 2. Who does what

| # | Role | Their job | What the system does for them |
|---|---|---|---|
| 1 | **Relationship Manager (RM)**, Origination | Opens the proposal for a borrower and amount | Gathers the data, asks for missing documents, writes the CAM, fills most fields |
| 2 | **Credit Underwriter**, Underwriting | Checks and challenges the analysis | Key risk challenges with options; *sustainable limit*; *deviation register*; connections |
| 3 | **Sanctioning Authority** | Sanctions, returns or declines | Every change Underwriting made (each to be agreed), every deviation, the case against |
| 4 | **Credit Administration (CAD)** | Collects the signed documents | Drafts the sanction letter, checks each uploaded document, prepares the release request |
| 5 | **Disbursement Operations** | Releases the money | Final compliance checklist (demo: no money moves) |

Any officer can **return** the proposal to the previous stage with remarks; some can **decline** it.

---

## 3. A proposal, step by step

### Step 1: the RM opens a proposal

**My Work Queue → Initiate Proposal**, then either:
- **Existing borrower:** choose by **sector**, **borrower name** or **CIN** (the three lists are linked). Every
  borrower with data on record is listed; prospects already initiated are marked *new-to-bank*.
- **New-to-bank prospect:** type the registered name (CIN and PAN optional). Initiating the same company again
  reuses its record — it is never listed twice.

Enter the facility (product, amount, tenor, purpose). Nothing runs yet: the CAM card offers **Generate CAM** or
**Ingest Bank CAM**.

### Step 2: the CAM is written

**Generate CAM.** For a new-to-bank borrower, step 1 runs first on the CAM card — five *agents* gather the data,
with a progress bar and the agent working:

| Agent | What it gathers |
|---|---|
| Identity & Registry | LEI (GLEIF, live), company registry |
| Financials | Audited statements from the annual reports |
| Credit & Banking | Bureau report, bank statements, GST |
| Compliance | Sanctions (OFAC, UN, live), KYC |
| Market & Reputation | Rating, news (live) |

Where no online service is connected, the CAM card lists the documents still needed. **Upload** them in Data Sources
— or, for UAT, click **Load test pack** to file a prepared set (TCI, KPI Green, H.G. Infra, Dixon). As soon as the
CAM's minimum data is in, steps 2 and 3 (analysis, writing) start on their own.

The CAM is a one-page **Decision Summary** built from data (no AI wording) and eight sections. **Ingest Bank CAM**
instead reads the bank's own CAM; the agents then fill what it does not state from the audited statements.

### Step 3: read the record

- **Overview:** the verdict (Approve / Refer / Decline), *hard rules*, key ratios against policy, mandatory checks.
- **Borrower data:** every field, by section (Borrower, Facility, Financials, Credit metrics, Risk & rating,
  Security & terms, Decision). Each value shows its source; **Provide** fills a missing one (a calculated figure the
  engine could not compute needs the reason); **Mark not provided** records that it is not available. The Copilot
  asks for missing fields one at a time.
- **Risk & decision:**
  - **Connections:** anyone connected in financial stress? within our exposure limits? linked to the bank's own
    directors? — then a map: directors and shareholders on the left, the borrower in the middle, lenders and group
    companies on the right;
  - **Auditor's report & notes**, **Limit assessment**;
  - **Key Risk Challenges:** each states the *decision needed*, what was found, why it matters and the evidence that
    would settle it, with options — reduce the limit, **accept the risk with justification**, **ask the RM for
    evidence**, **decline the proposal**;
  - **Deviation Register:** every policy breach, its mitigant and approval.
- **Documents & CAM:** the CAM, its progress, and the data sources.

### Step 4: Underwriting and Sanction

Underwriting answers the challenges, records a mitigant for each deviation, may override a figure (with a
rationale), then recommends. Ask the Copilot "What should I do next?" for numbered steps, or "Should the amount be
reduced?" for the arithmetic. Going against an engine **Decline** needs a written justification.

The Sanctioning Authority agrees or returns each override and approves or rejects each deviation; **Sanction** stays
disabled until all are done. A failed hard rule cannot be approved as a deviation.

### Step 5: CAD and disbursement

CAD receives the drafted sanction letter, the conditions and a prepared release request. The agent checks each
uploaded document and ticks what it can verify; CAD confirms the rest. Disbursement runs the final checklist and
releases (no payment system is called in the demo).

### The queue

Tick proposals (or the box in the header) and **Delete selected** to clear test proposals. Sanctioned and disbursed
proposals cannot be deleted.

---

## 4. Demo script

Start the app and open `http://localhost:8001/los`; switch role with the sign-out icon (top right).

| Journey | Borrower | Shows |
|---|---|---|
| A | Infosys (healthy) | A clean proposal from start to release, most fields filled by agents |
| B | Madras Fertilizers (weak) | How a weak loan is stopped: negative net worth, ratios outside policy, Decline, challenges, deviations |
| C | Transport Corporation of India (new to bank) | Agents gather what is online; the test pack fills the rest; the CAM starts on its own |

**A.** RM: Existing borrower → *Infosys Limited*, working capital → Generate CAM → point out the verdict, the risk
strip, the sources of the fields → Submit. Underwriting: "change EBITDA to 35900 because the one-off gain is
excluded" → **Re-run CAM** rewrites only the affected sections → Recommend. Sanction: **Concur** with the change →
Sanction. CAD: **Add demo executed documents** → Submit. Disbursement: Authorise Release. Show the **Audit Trail
Report**, the **CAM** PDF and **TAT & Productivity**.

**B.** RM: *Madras Fertilizers* → Generate CAM → **Decline**: its audited net worth is negative (₹-32 Cr), which fails
the "net worth must be positive" hard rule; current ratio 0.68x and other ratios outside policy. Submitting asks for a written justification. Underwriting: Copilot "What should I do
next?"; answer the challenges; record mitigants. Sanction: the hard-rule failure cannot be approved — decline or
return.

**C.** RM: New-to-bank prospect → *Transport Corporation of India Limited* → Generate CAM → step 1 lists the missing
documents → **Load test pack** → the agents read the annual reports and demo documents (statements read twice and
cross-checked) → the CAM engine starts on its own → continue as in A.

---

## 5. What you can download

| Report | Where | Contents |
|---|---|---|
| **CAM (PDF)** | "CAM" on the proposal | The CAM; page one is the live Decision Summary |
| **Audit Trail Report** | "⋯" menu | Every decision and who made it, every field's source, every change, the AI used, the event log |
| **AI Governance Pack** | "⋯" menu | Model card, AI use on this proposal, fairness check, impact assessment |
| **Sanction letter** | After sanction | Draft for CAD |
| **TAT & Productivity** | Left menu | Time to sanction, data auto-filled, decisions against the engine, SLA |

## 6. What the system will not do

- Approve, sanction, decline or release money — a named person does, with remarks.
- Invent a number — figures come from documents, records or fixed calculations, each with its source.
- Hide missing information — a check it could not run says **"Not verified"**, never "pass".

---

## Glossary

| Term | Meaning |
|---|---|
| **LOS** | Loan Origination System: software that processes a loan request from start to release |
| **CAM** | Credit Appraisal Memorandum: the report that analyses a borrower and recommends whether to lend |
| **Proposal** | One loan request moving through the officers |
| **RM** | Relationship Manager: the bank's contact for the borrower |
| **New-to-bank** | A borrower the bank has no record of yet (a prospect) |
| **Sanction** | The formal approval of a loan |
| **CAD** | Credit Administration: collects signed documents before release |
| **Disbursement** | Releasing the loan money |
| **Agent** | A small AI program that does one job (fetch data, read a document, check a figure) |
| **Credit Copilot** | The chat assistant on every screen |
| **Test pack** | A prepared set of a prospect's documents for UAT: real annual reports plus labelled demo documents |
| **Engine verdict** | The credit engine's recommendation: Approve, Refer (to a higher authority) or Decline |
| **Internal rating** | The bank's own grade for the borrower (A best … E weakest), with a score out of 100 |
| **External rating** | A rating agency's grade, e.g. "CRISIL AAA (Stable)" |
| **Hard rule** | A rule the bank never bends, e.g. KYC complete, company active |
| **Policy limit** | A minimum or maximum for a ratio, e.g. DSCR at least 1.20 |
| **Deviation** | Going ahead although a policy limit is broken; needs a mitigant and an approval |
| **Mitigant** | Something that reduces a risk: extra security, a covenant, a cash reserve |
| **Revenue / EBITDA / PAT** | Sales / operating profit before interest, tax and depreciation / profit after tax |
| **Net worth** | The owners' funds in the business |
| **DSCR** | Debt service coverage: cash available ÷ instalments and interest due |
| **Debt / EBITDA** | Years of operating profit needed to repay all debt |
| **Current ratio** | Short-term assets ÷ short-term dues |
| **TOL / TNW** | Total outside liabilities ÷ the owners' tangible funds |
| **Sustainable limit** | The largest loan that keeps every policy ratio within its limit |
| **Assessed limit** | The working-capital need from turnover, MPBF or the operating cycle |
| **Earnings quality** | How much of the profit is from the main business and backed by cash |
| **Revenue truth** | Whether GST returns and bank statements support the revenue in the accounts |
| **Early-warning flag** | A sign of stress or possible fraud found before lending |
| **Group exposure** | The bank's lending to the borrower and all companies connected to it |
| **Bureau / CRILC** | Credit bureaus (CIBIL, CRIF) / RBI's database of large exposures; *SMA* marks stressed accounts |
| **GST / KYC / LEI / MCA** | Goods and Services Tax / Know Your Customer / Legal Entity Identifier / the company registry |
| **CIN / PAN / DIN** | Company ID / tax ID / director ID |
| **FSV / Security cover** | Forced-sale value of security / security value ÷ loan amount |
| **Covenant** | A promise in the loan agreement, e.g. keep DSCR above 1.2 |
| **Condition precedent / subsequent** | A document needed before release / within a set time after release |
| **TAT / SLA** | How long a proposal takes / the target time for each stage |
