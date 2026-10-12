"""
CAM Intelligence Platform — Server Launcher
Run with:  python run.py
"""

import sys
import os
from pathlib import Path

# Ensure project root on path
root = Path(__file__).parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))


def main():
    import uvicorn
    from src.core.config_manager import config
    from src.core.env_loader import load_local_env

    load_local_env()
    config.load()
    host = config.get("settings", "server", "host", default="0.0.0.0")
    port = config.get("settings", "server", "port", default=8000)
    reload = config.get("settings", "server", "reload", default=True)

    print(f"\n{'='*60}")
    print(f"  CAM Intelligence Platform  v1.0.0")
    print(f"  http://localhost:{port}")
    print(f"{'='*60}\n")

    uvicorn.run(
        "src.api.main:app",
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    main()
