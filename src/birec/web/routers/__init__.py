"""Web API routers."""

from __future__ import annotations

from .tasks import router as tasks_router
from .websocket import ws_router

__all__ = ("tasks_router", "ws_router")
