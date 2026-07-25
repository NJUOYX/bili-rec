"""StreamStatistics: tracks stream-level statistics for progress display."""

from __future__ import annotations

from typing import Any

from ..statistics import SizedStatistics

__all__ = ("StreamStatistics",)


class StreamStatistics(SizedStatistics):
    """Stream-level statistics extending base Statistics with file tracking.

    Adds file size tracking and progress percentage for display.
    """

    def __init__(self) -> None:
        super().__init__()
        self._expected_size: int = 0
        self._segment_count: int = 0

    @property
    def expected_size(self) -> int:
        return self._expected_size

    @expected_size.setter
    def expected_size(self, value: int) -> None:
        self._expected_size = value

    @property
    def segment_count(self) -> int:
        return self._segment_count

    def increment_segment(self) -> None:
        self._segment_count += 1

    @property
    def progress_percent(self) -> float:
        """Calculate progress percentage if expected size is known."""
        if self._expected_size > 0:
            return min(100.0, (self._file_size / self._expected_size) * 100.0)
        return 0.0

    def snapshot(self) -> dict[str, Any]:
        snap = super().snapshot()
        snap["expected_size"] = self._expected_size
        snap["segment_count"] = self._segment_count
        snap["progress_percent"] = round(self.progress_percent, 1)
        return snap
