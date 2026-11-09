"""AI governance pack for one proposal (roadmap L2; RBI FREE-AI themes).

    build   the facts of AI use on this proposal: which model wrote what, with which prompt version and where;
            the figures check on the CAM and on Copilot answers; what people decided, changed, verified and
            justified; where the data came from (demo data labelled); the fairness check of the rating inputs;
            the model card and the impact assessment (config/ai_governance.yaml)
    html    the same as a printable page, linked from the proposal next to the Audit Trail Report
"""

from __future__ import annotations

import html as _html
import json
import os
import re
from typing import Optional

from src.flow import checks as chk


def _e(v) -> str:
    return _html.escape(str(v if v is not None else "—"))


def _cfg() -> dict:
    from src.core.config_manager import config
    return config.get("ai_governance", default={}) or {}


def deployment() -> dict:
    """The model the deployment uses and where its calls are processed."""
    from src.core.config_manager import config
    name = config.get("llm_providers", "active_provider", default="mock")
    p = (config.get("llm_providers", "providers", name, default={}) or {}) if name != "mock" else {}
    model = os.getenv(p.get("model_env", "") or "") or p.get("model") or p.get("deployment") or name
    region = (os.getenv("GOOGLE_CLOUD_LOCATION") or p.get("location")) if p.get("type") == "vertex_ai_gemini" else None
    where = {"vertex_ai_gemini": f"Google Vertex AI, {region or 'region not set'}"
             + (" (global endpoint: not pinned to India)" if region == "global" else ""),
             "openai": "OpenAI-compatible endpoint " + str(os.getenv(p.get("base_url_env", "") or "") or p.get("base_url") or "api.openai.com"),
             "anthropic": "Anthropic API", "azure_openai": "Azure OpenAI", "ollama": "Local model (on the bank's server)",
             }.get(p.get("type"), "No AI model (templates only)")
    from src.engines.cam_sections import PROMPT_VERSION
    return {"provider": p.get("name") or name, "model": model, "processing": where, "prompt_version": PROMPT_VERSION,
            "thinking_level": p.get("thinking_level")}


def fairness() -> dict:
    """Do any protected attributes appear among the rating's and the decision's inputs?"""
    from src.core.config_manager import config
    words = [str(w).lower() for w in _cfg().get("protected_attributes") or []]
    scanned = {"rating scorecard (settings.yaml → scoring)": config.get("settings", "scoring", default={}),
               "policy limits (rules.yaml → policy_thresholds)": config.get("rules", "policy_thresholds", default={}),
               "hard rules (rules.yaml → hard_rules)": config.get("rules", "hard_rules", default={})}
    found = []
    for where, obj in scanned.items():
        text = json.dumps(obj, default=str).lower()
        found += [f"{w} in {where}" for w in words if re.search(rf"\b{re.escape(w)}\b", text)]
    return {"protected_attributes": words, "scanned": list(scanned), "found": found,
            "result": "No protected attribute is an input to the rating or the decision" if not found
            else "Protected attribute(s) found among the inputs — review: " + "; ".join(found)}


def build(case: dict, events: list[dict], generated_at: str) -> dict:
    cam = case.get("cam") or {}
    fc = cam.get("figure_check")
    chat = case.get("chat") or []
    answers = [m for m in chat if m.get("kind") == "answer" and m.get("from") == "agent"]
    ai_answers = [m for m in answers if m.get("provenance") == "ai"]
    rejected = [m for m in answers if "was rejected" in (m.get("text") or "")]
    checks = chk.view(case.get("checks"), case.get("check_notes")) or {}
    acq = case.get("acquisition") or {}
    demo_sources = sorted({s["label"] for s in (acq.get("sources") or {}).values() if s.get("demo")})
    dep = deployment()
    people = {
        "decisions": [{k: d.get(k) for k in ("at", "stage_label", "by", "action", "comment")}
                      for d in case.get("decisions") or []],
        "overrides": [{"field": c["label"], "by": c.get("by_name"), "reason": c.get("reason"), "status": c["status"],
                       "decided_by": c.get("decided_by")} for c in case.get("changes") or []],
        "check_notes": [{"check": i["label"], **i["note"]} for i in checks.get("items") or [] if i.get("note")],
        "justifications": [{"by": d.get("by"), "stage": d.get("stage_label"), "reasons": d.get("reasons"),
                            "text": d.get("text")} for d in case.get("deviations") or []],
        "challenge_answers": [{"challenge": a["title"], **{k: v for k, v in (case.get("responses") or {}).get(a["id"], {}).items()
                                                           if k in ("kind", "by", "note")}}
                              for a in case.get("against") or [] if (case.get("responses") or {}).get(a["id"])],
    }
    flagged_n = sum(len(f["figures"]) for f in (fc or {}).get("flagged") or [])
    ia_facts = {
        "What decision does the AI influence, and who makes it?":
            f"The AI drafts text and reads documents; {len(people['decisions'])} decision(s) on this proposal were made "
            f"by named officers ({', '.join(sorted({d['by'] for d in people['decisions']})) or 'none yet'}).",
        "What data does the AI see, and where is it processed?":
            f"The proposal's fact pack and documents; processed by {dep['provider']} ({dep['model']}) — {dep['processing']}."
            + (f" Demo data used for: {', '.join(demo_sources)}." if demo_sources else "")
            + (" Mandatory checks ran on demo data." if checks.get("demo") else ""),
        "How are AI errors caught?":
            (f"Figures check on the CAM: {flagged_n} figure(s) in {len((fc or {}).get('flagged') or [])} section(s) to "
             f"verify; {len((fc or {}).get('rewritten') or [])} section(s) rewritten once." if fc else
             "The CAM narrative was not AI-written on this proposal.")
            + f" Copilot: {len(ai_answers)} AI answer(s) passed the figures check; {len(rejected)} rejected and "
              f"replaced by record lines.",
        "Is any protected attribute used?": fairness()["result"],
    }
    ia = [{"question": q["question"], "answer": ia_facts.get(q["question"], "") if q.get("answer") == "from_record"
           else q.get("answer")} for q in _cfg().get("impact_assessment") or []]
    return {"case_id": case["case_id"], "borrower": case["borrower_name"], "generated_at": generated_at,
            "deployment": dep,
            "cam": {"mode": cam.get("mode"), "narrative_mode": cam.get("narrative_mode"), "model": cam.get("model"),
                    "generated_at": cam.get("generated_at"), "llm_calls": cam.get("llm_calls"),
                    "sections_written": cam.get("sections_written"), "sections_reused": cam.get("sections_reused"),
                    "figure_check": fc},
            "copilot": {"answers": len(answers), "ai": len(ai_answers), "rejected": len(rejected),
                        "record_lookup": len(answers) - len(ai_answers)},
            "people": people, "data": {"demo_sources": demo_sources, "checks_demo": bool(checks.get("demo")),
                                       "checks": [{k: i[k] for k in ("label", "status_label", "source")}
                                                  for i in checks.get("items") or []]},
            "fairness": fairness(), "model_card": _cfg().get("model_card") or {}, "impact_assessment": ia}


_CSS = ("body{font:14px/1.5 'Segoe UI',system-ui,sans-serif;color:#0d1726;max-width:1000px;margin:24px auto;padding:0 16px}"
        "h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:24px 0 8px;border-bottom:2px solid #0a1f3d;padding-bottom:4px}"
        "table{border-collapse:collapse;width:100%;font-size:13px}td,th{border:1px solid #e1e7ef;padding:6px 8px;text-align:left;"
        "vertical-align:top}th{background:#f2f5f9}.muted{color:#5f6f86}.ok{color:#157a43}.warn{color:#a85a06}"
        ".note{background:#f6f8fb;border-left:3px solid #0a1f3d;padding:8px 12px}ul{margin:4px 0 4px 18px;padding:0}")


def html(p: dict) -> str:
    dep, cam, cp, mc, fair = p["deployment"], p["cam"], p["copilot"], p["model_card"], p["fairness"]
    fc = cam.get("figure_check")
    li = lambda xs: "<ul>" + "".join(f"<li>{_e(x)}</li>" for x in xs or []) + "</ul>"   # noqa: E731
    rows = lambda items, cols: "".join(                                                   # noqa: E731
        "<tr>" + "".join(f"<td>{_e(i.get(c))}</td>" for c in cols) + "</tr>" for i in items) or \
        f"<tr><td colspan={len(cols)} class=muted>None</td></tr>"
    if fc and fc.get("flagged"):
        figs = "".join(f"<tr><td>{_e(f['title'])}</td><td class=warn>{_e(', '.join(f['figures']))}</td></tr>"
                       for f in fc["flagged"])
        figs = (f"<p class=warn>{sum(len(f['figures']) for f in fc['flagged'])} figure(s) quoted by the AI are not in "
                f"its source data — verify before relying on the CAM.</p><table><tr><th>Section</th><th>Figures to "
                f"verify</th></tr>{figs}</table>")
    elif fc:
        figs = f"<p class=ok>Every figure in the {fc.get('sections_checked', 0)} AI-written sections was found in its source data.</p>"
    else:
        figs = "<p class=muted>The CAM narrative was not written by AI on this proposal (template or the bank's own CAM).</p>"
    ppl = p["people"]
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Governance Pack — {_e(p['case_id'])}</title><style>{_CSS}</style></head><body>
<h1>AI Governance Pack · {_e(p['borrower'])}</h1>
<div class="muted">{_e(p['case_id'])} · generated {_e(p['generated_at'])} · aligned to the themes of RBI's FREE-AI framework</div>
<p class="note">AI drafted text, read documents and answered questions on this proposal. It made no credit decision:
the rating and recommendation are rule-based, and every decision below is a named officer's.</p>
<h2>1. AI used on this proposal</h2><table>
<tr><th>Model</th><td>{_e(dep['provider'])} · {_e(cam.get('model') or dep['model'])}</td></tr>
<tr><th>Where calls are processed</th><td>{_e(dep['processing'])}</td></tr>
<tr><th>CAM prompt version</th><td>{_e(dep['prompt_version'])}</td></tr>
<tr><th>CAM narrative</th><td>{_e({'llm': 'AI-written', 'template': 'Templates (no AI)', 'template_fallback': 'Templates (AI unavailable)'}.get(cam.get('narrative_mode'), cam.get('mode') or '—'))}
 · {_e(cam.get('sections_written'))} section(s) written, {_e(cam.get('sections_reused'))} reused · {_e(cam.get('llm_calls'))} AI call(s) · {_e(cam.get('generated_at'))}</td></tr>
<tr><th>Credit Copilot</th><td>{cp['answers']} answer(s): {cp['ai']} AI-written (figures checked), {cp['record_lookup']} from record lines, {cp['rejected']} AI answer(s) rejected by the figures check</td></tr>
</table>
<h2>2. Figures check on the CAM</h2>{figs}
<h2>3. Human oversight: what people decided, changed and verified</h2>
<table><tr><th>When</th><th>Stage</th><th>Who</th><th>Decision</th><th>Comment</th></tr>{rows(ppl['decisions'], ['at', 'stage_label', 'by', 'action', 'comment'])}</table>
<p><b>Overrides of AI- or agent-filled figures</b></p>
<table><tr><th>Field</th><th>By</th><th>Reason</th><th>Status</th><th>Reviewed by</th></tr>{rows(ppl['overrides'], ['field', 'by', 'reason', 'status', 'decided_by'])}</table>
<p><b>Mandatory checks verified or justified by an officer</b></p>
<table><tr><th>Check</th><th>Kind</th><th>By</th><th>Note</th></tr>{rows(ppl['check_notes'], ['check', 'kind', 'by', 'note'])}</table>
<p><b>Answers to the risk challenges, and justifications for proceeding against the engine</b></p>
<table><tr><th>Challenge</th><th>How</th><th>By</th><th>Note</th></tr>{rows(ppl['challenge_answers'], ['challenge', 'kind', 'by', 'note'])}
{rows(ppl['justifications'], ['stage', 'reasons', 'by', 'text']) if ppl['justifications'] else ''}</table>
<h2>4. Data</h2>
<p>{'Demo data stood in for: ' + _e(', '.join(p['data']['demo_sources'])) + '.' if p['data']['demo_sources'] else ''}
{'The mandatory checks ran on demo bureau / MCA / registry files (APIs not connected).' if p['data']['checks_demo'] else ''}</p>
<table><tr><th>Mandatory check</th><th>Result</th><th>Source</th></tr>{rows(p['data']['checks'], ['label', 'status_label', 'source'])}</table>
<h2>5. Fairness</h2><p class="{'ok' if not fair['found'] else 'warn'}">{_e(fair['result'])}.</p>
<p class="muted">Scanned: {_e('; '.join(fair['scanned']))} for: {_e(', '.join(fair['protected_attributes']))}.</p>
<h2>6. Model card</h2><table>
<tr><th>System</th><td>{_e(mc.get('system'))} · version {_e(mc.get('version'))}</td></tr>
<tr><th>Owner</th><td>{_e(mc.get('owner'))} · review {_e(mc.get('review_cadence'))}</td></tr>
<tr><th>Purpose</th><td>{_e(mc.get('purpose'))}</td></tr>
<tr><th>The AI does</th><td>{li(mc.get('ai_does'))}</td></tr>
<tr><th>The AI does not</th><td>{li(mc.get('ai_does_not'))}</td></tr>
<tr><th>Controls</th><td>{li(mc.get('controls'))}</td></tr>
<tr><th>Limitations</th><td>{li(mc.get('limitations'))}</td></tr></table>
<h2>7. Impact assessment</h2><table><tr><th>Question</th><th>Answer</th></tr>{rows(p['impact_assessment'], ['question', 'answer'])}</table>
</body></html>"""
