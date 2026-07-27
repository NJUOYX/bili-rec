"""Web API routers."""

from __future__ import annotations

from .app import app_router
from .settings import settings_router
from .tasks import router as tasks_router
from .websocket import ws_router

__all__ = ("app_router", "settings_router", "tasks_router", "ws_router")
