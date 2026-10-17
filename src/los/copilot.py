"""
LOS copilot (Phase 6): an assistant on every application.

  next actions   a rule-based planner reads the application's state (step, gates,
                 SLA, prefill, IP Note, assessment, reviews, pack, conditions,
                 tranche) and proposes what to do next. Actions marked with a tool
                 can be run by the copilot as the signed-in user, with the user's own
                 permissions; every run is audited as copilot-initiated.
  drafts         return notes and borrower document requests, assembled from the
                 record (deterministic, editable before use).
  ask            questions about the application, answered by the configured LLM
                 from the application's own record only; figures are checked
                 against the record and an answer that quotes anything else is
                 rejected. Without an LLM, the matching record lines are returned.

The copilot never submits, approves, returns, rejects or sanctions — workflow
decisions stay with the person who holds the step.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Optional

COPILOT_VERSION = "los_copilot/v1"
TOOLS = {
    "run_prefill": "Read the documents and propose the sourcing values",
    "accept_high_confidence": "Accept the high-confidence prefilled values",
    "run_due_diligence": "Run the pending API due-diligence checks",
    "generate_ip_note": "Generate the IP Note",
    "start_assessment": "Run the credit assessment",
    "committee_brief": "Write the AI committee brief",
    "issue_sanction_letter": "Issue the sanction letter",
}
CORE_DOCUMENTS = [
    ("request", r"request", "Management request note for the credit facility"),
    ("kyc", r"pan", "PAN card / PAN verification copy"),
    ("kyc", r"incorporation", "Certificate of incorporation"),
    ("kyc", r"board_resolution", "Board resolution for the borrowing"),
    ("kyc", r"gst_registration", "GST registration certificate"),
    ("financials", r"audited|annual_report", "Audited financial statements for the last three years"),
    ("ratings", r"rating", "Latest credit rating rationale"),
    ("collateral", r"valuation", "Valuation report for the proposed security"),
]
_PRIORITY = {"high": 0, "medium": 1, "low": 2}


def _act(id_, title, why, priority="medium", tool=None, draft=None):
    return {"id": id_, "title": title, "why": why, "priority": priority, "tool": tool, "draft": draft}


# ─── Planner ────────────────────────────────────────────────────────────────

def next_actions(s: dict) -> list[dict]:
    """Ordered proposals for the person holding the step (``s`` is built by the service)."""
    out: list[dict] = []
    step = s.get("step_id")
    if not step:
        return [_act("done", "Nothing to do — the application is complete",
                     "The workflow has finished for this application.", "low")]
    if s.get("exception_requests"):                  # the Compliance VP: a decision waits for them
        return [_act("exception_decision", "Decide the exception request(s)",
                     "Requested on: " + ", ".join(s["exception_requests"]) + ". Open Checks to approve or decline.",
                     "high")]
    if not s.get("is_holder"):
        return [_act("not_yours", f"This step is with {s.get('holder') or 'another user'}",
                     f"{s.get('step_name')} belongs to the {s.get('role_name')} role.", "low")]
    sla = s.get("sla") or {}
    if sla.get("breached"):
        out.append(_act("sla", f"SLA breached at {s.get('step_name')}",
                        f"Overdue by {abs(sla.get('days_remaining') or 0):.1f} day(s) against an SLA of "
                        f"{sla.get('sla_days')} day(s) — complete it today or escalate with the reason.", "high"))
    elif sla.get("due_soon"):
        out.append(_act("sla", "SLA due within a day", f"{s.get('step_name')} is due {sla.get('due_at', '')[:10]}.", "medium"))
    if s.get("status") == "RETURNED" and s.get("returned_comment"):
        out.append(_act("returned", "Address the return comment",
                        f"Returned with: “{s['returned_comment']}”", "high"))
    d = s.get("due_diligence") or {}
    if d.get("runnable"):                            # what running the checks can fix: pending ones
        out.append(_act("dd", f"Complete {len(d['runnable'])} pending mandatory check(s)",
                        "Pending: " + ", ".join(d["runnable"][:3]) + (" (+more)" if len(d["runnable"]) > 3 else "")
                        + ". The copilot runs the API checks; record the manual ones in Checks.", "high",
                        tool="run_due_diligence"))
    if d.get("need_exception"):                      # what only the Compliance VP can release
        out.append(_act("dd_exception", "Ask the Compliance VP for an exception",
                        ", ".join(d["need_exception"][:3]) + " came back matched / failed / unavailable. Re-running "
                        "will not change that — open Checks and use “Request exception”, with your reason."
                        + (f" Who can approve: {s['approvers']}." if s.get("approvers") else ""), "high"))
    if d.get("awaiting_exception"):
        out.append(_act("dd_waiting", "Waiting for the Compliance VP",
                        "Exception requested on: " + ", ".join(d["awaiting_exception"][:3])
                        + ". Nothing to do until the Compliance VP decides.", "medium"))
    if not d.get("blocking") and d.get("pending") and d.get("at_dd_step"):
        out.append(_act("dd", f"Run the {d['pending']} pending due-diligence check(s)",
                        "Optional checks are still pending — run them before the next review.",
                        "medium", tool="run_due_diligence"))

    if step == "ps_maker":
        p = s.get("prefill")
        if not s.get("documents"):
            out.append(_act("upload", "Upload the borrower's documents",
                            "No documents are on file — the prefill and the credit assessment read them.", "high",
                            draft="document_request"))
        elif not p:
            out.append(_act("prefill", "Run the document prefill",
                            f"{s['documents']} document(s) on file; the copilot reads them and proposes the sourcing "
                            "details with source page and confidence.", "high", tool="run_prefill"))
        else:
            if p.get("unaccepted_high"):
                out.append(_act("accept", f"Accept {p['unaccepted_high']} high-confidence value(s)",
                                "They match the borrower master or several documents.", "high",
                                tool="accept_high_confidence"))
            if p.get("conflicts"):
                out.append(_act("conflicts", f"Resolve {len(p['conflicts'])} conflicting value(s)",
                                "Documents disagree on: " + ", ".join(p["conflicts"]), "high"))
            if p.get("not_found"):
                out.append(_act("missing", f"Request {len(p['not_found'])} missing item(s) from the borrower",
                                "Not found in the documents: " + ", ".join(p["not_found"]), "medium",
                                draft="document_request"))
    elif step == "ip_note":
        if not s.get("ip_note"):
            out.append(_act("ip_note", "Generate the IP Note",
                            "Required before the IP Note can be submitted for review.", "high", tool="generate_ip_note"))
        elif s["ip_note"].get("breaches"):
            out.append(_act("exceptions", "Explain the pre-screen exceptions in your submission comment",
                            "Policy exceptions: " + ", ".join(s["ip_note"]["breaches"]), "medium"))
    elif step in ("ip_risk_maker", "ap_risk_maker"):
        job = s.get("job_state")
        if job == "running":
            out.append(_act("wait", "Credit assessment is running", "The workspace fills in when it completes.", "low"))
        elif not s.get("credit_assessment"):
            out.append(_act("assess", "Run the credit assessment",
                            "Required before the Risk Maker step can be submitted.", "high", tool="start_assessment"))
        else:
            r = s.get("review") or {}
            if r.get("stale"):
                out.append(_act("stale", f"Re-check {r['stale']} stale review(s)",
                                "The engine value changed after you reviewed these fields.", "high"))
            if r.get("pending"):
                out.append(_act("review", f"Review {r['pending']} pending field(s)",
                                "Confirm or override the engine values; start with the Rating and Financials tabs.",
                                "medium"))
    elif step in s.get("committee_steps", ()):
        pack = s.get("pack") or {}
        if pack.get("can_brief") and not pack.get("brief_done"):
            out.append(_act("brief", "Generate the AI committee brief",
                            "A number-checked summary of the executive summary and recommendation.", "medium",
                            tool="committee_brief"))
        if pack.get("overrides"):
            out.append(_act("overrides", f"Review {pack['overrides']} analyst override(s)",
                            "The Risk Maker changed engine values — check the reasons in the pack.", "high"))
        if pack.get("high_risks"):
            out.append(_act("risks", f"{len(pack['high_risks'])} unresolved high-severity risk(s)",
                            "; ".join(pack["high_risks"][:3]), "high", draft="return_note"))
        if pack.get("deviations"):
            out.append(_act("deviations", f"{pack['deviations']} deviation(s) need your explicit acceptance",
                            "Record the acceptance (or the return) in your comment.", "medium"))
    elif step == "pos_maker":
        if not s.get("sanction_letter_issued"):
            out.append(_act("letter", "Issue the sanction letter",
                            "Built from the sanction, the conditions tracker, covenants and approved deviations.",
                            "medium", tool="issue_sanction_letter"))
        c = s.get("conditions") or {}
        if c.get("cp_open"):
            out.append(_act("cps", f"Clear {c['cp_open']} open condition(s) precedent",
                            "Satisfy with evidence, or defer / waive with a reason (the checker approves).", "high"))
    elif step == "pos_checker":
        c = s.get("conditions") or {}
        if c.get("pending_approval"):
            out.append(_act("approve_waivers", f"{c['pending_approval']} deferral(s) / waiver(s) await your approval",
                            "Approving the step approves them; return it if a reason is not acceptable.", "high",
                            draft="return_note"))
    elif step == "dis_maker":
        d = s.get("disbursement") or {}
        if not d.get("pending_tranche"):
            out.append(_act("tranche", "Record the disbursement tranche",
                            f"Undisbursed limit: ₹{(d.get('available_cr') or 0):,.2f} Cr.", "high"))
        if d.get("missing"):
            out.append(_act("checklist", f"Complete {len(d['missing'])} checklist item(s)",
                            "; ".join(d["missing"][:3]), "high"))
    elif step in ("dis_checker", "dis_vp_review", "dis_approver"):
        d = s.get("disbursement") or {}
        t = d.get("pending_tranche") or {}
        if t:
            out.append(_act("verify", f"Verify tranche {t.get('no')}: ₹{t.get('amount_cr'):,.2f} Cr value {t.get('value_date')}",
                            "Check the request, value date and account before approving.", "medium"))

    if s.get("step_kind") == "allocation" and s.get("suggested_allocatee"):
        out.append(_act("allocate", f"Allocate to {s['suggested_allocatee']}",
                        "Lowest current workload among eligible users.", "medium"))
    if s.get("step_kind") in ("checker", "committee", "vp_review") and not any(a.get("draft") == "return_note" for a in out):
        out.append(_act("return_draft", "Draft a return note if you are not satisfied",
                        "The copilot lists the open points from the record.", "low", draft="return_note"))
    gating = [a for a in out if a["priority"] == "high" and a["id"] not in ("sla", "returned")]
    if not gating and s.get("can_submit"):
        verb = {"maker": "Submit", "checker": "Approve", "vp_review": "Submit", "committee": "Decide", "allocation": "Allocate"}.get(
            s.get("step_kind"), "Complete")
        out.append(_act("ready", f"Ready — {verb.lower()} this step",
                        "Nothing in the record blocks the step. The decision is yours; the copilot does not submit, "
                        "approve or sanction.", "low"))
    return sorted(out, key=lambda a: _PRIORITY[a["priority"]])


# ─── Drafts ─────────────────────────────────────────────────────────────────

def draft_return_note(s: dict) -> str:
    points = []
    p = s.get("prefill") or {}
    if p.get("conflicts"):
        points.append("Resolve the conflicting values across documents: " + ", ".join(p["conflicts"]) + ".")
    if p.get("not_found"):
        points.append("Obtain the details not found in the documents: " + ", ".join(p["not_found"]) + ".")
    r = s.get("review") or {}
    if r.get("pending") or r.get("stale"):
        points.append(f"Complete the field review ({r.get('pending', 0)} pending, {r.get('stale', 0)} stale).")
    pack = s.get("pack") or {}
    for risk in pack.get("high_risks") or []:
        points.append(f"Address the unresolved risk: {risk}.")
    if pack.get("open_items"):
        points.append(f"Close or explain the {pack['open_items']} open due-diligence item(s) and challenge(s).")
    if (s.get("ip_note") or {}).get("breaches"):
        points.append("Justify the pre-screen policy exceptions: " + ", ".join(s["ip_note"]["breaches"]) + ".")
    c = s.get("conditions") or {}
    if c.get("pending_approval"):
        points.append("Strengthen the reasons for the deferred / waived conditions, or satisfy them with evidence.")
    d = s.get("disbursement") or {}
    if d.get("missing"):
        points.append("Complete the disbursement checklist: " + "; ".join(d["missing"]) + ".")
    if not points:
        points.append("[State the specific points to be addressed — the record shows no open items.]")
    lines = [f"Returned for the following before resubmission ({s.get('step_name')}):"]
    lines += [f"{i}. {pt}" for i, pt in enumerate(points, 1)]
    return "\n".join(lines)


def missing_documents(documents: list[str]) -> list[str]:
    have = [d.lower() for d in documents]
    return [label for cat, pattern, label in CORE_DOCUMENTS
            if not any(d.startswith(cat + "/") and re.search(pattern, d) for d in have)]


def draft_document_request(borrower: str, rm_name: str, documents: list[str], not_found: list[str]) -> str:
    docs = missing_documents(documents)
    lines = [f"Subject: {borrower} — documents required for the credit proposal", "",
             "Dear Sir / Madam,", "",
             "Thank you for your proposal. To complete our in-principle assessment, please share the following:"]
    n = 0
    for d in docs:
        n += 1
        lines.append(f"{n}. {d}")
    for f in not_found:
        n += 1
        lines.append(f"{n}. Document evidencing the {f}")
    if not n:
        lines.append("1. [No missing documents identified — add any specific requests]")
    lines += ["", "Self-attested copies by email are sufficient at this stage; originals will be verified before "
                  "disbursement.", "", "Regards,", rm_name or "Relationship Manager"]
    return "\n".join(lines)


# ─── Ask ────────────────────────────────────────────────────────────────────

ASK_SYSTEM_PROMPT = """You are the credit copilot in a bank's loan origination system. Answer the user's question about
ONE application using ONLY the application record given as JSON. Rules: if the record does not contain the answer,
say it is not available in the record; do not add outside facts; do NOT calculate, round or estimate any number —
quote figures exactly as they appear in the record; values labelled synthetic or demo must be described as demo data;
be concise (at most 120 words). Return ONLY a JSON object: {"answer": "<text>", "fields_used": ["<record key>", ...]}"""


def flatten(obj, prefix="") -> list[tuple[str, str]]:
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out += flatten(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(obj, list):
        if all(not isinstance(x, (dict, list)) for x in obj):
            if obj:
                out.append((prefix, ", ".join(str(x) for x in obj)))
        else:
            for i, v in enumerate(obj[:20]):
                out += flatten(v, f"{prefix}[{i}]")
    elif obj not in (None, ""):
        out.append((prefix, str(obj)))
    return out


def lookup_answer(question: str, record: dict, limit: int = 8) -> dict:
    """No LLM: the record lines that share the most words with the question."""
    words = {w for w in re.findall(r"[a-z0-9]+", question.lower()) if len(w) > 2} - {
        "what", "the", "is", "are", "was", "how", "much", "for", "this", "application", "does", "and", "which", "why"}
    scored = []
    for key, value in flatten(record):
        hay = (key.replace("_", " ") + " " + value).lower()
        score = sum(1 for w in words if w in hay)
        if score:
            scored.append((score, key, value))
    scored.sort(key=lambda x: -x[0])
    lines = [f"{k.replace('_', ' ')}: {v}" for _, k, v in scored[:limit]]
    return {"answer": ("From the record:\n" + "\n".join(lines)) if lines else
            "Nothing in the application record matches the question.", "provenance": "record",
            "mode": "lookup", "fields_used": [k for _, k, _ in scored[:limit]]}


def ask(question: str, record: dict, llm=None) -> dict:
    question = (question or "").strip()
    if not question:
        raise ValueError("Ask a question")
    if llm is None or getattr(llm, "name", "") == "mock":
        out = lookup_answer(question, record)
        out["note"] = "AI is not configured (mock provider) — showing the matching record lines."
        return out
    from src.services.observation_narrator import _parse_json_object, unsupported_figures

    content = json.dumps(record, ensure_ascii=False, default=str)
    try:
        data = _parse_json_object(llm.generate(prompt=f"Application record (JSON):\n{content}\n\nQuestion: {question}",
                                               system_prompt=ASK_SYSTEM_PROMPT, temperature=0.1, max_tokens=500))
        text = str(data.get("answer") or "").strip()
        if not text:
            raise ValueError("the model returned no answer")
        bad = unsupported_figures(text, content)
        if bad:
            raise ValueError(f"quoted figures not in the record: {', '.join(bad[:4])}")
    except Exception as e:                                      # never pass an unchecked answer through
        out = lookup_answer(question, record)
        out["note"] = f"The AI answer was rejected ({e}) — showing the matching record lines instead."
        return out
    return {"answer": text, "provenance": "ai", "mode": "ai",
            "model": getattr(llm, "model", None) or getattr(llm, "name", "llm"),
            "fields_used": [str(f) for f in data.get("fields_used") or []][:10],
            "note": "AI answer from this application's record; figures checked against the record."}


def stamp(now: Optional[datetime] = None) -> str:
    return (now or datetime.now()).isoformat(timespec="seconds")
