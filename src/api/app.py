"""FastAPI application factory."""

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from src.application.container import ServiceContainer, build_container
from src.application.errors import ApplicationError
from src.core.ui_paths import UI_ROOT


def _correlation() -> str:
    return "los-" + uuid.uuid4().hex[:12]


def create_app(container: ServiceContainer | None = None) -> FastAPI:
    from src.api.routers import ALL_ROUTERS

    app = FastAPI(title="CAM Intelligence Platform", version="1.0.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.state.container = container or build_container()

    @app.exception_handler(ApplicationError)
    async def _application_error(_: Request, exc: ApplicationError):
        cid = _correlation()
        return JSONResponse(status_code=exc.status_code,
                            content={"detail": str(exc), "error": exc.to_dict(cid)})

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception):
        # Reserve 500 for genuinely unexpected server errors: no stack trace, no paths,
        # no internal names — only a stable code and a correlation id for the logs.
        cid = _correlation()
        logging.getLogger("los.api").exception("unexpected error %s: %s", cid, exc)
        return JSONResponse(status_code=500,
                            content={"detail": "An unexpected server error occurred. "
                                               "Raise the reference id with your bank's support desk.",
                                     "error": {"code": "INTERNAL",
                                               "message": "An unexpected server error occurred.",
                                               "corrective_action": "Retry the action; if it repeats, "
                                                                    "contact the support desk with the reference id.",
                                               "correlation_id": cid}})

    app.mount("/static", StaticFiles(directory=str(UI_ROOT / "static")), name="static")
    for router in ALL_ROUTERS:
        app.include_router(router)
    return app
