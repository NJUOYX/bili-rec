"""Dump operator: write FLV stream to file."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import IO

from reactivex import Observable
from reactivex.abc import ObserverBase, SchedulerBase
from reactivex.disposable import Disposable

from ..format import FlvDumper
from ..models import FlvHeader, FlvTag
from .typing import FLVStream, FLVStreamItem

__all__ = ("dump", "Dumper")

logger = logging.getLogger(__name__)


class Dumper:
    """Dump FLV stream to file."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._file: IO[bytes] | None = None
        self._dumper: FlvDumper | None = None
        self._bytes_written = 0

    def open(self) -> None:
        """Open the file for writing."""
        self._file = open(self._path, "wb")  # noqa: SIM115
        self._dumper = FlvDumper(self._file)
        self._bytes_written = 0
        logger.debug("Opened %s for writing", self._path)

    def close(self) -> None:
        """Close the file."""
        if self._file is not None:
            self._file.close()
            self._file = None
            self._dumper = None
            logger.debug("Closed %s (%d bytes)", self._path, self._bytes_written)

    def write(self, item: FLVStreamItem) -> int:
        """Write an item to the file."""
        if self._dumper is None:
            raise RuntimeError("Dumper not opened")

        if isinstance(item, FlvHeader):
            self._dumper.dump_header(item)
            self._dumper.dump_previous_tag_size(0)
            self._bytes_written += item.size + 4
            return item.size + 4
        elif isinstance(item, FlvTag):
            self._dumper.dump_tag(item)
            self._dumper.dump_previous_tag_size(item.tag_size)
            self._bytes_written += item.tag_size + 4
            return item.tag_size + 4
        return 0

    @property
    def bytes_written(self) -> int:
        """Get total bytes written."""
        return self._bytes_written

    @property
    def path(self) -> Path:
        """Get the file path."""
        return self._path


def dump(path: Path) -> Callable[[FLVStream], FLVStream]:
    """Create a dump operator that writes stream to file.

    Args:
        path: Path to the output FLV file.

    Returns:
        An operator function that writes to file.
    """

    def operator(source: FLVStream) -> FLVStream:
        def subscribe(
            observer: ObserverBase[FLVStreamItem],
            scheduler: SchedulerBase | None = None,
        ) -> Disposable:
            dumper = Dumper(path)
            dumper.open()
            disposed = False

            def on_next(item: FLVStreamItem) -> None:
                if disposed:
                    return

                try:
                    dumper.write(item)
                    observer.on_next(item)
                except Exception as e:
                    logger.error("Error writing to %s: %s", path, e)
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
