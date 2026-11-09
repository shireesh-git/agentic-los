"""What the agentic LOS hands to auditors and to the business:

    audit_pack       one page per case: who decided what and why, every data point with its source,
                     each Credit Risk change and the Sanctioning Authority's decision on it, the models
                     and agents used, the post-sanction checks and the full event log
    sanction_letter  the letter CAD sends the borrower, drafted from the sanctioned terms
    time_report      per case and overall: time at each stage, hands-on touches, what the agents filled,
                     against the bank's own estimate of the manual process (config/flow.yaml: baseline)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from html import escape
from typing import Optional

from src.flow import datapoints as dpx

TOUCH = {"edit", "skip", "change_accept", "change_dispute", "approve", "reject", "send_back", "doc_upload",
         "condition_confirm", "condition_reopen", "drawdown_edit", "cam_generate", "cam_rerun", "cam_upload",
         "challenge_response", "deviation_propose", "deviation_approve", "deviation_reject", "query_raise", "query_answer", "withdraw"}
_KIND_LABEL = {"created": "Proposal initiated", "data_acquired": "Data acquisition agents ran",
               "source_document": "Data source document uploaded","cam_generate": "CAM generation requested (CAM engine)",
               "cam_rerun": "CAM re-run requested", "cam_ready": "CAM ready", "cam_failed": "CAM generation stopped",
               "cam_upload": "Bank CAM ingested", "cam_download": "CAM downloaded", "edit": "Credit data field updated",
               "skip": "Field marked not provided", "change_accept": "Override concurred",
               "change_dispute": "Override returned with remarks", "approve": "Approved / submitted",
               "reject": "Declined", "send_back": "Returned with remarks", "doc_upload": "Document uploaded",
               "condition_confirm": "Condition confirmed", "condition_reopen": "Condition re-opened",
               "drawdown_edit": "Disbursement request edited", "chat_question": "Credit Copilot query",
               "challenge_response": "Key risk challenge answered", "deviation_propose": "Deviation mitigant recorded",
               "deviation_approve": "Deviation approved", "deviation_reject": "Deviation rejected",
               "query_raise": "Clarification asked (proposal kept at its stage)", "query_answer": "Clarification answered",
               "query_withdraw": "Clarification withdrawn", "withdraw": "Proposal withdrawn",
               "archive": "Proposal archived", "unarchive": "Proposal restored from the archive"}


def _t(at: str) -> datetime:
    return datetime.fromisoformat(at)


def _dur(seconds: float) -> str:
    s = int(max(seconds, 0))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m {s % 60:02d}s"
    return f"{s // 3600}h {(s % 3600) // 60:02d}m"


# ── time-saving report ──────────────────────────────────────────────────────

def case_times(case: dict, events: list[dict], stages: list[dict], now: datetime) -> dict:
    """Wall-clock time at each stage, the hands-on touches and what the agents filled."""
    labels = {s["id"]: s["label"] for s in stages}
    spans: dict[str, float] = {}
    cur, since = stages[0]["id"], _t(case["created_at"])
    for e in events:
        if e["kind"] in ("approve", "reject", "send_back"):
            at = _t(e["at"])
            spans[cur] = spans.get(cur, 0) + (at - since).total_seconds()
            cur, since = (e["detail"] or {}).get("to_stage") or cur, at
    end = now if case["status"] == "open" else _t(case["updated_at"])
    spans[cur] = spans.get(cur, 0) + max((end - since).total_seconds(), 0)
    touches = [e for e in events if e["kind"] in TOUCH and e.get("role") not in (None, "agent")]
    by_role: dict[str, int] = {}
    for e in touches:
        by_role[e["role"]] = by_role.get(e["role"], 0) + 1
    total = len(dpx.specs())
    dp = case.get("dp") or {}
    agent = sum(1 for v in dp.values() if v.get("status") == "filled"
                and (v.get("source") or {}).get("kind") in ("engine", "upload", "record"))
    person = sum(1 for v in dp.values() if (v.get("source") or {}).get("kind") == "person")
    cam = case.get("cam") or {}
    return {"case_id": case["case_id"], "borrower_name": case["borrower_name"], "status": case["status"],
            "stage_label": labels.get(case["stage"], case["stage"]),
            "elapsed_seconds": int(sum(spans.values())), "elapsed": _dur(sum(spans.values())),
            "stages": [{"id": s["id"], "label": s["label"], "seconds": int(spans.get(s["id"], 0)),
                        "time": _dur(spans.get(s["id"], 0))} for s in stages if s["id"] in spans],
            "touches": len(touches), "touches_by_role": by_role,
            "questions_answered": sum(1 for e in events if e["kind"] == "chat_question"),
            "clarifications": sum(1 for e in events if e["kind"] == "query_raise"),
            "datapoints": {"total": total, "by_agent": agent, "by_person": person,
                           "auto_pct": round(100.0 * agent / total, 1) if total else 0.0},
            "cam": {"mode": cam.get("mode"), "seconds": cam.get("duration_seconds"),
                    "sections_written": cam.get("sections_written"), "sections_reused": cam.get("sections_reused")}}


def time_report(rows: list[dict], baseline: dict) -> dict:
    n = len(rows)
    done = [r for r in rows if r["status"] != "open"]
    hours = (baseline or {}).get("hours") or {}
    return {"cases": rows, "count": n, "completed": len(done),
            "avg_touches": round(sum(r["touches"] for r in rows) / n, 1) if n else 0,
            "avg_auto_pct": round(sum(r["datapoints"]["auto_pct"] for r in rows) / n, 1) if n else 0,
            "avg_elapsed": _dur(sum(r["elapsed_seconds"] for r in done) / len(done)) if done else None,
            "baseline": {"label": (baseline or {}).get("label") or "Bank's estimate of the manual process",
                         "hours": hours, "total_hours": sum(float(v) for v in hours.values()),
                         "fields_typed_by_hand": len(dpx.specs())}}


# ── run analytics and insights ──────────────────────────────────────────────

def _avg(xs: list[float]) -> Optional[float]:
    return sum(xs) / len(xs) if xs else None


def run_analytics(cases: list[dict], events: dict[str, list[dict]], stages: list[dict], rows: list[dict],
                  queue_rows: list[dict], baseline: dict, now: datetime, days: int = 14) -> dict:
    """What the agents and the officers did across every proposal, read from the event log: where the time
    goes, how much the agents fetched or wrote, how often work came back, and plain-language insights."""
    allev = [e for c in cases for e in events.get(c["case_id"], [])]
    count = lambda kind: sum(1 for e in allev if e["kind"] == kind)

    # where the time goes
    stage_rows = []
    for s in stages:
        secs = [st["seconds"] for r in rows for st in r["stages"] if st["id"] == s["id"]]
        stage_rows.append({"id": s["id"], "label": s.get("short") or s["label"], "cases": len(secs),
                           "avg_seconds": int(_avg(secs) or 0), "avg": _dur(_avg(secs) or 0),
                           "max": _dur(max(secs)) if secs else "—",
                           "send_backs": sum(1 for e in allev if e["kind"] == "send_back"
                                             and (e["detail"] or {}).get("from_stage") == s["id"])})
    total_avg = sum(s["avg_seconds"] for s in stage_rows) or 1
    for s in stage_rows:
        s["share_pct"] = round(100 * s["avg_seconds"] / total_avg, 1)
    worked = [s for s in stage_rows if s["cases"]]
    bottleneck = max(worked, key=lambda s: s["avg_seconds"]) if worked else None

    # funnel: how far proposals have got
    order = [s["id"] for s in stages]
    reached = lambda c: (len(order) if c["status"] == "disbursed"
                         else order.index(c["stage"]) if c["stage"] in order else 0)
    funnel = [{"id": s["id"], "label": s.get("short") or s["label"],
               "count": sum(1 for c in cases if reached(c) >= i)} for i, s in enumerate(stages)]
    funnel.append({"id": "disbursed", "label": "Disbursed", "count": sum(1 for c in cases if c["status"] == "disbursed")})

    # CAM engine runs
    cams = [c.get("cam") or {} for c in cases]
    gen = [c for c in cams if c.get("mode") == "generate" and c.get("state") == "ready"]
    ready = [e for e in allev if e["kind"] == "cam_ready"]
    written = sum(int((e["detail"] or {}).get("sections_written") or 0) for e in ready)
    reused = sum(int((e["detail"] or {}).get("sections_reused") or 0) for e in ready)
    durs = [float(c["duration_seconds"]) for c in gen if c.get("duration_seconds")]
    cam = {"runs": len(ready), "first_runs": count("cam_generate"), "reruns": count("cam_rerun"),
           "ingested": sum(1 for c in cams if c.get("mode") == "upload"), "failed": count("cam_failed"),
           "avg_seconds": int(_avg(durs)) if durs else None, "avg": _dur(_avg(durs)) if durs else None,
           "fastest": _dur(min(durs)) if durs else None,
           "sections_written": written, "sections_reused": reused,
           "reuse_pct": round(100 * reused / (written + reused), 1) if written + reused else None,
           "llm_calls": sum(int((e["detail"] or {}).get("llm_calls") or 0) for e in ready),
           "models": sorted({m for m in ((e["detail"] or {}).get("model") for e in ready) if m}),
           "downloads": count("cam_download")}

    # data acquisition agents
    acqs = [c["acquisition"] for c in cases if c.get("acquisition")]
    srcs = [s for a in acqs for s in (a.get("sources") or {}).values()]
    flags = [v for a in acqs for v in a.get("verification") or []]
    ms = [float((a.get("full_run") or {}).get("ms") or a.get("ms") or 0) for a in acqs if a.get("state") == "done"]
    agents = {"prospects": len(acqs), "runs": count("data_acquired"),
              "avg_seconds": round(_avg(ms) / 1000, 1) if ms else None,
              "sources": {"api": sum(1 for s in srcs if s["status"] == "fetched"),
                          "document": sum(1 for s in srcs if s["status"] == "read"),
                          "awaiting": sum(1 for s in srcs if s["status"] not in ("fetched", "read"))},
              "network_calls": sum(len(a.get("network_calls") or []) for a in acqs),
              "checks": {k: sum(1 for v in flags if v.get("status") == k) for k in ("pass", "warn", "fail")},
              "documents_uploaded": count("source_document")}

    # who filled the credit data
    filled = {"agent": sum(r["datapoints"]["by_agent"] for r in rows),
              "officer": sum(r["datapoints"]["by_person"] for r in rows)}
    filled["empty"] = max(sum(r["datapoints"]["total"] for r in rows) - filled["agent"] - filled["officer"], 0)

    # decisions, rework, overrides
    changes = [ch for c in cases for ch in c.get("changes") or [] if ch.get("status") != "superseded"]
    decisions = {"approvals": count("approve"), "send_backs": count("send_back"), "declines": count("reject"),
                 "overrides": len(changes), "concurred": sum(1 for ch in changes if ch["status"] == "accepted"),
                 "returned": sum(1 for ch in changes if ch["status"] == "disputed"),
                 "copilot_questions": count("chat_question")}
    decisions["rework_pct"] = (round(100 * sum(1 for c in cases if any(
        e["kind"] == "send_back" for e in events.get(c["case_id"], []))) / len(cases), 1) if cases else 0)
    by_role: dict[str, int] = {}
    for r in rows:
        for k, v in r["touches_by_role"].items():
            by_role[k] = by_role.get(k, 0) + v

    # activity over the last `days` days
    today = now.date()
    per_day = {}
    for e in allev:
        d = _t(e["at"]).date()
        if (today - d).days < days:
            per_day[d] = per_day.get(d, 0) + 1
    activity = [{"date": (today - timedelta(days=i)).isoformat(),
                 "label": (today - timedelta(days=i)).strftime("%d %b"),
                 "events": per_day.get(today - timedelta(days=i), 0)} for i in range(days - 1, -1, -1)]

    sla = {k: sum(1 for r in queue_rows if r["status"] == "open" and r["sla_state"] == k)
           for k in ("ok", "amber", "breach")}

    # time saved against the bank's estimate of the manual process
    base_h = sum(float(v) for v in ((baseline or {}).get("hours") or {}).values())
    done = [r for r in rows if r["status"] != "open"]
    actual_h = (_avg([r["elapsed_seconds"] for r in done]) or 0) / 3600 if done else None
    saved = {"baseline_hours": base_h, "actual_hours": round(actual_h, 2) if actual_h is not None else None,
             "saved_pct": round(100 * (1 - actual_h / base_h), 1) if actual_h is not None and base_h else None,
             "fields_auto": filled["agent"]}

    # outcomes: what happened to the proposals, and whether people followed the engine
    by_id = {c["case_id"]: c for c in cases}
    sanctioned = [c for c in cases if c.get("sanction")]
    declined = [c for c in cases if c["status"] == "rejected"]
    decided = len(sanctioned) + len(declined)

    def to(c, done) -> Optional[float]:
        at = next((e["at"] for e in events.get(c["case_id"], []) if done(e)), None)
        return (_t(at) - _t(c["created_at"])).total_seconds() if at else None

    t_sanction = [x for x in (to(c, lambda e: e["kind"] == "approve" and (e["detail"] or {}).get("from_stage") == "sanction")
                              for c in sanctioned) if x is not None]
    t_disburse = [x for x in (to(c, lambda e: e["kind"] == "approve" and (e["detail"] or {}).get("status") == "disbursed")
                              for c in cases if c["status"] == "disbursed") if x is not None]
    hours = (baseline or {}).get("hours") or {}
    base_sanction = sum(float(hours.get(k) or 0) for k in ("cam_preparation", "credit_review", "sanction"))
    against_engine = [c for c in cases if c.get("deviations") and (c.get("sanction") or c["stage"] != stages[0]["id"])]
    engine_decline = [c for c in cases if (c.get("risk") or {}).get("tone") == "bad"]
    chal = sum(len(c.get("against") or []) for c in cases)
    answered = sum(len(c.get("responses") or {}) for c in cases)
    open_rows = [r for r in queue_rows if r["status"] == "open"]
    outcomes = {"total": len(cases), "sanctioned": len(sanctioned), "declined": len(declined),
                "disbursed": sum(1 for c in cases if c["status"] == "disbursed"),
                "in_progress": sum(1 for c in cases if c["status"] == "open"),
                "sanctioned_cr": round(sum(float(c["sanction"].get("limit_cr") or 0) for c in sanctioned), 2),
                "sanction_rate": round(100 * len(sanctioned) / decided, 1) if decided else None,
                "time_to_sanction": _dur(_avg(t_sanction)) if t_sanction else None,
                "time_to_disburse": _dur(_avg(t_disburse)) if t_disburse else None,
                "baseline_sanction_hours": base_sanction, "baseline_total_hours": saved["baseline_hours"],
                "against_engine": [{"case_id": c["case_id"], "borrower_name": c["borrower_name"],
                                    "by": c["deviations"][0]["by"], "status": c["status"]} for c in against_engine],
                "engine_decline": len(engine_decline),
                "engine_decline_declined": sum(1 for c in engine_decline if c["status"] == "rejected")}
    quality = {"sanction_rate": outcomes["sanction_rate"], "rework_pct": decisions["rework_pct"],
               "sla_within_pct": round(100 * sum(1 for r in open_rows if r["sla_state"] != "breach") / len(open_rows), 1)
               if open_rows else None,
               "challenges": chal, "challenges_answered": answered,
               "challenges_answered_pct": round(100 * answered / chal, 1) if chal else None,
               "overrides": decisions["overrides"], "concurred": decisions["concurred"], "returned": decisions["returned"],
               "deviations": sum(len(c.get("register") or []) for c in cases),
               "deviations_approved": sum(1 for c in cases for d in c.get("register") or [] if d["status"] == "approved"),
               "auto_pct": round(100 * filled["agent"] / max(filled["agent"] + filled["officer"] + filled["empty"], 1), 1),
               "touches_per_proposal": round(sum(r["touches"] for r in rows) / len(rows), 1) if rows else 0}
    for r in rows:
        c = by_id.get(r["case_id"]) or {}
        r["engine"] = (c.get("risk") or {}).get("label")
        r["engine_tone"] = (c.get("risk") or {}).get("tone")
        r["outcome"] = ("Disbursed" if c.get("status") == "disbursed" else "Declined" if c.get("status") == "rejected"
                        else "Withdrawn" if c.get("status") == "withdrawn"
                        else "Sanctioned" if c.get("sanction") else "In progress")
        r["deviation"] = bool(c.get("deviations"))

    return {"stages": stage_rows, "bottleneck": bottleneck, "funnel": funnel, "cam": cam, "agents": agents,
            "filled": filled, "decisions": decisions, "touches_by_role": by_role, "activity": activity,
            "sla": sla, "saved": saved, "outcomes": outcomes, "quality": quality,
            "insights": _insights(outcomes, quality, bottleneck, filled)}


def _insights(o: dict, q: dict, bottleneck: Optional[dict], filled: dict) -> list[dict]:
    """At most five plain statements about outcomes; each is computed, none is written by a model."""
    if not o["total"]:
        return [{"tone": "info", "title": "No proposals yet", "text": "Initiate a proposal to start measuring."}]
    out: list[dict] = []
    decided = o["sanctioned"] + o["declined"]
    out.append({"tone": "info", "title": "Decisions",
                "text": (f"{decided} of {o['total']} proposal(s) decided: {o['sanctioned']} sanctioned"
                         + (f" (₹{o['sanctioned_cr']:,.2f} Cr)" if o["sanctioned"] else "")
                         + f", {o['declined']} declined; {o['in_progress']} in progress.")})
    if o["against_engine"]:
        names = ", ".join(x["borrower_name"] for x in o["against_engine"][:3])
        out.append({"tone": "bad", "title": "Moved forward against the engine",
                    "text": f"{len(o['against_engine'])} proposal(s) went ahead although the CAM engine recommended "
                            f"Decline or a hard rule failed ({names}); each carries a recorded justification."})
    elif o["engine_decline"]:
        out.append({"tone": "good", "title": "Engine verdicts followed",
                    "text": f"{o['engine_decline_declined']} of {o['engine_decline']} proposal(s) the engine "
                            f"recommended declining were declined; none went ahead without a justification."})
    if o["time_to_sanction"]:
        out.append({"tone": "good", "title": "Speed",
                    "text": f"Sanction took {o['time_to_sanction']} on average from initiation, against about "
                            f"{o['baseline_sanction_hours']:.0f} h by hand"
                            + (f"; disbursement {o['time_to_disburse']} against {o['baseline_total_hours']:.0f} h."
                               if o["time_to_disburse"] else ".")})
    total = filled["agent"] + filled["officer"] + filled["empty"]
    if total:
        out.append({"tone": "good" if q["auto_pct"] >= 80 else "warn", "title": "Effort",
                    "text": f"Agents filled {q['auto_pct']:.0f}% of the credit data; officers made "
                            f"{q['touches_per_proposal']} manual touches per proposal."})
    if bottleneck and bottleneck["avg_seconds"] and len(out) < 5:
        out.append({"tone": "warn" if bottleneck["share_pct"] >= 40 else "info", "title": "Where proposals wait",
                    "text": f"{bottleneck['label']} holds proposals longest: {bottleneck['avg']} on average, "
                            f"{bottleneck['share_pct']:.0f}% of the time in the chain."})
    return out[:5]


# ── audit pack ───────────────────────────────────────────────────────────────

_CSS = """body{font-family:Segoe UI,Arial,sans-serif;color:#1f2937;margin:32px auto;max-width:1040px;padding:0 16px;font-size:13px}
h1{font-size:22px;margin:0 0 4px;color:#003366}h2{font-size:15px;color:#003366;border-bottom:2px solid #dce8f5;padding-bottom:4px;margin-top:28px}
table{border-collapse:collapse;width:100%;margin:8px 0}th,td{border:1px solid #e5e7eb;padding:6px 8px;text-align:left;vertical-align:top}
th{background:#f5f7fb;font-weight:600}.muted{color:#6b7280}.ok{color:#166534;font-weight:600}.bad{color:#991b1b;font-weight:600}
.note{background:#eff6ff;border:1px solid #bfdbfe;padding:10px 12px;border-radius:8px}pre{white-space:pre-wrap;margin:0;font-family:inherit}
@media print{body{margin:0}}"""


def _e(v) -> str:
    return escape("" if v is None else str(v))


def _value(sp: dict, v) -> str:
    return _e(dpx.display(sp, v))


def audit_pack(case: dict, events: list[dict], stages: list[dict], release_checks: list[dict],
               generated_at: str) -> str:
    cam = case.get("cam") or {}
    rows = []
    for sp in dpx.specs():
        d = (case.get("dp") or {}).get(sp["id"]) or {}
        src = d.get("source") or {}
        who = ""
        if src.get("kind") == "person":
            who = f"{_e(src.get('label'))}<br><span class='muted'>{_e(src.get('at'))}" \
                  + (f" · reason: {_e(src.get('reason'))}" if src.get("reason") else "") + "</span>"
        rows.append(f"<tr><td>{_e(sp['label'])}</td><td><pre>{_value(sp, d.get('value'))}</pre></td>"
                    f"<td>{_e(src.get('label') or ('Skipped by ' + d['skipped_by'] if d.get('skipped_by') else '—'))}"
                    + (f"<br><span class='muted'>{_e(src.get('detail'))}</span>" if src.get("detail") else "")
                    + f"</td><td>{who or '<span class=muted>agent</span>' if d.get('value') not in (None, '') else '—'}</td></tr>")
    changes = "".join(
        f"<tr><td>{_e(c['label'])}{(' (' + _e(c['period']) + ')') if c.get('period') else ''}</td>"
        f"<td>{_value(dpx.spec(c['dp']) or {}, c['old'])}</td><td>{_value(dpx.spec(c['dp']) or {}, c['new'])}</td>"
        f"<td>{_e(c['by_name'])}<br><span class='muted'>{_e(c.get('reason') or 'no reason given')}</span></td>"
        f"<td class='{'ok' if c['status'] == 'accepted' else 'bad'}'>{_e(c['status'])}</td>"
        f"<td>{_e(c.get('decided_by') or '—')}<br><span class='muted'>{_e(c.get('comment') or '')}</span></td></tr>"
        for c in case.get("changes") or []) or "<tr><td colspan=6 class=muted>No underwriting overrides</td></tr>"
    decisions = "".join(
        f"<tr><td>{_e(d['at'])}</td><td>{_e(d['stage_label'])}</td><td>{_e(d['by'])}</td>"
        f"<td>{_e({'approve': 'Approved', 'reject': 'Rejected', 'send_back': 'Sent back', 'withdraw': 'Withdrawn'}.get(d['action'], d['action']))}</td>"
        f"<td>{_e(d.get('comment') or '')}</td></tr>" for d in case.get("decisions") or []) \
        or "<tr><td colspan=5 class=muted>No decisions yet</td></tr>"
    risk = case.get("risk") or {}
    resp = case.get("responses") or {}
    how = {"justify": "Justification recorded", "override": "Figure overridden", "send_back": "Returned for documents",
           "reject": "Declined"}
    verdict = ""
    if risk:
        failed = risk.get("hard_rules", {}).get("failed") or []
        ratios = "".join(f"<tr><td>{_e(r['label'])}</td><td>{_e(r['display'])}</td><td>{_e(r['limit_display'])}</td>"
                         f"<td class='{'bad' if r['status'] == 'bad' else 'ok' if r['status'] == 'good' else ''}'>"
                         f"{_e({'bad': 'outside policy', 'warn': 'close to the limit', 'good': 'within policy'}.get(r['status'], '—'))}"
                         f"</td></tr>" for r in risk.get("ratios") or [])
        verdict = (f"<h2>CAM engine verdict and policy</h2><table><tr><th>Recommendation</th><td class="
                   f"'{'bad' if risk.get('tone') == 'bad' else ''}'>{_e(risk.get('label'))}</td></tr>"
                   f"<tr><th>Internal rating</th><td>{_e(risk.get('rating'))} ({_e(risk.get('score'))}/100)</td></tr>"
                   f"<tr><th>Hard rules failed</th><td>{_e('; '.join((h['label'] or h['code']) + ' — ' + (h['detail'] or '') for h in failed) or 'none')}</td></tr>"
                   f"</table><table><tr><th>Ratio ({_e(risk.get('period'))})</th><th>Value</th><th>Policy</th><th>Status</th></tr>{ratios}</table>")
    reg = "".join(f"<tr><td>{_e(d['label'])}</td><td>{_e(d['policy'])}</td>"
                  f"<td>{_e(d.get('mitigant') or '—')}<br><span class=muted>{_e(d.get('justification') or '')}"
                  f"{(' — ' + _e(d['proposed_by'])) if d.get('proposed_by') else ''}</span></td>"
                  f"<td>{_e(d['authority'])}</td><td class='{'ok' if d['status'] == 'approved' else 'bad'}'>"
                  f"{_e('not deviable' if not d['deviable'] else d['status'])}"
                  f"<br><span class=muted>{_e(d.get('decided_by') or '')} {_e(d.get('comment') or '')}</span></td></tr>"
                  for d in case.get("register") or [])
    if reg:
        verdict += (f"<h3>Deviation register</h3><table><tr><th>Breach</th><th>Policy</th><th>Mitigant · justification"
                    f"</th><th>Authority</th><th>Status</th></tr>{reg}</table>")
    devs = "".join(f"<tr><td>{_e(d['at'])}</td><td>{_e(d['stage_label'])}</td><td>{_e(d['by'])}</td>"
                   f"<td>{_e('; '.join(d['reasons']))}</td><td>{_e(d['text'])}</td></tr>" for d in case.get("deviations") or [])
    if devs:
        verdict += (f"<h3>Proceeded against the engine (deviations)</h3><table><tr><th>When</th><th>Stage</th><th>Who</th>"
                    f"<th>Despite</th><th>Justification</th></tr>{devs}</table>")
    chal = "".join(f"<tr><td>{_e(a['title'])}<br><span class=muted>{_e(a.get('severity'))}</span></td><td>{_e(a.get('what'))}</td>"
                   f"<td class='{'ok' if a['id'] in resp else 'bad'}'>"
                   + (f"{_e(how.get(resp[a['id']]['kind'], resp[a['id']]['kind']))} by {_e(resp[a['id']]['by'])}"
                      f"<br><span class=muted>{_e(resp[a['id']].get('note') or '')}</span>" if a['id'] in resp else "open")
                   + "</td></tr>" for a in case.get("against") or [])
    if chal:
        verdict += (f"<h3>Key risk challenges (Credit Challenge Agent) and how they were answered</h3><table><tr>"
                    f"<th>Challenge</th><th>What is wrong</th><th>Answer</th></tr>{chal}</table>")
    answers = [m for m in case.get("chat") or [] if m.get("kind") == "answer"]
    ai_answers = sum(1 for m in answers if m.get("provenance") == "ai")
    ai = [("CAM", {"generate": "Generated by the CAM engine (7 agents: ingestion, screening, financial analysis, "
                               "validation, benchmark, policy, narrative)",
                   "upload": "Uploaded by the RM; read by the CAM intake agent"
                             + (" from its embedded data sheet" if cam.get("read_by") == "sheet" else
                                " (headings, labels, page evidence)")}.get(cam.get("mode"), "—")),
          ("CAM engine run", cam.get("run_id") or "—"),
          ("Writing model", cam.get("model") or ("template (no AI)" if cam.get("narrative_mode") == "template" else "—")),
          ("AI calls in the last run", cam.get("llm_calls")),
          ("Sections rewritten / reused in the last run",
           f"{cam.get('sections_written')} / {cam.get('sections_reused')}" if cam.get("sections_total") else "—"),
          ("Questions answered in chat", f"{len(answers)} ({ai_answers} by the AI, figures checked against the record; "
                                         f"{len(answers) - ai_answers} from a record lookup)"),
          ("Credit challenge agent", f"{len(case.get('against') or [])} point(s) put to the approvers")]
    post = ""
    if case.get("sanction"):
        s = case["sanction"]
        conds = "".join(
            f"<tr><td>{_e(c['label'])}<br><span class=muted>{'Precedent' if c.get('when', 'precedent') == 'precedent' else 'Subsequent' + (' · due ' + c['due'] if c.get('due') else '')}</span></td>"
            f"<td class='{'ok' if c['status'] in ('verified', 'confirmed', 'auto', 'not_applicable') else 'bad'}'>"
            f"{_e(c['status'].replace('_', ' '))}<br><span class=muted>{_e(c.get('basis') or '')}</span></td><td>{'<br>'.join(_e(d['name']) + ' — ' + _e(d['check']['note']) + (' (demo)' if d.get('demo') else '') for d in c['documents']) or '—'}</td>"
            f"<td>{_e(c.get('confirmed_by') or ('agent' if c['status'] == 'verified' else '—'))}"
            f"<br><span class='muted'>{_e(c.get('note') or '')}</span></td></tr>" for c in case.get("conditions") or [])
        checks = "".join(f"<tr><td>{_e(c['label'])}</td><td class='{'ok' if c['ok'] else 'bad'}'>"
                         f"{'pass' if c['ok'] else 'fail'}</td><td>{_e(c['detail'])}</td></tr>" for c in release_checks)
        d, r = case.get("drawdown") or {}, case.get("release") or {}
        post = (f"<h2>Sanction and disbursement</h2><table><tr><th>Sanctioned</th><td>₹{s['limit_cr']:,.2f} Cr "
                f"{_e(s['product'])} by {_e(s['by'])} on {_e(s['at'])} (ref {_e(s['reference'])}, valid until "
                f"{_e(s['valid_until'])})</td></tr><tr><th>Drawdown</th><td>₹{float(d.get('amount_cr') or 0):,.2f} Cr to "
                f"{_e(d.get('account'))}, value date {_e(d.get('value_date'))}; prepared by {_e(d.get('prepared_by'))}"
                f"{(', edited by ' + _e(d['edited_by'])) if d.get('edited_by') else ''}</td></tr>"
                + (f"<tr><th>Released</th><td>₹{r['amount_cr']:,.2f} Cr by {_e(r['by'])} on {_e(r['at'])} — reference "
                   f"{_e(r['reference'])} <span class=muted>({_e(r.get('note'))})</span></td></tr>" if r else "")
                + f"</table><h3>Conditions precedent and subsequent</h3><table><tr><th>Condition</th><th>Status</th><th>Documents and the agent's "
                  f"check</th><th>Met by</th></tr>{conds}</table><h3>Pre-disbursement compliance checklist</h3><table><tr><th>Check</th>"
                  f"<th>Result</th><th>Detail</th></tr>{checks}</table>")
    log_rows = "".join(
        f"<tr><td>{_e(e['at'])}</td><td>{_e(e.get('actor_name') or '')}<br><span class=muted>{_e(e.get('role') or '')}</span>"
        f"</td><td>{_e(_KIND_LABEL.get(e['kind'], e['kind']))}</td><td class=muted>"
        f"{_e(', '.join(f'{k}: {v}' for k, v in (e.get('detail') or {}).items() if v not in (None, '', [], {})))[:400]}</td></tr>"
        for e in events)
    chat = "".join(f"<tr><td>{_e(m['at'])}</td><td>{_e(m['name'])}</td><td><pre>{_e(m['text'])}</pre></td></tr>"
                   for m in case.get("chat") or [])
    acq = case.get("acquisition") or {}
    data = ""
    if acq.get("sources"):
        how = {"fetched": "Fetched via API", "read": "Read from document"}
        srows = "".join(
            f"<tr><td>{_e(s['label'])}<br><span class=muted>{_e(s.get('requirement') or '')}</span></td>"
            f"<td>{_e(s.get('provider'))}<br><span class=muted>{_e('API live' if s.get('mode') == 'api' else 'API inactive: ' + (s.get('mode_reason') or ''))}</span></td>"
            f"<td class='{'ok' if s['status'] in how else 'bad'}'>{_e(how.get(s['status'], s['status'].replace('_', ' ')))}</td>"
            f"<td>{_e(s.get('summary') or s.get('error') or '')}<br><span class=muted>"
            f"{_e(', '.join(s.get('documents') or []) or ((s.get('provenance') or {}).get('url') or ''))}</span></td></tr>"
            for s in acq["sources"].values())
        vrows = "".join(f"<tr><td>{_e(c['label'])}</td><td class='{'ok' if c['status'] == 'pass' else 'bad'}'>"
                        f"{_e(c['status'])}</td><td>{_e(c['detail'])}</td></tr>" for c in acq.get("verification") or [])
        data = (f"<h2>Data acquisition (new prospect)</h2><p class=muted>Agents ran API first; where an API is not "
                f"connected the RM uploaded the document and the agent read it. Last run {_e(acq.get('finished_at'))}."
                f"</p><table><tr><th>Source</th><th>Provider · mode</th><th>Obtained</th><th>Summary · evidence</th></tr>"
                f"{srows}</table><h3>Verification agent: cross-checks</h3><table><tr><th>Check</th><th>Result</th>"
                f"<th>Detail</th></tr>{vrows}</table>")
    fac = case["facility"]
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Audit Trail Report — {_e(case['case_id'])}</title><style>{_CSS}</style></head><body>
<h1>Audit Trail Report · {_e(case['borrower_name'])}</h1>
<div class="muted">{_e(case['case_id'])} · {_e(str(fac['product']).replace('_', ' '))} ₹{float(fac['amount_cr']):,.2f} Cr ·
status <b>{_e(case['status'])}</b> · generated {_e(generated_at)}</div>
<p class="note">Agents proposed; named people decided. No AI output approved, rejected or changed a figure on this case
without a person: every credit data field shows its source, and every underwriting override was concurred with or
returned by the Sanctioning Authority by name.</p>
{data}
{verdict}
<h2>Decisions</h2><table><tr><th>When</th><th>Stage</th><th>Who</th><th>Decision</th><th>Comment</th></tr>{decisions}</table>
<h2>Underwriting overrides and the Sanctioning Authority's concurrence</h2>
<table><tr><th>Data point</th><th>Was</th><th>Now</th><th>Changed by · reason</th><th>Status</th><th>Reviewed by</th></tr>{changes}</table>
<h2>Credit data fields and their sources</h2><table><tr><th>Field</th><th>Value</th><th>Source</th><th>Entered by</th></tr>{''.join(rows)}</table>
<h2>AI and agents used</h2><table>{''.join(f'<tr><th>{_e(k)}</th><td>{_e(v)}</td></tr>' for k, v in ai)}</table>
{post}
<h2>Event log</h2><table><tr><th>When</th><th>Who</th><th>What</th><th>Detail</th></tr>{log_rows}</table>
<h2>Credit Copilot transcript</h2><table><tr><th>When</th><th>Who</th><th>Message</th></tr>{chat}</table>
</body></html>"""


def sanction_letter(case: dict, bank: str = "The Bank") -> str:
    s = case.get("sanction") or {}
    lines = lambda v: "".join(f"<li>{_e(x.lstrip('• ').strip())}</li>" for x in str(v or "").splitlines() if x.strip())
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sanction letter — {_e(case['borrower_name'])}</title><style>{_CSS} li{{margin:3px 0}}</style></head><body>
<p class="muted">DRAFT prepared by Credit Copilot from the sanctioned terms — Credit Administration to review before issue.</p>
<p>Ref: {_e(s.get('reference'))}<br>Date: {_e(str(s.get('at', ''))[:10])}</p>
<p>To<br><b>{_e(case['borrower_name'])}</b></p>
<p><b>Sub: Sanction of {_e(str(s.get('product', '')).replace('_', ' ').lower())} facility of ₹{float(s.get('limit_cr') or 0):,.2f} crore</b></p>
<p>We are pleased to inform you that {_e(bank)} has sanctioned the following facility, subject to the terms below and
to the execution of the documents listed in the conditions precedent.</p>
<table><tr><th>Facility</th><td>{_e(str(s.get('product', '')).replace('_', ' ').capitalize())}</td></tr>
<tr><th>Limit</th><td>₹{float(s.get('limit_cr') or 0):,.2f} crore</td></tr>
<tr><th>Tenor</th><td>{_e(s.get('tenor_months'))} months</td></tr><tr><th>Purpose</th><td>{_e(s.get('purpose'))}</td></tr>
<tr><th>Pricing</th><td>{_e(s.get('pricing') or 'As per the bank’s rate card')}</td></tr>
<tr><th>Validity</th><td>This sanction is valid until {_e(s.get('valid_until'))}</td></tr></table>
<h3>Security</h3><ul>{lines(s.get('security')) or '<li>As per the CAM</li>'}</ul>
<h3>Financial covenants</h3><ul>{lines(s.get('covenants')) or '<li>None</li>'}</ul>
<h3>Key terms and conditions</h3><ul>{lines(s.get('key_terms')) or '<li>As per the bank’s standard terms</li>'}</ul>
<h3>Conditions precedent to the first disbursement</h3><ul>{''.join(f"<li>{_e(c['label'])}</li>" for c in case.get('conditions') or [] if c.get('when', 'precedent') == 'precedent' and c['status'] != 'not_applicable')}</ul>
<h3>Conditions subsequent</h3><ul>{''.join(f"<li>{_e(c['label'])} — within {_e(c.get('within_days'))} days of the first disbursement</li>" for c in case.get('conditions') or [] if c.get('when') == 'subsequent' and c['status'] != 'not_applicable') or '<li>None</li>'}</ul>
<p>Please sign and return a copy of this letter as your acceptance.</p>
<p>For {_e(bank)}<br><br>Sanctioned by: {_e(s.get('by'))}</p>
<p>Accepted for {_e(case['borrower_name'])}: ____________________ (authorised signatory)</p></body></html>"""


# ── Decision Summary (C2): the CAM's first page, from the proposal as it stands ────────────────────────

_ST = {"good": "Within policy", "warn": "Close to the limit", "bad": "Outside policy"}
_HOW = {"justify": "Justification recorded", "override": "Figure overridden", "send_back": "Returned for documents",
        "reject": "Declined"}


def _md_row(cells) -> str:
    return "| " + " | ".join(str(c).replace("|", "/").replace("\n", " ") for c in cells) + " |\n"


def decision_summary(case: dict, points: dict, stage_label: str) -> str:
    """Markdown for the CAM's Decision Summary — built from data, no model wording: the proposal, the engine's
    verdict, ratios against policy with the confidence of each figure, size and quality checks, the risk
    challenges and how each was answered, the deviation register, justifications and the decision trail."""
    r = case.get("risk") or {}
    fac = case["facility"]
    p = lambda k: points.get(k) or {}
    status = {"open": f"In progress — {stage_label}", "disbursed": "Disbursed", "rejected": "Declined",
              "withdrawn": "Withdrawn"}.get(case["status"], case["status"])
    out = "## DECISION SUMMARY\n\n"
    out += (f"*Prepared from the proposal's record on {case['updated_at'][:16].replace('T', ' ')} — no model-written text "
            f"on this page. Proposal {case['case_id']} · {status}.*\n\n")
    out += "### The Proposal\n\n" + _md_row(["Borrower", "Facility", "Requested", "Recommended", "Tenor", "Purpose"])
    out += _md_row(["---"] * 6) + _md_row([
        case["borrower_name"], str(fac.get("product") or "").replace("_", " ").title(), p("amount_cr").get("display", "—"),
        p("recommended_cr").get("display", "—"), p("tenor_months").get("display", "—") + " months"
        if p("tenor_months").get("value") else "—", fac.get("purpose") or "—"]) + "\n"
    if r:
        failed = (r.get("hard_rules") or {}).get("failed") or []
        unver = (r.get("hard_rules") or {}).get("not_verified") or []
        out += "### Engine Verdict\n\n" + _md_row(["Item", "Result", "Detail"]) + _md_row(["---"] * 3)
        out += _md_row(["Recommendation", str(r.get("label") or "—").upper(), r.get("rationale") or ""])
        out += _md_row(["Internal rating", f"{r.get('rating') or '—'} (score {r.get('score')}/100)", "Rating scorecard"])
        out += _md_row(["Hard rules", f"{len(failed)} failed · {len(unver)} not verifiable",
                        "; ".join(h["label"] or h["code"] for h in failed) or "None failed"]) + "\n"
    rows = [k for k in ("dscr", "interest_cover", "debt_to_ebitda", "current_ratio", "tol_tnw", "debt_to_equity",
                        "security_cover") if p(k).get("value") is not None]
    if rows:
        out += "### Key Ratios Against Policy\n\n" + _md_row(["Ratio", "Value", "Policy", "Status", "Confidence"])
        out += _md_row(["---"] * 5)
        for k in rows:
            b, c = p(k).get("band") or {}, p(k).get("confidence") or {}
            out += _md_row([p(k)["label"], p(k)["display"], b.get("limit", "—"), _ST.get(b.get("status"), "—"),
                            f"{c.get('level', '—')} ({c.get('score', '—')})" if c else "—"])
        out += "\n"
    out += "### Size and Quality\n\n" + _md_row(["Check", "Result", "Detail"]) + _md_row(["---"] * 3)
    for k in ("sustainable_limit_cr", "ecl_cr", "ecl_stage", "earnings_quality", "revenue_truth", "ews_flags"):
        pt = p(k)
        if pt:
            out += _md_row([pt["label"], pt.get("display", "—"), ((pt.get("source") or {}).get("detail") or "")[:300]])
    out += "\n"
    figs = [k for k in ("revenue_cr", "ebitda_cr", "pat_cr", "net_worth_cr", "total_debt_cr") if p(k).get("value") is not None]
    if figs:
        out += "### Confidence of Key Figures\n\n" + _md_row(["Figure", "Value", "Confidence", "Basis"]) + _md_row(["---"] * 4)
        for k in figs:
            c = p(k).get("confidence") or {}
            out += _md_row([p(k)["label"], p(k)["display"], f"{c.get('level', '—')} ({c.get('score', '—')})",
                            c.get("basis", "—")])
        out += "\n"
    against, resp = case.get("against") or [], case.get("responses") or {}
    if against:
        out += "### Key Risk Challenges and Their Answers\n\n" + _md_row(["Challenge", "Severity", "Answer"])
        out += _md_row(["---"] * 3)
        for a in against:
            x = resp.get(a["id"])
            out += _md_row([a["title"], str(a.get("severity") or "").title(),
                            f"{_HOW.get(x['kind'], x['kind'])} by {x['by']}" + (f": {x['note']}" if x.get("note") else "")
                            if x else "Open"])
        out += "\n"
    reg = case.get("register") or []
    if reg:
        out += "### Deviation Register\n\n" + _md_row(["Breach", "Policy", "Mitigant", "Authority", "Status"])
        out += _md_row(["---"] * 5)
        for d in reg:
            out += _md_row([d["label"], d["policy"], d.get("mitigant") or "—", d["authority"],
                            "Not deviable" if not d["deviable"] else
                            d["status"].title() + (f" — {d['decided_by']}" if d.get("decided_by") else "")])
        out += "\n"
    if case.get("deviations"):
        out += "### Proceeded Against the Engine\n\n"
        for d in case["deviations"]:
            out += f"- **{d['by']}** ({d['stage_label']}) despite {'; '.join(d['reasons'])}: “{d['text']}”\n"
        out += "\n"
    if case.get("decisions"):
        out += "### Decision Trail\n\n" + _md_row(["When", "Stage", "Who", "Decision", "Remarks"]) + _md_row(["---"] * 5)
        for d in case["decisions"]:
            out += _md_row([d["at"][:16].replace("T", " "), d["stage_label"], d["by"],
                            {"approve": "Approved", "reject": "Declined", "send_back": "Returned", "withdraw": "Withdrawn"}.get(d["action"], d["action"]),
                            d.get("comment") or ""])
        out += "\n"
    return out
