"""Danmaku XML item models for file-level representation."""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = (
    "DanmakuItem",
    "SuperChatItem",
    "GiftItem",
    "GuardItem",
    "ToastItem",
    "DanmakuMetadata",
    "DanmakuDocument",
)


@dataclass(frozen=True, slots=True)
class DanmakuItem:
    """A single danmaku entry in XML (<d> element).

    Attributes:
        time: Offset in seconds from stream start.
        mode: Danmaku mode (1=scroll, 4=bottom, 5=top).
        font_size: Font size (default 25).
        color: Decimal color value (default 16777215 = white).
        timestamp: Unix timestamp when sent.
        pool: Pool type (0=normal).
        uid: Sender user ID.
        row_id: Row ID for dedup (0 if unknown).
        content: Text content.
    """

    time: float
    content: str
    mode: int = 1
    font_size: int = 25
    color: int = 16777215
    timestamp: int = 0
    pool: int = 0
    uid: int = 0
    row_id: int = 0


@dataclass(frozen=True, slots=True)
class SuperChatItem:
    """A Super Chat entry in XML (<sc> element)."""

    time: float
    uid: int
    user: str
    price: int
    content: str
    sc_id: int = 0


@dataclass(frozen=True, slots=True)
class GiftItem:
    """A gift entry in XML (<gift> element)."""

    time: float
    uid: int
    user: str
    gift_name: str
    gift_id: int = 0
    num: int = 1
    price: int = 0
    coin_type: str = "silver"  # "gold" or "silver"
    action: str = "投喂"


@dataclass(frozen=True, slots=True)
class GuardItem:
    """A guard buy entry in XML (<guard> element)."""

    time: float
    uid: int
    user: str
    level: int  # 1=总督, 2=提督, 3=舰长
    num: int = 1
    price: int = 0


@dataclass(frozen=True, slots=True)
class ToastItem:
    """A user toast entry in XML (<toast> element)."""

    time: float
    uid: int
    user: str
    message: str


@dataclass(frozen=True, slots=True)
class DanmakuMetadata:
    """Metadata header for danmaku XML (<metadata> element)."""

    recorder: str = ""
    room_id: int = 0
    user_name: str = ""
    title: str = ""
    area: str = ""
    parent_area: str = ""
    live_start_time: str = ""
    live_end_time: str = ""


@dataclass(slots=True)
class DanmakuDocument:
    """Complete danmaku XML document representation."""

    metadata: DanmakuMetadata | None = None
    danmakus: list[DanmakuItem] = field(default_factory=list)
    super_chats: list[SuperChatItem] = field(default_factory=list)
    gifts: list[GiftItem] = field(default_factory=list)
    guards: list[GuardItem] = field(default_factory=list)
    toasts: list[ToastItem] = field(default_factory=list)

    @property
    def total_count(self) -> int:
        """Total number of all items."""
        return (
            len(self.danmakus)
            + len(self.super_chats)
            + len(self.gifts)
            + len(self.guards)
            + len(self.toasts)
        )

    def is_empty(self) -> bool:
        """Check if document has no danmaku items."""
        return len(self.danmakus) == 0 and self.total_count == 0
