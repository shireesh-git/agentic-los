# Credit Risk Observations (Step 1)

Structured credit findings derived **deterministically** from the outputs the
pipeline already produces. The LLM is optional and only rewords an observation
that has already been detected.

## Where it plugs in

```
7-agent pipeline (unchanged) ──► fact pack (unchanged)
                                    │  financial_summary · ratio_analysis · benchmark_summary
                                    │  validation_exceptions · policy_decisions · policy_thresholds
                                    ▼
             src/engines/observation_engine.py  (12 detectors, thresholds in config/rules.yaml)
                                    ▼
             case["observations"]  — stored with the run in case_runs (no new table)
                                    ▼
   GET  /api/cases/{id}/observations[?run_id=]     list + counts (back-fills older runs)
   PATCH /api/cases/{id}/observations/{obs_id}     {status, note}  — analyst review
   POST /api/cases/{id}/observations/explain       {observation_ids?} — AI wording, on demand
                                    ▼
   Workspace: "Credit observations" tab + Overview card
```

- Observations are computed in `build_case_result` after the pipeline, from that
  run's fact pack. They do not change the recommendation, the risk score or the CAM.
- No ratio is recomputed. The engine only takes period-on-period changes between
  values the engines already produced (growth %, change in days / bps / x) and
  compares them with thresholds.
- A failing detector is logged and skipped; observations can never fail a run.

## Model

`src/models/observations.py` — `CreditObservation`:
`observation_id, case_id, category, title, severity, status, summary,
detailed_explanation, metrics, period_comparison, trigger, evidence_references,
recommended_investigation, source_type, generated_by, created_at`, plus
`review` (analyst note) and `ai_explanation` (optional LLM wording).

- Severity: `CRITICAL · HIGH · MEDIUM · LOW · INFO`
- Status: `NEW · INVESTIGATION_REQUIRED · EXPLAINED · ACCEPTED · DISMISSED`
- `observation_id` = `OBS-{case_id}-{RULE_ID}` (stable across runs).

## AI explanations

`src/services/observation_narrator.py`. One small LLM call per observation. The
model receives only that observation's facts and is told not to judge whether the
risk exists or to compute numbers. Its JSON reply is rejected, and the rule-based
text kept, if it quotes any figure not present in those facts (same check the CAM
renderer uses, `_unsupported_figures`). The AI text is stored separately in
`ai_explanation`; severity, metrics, trigger and the rule-based text never change.

## Detector mapping and the demo borrower

Demo borrower: **ABC Engineering & Infrastructure Ltd. (`ABCE001`)** —
`src/data/demo_companies.py`. NTB, unlisted, infrastructure EPC, ₹250 Cr
working-capital request. FY2023–FY2025 steady; FY2026 deteriorates; FY2027_P
provisional continues the trend. Comparison below is FY2025 → FY2026.

| # | Detector (rule_id) | Existing source metric | Trigger (default thresholds) | Expected for ABCE001 |
|---|---|---|---|---|
| 1 | Working Capital Deterioration (`WC_DETERIORATION`) | `financial_summary` revenue, trade receivables | receivables growth − revenue growth ≥ 20 pp (HIGH ≥ 30 pp) | **HIGH** — receivables +52.1% vs revenue +18.2% (gap 33.9 pp) |
| 2 | Earnings-to-Cash Conversion (`EARNINGS_CASH_CONVERSION`) | `financial_summary` EBITDA, operating cash flow; ratio `ocf_to_debt` | EBITDA ≥ 0 growth and OCF −20%, or OCF/EBITDA < 50% (HIGH < 25% or OCF < 0) | **HIGH** — EBITDA +1.5%, OCF −76.3%, conversion 16.8% |
| 3 | Increasing Leverage (`LEVERAGE_INCREASE`) | `financial_summary` total debt, EBITDA; ratio `debt_to_ebitda` | debt growth − EBITDA growth ≥ 15 pp, or Debt/EBITDA +0.5x (HIGH above policy max 4.0x) | **HIGH** — debt +71.9% vs EBITDA +1.5%; Debt/EBITDA 2.42x → 4.10x |
| 4 | Debt Servicing Pressure (`DEBT_SERVICING_PRESSURE`) | ratios `dscr`, `interest_coverage_ratio`; `policy_thresholds` | DSCR < 1.20 or ICR < 2.0 (HIGH; CRITICAL if DSCR < 1.0); within 10% and falling (MEDIUM) | **HIGH** — DSCR 1.67x → 1.19x; ICR 3.48x → 2.34x |
| 5 | Receivable Collection Risk (`RECEIVABLE_COLLECTION`) | ratio `debtor_days`; policy `max_debtor_days` | +15 days (MEDIUM); also above 90 days (HIGH); only above 90 (LOW) | **HIGH** — 80.0 → 103.0 days |
| 6 | Inventory Build-up (`INVENTORY_BUILDUP`) | ratio `inventory_days`; `financial_summary` inventory | +15 days and +25% (HIGH ≥ +30 days) | **MEDIUM** — 25.1 → 43.0 days (+71.3%) |
| 7 | Margin Compression (`MARGIN_COMPRESSION`) | `financial_summary.ebitda_margin_pct`; evidence `ANAL_MARGIN_DECLINE` | decline ≥ 200 bps (HIGH ≥ 400 bps or below policy floor 10%) | **MEDIUM** — 15.0% → 12.9% (210 bps) |
| 8 | Data Reliability Concern (`DATA_RELIABILITY`) | validation exceptions `XSRC_*`, `STRUCT_*`, `DOC_*` (credit alerts excluded) | any such exception; severity = worst exception | **HIGH** — `XSRC_GST_REVENUE_MISMATCH`: revenue ₹2,080 Cr vs GST ₹1,835 Cr (11.8%) |
| 9 | Sector Underperformance (`SECTOR_UNDERPERFORMANCE`) | `benchmark_summary` (P25 / median / P75) | ≥ 1 metric in weakest band or ≥ 3 below median (HIGH ≥ 2 in weakest band) | **HIGH** — 11 worse than peers, 3 in weakest band (inventory days, payable days, WC cycle) |
| 10 | Policy Exception / Deviation (`POLICY_DEVIATION`) | tier-1 hard rules; ratios vs `policy_thresholds` | failed hard rule (CRITICAL); ≥ 3 breaches (HIGH); else MEDIUM | **HIGH** — 5 breaches: DSCR, current ratio, Debt/EBITDA, ROE, debtor days |
| 11 | Liquidity Stress (`LIQUIDITY_STRESS`) | ratio `current_ratio`; policy `min_current_ratio` | below 1.25 (MEDIUM; HIGH < 1.0) or fall ≥ 0.20 (LOW) | **MEDIUM** — 1.45x → 1.15x |
| 12 | Financial Distress Signal (`FINANCIAL_DISTRESS`) | ratio `altman_z_score` | Z < 1.81 (HIGH); left safe zone / fell ≥ 0.30 into grey zone (LOW) | **LOW** — 3.01 → 2.29 (grey zone) |

Result for ABCE001: 12 observations — 8 HIGH, 3 MEDIUM, 1 LOW. The machine-checked
version is `tests/fixtures/abce001_expected_observations.json`, verified by
`tests/test_observation_engine.py::test_demo_borrower_triggers_the_designed_observations`.

### The demo borrower's story (₹ Cr)

| | FY2023 | FY2024 | FY2025 | FY2026 |
|---|---|---|---|---|
| Revenue | 1,450 | 1,600 | 1,760 | 2,080 |
| EBITDA (margin) | 217.5 (15.0%) | 243.2 (15.2%) | 264.0 (15.0%) | 268.0 (12.9%) |
| Operating cash flow | 150 | 170 | 190 | 45 |
| Total debt | 560 | 600 | 640 | 1,100 |
| Trade receivables | 318 | 352 | 386 | 587 |
| Inventory | 100 | 110 | 121 | 245 |
| Current ratio | 1.45x | 1.45x | 1.45x | 1.15x |
| DSCR | 1.54x | 1.61x | 1.67x | 1.19x |

FY2026: growth on fixed-price contracts squeezes the margin, municipal clients pay
late, inventory piles up at stalled sites, and the gap plus a ₹410 Cr capex
programme is funded with short- and long-term debt. Every statement balances
(EBITDA = income − costs, PAT = PBT − tax, assets = equity + LTD + current
liabilities, equity and cash roll forward); the only deliberate conflict is the
FY2026 GST turnover. Bureau, MCA and GST records are supplied in the company's
cached `external_data`, so no external call is made.

With the existing policy engine the case scores 42.8 (grade D) → **decline**: the
benchmark penalties (3 high, 8 medium) take the financial score to 0. The policy
engine was not changed.

## Configuration

`config/rules.yaml → credit_observations` holds every threshold and an `enabled`
flag per detector. Policy limits are read from `policy_thresholds`. Both are also
editable on the Settings page.
