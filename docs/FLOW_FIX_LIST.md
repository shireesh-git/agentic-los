# Agentic LOS — fix list from user testing

Status: **F1–F10 built and tested 2026-11-06** (bank name on the CAM cover: on hold at the user's request).
Round 4 (F11–F15): **built and tested 2026-11-06** (src/flow/risk.py; tests/test_flow_risk.py).

## Round 1 — Infosys walkthrough (2026-11-06)

| # | Observation | Cause (from the code) | Fix to make |
|---|---|---|---|
| F1 | On **Generate CAM**, all the agent tags under the progress bar (Gathering data, PEP / KYC screening, …) turn green while it is still on section 1 — looks misleading. | Those six analysis agents genuinely finish in ~3 s (deterministic); 99% of the time is writing the 21 sections, which shows only as one blue "Writing the CAM" tag. So the tags are true but tell the wrong story. | Show the run as two phases: **Analysis** (6 agents, each green only on its own completion event, with its time) and **Writing the CAM** with one tag **per section** (grey → blue while writing → green when done, "reused" marked). Nothing turns green until its own event arrives. |
| F2 | Hard to find the missing data points. | Missing values show "—" in red, but the group header and label are not highlighted. | Missing (and required-missing) points: **label in red**, and the **group card header red** with a count ("Risk & rating · 1 missing"). |
| F3 | The **missing** mini-card should take you to the missing field. | Stats tiles are not clickable. | Click **missing** → scroll to and highlight the first missing field (next click → next one). Same for **skipped**. |
| F4 | "2 by people" should say who. | Count is by source kind only. | Show by role: e.g. "2 by Relationship Manager · 1 by Credit Risk"; same in the source chip ("entered by Ananya Rao (RM)"). |
| F5 | As Credit Risk, the chat's 2 suggested questions: clicking one answers it, but then the same question is offered/asked again. | Suggestion chips are static per role (never hidden once asked); and when a scripted question is pending, every free question is followed by "(Still waiting on the question above…)", which re-prompts. | Hide a suggestion once it has been asked (and offer a fresh one); don't repeat the pending-question hint after every answer — remind once, and keep the pending question pinned above the input instead. |
| F6 | Credit Risk changed the amount and sent the case back to the RM; **without switching user**, the chat immediately showed the RM's prompt "Everything required is filled. Review the screen, then Submit to Credit Risk." — misleading. | One shared chat thread: on send-back the assistant posts the RM's next prompt into the same thread, so Rahul sees a message meant for Ananya. | (a) Each message is addressed to a stage; a user sees the assistant's prompts for **their** turn, and messages for others are shown as a collapsed "to Ananya (RM)" note, not as a live question. (b) When the case comes back to the RM after Credit Risk changed a figure the CAM uses (e.g. the amount), the assistant asks Ananya: **"Rahul changed the amount from ₹500 Cr to ₹X Cr. Re-run the CAM? Yes / No"** — Yes starts the re-run (only affected sections); No keeps the CAM marked out of date and Submit stays blocked until it is re-run. |

## Round 2 — Infosys walkthrough, Credit Risk → CAD (2026-11-06)

| # | Observation | Cause (from the code) | Fix to make |
|---|---|---|---|
| F7 | When Credit Risk presses **Recommend**, the chat immediately asks — in Rahul's view — "…changed EBITDA … Accept or dispute?", which only the Sanctioning Authority should be asked. | Same root cause as F6: one shared thread; on approve the assistant posts the next stage's opening questions into it. | Covered by the F6 fix (prompts addressed to a stage, shown live only to that role). Rahul instead sees one closing line: "Sent to Vikram Shah (Sanctioning Authority) with 1 change for him to accept." |
| F8 | As CAD, the action bar says "8 condition(s) not yet met: Sanction letter accepted…, Board resolution…", but the assistant does not guide the officer through closing them. | The CAD opening message only says "upload the signed documents"; the assistant never walks the list. | The assistant drives CAD's checklist: lists what is open, asks for one document at a time ("Next: the borrower-signed sanction letter — upload it here"), accepts the file **in the chat**, reports the agent's check ("✓ names Infosys, recognised as a board resolution — 3 of 8 met"), asks CAD to confirm what it cannot verify ("Insurance: no bank clause found — confirm you've seen it?" Yes/No), and when all are met prepares the drawdown and asks "Send ₹X Cr for release?" |
| F9 | "Why is it asking to upload these documents at this step — are they really needed?" | All 8 conditions are configured as **before release** for every case, whatever the amount, product or borrower. | See the answer below; make the list **risk-based**: conditions precedent vs subsequent, amount thresholds, and items already satisfied earlier in the case are auto-met. |

**F9 — answer.** In Indian corporate lending, the bank must hold executed loan documents before releasing funds:
- the borrower's acceptance of the sanction terms;
- the board resolution authorising the borrowing;
- the stamped facility agreement;
- the security documents.

Internal policies say no release until documents are executed, and CAD checks this before disbursement. These four stay **before release**. The rest need not hold up the first drawdown:
- **Charge registration (CHG-1 with the ROC, CERSAI):** the law gives 30 days from creating the charge, so this is normally a **condition subsequent**, tracked after disbursement.
- **Legal vetting by a panel advocate:** banks require it **above an amount threshold**, not for every loan.
- **Insurance:** needed before release where the security is physical assets (hypothecation, mortgage). It doesn't apply to a lien on fixed deposits, which is Infosys' security.
- **KYC:** already done when the borrower was onboarded, so it should be **auto-met** from the record unless it is out of date.

**Proposed change:** in `config/flow.yaml` each condition gets `when: before_release | within_days: 30`, an optional `min_amount_cr`, and an `applies_if` (security type, product). Conditions the case already meets are ticked by the agent with their source. Infosys (₹500 Cr, FD lien) would then need 4 documents before release, plus legal vetting if ₹500 Cr is above the bank's threshold; charge registration would be tracked afterwards, and insurance and KYC would not ask CAD for anything — instead of 8 documents up front. Conditions subsequent show on the disbursed case with due dates.

**F9 approved by the user (2026-11-06):** risk-based conditions as proposed. The legal-vetting threshold
defaults to ₹100 Cr and can be changed in config.

## Round 3 — look and feel (2026-11-06)

| # | Observation | Fix to make |
|---|---|---|
| F10 | The UI and its wording look like a school project (e.g. "Five people, one chain — agents do the work in between. Choose who you are."). It must look and read like an **executive, industry-grade** banking product, with industry terminology, options and tags. | A full UI and copy pass (below). No change to the flow or the rules. |

**F10 — wording: from casual to industry terms**

| Now | Becomes |
|---|---|
| "Five people, one chain… Choose who you are." | **Corporate Credit Origination** · "Sign in to your workspace" · environment tag **UAT / DEMO** · "Single sign-on is disabled in demo mode" |
| Relationship Manager / Credit Risk / Sanctioning Authority / CAD / Disbursement | **Origination (RM)** · **Credit Underwriting** · **Sanctioning Authority (DoFP)** · **Credit Administration (CAD)** · **Disbursement Operations** |
| Cases · Waiting for you · All cases | **Deal Pipeline** · **My Work Queue** (ageing, SLA status) · **Portfolio View** |
| New case | **Initiate Proposal** |
| Credit Appraisal Memorandum · Generate / Upload CAM | **CAM** · **Generate CAM (AI)** / **Ingest Bank CAM** |
| Data points · filled by agents / by people | **Credit Data Fields** · tags **Auto-populated** · **Verified** · **Overridden** · **Pending** · **Not applicable** |
| Changes by Credit Risk · Accept / Dispute | **Underwriting Overrides** · **Concur** / **Return with Remarks** |
| The case against | **Key Risk Challenges** (Credit Challenge Agent) |
| Conditions before release | **Conditions Precedent (CP)** / **Conditions Subsequent (CS)**, with due dates |
| Drawdown | **Disbursement Request** · tranche, value date, beneficiary account |
| Release checks | **Pre-Disbursement Compliance Checklist** |
| Audit pack | **Audit Trail Report** |
| Time saved | **TAT & Productivity Analytics** |
| LOS assistant | **Credit Copilot**: formal, concise wording (no "Got it —" or "I'll…"); it states facts and the next action |
| Approve / Send back / Reject | **Recommend** · **Sanction** · **Return to RM / Underwriting (with remarks)** · **Decline** |

**F10 — visual and options**
- **Header bar:** bank logo slot, product name, environment tag, global search (borrower / CIN / proposal ID),
  notifications, user and role.
- **Work queue:** a table with proposal ID, borrower, facility, exposure, internal rating, stage, **ageing / SLA**
  (green / amber / red), assigned officer, priority. Filters by stage, rating, SLA breach; sort; quick actions.
- **Executive dashboard** (top of the pipeline): proposals in pipeline, exposure in ₹ Cr by stage, average
  TAT, SLA breaches, sanctions this month, auto-population rate.
- **Proposal header:** proposal ID, borrower, CIN, internal and external rating, proposed limit, product,
  tenor, TAT so far, stage tracker with time at each stage.
- **Tags and pills everywhere:** rating grade, risk severity (High / Medium / Low), CP/CS, SLA, data
  provenance (AI · Document p.12 · RM · Underwriting), deviation flags.
- **Visual system:** a restrained palette (navy / slate, semantic colours only for status), denser
  typography, tabular numbers, line icons (inline SVG) instead of ✓/●/○ characters, consistent cards and
  tables, skeleton loading, empty states written in product language.
- **Same flow and rules underneath:** labels come from `config/flow.yaml` (stages, roles), so a bank can
  rename them.

### Confirmed with the user (2026-11-06)
- F5: yes — an answered suggestion disappears and a **different relevant question takes its place** (e.g. from the
  case: open objections, the changes made, missing points), so the user always has two fresh ones.
- F6: yes — Credit Risk changed the amount and pressed **Send back to Relationship Manager**.

## Round 4 — Madras Fertilizers walkthrough, Credit Underwriting → Sanction (2026-11-06)

Case LOS-261106-F09E. The CAM engine said **Decline**: internal rating D (45.8/100), hard-rule failures
HR_NO_CRITICAL_EXCEPTIONS and HR_KYC_COMPLETE, DSCR 0.86x against a 1.2x minimum, Debt/EBITDA 7.67x against a
4.0x maximum. The proposal still went RM → Underwriting (Recommend) → Sanction with no warning and no gate.

| # | Observation | Cause (from the code) | Fix to make |
|---|---|---|---|
| F11 | The **Key Risk Challenges** shown to Credit Underwriting were hard to understand, and none said what to do about them. | The card shows the engine's challenge text and its "required response", which is written for a credit committee ("Provide the lender-wise debt schedule…"). Nothing links a challenge to an action on this screen, so the officer can't tell which button resolves it. | Rewrite each challenge as three short lines: **what is wrong** (one sentence, with the figure and the policy limit), **why it matters**, and **suggested action(s)**. Each action is a button that takes the officer to the right place: **Override a figure** (scrolls to and opens the field), **Reduce the amount** (prefilled with the amount that brings the ratio within policy, if one exists), **Return to RM for documents** (remarks prefilled with the documents asked for), **Add a condition**, **Record a justification** (deviation note), or **Decline**. A challenge is marked *addressed* once one of its actions is taken or a justification is recorded. |
| F12 | Copilot was asked "what do I have to do" and "reading the risks, do I change the amount requested". It gave no concrete next steps. | The first answer pasted the engine's generic list of required responses. The second was answered literally ("The amount requested is 240.0 Cr"). The Copilot reads the record but knows nothing about this officer's available actions, the policy limits or how a challenge maps to an action. | Give the Copilot an **action plan** tool. For the current role it returns numbered steps built from open challenges, hard-rule failures and missing fields. Each step has a **Go there** link (scroll and highlight) and, where possible, a **Do it** button (the existing confirm-then-act flow). Advisory questions get a computed answer, e.g. for the amount: "At 4.0x Debt/EBITDA the borrower can carry ₹180 Cr of debt; it already has ₹345 Cr, so no amount brings leverage within policy. Options: return to RM for a debt reduction plan, record a policy deviation with mitigants, or decline." The model words the answer; the numbers come from the engine (number-guard stays). |
| F13 | The header shows internal rating **D**, but everything below, in every role's screen, was green. | Green on a credit data field means **provenance** ("Auto-populated"), not health. The 32 fields hold raw amounts and text only. No coverage or leverage ratio is a field, so nothing can turn red. The engine's Decline and hard-rule failures appear only inside the Recommendation text. | (a) A **risk summary strip** under the header for every role: engine recommendation (Decline / Approve with conditions / Approve), hard-rule failures, rating, and the 4–5 key ratios against policy (DSCR, interest cover, Debt/EBITDA, current ratio, TOL/TNW), coloured **red / amber / green by policy**, with an icon and label. (b) Make provenance tags neutral grey so green means good. (c) **Gate:** Submit / Recommend / Sanction against an engine **Decline** or a hard-rule failure needs a mandatory justification ("Proceeding despite: …"). It is recorded as a deviation, shown to the next approver and included in the audit pack. |
| F14 | (Found while checking F11) The leverage challenge reads "Debt/EBITDA **rose** from 13.2x to 7.67x". | `src/agents/challenge_agent.py:286` always says "rose", even when the ratio fell. | Word it by direction ("fell from 13.2x to 7.67x but is still above the 4.0x policy maximum"). Check the other challenge and observation templates for the same bug. |
| F15 | The **TAT & Productivity** page is overwhelming and not intuitive. Simplify it and show stats that explain **outcomes**. | The page shows every run statistic (engine runs, LLM calls, sections reused, API calls, touches by role…) at the same weight. Little of it says what happened to the proposals. | **Top row, 4 outcome tiles:** decisions (sanctioned / declined / in progress); average time to sanction and to disbursement against the manual baseline; data auto-filled %; **decisions that went against the engine** (e.g. "1 recommended despite a Decline"). **What happened:** 3–4 plain sentences. **Where proposals wait:** one chart (time per stage). **Quality:** sanction rate, rework rate, SLA compliance %, overrides concurred / returned. Engine, agent and LLM run details go into a collapsed **Run details** section. The per-proposal table keeps a column for the engine recommendation against the final decision. |
