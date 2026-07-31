"""Core domain models: danmaku messages, stream events."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

__all__ = (
    "Danmaku",
    "SuperChat",
    "Gift",
    "GuardBuy",
    "DanmakuMessage",
    "StreamEvent",
    "StartedSegment",
    "CompletedSegment",
)


@dataclass(frozen=True)
class Danmaku:
    """A single danmaku message."""

    timestamp: float  # Unix timestamp
    content: str
    uid: int = 0
    uname: str = ""
    color: int = 0xFFFFFF
    font_size: int = 25
    dm_type: int = 0  # 0=scroll, 1=top, 2=bottom


@dataclass(frozen=True)
class SuperChat:
    """A Super Chat message."""

    timestamp: float
    uid: int
    uname: str
    price: int
    content: str
    message_id: int = 0


@dataclass(frozen=True)
class Gift:
    """A gift message."""

    timestamp: float
    uid: int
    uname: str
    gift_name: str
    gift_id: int = 0
    num: int = 1
    price: int = 0
    action: str = "投喂"


@dataclass(frozen=True)
class GuardBuy:
    """A guard (membership) purchase event."""

    timestamp: float
    uid: int
    uname: str
    guard_level: int  # 1=总督, 2=提督, 3=舰长
    num: int = 1
    price: int = 0


@dataclass
class DanmakuMessage:
    """Union type for all danmaku-related messages."""

    type: str  # "danmaku", "super_chat", "gift", "guard_buy"
    data: Danmaku | SuperChat | Gift | GuardBuy

    @staticmethod
    def danmaku(
        ts: float,
        content: str,
        uid: int = 0,
        uname: str = "",
        **kwargs: Any,
    ) -> DanmakuMessage:
        return DanmakuMessage(
            type="danmaku",
            data=Danmaku(timestamp=ts, content=content, uid=uid, uname=uname, **kwargs),
        )

    @staticmethod
    def super_chat(
        ts: float,
        uid: int,
        uname: str,
        price: int,
        content: str,
        message_id: int = 0,
    ) -> DanmakuMessage:
        return DanmakuMessage(
            type="super_chat",
            data=SuperChat(
                timestamp=ts,
                uid=uid,
                uname=uname,
                price=price,
                content=content,
                message_id=message_id,
            ),
        )

    @staticmethod
    def gift(
        ts: float,
        uid: int,
        uname: str,
        gift_name: str,
        gift_id: int = 0,
        num: int = 1,
        price: int = 0,
        action: str = "投喂",
    ) -> DanmakuMessage:
        return DanmakuMessage(
            type="gift",
            data=Gift(
                timestamp=ts,
                uid=uid,
                uname=uname,
                gift_name=gift_name,
                gift_id=gift_id,
                num=num,
                price=price,
                action=action,
            ),
        )

    @staticmethod
    def guard_buy(
        ts: float,
        uid: int,
        uname: str,
        guard_level: int,
        num: int = 1,
        price: int = 0,
    ) -> DanmakuMessage:
        return DanmakuMessage(
            type="guard_buy",
            data=GuardBuy(
                timestamp=ts,
                uid=uid,
                uname=uname,
                guard_level=guard_level,
                num=num,
                price=price,
            ),
        )


@dataclass
class StreamEvent:
    """Represents a stream lifecycle event."""

    type: str  # "stream_started", "stream_ended", "stream_failed"
    room_id: int
    timestamp: datetime = field(default_factory=lambda: datetime.now())
    reason: str = ""


@dataclass(frozen=True)
class StartedSegment:
    """The files one recording segment has just opened on disk.

    Reported as the segment starts so that "recording began" can be announced
    with the paths it will be writing to, which is what a user watching the
    dashboard is being told about.
    """

    video_path: str
    danmaku_path: str = ""
    raw_danmaku_path: str = ""


@dataclass(frozen=True)
class CompletedSegment:
    """The files one finished recording segment left on disk.

    Collected while the segment is closed down, because the danmaku paths live
    on the dumpers and those are dropped as part of the same teardown.
    """

    video_path: str
    danmaku_path: str = ""
    raw_danmaku_path: str = ""
