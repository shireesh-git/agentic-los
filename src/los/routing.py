"""Authority-driven workflow routing (R1).

The calculated authority — institution profile + product + amount + risk grade
+ policy deviations (+ E&S category where the ES process runs) — determines the
route an application takes, instead of one fixed chain for every case:

* which optional journey steps apply (CRP review, ESMS review, DMD / executive
  approval, the Recommendations committee, the final sanction committee, extra
  concurrence steps) — driven by the profile's module switches and the
  ``routing`` configuration,
* which **concurrences** the decision requires at each committee gate (an EVP
  note, a CRP note, an executive credit note, a board intimation …) — driven by
  the profile's delegation matrix,

and stores the selected route with the *basis*: why every conditional step was
included or excluded. The route is recorded when the application is created and
recalculated only when a material input changes (the reassessed amount or risk
grade, a new policy deviation, an E&S category decision). A non-material change
keeps the completed approvals; a change that moves the required authority flags
the route as ``material_change`` and the next approval requires an explicit
re-acknowledgement (reapproval) — the completed approvals are never silently
relied on for a different authority.
"""

from __future__ import annotations

import re
from typing import Optional

from src.los import authority as authmod
from src.los import profiles

# Concurrence markers in an authority label → the concurrence record they require
# (configurable per profile under ``routing.concurrence_markers``).
DEFAULT_CONCURRENCE_MARKERS = {
    "EVP note": "evp_note",
    "CRP note": "crp_note",
    "executive credit note": "executive_note",
    "board intimation": "board_intimation",
}

# Routing drivers an institution profile can gate optional steps on.
STEP_CONDITION_KEYS = ("product", "min_amount_cr", "max_amount_cr", "min_risk_grade",
                       "max_risk_grade", "es_category", "deviation_count_min")


def _grade_rank(grade: str) -> int:
    """AAA > AA > A > BBB > BB > B > CCC…  (lower rank = stronger credit)."""
    g = str(grade or "").strip().upper().split("/")[0]
    if g.startswith("AAA"):
        return 0
    if g.startswith("AA"):
        return 1
    if g.startswith("A"):
        return 2
    if g.startswith("BBB"):
        return 3
    if g.startswith("BB"):
        return 4
    if g.startswith("B"):
        return 5
    if g.startswith("CCC"):
        return 6
    if g.startswith("CC"):
        return 7
    if g.startswith("C"):
        return 8
    return 9 if g else -1


def routing_config(profile: dict) -> dict:
    return (profile or {}).get("routing") or {}


def concurrence_markers(profile: dict) -> dict:
    return {**DEFAULT_CONCURRENCE_MARKERS, **(routing_config(profile).get("concurrence_markers") or {})}


def concurrences_for(authority_label: str, profile: dict) -> list[dict]:
    """The concurrence records required by an authority label (matched case-insensitively)."""
    out, seen = [], set()
    label = (authority_label or "").lower()
    for marker, cid in concurrence_markers(profile).items():
        if marker.lower() in label and cid not in seen:
            seen.add(cid)
            out.append({"id": cid, "label": marker.title() + " concurrence"})
    return out


def step_conditions(profile: dict, step_id: str) -> dict:
    """Profile-level routing conditions for a step: the institution's own override
    (profile: routing: steps:) beats the base skeleton's — per-institution control."""
    base = profiles.get_profile("base")
    conds = (routing_config(base).get("steps") or {}).get(step_id) or {}
    override = (routing_config(profile).get("steps") or {}).get(step_id)
    if override is not None:
        conds = {**conds, **override} if override else {}
    return conds


def step_applies(step_id: str, profile: dict, inputs: dict) -> tuple[bool, str]:
    """Whether a routing-conditioned step applies, and why (the basis text)."""
    conds = step_conditions(profile, step_id)
    if not conds:
        return True, ""
    reasons = []
    for key, expected in conds.items():
        if key not in STEP_CONDITION_KEYS:
            continue
        if key == "product":
            want = expected if isinstance(expected, list) else [expected]
            if inputs.get("product") not in want:
                return False, f"product is {inputs.get('product') or 'not set'} (step needs {', '.join(want)})"
            reasons.append(f"product {inputs.get('product')}")
        elif key == "min_amount_cr":
            if (inputs.get("amount_cr") or 0) < float(expected):
                return False, f"amount {inputs.get('amount_cr')} Cr < {expected} Cr minimum"
            reasons.append(f"amount ≥ {expected} Cr")
        elif key == "max_amount_cr":
            if (inputs.get("amount_cr") or 0) > float(expected):
                return False, f"amount {inputs.get('amount_cr')} Cr > {expected} Cr maximum"
            reasons.append(f"amount ≤ {expected} Cr")
        elif key == "min_risk_grade":
            if _grade_rank(inputs.get("risk_grade") or "") > _grade_rank(expected):
                return False, f"risk grade {inputs.get('risk_grade') or 'not set'} is weaker than {expected}"
            reasons.append(f"risk grade {inputs.get('risk_grade')}")
        elif key == "max_risk_grade":
            if _grade_rank(inputs.get("risk_grade") or "") < _grade_rank(expected):
                return False, f"risk grade {inputs.get('risk_grade')} is stronger than {expected} (step not needed)"
            reasons.append(f"risk grade up to {expected}")
        elif key == "es_category":
            want = expected if isinstance(expected, list) else [expected]
            if (inputs.get("es_category") or "").upper() not in [str(w).upper() for w in want]:
                return False, f"E&S category is {inputs.get('es_category') or 'not set'} (step needs {', '.join(want)})"
            reasons.append(f"E&S category {inputs.get('es_category')}")
        elif key == "deviation_count_min":
            if (inputs.get("deviation_count") or 0) < int(expected):
                return False, f"{inputs.get('deviation_count') or 0} policy deviation(s) < {expected}"
            reasons.append(f"{inputs.get('deviation_count')} deviation(s)")
    return True, ("step applies: " + "; ".join(reasons)) if reasons else ""


def _sanction_role(profile: dict, wf) -> str:
    try:
        return wf.step("ap_sanction").role
    except Exception:
        return "sanction_committee"


def inputs_from_app(app: dict, profile: dict) -> dict:
    ca = app.get("credit_assessment") or {}
    # R11: the count includes the automatic policy deviations (the profile rules)
    devs = (len(app.get("manual_deviations") or []) + len(app.get("deviations") or [])
            + len(app.get("policy_deviation_items") or []))
    return {"product": app.get("product"),
            "amount_cr": app.get("amount_cr"),
            "risk_grade": ca.get("risk_grade") or (app.get("ratings") or {}).get("risk_grade"),
            "es_category": (app.get("esms") or {}).get("category"),
            "deviation_count": devs,
            "final": app.get("stage_id") in ("AP", "POS", "DIS")}


def _stage_for(app: dict, wf) -> str:
    """Which authority this route is the authority of record for: once the in-principle sanction
    has been taken — or the case has entered the appraisal stage — the next committee decision is
    the final sanction, so the route carries the *final* authority; before that, the route is
    the *preliminary* authority the in-principle committee will decide."""
    if (app.get("sanctions") or {}).get("IP"):
        return "final"
    try:
        stage = wf.step(app["step_id"]).stage_id if app.get("step_id") else None
    except Exception:
        stage = None
    return "final" if stage in ("AP", "POS", "DIS") else "preliminary"


def calculate(app: dict, profile: dict, wf) -> dict:
    """The route for this application now: included / excluded conditional steps (with the
    basis), the preliminary and final authority with their required concurrences, and the
    steps that would change if a re-appraisal moved the amount or the grade."""
    p = profile
    rid = (p.get("profile") or {}).get("id")
    inp = inputs_from_app(app, p)
    # enabled steps from the profile's journey; module switches already removed the others
    steps = list(wf.steps)
    included, excluded = [], []
    for s in steps:
        ok, why = step_applies(s.id, p, inp)
        (included if ok else excluded).append({"step": s.id, "stage": s.stage_id, "role": s.role,
                                                "name": s.name, "basis": why or ("module enabled by the institution profile")})
    # the authority at the in-principle and the final committee
    amount = inp.get("amount_cr") or 0
    grade = inp.get("risk_grade")
    devs = inp.get("deviation_count") or 0
    prelim = authmod.required_authority(amount, grade, deviations=devs, final=False, app=app,
                                        product=inp.get("product"))
    final = authmod.required_authority(amount, grade, deviations=devs, final=True, app=app,
                                       product=inp.get("product"))
    prelim_conc = concurrences_for(prelim["required"], p)
    final_conc = concurrences_for(final["required"], p)
    # what a stronger/weaker re-appraisal would change: probe the grade bands and amount bands
    would_change = _probe_changes(p, wf, inp)
    stage_last = {}
    for s in steps:
        stage_last[s.stage_id] = max(stage_last.get(s.stage_id, -1), s.index)
    pos = next((s.index for s in steps if s.id == app.get("step_id")), 0)
    route = {
        "version": 1,
        "status": "calculated",
        "position": max(int(app.get("position_index") or 0), pos),
        "stage_last": {**(app.get("routing", {}).get("stage_last") or {}), **stage_last},
        # the authority of record for each sanction: the snapshot when the case entered the
        # stage — a later recalculation in the same stage is carried on the route for the
        # record but does not impose its concurrences on a decision taken under the earlier
        # authority (completed approvals stay the approvals of record)
        "authority_of_record": {"preliminary_authority": prelim, "final_authority": final,
                                "preliminary_concurrences": prelim_conc, "final_concurrences": final_conc,
                                "concurrences": (prelim_conc + final_conc)},
        "profile": rid,
        "product": inp.get("product"),
        "inputs": {"amount_cr": amount, "risk_grade": grade,
                   "es_category": inp.get("es_category"), "deviation_count": devs},
        "preliminary_authority": prelim,
        "final_authority": final,
        "preliminary_concurrences": prelim_conc,
        "final_concurrences": final_conc,
        "sanction_role": _sanction_role(p, wf),
        "included": included,
        "excluded": excluded,
        "basis": [f"institution profile '{rid}'" + (f" · product {inp.get('product')}" if inp.get('product') else ""),
                  f"requested {amount:,.0f} Cr, risk grade {grade or 'not set'}, "
                  f"{devs} recorded policy deviation(s)"],
        "would_change_if": would_change,
        "stage": _stage_for(app, wf),
        "material_change": False,
        "reapproval_required": False,
        "calculated_at": None,
    }
    return route


def _probe_changes(p: dict, wf, inp: dict) -> list[str]:
    """The re-appraisal outcomes that would move the required authority (the route the next
    approval would have to be checked against)."""
    from src.los import products as prodmod
    out = []
    pid = (p.get("profile") or {}).get("id")
    try:
        full = profiles.get_profile(pid)
    except profiles.ProfileError:
        full = p
    product = inp.get("product")
    matrix = prodmod.approval_matrix(full, None, product, final=True)
    bands = [b[0] for b in matrix["table"] if b[0] != float("inf")]
    amount = inp.get("amount_cr") or 0
    if bands:
        if any(amount < b for b in bands):
            out.append(f"a sanctioned amount above {min(b for b in bands if b > amount):,.0f} Cr "
                       "moves the case to a higher authority band")
        if amount > (bands[0] if bands else 0):
            out.append("a materially lower sanctioned amount may reduce the required authority "
                       "(completed approvals remain valid)")
    if not (inp.get("risk_grade") or "").startswith(("AAA", "AA")):
        out.append("a reassessed risk grade of AA or stronger removes the sub-investment-grade "
                   "concurrence; a weaker grade keeps it")
    out.append("each newly recorded policy deviation escalates the required authority by the "
               "profile's deviation-escalation levels")
    return out


def public_route(route: Optional[dict]) -> Optional[dict]:
    """The route for JSON views: drops the heavy per-step lists (kept in the application record)."""
    if not route:
        return None
    return {k: v for k, v in route.items() if k not in ("included", "excluded")}


def record(app: dict, route: dict, at: str, note: str = "route calculated") -> dict:
    """Store the route (append-only history) on the application. When the required authority
    moves, the concurrences already recorded for earlier sanctions of the case are kept as
    the approvals of record (``prior_concurrences``) so the completed steps are not re-blocked;
    such a change is *recorded*, not re-approved — the reapproval flag is reserved for a
    move of the authority of record *after* the case has entered the appraisal stage (the
    final sanction still pending)."""
    app.setdefault("routing_history", [])
    prev = app.get("routing")
    entry = dict(route)
    entry["calculated_at"] = at
    entry["note"] = note
    entry.setdefault("prior_concurrences", [])
    if prev:
        if route.get("stage") != prev.get("stage"):
            route["authority_of_record"] = dict(route["authority_of_record"])
        moved = authority_moved(prev, route)
        # a move while the case is still ahead of the in-principle committee is recorded on the
        # route — the IP committee simply decides the (new) preliminary authority. A move of the
        # authority of record *after* the case has entered the appraisal stage (the final sanction
        # still pending) is a reapproval event: the committee must acknowledge the changed route
        # at ap_sanction before sanctioning.
        moved_final = moved and (route.get("stage") == "final")
        entry["material_change"] = moved or prev.get("material_change", False)
        entry["previous_route"] = prev.get("seq")
        entry["prior_concurrences"] = prev.get("prior_concurrences") or [
            {"id": c.get("id"), "label": c.get("label")} for c in (app.get("concurrences") or []) if c.get("approved_at")]
        entry["reapproval_required"] = bool(moved_final) or prev.get("reapproval_required", False)
    else:
        entry["reapproval_required"] = False
    app["routing_history"].append(entry)
    app["routing"] = entry
    return entry


def authority_moved(old: dict, new: dict) -> bool:
    """A material change: the required authority label or its concurrences differ."""
    def key(r):
        return ((r.get("final_authority") or {}).get("required", ""),
                sorted(c["id"] for c in r.get("final_concurrences") or []),
                sorted(c["id"] for c in r.get("preliminary_concurrences") or []))
    return key(old) != key(new)


def _completed_before(app: dict, when: str, step_id: str) -> bool:
    if not when:
        return False
    for e in reversed(app.get("history") or []):
        if e.get("to_step") == step_id and e.get("action") == "sanction":
            return True
    return False


def _reached_stage(app: dict, stage_id: str) -> bool:
    """Has the case left this stage? The recorded sanction is the durable record of it —
    a stage's committee having decided. (The journey position alone is not enough: a
    return to an earlier stage moves the position back while the stage's decision stands.)"""
    return bool((app.get("sanctions") or {}).get(stage_id))


def gate_message(app: dict, step_id: str, action: str) -> Optional[str]:
    """What the route requires before this decision: the concurrences of the authority being
    decided.

    The gate applies only to the authority *of record* for this sanction — the route snapshot
    taken when the case entered this stage (``authority_of_record``). A later recalculation
    (e.g. the re-assessed grade changing the preliminary label before the IP committee meets)
    is carried on the route for the record, but it does not impose its concurrences on a
    decision already taken under the earlier authority: completed approvals stay the approvals
    of record, and a move of the *final* authority after the case entered the appraisal stage
    flags a reapproval instead (the committee acknowledges the changed route at ap_sanction)."""
    route = app.get("routing") or {}
    if not route or action != "sanction":
        return None
    # the gate knows the case position (the workflow) through the app's journey: for a walk
    # (seeding) the position alone proves a stage is complete
    if step_id in ("ip_sanction", "ap_sanction"):
        stage_id = "IP" if step_id == "ip_sanction" else "AP"
        if _reached_stage(app, stage_id):
            return None
        snapshot = route.get("authority_of_record") or {}
        key = "preliminary_concurrences" if step_id == "ip_sanction" else "final_concurrences"
        key_auth = "preliminary_authority" if step_id == "ip_sanction" else "final_authority"
        conc = snapshot.get(key) if snapshot.get(key) is not None else route.get(key) or []
        prior = {c.get("id") for c in (route.get("prior_concurrences") or [])}
        done = {c.get("id") for c in (app.get("concurrences") or []) if c.get("approved_at")}
        missing = [c for c in conc if c["id"] not in done]
        if missing:
            # a note already signed for the *earlier* authority of record is carried as
            # ``prior_concurrences`` — it only stands when the authority label did not move
            # (e.g. a re-assessed grade at the same band); a move into a different authority
            # needs the new note(s) even when a stage-identical one was signed before
            aor = snapshot.get(key) or []
            auth_moved = bool(route.get("material_change")) and (
                (snapshot.get(key_auth) or {}).get("required")
                != (route.get(key_auth) or {}).get("required"))
            if not auth_moved:
                missing = [c for c in missing if c["id"] not in prior]
            # a note signed *for this authority of record* before the route was re-derived
            # (e.g. the note for the requested-amount authority, before the re-assessed
            # amount moved the label within the same band) stands as an approval of record
            if auth_moved:
                already_for_this = {c["id"] for c in aor if c["id"] in done}
                missing = [c for c in missing if c["id"] not in already_for_this]
        if missing:
            who = " and ".join(c["label"] for c in missing[:3])
            return ("The calculated authority for this case requires: " + who +
                    " — record the concurrence(s) before sanctioning")
    if route.get("reapproval_required") and step_id == "ap_sanction":
        ack = (app.get("routing_ack") or {})
        if not ack.get("approved_at"):
            return ("The route changed materially since the in-principle sanction (the required "
                    "authority moved) — the committee must acknowledge the new route before sanctioning")
    return None


def required_concurrences(app: dict, step_id: str) -> list[dict]:
    route = app.get("routing") or {}
    if step_id == "ap_sanction":
        return route.get("final_concurrences") or []
    if step_id == "ip_sanction":
        return route.get("preliminary_concurrences") or []
    return []
