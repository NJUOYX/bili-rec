"""DanmakuReceiver: bounded async queue for processed danmaku messages."""

from __future__ import annotations

import asyncio
import logging
from collections import deque

from ..event.event_emitter import EventEmitter, EventListener
from .models import DanmakuMessage

__all__ = ("DanmakuReceiver", "DanmakuReceiverListener")

logger = logging.getLogger(__name__)

_MAX_QUEUE_SIZE = 2000


class DanmakuReceiverListener(EventListener):
    """Listener interface for DanmakuReceiver events."""


class DanmakuReceiver(EventEmitter[DanmakuReceiverListener]):
    """Bounded async queue for processed danmaku messages.

    When the queue is full, oldest messages are dropped (FIFO eviction).
    """

    def __init__(self) -> None:
        super().__init__()
        self._queue: deque[DanmakuMessage] = deque(maxlen=_MAX_QUEUE_SIZE)
        self._event = asyncio.Event()
        self._dropped_count: int = 0
        self._stopped: bool = False

    @property
    def queue_size(self) -> int:
        return len(self._queue)

    @property
    def dropped_count(self) -> int:
        return self._dropped_count

    def push(self, msg: DanmakuMessage) -> None:
        """Push a danmaku message into the queue.

        If the queue is full, the oldest message is dropped.
        """
        if len(self._queue) >= _MAX_QUEUE_SIZE:
            self._dropped_count += 1
        self._queue.append(msg)
        self._event.set()

    async def get(self, timeout: float | None = None) -> DanmakuMessage | None:
        """Get the next danmaku message from the queue.

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

    def get_nowait(self) -> DanmakuMessage | None:
        """Get the next message without waiting, or None if empty."""
        if self._queue:
            return self._queue.popleft()
        return None

    def drain(self) -> list[DanmakuMessage]:
        """Drain all messages from the queue."""
        messages = list(self._queue)
        self._queue.clear()
        return messages

    def clear(self) -> None:
        """Clear the queue."""
        self._queue.clear()
        self._event.clear()
