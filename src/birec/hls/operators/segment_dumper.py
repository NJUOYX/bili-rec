"""SegmentDumper: write fMP4 segments to file."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import IO

from reactivex import Observable
from reactivex.abc import ObserverBase, SchedulerBase
from reactivex.disposable import Disposable

from .segment_fetcher import FetchedSegment

__all__ = ("dump_segments", "SegmentDumper")

logger = logging.getLogger(__name__)


class SegmentDumper:
    """Write fetched segments to an fMP4 file."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._file: IO[bytes] | None = None
        self._bytes_written = 0
        self._segment_count = 0
        self._init_written = False

    @property
    def path(self) -> Path:
        return self._path

    @property
    def bytes_written(self) -> int:
        return self._bytes_written

    @property
    def segment_count(self) -> int:
        return self._segment_count

    def open(self) -> None:
        """Open the output file for writing."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self._path, "wb")  # noqa: SIM115
        self._bytes_written = 0
        self._segment_count = 0
        self._init_written = False
        logger.debug("Opened %s for segment writing", self._path)

    def close(self) -> None:
        """Close the output file."""
        if self._file is not None:
            self._file.close()
            self._file = None
            logger.debug(
                "Closed %s (%d bytes, %d segments)",
                self._path,
                self._bytes_written,
                self._segment_count,
            )

    def write_init(self, data: bytes) -> int:
        """Write initialization segment data.

        Args:
            data: Init segment bytes.

        Returns:
            Number of bytes written.
        """
        if self._file is None:
            raise RuntimeError("SegmentDumper not opened")
        self._file.write(data)
        self._bytes_written += len(data)
        self._init_written = True
        return len(data)

    def write_segment(self, fetched: FetchedSegment) -> int:
        """Write a media segment.

        Args:
            fetched: The fetched segment with data.

        Returns:
            Number of bytes written.
        """
        if self._file is None:
            raise RuntimeError("SegmentDumper not opened")
        self._file.write(fetched.data)
        self._bytes_written += len(fetched.data)
        self._segment_count += 1
        return len(fetched.data)

    @property
    def is_open(self) -> bool:
        return self._file is not None


def dump_segments(
    path: Path,
) -> Callable[[Observable[FetchedSegment]], Observable[FetchedSegment]]:
    """Create an operator that writes segments to file.

    Args:
        path: Output file path for the fMP4 file.

    Returns:
        Operator that writes segments and passes them through.
    """

    def operator(
        source: Observable[FetchedSegment],
    ) -> Observable[FetchedSegment]:
        def subscribe(
            observer: ObserverBase[FetchedSegment],
            scheduler: SchedulerBase | None = None,
        ) -> Disposable:
            dumper = SegmentDumper(path)
            dumper.open()
            disposed = False

            def on_next(fetched: FetchedSegment) -> None:
                if disposed:
                    return
                try:
                    dumper.write_segment(fetched)
                    observer.on_next(fetched)
                except Exception as e:
                    logger.error("Error writing segment to %s: %s", path, e)
                    observer.on_error(e)

            def on_error(error: Exception) -> None:
                if not disposed:
                    dumper.close()
                    observer.on_error(error)

            def on_completed() -> None:
                if not disposed:
                    dumper.close()
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
                dumper.close()
                subscription.dispose()

            return Disposable(dispose)

        return Observable(subscribe)

    return operator
