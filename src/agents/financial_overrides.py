"""
RM-uploaded document overrides.

When the RM uploads audited, provisional, exchange-filing or debt-schedule
documents, their extracted figures replace the public-record baseline for the
latest period before analysis runs.
"""

from datetime import date

from src.models.canonical_model import ExistingExposure, FinancialStatement

def _first_numeric(value):
    """Extract a numeric value from possibly-nested data.
    For lists, returns the *maximum* positive value — this picks the
    consolidated figure over standalone when regex captures both from
    an annual report that contains both sets of financial statements."""
    if isinstance(value, list):
        best = 0.0
        for item in value:
            numeric = _first_numeric(item)
            if numeric > best:
                best = numeric
        return best
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0

def _latest_financial_context(financials: dict[str, FinancialStatement]):
    if financials:
        ranked = sorted(
            financials.items(),
            key=lambda item: (
                getattr(item[1], "as_of_date", date.min),
                item[0],
            ),
        )
        period, statement = ranked[-1]
        return period, statement.as_of_date, statement

    today = date.today()
    latest_year = today.year - 1 if today.month <= 3 else today.year
    return f"FY{latest_year}", date(latest_year, 3, 31), None

def _statement_from_upload(
    entity_id: str,
    period: str,
    as_of_date: date,
    source: str,
    base_statement: FinancialStatement | None,
    overrides: dict[str, float],
) -> FinancialStatement:
    line_items = dict((base_statement.line_items if base_statement else {}) or {})
    for key, value in overrides.items():
        if value > 0:
            line_items[key] = round(value, 2)

    if line_items.get("revenue_operating", 0) > 0 and line_items.get("total_income", 0) <= 0:
        line_items["total_income"] = line_items["revenue_operating"]

    # EBIT is rarely printed on a statement: derive it when the extraction did not find it (a statement read
    # from an upload has PBT and finance cost, or EBITDA and depreciation) — a missing EBIT is not zero
    if line_items.get("ebit", 0) <= 0:
        if line_items.get("pbt", 0) > 0 and line_items.get("finance_cost", 0) > 0:
            line_items["ebit"] = round(line_items["pbt"] + line_items["finance_cost"], 2)
        elif line_items.get("ebitda", 0) > 0 and line_items.get("depreciation", 0) > 0:
            line_items["ebit"] = round(line_items["ebitda"] - line_items["depreciation"], 2)
    if (line_items.get("depreciation", 0) <= 0 and line_items.get("ebitda", 0) > 0
            and 0 < line_items.get("ebit", 0) <= line_items["ebitda"]):
        line_items["depreciation"] = round(line_items["ebitda"] - line_items["ebit"], 2)

    rhs = (
        line_items.get("total_equity", 0)
        + line_items.get("long_term_debt", 0)
        + line_items.get("current_liabilities", 0)
    )
    if rhs > 0 and line_items.get("total_assets", 0) < rhs:
        line_items["total_assets"] = round(rhs, 2)

    return FinancialStatement(
        entity_id=entity_id,
        period=period,
        statement_type=base_statement.statement_type if base_statement else "standalone",
        source=source,
        as_of_date=as_of_date,
        line_items=line_items,
    )

def _apply_facility(company_data: dict, wanted: dict) -> list:
    """The facility the application requests (amount, tenor, type, purpose) replaces the one on the
    borrower record, so the credit case assesses what this application asks for."""
    fac = company_data.get("facility")
    if fac is None or not wanted:
        return []
    from src.models.canonical_model import FacilityType

    applied = []
    amount = wanted.get("amount_cr")
    if amount not in (None, ""):
        fac.amount_requested_cr = round(float(amount), 4)
        if getattr(fac, "proposed_limit_cr", None) is not None:
            fac.proposed_limit_cr = fac.amount_requested_cr
        applied.append("amount_requested_cr")
    if wanted.get("tenor_months") not in (None, ""):
        fac.tenor_months = int(float(wanted["tenor_months"]))
        applied.append("tenor_months")
    if wanted.get("purpose"):
        fac.purpose = str(wanted["purpose"])
        applied.append("purpose")
    try:
        fac.facility_type = FacilityType(wanted.get("facility_type"))
        applied.append("facility_type")
    except ValueError:
        pass                                # an LOS facility type the engine does not know: keep the record's
    return applied


def apply_verified_overrides(company_data: dict, overrides: dict) -> dict:
    """Values a person verified (overrode) in the LOS, applied to the borrower record before a run:

        {"financials": {period: {line_item: value}}, "collateral": {description: market_value_cr},
         "facility": {amount_cr, tenor_months, facility_type, purpose}}   # the application's request

    A verified value replaces the extracted / recorded one for that run, and later engine steps
    recompute everything that depends on it. Returns what was applied."""
    applied = {"financials": [], "collateral": []}
    financials = dict(company_data.get("financials") or {})
    stmt = overrides.get("statement")
    if stmt:
        # a prospect's statement: the figures a person accepted from its audited statements, over what an
        # earlier run extracted (the extraction reads the P&L only — debt and net worth would stay zero)
        borrower = company_data.get("borrower")
        prior = financials.get(stmt["period"])
        items = dict(getattr(prior, "line_items", None) or {})
        items.update({k: round(float(v), 4) for k, v in stmt["items"].items()})
        financials[stmt["period"]] = FinancialStatement(
            entity_id=getattr(borrower, "entity_id", "") or "", period=stmt["period"], statement_type="standalone",
            source=getattr(prior, "source", None) or "audited", as_of_date=date.fromisoformat(stmt["as_of"]),
            line_items=items)
        applied["financials"] += [f"{stmt['period']}.{k}" for k in stmt["items"]]
    for period, items in (overrides.get("financials") or {}).items():
        fs = financials.get(period)
        if fs is None:
            continue
        line_items = dict(fs.line_items or {})
        for key, value in items.items():
            line_items[key] = round(float(value), 4)
            applied["financials"].append(f"{period}.{key}")
        financials[period] = FinancialStatement(entity_id=fs.entity_id, period=fs.period,
                                                statement_type=fs.statement_type, source=fs.source,
                                                as_of_date=fs.as_of_date, line_items=line_items)
    company_data["financials"] = financials
    wanted = overrides.get("collateral") or {}
    for c in company_data.get("collateral") or []:
        desc = getattr(c, "description", None)
        if desc in wanted:
            c.market_value_cr = round(float(wanted[desc]), 4)
            applied["collateral"].append(desc)
    applied["facility"] = _apply_facility(company_data, overrides.get("facility") or {})
    company_data["verified_overrides"] = applied
    return applied


def apply_uploaded_financial_overrides(company_data: dict, extraction: dict, emit=None) -> None:
    if not extraction:
        return

    borrower = company_data.get("borrower")
    if borrower is None:
        return

    financials = dict(company_data.get("financials") or {})
    latest_period, latest_as_of, latest_statement = _latest_financial_context(financials)
    selected_docs = extraction.get("selected_documents") or {}
    override_summary: dict[str, object] = {
        "public_baseline": company_data.get("data_provider", "internal"),
        "latest_period": latest_period,
        "latest_rm_documents_override": False,
    }

    audited_data = ((extraction.get("financials") or {}).get("audited")) or {}
    audited_values = {
        "revenue_operating": _first_numeric(audited_data.get("revenue")),
        "total_income": _first_numeric(audited_data.get("total_income")),
        "ebitda": _first_numeric(audited_data.get("ebitda")),
        "pat": _first_numeric(audited_data.get("pat")),
        "pbt": _first_numeric(audited_data.get("pbt")),
        "depreciation": _first_numeric(audited_data.get("depreciation")),
        "finance_cost": _first_numeric(audited_data.get("finance_cost")),
    }
    audited_values = {key: value for key, value in audited_values.items() if value > 0}
    # A value a person verified in the LOS wins over the extracted one (apply_verified_overrides).
    verified = set((company_data.get("verified_overrides") or {}).get("financials") or [])
    if verified:
        audited_values = {k: v for k, v in audited_values.items() if f"{latest_period}.{k}" not in verified}
    # A document for an earlier year must not overwrite the latest period (e.g. annual_report_fy2024.pdf
    # selected while the latest statement is FY2025). Files without a year in the name keep the old behaviour.
    import re
    doc_year = re.search(r"fy\s*_?(\d{4})", str(selected_docs.get("audited_financials") or ""), flags=re.I)
    if audited_values and doc_year and not financials:
        # A new prospect has no statements yet: the uploaded audited statement is the first one, for
        # the year it states (not a year guessed from today's date).
        year = int(doc_year.group(1))
        latest_period, latest_as_of = f"FY{year}", date(year, 3, 31)
        override_summary["latest_period"] = latest_period
    if audited_values and doc_year and f"FY{doc_year.group(1)}" != latest_period:
        override_summary["audited_override_skipped"] = (
            f"{selected_docs.get('audited_financials')} is for FY{doc_year.group(1)}, latest period is {latest_period}")
        if emit:
            emit(f"Not overriding {latest_period} with {selected_docs.get('audited_financials')} (different year).")
        audited_values = {}
    candidate = (_statement_from_upload(borrower.entity_id, latest_period, latest_as_of, "rm_upload_audited",
                                        latest_statement, audited_values) if audited_values else None)
    if candidate is not None and latest_statement is not None:
        # Extracted figures may not replace a statement if they make it internally inconsistent
        # (EBITDA / PAT no longer reconcile) while the reported statement was consistent.
        from src.engines.validation_engine import validate_ebitda_consistency, validate_pat_consistency
        broken = [e.exception_code for e in validate_ebitda_consistency(candidate) + validate_pat_consistency(candidate)]
        was_ok = not (validate_ebitda_consistency(latest_statement) + validate_pat_consistency(latest_statement))
        if broken and was_ok:
            override_summary["audited_override_skipped"] = (
                f"extracted figures from {selected_docs.get('audited_financials')} do not reconcile ({', '.join(broken)})")
            if emit:
                emit(f"Not overriding {latest_period}: extracted figures do not reconcile ({', '.join(broken)}).")
            audited_values = {}
    if audited_values:
        financials[latest_period] = candidate
        company_data["financials"] = financials
        override_summary["latest_rm_documents_override"] = True
        override_summary["audited_source_file"] = selected_docs.get("audited_financials")
        override_summary["audited_override_metrics"] = sorted(audited_values.keys())
        if emit:
            emit("Applying latest RM-uploaded audited financials over Probe baseline...")

    provisional_data = extraction.get("provisional") or {}
    provisional_values = {
        "revenue_operating": _first_numeric(provisional_data.get("provisional_revenue")),
        "ebitda": _first_numeric(provisional_data.get("provisional_ebitda")),
        "pat": _first_numeric(provisional_data.get("provisional_pat")),
        "pbt": _first_numeric(provisional_data.get("provisional_pbt")),
        "depreciation": _first_numeric(provisional_data.get("provisional_depreciation")),
        "finance_cost": _first_numeric(provisional_data.get("provisional_finance_cost")),
        "tax_expense": _first_numeric(provisional_data.get("provisional_tax")),
    }
    provisional_values = {key: value for key, value in provisional_values.items() if value > 0}
    if provisional_values:
        company_data["provisional"] = _statement_from_upload(
            borrower.entity_id,
            f"{latest_period} (P)",
            date.today(),
            "rm_upload_provisional",
            latest_statement,
            provisional_values,
        )
        override_summary["latest_rm_documents_override"] = True
        override_summary["provisional_source_file"] = selected_docs.get("provisional")
        override_summary["provisional_override_metrics"] = sorted(provisional_values.keys())
        if emit:
            emit("Using latest RM-uploaded provisional / management financials for current-period analysis...")

    exchange_data = extraction.get("exchange") or {}
    nine_month_revenue = _first_numeric(exchange_data.get("nine_month_revenue"))
    exchange_revenue = nine_month_revenue or _first_numeric(exchange_data.get("revenue"))
    if exchange_revenue > 0:
        annualized_revenue = round(exchange_revenue * (12 / 9), 2) if nine_month_revenue else exchange_revenue
        company_data["exchange_filing"] = FinancialStatement(
            entity_id=borrower.entity_id,
            period=f"9M {date.today().year}",
            statement_type="standalone",
            source="rm_upload_exchange",
            as_of_date=date.today(),
            line_items={
                "revenue_operating": annualized_revenue,
                "total_income": annualized_revenue,
            },
        )
        override_summary["latest_rm_documents_override"] = True
        override_summary["exchange_source_file"] = selected_docs.get("exchange")
        override_summary["exchange_annualized_revenue_cr"] = annualized_revenue

    debt_schedule = (extraction.get("debt_schedule") or {}).get("facilities") or []
    uploaded_exposure: list[ExistingExposure] = []
    for idx, facility in enumerate(debt_schedule, start=1):
        if not isinstance(facility, dict):
            continue
        sanctioned = _first_numeric(facility.get("sanctioned"))
        outstanding = _first_numeric(facility.get("outstanding"))
        utilization = round(outstanding / sanctioned * 100, 1) if sanctioned else 0.0
        uploaded_exposure.append(ExistingExposure(
            facility_id=f"UPL-EXP-{borrower.entity_id}-{idx}",
            entity_id=borrower.entity_id,
            facility_type=str(facility.get("facility_type") or "uploaded_facility"),
            sanctioned_limit_cr=sanctioned,
            outstanding_cr=outstanding,
            utilization_pct=utilization,
            classification="RM Uploaded",
        ))
    if uploaded_exposure:
        company_data["existing_exposure"] = uploaded_exposure
        total_uploaded_debt = round(sum(
            exposure.outstanding_cr or exposure.sanctioned_limit_cr for exposure in uploaded_exposure
        ), 2)
        latest_financials = dict(company_data.get("financials") or {})
        debt_period, debt_as_of, debt_statement = _latest_financial_context(latest_financials)
        latest_financials[debt_period] = _statement_from_upload(
            borrower.entity_id,
            debt_period,
            debt_as_of,
            debt_statement.source if debt_statement else "rm_upload_audited",
            debt_statement,
            {
                "total_debt": total_uploaded_debt,
                "long_term_debt": round(total_uploaded_debt * 0.65, 2),
            },
        )
        company_data["financials"] = latest_financials
        override_summary["latest_rm_documents_override"] = True
        override_summary["debt_schedule_source_file"] = selected_docs.get("debt_schedule")
        override_summary["uploaded_facilities"] = len(uploaded_exposure)
        if emit:
            emit("Replacing public debt placeholders with RM-uploaded debt schedule...")

    if override_summary["latest_rm_documents_override"]:
        company_data["financial_data_strategy"] = override_summary

    # ── Wire optional document data into company_data for fact pack ──
    site_visit = extraction.get("site_visit") or {}
    if site_visit and site_visit.get("full_text"):
        company_data["site_visit_extraction"] = site_visit
        if emit:
            emit("Site visit report extracted — observations will feed into CAM narrative...")

    valuation = extraction.get("valuation") or {}
    if valuation and (valuation.get("market_value") or valuation.get("full_text")):
        company_data["valuation_extraction"] = valuation
        if emit:
            emit("Valuation report extracted — collateral data will feed into CAM narrative...")

    bank_stmt = extraction.get("bank_statement") or {}
    if bank_stmt and (bank_stmt.get("account_number") or bank_stmt.get("full_text")):
        company_data["bank_statement_extraction"] = bank_stmt
        if emit:
            emit("Bank statement extracted — conduct data will feed into CAM narrative...")
