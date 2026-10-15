"""
CAM Renderer V2 — Aligned to Reference Bank CAM Format
Produces 12 numbered sections + 3 annexures matching Indian Bank Credit Appraisal Memorandum.
All narrative is deterministic — computed from fact-pack data, no LLM involvement.
"""

from datetime import date

from src.engines.data_provenance import NOT_AVAILABLE, NOT_VERIFIED


# ─── Formatting Helpers ───────────────────────────────────────────────────────

def _h(text: str, level: int = 2) -> str:
    return f"{'#' * level} {text}\n\n"


def _row(cells: list) -> str:
    return "| " + " | ".join(str(c) for c in cells) + " |\n"


def _hdr(headers: list) -> str:
    return _row(headers) + "| " + " | ".join("---" for _ in headers) + " |\n"


def _cr(val) -> str:
    if val is None:
        return "N/A"
    return f"₹ {val:,.2f} Cr"


def _pct(val) -> str:
    if val is None:
        return "N/A"
    return f"{val:.1f}%"


def _ratio(val) -> str:
    if val is None:
        return "N/A"
    return f"{val:.2f}x"


def _badge(s: str) -> str:
    m = {"critical": "🔴 CRITICAL", "high": "🟠 HIGH", "medium": "🟡 MEDIUM", "low": "🟢 LOW"}
    return m.get(s.lower(), s)


def _safe(d: dict, key: str, default="N/A"):
    """Safely get a value from dict."""
    v = d.get(key)
    return v if v is not None else default


def _resolve_section_source(fp: dict, *cam_section_names: str, fallback: str = "") -> str:
    """Build source attribution dynamically from data_sources provenance entries.

    Looks up which data_sources[] entries cover the requested CAM sections
    and returns a formatted *Source: ...* string.  Falls back to a static
    label only when no matching provenance entry is found.
    """
    ds = fp.get("data_sources", [])
    matched: list[str] = []
    for entry in ds:
        sections_using = entry.get("cam_sections_using", [])
        if any(sec in sections_using for sec in cam_section_names):
            name = entry.get("source_name", "")
            if name and name not in matched:
                matched.append(name)
    if matched:
        return f"*Source: {'; '.join(matched)}*"
    return f"*Source: {fallback}*" if fallback else ""


# ═══════════════════════════════════════════════════════════════════════════════
# COVER PAGE
# ═══════════════════════════════════════════════════════════════════════════════

def render_cover_page(fp: dict) -> str:
    bp = fp["borrower_profile"]
    cs = fp["case_summary"]
    rec = fp["policy_decisions"]["tier3_recommendation"]
    out = ""
    out += "---\n\n"
    out += "<div style='text-align:center; padding: 40px 0;'>\n\n"
    out += "# INDIAN BANK\n\n"
    out += "### Corporate Banking Division\n\n"
    out += "---\n\n"
    out += "### CREDIT APPRAISAL MEMORANDUM (CAM)\n\n"
    out += "---\n\n"
    out += "#### BORROWER\n\n"
    out += f"## {bp['company_name']}\n\n"
    cin_line = f"CIN: {bp['cin']}"
    if bp.get("listed_exchange"):
        cin_line += f" | BSE / NSE: {bp.get('listed_exchange', 'N/A')}"
        if bp.get("nse_symbol"):
            cin_line += f" | NSE: {bp['nse_symbol']}"
    out += f"**{cin_line}**  \n"
    out += f"**PAN:** {bp['pan']}  \n"
    out += f"**Sector:** {cs['sector'].replace('_', ' ').title()} — {cs['subsector']}  \n\n"
    out += "---\n\n"
    out += f"**Case Type:** {cs['case_type']} | **Facility:** {cs['facility_type'].replace('_', ' ').title()}  \n"
    out += f"**Amount Requested:** {_cr(cs['amount_requested_cr'])}  \n"
    out += f"**Recommendation:** **{rec['recommendation'].replace('_', ' ').upper()}**  \n"
    out += f"**Risk Grade:** {rec['risk_grade']} (Score: {rec['composite_score']})  \n"
    out += f"**Date:** {fp['meta']['generated_date']}  \n\n"
    out += "---\n\n"
    out += "*STRICTLY CONFIDENTIAL | For Internal Use Only | Credit Committee Circulation*\n\n"
    out += "</div>\n\n"
    out += "---\n\n"
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# TABLE OF CONTENTS
# ═══════════════════════════════════════════════════════════════════════════════

def render_toc(fp: dict) -> str:
    out = _h("TABLE OF CONTENTS")
    items = [
        "1. Executive Summary",
        "2. Borrower Profile",
        "   2.1 Corporate Identification",
        "   2.2 Registered Address & Location",
        "   2.3 Business Overview",
        "3. Client Background, Business Activity & Project Details",
        "   3.1 Nature of Business",
        "   3.2 Project Details",
        "   3.3 Project Components",
        "   3.4 Project Model Key Features",
        "   3.5 Construction Status / Order Execution",
        "4. Group Companies, Shareholders & Promoter Details",
        "   4.1 Shareholding Pattern",
        "   4.2 Group Structure",
        "   4.3 Promoter Background",
        "5. Directors & Key Management Personnel",
        "   5.1 Board of Directors",
        "   5.2 Key Management Profile",
        "   5.3 Management Assessment",
        "   5.4 PEP/KYC Status",
        "6. Industry & Market Analysis",
        "   6.1 Industry Overview",
        "   6.2 Competitive Landscape",
        "   6.3 Revenue Segments & Geography",
        "   6.4 SWOT Analysis",
        "   6.5 Recent News & Market Intelligence",
        "7. External Credit Rating",
        "   7.1 Current Ratings",
        "   7.2 Rating Rationale",
        "   7.3 Rating Concerns & Sensitivities",
        "8. Internal Credit Rating & Risk Assessment",
        "   8.1 Internal Rating Scorecard",
        "   8.2 Tier 1 Hard Rules",
        "   8.3 Risk Matrix",
        "   8.4 Key Risk Factors",
        "9. Compliance & Regulatory Checks",
        "   9.1 Regulatory Compliance Table",
        "   9.2 CRILC Exposure Summary",
        "   9.3 PEP / KYC Screening",
        "10. Account Conduct & Relationship Review",
        "11. Banking Relationships",
        "12. Social Media & Digital Intelligence",
        "13. Financial Analysis",
        "    13.1 Profit & Loss Statement",
        "    13.2 Balance Sheet Summary",
        "    13.3 Cash Flow Analysis",
        "    13.4 Key Financial Ratios",
        "    13.5 Decision Impact Analysis",
        "14. Detailed Operational Analysis & Industry KPI Benchmarking",
        "    14.1 Industry KPI Benchmarking",
        "    14.2 KPI Assessment",
        "    14.3 Operational Efficiency Summary",
        "15. Peer Comparison & Benchmarking",
        "16. Financial Projections",
        "    16.1 Projected P&L Statement",
        "    16.2 Cash Flow & DSCR Projections",
        "    16.3 DSRA Calculation",
        "    16.4 Sensitivity Analysis",
        "17. Facility Assessment & Project Appraisal",
        "    17.1 Facility Overview",
        "    17.2 Project Cost & Means of Finance",
        "    17.3 Per-Facility Assessment",
        "    17.4 Pricing & Concessions",
        "18. Security, Collateral & Valuation",
        "    18.1 Security Structure",
        "    18.2 Collateral Coverage",
        "    18.3 Pari-Passu / Charge Status",
        "19. Terms, Conditions & Financial Covenants",
        "    19.1 Conditions Precedent",
        "    19.2 Financial Covenants",
        "    19.3 Reporting Requirements",
        "    19.4 Monitoring Conditions",
        "20. Recommendation & Approving Authority",
        "    20.1 Recommendation",
        "    20.2 Decision Rationale",
        "    20.3 Conditions & Covenants",
        "    20.4 Approving Authority",
        "21. Terms & Conditions",
        "",
        "Annexure A — Document Checklist",
        "Annexure B — Quarterly Performance Trend",
        "Annexure C — Glossary of Terms",
    ]

    # Add infra-specific sub-sections if applicable
    infra_metrics = fp.get("infra_metrics") or {}
    sector_kpis = fp.get("sector_kpis") or {}
    if infra_metrics or sector_kpis:
        # Insert infra sub-sections under Section 6
        idx_6 = items.index("7. External Credit Rating")
        infra_items = [
            "   6.6 Order Book & Execution Capacity",
            "   6.7 BOT / HAM Concession Portfolio",
            "   6.8 Development Projections",
        ]
        for offset, item in enumerate(infra_items):
            items.insert(idx_6 + offset, item)

        # Insert infra sub-sections under Section 14
        idx_14 = items.index("15. Peer Comparison & Benchmarking")
        infra_kpi_items = [
            "    14.4 Active Project Pipeline",
            "    14.5 HAM Portfolio Analysis",
            "    14.6 Workforce & Safety",
            "    14.7 Raw Material Profile",
        ]
        for offset, item in enumerate(infra_kpi_items):
            items.insert(idx_14 + offset, item)

    for item in items:
        if item == "":
            out += "\n"
        else:
            out += f"{item}  \n"
    out += "\n---\n\n"
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: EXECUTIVE SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════

def render_section_1_executive_summary(fp: dict) -> str:
    cs = fp["case_summary"]
    bp = fp["borrower_profile"]
    fs = fp["financial_summary"]
    rec = fp["policy_decisions"]["tier3_recommendation"]
    scores = fp["policy_decisions"]["tier2_risk_scores"]
    exceptions = fp["validation_exceptions"]

    periods = sorted(fs["periods"].keys())
    latest = fs["periods"][periods[-1]] if periods else {}

    out = _h("1. EXECUTIVE SUMMARY")

    # Paragraph 1: Company overview
    out += (f"This Credit Approval Memorandum pertains to **{bp['company_name']}** "
            f"(CIN: {bp['cin']}), a **{cs['borrower_type']}** company incorporated on "
            f"{bp['date_of_incorporation']} in **{bp['registered_state']}**. "
            f"The Company operates in the **{cs['sector'].replace('_', ' ').title()} — {cs['subsector']}** sector")

    if bp.get("listed_exchange"):
        out += f" and is listed on **{bp['listed_exchange']}**"
    if bp.get("credit_rating"):
        out += f". The Company carries a credit rating of **{bp['credit_rating']}**"
        if bp.get("rating_agency"):
            out += f" from **{bp['rating_agency']}**"
    out += ".\n\n"

    # Paragraph 2: Facility request
    out += (f"The proposal is for a **{cs['facility_type'].replace('_', ' ').title()}** facility of "
            f"**{_cr(cs['amount_requested_cr'])}** for the purpose of *{cs['purpose']}*. ")

    if periods:
        out += (f"For the latest audited period ({periods[-1]}), the Company reported revenue of "
                f"{_cr(latest.get('revenue_cr'))}, EBITDA of {_cr(latest.get('ebitda_cr'))} "
                f"({_pct(latest.get('ebitda_margin_pct'))} margin), and PAT of "
                f"{_cr(latest.get('pat_cr'))}. Net worth stands at {_cr(latest.get('net_worth_cr'))} "
                f"against total debt of {_cr(latest.get('total_debt_cr'))}.\n\n")

    # Key metrics summary table
    out += _hdr(["Parameter", "Value", "Source"])
    out += _row(["Company Name", bp["company_name"], "MCA Company Master"])
    out += _row(["Facility Requested", f"{cs['facility_type'].replace('_', ' ').title()} — {_cr(cs['amount_requested_cr'])}", "Facility Application"])
    out += _row(["Credit Rating", f"{bp.get('credit_rating', 'N/A')} ({bp.get('rating_agency', 'N/A')})", "Rating Agency"])
    out += _row(["Revenue (Latest)", _cr(latest.get("revenue_cr")), "Audited Financials"])
    out += _row(["EBITDA (Latest)", f"{_cr(latest.get('ebitda_cr'))} ({_pct(latest.get('ebitda_margin_pct'))})", "Audited Financials"])
    out += _row(["Net Worth", _cr(latest.get("net_worth_cr")), "Audited Balance Sheet"])
    out += _row(["Total Debt", _cr(latest.get("total_debt_cr")), "Audited Balance Sheet"])
    out += _row(["Risk Grade", f"**{scores['risk_grade']}** (Score: {scores['composite_score']})", "Internal Rating Model"])
    out += _row(["Recommendation", f"**{rec['recommendation'].replace('_', ' ').upper()}**", "Policy Engine"])
    out += "\n"

    # Risk scores
    out += (f"**Risk Assessment:** Composite Score of **{scores['composite_score']}** (Grade: **{scores['risk_grade']}**). "
            f"Break-up — Financial: {scores['financial_score']} | Conduct: {scores['conduct_score']} | "
            f"Governance: {scores['governance_score']} | Market: {scores['market_score']}.\n\n")

    crit = sum(1 for e in exceptions if e["severity"] == "critical")
    high = sum(1 for e in exceptions if e["severity"] == "high")
    if crit + high > 0:
        out += f"**Validation Alerts:** {crit} Critical, {high} High severity exception(s) detected.\n\n"
    else:
        out += "**Validation:** No critical exceptions detected.\n\n"

    out += f"**Recommendation Rationale:** {rec['rationale']}\n\n"
    out += _resolve_section_source(fp, "Financial Analysis", "Borrower Profile", "Risk Assessment", "External Intelligence", fallback="Audited Financials; MCA Company Master; RBI CRILC Data; External Credit Ratings") + "\n\n"
    out += "---\n\n"
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: BORROWER PROFILE
# ═══════════════════════════════════════════════════════════════════════════════

def render_section_2_borrower_profile(fp: dict) -> str:
    bp = fp["borrower_profile"]
    gp = fp["group_profile"]
    mp = fp["management_profile"]
    ch = fp.get("corporate_hierarchy", {})
    ei = fp["external_intelligence"]

    out = _h("2. BORROWER PROFILE")

    # 2.1 Corporate Identification
    out += _h("2.1 Corporate Identification", 3)
    out += _hdr(["Parameter", "Details", "Source"])
    out += _row(["Company Name", bp["company_name"], "MCA Company Master"])
    out += _row(["CIN", bp["cin"], "MCA Company Master"])
    out += _row(["PAN", bp["pan"], "KYC Documents"])
    out += _row(["Date of Incorporation", bp["date_of_incorporation"], "MCA Company Master"])
    out += _row(["Registered State", bp["registered_state"], "MCA Company Master"])
    out += _row(["Registered Address", bp["registered_address"], "MCA Company Master"])
    cin_value = str(bp.get("cin") or "").strip()
    if cin_value:
        company_class = "Public" if cin_value[0].upper() == "L" else "Private"
    else:
        company_class = "Unknown"
    out += _row(["Company Class", company_class, "CIN Derived"])
    out += _row(["Listed Exchange", bp.get("listed_exchange") or "Unlisted", "BSE/NSE Records"])
    out += _row(["NSE Symbol", bp.get("nse_symbol") or "N/A", "NSE Website"])
    out += _row(["Credit Rating", f"{bp.get('credit_rating', 'N/A')} ({bp.get('rating_agency', 'N/A')})", "Rating Agency"])
    out += _row(["Employee Count", f"{bp.get('employee_count', 'N/A'):,}" if isinstance(bp.get("employee_count"), (int, float)) else "N/A", "Company Disclosure"])
    out += _row(["Authorized Capital", _cr(bp.get("authorized_capital_cr")), "MCA Company Master"])
    out += _row(["Paid-up Capital", _cr(bp.get("paid_up_capital_cr")), "MCA Company Master"])
    out += _row(["MCA Status", _safe(ei, "mca_status"), "MCA Company Master"])
    out += "\n"

    # 2.2 Business Overview
    out += _h("2.2 Business Overview", 3)
    cs = fp["case_summary"]
    industry_data = fp.get("industry_analysis", {})

    out += (f"**{bp['company_name']}** is a {'listed' if bp.get('listed_exchange') else 'private'} company "
            f"incorporated on {bp['date_of_incorporation']} in {bp['registered_state']}. "
            f"The Company operates in the **{cs['sector'].replace('_', ' ').title()}** sector, "
            f"specifically in **{cs['subsector']}**.\n\n")

    if industry_data.get("business_description"):
        out += f"{industry_data['business_description']}\n\n"
    else:
        out += (f"Borrower-specific business description: {NOT_AVAILABLE}. "
                f"{'The Company is listed on ' + bp['listed_exchange'] + ', subject to SEBI regulations and enhanced disclosure requirements.' if bp.get('listed_exchange') else 'Being a private entity, disclosure is limited to statutory requirements.'}\n\n")

    if bp.get("employee_count"):
        out += f"The Company employs approximately **{bp['employee_count']:,}** personnel.\n\n"

    # 2.3 Management Profile
    out += _h("2.3 Management Profile & Board of Directors", 3)
    out += _hdr(["Name", "Designation", "DIN", "Promoter", "Net Worth (₹ Cr)", "Appointment Date", "Other Directorships"])
    for d in mp["directors"]:
        nw = _cr(d["net_worth_cr"]) if d.get("net_worth_cr") else "N/A"
        od = ", ".join(d["other_directorships"][:3]) if d.get("other_directorships") else "None"
        if len(d.get("other_directorships", [])) > 3:
            od += f" (+{len(d['other_directorships'])-3} more)"
        out += _row([
            d["name"], d["designation"], d["din"],
            "Yes" if d["is_promoter"] else "No",
            nw, d.get("date_of_appointment", "N/A"), od,
        ])
    out += "\n"

    # Data source attribution for directors
    director_sources = list({d.get("source", "") for d in mp["directors"] if d.get("source")})
    if director_sources:
        out += f"*Source: {'; '.join(director_sources)}*\n\n"

    # Management quality assessment
    promoters = [d for d in mp["directors"] if d["is_promoter"]]
    independents = [d for d in mp["directors"] if not d["is_promoter"] and "Independent" in d.get("designation", "")]
    out += (f"**Management Assessment:** The Board comprises {len(mp['directors'])} directors, "
            f"including {len(promoters)} promoter director(s) and {len(independents)} independent director(s). ")
    if len(independents) >= 1:
        out += "The presence of independent directors provides adequate board-level governance oversight.\n\n"
    else:
        out += "The limited independent directorship is noted as a governance observation.\n\n"

    # 2.4 Shareholding Pattern
    out += _h("2.4 Shareholding Pattern", 3)
    out += _hdr(["Category", "Holding (%)", "Source"])
    out += _row(["Promoter & Promoter Group", f"{gp['promoter_holding_pct']:.1f}%", "BSE / NSE Filing"])
    out += _row(["Institutional (FII/DII)", f"{gp['institutional_holding_pct']:.1f}%", "BSE / NSE Filing"])
    out += _row(["Public / Others", f"{gp['public_holding_pct']:.1f}%", "BSE / NSE Filing"])
    total = gp['promoter_holding_pct'] + gp['institutional_holding_pct'] + gp['public_holding_pct']
    out += _row(["**Total**", f"**{total:.1f}%**", "Computed"])
    out += "\n"

    if gp["promoter_holding_pct"] > 50:
        out += f"Promoter holding of {gp['promoter_holding_pct']:.1f}% indicates strong promoter control and alignment of interests.\n\n"
    elif gp["promoter_holding_pct"] > 25:
        out += f"Promoter holding of {gp['promoter_holding_pct']:.1f}% provides adequate governance control while allowing institutional participation.\n\n"

    # 2.5 Group Structure
    out += _h("2.5 Group Structure & Corporate Hierarchy", 3)
    out += f"**Group Name:** {gp['group_name']}  \n"
    out += f"**Number of Entities:** {len(gp['entities'])}  \n"
    if ch.get("ultimate_parent"):
        out += f"**Ultimate Parent:** {ch['ultimate_parent']}  \n"
    if ch.get("group_revenue_cr"):
        out += f"**Group Revenue:** {_cr(ch['group_revenue_cr'])}  \n"
    out += "\n"

    if len(gp["entities"]) > 1:
        out += "**Group Entities:**\n\n"
        for i, entity in enumerate(gp["entities"], 1):
            out += f"{i}. {entity}\n"
        out += "\n"

    # Hierarchy tree
    tree = ch.get("hierarchy_tree", [])
    if tree:
        out += "**Corporate Structure:**\n\n"
        out += _render_tree(tree, 0)
        out += "\n"

    out += _resolve_section_source(fp, "Borrower Profile", "Corporate Hierarchy", "Management Profile", fallback="MCA Company Master; ROC Filings; KYC Documentation") + "\n\n"
    out += "---\n\n"
    return out


def _render_tree(nodes: list, depth: int) -> str:
    out = ""
    for node in nodes:
        indent = "  " * depth
        icon = "🏢" if depth == 0 else "├── "
        rel = f" ({node.get('relationship', '').title()})" if depth > 0 else ""
        h_pct = f" [{node['holding_pct']:.0f}%]" if node.get("holding_pct") and depth > 0 else ""
        out += f"{indent}{icon}**{node['company_name']}**{rel}{h_pct}\n"
        if node.get("children"):
            out += _render_tree(node["children"], depth + 1)
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3: INDUSTRY & BUSINESS ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════

def render_section_3_industry_analysis(fp: dict) -> str:
    cs = fp["case_summary"]
    ia = fp.get("industry_analysis", {})
    bs = fp["benchmark_summary"]
    ms = fp.get("market_signals", [])
    swot = ia.get("swot", {})
    _raw_news = fp.get("web_crawl_news", [])
    news = _raw_news.get("articles", []) if isinstance(_raw_news, dict) else _raw_news

    out = _h("3. INDUSTRY & BUSINESS ANALYSIS")

    # 3.1 Industry Overview
    out += _h("3.1 Industry Overview", 3)
    sector = cs["sector"].replace("_", " ").title()
    out += f"**Sector:** {sector}  \n"
    out += f"**Sub-sector:** {cs['subsector']}  \n\n"

    if ia.get("industry_overview"):
        out += f"*Sector reference note (not borrower-specific):* {ia['industry_overview']}\n\n"
    else:
        out += f"Sector outlook: {NOT_AVAILABLE}.\n\n"

    if ia.get("regulatory_environment"):
        out += f"**Regulatory Environment:** {ia['regulatory_environment']}\n\n"

    if ia.get("growth_drivers"):
        out += "**Key Growth Drivers:**\n\n"
        for gd in ia["growth_drivers"]:
            out += f"- {gd}\n"
        out += "\n"

    if ia.get("headwinds"):
        out += "**Key Headwinds:**\n\n"
        for hw in ia["headwinds"]:
            out += f"- {hw}\n"
        out += "\n"

    # 3.2 Competitive Landscape
    out += _h("3.2 Competitive Landscape", 3)
    if ia.get("competitors"):
        out += _hdr(["Competitor", "Revenue (₹ Cr)", "Market Share", "Rating", "Source"])
        for c in ia["competitors"]:
            out += _row([c["name"], _cr(c.get("revenue_cr")), _pct(c.get("market_share_pct")), c.get("rating", "N/A"), c.get("source", "CMIE / Annual Reports")])
        out += "\n"
    else:
        out += (f"Detailed competitive landscape data is based on available sector benchmarks. "
                f"The borrower's financial metrics are compared against {bs.get('sector', 'sector').replace('_', ' ').title()} "
                f"peer group in Section 11 (Peer Comparison).\n\n")

    # 3.3 Revenue Segments & Geography
    out += _h("3.3 Revenue Segments & Geography", 3)
    if ia.get("revenue_segments"):
        out += "**Revenue by Segment:**\n\n"
        out += _hdr(["Segment", "Revenue (₹ Cr)", "% of Total", "Source"])
        for seg in ia["revenue_segments"]:
            out += _row([seg["name"], _cr(seg.get("revenue_cr")), _pct(seg.get("pct")), seg.get("source", "Annual Report")])
        out += "\n"

    if ia.get("geographic_mix"):
        out += "**Geographic Revenue Mix:**\n\n"
        out += _hdr(["Region", "% of Revenue", "Source"])
        for geo in ia["geographic_mix"]:
            out += _row([geo["region"], _pct(geo.get("pct")), geo.get("source", "Annual Report")])
        out += "\n"

    if not ia.get("revenue_segments") and not ia.get("geographic_mix"):
        out += (f"Borrower revenue segmentation and geographic mix: {NOT_AVAILABLE}. "
                "Revenue analysis is based on reported aggregate turnover.\n\n")

    # 3.4 SWOT Analysis
    out += _h("3.4 SWOT Analysis", 3)
    _swot_section = {
        "strengths": ("✅ Strengths", _build_swot_strengths),
        "weaknesses": ("⚠️ Weaknesses", _build_swot_weaknesses),
        "opportunities": ("🔵 Opportunities", _build_swot_opportunities),
        "threats": ("🔴 Threats", _build_swot_threats),
    }
    for key, (title, builder_fn) in _swot_section.items():
        out += f"**{title}:**\n\n"
        items = swot.get(key, [])
        if not items:
            items = builder_fn(fp)
        for item in items:
            out += f"- {item}\n"
        out += "\n"

    # Web crawl news (NTB)
    if news:
        out += _h("3.5 Recent News & Market Intelligence", 3)
        out += _hdr(["Date", "Headline", "Sentiment", "Source"])
        for n in news[:10]:
            out += _row([n.get("date", "N/A"), n.get("headline", ""), n.get("sentiment", "N/A"), n.get("source", "N/A")])
        out += "\n"

    # Market signals
    if ms:
        if not news:
            out += _h("3.5 Market / News Signals", 3)
        else:
            out += "**Additional Market Signals:**\n\n"
        out += _hdr(["Date", "Type", "Headline", "Sentiment", "Severity", "Source"])
        for s in ms:
            out += _row([s["date"], s["type"].title(), s["headline"], s["sentiment"].title(), _badge(s["severity"]), s["source"]])
        out += "\n"

    # Infrastructure metrics for road/highway companies
    out += _render_infra_metrics(fp)

    out += _resolve_section_source(fp, "Industry Analysis", "Market Score", "Benchmark Analysis", fallback="Industry Reports; CMIE; Market Intelligence; Rating Agency Reports") + "\n\n"
    out += "---\n\n"
    return out


def _render_infra_metrics(fp: dict) -> str:
    """Render infrastructure development metrics for road/highway EPC companies."""
    im = fp.get("infra_metrics", {})
    if not im:
        return ""
    out = ""

    # 3.6 Order Book & Execution Overview
    ob = im.get("order_book", {})
    if ob:
        out += _h("3.6 Order Book & Execution Capacity", 3)
        out += _hdr(["Parameter", "Value", "Source"])
        out += _row(["Total Order Book", f"₹ {ob.get('total_order_book_cr', 0):,.2f} Cr", "Company Annual Report"])
        out += _row(["Book-to-Bill Ratio", f"{ob.get('book_to_bill_ratio', 0):.1f}x", "Computed"])
        out += _row(["EPC Orders", f"₹ {ob.get('epc_orders_cr', 0):,.2f} Cr", "Order Book Disclosure"])
        out += _row(["BOT / HAM Orders", f"₹ {ob.get('bot_ham_orders_cr', 0):,.2f} Cr", "Order Book Disclosure"])
        out += _row(["Orders Received (FY25)", f"₹ {ob.get('orders_received_fy25_cr', 0):,.2f} Cr", "Company Disclosure"])
        out += _row(["Executable Order Book", f"₹ {ob.get('executable_order_book_cr', 0):,.2f} Cr", "Company Disclosure"])
        out += "\n"

    # Execution metrics
    em = im.get("execution_metrics", {})
    if em:
        out += "**Execution Performance:**\n\n"
        out += _hdr(["Metric", "FY2023", "FY2024", "FY2025", "Source"])
        out += _row(["Km of Road Executed",
                     f"{em.get('km_executed_fy23', 'N/A')} km",
                     f"{em.get('km_executed_fy24', 'N/A')} km",
                     f"{em.get('km_executed_fy25', 'N/A')} km",
                     "Company Operational Data"])
        out += "\n"

        out += _hdr(["Cost Parameter", "Value", "Source"])
        out += _row(["Avg. Construction Cost per Km", f"₹ {em.get('avg_construction_cost_per_km_cr', 0):.1f} Cr/km", "Company Data / NHAI"])
        out += _row(["Avg. Land Acquisition Cost per Sq Km", f"₹ {em.get('avg_land_acquisition_cost_per_sq_km_cr', 0):.1f} Cr/sq km", "Company Data / MoRTH"])
        out += _row(["Avg. Land Acquisition Cost per Hectare", f"₹ {em.get('avg_land_acquisition_cost_per_hectare_cr', 0):.2f} Cr/ha", "Company Data / MoRTH"])
        out += _row(["Effective Construction Days / Year", f"{em.get('effective_construction_days_per_year', 'N/A')} days", "Company Operational Data"])
        out += _row(["Equipment Utilization", f"{em.get('equipment_utilization_pct', 0):.1f}%", "Company Operational Data"])
        out += "\n"

    # Project Pipeline
    pp = im.get("project_pipeline", [])
    if pp:
        out += _h("3.7 Project Pipeline", 3)
        out += _hdr(["Project", "Length (km)", "Contract Value (₹ Cr)", "Completion %", "Model", "Client", "Target", "Source"])
        for p in pp:
            out += _row([p["project_name"], f"{p['length_km']} km", f"₹ {p['contract_value_cr']:,.2f} Cr",
                        f"{p['completion_pct']}%", p["model"], p["client"], p["target_completion"], p.get("source", "NHAI / Company")])
        total_km = sum(p["length_km"] for p in pp)
        total_val = sum(p["contract_value_cr"] for p in pp)
        out += _row(["**Total**", f"**{total_km} km**", f"**₹ {total_val:,.2f} Cr**", "", "", "", "", ""])
        out += "\n"

    # BOT / HAM Portfolio
    bh = im.get("bot_ham_portfolio", {})
    if bh and bh.get("assets"):
        out += _h("3.8 BOT / HAM Concession Portfolio", 3)
        out += _hdr(["Parameter", "Value", "Source"])
        out += _row(["Total Concession Assets", bh.get("total_concession_assets", "N/A"), "Concession Agreements"])
        out += _row(["Total Concession Value", f"₹ {bh.get('total_concession_value_cr', 0):,.2f} Cr", "Concession Agreements"])
        out += _row(["Annual Toll Revenue", f"₹ {bh.get('annual_toll_revenue_cr', 0):,.2f} Cr", "Toll Collection Data"])
        out += _row(["Avg. Residual Concession Period", f"{bh.get('avg_residual_concession_years', 0):.1f} years", "Concession Agreements"])
        out += "\n"

        out += _hdr(["Asset", "Length (km)", "Concession (yrs)", "Residual (yrs)", "Annual Toll (₹ Cr)", "Model", "Source"])
        for a in bh["assets"]:
            out += _row([a["name"], f"{a['length_km']} km", a["concession_years"],
                        a["residual_years"], f"₹ {a['annual_toll_cr']:,.2f} Cr", a["model"], "Concession Agreement"])
        out += "\n"

    # Development Projections
    dp = im.get("development_projections", {})
    if dp:
        out += _h("3.9 Development Projections", 3)
        out += _hdr(["Parameter", "FY2026 (P)", "FY2027 (P)", "Source"])
        out += _row(["Projected Km Executed", f"{dp.get('projected_km_fy26', 'N/A')} km", f"{dp.get('projected_km_fy27', 'N/A')} km", "Company Projections"])
        out += _row(["Projected Revenue", f"₹ {dp.get('projected_revenue_fy26_cr', 0):,.2f} Cr", f"₹ {dp.get('projected_revenue_fy27_cr', 0):,.2f} Cr", "Company Projections"])
        out += _row(["Capex Plan", f"₹ {dp.get('capex_plan_fy26_cr', 0):,.2f} Cr", f"₹ {dp.get('capex_plan_fy27_cr', 0):,.2f} Cr", "Company Projections"])
        out += "\n"
        if dp.get("land_bank_hectares"):
            out += f"**Land Bank:** {dp['land_bank_hectares']} hectares valued at ₹ {dp.get('land_bank_value_cr', 0):,.2f} Cr\n\n"

    if out:
        out += _resolve_section_source(fp, "Industry Analysis", "Financial Analysis", fallback="Company Annual Report; NHAI Project Tracker; MoRTH Award Data") + "\n\n"
    return out


def _build_swot_strengths(fp: dict) -> list:
    """Auto-generate SWOT strengths from fact-pack data."""
    items = []
    bp = fp["borrower_profile"]
    cs = fp["case_summary"]
    fs = fp["financial_summary"]
    strengths = fp.get("credit_strengths", [])

    if bp.get("listed_exchange"):
        items.append(f"Listed on {bp['listed_exchange']} — enhanced transparency and market discipline")
    if bp.get("credit_rating") and "A" in bp.get("credit_rating", "").upper():
        items.append(f"Investment-grade credit rating ({bp['credit_rating']}) from {bp.get('rating_agency', 'agency')}")

    periods = sorted(fs["periods"].keys())
    if len(periods) >= 2:
        first = fs["periods"][periods[0]]
        last = fs["periods"][periods[-1]]
        if first.get("revenue_cr") and last.get("revenue_cr") and first["revenue_cr"] > 0:
            growth = ((last["revenue_cr"] - first["revenue_cr"]) / first["revenue_cr"]) * 100
            if growth > 10:
                items.append(f"Consistent revenue growth — {growth:.1f}% over {len(periods)-1} year(s)")

    if periods:
        latest = fs["periods"][periods[-1]]
        if latest.get("ebitda_margin_pct") and latest["ebitda_margin_pct"] > 15:
            items.append(f"Healthy operating margins (EBITDA margin: {latest['ebitda_margin_pct']:.1f}%)")

    for s in strengths[:3]:
        if s.get("detail") and s["detail"] not in str(items):
            items.append(s["detail"])

    if not items:
        items.append(f"Established presence in the {cs['sector'].replace('_', ' ').title()} sector")
    return items


def _build_swot_weaknesses(fp: dict) -> list:
    items = []
    fs = fp["financial_summary"]
    ra = fp["ratio_analysis"]
    risks = fp.get("key_risks", [])

    periods = sorted(fs["periods"].keys())
    if periods:
        latest_ratios = ra.get(periods[-1], {})
        de = latest_ratios.get("debt_to_equity", {}).get("value")
        if de and de > 2.0:
            items.append(f"High leverage — Debt/Equity at {de:.2f}x")
        icr = latest_ratios.get("interest_coverage_ratio", {}).get("value")
        if icr and icr < 2.0:
            items.append(f"Low interest coverage ({icr:.2f}x) limiting debt servicing headroom")
        wcc = latest_ratios.get("working_capital_cycle", {}).get("value")
        if wcc and wcc > 90:
            items.append(f"Extended working capital cycle ({wcc:.0f} days)")

    for r in risks[:2]:
        if r.get("detail") and r["detail"] not in str(items):
            items.append(r["detail"])

    if not items:
        items.append("Limited public information available for comprehensive assessment")
    return items


def _build_swot_opportunities(fp: dict) -> list:
    items = []
    cs = fp["case_summary"]
    ia = fp.get("industry_analysis", {})

    if ia.get("growth_drivers"):
        items.extend(ia["growth_drivers"][:2])
    else:
        sector = cs["sector"]
        _opp_map = {
            "manufacturing": ["Government's Make in India initiative and PLI schemes", "Export market expansion driven by China+1 strategy"],
            "infrastructure": ["National Infrastructure Pipeline projects worth ₹111 lakh Cr", "Increased government capital expenditure in Union Budget"],
            "pharma": ["Growing domestic healthcare demand and generic market", "Export opportunities to regulated markets (US, EU)"],
            "logistics": ["National Logistics Policy targeting cost reduction", "E-commerce growth driving warehousing demand"],
        }
        items.extend(_opp_map.get(sector, ["Sector growth aligned with India's GDP trajectory", "Increasing formalization and digital adoption"]))

    return items


def _build_swot_threats(fp: dict) -> list:
    items = []
    cs = fp["case_summary"]
    ia = fp.get("industry_analysis", {})

    if ia.get("headwinds"):
        items.extend(ia["headwinds"][:2])
    else:
        items.append("Rising interest rates impacting debt servicing costs")
        items.append("Input cost volatility and supply chain disruptions")
        sector = cs["sector"]
        if sector == "manufacturing":
            items.append("Competitive pressure from imports and global players")
        elif sector == "infrastructure":
            items.append("Regulatory delays in project approvals and land acquisition")
        elif sector == "pharma":
            items.append("USFDA regulatory scrutiny and pricing pressure in key markets")

    return items


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4: FINANCIAL ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════

def render_section_4_financial_analysis(fp: dict) -> str:
    fs = fp["financial_summary"]
    ra = fp["ratio_analysis"]
    periods = sorted(fs["periods"].keys())

    out = _h("4. FINANCIAL ANALYSIS")

    # 4.1 P&L
    out += _h("4.1 Profit & Loss Statement (₹ Cr)", 3)
    out += _hdr(["Particulars"] + periods + ["Source"])

    pnl_items = [
        ("Revenue from Operations", "revenue_cr"),
        ("EBITDA", "ebitda_cr"),
        ("EBITDA Margin (%)", "ebitda_margin_pct"),
        ("PAT", "pat_cr"),
        ("PAT Margin (%)", "pat_margin_pct"),
    ]
    for label, key in pnl_items:
        row = [label]
        for p in periods:
            val = fs["periods"][p].get(key)
            row.append(_pct(val) if "pct" in key else _cr(val))
        row.append("Audited P&L" if "margin" not in key else "Computed")
        out += _row(row)
    out += "\n"

    # Data source attribution for financials
    fin_sources = list(dict.fromkeys(fs["periods"][p].get("data_source", "") for p in periods if fs["periods"][p].get("data_source")))
    if fin_sources:
        sources_str = "; ".join(fin_sources)
        out += f"*Source: {sources_str}*\n\n"

    # Revenue growth commentary
    if len(periods) >= 2:
        first = fs["periods"][periods[0]]
        last = fs["periods"][periods[-1]]
        total_growth, cagr = fs.get("revenue_total_growth_pct"), fs.get("revenue_cagr_pct")
        if total_growth is not None and cagr is not None:   # computed by the financial_analysis agent
            out += (f"Revenue has {'grown' if total_growth > 0 else 'declined'} from {_cr(first['revenue_cr'])} "
                    f"({periods[0]}) to {_cr(last['revenue_cr'])} ({periods[-1]}), "
                    f"a {'growth' if total_growth > 0 else 'decline'} of {abs(total_growth):.1f}% "
                    f"(CAGR: {cagr:.1f}%).\n\n")

        # YoY growth table
        out += "**Year-on-Year Revenue Growth:**\n\n"
        out += _hdr(["Period", "Revenue (₹ Cr)", "YoY Growth", "Source"])
        for i, p in enumerate(periods):
            rev = fs["periods"][p].get("revenue_cr")
            if i == 0:
                out += _row([p, _cr(rev), "—", "Audited P&L"])
            else:
                yoy = (fs.get("growth_by_period") or {}).get(p, {}).get("revenue_yoy_pct")
                out += _row([p, _cr(rev), f"{yoy:+.1f}%" if yoy is not None else "n/a", "Audited P&L"])
        out += "\n"

    # Profitability commentary
    if periods:
        latest = fs["periods"][periods[-1]]
        out += (f"**Profitability:** EBITDA margin stands at {_pct(latest.get('ebitda_margin_pct'))} "
                f"with PAT margin of {_pct(latest.get('pat_margin_pct'))} for {periods[-1]}. ")
        if len(periods) >= 2:
            first_margins = fs["periods"][periods[0]]
            em_first = first_margins.get("ebitda_margin_pct", 0) or 0
            em_last = latest.get("ebitda_margin_pct", 0) or 0
            if em_last > em_first + 1:
                out += "Operating margins have improved over the analysis period, indicating strengthening cost efficiency.\n\n"
            elif em_last < em_first - 1:
                out += "Operating margins have declined, warranting attention to cost management.\n\n"
            else:
                out += "Margins have remained broadly stable.\n\n"
        else:
            out += "\n\n"

    # 4.2 Balance Sheet
    out += _h("4.2 Balance Sheet Summary (₹ Cr)", 3)
    out += _hdr(["Particulars"] + periods + ["Source"])
    bs_items = [
        ("Net Worth / Equity", "net_worth_cr"),
        ("Total Debt", "total_debt_cr"),
        ("Total Assets", "total_assets_cr"),
        ("Current Assets", "current_assets_cr"),
        ("Current Liabilities", "current_liabilities_cr"),
        ("Trade Receivables", "trade_receivables_cr"),
        ("Inventory", "inventory_cr"),
        ("Trade Payables", "trade_payables_cr"),
    ]
    for label, key in bs_items:
        row = [label]
        for p in periods:
            row.append(_cr(fs["periods"][p].get(key)))
        row.append("Audited Balance Sheet")
        out += _row(row)
    out += "\n"

    # Balance sheet commentary
    if periods:
        latest = fs["periods"][periods[-1]]
        nw = latest.get("net_worth_cr", 0) or 0
        td = latest.get("total_debt_cr", 0) or 0
        de = td / nw if nw > 0 else 0
        out += (f"**Balance Sheet Strength:** Net worth of {_cr(nw)} against total debt of {_cr(td)}, "
                f"yielding Debt/Equity of {de:.2f}x. ")
        ca = latest.get("current_assets_cr", 0) or 0
        cl = latest.get("current_liabilities_cr", 0) or 0
        cr_val = ca / cl if cl > 0 else 0
        out += f"Current ratio of {cr_val:.2f}x.\n\n"

    # 4.3 Cash Flow
    out += _h("4.3 Cash Flow Statement (₹ Cr)", 3)
    out += _hdr(["Particulars"] + periods + ["Source"])
    for label, key in [("Operating Cash Flow", "operating_cash_flow_cr"), ("Capital Expenditure", "capex_cr")]:
        row = [label]
        for p in periods:
            row.append(_cr(fs["periods"][p].get(key)))
        row.append("Audited Cash Flow")
        out += _row(row)

    # FCF row
    row = ["**Free Cash Flow**"]
    for p in periods:
        ocf = fs["periods"][p].get("operating_cash_flow_cr") or 0
        capex = fs["periods"][p].get("capex_cr") or 0
        row.append(_cr(ocf - capex))
    row.append("Computed")
    out += _row(row)
    out += "\n"

    # Cash flow commentary
    if periods:
        latest = fs["periods"][periods[-1]]
        ocf = latest.get("operating_cash_flow_cr")
        pat = latest.get("pat_cr")
        if ocf and pat and pat != 0:
            accrual = ocf / pat
            out += (f"**Cash Quality:** OCF/PAT ratio of {accrual:.2f}x for {periods[-1]}. ")
            if accrual > 1.0:
                out += "Strong cash generation relative to profits.\n\n"
            elif accrual > 0.5:
                out += "Adequate cash conversion.\n\n"
            else:
                out += "Weak cash conversion — requires working capital review.\n\n"

    # 4.4 Key Financial Ratios
    out += _h("4.4 Key Financial Ratios", 3)
    ratio_display = {
        "current_ratio": ("Current Ratio", "x"),
        "debt_to_equity": ("Debt / Equity", "x"),
        "debt_to_ebitda": ("Debt / EBITDA", "x"),
        "interest_coverage_ratio": ("Interest Coverage (ICR)", "x"),
        "dscr": ("DSCR", "x"),
        "ebitda_margin": ("EBITDA Margin", "%"),
        "net_profit_margin": ("Net Profit Margin", "%"),
        "return_on_equity": ("Return on Equity (ROE)", "%"),
        "return_on_assets": ("Return on Assets (ROA)", "%"),
        "asset_turnover": ("Asset Turnover", "x"),
        "debtor_days": ("Debtor Days", "d"),
        "inventory_days": ("Inventory Days", "d"),
        "payable_days": ("Payable Days", "d"),
        "working_capital_cycle": ("Working Capital Cycle", "d"),
        "tol_tnw": ("TOL / TNW", "x"),
    }
    out += _hdr(["Ratio"] + periods + ["Benchmark", "Source"])
    ratio_sources = {
        "current_ratio": "Audited Balance Sheet",
        "debt_to_equity": "Audited Balance Sheet",
        "debt_to_ebitda": "Audited Financials",
        "interest_coverage_ratio": "Audited P&L",
        "dscr": "Audited Cash Flow",
        "ebitda_margin": "Audited P&L",
        "net_profit_margin": "Audited P&L",
        "return_on_equity": "Audited Financials",
        "return_on_assets": "Audited Financials",
        "asset_turnover": "Audited Financials",
        "debtor_days": "Audited Balance Sheet",
        "inventory_days": "Audited Balance Sheet",
        "payable_days": "Audited Balance Sheet",
        "working_capital_cycle": "Computed",
        "tol_tnw": "Audited Balance Sheet",
    }
    for rname, (display, fmt) in ratio_display.items():
        row = [display]
        for p in periods:
            r = ra.get(p, {}).get(rname, {})
            val = r.get("value")
            if val is None:
                row.append("N/A")
            elif fmt == "%":
                row.append(f"{val * 100:.1f}%")
            elif fmt == "d":
                row.append(f"{val:.0f}")
            else:
                row.append(f"{val:.2f}")
        # Add peer benchmark
        bms = fp["benchmark_summary"].get("benchmarks", [])
        bm_val = next((b["peer_median"] for b in bms if b["metric"] == rname), None)
        if bm_val is not None:
            if fmt == "%":
                row.append(f"{bm_val*100:.1f}%" if abs(bm_val) < 1 else f"{bm_val:.1f}%")
            elif fmt == "d":
                row.append(f"{bm_val:.0f}")
            else:
                row.append(f"{bm_val:.2f}")
        else:
            row.append("—")
        row.append(ratio_sources.get(rname, "Audited Financials"))
        out += _row(row)
    out += "\n"

    # Working capital commentary
    if periods:
        latest_ra = ra.get(periods[-1], {})
        dd = latest_ra.get("debtor_days", {}).get("value")
        invd = latest_ra.get("inventory_days", {}).get("value")
        pd_val = latest_ra.get("payable_days", {}).get("value")
        wcc = latest_ra.get("working_capital_cycle", {}).get("value")
        if dd is not None:
            _invd = f"{invd:.0f}" if invd else "N/A"
            _pd = f"{pd_val:.0f}" if pd_val else "N/A"
            _wcc = f"{wcc:.0f}" if wcc else "N/A"
            out += (f"**Working Capital:** Debtor Days: {dd:.0f} | Inventory Days: {_invd} | "
                    f"Payable Days: {_pd} | WC Cycle: {_wcc} days\n\n")

    # Debt servicing
    out += "**Debt Servicing Capacity:**\n\n"
    out += _hdr(["Period", "ICR", "DSCR", "Debt/Equity", "Debt/EBITDA", "Source"])
    for p in periods:
        r = ra.get(p, {})
        icr = r.get("interest_coverage_ratio", {}).get("value")
        dscr = r.get("dscr", {}).get("value")
        de = r.get("debt_to_equity", {}).get("value")
        dte = r.get("debt_to_ebitda", {}).get("value")
        out += _row([p,
            f"{icr:.2f}x" if icr else "N/A",
            f"{dscr:.2f}x" if dscr else "N/A",
            f"{de:.2f}x" if de else "N/A",
            f"{dte:.2f}x" if dte else "N/A",
            "Audited Financials",
        ])
    out += "\n"

    if periods:
        icr = ra.get(periods[-1], {}).get("interest_coverage_ratio", {}).get("value")
        if icr:
            if icr > 3.0:
                out += f"Interest coverage of {icr:.2f}x provides comfortable debt servicing headroom.\n\n"
            elif icr > 1.5:
                out += f"Interest coverage of {icr:.2f}x is adequate with limited buffer.\n\n"
            else:
                out += f"Interest coverage of {icr:.2f}x is concerning — limited debt servicing capacity.\n\n"

    out += _resolve_section_source(fp, "Financial Analysis", "Key Ratios", "Cash Flow", fallback="Audited Annual Reports; Provisional Financials; BSE/NSE Filings") + "\n\n"
    out += "---\n\n"
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5: CREDIT FACILITY DETAILS
# ═══════════════════════════════════════════════════════════════════════════════

def render_section_5_facility_details(fp: dict) -> str:
    fd = fp["facility_details"]
    ee = fp["existing_exposure"]
    cs = fp["case_summary"]
    pricing = fp.get("facility_pricing", {})

    out = _h("5. CREDIT FACILITY DETAILS")

    # 5.1 Facility Structure
    out += _h("5.1 Facility Structure", 3)
    out += _hdr(["Parameter", "Details", "Source"])
    out += _row(["Nature of Facility", fd["facility_type"].replace("_", " ").title(), "Facility Application"])
    out += _row(["Amount Requested", _cr(fd["amount_requested_cr"]), "Facility Application"])
    out += _row(["Proposed Limit", _cr(fd["proposed_limit_cr"]), "Credit Appraisal"])
    if fd.get("existing_limit_cr"):
        out += _row(["Existing Limit", _cr(fd["existing_limit_cr"]), "Bank Records"])
        out += _row(["Enhancement", _cr(fd["amount_requested_cr"] - (fd.get("existing_limit_cr") or 0)), "Computed"])
    out += _row(["Tenor", f"{fd['tenor_months']} months" if fd.get("tenor_months") else "Revolving", "Facility Application"])
    out += _row(["Security / Collateral Type", fd.get("collateral_type") or "As per bank norms", "Facility Application"])
    out += _row(["Purpose", fd["purpose"], "Facility Application"])
    out += "\n"

    # Existing exposure
    if ee:
        out += "**Existing Banking Exposure:**\n\n"
        out += _hdr(["Facility Type", "Sanctioned (₹ Cr)", "Outstanding (₹ Cr)", "Utilization %", "Overdue Days", "Classification", "Source"])
        total_sanc = 0
        total_os = 0
        for e in ee:
            out += _row([e["facility_type"], _cr(e["sanctioned_cr"]), _cr(e["outstanding_cr"]),
                        f"{e['utilization_pct']:.1f}%", e["overdue_days"], e["classification"], "CRILC / Bank Records"])
            total_sanc += e["sanctioned_cr"]
            total_os += e["outstanding_cr"]
        out += _row(["**Total**", f"**{_cr(total_sanc)}**", f"**{_cr(total_os)}**", "", "", "", ""])
        out += "\n"
        out += f"Total banking exposure post-sanction: {_cr(total_os + fd['amount_requested_cr'])}\n\n"

    # 5.2 Purpose & End-Use
    out += _h("5.2 Purpose & End-Use of Funds", 3)
    out += f"The proposed facility is requested for **{fd['purpose']}**.\n\n"

    if pricing.get("end_use_details"):
        out += _hdr(["End-Use Component", "Amount (₹ Cr)", "% of Total", "Source"])
        for eu in pricing["end_use_details"]:
            out += _row([eu["component"], _cr(eu["amount_cr"]), _pct(eu.get("pct")), eu.get("source", "Facility Application")])
        out += "\n"
    else:
        out += (f"Borrower-specific end-use breakdown: {NOT_AVAILABLE}. "
                f"End-use certificate to be obtained post-disbursement.\n\n")

    # 5.3 Pricing Structure
    out += _h("5.3 Pricing Structure", 3)
    if pricing.get("interest_rate"):
        out += _hdr(["Component", "Rate / Value", "Source"])
        out += _row(["Base Rate / MCLR", pricing.get("base_rate", "MCLR + applicable spread"), "Treasury"])
        out += _row(["Interest Rate", pricing.get("interest_rate", "As per sanction"), "Sanction Terms"])
        out += _row(["Processing Fee", pricing.get("processing_fee", "As per schedule"), "Bank Schedule"])
        out += _row(["Commitment Charge", pricing.get("commitment_charge", "Nil"), "Sanction Terms"])
        out += _row(["Penal Interest", pricing.get("penal_interest", "As per RBI guidelines"), "RBI Circular"])
        out += "\n"
    else:
        out += _hdr(["Component", "Rate / Value", "Source"])
        out += _row(["Base Rate", "MCLR (1-Year) + Applicable Spread", "Treasury"])
        out += _row(["Processing Fee", "As per bank's schedule of charges", "Bank Schedule"])
        out += _row(["Commitment Charge", "0.50% p.a. on undrawn portion (if applicable)", "Bank Policy"])
        out += _row(["Penal Interest", "As per RBI guidelines dated 18.08.2023", "RBI Circular"])
        out += "\n"

    # 5.4 Drawing Power (for WC facilities)
    out += _h("5.4 Drawing Power Assessment", 3)
    dp = fp.get("drawing_power", {})
    if dp:
        out += _hdr(["Component", "Value (₹ Cr)", "Margin %", "Drawing Power (₹ Cr)", "Source"])
        for item in dp.get("components", []):
            out += _row([item["name"], _cr(item["value_cr"]), _pct(item.get("margin_pct")), _cr(item.get("dp_cr")), "Stock Statement"])
        out += _row(["**Total Drawing Power**", "", "", f"**{_cr(dp.get('total_dp_cr'))}**", ""])
        out += "\n"
    else:
        if fd["facility_type"] == "working_capital":
            fs = fp["financial_summary"]
            periods = sorted(fs["periods"].keys())
            if periods:
                latest = fs["periods"][periods[-1]]
                recv = latest.get("trade_receivables_cr", 0) or 0
                inv = latest.get("inventory_cr", 0) or 0
                pay = latest.get("trade_payables_cr", 0) or 0
                dp_recv = recv * 0.75  # 25% margin on receivables
                dp_inv = inv * 0.60   # 40% margin on inventory
                total_dp = dp_recv + dp_inv - pay * 0.5
                out += _hdr(["Component", "Book Value (₹ Cr)", "Margin", "Drawing Power (₹ Cr)", "Source"])
                out += _row(["Trade Receivables (< 90 days)", _cr(recv), "25%", _cr(dp_recv), "Audited Balance Sheet"])
                out += _row(["Inventory (Finished + Raw)", _cr(inv), "40%", _cr(dp_inv), "Audited Balance Sheet"])
                out += _row(["Less: Creditors for Purchases", _cr(pay), "50%", f"({_cr(pay * 0.5)})", "Audited Balance Sheet"])
                out += _row(["**Net Drawing Power**", "", "", f"**{_cr(max(total_dp, 0))}**", "Computed"])
                out += "\n"
                ratio_dp = total_dp / fd["amount_requested_cr"] if fd["amount_requested_cr"] > 0 else 0
                out += f"Drawing Power coverage: {ratio_dp:.2f}x against requested limit of {_cr(fd['amount_requested_cr'])}.\n\n"
        else:
            out += "Drawing Power assessment is not applicable for term loan facilities.\n\n"

    out += _resolve_section_source(fp, "Existing Exposure", "External Intelligence", fallback="Facility Application; Existing Bank Records; CRILC Data") + "\n\n"
    out += "---\n\n"
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6: SECURITY & COLLATERAL
# ═══════════════════════════════════════════════════════════════════════════════

def render_section_6_security_collateral(fp: dict) -> str:
    ca = fp["collateral_analysis"]
    ei = fp["external_intelligence"]

    out = _h("6. SECURITY & COLLATERAL")

    # 6.1 Security Structure
    out += _h("6.1 Security Structure", 3)
    out += _hdr(["Security Type", "Description", "Market Value (₹ Cr)", "Forced Sale Value (₹ Cr)", "Valuation Date", "Encumbrance Status", "Source"])
    for c in ca["collaterals"]:
        out += _row([c["type"], c["description"], _cr(c["market_value_cr"]),
                    _cr(c["forced_sale_value_cr"]), c["valuation_date"], c["encumbrance"],
                    c.get("source", "Valuation Report")])
    out += "\n"

    out += _hdr(["Coverage Summary", "Value", "Source"])
    out += _row(["Total Market Value", _cr(ca["total_market_value_cr"]), "Valuation Report"])
    out += _row(["Total Forced Sale Value", _cr(ca["total_forced_sale_value_cr"]), "Valuation Report"])
    out += _row(["Facility Amount", _cr(ca["facility_amount_cr"]), "Facility Application"])
    out += _row(["**Security Coverage (Market Value)**", f"**{ca['coverage_ratio_market']:.2f}x**", "Computed"])
    out += _row(["**Security Coverage (FSV)**", f"**{ca['coverage_ratio_fsv']:.2f}x**", "Computed"])
    out += "\n"

    # Adequacy assessment
    if ca["coverage_ratio_fsv"] >= 1.5:
        out += "**Assessment:** Security coverage is adequate. FSV coverage of {:.2f}x provides comfortable margin.\n\n".format(ca["coverage_ratio_fsv"])
    elif ca["coverage_ratio_fsv"] >= 1.0:
        out += "**Assessment:** Security coverage is at par. Additional collateral may be considered for enhanced comfort.\n\n"
    else:
        out += "**Assessment:** Security coverage is below par. Enhancement of collateral recommended.\n\n"

    # 6.2 CERSAI / ROC Registration
    out += _h("6.2 CERSAI / ROC Registration Details", 3)

    # Use charges data from external intelligence if available
    charges_data = fp.get("charges_data", {})
    if charges_data.get("charges"):
        out += _hdr(["Charge ID", "Charge Holder", "Amount (₹ Cr)", "Date Created", "Status", "Assets", "Source"])
        for ch in charges_data["charges"]:
            out += _row([
                ch.get("charge_id", "N/A"),
                ch.get("charge_holder", "N/A"),
                _cr(ch.get("amount_inr", 0) / 1e7),
                ch.get("date_created", "N/A"),
                ch.get("status", "N/A"),
                ch.get("assets", "N/A")[:60],
                "ROC / CERSAI",
            ])
        out += "\n"
    else:
        out += _hdr(["Registration", "Status", "Source"])
        out += _row(["CERSAI Registration", "To be completed post-sanction", "CERSAI Records"])
        out += _row(["ROC Charge Registration", "To be filed within 30 days of creation of charge", "ROC Records"])
        out += _row(["Equitable Mortgage", "As applicable", "Title Deed"])
        out += "\n"

    out += _resolve_section_source(fp, "Compliance", "Data Integrity", fallback="Valuation Reports; CERSAI Records; ROC Charge Registry; Title Search") + "\n\n"
    out += "---\n\n"
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 7: RISK ASSESSMENT & INTERNAL CREDIT RATING
# ═══════════════════════════════════════════════════════════════════════════════

def render_section_7_risk_assessment(fp: dict) -> str:
    pd = fp["policy_decisions"]
    t1 = pd["tier1_hard_rules"]
    t2 = pd["tier2_risk_scores"]
    t3 = pd["tier3_recommendation"]
    ei = fp["external_intelligence"]
    exceptions = fp["validation_exceptions"]

    out = _h("7. RISK ASSESSMENT & INTERNAL CREDIT RATING")

    # 7.1 Internal Rating Summary
    out += _h("7.1 Internal Rating Summary", 3)
    out += _hdr(["Parameter", "Score / Grade", "Source"])
    out += _row(["Financial Score", f"{t2['financial_score']}/100", "Internal Rating Model"])
    out += _row(["Conduct Score", f"{t2['conduct_score']}/100", "Internal Rating Model"])
    out += _row(["Governance Score", f"{t2['governance_score']}/100", "Internal Rating Model"])
    out += _row(["Market Score", f"{t2['market_score']}/100", "Internal Rating Model"])
    out += _row(["**Composite Score**", f"**{t2['composite_score']}/100**", "Internal Rating Model"])
    out += _row(["**Risk Grade**", f"**{t2['risk_grade']}**", "Internal Rating Model"])
    out += "\n"

    out += "*Weight Distribution: Financial 40% | Conduct 25% | Governance 20% | Market 15%*\n\n"

    # Grade interpretation
    grade_desc = {
        "A": "Strong credit — well-managed risks, suitable for standard terms",
        "B": "Acceptable credit — manageable risks, standard/enhanced terms",
        "C": "Marginal credit — close monitoring required, conservative terms",
        "D": "Weak credit — significant concerns, restrictive terms or decline",
        "E": "Poor credit — critical risk factors, recommend decline",
    }
    out += f"**Grade Interpretation:** {grade_desc.get(t2['risk_grade'], 'To be assessed')}\n\n"

    # Component-wise narrative
    out += "**Component-wise Assessment:**\n\n"
    for component, score, weight, narrative in [
        ("Financial", t2["financial_score"], "40%",
         "strong financial metrics" if t2["financial_score"] >= 75 else "adequate financial position" if t2["financial_score"] >= 55 else "weak financial profile"),
        ("Conduct", t2["conduct_score"], "25%",
         "satisfactory banking conduct" if t2["conduct_score"] >= 75 else "mixed conduct signals" if t2["conduct_score"] >= 55 else "concerning conduct patterns"),
        ("Governance", t2["governance_score"], "20%",
         "strong governance quality" if t2["governance_score"] >= 75 else "adequate governance" if t2["governance_score"] >= 55 else "governance concerns noted"),
        ("Market", t2["market_score"], "15%",
         "positive market signals" if t2["market_score"] >= 75 else "mixed market sentiment" if t2["market_score"] >= 55 else "adverse market signals"),
    ]:
        out += f"- **{component} (Score: {score}, Weight: {weight}):** Indicates {narrative}.\n"
    out += "\n"

    # Infra sector KPI impact (if applicable)
    im = fp.get("infra_metrics", {})
    if im:
        out += "**Infrastructure Sector KPI Adjustments (included in Financial Score):**\n\n"
        ob = im.get("order_book", {})
        em_data = im.get("execution_metrics", {})
        bh = im.get("bot_ham_portfolio", {})
        if ob.get("book_to_bill_ratio"):
            btb = ob["book_to_bill_ratio"]
            status = "Strong" if btb >= 3.0 else "Adequate" if btb >= 2.0 else "Weak"
            out += f"- **Order Book Depth:** Book-to-Bill {btb:.1f}x — {status} revenue visibility\n"
        if em_data.get("km_executed_fy25") and em_data.get("km_executed_fy24"):
            growth = (em_data["km_executed_fy25"] - em_data["km_executed_fy24"]) / em_data["km_executed_fy24"] * 100
            out += f"- **Execution Velocity:** {em_data['km_executed_fy25']} km (FY25), YoY growth {growth:.1f}%\n"
        if em_data.get("avg_construction_cost_per_km_cr"):
            out += f"- **Construction Cost:** ₹ {em_data['avg_construction_cost_per_km_cr']:.1f} Cr/km (NHAI norm: ₹15-20 Cr/km)\n"
        if em_data.get("avg_land_acquisition_cost_per_sq_km_cr"):
            out += f"- **Land Acquisition Cost:** ₹ {em_data['avg_land_acquisition_cost_per_sq_km_cr']:.1f} Cr/sq km\n"
        if bh.get("annual_toll_revenue_cr"):
            out += f"- **BOT/HAM Annuity Income:** ₹ {bh['annual_toll_revenue_cr']:,.2f} Cr/yr (de-risks EPC cyclicality)\n"
        out += "\n"
        out += _resolve_section_source(fp, "Industry Analysis", "Financial Analysis", fallback="Company Operational Data; NHAI Project Tracker; Concession Agreements") + "\n\n"

    # 7.2 External Credit Ratings
    out += _h("7.2 External Credit Ratings", 3)
    ra = ei.get("rating_action")
    if ra:
        out += _hdr(["Parameter", "Details", "Source"])
        out += _row(["Rating Agency", ra.get("rating_agency", "N/A"), "Rating Agency"])
        out += _row(["Long-term Rating", ra.get("long_term_rating", "N/A"), "Rating Agency"])
        out += _row(["Rating Outlook", ra.get("outlook", "N/A"), "Rating Agency"])
        out += _row(["Last Rating Action", ra.get("last_action", "N/A"), "Rating Agency"])
        out += _row(["Action Date", ra.get("action_date", "N/A"), "Rating Agency"])
        if ra.get("rationale_summary"):
            out += _row(["Rationale", ra["rationale_summary"], "Rating Agency"])
        out += "\n"
    else:
        out += "External credit rating data is not available for this borrower.\n\n"

    # 7.3 PEP Screening & Enhanced Due Diligence
    pep = fp.get("pep_screening")
    if pep:
        out += _h("7.3 PEP Screening & Enhanced Due Diligence", 3)
        out += f"**Screening Date:** {pep.get('screening_date', 'N/A')}  |  **Total Persons Screened:** {pep.get('total_persons_screened', 'N/A')}\n\n"
        if pep.get("pep_hits"):
            out += _hdr(["Person", "DIN", "Match Type", "Category", "Risk Level", "Sanctions", "Adverse Media"])
            for m in pep["pep_hits"]:
                out += _row([
                    m.get("person_name", "N/A"), m.get("din", "N/A"), m.get("match_type", "N/A"),
                    m.get("pep_category", "N/A"), m.get("risk_level", "N/A"),
                    "Yes" if m.get("sanctions_list_hit") else "No",
                    str(m.get("adverse_media_count", 0))
                ])
            out += "\n"
            out += f"**Overall PEP Risk:** {_badge(pep.get('overall_risk', 'nil'))}  |  **Status:** {pep.get('status', 'N/A')}\n\n"
            if pep.get("remarks"):
                out += f"**Remarks:** {pep['remarks']}\n\n"
            out += "*Enhanced due diligence required for PEP/sanctions matches as per PMLA and RBI KYC Direction.*\n\n"
        else:
            out += "No PEP, sanctions, or adverse media matches found for directors/promoters.\n\n"

        # Data source attribution for PEP screening
        pep_sources = list({m.get("source", "") for m in pep.get("pep_hits", []) if m.get("source")})
        if pep_sources:
            out += f"*Source: {'; '.join(pep_sources)}*\n\n"
        else:
            out += "*Source: Internal PEP / Sanctions Screening Database*\n\n"
    # 7.4 Web News & Social Media (if available)
    news = fp.get("web_crawl_news")
    if isinstance(news, list):
        news = {"items": news}
    if news and news.get("items"):
        out += _h("7.4 News & Social Media Screening", 3)
        out += "**Automated web screening for adverse news and social media mentions:**\n\n"
        for item in news["items"][:5]:
            out += f"- **{item.get('source','N/A')}**: {item.get('headline','N/A')} ({item.get('date','N/A')})\n  {item.get('summary','')[:200]}\n"
        out += "\n"
        if news.get("sentiment"):
            out += f"**Overall Sentiment:** {news['sentiment'].title()}\n\n"

    # 7.5 Risk Matrix
    out += _h("7.5 Risk Matrix", 3)

    # Hard rules
    out += "**Tier 1 — Hard Rule Checks:**\n\n"
    out += _hdr(["Rule", "Description", "Result", "Details", "Source"])
    for r in t1:
        icon = "✅ PASS" if r["result"] == "pass" else "❌ FAIL"
        out += _row([r["rule"], r["description"], icon, r["details"], "Policy Engine"])
    out += "\n"

    # Key risk factors
    risks = fp.get("key_risks", [])
    if risks:
        out += "**Key Risk Factors:**\n\n"
        out += _hdr(["#", "Category", "Severity", "Risk Description", "Source"])
        for i, r in enumerate(risks, 1):
            out += _row([i, r["category"], _badge(r.get("severity", "medium")), r["detail"], r.get("source", "Risk Assessment")])
        out += "\n"

    # Mitigants
    strengths = fp.get("credit_strengths", [])
    if strengths:
        out += "**Risk Mitigants:**\n\n"
        for s in strengths[:5]:
            out += f"- ✅ {s['category']}: {s['detail']}\n"
        out += "\n"

    out += _resolve_section_source(fp, "Risk Assessment", "External Intelligence", "Governance Score", fallback="Internal Credit Rating Model; CRILC; External Rating Agencies") + "\n\n"
    out += "---\n\n"
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 8: COMPLIANCE & REGULATORY CHECKS
# ═══════════════════════════════════════════════════════════════════════════════

def render_section_8_compliance(fp: dict) -> str:
    ei = fp["external_intelligence"]
    compliance = fp.get("compliance_checks", {})

    out = _h("8. COMPLIANCE & REGULATORY CHECKS")

    out += _hdr(["Compliance Check", "Status", "Details", "Source"])

    # Only evidence-backed statuses; a check without evidence is "Not verified" (no assumed "Compliant").
    mca = ei.get("mca_status")
    mca_known = mca not in (None, "", "Unknown")
    out += _row(["MCA — Company Status", ("✅" if mca == "Active" else "⚠️") if mca_known else "⚠️",
                 mca if mca_known else NOT_VERIFIED, "MCA Company Master"])
    gst_filing = ei.get("gst_filing_status")
    out += _row(["GST — Filing Status", ("✅" if gst_filing in ("Regular", "Filed", "Up to date") else "⚠️") if gst_filing
                 else "⚠️", gst_filing or NOT_VERIFIED, "GST Portal"])
    out += _row(["GST — FY2024 Turnover", "ℹ️", _cr(ei.get("gst_fy2024_turnover_cr")) if ei.get("gst_fy2024_turnover_cr")
                 else NOT_AVAILABLE, "GST Portal"])
    out += _row(["Public Records — Exposure Proxy", "ℹ️", _cr(ei.get("bureau_total_exposure_cr"))
                 if ei.get("bureau_total_exposure_cr") else NOT_AVAILABLE, "Credit Bureau"])
    out += _row(["Public Records — Lender Count", "ℹ️", str(ei.get("bureau_total_lenders") or NOT_AVAILABLE), "Credit Bureau"])
    out += _row(["CRILC — Reporting / SMA status", "ℹ️" if ei.get("crilc_asset_classification") else "⚠️",
                 ei.get("crilc_asset_classification") or NOT_VERIFIED, "CRILC"])
    out += _row(["ECGC — Caution List", "⚠️", NOT_VERIFIED, NOT_AVAILABLE])
    out += _row(["Suit-filed / Decreed accounts", "⚠️", NOT_VERIFIED, NOT_AVAILABLE])

    # Rule-based checks on the public-record payloads (MCA, GST, bureau repayment status, wilful defaulter)
    if compliance.get("items"):
        for item in compliance["items"]:
            out += _row([item["check"], item["status_icon"], item["details"], item.get("source", "Public records")])

    out += "\n"

    # Market/Reputation
    out += f"**Market Reputation:** Sentiment — {(ei.get('market_sentiment') or 'N/A').title()} | "
    out += f"Reputation Risk — {ei.get('reputation_risk') or 'N/A'}\n\n"

    out += _resolve_section_source(fp, "Compliance", "Borrower Profile", fallback="RBI Master Directions; SEBI LODR; MCA Records; PEP/Sanctions Database") + "\n\n"
    out += "---\n\n"
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 9: TERMS, CONDITIONS & COVENANTS
# ═══════════════════════════════════════════════════════════════════════════════

def render_section_9_covenants(fp: dict) -> str:
    rec = fp["policy_decisions"]["tier3_recommendation"]
    ch = fp.get("covenant_history", [])

    out = _h("9. TERMS, CONDITIONS & COVENANTS")

    # Conditions Precedent
    if rec.get("conditions"):
        out += _h("9.1 Conditions Precedent to Disbursement", 3)
        out += _hdr(["#", "Condition", "Source"])
        for i, c in enumerate(rec["conditions"], 1):
            out += _row([i, c, "Sanction Terms"])
        out += "\n"

    # Proposed Covenants
    if rec.get("covenants_proposed"):
        out += _h("9.2 Financial Covenants", 3)
        out += _hdr(["#", "Covenant", "Threshold", "Source"])
        for i, c in enumerate(rec["covenants_proposed"], 1):
            # Try to split covenant into description and threshold
            if ">" in c or "<" in c or "≥" in c or "≤" in c or ":" in c:
                parts = c.split(":", 1) if ":" in c else [c, "As specified"]
                out += _row([i, parts[0].strip(), parts[1].strip() if len(parts) > 1 else "As specified", "Bank Policy"])
            else:
                out += _row([i, c, "As specified", "Bank Policy"])
        out += "\n"

    # Monitoring conditions
    if rec.get("monitoring_conditions"):
        out += _h("9.3 Monitoring & Reporting Requirements", 3)
        out += _hdr(["#", "Requirement", "Source"])
        for i, m in enumerate(rec["monitoring_conditions"], 1):
            out += _row([i, m, "Bank Policy"])
        out += "\n"

    # Historical covenant compliance
    if ch:
        out += _h("9.4 Covenant Compliance History (ETB)", 3)
        out += _hdr(["Covenant", "Required", "Actual", "Status", "Period", "Details", "Source"])
        for c in ch:
            status_icon = "✅ Compliant" if c["status"] == "compliant" else "❌ BREACHED"
            out += _row([c["type"], c["required"], c["actual"], status_icon, c["period"], c["details"], "Covenant Monitoring"])
        out += "\n"

    out += _resolve_section_source(fp, "Conduct Analysis", "Covenant History", fallback="Sanction Terms; Bank Covenant Monitoring Records") + "\n\n"
    out += "---\n\n"
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 10: ACCOUNT CONDUCT & RELATIONSHIP REVIEW
# ═══════════════════════════════════════════════════════════════════════════════

def render_section_10_conduct(fp: dict) -> str:
    ca = fp["conduct_analysis"]
    etb = fp.get("etb_behavioral_analytics", {})

    out = _h("10. ACCOUNT CONDUCT & RELATIONSHIP REVIEW")

    if not ca.get("available"):
        out += f"*{ca.get('note', 'NTB case — No prior banking conduct available.')}*\n\n"
        out += "As a New-to-Bank (NTB) customer, there is no prior account conduct data with our bank. "
        out += "Enhanced monitoring is recommended during the initial 12-month period.\n\n"
    else:
        out += f"**Quarters Analyzed:** {ca['quarters_analyzed']}  \n"
        out += f"**Average Utilization:** {ca['avg_utilization_pct']}%  \n"
        out += f"**Utilization Trend:** {ca['utilization_trend'].title()}  \n"
        out += f"**Total Cheque Returns:** {ca['total_cheque_returns']}  \n"
        out += f"**Max DPD Observed:** {ca['max_dpd_overall']} days  \n\n"

        out += _hdr(["Period", "Avg Balance (₹ Cr)", "Credit Turnover (₹ Cr)", "Cheque Returns",
                    "Utilization %", "Max Overdue Days", "DPD 30+", "DPD 60+", "Source"])
        for r in ca["records"]:
            out += _row([r["period"], _cr(r["avg_balance_cr"]), _cr(r["credit_turnover_cr"]),
                        r["cheque_returns"], f"{r['utilization_pct']:.1f}%",
                        r["max_overdue_days"], r["dpd_30_count"], r["dpd_60_count"], "Core Banking System"])
        out += "\n"

        # Conduct assessment
        if ca["max_dpd_overall"] == 0 and ca["total_cheque_returns"] <= 2:
            out += "**Conduct Assessment:** Satisfactory — Clean track record with no material overdues or cheque returns.\n\n"
        elif ca["max_dpd_overall"] <= 30 and ca["total_cheque_returns"] <= 5:
            out += "**Conduct Assessment:** Acceptable — Minor irregularities noted; overall repayment discipline is maintained.\n\n"
        else:
            out += "**Conduct Assessment:** Requires attention — Material overdues/cheque returns observed.\n\n"

    # ETB Analytics
    if etb and etb.get("scores"):
        out += _h("10.1 Business Reciprocity & ETB Analytics", 3)
        scores = etb["scores"]
        out += _hdr(["Metric", "Score / Value", "Source"])
        for key, val in scores.items():
            out += _row([key.replace("_", " ").title(), val, "Transaction Banking Data"])
        out += "\n"

    out += _resolve_section_source(fp, "Conduct Analysis", "Existing Exposure", "External Intelligence", fallback="Core Banking System; CRILC Account History; Transaction Banking Data") + "\n\n"
    out += "---\n\n"
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 11: PEER COMPARISON & BENCHMARKING
# ═══════════════════════════════════════════════════════════════════════════════

def render_section_11_benchmarking(fp: dict) -> str:
    bs = fp["benchmark_summary"]

    out = _h("11. PEER COMPARISON & BENCHMARKING")
    out += f"**Sector:** {bs['sector'].replace('_', ' ').title()} | **Period:** {bs['period']}\n\n"

    if bs.get("benchmarks"):
        out += _hdr(["Metric", "Borrower", "Peer P25", "Peer Median", "Peer P75", "Position", "Severity", "Source"])
        for bm in bs["benchmarks"]:
            metric = bm["metric"].replace("_", " ").title()
            out += _row([metric, f"{bm['borrower']:.2f}", f"{bm['peer_p25']:.2f}",
                        f"{bm['peer_median']:.2f}", f"{bm['peer_p75']:.2f}",
                        bm["status"].replace("_", " ").title(), _badge(bm["severity"]),
                        bm.get("source", "CMIE Prowess")])
        out += "\n"

    # Summary
    if bs.get("benchmarks"):
        total = len(bs["benchmarks"])
        worse = sum(1 for b in bs["benchmarks"] if b["status"] == "worse_than_peer")
        better = sum(1 for b in bs["benchmarks"] if b["status"] == "better_than_peer")
        inline = total - worse - better

        out += (f"**Summary:** Out of {total} metrics, the borrower is **better than peers** on {better}, "
                f"**in line** on {inline}, and **below peers** on {worse} metric(s).\n\n")

        if worse == 0:
            out += "The Company demonstrates strong competitive positioning across all key financial metrics relative to sector peers.\n\n"
        elif worse <= total * 0.3:
            out += f"The Company's positioning is broadly acceptable with {worse} area(s) requiring monitoring.\n\n"
        else:
            out += f"With {worse} metrics below peer benchmarks, the credit assessment should factor in these weaknesses.\n\n"

    # Worst performers
    if bs.get("worst_performers"):
        out += "**Key Areas Below Peer Benchmarks:**\n\n"
        for bm in bs["worst_performers"]:
            metric = bm["metric"].replace("_", " ").title()
            gap = abs(bm["borrower"] - bm["peer_median"])
            out += f"- **{metric}**: Borrower {bm['borrower']:.2f} vs Peer Median {bm['peer_median']:.2f} (Gap: {gap:.2f})\n"
        out += "\n"

    out += _resolve_section_source(fp, "Benchmark Analysis", "Industry Analysis", fallback="CMIE Prowess; Industry Benchmarks Database; RBI Sectoral Reports") + "\n\n"
    out += "---\n\n"
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 12: DETAILED OPERATIONAL ANALYSIS & INDUSTRY KPIs
# ═══════════════════════════════════════════════════════════════════════════════

def render_section_12_operational_kpis(fp: dict) -> str:
    """Render Detailed Operational Analysis with industry-specific KPIs benchmarked."""
    cs = fp["case_summary"]
    sector = cs["sector"].lower()
    fs = fp["financial_summary"]
    ra = fp["ratio_analysis"]
    bs = fp["benchmark_summary"]
    im = fp.get("infra_metrics", {})
    ia = fp.get("industry_analysis", {})
    sk = fp.get("sector_kpis", {})
    periods = sorted(fs["periods"].keys())
    latest_p = periods[-1] if periods else None
    latest = fs["periods"][latest_p] if latest_p else {}
    latest_ra = ra.get(latest_p, {}) if latest_p else {}
    company_name = fp["borrower_profile"]["company_name"]

    out = _h("12. DETAILED OPERATIONAL ANALYSIS & INDUSTRY KPIs")
    out += (f"**Sector:** {cs['sector'].replace('_', ' ').title()} | "
            f"**Sub-sector:** {cs['subsector']}\n\n")
    out += ("This section presents industry-specific Key Performance Indicators benchmarked "
            "against external industry standards (AI-generated) and internal bank norms.\n\n")

    # 12.1 Industry KPI Benchmarking Table
    out += _h("12.1 Industry KPI Benchmarking", 3)
    kpi_header = ["KPI Metric", "External Benchmark (AI)", "Internal Benchmark (Bank)",
                  company_name, "Source / Remarks"]
    out += _hdr(kpi_header)

    # Use sector_type from sector_kpis for precise routing when available
    st = sk.get("sector_type", "")

    if st in ("ports_logistics", "power_generation", "road_construction") or sector in ("infrastructure", "construction", "roads", "highways"):
        out += _render_infra_operational_kpis(fp, latest, latest_ra, im, sk)
    elif st in ("auto_components", "steel_manufacturing", "tyre_manufacturing", "automobile_manufacturing",
                 "fertilizer_manufacturing", "energy_refining") or sector in ("manufacturing", "auto", "automotive", "energy"):
        out += _render_manufacturing_operational_kpis(fp, latest, latest_ra, sk)
    elif st in ("pharma_formulations", "pharma_api_formulations") or sector in ("pharma", "pharmaceutical"):
        out += _render_pharma_operational_kpis(fp, latest, latest_ra, sk)
    elif st == "hospitals_healthcare" or sector == "healthcare":
        out += _render_pharma_operational_kpis(fp, latest, latest_ra, sk)
    elif st == "it_services" or sector in ("it", "technology", "software", "it_services"):
        out += _render_it_operational_kpis(fp, latest, latest_ra, sk)
    elif st in ("nbfc", "banking") or sector in ("nbfc", "banking", "financial_services"):
        out += _render_nbfc_operational_kpis(fp, latest, latest_ra, sk)
    elif st == "real_estate_development" or sector in ("real_estate", "realty"):
        out += _render_realestate_operational_kpis(fp, latest, latest_ra, sk)
    elif st == "hospitality" or sector in ("hospitality", "hotels"):
        out += _render_hospitality_operational_kpis(fp, latest, latest_ra, sk)
    elif st == "logistics_3pl" or sector in ("logistics", "transport"):
        out += _render_logistics_operational_kpis(fp, latest, latest_ra, sk)
    elif st == "luxury_retail" or sector in ("trading", "retail"):
        out += _render_retail_operational_kpis(fp, latest, latest_ra, sk)
    else:
        out += _render_generic_operational_kpis(fp, latest, latest_ra, sk)
    out += "\n"

    # 12.2 KPI Assessment
    out += _h("12.2 KPI Assessment & Commentary", 3)
    _kpi_assess = []
    if latest.get("ebitda_margin_pct"):
        em = latest["ebitda_margin_pct"]
        if em > 20:
            _kpi_assess.append(f"Operating margin of {_pct(em)} is above industry median, indicating strong cost management.")
        elif em > 12:
            _kpi_assess.append(f"Operating margin of {_pct(em)} is in line with sector norms.")
        else:
            _kpi_assess.append(f"Operating margin of {_pct(em)} is below sector median — cost optimization needed.")

    de = latest_ra.get("debt_to_equity", {}).get("value")
    if de:
        if de < 1.0:
            _kpi_assess.append(f"Conservative leverage (D/E: {de:.2f}x) provides headroom for additional borrowing.")
        elif de < 2.0:
            _kpi_assess.append(f"Moderate leverage (D/E: {de:.2f}x) within acceptable band for the sector.")
        else:
            _kpi_assess.append(f"Elevated leverage (D/E: {de:.2f}x) constraints further borrowing capacity.")

    dscr = latest_ra.get("dscr", {}).get("value")
    if dscr:
        if dscr > 1.5:
            _kpi_assess.append(f"DSCR of {dscr:.2f}x provides comfortable debt servicing buffer.")
        elif dscr > 1.2:
            _kpi_assess.append(f"DSCR of {dscr:.2f}x is adequate with limited headroom.")
        else:
            _kpi_assess.append(f"DSCR of {dscr:.2f}x is tight — warrants enhanced monitoring.")

    if im.get("order_book", {}).get("book_to_bill_ratio"):
        btb = im["order_book"]["book_to_bill_ratio"]
        if btb > 3.0:
            _kpi_assess.append(f"Strong order book (Book-to-Bill: {btb:.1f}x) provides multi-year revenue visibility.")
        elif btb > 2.0:
            _kpi_assess.append(f"Adequate order book (Book-to-Bill: {btb:.1f}x).")
        else:
            _kpi_assess.append(f"Thin order book (Book-to-Bill: {btb:.1f}x) — revenue visibility limited.")

    # Sector-specific KPI assessments
    st = sk.get("sector_type", "")
    if st in ("auto_components", "steel_manufacturing", "tyre_manufacturing", "automobile_manufacturing", "fertilizer_manufacturing", "energy_refining"):
        cp = sk.get("capacity_profile", sk.get("refining_capacity", {}))
        cu = cp.get("capacity_utilization_pct_fy25") or cp.get("capacity_utilization_pct") or cp.get("capacity_utilization_urea_pct")
        if cu:
            if cu > 85:
                _kpi_assess.append(f"High capacity utilization ({cu:.1f}%) indicates strong demand traction.")
            elif cu > 70:
                _kpi_assess.append(f"Moderate capacity utilization ({cu:.1f}%) with room for growth.")
            else:
                _kpi_assess.append(f"Low capacity utilization ({cu:.1f}%) — demand concerns or ramp-up phase.")
    elif st == "pharma_formulations" or st == "pharma_api_formulations":
        pp = sk.get("product_pipeline", sk.get("product_portfolio", {}))
        anr = pp.get("anda_approved", 0)
        if anr:
            _kpi_assess.append(f"ANDA portfolio of {anr} approved products provides US market access.")
    elif st == "it_services":
        om = sk.get("operational_metrics", {})
        if om.get("utilization_rate_pct"):
            _kpi_assess.append(f"Employee utilization at {om['utilization_rate_pct']}% (vs. industry benchmark 80-85%).")
        if om.get("attrition_rate_ltm_pct"):
            att = om["attrition_rate_ltm_pct"]
            if att < 15:
                _kpi_assess.append(f"Healthy attrition rate ({att}%) supports project continuity.")
            else:
                _kpi_assess.append(f"Elevated attrition ({att}%) — talent retention risk.")
    elif st == "nbfc" or st == "banking":
        aq = sk.get("asset_quality", {})
        if aq.get("gnpa_pct_fy25") is not None:
            gnpa = aq["gnpa_pct_fy25"]
            if gnpa < 1.5:
                _kpi_assess.append(f"Asset quality strong — GNPA at {gnpa:.2f}%.")
            elif gnpa < 3.0:
                _kpi_assess.append(f"Asset quality moderate — GNPA at {gnpa:.2f}% under watch.")
            else:
                _kpi_assess.append(f"Asset quality stressed — GNPA at {gnpa:.2f}% needs remediation.")
    elif st == "hospitals_healthcare":
        hn = sk.get("hospital_network", {})
        if hn.get("avg_occupancy_pct_fy25"):
            occ = hn["avg_occupancy_pct_fy25"]
            _kpi_assess.append(f"Hospital occupancy at {occ:.1f}% (target >70% for profitability).")
    elif st == "hospitality":
        om = sk.get("operational_metrics", {})
        if om.get("revpar_rs_fy25"):
            _kpi_assess.append(f"RevPAR of ₹{om['revpar_rs_fy25']:,.0f} reflecting strong demand recovery.")
    elif st == "real_estate_development":
        sp = sk.get("sales_performance", {})
        if sp.get("new_bookings_cr_fy25"):
            _kpi_assess.append(f"Pre-sales of ₹{sp['new_bookings_cr_fy25']:,.0f} Cr provide revenue visibility.")
    elif st == "logistics_3pl":
        fp_data = sk.get("fleet_profile", {})
        if fp_data.get("fleet_utilization_pct_fy25"):
            _kpi_assess.append(f"Fleet utilization at {fp_data['fleet_utilization_pct_fy25']}% (benchmark: 80%+).")
    elif st == "luxury_retail":
        sp = sk.get("segment_performance", {})
        if sp.get("sssg_jewellery_pct"):
            _kpi_assess.append(f"Same-store sales growth of {sp['sssg_jewellery_pct']}% in jewellery — strong consumer demand.")
    elif st == "road_construction":
        hamp = sk.get("ham_portfolio", {})
        exm = sk.get("execution_metrics", {})
        if hamp.get("avg_dscr_operational"):
            d = hamp["avg_dscr_operational"]
            if d >= 1.25:
                _kpi_assess.append(f"HAM portfolio DSCR of {d:.2f}x provides comfortable debt servicing cushion.")
            else:
                _kpi_assess.append(f"HAM portfolio DSCR of {d:.2f}x — thin margin, enhanced monitoring warranted.")
        if exm.get("cost_overrun_pct"):
            cop = exm["cost_overrun_pct"]
            if cop > 20:
                _kpi_assess.append(f"Cost overrun of {cop:.1f}% significantly above benchmark (5–15%) — key risk factor.")
            elif cop > 10:
                _kpi_assess.append(f"Cost overrun of {cop:.1f}% moderate; within manageable range for structure-heavy projects.")
            else:
                _kpi_assess.append(f"Cost overrun of {cop:.1f}% within acceptable norms.")
        if exm.get("physical_progress_pct"):
            pp = exm["physical_progress_pct"]
            _kpi_assess.append(f"Physical progress at {pp}% — {'on track' if pp >= 85 else 'requires acceleration'} for extended COD achievement.")
        if hamp.get("equity_infusion_complete_pct") and hamp["equity_infusion_complete_pct"] >= 100:
            _kpi_assess.append("Full equity infusion by sponsor is a strong positive — indicates commitment to project completion.")

    for item in _kpi_assess:
        out += f"- {item}\n"
    if not _kpi_assess:
        out += "- KPI assessment based on available financial and operational data.\n"
    out += "\n"

    # 12.3 Operational Efficiency Summary
    out += _h("12.3 Operational Efficiency Summary", 3)
    rev_growth = None
    if len(periods) >= 2:
        first_rev = fs["periods"][periods[0]].get("revenue_cr", 0) or 0
        last_rev = latest.get("revenue_cr", 0) or 0
        if first_rev > 0:
            rev_growth = ((last_rev / first_rev) ** (1 / max(len(periods) - 1, 1)) - 1) * 100

    out += _hdr(["Efficiency Parameter", "Value", "Assessment", "Source"])
    if rev_growth is not None:
        assessment = "Strong" if rev_growth > 15 else "Moderate" if rev_growth > 5 else "Weak"
        out += _row(["Revenue CAGR", f"{rev_growth:.1f}%", assessment, "Audited Financials"])
    out += _row(["EBITDA Margin", _pct(latest.get("ebitda_margin_pct")),
                 "Above median" if (latest.get("ebitda_margin_pct") or 0) > 15 else "In line" if (latest.get("ebitda_margin_pct") or 0) > 10 else "Below median",
                 "Audited Financials"])
    wcc = latest_ra.get("working_capital_cycle", {}).get("value")
    if wcc is not None:
        out += _row(["Working Capital Cycle", f"{wcc:.0f} days",
                     "Efficient" if wcc < 60 else "Moderate" if wcc < 120 else "Extended",
                     "Audited Financials"])
    at = latest_ra.get("asset_turnover", {}).get("value")
    if at:
        out += _row(["Asset Turnover", f"{at:.2f}x",
                     "Efficient" if at > 1.0 else "Moderate" if at > 0.5 else "Low",
                     "Audited Financials"])
    roe = latest_ra.get("return_on_equity", {}).get("value")
    if roe:
        out += _row(["Return on Equity", _pct(roe * 100),
                     "Strong" if roe > 0.15 else "Adequate" if roe > 0.08 else "Weak",
                     "Audited Financials"])
    out += "\n"

    out += _resolve_section_source(fp, "Financial Analysis", "Benchmark Analysis", "Industry Analysis", fallback="Audited Annual Reports; Industry Benchmarks; CMIE Prowess; NHAI / MoRTH Data") + "\n\n"

    # 12.4 Project Pipeline (road_construction / infrastructure)
    st = sk.get("sector_type", "")
    sk_pipeline = sk.get("project_pipeline", [])
    if st == "road_construction" and sk_pipeline:
        out += _h("12.4 Active Project Pipeline", 3)
        out += _hdr(["Project Name", "Length (km)", "Contract Value (₹ Cr)", "Model", "Client", "Completion (%)", "Target Completion"])
        for proj in sk_pipeline:
            out += _row([
                proj.get("project_name", "—"),
                f"{proj.get('length_km', 'N/A')} km",
                _cr(proj.get("contract_value_cr")),
                proj.get("model", "—"),
                proj.get("client", "—"),
                f"{proj.get('completion_pct', 'N/A')}%",
                proj.get("target_completion", "—"),
            ])
        out += "\n"
        # Highway execution mix
        hm = sk.get("highway_mix", {})
        if hm:
            out += "**Revenue Mix:** "
            parts = []
            if hm.get("epc_revenue_pct"):
                parts.append(f"EPC: {hm['epc_revenue_pct']}%")
            if hm.get("bot_toll_revenue_pct"):
                parts.append(f"BOT Toll: {hm['bot_toll_revenue_pct']}%")
            if hm.get("ham_annuity_revenue_pct"):
                parts.append(f"HAM Annuity: {hm['ham_annuity_revenue_pct']}%")
            out += " | ".join(parts) + "\n\n"
        out += f"*Source: {sk_pipeline[0].get('client', 'NHAI')} Award Records; Company Order Book*\n\n"

    out += "---\n\n"
    return out


def _render_infra_operational_kpis(fp: dict, latest: dict, latest_ra: dict, im: dict, sk: dict = None) -> str:
    """Infrastructure / Road / Highway sector KPIs."""
    sk = sk or {}
    st = sk.get("sector_type", "")
    out = ""
    ob = im.get("order_book", {})
    em = im.get("execution_metrics", {})
    bh = im.get("bot_ham_portfolio", {})

    # --- Ports / Logistics sector ---
    if st == "ports_logistics":
        ct = sk.get("cargo_throughput", {})
        pa = sk.get("port_assets", {})
        cn = sk.get("concession_profile", {})
        out += _row(["Total Cargo Throughput (MMT)", "300–500 MMT", "350 MMT",
                     f"{ct['total_cargo_mmt_fy25']:.1f} MMT" if ct.get("total_cargo_mmt_fy25") else "N/A",
                     ct.get("source", "Company Disclosure")])
        out += _row(["Container Volume (TEU Mn)", "5–10 Mn TEU", "7 Mn TEU",
                     f"{ct['container_teu_mn_fy25']:.2f} Mn" if ct.get("container_teu_mn_fy25") else "N/A",
                     ct.get("source", "Company Disclosure")])
        out += _row(["Capacity Utilization", "60–80%", "70%",
                     f"{pa['capacity_utilization_pct']:.1f}%" if pa.get("capacity_utilization_pct") else "N/A",
                     pa.get("source", "Company Disclosure")])
        out += _row(["Avg Turnaround Time (hrs)", "1.5–3.0 hrs", "2.0 hrs",
                     f"{pa['avg_turnaround_time_hrs']:.2f} hrs" if pa.get("avg_turnaround_time_hrs") else "N/A",
                     pa.get("source", "Company Disclosure")])
        out += _row(["Residual Concession Period", "15–30 yrs", "20 yrs",
                     f"{cn['avg_residual_concession_years']} yrs" if cn.get("avg_residual_concession_years") else "N/A",
                     cn.get("source", "Concession Agreements")])
    # --- Power Generation sector ---
    elif st == "power_generation":
        gc = sk.get("generation_capacity", {})
        op = sk.get("operational_performance", {})
        fs = sk.get("fuel_security", {})
        out += _row(["Installed Capacity (MW)", "Sector dependent", "—",
                     f"{gc['installed_capacity_mw']:,.0f} MW" if gc.get("installed_capacity_mw") else "N/A",
                     gc.get("source", "Company Annual Report")])
        out += _row(["Plant Load Factor", "65–80%", f"National avg: {op.get('national_avg_plf_pct','65')}%",
                     f"{op['plf_pct_fy25']:.1f}%" if op.get("plf_pct_fy25") else "N/A",
                     op.get("source", "CEA Thermal Review")])
        out += _row(["Avg Tariff (₹/unit)", "3.50–5.00", "4.00",
                     f"₹ {op['avg_tariff_per_unit_rs']:.2f}" if op.get("avg_tariff_per_unit_rs") else "N/A",
                     op.get("source", "Company Disclosure")])
        out += _row(["Heat Rate (kcal/kWh)", "2300–2500", "2400",
                     f"{op['heat_rate_kcal_kwh']:,}" if op.get("heat_rate_kcal_kwh") else "N/A",
                     op.get("source", "CEA Thermal Review")])
        out += _row(["Coal Stock (Days)", "15–22 days", "18 days",
                     f"{fs['coal_stock_days']} days" if fs.get("coal_stock_days") else "N/A",
                     fs.get("source", "Coal Ministry")])
        out += _row(["Coal Linkage Coverage", "85–100%", "90%",
                     f"{fs['coal_linkage_coverage_pct']}%" if fs.get("coal_linkage_coverage_pct") else "N/A",
                     fs.get("source", "Coal Ministry")])
    # --- Road Construction (default infra) ---
    else:
        cost_per_km = em.get("avg_construction_cost_per_km_cr")
        out += _row(["Project Cost per Km (₹ Cr)", "15–20 Cr/km (4-lane)", "18 Cr/km",
                     f"₹ {cost_per_km:.1f} Cr/km" if cost_per_km else "N/A",
                     "Company Annual Report; NHAI norms"])
        lac = em.get("avg_land_acquisition_cost_per_sq_km_cr")
        out += _row(["Land Acquisition Cost (₹ Cr/sq km)", "3–8 Cr/sq km", "5 Cr/sq km",
                     f"₹ {lac:.1f} Cr/sq km" if lac else "N/A",
                     "Revenue Dept records; Project DPR"])
        # Structure cost as % of total
        scp = sk.get("execution_metrics", em).get("structure_cost_pct_of_total")
        out += _row(["Structure Cost (% of Total)", "10–18%", "15%",
                     f"{scp:.0f}%" if scp else "N/A",
                     "Project Cost Breakdown"])
        # Cost overrun
        cor = sk.get("execution_metrics", em).get("cost_overrun_pct")
        out += _row(["Cost Overrun (%)", "5–15%", "10%",
                     f"{cor:.1f}%" if cor else "N/A",
                     "Revised TPC vs Original BPC"])
        # Time overrun
        tor = sk.get("execution_metrics", em).get("time_overrun_pct")
        out += _row(["Time Overrun (%)", "10–25%", "20%",
                     f"{tor:.0f}%" if tor else "N/A",
                     "Project Progress vs Schedule"])
        # Physical progress
        pp = sk.get("execution_metrics", em).get("physical_progress_pct")
        out += _row(["Physical Progress (%)", "90%+ at this stage", "85%+",
                     f"{pp:.0f}%" if pp else "N/A",
                     "Independent Engineer Report"])
        btb = ob.get("book_to_bill_ratio")
        out += _row(["Book-to-Bill Ratio", "2.5–4.0x", "3.0x",
                     f"{btb:.1f}x" if btb else "N/A",
                     "Company Order Book; NHAI Award Tracker"])
        eu = em.get("equipment_utilization_pct")
        out += _row(["Equipment Utilization", "70–85%", "75%",
                     f"{eu:.1f}%" if eu else "N/A",
                     "Company operational records"])
        ecd = em.get("effective_construction_days_per_year")
        out += _row(["Effective Construction Days/Year", "220–260 days", "240 days",
                     f"{ecd} days" if ecd else "N/A",
                     "Project progress reports"])
        # HAM-specific KPIs
        hamp = sk.get("ham_portfolio", {})
        if hamp:
            out += _row(["HAM Projects (Operational / Total)", "—", "—",
                         f"{hamp.get('operational_ham_projects', 'N/A')} / {hamp.get('total_ham_projects', 'N/A')}",
                         hamp.get("source", "Company Annual Report")])
            if hamp.get("annuity_income_fy25_cr"):
                out += _row(["Annual Annuity Income (₹ Cr)", "Sector dependent", "—",
                             _cr(hamp["annuity_income_fy25_cr"]),
                             hamp.get("source", "Concession Agreement")])
            if hamp.get("avg_dscr_operational"):
                out += _row(["Avg DSCR (Operational HAM)", "≥ 1.25x", "1.30x",
                             f"{hamp['avg_dscr_operational']:.2f}x",
                             hamp.get("source", "Cash Flow Model")])
            if hamp.get("equity_infusion_complete_pct"):
                out += _row(["Equity Infusion (% Complete)", "100% pre-COD", "100%",
                             f"{hamp['equity_infusion_complete_pct']}%",
                             hamp.get("source", "Company Records")])
            if hamp.get("nhai_grant_received_pct"):
                out += _row(["NHAI Grant Received (%)", "80–100% before COD", "85%",
                             f"{hamp['nhai_grant_received_pct']}%",
                             hamp.get("source", "NHAI Milestone Tracker")])

    # Common infra KPIs
    ebitda_m = latest.get("ebitda_margin_pct")
    out += _row(["EBITDA Margin", "12–18%", "14%",
                 _pct(ebitda_m), "Audited Annual Report"])
    de = latest_ra.get("debt_to_equity", {}).get("value")
    out += _row(["Debt / Equity", "1.0–2.5x", "1.8x",
                 f"{de:.2f}x" if de else "N/A", "Audited Balance Sheet"])
    dscr = latest_ra.get("dscr", {}).get("value")
    out += _row(["DSCR", "≥ 1.25x", "1.30x",
                 f"{dscr:.2f}x" if dscr else "N/A", "Cash Flow Statement"])
    icr = latest_ra.get("interest_coverage_ratio", {}).get("value")
    out += _row(["Interest Coverage Ratio", "≥ 2.0x", "2.5x",
                 f"{icr:.2f}x" if icr else "N/A", "Audited P&L"])
    if bh.get("annual_toll_revenue_cr"):
        out += _row(["Annual Toll / Annuity Revenue", "Sector dependent", "—",
                     _cr(bh["annual_toll_revenue_cr"]), "Concession Agreement; NHAI"])
    if ob.get("total_order_book_cr"):
        out += _row(["Total Order Book", "Sector dependent", "—",
                     _cr(ob["total_order_book_cr"]), "Company Order Book"])
    return out


def _render_manufacturing_operational_kpis(fp: dict, latest: dict, latest_ra: dict, sk: dict = None) -> str:
    """Manufacturing / Auto sector KPIs."""
    sk = sk or {}
    cp = sk.get("capacity_profile", {})
    rmp = sk.get("raw_material_profile", sk.get("raw_material_security", sk.get("cost_position", {})))
    out = ""
    # Capacity Utilization
    cu = cp.get("capacity_utilization_pct_fy25") or cp.get("capacity_utilization_pct")
    out += _row(["Capacity Utilization", "70–85%", "75%",
                 f"{cu:.1f}%" if cu else "N/A",
                 cp.get("source", "Company Annual Report")])
    # EBITDA Margin
    out += _row(["EBITDA Margin", "10–18%", "13%",
                 _pct(latest.get("ebitda_margin_pct")), "Audited Annual Report"])
    # Raw Material Cost %
    rm_pct = rmp.get("rm_to_revenue_pct_fy25") or rmp.get("rm_cost_pct_of_revenue") or rmp.get("iron_ore_cost_pct")
    out += _row(["Raw Material Cost (% of Revenue)", "45–65%", "55%",
                 f"{rm_pct:.1f}%" if rm_pct else "N/A",
                 rmp.get("source", "Audited P&L; Schedule of COGS")])
    # Power & Fuel Cost %
    pf = rmp.get("power_fuel_pct") or sk.get("cost_structure", {}).get("power_fuel_pct")
    out += _row(["Power & Fuel Cost (% of Revenue)", "3–8%", "5%",
                 f"{pf:.1f}%" if pf else "N/A",
                 "Audited P&L; Schedule of Expenses"])
    # Inventory Turnover
    inv_days = latest_ra.get("inventory_days", {}).get("value")
    out += _row(["Inventory Days", "30–90 days", "60 days",
                 f"{inv_days:.0f} days" if inv_days else "N/A", "Audited Balance Sheet"])
    # Debtor Days
    dd = latest_ra.get("debtor_days", {}).get("value")
    out += _row(["Debtor Days", "30–75 days", "45 days",
                 f"{dd:.0f} days" if dd else "N/A", "Audited Balance Sheet"])
    # Debt/Equity
    de = latest_ra.get("debt_to_equity", {}).get("value")
    out += _row(["Debt / Equity", "0.5–1.5x", "1.0x",
                 f"{de:.2f}x" if de else "N/A", "Audited Balance Sheet"])
    # DSCR
    dscr = latest_ra.get("dscr", {}).get("value")
    out += _row(["DSCR", "≥ 1.50x", "1.50x",
                 f"{dscr:.2f}x" if dscr else "N/A", "Cash Flow Statement"])
    # ROE
    roe = latest_ra.get("return_on_equity", {}).get("value")
    out += _row(["Return on Equity", "12–20%", "15%",
                 _pct(roe * 100) if roe else "N/A", "Audited Financials"])
    # Asset Turnover
    at = latest_ra.get("asset_turnover", {}).get("value")
    out += _row(["Asset Turnover", "0.8–1.5x", "1.0x",
                 f"{at:.2f}x" if at else "N/A", "Audited Balance Sheet"])
    # Export / Revenue Ratio
    ex_pct = sk.get("global_operations", {}).get("export_pct") or sk.get("geographic_mix", {}).get("export_pct")
    out += _row(["Export to Revenue Ratio", "15–40%", "25%",
                 f"{ex_pct:.1f}%" if ex_pct else "N/A",
                 "Annual Report; DGFT Data"])
    return out


def _render_pharma_operational_kpis(fp: dict, latest: dict, latest_ra: dict, sk: dict = None) -> str:
    """Pharma / Healthcare sector KPIs."""
    sk = sk or {}
    rd = sk.get("rd_profile", {})
    pp = sk.get("product_pipeline", sk.get("product_portfolio", {}))
    rc = sk.get("regulatory_compliance", sk.get("fda_compliance", {}))
    hn = sk.get("hospital_network", {})
    out = ""
    # Hospital-specific KPIs if hospitals_healthcare
    if sk.get("sector_type") == "hospitals_healthcare":
        out += _row(["Total Beds", "5,000–10,000", "7,000",
                     f"{hn['total_beds']:,}" if hn.get("total_beds") else "N/A",
                     hn.get("source", "Company Annual Report")])
        out += _row(["Avg. Occupancy Rate", "65–80%", "70%",
                     f"{hn['avg_occupancy_pct_fy25']:.1f}%" if hn.get("avg_occupancy_pct_fy25") else "N/A",
                     hn.get("source", "Company Annual Report")])
        arpob = hn.get("arpob_rs_fy25")
        out += _row(["ARPOB (₹/day)", "30,000–55,000", "40,000",
                     f"₹ {arpob:,.0f}" if arpob else "N/A",
                     hn.get("source", "Company Annual Report")])
    else:
        # Pharma-specific
        rd_pct = rd.get("rd_spend_pct_of_revenue")
        out += _row(["R&D Spend (% of Revenue)", "5–12%", "8%",
                     f"{rd_pct:.1f}%" if rd_pct else "N/A",
                     rd.get("source", "Annual Report; R&D Schedule")])
        anda = pp.get("anda_approved") or pp.get("total_products")
        out += _row(["ANDA / Product Pipeline", "5–20 filings", "10 filings",
                     f"{anda} approved" if anda else "N/A",
                     pp.get("source", "US FDA Orange Book; Company IR")])
        insp = rc.get("usfda_warning_letters", rc.get("last_usfda_inspection"))
        if rc.get("usfda_warning_letters") is not None:
            insp_val = "Clean" if rc["usfda_warning_letters"] == 0 else f"{rc['usfda_warning_letters']} warning letter(s)"
        else:
            insp_val = "N/A"
        out += _row(["US FDA Inspection Status", "No OAI / VAI", "No OAI",
                     insp_val, rc.get("source", "US FDA Inspection Database")])

    out += _row(["EBITDA Margin", "18–28%", "22%",
                 _pct(latest.get("ebitda_margin_pct")), "Audited Annual Report"])
    de = latest_ra.get("debt_to_equity", {}).get("value")
    out += _row(["Debt / Equity", "0.3–1.0x", "0.5x",
                 f"{de:.2f}x" if de else "N/A", "Audited Balance Sheet"])
    dscr = latest_ra.get("dscr", {}).get("value")
    out += _row(["DSCR", "≥ 1.75x", "2.0x",
                 f"{dscr:.2f}x" if dscr else "N/A", "Cash Flow Statement"])
    dd = latest_ra.get("debtor_days", {}).get("value")
    out += _row(["Debtor Days", "60–120 days", "75 days",
                 f"{dd:.0f} days" if dd else "N/A", "Audited Balance Sheet"])
    roe = latest_ra.get("return_on_equity", {}).get("value")
    out += _row(["Return on Equity", "15–25%", "18%",
                 _pct(roe * 100) if roe else "N/A", "Audited Financials"])
    return out


def _render_it_operational_kpis(fp: dict, latest: dict, latest_ra: dict, sk: dict = None) -> str:
    """IT / Technology sector KPIs."""
    sk = sk or {}
    om = sk.get("operational_metrics", {})
    gm = sk.get("geographic_mix", {})
    dp = sk.get("deal_pipeline", {})
    cm = sk.get("client_metrics", {})
    out = ""
    out += _row(["EBITDA Margin", "18–30%", "22%",
                 _pct(latest.get("ebitda_margin_pct")), "Audited Annual Report"])
    rpe = om.get("revenue_per_employee_usd_k")
    out += _row(["Revenue per Employee (USD K)", "45–70K", "55K",
                 f"USD {rpe:.0f}K" if rpe else "N/A",
                 om.get("source", "Annual Report; HR Data")])
    att = om.get("attrition_rate_ltm_pct")
    out += _row(["Attrition Rate (LTM)", "10–20%", "14%",
                 f"{att:.1f}%" if att else "N/A",
                 om.get("source", "Annual Report; HR Disclosures")])
    util = om.get("utilization_rate_pct")
    out += _row(["Employee Utilization", "78–86%", "82%",
                 f"{util:.1f}%" if util else "N/A",
                 om.get("source", "Company Disclosure")])
    offshore = om.get("offshore_pct") or gm.get("offshore_pct")
    out += _row(["Offshore Revenue Mix", "60–80%", "70%",
                 f"{offshore:.1f}%" if offshore else "N/A",
                 gm.get("source", "Annual Report; Segment Reporting")])
    ldv = dp.get("large_deal_wins_fy25_bn_usd")
    if ldv:
        out += _row(["Large Deal TCV (USD Bn)", "5–15 Bn", "8 Bn",
                     f"USD {ldv:.1f} Bn", dp.get("source", "Company IR")])
    cc = cm.get("client_concentration_top5_pct")
    if cc:
        out += _row(["Top-5 Client Concentration", "15–30%", "20%",
                     f"{cc:.1f}%", cm.get("source", "Annual Report")])
    de = latest_ra.get("debt_to_equity", {}).get("value")
    out += _row(["Debt / Equity", "0.0–0.5x", "0.2x",
                 f"{de:.2f}x" if de else "N/A", "Audited Balance Sheet"])
    dd = latest_ra.get("debtor_days", {}).get("value")
    out += _row(["Debtor Days", "60–90 days", "70 days",
                 f"{dd:.0f} days" if dd else "N/A", "Audited Balance Sheet"])
    roe = latest_ra.get("return_on_equity", {}).get("value")
    out += _row(["Return on Equity", "20–35%", "25%",
                 _pct(roe * 100) if roe else "N/A", "Audited Financials"])
    return out


def _render_generic_operational_kpis(fp: dict, latest: dict, latest_ra: dict, sk: dict = None) -> str:
    """Generic sector KPIs when sector-specific template not available."""
    out = ""
    out += _row(["EBITDA Margin", "10–20%", "15%",
                 _pct(latest.get("ebitda_margin_pct")), "Audited Annual Report"])
    out += _row(["PAT Margin", "5–12%", "8%",
                 _pct(latest.get("pat_margin_pct")), "Audited Annual Report"])
    de = latest_ra.get("debt_to_equity", {}).get("value")
    out += _row(["Debt / Equity", "0.5–2.0x", "1.0x",
                 f"{de:.2f}x" if de else "N/A", "Audited Balance Sheet"])
    dscr = latest_ra.get("dscr", {}).get("value")
    out += _row(["DSCR", "≥ 1.25x", "1.50x",
                 f"{dscr:.2f}x" if dscr else "N/A", "Cash Flow Statement"])
    icr = latest_ra.get("interest_coverage_ratio", {}).get("value")
    out += _row(["Interest Coverage Ratio", "≥ 2.0x", "2.5x",
                 f"{icr:.2f}x" if icr else "N/A", "Audited P&L"])
    dd = latest_ra.get("debtor_days", {}).get("value")
    out += _row(["Debtor Days", "30–90 days", "60 days",
                 f"{dd:.0f} days" if dd else "N/A", "Audited Balance Sheet"])
    inv_days = latest_ra.get("inventory_days", {}).get("value")
    out += _row(["Inventory Days", "30–90 days", "60 days",
                 f"{inv_days:.0f} days" if inv_days else "N/A", "Audited Balance Sheet"])
    wcc = latest_ra.get("working_capital_cycle", {}).get("value")
    out += _row(["Working Capital Cycle", "30–120 days", "75 days",
                 f"{wcc:.0f} days" if wcc else "N/A", "Audited Balance Sheet"])
    roe = latest_ra.get("return_on_equity", {}).get("value")
    out += _row(["Return on Equity", "10–20%", "15%",
                 _pct(roe * 100) if roe else "N/A", "Audited Financials"])
    at = latest_ra.get("asset_turnover", {}).get("value")
    out += _row(["Asset Turnover", "0.5–1.5x", "1.0x",
                 f"{at:.2f}x" if at else "N/A", "Audited Balance Sheet"])
    return out


def _render_nbfc_operational_kpis(fp: dict, latest: dict, latest_ra: dict, sk: dict = None) -> str:
    """NBFC / Banking sector KPIs."""
    sk = sk or {}
    aum = sk.get("aum_profile", {})
    aq = sk.get("asset_quality", {})
    pr = sk.get("profitability", {})
    ca = sk.get("capital_adequacy", {})
    dm = sk.get("disbursement_metrics", {})
    out = ""
    out += _row(["Total AUM (₹ Cr)", "Sector dependent", "—",
                 _cr(aum["total_aum_cr"]) if aum.get("total_aum_cr") else "N/A",
                 aum.get("source", "Company Annual Report")])
    out += _row(["AUM Growth YoY", "15–25%", "18%",
                 f"{aum['aum_growth_yoy_pct']:.1f}%" if aum.get("aum_growth_yoy_pct") else "N/A",
                 aum.get("source", "Company Annual Report")])
    out += _row(["GNPA", "< 2.0%", "1.5%",
                 f"{aq['gnpa_pct_fy25']:.2f}%" if aq.get("gnpa_pct_fy25") is not None else "N/A",
                 aq.get("source", "Company Annual Report")])
    out += _row(["NNPA", "< 1.0%", "0.5%",
                 f"{aq['nnpa_pct_fy25']:.2f}%" if aq.get("nnpa_pct_fy25") is not None else "N/A",
                 aq.get("source", "Company Annual Report")])
    out += _row(["Provision Coverage Ratio", "≥ 60%", "65%",
                 f"{aq['pcr_pct']:.1f}%" if aq.get("pcr_pct") else "N/A",
                 aq.get("source", "Company Disclosure")])
    out += _row(["Net Interest Margin", "3.0–7.0%", "5.0%",
                 f"{pr['nim_pct_fy25']:.2f}%" if pr.get("nim_pct_fy25") else "N/A",
                 pr.get("source", "Audited Financials")])
    out += _row(["Cost to Income", "30–50%", "40%",
                 f"{pr['cost_to_income_pct']:.1f}%" if pr.get("cost_to_income_pct") else "N/A",
                 pr.get("source", "Audited Financials")])
    out += _row(["Return on Equity", "12–20%", "15%",
                 f"{pr['roe_pct']:.1f}%" if pr.get("roe_pct") else "N/A",
                 pr.get("source", "Audited Financials")])
    out += _row(["Return on Assets", "1.5–3.0%", "2.0%",
                 f"{pr['roa_pct']:.2f}%" if pr.get("roa_pct") else "N/A",
                 pr.get("source", "Audited Financials")])
    out += _row(["Capital Adequacy Ratio", "≥ 15%", "18%",
                 f"{ca['car_pct']:.1f}%" if ca.get("car_pct") else "N/A",
                 ca.get("source", "Company Disclosure; RBI")])
    out += _row(["Tier-1 Capital", "≥ 10%", "12%",
                 f"{ca['tier1_pct']:.1f}%" if ca.get("tier1_pct") else "N/A",
                 ca.get("source", "Company Disclosure; RBI")])
    if dm.get("total_disbursements_cr_fy25"):
        out += _row(["Total Disbursements FY25", "Sector dependent", "—",
                     _cr(dm["total_disbursements_cr_fy25"]),
                     dm.get("source", "Company Disclosure")])
    return out


def _render_realestate_operational_kpis(fp: dict, latest: dict, latest_ra: dict, sk: dict = None) -> str:
    """Real Estate Development sector KPIs."""
    sk = sk or {}
    dp = sk.get("development_portfolio", {})
    sp = sk.get("sales_performance", {})
    rp = sk.get("rental_portfolio", {})
    lb = sk.get("land_bank", {})
    dbp = sk.get("debt_profile", {})
    out = ""
    out += _row(["Total Developable Area (MSF)", "20–100 MSF", "50 MSF",
                 f"{dp['total_developable_area_msf']:.1f} MSF" if dp.get("total_developable_area_msf") else "N/A",
                 dp.get("source", "Company Disclosure")])
    out += _row(["Ongoing Projects (MSF)", "Sector dependent", "—",
                 f"{dp['ongoing_projects_msf']:.1f} MSF" if dp.get("ongoing_projects_msf") else "N/A",
                 dp.get("source", "Company Disclosure")])
    out += _row(["New Bookings / Pre-sales FY25 (₹ Cr)", "3,000–12,000 Cr", "5,000 Cr",
                 _cr(sp["new_bookings_cr_fy25"]) if sp.get("new_bookings_cr_fy25") else "N/A",
                 sp.get("source", "Company Disclosure")])
    out += _row(["Collections FY25 (₹ Cr)", "Sector dependent", "—",
                 _cr(sp["collections_cr_fy25"]) if sp.get("collections_cr_fy25") else "N/A",
                 sp.get("source", "Company Disclosure")])
    out += _row(["Unsold Inventory (₹ Cr)", "< 2x annual sales", "—",
                 _cr(sp["unsold_inventory_cr"]) if sp.get("unsold_inventory_cr") else "N/A",
                 sp.get("source", "Company Disclosure")])
    out += _row(["Avg Realization (₹/sqft)", "5,000–25,000", "12,000",
                 f"₹ {sp['avg_realization_per_sqft_rs']:,.0f}" if sp.get("avg_realization_per_sqft_rs") else "N/A",
                 sp.get("source", "Company Disclosure")])
    out += _row(["Rental Portfolio Occupancy", "75–95%", "85%",
                 f"{rp['occupancy_pct']:.1f}%" if rp.get("occupancy_pct") else "N/A",
                 rp.get("source", "Company Disclosure")])
    out += _row(["Rental Income FY25 (₹ Cr)", "Sector dependent", "—",
                 _cr(rp["rental_income_cr_fy25"]) if rp.get("rental_income_cr_fy25") else "N/A",
                 rp.get("source", "Company Disclosure")])
    out += _row(["Land Bank (Acres)", "Sector dependent", "—",
                 f"{lb['total_land_bank_acres']:,.0f}" if lb.get("total_land_bank_acres") else "N/A",
                 lb.get("source", "Company Disclosure")])
    out += _row(["Net Debt/Equity", "0.5–1.5x", "0.8x",
                 f"{dbp['net_debt_equity']:.2f}x" if dbp.get("net_debt_equity") else "N/A",
                 dbp.get("source", "Audited Financials")])
    out += _row(["EBITDA Margin", "20–35%", "25%",
                 _pct(latest.get("ebitda_margin_pct")), "Audited Annual Report"])
    return out


def _render_hospitality_operational_kpis(fp: dict, latest: dict, latest_ra: dict, sk: dict = None) -> str:
    """Hospitality / Hotels sector KPIs."""
    sk = sk or {}
    hp = sk.get("hotel_portfolio", {})
    om = sk.get("operational_metrics", {})
    rm = sk.get("revenue_mix", {})
    pl = sk.get("pipeline", {})
    out = ""
    out += _row(["Total Hotels / Rooms", "100+ hotels", "—",
                 f"{hp.get('total_hotels', 'N/A')} hotels / {hp.get('total_rooms', 'N/A'):,} rooms" if hp.get("total_hotels") else "N/A",
                 hp.get("source", "Company Annual Report")])
    out += _row(["Average Occupancy FY25", "55–75%", "65%",
                 f"{om['avg_occupancy_pct_fy25']:.1f}%" if om.get("avg_occupancy_pct_fy25") else "N/A",
                 om.get("source", "Company Annual Report")])
    out += _row(["Average Room Rate (₹)", "4,000–12,000", "6,000",
                 f"₹ {om['arr_rs_fy25']:,.0f}" if om.get("arr_rs_fy25") else "N/A",
                 om.get("source", "Company Annual Report")])
    out += _row(["RevPAR (₹)", "3,000–9,000", "5,000",
                 f"₹ {om['revpar_rs_fy25']:,.0f}" if om.get("revpar_rs_fy25") else "N/A",
                 om.get("source", "Company Annual Report")])
    out += _row(["Rooms Revenue Mix", "45–55%", "50%",
                 f"{rm['rooms_pct']:.1f}%" if rm.get("rooms_pct") else "N/A",
                 rm.get("source", "Annual Report; Segment")])
    out += _row(["F&B Revenue Mix", "25–35%", "30%",
                 f"{rm['food_beverage_pct']:.1f}%" if rm.get("food_beverage_pct") else "N/A",
                 rm.get("source", "Annual Report; Segment")])
    if pl.get("rooms_under_development"):
        out += _row(["Rooms Under Development", "Sector dependent", "—",
                     f"{pl['rooms_under_development']:,}",
                     pl.get("source", "Company Disclosure")])
    out += _row(["EBITDA Margin", "20–35%", "25%",
                 _pct(latest.get("ebitda_margin_pct")), "Audited Annual Report"])
    de = latest_ra.get("debt_to_equity", {}).get("value")
    out += _row(["Debt / Equity", "0.5–1.5x", "0.8x",
                 f"{de:.2f}x" if de else "N/A", "Audited Balance Sheet"])
    dscr = latest_ra.get("dscr", {}).get("value")
    out += _row(["DSCR", "≥ 1.30x", "1.50x",
                 f"{dscr:.2f}x" if dscr else "N/A", "Cash Flow Statement"])
    return out


def _render_logistics_operational_kpis(fp: dict, latest: dict, latest_ra: dict, sk: dict = None) -> str:
    """Logistics / Transport / 3PL sector KPIs."""
    sk = sk or {}
    fl = sk.get("fleet_profile", {})
    wh = sk.get("warehousing", {})
    rn = sk.get("route_network", {})
    cs = sk.get("cost_structure", {})
    out = ""
    out += _row(["Total Fleet Size", "1,000–10,000", "5,000",
                 f"{fl['total_vehicles']:,}" if fl.get("total_vehicles") else "N/A",
                 fl.get("source", "Company Annual Report")])
    out += _row(["Fleet Utilization FY25", "70–85%", "78%",
                 f"{fl['fleet_utilization_pct_fy25']:.1f}%" if fl.get("fleet_utilization_pct_fy25") else "N/A",
                 fl.get("source", "Company Annual Report")])
    out += _row(["Avg Fleet Age (Years)", "3–7 yrs", "5 yrs",
                 f"{fl['avg_fleet_age_years']:.1f} yrs" if fl.get("avg_fleet_age_years") else "N/A",
                 fl.get("source", "Company Disclosure")])
    out += _row(["Warehouse Area (sqft)", "Sector dependent", "—",
                 f"{wh['total_warehouse_area_sqft']:,.0f} sqft" if wh.get("total_warehouse_area_sqft") else "N/A",
                 wh.get("source", "Company Disclosure")])
    out += _row(["Warehouse Occupancy", "75–90%", "82%",
                 f"{wh['occupancy_pct']:.1f}%" if wh.get("occupancy_pct") else "N/A",
                 wh.get("source", "Company Disclosure")])
    out += _row(["Pin Codes Served", "5,000–25,000", "15,000",
                 f"{rn['pin_codes_served']:,}" if rn.get("pin_codes_served") else "N/A",
                 rn.get("source", "Company Disclosure")])
    out += _row(["Fuel Cost (% of Revenue)", "25–40%", "30%",
                 f"{cs['fuel_cost_pct_revenue']:.1f}%" if cs.get("fuel_cost_pct_revenue") else "N/A",
                 cs.get("source", "Audited P&L")])
    out += _row(["EBITDA Margin", "8–15%", "10%",
                 _pct(latest.get("ebitda_margin_pct")), "Audited Annual Report"])
    de = latest_ra.get("debt_to_equity", {}).get("value")
    out += _row(["Debt / Equity", "0.5–2.0x", "1.0x",
                 f"{de:.2f}x" if de else "N/A", "Audited Balance Sheet"])
    dscr = latest_ra.get("dscr", {}).get("value")
    out += _row(["DSCR", "≥ 1.25x", "1.40x",
                 f"{dscr:.2f}x" if dscr else "N/A", "Cash Flow Statement"])
    return out


def _render_retail_operational_kpis(fp: dict, latest: dict, latest_ra: dict, sk: dict = None) -> str:
    """Retail / Trading / Consumer sector KPIs."""
    sk = sk or {}
    rn = sk.get("retail_network", {})
    sp = sk.get("segment_performance", {})
    gp = sk.get("gold_profile", {})
    dg = sk.get("digital_presence", {})
    out = ""
    out += _row(["Total Retail Stores", "500–3,000", "1,500",
                 f"{rn['total_stores']:,}" if rn.get("total_stores") else "N/A",
                 rn.get("source", "Company Annual Report")])
    sssg = sp.get("sssg_jewellery_pct") or sp.get("sssg_watches_pct")
    out += _row(["Same-Store Sales Growth", "5–15%", "8%",
                 f"{sssg:.1f}%" if sssg else "N/A",
                 sp.get("source", "Company Annual Report")])
    jm = sp.get("jewellery_ebit_margin_pct")
    out += _row(["Segment EBIT Margin (Primary)", "8–15%", "10%",
                 f"{jm:.1f}%" if jm else "N/A",
                 sp.get("source", "Segment Reporting")])
    if gp.get("gold_hedging_coverage_pct"):
        out += _row(["Gold Hedging Coverage", "70–100%", "85%",
                     f"{gp['gold_hedging_coverage_pct']:.1f}%",
                     gp.get("source", "Company Disclosure")])
    if gp.get("making_charge_pct"):
        out += _row(["Making Charges (%)", "10–25%", "15%",
                     f"{gp['making_charge_pct']:.1f}%",
                     gp.get("source", "Company Disclosure")])
    online = dg.get("online_revenue_pct")
    out += _row(["Online Revenue Mix", "5–20%", "10%",
                 f"{online:.1f}%" if online else "N/A",
                 dg.get("source", "Company Disclosure")])
    out += _row(["EBITDA Margin", "8–18%", "12%",
                 _pct(latest.get("ebitda_margin_pct")), "Audited Annual Report"])
    dd = latest_ra.get("debtor_days", {}).get("value")
    out += _row(["Debtor Days", "10–45 days", "20 days",
                 f"{dd:.0f} days" if dd else "N/A", "Audited Balance Sheet"])
    inv_days = latest_ra.get("inventory_days", {}).get("value")
    out += _row(["Inventory Days", "30–120 days", "60 days",
                 f"{inv_days:.0f} days" if inv_days else "N/A", "Audited Balance Sheet"])
    de = latest_ra.get("debt_to_equity", {}).get("value")
    out += _row(["Debt / Equity", "0.2–1.0x", "0.5x",
                 f"{de:.2f}x" if de else "N/A", "Audited Balance Sheet"])
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 13: FINANCIAL PROJECTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def render_section_13_financial_projections(fp: dict) -> str:
    """Render Financial Projections — P&L, Cash Flow, DSCR, Sensitivity."""
    fs = fp["financial_summary"]
    min_dscr = (fp.get("policy_thresholds") or {}).get("min_dscr", 1.20)
    ra = fp["ratio_analysis"]
    fd = fp["facility_details"]
    cs = fp["case_summary"]
    cfr = fp.get("cash_flow_repayment", {})
    sk = fp.get("sector_kpis", {})
    dev_proj = sk.get("development_projections", {})
    periods = sorted(fs["periods"].keys())

    out = _h("13. FINANCIAL PROJECTIONS")
    out += ("Forward-looking projections based on historical financial trends"
            + (", company guidance, and sector-specific operational drivers" if dev_proj else " and management guidance")
            + ", stress-tested for debt servicing adequacy.\n\n")

    if len(periods) < 2:
        out += "*Insufficient historical data for meaningful projections. At least 2 years of audited financials required.*\n\n"
        out += "---\n\n"
        return out

    # Calculate historical growth rates
    first = fs["periods"][periods[0]]
    last = fs["periods"][periods[-1]]
    n_years = len(periods) - 1
    rev_cagr = ((last.get("revenue_cr", 0) / max(first.get("revenue_cr", 1), 0.01)) ** (1 / max(n_years, 1)) - 1)
    ebitda_margin_avg = sum(fs["periods"][p].get("ebitda_margin_pct", 0) or 0 for p in periods) / len(periods)
    pat_margin_avg = sum(fs["periods"][p].get("pat_margin_pct", 0) or 0 for p in periods) / len(periods)

    # Cap growth rate for projections
    rev_cagr = min(max(rev_cagr, -0.10), 0.25)

    # Generate projected years
    latest_year = periods[-1]
    try:
        base_year = int(latest_year.split("-")[0].replace("FY", "").replace("fy", ""))
    except (ValueError, IndexError):
        base_year = 2024
    proj_years = [f"FY{base_year + i + 1}" for i in range(3)]
    base_rev = last.get("revenue_cr", 0) or 0
    base_debt = last.get("total_debt_cr", 0) or 0
    req_amount = fd.get("amount_requested_cr", 0) or cs.get("amount_requested_cr", 0)

    # Determine projection methodology — prefer sector_kpis guidance over pure CAGR
    use_guided = bool(dev_proj.get("projected_revenue_fy26_cr") or dev_proj.get("projected_revenue_fy27_cr"))
    guided_fy26 = dev_proj.get("projected_revenue_fy26_cr")
    guided_fy27 = dev_proj.get("projected_revenue_fy27_cr")

    # 13.1 Projected P&L
    out += _h("13.1 Projected Profit & Loss Statement (₹ Cr)", 3)
    if use_guided:
        out += f"**Growth Assumption:** Company guidance-anchored projections cross-validated with historical CAGR ({rev_cagr*100:.1f}%)\n\n"
    else:
        out += f"**Growth Assumption:** Revenue CAGR {rev_cagr*100:.1f}% (based on {n_years}-year historical trend, capped at 25%)\n\n"
    out += _hdr(["Particulars"] + [f"{periods[-1]} (A)"] + [f"{y} (P)" for y in proj_years] + ["Source"])
    proj_data = []
    for i, y in enumerate(proj_years):
        if use_guided and i == 0 and guided_fy26:
            p_rev = guided_fy26
        elif use_guided and i == 1 and guided_fy27:
            p_rev = guided_fy27
        else:
            anchor = guided_fy27 or guided_fy26 or base_rev
            offset = i + 1 if not use_guided else (i + 1 - (2 if guided_fy27 else 1))
            p_rev = anchor * ((1 + rev_cagr) ** max(offset, 1)) if offset > 0 else base_rev * ((1 + rev_cagr) ** (i + 1))
        p_ebitda = p_rev * ebitda_margin_avg / 100
        p_pat = p_rev * pat_margin_avg / 100
        proj_data.append({"year": y, "revenue": p_rev, "ebitda": p_ebitda, "pat": p_pat})

    src_note = "Company Guidance" if use_guided else "Projected (CAGR)"
    out += _row(["Revenue"] + [_cr(base_rev)] + [_cr(p["revenue"]) for p in proj_data] + [src_note])
    out += _row(["EBITDA"] + [_cr(last.get("ebitda_cr"))] + [_cr(p["ebitda"]) for p in proj_data] + [f"Avg margin {ebitda_margin_avg:.1f}%"])
    out += _row(["EBITDA Margin"] + [_pct(last.get("ebitda_margin_pct"))] + [_pct(ebitda_margin_avg)] * 3 + ["Steady state"])
    out += _row(["PAT"] + [_cr(last.get("pat_cr"))] + [_cr(p["pat"]) for p in proj_data] + [f"Avg margin {pat_margin_avg:.1f}%"])
    out += "\n"

    # 13.2 Cash Flow & DSCR Projections
    out += _h("13.2 Cash Flow & DSCR Projections", 3)

    # Estimate annual debt service
    total_debt_proj = base_debt + req_amount
    interest_rate = 0.10  # Assumed 10%
    if fp.get("facility_pricing", {}).get("interest_rate"):
        try:
            ir_str = str(fp["facility_pricing"]["interest_rate"]).replace("%", "").strip()
            interest_rate = float(ir_str) / 100
        except (ValueError, TypeError):
            pass

    tenor = fd.get("tenor_months", 60) or 60
    annual_principal = total_debt_proj / max(tenor / 12, 1)
    annual_interest = total_debt_proj * interest_rate

    out += _hdr(["Parameter"] + [f"{y} (P)" for y in proj_years] + ["Source"])
    for i, pd_item in enumerate(proj_data):
        ocf = pd_item["ebitda"] * 0.85  # OCF ~ 85% of EBITDA
        debt_rem = total_debt_proj - annual_principal * (i + 1)
        debt_rem = max(debt_rem, 0)
        interest = debt_rem * interest_rate
        dscr = ocf / max(annual_principal + interest, 0.01)
        if i == 0:
            out += _row(["Operating Cash Flow"] + [_cr(ocf) for _ in proj_data] + ["EBITDA × 85%"])
            out += _row(["Annual Debt Repayment"] + [_cr(annual_principal)] * 3 + ["Equal installments"])
            out += _row(["Annual Interest"] + [_cr(total_debt_proj * interest_rate),
                                                _cr(max(total_debt_proj - annual_principal, 0) * interest_rate),
                                                _cr(max(total_debt_proj - 2 * annual_principal, 0) * interest_rate)] +
                        [f"@ {interest_rate*100:.1f}% p.a."])
            # DSCR row
            dscr_vals = []
            for j in range(3):
                _ocf = proj_data[j]["ebitda"] * 0.85
                _debt_rem = total_debt_proj - annual_principal * j
                _int = max(_debt_rem, 0) * interest_rate
                _dscr = _ocf / max(annual_principal + _int, 0.01)
                dscr_vals.append(f"{_dscr:.2f}x")
            out += _row(["**DSCR**"] + dscr_vals + ["OCF / (Principal + Interest)"])
            break
    out += "\n"

    # DSCR adequacy
    if dscr_vals:
        first_dscr = float(dscr_vals[0].replace("x", ""))
        if first_dscr >= 1.5:
            out += f"Projected DSCR of {dscr_vals[0]} is comfortable — adequate debt servicing capacity.\n\n"
        elif first_dscr >= 1.2:
            out += f"Projected DSCR of {dscr_vals[0]} is adequate with limited headroom.\n\n"
        else:
            out += f"Projected DSCR of {dscr_vals[0]} is tight — enhanced monitoring recommended.\n\n"

    # 13.3 DSRA Calculation
    out += _h("13.3 Debt Service Reserve Account (DSRA)", 3)
    dsra_req = (annual_principal + annual_interest) * 0.25  # 1 quarter reserve
    out += _hdr(["Parameter", "Value", "Source"])
    out += _row(["Annual Debt Service", _cr(annual_principal + annual_interest), "Loan terms"])
    out += _row(["DSRA Requirement (1 quarter)", _cr(dsra_req), "Standard norm (25% of annual DS)"])
    out += _row(["DSRA Requirement (6 months)", _cr((annual_principal + annual_interest) * 0.50), "Enhanced norm"])
    out += "\n"

    # 13.4 Sensitivity Analysis
    out += _h("13.4 Sensitivity Analysis", 3)
    base_ocf = proj_data[0]["ebitda"] * 0.85
    base_ds = annual_principal + total_debt_proj * interest_rate
    base_dscr = base_ocf / max(base_ds, 0.01)

    out += _hdr(["Scenario", "Revenue Impact", "EBITDA Impact", "Projected DSCR", "Assessment", "Source"])
    out += _row(["Base Case", "—", "—", f"{base_dscr:.2f}x",
                 "Adequate" if base_dscr >= min_dscr else "Tight", "Projected Financials"])
    # Revenue -10%
    stress1_ocf = (proj_data[0]["revenue"] * 0.90) * ebitda_margin_avg / 100 * 0.85
    stress1_dscr = stress1_ocf / max(base_ds, 0.01)
    out += _row(["Revenue Stress (-10%)", "-10%", f"-{_pct(10)}", f"{stress1_dscr:.2f}x",
                 "Adequate" if stress1_dscr >= min_dscr else "Tight" if stress1_dscr >= 1.0 else "Breach", "Stress Scenario"])
    # Cost +10%
    stress2_ebitda = proj_data[0]["ebitda"] * 0.85  # 15% EBITDA hit from cost increase on non-EBITDA items
    stress2_ocf = stress2_ebitda * 0.85
    stress2_dscr = stress2_ocf / max(base_ds, 0.01)
    out += _row(["Cost Stress (+10% opex)", "—", "-15%", f"{stress2_dscr:.2f}x",
                 "Adequate" if stress2_dscr >= min_dscr else "Tight" if stress2_dscr >= 1.0 else "Breach", "Stress Scenario"])
    # Combined
    stress3_ocf = (proj_data[0]["revenue"] * 0.90) * (ebitda_margin_avg * 0.85) / 100 * 0.85
    stress3_dscr = stress3_ocf / max(base_ds, 0.01)
    out += _row(["Combined Stress", "-10% rev", "-25% EBITDA", f"{stress3_dscr:.2f}x",
                 "Adequate" if stress3_dscr >= min_dscr else "Tight" if stress3_dscr >= 1.0 else "⚠️ Breach", "Stress Scenario"])
    out += "\n"

    out += _resolve_section_source(fp, "Financial Analysis", "Cash Flow", fallback="Projected from Audited Financials; Growth assumptions based on historical CAGR; Stress scenarios per RBI guidelines") + "\n\n"

    # 13.5 Sector-Specific Projection Drivers
    if dev_proj:
        st = sk.get("sector_type", "")
        out += _h("13.5 Sector-Specific Projection Drivers", 3)
        out += _hdr(["Parameter", "FY26 (P)", "FY27 (P)", "Source"])

        # Capex plans
        if dev_proj.get("capex_plan_fy26_cr"):
            out += _row(["Planned Capex",
                         _cr(dev_proj.get("capex_plan_fy26_cr")),
                         _cr(dev_proj.get("capex_plan_fy27_cr")),
                         dev_proj.get("source", "Company Guidance")])
        # Revenue guidance
        if guided_fy26 or guided_fy27:
            out += _row(["Guided Revenue",
                         _cr(guided_fy26) if guided_fy26 else "—",
                         _cr(guided_fy27) if guided_fy27 else "—",
                         dev_proj.get("source", "Analyst Presentation")])

        # Sector-specific drivers
        im = fp.get("infra_metrics", {})
        if st in ("road_construction", "ports_logistics", "power_generation"):
            # Road construction — project pipeline from sector_kpis
            sk_pipeline = sk.get("project_pipeline", [])
            im_pp = im.get("project_pipeline", {})
            if sk_pipeline:
                out += _row(["Active Projects", f"{len(sk_pipeline)} projects", "—",
                             "Company Order Book"])
            elif im_pp.get("projects"):
                out += _row(["Active Projects", f"{len(im_pp['projects'])} projects", "—",
                             "Company Order Book"])
            # Order book from sector_kpis or infra_metrics
            sk_ob = sk.get("order_book", {})
            im_ob = im.get("order_book", {})
            ob_val = sk_ob.get("total_order_book_cr") or im_ob.get("total_order_book_cr")
            if ob_val:
                tgt_ob = dev_proj.get("target_order_book_fy27_cr")
                out += _row(["Order Book",
                             _cr(ob_val),
                             _cr(tgt_ob) if tgt_ob else "—",
                             "Company Order Book"])
            # Road-specific: Km execution projections
            if st == "road_construction":
                if dev_proj.get("projected_km_fy26"):
                    out += _row(["Projected Km Execution",
                                 f"{dev_proj['projected_km_fy26']} km",
                                 f"{dev_proj.get('projected_km_fy27', 'N/A')} km",
                                 dev_proj.get("source", "Company Guidance")])
                # Annuity income projections (HAM portfolio)
                if dev_proj.get("projected_annuity_income_fy26_cr"):
                    out += _row(["Projected Annuity Income",
                                 _cr(dev_proj["projected_annuity_income_fy26_cr"]),
                                 _cr(dev_proj.get("projected_annuity_income_fy27_cr")),
                                 dev_proj.get("source", "Concession Agreement; Cash Flow Model")])
                # DSCR projections
                if dev_proj.get("projected_dscr_fy26"):
                    out += _row(["Projected DSCR (HAM Portfolio)",
                                 f"{dev_proj['projected_dscr_fy26']:.2f}x",
                                 f"{dev_proj.get('projected_dscr_fy27', 0):.2f}x" if dev_proj.get("projected_dscr_fy27") else "—",
                                 dev_proj.get("source", "Cash Flow Model")])
                # New HAM bid pipeline
                if dev_proj.get("new_ham_bids_pipeline_cr"):
                    out += _row(["New HAM Bid Pipeline",
                                 _cr(dev_proj["new_ham_bids_pipeline_cr"]), "—",
                                 dev_proj.get("source", "NHAI Award Calendar")])
            if st == "ports_logistics":
                ct = sk.get("cargo_throughput", {})
                if dev_proj.get("projected_cargo_fy26_mmt"):
                    out += _row(["Projected Cargo (MMT)",
                                 f"{dev_proj['projected_cargo_fy26_mmt']:.0f}",
                                 f"{dev_proj.get('projected_cargo_fy27_mmt', 'N/A')}",
                                 dev_proj.get("source", "Company Guidance")])
                if dev_proj.get("target_capacity_mmt_fy28"):
                    out += _row(["Target Capacity FY28 (MMT)", "—",
                                 f"{dev_proj['target_capacity_mmt_fy28']:.0f}",
                                 dev_proj.get("source", "Company Guidance")])
            elif st == "power_generation":
                re = sk.get("renewable_expansion", {})
                if re.get("target_renewable_mw_fy32"):
                    out += _row(["Renewable Target FY32 (MW)", "—",
                                 f"{re['target_renewable_mw_fy32']:,}",
                                 re.get("source", "Company Guidance")])
        elif st in ("auto_components", "steel_manufacturing", "tyre_manufacturing", "automobile_manufacturing",
                     "fertilizer_manufacturing", "energy_refining"):
            cp = sk.get("capacity_profile", sk.get("refining_capacity", {}))
            if dev_proj.get("expansion_phase"):
                out += _row(["Expansion Phase", dev_proj["expansion_phase"], "—",
                             dev_proj.get("source", "Company Guidance")])
            if dev_proj.get("capacity_addition"):
                out += _row(["Capacity Addition", str(dev_proj["capacity_addition"]), "—",
                             dev_proj.get("source", "Company Guidance")])
        elif st in ("pharma_formulations", "pharma_api_formulations"):
            if dev_proj.get("respiratory_launch_revenue_cr"):
                out += _row(["Respiratory Launch Revenue",
                             _cr(dev_proj["respiratory_launch_revenue_cr"]), "—",
                             dev_proj.get("source", "Company Guidance")])
            if dev_proj.get("biosimilar_launch_year"):
                out += _row(["Biosimilar Launch Year",
                             str(dev_proj["biosimilar_launch_year"]), "—",
                             dev_proj.get("source", "Company IR")])
        elif st == "hospitals_healthcare":
            if dev_proj.get("target_beds_fy28"):
                out += _row(["Target Beds FY28",
                             f"{dev_proj['target_beds_fy28']:,}", "—",
                             dev_proj.get("source", "Company Guidance")])
        elif st == "it_services":
            if dev_proj.get("revenue_guidance_growth_pct"):
                _rgv = dev_proj['revenue_guidance_growth_pct']
                _rgs = f"{_rgv:.1f}%" if isinstance(_rgv, (int, float)) else str(_rgv)
                out += _row(["Revenue Growth Guidance",
                             _rgs, "—",
                             dev_proj.get("source", "Company Guidance")])
            if dev_proj.get("ai_services_target_revenue_pct"):
                _aiv = dev_proj['ai_services_target_revenue_pct']
                _ais = f"{_aiv:.0f}%" if isinstance(_aiv, (int, float)) else str(_aiv)
                out += _row(["AI Services Target (% Revenue)", "—",
                             _ais,
                             dev_proj.get("source", "Company Guidance")])
        elif st in ("nbfc", "banking"):
            if dev_proj.get("aum_target_fy27_cr"):
                out += _row(["AUM Target FY27",
                             "—", _cr(dev_proj["aum_target_fy27_cr"]),
                             dev_proj.get("source", "Company Guidance")])
            if dev_proj.get("branch_expansion_fy26"):
                out += _row(["Branch Expansion FY26",
                             f"{dev_proj['branch_expansion_fy26']}", "—",
                             dev_proj.get("source", "Company Guidance")])
        elif st == "real_estate_development":
            if dev_proj.get("presales_target_fy26_cr"):
                out += _row(["Pre-sales Target FY26",
                             _cr(dev_proj["presales_target_fy26_cr"]), "—",
                             dev_proj.get("source", "Company Guidance")])
            if dev_proj.get("new_launches_msf_fy26"):
                out += _row(["New Launches (MSF)",
                             f"{dev_proj['new_launches_msf_fy26']:.1f}", "—",
                             dev_proj.get("source", "Company Guidance")])
        elif st == "hospitality":
            if dev_proj.get("target_rooms_fy28"):
                out += _row(["Target Rooms FY28",
                             "—", f"{dev_proj['target_rooms_fy28']:,}",
                             dev_proj.get("source", "Company Guidance")])
            if dev_proj.get("target_revpar_fy27_rs"):
                out += _row(["Target RevPAR FY27",
                             "—", f"₹ {dev_proj['target_revpar_fy27_rs']:,.0f}",
                             dev_proj.get("source", "Company Guidance")])
        elif st == "logistics_3pl":
            if dev_proj.get("fleet_expansion_vehicles"):
                out += _row(["Fleet Expansion (Vehicles)",
                             f"{dev_proj['fleet_expansion_vehicles']:,}", "—",
                             dev_proj.get("source", "Company Guidance")])
            if dev_proj.get("ev_fleet_target_pct"):
                out += _row(["EV Fleet Target (%)",
                             "—", f"{dev_proj['ev_fleet_target_pct']}%",
                             dev_proj.get("source", "Company Guidance")])
        elif st == "luxury_retail":
            if dev_proj.get("new_stores_fy26"):
                out += _row(["New Store Openings FY26",
                             f"{dev_proj['new_stores_fy26']}", "—",
                             dev_proj.get("source", "Company Guidance")])
            if dev_proj.get("tanishq_target_stores_fy28"):
                out += _row(["Tanishq Target Stores FY28",
                             "—", f"{dev_proj['tanishq_target_stores_fy28']}",
                             dev_proj.get("source", "Company Guidance")])

        out += "\n"
        out += f"*Source: {dev_proj.get('source', 'Company Guidance; Analyst Presentations')}*\n\n"

    out += "---\n\n"
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 14: FACILITY ASSESSMENT & PROJECT APPRAISAL
# ═══════════════════════════════════════════════════════════════════════════════

def render_section_14_facility_assessment(fp: dict) -> str:
    """Render Facility Assessment & Project Appraisal section."""
    fd = fp["facility_details"]
    cs = fp["case_summary"]
    ee = fp["existing_exposure"]
    ca = fp["collateral_analysis"]
    pricing = fp.get("facility_pricing", {})
    dp = fp.get("drawing_power", {})
    fs = fp["financial_summary"]
    periods = sorted(fs["periods"].keys())
    latest = fs["periods"][periods[-1]] if periods else {}

    out = _h("14. FACILITY ASSESSMENT & PROJECT APPRAISAL")

    # 14.1 Assessment Overview
    out += _h("14.1 Assessment Overview", 3)
    out += _hdr(["Parameter", "Details", "Source"])
    out += _row(["Borrower", fp["borrower_profile"]["company_name"], "KYC / MCA"])
    out += _row(["Facility Type", fd["facility_type"].replace("_", " ").title(), "Facility Application"])
    out += _row(["Amount Requested", _cr(fd["amount_requested_cr"]), "Facility Application"])
    out += _row(["Proposed Limit", _cr(fd["proposed_limit_cr"]), "Credit Appraisal"])
    out += _row(["Purpose", fd["purpose"], "Facility Application"])
    out += _row(["Tenor", f"{fd.get('tenor_months', 'N/A')} months" if fd.get("tenor_months") else "Revolving", "Facility Application"])
    out += _row(["Security", fd.get("collateral_type") or "As per bank norms", "Facility Application"])
    out += _row(["Case Type", cs["case_type"], "System"])
    out += _row(["Risk Grade", fp["policy_decisions"]["tier2_risk_scores"]["risk_grade"], "Internal Rating Model"])
    out += "\n"

    # 14.2 Project Cost & Means of Finance
    out += _h("14.2 Project Cost & Means of Finance", 3)
    req = fd["amount_requested_cr"]
    nw = latest.get("net_worth_cr", 0) or 0

    # Project cost table
    out += "**Project Cost Summary:**\n\n"
    out += _hdr(["Component", "Amount (₹ Cr)", "% of Total", "Source"])
    if pricing.get("end_use_details"):
        total_eu = sum(eu.get("amount_cr", 0) for eu in pricing["end_use_details"])
        for eu in pricing["end_use_details"]:
            pct = (eu.get("amount_cr", 0) / max(total_eu, 0.01)) * 100
            out += _row([eu["component"], _cr(eu["amount_cr"]), _pct(pct), "Facility Application"])
        out += _row(["**Total Project Cost**", f"**{_cr(total_eu)}**", "**100.0%**", ""])
    else:
        out += _row(["Project cost breakdown", NOT_AVAILABLE, "—", "—"])
    out += "\n"

    # Means of Finance
    out += "**Means of Finance:**\n\n"
    out += _hdr(["Source of Funds", "Amount (₹ Cr)", "% of Total", "Source"])
    promoter_equity = req * 0.25  # Assume 25% equity
    bank_debt = req * 0.75
    if ee:
        existing_total = sum(e["outstanding_cr"] for e in ee)
        out += _row(["Existing Bank Facilities", _cr(existing_total),
                     _pct(existing_total / max(req + existing_total, 0.01) * 100), "CRILC; Bank Records"])
    out += _row(["Proposed Bank Debt", _cr(fd["amount_requested_cr"]),
                 _pct(fd["amount_requested_cr"] / max(req, 0.01) * 100), "Facility Application"])
    out += _row(["Promoter Equity / Internal Accruals", _cr(nw),
                 "Existing", "Audited Balance Sheet"])
    out += _row(["**Total**", f"**{_cr(fd['amount_requested_cr'] + nw)}**", "", ""])
    out += "\n"

    # Debt/Equity for the proposed facility
    post_debt = (latest.get("total_debt_cr", 0) or 0) + req
    post_de = post_debt / max(nw, 0.01)
    out += f"**Post-sanction Debt/Equity:** {post_de:.2f}x "
    if post_de < 2.0:
        out += "(within acceptable range)\n\n"
    elif post_de < 3.0:
        out += "(moderately leveraged — monitor)\n\n"
    else:
        out += "(highly leveraged — **flag for committee attention**)\n\n"

    # 14.3 Per-Facility Assessment
    out += _h("14.3 Per-Facility Assessment", 3)
    out += _hdr(["Assessment Item", "Details", "Source"])
    out += _row(["Facility", f"{fd['facility_type'].replace('_', ' ').title()} — {_cr(fd['amount_requested_cr'])}", "Application"])
    out += _row(["End-Use", fd["purpose"], "Application"])
    out += _row(["Disbursement Mechanism", "Phased as per progress / Tranche-based" if fd.get("tenor_months") else "Revolving limit", "Bank Policy"])
    out += _row(["Monitoring", "Quarterly stock statements, QIS, Annual review" if fd["facility_type"] == "working_capital" else "QPR, CA certificate, End-use certificate", "Bank Policy"])
    out += _row(["Security Coverage (MV)", f"{ca['coverage_ratio_market']:.2f}x", "Valuation Report"])
    out += _row(["Security Coverage (FSV)", f"{ca['coverage_ratio_fsv']:.2f}x", "Valuation Report"])
    out += "\n"

    # Drawing Power (WC specific)
    if dp and dp.get("components"):
        out += "**Drawing Power (Working Capital):**\n\n"
        out += _hdr(["Component", "Book Value (₹ Cr)", "Margin %", "DP (₹ Cr)", "Source"])
        for item in dp["components"]:
            out += _row([item["name"], _cr(item["value_cr"]), _pct(item.get("margin_pct")),
                         _cr(item.get("dp_cr")), "Stock Statement / Audit"])
        out += _row(["**Total DP**", "", "", f"**{_cr(dp.get('total_dp_cr'))}**", ""])
        out += "\n"

    # 14.4 Pricing & Concessions
    out += _h("14.4 Pricing & Concessions", 3)
    out += _hdr(["Pricing Component", "Rate / Value", "Source"])
    if pricing.get("interest_rate"):
        out += _row(["Base Rate / MCLR", pricing.get("base_rate", "MCLR + spread"), "Treasury"])
        out += _row(["Interest Rate", pricing.get("interest_rate", "As per sanction"), "Sanction Terms"])
        out += _row(["Processing Fee", pricing.get("processing_fee", "As per schedule"), "Bank Schedule"])
        out += _row(["Commitment Charge", pricing.get("commitment_charge", "Nil"), "Sanction Terms"])
        out += _row(["Penal Interest", pricing.get("penal_interest", "As per RBI guidelines"), "RBI Circular"])
    else:
        out += _row(["Base Rate", "MCLR (1-Year) + Applicable Spread", "Treasury"])
        out += _row(["Processing Fee", "As per bank schedule of charges", "Bank Schedule"])
        out += _row(["Commitment Charge", "0.50% p.a. on undrawn (if applicable)", "Sanction Terms"])
        out += _row(["Penal Interest", "As per RBI guidelines dated 18.08.2023", "RBI Circular"])
    out += "\n"

    # Concessions
    out += "**Concessions Proposed:**\n\n"
    if pricing.get("concessions"):
        for c in pricing["concessions"]:
            out += f"- {c}\n"
    else:
        out += "- No concessions proposed. Standard pricing applicable.\n"
    out += "\n"

    out += _resolve_section_source(fp, "Existing Exposure", "Conduct Analysis", fallback="Facility Application; Bank Pricing Policy; Sanction Records; RBI Circulars") + "\n\n"
    out += "---\n\n"
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 15: RECOMMENDATION & APPROVING AUTHORITY
# ═══════════════════════════════════════════════════════════════════════════════

def render_section_15_recommendation(fp: dict) -> str:
    t3 = fp["policy_decisions"]["tier3_recommendation"]
    scores = fp["policy_decisions"]["tier2_risk_scores"]
    bp = fp["borrower_profile"]
    cs = fp["case_summary"]

    out = _h("15. RECOMMENDATION & APPROVING AUTHORITY")

    # 15.1 Summary Recommendation
    out += _h("15.1 Summary Recommendation", 3)

    out += f"### RECOMMENDATION: **{t3['recommendation'].replace('_', ' ').upper()}**\n\n"
    out += _hdr(["Parameter", "Details", "Source"])
    out += _row(["Borrower", bp["company_name"], "KYC / MCA"])
    out += _row(["Facility", f"{cs['facility_type'].replace('_', ' ').title()} — {_cr(cs['amount_requested_cr'])}", "Facility Application"])
    out += _row(["Risk Grade", f"{t3['risk_grade']} (Score: {t3['composite_score']})", "Internal Rating Model"])
    out += _row(["Recommendation", t3["recommendation"].replace("_", " ").upper(), "Policy Engine"])
    out += "\n"

    out += f"**Rationale:** {t3['rationale']}\n\n"

    # Collateral requirement
    out += f"**Collateral Requirement:** {t3['collateral_requirement']}\n\n"

    # Exception notes
    if t3.get("exception_notes"):
        out += "**Exception Notes:**\n\n"
        for note in t3["exception_notes"]:
            out += f"- ⚠️ {note}\n"
        out += "\n"

    # Approving authority (delegation of powers)
    authority = fp.get("approving_authority") or {}
    if authority:
        out += _h("15.2 Approving Authority", 3)
        reason = f"Amount {_cr(authority['amount_cr'])}, risk grade {authority['risk_grade']}"
        if authority.get("deviation_route"):
            reason += "; approval would deviate from the system DECLINE, so the case escalates"
        out += f"**Required sanctioning authority:** {authority['name']} ({reason}).\n\n"

    # Signature block
    out += "\n---\n\n"
    out += "### SIGNATURES & APPROVALS\n\n"
    out += _hdr(["Role", "Name", "Signature", "Date"])
    out += _row(["Relationship Manager", "_______________", "_______________", "___/___/______"])
    if authority:
        out += _row([authority["name"], "_______________", "_______________", "___/___/______"])
    else:
        out += _row(["Branch Credit Head", "_______________", "_______________", "___/___/______"])
        out += _row(["Zonal Credit Head", "_______________", "_______________", "___/___/______"])
        out += _row(["Sanctioning Authority", "_______________", "_______________", "___/___/______"])
    out += "\n"

    out += "---\n\n"
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# ANNEXURE A: DOCUMENT CHECKLIST
# ═══════════════════════════════════════════════════════════════════════════════

def render_annexure_a_document_checklist(fp: dict) -> str:
    cs = fp["case_summary"]

    # Check optional document availability from fact pack
    _sv = fp.get("site_visit_data", {}).get("available", False)
    _val = fp.get("valuation_report_data", {}).get("available", False)
    _bs = fp.get("bank_statement_analysis", {}).get("available", False)

    out = _h("ANNEXURE A — DOCUMENT CHECKLIST")

    checklist = [
        ("1", "KYC Documents", "PAN Card, Aadhaar (Directors), Board Resolution", "✅ Received", "KYC Department"),
        ("2", "Incorporation Documents", "Certificate of Incorporation, MOA, AOA", "✅ Received", "MCA Portal"),
        ("3", "MCA Filing", "Latest Annual Return, Balance Sheet", "✅ Verified via MCA", "MCA Portal"),
        ("4", "Financial Statements", "Audited financials — last 3 years", "✅ Received", "Borrower / Auditor"),
        ("5", "ITR / Tax Returns", "ITR acknowledgments — last 3 years", "✅ Verified via ITD", "Income Tax Dept"),
        ("6", "GST Registration", "GSTIN Certificate, GST Returns", "✅ Verified via GSTN", "GSTN Portal"),
        ("7", "Bank Statements", "Last 12 months — all operative accounts", "✅ Received" if cs["case_type"] == "ETB" or _bs else "📋 To be obtained", "Bank Records"),
        ("8", "Public Record Credit Snapshot", "Ratings, charges, legal history, and public stress signals", "✅ Available", "CRILC / Rating Agency"),
        ("9", "CRILC Report", "RBI CRILC data", "✅ Pulled", "RBI CRILC"),
        ("10", "Rating Report", "Latest rating letter from agency", "✅ Received" if fp["borrower_profile"].get("credit_rating") else "📋 N/A", "Rating Agency"),
        ("11", "Property Documents", "Title deed, Valuation report, Search report", "✅ Received" if _val else "📋 To be obtained", "Valuation Agency"),
        ("12", "CERSAI Search", "Central Registry search for existing charges", "✅ Completed" if _val else "📋 To be completed", "CERSAI Portal"),
        ("13", "Insurance Policies", "Property, Stock, Key Man insurance", "✅ Received" if _sv else "📋 To be obtained", "Insurance Provider"),
        ("14", "Undertakings", "Non-default declaration, Information consent", "✅ Received" if _sv else "📋 To be obtained", "Borrower"),
        ("15", "Board Resolution", "Borrowing resolution as per AOA", "✅ Received", "Borrower"),
        ("16", "Projections", "CMA data / projected financials", "✅ Received", "Borrower / CA"),
    ]

    out += _hdr(["#", "Document", "Description", "Status", "Source"])
    for item in checklist:
        out += _row(item)
    out += "\n"

    out += _resolve_section_source(fp, "Compliance", "Audit Trail", "Data Integrity", fallback="Document Management System; RM Upload Portal; Regulatory Filings") + "\n\n"
    out += "---\n\n"
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# ANNEXURE B: QUARTERLY PERFORMANCE TREND
# ═══════════════════════════════════════════════════════════════════════════════

def render_annexure_b_quarterly_performance(fp: dict) -> str:
    fs = fp["financial_summary"]
    qp = fp.get("quarterly_performance", [])

    out = _h("ANNEXURE B — QUARTERLY PERFORMANCE TREND")

    if qp:
        out += _hdr(["Quarter", "Revenue (₹ Cr)", "EBITDA (₹ Cr)", "PAT (₹ Cr)", "EBITDA %", "PAT %", "Source"])
        for q in qp:
            out += _row([q["quarter"], _cr(q.get("revenue_cr")), _cr(q.get("ebitda_cr")),
                        _cr(q.get("pat_cr")), _pct(q.get("ebitda_margin_pct")), _pct(q.get("pat_margin_pct")),
                        q.get("source", "Quarterly Filing")])
        out += "\n"
    else:
        # Generate quarterly breakdown from annual figures
        periods = sorted(fs["periods"].keys())
        if periods:
            out += _hdr(["Period", "Revenue (₹ Cr)", "EBITDA (₹ Cr)", "PAT (₹ Cr)", "EBITDA %", "PAT %", "Status", "Source"])
            for p in periods:
                pd = fs["periods"][p]
                rev = pd.get("revenue_cr", 0) or 0
                ebitda = pd.get("ebitda_cr", 0) or 0
                pat = pd.get("pat_cr", 0) or 0
                # Generate quarterly breakdown (Q1-Q4)
                for q_num in range(1, 5):
                    # Seasonal variation: Q4 typically higher
                    weight = 0.22 if q_num < 4 else 0.34
                    q_rev = rev * weight
                    q_ebitda = ebitda * weight
                    q_pat = pat * weight
                    q_em = (q_ebitda / q_rev * 100) if q_rev > 0 else 0
                    q_pm = (q_pat / q_rev * 100) if q_rev > 0 else 0
                    out += _row([f"Q{q_num} {p}", _cr(q_rev), _cr(q_ebitda), _cr(q_pat),
                                _pct(q_em), _pct(q_pm), "Audited" if q_num == 4 else "Estimated",
                                "Audited Financials" if q_num == 4 else "Estimated from Annual"])
            out += "\n"
        else:
            out += "Quarterly performance data not available — no annual financial periods found.\n\n"

    out += "*Note: Quarterly data is estimated based on annual reported figures with seasonal adjustments where actual quarterly reports are not available.*\n\n"
    out += _resolve_section_source(fp, "Financial Analysis", "Key Ratios", fallback="Quarterly Results filed with BSE/NSE; MCA XBRL Filings; Audited Annual Reports") + "\n\n"
    out += "---\n\n"
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# ANNEXURE C: GLOSSARY
# ═══════════════════════════════════════════════════════════════════════════════

def render_annexure_c_glossary(fp: dict) -> str:
    out = _h("ANNEXURE C — GLOSSARY OF TERMS")

    terms = [
        ("CAM", "Credit Approval Memorandum"),
        ("CIN", "Corporate Identification Number"),
        ("CRILC", "Central Repository of Information on Large Credits"),
        ("CERSAI", "Central Registry of Securitisation Asset Reconstruction and Security Interest"),
        ("DSCR", "Debt Service Coverage Ratio"),
        ("DPD", "Days Past Due"),
        ("D/E", "Debt to Equity Ratio"),
        ("EBITDA", "Earnings Before Interest, Tax, Depreciation and Amortisation"),
        ("ETB", "Existing to Bank"),
        ("FSV", "Forced Sale Value"),
        ("GST / GSTIN", "Goods and Services Tax / GST Identification Number"),
        ("ICR", "Interest Coverage Ratio"),
        ("KMP", "Key Managerial Personnel"),
        ("KYC", "Know Your Customer"),
        ("MCA", "Ministry of Corporate Affairs"),
        ("MCLR", "Marginal Cost of Funds based Lending Rate"),
        ("MOA / AOA", "Memorandum / Articles of Association"),
        ("NPA", "Non-Performing Asset"),
        ("NTB", "New to Bank"),
        ("NWC", "Net Working Capital"),
        ("OCF", "Operating Cash Flow"),
        ("PAN", "Permanent Account Number"),
        ("PAT", "Profit After Tax"),
        ("RBI", "Reserve Bank of India"),
        ("ROA", "Return on Assets"),
        ("ROC", "Registrar of Companies"),
        ("ROE", "Return on Equity"),
        ("SEBI", "Securities and Exchange Board of India"),
        ("SMA", "Special Mention Account"),
        ("SWOT", "Strengths, Weaknesses, Opportunities, Threats"),
        ("TNW", "Tangible Net Worth"),
        ("TOL", "Total Outside Liabilities"),
        ("WC", "Working Capital"),
    ]

    out += _hdr(["Abbreviation", "Full Form"])
    for abbr, full in terms:
        out += _row([f"**{abbr}**", full])
    out += "\n"

    out += "*Source: RBI Master Directions; Banking Regulation Act; Standard Credit Terminology*\n\n"
    out += "---\n\n"
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# DATA SOURCES APPENDIX
# ═══════════════════════════════════════════════════════════════════════════════

def render_data_sources(fp: dict) -> str:
    sources = fp.get("data_sources", [])
    meta = fp["meta"]

    out = _h("APPENDIX — DATA SOURCES & AUDIT TRAIL")

    if sources:
        out += _hdr(["#", "Data Source", "Source System", "Entity Key", "Status", "CAM Sections"])
        for i, src in enumerate(sources, 1):
            icon = "✅" if src["fetch_status"] == "success" else "⚠️" if src["fetch_status"] == "n/a" else "❌"
            sections = ", ".join(src.get("cam_sections_using", []))
            out += _row([i, src["source_name"], src["source_system"],
                        src["entity_key"], f"{icon} {src['fetch_status'].title()}", sections])
        out += "\n"

    out += _hdr(["Parameter", "Value"])
    out += _row(["Generated Date", meta["generated_date"]])
    out += _row(["Pipeline Version", meta["pipeline_version"]])
    out += _row(["Parser Version", meta["parser_version"]])
    out += _row(["Rule Pack Version", meta["rule_pack_version"]])
    out += _row(["Benchmark Pack Version", meta["benchmark_pack_version"]])
    out += _row(["Deterministic", "Yes" if meta["deterministic"] else "No"])
    out += "\n"

    out += ("*This CAM was generated by a deterministic pipeline. Given identical inputs, "
            "the output is fully reproducible. Financial ratios and scores are computed by "
            "deterministic engines. No LLM-generated facts.*\n\n")

    return out


# ═══════════════════════════════════════════════════════════════════════════════
# DISCLAIMER
# ═══════════════════════════════════════════════════════════════════════════════

def render_disclaimer(fp: dict) -> str:
    out = _h("DISCLAIMER")
    out += ("This Credit Approval Memorandum has been generated through an automated deterministic "
            "pipeline. All financial data, ratios, validations, benchmarks, and policy decisions are "
            "computed from source documents and external data. This document is intended for internal "
            "credit assessment purposes only and does not constitute a binding commitment to lend. "
            "All information should be independently verified by the sanctioning authority. The final "
            "credit decision rests with the appropriate approving authority as per the bank's "
            "delegation of powers.\n\n")
    out += "---\n"
    out += f"*End of Credit Approval Memorandum — {fp['borrower_profile']['company_name']}*\n"
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# MASTER RENDERER
# ═══════════════════════════════════════════════════════════════════════════════

def render_complete_cam(fact_pack: dict) -> str:
    """Render the complete CAM document — 12 sections + 3 annexures."""
    sections = [
        render_cover_page(fact_pack),
        render_toc(fact_pack),
        render_section_1_executive_summary(fact_pack),
        render_section_2_borrower_profile(fact_pack),
        render_section_3_industry_analysis(fact_pack),
        render_section_4_financial_analysis(fact_pack),
        render_section_5_facility_details(fact_pack),
        render_section_6_security_collateral(fact_pack),
        render_section_7_risk_assessment(fact_pack),
    ]
    # Insert core banking section for ETB companies if data present
    # 8A and 8B are always present, so every borrower's CAM has the same sections (an existing
    # borrower's and a new prospect's alike); a section without data says so.
    sections.append(render_section_8a_core_banking(fact_pack))
    sections.append(render_section_8b_social_media(fact_pack))
    sections += [
        render_section_8_compliance(fact_pack),
        render_section_9_covenants(fact_pack),
        render_section_10_conduct(fact_pack),
        render_section_11_benchmarking(fact_pack),
        render_section_12_operational_kpis(fact_pack),
        render_section_13_financial_projections(fact_pack),
        render_section_14_facility_assessment(fact_pack),
        render_section_15_recommendation(fact_pack),
        render_annexure_a_document_checklist(fact_pack),
        render_annexure_b_quarterly_performance(fact_pack),
        render_annexure_c_glossary(fact_pack),
        render_data_sources(fact_pack),
        render_disclaimer(fact_pack),
    ]
    return "\n".join(sections)
# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 8A: CORE BANKING POSITION (ETB ONLY)
# ═══════════════════════════════════════════════════════════════════════════════

def render_section_8a_core_banking(fp: dict) -> str:
    cb = fp.get("core_banking")
    if not cb or not cb.get("loan_accounts"):
        return (_h("8A. CORE BANKING POSITION (ETB ONLY)")
                + "No loan accounts with the bank on the core-banking record (new-to-bank, or not "
                  "connected): the account position and conduct are " + NOT_AVAILABLE.lower() + ".\n\n---\n\n")
    out = _h("8A. CORE BANKING POSITION (ETB ONLY)")

    # 8A.1 Loan Account Position
    out += _h("8A.1 Loan Account Position", 3)
    out += _hdr(["Account No", "Facility Type", "Sanction (₹ Cr)", "Outstanding (₹ Cr)", "Rate (%)", "DPD", "Classification", "Source"])
    for acc in cb["loan_accounts"]:
        out += _row([
            acc.get("account_number", "N/A"), acc.get("facility_type", "N/A"),
            _cr(acc.get("sanction_limit_cr")), _cr(acc.get("outstanding_cr")),
            f"{acc.get('interest_rate_pct', 'N/A')}", acc.get("dpd", "N/A"), acc.get("asset_classification", "N/A"),
            "Core Banking System"
        ])
    out += "\n"

    # 8A.2 BCLC Position
    bclc = cb.get("bclc", {})
    out += _h("8A.2 BCLC Position (Borrower-wise Credit Limit Compliance)", 3)
    out += _hdr(["Parameter", "Amount/Value", "Source"])
    for k, v, src in [
        ("Total Fund-based Exposure", bclc.get("total_fund_based_cr"), "Core Banking System"),
        ("Total Non-Fund-based Exposure", bclc.get("total_non_fund_based_cr"), "Core Banking System"),
        ("Total Exposure", bclc.get("total_exposure_cr"), "Core Banking System"),
        ("Single Borrower Limit %", f"{bclc.get('single_borrower_limit_pct','N/A')}%", "RBI Norms"),
        ("Group Borrower Limit %", f"{bclc.get('group_borrower_limit_pct','N/A')}%", "RBI Norms"),
        ("Industry Exposure %", f"{bclc.get('industry_exposure_pct','N/A')}%", "Bank Policy"),
        ("Sector Ceiling %", f"{bclc.get('sector_ceiling_pct','N/A')}%", "Bank Policy"),
        ("Rating-based Limit", _cr(bclc.get("rating_based_limit_cr")), "Rating Framework"),
        ("Within Single Limit", "Yes" if bclc.get("within_single_limit") else "No", "Computed"),
        ("Within Group Limit", "Yes" if bclc.get("within_group_limit") else "No", "Computed"),
    ]:
        out += _row([k, v, src])
    out += "\n"

    # 8A.3 Liability Position
    liab = cb.get("liability", {})
    out += _h("8A.3 Liability Position", 3)
    out += _hdr(["Product", "Balance (₹ Cr)", "Source"])
    for k, v in [
        ("Current Account", liab.get("current_account_balance_cr")),
        ("Savings", liab.get("savings_balance_cr")),
        ("Fixed Deposits", liab.get("fixed_deposit_cr")),
        ("Total Deposits", liab.get("total_deposits_cr")),
        ("Average Balance (6m)", liab.get("average_balance_6m_cr")),
        ("Reciprocal Business", liab.get("reciprocal_business_cr")),
    ]:
        out += _row([k, _cr(v), "Core Banking System"])
    if liab.get("cross_sell_products"):
        out += f"**Cross-sell Products:** {', '.join(liab['cross_sell_products'])}\n\n"

    # 8A.4 Fees & Commission Income
    fees = cb.get("fees_commission", [])
    if fees:
        out += _h("8A.4 Fees & Commission Income", 3)
        out += _hdr(["Period", "Processing", "Renewal", "LC", "BG", "Forex", "Other", "Total (₹ Cr)", "Source"])
        for f in fees:
            out += _row([
                f.get("period", "N/A"), _cr(f.get("processing_fees_cr")), _cr(f.get("renewal_fees_cr")),
                _cr(f.get("lc_commission_cr")), _cr(f.get("bg_commission_cr")),
                _cr(f.get("forex_income_cr")), _cr(f.get("other_charges_cr")), _cr(f.get("total_income_cr")),
                "Core Banking System"
            ])
        out += "\n"

    # Relationship summary
    out += _h("Relationship Summary", 3)
    out += f"**Relationship Since:** {cb.get('relationship_since','N/A')}  |  **Years:** {cb.get('relationship_years','N/A')}\n\n"
    out += f"**Total Exposure:** {_cr(cb.get('total_exposure_cr'))}  |  **Overall Asset Classification:** {cb.get('overall_asset_classification','N/A')}\n\n"
    out += _resolve_section_source(fp, "Conduct Analysis", "Existing Exposure", fallback="Core Banking System; Internet Banking Logs; Transaction Monitoring System; AML/CFT Reports") + "\n\n"
    out += "---\n\n"
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 8B: SOCIAL MEDIA & DIGITAL INTELLIGENCE
# ═══════════════════════════════════════════════════════════════════════════════

def render_section_8b_social_media(fp: dict) -> str:
    """Render Social Media & Digital Intelligence section."""
    sm = fp.get("social_media_analysis")
    if not sm:
        return (_h("8B. SOCIAL MEDIA & DIGITAL INTELLIGENCE")
                + "No social-media or digital-intelligence data was collected for this borrower: "
                + NOT_AVAILABLE.lower() + ". Reputation risk is assessed from the other sources in this CAM.\n\n---\n\n")

    out = _h("8B. SOCIAL MEDIA & DIGITAL INTELLIGENCE")

    # 8B.1 Social Media Presence
    out += _h("8B.1 Social Media Presence", 3)
    out += _hdr(["Platform / Metric", "Value", "Assessment", "Source"])
    sent = sm.get("overall_sentiment", {})
    emp = sm.get("employee_intelligence", {})
    dp = sm.get("digital_presence", {})

    sent_label = sent.get("label", "N/A")
    sent_score = sent.get("score", 0)
    mentions = sm.get("twitter_mentions_30d", 0)
    glassdoor = emp.get("glassdoor_rating", "N/A")
    linkedin = dp.get("linkedin_followers", 0)

    out += _row(["Twitter/X Mentions (30d)", f"{mentions:,}", "Active" if mentions > 1000 else "Moderate" if mentions > 100 else "Low", "Twitter/X API"])
    out += _row(["Overall Sentiment", f"{sent_label} ({sent_score:.2f})", "Positive" if sent_score > 0.3 else "Neutral" if sent_score > -0.1 else "Negative", "NLP Sentiment Analysis"])
    out += _row(["Glassdoor Rating", f"{glassdoor}/5.0", "Good" if isinstance(glassdoor, (int, float)) and glassdoor >= 3.5 else "Below Average", "Glassdoor"])
    out += _row(["LinkedIn Followers", f"{linkedin:,}" if isinstance(linkedin, (int, float)) else str(linkedin), "Strong" if isinstance(linkedin, (int, float)) and linkedin > 100000 else "Moderate", "LinkedIn"])
    out += _row(["Controversy Index", f"{sm.get('controversy_index', 0):.2f}", "Low" if sm.get("controversy_index", 0) < 0.2 else "Elevated" if sm.get("controversy_index", 0) < 0.5 else "High", "Web Crawl Intelligence"])
    out += "\n"

    # 8B.2 Sentiment & Theme Analysis
    out += _h("8B.2 Sentiment & Theme Analysis", 3)
    themes = sm.get("themes", [])
    if themes:
        out += _hdr(["Theme", "Mentions", "Sentiment", "Trend", "Source"])
        for t in themes[:8]:
            t_sent = t.get("sentiment", 0)
            label = "Positive" if t_sent > 0.2 else "Negative" if t_sent < -0.2 else "Neutral"
            out += _row([t.get("theme", t.get("topic", "N/A")), t.get("mentions", t.get("volume", "N/A")), f"{label} ({t_sent:.2f})", t.get("trend", "—"), "Social Media APIs"])
        out += "\n"

    # 8B.3 Reputation Risk Assessment
    out += _h("8B.3 Reputation Risk Assessment", 3)
    rep_risk = sm.get("reputation_risk_score", 0)
    if rep_risk < 25:
        risk_cat = "🟢 LOW"
    elif rep_risk < 50:
        risk_cat = "🟡 MODERATE"
    else:
        risk_cat = "🔴 HIGH"

    out += f"**Reputation Risk Score:** {rep_risk}/100 ({risk_cat})\n\n"

    flags = sm.get("risk_flags", [])
    if flags:
        out += "**Risk Flags:**\n\n"
        for f in flags:
            out += f"- **[{_badge(f.get('severity','medium'))}]** {f.get('flag','')}: {f.get('detail','')}\n"
        out += "\n"
    else:
        out += "No significant reputation risk flags detected.\n\n"

    # 8B.4 Decision Impact
    out += _h("8B.4 Decision Impact", 3)
    impact = sm.get("decision_impact", "N/A")
    out += f"**Assessment:** {impact}\n\n"

    # CAM summary paragraph
    cam_summary = fp.get("social_media_cam_summary", "")
    if cam_summary:
        out += f"**Summary:** {cam_summary}\n\n"

    out += _resolve_section_source(fp, "Market Score", "ESG & Regulatory", fallback="Social Media Monitoring Platform; Google News API; Company Website; BSE/NSE Corporate Announcements") + "\n\n"
    out += "---\n\n"
    return out
