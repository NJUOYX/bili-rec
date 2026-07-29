"""DanmakuReceiver: bounded async queue for processed danmaku messages."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque

from ..bili.danmaku_client import DanmakuClientListener
from ..bili.typing import Danmaku as RawDanmaku
from ..event.event_emitter import EventEmitter, EventListener
from .models import DanmakuMessage

__all__ = ("DanmakuReceiver", "DanmakuReceiverListener")

logger = logging.getLogger(__name__)

_MAX_QUEUE_SIZE = 2000


class DanmakuReceiverListener(EventListener):
    """Listener interface for DanmakuReceiver events."""


class DanmakuReceiver(EventEmitter[DanmakuReceiverListener], DanmakuClientListener):
    """Bounded async queue for processed danmaku messages.

    Doubles as a :class:`DanmakuClientListener`: raw broadcast commands are
    parsed into typed messages here (§5.4) and queued for the dumper. The queue
    decouples the WebSocket callback from file I/O, and when it is full the
    oldest messages are dropped (FIFO eviction) so that a danmaku flood can
    never stall recording.
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

    # ── DanmakuClientListener ────────────────────────────────────────────

    def on_danmaku(self, danmaku: RawDanmaku) -> None:
        """Parse a raw broadcast command and queue it if it is recordable."""
        msg = self._parse(danmaku)
        if msg is not None:
            self.push(msg)

    def _parse(self, danmaku: RawDanmaku) -> DanmakuMessage | None:
        """Convert a raw command into a typed message, or None to ignore it.

        The live broadcast carries dozens of command types we do not record;
        anything unrecognised (or malformed, since the payload shape is not
        contractual) is dropped rather than raised, so one odd message cannot
        break the danmaku stream.
        """
        cmd = str(danmaku.get("cmd", ""))
        # Some rooms suffix the command, e.g. "DANMU_MSG:4:0:2:2:2:0".
        if cmd.startswith("DANMU_MSG"):
            parser = self._parse_danmaku
        elif cmd == "SEND_GIFT":
            parser = self._parse_gift
        elif cmd == "GUARD_BUY":
            parser = self._parse_guard_buy
        elif cmd == "SUPER_CHAT_MESSAGE":
            parser = self._parse_super_chat
        else:
            return None
        try:
            return parser(danmaku)
        except (KeyError, IndexError, TypeError, ValueError):
            logger.debug("Malformed %s payload, dropped", cmd)
            return None

    @staticmethod
    def _parse_danmaku(danmaku: RawDanmaku) -> DanmakuMessage:
        """``info`` is a positional array: [meta, content, user, ...]."""
        info = danmaku["info"]
        meta, content, user = info[0], info[1], info[2]
        return DanmakuMessage.danmaku(
            ts=float(meta[4]) / 1000,  # the wire format is milliseconds
            content=str(content),
            uid=int(user[0]),
            uname=str(user[1]),
            dm_type=int(meta[1]),
            font_size=int(meta[2]),
            color=int(meta[3]),
        )

    @staticmethod
    def _parse_gift(danmaku: RawDanmaku) -> DanmakuMessage:
        data = danmaku["data"]
        return DanmakuMessage.gift(
            ts=float(data.get("timestamp") or time.time()),
            uid=int(data["uid"]),
            uname=str(data["uname"]),
            gift_name=str(data["giftName"]),
            gift_id=int(data.get("giftId", 0)),
            num=int(data.get("num", 1)),
            price=int(data.get("price", 0)),
            action=str(data.get("action", "投喂")),
        )

    @staticmethod
    def _parse_guard_buy(danmaku: RawDanmaku) -> DanmakuMessage:
        data = danmaku["data"]
        return DanmakuMessage.guard_buy(
            ts=float(data.get("start_time") or time.time()),
            uid=int(data["uid"]),
            uname=str(data["username"]),
            guard_level=int(data["guard_level"]),
            num=int(data.get("num", 1)),
            price=int(data.get("price", 0)),
        )

    @staticmethod
    def _parse_super_chat(danmaku: RawDanmaku) -> DanmakuMessage:
        data = danmaku["data"]
        return DanmakuMessage.super_chat(
            ts=float(data.get("start_time") or time.time()),
            uid=int(data["uid"]),
            uname=str(data.get("user_info", {}).get("uname", "")),
            price=int(data["price"]),
            content=str(data["message"]),
            message_id=int(data.get("id", 0)),
        )

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
