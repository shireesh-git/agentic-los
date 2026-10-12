"""
Shared test setup.

Runtime paths and the config directory are read from environment variables at
import time, so they are redirected to a throwaway copy *before* any ``src``
module is imported. Tests never touch the developer's real config, SQLite
database, output folder or documents, never call a real LLM and never call
Probe42.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_TMP = Path(tempfile.mkdtemp(prefix="cam_tests_"))


def _prepare_config(target: Path) -> None:
    shutil.copytree(PROJECT_ROOT / "config", target)

    llm_path = target / "llm_providers.yaml"
    llm = yaml.safe_load(llm_path.read_text(encoding="utf-8"))
    llm["active_provider"] = "mock"
    llm_path.write_text(yaml.safe_dump(llm, sort_keys=False, allow_unicode=True), encoding="utf-8")

    apis_path = target / "external_apis.yaml"
    apis = yaml.safe_load(apis_path.read_text(encoding="utf-8"))
    apis.setdefault("probe42", {})["enabled"] = False
    apis_path.write_text(yaml.safe_dump(apis, sort_keys=False, allow_unicode=True), encoding="utf-8")


if (PROJECT_ROOT / "storage").exists():
    shutil.copytree(PROJECT_ROOT / "storage", _TMP / "storage",
                    ignore=shutil.ignore_patterns("cache"))
_prepare_config(_TMP / "config")

os.environ["CAM_CONFIG_DIR"] = str(_TMP / "config")
os.environ["CAM_STORAGE_ROOT"] = str(_TMP / "storage")
os.environ["CAM_RUNTIME_DB_ROOT"] = str(_TMP / "db")
os.environ["CAM_OUTPUT_ROOT"] = str(_TMP / "output")
os.environ["CAM_REFERENCE_ROOT"] = str(_TMP / "reference")

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest  # noqa: E402

from src.core.config_manager import config  # noqa: E402

config.load()


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture(scope="session")
def tmp_runtime_root() -> Path:
    return _TMP
