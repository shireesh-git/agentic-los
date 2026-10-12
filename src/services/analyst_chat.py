"""
Analyst Chat Service
=====================
LLM-powered Q&A for credit analysts. Builds context from:
  - Fact packs & CAM data
  - Document extraction results
  - ETB behavioral analytics
  - Validation findings
  - Financial ratios & benchmarks

Replies come from the active LLM provider (config/llm_providers.yaml) through
src.core.llm_provider, the same layer CAM generation uses; a rule-based answer
is the fallback when the provider fails.
"""

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from src.core.config_manager import config


@dataclass
class ChatMessage:
    role: str            # "user" | "assistant" | "system"
    content: str
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()

    def to_dict(self):
        return {"role": self.role, "content": self.content, "timestamp": self.timestamp}


@dataclass
class ChatSession:
    entity_id: str
    messages: list[ChatMessage] = field(default_factory=list)
    context: str = ""
    created_at: float = 0.0

    def __post_init__(self):
        if not self.created_at:
            self.created_at = time.time()


# In-memory session store
_sessions: dict[str, ChatSession] = {}

# Default config
OLLAMA_HOST = "http://localhost:11434"
MODEL = "llama3:8b"
MAX_CONTEXT_CHARS = 18000
MAX_HISTORY = 20


def _get_ollama_host() -> str:
    """Get Ollama host from environment or default."""
    import os
    active = config.get_active_llm_provider() or {}
    configured = active.get("base_url") if active.get("type") == "ollama" else None
    return os.environ.get("OLLAMA_HOST", configured or OLLAMA_HOST)


def _get_chat_model() -> str:
    """Use the active Ollama model when available so chat matches CAM generation."""
    active = config.get_active_llm_provider() or {}
    if active.get("type") == "ollama" and active.get("model"):
        return str(active["model"])

    fallback = config.get("llm_providers", "providers", "ollama", "model", default=None)
    return str(fallback or MODEL)


# ═══════════════════════════════════════════════════════════════════════════════
#  Context Assembly
# ═══════════════════════════════════════════════════════════════════════════════

def build_context(entity_id: str, case_data: dict | None = None,
                  extraction: dict | None = None,
                  etb_analysis: dict | None = None,
                  probe_context: str | None = None) -> str:
    """
    Assemble context from available data sources for the LLM.
    Includes CAM fact pack for comprehensive financial advisor capability.
    Truncated to MAX_CONTEXT_CHARS to fit model context window.
    """
    parts = [f"# Credit Analysis Context — {entity_id}\n"]

    if case_data:
        # Company info from case result
        parts.append(f"## Company: {case_data.get('company_name', 'N/A')}")
        if case_data.get("data_provider"):
            parts.append(f"- Data Provider: {case_data.get('data_provider')}")
        parts.append(f"- Sector: {case_data.get('sector', 'N/A')}")
        parts.append(f"- Risk Grade: {case_data.get('risk_grade', 'N/A')}")
        parts.append(f"- Composite Score: {case_data.get('composite_score', 'N/A')}/100")
        parts.append(f"- Recommendation: {case_data.get('recommendation', 'N/A')}")
        parts.append(f"- Financial Score: {case_data.get('financial_score', 'N/A')}")
        parts.append(f"- Conduct Score: {case_data.get('conduct_score', 'N/A')}")
        parts.append(f"- Governance Score: {case_data.get('governance_score', 'N/A')}")
        parts.append(f"- Market Score: {case_data.get('market_score', 'N/A')}")
        parts.append(f"- Facility: {case_data.get('facility_type', 'N/A')} — ₹{case_data.get('requested_amount_cr', 'N/A')} Cr")
        parts.append("")

        # CAM Fact Pack — comprehensive financial data
        fp = case_data.get("fact_pack", {})
        if fp:
            # Financial summary
            fin = fp.get("financial_summary", {})
            if fin.get("periods"):
                parts.append("## Financial Performance (₹ Crore)")
                for period, data in sorted(fin["periods"].items()):
                    parts.append(f"\n### {period}")
                    for key in ["revenue_cr", "ebitda_cr", "ebitda_margin_pct", "pat_cr",
                                "net_worth_cr", "total_debt_cr", "total_assets_cr",
                                "operating_cash_flow_cr"]:
                        val = data.get(key)
                        if val is not None:
                            label = key.replace("_cr", "").replace("_pct", " %").replace("_", " ").title()
                            parts.append(f"- {label}: {val}")
                if fin.get("growth"):
                    parts.append("\n### Growth Rates")
                    for k, v in fin["growth"].items():
                        parts.append(f"- {k}: {v}%")

            # Ratios
            ratios = fp.get("ratios", {})
            if ratios:
                parts.append("\n## Key Financial Ratios")
                for period, rdata in sorted(ratios.items()):
                    parts.append(f"\n### {period}")
                    for rname, rinfo in rdata.items():
                        val = rinfo.get("value")
                        status = rinfo.get("status", "")
                        if val is not None:
                            parts.append(f"- {rname}: {val:.2f} ({status})")

            # Credit strengths
            strengths = fp.get("credit_strengths", [])
            if strengths:
                parts.append("\n## Credit Strengths")
                for s in strengths:
                    if isinstance(s, dict):
                        parts.append(f"- {s.get('category', '')}: {s.get('detail', '')}")
                    else:
                        parts.append(f"- {s}")

            # Key risks
            risks = fp.get("key_risks", [])
            if risks:
                parts.append("\n## Key Risks & Concerns")
                for r in risks:
                    if isinstance(r, dict):
                        parts.append(f"- [{r.get('severity', 'medium').upper()}] {r.get('category', '')}: {r.get('detail', '')}")
                    else:
                        parts.append(f"- {r}")

            # Industry and market signals
            industry = fp.get("industry_analysis", {})
            if industry:
                parts.append("\n## Industry & Market Context")
                if industry.get("industry_overview"):
                    parts.append(f"- Industry overview: {industry['industry_overview']}")
                growth_drivers = industry.get("growth_drivers", [])
                if growth_drivers:
                    parts.append(f"- Growth drivers: {'; '.join(growth_drivers[:4])}")
                headwinds = industry.get("headwinds", [])
                if headwinds:
                    parts.append(f"- Headwinds: {'; '.join(headwinds[:4])}")
                competitors = industry.get("competitors", [])
                if competitors:
                    peer_summaries = []
                    for peer in competitors[:4]:
                        if isinstance(peer, dict):
                            peer_summaries.append(
                                f"{peer.get('name', 'Peer')} revenue {peer.get('revenue_cr', 'n/a')} Cr, "
                                f"share {peer.get('market_share_pct', 'n/a')}%, rating {peer.get('rating', 'n/a')}"
                            )
                    if peer_summaries:
                        parts.append(f"- Peers: {' | '.join(peer_summaries)}")

            market_signals = fp.get("market_signals", [])
            if market_signals:
                parts.append("\n## Market Signals")
                for signal in market_signals[:6]:
                    if isinstance(signal, dict):
                        parts.append(
                            f"- [{str(signal.get('severity', 'low')).upper()} / {str(signal.get('sentiment', 'neutral')).upper()}] "
                            f"{signal.get('headline', 'Signal')} "
                            f"(Source: {signal.get('source', 'n/a')}; Detail: {signal.get('details', 'n/a')})"
                        )

            # Existing banking exposure and pricing
            existing_exposure = fp.get("existing_exposure", [])
            if existing_exposure:
                parts.append("\n## Existing Banking Exposure")
                total_sanctioned = 0.0
                total_outstanding = 0.0
                for facility in existing_exposure[:8]:
                    if not isinstance(facility, dict):
                        continue
                    sanctioned = float(facility.get("sanctioned_cr") or 0)
                    outstanding = float(facility.get("outstanding_cr") or 0)
                    total_sanctioned += sanctioned
                    total_outstanding += outstanding
                    parts.append(
                        f"- {facility.get('facility_type', 'Facility')}: sanctioned {sanctioned} Cr, "
                        f"outstanding {outstanding} Cr, utilization {facility.get('utilization_pct', 'n/a')}%, "
                        f"classification {facility.get('classification', 'n/a')}"
                    )
                parts.append(f"- Total sanctioned exposure: {round(total_sanctioned, 1)} Cr")
                parts.append(f"- Total outstanding exposure: {round(total_outstanding, 1)} Cr")

            facility_pricing = fp.get("facility_pricing", {})
            if facility_pricing:
                parts.append("\n## Facility Pricing & End Use")
                for key in ["base_rate", "interest_rate", "processing_fee", "commitment_charge", "penal_interest"]:
                    if facility_pricing.get(key):
                        parts.append(f"- {key.replace('_', ' ').title()}: {facility_pricing[key]}")
                end_use = facility_pricing.get("end_use_details", [])
                for item in end_use[:5]:
                    if isinstance(item, dict):
                        parts.append(
                            f"- End use: {item.get('component', 'component')} "
                            f"{item.get('amount_cr', 'n/a')} Cr ({item.get('pct', 'n/a')}%)"
                        )

            # Collateral
            coll = fp.get("collateral_analysis", {})
            if coll.get("collaterals"):
                parts.append(f"\n## Collateral Coverage")
                parts.append(f"- Market Coverage: {coll.get('coverage_market', 'N/A')}x")
                parts.append(f"- FSV Coverage: {coll.get('coverage_fsv', 'N/A')}x")

            # Corporate hierarchy
            hier = fp.get("corporate_hierarchy", {})
            if hier.get("entities"):
                parts.append(f"\n## Group Structure: {hier.get('group_name', 'N/A')}")
                for e in hier.get("entities", [])[:5]:
                    if isinstance(e, dict):
                        parts.append(f"- {e.get('company_name', 'N/A')} ({e.get('relationship', '')})")

            # Cash flow & repayment
            cf = fp.get("cash_flow_repayment", {})
            if cf.get("repayment_assessment"):
                ra = cf["repayment_assessment"]
                parts.append(f"\n## Repayment Assessment")
                parts.append(f"- Status: {ra.get('status', 'N/A')}")
                parts.append(f"- DSCR: {ra.get('dscr', 'N/A')}")

            # Data sources — provenance for citation
            data_sources = fp.get("data_sources", [])
            if data_sources:
                parts.append("\n## Data Sources (cite these when answering)")
                for ds in data_sources:
                    status = ds.get('fetch_status', 'unknown')
                    sections = ', '.join(ds.get('cam_sections_using', []))
                    parts.append(f"- {ds['source_name']} [{ds['source_system']}]: "
                                 f"Entity={ds['entity_key']} | Status={status} | Used in: {sections}")

        # Rationale and conditions
        rationale = case_data.get("rationale", "")
        if rationale:
            parts.append(f"\n## Credit Rationale")
            parts.append(rationale)

        conditions = case_data.get("conditions", [])
        if conditions:
            parts.append(f"\n## Conditions")
            for c in conditions:
                parts.append(f"- {c}")

        # Validation exceptions
        exceptions = case_data.get("exceptions", [])
        if exceptions:
            parts.append("\n## Validation Exceptions")
            for v in exceptions[:10]:
                if isinstance(v, dict):
                    parts.append(f"- [{v.get('severity', 'info').upper()}] {v.get('message', v.get('description', ''))}")
                else:
                    parts.append(f"- {v}")

    if probe_context:
        parts.append("\n" + probe_context.strip())

    if extraction:
        parts.append("\n## Document Extraction Summary")
        if extraction.get("financials"):
            parts.append("- Audited financials extracted from PDF")
            for key, vals in extraction.get("financials", {}).get("audited", {}).items():
                if vals:
                    parts.append(f"  - {key}: {vals}")
        if extraction.get("provisional"):
            parts.append("- Provisional financials extracted from Excel")
            for k, v in extraction.get("provisional", {}).items():
                parts.append(f"  - {k}: {v}")
        if extraction.get("gst"):
            parts.append(f"- GST: {extraction['gst']}")
        if extraction.get("rating"):
            parts.append(f"- Rating: {extraction['rating']}")

    if etb_analysis:
        parts.append("\n## ETB Behavioral Analytics")
        parts.append(f"- Composite Score: {etb_analysis.get('composite_score', 'N/A')}/100")
        parts.append(f"- Risk Grade: {etb_analysis.get('risk_grade', 'N/A')}")
        conduct = etb_analysis.get("conduct", {})
        parts.append(f"- Conduct Score: {conduct.get('score', 'N/A')}")
        parts.append(f"- Cheque Returns: {conduct.get('total_cheque_returns', 0)}")
        repayment = etb_analysis.get("repayment", {})
        parts.append(f"- Repayment Score: {repayment.get('score', 'N/A')}")
        parts.append(f"- Max DPD: {repayment.get('max_dpd', 0)}")
        covenant = etb_analysis.get("covenant", {})
        parts.append(f"- Covenant Breach Rate: {covenant.get('breach_rate_pct', 0)}%")
        flags = etb_analysis.get("all_flags", [])
        if flags:
            parts.append(f"- Red Flags: {'; '.join(flags[:5])}")

    context = "\n".join(parts)
    if len(context) > MAX_CONTEXT_CHARS:
        context = context[:MAX_CONTEXT_CHARS] + "\n\n[Context truncated for model limits]"

    return context


# ═══════════════════════════════════════════════════════════════════════════════
#  Chat Functions
# ═══════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are an expert credit analyst and financial advisor for a corporate lending platform.
You have comprehensive access to the company's CAM (Credit Appraisal Memorandum) data including:
- Financial statements, ratios, and growth trends
- Credit strengths and key risks identified by the analysis engine
- Collateral coverage and security details
- Corporate hierarchy and group structure
- Cash flow analysis and repayment capacity
- ETB behavioral analytics (conduct, repayment history, covenants)
- Document extraction results
- Validation exceptions and policy decisions

Your role as Financial Advisor:
- Explain the credit assessment and its implications clearly
- Break down financial metrics, ratios, and what they mean for creditworthiness
- Highlight key strengths that support the lending decision
- Identify and explain risks and their potential impact
- Compare performance against industry benchmarks
- Advise on conditions, covenants, and monitoring requirements
- Provide insights on corporate hierarchy and group risk
- Answer any question about the CAM report content
- Guide analysts through the credit decision rationale

Be concise, professional, and data-driven. Use Indian banking terminology where appropriate.
Always cite specific numbers from the data when answering. Distinguish between facts and assessments.
Amounts are in ₹ Crore unless specified otherwise.
Use short section headers when useful and keep multiline formatting readable.
Never use placeholders such as X, TBD, or assumed values. If a value is unavailable, explicitly say it is unavailable.
When the user asks for a detailed explanation, complete the answer fully and end with a short conclusion. Do not stop mid-sentence.

When answering, cite the data source (e.g., "Source: MCA Company Master", "Source: CIBIL Bureau Report",
"Source: Audited Financials FY2024") so the analyst knows where each data point originated.
If the data source status shows 'n/a' or 'failed', note the limitation in your response."""


def get_or_create_session(entity_id: str, case_data: dict | None = None,
                          extraction: dict | None = None,
                          etb_analysis: dict | None = None,
                          probe_context: str | None = None) -> ChatSession:
    """Get existing session or create a new one with context."""
    context = build_context(entity_id, case_data, extraction, etb_analysis, probe_context)
    if entity_id in _sessions:
        session = _sessions[entity_id]
        if session.context != context:
            session.context = context
            if session.messages and session.messages[0].role == "system":
                session.messages[0].content = f"{SYSTEM_PROMPT}\n\n{context}"
        return session

    session = ChatSession(entity_id=entity_id, context=context)
    session.messages.append(ChatMessage(role="system", content=f"{SYSTEM_PROMPT}\n\n{context}"))
    _sessions[entity_id] = session
    return session


def clear_session(entity_id: str):
    """Clear chat session for an entity."""
    _sessions.pop(entity_id, None)


async def chat(entity_id: str, user_message: str,
               case_data: dict | None = None,
               extraction: dict | None = None,
               etb_analysis: dict | None = None,
               probe_context: str | None = None) -> dict[str, Any]:
    """
    Send a message and get LLM response.
    Falls back to rule-based response if Ollama is unavailable.
    """
    session = get_or_create_session(entity_id, case_data, extraction, etb_analysis, probe_context)

    # Add user message
    session.messages.append(ChatMessage(role="user", content=user_message))

    # Trim history if too long
    if len(session.messages) > MAX_HISTORY + 1:  # +1 for system message
        session.messages = [session.messages[0]] + session.messages[-(MAX_HISTORY):]

    # Try LLM (active provider or Ollama)
    try:
        active = config.get_active_llm_provider() or {}
        if active.get("type") == "ollama":
            response = await _call_ollama(session)
            model_name = _get_chat_model()
        else:
            response = await _call_llm_provider(session)
            model_name = active.get("model", active.get("type", "unknown"))
        session.messages.append(ChatMessage(role="assistant", content=response))
        return {
            "response": response,
            "source": "llm",
            "model": model_name,
            "entity_id": entity_id,
            "message_count": len(session.messages),
        }
    except Exception as e:
        # Fallback to rule-based
        response = _rule_based_response(user_message, session.context)
        session.messages.append(ChatMessage(role="assistant", content=response))
        return {
            "response": response,
            "source": "rule_based",
            "llm_error": str(e),
            "entity_id": entity_id,
            "message_count": len(session.messages),
        }


_CHAT_TEMPERATURE = 0.25
_CHAT_MAX_TOKENS = 1400
_provider_cache: dict[str, Any] = {}


def _chat_provider(cfg: dict):
    """A provider for chat, reused across messages while its configuration is unchanged.

    Chat goes through the same provider layer as CAM generation, so it gets the same
    retries, connection reuse, keep-alive and truncation warnings.
    """
    from src.core.llm_provider import create_llm_provider

    key = json.dumps(cfg, sort_keys=True, default=str)
    provider = _provider_cache.get(key)
    if provider is None:
        if len(_provider_cache) >= 8:  # config edited many times: drop stale entries
            _provider_cache.clear()
        provider = _provider_cache[key] = create_llm_provider(cfg)
    return provider


async def _call_llm_provider(session: ChatSession) -> str:
    """Call the active (non-Ollama) LLM provider for chat completion."""
    provider = _chat_provider(config.get_active_llm_provider())

    system_content = ""
    parts = []
    for m in session.messages:
        if m.role == "system":
            system_content = m.content
        elif m.role == "user":
            parts.append(f"User: {m.content}")
        elif m.role == "assistant":
            parts.append(f"Assistant: {m.content}")
    prompt = "\n\n".join(parts)

    response = await asyncio.to_thread(provider.generate, prompt, system_prompt=system_content,
                                       temperature=_CHAT_TEMPERATURE, max_tokens=_CHAT_MAX_TOKENS)
    return str(response).strip()


def _ollama_chat_provider():
    """The Ollama provider configured for chat: the chat model and host, and the
    chat timeout instead of the (much longer) per-CAM-section timeout."""
    settings = config.get("llm_providers", "providers", "ollama", default={}) or {}
    cfg = {**settings, "type": "ollama", "model": _get_chat_model(), "base_url": _get_ollama_host(),
           "timeout_seconds": settings.get("chat_timeout_seconds", 120)}
    return _chat_provider(cfg)


async def _call_ollama(session: ChatSession) -> str:
    """Chat completion on Ollama, with one continuation if the reply stops mid-thought."""
    provider = _ollama_chat_provider()

    # Build a single prompt from conversation history
    parts = []
    for m in session.messages:
        if m.role == "system":
            parts.append(f"System: {m.content}")
        elif m.role == "user":
            parts.append(f"User: {m.content}")
        elif m.role == "assistant":
            parts.append(f"Assistant: {m.content}")
    parts.append("Assistant:")
    prompt = "\n\n".join(parts)

    response = await _ollama_generate(provider, prompt)

    if _response_looks_incomplete(response):
        continuation_prompt = (
            f"{prompt}{response}\n\n"
            "Assistant: Continue from the last incomplete sentence only. "
            "Do not repeat earlier sections. Finish the remaining analysis and end with a short conclusion."
        )
        continuation = await _ollama_generate(provider, continuation_prompt)
        if continuation:
            response = f"{response.rstrip()}\n\n{continuation.lstrip()}"

    return response


async def _ollama_generate(provider, prompt: str) -> str:
    # The prompt already carries the "System:/User:/Assistant:" transcript, so no separate
    # system prompt. The provider reuses the model's loaded context size (no reload after
    # a CAM run) and applies keep_alive / think from the Ollama settings.
    text = await asyncio.to_thread(provider.generate, prompt,
                                   temperature=_CHAT_TEMPERATURE, max_tokens=_CHAT_MAX_TOKENS)
    return text or "No response from model."


def _response_looks_incomplete(text: str) -> bool:
    content = str(text or "").strip()
    if not content:
        return True
    if content.endswith((":", ",", ";", "-", "(", "/", "vs", "vs.")):
        return True
    if re.search(r"\b(ongoing|regulatory|compliance|market|exposure)\s*$", content, re.IGNORECASE):
        return True
    return content[-1] not in ".!?)”\"'"


def _rule_based_response(question: str, context: str) -> str:
    """Fallback rule-based responses when LLM is unavailable."""
    q = question.lower()

    if any(w in q for w in ["revenue", "sales", "turnover", "top line"]):
        return _extract_context_answer(context, "Revenue")
    if any(w in q for w in ["profit", "pat", "net income", "bottom line"]):
        return _extract_context_answer(context, "PAT")
    if any(w in q for w in ["ebitda", "operating profit", "margin"]):
        return _extract_context_answer(context, "EBITDA")
    if any(w in q for w in ["debt", "leverage", "borrowing"]):
        return _extract_context_answer(context, "Debt")
    if any(w in q for w in ["ratio", "current ratio", "debt equity"]):
        return _extract_context_answer(context, "Ratio")
    if any(w in q for w in ["risk", "flag", "concern", "issue"]):
        return _extract_context_answer(context, "Red Flag")
    if any(w in q for w in ["recommendation", "decision", "approve", "grade"]):
        return _extract_context_answer(context, "Policy Decision")
    if any(w in q for w in ["conduct", "cheque", "dpd", "repayment"]):
        return _extract_context_answer(context, "ETB")
    if any(w in q for w in ["covenant", "breach", "compliance"]):
        return _extract_context_answer(context, "Covenant")
    if any(w in q for w in ["rating", "crisil", "care", "icra"]):
        return _extract_context_answer(context, "Rating")
    if any(w in q for w in ["source", "data source", "provenance", "where", "origin"]):
        return _extract_context_answer(context, "Data Source")
    if any(w in q for w in ["summary", "overview", "brief"]):
        return f"Based on the available data:\n\n{context[:1500]}\n\n(Note: LLM unavailable, showing raw context. Start Ollama for intelligent responses.)"

    return ("I can help with questions about this company's financials, ratios, risk assessment, "
            "validation findings, ETB conduct, covenants, and credit recommendation. "
            "Please ask a specific question.\n\n"
            "(Note: Ollama LLM is currently unavailable. Responses are rule-based. "
            "Start Ollama on the host machine for full AI-powered analysis.)")


def _extract_context_answer(context: str, topic: str) -> str:
    """Extract relevant lines from context for a topic."""
    lines = context.split("\n")
    relevant = []
    capturing = False
    for line in lines:
        if topic.lower() in line.lower() or (capturing and line.startswith("  ")):
            relevant.append(line)
            capturing = True
        elif capturing and not line.startswith(" "):
            if line.strip() and not line.startswith("#"):
                capturing = False
            elif line.startswith("##"):
                capturing = False

    if relevant:
        return "\n".join(relevant[:15]) + "\n\n(Rule-based extraction. Start Ollama for AI analysis.)"
    return f"No specific {topic} data found in context. Try asking about financials, ratios, or risk flags."


def get_session_history(entity_id: str) -> list[dict]:
    """Get chat history for an entity."""
    session = _sessions.get(entity_id)
    if not session:
        return []
    return [m.to_dict() for m in session.messages if m.role != "system"]


def list_sessions() -> list[dict]:
    """List all active chat sessions."""
    return [
        {
            "entity_id": eid,
            "message_count": len(s.messages),
            "created_at": s.created_at,
        }
        for eid, s in _sessions.items()
    ]
