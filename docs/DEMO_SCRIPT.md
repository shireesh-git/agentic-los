# Demo script

Three short journeys that show what is different. Start the app (`python run.py`) and open
`http://localhost:8001/los`. Sign in by choosing a workspace; use the sign-out icon (top right) to switch
role. To repeat a journey, open the proposal's "⋯" menu and choose **Reset borrower**.

| Journey | Borrower | Shows | Time |
|---|---|---|---|
| A | Infosys (healthy) | A clean proposal from start to release, with most fields filled by agents | 10 min |
| B | Madras Fertilizers (weak) | How the system stops a bad loan: verdict, challenges, sustainable limit, deviation register, Copilot | 10 min |
| C | A new prospect (Dixon Technologies) | Data agents fetch what they can online and ask for the rest | 10 min |

---

## A. Infosys: a clean proposal

1. **Origination** (Ananya Rao, RM).
   - **Initiate Proposal** → Existing borrower → *Infosys Limited*, working capital ₹450 Cr → **Initiate**.
   - **Generate CAM** and watch the progress bar: analysis agents, then 8 sections.
   - **Point out:**
     - the risk strip (verdict *Refer*, rating A, all ratios green);
     - about 40 of 46 fields filled, each with its source and confidence;
     - the chat asks for just one thing, the banking arrangement.
   - Answer it, then **Submit for Underwriting**.
2. **Underwriting** (Rahul Mehta).
   - In the chat: "change EBITDA to 35900 because the one-off gain is excluded". The CAM is now out of
     date: **Re-run CAM** rewrites only the sections that use EBITDA.
   - **Recommend for Sanction**.
3. **Sanction** (Vikram Shah).
   - The change is shown, and must be agreed (**Concur**) before **Sanction** is enabled.
   - **Sanction**.
4. **Credit Admin** (Meera Iyer).
   - Sanction letter drafted; conditions listed; release request prepared.
   - **Add demo executed documents**: the agent checks each one.
   - **Submit Disbursement Request**.
5. **Disbursement** (Arjun Nair). The compliance checklist passes → **Authorise Release**.
6. **Show:** "⋯" → **Audit Trail Report**, the **CAM** PDF (first page: Decision Summary), and
   **TAT & Productivity**.

## B. Madras Fertilizers: stopping a weak loan

1. **Origination.** Initiate Madras Fertilizers, working capital ₹240 Cr → **Generate CAM**.
2. **Point out the risk strip:**
   - **Decline**, rating D;
   - two **hard rules failed** (KYC incomplete, critical exceptions);
   - four ratios **outside policy**.
3. **Point out Size and quality:**
   - **Sustainable limit ₹0**: leverage, interest cover and DSCR are already outside policy, so no amount
     or tenor passes;
   - **earnings quality 75**: other income is 110% of pre-tax profit;
   - **4 early-warning flags**.
4. **Submit for Underwriting.** It asks for a **written justification**, because the engine says Decline.
5. **Underwriting.**
   - Ask the Copilot **"What should I do next?"**. You get numbered steps, starting with the deviation
     register.
   - Ask **"Should the amount be reduced?"**. You get the arithmetic for each policy limit.
   - In **Key Risk Challenges**: each one says what is wrong, why it matters and what evidence to ask
     for. Try **Return for documents**: the remarks are already written.
   - **Recommend for Sanction** is blocked until each deviation has a mitigant. Record them in the
     **Deviation Register**, then recommend.
6. **Sanction.**
   - Approve the four ratio deviations.
   - **Sanction stays disabled:** a failed hard rule is not deviable under bank policy. Decline or return.
7. **Analytics.** **TAT & Productivity** shows "1 proposal moved forward against the engine".

## C. A new prospect: Dixon Technologies

Prepare the documents once: `python test-documents/dixon_technologies/prepare.py`. It downloads the
public annual reports and the rating rationale, and generates the demo files.

1. **Origination** → **Initiate Proposal** → *New-to-bank prospect*.
   - Name *Dixon Technologies (India) Limited*.
   - Working capital ₹250 Cr.
2. **The Data Sources panel.** Five agents run in parallel:
   - the **LEI** comes from GLEIF (live);
   - **sanctions screening** runs against the OFAC and UN lists (live);
   - **adverse media** comes from GDELT (live; if rate-limited, it shows "unavailable");
   - the rest are not connected, so the chat asks for one document at a time.
3. Upload from `test-documents/dixon_technologies/`:
   - `demo/mca`, `public/` (two annual reports) and `demo/kyc`;
   - then the bureau, bank statement, GST and rating documents.
4. **The verification agent.** It cross-checks the sources (CIN, PAN, reconciliation, GST and bank against
   revenue) and flags what needs review:
   - other income is about 90% of pre-tax profit;
   - borrowings from subsidiaries are not in the bureau report.
5. **Generate CAM** and continue as in journey A.
