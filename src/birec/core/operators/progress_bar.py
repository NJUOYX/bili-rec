"""ProgressBar: displays recording progress."""

from __future__ import annotations

import logging
import time

__all__ = ("ProgressBar",)

logger = logging.getLogger(__name__)


class ProgressBar:
    """Displays recording progress with size, rate, and elapsed time."""

    def __init__(self) -> None:
        self._total_bytes: int = 0
        self._start_time: float = 0.0
        self._last_update_time: float = 0.0
        self._last_bytes: int = 0
        self._rate: float = 0.0

    @property
    def total_bytes(self) -> int:
        return self._total_bytes

    @property
    def rate(self) -> float:
        return self._rate

    @property
    def elapsed(self) -> float:
        if self._start_time:
            return time.monotonic() - self._start_time
        return 0.0

    def start(self) -> None:
        """Start the progress bar."""
        self._start_time = time.monotonic()
        self._last_update_time = self._start_time
        self._total_bytes = 0
        self._last_bytes = 0
        self._rate = 0.0

    def update(self, size: int) -> None:
        """Update with new data size."""
        self._total_bytes += size
        now = time.monotonic()
        dt = now - self._last_update_time
        if dt > 0:
            self._rate = (self._total_bytes - self._last_bytes) / dt
        self._last_update_time = now
        self._last_bytes = self._total_bytes

    def format_size(self, size: int) -> str:
        """Format byte size to human-readable string."""
        if size < 1024:
            return f"{size}B"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f}KB"
        if size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f}MB"
        return f"{size / (1024 * 1024 * 1024):.2f}GB"

    def format_rate(self, rate: float) -> str:
        """Format rate to human-readable string."""
        return f"{self.format_size(int(rate))}/s"

    def format_elapsed(self, elapsed: float) -> str:
        """Format elapsed time to HH:MM:SS."""
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def render(self) -> str:
        """Render the progress bar as a string."""
        return (
            f"{self.format_size(self._total_bytes)} "
            f"| {self.format_rate(self._rate)} "
            f"| {self.format_elapsed(self.elapsed)}"
        )

    def reset(self) -> None:
        """Reset progress bar."""
        self._total_bytes = 0
        self._start_time = 0.0
        self._last_update_time = 0.0
        self._last_bytes = 0
        self._rate = 0.0
