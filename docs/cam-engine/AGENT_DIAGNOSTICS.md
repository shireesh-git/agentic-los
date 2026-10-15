# Agent Evaluation & Debug Harness (M6.1)

Run any of the 7 pipeline agents on its own, on a cached case, and see what it
actually did. The findings below come from reading the code and running the
harness on MFL001, APOL001 and ABCE001 (October 2026), not from the earlier
documentation.

## Commands

```bash
# one agent (runs only what it depends on, plus later agents to observe consumption)
python scripts/test_agent.py --case MFL001 --agent financial_analysis
python scripts/test_agent.py --case MFL001 --agent validation --no-downstream

# several agents
python scripts/test_agent.py --case MFL001 --agent all --stop-after policy
python scripts/test_agent.py --case MFL001 --agent all            # all 7, narrative in plan mode

# same agent, several cases (comparison table at the end)
python scripts/test_agent.py --agent financial_analysis --cases APOL001,MFL001

# narrative without the 20–50 minute CAM
python scripts/test_agent.py --case MFL001 --agent narrative                          # plan: fact pack + 21 prompts, no LLM
python scripts/test_agent.py --case MFL001 --agent narrative --narrative-mode llm \
       --sections financial_analysis,benchmarking --show-prompts                     # only these sections hit the LLM
python scripts/test_agent.py --case MFL001 --agent narrative --narrative-mode template
python scripts/test_agent.py --case MFL001 --agent narrative --narrative-mode full   # the production CAM (checkpoints on)

# before / after a prompt or code change
python scripts/test_agent.py --case MFL001 --agent narrative --save before
python scripts/test_agent.py --case MFL001 --agent narrative --compare before

# other
python scripts/test_agent.py --list                        # each agent's contract, from the code
python scripts/test_agent.py --snapshots --cases APOL001,MFL001
python scripts/test_agent.py ... --json [--show-output]    # machine-readable report
python scripts/test_agent.py ... --refresh-snapshot        # re-run data_ingestion
```

API (same engine): `GET /api/diagnostics/agents` (contracts) and
`POST /api/diagnostics/agents/run` with `{"agent", "cases", "stop_after", "narrative_mode", "sections",
"refresh_snapshot", "include_output"}`.

Every run is written to `output/agent_harness/runs/*.json`; baselines to
`output/agent_harness/baselines/{case}/{agent}/{label}.json`.

## Caching

```
DMS / documents → extraction (per-file OCR cache, storage/cache/extractions — existing)
               → data_ingestion → case snapshot (storage/cache/agent_snapshots/{case}.pkl — new, dev-only)
               → individual agents
```

* The existing per-file extraction cache already avoids repeated OCR; the new
  snapshot also skips the rest of ingestion (DMS fetch, report processing,
  verification, overrides) — MFL001: 23 s fresh, milliseconds from the snapshot.
* A snapshot is reused while the company record, the files in
  `storage/documents/{case}/` and the ingestion code are unchanged (fingerprint);
  otherwise it is rebuilt automatically. `--refresh-snapshot` forces it.
* Snapshots are pickles read only by this tool and git-ignored.

## What each report contains

Agent, case, start/end, duration (now measured with `perf_counter`), execution
mode, LLM invoked and every call (provider, model, full system prompt and prompt,
response, timing — never keys), prompt version and code version (hash of the
agent's source files), input summary, raw output, structured output with types
and empty flags, evidence, confidence, checks against the agent's actual
contract, warnings, errors, and for every output key the agents that **read it at
runtime** (tracked) plus the readers found in the code. Status: PASS / PARTIAL
(warnings) / FAIL (error or a failed check).

## Pipeline logging (production)

Each agent now ends with a line such as

```
[AGENT] financial_analysis status=completed execution_mode=deterministic llm_invoked=false llm_calls=0 output_present=true duration_ms=0.746
[AGENT] data_ingestion status=completed execution_mode=io llm_invoked=false llm_calls=0 output_present=false duration_ms=23025.9 empty_outputs=bureau_data,...
[AGENT] narrative status=completed execution_mode=llm+cached llm_invoked=true llm_calls=3 output_present=true duration_ms=...
```

Modes: `deterministic`, `empty` (completed with no content), `skipped` (missing
requirements), `failed`, `io` / `io+cached` (ingestion), `template`, `llm`,
`llm+cached`, `cached` (narrative sections from checkpoints). The same fields are
stored in `pipeline_log[*].diagnostics` and shown in the workspace Runs tab.

## What the 7 agents actually do

| Agent | Typical time | LLM | Real work | Output consumed? |
|---|---|---|---|---|
| data_ingestion | 2–25 s | no | DMS fetch, extraction, overrides, hashes | bureau/gst → validation, policy; **6 of 9 outputs never read** |
| pep_screening | < 1 ms | no | DIN lookup in a 7-entry in-code list | pep_result → narrative; **4 of 5 outputs never read** |
| financial_analysis | < 1 ms | no | 27 formula ratios per period | latest_ratios → policy, narrative; **multi_period_ratios never read** |
| validation | 1–3 ms | no | ~20 rule checks | exceptions → policy, narrative, case |
| benchmark | < 1 ms | no | peer bands, 5 sectors | view → narrative, latest → policy; 2 outputs never read |
| policy | 1–2 ms | no | 9 hard rules, weighted score, recommendation | outcome → narrative; score/recommendation → case |
| narrative | 0.3 s fact pack + **~50 s per LLM section** | yes | fact pack (≈49 keys, much of it computed here) + 21 LLM sections | case record, CAM, M1–M6 |

The analytical agents are fast because they are small deterministic formula
engines running on a few dozen numbers — that is genuine work, not a no-op. The
narrative's 20–50 minutes is the LLM writing 21 sections (MFL001: 183,357 prompt
characters; one section = 50.6 s on NVIDIA NIM gpt-oss-20b); building the fact
pack takes about 0.3 s.

### data_ingestion
* **Purpose / processing:** DMS fetch (uses files on disk if ≥ 5; otherwise tries to
  generate them), report OCR, `extract_all_documents`, uploaded-financial overrides
  (replaces `financials`), SHA-256 verification, ETB analytics, and copies the
  cached Probe42 bundle from `company_data['external_data']`.
* **Output:** `mca_data, bureau_data, market_data, gst_data, rating_data` (copied),
  `web_crawl_news, swot_signals, social_media` (**hard-coded empty**), `downloaded_reports`.
* **Consumers:** bureau_data → validation & policy; gst_data → validation. Nothing
  reads mca/market/rating (the fact builder reads `external_data` directly),
  the three placeholders, or downloaded_reports.
* **Defects found:** (1) **MFL001 extraction is abandoned entirely** —
  `find_best_document(..., "provisional_financials")` picks
  `unaudited_results_fy2026.pdf` and passes it to the XLSX-only
  `extract_provisional_financials`; openpyxl raises and the whole extraction is
  skipped with only a progress message, so none of the 4 annual reports is read.
  (2) The DMS generator import fails for every company (`KeyError: 'FY2022'`).
  (3) MFL001 has no cached bureau/GST bundle, so every cross-source validation is
  skipped for it.

### pep_screening
* **Processing:** exact DIN match against `_PEP_DATABASE` (7 in-code entries) and an
  exact-name sanctions list. No external service, no fuzzy matching.
* **Output / consumers:** `pep_result` → narrative fact pack. `adverse_media_articles`
  (0), `adverse_headlines` ([]), `social_controversy_index` (0.0) are **constants**;
  `directors_screened` is unread.
* **Bug:** the progress message reads `result.total_hits`, which does not exist —
  it always says "0 hit(s)".

### financial_analysis
* **Processing:** `compute_multi_period_ratios` + `compute_all_ratios(latest)` — the
  same 27 ratios, the latest period computed twice. No growth, trend,
  working-capital narrative or credit implications (ratios only).
* **Consumers:** `latest_ratios` → policy scoring and narrative (strengths, risks,
  cash flow). **`multi_period_ratios` is never read**: the fact pack's
  `ratio_analysis`, which every CAM ratio table uses, is recomputed by
  `cam_fact_builder.build_ratio_summary` (values currently identical).

### validation
* **Processing:** `run_all_validations` — structural, cross-source, analytical,
  temporal, NTB documents, conduct, covenants, group signals, extraction, ETB.
* **Consumers:** policy (tier-1 critical-exception rule, tier-3), narrative, case.
* **Concerns:** NTB document checks are called with KYC / board resolution /
  collateral documents hard-coded as present, so they can never fire.
  Cross-source checks silently do nothing when bureau/GST data is absent (MFL001).

### benchmark
* **Processing:** recomputes every ratio for every period (does not use
  financial_analysis) and compares with in-code peer bands for manufacturing,
  infrastructure, pharma, logistics and construction EPC only.
* **Consumers:** `view` → narrative; `latest_benchmarks` → policy. `benchmarks` and
  `worst_benchmarks` are unread duplicates.
* **Concern:** other sectors get no benchmarks at all.

### policy
* **Processing:** 9 tier-1 rules, weighted tier-2 score, tier-3 recommendation,
  collateral cover.
* **Consumers:** `outcome` → narrative; score / recommendation / tier-1 → case.
  `collateral_coverage` unread.
* **Concern:** `HR_COMPANY_ACTIVE` and `HR_KYC_COMPLETE` always pass — MCA status
  and KYC documents are not actually checked.

### narrative
* **Consumes correctly:** validation exceptions, benchmark view, policy outcome,
  latest ratios, PEP result (verified at runtime: identical values in the fact pack).
* **But also performs analysis itself** (14 fact-pack sections with no analytical
  agent behind them): ratio_analysis (duplicate), financial_summary + growth,
  credit_strengths, key_risks, cash_flow_repayment (treats a working-capital limit as
  an amortising loan), financial_projections + stress tests, industry_analysis,
  compliance_checks, drawing_power (counts all receivables as < 90 days),
  facility_pricing, core_banking_analysis, external_intelligence (reads
  `external_data` directly), plus **mock data**: `social_media_analysis` (in-code
  profiles) and `web_crawl_news` — **fabricated headlines with the borrower's name
  attributed to real outlets** ("… wins NHAI highway project worth ₹800 Cr —
  Economic Times"), fed to the Industry Analysis and Social Media section prompts.
* **Prompts that make the LLM compute:** financial_analysis asks for a "YoY Growth"
  column for every P&L line (only revenue growth is in the data) and an "OCF/PAT
  ratio"; operational_kpis says "extract and compute the value" and embeds
  infrastructure benchmark ranges in the prompt. The template renderer computes
  CAGR and YoY growth itself.
* 10 of 21 sections receive one or more empty data keys for MFL001 (e.g. infra_metrics,
  covenant_history, charges_data).

## Placeholder / no-op outputs

* data_ingestion: `web_crawl_news`, `swot_signals`, `social_media` (constants).
* pep_screening: `adverse_media_articles`, `adverse_headlines`, `social_controversy_index` (constants).
* policy: `HR_COMPANY_ACTIVE`, `HR_KYC_COMPLETE` (always pass); validation NTB document checks (always pass).
* No agent is a complete no-op: each of the 6 analytical agents produces a real,
  consumed result; the issues are dead outputs, duplicated work and mock inputs.
