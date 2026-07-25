"""RecordingMonitor: monitors recording progress and triggers events."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

__all__ = ("RecordingMonitor",)

logger = logging.getLogger(__name__)


class RecordingMonitor:
    """Monitors recording progress, detects stalls, and reports status."""

    def __init__(
        self,
        *,
        stall_timeout: float = 30.0,
        report_interval: float = 10.0,
    ) -> None:
        self._stall_timeout = stall_timeout
        self._report_interval = report_interval
        self._last_data_time: float = 0.0
        self._last_report_time: float = 0.0
        self._total_bytes: int = 0
        self._is_recording: bool = False
        self._stalled: bool = False
        self._on_stall: Callable[[], None] | None = None
        self._on_report: Callable[[dict[str, Any]], None] | None = None

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    @property
    def stalled(self) -> bool:
        return self._stalled

    @property
    def total_bytes(self) -> int:
        return self._total_bytes

    def set_callbacks(
        self,
        on_stall: Callable[[], None] | None = None,
        on_report: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._on_stall = on_stall
        self._on_report = on_report

    def start(self) -> None:
        """Start monitoring."""
        self._is_recording = True
        self._stalled = False
        self._last_data_time = time.monotonic()
        self._last_report_time = time.monotonic()
        self._total_bytes = 0

    def stop(self) -> None:
        """Stop monitoring."""
        self._is_recording = False

    def on_data(self, size: int) -> None:
        """Called when data is received."""
        self._total_bytes += size
        self._last_data_time = time.monotonic()
        if self._stalled:
            self._stalled = False
            logger.info("Recording resumed after stall")

    def tick(self) -> None:
        """Periodic check for stalls and reporting."""
        now = time.monotonic()

        # Check for stall
        if (
            self._is_recording
            and not self._stalled
            and now - self._last_data_time > self._stall_timeout
        ):
            self._stalled = True
            logger.warning(
                "Recording stalled: no data for %.1fs",
                self._stall_timeout,
            )
            if self._on_stall:
                self._on_stall()

        # Periodic report
        if self._is_recording and now - self._last_report_time >= self._report_interval:
            self._last_report_time = now
            report = {
                "total_bytes": self._total_bytes,
                "stalled": self._stalled,
                "elapsed": now - self._last_data_time,
            }
            if self._on_report:
                self._on_report(report)

    def reset(self) -> None:
        """Reset all state."""
        self._is_recording = False
        self._stalled = False
        self._total_bytes = 0
        self._last_data_time = 0.0
        self._last_report_time = 0.0
