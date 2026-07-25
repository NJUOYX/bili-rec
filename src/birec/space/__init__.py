"""Disk space monitoring and reclamation."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

__all__ = ("SpaceInfo", "SpaceMonitor", "SpaceReclaimer")

logger = logging.getLogger(__name__)

# Default TTL for recording files (24 hours)
DEFAULT_REC_TTL = 24 * 60 * 60

# File extensions eligible for reclamation
RECLAIMABLE_EXTENSIONS = {
    ".flv",
    ".mp4",
    ".m4s",
    ".xml",
    ".jsonl",
    ".ass",
    ".jpg",
    ".png",
}


@dataclass(frozen=True, slots=True)
class SpaceInfo:
    """Disk space information."""

    total: int
    used: int
    free: int
    path: str

    @property
    def percent_used(self) -> float:
        """Percentage of disk used."""
        if self.total == 0:
            return 0.0
        return (self.used / self.total) * 100.0


class SpaceMonitor:
    """Periodically monitor disk space and emit alerts.

    Checks remaining space at a configurable interval and calls
    the callback when free space drops below the threshold.
    """

    def __init__(
        self,
        path: Path | str,
        *,
        threshold: int = 1024 * 1024 * 1024,  # 1 GB default
        check_interval: float = 60.0,
        on_space_low: Callable[[SpaceInfo], None] | None = None,
    ) -> None:
        self._path = Path(path)
        self._threshold = threshold
        self._check_interval = check_interval
        self._on_space_low = on_space_low
        self._running = False
        self._task: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        return self._running

    def get_space_info(self) -> SpaceInfo:
        """Get current disk space information."""
        usage = shutil.disk_usage(self._path)
        return SpaceInfo(
            total=usage.total,
            used=usage.used,
            free=usage.free,
            path=str(self._path),
        )

    async def start(self) -> None:
        """Start monitoring."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.debug("SpaceMonitor started for %s", self._path)

    async def stop(self) -> None:
        """Stop monitoring."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        logger.debug("SpaceMonitor stopped")

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                info = self.get_space_info()
                if info.free < self._threshold:
                    logger.warning(
                        "Low disk space: %d bytes free (threshold: %d)",
                        info.free,
                        self._threshold,
                    )
                    if self._on_space_low is not None:
                        self._on_space_low(info)
            except OSError as e:
                logger.error("Failed to check disk space: %s", e)

            await asyncio.sleep(self._check_interval)


class SpaceReclaimer:
    """Reclaim disk space by deleting oldest recording files.

    Deletes files by mtime ascending (oldest first) with TTL protection.
    """

    def __init__(
        self,
        directories: list[Path],
        *,
        rec_ttl: int = DEFAULT_REC_TTL,
        extensions: set[str] | None = None,
    ) -> None:
        self._directories = directories
        self._rec_ttl = rec_ttl
        self._extensions = extensions or RECLAIMABLE_EXTENSIONS

    @property
    def rec_ttl(self) -> int:
        return self._rec_ttl

    def find_reclaimable_files(self) -> list[Path]:
        """Find files eligible for reclamation (past TTL).

        Returns:
            List of files sorted by mtime ascending (oldest first).
        """
        now = time.time()
        cutoff = now - self._rec_ttl
        candidates: list[tuple[float, Path]] = []

        for directory in self._directories:
            if not directory.exists():
                continue
            for file_path in directory.rglob("*"):
                if not file_path.is_file():
                    continue
                if file_path.suffix.lower() not in self._extensions:
                    continue
                try:
                    mtime = file_path.stat().st_mtime
                    if mtime < cutoff:
                        candidates.append((mtime, file_path))
                except OSError:
                    continue

        # Sort by mtime ascending (oldest first)
        candidates.sort(key=lambda x: x[0])
        return [path for _, path in candidates]

    def reclaim(self, target_free: int) -> int:
        """Reclaim space until target free bytes is reached.

        Args:
            target_free: Desired free space in bytes.

        Returns:
            Number of bytes reclaimed.
        """
        reclaimed = 0
        files = self.find_reclaimable_files()

        for file_path in files:
            try:
                size = file_path.stat().st_size
                file_path.unlink()
                reclaimed += size
                logger.debug("Reclaimed %s (%d bytes)", file_path, size)
            except OSError as e:
                logger.warning("Failed to delete %s: %s", file_path, e)
                continue

            # Check if we've reclaimed enough
            try:
                info = SpaceInfo(
                    total=0,
                    used=0,
                    free=shutil.disk_usage(self._directories[0]).free,
                    path=str(self._directories[0]),
                )
                if info.free >= target_free:
                    break
            except OSError:
                break

        if reclaimed > 0:
            logger.info("Reclaimed %d bytes total", reclaimed)
        return reclaimed
