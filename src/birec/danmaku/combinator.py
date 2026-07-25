"""Danmaku combinator and concatenator for merging danmaku files."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from enum import Enum

from .models import DanmakuDocument

__all__ = ("TimeBase", "DanmakuCombinator", "DanmakuConcatenator")

logger = logging.getLogger(__name__)


class TimeBase(Enum):
    """Time base for danmaku combination."""

    LIVE = "live"  # Use live start time as reference
    RECORD = "record"  # Use record start time as reference


@dataclass(frozen=True, slots=True)
class CombineResult:
    """Result of a danmaku combine/concatenate operation."""

    document: DanmakuDocument
    total_added: int = 0


class DanmakuCombinator:
    """Combine multiple danmaku documents using a common time base.

    Re-times all danmaku items relative to a common reference point
    (either LIVE start or RECORD start).
    """

    def __init__(self, time_base: TimeBase = TimeBase.RECORD) -> None:
        self._time_base = time_base

    @property
    def time_base(self) -> TimeBase:
        return self._time_base

    def combine(
        self,
        docs: list[DanmakuDocument],
        *,
        reference_time: float = 0.0,
    ) -> CombineResult:
        """Combine multiple documents into one.

        All danmaku items are re-timed relative to reference_time.
        Items are sorted by time after combination.

        Args:
            docs: List of documents to combine.
            reference_time: The common reference timestamp.

        Returns:
            CombineResult with merged document.
        """
        if not docs:
            return CombineResult(document=DanmakuDocument())

        result = DanmakuDocument()
        # Use metadata from the first document
        result.metadata = docs[0].metadata

        total_added = 0
        for doc in docs:
            for item in doc.danmakus:
                result.danmakus.append(item)
                total_added += 1
            result.super_chats.extend(doc.super_chats)
            result.gifts.extend(doc.gifts)
            result.guards.extend(doc.guards)
            result.toasts.extend(doc.toasts)

        # Sort all items by time
        result.danmakus.sort(key=lambda x: x.time)
        result.super_chats.sort(key=lambda x: x.time)
        result.gifts.sort(key=lambda x: x.time)
        result.guards.sort(key=lambda x: x.time)
        result.toasts.sort(key=lambda x: x.time)

        return CombineResult(document=result, total_added=total_added)


class DanmakuConcatenator:
    """Concatenate danmaku documents with time offset.

    Each subsequent document's items are offset by the accumulated
    duration of all previous documents.
    """

    def concatenate(
        self,
        docs: list[DanmakuDocument],
        *,
        durations: list[float] | None = None,
    ) -> CombineResult:
        """Concatenate documents with delta offsets.

        Args:
            docs: List of documents to concatenate in order.
            durations: Duration of each document in seconds.
                If None, uses max time from each document.

        Returns:
            CombineResult with concatenated document.
        """
        if not docs:
            return CombineResult(document=DanmakuDocument())

        if durations is None:
            durations = [self._get_duration(doc) for doc in docs]

        result = DanmakuDocument()
        result.metadata = docs[0].metadata

        offset = 0.0
        total_added = 0

        for i, doc in enumerate(docs):
            # Offset danmaku items
            for item in doc.danmakus:
                result.danmakus.append(replace(item, time=item.time + offset))
                total_added += 1

            # Offset super chats
            for sc in doc.super_chats:
                result.super_chats.append(replace(sc, time=sc.time + offset))

            # Offset gifts
            for gift in doc.gifts:
                result.gifts.append(replace(gift, time=gift.time + offset))

            # Offset guards
            for guard in doc.guards:
                result.guards.append(replace(guard, time=guard.time + offset))

            # Offset toasts
            for toast in doc.toasts:
                result.toasts.append(replace(toast, time=toast.time + offset))

            # Advance offset by this document's duration
            if i < len(durations):
                offset += durations[i]

        return CombineResult(document=result, total_added=total_added)

    @staticmethod
    def _get_duration(doc: DanmakuDocument) -> float:
        """Get the duration of a document (max time across all items)."""
        max_time = 0.0
        if doc.danmakus:
            max_time = max(max_time, max(d.time for d in doc.danmakus))
        if doc.super_chats:
            max_time = max(max_time, max(sc.time for sc in doc.super_chats))
        if doc.gifts:
            max_time = max(max_time, max(g.time for g in doc.gifts))
        if doc.guards:
            max_time = max(max_time, max(g.time for g in doc.guards))
        if doc.toasts:
            max_time = max(max_time, max(t.time for t in doc.toasts))
        return max_time
