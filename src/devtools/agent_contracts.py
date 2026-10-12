"""
What each of the 7 pipeline agents actually does — derived from the code (October 2026),
not from the documentation. The harness prints these next to runtime evidence, and the
evaluation checks are written against these contracts.

``consumers`` maps each output key to the code that reads it; an empty list means
nothing downstream reads it. The harness also observes reads at runtime.
"""

AGENT_ORDER = ["data_ingestion", "pep_screening", "financial_analysis", "validation", "benchmark", "policy",
               "narrative"]

# Source files whose content identifies the version of an agent's behaviour.
SOURCE_FILES = {
    "data_ingestion": ["src/agents/ingestion_agent.py", "src/agents/financial_overrides.py",
                       "src/services/document_extractor.py", "src/services/dms_service.py"],
    "pep_screening": ["src/agents/screening_agent.py", "src/services/pep_service.py"],
    "financial_analysis": ["src/agents/analysis_agents.py", "src/engines/ratio_engine.py"],
    "validation": ["src/agents/analysis_agents.py", "src/engines/credit_assessment.py",
                   "src/engines/validation_engine.py"],
    "benchmark": ["src/agents/analysis_agents.py", "src/engines/benchmark_engine.py"],
    "policy": ["src/agents/analysis_agents.py", "src/engines/policy_engine.py", "config/rules.yaml"],
    "narrative": ["src/agents/narrative_agent.py", "src/engines/cam_fact_builder.py",
                  "src/engines/cam_llm_renderer.py", "src/engines/cam_sections.py"],
}

CONTRACTS = {
    "data_ingestion": {
        "purpose": "Collect the borrower's documents and data and make them available to the other agents.",
        "inputs": ["company_data (borrower, financials, external_data bundle)", "storage/documents/{entity}/",
                   "reference annual-report folder", "extraction / ETB in-memory stores"],
        "prompt": None,
        "processing": [
            "dms_service.fetch_documents — uses files already on disk when 5+ exist; otherwise tries to generate "
            "them with scripts/generate_poc_documents.py (that import currently fails for every company: KeyError "
            "'FY2022').",
            "ingest_downloaded_documents — PyMuPDF/OCR of reference annual reports.",
            "extract_all_documents — PDF/XLSX/JSON parsing with a per-file content-hash cache on disk.",
            "apply_uploaded_financial_overrides — REPLACES company_data['financials'] with uploaded statements.",
            "verify_batch — SHA-256 fingerprints of PDFs.",
            "run_etb_analytics — when conduct data was extracted.",
            "External payloads — copied from company_data['external_data'] (cached Probe42 bundle); no API call.",
        ],
        "outputs": {
            "mca_data": "dict", "bureau_data": "dict", "market_data": "dict", "gst_data": "dict",
            "rating_data": "dict", "web_crawl_news": "dict (hard-coded empty)", "swot_signals": "dict (hard-coded {})",
            "social_media": "dict (hard-coded {})", "downloaded_reports": "dict",
        },
        "side_effects": ["company_data['extraction']", "company_data['financials'] (overrides)",
                         "company_data['document_verification']", "company_data['etb_analysis_data']"],
        "consumers": {
            "bureau_data": ["validation (cross-source checks)", "policy (tier-1 bureau / wilful-defaulter rules)"],
            "gst_data": ["validation (revenue vs GST)"],
            "mca_data": [], "market_data": [], "rating_data": [],
            "web_crawl_news": [], "swot_signals": [], "social_media": [], "downloaded_reports": [],
        },
        "notes": [
            "The narrative fact builder reads company_data['external_data'] directly, so mca/market/rating from this "
            "agent are never used.",
            "web_crawl_news / swot_signals / social_media are constants; the narrative step later generates its own "
            "(mock) news and social-media data.",
        ],
    },
    "pep_screening": {
        "purpose": "Screen directors and promoters against PEP and sanctions lists.",
        "inputs": ["company_data['directors']"],
        "prompt": None,
        "processing": [
            "pep_service.screen_directors — exact DIN lookup in an in-code dictionary (_PEP_DATABASE, 7 entries) "
            "and an exact-name check against an in-code sanctions list. No external screening service.",
        ],
        "outputs": {"pep_result": "PEPScreeningResult", "adverse_media_articles": "int (constant 0)",
                    "adverse_headlines": "list (constant [])", "social_controversy_index": "float (constant 0.0)",
                    "directors_screened": "int"},
        "consumers": {"pep_result": ["narrative (fact_pack['pep_screening'])"], "adverse_media_articles": [],
                      "adverse_headlines": [], "social_controversy_index": [], "directors_screened": []},
        "notes": ["Progress message reports the real hit count (fixed in M6.2)."],
    },
    "financial_analysis": {
        "purpose": "Compute the financial ratios.",
        "inputs": ["company_data['financials'] (after ingestion overrides)"],
        "prompt": None,
        "processing": ["ratio_engine.compute_multi_period_ratios — 27 formula ratios per period (latest = last).",
                       "ratio_engine.compute_growth_metrics — YoY growth of key lines, OCF/PAT, revenue CAGR."],
        "outputs": {"multi_period_ratios": "{period: [RatioResult]}", "latest_ratios": "[RatioResult]",
                    "latest_period": "str", "growth_metrics": "dict"},
        "consumers": {"latest_ratios": ["policy (tier-2 scoring)", "narrative (strengths, risks, cash-flow section)"],
                      "multi_period_ratios": ["benchmark", "narrative (fact_pack['ratio_analysis'])"],
                      "growth_metrics": ["narrative (fact_pack['financial_summary'] growth)"], "latest_period": []},
        "notes": ["Ratios and growth are authoritative here; the fact pack and benchmark reuse them (M6.2).",
                  "No credit commentary is produced here (that is M1–M6 and the narrative)."],
    },
    "validation": {
        "purpose": "Check the data for structural, cross-source, analytical, temporal and policy exceptions.",
        "inputs": ["company_data (financials, provisional, exchange_filing, extraction, conduct, covenants)",
                   "data_ingestion.bureau_data", "data_ingestion.gst_data"],
        "prompt": None,
        "processing": ["validation_engine.run_all_validations — rule checks (balance sheet, PAT, EBITDA, revenue vs "
                       "exchange/GST, debt vs bureau, DPD, receivable spike, negative OCF, margin decline, stale "
                       "financials, NTB documents, conduct, covenants, group signals, extracted revenue, ETB flags)."],
        "outputs": {"exceptions": "[ValidationException]"},
        "consumers": {"exceptions": ["policy (tier-1 critical-exception rule, tier-3)", "narrative (fact pack)",
                                     "case record"]},
        "notes": ["NTB document checks use data_ingestion's document_inventory (files on disk, or a declared "
                  "set for the synthetic demo borrower) — M6.2."],
    },
    "benchmark": {
        "purpose": "Compare the borrower's ratios with sector peers.",
        "inputs": ["company_data['financials']", "borrower.sector / subsector"],
        "prompt": None,
        "processing": ["benchmark_engine.benchmark_all_periods — compares financial_analysis.multi_period_ratios "
                       "with in-code peer bands for 5 sectors (M6.2: no recomputation)."],
        "outputs": {"view": "BenchmarkView", "benchmarks": "{period: [BenchmarkResult]}",
                    "latest_benchmarks": "[BenchmarkResult]", "worst_benchmarks": "[BenchmarkResult]"},
        "consumers": {"view": ["narrative (fact_pack['benchmark_summary'])"], "latest_benchmarks": ["policy"],
                      "benchmarks": [], "worst_benchmarks": []},
        "notes": ["Sectors without a peer table (IT, healthcare, hospitality, NBFC, real estate, trading, energy) get "
                  "no benchmarks at all."],
    },
    "policy": {
        "purpose": "Apply hard rules, compute the risk score and assemble the system recommendation.",
        "inputs": ["validation.exceptions", "financial_analysis.latest_ratios", "benchmark.latest_benchmarks",
                   "data_ingestion.bureau_data", "company_data (borrower, facility, directors, conduct, collateral)"],
        "prompt": None,
        "processing": ["policy_engine.tier1_hard_rules (9 rules)", "tier2_scoring (weighted 40/25/20/15)",
                       "tier3_recommendation", "collateral coverage on forced-sale value"],
        "outputs": {"outcome": "PolicyOutcome", "tier1_decisions": "[PolicyDecision]", "risk_score": "RiskScore",
                    "recommendation": "CreditRecommendation", "collateral_coverage": "float"},
        "consumers": {"outcome": ["narrative (fact pack)"],
                      "risk_score": ["case record (build_case_result)"],
                      "recommendation": ["case record (build_case_result)"],
                      "tier1_decisions": ["case record (build_case_result)"], "collateral_coverage": []},
        "notes": ["HR_COMPANY_ACTIVE (MCA status) and HR_KYC_COMPLETE (document inventory) are evidence-based: "
                  "pass / fail / not_verified; a not-verified rule blocks approval (refer)."],
    },
    "narrative": {
        "purpose": "Build the fact pack and write the CAM.",
        "inputs": ["validation.exceptions", "benchmark.view", "financial_analysis.latest_ratios", "policy.outcome",
                   "pep_screening.pep_result", "company_data (everything, incl. external_data)"],
        "prompt": "SYSTEM_PROMPT + one instruction per section (src/engines/cam_sections.py, PROMPT_VERSION); "
                  "the data is a JSON slice of the fact pack.",
        "processing": [
            "cam_fact_builder.build_cam_fact_pack — consumes the analytical agents' assessment, but ALSO computes: "
            "ratio_analysis for every period (again), revenue growth, credit strengths and key risks, cash flow and "
            "repayment, projections and stress tests, industry analysis, compliance checks, drawing power, pricing, "
            "CRILC, charges, hierarchy; and calls mock services for social media, core banking and web news.",
            "cam_llm_renderer — 21 LLM sections (one at a time on Ollama), checkpointed by prompt hash; or the "
            "template renderer, which computes CAGR and YoY growth itself.",
        ],
        "outputs": {"fact_pack": "dict (~40 sections)", "cam_text": "markdown", "narrative_mode": "str"},
        "consumers": {"fact_pack": ["case record → CAM HTML/PDF, one-pager, chat, credit observations (M1–M6)"],
                      "cam_text": ["case record → CAM HTML/PDF"], "narrative_mode": ["case record"]},
        "notes": [],
    },
}

# Fact-pack sections the narrative step builds without any analytical agent behind them
# (from build_cam_fact_pack). Reported as lineage findings.
NARRATIVE_OWN_ANALYSIS = {
    "financial_summary": "built from statements; growth taken from financial_analysis.growth_metrics",
    "credit_strengths": "rules in _identify_strengths (thresholds in code)",
    "key_risks": "rules in _identify_risks (thresholds in code)",
    "cash_flow_repayment": "computed here; treats a working-capital limit as an amortising loan",
    "financial_projections": "projection_engine — projections and stress tests computed inside the narrative step",
    "industry_analysis": "in-code sector descriptions",
    "compliance_checks": "rules on external payloads",
    "drawing_power": "computed here; counts all receivables as < 90 days",
    "facility_pricing": "in-code pricing grid",
    "social_media_analysis": "in-code demo profile, labelled synthetic; otherwise not available",
    "core_banking_analysis": "core_banking_engine on company_data['core_banking']",
    "web_crawl_news": "verified feed only; otherwise marked not available (fabricated fallback removed in M6.2)",
    "crilc_exposure": "generated by crilc_report_generator",
    "external_intelligence": "read directly from company_data['external_data'] (bypasses data_ingestion)",
}

# M6.1 found two section prompts asking the LLM to compute (YoY growth, OCF/PAT, KPI values). M6.2 supplies
# those figures deterministically and changed the instructions; the harness now scans the live prompts.
PROMPT_COMPUTE_REQUESTS: dict = {}
