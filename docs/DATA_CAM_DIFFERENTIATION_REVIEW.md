# Data points, CAM structure and differentiation: review and enhancement list

Status: **Phase 1 built and tested 2026-11-06** (D1–D5, C1, C2, L1); Phases 2–4 are analysis only.

Phase 1, as built:
- **D1 — credit metrics:** 15 typed fields in a new "Credit metrics" group (`config/flow.yaml`). Each carries a policy band, and computed fields cannot be edited by hand.
- **D2 — sustainable limit:** the fact pack's `debt_capacity` block (`src/engines/quality_engine.py`). It gives each policy limit's capacity, the binding limit and the structure that passes, offered as a one-click "Set limit / Extend tenor".
- **D3 — quality of the numbers:**
  - `earnings_quality` and `revenue_truth`;
  - `ews_indicators`: a forensic signal only counts when its inputs are on record, and missing data shows as "not checked".
- **D4 — confidence:** a per-figure confidence (score, level, basis) on every number.
- **D5 — cleanup:**
  - weaknesses and key risks merged into an agent-built "Risks and mitigants" field;
  - outlook, marketing and deviations are filled by agents, not asked;
  - constitution derived from the CIN, and banking arrangement from the bureau / CRILC lender count;
  - social media removed from the CAM.
- **C1 — streamlined CAM:** a Decision Summary plus 8 merged sections (`CAM_SECTIONS_STREAMLINED`; the classic 21-section layout is still available via `narrative.cam_structure`). Fixed data tables follow the model's text.
- **C2 — live Decision Summary:** built from data. The engine version is replaced at download by the workflow's live one: challenge answers, deviation register, justifications, decision trail and confidence.
- **L1 — deviation register:** one entry per policy breach. Underwriting records a mitigant before recommending; the Sanctioning Authority approves each before Sanction. A failed hard rule is not deviable (`deviation_register.hard_rules_deviable`).
Date: 2026-11-06.

The question behind this review: buyers do not need another tool that copies a bank's existing process or CAM. Every data point, CAM section and LOS step should therefore be judged by one test: **what can a bank do with it that it cannot do today?**

---

## 0. Summary

1. **We capture a lot, but the workflow sees little of it.**
   - The CAM engine builds 50 data blocks: 27 ratios per year, quarterly results, stress tests, repayment analysis, 9 hard rules, challenges, observations and investigations.
   - The LOS workflow carries only **32 credit data fields**. Most are free text, and none of them is a ratio.
   - That gap is why Madras Fertilizers looked "all green" (F13).
   - The data is the asset. It needs to reach the workflow, the policy checks and the analytics as typed, sourced, checked fields.
2. **About a quarter of what we collect comes back empty on real runs.**
   - Empty blocks: 11 of 50 for Infosys and 15 of 50 for Madras.
   - On Infosys, **5 of the 9 hard rules are "not verified"**: no commercial bureau report, MCA status, RBI defaulter list or suit-filed list. A bank cannot use a "pass" it cannot verify.
   - The biggest data gap is the **regulatory checks**, not more financial ratios.
3. **Bank standards we miss:**
   - working-capital limit assessment (turnover / MPBF / cash budget);
   - term-loan appraisal (IRR, break-even);
   - risk-based pricing (RAROC);
   - unhedged foreign-currency exposure;
   - group exposure against the Large Exposures Framework;
   - related-party lending checks (RBI directions finalised in January 2026);
   - **expected credit loss (ECL) at origination**: RBI's final ECL directions apply from **1 April 2027**.
4. **AI drafting of the CAM is no longer a differentiator on its own.**
   - Moody's sells an agentic AI credit memo, built from Moody's data and the borrower's financials, that is "clearly sourced" and "ready for expert review".
   - nCino's Banking Advisor drafts memo narratives at US banks.
   - Our edge has to come from what happens **around** the memo.
5. **Where we are already different, and should go further:**
   - **Implemented already:**
     - an adversarial *Credit Challenge Agent* that argues against the proposal and now proposes concrete actions;
     - a provenance link on every figure;
     - a re-run that rewrites only the sections a change affects;
     - verification that cross-checks one source against another (e.g. GST vs bank statements vs audited accounts);
     - a written-justification gate when an officer goes against the engine.
   - **To build:** the items in §5.
6. **The CAM can drop from 21 sections to 9 plus a one-page Decision Summary**, cutting about 60% of the length (13,900 words today → about 5,000). The consolidation map is in §4. Part of it already exists: the engine builds a 12-section version, but the PDF does not use it.

---

## 1. What we capture today, by category

**Layers:**
- **(E)** CAM engine fact pack: 50 blocks.
- **(W)** workflow credit data fields: 32, in `config/flow.yaml`.
- **(A)** new-prospect acquisition sources: 10, in `config/data_sources.yaml`.

**Fill state** is measured on the latest real runs (Infosys / Madras Fertilizers).

| # | Category | What is captured | Layer | Fill state on real runs | Assessment |
|---|---|---|---|---|---|
| 1 | Identity & KYC | Name, CIN, PAN, incorporation, address, listing, capital, employees; LEI; KYC pack | E, W, A | Filled | Good. CIN/PAN/LEI should be **verified** (MCA/GLEIF), not just stated. |
| 2 | Group, promoters & management | Group entities, shareholding, directors, corporate hierarchy, group revenue/net worth/debt | E | Filled (from records) | Missing: **promoter pledge %**, director DIN checks (disqualified, other directorships), related parties. |
| 3 | Facility | Product, amount, tenor, purpose, proposed/existing limit, collateral type, pricing (base rate, spread, fees) | E, W | Filled | Missing: assessed limit (what the borrower *needs*), **RAROC / hurdle price**, end-use plan. |
| 4 | Financial statements | 3 years, 40+ line items; financial summary; growth/CAGR; provisional figures | E, A | Filled | Good. Deterministic reader + reconciliation is a strength. |
| 5 | Ratios | 27 per year: liquidity, leverage, coverage (DSCR, ICR, FCC), profitability, efficiency (debtor/inventory/payable days, WC cycle), Altman Z, TNW, FCFF, contingent-liability ratio | E (6 shown in the risk strip) | Filled | **Not visible as workflow fields**; policy thresholds cover only 9 of them. |
| 6 | Quarterly performance | 12 quarters: revenue, EBITDA, PAT, margins | E | Filled for listed companies | Good for listed borrowers; nothing equivalent for unlisted ones (could come from GST monthly turnover). |
| 7 | Repayment, projections, stress | Cash-flow repayment capacity, DSCR by year, 3–5-year projections, DSRA, stress scenarios with policy checks | E | Filled | Good. Missing: **break-even, IRR** (term loans), sensitivity on the bank's own covenant levels. |
| 8 | Working capital | Drawing power (components, total DP); WC cycle | E | Filled (DP) | Missing: **WC assessment methods** (turnover / MPBF / cash budget) → *assessed* limit vs requested. |
| 9 | Collateral | Collaterals, market value, forced-sale value, coverage (market and FSV), valuation report | E | Partly | Missing: **LGD** from FSV and seniority; charges registered with the ROC (`charges_data` is empty). |
| 10 | Bureau, CRILC, existing exposure | Bureau score / DPD / lenders, CRILC exposure and SMA history, existing facilities | E, A | **Thin**: Madras has no existing exposure and no CRILC | Commercial bureau (CIC) not connected → 4 hard rules cannot be verified. |
| 11 | Account conduct (existing-to-bank, ETB) | Conduct analysis, covenant history, core-banking analysis, ETB behavioural analytics | E | **Empty** in both runs | Engines exist (`core_banking_engine`, `etb_analytics_engine`) but get no data in the flow. |
| 12 | Bank statements & GST | Bank-statement analysis (balances, credits, cheque returns); GST turnover and filing status | E, A | Partly (prospects via upload) | Missing: **GST vs bank vs books triangulation as a score**, buyer/supplier concentration from GSTR-1/2B. |
| 13 | Compliance & screening | MCA status, filings, GST compliance, PEP/sanctions/adverse media screening, OFAC/UN lists | E, A | Filled (screening); MCA status "not verified" | Missing: **RBI wilful-defaulter / suit-filed lists, RFA / fraud flags, ECGC caution list**, NCLT/IBC cases. |
| 14 | Market & reputation | Market signals, social media (Twitter mentions, sentiment, controversy index), web news, ESG | E, A | Social media filled; web news empty | Social-media metrics are noisy and add little to the credit decision (see §3.4). |
| 15 | Industry & peers | Industry overview, drivers, headwinds, competitors, SWOT, sector KPIs, benchmarks, worst performers | E | Filled | Good. Outlook is narrative; missing **sector-cap headroom in the bank's own book**. |
| 16 | Policy & decision | Policy thresholds (9), tier-1 hard rules (9), tier-2 scores, tier-3 recommendation, approving authority, validation exceptions, observations, investigations, challenges | E | Filled | Strong. Missing: **deviation register** with authority to approve each, policy-as-code versioning visible to the user. |
| 17 | Provenance | Per-block data provenance, data sources (8), document verification | E | Filled | A differentiator. Extend to a **per-figure confidence score** (§3.2). |
| 18 | Unused or orphaned | Fraud detection engine (782 lines; used only by an analytics API), CRILC report generator, site visit, infra metrics, downloaded annual reports | E | Not in the CAM flow | Wire the fraud engine into origination (§5, D3); drop what has no data source. |

**The 32 workflow fields, as they stand:**
- **Typed numbers:** 9. Amount, tenor, recommended limit and 5 financial lines.
- **Free text:** 23, of which 11 are long text: background, governance, strengths, weaknesses, risks, outlook, marketing, security, terms, covenants, deviations, recommendation.
- **Not represented in the workflow:** ratios, policy results, bureau, conduct, collateral values, pricing economics, ECL.

---

## 2. Measured against bank standards and current regulation

Standard practice in Indian corporate appraisal:
- **CMA data** in the IBA format: historical and projected financials, MPBF, fund flow and ratios; normally 3+ audited years plus provisional and 3–5 projected years.
- **Term-loan appraisal:** DSCR, IRR, break-even, sensitivity and security cover.

New or upcoming regulation shapes what a 2027 bank will need.

| Standard / regulation | What it requires at origination | Do we have it? | Gap → data point |
|---|---|---|---|
| CMA / working-capital assessment | Assessed limit by turnover method, MPBF or cash budget; holding levels; drawing power | DP yes; assessment no | `assessed_wc_limit_cr`, `wc_method`, `wc_gap_cr`, `holding_levels` |
| Term-loan appraisal | DSCR (have), IRR, break-even, sensitivity, security margin cover | DSCR and stress yes | `project_irr`, `break_even_pct`, `sensitivity_dscr` |
| Risk-based pricing | Rate ≥ cost of funds + expected loss + capital charge + opex (RAROC ≥ hurdle) | Rate only | `raroc_pct`, `hurdle_rate`, `min_price` |
| **ECL directions** (final 27 April 2026, effective 1 April 2027) | Stage 1 / 2 / 3; 12-month vs lifetime ECL; early recognition of credit stress | No | `pd_12m`, `pd_lifetime`, `lgd`, `ead`, `ecl_stage`, `ecl_cr` at origination |
| Large Exposures Framework | Single / group exposure against Tier 1 limits | Group financials only | `group_exposure_cr`, `lef_headroom_pct` |
| Lending to related parties (directions, Jan 2026) | Identify related parties; recusal; board approval above thresholds | No | `related_party_flag`, `related_party_basis` |
| Fraud risk management Master Directions (July 2024): EWS / RFA | EWS framework; red-flag accounts on EWS indicators (e.g. default on statutory dues, bounced high-value cheques) | Partly (cheque returns, GST compliance) | `ews_indicators[]` at origination, `rfa_status` |
| Unhedged foreign-currency exposure (RBI) | UFCE assessment, incremental provisioning and capital | No | `ufce_cr`, `ufce_ratio` |
| CIC / CRILC / defaulter lists | Commercial bureau, CRILC SMA, wilful defaulter, suit-filed | Engine fields exist; data mostly missing | Connect CIC / CRILC sources; make "not verified" visible (done in the F13 risk strip) |
| **FREE-AI** framework (Aug 2025) | AI used for credit must be explainable, auditable and free of bias; board AI policy; model risk management across the AI lifecycle | Provenance, number guard and audit pack yes | `ai_use_log` per CAM (model, prompt version, guard results), a model card, bias checks |
| Climate risk disclosure (draft Feb 2024; reports say voluntary from FY27) | Climate risk in credit risk management | ESG text only | `climate_physical_risk`, `transition_risk_sector`, emissions intensity (when available) |

---

## 3. Data-point recommendations

**Principle:** every data point is (a) auto-populated with a source, (b) typed where it is a number, (c) checked against policy where policy has a limit, and (d) used by a decision, a check or an analytic. A data point that does none of these is removed.

### 3.1 Promote: exists in the engine, make it a workflow field

| Data point | Why | Differentiator |
|---|---|---|
| DSCR, ICR, Debt/EBITDA, current ratio, TOL/TNW, D/E (with policy band) | Approvers decide on these; today they appear only in the risk strip | Coloured by policy, with a link to the formula and the source lines |
| Engine recommendation, hard-rule results, internal rating score | Drives the justification gate and analytics | "Decisions against the engine" becomes a measurable KPI |
| Collateral FSV and coverage | Needed for LGD and security conditions | Feeds LGD automatically |
| Bureau score, CRILC SMA flag, existing exposure | Standard and currently invisible | "Not verifiable" shown explicitly instead of an assumed pass |
| Verification flags (e.g. other income = 90% of PBT; borrowings not reported to the bureau) | Strong findings, today buried in the Data Sources panel | Becomes a challenge with actions |

### 3.2 Add: calculated data points (no new data source needed)

| Data point | Formula / source | Differentiator |
|---|---|---|
| **Sustainable limit** (debt capacity) | min(Debt/EBITDA headroom, DSCR-based capacity, DP / assessed WC gap) | Answers "how much can we safely lend?" with the arithmetic. The amount check built in F12 covers leverage only. |
| **Structure that would pass policy** | Search over amount, tenor, DSRA and security to meet every threshold | "What would make this approvable": rare in LOS products we found (§5, D2) |
| **PD, LGD, EAD, ECL stage, ECL** at origination | PD from the internal rating (bank master-scale mapping); LGD from FSV and seniority; EAD from limit and expected utilisation | Prices and provisions on day one, ready for April 2027 |
| **RAROC and minimum price** | (spread + fees − cost − EL) / capital | Pricing is no longer a free-text field |
| **Revenue truth score** | Agreement between audited revenue, GST turnover and bank credits (built for prospects; generalise) | Catches inflated revenue before sanction (EWS at origination) |
| **Earnings quality** | Other-income share, one-offs, cash conversion (OCF/EBITDA), accrual ratio | Dixon's other income at 90% of PBT is exactly this |
| **Customer / supplier concentration** | Top-5 share from GSTR-1 / 2B or e-invoice data (when consented) | Counterparty risk that today relies on the RM's word |
| **EWS indicators at origination** | RBI EWS indicator list evaluated on the onboarding data | Fraud-risk compliance from day one, not only after disbursal |
| **Per-figure confidence** | Source class (API > audited > provisional > stated) × cross-check result | Approvers see *how sure* each figure is |
| Assessed WC limit, WC gap, holding levels | Turnover / MPBF / cash-budget methods from CMA data | Standard, but auto-computed with method comparison |
| IRR, break-even, sensitivity (term loans) | From projections | Standard; automated |
| Group exposure and LEF headroom; sector cap headroom | Bank book + group map | Portfolio-aware origination |
| UFCE ratio | From the notes to accounts (forex exposure, hedges) | Regulatory; often missed |

### 3.3 Add: new data sources (API-first, document fallback, as built for prospects)

1. **Commercial bureau (CIC):** Probe42 / Crif / TransUnion CIBIL commercial. This unlocks 4 hard rules.
2. **RBI / CIC defaulter lists** (wilful defaulter, suit-filed), **NCLT / IBC cases**, **ECGC caution list**.
3. **MCA charges** (CHG-1) and director DIN status. `charges_data` is empty today.
4. **CRILC** for existing-to-bank borrowers (bank-internal).
5. **Core banking / account conduct** for existing-to-bank borrowers. The engine exists; it needs a feed.
6. **Account Aggregator (AA) / Unified Lending Interface (ULI)** for bank statements and GST, by consent. ULI's published examples are MSME, so treat corporate use as an assumption to verify.
7. **Shareholding pattern / promoter pledge** (exchange filings, for listed companies).

### 3.4 Remove or merge

| Field / block | Action | Why |
|---|---|---|
| Social media (Twitter mentions, digital presence, employee intelligence) | **Remove from the CAM**; keep only adverse-media hits inside screening | Noisy, rarely decision-relevant, and a privacy / FREE-AI liability. Reputational risk is covered by verified adverse media. |
| Strengths / Weaknesses / Key risks (3 free-text fields) | **Merge** into one structured "Risks & mitigants" list generated from challenges and observations | Removes duplication; each risk gets a mitigant and an owner |
| Industry outlook, Marketing arrangements | **Drop as asked fields**; the engine writes them with sources | Officers should not type what an agent can draft |
| Constitution, Banking arrangement | **Derive** (MCA / CRILC lender count) rather than ask | Fewer questions to the RM |
| Section 21 "Terms & Conditions" | **Merge** into section 19 | Duplicate of terms and covenants |
| Infra metrics, site-visit block, downloaded annual reports block | Keep only where a source exists (infra sector / uploaded visit report) | Empty blocks look like missing work |

---

## 4. Streamlining the CAM: 21 sections → Decision Summary + 9

Today's PDF has 21 sections plus 4 annexures, about 13,900 words for Infosys.

Several sections overlap:
- Borrower profile (2), group (4) and directors (5);
- External rating (7), compliance (9), conduct (10), banking (11) and social media (12);
- Operational KPIs (14) and peers (15);
- Terms (19) and Terms & conditions (21).

The engine already composes a 12-section version (`src/engines/cam_composer.py`), but the downloaded PDF does not use it.

| New section | Replaces (today's numbers) | What changes |
|---|---|---|
| **0. Decision Summary (1 page)** | Part of 1 | The ask; engine verdict; rating and score; 6 ratios against policy; top 3 challenges and their answers; deviations and who justified them; sustainable limit; ECL / RAROC; conditions. *Approvers read this page first; most never read further.* |
| 1. Borrower, Group & Management | 2, 4, 5 | Adds related-party flag, promoter pledge, DIN checks |
| 2. Business, Industry & Peers | 3, 6, 14, 15 | One narrative; peers as a table |
| 3. Financial Performance & Earnings Quality | 13 | Adds earnings quality and the revenue truth score |
| 4. Repayment Capacity, Projections & Stress | 16, plus the repayment and stress engines | Sustainable limit; structure that would pass policy |
| 5. Facility Assessment, Structure & Pricing | 17 | WC / TL assessment methods; RAROC; ECL |
| 6. Conduct, Compliance & Due Diligence | 7, 9, 10, 11, 12 | Each check shown as pass / fail / *not verifiable*; social media removed |
| 7. Risk Assessment & Challenges | 8, plus challenges, investigations | The case against, with the response to each challenge |
| 8. Security, Covenants, Terms & Recommendation | 18, 19, 20, 21 | One list of terms; approving authority |
| Annex | A–C, data sources | Data sources and per-figure provenance; document checklist; quarterly trend |

**Effect:**
- **Speed:** 21 → 9 LLM-written sections, with section 0 assembled from data, not written by the model. That means fewer model calls and roughly half the generation time.
- **Length:** target about 5,000 words.
- **Re-runs:** a change touches fewer sections.

**Differentiators to build into the CAM itself:**
- **Role views of the same CAM:** RM (gaps and asks), Underwriter (challenges and evidence), Sanctioning Authority (Decision Summary and deviations), CAD (terms and conditions).
- **Delta CAM for renewals and re-runs:** "what changed since the last sanction / last version", with each changed figure highlighted.
- **Live CAM:** the PDF is a snapshot; the on-screen CAM keeps every figure clickable to its source and confidence.

---

## 5. Enhancement list

Columns:
- **Type:** D = data, C = CAM, L = LOS.
- **Effort:** S = up to 2 days, M = up to 1 week, L = more than 1 week.
- **Differentiator:** "High" means we found no equivalent as a standard feature of the Indian corporate LOS products and AI-memo products we researched. This is not an exhaustive market study.

### Phase 1: make the data we have count (no new sources)

| ID | Enhancement | Type | Differentiator | Effort |
|---|---|---|---|---|
| D1 | Promote ratios, engine verdict, hard rules, bureau / CRILC and collateral values to typed workflow fields with policy bands; the analytics and the Copilot read them | D/L | Medium: makes the "all green" problem impossible | M |
| D2 | **Sustainable limit and the structure that would pass policy** (amount / tenor / DSRA / security search), offered as one-click overrides | D/L | **High** | M |
| D3 | **Revenue truth score and earnings quality** generalised from prospect verification to every borrower; wire the existing fraud detection engine into origination as **EWS-at-origination** | D | **High** | M |
| D4 | Per-figure confidence score shown next to each figure and in the CAM | D/C | **High** | S |
| D5 | Remove / merge the fields in §3.4; derive constitution and banking arrangement | D | Low (hygiene) | S |
| C1 | CAM restructure: Decision Summary + 9 sections; use the composer; remove social media | C | Medium | M |
| C2 | Decision Summary built from data, not written by the model (no model wording on the decisive page) | C | **High**: auditability under FREE-AI | S |
| L1 | Deviation register: each policy breach recorded, with the authority empowered to approve it and the mitigant (builds on the F13 gate) | L | Medium | S |

### Phase 2: regulation-ready differentiators

| ID | Enhancement | Type | Differentiator | Effort |
|---|---|---|---|---|
| D6 | **ECL at origination** (PD / LGD / EAD / stage / ECL) from rating and collateral, using a configurable bank master scale | D/C | **High**: ahead of the April 2027 deadline | M |
| D7 | **RAROC and minimum price**; pricing field becomes computed against the hurdle | D/C | **High** in Indian corporate LOS | M |
| D8 | Working-capital assessment (turnover / MPBF / cash budget) and term-loan appraisal (IRR, break-even, sensitivity) from CMA data | D/C | Low–medium (standard, but automated end to end) | L |
| D9 | Related-party, Large Exposures Framework group headroom and UFCE checks | D | Medium (compliance) | M |
| L2 | **FREE-AI governance pack:** per-CAM AI-use log (model, prompt version, number-guard results, human changes), model card, bias checks, impact-assessment template | L | **High**: makes the AI buyable by a regulated bank | M |
| C3 | **Delta CAM** for re-runs and renewals; role views of the same CAM | C | **High** | M |

### Phase 3: new data sources (API-first; inactive until keys or contracts exist)

| ID | Enhancement | Type | Differentiator | Effort |
|---|---|---|---|---|
| D10 | Commercial bureau (CIC / Probe42), defaulter lists, NCLT / IBC, ECGC caution list: makes the 4 "not verified" hard rules verifiable | D | Low (needed to be credible) | M per source |
| D11 | MCA charges and DIN checks; promoter pledge from exchange filings | D | Medium | M |
| D12 | Account Aggregator / ULI consent-based bank and GST pulls; **customer / supplier concentration** from GSTR-1 / 2B / e-invoice | D | **High** for corporate | L |
| D13 | Core banking / CRILC feeds for existing-to-bank conduct (engines exist) | D | Low | M |

### Phase 4: beyond origination

| ID | Enhancement | Type | Differentiator | Effort |
|---|---|---|---|---|
| L3 | **Covenant and EWS monitoring from the CAM** (post-disbursement): the CAM's covenants become monitored rules; a breach re-opens the challenge | L | **High**: closes the loop no memo product closes | L |
| L4 | Portfolio-aware origination: sector caps, concentration, ECL impact on the book shown before sanction | L | **High** | L |
| L5 | Credit-committee pack: anticipated questions with answers from the record (extends the Copilot) | L | Medium | S |

**Recommended order:** Phase 1 (D1, D2, D3, C1, C2 first), then D6, D7 and L2 from Phase 2. Those three are the regulation-timed differentiators a bank will pay for in 2026–27.

---

## 6. Sources

- CMA data format and contents: [Taxguru — CMA data insight](https://taxguru.in/finance/credit-monitoring-arrangement-cma-data-insight.html), [Taxguru — CMA report for bank loans](https://taxguru.in/finance/cma-report-bank-loan-is-banks-it.html)
- Term-loan appraisal (DSCR, IRR, break-even, sensitivity): [Union Bank of India — term loan financing](https://bombaychamber.com/wp-content/uploads/2022/05/On-Term-Loan-Financing-Presentation-by-A.R.-Manickam-Deputy-General-Manager-Central-Credit-MSME-Dept.-Union-Bank-of-India.pdf), [D&B — project appraisal](https://www.dnb.co.in/blog/what-banks-look-in-a-project-appraisal-report)
- ECL directions (effective 1 April 2027): [KPMG India](https://kpmg.com/in/en/insights/2026/05/expected-credit-loss.html), [Business Today](https://www.businesstoday.in/india/story/rbi-tightens-bad-loan-recognition-new-norms-push-banks-towards-global-standards-527682-2026-04-27), [RBI Master Directions](https://rbi.org.in/scriptS/BS_ViewMasDirections.aspx?id=13400)
- Fraud risk management, EWS and RFA: [RBI Master Directions](https://rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=10477), [Grant Thornton summary](https://www.grantthornton.in/globalassets/1.-member-firms/india/assets/pdfs/services/rbi-master-directions-on-fraud-risk-management.pdf)
- Lending to related parties: [RBI press release](https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx?prid=61972), [Vinod Kothari](https://vinodkothari.com/2025/10/rbi-proposes-revised-norms-on-related-party-lending-and-contracting/)
- FREE-AI framework: [Chambers](https://chambers.com/articles/rbi-committee-report-on-responsible-ai-in-the-financial-sector-free-ai-framework), [Presencis](https://cdn.presencis.com/regulations/rbi-free-ai/article-overview/)
- Climate risk disclosure: [BDO](https://www.bdo.global/en-gb/news/ifrs-news/india%E2%80%99s-central-bank-publishes-draft-disclosure-framework-on-climate-related-financial-risks), [Cyril Amarchand Mangaldas](https://cyrilshroff.com/wp-content/uploads/2024/04/Client-Alert-RBI-Draft-Disclosure-Framework-for-Climate-Related-Fin-Risks.pdf)
- ULI and Account Aggregator: [IIFL](https://www.iifl.com/blogs/other/what-is-uli-unified-lending-interface), [SMFG India Credit](https://www.smfgindiacredit.com/knowledge-center/unified-lending-interface.aspx)
- GST / e-invoice data in underwriting: [FinBox Research](https://research.finbox.in/blog/gst-invoices-alternate-data-and-cash-flow-underwriting-how-to-unlock-the-400-bn-msme-financing-opportunity/), [B2B lending India — GST data](https://javajack.github.io/b2b-lending-india/04-integrations/gst-data-and-gsps/)
- AI credit memos in the market: [Moody's AI credit memo](https://www.moodys.com/web/en/us/capabilities/gen-ai/agentic-solutions/credit-memo.html), [American Banker — Great Southern / nCino](https://www.americanbanker.com/news/great-southern-loan-officers-use-gen-ai-to-chat-with-data)
- Indian LOS market context: [Biz2x — corporate LOS](https://www.biz2x.com/india/loan-origination-system/corporate-loan-origination-system-future-enterprise-lending), [Intellect eMACH.ai case study](https://www.intellectdesign.com/wp-content/uploads/2026/04/Case-Study_Lending_India_Indias-leading-bank-accelerates-credit-decisions-for-MSME-and-Agri-Customers-by-50-with-eMACH.ai-Lending.pdf)

Most market and regulatory sources above are secondary commentary. Before building the regulatory items (D6, D9, L2), check thresholds and effective dates against the primary RBI texts.
