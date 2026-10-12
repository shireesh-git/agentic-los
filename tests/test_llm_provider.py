"""LLM provider configuration helpers (no network)."""

import os
from unittest.mock import patch

from src.core.llm_provider import OllamaProvider, OpenAIProvider, strip_reasoning


def _provider(**cfg):
    return OllamaProvider({"model": "qwen3:8b", "num_ctx": 8192, "max_num_ctx": 32768, **cfg})


def test_short_prompt_keeps_configured_window():
    assert _provider().context_window("x" * 3000, num_predict=2500) == 8192


def test_long_prompt_grows_window_in_doublings():
    # ~15,000 prompt tokens + 2,500 answer tokens needs the 32K bucket.
    assert _provider().context_window("x" * 45_000, num_predict=2500) == 32768
    assert _provider().context_window("x" * 24_000, num_predict=2500) == 16384


def test_window_is_capped_at_max():
    assert _provider().context_window("x" * 300_000, num_predict=2500) == 32768


def test_strip_reasoning():
    assert strip_reasoning("<think>plan\nsteps</think>\n## Section") == "## Section"
    assert strip_reasoning(None) == ""


def test_openai_compatible_provider_honours_model_and_timeout_environment():
    cfg = {
        "model": "fallback-model",
        "model_env": "TEST_NIM_MODEL",
        "api_key_env": "TEST_NIM_KEY",
        "timeout_seconds": 300,
        "timeout_seconds_env": "TEST_NIM_TIMEOUT",
        "chat_template_kwargs": {"enable_thinking": False},
    }
    with patch.dict(os.environ, {
        "TEST_NIM_MODEL": "nvidia/nemotron-3-super-120b-a12b",
        "TEST_NIM_KEY": "test-only",
        "TEST_NIM_TIMEOUT": "60",
    }, clear=False):
        provider = OpenAIProvider(cfg)
    assert provider.model == "nvidia/nemotron-3-super-120b-a12b"
    assert provider._timeout == 60.0
    assert provider._chat_template_kwargs == {"enable_thinking": False}
