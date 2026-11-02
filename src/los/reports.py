"""R14 — downloadable case reports, derived from the stored application record.

Every report is a pure function of the application (its facilities, sanctions,
conditions, documents, events) — no external access. CSV output is
formula-injection safe: any cell that would be read as a spreadsheet formula
(starting with =, +, -, @, tab or CR) is prefixed with a single quote. Reports
carry the generation time and the application id; no secrets or file paths.
"""
from __future__ import annotations

from html import escape as _esc
from datetime import datetime

# The report types and their columns (what the bank can download per case).
CATALOG: dict[str, dict] = {
    "case_summary": {
        "name": "Case summary",
        "description": "Headline terms, the position at each stage, the open risks and the recent decisions.",
        "columns": ["Item", "Value"],
    },
    "sanction_record": {
        "name": "Sanction record",
        "description": "The sanctioned amount, the approval authority, the facility terms and the conditions.",
        "columns": ["Item", "Value"],
    },
    "audit_trail": {
        "name": "Audit trail",
        "description": "Every recorded event on the application, in order (who, what, when).",
        "columns": ["At", "Action", "Step", "By", "Role", "Comment"],
    },
    "document_checklist": {
        "name": "Document checklist",
        "description": "The document register: each document, its versions, its review state.",
        "columns": ["Document", "Kind", "Status", "Versions", "Last version", "Reviewed by"],
    },
    "conditions": {
        "name": "Conditions & covenants",
        "description": "The conditions precedent / subsequent and the covenants with their state.",
        "columns": ["ID", "Type", "Text", "Status", "Note"],
    },
    "disbursement": {
        "name": "Disbursement schedule",
        "description": "The tranches requested / paid against the sanctioned amount.",
        "columns": ["Tranche", "Amount (Cr)", "Value date", "Purpose", "Facility"],
    },
    "pipeline": {
        "name": "Pipeline timeline",
        "description": "Stage-by-stage history: every step the case moved through, who decided, what the decision was, and how long each step took.",
        "columns": ["Stage", "Step", "Role", "Entered", "Decided at", "Action", "By", "Days in step"],
    },
    "deviations": {
        "name": "Policy deviations",
        "description": "Every deviation on the case: the detected policy-rule breaches, the manual deviations and the committee-level deviations, with severity and the required authority.",
        "columns": ["ID", "Source", "Type", "Description", "Expected", "Actual", "Severity", "Required authority", "Status", "Raised by", "Raised at"],
    },
}


def _cell(value) -> str:
    """A formula-injection safe CSV cell."""
    s = "" if value is None else str(value)
    s = s.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    if s and s[0] in "=+-@\t":
        s = "'" + s
    if any(c in s for c in (',', '"', "\n")):
        s = '"' + s.replace('"', '""') + '"'
    return s


def _csv(columns: list[str], rows: list[dict], meta: list[str]) -> str:
    """RFC-4180 CSV: the meta lines (generation time, application, profile) then the table.
    A leading =, +, -, @ or tab in a data cell is neutralised (dropped) so no spreadsheet
    reads the value as a formula."""
    lines = [",".join(_cell(c) for c in meta)] + [",".join(_cell(c) for c in columns)]
    for r in rows:
        lines.append(",".join(_csv_cell(r.get(c)) for c in columns))
    return "\n".join(lines) + "\n"


def _csv_cell(value) -> str:
    """A data cell: a leading =, +, -, @ or tab is neutralised (dropped) so no spreadsheet
    reads the value as a formula; the rest of the content is preserved."""
    s = "" if value is None else str(value)
    s = s.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").replace("\t", " ")
    if s and s[0] in "=+-@":
        s = s[1:]
    if any(c in s for c in (',', '"', "\n")):
        s = '"' + s.replace('"', '""') + '"'
    return s


def _html(title: str, sid: str, columns: list[str], rows: list[dict], generated: str, profile: str) -> str:
    head = "".join(f"<th>{_esc(str(c))}</th>" for c in columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{_esc(str(r.get(c) or ''))}</td>" for c in columns) + "</tr>"
        for r in rows)
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{_esc(title)} — {_esc(sid)}</title>"
        "<style>body{font-family:Segoe UI,Arial,sans-serif;margin:2rem;color:#1c2733}"
        "h1{font-size:1.3rem}table{border-collapse:collapse;width:100%}"
        "th,td{border:1px solid #c9d2dc;padding:.45rem .6rem;text-align:left;font-size:.9rem}"
        "th{background:#eef2f6}meta{color:#667085;font-size:.8rem}</style></head><body>"
        f"<h1>{_esc(title)}</h1>"
        f"<p class='meta'>Application <b>{_esc(sid)}</b> · Institution profile "
        f"<b>{_esc(profile)}</b> · Generated {generated} (report derived from the stored "
        "application record)</p>"
        f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></body></html>"
    )


def svc_committee_deviations(case):
    from src.los.committee import committee_deviations
    return committee_deviations(case)


def _app_rows(svc, app: dict, report: str) -> list[dict]:
    sid = app["application_id"]
    if report == "case_summary":
        s = svc.summary(app)
        positions = s.get("positions") or {}
        rows = [
            {"Item": "Application", "Value": sid},
            {"Item": "Borrower", "Value": s.get("name")},
            {"Item": "Status", "Value": s.get("status")},
            {"Item": "Stage", "Value": s.get("stage")},
            {"Item": "Profile", "Value": s.get("profile")},
            {"Item": "Product", "Value": s.get("product")},
            {"Item": "Total amount (Cr)", "Value": s.get("total_amount_cr")},
            {"Item": "Facilities", "Value": "; ".join(
                f"{f.get('facility_type') or 'facility'} ₹{f.get('amount_cr')} Cr"
                for f in s.get("facilities") or [])},
            {"Item": "IP authority (route)", "Value": (positions.get("ip_authority") or {}).get("recommended")},
            {"Item": "Final authority (route)", "Value": (positions.get("final_authority") or {}).get("recommended")},
            {"Item": "IP committee", "Value": (positions.get("ip_committee") or {}).get("decision")},
            {"Item": "Sanction committee", "Value": (positions.get("sanction_committee") or {}).get("decision")},
            {"Item": "Sanctioned amount (Cr)", "Value": (positions.get("sanction") or {}).get("amount_cr")},
            {"Item": "Latest risk grade", "Value": (positions.get("latest_risk_assessment") or {}).get("risk_grade")},
            {"Item": "Open risks", "Value": "; ".join(
                f"{r.get('kind')} {r.get('id')} ({r.get('status')})" for r in s.get("open_risks") or []) or "none"},
            {"Item": "Pending", "Value": "; ".join(
                f"{p.get('where')}: {p.get('waiting')}" for p in s.get("pending") or []) or "none"},
        ]
        for d in (s.get("recent_decisions") or [])[-5:]:
            rows.append({"Item": f"Decision {d.get('at', '')}",
                         "Value": f"{d.get('decision') or d.get('action')} — {d.get('by') or d.get('by_name')}"})
        return rows
    if report == "sanction_record":
        rows = [{"Item": "Application", "Value": sid},
                {"Item": "Borrower", "Value": app.get("borrower_name")}]
        for stage_id, sanc in (app.get("sanctions") or {}).items():
            rows.append({"Item": f"Sanction ({stage_id}) — amount (Cr)", "Value": (sanc or {}).get("sanctioned_cr")})
            rows.append({"Item": f"Sanction ({stage_id}) — authority", "Value": (sanc or {}).get("authority")})
            rows.append({"Item": f"Sanction ({stage_id}) — at", "Value": (sanc or {}).get("at")})
            rows.append({"Item": f"Sanction ({stage_id}) — minutes", "Value": (sanc or {}).get("minutes")})
        for f in app.get("facilities") or [app.get("facility") or {}]:
            rows.append({"Item": f"Facility {f.get('facility_id')} — type", "Value": f.get("facility_type")})
            rows.append({"Item": f"Facility {f.get('facility_id')} — amount (Cr)", "Value": f.get("amount_cr")})
            rows.append({"Item": f"Facility {f.get('facility_id')} — tenor (months)", "Value": f.get("tenor_months")})
            rows.append({"Item": f"Facility {f.get('facility_id')} — rate (%)", "Value": f.get("interest_rate")})
            rows.append({"Item": f"Facility {f.get('facility_id')} — sanctioned amount (Cr)",
                         "Value": f.get("sanctioned_amount_cr") or f.get("amount_cr")})
        conds = [c for c in (app.get("conditions") or []) if c.get("type") in ("PC", "CP", "PDS", "PDM")]
        rows.append({"Item": "Conditions", "Value": str(len(conds))})
        covs = app.get("covenants") or []
        rows.append({"Item": "Covenants", "Value": str(len(covs))})
        return rows
    if report == "audit_trail":
        events = list(reversed(svc.store.events(sid, limit=100000)))   # oldest first
        rows = []
        for e in events:
            rows.append({"At": e.get("at"), "Action": e.get("action"),
                         "Step": e.get("from_step") or e.get("to_step"),
                         "By": e.get("actor_id"), "Role": e.get("actor_role"),
                         "Comment": e.get("comment"),
                         "action": e.get("action"), "at": e.get("at")})
        return rows
    if report == "document_checklist":
        rows = []
        for d in app.get("documents") or []:
            versions = d.get("versions") or []
            last = versions[-1] if versions else {}
            rows.append({"Document": d.get("name"), "Kind": d.get("kind"), "Status": d.get("status"),
                         "Versions": len(versions), "Last version": last.get("file_name"),
                         "Reviewed by": d.get("reviewer")})
        return rows
    if report == "conditions":
        rows = [{"ID": c.get("condition_id"), "Type": c.get("type"), "Text": c.get("condition_text"),
                 "Status": c.get("status"), "Note": c.get("note")}
                for c in app.get("conditions") or []]
        for c in app.get("covenants") or []:
            latest = (c.get("monitoring") or [{}])[-1]
            rows.append({"ID": c.get("covenant_id"), "Type": "covenant", "Text": c.get("description"),
                         "Status": latest.get("status") or c.get("status"),
                         "Note": c.get("description") and (c.get("test_frequency") or "")})
        return rows
    if report == "disbursement":
        rows = []
        dis = app.get("disbursement") or {}
        for t in dis.get("tranches") or []:
            rows.append({"Tranche": t.get("tranche_id"), "Amount (Cr)": t.get("amount_cr"),
                         "Value date": t.get("value_date"), "Purpose": t.get("purpose"),
                         "Facility": t.get("facility_id")})
        paid = sum(float(t.get("amount_cr") or 0) for t in (dis.get("tranches") or [])
                   if t.get("status") in ("approved", "disbursed"))
        if paid:
            rows.append({"Tranche": "total paid", "Amount (Cr)": round(paid, 2)})
        sanctioned = (app.get("sanctions") or {}).get("AP") or {}
        rows.append({"Tranche": "sanctioned", "Amount (Cr)": sanctioned.get("sanctioned_cr")})
        return rows
    if report == "pipeline":
        wf = svc._wf(app)
        step_names = {st.id: st for st in wf.steps}
        role_names = wf.roles
        events = list(reversed(svc.store.events(sid, limit=100000)))   # oldest first
        rows = []
        current = None            # (step_id, entered_at)
        for e in events:
            frm, to = e.get("from_step"), e.get("to_step")
            at = e.get("at") or ""
            if e.get("action") == "create" and to:      # the case entered at creation
                current = (to, at or app.get("created_at"))
                continue
            if current and frm and frm == current[0] and to and to != frm and at:
                entered = current[1]
                days = ""
                try:
                    from datetime import datetime as _dt
                    days = round((_dt.fromisoformat(at[:19]) - _dt.fromisoformat(entered[:19])).total_seconds() / 86400, 1)
                except Exception:
                    days = ""
                st = step_names.get(frm)
                rows.append({"Stage": st.stage_id if st else "", "Step": st.name if st else frm,
                             "Role": role_names.get(st.role, st.role) if st else "",
                             "Entered": entered, "Decided at": at,
                             "Action": e.get("action"), "By": e.get("actor_name") or e.get("actor_id"),
                             "Days in step": days})
                current = (to, at)
        if current and (app.get("status") not in ("APPROVED", "REJECTED", "WITHDRAWN", "DROPPED")):
            st = step_names.get(current[0])
            rows.append({"Stage": st.stage_id if st else "", "Step": st.name if st else current[0],
                         "Role": role_names.get(st.role, st.role) if st else "",
                         "Entered": current[1], "Decided at": "— (current step)",
                         "Action": "in progress", "By": "", "Days in step": ""})
        return rows
    if report == "deviations":
        rows = []
        for d in app.get("policy_deviation_items") or []:
            rows.append({"ID": d.get("deviation_id"), "Source": "policy rule",
                         "Type": d.get("type"), "Description": d.get("summary"),
                         "Expected": d.get("expected"), "Actual": d.get("actual"),
                         "Severity": d.get("severity"), "Required authority": d.get("required_authority"),
                         "Status": d.get("status"), "Raised by": d.get("raised_by"),
                         "Raised at": (d.get("raised_at") or "")[:10]})
        for d in app.get("manual_deviations") or []:
            rows.append({"ID": f"MAN-{(d.get('raised_at_step') or '')[:4]}", "Source": "manual",
                         "Type": d.get("type"), "Description": d.get("description"),
                         "Expected": "", "Actual": "", "Severity": "",
                         "Required authority": "Committee with recorded minutes",
                         "Status": "removed" if d.get("removed") else "open",
                         "Raised by": d.get("raised_by"),
                         "Raised at": (d.get("raised_at") or "")[:10]})
        case, _ = svc._app_case(app)
        for dev, value, basis in (svc_committee_deviations(case) if case else []):
            rows.append({"ID": "", "Source": "committee (credit case)", "Type": "",
                         "Description": dev, "Expected": "", "Actual": value,
                         "Severity": "", "Required authority": "", "Status": "accepted",
                         "Raised by": "", "Raised at": ""})
        if not rows:
            rows.append({"ID": "—", "Source": "", "Type": "", "Description": "No deviations on this case",
                         "Expected": "", "Actual": "", "Severity": "", "Required authority": "",
                         "Status": "", "Raised by": "", "Raised at": ""})
        return rows
    raise KeyError(report)


def build_report(svc, application_id: str, report: str, *, fmt: str = "csv") -> dict:
    """Build a report for the application: rows, the CSV and the branded HTML."""
    if report not in CATALOG:
        raise KeyError(report)
    app = svc._require(application_id)
    rows = _app_rows(svc, app, report)
    cols = CATALOG[report]["columns"]
    generated = svc.now().isoformat(timespec="seconds")
    profile = app.get("profile") or svc.default_profile
    title = f"{CATALOG[report]['name']} — {application_id}"
    built_name = CATALOG[report]["name"]
    return {
        "report": report,
        "name": CATALOG[report]["name"],
        "application_id": application_id,
        "profile": profile,
        "generated_at": generated,
        "fmt": fmt,
        "columns": cols,
        "rows": rows,
        "csv": _csv(cols, rows, ["Report", built_name, "Application", application_id,
                                  "Profile", profile, "Generated at", generated]),
        "html": _html(title, application_id, cols, rows, generated, profile),
    }
