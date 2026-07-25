"""Correct operator: correct timestamps to be monotonically increasing."""

from __future__ import annotations

import logging
from collections.abc import Callable

from reactivex import Observable
from reactivex.abc import ObserverBase, SchedulerBase
from reactivex.disposable import Disposable

from ..models import FlvTag
from .typing import FLVStream, FLVStreamItem

__all__ = ("correct",)

logger = logging.getLogger(__name__)


def correct() -> Callable[[FLVStream], FLVStream]:
    """Create a correct operator that ensures monotonically increasing timestamps.

    If a tag has a timestamp less than the previous tag, it is corrected
    to be at least equal to the previous timestamp.

    Returns:
        An operator function that corrects timestamps.
    """

    def operator(source: FLVStream) -> FLVStream:
        def subscribe(
            observer: ObserverBase[FLVStreamItem],
            scheduler: SchedulerBase | None = None,
        ) -> Disposable:
            last_timestamp: int | None = None
            disposed = False

            def on_next(item: FLVStreamItem) -> None:
                nonlocal last_timestamp

                if disposed:
                    return

                if isinstance(item, FlvTag):
                    if last_timestamp is not None and item.timestamp < last_timestamp:
                        # Correct timestamp
                        logger.debug(
                            "Correcting timestamp: %d -> %d",
                            item.timestamp,
                            last_timestamp,
                        )
                        item = item.evolve(timestamp=last_timestamp)
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
