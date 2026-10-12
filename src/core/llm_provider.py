"""
LLM Provider Abstraction Layer
Supports Mock, OpenAI, Anthropic, Azure OpenAI, and Ollama.
Switch providers via config/llm_providers.yaml — no code changes.
"""

import copy
import json
import logging
import os
import random
import re
import threading
import time
from abc import ABC, abstractmethod
from contextlib import contextmanager


log = logging.getLogger(__name__)

_REASONING_BLOCK = re.compile(r"<think>.*?</think>", flags=re.DOTALL | re.IGNORECASE)


def strip_reasoning(text: str) -> str:
    """Remove <think>…</think> reasoning that some local models emit inline."""
    return _REASONING_BLOCK.sub("", text or "").strip()


class BaseLLMProvider(ABC):
    name: str = "base"
    # Attribute holding the model name (Azure uses its deployment, Gemini model_name).
    _model_attr: str = "model"

    def with_model(self, model: str) -> "BaseLLMProvider":
        """This provider, same settings and client, but calling ``model`` — used to route
        CAM sections to a different model."""
        clone = copy.copy(self)
        setattr(clone, self._model_attr, model)
        return clone

    @abstractmethod
    def generate(self, prompt: str, system_prompt: str = "",
                 temperature: float = 0.1, max_tokens: int = 4000) -> str:
        pass

    @abstractmethod
    def test_connection(self) -> dict:
        pass


# ─── Shared helpers for hosted (frontier) providers ─────────────────────────

_DEFAULT_MAX_RETRIES = 4
# Rate limits, timeouts and server errors are worth retrying; bad requests and auth errors are not.
_TRANSIENT_STATUS = {408, 409, 429, 500, 502, 503, 504}
_TRANSIENT_NAMES = ("Timeout", "Connection", "ServerError", "ResourceExhausted", "ServiceUnavailable",
                    "RateLimit", "InternalServer")


class _CachedClient:
    """Builds an API client once per provider and reuses it.

    The OpenAI, Anthropic and Google SDK clients are thread-safe and keep a
    connection pool, so parallel CAM sections share connections instead of
    opening a new one (and a new TLS handshake) per call.
    """

    def __init__(self, factory):
        self._factory = factory
        self._client = None
        self._lock = threading.Lock()

    def get(self):
        if self._client is None:
            with self._lock:
                if self._client is None:
                    self._client = self._factory()
        return self._client


def _is_transient(error: Exception) -> bool:
    code = getattr(error, "code", None)
    if not isinstance(code, int):
        code = getattr(error, "status_code", None)
    if isinstance(code, int):
        return code in _TRANSIENT_STATUS
    return any(part in type(error).__name__ for part in _TRANSIENT_NAMES)


def _call_with_retries(call, *, provider: str, max_retries: int, base_delay: float = 2.0,
                       max_delay: float = 60.0):
    """Run ``call()``; on a transient error wait (exponential backoff with jitter) and retry.

    Used for SDKs without built-in retries. OpenAI and Anthropic retry by
    themselves (their ``max_retries`` setting, which also honours Retry-After).
    """
    for attempt in range(max_retries + 1):
        try:
            return call()
        except Exception as e:
            if attempt >= max_retries or not _is_transient(e):
                raise
            delay = min(max_delay, base_delay * (2 ** attempt)) * random.uniform(0.5, 1.0)
            log.warning("%s call failed (%s: %s); retry %d of %d in %.1fs",
                        provider, type(e).__name__, getattr(e, "code", ""), attempt + 1, max_retries, delay)
            time.sleep(delay)


def _warn_if_truncated(provider: str, truncated: bool, limit) -> None:
    if truncated:
        # A cut-off CAM section reads as finished; make it visible so its limit can be raised
        # in llm_providers.yaml (narrative.section_max_tokens).
        log.warning("%s output hit the %s-token limit and was cut short", provider, limit)


class MockLLMProvider(BaseLLMProvider):
    name = "mock"

    def generate(self, prompt: str, system_prompt: str = "",
                 temperature: float = 0.1, max_tokens: int = 4000) -> str:
        return "[Mock Mode — using deterministic template rendering]"

    def test_connection(self) -> dict:
        return {"status": "ok", "provider": "mock", "message": "Mock provider always available"}


class OpenAIProvider(BaseLLMProvider):
    name = "openai"

    def __init__(self, cfg: dict):
        self.model = os.environ.get(cfg.get("model_env", "")) or cfg.get("model", "gpt-4")
        self.api_key = os.environ.get(cfg.get("api_key_env", "OPENAI_API_KEY"), "")
        # OpenAI-compatible endpoints (e.g. NVIDIA NIM): base_url_env, when set in the
        # environment, overrides base_url. None = api.openai.com.
        self.base_url = os.environ.get(cfg.get("base_url_env", "")) or cfg.get("base_url")
        self._temp = cfg.get("temperature", 0.1)
        self._max = cfg.get("max_tokens", 4000)
        self._max_retries = int(cfg.get("max_retries", _DEFAULT_MAX_RETRIES))
        timeout_env = os.environ.get(cfg.get("timeout_seconds_env", ""))
        self._timeout = float(timeout_env) if timeout_env else cfg.get("timeout_seconds")
        # Reasoning models (o-series, gpt-oss): "low" | "medium" | "high". Unset = not sent.
        self._reasoning_effort = cfg.get("reasoning_effort")
        self._chat_template_kwargs = cfg.get("chat_template_kwargs") or None
        self._client = _CachedClient(self._make_client)

    def _make_client(self):
        import openai
        kwargs = {"api_key": self.api_key, "max_retries": self._max_retries}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        if self._timeout:
            kwargs["timeout"] = float(self._timeout)
        return openai.OpenAI(**kwargs)

    def generate(self, prompt: str, system_prompt: str = "",
                 temperature: float = None, max_tokens: int = None) -> str:
        msgs = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        msgs.append({"role": "user", "content": prompt})
        limit = max_tokens or self._max
        extra = {"reasoning_effort": self._reasoning_effort} if self._reasoning_effort else {}
        if self._chat_template_kwargs:
            extra["extra_body"] = {"chat_template_kwargs": self._chat_template_kwargs}
        r = self._client.get().chat.completions.create(
            model=self.model, messages=msgs,
            temperature=self._temp if temperature is None else temperature,
            max_tokens=limit,
            **extra,
        )
        choice = r.choices[0]
        _warn_if_truncated(self.name, choice.finish_reason == "length", limit)
        return choice.message.content or ""

    def test_connection(self) -> dict:
        try:
            self._client.get().models.list()
            return {"status": "ok", "provider": "openai", "model": self.model}
        except Exception as e:
            return {"status": "error", "provider": "openai", "message": str(e)}


class AnthropicProvider(BaseLLMProvider):
    name = "anthropic"

    def __init__(self, cfg: dict):
        self.model = cfg.get("model", "claude-sonnet-4-20250514")
        self.api_key = os.environ.get(cfg.get("api_key_env", "ANTHROPIC_API_KEY"), "")
        self._temp = cfg.get("temperature", 0.1)
        self._max = cfg.get("max_tokens", 4000)
        self._max_retries = int(cfg.get("max_retries", _DEFAULT_MAX_RETRIES))
        self._client = _CachedClient(self._make_client)

    def _make_client(self):
        import anthropic
        return anthropic.Anthropic(api_key=self.api_key, max_retries=self._max_retries)

    def generate(self, prompt: str, system_prompt: str = "",
                 temperature: float = None, max_tokens: int = None) -> str:
        limit = max_tokens or self._max
        r = self._client.get().messages.create(
            model=self.model,
            max_tokens=limit,
            system=system_prompt or "You are a helpful assistant.",
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature or self._temp,
        )
        _warn_if_truncated(self.name, r.stop_reason == "max_tokens", limit)
        return "".join(block.text for block in r.content if getattr(block, "type", "") == "text")

    def test_connection(self) -> dict:
        if not self.api_key:
            return {"status": "error", "provider": "anthropic", "message": "API key not set"}
        return {"status": "ok", "provider": "anthropic", "model": self.model}


class AzureOpenAIProvider(BaseLLMProvider):
    name = "azure_openai"
    _model_attr = "deployment"

    def __init__(self, cfg: dict):
        self.deployment = cfg.get("deployment", "gpt-4")
        self.api_key = os.environ.get(cfg.get("api_key_env", "AZURE_OPENAI_API_KEY"), "")
        self.endpoint = os.environ.get(cfg.get("endpoint_env", "AZURE_OPENAI_ENDPOINT"), "")
        self.api_version = cfg.get("api_version", "2024-02-15-preview")
        self._temp = cfg.get("temperature", 0.1)
        self._max = cfg.get("max_tokens", 4000)
        self._max_retries = int(cfg.get("max_retries", _DEFAULT_MAX_RETRIES))
        self._client = _CachedClient(self._make_client)

    def _make_client(self):
        import openai
        return openai.AzureOpenAI(
            api_key=self.api_key, azure_endpoint=self.endpoint,
            api_version=self.api_version, max_retries=self._max_retries,
        )

    def generate(self, prompt: str, system_prompt: str = "",
                 temperature: float = None, max_tokens: int = None) -> str:
        msgs = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        msgs.append({"role": "user", "content": prompt})
        limit = max_tokens or self._max
        r = self._client.get().chat.completions.create(
            model=self.deployment, messages=msgs,
            temperature=temperature or self._temp,
            max_tokens=limit,
        )
        choice = r.choices[0]
        _warn_if_truncated(self.name, choice.finish_reason == "length", limit)
        return choice.message.content or ""

    def test_connection(self) -> dict:
        if not self.api_key or not self.endpoint:
            return {"status": "error", "provider": "azure_openai", "message": "Key or endpoint not set"}
        return {"status": "ok", "provider": "azure_openai", "deployment": self.deployment}


class VertexAIGeminiProvider(BaseLLMProvider):
    name = "vertex_ai_gemini"
    _model_attr = "model_name"

    def __init__(self, cfg: dict):
        self.model_name = cfg.get("model", "gemini-2.0-flash")
        self.project = cfg.get("project") or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
        self.location = cfg.get("location", "asia-south1")
        self.api_key = os.environ.get(cfg.get("api_key_env", "GOOGLE_API_KEY"), "")
        self._temp = cfg.get("temperature", 0.15)
        self._max = cfg.get("max_tokens", 4000)
        self._max_retries = int(cfg.get("max_retries", _DEFAULT_MAX_RETRIES))
        self._cached_client = _CachedClient(self._make_client)

    def _make_client(self):
        from google import genai
        if self.api_key:
            return genai.Client(api_key=self.api_key)
        return genai.Client(vertexai=True, project=self.project, location=self.location)

    def _client(self):
        return self._cached_client.get()

    def generate(self, prompt: str, system_prompt: str = "",
                 temperature: float = None, max_tokens: int = None) -> str:
        from google.genai import types
        limit = max_tokens or self._max
        config = types.GenerateContentConfig(
            system_instruction=system_prompt or None,
            temperature=temperature or self._temp,
            max_output_tokens=limit,
        )
        # The google-genai SDK does not retry on its own; rate limits are likely
        # when several CAM sections are generated in parallel.
        response = _call_with_retries(
            lambda: self._client().models.generate_content(
                model=self.model_name, contents=prompt, config=config,
            ),
            provider=self.name, max_retries=self._max_retries,
        )
        candidates = getattr(response, "candidates", None) or []
        finish = getattr(candidates[0], "finish_reason", None) if candidates else None
        _warn_if_truncated(self.name, str(getattr(finish, "name", finish) or "").upper().endswith("MAX_TOKENS"),
                           limit)
        return response.text or ""

    def test_connection(self) -> dict:
        try:
            client = self._client()
            from google.genai import types
            config = types.GenerateContentConfig(max_output_tokens=20)
            resp = client.models.generate_content(
                model=self.model_name, contents="Say hello", config=config,
            )
            mode = "api_key" if self.api_key else "vertex_ai"
            return {"status": "ok", "provider": "vertex_ai_gemini",
                    "model": self.model_name, "mode": mode, "response": resp.text[:50]}
        except Exception as e:
            raise RuntimeError(f"LLM connection failed: {e}. Provider: vertex_ai_gemini")


# Ollama reloads a model whenever a request's num_ctx differs from the one it is
# loaded with. CAM generation and chat share the model, so each call records the
# num_ctx it used and chat reuses it instead of falling back to Ollama's default.
_ollama_ctx_lock = threading.Lock()
_ollama_ctx_in_use: dict[tuple[str, str], int] = {}


def _ollama_key(base_url: str, model: str) -> tuple[str, str]:
    return (str(base_url or "").rstrip("/"), str(model or ""))


def _record_ollama_context(base_url: str, model: str, num_ctx: int) -> None:
    with _ollama_ctx_lock:
        _ollama_ctx_in_use[_ollama_key(base_url, model)] = int(num_ctx)


def _ollama_context_in_use(base_url: str, model: str) -> int:
    with _ollama_ctx_lock:
        return _ollama_ctx_in_use.get(_ollama_key(base_url, model), 0)


class OllamaProvider(BaseLLMProvider):
    name = "ollama"

    def __init__(self, cfg: dict):
        self.model = cfg.get("model", "llama3")
        # OLLAMA_HOST env var (set in Docker compose) takes priority over config
        self.base_url = os.environ.get("OLLAMA_HOST") or cfg.get("base_url", "http://localhost:11434")
        self._temp = cfg.get("temperature", 0.1)
        self._max = cfg.get("max_tokens", 4000)
        self._num_ctx = int(cfg.get("num_ctx", 8192))
        self._max_ctx = int(cfg.get("max_num_ctx", 32768))
        self._timeout = float(cfg.get("timeout_seconds", 600))
        # Reasoning models (qwen3, deepseek-r1): False skips the hidden "thinking" pass.
        self._think = cfg.get("think")
        # How long Ollama keeps the model in memory after a call ("15m", seconds, 0 = unload
        # at once). None leaves Ollama's own default (5 minutes).
        self._keep_alive = cfg.get("keep_alive")
        # Set by fixed_context_window() for the length of a batch (one CAM run).
        self._fixed_ctx: int | None = None

    @contextmanager
    def fixed_context_window(self, requests: list[tuple[str, str, int]]):
        """Use one ``num_ctx`` for a batch of ``(system_prompt, prompt, max_tokens)`` calls.

        Ollama reloads the model whenever ``num_ctx`` changes, and per-prompt sizing
        can switch between 8K/16K/32K several times in one CAM — each switch costs
        a full model reload on CPU. The batch uses the largest window any of its
        prompts needs, so no prompt is truncated and the model loads once.
        """
        window = max((self.context_window(self._full_prompt(system_prompt, prompt), max_tokens)
                      for system_prompt, prompt, max_tokens in requests), default=self._num_ctx)
        previous, self._fixed_ctx = self._fixed_ctx, window
        log.info("Ollama: fixed num_ctx=%d for %d prompt(s)", window, len(requests))
        try:
            yield window
        finally:
            self._fixed_ctx = previous

    @staticmethod
    def _full_prompt(system_prompt: str, prompt: str) -> str:
        return f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

    def context_window(self, prompt: str, num_predict: int) -> int:
        """Smallest context bucket that holds the prompt plus the answer.

        Ollama silently drops the *start* of a prompt that exceeds ``num_ctx``,
        which would cut the system prompt and section instructions. Sizes step
        in doublings so Ollama reloads the model rarely (a reload happens
        whenever ``num_ctx`` changes).
        """
        estimated_tokens = len(prompt) // 3 + num_predict  # JSON-heavy text ≈ 3 chars/token
        window = self._num_ctx
        while window < estimated_tokens and window < self._max_ctx:
            window *= 2
        window = min(window, self._max_ctx)
        if estimated_tokens > window:
            log.warning("Prompt (~%d tokens incl. answer) exceeds max_num_ctx=%d; the start will be truncated",
                        estimated_tokens, window)
        return window

    def generate(self, prompt: str, system_prompt: str = "",
                 temperature: float = None, max_tokens: int = None) -> str:
        import httpx
        full = self._full_prompt(system_prompt, prompt)
        num_predict = self._max if max_tokens is None else max_tokens
        # A CAM batch fixes num_ctx; any other call (e.g. chat) reuses the size the model is
        # already loaded with, so switching between them does not force a reload.
        num_ctx = self._fixed_ctx or max(self.context_window(full, num_predict),
                                         _ollama_context_in_use(self.base_url, self.model))
        # Streamed, so timeout_seconds limits *silence* (no token for that long), not the
        # total time: a long section on a slow CPU keeps going as long as tokens arrive.
        # With stream=false Ollama sends nothing until the end, and a big section (e.g.
        # financial analysis) could hit the timeout while working normally.
        payload = {"model": self.model, "prompt": full, "stream": True,
                   "options": {"temperature": self._temp if temperature is None else temperature,
                               "num_predict": num_predict,
                               "num_ctx": num_ctx}}
        if self._think is not None:
            payload["think"] = bool(self._think)
        if self._keep_alive is not None:
            payload["keep_alive"] = self._keep_alive

        parts: list[str] = []
        final: dict = {}
        timeout = httpx.Timeout(self._timeout, connect=30.0)
        with httpx.stream("POST", f"{self.base_url}/api/generate", json=payload, timeout=timeout) as r:
            if r.status_code == 404:
                raise RuntimeError(f"Ollama model '{self.model}' is not installed. Run: ollama pull {self.model}")
            if r.status_code >= 400:
                r.read()
                r.raise_for_status()
            _record_ollama_context(self.base_url, self.model, num_ctx)
            for line in r.iter_lines():
                if not line.strip():
                    continue
                chunk = json.loads(line)
                if chunk.get("error"):
                    raise RuntimeError(f"Ollama error: {chunk['error']}")
                parts.append(chunk.get("response", ""))
                if chunk.get("done"):
                    final = chunk
                    break
        _warn_if_truncated(self.name, final.get("done_reason") == "length", num_predict)
        if final.get("eval_count") and final.get("eval_duration"):
            log.info("Ollama %s: %d tokens at %.1f tok/s (prompt %s tokens)", self.model, final["eval_count"],
                     final["eval_count"] / (final["eval_duration"] / 1e9), final.get("prompt_eval_count", "?"))
        return strip_reasoning("".join(parts))

    def release(self) -> None:
        """Unload this model from Ollama now, freeing its RAM (used between routed model groups)."""
        import httpx
        try:
            httpx.post(f"{self.base_url}/api/generate", json={"model": self.model, "keep_alive": 0}, timeout=60)
            with _ollama_ctx_lock:
                _ollama_ctx_in_use.pop(_ollama_key(self.base_url, self.model), None)
            log.info("Ollama: unloaded %s", self.model)
        except Exception as e:  # best effort: Ollama unloads it after keep_alive anyway
            log.warning("Ollama: could not unload %s: %s", self.model, e)

    def test_connection(self) -> dict:
        """Ollama is reachable and the configured model is installed."""
        try:
            import httpx
            r = httpx.get(f"{self.base_url}/api/tags", timeout=5.0)
            models = [m["name"] for m in r.json().get("models", [])]
        except Exception as e:
            return {"status": "error", "provider": "ollama", "message": f"Ollama not reachable: {e}"}
        if self.model not in models and f"{self.model}:latest" not in models:
            return {"status": "error", "provider": "ollama", "models": models,
                    "message": f"Model '{self.model}' is not installed. Run: ollama pull {self.model}"}
        return {"status": "ok", "provider": "ollama", "model": self.model, "models": models}


# ─── Factory ────────────────────────────────────────────────────────────────

_PROVIDERS = {
    "mock": lambda c: MockLLMProvider(),
    "openai": lambda c: OpenAIProvider(c),
    "anthropic": lambda c: AnthropicProvider(c),
    "azure_openai": lambda c: AzureOpenAIProvider(c),
    "vertex_ai_gemini": lambda c: VertexAIGeminiProvider(c),
    "ollama": lambda c: OllamaProvider(c),
}


def create_llm_provider(provider_config: dict) -> BaseLLMProvider:
    ptype = provider_config.get("type")
    if not ptype:
        raise RuntimeError("LLM provider type not configured in llm_providers.yaml")
    factory = _PROVIDERS.get(ptype)
    if not factory:
        raise RuntimeError(f"Unknown LLM provider type: {ptype}")
    provider = factory(provider_config)
    # Optional per-provider cap on concurrent CAM section calls (None = use the narrative default).
    provider.max_parallel_sections = provider_config.get("max_parallel_sections")
    # Optional per-section model routing ({enabled, routes: {model: [section ids]}}); see
    # model_routing in config/llm_providers.yaml and cam_llm_renderer.render_cam_with_llm.
    provider.model_routing = provider_config.get("model_routing")
    return provider
