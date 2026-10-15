# POC Demo Script — Agentic LOS, a new prospect from documents to Exit

> **The point of the demo:** agents populate the case from the borrower's documents and the
> credit engine; people verify by exception and make every decision. The headline is the
> **Agents · populate → verify** panel in the Management MIS: how much arrived pre-filled and
> how much was accepted unchanged.
>
> The same journey runs as an automated test:
> `pytest tests/test_poc_golden_and_e2e.py -k to_exit`.

## 0. Before the demo (5 minutes)

1. Start the app: `python run.py` and open `http://localhost:<port>/los` (the port is
   `server.port` in `config/settings.yaml`).
2. Write the demo documents (a fictional prospect, *Zeta Foods Private Limited*):
   `python scripts/make_demo_documents.py demo_documents`
3. **LLM.** With `active_provider: mock` everything works except AI drafting and reading
   scanned pages. To show the PAN being read off the **scanned** PAN card, use a provider with
   `vision: true` (Claude or Gemini) in `config/llm_providers.yaml`, or install Tesseract.
4. *(Optional)* For the bank's own pilot, replace `demo_documents/` with the borrower's real
   documents in the same folders, and update the golden values in
   `src/devtools/demo_documents.py` with what a person read from them.

## 1. Prospect Sourcing — *Ananya Rao, RM (Prospect Sourcing Maker)*

| Do | Show |
|---|---|
| **New Application → New prospect from documents.** Add `request/request_letter.pdf` (category *Request*), `kyc/*.pdf` (*KYC*), `financials/audited_financials_fy2025.pdf` (*Financials*). | The staged documents. |
| **Read documents with the intake agent.** | Identity and facility filled in, each with *document · page · confidence*. **PAN is left empty** with "scanned page not read" (no vision model): the agent reports, it never guesses. No duplicate on record. |
| Enter the PAN by hand if not read; choose **Sector**; record the sourcing decision; **Create draft**. | The borrower is registered without invented identifiers. The application opens and the **preparation agent** runs: lanes *identity · checks · intake* in parallel. |
| **Accept all high-confidence**. Record the manual checks (CRILC, KYC, MLRA). **Submit to IP Note** (remarks required). | Field store: "13 of 21 auto-populated · verified · % accepted unchanged". |

### 1a. Variant: start from a CAM

- **Bank's CAM:** in step 1, also add `cam/credit_appraisal_memo.pdf` (category *Cam*). After reading, the CAM card
  shows the 13 sections and 13 values the CAM intake agent read. The PAN is found in the CAM's text even though the
  PAN card is a scan. Create the draft: the IP Note opens with the bank's narratives, terms, covenants and security.
- **Workspace CAM:** for an existing borrower (e.g. Apollo), generate the CAM in the CAM workspace (`/`), then
  **Start LOS application**. The facility comes from the CAM, and the IP fields are filled the moment the draft is created.

## 2. IP Note — *Karan Malhotra, RM*

| Do | Show |
|---|---|
| **Prepare with agents** (the *Agents · verify by exception* card). | Lanes: *credit case → checks → populate → IP Note*. The credit pipeline runs on the uploaded audited statement (revenue ₹312.40 Cr, not the ₹316.50 Cr total income). The reconciliation agents write the CMA, pricing (labelled demo) and proposal narrative; the IP Note is drafted. |
| In the verify panel: **Confirm selected** for the pre-ticked fields; read and confirm the drafted narrative. | Decision-driving and drafted fields are never pre-ticked. |
| **Recommend IP proposal** with remarks. | The IP Note gate checks blocking due diligence and the IP documents. |

## 3. Review, allocation, Risk Maker, committees

1. **IP Note VP Review → CRP allocations** (approve / allocate with remarks).
2. **Risk Maker — *Neha Kulkarni / Arjun Menon, Risk Analyst*:** *Prepare with agents* reuses the
   pinned credit case. In the verify panel, **Change…** a CMA revenue figure (with a reason) to
   show the **feedback loop**: the credit case re-runs automatically with the person's value,
   and the ratios follow.
3. **Risk review, EVP, IP Sanction Committee** (sanction ₹45 Cr with remarks).
4. **Application Processing → LPF VP AP Review**: the step asks for the **material-information date**
   (a decision field). Show that a reviewer **cannot edit** the proposal (read-only).
5. **Risk Maker (AP), Post-rating, EVP, Recommendations Committee, the ES process (4 steps), DMD Approval, Committee Sanction.**

Along the way: **Defer** on a maker step (with a date) shows the on-hold state with the SLA
paused and only *Reactivate* offered; **Drop** needs a reason.

## 4. Post Sanction — *Farah Sheikh (POS Maker)*

| Do | Show |
|---|---|
| Upload `legal/signed_sanction_letter.pdf` and `legal/facility_agreement.pdf` (category *Legal*). **Prepare with agents**. | The consent form arrives **pre-filled**: accepted by *Rohan Desai*, 05-Nov-2026; agreement dated 10-Nov-2026. |
| Generate the sanction letter; **Record sanction consent**; clear the CPs; review the material change (new documents since sanction); **Submit**. | Saving the form verifies the values: the field store records them as *confirmed*. |
| **Post Sanction Checker:** *Recommend for disbursement*. | |

## 5. Disbursement — *Lakshmi Narayan (DIS Maker)* → Exit

| Do | Show |
|---|---|
| Upload `request/drawdown_request.pdf`; **Prepare with agents**. | Tranche and beneficiary **pre-filled**: ₹20 Cr, value 20-Nov-2026, account and IFSC. |
| Record the beneficiary and the tranche (as pre-filled), complete the disbursement record and memo; **Submit**. | CIF, limit and CBS security numbers are **demo values**: core banking is not integrated. |
| **Checker → Disbursement VP Review → Final Approval**: *Approve disbursement*. | **Exit**. |

## 6. The headline — *Sunil Chopra (EVP)* → Management MIS

**Agents · populate → verify**:
- the share of fields auto-populated;
- the share verified by people;
- **accepted unchanged**;
- *values nobody had to type*;
- agent preparations and their average time;
- feedback re-runs;
- prospects sourced from documents.

The per-domain table breaks these down by sourcing, CMA, narrative, post-sanction, disbursement and so on.

## What is demo data (say it in the room)

- Bank systems (CBS, bureau, MCA, screening) are labelled demo services.
- The rating, RAROC, pricing and authority matrices are labelled demo models.
- The sign-in is a picker.
- Payment execution is outside the LOS.

These are the integration and model work in [ROADMAP.md](ROADMAP.md)
sections 4 and 5.
