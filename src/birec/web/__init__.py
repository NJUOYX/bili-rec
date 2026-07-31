"""Web layer: FastAPI app, routes, middleware, exception handling."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__
from .middleware import BaseHrefMiddleware, RouteRedirectMiddleware
from .models import ResponseMessage
from .routers import app_router, settings_router, tasks_router, ws_router

__all__ = (
    "BaseHrefMiddleware",
    "ResponseMessage",
    "RouteRedirectMiddleware",
    "create_app",
)


def create_app(
    *,
    static_dir: Path | None = None,
    base_href: str | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        static_dir: Directory of the built frontend (``index.html`` + assets).
            When ``None`` it is resolved from ``BIREC_STATIC_DIR`` env or the
            bundled ``web/static`` directory; if no ``index.html`` is present
            the app runs API-only (no static hosting).
        base_href: Sub-path for reverse-proxy deploys (e.g. ``/birec``). When
            ``None`` it is resolved from ``BIREC_BASE_HREF`` env. A non-root
            value enables ``<base href>`` injection into served HTML.

    Returns:
        Configured FastAPI app with routes, middleware, handlers, and — when a
        frontend build is available — SPA static hosting with route fallback.
    """
    app = FastAPI(
        title="bili-rec",
        description="Bilibili live-stream recorder API",
        version=__version__,
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

    # Mount the built frontend (SPA) when available (§12).
    _mount_frontend(app, static_dir=static_dir, base_href=base_href)

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


def _resolve_static_dir(static_dir: Path | None) -> Path:
    """Resolve the frontend static directory (explicit → env → bundled)."""
    if static_dir is not None:
        return static_dir
    env_dir = os.environ.get("BIREC_STATIC_DIR")
    if env_dir:
        return Path(env_dir)
    # Bundled default: ``birec/web/static`` (populated by the build/Docker stage).
    return Path(__file__).parent / "static"


def _mount_frontend(
    app: FastAPI,
    *,
    static_dir: Path | None,
    base_href: str | None,
) -> None:
    """Serve the built frontend with SPA route fallback and ``<base href>``.

    No-op when no ``index.html`` is found, keeping the app API-only for dev and
    tests that do not ship a frontend build.
    """
    directory = _resolve_static_dir(static_dir)
    if not (directory / "index.html").is_file():
        return

    href = base_href if base_href is not None else os.environ.get("BIREC_BASE_HREF")

    # SPA fallback: non-API/-WS, extension-less GET that 404s → index.html
    # served in place, so deep links survive refresh and bookmarks.
    app.add_middleware(RouteRedirectMiddleware, index_file=directory / "index.html")
    # ``<base href>`` is always injected (outermost, so it rewrites every HTML
    # response including the fallback index). The build emits *relative* asset
    # URLs, which would resolve against the requested directory and 404 on a
    # nested deep link such as ``/tasks/new``; an explicit base anchors them to
    # the deployment root, defaulting to ``/`` when no sub-path is configured.
    app.add_middleware(BaseHrefMiddleware, base_href=href or "/")

    # Mount last so API/WS routers registered earlier take precedence.
    app.mount("/", StaticFiles(directory=str(directory), html=True), name="frontend")
