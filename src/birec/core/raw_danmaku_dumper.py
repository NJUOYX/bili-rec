"""RawDanmakuDumper: writes raw danmaku data to JSONL format."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from typing import Any

from ..event.event_emitter import EventEmitter, EventListener
from ..utils.mixins import AsyncStoppableMixin
from .raw_danmaku_receiver import RawDanmakuReceiver

__all__ = ("RawDanmakuDumper", "RawDanmakuDumperListener")

logger = logging.getLogger(__name__)


class RawDanmakuDumperListener(EventListener):
    """Listener interface for RawDanmakuDumper events."""


class RawDanmakuDumper(AsyncStoppableMixin, EventEmitter[RawDanmakuDumperListener]):
    """Writes raw danmaku data to JSONL (JSON Lines) format.

    Each line is a JSON object with an added timestamp field.
    """

    def __init__(
        self,
        receiver: RawDanmakuReceiver,
        output_path: str,
        *,
        flush_interval: float = 5.0,
    ) -> None:
        super().__init__()
        self._receiver = receiver
        self._output_path = output_path
        self._flush_interval = flush_interval
        self._buffer: list[str] = []
        self._written_count: int = 0
        self._dump_task: asyncio.Task[None] | None = None

    @property
    def output_path(self) -> str:
        return self._output_path

    @property
    def written_count(self) -> int:
        return self._written_count

    async def _do_start(self) -> None:
        """Prepare the output file and consume the receiver in the background.

        Spawned rather than awaited for the same reason as the XML dumper:
        ``start()`` holds the lifecycle lock across ``_do_start``.
        """
        dir_path = os.path.dirname(self._output_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        self._dump_task = asyncio.create_task(self._dump_loop())

    async def _do_stop(self) -> None:
        """Stop the loop, then persist whatever is still queued."""
        if self._dump_task is not None:
            self._dump_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._dump_task
            self._dump_task = None
        for data in self._receiver.drain():
            self._buffer_data(data)
        self.finalize()

    async def _dump_loop(self) -> None:
        """Main loop: consume raw data from receiver and write to JSONL."""
        while not self._stopped:
            data = await self._receiver.get(timeout=self._flush_interval)
            if data is not None:
                self._buffer_data(data)

            if self._buffer:
                self._flush_buffer()

    def _buffer_data(self, data: dict[str, Any]) -> None:
        """Serialize and buffer a raw data dict."""
        line = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        self._buffer.append(line)
        self._written_count += 1

    def _flush_buffer(self) -> None:
        """Flush buffer to the JSONL file."""
        if not self._buffer:
            return
        with open(self._output_path, "a", encoding="utf-8") as f:
            for line in self._buffer:
                f.write(line + "\n")
        self._buffer.clear()

    def finalize(self) -> None:
        """Flush remaining data."""
        if self._buffer:
            self._flush_buffer()
