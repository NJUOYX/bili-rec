"""LiveMonitor: event-driven live status monitoring with debounce and polling."""

from __future__ import annotations

import asyncio
import random
from typing import Any

from loguru import logger

from ..event.event_emitter import EventEmitter, EventListener
from ..utils.mixins import SwitchableMixin
from .live import Live
from .models import LiveStatus

__all__ = ("LiveMonitor", "LiveMonitorListener")

# Polling constants
_STREAM_POLL_INTERVAL = 1  # seconds
_STREAM_POLL_TIMEOUT = 30 * 60  # 30 minutes
_PERIODIC_CHECK_INTERVAL = 600  # ~600s
_PERIODIC_CHECK_JITTER = 60  # ±60s


class LiveMonitorListener(EventListener):
    """Interface for LiveMonitor event listeners."""

    def on_live_began(self, live: Live) -> None: ...
    def on_live_ended(self, live: Live) -> None: ...
    def on_live_stream_available(self, live: Live) -> None: ...
    def on_live_stream_reset(self, live: Live) -> None: ...
    def on_room_changed(self, live: Live) -> None: ...


class LiveMonitor(SwitchableMixin, EventEmitter[LiveMonitorListener]):
    """Monitors live room status via danmaku commands and periodic polling.

    Emits events:
    - live_began: First LIVE command received.
    - live_ended: PREPARING command received.
    - live_stream_available: Stream URL confirmed reachable after live began.
    - live_stream_reset: Consecutive LIVE commands (stream restarted).
    - room_changed: ROOM_CHANGE command received.
    """

    def __init__(self, live: Live) -> None:
        SwitchableMixin.__init__(self)
        EventEmitter.__init__(self)
        self._live = live
        self._logger = logger.bind(room_id=live.room_id)

        self._is_living = False
        self._stream_available = False

        self._stream_poll_task: asyncio.Task[None] | None = None
        self._periodic_check_task: asyncio.Task[None] | None = None

    @property
    def is_living(self) -> bool:
        return self._is_living

    @property
    def stream_available(self) -> bool:
        return self._stream_available

    # --- SwitchableMixin ---

    def _do_enable(self) -> None:
        self._periodic_check_task = asyncio.ensure_future(self._periodic_check_loop())
        self._logger.debug("LiveMonitor enabled")

    def _do_disable(self) -> None:
        self._cancel_tasks()
        self._logger.debug("LiveMonitor disabled")

    def _cancel_tasks(self) -> None:
        if self._stream_poll_task is not None:
            self._stream_poll_task.cancel()
            self._stream_poll_task = None
        if self._periodic_check_task is not None:
            self._periodic_check_task.cancel()
            self._periodic_check_task = None

    # --- Danmaku Command Handling ---

    async def handle_command(
        self, command: str, data: dict[str, Any] | None = None
    ) -> None:
        """Process a danmaku command (LIVE/PREPARING/ROUND/ROOM_CHANGE)."""
        if not self.enabled:
            return

        match command:
            case "LIVE":
                await self._on_live_command()
            case "PREPARING":
                await self._on_preparing_command()
            case "ROUND":
                await self._on_preparing_command()
            case "ROOM_CHANGE":
                await self._on_room_change_command()

    async def _on_live_command(self) -> None:
        """Handle LIVE command with debounce."""
        if self._is_living:
            # Consecutive LIVE → stream reset
            self._logger.info("Live stream reset (consecutive LIVE)")
            self._stream_available = False
            await self._emit("live_stream_reset", self._live)
            self._start_stream_poll()
        else:
            # First LIVE → live began
            self._is_living = True
            self._stream_available = False
            self._logger.info("Live began")
            await self._emit("live_began", self._live)
            self._start_stream_poll()

    async def _on_preparing_command(self) -> None:
        """Handle PREPARING/ROUND command → live ended."""
        if self._is_living:
            self._is_living = False
            self._stream_available = False
            self._cancel_stream_poll()
            self._logger.info("Live ended")
            await self._emit("live_ended", self._live)

    async def _on_room_change_command(self) -> None:
        """Handle ROOM_CHANGE command."""
        self._logger.info("Room changed")
        await self._emit("room_changed", self._live)

    # --- Stream Availability Polling ---

    def _start_stream_poll(self) -> None:
        """Start polling for stream availability."""
        self._cancel_stream_poll()
        self._stream_poll_task = asyncio.ensure_future(self._stream_poll_loop())

    def _cancel_stream_poll(self) -> None:
        if self._stream_poll_task is not None:
            self._stream_poll_task.cancel()
            self._stream_poll_task = None

    async def _stream_poll_loop(self) -> None:
        """Poll stream URL every second until available or timeout (30min)."""
        elapsed = 0.0
        try:
            while elapsed < _STREAM_POLL_TIMEOUT and self._is_living:
                try:
                    url = await self._live.get_stream_url()
                    if url and await self._live.test_connectivity(url):
                        self._stream_available = True
                        self._logger.info("Live stream available")
                        await self._emit("live_stream_available", self._live)
                        return
                except Exception:
                    pass
                await asyncio.sleep(_STREAM_POLL_INTERVAL)
                elapsed += _STREAM_POLL_INTERVAL
        except asyncio.CancelledError:
            pass

    # --- Periodic Status Check (Fallback) ---

    async def _periodic_check_loop(self) -> None:
        """Reconcile status once, then re-check periodically (~600s ± 60s).

        The upfront check matters for rooms that are *already* live when the
        monitor is enabled (a task added mid-stream, or a restart): the danmaku
        server only pushes future transitions, so without it the room would look
        offline until the first interval elapses.
        """
        try:
            await self._check_status()
            while self.enabled:
                jitter = random.uniform(-_PERIODIC_CHECK_JITTER, _PERIODIC_CHECK_JITTER)
                await asyncio.sleep(_PERIODIC_CHECK_INTERVAL + jitter)
                if not self.enabled:
                    break
                await self._check_status()
        except asyncio.CancelledError:
            pass

    async def _check_status(self) -> None:
        """Re-check live status and reconcile state."""
        try:
            status = await self._live.get_live_status()
        except Exception:
            self._logger.debug("Periodic status check failed")
            return

        if status == LiveStatus.LIVE and not self._is_living:
            # Missed the LIVE event
            self._is_living = True
            self._stream_available = False
            self._logger.info("Periodic check: live began (recovered)")
            await self._emit("live_began", self._live)
            self._start_stream_poll()
        elif status != LiveStatus.LIVE and self._is_living:
            # Missed the PREPARING event
            self._is_living = False
            self._stream_available = False
            self._cancel_stream_poll()
            self._logger.info("Periodic check: live ended (recovered)")
            await self._emit("live_ended", self._live)

    # --- Reconnection State Repair ---

    async def repair_state_on_reconnect(self) -> None:
        """Re-check status after danmaku client reconnects and re-emit events."""
        self._logger.debug("Repairing state on reconnect")
        try:
            status = await self._live.get_live_status()
        except Exception:
            return

        if status == LiveStatus.LIVE:
            if not self._is_living:
                self._is_living = True
                self._stream_available = False
                await self._emit("live_began", self._live)
            if not self._stream_available:
                self._start_stream_poll()
        else:
            if self._is_living:
                self._is_living = False
                self._stream_available = False
                self._cancel_stream_poll()
                await self._emit("live_ended", self._live)
