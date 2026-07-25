"""Defragment operator: discard fragmented streams."""

from __future__ import annotations

import logging
from collections.abc import Callable

from reactivex import Observable
from reactivex.abc import ObserverBase, SchedulerBase
from reactivex.disposable import Disposable

from ..models import FlvTag
from .typing import FLVStream, FLVStreamItem

__all__ = ("defragment",)

logger = logging.getLogger(__name__)


def defragment(
    *,
    min_duration: int = 1000,
) -> Callable[[FLVStream], FLVStream]:
    """Create a defragment operator that discards short streams.

    Args:
        min_duration: Minimum stream duration in milliseconds.

    Returns:
        An operator function that filters out short streams.
    """

    def operator(source: FLVStream) -> FLVStream:
        def subscribe(
            observer: ObserverBase[FLVStreamItem],
            scheduler: SchedulerBase | None = None,
        ) -> Disposable:
            first_timestamp: int | None = None
            last_timestamp: int | None = None
            disposed = False

            def on_next(item: FLVStreamItem) -> None:
                nonlocal first_timestamp, last_timestamp

                if disposed:
                    return

                if isinstance(item, FlvTag):
                    if first_timestamp is None:
                        first_timestamp = item.timestamp
                    last_timestamp = item.timestamp

                observer.on_next(item)

            def on_error(error: Exception) -> None:
                if not disposed:
                    observer.on_error(error)

            def on_completed() -> None:
                nonlocal disposed
                if disposed:
                    return

                # Check if stream is too short
                if first_timestamp is not None and last_timestamp is not None:
                    duration = last_timestamp - first_timestamp
                    if duration < min_duration:
                        logger.debug(
                            "Discarding fragmented stream: duration=%dms < %dms",
                            duration,
                            min_duration,
                        )
                        disposed = True
                        observer.on_completed()
                        return

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
