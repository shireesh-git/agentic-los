"""
CAM Narrative Renderer — LEGACY (v1)

Not used by the application: CAM rendering goes through cam_renderer_v2 (template)
and cam_llm_renderer (LLM). Kept only because tests/test_pipeline.py asserts on this
version's headings. To retire it, point those tests at cam_renderer_v2, adjust the
heading assertions to v2's wording, confirm they pass, then delete this module.

Pass 2: Converts the approved factual JSON into a complete Credit Approval Memorandum.
This generates deterministic narrative from fixed templates + fact data.
No hallucination — every sentence traces to the fact pack.
"""

from datetime import date


def _header(text: str, level: int = 2) -> str:
    return f"{'#' * level} {text}\n\n"


def _table_row(cells: list) -> str:
    return "| " + " | ".join(str(c) for c in cells) + " |\n"


def _table_header(headers: list) -> str:
    row = _table_row(headers)
    sep = "| " + " | ".join("---" for _ in headers) + " |\n"
    return row + sep


def _format_cr(val) -> str:
    if val is None:
        return "N/A"
    return f"₹ {val:,.2f} Cr"


def _format_pct(val) -> str:
    if val is None:
        return "N/A"
    return f"{val:.1f}%"


def _format_ratio(val) -> str:
    if val is None:
        return "N/A"
    return f"{val:.2f}x"


def _severity_badge(s: str) -> str:
    badges = {"critical": "🔴 CRITICAL", "high": "🟠 HIGH", "medium": "🟡 MEDIUM", "low": "🟢 LOW"}
    return badges.get(s.lower(), s)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION RENDERERS
# ═══════════════════════════════════════════════════════════════════════════════

def render_table_of_contents(fp: dict) -> str:
    """Render a table of contents."""
    out = _header("TABLE OF CONTENTS")
    toc_items = [
        "360° Credit Overview (at a glance)",
        "1. Executive Summary",
        "2. Borrower Profile",
        "   2.1 Company Overview",
        "   2.2 Group Structure",
        "   2.3 Management / Board of Directors",
        "   2.4 Corporate Hierarchy & Group Structure",
        "3. Facility Details",
        "   3.1 Proposed Facility",
        "   3.2 Existing Exposure",
        "4. Financial Analysis",
        "   4.1 Income Statement Summary",
        "   4.2 Balance Sheet Summary",
        "   4.3 Cash Flow Summary",
        "   4.4 Provisional / Latest Unaudited Financials",
        "   4.5 Key Financial Ratios",
        "   4.6 Financial Commentary & Trend Analysis",
        "5. Credit Strengths",
        "6. Key Risks & Concerns",
        "7. Cash Flow & Repayment Analysis",
        "8. Industry Benchmark Analysis",
        "   8.1 Full Benchmark Comparison",
        "   8.2 Key Concerns vs Peers",
        "   8.3 Peer Positioning Commentary",
        "9. Collateral / Security Analysis",
        "10. Banking Conduct Analysis",
        "   10.1 Covenant Compliance History",
        "11. External Intelligence",
        "   11.1 Bureau / External Data",
        "   11.2 Latest Rating Action",
        "   11.3 Market / News / Social Signals",
        "12. ESG & Regulatory Compliance",
        "13. Validation & Exception Summary",
        "14. Risk Assessment & Policy Decisions",
        "   14.1 Hard Rule Checks (Tier 1)",
        "   14.2 Risk Scores (Tier 2)",
        "   14.3 Risk Narrative",
        "15. Recommendation",
        "   15.1 Conditions Precedent",
        "   15.2 Proposed Covenants",
        "   15.3 Collateral Requirement",
        "   15.4 Monitoring Conditions",
        "16. Final Lending Decision",
        "17. Audit Trail & Reproducibility",
        "Appendix A — Data Sources & Provenance",
    ]
    for item in toc_items:
        out += f"{item}  \n"
    out += "\n---\n\n"
    return out

def render_cover_page(fp: dict) -> str:
    """Render CAM cover page."""
    cs = fp["case_summary"]
    bp = fp["borrower_profile"]
    rec = fp["policy_decisions"]["tier3_recommendation"]

    out = _header("CREDIT APPROVAL MEMORANDUM", 1)
    out += "---\n\n"
    out += f"**Borrower:** {bp['company_name']}  \n"
    out += f"**CIN:** {bp['cin']}  \n"
    out += f"**PAN:** {bp['pan']}  \n"
    out += f"**Case Type:** {cs['case_type']} | **Borrower Type:** {cs['borrower_type'].title()}  \n"
    out += f"**Sector:** {cs['sector'].title()} — {cs['subsector']}  \n"
    out += f"**Facility Type:** {cs['facility_type'].replace('_', ' ').title()}  \n"
    out += f"**Amount Requested:** {_format_cr(cs['amount_requested_cr'])}  \n"
    out += f"**Credit Rating:** {bp.get('credit_rating', 'N/A')}  \n"
    out += f"**Date of Memo:** {fp['meta']['generated_date']}  \n"
    out += f"**Risk Grade:** {rec['risk_grade']} (Score: {rec['composite_score']})  \n"
    out += f"**Recommendation:** **{rec['recommendation'].replace('_', ' ').upper()}**  \n"
    out += "\n---\n\n"
    return out


def render_executive_summary(fp: dict) -> str:
    """Render executive summary."""
    cs = fp["case_summary"]
    bp = fp["borrower_profile"]
    fs = fp["financial_summary"]
    rec = fp["policy_decisions"]["tier3_recommendation"]
    scores = fp["policy_decisions"]["tier2_risk_scores"]
    exceptions = fp["validation_exceptions"]

    periods = sorted(fs["periods"].keys())
    latest = fs["periods"][periods[-1]] if periods else {}

    out = _header("1. EXECUTIVE SUMMARY")

    out += f"This Credit Approval Memorandum pertains to the proposal from **{bp['company_name']}** "
    out += f"for a **{cs['facility_type'].replace('_', ' ')}** facility of **{_format_cr(cs['amount_requested_cr'])}**. "
    out += f"The Company is a **{cs['borrower_type']}** entity incorporated on {bp['date_of_incorporation']} "
    out += f"and registered in **{bp['registered_state']}**, operating in the **{cs['sector']} — {cs['subsector']}** sector.\n\n"

    out += f"**Purpose:** {cs['purpose']}\n\n"

    out += f"For the latest audited period ({periods[-1] if periods else 'N/A'}), the Company reported:\n"
    out += f"- Revenue: {_format_cr(latest.get('revenue_cr'))}\n"
    out += f"- EBITDA: {_format_cr(latest.get('ebitda_cr'))} (Margin: {_format_pct(latest.get('ebitda_margin_pct'))})\n"
    out += f"- PAT: {_format_cr(latest.get('pat_cr'))}\n"
    out += f"- Net Worth: {_format_cr(latest.get('net_worth_cr'))}\n"
    out += f"- Total Debt: {_format_cr(latest.get('total_debt_cr'))}\n\n"

    out += f"**Risk Assessment:**\n"
    out += f"- Composite Risk Score: **{scores['composite_score']}** (Grade: **{scores['risk_grade']}**)\n"
    out += f"- Financial Score: {scores['financial_score']} | Conduct: {scores['conduct_score']} | "
    out += f"Governance: {scores['governance_score']} | Market: {scores['market_score']}\n\n"

    critical_count = sum(1 for e in exceptions if e["severity"] == "critical")
    high_count = sum(1 for e in exceptions if e["severity"] == "high")
    out += f"**Validation:** {len(exceptions)} exception(s) detected — "
    out += f"{critical_count} Critical, {high_count} High severity.\n\n"

    out += f"**Recommendation:** {rec['recommendation'].replace('_', ' ').upper()}\n\n"
    out += f"*Rationale:* {rec['rationale']}\n\n"

    return out


def render_borrower_profile(fp: dict) -> str:
    """Render borrower and group profile."""
    bp = fp["borrower_profile"]
    gp = fp["group_profile"]
    mp = fp["management_profile"]

    out = _header("2. BORROWER PROFILE")

    out += _header("2.1 Company Overview", 3)
    out += _table_header(["Parameter", "Details"])
    out += _table_row(["Company Name", bp["company_name"]])
    out += _table_row(["CIN", bp["cin"]])
    out += _table_row(["PAN", bp["pan"]])
    out += _table_row(["Date of Incorporation", bp["date_of_incorporation"]])
    out += _table_row(["Registered State", bp["registered_state"]])
    out += _table_row(["Registered Address", bp["registered_address"]])
    out += _table_row(["Listed Exchange", bp.get("listed_exchange") or "Unlisted"])
    out += _table_row(["NSE Symbol", bp.get("nse_symbol") or "N/A"])
    out += _table_row(["Credit Rating", bp.get("credit_rating") or "N/A"])
    out += _table_row(["Rating Agency", bp.get("rating_agency") or "N/A"])
    out += _table_row(["Employee Count", bp.get("employee_count") or "N/A"])
    out += _table_row(["Authorized Capital", _format_cr(bp.get("authorized_capital_cr"))])
    out += _table_row(["Paid-up Capital", _format_cr(bp.get("paid_up_capital_cr"))])
    out += "\n"

    out += _header("2.2 Group Structure", 3)
    out += f"**Group Name:** {gp['group_name']}  \n"
    out += f"**Group Entities:** {', '.join(gp['entities'])}  \n"
    out += f"**Shareholding:** Promoter: {gp['promoter_holding_pct']}% | "
    out += f"Institutional: {gp['institutional_holding_pct']}% | Public: {gp['public_holding_pct']}%\n\n"

    out += _header("2.3 Management / Board of Directors", 3)
    out += _table_header(["Name", "Designation", "DIN", "Promoter", "Net Worth (Cr)", "Other Directorships"])
    for d in mp["directors"]:
        out += _table_row([
            d["name"], d["designation"], d["din"],
            "Yes" if d["is_promoter"] else "No",
            _format_cr(d["net_worth_cr"]) if d["net_worth_cr"] else "N/A",
            ", ".join(d["other_directorships"]) if d["other_directorships"] else "None",
        ])
    out += "\n"

    return out


def render_facility_details(fp: dict) -> str:
    """Render facility request details."""
    fd = fp["facility_details"]
    ee = fp["existing_exposure"]

    out = _header("3. FACILITY DETAILS")

    out += _header("3.1 Proposed Facility", 3)
    out += _table_header(["Parameter", "Details"])
    out += _table_row(["Facility Type", fd["facility_type"].replace("_", " ").title()])
    out += _table_row(["Amount Requested", _format_cr(fd["amount_requested_cr"])])
    out += _table_row(["Proposed Limit", _format_cr(fd["proposed_limit_cr"])])
    if fd.get("existing_limit_cr"):
        out += _table_row(["Existing Limit", _format_cr(fd["existing_limit_cr"])])
    out += _table_row(["Tenor", f"{fd['tenor_months']} months" if fd.get("tenor_months") else "N/A"])
    out += _table_row(["Collateral Type", fd.get("collateral_type") or "Unsecured"])
    out += _table_row(["Purpose", fd["purpose"]])
    out += "\n"

    if ee:
        out += _header("3.2 Existing Exposure", 3)
        out += _table_header(["Facility Type", "Sanctioned (Cr)", "Outstanding (Cr)", "Utilization %", "Overdue Days", "Classification"])
        for e in ee:
            out += _table_row([
                e["facility_type"],
                _format_cr(e["sanctioned_cr"]),
                _format_cr(e["outstanding_cr"]),
                f"{e['utilization_pct']:.1f}%",
                e["overdue_days"],
                e["classification"],
            ])
        out += "\n"

    return out


def render_financial_analysis(fp: dict) -> str:
    """Render complete financial analysis."""
    fs = fp["financial_summary"]
    ra = fp["ratio_analysis"]

    periods = sorted(fs["periods"].keys())

    out = _header("4. FINANCIAL ANALYSIS")

    # ── Income Statement Summary ──
    out += _header("4.1 Income Statement Summary (₹ Cr)", 3)
    out += _table_header(["Particulars"] + periods)
    metrics = [
        ("Revenue from Operations", "revenue_cr"),
        ("EBITDA", "ebitda_cr"),
        ("EBITDA Margin %", "ebitda_margin_pct"),
        ("PAT", "pat_cr"),
        ("PAT Margin %", "pat_margin_pct"),
    ]
    for label, key in metrics:
        row = [label]
        for p in periods:
            val = fs["periods"][p].get(key)
            if "pct" in key:
                row.append(_format_pct(val))
            else:
                row.append(_format_cr(val))
        out += _table_row(row)
    out += "\n"

    # Growth rates
    if fs.get("growth"):
        out += "**Revenue Growth (YoY):** "
        growths = [f"{k}: {v}%" for k, v in fs["growth"].items()]
        out += " | ".join(growths) + "\n\n"

    # ── Balance Sheet Summary ──
    out += _header("4.2 Balance Sheet Summary (₹ Cr)", 3)
    out += _table_header(["Particulars"] + periods)
    bs_metrics = [
        ("Net Worth / Equity", "net_worth_cr"),
        ("Total Debt", "total_debt_cr"),
        ("Total Assets", "total_assets_cr"),
        ("Current Assets", "current_assets_cr"),
        ("Current Liabilities", "current_liabilities_cr"),
        ("Trade Receivables", "trade_receivables_cr"),
        ("Inventory", "inventory_cr"),
        ("Trade Payables", "trade_payables_cr"),
    ]
    for label, key in bs_metrics:
        row = [label]
        for p in periods:
            row.append(_format_cr(fs["periods"][p].get(key)))
        out += _table_row(row)
    out += "\n"

    # ── Cash Flow Summary ──
    out += _header("4.3 Cash Flow Summary (₹ Cr)", 3)
    out += _table_header(["Particulars"] + periods)
    cf_metrics = [
        ("Operating Cash Flow", "operating_cash_flow_cr"),
        ("Capex", "capex_cr"),
    ]
    for label, key in cf_metrics:
        row = [label]
        for p in periods:
            row.append(_format_cr(fs["periods"][p].get(key)))
        out += _table_row(row)
    out += "\n"

    # ── Provisional ──
    if fs.get("provisional"):
        prov = fs["provisional"]
        out += _header("4.4 Provisional / Latest Unaudited Financials", 3)
        out += _table_header(["Metric", f"{prov['period']}"])
        out += _table_row(["Revenue", _format_cr(prov.get("revenue_cr"))])
        out += _table_row(["EBITDA", _format_cr(prov.get("ebitda_cr"))])
        out += _table_row(["PAT", _format_cr(prov.get("pat_cr"))])
        out += _table_row(["Total Debt", _format_cr(prov.get("total_debt_cr"))])
        out += _table_row(["Equity", _format_cr(prov.get("total_equity_cr"))])
        out += "\n"

    # ── Key Ratios ──
    out += _header("4.5 Key Financial Ratios", 3)
    ratio_names_display = {
        "current_ratio": "Current Ratio",
        "debt_to_equity": "Debt / Equity",
        "debt_to_ebitda": "Debt / EBITDA",
        "interest_coverage_ratio": "Interest Coverage (ICR)",
        "net_profit_margin": "Net Profit Margin",
        "ebitda_margin": "EBITDA Margin",
        "return_on_equity": "Return on Equity (ROE)",
        "return_on_assets": "Return on Assets (ROA)",
        "asset_turnover": "Asset Turnover",
        "debtor_days": "Debtor Days",
        "inventory_days": "Inventory Days",
        "payable_days": "Payable Days",
        "working_capital_cycle": "Working Capital Cycle (Days)",
        "dscr": "DSCR",
        "tol_tnw": "TOL / TNW",
    }
    out += _table_header(["Ratio"] + periods)
    for rname, display in ratio_names_display.items():
        row = [display]
        for p in periods:
            r = ra.get(p, {}).get(rname, {})
            val = r.get("value")
            if val is None:
                row.append("N/A")
            elif "margin" in rname or "return" in rname:
                row.append(f"{val * 100:.1f}%")
            elif "days" in rname or "cycle" in rname:
                row.append(f"{val:.0f}")
            else:
                row.append(f"{val:.2f}")
        out += _table_row(row)
    out += "\n"

    # ── Financial Commentary ──
    out += render_financial_commentary(fp)

    return out


def render_financial_commentary(fp: dict) -> str:
    """Generate detailed financial commentary from fact-pack data."""
    fs = fp["financial_summary"]
    ra = fp["ratio_analysis"]
    cs = fp["case_summary"]
    periods = sorted(fs["periods"].keys())

    out = _header("4.6 Financial Commentary & Trend Analysis", 3)

    # Revenue trend analysis
    out += "**Revenue Trend:**\n\n"
    if len(periods) >= 2:
        first = fs["periods"][periods[0]]
        last = fs["periods"][periods[-1]]
        if first.get("revenue_cr") and last.get("revenue_cr") and first["revenue_cr"] > 0:
            total_growth = ((last["revenue_cr"] - first["revenue_cr"]) / first["revenue_cr"]) * 100
            cagr_years = len(periods) - 1
            cagr = ((last["revenue_cr"] / first["revenue_cr"]) ** (1 / cagr_years) - 1) * 100 if cagr_years > 0 else 0
            out += (f"Over the {cagr_years}-year period from {periods[0]} to {periods[-1]}, "
                    f"the Company's revenue from operations has {'grown' if total_growth > 0 else 'declined'} "
                    f"from {_format_cr(first['revenue_cr'])} to {_format_cr(last['revenue_cr'])}, "
                    f"representing a cumulative {'increase' if total_growth > 0 else 'decrease'} of "
                    f"{abs(total_growth):.1f}% ({cagr:.1f}% CAGR).\n\n")

            for i in range(1, len(periods)):
                curr = fs["periods"][periods[i]]
                prev = fs["periods"][periods[i-1]]
                if prev.get("revenue_cr") and prev["revenue_cr"] > 0:
                    yoy = ((curr["revenue_cr"] - prev["revenue_cr"]) / prev["revenue_cr"]) * 100
                    out += (f"- **{periods[i]}:** Revenue {'increased' if yoy > 0 else 'decreased'} "
                            f"by {abs(yoy):.1f}% YoY to {_format_cr(curr['revenue_cr'])}.\n")
            out += "\n"

    # Profitability analysis
    out += "**Profitability Analysis:**\n\n"
    latest = fs["periods"][periods[-1]] if periods else {}
    if latest:
        ebitda_m = latest.get("ebitda_margin_pct")
        pat_m = latest.get("pat_margin_pct")
        out += (f"For the latest period ({periods[-1]}), the Company reported an EBITDA margin of "
                f"{_format_pct(ebitda_m)} and a net profit margin of {_format_pct(pat_m)}. ")

        # Margin trend
        if len(periods) >= 2:
            first_ebitda_m = fs["periods"][periods[0]].get("ebitda_margin_pct", 0)
            if ebitda_m and first_ebitda_m:
                if ebitda_m > first_ebitda_m:
                    out += (f"EBITDA margins have improved from {_format_pct(first_ebitda_m)} "
                            f"in {periods[0]}, indicating strengthening operational efficiency.\n\n")
                elif ebitda_m < first_ebitda_m:
                    out += (f"EBITDA margins have declined from {_format_pct(first_ebitda_m)} "
                            f"in {periods[0]}, raising concerns about cost pressures or pricing erosion.\n\n")
                else:
                    out += f"EBITDA margins have remained stable over the analysis period.\n\n"
            else:
                out += "\n\n"

        out += "Period-wise profitability trend:\n\n"
        out += _table_header(["Period", "Revenue", "EBITDA", "EBITDA %", "PAT", "PAT %"])
        for p in periods:
            pd_data = fs["periods"][p]
            out += _table_row([
                p,
                _format_cr(pd_data.get("revenue_cr")),
                _format_cr(pd_data.get("ebitda_cr")),
                _format_pct(pd_data.get("ebitda_margin_pct")),
                _format_cr(pd_data.get("pat_cr")),
                _format_pct(pd_data.get("pat_margin_pct")),
            ])
        out += "\n"

    # Balance sheet strength
    out += "**Balance Sheet Strength:**\n\n"
    if latest:
        de = latest.get("total_debt_cr", 0) / latest.get("net_worth_cr", 1) if latest.get("net_worth_cr", 0) > 0 else float('inf')
        out += (f"As of {periods[-1]}, the Company's net worth stands at {_format_cr(latest.get('net_worth_cr'))} "
                f"against total debt of {_format_cr(latest.get('total_debt_cr'))}, "
                f"yielding a Debt-to-Equity ratio of {de:.2f}x. ")

        ca = latest.get("current_assets_cr", 0)
        cl = latest.get("current_liabilities_cr", 0)
        if cl > 0:
            cr = ca / cl
            out += (f"The current ratio stands at {cr:.2f}x "
                    f"(current assets {_format_cr(ca)} vs current liabilities {_format_cr(cl)}).")
        out += "\n\n"

        if len(periods) >= 2:
            first_data = fs["periods"][periods[0]]
            first_de = first_data.get("total_debt_cr", 0) / first_data.get("net_worth_cr", 1) if first_data.get("net_worth_cr", 0) > 0 else 0
            if de < first_de:
                out += "The leverage position has improved over the analysis period, indicating effective deleveraging.\n\n"
            elif de > first_de:
                out += "Leverage has increased over the analysis period, warranting close monitoring of debt servicing capacity.\n\n"

    # Cash flow analysis
    out += "**Cash Flow Analysis:**\n\n"
    for p in periods:
        pd_data = fs["periods"][p]
        ocf = pd_data.get("operating_cash_flow_cr")
        capex = pd_data.get("capex_cr")
        if ocf is not None:
            out += f"- **{p}:** Operating cash flow of {_format_cr(ocf)}"
            if capex:
                fcf = ocf - capex
                out += f", Capex of {_format_cr(capex)}, Free Cash Flow of {_format_cr(fcf)}"
            out += ".\n"
    out += "\n"

    if latest.get("operating_cash_flow_cr") and latest.get("pat_cr"):
        accrual_quality = latest["operating_cash_flow_cr"] / latest["pat_cr"] if latest["pat_cr"] != 0 else 0
        out += (f"Cash flow quality: Operating CF / PAT = {accrual_quality:.2f}x for {periods[-1]}. ")
        if accrual_quality > 1.0:
            out += "Cash generation is strong relative to reported profits, indicating healthy earnings quality.\n\n"
        elif accrual_quality > 0.5:
            out += "Cash conversion is adequate though some working capital build-up is evident.\n\n"
        elif accrual_quality > 0:
            out += "Cash generation is weak relative to reported profits — working capital or receivable quality requires review.\n\n"
        else:
            out += "Negative operating cash flows despite reported profits — significant accrual quality concern.\n\n"

    # Working capital analysis
    out += "**Working Capital Analysis:**\n\n"
    for p in periods:
        r = ra.get(p, {})
        dd = r.get("debtor_days", {}).get("value")
        invd = r.get("inventory_days", {}).get("value")
        pd_val = r.get("payable_days", {}).get("value")
        wcc = r.get("working_capital_cycle", {}).get("value")
        if dd is not None:
            inv_str = f"{invd:.0f}" if invd is not None else "N/A"
            pay_str = f"{pd_val:.0f}" if pd_val is not None else "N/A"
            wcc_str = f"{wcc:.0f}" if wcc is not None else "N/A"
            out += (f"- **{p}:** Debtor Days: {dd:.0f} | Inventory Days: {inv_str} | "
                    f"Payable Days: {pay_str} | Working Capital Cycle: {wcc_str} days\n")
    out += "\n"

    if len(periods) >= 2:
        latest_wcc = ra.get(periods[-1], {}).get("working_capital_cycle", {}).get("value")
        first_wcc = ra.get(periods[0], {}).get("working_capital_cycle", {}).get("value")
        if latest_wcc and first_wcc:
            if latest_wcc > first_wcc + 10:
                out += ("The working capital cycle has elongated, indicating potential inefficiency in "
                        "receivable collection or inventory management. This trend requires monitoring.\n\n")
            elif latest_wcc < first_wcc - 10:
                out += ("The working capital cycle has contracted, suggesting improved operational efficiency "
                        "in managing receivables, inventory, and payables.\n\n")
            else:
                out += "The working capital cycle has remained broadly stable across the analysis period.\n\n"

    # Debt servicing
    out += "**Debt Servicing Capacity:**\n\n"
    for p in periods:
        r = ra.get(p, {})
        icr = r.get("interest_coverage_ratio", {}).get("value")
        dscr_val = r.get("dscr", {}).get("value")
        de_val = r.get("debt_to_equity", {}).get("value")
        if icr is not None:
            out += (f"- **{p}:** ICR: {icr:.2f}x | DSCR: {dscr_val:.2f}x | "
                    f"D/E: {de_val:.2f}x | Debt/EBITDA: {r.get('debt_to_ebitda', {}).get('value', 0):.2f}x\n")
    out += "\n"

    latest_icr = ra.get(periods[-1], {}).get("interest_coverage_ratio", {}).get("value") if periods else None
    if latest_icr:
        if latest_icr > 3.0:
            out += f"The interest coverage ratio of {latest_icr:.2f}x provides comfortable headroom for debt servicing.\n\n"
        elif latest_icr > 1.5:
            out += f"The interest coverage ratio of {latest_icr:.2f}x is adequate though leaves limited buffer for adverse scenarios.\n\n"
        else:
            out += f"The interest coverage ratio of {latest_icr:.2f}x is concerning and indicates significant debt servicing strain.\n\n"

    return out


def render_benchmark_analysis(fp: dict) -> str:
    """Render benchmark comparison."""
    bs = fp["benchmark_summary"]
    out = _header("5. INDUSTRY BENCHMARK ANALYSIS")
    out += f"**Sector:** {bs['sector'].title()} | **Period:** {bs['period']}\n\n"

    if bs["benchmarks"]:
        out += _header("5.1 Full Benchmark Comparison", 3)
        out += _table_header(["Metric", "Borrower", "Peer P25", "Peer Median", "Peer P75", "Status", "Severity"])
        for bm in bs["benchmarks"]:
            metric_display = bm["metric"].replace("_", " ").title()
            out += _table_row([
                metric_display,
                f"{bm['borrower']:.2f}",
                f"{bm['peer_p25']:.2f}",
                f"{bm['peer_median']:.2f}",
                f"{bm['peer_p75']:.2f}",
                bm["status"].replace("_", " ").title(),
                _severity_badge(bm["severity"]),
            ])
        out += "\n"

    if bs.get("worst_performers"):
        out += _header("5.2 Key Concerns vs Peers", 3)
        for bm in bs["worst_performers"]:
            out += f"- **{bm['metric'].replace('_', ' ').title()}**: "
            out += f"Borrower = {bm['borrower']:.2f} vs Peer Median = {bm['peer_median']:.2f} "
            out += f"({_severity_badge(bm['severity'])})\n"
        out += "\n"

    # Peer positioning commentary
    out += _header("5.3 Peer Positioning Commentary", 3)
    total = len(bs["benchmarks"]) if bs["benchmarks"] else 0
    worse = len([b for b in bs["benchmarks"] if b["status"] == "worse_than_peer"]) if bs["benchmarks"] else 0
    better = len([b for b in bs["benchmarks"] if b["status"] == "better_than_peer"]) if bs["benchmarks"] else 0
    inline = total - worse - better

    out += (f"Out of {total} benchmark metrics analyzed, the borrower positions "
            f"**better than peers** on {better} metric(s), **in line with peers** on "
            f"{inline} metric(s), and **worse than peers** on {worse} metric(s).\n\n")

    if worse == 0:
        out += ("The Company demonstrates a strong competitive positioning relative to sector peers "
                "across all key financial metrics. No significant deviations from peer benchmarks "
                "have been identified.\n\n")
    elif worse <= total * 0.3:
        out += ("While the majority of financial metrics are at or above peer levels, "
                f"there are {worse} area(s) of concern that require monitoring. "
                "These deviations are not systemic but should be tracked as part of "
                "ongoing credit supervision.\n\n")
    elif worse <= total * 0.6:
        out += (f"With {worse} metrics below peer benchmarks, the Company shows mixed positioning "
                "relative to the sector. The credit assessment should factor in these weaknesses "
                "alongside the Company's strengths in other areas. Structural improvement in "
                "lagging metrics should be a condition for continued support.\n\n")
    else:
        out += (f"The Company significantly underperforms peers on {worse} out of {total} metrics, "
                "indicating fundamental financial challenges relative to the sector. "
                "This poor peer positioning warrants conservative terms and enhanced monitoring.\n\n")

    if bs.get("worst_performers"):
        out += "**Key areas requiring management attention:**\n\n"
        for i, bm in enumerate(bs["worst_performers"], 1):
            metric = bm["metric"].replace("_", " ").title()
            gap = abs(bm["borrower"] - bm["peer_median"])
            direction = "above" if bm["borrower"] > bm["peer_median"] else "below"
            out += (f"{i}. **{metric}** — The borrower's value of {bm['borrower']:.2f} is "
                    f"{gap:.2f} {direction} the peer median of {bm['peer_median']:.2f}. ")
            if "debt" in bm["metric"].lower() or "leverage" in bm["metric"].lower():
                out += "This indicates relatively higher leverage which could impact debt servicing capacity.\n"
            elif "margin" in bm["metric"].lower() or "return" in bm["metric"].lower():
                out += "This suggests weaker profitability relative to peers, potentially reflecting pricing pressure or cost inefficiencies.\n"
            elif "days" in bm["metric"].lower() or "cycle" in bm["metric"].lower():
                out += "Extended working capital indicates potential collection or inventory management concerns.\n"
            elif "coverage" in bm["metric"].lower() or "dscr" in bm["metric"].lower():
                out += "Weaker debt servicing coverage reduces the margin of safety for lenders.\n"
            else:
                out += "This deviation from peers warrants close monitoring.\n"
        out += "\n"

    return out


def render_collateral_analysis(fp: dict) -> str:
    """Render collateral / security analysis."""
    ca = fp["collateral_analysis"]
    out = _header("6. COLLATERAL / SECURITY ANALYSIS")

    out += _table_header(["Collateral", "Description", "Market Value (Cr)", "Forced Sale Value (Cr)", "Valuation Date", "Encumbrance"])
    for c in ca["collaterals"]:
        out += _table_row([
            c["type"], c["description"],
            _format_cr(c["market_value_cr"]),
            _format_cr(c["forced_sale_value_cr"]),
            c["valuation_date"], c["encumbrance"],
        ])
    out += "\n"

    out += _table_header(["Summary", "Value"])
    out += _table_row(["Total Market Value", _format_cr(ca["total_market_value_cr"])])
    out += _table_row(["Total Forced Sale Value", _format_cr(ca["total_forced_sale_value_cr"])])
    out += _table_row(["Facility Amount", _format_cr(ca["facility_amount_cr"])])
    out += _table_row(["Coverage (Market)", f"{ca['coverage_ratio_market']:.2f}x"])
    out += _table_row(["Coverage (FSV)", f"{ca['coverage_ratio_fsv']:.2f}x"])
    out += "\n"

    return out


def render_conduct_analysis(fp: dict) -> str:
    """Render ETB conduct analysis."""
    ca = fp["conduct_analysis"]
    out = _header("7. BANKING CONDUCT ANALYSIS")

    if not ca.get("available"):
        out += f"*{ca.get('note', 'No conduct data available.')}*\n\n"
        return out

    out += f"**Quarters Analyzed:** {ca['quarters_analyzed']}  \n"
    out += f"**Total Cheque Returns:** {ca['total_cheque_returns']}  \n"
    out += f"**Max DPD:** {ca['max_dpd_overall']} days  \n"
    out += f"**Average Utilization:** {ca['avg_utilization_pct']}%  \n"
    out += f"**Utilization Trend:** {ca['utilization_trend'].title()}\n\n"

    out += _table_header(["Period", "Avg Balance (Cr)", "Credit Turnover (Cr)", "Cheque Returns",
                          "Utilization %", "Max Overdue Days", "DPD 30+", "DPD 60+"])
    for r in ca["records"]:
        out += _table_row([
            r["period"], _format_cr(r["avg_balance_cr"]), _format_cr(r["credit_turnover_cr"]),
            r["cheque_returns"], f"{r['utilization_pct']:.1f}%",
            r["max_overdue_days"], r["dpd_30_count"], r["dpd_60_count"],
        ])
    out += "\n"

    return out


def render_covenant_history(fp: dict) -> str:
    """Render covenant compliance history."""
    ch = fp["covenant_history"]
    if not ch:
        return ""

    out = _header("7.1 Covenant Compliance History")
    out += _table_header(["Covenant", "Required", "Actual", "Status", "Period", "Details"])
    for c in ch:
        status_display = "✅ Compliant" if c["status"] == "compliant" else "❌ BREACHED"
        out += _table_row([c["type"], c["required"], c["actual"], status_display, c["period"], c["details"]])
    out += "\n"
    return out


def render_external_intelligence(fp: dict) -> str:
    """Render external data intelligence."""
    ei = fp["external_intelligence"]
    ms = fp["market_signals"]

    out = _header("8. EXTERNAL INTELLIGENCE")

    out += _header("8.1 Public Records / External Data", 3)
    out += _table_header(["Source", "Data Point", "Value"])
    out += _table_row(["MCA", "Company Status", ei.get("mca_status", "N/A")])
    out += _table_row(["Public Records", "Credit Score", ei.get("bureau_score", "N/A")])
    out += _table_row(["Public Records", "DPD Status", ei.get("bureau_dpd_status", "N/A")])
    out += _table_row(["Public Records", "Total Exposure", _format_cr(ei.get("bureau_total_exposure_cr"))])
    out += _table_row(["Public Records", "Total Lenders", ei.get("bureau_total_lenders", "N/A")])
    out += _table_row(["GST", "FY2024 Turnover", _format_cr(ei.get("gst_fy2024_turnover_cr"))])
    out += _table_row(["GST", "Filing Status", ei.get("gst_filing_status", "N/A")])
    out += _table_row(["Market", "Overall Sentiment", ei.get("market_sentiment", "N/A")])
    out += _table_row(["Market", "Reputation Risk", ei.get("reputation_risk", "N/A")])
    out += "\n"

    if ei.get("rating_action"):
        ra = ei["rating_action"]
        out += _header("8.2 Latest Rating Action", 3)
        out += _table_header(["Parameter", "Value"])
        out += _table_row(["Agency", ra.get("rating_agency", "N/A")])
        out += _table_row(["Long-term Rating", ra.get("long_term_rating", "N/A")])
        out += _table_row(["Outlook", ra.get("outlook", "N/A")])
        out += _table_row(["Last Action", ra.get("last_action", "N/A")])
        out += _table_row(["Action Date", ra.get("action_date", "N/A")])
        out += _table_row(["Rationale", ra.get("rationale_summary", "N/A")])
        out += "\n"

    if ms:
        out += _header("8.3 Market / News / Social Signals", 3)
        out += _table_header(["Date", "Type", "Headline", "Sentiment", "Severity", "Source"])
        for s in ms:
            out += _table_row([
                s["date"], s["type"].title(), s["headline"],
                s["sentiment"].title(), _severity_badge(s["severity"]), s["source"],
            ])
        out += "\n"

    return out


def render_validation_summary(fp: dict) -> str:
    """Render validation exceptions."""
    exceptions = fp["validation_exceptions"]
    out = _header("9. VALIDATION & EXCEPTION SUMMARY")

    if not exceptions:
        out += "**No validation exceptions detected.** All checks passed.\n\n"
        return out

    out += f"**Total Exceptions:** {len(exceptions)}\n\n"

    critical = [e for e in exceptions if e["severity"] == "critical"]
    high = [e for e in exceptions if e["severity"] == "high"]
    medium = [e for e in exceptions if e["severity"] == "medium"]

    out += f"- 🔴 Critical: {len(critical)}\n"
    out += f"- 🟠 High: {len(high)}\n"
    out += f"- 🟡 Medium: {len(medium)}\n\n"

    out += _table_header(["#", "Code", "Severity", "Description", "Expected", "Observed", "Status"])
    for i, e in enumerate(exceptions, 1):
        out += _table_row([
            i, e["code"], _severity_badge(e["severity"]),
            e["description"][:120], e.get("expected") or "-",
            e.get("observed") or "-", e["status"],
        ])
    out += "\n"

    return out


def render_risk_assessment(fp: dict) -> str:
    """Render risk assessment / policy decision summary."""
    pd = fp["policy_decisions"]
    t1 = pd["tier1_hard_rules"]
    t2 = pd["tier2_risk_scores"]
    t3 = pd["tier3_recommendation"]

    out = _header("10. RISK ASSESSMENT & POLICY DECISIONS")

    out += _header("10.1 Hard Rule Checks (Tier 1)", 3)
    out += _table_header(["Rule", "Description", "Result", "Details"])
    for r in t1:
        result_icon = "✅ PASS" if r["result"] == "pass" else "❌ FAIL"
        out += _table_row([r["rule"], r["description"], result_icon, r["details"]])
    out += "\n"

    out += _header("10.2 Risk Scores (Tier 2)", 3)
    out += _table_header(["Component", "Score (0-100)"])
    out += _table_row(["Financial Score", t2["financial_score"]])
    out += _table_row(["Conduct Score", t2["conduct_score"]])
    out += _table_row(["Governance Score", t2["governance_score"]])
    out += _table_row(["Market Score", t2["market_score"]])
    out += _table_row(["**Composite Score**", f"**{t2['composite_score']}**"])
    out += _table_row(["**Risk Grade**", f"**{t2['risk_grade']}**"])
    out += "\n"

    out += f"*Weights: Financial 40% | Conduct 25% | Governance 20% | Market 15%*\n\n"

    # Risk narrative
    out += _header("10.3 Risk Narrative", 3)

    grade = t2["risk_grade"]
    composite = t2["composite_score"]
    fin_score = t2["financial_score"]
    cond_score = t2["conduct_score"]
    gov_score = t2["governance_score"]
    mkt_score = t2["market_score"]

    grade_descriptions = {
        "A": "strong credit profile with well-managed risks",
        "B": "acceptable credit profile with manageable risks",
        "C": "marginal credit profile requiring close monitoring",
        "D": "weak credit profile with significant concerns",
        "E": "poor credit profile with critical risk factors",
    }
    out += (f"The borrower's composite risk score of **{composite}** places it in "
            f"**Grade {grade}**, indicating a **{grade_descriptions.get(grade, 'reviewed')}**.\n\n")

    out += "**Component-wise Assessment:**\n\n"

    # Financial risk
    if fin_score >= 75:
        fin_assessment = "The financial profile is strong, with key ratios broadly in line with or exceeding peer benchmarks."
    elif fin_score >= 55:
        fin_assessment = "The financial profile is adequate with some areas of concern. Key leverage and coverage metrics are within acceptable bands but with limited headroom."
    else:
        fin_assessment = "The financial profile is weak, with multiple metrics below acceptable thresholds. Debt servicing capacity, leverage, and profitability require significant improvement."
    out += f"1. **Financial Risk (Score: {fin_score}, Weight: 40%):** {fin_assessment}\n\n"

    # Conduct risk
    if cond_score >= 75:
        cond_assessment = "Banking conduct is satisfactory with no significant operational concerns."
    elif cond_score >= 55:
        cond_assessment = "Banking conduct shows some warning signs that require monitoring, including limit utilization patterns and occasional overdue incidents."
    else:
        cond_assessment = "Banking conduct is concerning with persistent overdues, high cheque returns, and/or covenant breaches indicating operational stress and potential repayment challenges."
    out += f"2. **Conduct Risk (Score: {cond_score}, Weight: 25%):** {cond_assessment}\n\n"

    # Governance risk
    if gov_score >= 75:
        gov_assessment = "Governance quality is strong with experienced management, appropriate board composition, and positive external ratings."
    elif gov_score >= 55:
        gov_assessment = "Governance is adequate but may benefit from strengthening independent representation or addressing rating agency observations."
    else:
        gov_assessment = "Governance concerns exist, potentially including negative rating actions, limited independent oversight, or complex group structures that could obscure true risk."
    out += f"3. **Governance Risk (Score: {gov_score}, Weight: 20%):** {gov_assessment}\n\n"

    # Market risk
    if mkt_score >= 75:
        mkt_assessment = "External market signals are broadly positive or neutral. No adverse media, regulatory, or reputation events have been identified."
    elif mkt_score >= 55:
        mkt_assessment = "Some mixed signals from external sources — isolated negative news or mild reputational concerns exist but are not systemic."
    else:
        mkt_assessment = "Significant adverse market signals have been detected, including negative media coverage, regulatory concerns, or deteriorating market reputation that could impact the borrower's business relationships and credit standing."
    out += f"4. **Market Risk (Score: {mkt_score}, Weight: 15%):** {mkt_assessment}\n\n"

    # Overall risk summary
    exceptions = fp["validation_exceptions"]
    critical_count = sum(1 for e in exceptions if e["severity"] == "critical")
    high_count = sum(1 for e in exceptions if e["severity"] == "high")
    medium_count = sum(1 for e in exceptions if e["severity"] == "medium")

    out += "**Key Risk Factors:**\n\n"
    if critical_count + high_count == 0:
        out += "- No critical or high-severity validation exceptions were identified, indicating a clean data submission with consistent financials across sources.\n"
    else:
        if critical_count > 0:
            out += f"- {critical_count} CRITICAL exception(s) require immediate resolution before credit decision.\n"
        if high_count > 0:
            out += f"- {high_count} HIGH severity exception(s) detected that materially impact credit assessment.\n"
        for e in exceptions:
            if e["severity"] in ("critical", "high"):
                out += f"  - *{e['code']}*: {e['description'][:200]}\n"
    if medium_count > 0:
        out += f"- {medium_count} MEDIUM severity exception(s) noted for monitoring purposes.\n"
    out += "\n"

    # Mitigants
    bp = fp["borrower_profile"]
    ca = fp["collateral_analysis"]
    out += "**Risk Mitigants:**\n\n"
    if bp.get("credit_rating") and ("A" in bp["credit_rating"].upper()):
        out += f"- External credit rating ({bp['credit_rating']} by {bp.get('rating_agency', 'N/A')}) provides independent validation of credit quality.\n"
    if bp.get("listed_exchange"):
        out += f"- Listed on {bp['listed_exchange']} — subject to enhanced disclosure requirements and market discipline.\n"
    if ca["coverage_ratio_fsv"] >= 1.5:
        out += f"- Collateral coverage (FSV) of {ca['coverage_ratio_fsv']:.2f}x provides adequate security.\n"
    elif ca["coverage_ratio_fsv"] >= 1.0:
        out += f"- Collateral coverage (FSV) of {ca['coverage_ratio_fsv']:.2f}x provides baseline security.\n"
    out += "\n"

    return out


def render_recommendation(fp: dict) -> str:
    """Render final recommendation."""
    t3 = fp["policy_decisions"]["tier3_recommendation"]

    out = _header("11. RECOMMENDATION")

    out += f"### Recommendation: **{t3['recommendation'].replace('_', ' ').upper()}**\n\n"
    out += f"**Risk Grade:** {t3['risk_grade']} | **Composite Score:** {t3['composite_score']}\n\n"
    out += f"**Rationale:** {t3['rationale']}\n\n"

    if t3.get("conditions"):
        out += _header("11.1 Conditions Precedent", 3)
        for i, c in enumerate(t3["conditions"], 1):
            out += f"{i}. {c}\n"
        out += "\n"

    if t3.get("covenants_proposed"):
        out += _header("11.2 Proposed Covenants", 3)
        for i, c in enumerate(t3["covenants_proposed"], 1):
            out += f"{i}. {c}\n"
        out += "\n"

    out += _header("11.3 Collateral Requirement", 3)
    out += f"{t3['collateral_requirement']}\n\n"

    if t3.get("monitoring_conditions"):
        out += _header("11.4 Monitoring Conditions", 3)
        for i, m in enumerate(t3["monitoring_conditions"], 1):
            out += f"{i}. {m}\n"
        out += "\n"

    if t3.get("exception_notes"):
        out += _header("11.5 Exception Notes", 3)
        for note in t3["exception_notes"]:
            out += f"- {note}\n"
        out += "\n"

    return out


def render_audit_trail(fp: dict) -> str:
    """Render pipeline audit trail."""
    meta = fp["meta"]
    out = _header("12. AUDIT TRAIL & REPRODUCIBILITY")
    out += _table_header(["Parameter", "Value"])
    out += _table_row(["Generated Date", meta["generated_date"]])
    out += _table_row(["Pipeline Version", meta["pipeline_version"]])
    out += _table_row(["Parser Version", meta["parser_version"]])
    out += _table_row(["Rule Pack Version", meta["rule_pack_version"]])
    out += _table_row(["Benchmark Pack Version", meta["benchmark_pack_version"]])
    out += _table_row(["Deterministic", "Yes" if meta["deterministic"] else "No"])
    out += "\n"
    out += "*This CAM was generated by a deterministic pipeline. Given the same input documents, "
    out += "source priority rules, parser version, rule pack, and benchmark dataset, this memo "
    out += "will produce identical output. No LLM-generated facts — all numbers and ratios "
    out += "computed by deterministic engines. Narrative sections are template-driven with citations "
    out += "to the approved fact pack.*\n\n"
    return out


def render_disclaimer(fp: dict) -> str:
    """Render standard disclaimer."""
    out = _header("DISCLAIMER")
    out += ("This Credit Approval Memorandum has been generated through an automated deterministic "
            "pipeline. All financial data, ratios, validations, benchmarks, and policy decisions are "
            "computed from the source documents and external data provided. The narrative sections "
            "are template-driven and trace back to the approved factual dataset.\n\n"
            "This document is intended for internal credit assessment purposes only and does not "
            "constitute a binding commitment to lend. All information should be independently "
            "verified by the sanctioning authority. The final credit decision rests with the "
            "appropriate approving authority as per the bank's delegation of powers.\n\n")
    out += "---\n"
    out += f"*End of Credit Approval Memorandum — {fp['borrower_profile']['company_name']}*\n"
    return out


def render_data_sources_appendix(fp: dict) -> str:
    """Render data source provenance appendix — traceability of every data point."""
    sources = fp.get("data_sources", [])
    if not sources:
        return ""

    out = _header("APPENDIX A — DATA SOURCES & PROVENANCE")

    out += ("This appendix provides a complete audit trail of all external and internal data sources "
            "used in the preparation of this Credit Approval Memorandum. Each data point in this CAM "
            "can be traced to the source system listed below.\n\n")

    out += _table_header(["#", "Data Source", "Source System", "Entity Key", "Fetch Status", "CAM Sections"])
    for i, src in enumerate(sources, 1):
        status_icon = "✅" if src["fetch_status"] == "success" else "⚠️" if src["fetch_status"] == "n/a" else "❌"
        sections = ", ".join(src["cam_sections_using"])
        out += _table_row([
            i,
            src["source_name"],
            src["source_system"],
            src["entity_key"],
            f"{status_icon} {src['fetch_status'].title()}",
            sections,
        ])
    out += "\n"

    out += "**Data Freshness:**\n\n"
    out += f"- All external data fetched as of: {fp['meta']['generated_date']}\n"
    out += "- Financial data: Based on audited statements uploaded by the analyst\n"
    out += "- Bureau data: Real-time pull from credit information company\n"
    out += "- Rating data: Latest available rating action from credit rating agency\n"
    out += "- Market signals: Aggregated from news & sentiment feeds (90-day window)\n\n"

    out += "**Source Priority Rules:**\n\n"
    out += "1. Audited financials take precedence over provisional/estimated data\n"
    out += "2. Bureau data overrides self-declared exposure information\n"
    out += "3. GST turnover is cross-validated against reported revenue\n"
    out += "4. MCA filing data is treated as ground truth for corporate identity\n"
    out += "5. Market signals are informational — do not override quantitative scores\n\n"

    return out


# ═══════════════════════════════════════════════════════════════════════════════
# MASTER RENDERER
# ═══════════════════════════════════════════════════════════════════════════════

def render_complete_cam(fact_pack: dict) -> str:
    """Render the complete CAM document from the fact pack."""
    sections = [
        render_cover_page(fact_pack),
        render_table_of_contents(fact_pack),
        render_360_overview(fact_pack),
        render_executive_summary(fact_pack),
        render_borrower_profile(fact_pack),
        render_corporate_hierarchy(fact_pack),
        render_facility_details(fact_pack),
        render_financial_analysis(fact_pack),
        render_credit_strengths(fact_pack),
        render_key_risks(fact_pack),
        render_cash_flow_repayment(fact_pack),
        render_benchmark_analysis(fact_pack),
        render_collateral_analysis(fact_pack),
        render_conduct_analysis(fact_pack),
        render_covenant_history(fact_pack),
        render_external_intelligence(fact_pack),
        render_esg_regulatory(fact_pack),
        render_validation_summary(fact_pack),
        render_risk_assessment(fact_pack),
        render_recommendation(fact_pack),
        render_lending_decision(fact_pack),
        render_audit_trail(fact_pack),
        render_data_sources_appendix(fact_pack),
        render_disclaimer(fact_pack),
    ]
    return "\n".join(sections)


# ═══════════════════════════════════════════════════════════════════════════════
# NEW SECTIONS: 360° View, Hierarchy, Strengths, Risks, Cash Flow, ESG, Decision
# ═══════════════════════════════════════════════════════════════════════════════

def render_360_overview(fp: dict) -> str:
    """Render 360° overview at the beginning of the CAM."""
    cs = fp["case_summary"]
    bp = fp["borrower_profile"]
    fs = fp["financial_summary"]
    rec = fp["policy_decisions"]["tier3_recommendation"]
    scores = fp["policy_decisions"]["tier2_risk_scores"]
    ei = fp["external_intelligence"]
    strengths = fp.get("credit_strengths", [])
    risks = fp.get("key_risks", [])

    periods = sorted(fs["periods"].keys())
    latest = fs["periods"][periods[-1]] if periods else {}

    out = _header("360° CREDIT OVERVIEW", 1)
    out += "---\n\n"

    # Key metrics grid
    out += _table_header(["Metric", "Value", "Metric", "Value"])
    out += _table_row([
        "Company", bp["company_name"],
        "Sector", f"{cs['sector'].title()} — {cs['subsector']}",
    ])
    out += _table_row([
        "Revenue", _format_cr(latest.get("revenue_cr")),
        "EBITDA", _format_cr(latest.get("ebitda_cr")),
    ])
    out += _table_row([
        "PAT", _format_cr(latest.get("pat_cr")),
        "Net Worth", _format_cr(latest.get("net_worth_cr")),
    ])
    out += _table_row([
        "Total Debt", _format_cr(latest.get("total_debt_cr")),
        "Facility Requested", _format_cr(cs["amount_requested_cr"]),
    ])
    out += _table_row([
        "Credit Rating", bp.get("credit_rating") or "N/A",
        "Public-Record Score", ei.get("bureau_score") or "N/A",
    ])
    out += _table_row([
        "Risk Grade", f"**{scores['risk_grade']}** ({scores['composite_score']})",
        "Recommendation", f"**{rec['recommendation'].replace('_', ' ').upper()}**",
    ])
    out += "\n"

    # Score breakdown
    out += "**Risk Score Breakdown:** "
    out += f"Financial: {scores['financial_score']} | Conduct: {scores['conduct_score']} | "
    out += f"Governance: {scores['governance_score']} | Market: {scores['market_score']}\n\n"

    # Top strengths
    if strengths:
        out += "**Key Strengths:**\n"
        for s in strengths[:5]:
            out += f"- ✅ **{s['category']}:** {s['detail']}\n"
        out += "\n"

    # Top risks
    if risks:
        out += "**Key Risks:**\n"
        for r in risks[:5]:
            sev = r.get("severity", "medium")
            icon = "🔴" if sev == "critical" else "🟠" if sev == "high" else "🟡"
            out += f"- {icon} **{r['category']}:** {r['detail']}\n"
        out += "\n"

    out += "---\n\n"
    return out


def render_corporate_hierarchy(fp: dict) -> str:
    """Render corporate group hierarchy section."""
    ch = fp.get("corporate_hierarchy", {})
    if not ch:
        return ""

    out = _header("2.4 Corporate Hierarchy & Group Structure", 3)
    out += f"**Group Name:** {ch.get('group_name', 'Standalone')}  \n"
    out += f"**Ultimate Parent:** {ch.get('ultimate_parent', 'N/A')}  \n"
    out += f"**Group Entities:** {ch.get('entity_count', 1)}  \n\n"

    if ch.get("group_revenue_cr"):
        out += _table_header(["Group Metric", "Value"])
        out += _table_row(["Group Revenue", _format_cr(ch.get("group_revenue_cr"))])
        out += _table_row(["Group Net Worth", _format_cr(ch.get("group_net_worth_cr"))])
        out += _table_row(["Group Total Debt", _format_cr(ch.get("group_total_debt_cr"))])
        out += "\n"

    tree = ch.get("hierarchy_tree", [])
    if tree:
        out += "**Corporate Structure:**\n\n"
        out += _render_hierarchy_tree(tree, depth=0)
        out += "\n"

        # Detailed table of group entities
        all_entities = _flatten_hierarchy(tree)
        if len(all_entities) > 1:
            out += _table_header(["Entity", "Relationship", "Holding %", "Sector", "Revenue (Cr)", "Rating"])
            for e in all_entities:
                out += _table_row([
                    e["company_name"],
                    e["relationship"].title(),
                    f"{e['holding_pct']:.0f}%" if e["holding_pct"] else "N/A",
                    e.get("sector") or "N/A",
                    _format_cr(e.get("revenue_cr")) if e.get("revenue_cr") else "N/A",
                    e.get("credit_rating") or "N/A",
                ])
            out += "\n"

    return out


def _render_hierarchy_tree(nodes: list, depth: int = 0) -> str:
    """Render hierarchy tree as indented text."""
    out = ""
    for node in nodes:
        indent = "  " * depth
        icon = "🏢" if depth == 0 else "├── " if node.get("relationship") == "subsidiary" else "└── "
        rel = f" ({node['relationship'].title()})" if depth > 0 else ""
        holding = f" [{node['holding_pct']:.0f}%]" if node.get("holding_pct") and depth > 0 else ""
        out += f"{indent}{icon}**{node['company_name']}**{rel}{holding}\n"
        if node.get("children"):
            out += _render_hierarchy_tree(node["children"], depth + 1)
    return out


def _flatten_hierarchy(nodes: list) -> list:
    """Flatten hierarchy tree to a list."""
    result = []
    for node in nodes:
        result.append(node)
        if node.get("children"):
            result.extend(_flatten_hierarchy(node["children"]))
    return result


def render_credit_strengths(fp: dict) -> str:
    """Render credit strengths section."""
    strengths = fp.get("credit_strengths", [])
    if not strengths:
        return ""

    out = _header("CREDIT STRENGTHS")
    out += _table_header(["#", "Category", "Strength"])
    for i, s in enumerate(strengths, 1):
        out += _table_row([i, s["category"], s["detail"]])
    out += "\n"
    return out


def render_key_risks(fp: dict) -> str:
    """Render key risks section."""
    risks = fp.get("key_risks", [])
    if not risks:
        return ""

    out = _header("KEY RISKS & CONCERNS")
    out += _table_header(["#", "Category", "Severity", "Risk"])
    for i, r in enumerate(risks, 1):
        sev = r.get("severity", "medium")
        out += _table_row([i, r["category"], _severity_badge(sev), r["detail"]])
    out += "\n"
    return out


def render_cash_flow_repayment(fp: dict) -> str:
    """Render cash flow & repayment analysis."""
    cfr = fp.get("cash_flow_repayment", {})
    if not cfr:
        return ""

    out = _header("CASH FLOW & REPAYMENT ANALYSIS")

    periods = sorted(cfr.get("periods", {}).keys())
    if periods:
        out += _table_header(["Period", "Operating CF (Cr)", "Capex (Cr)", "Free CF (Cr)", "EBITDA (Cr)"])
        for p in periods:
            d = cfr["periods"][p]
            out += _table_row([
                p,
                _format_cr(d.get("operating_cash_flow_cr")),
                _format_cr(d.get("capex_cr")),
                _format_cr(d.get("free_cash_flow_cr")),
                _format_cr(d.get("ebitda_cr")),
            ])
        out += "\n"

    rep = cfr.get("repayment_capacity", {})
    if rep:
        out += "**Repayment Capacity Assessment:**\n\n"
        out += _table_header(["Metric", "Value"])
        out += _table_row(["Annual EBITDA", _format_cr(rep.get("annual_ebitda_cr"))])
        out += _table_row(["Annual Interest", _format_cr(rep.get("annual_interest_cr"))])
        out += _table_row(["Annual Repayment", _format_cr(rep.get("annual_repayment_cr"))])
        out += _table_row(["Estimated Surplus", _format_cr(rep.get("estimated_surplus_cr"))])
        out += _table_row(["DSCR", f"{cfr.get('dscr', 'N/A')}"])
        adequate = "✅ **ADEQUATE**" if rep.get("adequate") else "❌ **INADEQUATE**"
        out += _table_row(["Assessment", adequate])
        out += "\n"

    return out


def render_esg_regulatory(fp: dict) -> str:
    """Render ESG & Regulatory compliance section."""
    esg = fp.get("esg_regulatory", {})
    if not esg:
        return ""

    out = _header("ESG & REGULATORY COMPLIANCE")

    env = esg.get("environmental", {})
    soc = esg.get("social", {})
    gov = esg.get("governance", {})
    reg = esg.get("regulatory", {})

    out += _table_header(["Category", "Parameter", "Status"])
    out += _table_row(["Environmental", "Sector Risk", env.get("sector_risk", "N/A")])
    out += _table_row(["Environmental", "Compliance", env.get("compliance_status", "N/A")])
    out += _table_row(["Social", "Employee Count", soc.get("employee_count") or "N/A"])
    out += _table_row(["Social", "EPFO Compliance", soc.get("epfo_compliant", "N/A")])
    out += _table_row(["Governance", "Listed", "Yes" if gov.get("listed") else "No"])
    out += _table_row(["Governance", "Board Composition", gov.get("board_composition", "N/A")])
    out += _table_row(["Regulatory", "RBI Compliance", reg.get("rbi_compliance", "N/A")])
    out += _table_row(["Regulatory", "SEBI Compliance", reg.get("sebi_compliance", "N/A")])
    out += _table_row(["Regulatory", "GST Filing", reg.get("gst_filing", "N/A")])
    out += _table_row(["Regulatory", "ITR Filing", reg.get("itr_filing", "N/A")])
    out += "\n"

    return out


def render_lending_decision(fp: dict) -> str:
    """Render final lending decision summary."""
    rec = fp["policy_decisions"]["tier3_recommendation"]
    scores = fp["policy_decisions"]["tier2_risk_scores"]
    strengths = fp.get("credit_strengths", [])
    risks = fp.get("key_risks", [])
    cs = fp["case_summary"]

    out = _header("FINAL LENDING DECISION")
    out += "---\n\n"

    recommendation = rec["recommendation"].replace("_", " ").upper()
    out += f"### Decision: **{recommendation}**\n\n"
    out += f"**Facility:** {cs['facility_type'].replace('_', ' ').title()} — {_format_cr(cs['amount_requested_cr'])}  \n"
    out += f"**Risk Grade:** {scores['risk_grade']} (Composite: {scores['composite_score']})  \n\n"

    out += f"**Decision Rationale:** {rec['rationale']}\n\n"

    if strengths:
        out += "**Supporting Factors:**\n"
        for s in strengths[:3]:
            out += f"- ✅ {s['detail']}\n"
        out += "\n"

    if risks:
        out += "**Risk Factors to Monitor:**\n"
        for r in risks[:3]:
            out += f"- ⚠️ {r['detail']}\n"
        out += "\n"

    if rec.get("conditions"):
        out += "**Conditions:**\n"
        for i, c in enumerate(rec["conditions"], 1):
            out += f"{i}. {c}\n"
        out += "\n"

    out += "---\n\n"
    return out
