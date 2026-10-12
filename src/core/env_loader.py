"""Minimal local .env loader used for developer runtime configuration."""

from __future__ import annotations

import os
from pathlib import Path


def load_local_env(*filenames: str) -> list[str]:
    root = Path(__file__).resolve().parents[2]
    loaded: list[str] = []
    names = filenames or (".env.local", ".env")

    for name in names:
        path = root / name
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key or key in os.environ:
                continue
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            os.environ[key] = value
        loaded.append(str(path))

    return loaded
