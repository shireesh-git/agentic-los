"""
Centralized Configuration Manager
Loads YAML configs with hot-reload support and typed accessors.
"""

import logging
import os
import yaml
from pathlib import Path
from typing import Any
import threading

log = logging.getLogger(__name__)


class ConfigManager:
    """Singleton YAML configuration manager."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._configs: dict[str, dict] = {}
        self._config_dir: Path | None = None
        self._file_mtimes: dict[str, float] = {}
        self._initialized = True

    def load(self, config_dir: str | Path = None):
        """Load all YAML configs from directory."""
        if config_dir is None:
            config_dir = (os.getenv("CAM_CONFIG_DIR", "").strip()
                          or Path(__file__).parent.parent.parent / "config")
        self._config_dir = Path(config_dir)

        if not self._config_dir.exists():
            return

        for f in self._config_dir.glob("*.yaml"):
            self._load_file(f)

    def _load_file(self, path: Path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            self._configs[path.stem] = data
            self._file_mtimes[path.stem] = path.stat().st_mtime
        except Exception as e:
            log.error("Error loading config %s: %s", path, e)

    def reload(self):
        """Reload configs that have changed on disk."""
        if self._config_dir is None:
            return
        for f in self._config_dir.glob("*.yaml"):
            mtime = f.stat().st_mtime
            if f.stem not in self._file_mtimes or self._file_mtimes[f.stem] < mtime:
                self._load_file(f)

    # ─── Generic getter ──────────────────────────────────────────────────

    def get(self, config_name: str, *keys, default=None) -> Any:
        """Nested lookup.  config.get('settings', 'scoring', 'weights')"""
        if not self._configs:
            self.load()

        cfg = self._configs.get(config_name)
        if cfg is None:
            return default
        for k in keys:
            if isinstance(cfg, dict):
                cfg = cfg.get(k)
                if cfg is None:
                    return default
            else:
                return default
        return cfg

    # ─── Typed accessors ─────────────────────────────────────────────────

    def get_benchmarks(self, sector: str = None) -> dict:
        sectors = self.get("benchmarks", "sectors", default={})
        if sector:
            return sectors.get(sector, {})
        return sectors

    def get_benchmark_classifications(self) -> tuple[set, set]:
        worse = set(self.get("benchmarks", "higher_is_worse", default=[]))
        better = set(self.get("benchmarks", "higher_is_better", default=[]))
        return worse, better

    def get_validation_tolerances(self) -> dict:
        return self.get("settings", "validation", default={})

    def get_scoring_weights(self) -> dict:
        return self.get("settings", "scoring", "weights", default={
            "financial": 0.40, "conduct": 0.25, "governance": 0.20, "market": 0.15,
        })

    def get_grade_thresholds(self) -> dict:
        return self.get("settings", "scoring", "grade_thresholds", default={
            "A": 80, "B": 65, "C": 50, "D": 35,
        })

    def get_rules(self) -> dict:
        return self.get("rules", default={})

    def get_llm_config(self) -> dict:
        return self.get("llm_providers", default={})

    def get_active_llm_provider(self) -> dict:
        name = self.get("llm_providers", "active_provider", default=None)
        if not name:
            raise RuntimeError(
                "No LLM provider configured. Set active_provider in config/llm_providers.yaml"
            )
        if name == "mock":
            return {"type": "mock", "name": "Mock (Deterministic)"}
        provider = self.get("llm_providers", "providers", name, default=None)
        if not provider:
            raise RuntimeError(f"LLM provider '{name}' not found in config/llm_providers.yaml")
        return provider

    def get_narrative_settings(self) -> dict:
        settings = self.get("llm_providers", "narrative", default=None)
        if not settings or settings.get("mode") != "llm":
            raise RuntimeError(
                "Narrative mode must be 'llm' in config/llm_providers.yaml. "
                "Template fallback has been removed."
            )
        return settings

    # ─── Write-back ──────────────────────────────────────────────────────

    def update_config(self, config_name: str, data: dict):
        """Persist config to YAML and update in-memory cache."""
        self._configs[config_name] = data
        if self._config_dir:
            path = self._config_dir / f"{config_name}.yaml"
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
            self._file_mtimes[config_name] = path.stat().st_mtime

    def all_configs(self) -> dict:
        if not self._configs:
            self.load()
        return dict(self._configs)

    @classmethod
    def reset(cls):
        """Reset singleton (for testing)."""
        cls._instance = None


# Module-level singleton
config = ConfigManager()
