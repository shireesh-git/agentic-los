"""
The carry-forward agent (R-P3): the Disbursement Maker's operational record proposed from what the
application already decided, so the maker confirms instead of retyping.

    interest terms        the sanctioned facility pricing: benchmark, spread, rate, reset, penal rate
    repayment (Annex I)   the facility's tenor, moratorium and repayment frequency
    fee collection        the fees approved at AP (pricing & fees)
    security (Annex IV)   the securities record: type, description, facility, value, valuation date

Each value is a field-store proposal in the ``dis_carry`` domain (verified at the Disbursement
Maker), with the record it came from as evidence. List rows are matched on their natural keys (fee
nature and facility; security id), so a person's saved row is found again, never duplicated. A
missing source gives an unavailable proposal, never a guess.
"""

from __future__ import annotations

import re
from typing import Optional

from src.los.reconcile import _p

DOMAIN = "dis_carry"
_FEE_NATURE = (("processing", "processing"), ("upfront", "upfront"), ("annual", "annual_review"),
               ("review", "annual_review"), ("stamp", "stamp_duty"))


def _primary(app: dict) -> Optional[dict]:
    facs = app.get("facilities") or []
    return next((f for f in facs if f.get("facility_nature") == "fund_based"), facs[0] if facs else None)


def _num(text) -> Optional[float]:
    m = re.search(r"(-?[0-9]+(?:\.[0-9]+)?)", str(text or ""))
    return float(m.group(1)) if m else None


def resolve_interest(ctx: dict) -> list[dict]:
    app, reg = ctx["app"], ctx["registry"]
    f = _primary(app)
    if not f:
        return []
    fid = f["facility_id"]
    fp = f.get("pricing") or {}
    ap = ((app.get("pricing") or {}).get("facilities") or {}).get(fid) or {}
    rate_card = (ctx.get("fact_pack") or {}).get("facility_pricing") or {}
    benchmark = fp.get("benchmark") or ap.get("proposed_benchmark")
    rate = fp.get("interest_rate") if fp.get("interest_rate") is not None else ap.get("proposed_rate")
    spread = fp.get("spread") if fp.get("spread") is not None else (
        round(float(ap["proposed_spread_bps"]) / 100, 4) if ap.get("proposed_spread_bps") not in (None, "") else None)
    penal = fp.get("penal_rate") if fp.get("penal_rate") is not None else _num(rate_card.get("penal_interest"))
    src = {"path": f"sanctioned facility {fid} pricing" + (" (Pricing & fees at AP)" if not fp.get("interest_rate") else "")}
    rows = (("benchmark", "Benchmark", benchmark, "text", src),
            ("rate", "Interest rate (%)", rate, "number", src),
            ("spread", "Spread (%)", spread, "number", src),
            ("effective_rate", "Effective rate (%)", fp.get("effective_rate") or rate, "number", src),
            ("reset_frequency", "Reset frequency", fp.get("reset_frequency"), "text", src),
            ("penal_rate", "Penal rate (% p.a. above the applicable rate)", penal, "number",
             {"path": "facility pricing" if fp.get("penal_rate") is not None
              else f"rate card: {rate_card.get('penal_interest') or 'not available'}"}))
    return [_p(f"{DOMAIN}.interest.{k}", f"Interest terms — {label}", v, provenance="source", source="record",
               registry=reg, value_type=vt, evidence=ev, target=["disops", "interest_terms", k], run_id=ctx.get("run_id"))
            for k, label, v, vt, ev in rows]


def resolve_repayment(ctx: dict) -> list[dict]:
    app, reg = ctx["app"], ctx["registry"]
    f = _primary(app)
    if not f:
        return []
    rp = f.get("repayment") or {}
    ev = {"path": f"sanctioned facility {f['facility_id']} (tenor and repayment)"}
    freq = rp.get("repayment_frequency")
    rows = (("tenor_months", "Tenor (months)", f.get("tenor_months"), "number"),
            ("moratorium_months", "Moratorium (months)", rp.get("moratorium_months"), "number"),
            ("instalment_frequency", "Instalment frequency", freq, "text"),
            ("repayment_conditions", "Repayment conditions",
             f"{str(rp['repayment_type']).replace('_', ' ')} repayment" if rp.get("repayment_type") else None, "text"))
    return [_p(f"{DOMAIN}.repayment.{k}", f"Repayment schedule (Annexure I) — {label}", v, provenance="source",
               source="record", registry=reg, value_type=vt, evidence=ev,
               target=["disops", "repayment_final", k], run_id=ctx.get("run_id"))
            for k, label, v, vt in rows]


def _fee_nature(text: str) -> str:
    t = str(text or "").lower()
    return next((n for k, n in _FEE_NATURE if k in t), "other")


def resolve_fees(ctx: dict) -> list[dict]:
    app, reg, out = ctx["app"], ctx["registry"], []
    for fee in (app.get("pricing") or {}).get("fees") or []:
        nature = _fee_nature(fee.get("nature"))
        fid = fee.get("facility_id") if fee.get("scope", "facility") == "facility" else None
        gross = fee.get("total_cr") if fee.get("total_cr") is not None else fee.get("amount_cr")
        key = f"{nature}_{(fid or 'common').lower().replace('-', '_')}"
        target = ["disops", "fees", {"find": {"nature": nature, "facility_id": fid}, "new": {
            "fee_id": None, "facility_id": fid, "nature": nature, "type": fee.get("type"),
            "scope": "facility" if fid else "common", "amount_cr": fee.get("amount_cr"), "pct": fee.get("pct"),
            "milestone": fee.get("milestone"), "comments": f"Carried from the fees approved at AP ({fee.get('fee_id')})",
            "gross_cr": None, "due_cr": None, "gst_cr": 0.0, "total_cr": None, "receipt_date": None,
            "received_cr": None, "balance_cr": None, "pending_due_date": None, "remarks": None, "origin": "agent"}}]
        ev = {"path": f"pricing & fees {fee.get('fee_id')}: {fee.get('nature')}"}
        out.append(_p(f"{DOMAIN}.fee.{key}.gross_cr", f"Fee collection — {fee.get('nature')} gross (₹ Cr)", gross,
                      provenance="source", source="record", registry=reg, value_type="number", evidence=ev,
                      target=target + ["gross_cr"], run_id=ctx.get("run_id")))
        out.append(_p(f"{DOMAIN}.fee.{key}.due_cr", f"Fee collection — {fee.get('nature')} due (₹ Cr)", gross,
                      provenance="source", source="record", registry=reg, value_type="number", evidence=ev,
                      target=target + ["due_cr"], run_id=ctx.get("run_id")))
    return out


def resolve_securities(ctx: dict) -> list[dict]:
    app, reg, out = ctx["app"], ctx["registry"], []
    for s in app.get("securities") or []:
        sid = s.get("security_id")
        if not sid:
            continue
        facility = (s.get("facility_ids") or [None])[0]
        target = ["disops", "security_refs", {"find": {"security_id": sid}, "new": {
            "security_id": sid, "los_security_id": sid, "type": None, "facility_id": facility, "description": None,
            "creation_status": "pending", "creation_date": None, "perfection_status": "pending", "perfection_eta": None,
            "valuation_date": None, "valuation_cr": None, "cersai": "pending", "roc": "pending",
            "cbs_security_no": None, "origin": "agent"}}]
        ev = {"path": f"securities record {sid}"}
        for k, label, v, vt in (("type", "type", s.get("type"), "text"),
                                ("description", "description", s.get("description"), "text"),
                                ("valuation_cr", "value (₹ Cr)", s.get("proposed_value_cr"), "number"),
                                ("valuation_date", "valuation date", s.get("valuation_date"), "text")):
            out.append(_p(f"{DOMAIN}.security.{sid.lower().replace('-', '_')}.{k}",
                          f"Security Annexure IV — {sid} {label}", v, provenance="source", source="record",
                          registry=reg, value_type=vt, evidence=ev, target=target + [k], run_id=ctx.get("run_id")))
    return out


RESOLVERS = {"carry_interest": resolve_interest, "carry_repayment": resolve_repayment,
             "carry_fees": resolve_fees, "carry_securities": resolve_securities}
# The disops sections the agent fills, and how a saved row is matched to its proposals
SECTIONS = {"interest_terms": None, "repayment_final": None, "fees": ("nature", "facility_id"),
            "security_refs": ("security_id",)}
