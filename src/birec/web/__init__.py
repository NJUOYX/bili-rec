"""Web layer: FastAPI app, routes, middleware, exception handling."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .middleware import BaseHrefMiddleware, RouteRedirectMiddleware
from .models import ResponseMessage
from .routers import app_router, settings_router, tasks_router, ws_router

__all__ = (
    "BaseHrefMiddleware",
    "ResponseMessage",
    "RouteRedirectMiddleware",
    "create_app",
)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI app with routes, middleware, and handlers.
    """
    app = FastAPI(
        title="bili-rec",
        description="Bilibili live-stream recorder API",
        version="0.1.0",
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register exception handlers
    _register_exception_handlers(app)

    # Register routes
    _register_routes(app)

    return app


def _register_exception_handlers(app: FastAPI) -> None:
    """Register custom exception handlers."""

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc: Any) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content=ResponseMessage(code=404, message="Not Found").to_dict(),
        )

    @app.exception_handler(403)
    async def forbidden_handler(request: Request, exc: Any) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content=ResponseMessage(code=403, message="Forbidden").to_dict(),
        )


def _register_routes(app: FastAPI) -> None:
    """Register API routes."""
    # Settings routes (§7.2)
    app.include_router(settings_router)

    # App/login/validation/update routes (§7.3)
    app.include_router(app_router)

    # Task routes (modular router)
    app.include_router(tasks_router)

    # WebSocket routes
    app.include_router(ws_router)
