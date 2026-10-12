"""
Pluggable Engine Registry
Register, enable/disable, and invoke computation engines at runtime.
"""

from typing import Callable, Any
import threading


class EngineEntry:
    __slots__ = ("name", "fn", "version", "description", "enabled", "category")

    def __init__(self, name, fn, version="1.0.0", description="", enabled=True, category="core"):
        self.name = name
        self.fn = fn
        self.version = version
        self.description = description
        self.enabled = enabled
        self.category = category


class EngineRegistry:
    """Singleton registry for pluggable computation engines."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._engines: dict[str, EngineEntry] = {}
        return cls._instance

    def register(self, name: str, fn: Callable, **kwargs):
        self._engines[name] = EngineEntry(name, fn, **kwargs)

    def get(self, name: str) -> Callable | None:
        entry = self._engines.get(name)
        return entry.fn if entry and entry.enabled else None

    def execute(self, name: str, *args, **kwargs) -> Any:
        fn = self.get(name)
        if fn is None:
            raise ValueError(f"Engine '{name}' not found or disabled")
        return fn(*args, **kwargs)

    def enable(self, name: str):
        if name in self._engines:
            self._engines[name].enabled = True

    def disable(self, name: str):
        if name in self._engines:
            self._engines[name].enabled = False

    def is_enabled(self, name: str) -> bool:
        e = self._engines.get(name)
        return e.enabled if e else False

    def list_engines(self) -> list[dict]:
        return [
            {
                "name": e.name,
                "version": e.version,
                "description": e.description,
                "enabled": e.enabled,
                "category": e.category,
            }
            for e in self._engines.values()
        ]

    @classmethod
    def reset(cls):
        cls._instance = None


# Module-level singleton
registry = EngineRegistry()


def register_default_engines():
    """Register the default deterministic engine set."""
    from src.engines.ratio_engine import compute_all_ratios, compute_multi_period_ratios
    from src.engines.validation_engine import run_all_validations
    from src.engines.benchmark_engine import benchmark_all_periods, get_worst_benchmarks
    from src.engines.policy_engine import tier1_hard_rules, tier2_scoring, tier3_recommendation
    from src.engines.cam_fact_builder import build_cam_fact_pack
    # v2 is the template renderer the CAM path uses (cam_service, cam_llm_renderer);
    # src/engines/cam_renderer.py is the legacy v1 kept only for older tests.
    from src.engines.cam_renderer_v2 import render_complete_cam

    engines = [
        ("ratio_engine",       compute_all_ratios,         "1.0.0", "Compute 15 financial ratios",         "analysis"),
        ("ratio_multi_period", compute_multi_period_ratios,"1.0.0", "Multi-period ratio analysis",         "analysis"),
        ("validation_engine",  run_all_validations,        "1.0.0", "5-level validation engine",           "validation"),
        ("benchmark_engine",   benchmark_all_periods,      "1.0.0", "Sector peer benchmarking",            "benchmark"),
        ("benchmark_worst",    get_worst_benchmarks,       "1.0.0", "Extract worst benchmark results",     "benchmark"),
        ("policy_tier1",       tier1_hard_rules,           "1.0.0", "Hard pass/fail rules",                "policy"),
        ("policy_tier2",       tier2_scoring,              "1.0.0", "Risk scoring model",                  "policy"),
        ("policy_tier3",       tier3_recommendation,       "1.0.0", "Recommendation assembly",             "policy"),
        ("fact_pack_builder",  build_cam_fact_pack,        "1.0.0", "CAM fact-pack builder",               "cam"),
        ("cam_renderer",       render_complete_cam,        "1.0.0", "CAM narrative renderer (template)",   "cam"),
    ]
    for name, fn, ver, desc, cat in engines:
        registry.register(name, fn, version=ver, description=desc, category=cat)
