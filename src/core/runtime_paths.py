from __future__ import annotations

import os
from pathlib import Path


def _env_path(name: str, default: Path) -> Path:
    raw = os.getenv(name, "").strip()
    return Path(raw).expanduser() if raw else default


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STORAGE_ROOT = _env_path("CAM_STORAGE_ROOT", PROJECT_ROOT / "storage")
DOCUMENTS_ROOT = STORAGE_ROOT / "documents"
CACHE_ROOT = STORAGE_ROOT / "cache"
OUTPUT_ROOT = _env_path("CAM_OUTPUT_ROOT", PROJECT_ROOT / "output")
RUNTIME_DB_ROOT = _env_path("CAM_RUNTIME_DB_ROOT", PROJECT_ROOT / "runtime-db")
RUNTIME_DB_PATH = RUNTIME_DB_ROOT / "cam_platform.sqlite3"
REFERENCE_ROOT = _env_path("CAM_REFERENCE_ROOT", PROJECT_ROOT / "downloaded document")
REFERENCE_CAM_ROOT = REFERENCE_ROOT / "CAM"
SYNTHETIC_ROOT = _env_path("CAM_SYNTHETIC_ROOT", PROJECT_ROOT / "synthetic-assets")
ETB_OVERLAY_ROOT = SYNTHETIC_ROOT / "etb_overlays"


def ensure_runtime_dirs() -> None:
    for path in (
        STORAGE_ROOT,
        DOCUMENTS_ROOT,
        CACHE_ROOT,
        OUTPUT_ROOT,
        RUNTIME_DB_ROOT,
        SYNTHETIC_ROOT,
        ETB_OVERLAY_ROOT,
    ):
        path.mkdir(parents=True, exist_ok=True)


ensure_runtime_dirs()
