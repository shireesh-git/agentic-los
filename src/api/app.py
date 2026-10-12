"""FastAPI application factory."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from src.application.container import ServiceContainer, build_container
from src.application.errors import ApplicationError
from src.core.ui_paths import UI_ROOT


def create_app(container: ServiceContainer | None = None) -> FastAPI:
    from src.api.routers import ALL_ROUTERS

    app = FastAPI(title="CAM Intelligence Platform", version="1.0.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.state.container = container or build_container()

    @app.exception_handler(ApplicationError)
    async def _application_error(_: Request, exc: ApplicationError):
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})

    app.mount("/static", StaticFiles(directory=str(UI_ROOT / "static")), name="static")
    for router in ALL_ROUTERS:
        app.include_router(router)
    return app
