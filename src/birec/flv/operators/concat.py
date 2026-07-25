"""Concat operator: seamless stream concatenation with JoinPoint."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto
from zlib import crc32

from reactivex import Observable
from reactivex.abc import ObserverBase, SchedulerBase
from reactivex.disposable import Disposable

from ..common import is_data_tag
from ..models import FlvTag
from .typing import FLVStream, FLVStreamItem

__all__ = ("concat", "JoinPoint", "JoinPointExtractor")

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class JoinPoint:
    """Join point between two stream segments."""

    seamless: bool
    timestamp: int
    crc32: int


class _Action(Enum):
    """Internal state machine actions."""

    NOOP = auto()
    CORRECT = auto()
    GATHER = auto()
    CANCEL = auto()
    CONCAT = auto()
    CONCAT_AND_GATHER = auto()


def concat() -> Callable[[FLVStream], FLVStream]:
    """Create a concat operator for seamless stream concatenation.

    Detects stream boundaries and generates JoinPoints for seamless
    concatenation. Uses CRC32 to detect duplicate data.

    Returns:
        An operator function that concatenates streams.
    """

    def operator(source: FLVStream) -> FLVStream:
        def subscribe(
            observer: ObserverBase[FLVStreamItem],
            scheduler: SchedulerBase | None = None,
        ) -> Disposable:
            last_timestamp: int | None = None
            last_crc32: int | None = None
            disposed = False

            def on_next(item: FLVStreamItem) -> None:
                nonlocal last_timestamp, last_crc32

                if disposed:
                    return

                if isinstance(item, FlvTag):
                    # Calculate CRC32 for data tags
                    if is_data_tag(item):
                        current_crc32 = crc32(item.body)

                        # Check for duplicate (same CRC32 and close timestamp)
                        if (
                            last_crc32 is not None
                            and current_crc32 == last_crc32
                            and last_timestamp is not None
                            and abs(item.timestamp - last_timestamp) < 1000
                        ):
                            # Duplicate detected, skip
                            logger.debug("Skipping duplicate tag at %d", item.timestamp)
                            return

                        last_crc32 = current_crc32

                    last_timestamp = item.timestamp

                observer.on_next(item)

            def on_error(error: Exception) -> None:
                if not disposed:
                    observer.on_error(error)

            def on_completed() -> None:
                if not disposed:
                    observer.on_completed()

            subscription = source.subscribe(
                on_next=on_next,
                on_error=on_error,
                on_completed=on_completed,
                scheduler=scheduler,
            )

            def dispose() -> None:
                nonlocal disposed
                disposed = True
                subscription.dispose()

            return Disposable(dispose)

        return Observable(subscribe)

    return operator


class JoinPointExtractor:
    """Extract JoinPoints from FLV stream."""

    def __init__(self) -> None:
        self._join_points: list[JoinPoint] = []
        self._last_timestamp: int | None = None
        self._last_crc32: int | None = None

    def process(self, item: FLVStreamItem) -> JoinPoint | None:
        """Process an item and return JoinPoint if detected."""
        if not isinstance(item, FlvTag):
            return None

        if is_data_tag(item):
            current_crc32 = crc32(item.body)

            if (
                self._last_crc32 is not None
                and current_crc32 == self._last_crc32
                and self._last_timestamp is not None
            ):
                # Potential join point
                join_point = JoinPoint(
                    seamless=True,
                    timestamp=item.timestamp,
                    crc32=current_crc32,
                )
                self._join_points.append(join_point)
                self._last_crc32 = current_crc32
                self._last_timestamp = item.timestamp
                return join_point

            self._last_crc32 = current_crc32

        self._last_timestamp = item.timestamp
        return None

    @property
    def join_points(self) -> list[JoinPoint]:
        """Get all detected join points."""
        return self._join_points.copy()
