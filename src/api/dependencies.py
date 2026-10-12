"""FastAPI dependency providers."""

from fastapi import Request

from src.application.container import ServiceContainer


def get_container(request: Request) -> ServiceContainer:
    return request.app.state.container
