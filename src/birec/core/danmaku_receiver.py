"""DanmakuReceiver: bounded async queue for processed danmaku messages."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any

from ..bili.danmaku_client import DanmakuClientListener
from ..bili.typing import Danmaku as RawDanmaku
from ..event.event_emitter import EventEmitter, EventListener
from .models import DanmakuMessage

__all__ = ("DanmakuReceiver", "DanmakuReceiverListener")

logger = logging.getLogger(__name__)

_MAX_QUEUE_SIZE = 2000

# Room-state transitions the broadcast pushes (§3.3). Nothing records them to
# disk, but the LiveMonitor needs them: they are the instant channel that
# flips the state the moment a broadcast begins or ends, while the periodic
# poll only catches up a whole check interval later (#27).
_LIVE_STATUS_COMMANDS = frozenset({"LIVE", "PREPARING", "ROUND", "ROOM_CHANGE"})

# ``LiveMonitor.handle_command`` is the intended target.
LiveCommandHandler = Callable[[str, dict[str, Any] | None], Awaitable[None]]


class DanmakuReceiverListener(EventListener):
    """Listener interface for DanmakuReceiver events."""


# ``LiveMonitor.repair_state_on_reconnect`` is the intended target.
ReconnectHandler = Callable[[], Awaitable[None]]


class DanmakuReceiver(EventEmitter[DanmakuReceiverListener], DanmakuClientListener):
    """Bounded async queue for processed danmaku messages.

    Doubles as a :class:`DanmakuClientListener`: raw broadcast commands are
    parsed into typed messages here (§5.4) and queued for the dumper. The queue
    decouples the WebSocket callback from file I/O, and when it is full the
    oldest messages are dropped (FIFO eviction) so that a danmaku flood can
    never stall recording.

    The room-state commands (LIVE/PREPARING/ROUND/ROOM_CHANGE) are not
    recordable, so they never enter the queue; when a ``live_command_handler``
    is installed they are forwarded to it instead — that is the wire that lets
    the LiveMonitor flip the moment a broadcast begins or ends (#27).

    When the danmaku client (re)connects successfully, ``on_danmaku_connected``
    schedules the ``on_reconnect`` handler as a task. This is the wire that
    lets the LiveMonitor repair stale state the moment the WebSocket comes
    back, rather than waiting for the next periodic poll (#28).
    """

    def __init__(
        self,
        *,
        live_command_handler: LiveCommandHandler | None = None,
        on_reconnect: ReconnectHandler | None = None,
    ) -> None:
        super().__init__()
        self._queue: deque[DanmakuMessage] = deque(maxlen=_MAX_QUEUE_SIZE)
        self._event = asyncio.Event()
        self._dropped_count: int = 0
        self._stopped: bool = False
        self._live_command_handler = live_command_handler
        self._on_reconnect = on_reconnect

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
        cmd = str(danmaku.get("cmd", ""))
        if cmd in _LIVE_STATUS_COMMANDS:
            self._forward_live_command(cmd, danmaku)
            return
        msg = self._parse(danmaku)
        if msg is not None:
            self.push(msg)

    def on_danmaku_connected(self) -> None:
        """Schedule the reconnect handler after a successful (re)connection.

        ``on_danmaku_connected`` runs inside the WebSocket handshake and cannot
        await, so the async handler is scheduled as a task. The handler itself
        is best-effort: any exception it raises is logged and swallowed, so a
        failed status check cannot break the danmaku pipeline (#28).
        """
        handler = self._on_reconnect
        if handler is None:
            return
        asyncio.ensure_future(self._run_reconnect_handler(handler))

    @staticmethod
    async def _run_reconnect_handler(handler: ReconnectHandler) -> None:
        """Run the reconnect handler so its failure cannot break the pipeline."""
        try:
            await handler()
        except Exception:
            logger.exception("Reconnect state repair failed")

    def on_danmaku_disconnected(self) -> None:
        """No-op: disconnection is handled by the reconnect path on recovery."""

    def _forward_live_command(self, cmd: str, danmaku: RawDanmaku) -> None:
        """Hand a room-state command to the live monitor's handler.

        ``on_danmaku`` runs inside the WebSocket receive loop and cannot await,
        so the async handler is scheduled as a task. Scheduled tasks run FIFO,
        so the state machine still sees the commands in arrival order.
        """
        handler = self._live_command_handler
        if handler is None:
            return
        payload = danmaku.get("data")
        data = payload if isinstance(payload, dict) else None
        asyncio.ensure_future(self._run_live_command_handler(handler, cmd, data))

    @staticmethod
    async def _run_live_command_handler(
        handler: LiveCommandHandler, cmd: str, data: dict[str, Any] | None
    ) -> None:
        """Run the handler so its failure cannot break the danmaku pipeline."""
        try:
            await handler(cmd, data)
        except Exception:
            logger.exception("Forwarding live command %s failed", cmd)

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
