"""
Deterministic Validation Engine
5-level validation: structural, cross-source, analytical, temporal, policy.
Every check is rule-based — no LLM involvement.
"""

from datetime import date, timedelta
from src.models.canonical_model import (
    Borrower, FinancialStatement, FacilityRequest, ValidationException,
    RiskSeverity, ValidationStatus, CaseType, BorrowerType,
)


# ─── Tolerance Config ────────────────────────────────────────────────────────

REVENUE_MISMATCH_TOLERANCE = 0.05  # 5%
BALANCE_SHEET_TOLERANCE = 0.20     # 20% — POC uses simplified line items; production would be 1%
STALE_FILING_DAYS = 365
GST_REVENUE_TOLERANCE = 0.10      # 10%


# ─── Structural Validations ──────────────────────────────────────────────────

def validate_balance_sheet_balances(fs: FinancialStatement) -> list[ValidationException]:
    """Check: Total Assets ≈ Total Equity + Long-Term Debt + Current Liabilities
    Note: current_liabilities includes short-term borrowings, so we use long_term_debt
    to avoid double counting short_term_debt."""
    results = []
    ta = fs.get("total_assets")
    te = fs.get("total_equity")
    ltd = fs.get("long_term_debt")
    cl = fs.get("current_liabilities")
    if ta > 0:
        rhs = te + ltd + cl
        diff_pct = abs(ta - rhs) / ta
        if diff_pct > BALANCE_SHEET_TOLERANCE:
            results.append(ValidationException(
                exception_code="STRUCT_BS_MISMATCH",
                severity=RiskSeverity.CRITICAL,
                entity_id=fs.entity_id,
                description=f"Balance sheet does not balance for {fs.period}. "
                            f"Total Assets={ta:.2f} Cr vs RHS={rhs:.2f} Cr (diff={diff_pct:.2%})",
                expected_value=f"{ta:.2f}",
                observed_value=f"{rhs:.2f}",
                source_doc_ref=f"Financial Statement {fs.period}",
                impacted_metric="total_assets",
            ))
    return results


def validate_pat_consistency(fs: FinancialStatement) -> list[ValidationException]:
    """Check: PAT ≈ PBT - Tax"""
    results = []
    pbt = fs.get("pbt")
    tax = fs.get("tax_expense")
    pat = fs.get("pat")
    expected_pat = pbt - tax
    if pat != 0 and abs(pat - expected_pat) > 0.5:
        results.append(ValidationException(
            exception_code="STRUCT_PAT_INCONSISTENT",
            severity=RiskSeverity.HIGH,
            entity_id=fs.entity_id,
            description=f"PAT inconsistent for {fs.period}. "
                        f"PBT({pbt:.2f}) - Tax({tax:.2f}) = {expected_pat:.2f} but PAT = {pat:.2f}",
            expected_value=f"{expected_pat:.2f}",
            observed_value=f"{pat:.2f}",
            source_doc_ref=f"Financial Statement {fs.period}",
            impacted_metric="pat",
        ))
    return results


def validate_ebitda_consistency(fs: FinancialStatement) -> list[ValidationException]:
    """Check: EBITDA ≈ Revenue - Raw Material - Employee Cost - Other Expenses"""
    results = []
    rev = fs.get("total_income")
    rm = fs.get("raw_material_cost")
    emp = fs.get("employee_cost")
    oth = fs.get("other_expenses")
    ebitda = fs.get("ebitda")
    expected = rev - rm - emp - oth
    if ebitda != 0 and abs(ebitda - expected) > 0.5:
        results.append(ValidationException(
            exception_code="STRUCT_EBITDA_INCONSISTENT",
            severity=RiskSeverity.HIGH,
            entity_id=fs.entity_id,
            description=f"EBITDA inconsistent for {fs.period}. "
                        f"Expected {expected:.2f} but found {ebitda:.2f}",
            expected_value=f"{expected:.2f}",
            observed_value=f"{ebitda:.2f}",
            source_doc_ref=f"Financial Statement {fs.period}",
            impacted_metric="ebitda",
        ))
    return results


# ─── Cross-Source Validations ─────────────────────────────────────────────────

def validate_revenue_vs_exchange(borrower_fs: FinancialStatement,
                                  exchange_fs: FinancialStatement) -> list[ValidationException]:
    """Cross-source: borrower submitted revenue vs exchange-filed revenue."""
    results = []
    if exchange_fs is None:
        return results
    b_rev = borrower_fs.get("revenue_operating")
    e_rev = exchange_fs.get("revenue_operating")
    if b_rev > 0 and e_rev > 0:
        exchange_period = str(getattr(exchange_fs, "period", "") or "").lower()
        exchange_source = str(getattr(exchange_fs, "source", "") or "").lower()
        is_interim_exchange = "9m" in exchange_period or "quarter" in exchange_period or "exchange" in exchange_source
        diff_pct = abs(b_rev - e_rev) / max(b_rev, e_rev)
        tolerance = 0.25 if is_interim_exchange else REVENUE_MISMATCH_TOLERANCE
        if diff_pct > tolerance:
            results.append(ValidationException(
                exception_code="XSRC_REVENUE_MISMATCH",
                severity=RiskSeverity.HIGH if is_interim_exchange else RiskSeverity.CRITICAL,
                entity_id=borrower_fs.entity_id,
                description=f"Revenue mismatch: borrower submitted {b_rev:.2f} Cr "
                            f"vs exchange filing {e_rev:.2f} Cr (diff={diff_pct:.1%})"
                            f"{' — interim / annualized exchange comparison' if is_interim_exchange else ''}",
                expected_value=f"{e_rev:.2f} (exchange)",
                observed_value=f"{b_rev:.2f} (borrower)",
                source_doc_ref="Borrower Provisional vs Exchange Filing",
                impacted_metric="revenue_operating",
            ))
    return results


def validate_revenue_vs_gst(fs: FinancialStatement, gst_payload: dict) -> list[ValidationException]:
    """Cross-source: revenue vs GST aggregate turnover."""
    results = []
    gst_rev = gst_payload.get("payload", {}).get(f"aggregate_turnover_{fs.period.lower()}_cr")
    if gst_rev is None:
        # Try FY format
        fy_key = fs.period.replace("FY", "fy")
        gst_rev = gst_payload.get("payload", {}).get(f"aggregate_turnover_{fy_key}_cr")
    if gst_rev and gst_rev > 0:
        b_rev = fs.get("revenue_operating")
        diff_pct = abs(b_rev - gst_rev) / max(b_rev, gst_rev)
        if diff_pct > GST_REVENUE_TOLERANCE:
            results.append(ValidationException(
                exception_code="XSRC_GST_REVENUE_MISMATCH",
                severity=RiskSeverity.HIGH,
                entity_id=fs.entity_id,
                description=f"Revenue vs GST turnover mismatch for {fs.period}. "
                            f"Audited={b_rev:.2f} Cr vs GST={gst_rev:.2f} Cr (diff={diff_pct:.1%})",
                expected_value=f"{gst_rev:.2f} (GST)",
                observed_value=f"{b_rev:.2f} (audited)",
                source_doc_ref="Audited Financials vs GST Returns",
                impacted_metric="revenue_operating",
            ))
    return results


def validate_debt_vs_bureau(fs: FinancialStatement, bureau_payload: dict) -> list[ValidationException]:
    """Cross-source: total debt vs public-record exposure."""
    results = []
    bureau_exp = bureau_payload.get("payload", {}).get("total_exposure_cr")
    if bureau_exp and bureau_exp > 0:
        b_debt = fs.get("total_debt")
        diff_pct = abs(b_debt - bureau_exp) / max(b_debt, bureau_exp) if max(b_debt, bureau_exp) > 0 else 0
        if diff_pct > 0.15:  # 15% tolerance — some timing differences expected
            results.append(ValidationException(
                exception_code="XSRC_DEBT_BUREAU_MISMATCH",
                severity=RiskSeverity.HIGH,
                entity_id=fs.entity_id,
                description=f"Debt mismatch: audited total debt={b_debt:.2f} Cr "
                            f"vs public-record exposure={bureau_exp:.2f} Cr (diff={diff_pct:.1%})",
                expected_value=f"{bureau_exp:.2f} (public records)",
                observed_value=f"{b_debt:.2f} (audited)",
                source_doc_ref="Audited Financials vs Public-Record Snapshot",
                impacted_metric="total_debt",
            ))
    return results


def validate_bureau_dpd(bureau_payload: dict, entity_id: str) -> list[ValidationException]:
    """Cross-source: check if public records show DPD or SMA status."""
    results = []
    payload = bureau_payload.get("payload", {})
    dpd_status = payload.get("dpd_status", "")
    max_dpd = payload.get("max_dpd_last_12m", 0)
    if dpd_status in ("SMA-1", "SMA-2", "Substandard", "Doubtful", "Loss"):
        results.append(ValidationException(
            exception_code="XSRC_BUREAU_DPD_ALERT",
            severity=RiskSeverity.CRITICAL,
            entity_id=entity_id,
            description=f"Public records show adverse DPD status: {dpd_status}, "
                        f"max DPD in last 12 months = {max_dpd} days",
            expected_value="Standard / SMA-0",
            observed_value=dpd_status,
            source_doc_ref="Public-Record Credit Snapshot",
            impacted_metric="credit_quality",
        ))
    wilful = payload.get("wilful_defaulter", False)
    if wilful:
        results.append(ValidationException(
            exception_code="XSRC_BUREAU_WILFUL_DEFAULTER",
            severity=RiskSeverity.CRITICAL,
            entity_id=entity_id,
            description="Borrower flagged as Wilful Defaulter in public records",
            expected_value="Not a wilful defaulter",
            observed_value="Wilful Defaulter",
            source_doc_ref="Public-Record Credit Snapshot",
            impacted_metric="credit_quality",
        ))
    return results


# ─── Analytical Validations ──────────────────────────────────────────────────

def validate_receivable_spike(fs_current: FinancialStatement,
                              fs_prior: FinancialStatement) -> list[ValidationException]:
    """Analytical: sudden receivable spike without proportional revenue growth."""
    results = []
    rec_curr = fs_current.get("trade_receivables")
    rec_prev = fs_prior.get("trade_receivables")
    rev_curr = fs_current.get("revenue_operating")
    rev_prev = fs_prior.get("revenue_operating")
    if rec_prev > 0 and rev_prev > 0:
        rec_growth = (rec_curr - rec_prev) / rec_prev
        rev_growth = (rev_curr - rev_prev) / rev_prev
        if rec_growth > 0.30 and rev_growth < 0.15:
            results.append(ValidationException(
                exception_code="ANAL_RECEIVABLE_SPIKE",
                severity=RiskSeverity.HIGH,
                entity_id=fs_current.entity_id,
                description=f"Receivables grew {rec_growth:.1%} YoY while revenue grew only {rev_growth:.1%}. "
                            f"Indicates possible collection issues or revenue quality concerns.",
                expected_value=f"Receivable growth ~{rev_growth:.1%}",
                observed_value=f"Receivable growth {rec_growth:.1%}",
                source_doc_ref=f"Financial Statements {fs_prior.period} vs {fs_current.period}",
                impacted_metric="trade_receivables",
            ))
    return results


def validate_negative_ocf_with_growth(fs: FinancialStatement) -> list[ValidationException]:
    """Analytical: negative operating cash flow despite revenue > 0."""
    results = []
    ocf = fs.get("operating_cash_flow")
    rev = fs.get("revenue_operating")
    if ocf < 0 and rev > 100:
        results.append(ValidationException(
            exception_code="ANAL_NEGATIVE_OCF",
            severity=RiskSeverity.HIGH,
            entity_id=fs.entity_id,
            description=f"Negative operating cash flow ({ocf:.2f} Cr) despite revenue of {rev:.2f} Cr "
                        f"in {fs.period}. Cash conversion problem.",
            expected_value="Positive OCF",
            observed_value=f"{ocf:.2f} Cr",
            source_doc_ref=f"Cash Flow Statement {fs.period}",
            impacted_metric="operating_cash_flow",
        ))
    return results


def validate_margin_decline(financials: dict[str, FinancialStatement]) -> list[ValidationException]:
    """Analytical: sustained EBITDA margin decline over 3 years."""
    results = []
    periods = sorted(financials.keys())
    if len(periods) < 3:
        return results
    margins = []
    for p in periods:
        rev = financials[p].get("revenue_operating")
        eb = financials[p].get("ebitda")
        if rev > 0:
            margins.append((p, eb / rev))
    if len(margins) >= 3:
        # Check if consistently declining
        if margins[-1][1] < margins[-2][1] < margins[-3][1]:
            latest = margins[-1]
            results.append(ValidationException(
                exception_code="ANAL_MARGIN_DECLINE",
                severity=RiskSeverity.MEDIUM,
                entity_id=financials[periods[-1]].entity_id,
                description=f"EBITDA margin declining for 3 consecutive years: "
                            f"{', '.join(f'{p}={m:.1%}' for p, m in margins)}",
                expected_value="Stable or improving margin",
                observed_value=f"{latest[1]:.1%} ({latest[0]})",
                source_doc_ref="3-year Financial Analysis",
                impacted_metric="ebitda_margin",
            ))
    return results


# ─── Temporal Validations ────────────────────────────────────────────────────

def validate_stale_financials(fs: FinancialStatement, reference_date: date) -> list[ValidationException]:
    """Temporal: check if financials are stale (> 365 days old)."""
    results = []
    age = (reference_date - fs.as_of_date).days
    if age > STALE_FILING_DAYS:
        results.append(ValidationException(
            exception_code="TEMP_STALE_FINANCIALS",
            severity=RiskSeverity.MEDIUM,
            entity_id=fs.entity_id,
            description=f"Financial statement for {fs.period} is {age} days old "
                        f"(as_of_date={fs.as_of_date}). Stale data risk.",
            expected_value=f"<= {STALE_FILING_DAYS} days",
            observed_value=f"{age} days",
            source_doc_ref=f"Financial Statement {fs.period}",
            impacted_metric="data_freshness",
        ))
    return results


# ─── Policy Validations ──────────────────────────────────────────────────────

def validate_mandatory_docs_ntb(borrower: Borrower, has_kyc: bool, has_board_resolution: bool,
                                 has_audited_3yr: bool, has_collateral_docs: bool) -> list[ValidationException]:
    """Policy: check NTB mandatory document checklist."""
    results = []
    if not has_kyc:
        results.append(ValidationException(
            exception_code="POL_MISSING_KYC",
            severity=RiskSeverity.CRITICAL,
            entity_id=borrower.entity_id,
            description="KYC documents missing for NTB case — onboarding cannot proceed",
            source_doc_ref="Document Checklist",
            impacted_metric="kyc_compliance",
        ))
    if not has_board_resolution:
        results.append(ValidationException(
            exception_code="POL_MISSING_BOARD_RES",
            severity=RiskSeverity.HIGH,
            entity_id=borrower.entity_id,
            description="Board resolution for borrowing not provided",
            source_doc_ref="Document Checklist",
            impacted_metric="authority_to_borrow",
        ))
    if not has_audited_3yr:
        results.append(ValidationException(
            exception_code="POL_MISSING_3YR_AUDITED",
            severity=RiskSeverity.HIGH,
            entity_id=borrower.entity_id,
            description="Less than 3 years of audited financials provided",
            source_doc_ref="Document Checklist",
            impacted_metric="financial_assessment",
        ))
    if not has_collateral_docs:
        results.append(ValidationException(
            exception_code="POL_MISSING_COLLATERAL_DOCS",
            severity=RiskSeverity.MEDIUM,
            entity_id=borrower.entity_id,
            description="Collateral documents not fully provided",
            source_doc_ref="Document Checklist",
            impacted_metric="security_assessment",
        ))
    return results


# ─── Conduct Validations (ETB) ───────────────────────────────────────────────

def validate_etb_conduct(conduct_records: list, entity_id: str) -> list[ValidationException]:
    """ETB: validate internal banking conduct."""
    results = []
    if not conduct_records:
        return results

    latest = conduct_records[0]  # Assume sorted most recent first
    total_returns = sum(c.cheque_returns for c in conduct_records)
    max_dpd = max(c.max_overdue_days for c in conduct_records)
    avg_util = sum(c.limit_utilization_pct for c in conduct_records) / len(conduct_records)

    if total_returns > 20:
        results.append(ValidationException(
            exception_code="COND_HIGH_CHEQUE_RETURNS",
            severity=RiskSeverity.HIGH,
            entity_id=entity_id,
            description=f"Total cheque returns = {total_returns} over {len(conduct_records)} quarters. "
                        f"Indicates cash-flow stress.",
            expected_value="<= 10 total",
            observed_value=str(total_returns),
            source_doc_ref="Internal Account Conduct Report",
            impacted_metric="conduct_quality",
        ))

    if max_dpd > 30:
        results.append(ValidationException(
            exception_code="COND_DPD_BREACH",
            severity=RiskSeverity.HIGH,
            entity_id=entity_id,
            description=f"Maximum DPD of {max_dpd} days in recent quarters. "
                        f"Repayment discipline concern.",
            expected_value="<= 30 days",
            observed_value=f"{max_dpd} days",
            source_doc_ref="Internal Repayment History",
            impacted_metric="repayment_conduct",
        ))

    if avg_util > 90:
        results.append(ValidationException(
            exception_code="COND_HIGH_UTILIZATION",
            severity=RiskSeverity.MEDIUM,
            entity_id=entity_id,
            description=f"Average limit utilization = {avg_util:.1f}% over recent quarters. "
                        f"Indicates stretched working capital.",
            expected_value="<= 85%",
            observed_value=f"{avg_util:.1f}%",
            source_doc_ref="Internal Utilization Report",
            impacted_metric="working_capital_adequacy",
        ))

    return results


def validate_covenant_compliance(covenants: list, entity_id: str) -> list[ValidationException]:
    """ETB: validate covenant compliance history."""
    results = []
    breaches = [c for c in covenants if c.compliance_status == "breached"]
    for b in breaches:
        results.append(ValidationException(
            exception_code="COV_BREACH",
            severity=RiskSeverity.HIGH,
            entity_id=entity_id,
            description=f"Covenant breach: {b.covenant_type} — "
                        f"Required: {b.required_value}, Actual: {b.actual_value}. "
                        f"{b.breach_details}",
            expected_value=b.required_value,
            observed_value=b.actual_value,
            source_doc_ref=f"Covenant Monitoring — {b.period}",
            impacted_metric=b.covenant_type,
        ))
    return results


# ─── Document-Extraction-Backed Validations ──────────────────────────────────

def validate_extracted_revenue_consistency(entity_id: str, extraction: dict) -> list[ValidationException]:
    """Cross-source: compare revenue across audited PDF, provisional Excel,
    exchange filing, and GST certificate — all extracted from actual documents."""
    results = []
    sources = {}

    # Audited (from PDF extraction)
    audited_fin = extraction.get("financials", {}).get("audited", {})
    rev_list = audited_fin.get("revenue", [])
    if rev_list:
        sources["audited_pdf"] = rev_list[0]  # most recent

    # Provisional (from Excel extraction)
    prov = extraction.get("provisional", {})
    prov_rev = prov.get("provisional_revenue")
    if prov_rev:
        sources["provisional_excel"] = prov_rev

    # Exchange filing (from PDF extraction)
    exch = extraction.get("exchange", {})
    nine_m = exch.get("nine_month_revenue") or exch.get("revenue", [None])
    if isinstance(nine_m, list):
        nine_m = nine_m[0] if nine_m else None
    if nine_m:
        sources["exchange_9m"] = nine_m

    # GST (from PDF extraction)
    gst = extraction.get("gst", {})
    gst_turn = gst.get("total_turnover")
    if gst_turn:
        sources["gst_turnover"] = gst_turn

    if len(sources) < 2:
        return results

    # Pairwise comparison
    keys = list(sources.keys())
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            k1, k2 = keys[i], keys[j]
            v1, v2 = sources[k1], sources[k2]
            if v1 > 0 and v2 > 0:
                # Annualize 9-month figures before comparing with full-year
                comp_v1, comp_v2 = v1, v2
                is_cross_period = False
                if "9m" in k1 and "9m" not in k2:
                    comp_v1 = v1 * (12 / 9)
                    is_cross_period = True
                elif "9m" in k2 and "9m" not in k1:
                    comp_v2 = v2 * (12 / 9)
                    is_cross_period = True

                diff_pct = abs(comp_v1 - comp_v2) / max(comp_v1, comp_v2)

                # Cross-period comparisons use wider tolerance (annualization is approximate)
                if is_cross_period:
                    tolerance = 0.25
                else:
                    tolerance = 0.10

                if diff_pct > tolerance:
                    # Cross-period: cap at MEDIUM (annualization + OCR imprecision)
                    if is_cross_period:
                        severity = RiskSeverity.MEDIUM
                    else:
                        severity = RiskSeverity.CRITICAL if diff_pct > 0.20 else RiskSeverity.HIGH

                    ann_note = " (annualized)" if is_cross_period else ""
                    results.append(ValidationException(
                        exception_code="DOC_REVENUE_CROSS_SOURCE",
                        severity=severity,
                        entity_id=entity_id,
                        description=f"Document-extracted revenue mismatch{ann_note}: {k1}={comp_v1:.2f} Cr "
                                    f"vs {k2}={comp_v2:.2f} Cr (diff={diff_pct:.1%}). "
                                    f"Sources: {k1} (document) vs {k2} (document).",
                        expected_value=f"{comp_v1:.2f} ({k1})",
                        observed_value=f"{comp_v2:.2f} ({k2})",
                        source_doc_ref=f"Extracted: {k1} vs {k2}",
                        impacted_metric="revenue_operating",
                    ))

    return results


def validate_extracted_etb_flags(entity_id: str, etb_analysis: dict) -> list[ValidationException]:
    """Convert ETB analytics red flags into validation exceptions."""
    results = []
    if not etb_analysis:
        return results

    all_flags = etb_analysis.get("all_flags", [])
    composite_score = etb_analysis.get("composite_score", 100)

    if composite_score < 40:
        results.append(ValidationException(
            exception_code="ETB_CRITICAL_CONDUCT",
            severity=RiskSeverity.CRITICAL,
            entity_id=entity_id,
            description=f"ETB composite conduct score is {composite_score:.0f}/100 — "
                        f"Very High behavioral risk. {len(all_flags)} red flags detected.",
            expected_value=">= 60/100",
            observed_value=f"{composite_score:.0f}/100",
            source_doc_ref="ETB Behavioral Analytics",
            impacted_metric="conduct_quality",
        ))
    elif composite_score < 60:
        results.append(ValidationException(
            exception_code="ETB_MODERATE_CONDUCT",
            severity=RiskSeverity.HIGH,
            entity_id=entity_id,
            description=f"ETB composite conduct score is {composite_score:.0f}/100 — "
                        f"High behavioral risk. {len(all_flags)} red flags.",
            expected_value=">= 60/100",
            observed_value=f"{composite_score:.0f}/100",
            source_doc_ref="ETB Behavioral Analytics",
            impacted_metric="conduct_quality",
        ))

    # Add individual critical flags
    for flag in all_flags[:5]:
        if any(w in flag.lower() for w in ["breach", "dpd", "consecutive", "over-limit"]):
            results.append(ValidationException(
                exception_code="ETB_FLAG",
                severity=RiskSeverity.HIGH,
                entity_id=entity_id,
                description=f"ETB red flag: {flag}",
                source_doc_ref="ETB Behavioral Analytics",
                impacted_metric="conduct_quality",
            ))

    return results


# ─── Group Risk Validations ──────────────────────────────────────────────────

def validate_group_risk(market_signals: list, entity_id: str) -> list[ValidationException]:
    """Validate group-level risk signals from market/news."""
    results = []
    critical_signals = [s for s in market_signals if s.severity in (RiskSeverity.HIGH, RiskSeverity.CRITICAL)]
    negative_signals = [s for s in market_signals if s.sentiment == "negative"]

    if len(critical_signals) >= 2:
        results.append(ValidationException(
            exception_code="GRP_MULTIPLE_HIGH_RISK_SIGNALS",
            severity=RiskSeverity.HIGH,
            entity_id=entity_id,
            description=f"{len(critical_signals)} high/critical risk signals detected: "
                        f"{'; '.join(s.headline for s in critical_signals)}",
            source_doc_ref="Market Intelligence Report",
            impacted_metric="reputation_risk",
        ))

    for s in market_signals:
        if s.severity == RiskSeverity.CRITICAL:
            results.append(ValidationException(
                exception_code="GRP_CRITICAL_EVENT",
                severity=RiskSeverity.CRITICAL,
                entity_id=entity_id,
                description=f"Critical event: {s.headline}. {s.details}",
                source_doc_ref=f"{s.source_name} — {s.signal_date}",
                impacted_metric="reputation_risk",
            ))

    return results


# ─── Master Validation Runner ────────────────────────────────────────────────

def run_all_validations(
    borrower: Borrower,
    financials: dict[str, FinancialStatement],
    provisional: FinancialStatement = None,
    exchange_filing: FinancialStatement = None,
    bureau_payload: dict = None,
    gst_payload: dict = None,
    market_signals: list = None,
    conduct_records: list = None,
    covenants: list = None,
    reference_date: date = None,
    case_type: CaseType = CaseType.NTB,
    extraction: dict = None,
    etb_analysis: dict = None,
    document_inventory: dict | None = None,
) -> list[ValidationException]:
    """Run all applicable validations. Returns sorted list of exceptions."""

    if reference_date is None:
        reference_date = date.today()

    all_exceptions = []
    periods = sorted(financials.keys())

    # Structural
    for p, fs in financials.items():
        all_exceptions.extend(validate_balance_sheet_balances(fs))
        all_exceptions.extend(validate_pat_consistency(fs))
        all_exceptions.extend(validate_ebitda_consistency(fs))

    # Cross-source
    if provisional and exchange_filing:
        all_exceptions.extend(validate_revenue_vs_exchange(provisional, exchange_filing))

    latest_period = periods[-1] if periods else None
    latest_fs = financials.get(latest_period)

    if latest_fs and bureau_payload:
        all_exceptions.extend(validate_debt_vs_bureau(latest_fs, bureau_payload))
        all_exceptions.extend(validate_bureau_dpd(bureau_payload, borrower.entity_id))

    if latest_fs and gst_payload:
        all_exceptions.extend(validate_revenue_vs_gst(latest_fs, gst_payload))

    # Analytical
    if len(periods) >= 2:
        curr_fs = financials[periods[-1]]
        prev_fs = financials[periods[-2]]
        all_exceptions.extend(validate_receivable_spike(curr_fs, prev_fs))

    for fs in financials.values():
        all_exceptions.extend(validate_negative_ocf_with_growth(fs))

    all_exceptions.extend(validate_margin_decline(financials))

    # Temporal
    if latest_fs:
        all_exceptions.extend(validate_stale_financials(latest_fs, reference_date))

    # Policy (NTB): the document checklist uses the documents actually available (data_ingestion's
    # inventory). Without an inventory (assessment outside a pipeline run) only the audited-years check runs.
    if case_type == CaseType.NTB:
        inv = document_inventory
        all_exceptions.extend(validate_mandatory_docs_ntb(
            borrower,
            has_kyc=inv["has_kyc"] if inv else True,
            has_board_resolution=inv["has_board_resolution"] if inv else True,
            has_audited_3yr=len(periods) >= 3,
            has_collateral_docs=inv["has_collateral_docs"] if inv else True,
        ))

    # Conduct (ETB)
    if case_type == CaseType.ETB and conduct_records:
        all_exceptions.extend(validate_etb_conduct(conduct_records, borrower.entity_id))

    if covenants:
        all_exceptions.extend(validate_covenant_compliance(covenants, borrower.entity_id))

    # Group/market signals
    if market_signals:
        all_exceptions.extend(validate_group_risk(market_signals, borrower.entity_id))

    # Document-extraction-backed cross-source validation
    if extraction:
        all_exceptions.extend(validate_extracted_revenue_consistency(borrower.entity_id, extraction))

    # ETB behavioral analytics flags
    if etb_analysis:
        all_exceptions.extend(validate_extracted_etb_flags(borrower.entity_id, etb_analysis))

    # Sort by severity
    severity_order = {RiskSeverity.CRITICAL: 0, RiskSeverity.HIGH: 1,
                      RiskSeverity.MEDIUM: 2, RiskSeverity.LOW: 3}
    all_exceptions.sort(key=lambda e: severity_order.get(e.severity, 99))

    return all_exceptions
