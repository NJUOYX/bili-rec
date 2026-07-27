"""WebSocket endpoints for real-time event/exception streaming (§7.4).

- ``/ws/v1/events``: subscribes to EventCenter and forwards events.
- ``/ws/v1/exceptions``: subscribes to ExceptionCenter and forwards exceptions.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from reactivex.abc import DisposableBase

from ...event import EventCenter
from ...exception import ExceptionCenter, format_exception

__all__ = ("ws_router",)

ws_router = APIRouter(tags=["websocket"])


@ws_router.websocket("/ws/v1/events")
async def ws_events(websocket: WebSocket) -> None:
    """Stream application events to the connected WebSocket client."""
    await websocket.accept()
    event_center = EventCenter.get_instance()
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    def on_event(event: Any) -> None:
        queue.put_nowait(event.model_dump(mode="json"))

    subscription: DisposableBase = event_center.events.subscribe(on_event)

    try:
        while True:
            # Forward events from queue to WebSocket
            try:
                data = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_json(data)
            except TimeoutError:
                # Send ping to keep connection alive
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        subscription.dispose()


@ws_router.websocket("/ws/v1/exceptions")
async def ws_exceptions(websocket: WebSocket) -> None:
    """Stream application exceptions to the connected WebSocket client."""
    await websocket.accept()
    exception_center = ExceptionCenter.get_instance()
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    def on_exception(exc: BaseException) -> None:
        queue.put_nowait(
            {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": format_exception(exc),
            }
        )

    subscription: DisposableBase = exception_center.exceptions.subscribe(on_exception)

    try:
        while True:
            try:
                data = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_json(data)
            except TimeoutError:
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        subscription.dispose()
