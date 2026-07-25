"""DanmakuReader: read Bilibili-compatible danmaku XML files."""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path
from xml.etree.ElementTree import Element, parse

from .models import (
    DanmakuDocument,
    DanmakuItem,
    DanmakuMetadata,
    GiftItem,
    GuardItem,
    SuperChatItem,
    ToastItem,
)

__all__ = ("DanmakuReader",)

logger = logging.getLogger(__name__)


class DanmakuReader:
    """Read danmaku XML files into DanmakuDocument objects.

    Supports Bilibili's danmaku XML format with elements:
    <metadata>, <d>, <sc>, <gift>, <guard>, <toast>.
    """

    def read(self, path: Path | str) -> DanmakuDocument:
        """Read a danmaku XML file.

        Args:
            path: Path to the XML file.

        Returns:
            Parsed DanmakuDocument.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the XML is malformed.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Danmaku file not found: {path}")

        try:
            tree = parse(path)  # noqa: S314
        except Exception as e:
            raise ValueError(f"Failed to parse danmaku XML: {path}: {e}") from e

        root = tree.getroot()
        doc = DanmakuDocument()

        for child in root:
            tag = child.tag.lower() if isinstance(child.tag, str) else ""
            if tag == "metadata":
                doc.metadata = self._parse_metadata(child)
            elif tag == "d":
                item = self._parse_danmaku(child)
                if item is not None:
                    doc.danmakus.append(item)
            elif tag == "sc":
                sc = self._parse_super_chat(child)
                if sc is not None:
                    doc.super_chats.append(sc)
            elif tag == "gift":
                gift = self._parse_gift(child)
                if gift is not None:
                    doc.gifts.append(gift)
            elif tag == "guard":
                guard = self._parse_guard(child)
                if guard is not None:
                    doc.guards.append(guard)
            elif tag == "toast":
                toast = self._parse_toast(child)
                if toast is not None:
                    doc.toasts.append(toast)

        return doc

    def _parse_metadata(self, elem: Element) -> DanmakuMetadata:
        """Parse <metadata> element."""

        def _text(tag: str) -> str:
            child = elem.find(tag)
            return child.text.strip() if child is not None and child.text else ""

        room_id_str = _text("room_id")
        room_id = 0
        with contextlib.suppress(ValueError):
            room_id = int(room_id_str)

        return DanmakuMetadata(
            recorder=_text("recorder"),
            room_id=room_id,
            user_name=_text("user_name"),
            title=_text("title"),
            area=_text("area"),
            parent_area=_text("parent_area"),
            live_start_time=_text("live_start_time"),
            live_end_time=_text("live_end_time"),
        )

    def _parse_danmaku(self, elem: Element) -> DanmakuItem | None:
        """Parse <d> element."""
        p_attr = elem.get("p", "")
        if not p_attr:
            return None

        parts = p_attr.split(",")
        if len(parts) < 4:
            return None

        try:
            time_val = float(parts[0])
            mode = int(parts[1])
            font_size = int(parts[2])
            color = int(parts[3])
            timestamp = int(parts[4]) if len(parts) > 4 else 0
            pool = int(parts[5]) if len(parts) > 5 else 0
            uid = int(parts[6]) if len(parts) > 6 else 0
            row_id = int(parts[7]) if len(parts) > 7 else 0
        except (ValueError, IndexError):
            return None

        content = elem.text or ""
        return DanmakuItem(
            time=time_val,
            content=content,
            mode=mode,
            font_size=font_size,
            color=color,
            timestamp=timestamp,
            pool=pool,
            uid=uid,
            row_id=row_id,
        )

    def _parse_super_chat(self, elem: Element) -> SuperChatItem | None:
        """Parse <sc> element."""
        try:
            time_val = float(elem.get("ts", "0"))
            uid = int(elem.get("uid", "0"))
            user = elem.get("user", "")
            price = int(elem.get("price", "0"))
            sc_id = int(elem.get("id", "0"))
        except ValueError:
            return None

        content = elem.text or ""
        return SuperChatItem(
            time=time_val,
            uid=uid,
            user=user,
            price=price,
            content=content,
            sc_id=sc_id,
        )

    def _parse_gift(self, elem: Element) -> GiftItem | None:
        """Parse <gift> element."""
        try:
            time_val = float(elem.get("ts", "0"))
            uid = int(elem.get("uid", "0"))
            user = elem.get("user", "")
            gift_name = elem.get("giftname", "")
            gift_id = int(elem.get("giftid", "0"))
            num = int(elem.get("num", "1"))
            price = int(elem.get("price", "0"))
            coin_type = elem.get("coin_type", "silver")
            action = elem.get("action", "投喂")
        except ValueError:
            return None

        return GiftItem(
            time=time_val,
            uid=uid,
            user=user,
            gift_name=gift_name,
            gift_id=gift_id,
            num=num,
            price=price,
            coin_type=coin_type,
            action=action,
        )

    def _parse_guard(self, elem: Element) -> GuardItem | None:
        """Parse <guard> element."""
        try:
            time_val = float(elem.get("ts", "0"))
            uid = int(elem.get("uid", "0"))
            user = elem.get("user", "")
            level = int(elem.get("level", "3"))
            num = int(elem.get("num", "1"))
            price = int(elem.get("price", "0"))
        except ValueError:
            return None

        return GuardItem(
            time=time_val,
            uid=uid,
            user=user,
            level=level,
            num=num,
            price=price,
        )

    def _parse_toast(self, elem: Element) -> ToastItem | None:
        """Parse <toast> element."""
        try:
            time_val = float(elem.get("ts", "0"))
            uid = int(elem.get("uid", "0"))
            user = elem.get("user", "")
        except ValueError:
            return None

        message = elem.text or ""
        return ToastItem(
            time=time_val,
            uid=uid,
            user=user,
            message=message,
        )
