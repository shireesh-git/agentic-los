"""
Deterministic financial projections and debt-service stress tests.

Computed once into the CAM fact pack so the LLM narrates these figures instead
of extrapolating its own. Method (same as the template renderer):

* Revenue: company guidance (sector_kpis.development_projections) when given,
  otherwise historical revenue CAGR capped to [-10%, +25%].
* EBITDA / PAT: average historical margins applied to projected revenue.
* Debt service: existing debt + requested facility, repaid evenly over the
  tenor; interest at the facility's quoted rate (10% if none).
* Operating cash flow: 85% of EBITDA.
"""

import re

OCF_TO_EBITDA = 0.85
DEFAULT_INTEREST_RATE = 0.10
DEFAULT_TENOR_MONTHS = 60
CAGR_FLOOR, CAGR_CAP = -0.10, 0.25


def _quoted_rate(facility_pricing: dict) -> float:
    """Final percentage in strings like 'MCLR + 0.80% = 9.20% p.a.' → 0.092."""
    text = str((facility_pricing or {}).get("interest_rate") or "")
    rates = re.findall(r"(\d+(?:\.\d+)?)\s*%", text)
    return float(rates[-1]) / 100 if rates else DEFAULT_INTEREST_RATE


def _assessment(dscr: float, min_dscr: float) -> str:
    if dscr >= min_dscr:
        return "Adequate"
    return "Tight" if dscr >= 1.0 else "Breach"


def build_projections(financial_summary: dict, facility_details: dict, facility_pricing: dict,
                      sector_kpis: dict, min_dscr: float) -> dict:
    periods_data = (financial_summary or {}).get("periods") or {}
    periods = sorted(periods_data)
    if len(periods) < 2:
        return {"available": False,
                "reason": "At least two years of financials are needed for projections."}

    first, last = periods_data[periods[0]], periods_data[periods[-1]]
    n_years = len(periods) - 1
    base_rev = last.get("revenue_cr") or 0
    raw_cagr = (base_rev / max(first.get("revenue_cr") or 1, 0.01)) ** (1 / n_years) - 1
    rev_cagr = min(max(raw_cagr, CAGR_FLOOR), CAGR_CAP)
    ebitda_margin = sum(periods_data[p].get("ebitda_margin_pct") or 0 for p in periods) / len(periods)
    pat_margin = sum(periods_data[p].get("pat_margin_pct") or 0 for p in periods) / len(periods)

    guidance = (sector_kpis or {}).get("development_projections") or {}
    guided = {1: guidance.get("projected_revenue_fy26_cr"), 2: guidance.get("projected_revenue_fy27_cr")}
    try:
        base_year = int(periods[-1].split("-")[0].upper().replace("FY", ""))
    except ValueError:
        base_year = 2024

    years = []
    for i in range(1, 4):
        if guided.get(i):
            revenue, basis = guided[i], "Company guidance"
        elif any(guided.values()):
            anchor_year = max(k for k, v in guided.items() if v)
            revenue, basis = guided[anchor_year] * (1 + rev_cagr) ** (i - anchor_year), "Guidance + CAGR"
        else:
            revenue, basis = base_rev * (1 + rev_cagr) ** i, "Historical CAGR"
        years.append({"year": f"FY{base_year + i}", "basis": basis, "revenue_cr": revenue,
                      "ebitda_cr": revenue * ebitda_margin / 100, "pat_cr": revenue * pat_margin / 100})

    facility_details = facility_details or {}
    total_debt = (last.get("total_debt_cr") or 0) + (facility_details.get("amount_requested_cr") or 0)
    tenor_months = facility_details.get("tenor_months") or DEFAULT_TENOR_MONTHS
    rate = _quoted_rate(facility_pricing)
    annual_principal = total_debt / max(tenor_months / 12, 1)

    for i, year in enumerate(years):
        outstanding = max(total_debt - annual_principal * i, 0)
        interest = outstanding * rate
        ocf = year["ebitda_cr"] * OCF_TO_EBITDA
        year.update(operating_cash_flow_cr=ocf, principal_cr=annual_principal, interest_cr=interest,
                    dscr=ocf / max(annual_principal + interest, 0.01))
        year["assessment"] = _assessment(year["dscr"], min_dscr)

    base_service = annual_principal + total_debt * rate
    y1 = years[0]
    scenarios = [
        ("Base case", y1["ebitda_cr"]),
        ("Revenue -10%", y1["revenue_cr"] * 0.90 * ebitda_margin / 100),
        ("Costs +10% (EBITDA -15%)", y1["ebitda_cr"] * 0.85),
        ("Combined stress", y1["revenue_cr"] * 0.90 * ebitda_margin * 0.85 / 100),
    ]
    stress = []
    for name, ebitda in scenarios:
        dscr = ebitda * OCF_TO_EBITDA / max(base_service, 0.01)
        stress.append({"scenario": name, "dscr": dscr, "assessment": _assessment(dscr, min_dscr)})

    def _round(obj):
        if isinstance(obj, float):
            return round(obj, 2)
        if isinstance(obj, dict):
            return {k: _round(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_round(v) for v in obj]
        return obj

    return _round({
        "available": True,
        "base_period": periods[-1],
        "assumptions": {
            "revenue_method": "Company guidance" if any(guided.values()) else "Historical CAGR (capped -10% to +25%)",
            "historical_revenue_cagr_pct": raw_cagr * 100,
            "applied_revenue_cagr_pct": rev_cagr * 100,
            "avg_ebitda_margin_pct": ebitda_margin,
            "avg_pat_margin_pct": pat_margin,
            "ocf_to_ebitda_pct": OCF_TO_EBITDA * 100,
            "interest_rate_pct": rate * 100,
            "tenor_months": tenor_months,
            "debt_basis_cr": total_debt,
            "min_dscr_policy": min_dscr,
        },
        "projected_years": years,
        "dsra_requirement_cr": base_service * 0.25,  # one quarter of annual debt service
        "stress_tests": stress,
    })
