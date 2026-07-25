"""FLV utility functions and context managers."""

from __future__ import annotations

from types import TracebackType
from typing import Self

from .struct_io import RandomIO

__all__ = ("format_timestamp", "AutoRollbacker", "OffsetRepositor")


def format_timestamp(ms: int) -> str:
    """Format milliseconds to HH:MM:SS.mmm string."""
    if ms < 0:
        sign = "-"
        ms = -ms
    else:
        sign = ""
    hours, remainder = divmod(ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{sign}{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


class AutoRollbacker:
    """Context manager that rolls back stream position on exception."""

    def __init__(self, stream: RandomIO) -> None:
        self._stream = stream
        self._offset = 0

    def __enter__(self) -> Self:
        self._offset = self._stream.tell()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            self._stream.seek(self._offset)


class OffsetRepositor:
    """Context manager that restores stream position after block."""

    def __init__(self, stream: RandomIO) -> None:
        self._stream = stream
        self._offset = 0

    def __enter__(self) -> Self:
        self._offset = self._stream.tell()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self._stream.seek(self._offset)
