"""
One-Page Corporate Credit Appraisal Memo
==========================================
Generates an HTML one-pager from the fact pack with 9 sections:
1. Credit Appraisal Memo Summary (Header)
2. Business Profile
3. Financial Snapshot
4. Credit Strengths
5. Key Risks
6. Cash Flow & Repayment Analysis
7. Security & Collateral
8. Covenants / ESG / Regulatory
9. Final Credit View
"""

from datetime import date


def _fmt_cr(val) -> str:
    if val is None:
        return "N/A"
    return f"₹ {val:,.1f} Cr"


def _fmt_pct(val) -> str:
    if val is None:
        return "N/A"
    return f"{val:.1f}%"


def _grade_color(grade: str) -> str:
    colors = {"A": "#22c55e", "B": "#3b82f6", "C": "#f59e0b", "D": "#ef4444", "E": "#991b1b"}
    return colors.get(grade, "#888")


def _rec_color(rec: str) -> str:
    colors = {
        "approve": "#22c55e", "conditional_approve": "#3b82f6",
        "refer": "#f59e0b", "decline": "#ef4444",
    }
    return colors.get(rec, "#888")


def _rec_label(rec: str) -> str:
    return rec.replace("_", " ").upper() if rec else "PENDING"


def generate_one_pager_html(fact_pack: dict, case_result: dict) -> str:
    """Generate complete one-page HTML memo from fact pack and case result."""

    # Extract data — keys aligned with cam_fact_builder output
    borrower = fact_pack.get("borrower_profile", {})   # flat dict, not nested under 'company'
    company = borrower  # borrower_profile IS the company data (no 'company' sub-key)
    facility = fact_pack.get("facility_details", {})    # flat dict, no 'proposed' sub-key
    fin_summary = fact_pack.get("financial_summary", {})
    ratios = fact_pack.get("ratio_analysis", {})        # key is ratio_analysis not ratios
    collateral = fact_pack.get("collateral_analysis", {})
    hierarchy = fact_pack.get("corporate_hierarchy", {})
    strengths = fact_pack.get("credit_strengths", [])
    risks = fact_pack.get("key_risks", [])
    cash_flow = fact_pack.get("cash_flow_repayment", {})
    esg = fact_pack.get("esg_regulatory", {})
    benchmarks = fact_pack.get("benchmark_summary", {})
    # recommendation data comes from case_result, not fact_pack
    recommendation = {
        "conditions": case_result.get("conditions", []),
        "covenants_proposed": case_result.get("covenants_proposed", []),
        "rationale": case_result.get("rationale", ""),
    }
    risk_score = {}  # scores are directly on case_result
    validation = fact_pack.get("validation_exceptions", [])  # key is validation_exceptions
    conduct = fact_pack.get("conduct_analysis", {})     # key is conduct_analysis
    external = fact_pack.get("external_intelligence", {})

    # Derived values
    entity_id = case_result.get("entity_id", "")
    company_name = case_result.get("company_name", company.get("company_name", company.get("name", "")))
    sector = case_result.get("sector", company.get("sector", ""))
    rec = case_result.get("recommendation", "pending")
    risk_grade = case_result.get("risk_grade", risk_score.get("risk_grade", "N/A"))
    composite = case_result.get("composite_score", risk_score.get("composite_score", 0))
    financial_score = case_result.get("financial_score", risk_score.get("financial_score", 0))
    conduct_score = case_result.get("conduct_score", risk_score.get("conduct_score", 0))
    governance_score = case_result.get("governance_score", risk_score.get("governance_score", 0))
    market_score = case_result.get("market_score", risk_score.get("market_score", 0))

    # Financial periods
    periods = sorted(fin_summary.get("periods", {}).keys())
    latest_period = periods[-1] if periods else "N/A"
    latest_fin = fin_summary.get("periods", {}).get(latest_period, {}) if periods else {}

    # Latest ratios
    latest_ratios = ratios.get(latest_period, {}) if periods else {}

    # Build HTML
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Credit Appraisal Memo — {company_name}</title>
<style>
  @page {{ size: A4; margin: 8mm; }}
  @media print {{
    body {{ font-size: 8pt !important; }}
    .memo-page {{ box-shadow: none !important; border: none !important; padding: 6mm !important; }}
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    font-size: 9pt;
    color: #1a1a2e;
    background: #0d0d1a;
    display: flex;
    justify-content: center;
    padding: 10px;
  }}
  .memo-page {{
    width: 210mm;
    min-height: 297mm;
    background: #fff;
    padding: 8mm;
    box-shadow: 0 4px 20px rgba(0,0,0,0.5);
  }}
  /* ── Header ── */
  .memo-header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    border-bottom: 3px solid #1e3a5f;
    padding-bottom: 6px;
    margin-bottom: 6px;
  }}
  .memo-header h1 {{
    font-size: 14pt;
    color: #1e3a5f;
    letter-spacing: 0.5px;
  }}
  .memo-header .subtitle {{
    font-size: 9pt;
    color: #555;
  }}
  .header-badge {{
    text-align: right;
  }}
  .header-badge .rec-badge {{
    display: inline-block;
    padding: 4px 12px;
    border-radius: 4px;
    color: #fff;
    font-weight: 700;
    font-size: 10pt;
    letter-spacing: 0.5px;
  }}
  .header-badge .grade-badge {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 3px;
    font-weight: 600;
    border: 2px solid;
    font-size: 9pt;
    margin-top: 3px;
  }}
  .header-badge .score-text {{
    font-size: 8pt;
    color: #666;
    margin-top: 2px;
  }}
  /* ── Grid Layout ── */
  .grid-2 {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
  }}
  .grid-3 {{
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 6px;
  }}
  /* ── Section ── */
  .section {{
    margin-bottom: 5px;
  }}
  .section-title {{
    font-size: 9pt;
    font-weight: 700;
    color: #1e3a5f;
    border-bottom: 1.5px solid #d0d8e8;
    padding-bottom: 2px;
    margin-bottom: 4px;
    text-transform: uppercase;
    letter-spacing: 0.6px;
  }}
  /* ── Key-Value pairs ── */
  .kv-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1px 8px;
  }}
  .kv-grid.cols-3 {{
    grid-template-columns: 1fr 1fr 1fr;
  }}
  .kv {{ display: flex; gap: 4px; padding: 1px 0; }}
  .kv-label {{ color: #666; font-size: 8pt; white-space: nowrap; }}
  .kv-val {{ font-weight: 600; font-size: 8.5pt; }}
  /* ── Tables ── */
  .memo-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 8pt;
  }}
  .memo-table th {{
    background: #1e3a5f;
    color: #fff;
    font-weight: 600;
    padding: 3px 4px;
    text-align: left;
    font-size: 7.5pt;
  }}
  .memo-table td {{
    padding: 2px 4px;
    border-bottom: 0.5px solid #e0e0e0;
  }}
  .memo-table tr:nth-child(even) td {{ background: #f8f9fb; }}
  /* ── Score bar ── */
  .score-bar {{
    display: flex;
    align-items: center;
    gap: 6px;
    margin: 2px 0;
  }}
  .score-bar-label {{ font-size: 7.5pt; color: #555; width: 65px; }}
  .score-bar-track {{
    flex: 1;
    height: 8px;
    background: #e5e7eb;
    border-radius: 4px;
    overflow: hidden;
  }}
  .score-bar-fill {{
    height: 100%;
    border-radius: 4px;
    transition: width 0.3s;
  }}
  .score-bar-val {{ font-size: 7.5pt; font-weight: 600; width: 28px; text-align: right; }}
  /* ── Chips ── */
  .chip {{
    display: inline-block;
    padding: 1px 6px;
    border-radius: 3px;
    font-size: 7pt;
    font-weight: 600;
    margin: 1px;
  }}
  .chip-green {{ background: #dcfce7; color: #166534; }}
  .chip-red {{ background: #fee2e2; color: #991b1b; }}
  .chip-amber {{ background: #fef3c7; color: #92400e; }}
  .chip-blue {{ background: #dbeafe; color: #1e40af; }}
  /* ── Footer ── */
  .memo-footer {{
    margin-top: 6px;
    padding-top: 4px;
    border-top: 1px solid #d0d8e8;
    display: flex;
    justify-content: space-between;
    font-size: 7pt;
    color: #999;
  }}
</style>
</head>
<body>
<div class="memo-page">

  <!-- ═══ 1. HEADER ═══════════════════════════════════════════════ -->
  <div class="memo-header">
    <div>
      <h1>Corporate Credit Appraisal Memo</h1>
      <div class="subtitle"><strong>{company_name}</strong> &nbsp;|&nbsp; {sector} &nbsp;|&nbsp; {entity_id}</div>
    </div>
    <div class="header-badge">
      <div class="rec-badge" style="background:{_rec_color(rec)}">{_rec_label(rec)}</div>
      <div class="grade-badge" style="border-color:{_grade_color(risk_grade)}; color:{_grade_color(risk_grade)}">
        Grade {risk_grade}
      </div>
      <div class="score-text">Composite: {composite:.0f}/100</div>
    </div>
  </div>

  <div class="grid-2">
    <!-- ═══ LEFT COLUMN ═══ -->
    <div>
      <!-- ═══ 2. BUSINESS PROFILE ═══ -->
      <div class="section">
        <div class="section-title">Business Profile</div>
        <div class="kv-grid">
          <div class="kv"><span class="kv-label">Incorporated:</span><span class="kv-val">{company.get("date_of_incorporation", "N/A")}</span></div>
          <div class="kv"><span class="kv-label">Type:</span><span class="kv-val">{(case_result.get("case_type") or "Corporate").upper()}</span></div>
          <div class="kv"><span class="kv-label">CIN:</span><span class="kv-val">{company.get("cin", "N/A")}</span></div>
          <div class="kv"><span class="kv-label">PAN:</span><span class="kv-val">{company.get("pan", "N/A")}</span></div>
          <div class="kv"><span class="kv-label">Rating:</span><span class="kv-val">{company.get("credit_rating", "N/A")} {company.get("rating_agency","")}</span></div>
          <div class="kv"><span class="kv-label">Employees:</span><span class="kv-val">{company.get("employee_count", "N/A")}</span></div>
        </div>
        <div class="kv" style="margin-top:2px">
          <span class="kv-label">Facility:</span>
          <span class="kv-val">{facility.get("facility_type", case_result.get("facility_type","N/A"))} — {_fmt_cr(facility.get("amount_requested_cr", case_result.get("requested_amount_cr")))} ({facility.get("purpose","N/A")})</span>
        </div>
{_build_group_section(hierarchy)}
      </div>

      <!-- ═══ 3. FINANCIAL SNAPSHOT ═══ -->
      <div class="section">
        <div class="section-title">Financial Snapshot (₹ Cr)</div>
{_build_financial_table(fin_summary, periods)}
      </div>

      <!-- ═══ Key Ratios ═══ -->
      <div class="section">
        <div class="section-title">Key Ratios ({latest_period})</div>
{_build_ratios_section(latest_ratios)}
      </div>

      <!-- ═══ 7. SECURITY & COLLATERAL ═══ -->
      <div class="section">
        <div class="section-title">Security &amp; Collateral</div>
{_build_collateral_section(collateral, facility)}
      </div>
    </div>

    <!-- ═══ RIGHT COLUMN ═══ -->
    <div>
      <!-- ═══ SCORE BREAKDOWN ═══ -->
      <div class="section">
        <div class="section-title">Credit Score Breakdown</div>
{_build_score_bars(financial_score, conduct_score, governance_score, market_score, composite)}
      </div>

      <!-- ═══ 4. CREDIT STRENGTHS ═══ -->
      <div class="section">
        <div class="section-title">Credit Strengths</div>
{_build_strengths(strengths)}
      </div>

      <!-- ═══ 5. KEY RISKS ═══ -->
      <div class="section">
        <div class="section-title">Key Risks &amp; Concerns</div>
{_build_risks(risks)}
      </div>

      <!-- ═══ 6. CASH FLOW & REPAYMENT ═══ -->
      <div class="section">
        <div class="section-title">Cash Flow &amp; Repayment</div>
{_build_cash_flow_section(cash_flow)}
      </div>

      <!-- ═══ 8. COVENANTS / ESG / REGULATORY ═══ -->
      <div class="section">
        <div class="section-title">Covenants / ESG / Regulatory</div>
{_build_esg_section(esg, conduct)}
      </div>
    </div>
  </div>

  <!-- ═══ 9. FINAL CREDIT VIEW (full width) ═══ -->
  <div class="section" style="margin-top:4px">
    <div class="section-title">Final Credit View</div>
    <div class="grid-3">
      <div>
        <div class="kv"><span class="kv-label">Decision:</span>
          <span class="kv-val" style="color:{_rec_color(rec)}">{_rec_label(rec)}</span></div>
        <div class="kv"><span class="kv-label">Risk Grade:</span>
          <span class="kv-val" style="color:{_grade_color(risk_grade)}">Grade {risk_grade}</span></div>
        <div class="kv"><span class="kv-label">Composite Score:</span>
          <span class="kv-val">{composite:.0f}/100</span></div>
      </div>
      <div>
{_build_conditions(recommendation)}
      </div>
      <div>
        <div style="font-size:7.5pt; color:#555; line-height:1.5">
          {recommendation.get("rationale", case_result.get("rationale", ""))}
        </div>
      </div>
    </div>
  </div>

  <!-- ═══ FOOTER ═══ -->
  <div class="memo-footer">
    <div>Generated by CAM Intelligence Platform &nbsp;|&nbsp; {date.today().isoformat()}</div>
    <div>CONFIDENTIAL — For Internal Use Only</div>
  </div>
</div>
</body>
</html>"""

    return html


# ═══════════════════════════════════════════════════════════════════════════════
# Helper builders
# ═══════════════════════════════════════════════════════════════════════════════

def _build_group_section(hierarchy: dict) -> str:
    if not hierarchy or not hierarchy.get("entities"):
        return ""
    entities = hierarchy.get("entities", [])
    group_name = hierarchy.get("group_name", "")
    lines = [f'        <div style="margin-top:3px; font-size:7.5pt">']
    lines.append(f'          <strong>Group:</strong> {group_name} ({len(entities)} entities)')
    # Show top 3 entities
    for e in entities[:3]:
        name = e.get("company_name", e.get("entity_name", ""))
        rel = e.get("relationship", "")
        lines.append(f'          <br><span class="chip chip-blue">{rel}</span> {name}')
    if len(entities) > 3:
        lines.append(f'          <br><span style="color:#888">+{len(entities)-3} more</span>')
    lines.append('        </div>')
    return "\n".join(lines)


def _build_financial_table(fin_summary: dict, periods: list) -> str:
    if not periods:
        return '        <div style="color:#999; font-size:8pt">No financial data available.</div>'

    metrics = [
        ("Revenue", "revenue_cr"),
        ("EBITDA", "ebitda_cr"),
        ("EBITDA Margin", "ebitda_margin_pct"),
        ("PAT", "pat_cr"),
        ("Net Worth", "net_worth_cr"),
        ("Total Debt", "total_debt_cr"),
        ("Total Assets", "total_assets_cr"),
    ]

    lines = ['        <table class="memo-table">']
    lines.append("          <tr><th>Metric</th>" + "".join(f"<th>{p}</th>" for p in periods[-3:]) + "</tr>")

    for label, key in metrics:
        lines.append("          <tr>")
        lines.append(f"            <td>{label}</td>")
        for p in periods[-3:]:
            val = fin_summary.get("periods", {}).get(p, {}).get(key)
            if key.endswith("_pct"):
                cell = _fmt_pct(val) if val is not None else "—"
            else:
                cell = f"{val:,.1f}" if val is not None else "—"
            lines.append(f"            <td>{cell}</td>")
        lines.append("          </tr>")

    lines.append("        </table>")
    return "\n".join(lines)


def _ratio_status(name: str, val) -> tuple:
    """Return (status_label, chip_class) based on ratio name and value."""
    if val is None:
        return "N/A", "chip-blue"
    thresholds = {
        "current_ratio":           [(1.5, "healthy", "chip-green"), (1.0, "moderate", "chip-amber"), (0, "weak", "chip-red")],
        "debt_to_equity":          [(0, "healthy", "chip-green"), (1.5, "moderate", "chip-amber"), (2.5, "high", "chip-red")],
        "interest_coverage_ratio": [(3.0, "healthy", "chip-green"), (2.0, "moderate", "chip-amber"), (0, "weak", "chip-red")],
        "dscr":                    [(1.5, "healthy", "chip-green"), (1.0, "moderate", "chip-amber"), (0, "weak", "chip-red")],
        "net_profit_margin":       [(0.1, "healthy", "chip-green"), (0.05, "moderate", "chip-amber"), (0, "weak", "chip-red")],
        "ebitda_margin":           [(0.2, "healthy", "chip-green"), (0.1, "moderate", "chip-amber"), (0, "weak", "chip-red")],
    }
    t = thresholds.get(name)
    if t is None:
        return "computed", "chip-blue"
    # For debt ratios, lower is better; for others higher is better
    if name in ("debt_to_equity",):
        if val < 1.0: return "healthy", "chip-green"
        if val < 2.0: return "moderate", "chip-amber"
        return "high", "chip-red"
    for threshold, label, cls in t:
        if val >= threshold:
            return label, cls
    return t[-1][1], t[-1][2]


def _build_ratios_section(latest_ratios: dict) -> str:
    key_ratios = [
        "current_ratio", "debt_to_equity", "interest_coverage_ratio",
        "dscr", "net_profit_margin", "ebitda_margin",
    ]
    if not latest_ratios:
        return '        <div style="color:#999; font-size:8pt">No ratio data available.</div>'

    labels = {
        "current_ratio": "Current Ratio",
        "debt_to_equity": "D/E Ratio",
        "interest_coverage_ratio": "ICR",
        "dscr": "DSCR",
        "net_profit_margin": "Net Margin",
        "ebitda_margin": "EBITDA Margin",
    }
    lines = ['        <div class="kv-grid cols-3">']
    for rname in key_ratios:
        rdata = latest_ratios.get(rname, {})
        val = rdata.get("value")
        # Percentages are stored as decimals (0.21 = 21%)
        if rname in ("net_profit_margin", "ebitda_margin") and val is not None:
            display = f"{val*100:.1f}%"
        else:
            display = f"{val:.2f}" if val is not None else "—"
        status, chip_cls = _ratio_status(rname, val)
        label = labels.get(rname, rname.replace("_", " ").title())
        lines.append(f'          <div class="kv"><span class="kv-label">{label}:</span>'
                     f'<span class="kv-val">{display}</span>'
                     f'<span class="chip {chip_cls}" style="margin-left:2px">{status}</span></div>')
    lines.append("        </div>")
    return "\n".join(lines)


def _build_score_bars(financial: float, conduct: float, governance: float,
                      market: float, composite: float) -> str:
    bars = [
        ("Financial", financial, "#3b82f6"),
        ("Conduct", conduct, "#8b5cf6"),
        ("Governance", governance, "#06b6d4"),
        ("Market", market, "#f59e0b"),
        ("Composite", composite, "#10b981"),
    ]
    lines = []
    for label, val, color in bars:
        width = min(max(val, 0), 100)
        lines.append(f'''        <div class="score-bar">
          <span class="score-bar-label">{label}</span>
          <div class="score-bar-track"><div class="score-bar-fill" style="width:{width}%;background:{color}"></div></div>
          <span class="score-bar-val">{val:.0f}</span>
        </div>''')
    return "\n".join(lines)


def _build_strengths(strengths: list) -> str:
    if not strengths:
        return '        <div style="color:#999; font-size:8pt">Pipeline not run or no strengths identified.</div>'
    lines = []
    for s in strengths[:6]:
        cat = s.get("category", "") if isinstance(s, dict) else str(s)
        detail = s.get("detail", "") if isinstance(s, dict) else ""
        lines.append(f'        <div style="padding:1px 0"><span class="chip chip-green">{cat}</span> '
                     f'<span style="font-size:7.5pt">{detail}</span></div>')
    return "\n".join(lines)


def _build_risks(risks: list) -> str:
    if not risks:
        return '        <div style="color:#999; font-size:8pt">Pipeline not run or no risks identified.</div>'
    sev_cls = {"critical": "chip-red", "high": "chip-red", "medium": "chip-amber", "low": "chip-blue"}
    lines = []
    for r in risks[:6]:
        cat = r.get("category", "") if isinstance(r, dict) else str(r)
        detail = r.get("detail", "") if isinstance(r, dict) else ""
        sev = r.get("severity", "medium") if isinstance(r, dict) else "medium"
        cls = sev_cls.get(sev, "chip-amber")
        lines.append(f'        <div style="padding:1px 0"><span class="chip {cls}">{sev.upper()}</span> '
                     f'<span style="font-size:7.5pt"><strong>{cat}:</strong> {detail}</span></div>')
    return "\n".join(lines)


def _build_cash_flow_section(cash_flow: dict) -> str:
    periods = cash_flow.get("periods", {})
    if not periods:
        return '        <div style="color:#999; font-size:8pt">No cash flow data.</div>'
    plist = sorted(periods.keys())[-3:]
    lines = ['        <table class="memo-table">']
    lines.append("          <tr><th>Metric</th>" + "".join(f"<th>{p}</th>" for p in plist) + "</tr>")
    for label, key in [("Operating CF", "operating_cash_flow_cr"), ("Capex", "capex_cr"), ("FCF", "free_cash_flow_cr")]:
        lines.append("          <tr>")
        lines.append(f"            <td>{label}</td>")
        for p in plist:
            val = periods.get(p, {}).get(key)
            cell = f"{val:,.1f}" if val is not None else "—"
            lines.append(f"            <td>{cell}</td>")
        lines.append("          </tr>")
    lines.append("        </table>")
    # Repayment assessment
    repay = cash_flow.get("repayment_capacity", cash_flow.get("repayment_assessment", {}))
    if repay:
        status = repay.get("status", "")
        # Derive from 'adequate' flag when explicit status is absent
        if not status:
            adequate_flag = repay.get("adequate")
            if adequate_flag is True:
                status = "adequate"
            elif adequate_flag is False:
                status = "insufficient"
        if status and status != "N/A":
            surplus = repay.get("estimated_surplus_cr")
            surplus_txt = f" | Surplus ₹{surplus:,.0f} Cr" if surplus is not None else ""
            color = "#22c55e" if "adequate" in status.lower() else ("#f59e0b" if "tight" in status.lower() else "#ef4444")
            lines.append(f'        <div style="margin-top:2px; font-size:7.5pt">'
                         f'<strong>Repayment Capacity:</strong> '
                         f'<span style="color:{color}; font-weight:600">{status.title()}</span>{surplus_txt}</div>')
    return "\n".join(lines)


def _build_collateral_section(collateral: dict, facility: dict) -> str:
    coll_list = collateral.get("collaterals", [])
    if not coll_list:
        return '        <div style="color:#999; font-size:8pt">Unsecured / No collateral pledged.</div>'
    lines = ['        <table class="memo-table">']
    lines.append("          <tr><th>Type</th><th>Market Value</th><th>FSV</th></tr>")
    for c in coll_list[:4]:
        lines.append(f"          <tr><td>{c.get('type', 'N/A')}</td>"
                     f"<td>{_fmt_cr(c.get('market_value_cr'))}</td>"
                     f"<td>{_fmt_cr(c.get('forced_sale_value_cr'))}</td></tr>")
    lines.append("        </table>")
    cov_mkt = collateral.get("coverage_ratio_market", collateral.get("coverage_market", 0))
    cov_fsv = collateral.get("coverage_ratio_fsv", collateral.get("coverage_fsv", 0))
    lines.append(f'        <div style="font-size:7.5pt; margin-top:2px">'
                 f'Coverage: <strong>{cov_mkt:.2f}x</strong> (market) / '
                 f'<strong>{cov_fsv:.2f}x</strong> (FSV)</div>')
    return "\n".join(lines)


def _build_esg_section(esg: dict, conduct: dict) -> str:
    lines = []
    # Conduct / account behaviour stats
    if conduct.get("available"):
        util = conduct.get("avg_utilization_pct")
        dpd = conduct.get("max_dpd_overall")
        cheques = conduct.get("total_cheque_returns", 0)
        qtrs = conduct.get("quarters_analyzed", "N/A")
        trend = conduct.get("utilization_trend", "")
        stat_parts = [f"Qtrs analysed: {qtrs}"]
        if util is not None:
            stat_parts.append(f"Avg utilisation: {util:.0f}%")
        if dpd is not None:
            dpd_color = "#22c55e" if dpd == 0 else ("#f59e0b" if dpd <= 30 else "#ef4444")
            stat_parts.append(f'<span style="color:{dpd_color}">Max DPD: {dpd}d</span>')
        if cheques:
            stat_parts.append(f"Cheque returns: {cheques}")
        lines.append(f'        <div style="font-size:7.5pt; padding:1px 0">'
                     f'<strong>Account Conduct:</strong> {", ".join(stat_parts)}</div>')
        if trend:
            lines.append(f'        <div style="font-size:7pt; padding-left:6px">Utilisation trend: {trend}</div>')

    # ESG items
    for section, label in [("environmental", "Environmental"), ("social", "Social"),
                            ("governance", "Governance"), ("regulatory", "Regulatory")]:
        items = esg.get(section, {})
        if items:
            if isinstance(items, dict):
                # Only evidenced values; a section with none says so (no assumed "Compliant" / "Adequate").
                known = [(k, v) for k, v in items.items()
                         if v not in (None, "") and not k.endswith(("_note", "_basis"))]
                status_list = ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in known[:2]) \
                    or "Not available from submitted information"
            elif isinstance(items, list):
                status_list = ", ".join(
                    f"{i.get('item', '')}: {i.get('status', '')}" if isinstance(i, dict) else str(i)
                    for i in items[:2]
                )
            else:
                status_list = str(items)
            lines.append(f'        <div style="font-size:7.5pt; padding:1px 0">'
                         f'<strong>{label}:</strong> {status_list}</div>')

    if not lines:
        return '        <div style="color:#999; font-size:8pt">No conduct / ESG data available.</div>'
    return "\n".join(lines)


def _build_conditions(recommendation: dict) -> str:
    conditions = recommendation.get("conditions", [])
    covenants = recommendation.get("covenants_proposed", [])
    lines = []
    if conditions:
        lines.append('        <div style="font-size:7.5pt"><strong>Conditions:</strong></div>')
        for c in conditions[:3]:
            lines.append(f'        <div style="font-size:7pt; padding-left:6px">• {c}</div>')
    if covenants:
        lines.append('        <div style="font-size:7.5pt; margin-top:2px"><strong>Proposed Covenants:</strong></div>')
        for c in covenants[:3]:
            lines.append(f'        <div style="font-size:7pt; padding-left:6px">• {c}</div>')
    if not lines:
        return '        <div style="color:#999; font-size:8pt">No conditions specified.</div>'
    return "\n".join(lines)
