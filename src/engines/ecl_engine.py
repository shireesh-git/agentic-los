"""Expected credit loss at origination (roadmap D6).

RBI's expected-credit-loss framework replaces incurred-loss provisioning for banks (from 1 April 2027 on the
roadmap). At origination the CAM shows what the proposal would cost in provisions on day one:

    stage   1 performing; 2 significant increase in credit risk (SMA-1 / SMA-2 with other lenders, or overdue
            more than 30 days); 3 credit-impaired (NPA status, or overdue more than 90 days)
    PD      12-month probability of default from the bank's master scale by internal grade; lifetime PD over
            the tenor for stage 2 (1 − (1 − PD)^years); 1.0 for stage 3
    LGD     loss given default: the unsecured LGD scaled by the uncovered share of exposure, floored for
            secured exposure — max(floor, unsecured × (1 − FSV / EAD))
    EAD     exposure at default: the limit × the credit-conversion factor for the product
    ECL     PD × LGD × EAD, and as a share of EAD

Every parameter is in config/rules.yaml → ``ecl``. The values shipped are demo values, labelled as such
everywhere they are shown; a bank replaces them with its validated PD / LGD models.
"""

from __future__ import annotations

from typing import Optional

DEFAULTS = {
    "label": "Bank master scale (demo values: replace with the bank's validated PD / LGD models)",
    "pd_12m": {"A": 0.0025, "B": 0.0075, "C": 0.025, "D": 0.08, "E": 0.20},
    "lgd": {"unsecured": 0.65, "secured_floor": 0.25},
    "ccf": {"working_capital": 0.75, "cash_credit": 0.75, "term_loan": 1.0, "project_finance": 1.0, "default": 1.0},
    "stage2": {"statuses": ["SMA-1", "SMA-2"], "dpd_over": 30},
    "stage3": {"statuses": ["Substandard", "Doubtful", "Loss", "NPA"], "dpd_over": 90},
}


def _cfg() -> dict:
    from src.core.config_manager import config
    got = config.get("rules", "ecl", default=None) or {}
    return {**DEFAULTS, **got, "lgd": {**DEFAULTS["lgd"], **(got.get("lgd") or {})},
            "ccf": {**DEFAULTS["ccf"], **(got.get("ccf") or {})},
            "pd_12m": {**DEFAULTS["pd_12m"], **(got.get("pd_12m") or {})}}


def _pct(v: float) -> str:
    return f"{v * 100:.2f}%"


def ecl(*, grade: Optional[str], amount_cr: float, tenor_months: Optional[int], product: str,
        fsv_cr: float, bureau_status: Optional[str], max_dpd: Optional[float], cfg: Optional[dict] = None) -> dict:
    cfg = cfg or _cfg()
    g = str(grade or "").strip()[:1].upper()
    if not g or g not in cfg["pd_12m"] or not amount_cr:
        return {"available": False, "reason": "No internal grade or amount to estimate expected credit loss from"}
    status = str(bureau_status or "").strip()
    dpd = float(max_dpd or 0)
    if status in cfg["stage3"]["statuses"] or dpd > cfg["stage3"]["dpd_over"]:
        stage, why = 3, f"credit-impaired: {status or f'{dpd:.0f} days past due'}"
    elif status in cfg["stage2"]["statuses"] or dpd > cfg["stage2"]["dpd_over"]:
        stage, why = 2, f"significant increase in credit risk: {status or f'{dpd:.0f} days past due'} with other lenders"
    else:
        stage, why = 1, "performing: no overdue or SMA status with other lenders"
    years = max(1.0, (tenor_months or 12) / 12)
    pd12 = float(cfg["pd_12m"][g])
    pd = 1.0 if stage == 3 else (1 - (1 - pd12) ** years if stage == 2 else pd12)
    ccf = float(cfg["ccf"].get(product, cfg["ccf"]["default"]))
    ead = round(amount_cr * ccf, 2)
    cover = (fsv_cr or 0) / ead if ead else 0
    unsecured, floor = float(cfg["lgd"]["unsecured"]), float(cfg["lgd"]["secured_floor"])
    lgd = max(floor, unsecured * max(0.0, 1 - cover))
    loss = round(pd * lgd * ead, 2)
    horizon = "12-month" if stage == 1 else ("lifetime" if stage == 2 else "credit-impaired")
    return {"available": True, "stage": stage, "stage_reason": why, "grade": g, "pd_12m": pd12, "pd": round(pd, 6),
            "pd_horizon": horizon, "years": years, "lgd": round(lgd, 4), "security_cover": round(cover, 2),
            "ccf": ccf, "ead_cr": ead, "ecl_cr": loss, "coverage": round(loss / ead, 6) if ead else 0.0,
            "display": f"₹{loss:,.2f} Cr ({_pct(loss / ead if ead else 0)} of exposure)",
            "basis": (f"Stage {stage} ({why}). {horizon.capitalize()} PD {_pct(pd)} (grade {g}, 12-month "
                      f"{_pct(pd12)}) × LGD {_pct(lgd)} (security cover {cover:.2f}x on FSV) × EAD ₹{ead:,.2f} Cr "
                      f"(limit ₹{amount_cr:,.2f} Cr × CCF {ccf:g}) = ₹{loss:,.2f} Cr."),
            "scale": cfg["label"], "demo": "demo" in str(cfg["label"]).lower()}


def from_fact_pack(company_data: dict, fact_pack: dict) -> dict:
    """ECL for the proposal from the fact pack the CAM engine built."""
    tiers = (fact_pack.get("policy_decisions") or {})
    grade = (tiers.get("tier3_recommendation") or {}).get("risk_grade") or \
        (tiers.get("tier2_risk_scores") or {}).get("risk_grade")
    fac = company_data.get("facility")
    product = str(getattr(getattr(fac, "facility_type", None), "value", getattr(fac, "facility_type", "")) or "")
    fsv = sum(float(getattr(c, "forced_sale_value_cr", 0) or 0) for c in company_data.get("collateral") or [])
    bureau = (((company_data.get("external_data") or {}).get("bureau_data") or {}).get("payload") or {})
    return ecl(grade=grade, amount_cr=float(getattr(fac, "amount_requested_cr", 0) or 0),
               tenor_months=getattr(fac, "tenor_months", None), product=product, fsv_cr=fsv,
               bureau_status=bureau.get("dpd_status") or bureau.get("worst_status_12m"),
               max_dpd=bureau.get("max_dpd_last_12m"))
