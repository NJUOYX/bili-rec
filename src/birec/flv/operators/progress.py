"""Progress operator: report recording progress."""

from __future__ import annotations

import logging
from collections.abc import Callable

from reactivex import Observable
from reactivex.abc import ObserverBase, SchedulerBase
from reactivex.disposable import Disposable

from ..models import FlvTag
from .typing import FLVStream, FLVStreamItem

__all__ = ("progress", "ProgressBar")

logger = logging.getLogger(__name__)


class ProgressBar:
    """Track and report recording progress."""

    def __init__(self) -> None:
        self._bytes_written = 0
        self._duration_ms = 0
        self._first_timestamp: int | None = None
        self._last_timestamp: int | None = None

    def update(self, item: FLVStreamItem, bytes_written: int) -> None:
        """Update progress with new item."""
        self._bytes_written += bytes_written

        if isinstance(item, FlvTag):
            if self._first_timestamp is None:
                self._first_timestamp = item.timestamp
            self._last_timestamp = item.timestamp

    @property
    def bytes_written(self) -> int:
        """Get total bytes written."""
        return self._bytes_written

    @property
    def duration_ms(self) -> int:
        """Get recording duration in milliseconds."""
        if self._first_timestamp is not None and self._last_timestamp is not None:
            return self._last_timestamp - self._first_timestamp
        return 0

    @property
    def duration_str(self) -> str:
        """Get formatted duration string."""
        ms = self.duration_ms
        hours, remainder = divmod(ms, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        seconds, millis = divmod(remainder, 1_000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"

    def get_status(self) -> dict[str, int | str]:
        """Get progress status."""
        return {
            "bytes_written": self._bytes_written,
            "duration_ms": self.duration_ms,
            "duration_str": self.duration_str,
        }


def progress(
    callback: Callable[[ProgressBar], None] | None = None,
    interval: int = 1000,
) -> Callable[[FLVStream], FLVStream]:
    """Create a progress operator that reports recording progress.

    Args:
        callback: Optional callback invoked with ProgressBar periodically.
        interval: Callback interval in milliseconds (based on stream time).

    Returns:
        An operator function that tracks progress.
    """

    def operator(source: FLVStream) -> FLVStream:
        def subscribe(
            observer: ObserverBase[FLVStreamItem],
            scheduler: SchedulerBase | None = None,
        ) -> Disposable:
            progress_bar = ProgressBar()
            last_callback_time = 0
            disposed = False

            def on_next(item: FLVStreamItem) -> None:
                nonlocal last_callback_time

                if disposed:
                    return

                # Estimate bytes (tag size + back pointer)
                bytes_written = item.tag_size + 4 if isinstance(item, FlvTag) else 13

                progress_bar.update(item, bytes_written)

                # Call callback periodically
                if callback is not None:
                    current_time = progress_bar.duration_ms
                    if current_time - last_callback_time >= interval:
                        callback(progress_bar)
                        last_callback_time = current_time

                observer.on_next(item)

            def on_error(error: Exception) -> None:
                if not disposed:
                    observer.on_error(error)

            def on_completed() -> None:
                if not disposed:
                    # Final callback
                    if callback is not None:
                        callback(progress_bar)
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
