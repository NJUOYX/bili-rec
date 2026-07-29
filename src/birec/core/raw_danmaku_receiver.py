"""RawDanmakuReceiver: bounded async queue for raw (unprocessed) danmaku data."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Any

from ..bili.danmaku_client import DanmakuClientListener
from ..bili.typing import Danmaku as RawDanmaku
from ..event.event_emitter import EventEmitter, EventListener

__all__ = ("RawDanmakuReceiver", "RawDanmakuReceiverListener")

logger = logging.getLogger(__name__)

_MAX_QUEUE_SIZE = 2000


class RawDanmakuReceiverListener(EventListener):
    """Listener interface for RawDanmakuReceiver events."""


class RawDanmakuReceiver(
    EventEmitter[RawDanmakuReceiverListener], DanmakuClientListener
):
    """Bounded async queue for raw danmaku data (JSON dicts from WebSocket).

    Doubles as a :class:`DanmakuClientListener`, queueing every command
    verbatim (no filtering) so the JSONL dump is a faithful record of the
    broadcast. When the queue is full, oldest messages are dropped.
    """

    def __init__(self) -> None:
        super().__init__()
        self._queue: deque[dict[str, Any]] = deque(maxlen=_MAX_QUEUE_SIZE)
        self._event = asyncio.Event()
        self._dropped_count: int = 0
        self._stopped: bool = False

    @property
    def queue_size(self) -> int:
        return len(self._queue)

    @property
    def dropped_count(self) -> int:
        return self._dropped_count

    def push(self, data: dict[str, Any]) -> None:
        """Push a raw danmaku dict into the queue."""
        if len(self._queue) >= _MAX_QUEUE_SIZE:
            self._dropped_count += 1
        self._queue.append(data)
        self._event.set()

    def on_danmaku(self, danmaku: RawDanmaku) -> None:
        """Queue the command as received."""
        self.push(danmaku)

    async def get(self, timeout: float | None = None) -> dict[str, Any] | None:
        """Get the next raw danmaku dict.

        Returns None if timeout expires or the receiver is stopped.
        """
        while not self._stopped:
            if self._queue:
                return self._queue.popleft()
            self._event.clear()
            try:
                await asyncio.wait_for(self._event.wait(), timeout=timeout)
            except TimeoutError:
                return None
        return None

    def get_nowait(self) -> dict[str, Any] | None:
        """Get the next raw dict without waiting, or None if empty."""
        if self._queue:
            return self._queue.popleft()
        return None

    def drain(self) -> list[dict[str, Any]]:
        """Drain all raw dicts from the queue."""
        data = list(self._queue)
        self._queue.clear()
        return data

    def clear(self) -> None:
        """Clear the queue."""
        self._queue.clear()
        self._event.clear()
