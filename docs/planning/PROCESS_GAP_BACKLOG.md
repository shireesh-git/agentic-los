# Process Gap Backlog — code enhancements

> **Scope:** functional gaps between the bank's *Current-State Functional Process* and this
> codebase that can be closed **in code now**, without bank inputs. Integrations, bank models,
> templates and production hardening are out of scope here; see
> [MODERNISATION_GAP_ANALYSIS.md](MODERNISATION_GAP_ANALYSIS.md) groups A and B.
> Where a bank rule is unknown, the build uses a **configurable, labelled default** in YAML,
> as the code already does for the authority matrix.
>
> Every gap below was confirmed against the code (commit `82117cf`).
> Size: **S** ≤ 1 day · **M** 2–4 days · **L** 1–2 weeks.

---

## Build order at a glance

| Wave | IDs | Theme | Why this order |
|---|---|---|---|
| 1 | G-01, G-02, G-03, G-04 | Workflow engine: outcomes, routes, decision record | Everything else plugs into the engine |
| 2 | G-05, G-06 | Read-only reviewers; conditional approval routing | Needs the wave-1 engine changes |
| 3 | G-07, G-08, G-09 | Prospect Sourcing parity | Independent; visible in the first demo step |
| 4 | G-10, G-11, G-12 | IP/AP stage gates and check rules | Needs the wave-1 gate hooks |
| 5 | G-13, G-14 | Facility hierarchy; modification variants | Data-model changes; touch many views |
| 6 | G-15 | UI, docs, MIS, seed data catch-up | After the behaviour settles |

---

## Wave 1: Workflow engine

### G-01 · Defer as a real workflow state · **L**
**Process:** §4 and §5 (PS and IP Note outcomes: *Defer, retain in the deferred route until taken up again*).
**Code today:** `Defer` is only a value of `sourcing_decision`, recorded at creation
([service.py:78](../../src/los/service.py#L78), [service.py:3556](../../src/los/service.py#L3556)).
Nothing reads it, so a deferred prospect is created as an active `DRAFT` at `ps_maker`.
There is no defer action in [workflow.py](../../src/los/workflow.py).
**Build:**
- New status `DEFERRED` (non-terminal), plus action `defer` on maker steps listed as
  `defer_allowed` in YAML (default: `ps_maker`, `ip_note`).
- `defer` requires a reason, a deferred-until date and conditional remarks. Store an
  `app["deferral"]` history (who, when, until, reason, reactivated_at, by).
- Action `reactivate`, available to the step role (and admin). It returns the case to the
  *same* step with its data intact and resets the SLA clock.
- SLA, escalation and assignment are paused while deferred. The dashboard gets a
  "Deferred" bucket with a "due for review" flag once the deferred-until date passes.
- The creation-time `sourcing_decision`: keep it as the RM's recorded view, but **stop
  using `Defer`/`Decline` there**. They become stage outcomes (here and in G-02).
**Tests:** defer → no actions except reactivate; reactivate restores the step and assignee;
SLA is not breached while deferred; reason and date are mandatory; the audit events are there.

### G-02 · Outcome sets per step match the process · **M**
**Process:** Drop (with reason) at PS, IP Note and AP. Final Disbursement Approval is
Submit/Rework only. Disbursement Checker and VP are Submit/Rework.
**Code today:** `ACTIONS_BY_KIND` gives makers `submit / withdraw / propose_modification`,
so **makers cannot drop**. `dis_approver` is a `checker` step and therefore also offers
`reject / drop / recommend_modification`.
**Build:**
- Optional per-step `actions:` list in [config/los_workflow.yaml](../../config/los_workflow.yaml)
  that narrows (or explicitly widens) the kind's defaults, validated against the kind at load.
- Add `drop` to the maker base set; configure it on `ps_maker`, `ip_note`, `ap_note`
  (`pos_maker` per the process: "where allowed").
- `dis_checker`, `dis_approver`: `approve | return` only.
- Labels per step in YAML (`Submit`, `Recommend`, `Recommend for Sanction`, `Recommend
  for Disbursement`, …), so the UI shows the process wording.
- Drop reason: a configurable picklist plus free text.
**Tests:** the action matrix for every step matches YAML; drop at a maker step is terminal with
a reason; a disallowed action raises an error.

### G-03 · Remarks on every decision · **S**
**Process:** §3: "Every decision shall record the acting user, stage, date/time, outcome
and remarks."
**Code today:** `COMMENT_REQUIRED` covers only negative actions. Submit, approve and sanction
can be done with no remarks (the exception is `pos_checker`, which is hard-coded at
[service.py:578](../../src/los/service.py#L578)).
**Build:** a YAML flag `remarks_required: all | negative` (default `all`); remove the
`pos_checker` special case. Allocation steps are exempt.
**Tests:** submit/approve without remarks fails when the flag is `all`.

### G-04 · Standard review decision record · **M**
**Process:** AP VP Review records "decision, remarks, material-information date, committee
matters and significant changes". EVP AP records significant changes. Recommendations
Committee records minutes, key matters and the CEAC recommendation. The POS Maker records
material/significant changes. The Disbursement VP records significant changes.
**Code today:** `significant_changes` is captured **only at `dis_vp_review`**
([service.py:642](../../src/los/service.py#L642)). Material-information date is an entity
field, not part of the decision. Minutes exist only on sanction.
**Build:**
- Per-step `decision_fields:` in YAML: `significant_changes`, `material_information_date`,
  `committee_matters`, `minutes`, `ceac_recommendation`, each with a required flag.
- `act()` accepts a generic `decision_data` dict, validates it against the step's fields and
  stores it in `app["decisions"][]` and in the event detail. `dis_vp_review` moves onto the
  same mechanism.
- Committee pack and history show the prior decisions read-only ("each reviewer shall
  preserve prior decisions").
**Tests:** a required field is enforced per step; decisions are append-only; the pack shows them in order.

---

## Wave 2: Review integrity and routing

### G-05 · Read-only reviewers (edit-permission matrix) · **M**
**Process:** §3: "Checker and approval stages shall … not alter core proposal
information"; repeated in §10, §12 and §13.
**Code today:** `_workspace_may` ([service.py:1743](../../src/los/service.py#L1743)) allows
**any holder of the current step's role**. A checker, VP or committee on their own step can
therefore save parties, facilities, securities, pricing, ratings, CMA, proposal and disbursement
data (29 call sites).
**Build:**
- Classify every workspace operation into a **domain** (parties, facilities, securities,
  projects, esms, ewp, ratings, raroc, cma, proposal, pricing, fees, disops, conditions,
  documents, …) and an **intent**: `edit` (maker data) or `review` (CMA approve,
  Disbursement Memo review, document review, material-change review, condition-waiver approval).
- YAML `edit_matrix`: step → domains it may edit. The default is derived from the step kind:
  maker steps edit their stage's domains; checker, vp_review and committee steps get
  `review` intents only.
- Replace `_workspace_may(app, session, what)` with `_may(app, session, domain, intent)`.
  The UI hides the edit controls (the view returns `editable_domains`).
- Explicit exceptions where the process allows them: the Risk Maker and Post-Rating steps
  edit ratings and RAROC; the Disbursement Maker may complete "permitted pending" items.
**Tests:** for each reviewer step, every edit endpoint returns 403 and every review endpoint
works; for each maker step, its domains are editable.

### G-06 · Conditional, authority-driven approval routing · **L**
**Process:** §6 "Where configured, allocate the proposal for CRP review"; §8 "Remaining
ESMS, CRP, DMD or sanction authority steps are completed according to the applicable approval route."
**Code today:** steps run strictly in list order. `authority.required_authority()`
([authority.py:33](../../src/los/authority.py#L33)) is computed and recorded but **never changes
the route**. There is no ESMS/CRP processing step and no DMD step.
**Build:**
- Optional `when:` on a step in YAML: a small, safe condition language evaluated against
  the application. Examples: `amount_cr > 500`, `esms.category in [A, B]`,
  `deviations.open > 0`, `authority.final == "Board"`. No `eval`; parse into a whitelisted AST.
- `next_step` and `previous_maker` skip steps whose `when` is false. The decision is
  recorded in the event ("skipped: CRP review, condition false").
- New steps and roles (labelled demo): `ap_esms_crp` (ESMS/CRP Processing, role
  `esms_officer`) and `ap_dmd` (DMD Review, role `dmd`). Both are conditional.
- Sanction authority: `ap_sanction` assigns to the role that `required_authority` maps to
  (committee vs board vs delegated authority). The matrix moves into YAML.
- The application rail and dashboard show the *planned* route for this case, with skipped steps greyed out.
**Tests:** a small case skips DMD and a large one routes to it; ESMS category A routes to
ESMS/CRP; the route is recomputed when the amount changes before sanction; the skip is audited.

---

## Wave 3: Prospect Sourcing parity

### G-07 · Create a new prospect borrower in the LOS · **M**
**Process:** §4: "Add the primary borrower … Otherwise continue as a new customer."
**Code today:** `create()` requires `entity_id` to exist in the company catalog
([service.py:489](../../src/los/service.py#L489)), so the RM cannot source a company the
platform does not already know.
**Build:**
- `create_prospect_borrower` takes name, constitution, PAN, CIN, GSTIN, sector, subsector
  and address. It validates formats, runs the dedupe check (existing LOS, catalog/ETB
  demo), and registers a minimal borrower in the catalog marked `source: los_prospect`.
- Check whether `src/services/company_onboarding.py` / `/onboard` already does most of this,
  and reuse it if so.
- The CAM pipeline must cope with a sparse borrower: the case is enriched later at IP by
  documents and prefill.
**Tests:** create an unknown borrower → application created → duplicate PAN blocked/flagged.

### G-08 · Prospect Sourcing fields and discussion log · **M**
**Process:** §4: sector, subsector, sourcing branch; facility currency; discussion
participants, summary and status; project type, funding type, infra-finance qualification;
"a concluded discussion cannot carry a future discussion date".
**Code today:** one free-text `prospect_discussion`
([service.py:3502](../../src/los/service.py#L3502)). There is no subsector, sourcing branch
(it lives on the user only), currency, participants, discussion date, status or infra flag.
**Build:**
- Application: `subsector`, `sourcing_branch` (defaults to the user's branch),
  `infra_finance` (`qualifies: bool`, `basis`).
- Facility: `currency` (default INR; amounts stay in ₹ Cr with an optional `amount_fcy` +
  `fx_rate` for non-INR).
- `discussions[]`: date, participants (bank/client), mode, summary, status (`scheduled |
  concluded | follow_up`), next action. Validation: `concluded` ⇒ date ≤ today. The prospect
  status lives on the application. Keep the existing fields as the first entry (migration).
- Picklists (subsector, project type, funding type, prospect status) go in YAML.
**Tests:** a future-dated concluded discussion is rejected; currency is defaulted; the fields
carry through to the IP Note and copilot record.

### G-09 · PS submit gate · **S**
**Process:** §4 progression checks: borrower and facility present, existing-customer and
duplicate checks completed.
**Code today:** the identity/dedupe snapshot is taken at creation but never *acknowledged*.
The DD gate runs at `ps_maker`.
**Build:** submit at `ps_maker` requires: at least one facility; the dedupe result
acknowledged (or no matches); the ETB/NTB selection made; at least one discussion (if the
process requires it, configurable). Register these as rules in [rules.py](../../src/los/rules.py)
so they appear in the rule view and MIS.
**Tests:** submit is blocked until each item is satisfied.

---

## Wave 4: Stage gates and check rules

### G-10 · IP Note and AP-maker submission gates · **M**
**Process:** §5: "Mandatory IP documents, unresolved deviations and blocking checks must be
completed before submission"; §7 same for AP.
**Code today:** `ip_note` submit only needs a generated IP Note
([service.py:580](../../src/los/service.py#L580)). `DD_GATE_STEPS` excludes `ip_note` and
`ap_note`. Document stage gates run only at `dis_maker`.
**Build:** a generic `gates:` list per step in YAML, naming rule IDs from `rules.py`
(`dd_blocking`, `docs_mandatory_stage`, `deviations_resolved`, `esms_exclusion_approved`,
`raroc_current`, `cma_recorded`, `pricing_complete`, …). `act()` evaluates the step's
gates through the rule catalog instead of the hard-coded `if step.id == …` chain, so
existing gates move into config unchanged.
**Tests:** each gate blocks with a clear message and passes once resolved; the existing
gate tests still pass.

### G-11 · Check applicability by entity type / constitution, and validity · **M**
**Process:** §5: "Checks apply according to entity type and constitution … Expired or aged
checks must be retriggered based on their applicable validity rule."
**Code today:** 15 flat checks with a static `mandatory` flag
([verification.py:38](../../src/los/verification.py#L38)). Only *exceptions* expire and
re-screening has reminders; a completed check never goes stale.
**Build:**
- YAML matrix: check × (individual / company / LLP / partnership / trust / SPV) →
  `applicable`, `mandatory`; check → `validity_days` (labelled demo defaults).
- Apply it to the borrower and to each related party (party-level evidence already exists).
- A check whose result is older than its validity becomes `stale`: it is blocking if mandatory,
  and the UI shows "retrigger required". Retrigger keeps history (already supported).
**Tests:** an individual guarantor gets bureau-individual checks rather than MCA; an aged
check blocks submit until retriggered.

### G-12 · E&S excluded-activity exception · **S**
**Process:** §5: "An excluded environmental or social activity requires the specified
exception approval before progression."
**Code today:** the ESMS gate only enforces remarks on Yes/Not-available answers.
**Build:** any `Yes` on an exclusion item creates an ESMS exception that needs approval by a
configured role (default `compliance_vp`). Gate `esms_exclusion_approved` (via G-10) applies
at `ip_note` and `ap_note`.
**Tests:** Yes → blocked → approved → passes; re-answering voids the approval.

---

## Wave 5: Data model

### G-13 · Facility hierarchy: parent facilities and sublimits · **M**
**Process:** §5: "Identify parent facilities and any sublimits … takeover or reimbursement
information as applicable."
**Code today:** facilities are a flat list ([facilities.py](../../src/los/facilities.py)).
There are no `parent_facility_id`, takeover or reimbursement attributes.
**Build:** `parent_facility_id` (one level), with validation: sublimit ≤ parent and the sum
of sublimits may exceed the parent only if marked interchangeable. Exposure counts the parent
only. Add `takeover: {from_bank, outstanding_cr}` and `reimbursement: {expenditure_cr, period}`.
Update the sanction, letters, disbursement (draw against a sublimit within the parent's
balance), RAROC and pricing per facility.
**Tests:** exposure is not double-counted; a sublimit draw reduces both balances; the
letters show the hierarchy.

### G-14 · Modification route variants · **M**
**Process:** §9 and §10: "Modification route: initiate modification where sanctioned terms
require change … route the case to the applicable modification process."
**Code today:** every modification goes back to `ap_risk_maker`
([workflow.py:47](../../src/los/workflow.py#L47)).
**Build:** a modification captures its `type` (pricing / tenor / security / conditions /
amount / other) and the facilities affected. YAML maps type → re-entry step (for example,
pricing → `ap_risk_maker`; conditions → `ap_review`; amount increase → `ap_note`). The
snapshot diff limits re-review to the changed domains. On the second sanction, the sanction
letter is reissued as a new version, labelled "modified".
**Tests:** each type re-enters the configured step; the sanction letter version increments;
the modification status closes.

---

## Wave 6: Catch-up

### G-15 · UI, docs, MIS and seed data · **M**
- [los.js](../../src/ui/static/js/los/los.js) and templates: the deferred bucket, the per-step
  action labels, decision fields, read-only reviewer views, the planned route on the rail,
  the PS discussion log, and the facility tree.
- MIS: deferred count and ageing, drops by stage and reason, skipped-step stats.
- Demo seed: one deferred prospect, one dropped at IP, one routed via DMD, one modification.
- Docs: update [FUNCTIONAL_GUIDE.html](../FUNCTIONAL_GUIDE.html),
  [DEVELOPER_GUIDE.md](../DEVELOPER_GUIDE.md) (it still says SLAs use calendar days; the code
  uses working days) and [LOS_API_REFERENCE.md](../LOS_API_REFERENCE.md); regenerate the Postman collection.

---

## Already covered (no work needed)

These were checked and match the process:
- condition categories (PC, CP, PD, CPS, FC, NC, GC, FS) and covenant test frequency
- uploading back the signed sanction letter, with review
- rework to any earlier step with remarks and history kept
- duplicate LOS-application check
- name-screening compliance exception
- RAROC staleness
- material-change block after sanction
- partial execution with balance
- subsequent tranches
- Exit on final approval
- working-day SLAs
