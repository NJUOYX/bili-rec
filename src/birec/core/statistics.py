"""Recording statistics: rate, count, and elapsed time tracking."""

from __future__ import annotations

import time
from typing import Any

__all__ = ("Statistics", "SizedStatistics")


class Statistics:
    """Tracks download rate, danmaku rate, and recording elapsed time."""

    def __init__(self) -> None:
        self._dl_total: int = 0
        self._dl_rate: float = 0.0
        self._danmu_total: int = 0
        self._danmu_rate: float = 0.0
        self._rec_elapsed: float = 0.0
        self._rec_total: float = 0.0
        self._rec_rate: float = 0.0
        self._start_time: float | None = None
        self._last_update: float | None = None
        self._last_dl: int = 0
        self._last_danmu: int = 0

    @property
    def dl_total(self) -> int:
        return self._dl_total

    @property
    def dl_rate(self) -> float:
        return self._dl_rate

    @property
    def danmu_total(self) -> int:
        return self._danmu_total

    @property
    def danmu_rate(self) -> float:
        return self._danmu_rate

    @property
    def rec_elapsed(self) -> float:
        if self._start_time is not None:
            return time.monotonic() - self._start_time
        return self._rec_elapsed

    @property
    def rec_total(self) -> float:
        return self._rec_total

    @property
    def rec_rate(self) -> float:
        return self._rec_rate

    def start(self) -> None:
        """Start recording timer."""
        self._start_time = time.monotonic()
        self._last_update = self._start_time

    def stop(self) -> None:
        """Stop recording timer and accumulate total."""
        if self._start_time is not None:
            self._rec_elapsed = time.monotonic() - self._start_time
            self._rec_total += self._rec_elapsed
            self._start_time = None
            self._last_update = None

    def reset(self) -> None:
        """Reset all counters."""
        self._dl_total = 0
        self._dl_rate = 0.0
        self._danmu_total = 0
        self._danmu_rate = 0.0
        self._rec_elapsed = 0.0
        self._rec_total = 0.0
        self._rec_rate = 0.0
        self._start_time = None
        self._last_update = None
        self._last_dl = 0
        self._last_danmu = 0

    def update_dl(self, size: int) -> None:
        """Record downloaded bytes."""
        self._dl_total += size

    def update_danmu(self, count: int = 1) -> None:
        """Record received danmaku count."""
        self._danmu_total += count

    def tick(self) -> None:
        """Update rates based on elapsed time since last tick."""
        now = time.monotonic()
        if self._last_update is None:
            self._last_update = now
            return

        dt = now - self._last_update
        if dt <= 0:
            return

        self._dl_rate = (self._dl_total - self._last_dl) / dt
        self._danmu_rate = (self._danmu_total - self._last_danmu) / dt
        elapsed = self.rec_elapsed
        if elapsed > 0:
            self._rec_rate = self._dl_total / elapsed

        self._last_update = now
        self._last_dl = self._dl_total
        self._last_danmu = self._danmu_total

    def snapshot(self) -> dict[str, Any]:
        """Return current statistics as a dict."""
        return {
            "dl_total": self._dl_total,
            "dl_rate": round(self._dl_rate, 2),
            "danmu_total": self._danmu_total,
            "danmu_rate": round(self._danmu_rate, 2),
            "rec_elapsed": round(self.rec_elapsed, 2),
            "rec_total": round(self._rec_total, 2),
            "rec_rate": round(self._rec_rate, 2),
        }


class SizedStatistics(Statistics):
    """Statistics variant that also tracks file size for progress display."""

    def __init__(self) -> None:
        super().__init__()
        self._file_size: int = 0

    @property
    def file_size(self) -> int:
        return self._file_size

    def update_file_size(self, size: int) -> None:
        self._file_size = size

    def snapshot(self) -> dict[str, Any]:
        snap = super().snapshot()
        snap["file_size"] = self._file_size
        return snap
