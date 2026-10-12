"""
CAM Intelligence Platform — ASGI entry point (``src.api.main:app``).

The application is assembled in ``src.api.app.create_app``; routes live in
``src.api.routers`` and business logic in ``src.application``.
"""

import logging
import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parents[2])
if _root not in sys.path:
    sys.path.insert(0, _root)

from src.core.env_loader import load_local_env  # noqa: E402

load_local_env()

from src.api.app import create_app  # noqa: E402
from src.core.config_manager import config  # noqa: E402
from src.core.engine_registry import register_default_engines  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
config.load()
register_default_engines()

app = create_app()
