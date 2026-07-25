"""DanmakuDumper: writes processed danmaku to Bilibili XML format."""

from __future__ import annotations

import io
import logging
import os
import time

from ..event.event_emitter import EventEmitter, EventListener
from ..utils.mixins import AsyncStoppableMixin
from .danmaku_receiver import DanmakuReceiver
from .models import Danmaku, DanmakuMessage, Gift, GuardBuy, SuperChat

__all__ = ("DanmakuDumper", "DanmakuDumperListener")

logger = logging.getLogger(__name__)


class DanmakuDumperListener(EventListener):
    """Listener interface for DanmakuDumper events."""


class DanmakuDumper(AsyncStoppableMixin, EventEmitter[DanmakuDumperListener]):
    """Writes processed danmaku messages to Bilibili XML format.

    The XML format follows Bilibili's danmaku XML specification:
    - <i> root element with <d> for danmaku and <sc> for super chat
    - Each <d> has attributes: p (parameters), text content
    - Parameters format: time,mode,font_size,color,timestamp,pool,user_id,rowID
    """

    def __init__(
        self,
        receiver: DanmakuReceiver,
        output_path: str,
        *,
        flush_interval: float = 5.0,
    ) -> None:
        super().__init__()
        self._receiver = receiver
        self._output_path = output_path
        self._flush_interval = flush_interval
        self._messages: list[DanmakuMessage] = []
        self._start_time: float = 0.0
        self._written_count: int = 0

    @property
    def output_path(self) -> str:
        return self._output_path

    @property
    def written_count(self) -> int:
        return self._written_count

    async def _do_start(self) -> None:
        """Start the dumper loop."""
        self._start_time = time.time()
        self._write_header()
        await self._dump_loop()

    async def _do_stop(self) -> None:
        """Stop the dumper and finalize."""
        self.finalize()

    async def _dump_loop(self) -> None:
        """Main loop: consume messages from receiver and write to XML."""
        while not self._stopped:
            msg = await self._receiver.get(timeout=self._flush_interval)
            if msg is not None:
                self._messages.append(msg)
                self._written_count += 1

            if self._messages:
                self._flush_messages()

    def _write_header(self) -> None:
        """Write XML file header."""
        dir_path = os.path.dirname(self._output_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        with open(self._output_path, "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n')
            f.write("<i>\n")

    def _flush_messages(self) -> None:
        """Flush accumulated messages to the XML file."""
        if not self._messages:
            return
        with open(self._output_path, "a", encoding="utf-8") as f:
            for msg in self._messages:
                self._write_message(f, msg)
        self._messages.clear()

    def _write_message(self, f: io.TextIOBase, msg: DanmakuMessage) -> None:
        """Write a single message to the file."""
        if msg.type == "danmaku":
            self._write_danmaku(f, msg.data)  # type: ignore[arg-type]
        elif msg.type == "super_chat":
            self._write_super_chat(f, msg.data)  # type: ignore[arg-type]
        elif msg.type == "gift":
            self._write_gift(f, msg.data)  # type: ignore[arg-type]
        elif msg.type == "guard_buy":
            self._write_guard_buy(f, msg.data)  # type: ignore[arg-type]

    def _write_danmaku(self, f: io.TextIOBase, d: Danmaku) -> None:
        """Write a danmaku element."""
        elapsed = d.timestamp - self._start_time if self._start_time else 0.0
        params = (
            f"{elapsed:.5f},{d.dm_type},{d.font_size},{d.color},"
            f"{int(d.timestamp)},0,{d.uid},0"
        )
        content = _escape_xml(d.content)
        f.write(f'  <d p="{params}">{content}</d>\n')

    def _write_super_chat(self, f: io.TextIOBase, sc: SuperChat) -> None:
        """Write a super chat element."""
        elapsed = sc.timestamp - self._start_time if self._start_time else 0.0
        content = _escape_xml(sc.content)
        f.write(  # noqa: E501
            f'  <sc ts="{elapsed:.5f}" uid="{sc.uid}"'
            f' user="{_escape_xml(sc.uname)}" price="{sc.price}"'
            f' id="{sc.message_id}">{content}</sc>\n'
        )

    def _write_gift(self, f: io.TextIOBase, g: Gift) -> None:
        """Write a gift element."""
        elapsed = g.timestamp - self._start_time if self._start_time else 0.0
        f.write(  # noqa: E501
            f'  <gift ts="{elapsed:.5f}" uid="{g.uid}"'
            f' user="{_escape_xml(g.uname)}" giftname="{_escape_xml(g.gift_name)}"'
            f' giftid="{g.gift_id}" num="{g.num}"'
            f' price="{g.price}" action="{_escape_xml(g.action)}"/>\n'
        )

    def _write_guard_buy(self, f: io.TextIOBase, gb: GuardBuy) -> None:
        """Write a guard buy element."""
        elapsed = gb.timestamp - self._start_time if self._start_time else 0.0
        f.write(  # noqa: E501
            f'  <guard ts="{elapsed:.5f}" uid="{gb.uid}"'
            f' user="{_escape_xml(gb.uname)}" level="{gb.guard_level}"'
            f' num="{gb.num}" price="{gb.price}"/>\n'
        )

    def finalize(self) -> None:
        """Write closing tag and finalize the XML file."""
        # Flush remaining messages
        if self._messages:
            self._flush_messages()
        with open(self._output_path, "a", encoding="utf-8") as f:
            f.write("</i>\n")


def _escape_xml(text: str) -> str:
    """Escape XML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
