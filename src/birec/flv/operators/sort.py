"""Sort operator: sort tags within GOP by DTS."""

from __future__ import annotations

import logging
from collections.abc import Callable

from reactivex import Observable
from reactivex.abc import ObserverBase, SchedulerBase
from reactivex.disposable import Disposable

from ..common import is_video_nalu_keyframe
from ..models import FlvTag
from .typing import FLVStream, FLVStreamItem

__all__ = ("sort",)

logger = logging.getLogger(__name__)


def sort() -> Callable[[FLVStream], FLVStream]:
    """Create a sort operator that sorts tags within GOP by DTS.

    Buffers tags until a keyframe is encountered, then sorts the buffer
    by timestamp before emitting.

    Returns:
        An operator function that sorts tags within GOP.
    """

    def operator(source: FLVStream) -> FLVStream:
        def subscribe(
            observer: ObserverBase[FLVStreamItem],
            scheduler: SchedulerBase | None = None,
        ) -> Disposable:
            buffer: list[FlvTag] = []
            disposed = False

            def flush_buffer() -> None:
                nonlocal buffer
                if buffer:
                    # Sort by timestamp
                    buffer.sort(key=lambda t: t.timestamp)
                    for tag in buffer:
                        observer.on_next(tag)
                    buffer = []

            def on_next(item: FLVStreamItem) -> None:
                nonlocal buffer

                if disposed:
                    return

                if isinstance(item, FlvTag):
                    if is_video_nalu_keyframe(item) and buffer:
                        # Keyframe encountered, flush and sort buffer
                        flush_buffer()
                    buffer.append(item)
                else:
                    # Non-tag item (e.g., header), flush buffer first
                    flush_buffer()
                    observer.on_next(item)

            def on_error(error: Exception) -> None:
                if not disposed:
                    observer.on_error(error)

            def on_completed() -> None:
                if not disposed:
                    flush_buffer()
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
