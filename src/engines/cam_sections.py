"""
CAM prompt definitions: the system prompt and the ordered list of CAM sections.

Pure data, kept apart from the rendering logic in cam_llm_renderer so prompt
changes are reviewed on their own. Each section has an id and title; LLM
sections also have data_keys (the fact-pack slices the model sees), an
instruction and optionally max_tokens; skip_llm sections are rendered from
templates. Section output limits can also be set without code changes in
config/llm_providers.yaml (narrative.section_max_tokens).

Changing an instruction or SYSTEM_PROMPT changes the section prompt hashes, so
saved section checkpoints are regenerated; bump PROMPT_VERSION as well so the
change is traceable.
"""

# ═══════════════════════════════════════════════════════════════════════════════
# Section Definitions: Each section has a prompt builder + data slicer
# ═══════════════════════════════════════════════════════════════════════════════

CAM_SECTIONS = [
    # ── Structural (template-only) ──
    {
        "id": "cover_page",
        "title": "Cover Page",
        "skip_llm": True,
    },
    {
        "id": "toc",
        "title": "Table of Contents",
        "skip_llm": True,
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 1. Executive Summary
    # ══════════════════════════════════════════════════════════════════════════
    {
        "id": "executive_summary",
        "title": "1. Executive Summary",
        "data_keys": ["case_summary", "borrower_profile", "financial_summary",
                       "policy_decisions", "credit_strengths", "key_risks",
                       "facility_details", "infra_metrics"],
        "instruction": (
            "Write a comprehensive Executive Summary for a Credit Approval Memorandum.\n\n"
            "**Parameter Table** (render as markdown table with Source / Remarks column):\n"
            "| Parameter | Details | Source / Remarks |\n"
            "Include rows: Borrower Name, Constitution (Public Ltd/Private Ltd), CIN, "
            "Date of Incorporation, Nature of Activity, Credit Rating, Facility Type, "
            "Amount Requested (₹ Cr), Purpose, Risk Grade, Recommendation.\n\n"
            "**Narrative (2-3 paragraphs):**\n"
            "- Para 1: Company overview — name, sector, year of incorporation, promoter background, "
            "nature of business, current scale (revenue, assets, order book if infrastructure).\n"
            "- Para 2: Business highlights — key projects, recent performance, competitive advantages, "
            "credit rating rationale.\n"
            "- Para 3: Facility request — amount, purpose, recommended action "
            "(APPROVE/CONDITIONAL APPROVE/REFER/DECLINE), risk grade, composite score, "
            "key strengths and key concerns.\n\n"
            "Use formal Indian banking language. 300-400 words."
        ),
        "max_tokens": 2000,
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 2. Borrower Profile (Corporate Identification)
    # ══════════════════════════════════════════════════════════════════════════
    {
        "id": "borrower_profile",
        "title": "2. Borrower Profile",
        "data_keys": ["borrower_profile", "group_profile", "external_intelligence",
                       "industry_analysis"],
        "instruction": (
            "Write the Borrower Profile section focusing on Corporate Identification.\n\n"
            "(2.1) Corporate Identification Table — with **Source / Remarks** column:\n"
            "| Particulars | Details | Source / Remarks |\n"
            "Include rows: Company Name, CIN, PAN, Date of Incorporation, Registered State, "
            "Registered Address, Authorized Capital (₹ Cr), Paid-up Capital (₹ Cr), "
            "Listed Exchange, NSE/BSE Symbol, Credit Rating, Rating Agency, Employee Count.\n"
            "Fill each row's source as per the system rules (data provenance only).\n\n"
            "(2.2) Registered Address & Location — Full registered address, corporate office "
            "address if different, state, PIN code.\n\n"
            "(2.3) Business Overview — Brief company history (1-2 paragraphs), key milestones, "
            "sector positioning, nature of activities, geographic presence.\n\n"
            "200-300 words."
        ),
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 3. Client Background, Business Activity & Project Details
    # ══════════════════════════════════════════════════════════════════════════
    {
        "id": "project_details",
        "title": "3. Client Background, Business Activity & Project Details",
        "data_keys": ["case_summary", "borrower_profile", "industry_analysis",
                       "infra_metrics", "sector_kpis", "facility_details"],
        "instruction": (
            "Write a comprehensive section on the client's business activity and the specific "
            "project(s) for which the loan is requested. THIS IS A CRITICAL SECTION — the Credit "
            "Committee needs to understand WHAT exactly the loan finances.\n\n"
            "(3.1) Nature of Business — Describe the company's core business activities, revenue "
            "segments (EPC, BOT, HAM if infrastructure), key capabilities, and competitive "
            "positioning. Include a revenue segment breakdown table with Source column.\n\n"
            "(3.2) Project Details — For the specific project(s) linked to this facility request:\n"
            "Table with Source / Remarks column:\n"
            "| Parameter | Details | Source / Remarks |\n"
            "Include: Project Name, Location/Stretch, Length (km), Concession Model "
            "(EPC/BOT/HAM), Concession Period, Contract Value (₹ Cr), Appointed Date, "
            "PCOD/COD, Client/Authority (e.g., NHAI).\n"
            "\n"
            "(3.3) Project Components — If infrastructure project, show:\n"
            "| Component | Scope | Status | Source / Remarks |\n"
            "Include: Road Works (km), Structures (bridges, flyovers, ROBs), "
            "Toll Plazas/Infrastructure, Land Acquisition, Utility Shifting.\n\n"
            "(3.4) Project Model Key Features — If HAM/BOT:\n"
            "| Feature | Details | Source / Remarks |\n"
            "Include: Bid Project Cost (₹ Cr), Construction Period, O&M Period, "
            "Grant Component (% of BPC), Premium/Annuity, Traffic Risk allocation, "
            "Termination clauses.\n\n"
            "(3.5) Construction Status / Order Execution:\n"
            "Table: Project | Physical Progress % | Financial Progress % | Appointed Date | "
            "Target COD | Ahead/Behind Schedule | Source / Remarks.\n\n"
            "Use infra_metrics / sector_kpis to populate project-specific details. Include "
            "sub-sections 3.2–3.5 ONLY when the data contains project details; otherwise omit "
            "them and describe the business activity and the purpose of the facility.\n\n"
            "300-500 words."
        ),
        "max_tokens": 2500,
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 4. Group Companies, Shareholders & Promoter Details
    # ══════════════════════════════════════════════════════════════════════════
    {
        "id": "group_shareholders",
        "title": "4. Group Companies, Shareholders & Promoter Details",
        "data_keys": ["group_profile", "borrower_profile", "corporate_hierarchy",
                       "management_profile"],
        "instruction": (
            "Write the Group & Shareholding section:\n\n"
            "(4.1) Shareholding Pattern — Table with Source column:\n"
            "| Category | Holding (%) | Source / Remarks |\n"
            "Promoter & Promoter Group, Institutional (FII/DII), Public/Others, Total.\n"
            "\n"
            "(4.2) Group Structure — Parent company, subsidiary/associate companies, JV partners.\n"
            "Table: Entity Name | Relationship | CIN | Activity | Stake % | Source / Remarks.\n\n"
            "(4.3) Promoter Background — Key promoter details: name, stake, net worth, background.\n"
            "Table: Promoter Name | Stake % | Net Worth (₹ Cr) | Background | Source / Remarks.\n\n"
            "150-250 words."
        ),
        "max_tokens": 1500,
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 5. Directors & Key Management Personnel
    # ══════════════════════════════════════════════════════════════════════════
    {
        "id": "directors_kmp",
        "title": "5. Directors & Key Management Personnel",
        "data_keys": ["management_profile", "borrower_profile", "pep_screening"],
        "instruction": (
            "Write the Directors & KMP section:\n\n"
            "(5.1) Board of Directors — Table with Source column:\n"
            "| S.No | Name | DIN | Designation | Date of Appointment | Promoter (Y/N) | "
            "Net Worth (₹ Cr) | Other Directorships | Source / Remarks |\n"
            "\n"
            "(5.2) Key Management Profile — Brief profile (2-3 lines each), only for people in the data:\n"
            "- Managing Director / CEO: background, experience, tenure, previous roles\n"
            "- CFO / Finance Director: qualifications, experience\n"
            "- Other key directors: domain expertise and contribution\n\n"
            "(5.3) Management Assessment — Overall management quality: experience depth, "
            "succession planning, governance practices, related party concerns if any.\n\n"
            "(5.4) PEP/KYC Status — Summary: total persons screened, any PEP hits, "
            "sanctions hits, overall risk level.\n\n"
            "200-300 words."
        ),
        "max_tokens": 2000,
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 6. Industry & Market Analysis
    # ══════════════════════════════════════════════════════════════════════════
    {
        "id": "industry_analysis",
        "title": "6. Industry & Market Analysis",
        "data_keys": ["case_summary", "benchmark_summary", "market_signals",
                       "industry_analysis", "web_crawl_news", "credit_strengths", "key_risks",
                       "infra_metrics", "sector_kpis"],
        "instruction": (
            "Write the Industry Analysis section:\n\n"
            "(6.1) Industry Overview — Current state of the sector, size, growth rate, "
            "regulatory environment, government policy thrust.\n"
            "Table: Parameter | Value | Source / Remarks.\n\n"
            "(6.2) Competitive Landscape — only if competitor data is provided; table of key competitors:\n"
            "Company | Revenue (₹ Cr) | Market Cap | Rating | Key Differentiator | Source / Remarks.\n\n"
            "(6.3) Revenue Segments & Geography — Revenue breakdown by segment and geography.\n\n"
            "(6.4) SWOT Analysis — Strengths, Weaknesses, Opportunities, Threats.\n\n"
            "(6.5) Recent News & Market Intelligence — if web_crawl_news available.\n\n"
            "INFRASTRUCTURE / ROAD SECTOR — If infra_metrics data is present, add:\n"
            "(6.6) Order Book & Execution Capacity — Table with Source:\n"
            "Total Order Book (₹ Cr), Book-to-Bill Ratio, EPC Orders, BOT/HAM Orders, "
            "Orders Won FY25, Executable Book, Km Executed (FY23/24/25), "
            "Avg Construction Cost per Km, Equipment Utilization %.\n\n"
            "(6.7) BOT / HAM Concession Portfolio — Per-asset table:\n"
            "Asset Name | Length (km) | Concession Years | Residual Years | "
            "Annual Toll/Annuity (₹ Cr) | DSCR | Model | Source / Remarks.\n\n"
            "(6.8) Development Projections — Projected Km, Revenue, Capex for FY26/27.\n\n"
            "All tables MUST have Source / Remarks column. 300-500 words (longer if infra data present)."
        ),
        "max_tokens": 3000,
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 7. External Credit Rating
    # ══════════════════════════════════════════════════════════════════════════
    {
        "id": "external_rating",
        "title": "7. External Credit Rating",
        "data_keys": ["external_intelligence", "borrower_profile", "market_signals"],
        "instruction": (
            "Write the External Credit Rating section with detailed analysis:\n\n"
            "(7.1) Current Ratings — Table with Source:\n"
            "| Agency | Instrument | Rating | Outlook | Date | Source / Remarks |\n\n"
            "(7.2) Rating Rationale — Key Strengths cited by the rating agency, only as stated in the data:\n"
            "Bullet list of strengths (e.g., strong order book, established track record, "
            "comfortable financial metrics). Source reference for each point.\n\n"
            "(7.3) Rating Concerns & Sensitivities:\n"
            "- Factors that could lead to downgrade\n"
            "- Factors that could lead to upgrade\n"
            "Table: Sensitivity Factor | Direction (Upgrade/Downgrade) | Source / Remarks.\n\n"
            "(7.4) Historical Rating Movement — If available, show rating trajectory.\n\n"
            "120-200 words."
        ),
        "max_tokens": 1500,
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 8. Internal Credit Rating & Risk Assessment
    # ══════════════════════════════════════════════════════════════════════════
    {
        "id": "risk_assessment",
        "title": "8. Internal Credit Rating & Risk Assessment",
        "data_keys": ["policy_decisions", "external_intelligence", "key_risks",
                       "credit_strengths", "validation_exceptions"],
        "instruction": (
            "Write the Internal Credit Rating & Risk Assessment section:\n\n"
            "(8.1) Internal Rating Scorecard — Table with Source:\n"
            "| Parameter | Score | Weight | Weighted Score | Source / Remarks |\n"
            "Include: Financial Score, Conduct Score, Governance Score, Market Score, "
            "Composite Score. Overall Risk Grade and interpretation.\n\n"
            "(8.2) Tier 1 Hard Rules — Table:\n"
            "Rule | Description | Result (Pass/Fail) | Details | Source / Remarks.\n\n"
            "(8.3) Risk Matrix — Table:\n"
            "Risk Factor | Category | Severity (High/Medium/Low) | Mitigant | Source / Remarks.\n"
            "Cover: Credit Risk, Market Risk, Operational Risk, Concentration Risk, "
            "Regulatory Risk.\n\n"
            "(8.4) Key Risk Factors — Narrative on top 3-5 risks with mitigants.\n\n"
            "200-300 words."
        ),
        "max_tokens": 2000,
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 9. Compliance & Regulatory Checks
    # ══════════════════════════════════════════════════════════════════════════
    {
        "id": "compliance",
        "title": "9. Compliance & Regulatory Checks",
        "data_keys": ["external_intelligence", "compliance_checks", "pep_screening",
                       "crilc_exposure"],
        "instruction": (
            "Write the Compliance section:\n\n"
            "(9.1) Regulatory Compliance Table — with Source / Remarks:\n"
            "| Check | Status | Details | Source / Remarks |\n"
            "Include: MCA Status, MCA Filing Status, GST Filing Status, GST Turnover, "
            "Bureau Score, DPD Status, Total Exposure, Active Lenders, "
            "CRILC SMA Flag, CRILC Classification, Wilful Defaulter Check, "
            "ECGC Caution List, SUIT Filing, RBI Defaulter List.\n"
            "Source: 'MCA21', 'GST Portal', 'CIBIL/Equifax', 'RBI CRILC', 'ECGC Database'.\n\n"
            "(9.2) CRILC Exposure Summary — If crilc_exposure data available:\n"
            "Table with aggregate exposure, SMA flag, asset classification across banking system.\n\n"
            "(9.3) PEP / KYC Screening:\n"
            "Table: Person | DIN | PEP Category | Risk Level | Sanctions Hit | "
            "Adverse Media | Source / Remarks.\n"
            "Overall screening outcome.\n\n"
            "150-250 words."
        ),
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 10. Account Conduct & Relationship Review
    # ══════════════════════════════════════════════════════════════════════════
    {
        "id": "conduct",
        "title": "10. Account Conduct & Relationship Review",
        "data_keys": ["conduct_analysis", "covenant_history", "etb_behavioral_analytics"],
        "instruction": (
            "Write the Account Conduct section:\n"
            "If ETB: quarterly conduct table with Source column "
            "(Period | Balance ₹ Cr | Turnover ₹ Cr | Cheque Returns | "
            "Utilization % | DPD | Source / Remarks), conduct assessment, "
            "business reciprocity.\n"
            "If NTB: state 'New-to-Bank (NTB) — Fresh relationship. "
            "No prior account conduct history available. Enhanced monitoring "
            "recommended during initial 12-month period.'\n"
            "All tables must have Source / Remarks column."
        ),
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 11. Banking Relationships
    # ══════════════════════════════════════════════════════════════════════════
    {
        "id": "core_banking",
        "title": "11. Banking Relationships",
        "data_keys": ["core_banking", "core_banking_analysis", "case_summary",
                       "existing_exposure", "facility_details"],
        "instruction": (
            "Write the Banking Relationships section:\n\n"
            "If NTB: state 'New-to-Bank customer — no existing banking relationship. "
            "This is an NTB (New to Bank) proposal.' Then describe existing lender "
            "relationships from bureau/CRILC data if available.\n\n"
            "For ETB, include:\n"
            "(11.1) Consortium / Multiple Banking Arrangement — Table:\n"
            "Bank Name | Facility Type | Sanctioned (₹ Cr) | Outstanding (₹ Cr) | "
            "Share % | Lead Bank (Y/N) | Source / Remarks.\n\n"
            "(11.2) Loan Account Summary — Table:\n"
            "Account No | Facility | Sanctioned | Outstanding | Utilization % | "
            "Rate | DPD | Classification | Source / Remarks.\n\n"
            "(11.3) Deposit & Cross-Sell — Table:\n"
            "Product | Balance (₹ Cr) | Tenure | Source / Remarks.\n"
            "Fee income summary: Processing Fees + LC/BG Commission + Forex Income.\n\n"
            "(11.4) Relationship Assessment — tenure, health, profitability, cross-sell.\n\n"
            "200-300 words."
        ),
        "max_tokens": 2000,
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 12. Social Media & Digital Intelligence
    # ══════════════════════════════════════════════════════════════════════════
    {
        "id": "social_media",
        "title": "12. Social Media & Digital Intelligence",
        "data_keys": ["social_media_analysis", "social_media_cam_summary"],
        "instruction": (
            "Write the Social Media & Digital Intelligence section:\n"
            "(12.1) Social Media Presence — Table:\n"
            "Platform | Metric | Value | Assessment | Source / Remarks.\n\n"
            "(12.2) Sentiment Analysis — Overall sentiment score, positive/negative/neutral "
            "breakdown, key themes.\n\n"
            "(12.3) Reputation Risk — Table:\n"
            "Risk Factor | Level | Details | Source / Remarks.\n\n"
            "(12.4) Decision Impact — How social media intelligence affects "
            "the credit assessment.\n"
            "Be concise and analytical. 150-250 words."
        ),
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 13. Financial Analysis
    # ══════════════════════════════════════════════════════════════════════════
    {
        "id": "financial_analysis",
        "title": "13. Financial Analysis",
        "data_keys": ["financial_summary", "ratio_analysis", "benchmark_summary",
                       "cash_flow_repayment"],
        "instruction": (
            "Write comprehensive Financial Analysis (most data-intensive section):\n\n"
            "(13.1) Profit & Loss Statement — Table with ALL periods + Source column:\n"
            "| Particulars | <one column per period in financial_summary> | YoY Growth (from financial_summary.growth_by_period; 'n/a' if absent) | Source / Remarks |\n"
            "Revenue, Other Income, Total Income, Raw Material/Sub-contracting Cost, "
            "Employee Cost, Other Expenses, EBITDA, EBITDA Margin %, Depreciation, "
            "EBIT, Interest/Finance Cost, PBT, Tax, PAT, PAT Margin %.\n"
            "Source: each period's statement source from the data.\n"
            "Add analytical commentary on revenue drivers, margin trajectory.\n\n"
            "(13.2) Balance Sheet Summary — Table with Source:\n"
            "| Particulars | <one column per period> | Source / Remarks |\n"
            "Net Worth, Long-Term Debt, Short-Term Debt, Total Debt, Total Assets, "
            "Fixed Assets, Current Assets (Trade Receivables, Inventory, Cash), "
            "Current Liabilities (Trade Payables, Short-term Borrowings).\n"
            "Commentary: leverage assessment, working capital position.\n\n"
            "(13.3) Cash Flow Analysis — Table with Source:\n"
            "| Particulars | <one column per period> | Source / Remarks |\n"
            "OCF, Capex, FCF, Debt Repayment, Net Cash Flow.\n"
            "Cash quality: OCF/PAT from financial_summary.growth_by_period.<period>.ocf_to_pat (quote it; do not compute).\n\n"
            "(13.4) Key Financial Ratios — Comprehensive table:\n"
            "| Ratio | <one column per period> | Peer Median (benchmark_summary) | Assessment | Source / Remarks |\n"
            "Current Ratio, D/E, Debt/EBITDA, ICR, DSCR, EBITDA Margin, PAT Margin, "
            "ROE, ROA, Asset Turnover, Debtor Days, Inventory Days, Working Capital Cycle, TOL/TNW.\n\n"
            "(13.5) Decision Impact Analysis — For each key metric: what it means for credit "
            "quality, trend direction, peer comparison, recommendation impact.\n\n"
            "Use ₹ Cr for amounts. 500-700 words."
        ),
        "max_tokens": 3000,
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 14. Detailed Operational Analysis & Industry KPI Benchmarking
    # ══════════════════════════════════════════════════════════════════════════
    {
        "id": "operational_kpis",
        "title": "14. Detailed Operational Analysis & Industry KPI Benchmarking",
        "data_keys": ["infra_metrics", "industry_analysis", "benchmark_summary",
                       "financial_summary", "ratio_analysis", "case_summary", "sector_kpis",
                       "policy_thresholds"],
        "instruction": (
            "Write the Detailed Operational Analysis section with industry-specific KPIs.\n\n"
            "(14.1) Industry KPI Benchmarking — CRITICAL table:\n"
            "| KPI Metric | External Benchmark | Internal Benchmark | Company Value | Assessment | Source / Remarks |\n\n"
            "For INFRASTRUCTURE / ROAD CONSTRUCTION sector, the following are INDICATIVE INDUSTRY RANGES "
            "(an internal reference list, not verified data) — label that column 'Indicative range (reference)':\n"
            "- Construction Cost per Km: ₹15-20 Cr (plain terrain); ₹25-40 Cr (hilly/structural)\n"
            "- Land Acquisition Cost per Km: ₹5-12 Cr (varies by state & terrain)\n"
            "- Structure Cost as % of Total: 25-35% (plains); 40-55% (structure heavy)\n"
            "- Execution Rate: 250-400 km/year (large companies); 80-150 km/year (mid-size)\n"
            "- Order Book-to-Bill Ratio: 2.5x-4.0x (healthy range)\n"
            "- Equipment Utilization: 70-85% (industry average)\n"
            "- Effective Construction Days: 220-260 days/year\n"
            "- EBITDA Margin: 12-18% (EPC); 60-80% (BOT/Toll); 20-30% (HAM)\n"
            "- DSCR (Project Level): 1.2x-1.5x (HAM); 1.3x-2.0x (BOT Toll)\n"
            "- Debt/Equity (Project Level): 70:30 to 80:20\n"
            "- Physical vs Financial Progress Gap: Within ±10%\n"
            "- Cost Overrun: <5% (good); 5-15% (acceptable); >15% (concern)\n"
            "- Subcontractor Dependency: <40% (good); 40-60% (moderate); >60% (high risk)\n"
            "- Labour Productivity (km/worker/yr): 0.008-0.012 km\n"
            "- Safety (LTIFR): <0.5 (excellent); 0.5-1.0 (good); >1.0 (concern)\n\n"
            "For OTHER sectors, the External Benchmark is the peer median from benchmark_summary; "
            "write 'N/A' where none is given. Do not apply the infrastructure ranges to other sectors.\n\n"
            "INTERNAL BENCHMARKS: use policy_thresholds exactly (the bank's credit-policy limits).\n\n"
            "Use the company's ACTUAL values from infra_metrics, sector_kpis and financial data exactly as given. "
            "Do NOT calculate or derive a KPI; if a value is not in the data write 'Not available'.\n\n"
            "(14.2) KPI Assessment — Commentary on each KPI vs benchmarks. "
            "Flag areas of concern (red) and areas of strength (green).\n\n"
            "(14.3) Operational Efficiency Summary — Overall assessment.\n\n"
            "INFRASTRUCTURE ADDITIONAL SUB-SECTIONS — If sector_kpis data is present:\n"
            "(14.4) Active Project Pipeline — Table with Source:\n"
            "Project | Length (km) | Contract Value (₹ Cr) | Completion % | Model | "
            "Client | Target | Source / Remarks. Include total row.\n\n"
            "(14.5) HAM Portfolio Analysis — Operational vs Total, Annual Annuity, "
            "Avg DSCR, Equity Infusion %, NHAI Grant %.\n\n"
            "(14.6) Workforce & Safety — Employee count, engineers, labour productivity, "
            "safety metrics (LTIFR, fatality rate).\n\n"
            "(14.7) Raw Material Profile — Key materials, consumption, price trends.\n\n"
            "All tables MUST include Source / Remarks column. 400-600 words."
        ),
        "max_tokens": 3500,
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 15. Peer Comparison & Benchmarking
    # ══════════════════════════════════════════════════════════════════════════
    {
        "id": "benchmarking",
        "title": "15. Peer Comparison & Benchmarking",
        "data_keys": ["benchmark_summary"],
        "instruction": (
            "Write the Benchmarking section:\n"
            "Table with Source column:\n"
            "Metric | Borrower Value | Peer P25 | Peer Median | Peer P75 | Position | "
            "Gap | Source / Remarks.\n\n"
            "Summary: X metrics above median, Y in line, Z below peers.\n"
            "Highlight worst performers with specific gap analysis and credit impact.\n\n"
            "Source: 'Benchmark engine (sector peer percentiles)'."
        ),
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 16. Financial Projections
    # ══════════════════════════════════════════════════════════════════════════
    {
        "id": "financial_projections",
        "title": "16. Financial Projections",
        "data_keys": ["financial_projections", "policy_thresholds", "financial_summary",
                       "cash_flow_repayment", "facility_details", "case_summary"],
        "instruction": (
            "Write the Financial Projections section using ONLY the computed figures in "
            "financial_projections. Do not calculate or extrapolate any number yourself.\n\n"
            "If financial_projections.available is false, state its reason and that projections "
            "are pending from management / RM, then stop.\n\n"
            "(16.1) Basis & Assumptions — state the revenue method and each assumption "
            "(CAGR applied, average margins, OCF conversion, interest rate, tenor, debt basis).\n\n"
            "(16.2) Projected P&L — table: Particulars | base_period (Actual, from financial_summary) | "
            "one column per projected year | Source / Remarks ('Projection engine'). "
            "Rows: Revenue, EBITDA, PAT.\n\n"
            "(16.3) Debt Service & DSCR — table: Year | OCF | Principal | Interest | DSCR | Assessment. "
            "Compare DSCR with policy_thresholds.min_dscr and flag any year below it.\n\n"
            "(16.4) DSRA requirement — quote dsra_requirement_cr (one quarter of annual debt service).\n\n"
            "(16.5) Stress tests — table: Scenario | DSCR | Assessment, from stress_tests.\n\n"
            "Close with a short note that these are model projections pending management's CMA data.\n\n"
            "250-400 words."
        ),
        "max_tokens": 2500,
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 17. Facility Assessment & Project Appraisal
    # ══════════════════════════════════════════════════════════════════════════
    {
        "id": "facility_assessment",
        "title": "17. Facility Assessment & Project Appraisal",
        "data_keys": ["facility_details", "facility_pricing", "drawing_power",
                       "collateral_analysis", "existing_exposure", "case_summary",
                       "infra_metrics"],
        "instruction": (
            "Write the Facility Assessment section:\n\n"
            "(17.1) Facility Overview Table — with Source:\n"
            "| Parameter | Details | Source / Remarks |\n"
            "Facility Type, Amount (₹ Cr), Purpose, Tenor, Security, Pricing.\n\n"
            "(17.2) Project Cost & Means of Finance — If a project-linked facility:\n"
            "**Project Cost Table:**\n"
            "| Component | Amount (₹ Cr) | % of Total | Source / Remarks |\n"
            "EPC Cost, Land Cost, Financing Cost, Contingency, Total.\n"
            "**Means of Finance Table:**\n"
            "| Source of Finance | Amount (₹ Cr) | % of Total | Status | Source / Remarks |\n"
            "Equity, Term Loan (Our Bank), Term Loan (Others), NHAI Grant (if HAM), "
            "Internal Accruals.\n\n"
            "(17.3) Per-Facility Assessment — End-use, disbursement mechanism, "
            "monitoring, repayment source.\n\n"
            "(17.4) Pricing & Concessions:\n"
            "| Facility | Interest Rate | Processing Fee | Penal Interest | "
            "Concessions | Source / Remarks |\n\n"
            "200-350 words."
        ),
        "max_tokens": 2000,
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 18. Security, Collateral & Valuation
    # ══════════════════════════════════════════════════════════════════════════
    {
        "id": "security_collateral",
        "title": "18. Security, Collateral & Valuation",
        "data_keys": ["collateral_analysis", "external_intelligence", "charges_data"],
        "instruction": (
            "Write the Security & Collateral section:\n\n"
            "(18.1) Security Structure — Table with Source:\n"
            "| S.No | Security Type | Description | Market Value (₹ Cr) | FSV (₹ Cr) | "
            "Encumbrance | Source / Remarks |\n"
            "\n"
            "(18.2) Collateral Coverage:\n"
            "| Item | Value (₹ Cr) | Source / Remarks |\n"
            "Total Market Value, Total FSV, Facility Amount, FSV Coverage Ratio, "
            "Security Margin. Adequacy assessment.\n\n"
            "(18.3) Pari-Passu / Charge Status — CERSAI & ROC registered charges if available.\n\n"
            "150-250 words."
        ),
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 19. Terms, Conditions & Financial Covenants
    # ══════════════════════════════════════════════════════════════════════════
    {
        "id": "covenants",
        "title": "19. Terms, Conditions & Financial Covenants",
        "data_keys": ["policy_decisions", "covenant_history", "policy_thresholds", "ratio_analysis"],
        "instruction": (
            "Write the Covenants section:\n\n"
            "(19.1) Conditions Precedent — Numbered table with Source / Remarks column.\n\n"
            "(19.2) Financial Covenants — Table:\n"
            "| Covenant | Threshold | Current Actual | Compliance | Source / Remarks |\n"
            "Include: Min DSCR, Max D/E, Min Current Ratio, Max TOL/TNW, Min EBITDA Margin. "
            "Thresholds come from policy_thresholds (and the covenants in policy_decisions); "
            "Current Actual is the latest-period value from ratio_analysis.\n\n"
            "(19.3) Reporting Requirements — Table:\n"
            "Report | Frequency | Due Date | Source / Remarks.\n\n"
            "(19.4) Monitoring Conditions — Special monitoring requirements if any.\n\n"
            "If ETB, add covenant compliance history table."
        ),
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 20. Recommendation & Approving Authority
    # ══════════════════════════════════════════════════════════════════════════
    {
        "id": "recommendation",
        "title": "20. Recommendation & Approving Authority",
        "data_keys": ["policy_decisions", "borrower_profile", "case_summary",
                       "collateral_analysis", "core_banking_analysis",
                       "social_media_cam_summary", "pep_screening",
                       "credit_strengths", "key_risks", "approving_authority"],
        "instruction": (
            "Write the Recommendation section with comprehensive decision details:\n\n"
            "(20.1) RECOMMENDATION: State clearly — [APPROVE / CONDITIONAL APPROVE / REFER / DECLINE].\n"
            "Summary table with Source:\n"
            "| Parameter | Details | Source / Remarks |\n"
            "Borrower, Facility Type, Amount ₹ Cr, Risk Grade, Composite Score, Recommendation.\n\n"
            "(20.2) Decision Rationale — structured as:\n"
            "  - Key Credit Strengths (bullet list from data)\n"
            "  - Key Risk Factors (bullet list with severity: high/medium/low)\n"
            "  - Mitigating Factors (what offsets the risks)\n"
            "  - PEP/Compliance: screening outcome and impact\n"
            "  - Core Banking (ETB): relationship health, conduct history\n"
            "  - Social Media/Reputation: any reputation flags\n\n"
            "(20.3) Conditions & Covenants — collateral requirement, exception notes, "
            "financial covenants, monitoring frequency, reporting requirements.\n\n"
            "(20.4) Approving Authority — state the required sanctioning authority from "
            "approving_authority (name, and the reason: amount, risk grade, and whether approval "
            "would be a deviation from the system recommendation). Then a signature table:\n"
            "| Authority | Name | Designation | Signature | Date |\n"
            "Relationship Manager, then the required sanctioning authority.\n\n"
            "Be analytical and connect data points to the decision."
        ),
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 21. Terms & Conditions
    # ══════════════════════════════════════════════════════════════════════════
    {
        "id": "terms_conditions",
        "title": "21. Terms & Conditions",
        "data_keys": ["policy_decisions", "facility_details", "case_summary"],
        "instruction": (
            "Write the Terms & Conditions section:\n\n"
            "(21.1) General Terms — Table:\n"
            "| S.No | Term | Details | Source / Remarks |\n"
            "Include: Disbursement conditions, end-use monitoring, insurance requirements, "
            "security creation timeline, personal guarantee requirements, "
            "no-lien declaration, cross-default clause.\n\n"
            "(21.2) Specific Conditions — Any sector-specific or deal-specific conditions:\n"
            "- For infrastructure: Escrow account, DSRA maintenance, TRA (Trust & Retention Account)\n"
            "- For HAM: NHAI grant disbursement linkage, milestone-based drawdown\n"
            "- Negative covenants: Asset sale restriction, dividend restriction, "
            "additional borrowing restriction.\n\n"
            "(21.3) Review & Renewal — Annual review date, renewal conditions, "
            "early termination provisions.\n\n"
            "150-250 words."
        ),
        "max_tokens": 1500,
    },

    # ── Structural (template-only) ──
    {
        "id": "annexure_a",
        "title": "Annexure A — Document Checklist",
        "skip_llm": True,
    },
    {
        "id": "annexure_b",
        "title": "Annexure B — Quarterly Performance Trend",
        "skip_llm": True,
    },
    {
        "id": "annexure_c",
        "title": "Annexure C — Glossary of Terms",
        "skip_llm": True,
    },
    {
        "id": "data_sources",
        "title": "Appendix — Data Sources & Audit Trail",
        "skip_llm": True,
    },
    {
        "id": "disclaimer",
        "title": "Disclaimer",
        "skip_llm": True,
    },
]


SYSTEM_PROMPT = (
    "You are a senior credit analyst at a leading Indian commercial bank writing a "
    "Credit Approval Memorandum (CAM) for the Credit Committee.\n\n"
    "WRITING STYLE:\n"
    "- Write with authority and analytical depth — this is a formal banking document.\n"
    "- Every claim must be supported by data. State the number, then interpret it.\n"
    "- Use comparative framing: 'X improved from Y to Z, indicating...' or 'At X%, this is above/below peer median of Y%'.\n"
    "- Connect data points to credit implications: 'The declining DSCR of 1.2x (vs. 1.8x prior year) "
    "suggests thinning debt-servicing headroom, warranting enhanced monitoring.'\n"
    "- Use transition phrases between subsections for narrative flow.\n\n"
    "FORMATTING RULES:\n"
    "1. Use ONLY the data provided in the JSON context. NEVER fabricate facts, numbers, names, or dates.\n"
    "2. Use ₹ Cr for currency amounts. Use % for percentages. Use 'x' for multiples (e.g., 2.5x).\n"
    "3. Present tabular data in clean markdown tables with right-aligned numbers.\n"
    "4. Every financial claim must trace directly to the provided data.\n"
    "5. If data for a topic is missing, state 'Information not available' — NEVER fabricate.\n"
    "6. Use past tense for historical data, present tense for current state, future tense for projections.\n"
    "7. Keep each section focused and within the specified word count.\n"
    "8. Do NOT add meta-commentary like 'based on the data provided' or disclaimers.\n"
    "9. Output clean markdown with proper headings (##, ###), tables, bold for emphasis, and paragraphs.\n"
    "10. For risk items, always state: the risk, its severity, and the mitigant (if any).\n"
    "11. EVERY table that contains factual data MUST include a 'Source / Remarks' column as the LAST column. "
    "Fill it ONLY with provenance that appears in the data (a 'source' field, data provider, or a document "
    "named in the data). Otherwise name the data area it came from, e.g. 'Financial summary', "
    "'Policy engine', 'Bureau data', 'Benchmark engine'. NEVER invent document names, report dates, "
    "rating agencies or filing references — the Credit Committee relies on this traceability.\n"
    "12. Benchmark columns may only use values given in the data (benchmark_summary, policy_thresholds) "
    "or stated in the section instructions. Write 'N/A' where no benchmark is provided.\n"
    "13. Use the financial periods present in the data as table columns; never add years that are not in the data.\n"
    "14. When the data contains a computed value (ratios, projections, DSCR, scores), quote it. "
    "Do not recalculate or extrapolate your own figures.\n"
    "15. Omit a requested sub-section or table entirely when the data has nothing for it, rather than "
    "filling it with placeholders.\n"
    "16. DATA PROVENANCE: the data carries _provenance labels per section. Present items labelled 'Synthetic demo data' as demo data that is not verified; never present them as verified external evidence. Where a section is 'Not available', say it is not available — do not substitute headlines, events, ratings or attributions. Quote calculated figures as given; never calculate a figure that is not in the data.\n"
)


# Bump whenever CAM_SECTIONS instructions or SYSTEM_PROMPT change in a way that
# should invalidate saved section checkpoints and be traceable in the output.
PROMPT_VERSION = "cam-2026.10-4"  # -4: no LLM calculation; data provenance; compact ratios
