# Gap Assessment: Agentic Journey vs the Bank's Reference LOS (IP → AP → Post Sanction)

> **Status:** draft for requirement sign-off (13-Oct-2026). No code has been changed for it.
>
> **Reference:** the bank's current, non-agentic LOS training manuals in `reference/`:
> - *User Training: IP Note Processing* (78 slides, which also cover Prospect Sourcing);
> - *AP Training Manual* (97 slides, Application Processing and committee sanction);
> - *Post Sanction and Disbursement Manual* (60 pages).
>
> **Compared with:** this repository (the agentic POC after sprints S1–S6).
>
> **Depth:** this is a **section-level** comparison. It is based on the manuals' slide text and on a
> review of the code (workspace modules, workflow configuration, agent resolvers). The manuals
> are mostly screenshots, and the screenshots carry field-level detail; for example, Sourcing
> Details shows *Source, Sourcing Branch, Prospect Owned By, Sol ID, Sub-Sub-Sector*. A
> field-by-field pass over the screenshots is proposed as step 0 of the build (§7).

**How to read the tables**
- **Built:** what the code has today. Most of the bank's screens were already built as governed workspaces during the earlier UAT remediation (`clientspec.md`), so most gaps are about **pre-fill** rather than missing screens.
- **Agent pre-fill:** whether an agent fills it today:
  - ✅ filled;
  - ◐ partly filled;
  - — a person keys it.
- **Gap:** what is missing against the reference.

---

## 1. Summary

| Area | Screens and sections | Workflow steps | Agent pre-fill |
|---|---|---|---|
| **Prospect Sourcing** | Mostly built. Some sourcing-detail fields missing | Matches | ✅ identity, facility, checks |
| **IP Note Processing** | Built (16 of 16 sections exist in some form) | IP flow is **missing Post Rating VP Review** | ◐ about 9 of 16 sections |
| **Application Processing** | Mostly built. **Unit Visit** missing; **pre-sanction T&C authoring** missing | **ES stages (4) and DMD Approval missing** | ◐ about 8 of 27 sections |
| **Post Sanction** | Built. Condition vocabulary differs | Matches; decision labels differ | ◐ consent and execution |
| **Disbursement** | Built (operational IDs are demo) | Matches | ◐ tranche and beneficiary only |
| **CAM as input** (new) | Not built | n/a | Not built |

**What this means:** the agentic gain is concentrated in Prospect Sourcing, IP Note and Risk
Maker. The AP maker step, the post-sanction terms and the disbursement operational record are
still largely typed by people, although most of that data already exists earlier in the
application or in a CAM. Using a **CAM as an input** is the biggest single lever: one document
can feed most IP and AP sections.

---

## 2. Workflow sequence

### 2.1 In-Principle

| # | Reference (bank) | Ours | Gap |
|---|---|---|---|
| 1 | Prospect Sourcing (RM) | `ps_maker` | — |
| 2 | IP Note Processing (LPFG analyst / RM) | `ip_note` | — |
| 3 | IP VP Review (VP LPF) | `ip_note_review` | — |
| 4 | CRP EVP allocation | `ip_crp_evp` | — |
| 5 | CRP VP allocation | `ip_crp_vp` | — |
| 6 | CRP Risk Observation (Risk Maker) | `ip_risk_maker` | — |
| 7 | CRP VP Review | `ip_risk_review` | — |
| 8 | **Post Rating VP Review** | *missing* | **G-W1: add the step** |
| 9 | EVP Recommendation | `ip_evp` | — |
| 10 | IP Committee Sanction | `ip_sanction` | — |
| — | *Compliance Approval* (exception) appears in the remarks history as a work step | Compliance VP exception (an action, not a step) | Show it in the remarks history (G-W5) |

### 2.2 Application Processing → final sanction

| # | Reference | Ours | Gap |
|---|---|---|---|
| 1 | Application Processing (maker) | `ap_note` | — |
| 2 | VP AP Review | `ap_review` | — |
| 3 | CRP Allocation | `ap_crp_vp` | — |
| 4 | Risk Maker (Risk Observation) | `ap_risk_maker` | — |
| 5 | Risk Review | `ap_risk_review` | — |
| 6 | Post Rating Processing | `ap_post_rating` | — |
| 7 | Post Rating VP Review | `ap_rating_vp` | — |
| 8 | EVP AP Recommendation | `ap_evp` | — |
| 9 | Recommendations Committee (CEAC) | `ap_recommend` | — |
| 10 | **CRP ES Maker → ES Preparation → ES Review → ES Recommendation** | *missing* | **G-W2: ESMS stages** |
| 11 | **DMD Approval** (AP manual) | *missing* | **G-W3: DMD step.** The order is to be confirmed: the AP manual has *ES Process → DMD*, while the POS manual has *ES stages → Committee Sanction* |
| 12 | Committee Sanction | `ap_sanction` | — |

### 2.3 Post Sanction and Disbursement

| Reference | Ours | Gap |
|---|---|---|
| Post Sanction Maker → Checker (read-only) | `pos_maker` → `pos_checker` | Decision labels (G-W4) |
| Disbursement Maker → Checker → VP Review → Approval → Exit | `dis_maker` → `dis_checker` → `dis_vp_review` → `dis_approver` → Exit | Decision labels (G-W4) |

### 2.4 Decisions and remarks (all stages)

| Step | Reference decisions | Ours | Gap |
|---|---|---|---|
| IP Note Processing | Recommend · Defer · Drop | Recommend IP proposal · Defer · Drop · **Withdraw** | Withdraw is extra |
| IP Note Decision tab | **Computed IP Sanction Committee** (e.g. CEAC1); deviations (auto + **manual add**); **remarks history** table | Authority computed and shown; deviations auto only; decision trail | **G-W5** |
| AP maker and every AP review (VP AP, Risk Maker, Risk Review, Post Rating, Post Rating VP) | Decision + remarks + **date of last material information, key matters for the committee, proposal for confirmation/ratification, purpose of seeking approval, significant changes** | Captured only at `ap_review` (3 of these) and as significant changes at the EVP | **G-W6: one standard decision record at every AP step** |
| EVP AP / Recommendations Committee | Recommend for Sanction · Rework; CEAC recommendation; minutes upload | Recommend · Return; minutes + CEAC fields | Labels; minutes as an upload |
| Post Sanction Maker | Application Withdrawn · Modification Proposed · Submit; significant changes | Submit · Propose modification · **Drop** · Withdraw | Drop is extra |
| Post Sanction Checker | Recommend for Disbursement · Recommend for Modification · Rework · Drop | Recommend for disbursement · Recommend for modification · Return · Reject · Drop | Reject is extra; Return should read "Rework" |
| Disbursement Approval | Submit → Exit | Approve disbursement · Return | Return is extra |

---

## 3. IP stage, section by section

### 3.1 Prospect Sourcing

| Reference section | Built | Agent pre-fill | Gap |
|---|---|---|---|
| Sourcing details: received date, source, sourcing branch, owned by, Sol ID, sector / sub-sector / **sub-sub-sector** | Sector, subsector | — | Missing: received date, source, branch, owner, Sol ID, sub-sub-sector (G-08) |
| Entity: incorporated?, DOI, PAN, name as per PAN, **Verify** → CBS customer grid; constitution; **Validate CIN**; GSTIN select + **Verify GST**; dedupe (LOS matches by PAN) | All present; CBS, CIN and GST are demo or format checks | ✅ intake agent + identity lane | Verify / Validate are demo (integration) |
| Facility: product type, nature, type, amount, tenor (years + months), ad hoc | Present (tenor in months) | ✅ from the request letter | Years + months display |
| Prospect discussion: project type, funding type, brief | Present | ◐ (purpose) | — |
| Decision: Submit + remarks | Present | — | — |

### 3.2 IP Note Processing

| # | Reference section | Built | Agent pre-fill | Gap |
|---|---|---|---|---|
| 1 | Sourcing details carried forward + **LPFG analyst / senior analyst** | Assignments exist | Carried forward | Analyst not proposed |
| 2 | Entity details grid: Yes/No flags; **Fetch Capital Market**; Fetch MCA; litigation; **Verify TAN**; **industry classification** (harmonised sector → IRAC); group; addresses with source; key persons | Parties, addresses with source, key-person role; MCA and litigation checks | ◐ parties (directors, group) | Capital market fetch, TAN verify, harmonised/IRAC classification, key-person contacts |
| 3 | Facility details: detailed sub-form, deal-details RTE, **existing LMS loans** grid, exposure computed, commercial bureau | Facilities lifecycle; exposure (demo fetch); CIBIL check | ◐ exposure | LMS loans grid with "consider in exposure"; deal-details narrative |
| 4 | Shareholding (MCA, auto) + beneficial owners; associates / group | Parties with ownership %, beneficial-owner role | ◐ | MCA shareholding pattern not auto; BO ID details |
| 5 | Prospect discussion (carried forward) | ✅ | ✅ | — |
| 6 | Verification checks: initiate all; tick / cross; re-trigger; reports; comments; CRILC manual; name screening 90-day validity; exact/probable match → Compliance exception with borrower justification | All present (15 checks, history, 90-day re-screen, exception) | ✅ run in parallel; settled checks kept (fixed 13-Oct) | Borrower justification captured as remarks; "View report" is demo |
| 7 | Financials: per-entity CMA; **upload CMA sheet** → financial highlights; comments | CMA workspace per entity; highlights computed | ✅ CMA from the statements | CMA Excel upload/import |
| 8 | Risk rating: external (auto from *Save Risk*, instrument-wise), internal (borrower / promoter / sponsor), RAROC (optional at IP; stale on change) | All present (Save Risk is a demo fetch) | ◐ internal rating only | **External rating** not pre-filled; RAROC not auto-computed |
| 9 | Other proposal info: borrower details, business background, industry outlook, **marketing arrangement**, strengths **and weaknesses** | Present (8 RTEs) | ◐ 4 of 8 drafted | Marketing, weaknesses, governance, other material info not drafted |
| 10 | Exposure norms: LEF / ERM summary, committed exposure (LMS), breach alert | Present (demo fetch), breach alert | ◐ | — |
| 11 | Banking arrangement: type, shares (syndication → consortium) | Present | — | Not pre-filled |
| 12 | Project: create and link to a facility; details, location, means of finance, capex, viability, tie-up | Present | — | **Not pre-filled** |
| 13 | ESMS: excluded-activities screening (Yes / No / NA; remarks) | Present | — | Not pre-filled (proposals would need *must verify*) |
| 14 | Security: primary + collateral; NTB new / ETB from CBS; description, priority, apportionment | Present | ✅ from the case collateral | ETB from CBS is demo |
| 15 | Terms & conditions: **upload term sheet**, key T&C RTE, history | Term sheet generated **after** IP sanction | — | Term sheet / key terms at the IP Note step |
| 16 | Pricing & fees: fees per facility; benchmark, recommended spread / RoI, proposed spread → RoI | Present | ◐ pricing (demo grid) | Fees not pre-filled |
| 17 | Documentation: upload by entity and category (checklist, versions); **generate pre-sanction documents** | Present (CAM, executive summary, DD report, ESMS note, IP Note) | ◐ IP Note drafted | — |
| 18 | Decision (see §2.4) | Present | — | G-W5 |

---

## 4. AP stage, section by section

The AP maker sees the IP sections again (carried forward, editable) plus the following.

| Reference section | Built | Agent pre-fill | Gap |
|---|---|---|---|
| Entity: existing/new entity, relationship, customer ID fetch; **PSU / Government entity** (State / Central); **Verify TAN**; addresses auto-fetched (MCA / CBS / GSTIN); key persons (salutation, mobile, email) | Parties | ◐ | PSU flag, TAN, key-person contacts |
| Facility: title, product…; existing LMS loans (*consider in exposure*); **existing bond exposure from FT**; **committed loans** (linked work items, parent facility); trigger bureau; bureau facilities with asset classification | Facilities, exposure (demo), bureau check | ◐ exposure | LMS / FT grids, committed loans, parent facility (G-13) |
| Shareholding / BO (ID type, PAN, DOB, Aadhaar); associates / JV | Parties | ◐ | BO identity fields |
| Verification checks: CRILC, CIBIL (CMR), CRIF, litigation, EWS, CFR, CEIB (Proforma A), MCA, GSTIN, LEI, **EDD risk parameters**, **UDIN (OTP)**, KYC (POI / POA uploads), name screening (including BOs, ageing), **MLRA fetch** | All 15 present (UDIN grid, evidence, re-screening) | ✅ API checks | EDD as a parameter list; OTP is demo |
| Financials: per-entity analysis; CMA actuals **and projections**; highlights; external rating | CMA (audited / provisional / projected) | ✅ actuals | Projections not pre-filled; external rating |
| Risk rating: internal per entity (rating, score, date); **group rating** + trigger-based review; RAROC (weighted tenor, payment frequency); **CRP observations** (LPF note, rating report, CRP note uploads) | All present | ◐ internal rating | Group rating not computed by an agent; RAROC not auto |
| **Unit visit details** (+ report upload) | **Missing** | — | **G-F1: build** |
| Proposal info (summary, purpose, tenure, pricing, security, marketing, governance, industry, risks, strengths / weaknesses) | Present | ◐ 4 of 8 | Remaining narratives |
| Exposure norms (fetch bond and loan exposure) | Present (demo) | ◐ | — |
| Annexure IX: account conduct and financial-difficulty testing | Present | ✅ conduct (existing customers) | FD testing remarks |
| Annexure XI compliances; inter-firm comparison; losses; connected lending; Annexures VI, XIII, XIV; other annexure | Present | — | **Not pre-filled.** Inter-firm comparison could come from the CAM benchmarking engine |
| CAM abbreviations (reference only) | Missing | n/a | Low value |
| Project: details (NIP / NMP, refinancing); project-specific (EFG testing, TEV); common info (repayment, DSRA, escrow / TRA…); critical risk factors; status (stage, cost breakup, means of finance) | Present | — | **Not pre-filled** (TEV report and CAM are natural sources) |
| ESMS: pre-screening; E&S risk categorisation; ESMS recommendation | Present | — | Not pre-filled |
| **Terms & conditions authored before sanction:** pre-commitment, pre/post disbursement, **covenants (Annexure III)**, general, facility-specific | Categories exist, but conditions are **generated at final sanction** from the reassessment; the maker cannot author them during AP | — | **G-F2: T&C authoring at AP**, pre-filled from the reassessment (M6) |
| Security: details, **summary with coverage ratio**, **additional info** (changes since last sanction, security trustee) | Details and cover present | ✅ | Additional-info fields |
| Pricing & fees: previously approved fees + new; pricing vs other banks; pricing change → RAROC alert; repayment schedule (term loans) | Present | ◐ pricing | Fees, schedule not pre-filled |
| EWP management: LIA, LIE, ST, ESDD, LLC | Present | — | — (human) |
| Documentation: pre-sanction checklist; generated CAM, executive summary, DD report, ESMS approval note | Present | ✅ generated | — |
| Decision: other approvals (deviations auto / manual, previous waivers, justification, authority observations); decision record (§2.4) | Deviations auto | — | Manual deviations; decision record (G-W6) |
| Risk Maker: external and internal ratings, group rating, adverse event; decision record | Present | ◐ | G-W6 |
| Recommendations Committee: CEAC recommendation, **minutes upload** | Fields present | — | Minutes as a document |

---

## 5. Post Sanction and Disbursement

### 5.1 Post Sanction Maker / Checker

| Reference section | Built | Agent pre-fill | Gap |
|---|---|---|---|
| External rating view + **credit weaknesses** from the rating rationale | Ratings workspace | — | Credit-weakness field; carry the rating forward |
| Pre-commitment T&C: **Complied / Not Complied**, reason, remarks, documents | Conditions (category PC): open / satisfied / deferred / waived / non-compliant + evidence | — | **Vocabulary** (G-F3); agent proposal from uploaded evidence |
| Pre / post disbursement T&C status update | Category PD | — | Same |
| Covenants Annexure III: financial (party, name, stipulated value, due date, testing frequency); non-financial | Covenant monitoring (FC / NC) | ◐ from the reassessment | — |
| Facility-specific T&C | Category FS | — | — |
| **Sanction consent:** upload the signed sanction letter (mandatory) | Consent + document-registry gate | ✅ the agent reads the signed letter | — |
| System-generated documents | Present | ✅ | — |
| Facility execution: status, agreement date, committed amount; partial → balance auto | Present (lifecycle and balance) | ✅ the agent reads the agreement | — |
| Decision (§2.4); checker read-only | Present | — | Labels |

### 5.2 Disbursement Maker → Checker → VP → Approval

| Reference section | Built | Agent pre-fill | Gap |
|---|---|---|---|
| External rating update / re-trigger | Ratings | — | Carry forward |
| Complete missing T&C; **CP to subsequent disbursement** | Category CPS | — | — |
| Disbursement memo (mandatory) | Present (generate + review gate) | — | — |
| CIF creation / update; Limit ID (TOT, FB, NFB) / loan account; **CBS security number for every security** | Present (demo references) | — | Demo (integration B-3) |
| Facility execution status | Present | ✅ | — |
| **Beneficiary:** facility, type, name, account, **bank, branch, IFSC, payment mode, amount** | Present | ◐ name, account, IFSC from the drawdown request | Bank, branch, payment mode, amount per beneficiary |
| Fee collection (upfront, annual review; GST; received; balance); NFB fee details | Present | — | **Carry forward from pricing / fees** |
| Repayment schedule (Annexure I) | Present | — | **Carry forward from the sanctioned terms** |
| Project status (DCCO change, scope, cost overrun, means of finance) | Project change record | — | Carry forward |
| Interest details: benchmark, spread, reset, additional interest for non-perfection, effective, penal | Present | — | **Carry forward from pricing** |
| Security Annexure IV: created / perfected, dates, value, **CERSAI, ROC** | Securities lifecycle | — | Carry forward |
| Arrears (any arrears? amount, due since) | Present | — | — |
| Annexures: drawdown request, drawdown schedule report, Interim SOP (Annexure II) | Present | ✅ drawdown request read | — |
| Checker / VP / Approval: read-only, Submit / Rework, significant changes | Present | — | Labels |

**The pattern at disbursement:** most fields are a **carry-forward** of values already decided
earlier in the application: pricing → interest details, fees → fee collection, sanctioned
terms → repayment schedule, securities → Annexure IV, conditions → CP to subsequent
disbursement. A deterministic **carry-forward agent** would remove most of the typing here.

---

## 6. New requirement: the CAM as an input to the journey

**Ask.** If a CAM is available, use it at the start to pre-fill most of the IP stage. If not,
offer to generate the CAM first, then start the LOS journey with the IP fields pre-filled.

**What exists today**
- The CAM engine produces a 21-section CAM plus the composed banker CAM (M1–M7).
- The LOS generates a CAM **inside** the journey, at IP Note preparation, and pins it to the
  application.
- A CAM already generated in the CAM workspace (`/`) for the same borrower is **not reused**:
  the LOS runs a fresh case.
- There is **no way to upload a CAM document** (for example, the bank's own CAM in PDF or Word).
- There is no "start an LOS application from this CAM" action in the CAM workspace.

**Proposed requirements (R-CAM)**

| Id | Requirement |
|---|---|
| R-CAM-1 | **New Application → Start from a CAM**, with three options: (a) choose a CAM already generated in the CAM workspace for the borrower; (b) **upload a CAM document** (PDF / DOCX); (c) **no CAM yet → Generate CAM** from the borrower's documents (the credit pipeline), then continue |
| R-CAM-2 | A **CAM intake agent** reads the CAM section by section and proposes field values for PS and IP, each with **CAM section / page, confidence and verbatim evidence**. A generated CAM maps directly; an uploaded CAM is read with the same evidence rules as other documents |
| R-CAM-3 | Coverage target: identity; facility; sector; parties, shareholding and group; existing exposure; banking arrangement; CMA / financial highlights; external and internal rating; all proposal narratives; project; security; key terms / covenants; pricing and fees; ESMS category; risks and mitigants; deviations |
| R-CAM-4 | The application **pins** that CAM (no second CAM run at IP). The IP Note step opens already populated; agents only fill what the CAM lacks |
| R-CAM-5 | Where the CAM disagrees with documents or the engine, the field becomes a **conflict** (never a silent overwrite). Ratings, decisions and narratives stay *must verify* |
| R-CAM-6 | **Start LOS application** button on a CAM in the CAM workspace (same flow as R-CAM-1a) |
| R-CAM-7 | The MIS reports the CAM's contribution: fields filled from the CAM, accepted unchanged |

**Open decisions:** what "CAM" means (an uploaded bank CAM, ours, or both), and where the
journey starts (PS pre-filled, or straight to IP). See §8.

---

## 7. Proposed requirements and priority

### 7.0 Before building
- **R-0:** a field-level pass over the screenshots for the in-scope sections, producing a field list per section with the bank's labels and mandatory flags.

### 7.1 Agentic pre-fill (the POC's purpose)

| Id | Requirement | Priority |
|---|---|---|
| R-CAM-1…7 | CAM as an input (§6) | **Must** |
| R-P1 | IP pre-fill extension: external rating; shareholding / group / key persons from MCA data and documents; banking arrangement; **all 8 proposal narratives**; project details; ESMS screening *proposals* (must verify); fees; key T&C draft | **Must** |
| R-P2 | AP pre-fill: **T&C and covenants from the reassessment (M6)**; inter-firm comparison from the benchmark engine; RAROC auto-compute once inputs are verified; CMA projections from the CAM; annexure *drafts* where a source exists | **Should** |
| R-P3 | **Carry-forward agent** for POS / DIS: interest details, fees, repayment schedule, Annexure IV, CP to subsequent disbursement, external rating, beneficiary bank / branch / amount | **Must** |
| R-P4 | Condition-compliance proposals from uploaded evidence documents | Could |

### 7.2 Workflow alignment

| Id | Requirement | Priority |
|---|---|---|
| G-W1 | IP: add Post Rating VP Review | **Must** |
| G-W2 / G-W3 | AP: ES stages (CRP ES Maker, ES Preparation, ES Review, ES Recommendation) and DMD Approval before Committee Sanction; new roles | **Should** (needs the bank to confirm the order) |
| G-W4 | Decision vocabulary per step as in the reference | **Must** (configuration) |
| G-W5 | IP Decision tab: computed committee shown, manual deviations, remarks history (including the compliance exception) | **Must** |
| G-W6 | Standard decision record at every AP step | **Must** (configuration + UI) |

### 7.3 Functional gaps

| Id | Requirement | Priority |
|---|---|---|
| G-F1 | Unit visit details (+ report) | Should |
| G-F2 | T&C authoring at AP (pre-commitment, pre/post disbursement, covenants, general, facility-specific), carried into the conditions tracker | **Must** (R-P2 pre-fills it) |
| G-F3 | Condition statuses as Complied / Not Complied (+ reason), keeping deferral and waiver as governed exceptions | Should |
| G-08 | Sourcing-detail fields (received date, source, branch, owner, Sol ID, sub-sub-sector) | Should |
| — | Capital market fetch, TAN verify, PSU flag, harmonised / IRAC classification, LMS / FT / committed-loan grids, BO identity fields, CMA Excel import, CAM abbreviations | Could (several need integrations) |

---

## 8. Decisions needed before coding

1. **What is "the CAM"?** The bank's own CAM document (uploaded), a CAM generated in this platform's CAM workspace, or both.
2. **Where does a CAM-first journey start?** At Prospect Sourcing, pre-filled (keeping dedupe and the sourcing decision), or directly at the IP Note.
3. **Workflow steps.** Add the missing steps now (IP Post Rating VP Review; AP ES stages and DMD), or IP only.
4. **Scope of this round.** Pre-fill + CAM + workflow alignment only; or also the functional gaps in §7.3.
5. **A sample CAM.** If the answer to 1 includes an uploaded CAM, a sample of the bank's CAM format (even redacted) is needed to build and test the CAM intake agent against.

---

## Status

- **S8 (CAM as input) — built 13-Oct-2026:** R-CAM-1 to R-CAM-7. `src/los/cam_intake.py`; the CAM card on New Application;
  *Start LOS application* in the CAM workspace; `tests/test_los_cam.py`. Tested against the fictional bank-format demo CAM;
  a sample of the bank's own CAM format is still needed.
  - Added during testing: a CAM whose PAN or CIN belongs to another company is refused before the application is created.
- **S9 (IP and AP pre-fill, T&C at AP) — built 13-Oct-2026:** R-P1, R-P2, G-F2. `src/los/prefill.py` (narratives,
  external rating, shareholding, banking arrangement, project, ESMS screening, fees, inter-firm comparison, CMA
  projections), `src/los/terms.py` (the T&C agent, authoring at AP, hand-over to the post-sanction tracker), the RAROC
  agent (computed once the rating grade and the rate are verified); `tests/test_los_prefill.py`.
  - Measured: the IP Note opens with 15 of 16 sections pre-filled for Apollo (banking arrangement missing — not on the
    record) and 13 of 15 applicable for the new prospect (no collateral or banking documents uploaded).
  - Found during validation and fixed: a new prospect's CAM omitted sections without data (now every CAM has the same
    sections, saying "not available"); the simulated DMS step could add synthetic documents to a prospect's folder
    (never when documents are on file); pre-commitment conditions now count with the pre-disbursement CPs at post sanction.
- **Both journeys validated to Exit** (`tests/test_poc_existing_borrower.py`, `tests/test_poc_golden_and_e2e.py`): the new
  prospect's CAM is generated by the CAM engine at sourcing, in the same format as an existing borrower's.
- **UI:** the application page is split into *My task · Checks · Workspaces · Credit assessment · History*; a
  *What to do now* panel lists the server's own submit blockers with a link to each; errors stay on screen until dismissed.
- **S7 (workflow steps and decisions) — built 13-Oct-2026:** G-W1 Post Rating VP Review in IP; G-W2 the ES process
  (CRP ES Maker → ES Preparation → ES Review → ES Recommendation, five new roles); G-W3 DMD Approval before Committee
  Sanction (`enabled: false` gives the POS-manual order; default follows the AP manual — **the bank to confirm**);
  G-W4 the decision wording per step (Rework, Recommend for sanction, Application withdrawn, …); G-W5 the Decision tab
  (computed committee, automatic + manual deviations, remarks history); G-W6 the AP decision record at every AP maker /
  review step, with the bank's labels and mandatory flags, carried forward. `tests/test_los_s7.py`.
  - R-0 done: [REFERENCE_FIELD_LIST.md](REFERENCE_FIELD_LIST.md) lists the bank's fields per section and the field gaps (§6).
  - Kept, pending the bank's view: *Withdraw* at Prospect Sourcing (a UAT requirement in `clientspec.md`, absent from the
    manual) and *Rework* at the Disbursement Approver (absent from the manual; removing it would remove a control).
- **S10 (carry-forward and the field gaps) — built 13-Oct-2026:** R-P3 the carry-forward agent
  (`src/los/carry_forward.py`: interest terms, repayment Annexure I, fee collection, security Annexure IV, proposed at
  the Disbursement Maker and recorded when the maker saves); F-1 the bank's nine AP narratives, F-2 the decision-tab
  notes, F-3 the bank's Annex 5-2 excluded-activities list (a *Yes* blocks), F-4 Unit Visit Details, F-5 sourcing
  details, F-6 facility fields (first disbursement date, parent facility, takeover; *secured* derived), F-9 security
  remarks, F-10 *Complied / Not complied* wording and the credit weaknesses from the rating rationale; MIS blocks for the
  T&C and carry-forward agents. `tests/test_los_s10.py`.
  - Found while building: the facility edit form and the disbursement repayment / interest panels sent or read values
    the server does not use (now aligned and editable).
- Open: F-7 / F-8 (entity identifiers, group tables), F-11 / F-12 (the bank's pricing model and committee names — bank
  input); beneficiary bank / branch / payment mode from the drawdown request.

## 9. Decisions (13-Oct-2026)

| # | Decision |
|---|---|
| 1 | **Both CAM sources:** the bank's own CAM document (uploaded) and a CAM generated in the CAM workspace. With neither, the user can **Generate CAM** first |
| 2 | **A CAM-first journey starts at Prospect Sourcing, pre-filled.** The RM confirms, completes the dedupe and the sourcing decision, and submits into an already-populated IP Note |
| 3 | **Add all missing steps:** IP Post Rating VP Review now; the ES stages and DMD Approval in AP in the POS manual's order, configurable in YAML so the bank can confirm or reorder them |
| 4 | **Scope this round:** pre-fill + CAM + workflow alignment + T&C authoring at AP. The other functional gaps in §7.3 move to the next round |

## 10. Final scope for this round

| Id | Requirement | Acceptance (summary) |
|---|---|---|
| R-0 | Field-level pass over the screenshots for the in-scope sections | A field list per section with the bank's labels and mandatory flags, checked into `docs/planning/` |
| R-CAM-1 | New Application → **Start from a CAM**: choose an existing CAM in the workspace, **upload a CAM document**, or **Generate CAM** | All three paths reach a pre-filled PS for an existing borrower and for a new prospect |
| R-CAM-2 | **CAM intake agent**: generated CAM → direct mapping; uploaded CAM → section-aware extraction with section / page / verbatim evidence | Each value cites its CAM section and page; precision measured on a golden CAM |
| R-CAM-3 | CAM → PS and IP field mapping across the coverage list in §6 | The IP Note opens with at least the sections in R-P1 populated |
| R-CAM-4 | The application **pins** the CAM; no second CAM run at the IP Note | One credit run per application unless a person changes an engine input |
| R-CAM-5 | CAM vs documents / engine disagreements become **conflicts**; ratings, decisions and narratives stay *must verify* | Tested with a deliberately inconsistent CAM |
| R-CAM-6 | **Start LOS application** from a CAM in the CAM workspace | The button creates the PS draft pre-filled |
| R-CAM-7 | MIS: the CAM's contribution (filled from the CAM, accepted unchanged) | Shown in the agents panel |
| R-P1 | IP pre-fill extension: external rating; shareholding / group / key persons; banking arrangement; all 8 proposal narratives; project; ESMS screening proposals; fees; key T&C draft | Pre-filled share of IP sections rises from about 9 / 16 to at least 14 / 16 |
| R-P2 | AP pre-fill: T&C and covenants from the reassessment (M6) into the new T&C authoring; inter-firm comparison from benchmarking; RAROC auto-compute once inputs are verified; CMA projections from the CAM | The AP maker step opens with T&C, covenants and RAROC populated |
| R-P3 | **Carry-forward agent** for POS / DIS: interest, fees, repayment Annexure I, security Annexure IV, CP to subsequent disbursement, external rating, beneficiary bank / branch / amount | The DIS maker's operational record opens pre-filled from the sanctioned record |
| G-W1 | IP Post Rating VP Review step | In `los_workflow.yaml`; the end-to-end tests pass through it |
| G-W2 / G-W3 | ES stages (CRP ES Maker, ES Preparation, ES Review, ES Recommendation) + DMD Approval before Committee Sanction; roles and demo users | Configurable order; ESMS workspace edited at the ES maker / preparation steps |
| G-W4 | Decision vocabulary per step as in the reference | Labels and action sets match §2.4 |
| G-W5 | IP Decision tab: computed committee, manual deviations, remarks history (including the compliance exception) | Visible at the IP Note step |
| G-W6 | Standard decision record at every AP maker / review step | Required fields enforced from the YAML |
| G-F2 | **T&C authoring at AP** (pre-commitment, pre/post disbursement, covenants Annexure III, general, facility-specific), carried into the post-sanction conditions tracker | Conditions at POS are the ones authored and approved at AP, not regenerated |

**Inputs needed from the bank:** a sample CAM in the bank's format (redacted is fine), and
confirmation of the ES / DMD step order. Until a sample CAM arrives, the upload path is built
and tested against this platform's own CAM exported as PDF.

**Proposed build order** (each sprint ends with the end-to-end tests green for the new-prospect
and existing-borrower journeys):
1. **S7. Workflow and decision alignment:** G-W1, G-W2 / G-W3, G-W4, G-W5, G-W6, plus R-0. Mostly configuration; it unblocks the rest.
2. **S8. CAM as input:** R-CAM-1…7, including the CAM workspace button and the CAM intake agent.
3. **S9. IP and AP pre-fill:** R-P1, R-P2 and G-F2 (T&C authoring at AP, pre-filled from M6).
4. **S10. Carry-forward to POS / DIS:** R-P3; update the walkthrough and orchestration documents, the golden sets and the MIS.
