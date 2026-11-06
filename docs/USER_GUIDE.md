# User guide

This guide explains what the system does and how to use it. It assumes **no knowledge of lending
systems or technology**. Words in *italics* are explained in the [glossary](#glossary) at the end.

---

## 1. What this is

When a company asks a bank for a loan, the bank:
- collects information about the company;
- writes a *credit appraisal memorandum (CAM)*, the report that recommends yes or no;
- passes the proposal through several officers, each of whom checks and approves it;
- collects signed documents and releases the money.

This takes weeks, and much of it is people copying figures from one document to another.

This system does the collecting, the copying, the arithmetic and the first draft of the CAM with **AI
agents**, small programs that each do one job. **People still make every decision.** An agent never
approves, declines or releases money. It prepares the work, explains its reasoning, and points out
what needs a person's judgement.

There are two parts:

| Part | Address | What it is |
|---|---|---|
| **Loan origination (the LOS)** | `http://localhost:8001/los` | The screens the bank's officers work in, from opening a proposal to releasing the money |
| **CAM workspace** | `http://localhost:8001/` | The credit engine on its own, for analysts who want to look at a borrower's analysis in depth |

---

## 2. Who does what

A proposal passes through five officers in turn. Each signs in as their own role; this demo
uses a sign-in picker with no password.

| # | Role | Their job | What the system does for them |
|---|---|---|---|
| 1 | **Relationship Manager (RM)**, Origination | Opens the proposal for a borrower and the loan amount | Fetches data, asks for missing documents one at a time, writes the CAM, fills about 40 of 46 fields |
| 2 | **Credit Underwriter**, Underwriting | Checks the analysis, challenges it, may change figures | Lists the *key risk challenges* with suggested actions; works out the *sustainable limit*; keeps the *deviation register* |
| 3 | **Sanctioning Authority** | Decides: sanction, return or decline | Shows every change Underwriting made (each must be agreed), every policy breach and its mitigant, and the *case against* |
| 4 | **Credit Administration (CAD)** | Collects the signed documents before money is released | Drafts the sanction letter; checks each uploaded document; prepares the release request |
| 5 | **Disbursement Operations** | Releases the money | Runs the final compliance checklist (demo: no money moves) |

Any officer can **return** the proposal to the previous stage with remarks, and some can **decline** it.

---

## 3. A proposal, step by step

### Step 1: the RM opens a proposal

Choose **Initiate Proposal**, then one of:
- **Existing borrower:** pick the company. Its documents are already on record.
- **New-to-bank prospect:** type the name (CIN and PAN are optional). Five agents start straight away:

| Agent | What it fetches |
|---|---|
| Identity & Registry | LEI, company registry |
| Financials | Audited statements |
| Credit & Banking | Bureau, bank statements, GST |
| Compliance | Sanctions, KYC |
| Market & Reputation | Rating, news |

  Each agent tries an **online service first**. Where none is connected, it **asks you for one
  document** in the chat, e.g. "Upload the last two annual reports", and reads it. The **Data Sources**
  panel shows each source: fetched online, read from your document, or still awaited.

Then enter the facility: product, amount, tenor and purpose.

### Step 2: the CAM is written

Press **Generate CAM**. The progress bar shows each part. The CAM is:
- **a one-page Decision Summary**, built only from data with no AI wording;
- **eight sections**: borrower; business & industry; financial performance; repayment & stress; the
  facility; conduct & compliance; risks & challenges; security, terms & recommendation.

It takes about 30 seconds with the AI. You can also **upload the bank's own CAM** instead, and an agent
reads it.

About 40 of the 46 fields fill in by themselves, each with its source. The chat asks you only for
what no agent could find, such as the banking arrangement.

### Step 3: read the risk strip

Under the proposal header, the **risk strip** shows at a glance:
- **The engine's verdict:** Approve, Refer or **Decline**, with the internal rating.
- **Hard rules:** rules the bank never bends, e.g. "KYC must be complete". A failed one is shown in red.
- **Key ratios against policy:** each ratio is green (within), amber (close) or red (outside) the bank's limit.
- **Size and quality of the numbers:**
  - the *sustainable limit*;
  - *earnings quality*;
  - *revenue truth*;
  - *early-warning flags*.

If the loan is larger than the sustainable limit, the strip says why. Where a smaller amount or a
longer tenor would pass, it offers a **one-click fix**.

### Step 4: Underwriting

The Credit Underwriter sees:
- **Key Risk Challenges.** The *Credit Challenge Agent* argues against the proposal. Each challenge says
  *what is wrong*, *why it matters* and the *evidence to ask for*, with buttons for the suggested
  actions:
  - **Set limit / Extend tenor** (where a structure would pass);
  - **Override a figure**;
  - **Return for documents** (remarks already filled in);
  - **Record justification**;
  - **Decline**.
- **Deviation Register.** Every policy breach is listed. Underwriting records a *mitigant* and a
  justification for each before recommending.
- **Credit Copilot** (the chat). Ask "What should I do next?" for numbered steps with buttons. Ask
  "Should the amount be reduced?" and it shows the arithmetic. You can also change a figure in the
  chat: "change EBITDA to 35900 because the one-off gain is excluded".

If the engine recommends **Decline**, or a hard rule failed, moving the proposal on needs a **written
justification**. The next officer sees it, and it goes into the audit trail.

### Step 5: Sanction

The Sanctioning Authority:
- agrees or returns **each figure Underwriting changed**;
- approves or rejects **each deviation**.

**Sanction** stays disabled until all of these are done. A failed hard rule **cannot** be approved as a
deviation (bank policy). The proposal must be returned for the missing evidence, or declined.

### Step 6: CAD and disbursement

CAD receives a drafted **sanction letter**, the list of conditions and a prepared release request.

Documents can be uploaded on screen or in the chat. The agent checks each one, e.g. "names the
borrower, recognised as a board resolution", and ticks what it can verify. CAD confirms the rest.
Conditions due after release, such as charge registration within 30 days, are tracked with due dates.

Disbursement Operations runs the final checklist and releases. In this demo no payment system is
called.

---

## 4. What you can download

| Report | Where | What it contains |
|---|---|---|
| **CAM (PDF)** | "CAM" button on the proposal | The full CAM. Its first page is the *live* Decision Summary: answers to challenges, the deviation register, justifications, who decided what, and how sure each key figure is |
| **Audit Trail Report** | "⋯" menu | Every decision and who made it; every field's source; every change and who agreed it; the engine's verdict; the deviation register; the AI used; the full event log and chat |
| **Sanction letter** | After sanction | Draft for CAD to review |
| **TAT & Productivity** | Left menu | Decisions, time to sanction, data auto-filled, proposals that went ahead against the engine, where proposals wait, quality of decisions |

---

## 5. What the system will not do

- It never approves, sanctions, declines or releases money. A named person does, with remarks.
- It never invents a number. Figures come from documents, records or fixed calculations, and every one
  shows its source.
- It never hides missing information. A check it could not run says **"Not checked"** or **"Not
  verifiable"**, never "pass".

---

## Glossary

| Term | Meaning |
|---|---|
| **LOS** | Loan Origination System: the software a bank uses to process a loan request from start to release of money |
| **CAM** | Credit Appraisal Memorandum: the report that analyses a borrower and recommends whether to lend |
| **Proposal** | One loan request moving through the officers |
| **RM** | Relationship Manager: the bank's contact for the borrower |
| **Sanction** | The formal approval of a loan |
| **CAD** | Credit Administration: the team that collects signed documents before release |
| **Disbursement** | Releasing the loan money |
| **Agent** | A small AI program that does one job (fetch data, read a document, check a figure) |
| **Credit Copilot** | The chat assistant on every screen |
| **Credit Challenge Agent** | An agent whose job is to argue against the proposal, so weaknesses are not missed |
| **Engine verdict** | The credit engine's recommendation: Approve, Refer (to a higher authority) or Decline |
| **Internal rating** | The bank's own grade for the borrower (A best … D weakest) with a score out of 100 |
| **External rating** | A rating agency's grade, e.g. "ICRA AA (Stable)" |
| **Hard rule** | A rule the bank never bends, e.g. KYC must be complete, the company must be active |
| **Policy limit** | A minimum or maximum the bank sets for a ratio, e.g. DSCR at least 1.20 |
| **Deviation** | Going ahead although a policy limit is broken; needs a mitigant and an approval |
| **Mitigant** | Something that reduces a risk, e.g. extra security, a covenant, a cash reserve |
| **Deviation register** | The list of all deviations on a proposal, with mitigants and approvals |
| **Revenue** | Sales in the year |
| **EBITDA** | Operating profit before interest, tax, depreciation and amortisation |
| **PAT** | Profit after tax |
| **Net worth** | The owners' funds in the business |
| **DSCR** | Debt service coverage ratio: cash available ÷ loan instalments and interest due. Below 1 means it cannot pay from its own cash |
| **Interest cover** | Operating profit ÷ interest |
| **Debt / EBITDA** | How many years of operating profit it would take to repay all debt |
| **Current ratio** | Short-term assets ÷ short-term dues |
| **TOL / TNW** | Total outside liabilities ÷ the owners' own (tangible) funds |
| **Sustainable limit** | The largest loan that keeps every policy ratio within its limit |
| **Earnings quality** | How much of the profit is from the main business and backed by cash |
| **Revenue truth** | Whether GST returns and bank statements support the revenue in the accounts |
| **Early-warning flag** | A warning sign of stress or possible fraud found before lending |
| **Bureau** | A credit bureau (CIBIL, CRIF) that reports a company's borrowings and repayment record |
| **CRILC** | RBI's database of large borrowers' exposures; *SMA* marks accounts showing stress |
| **GST** | Goods and Services Tax; its returns show a company's sales |
| **KYC** | Know Your Customer: identity documents of the company and its signatories |
| **LEI** | Legal Entity Identifier: a global company ID (GLEIF) |
| **MCA** | Ministry of Corporate Affairs: India's company registry |
| **CIN / PAN / DIN** | Company ID / tax ID / director ID |
| **Sanctions screening** | Checking the company and directors against government sanctions lists |
| **FSV** | Forced-sale value: what security would fetch in a quick sale |
| **Security cover** | Security value ÷ loan amount |
| **Covenant** | A promise in the loan agreement, e.g. keep DSCR above 1.2 |
| **Condition precedent / subsequent** | A document needed before release / within a set time after release |
| **TAT** | Turnaround time: how long a proposal takes |
| **SLA** | The target time for each stage |
| **API** | A way for one computer system to ask another for data automatically |
