"""Probe operator for HLS: probe fMP4 files using ffprobe."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from reactivex import Observable
from reactivex.abc import ObserverBase, SchedulerBase
from reactivex.disposable import Disposable

from .segment_fetcher import FetchedSegment

__all__ = ("probe", "HlsProber", "HlsStreamInfo")

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class HlsStreamInfo:
    """Stream information from ffprobe for HLS/fMP4."""

    codec_name: str | None = None
    width: int | None = None
    height: int | None = None
    duration: float | None = None
    bit_rate: int | None = None
    format_name: str | None = None


class HlsProber:
    """Probe fMP4/HLS media files using ffprobe."""

    def __init__(self, ffprobe_path: str | None = None) -> None:
        self._ffprobe_path = ffprobe_path or shutil.which("ffprobe") or "ffprobe"

    @property
    def available(self) -> bool:
        """Check if ffprobe is available."""
        return shutil.which(self._ffprobe_path) is not None

    async def probe_file(self, path: Path) -> HlsStreamInfo | None:
        """Probe a media file and return stream info.

        Args:
            path: Path to the media file.

        Returns:
            HlsStreamInfo or None if probe fails.
        """
        if not self.available:
            logger.warning("ffprobe not available")
            return None

        try:
            result = await asyncio.create_subprocess_exec(
                self._ffprobe_path,
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_streams",
                "-show_format",
                str(path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await result.communicate()

            if result.returncode != 0:
                logger.error("ffprobe failed with code %d", result.returncode)
                return None

            data = json.loads(stdout.decode())
            return self._parse_output(data)

        except Exception as e:
            logger.error("ffprobe error: %s", e)
            return None

    def _parse_output(self, data: dict[str, Any]) -> HlsStreamInfo:
        """Parse ffprobe JSON output."""
        video_stream = None
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                video_stream = stream
                break

        format_info = data.get("format", {})

        if video_stream is None:
            return HlsStreamInfo(
                format_name=format_info.get("format_name"),
                duration=_safe_float(format_info.get("duration")),
                bit_rate=_safe_int(format_info.get("bit_rate")),
            )

        return HlsStreamInfo(
            codec_name=video_stream.get("codec_name"),
            width=video_stream.get("width"),
            height=video_stream.get("height"),
            duration=_safe_float(
                video_stream.get("duration") or format_info.get("duration")
            ),
            bit_rate=_safe_int(
                video_stream.get("bit_rate") or format_info.get("bit_rate")
            ),
            format_name=format_info.get("format_name"),
        )


def _safe_float(value: Any) -> float | None:
    """Safely convert to float."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _safe_int(value: Any) -> int | None:
    """Safely convert to int."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def probe(
    ffprobe_path: str | None = None,
) -> Callable[[Observable[FetchedSegment]], Observable[FetchedSegment]]:
    """Create a probe operator (pass-through for HLS segments).

    The HlsProber class can be used directly to probe files.

    Args:
        ffprobe_path: Path to ffprobe executable.

    Returns:
        Pass-through operator.
    """

    def operator(
        source: Observable[FetchedSegment],
    ) -> Observable[FetchedSegment]:
        def subscribe(
            observer: ObserverBase[FetchedSegment],
            scheduler: SchedulerBase | None = None,
        ) -> Disposable:
            disposed = False

            def on_next(item: FetchedSegment) -> None:
                if not disposed:
                    observer.on_next(item)

            def on_error(error: Exception) -> None:
                if not disposed:
                    observer.on_error(error)

            def on_completed() -> None:
                if not disposed:
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
