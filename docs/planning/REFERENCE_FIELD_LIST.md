# Reference Field List: the Bank's Screens vs the Agentic LOS (R-0)

> **Status:** 13-Oct-2026. Field-level pass over the screenshots in `reference/` (IP Note training deck,
> AP training deck, Post Sanction and Disbursement manual), done for S7.
> **How it was read:** every screen that shows fields was read from its screenshot. Where only the
> slide or page text was read, the row says *(text)*.
> **Legend:** `*` mandatory on the bank's screen · ✅ in our build · ◐ partly (different shape or
> fewer values) · ✗ missing · 🤖 an agent pre-fills it.

This list complements [REFERENCE_JOURNEY_GAP_ASSESSMENT.md](REFERENCE_JOURNEY_GAP_ASSESSMENT.md),
which compares at section level. The **field gaps found here** are collected in §6.

---

## 1. Prospect Sourcing (IP deck, slides 5–14)

| Section | Bank fields | Ours |
|---|---|---|
| Header | Name of the Applicant, Constitution, Sol ID, Branch, Stage, Prospect Creation Date, Ageing (Days) | ◐ application id, borrower, stage, SLA and turnaround; no Sol ID |
| Sourcing Details | Prospect Received date*, Prospect Creation date, Prospect Created by, Source*, Sourcing Branch*, Prospect Owned By (Primary)*, Sol ID, Sector*, Sub Sector*, **Sub Sub Sector*** | ◐ sector 🤖, subsector; ✗ received date, source, sourcing branch, owner, Sol ID, sub-sub-sector |
| Entity Details | Whether Incorporated*; grid: Existing/New, Relationship, Customer ID, Entity Name. Pop-up: Existing/New, Entity Type, Whether Incorporated*, Constitution*, CIN* (Validate CIN), Date of Incorporation, PAN* (Verify), Entity Name*, Dedupe Check → Status + **LOS Matches** grid (Customer ID, Entity Name, Entity Type, Work item No, Current Workstep, Whether Rejected), Relationship*, GSTIN* (Verify GST) | ✅ identity 🤖 from documents, dedupe with LOS matches, CIN / GSTIN checks (demo); ◐ "Whether Incorporated" not asked |
| Facility Details | Type of Proposal; Product Type, Facility Nature*, Facility Type, Currency, Proposed Amount / Limit, Equivalent INR, Tenor (Years), Tenor (months), Total Tenor, Conversion Rate, Is proposed facility Adhoc | ✅ 🤖 type, nature, amount, tenor, purpose, ad hoc; ◐ currency / conversion (INR only), tenor in months only |
| Prospect Discussion Details | grid: Prospect Status, Date of Discussion, Participant Details, Discussion Remarks; Project Type, Funding Type; Project details in brief (RTE) | ✅ |
| Decision | Decision* (**Defer · Submit · Drop**), Decision Remarks | ✅ ◐ we also offer *Withdraw* |

## 2. IP Note Processing (IP deck, slides 26–77)

| Tab / section | Bank fields | Ours |
|---|---|---|
| Sourcing Details | as PS, plus **LPFG Analyst***, **LPFG Senior Analyst***, Prospect Owned By (Secondary)* | ◐ analyst assignment exists; ✗ the LPFG analyst pair and the secondary owner |
| Entity Details (pop-up) | Existing/New*, Entity Type*, Relationship*, Whether Incorporated*, Constitution*, CIN*, PAN*, Entity Name*, Date of Incorporation*, Verify PAN, Dedupe, Status, Customer ID, GSTIN*, **Whether Foreign Entity***, **Whether NBFC***, **Whether Govt Entity***, Borrower Since | ✅ identity; ◐ Yes/No flags partly (`entity` flags); ✗ foreign / NBFC flags |
| Capital market and MCA | Fetch Capital Market Details: As on date, 52-week high / low, Mkt cap, Current price; Fetch MCA: E-filing status, Company name, last updated dates, last FY end, last filing date, MCA status; ETB-Type; **TAN (Verify TAN)**; Country of Incorporation; **LEI Number, LEI Expiry Date***; Company email / phone / website, short name, Business Type, **RBI Sector**, Govt-sponsored schemes | ◐ MCA and LEI as checks (demo); ✗ capital-market fetch, TAN, RBI sector, contact fields |
| Industry and group | Industry, **IRAC Classification** (auto), **Activity***; Name of Group, RBI Group Code, LMS Group ID, Group Dealing Since, Geographic concentration | ◐ sector / group from the record 🤖; ✗ IRAC classification, activity code, RBI group code |
| Address / contacts | Address grid: Address Type, **Source** (CBS / GST / MCA), lines, landmark, PIN, city, state, country; **Key Person**: salutation, name, designation, mobile, email | ◐ addresses with source on parties 🤖; ✗ key-person contacts |
| Proposed Facility (pop-up) | **Parent Facility***, Product Type*, Facility Nature*, Facility Type*, LOS Facility ID, Currency*, Amount*, **Moratorium (Years / Months)***, **Repayment Period (Years / Months)***, Total Tenor, Detailed Facility Purpose, Reimbursement Allowed, **Expected Date of First Disbursement***, **Whether secured?***, **Takeover Case***, Adhoc | ◐ type, nature, amount, tenor, purpose, moratorium (facility repayment); ✗ parent facility, first-disbursement date, secured flag, takeover flag |
| Deal and existing loans | **Deal details*** (RTE), Indicative / Tentative Pricing (RTE); **Borrower Existing Loans (LMS)** grid: account, sanctioned, outstanding, *to be considered in total exposure*, disbursed, ROI, last disbursement; **Existing Bond Exposure from FT**; Additional exposure proposed, Existing exposure, Total proposed exposure; Trigger Commercial Bureau | ◐ exposure totals 🤖; ✗ LMS / FT grids, deal-details RTE |
| Shareholding / ownership | As on Date; **Shareholding Pattern as per MCA** (shareholding of, name, type, no. of shares, amount, % holding, % pledged); **Beneficial Owner** grid (name, ID type, PAN, DOB, Aadhaar); **Ownership Details*** (RTE) | ◐ promoter / institutional / public % 🤖 (S9), parties with ownership; ✗ MCA pattern grid, BO identity fields |
| Associates / group | grid: Entity Name, Activity, Relationship; *SMA / NPA status* (RTE); *dealings with our bank* (RTE); **Tangible Net Worth of the Group**, **Leverage of the Group**, **Credit Risk Index of the Group** tables; Exposure to Group | ◐ group entities 🤖; ✗ group TNW / leverage / credit-risk-index tables |
| Verification Checks | Initiate / Refresh; MCA Check, CIBIL Commercial Bureau, LEI, CRILC (Manual), **Name Screening** (by name and by ID: status, date, match found, ageing, Trigger) | ✅ (15 checks, 90-day ageing, exception route) |
| Financials | CMA per entity (spreadsheet: audited / provisional / projected years, ~100 rows), Financial Highlights | ◐ CMA rows (8) per entity 🤖, projections 🤖 (S9); ✗ the full CMA row set and spreadsheet upload |
| Risk Rating | External: available*, grid (rated for, rated by, Fetch Rating, type, date, instrument, amount, rating, **our exposure included**, our exposure amount, outlook, remarks). Internal: **Group Rating***, grid (rating for, relationship, rating, date). RAROC (optional at IP) | ✅ 🤖 external (S9), internal 🤖, RAROC 🤖 (S9); ◐ outlook / exposure-included columns |
| RAROC (pop-up) | Facility ID*, nature, product, amount, benchmark, NBFIR, NLR, CRP, SP, PAPM interest, **Wt Avg Tenor***, fees %, **Payment Frequency***; calculation block (exposure, PAPM rate, annualised rate, cost of funds, NII, income on capital, fee income, net income, CRAR, cost of capital, expected loss, …) | ◐ labelled demo model (amount, rate, PD / LGD, capital); ✗ the bank's PAPM components |
| Other Proposal Info | **Brief detail of the borrower / business background***; **Analysis of marketing arrangements / off-take***; **Market enquiries on sponsor, promoter and borrower / corporate action details***; **Other information (key strengths and weakness)***; **Key Risk*** | ◐ 🤖 business, marketing, strengths, weaknesses, key risks (S9); ✗ **market enquiries** |
| Exposure Norms | Fetch Bond Exposure → Listed / Unlisted / State-owned (book value, sanctioned-not-committed, available); Fetch Loan Exposure → by constitution, sector, state (sanctioned, disbursed, outstanding); LEF / ERM summary | ✅ (demo fetch); 🤖 nil for new-to-bank (S9) |
| Banking Arrangement | Banking arrangement for (entity), **Type of Banking: Sole / Consortium / Multiple**; Comments on banking arrangement*; **Borrower's banking arrangement***; **Sponsor / promoter's banking arrangement*** | ◐ type 🤖 (S9), banks; ✗ the three RTEs |
| Project | grid: Project ID, Name, View Details; Project other information: Details*, Address / Location*, **Sources of Equity and Quantum***, Whether down-sell, Other observations, **Comments on acceptability on terms***, Any other relevant information*, Project / Balance-sheet funding, Project Type, NIP / NMP, Approval, Status, **Partly outside India***, **PPP / Non-PPP***, Expected SCOD, Actual COD, Original DCCO*, Revised DCCO*, Site PIN | ◐ 🤖 name, purpose, type, location, viability, DSRA (S9); fields for DCCO, NIP; ✗ PPP, outside-India, SCOD / COD, equity sources |
| ESMS | Date of Screening*; **Screening checklist against NaBFID's Excluded Activities (Annex 5-2)**: forced / child labour; illegal activities or international bans; weapons of mass destruction; … (Response Yes / No, Remarks) | ◐ 🤖 screening (S9) on **5 generic statements**; ✗ the bank's Annex 5-2 list |
| Security (pop-up) | Existing/New, Category, Type*, Sub-Type, LOS Security ID, Facility ID*, Facility Name, Provided By, **Security Ownership** grid (owner, type, CIF, %), Description*, **Shared pari-passu?**, NaBFID's share of value, Priority of Charges* | ✅ 🤖 from the case collateral; ◐ ownership grid, sub-type |
| Terms & Conditions | Upload Termsheet, View Termsheet, **Key Terms and Conditions** (RTE), View History | ✅ term sheet; 🤖 key T&C draft (S9) |
| Pricing & Fees | Fees: Nature of Fees (facility / common), Fee Type, Currency, Computation Basis*, Applicable Fee, Applicable Fee %, Remarks. Pricing: product, facility type / ID, **Benchmark Type*** (e.g. NLR 1 year), Benchmark Rate, Recommended Spread, **Proposed Spread**, Applicable ROI, **Concession Requested**, Borrower Risk Rating, **Recommended CRP**, **Recommended SP** | ✅ 🤖 fees (S9), benchmark / spread / rate 🤖; ✗ concession flag, CRP / SP split |
| Documentation | Document upload; System generated documents: **Credit Appraisal Memorandum***, **Sanction Letter*** (Generate / View) | ✅ |
| Decision | **IP Sanction Committee** (computed, e.g. CEAC1); Deviations: Check Deviation, grid (**Nature of Deviation**, Deviation Type, Description, Others Name); **Broad Compliance with Credit Policy Guidelines*** (RTE); Decision* (**Recommend · Defer · Drop**); Remarks History (date / time, workstep, user, decision, remarks) | ✅ S7: computed committee, auto + manual deviations, remarks history, Recommend · Defer · Drop; ✗ the *broad compliance* RTE; ◐ committee names are a demo matrix |

## 3. Application Processing (AP deck)

Sections already in §2 repeat at AP, carried forward and editable. AP adds or changes:

| Tab / section | Bank fields | Ours |
|---|---|---|
| Verification Checks *(text, slides 17–31)* | CRILC (Manual), CIBIL, **CRIF**, Legal Litigation, **EWS** (total / open / closed triggers), **Central Fraud Registry (Manual)**, **CEIB**, MCA, GSTIN, LEI, **Enhanced Due Diligence** (risk parameters), **UDIN** (OTP), **KYC** (POI / POA uploads), Name Screening, **MLRA Rating** | ✅ all 15 checks (several demo); ◐ EDD parameter list, OTP |
| Financials *(text, 32–35)* | Financial analysis per entity; CMA in ₹ Cr (actuals and projections); Highlights; External rating | ✅ 🤖 actuals + projections |
| Risk Rating *(text, 36–40)* | Internal per entity; **Calculate Group Rating** / trigger-based review; RAROC (facility title, weighted average tenor, payment frequency); **CRP Observations** (LPF Note, Rating Report, CRP Note uploads) | ✅ 🤖 (RAROC agent, S9) |
| **Unit Visit Details** (slide 42) | Entity Name, Address Visited, Date of Visit*, Place of Visit, Name(s) of Visiting Official(s) + designation, **Observation** (e.g. Satisfactory), Upload / View Unit Visit Report, Remarks | ✗ **G-F1** |
| Proposal Info (slide 43) | Proposal in brief (amount, purpose, tenor, pricing, security); Marketing arrangement of finished goods; Market enquiries; **Corporate Governance Standards***; **Whether promoters' shares pledged***; **Corporate actions done / proposed (merger, demerger, restructuring, sale of undertakings)***; Industry risk / outlook; **Whether in SMA / NPA / restructured / financial difficulty / RFA / settlement***; Key strengths and weakness; Key Risk*; **Whether all committee directions complied***; **Whether deferred / rejected in the past***; **Unhedged exposures and risk-mitigation plan***; **Reason for proposal being submitted to committee***; **Justification for the proposal*** | ◐ 🤖 summary, marketing, governance, industry, strengths / weaknesses, key risks, other material information (S9); ✗ the 9 bank-specific RTEs in bold |
| Exposure, Annexures *(text, 44–56)* | Exposure Norms; Annexure IX (conduct + financial-difficulty testing); Annexure XI compliances; Inter-Firm Comparison; Losses incurred by bank; Banking Arrangement (Multiple / Consortium); Connected Lending; Annexure VI; Annexure XIII; Annexure XIV; Other Annexure; CAM Abbreviations | ✅ workspaces; 🤖 conduct, inter-firm (S9) |
| Project *(text, 57–62)* | Project details; Project-specific (EFG testing, TEV); Common project information (repayment, DSRA, escrow / TRA …); Critical risk factors; Project status (stage, current status) | ✅ fields; 🤖 core fields (S9) |
| ESMS (slides 64–65) | Pre-Screening; **E&S Risk Categorisation**: Applicable ES risk categorisation* (Project / Entity), checklist (Annex 5-4): CPCB category, coastal / eco-sensitive zone, involuntary resettlement, adverse community impact, monuments, E&S litigation (NGT), EIA category — each with Response, **Source of Information**, Remarks. **ESMS Recommendation**: Proposed E&S Category (as per ESMS team), Introduction, Proposal, Company E&S Risk Assessment, Summary, ESDD Requirement, **ESDD Applicable** grid (project, ESDD recommended, E&S committee resolution), **Additional conditions recommended by ESMS**, Committee Recommendations, Annexure 1 E&S factors | ◐ category, CPCB, coastal, resettlement, impact, litigation, ESDD, introduction, summary, additional conditions, committee recommendation; ✗ monuments item, EIA category, per-item source, ESDD grid |
| Terms & Conditions (slides 66–70) | **Pre-Commitment** (Sr. No., Existing/New, Facility Title, Description); **Pre/Post Disbursement** (+ upload / view termsheet); **Covenants – Annexure III**: Financial (Existing/New, Applicable Party, Covenant Name, …), Non-Financial (Existing/New, Applicable Party, Name, Type); **General**; **Facility Specific** | ✅ S9 T&C authoring 🤖 (categories PC, CP / PD, FC / NC, GC, FS); ◐ *Existing/New* and *applicable party* columns |
| Security (73–74) | Security details grid (type, category, sub-type, **NaBFID apportioned value**, facility); Status of security creation for existing facility*; Remarks on estimated timelines for creation and perfection*; Security Summary; **Comments on change in security from the last sanction***; **Whether security held by security trustee*** | ✅ details 🤖, cover; ✗ the creation-timeline and change remarks |
| Pricing & Fees *(text, 75–80)* | Previously approved fees + new; pricing; **Repayment Schedule (Tentative)** for term loans | ✅ 🤖 fees |
| EWP Management *(text, 81–85)* | LIA, LIE, ST, ESDD, LLC (consultant, contact, email, phase, request) | ✅ |
| Decision – Other Approvals (slide 88) | Approval Matrix; **Sanction Committee** (e.g. EC / Board); Deviations (Nature: **Manual / Auto**, Type, Description); **Deviations / waivers / relaxations granted from the last review***; **Any other matter requiring committee approval, with justification***; **Compliance with the observations of the IP approving authority***; Broad compliance with credit policy guidelines | ✅ S7: committee, manual + auto deviations; ✗ the four RTEs |
| Decision & Remarks (slide 89, and every AP review 90–95) | **Date of receipt last material information***; **Any other matter to be highlighted to Committee***; Proposal for confirmation / ratification; Decision*; **Purpose to seek approval***; **Significant changes since the last review and material disclosures***; Remarks History | ✅ S7 (G-W6): the same record, same labels and mandatory flags, at every AP maker / review step, carried forward |
| EVP AP / Recommendations Committee (96–97) | Decision: **Recommend for Sanction · Rework**; **CEAC Recommendation***; **Minutes of Committee Meeting (Upload / View)** | ✅ S7 wording; minutes as text; ◐ minutes upload |

## 4. Post Sanction (POS manual, pages 3–22)

| Section | Bank fields | Ours |
|---|---|---|
| Workflow (p4) | … Recommendations Committee → **CRP ES Maker → ES Preparation → ES Review → ES Recommendation** → **Committee Sanction** → Post Sanction Maker … | ✅ S7; DMD Approval is in the AP manual's order only (switchable) |
| External rating (p5) | View / capture ratings; **credit weaknesses / observations from the rating rationale** | ◐ ratings; ✗ credit-weakness field |
| Pre-Commitment T&C (p6–7) | Facility Title, Description; compliance update: **Complied / Not Complied**, reason for non-compliance, remarks, documents | ◐ conditions carried from AP (S9); vocabulary satisfied / deferred / waived (G-F3, S10) |
| Pre / Post Disbursement T&C (p8–9) | status Complied / Not Complied, documents, remarks | ◐ as above |
| Covenants – Annexure III (p10–12) | Financial: Applicable Party, Covenant Name, Description, **Stipulated Value**, Due Date, **Testing Frequency**; Non-financial: Type, Name, Description, Due Dates, Frequency, Remarks | ✅ 🤖 stipulated value and frequency from AP (S9); covenant monitoring |
| Facility-specific T&C (p13) | Facility Title, **Applicable Facility Sub-Type**, Description | ✅ FS conditions with facility |
| Sanction Consent (p14) | Upload the signed **Sanction Letter** (mandatory) | ✅ 🤖 the agent reads the signed letter |
| Facility Execution (p16–18) | Sanctioned Amount, Execution Status, Facility Agreement Date, Committed Amount, partial → Balance (auto) | ✅ 🤖 |
| Decision (p19, p22) | Maker: **Application Withdrawn / Modification Proposed / Submit**, significant changes. Checker (read-only): **Recommend for Disbursement / Recommend for Modification / Rework / Drop** | ✅ S7 |

## 5. Disbursement (POS manual, pages 23–60)

| Section | Bank fields | Ours |
|---|---|---|
| Rating / T&C catch-up (p24–29) | External rating re-trigger; complete missing pre-commitment, pre/post, **CP to subsequent disbursement** (facility, frequency, due date), covenants, facility-specific | ✅ conditions; ◐ the catch-up of missing items |
| Disbursement Memo (p30) | Generate and review (mandatory) | ✅ |
| CIF / Limit / Account / Security IDs (p31–34) | CIF create or update; Limit IDs (TOT, FB, NFB), Limit Suffix, Next review date, Loan Account; **Create CBS Security No** for every security | ✅ (demo references) |
| Beneficiary (p36–37) | Facility Title, Beneficiary Type, Name, Account Number, **Bank Name, Branch Name**, IFSC, **Payment Mode**, **Amount** | ◐ 🤖 name, account, IFSC from the drawdown request; bank, branch, mode, amount (S10) |
| Fee collection (p38–40) | Particulars, Amount Due, GST, Total, Amount Received, Balance, Actual Receipt Date, due date, remarks; NFB fee details | ✅ fields; 🤖 carry-forward from fees (S10) |
| Repayment Schedule – Annexure I (p41) | moratorium, tenure, instalment frequency, interest payment | ✅ fields; 🤖 carry-forward (S10) |
| Project Status (p42) | Change in DCCO, Revised DCCO, repayment shift, change of scope, cost overrun, means of finance | ✅ |
| Interest Details (p43–44) | Benchmark (e.g. NLR), spread, benchmark rate, reset frequency / date, additional interest (non-perfection), effective rate, penal rate, interest start date | ✅ fields; 🤖 carry-forward from pricing (S10) |
| Security – Annexure IV (p45–46) | Type, facility, description, **created / perfected**, creation date, valuation date, proposed value, **CERSAI**, **ROC filing** | ✅ fields; 🤖 carry-forward (S10) |
| Arrears (p47–48) | Any arrears (Yes / No); type, amount, currency, due since, remarks | ✅ |
| Annexures (p49) | Drawdown Request, Drawdown Schedule Report, Interim SOP (Annexure II) checklist "In Compliance" | ✅ 🤖 drawdown request read |
| Decisions (p50–60) | Maker: Submit + matters for committee, confirmation; Checker: **Submit / Rework**; VP Review: **Submit / Rework** + significant changes; Approval: **Submit → Exit** | ✅ S7 wording; ◐ we keep *Rework* at the Disbursement Approver (a control the manual does not show; kept pending the bank's view) |

---

## 6. Field gaps found in this pass

> **Status (S10, 13-Oct-2026):** F-1, F-2, F-3, F-4, F-5, F-6, F-9 and F-10 are built; F-7, F-8 are open; F-11 and
> F-12 need the bank's models and approval matrix.

Ordered by how often they block a real proposal. **Agentic** = an agent could pre-fill it from a source we already have.

| # | Gap | Where | Agentic? | Proposed sprint |
|---|---|---|---|---|
| F-1 | **The 9 bank-specific AP proposal RTEs** (pledged shares, corporate actions, SMA / NPA / RFA status, committee directions, past deferral / rejection, unhedged exposure, reason for committee, justification, market enquiries) | AP / IP Proposal Info | Partly: SMA / NPA from the bureau check; pledge % from shareholding; past decisions from the LOS history | S10+ |
| F-2 | **Decision RTEs** at IP / AP: broad compliance with credit policy; deviations from the last review; other matters for committee approval; compliance with the IP authority's observations | Decision tab | Partly: policy compliance from the policy engine; IP observations from the IP decision records | S10+ |
| F-3 | **ESMS lists as the bank's annexes**: Excluded Activities (Annex 5-2) and the E&S risk checklist (Annex 5-4, incl. monuments and EIA category), per-item *source of information*; ESDD-applicable grid | ESMS | Yes: the sector rule already screens; needs the bank's list text | S10 |
| F-4 | **Unit Visit Details** (G-F1) | AP | No (a person's visit); report upload read by the intake agent | S10 |
| F-5 | Sourcing-detail fields: received date, source, sourcing branch, owner (primary / secondary), Sol ID, sub-sub-sector; LPFG analyst pair | PS / IP | Owner / branch from the session; sub-sub-sector from the CAM | S10 |
| F-6 | Facility fields: parent facility, expected date of first disbursement, whether secured, takeover case, currency / conversion | IP / AP facility | Secured from securities; dates from the request letter | S10 |
| F-7 | Entity flags and identifiers: foreign entity, NBFC, TAN, RBI sector, IRAC classification, activity code, key-person contacts | IP entity | Yes: MCA / documents | later |
| F-8 | Group tables: group TNW, group leverage, group credit-risk index | IP associates | Yes: the corporate hierarchy and the engine | later |
| F-9 | Security remarks: creation status / timelines, change from the last sanction, held by security trustee | AP security | Partly | S10 |
| F-10 | POS condition vocabulary **Complied / Not Complied** (G-F3); credit weaknesses from the rating rationale | POS | Rating rationale via document intake | S10 |
| F-11 | Pricing split: recommended CRP / SP, concession requested; the bank's PAPM-based RAROC | IP / AP pricing | Needs the bank's models | bank input |
| F-12 | Committee names (CEAC1, EC / Board) from the bank's approval matrix | Decision | Needs the bank's matrix | bank input |
