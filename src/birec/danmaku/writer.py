"""DanmakuWriter: write Bilibili-compatible danmaku XML files."""

from __future__ import annotations

import re
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from .models import (
    DanmakuDocument,
    DanmakuItem,
    DanmakuMetadata,
    GiftItem,
    GuardItem,
    SuperChatItem,
    ToastItem,
)

__all__ = ("DanmakuWriter",)

# Control characters to strip (except tab, newline, carriage return)
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _clean_text(text: str) -> str:
    """Remove control characters from text."""
    return _CONTROL_CHARS_RE.sub("", text)


class DanmakuWriter:
    """Write danmaku documents to Bilibili-compatible XML format.

    The XML structure follows Bilibili's danmaku specification:
    - Root element: <i>
    - Optional <metadata> with recording info
    - <d> for danmaku, <sc> for super chat, <gift>, <guard>, <toast>
    """

    def write(self, doc: DanmakuDocument, path: Path | str) -> None:
        """Write a DanmakuDocument to an XML file.

        Args:
            doc: The danmaku document to write.
            path: Output file path.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        lines: list[str] = []
        lines.append('<?xml version="1.0" encoding="utf-8"?>')
        lines.append("<i>")

        if doc.metadata is not None:
            lines.extend(self._write_metadata(doc.metadata))

        for item in doc.danmakus:
            lines.append(self._write_danmaku(item))

        for sc in doc.super_chats:
            lines.append(self._write_super_chat(sc))

        for gift in doc.gifts:
            lines.append(self._write_gift(gift))

        for guard in doc.guards:
            lines.append(self._write_guard(guard))

        for toast in doc.toasts:
            lines.append(self._write_toast(toast))

        lines.append("</i>")

        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_metadata(self, meta: DanmakuMetadata) -> list[str]:
        """Write metadata element."""
        lines = ["  <metadata>"]
        if meta.recorder:
            lines.append(f"    <recorder>{escape(meta.recorder)}</recorder>")
        if meta.room_id:
            lines.append(f"    <room_id>{meta.room_id}</room_id>")
        if meta.user_name:
            lines.append(f"    <user_name>{escape(meta.user_name)}</user_name>")
        if meta.title:
            lines.append(f"    <title>{escape(meta.title)}</title>")
        if meta.area:
            lines.append(f"    <area>{escape(meta.area)}</area>")
        if meta.parent_area:
            lines.append(f"    <parent_area>{escape(meta.parent_area)}</parent_area>")
        if meta.live_start_time:
            lines.append(
                f"    <live_start_time>{escape(meta.live_start_time)}</live_start_time>"
            )
        if meta.live_end_time:
            lines.append(
                f"    <live_end_time>{escape(meta.live_end_time)}</live_end_time>"
            )
        lines.append("  </metadata>")
        return lines

    def _write_danmaku(self, item: DanmakuItem) -> str:
        """Write a <d> element."""
        content = _clean_text(item.content)
        params = (
            f"{item.time:.5f},{item.mode},{item.font_size},{item.color},"
            f"{item.timestamp},{item.pool},{item.uid},{item.row_id}"
        )
        return f'  <d p="{params}">{escape(content)}</d>'

    def _write_super_chat(self, sc: SuperChatItem) -> str:
        """Write a <sc> element."""
        content = _clean_text(sc.content)
        user = _clean_text(sc.user)
        return (
            f'  <sc ts="{sc.time:.5f}" uid="{sc.uid}"'
            f' user={quoteattr(user)} price="{sc.price}"'
            f' id="{sc.sc_id}">{escape(content)}</sc>'
        )

    def _write_gift(self, gift: GiftItem) -> str:
        """Write a <gift> element."""
        user = _clean_text(gift.user)
        gift_name = _clean_text(gift.gift_name)
        action = _clean_text(gift.action)
        return (
            f'  <gift ts="{gift.time:.5f}" uid="{gift.uid}"'
            f" user={quoteattr(user)} giftname={quoteattr(gift_name)}"
            f' giftid="{gift.gift_id}" num="{gift.num}"'
            f' price="{gift.price}" coin_type="{gift.coin_type}"'
            f" action={quoteattr(action)}/>"
        )

    def _write_guard(self, guard: GuardItem) -> str:
        """Write a <guard> element."""
        user = _clean_text(guard.user)
        return (
            f'  <guard ts="{guard.time:.5f}" uid="{guard.uid}"'
            f' user={quoteattr(user)} level="{guard.level}"'
            f' num="{guard.num}" price="{guard.price}"/>'
        )

    def _write_toast(self, toast: ToastItem) -> str:
        """Write a <toast> element."""
        user = _clean_text(toast.user)
        message = _clean_text(toast.message)
        return (
            f'  <toast ts="{toast.time:.5f}" uid="{toast.uid}"'
            f" user={quoteattr(user)}>{escape(message)}</toast>"
        )
