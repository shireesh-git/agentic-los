"""
Probe42 v2 MCP client.

Implements the minimal MCP-over-HTTP flow needed by this app:
  1. initialize session
  2. call tools/list or tools/call

Probe returns JSON either directly or inside an SSE `data:` frame, and some tool
responses wrap JSON inside nested text payloads. This client normalizes that
shape so the service layer can work with plain Python dicts/lists.
"""

from __future__ import annotations

import json
import os
from typing import Any
from uuid import uuid4

import httpx

from src.core.config_manager import config


class ProbeMcpError(RuntimeError):
    """Raised when Probe42 MCP returns an error or invalid payload."""


def _try_json_loads(value: str) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return None


def _extract_sse_json(response_text: str) -> dict[str, Any]:
    stripped = (response_text or "").strip()
    if not stripped:
        raise ProbeMcpError("Empty response from Probe42 MCP")

    direct = _try_json_loads(stripped)
    if isinstance(direct, dict):
        return direct

    messages: list[dict[str, Any]] = []
    for raw_line in stripped.splitlines():
        line = raw_line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        parsed = _try_json_loads(payload)
        if isinstance(parsed, dict):
            messages.append(parsed)

    if not messages:
        raise ProbeMcpError("Could not parse Probe42 MCP response")

    return messages[-1]


def _unwrap_text_payload(value: Any) -> Any:
    """
    Probe sometimes nests JSON strings two levels deep:
      {"content":{"type":"text","text":"{...actual json...}"}}
    """
    current = value
    for _ in range(4):
        if not isinstance(current, str):
            return current
        parsed = _try_json_loads(current.strip())
        if not isinstance(parsed, dict):
            return current
        content = parsed.get("content")
        if isinstance(content, dict) and content.get("type") == "text" and isinstance(content.get("text"), str):
            current = content["text"]
            continue
        if "data" in parsed or "metadata" in parsed:
            return parsed
        return parsed
    return current


def normalize_mcp_tool_result(result: dict[str, Any]) -> dict[str, Any]:
    texts: list[str] = []
    data: Any = result.get("structuredContent")
    if isinstance(data, dict) and "data" not in data and "metadata" not in data:
        nested_content = data.get("content")
        if isinstance(nested_content, dict) and isinstance(nested_content.get("text"), str):
            data = _unwrap_text_payload(nested_content.get("text"))
        else:
            nested_structured = data.get("structured_content")
            if isinstance(nested_structured, dict):
                data = nested_structured

    for item in result.get("content", []):
        if not isinstance(item, dict) or item.get("type") != "text":
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        texts.append(text)
        if data is None:
            unwrapped = _unwrap_text_payload(text)
            if isinstance(unwrapped, (dict, list)):
                data = unwrapped

    if isinstance(data, str):
        data = _unwrap_text_payload(data)

    return {
        "data": data,
        "text": "\n".join(texts).strip(),
        "raw": result,
    }


class ProbeMcpClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key_env: str | None = None,
        timeout_seconds: float = 30.0,
    ):
        probe_cfg = config.get("external_apis", "probe42", default={}) or {}
        self.base_url = base_url or probe_cfg.get("mcp_url") or "https://api-mcp.probe42.in/api/mcp"
        self.api_key_env = api_key_env or probe_cfg.get("api_key_env") or "PROBE42_API_KEY"
        self.timeout_seconds = float(timeout_seconds)

    def get_api_key(self) -> str | None:
        return os.environ.get(self.api_key_env)

    def is_configured(self) -> bool:
        return bool(self.get_api_key())

    def _headers(self, session_id: str | None = None) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if session_id:
            headers["mcp-session-id"] = session_id
        return headers

    def _post(self, payload: dict[str, Any], session_id: str | None = None) -> tuple[dict[str, Any], str | None]:
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(self.base_url, headers=self._headers(session_id), json=payload)
            response.raise_for_status()
        body = _extract_sse_json(response.text)
        if "error" in body:
            error = body["error"] or {}
            raise ProbeMcpError(error.get("message") or "Probe42 MCP error")
        return body, response.headers.get("mcp-session-id") or session_id

    def initialize_session(self) -> str:
        payload = {
            "jsonrpc": "2.0",
            "id": f"probe-init-{uuid4()}",
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "CAM Intelligence Platform", "version": "1.0.0"},
            },
        }
        body, session_id = self._post(payload)
        if not session_id:
            raise ProbeMcpError("Probe42 MCP did not return a session id")

        # The MCP spec expects an initialized notification after successful init.
        notify = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }
        try:
            self._post(notify, session_id=session_id)
        except Exception:
            # Probe works even if this notification is ignored or unsupported.
            pass

        if body.get("result") is None:
            raise ProbeMcpError("Probe42 MCP initialize returned no result")
        return session_id

    def list_tools(self, session_id: str | None = None) -> dict[str, Any]:
        sid = session_id or self.initialize_session()
        payload = {
            "jsonrpc": "2.0",
            "id": f"probe-tools-{uuid4()}",
            "method": "tools/list",
            "params": {},
        }
        body, _ = self._post(payload, session_id=sid)
        return body.get("result", {})

    def call_tool(self, tool_name: str, arguments: dict[str, Any], session_id: str | None = None) -> dict[str, Any]:
        sid = session_id or self.initialize_session()
        payload = {
            "jsonrpc": "2.0",
            "id": f"probe-call-{uuid4()}",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }
        body, _ = self._post(payload, session_id=sid)
        return normalize_mcp_tool_result(body.get("result", {}))
