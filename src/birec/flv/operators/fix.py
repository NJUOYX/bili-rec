"""Fix operator: fix timestamp jumps."""

from __future__ import annotations

import logging
from collections.abc import Callable

from reactivex import Observable
from reactivex.abc import ObserverBase, SchedulerBase
from reactivex.disposable import Disposable

from ..models import FlvTag
from .typing import FLVStream, FLVStreamItem

__all__ = ("fix",)

logger = logging.getLogger(__name__)

# Default threshold for detecting timestamp jumps (1 hour)
DEFAULT_JUMP_THRESHOLD = 3_600_000


def fix(
    *,
    jump_threshold: int = DEFAULT_JUMP_THRESHOLD,
) -> Callable[[FLVStream], FLVStream]:
    """Create a fix operator that handles timestamp jumps.

    When a large timestamp jump is detected (e.g., stream restart),
    the timestamps are reset to continue from the last known timestamp.

    Args:
        jump_threshold: Threshold in milliseconds for detecting jumps.

    Returns:
        An operator function that fixes timestamp jumps.
    """

    def operator(source: FLVStream) -> FLVStream:
        def subscribe(
            observer: ObserverBase[FLVStreamItem],
            scheduler: SchedulerBase | None = None,
        ) -> Disposable:
            last_timestamp: int | None = None
            offset: int = 0
            disposed = False

            def on_next(item: FLVStreamItem) -> None:
                nonlocal last_timestamp, offset

                if disposed:
                    return

                if isinstance(item, FlvTag):
                    if last_timestamp is not None:
                        jump = item.timestamp - last_timestamp
                        if abs(jump) > jump_threshold:
                            # Large jump detected, adjust offset
                            logger.debug(
                                "Timestamp jump detected: %d -> %d (jump=%d)",
                                last_timestamp,
                                item.timestamp,
                                jump,
                            )
                            offset = last_timestamp - item.timestamp

                    # Apply offset
                    if offset != 0:
                        new_timestamp = item.timestamp + offset
                        item = item.evolve(timestamp=new_timestamp)

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
