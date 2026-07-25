"""Probe operator: probe stream using ffprobe."""

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

from .typing import FLVStream, FLVStreamItem

__all__ = ("probe", "Prober", "StreamInfo")

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StreamInfo:
    """Stream information from ffprobe."""

    codec_name: str | None = None
    width: int | None = None
    height: int | None = None
    avg_frame_rate: str | None = None
    bit_rate: int | None = None
    duration: float | None = None


class Prober:
    """Probe media files using ffprobe."""

    def __init__(self, ffprobe_path: str | None = None) -> None:
        self._ffprobe_path = ffprobe_path or shutil.which("ffprobe") or "ffprobe"

    @property
    def available(self) -> bool:
        """Check if ffprobe is available."""
        return shutil.which(self._ffprobe_path) is not None

    async def probe_file(self, path: Path) -> StreamInfo | None:
        """Probe a media file and return stream info."""
        if not self.available:
            logger.warning("ffprobe not available")
            return None

        try:
            result = await asyncio.create_subprocess_exec(
                self._ffprobe_path,
                "-v", "quiet",
                "-print_format", "json",
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

    def _parse_output(self, data: dict[str, Any]) -> StreamInfo:
        """Parse ffprobe JSON output."""
        video_stream = None
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                video_stream = stream
                break

        if video_stream is None:
            return StreamInfo()

        # Parse frame rate
        avg_frame_rate = video_stream.get("avg_frame_rate")
        bit_rate = video_stream.get("bit_rate")
        duration = video_stream.get("duration")

        return StreamInfo(
            codec_name=video_stream.get("codec_name"),
            width=video_stream.get("width"),
            height=video_stream.get("height"),
            avg_frame_rate=avg_frame_rate,
            bit_rate=int(bit_rate) if bit_rate else None,
            duration=float(duration) if duration else None,
        )


def probe(
    ffprobe_path: str | None = None,
) -> Callable[[FLVStream], FLVStream]:
    """Create a probe operator (pass-through, for future use).

    Currently this is a pass-through operator. The Prober class
    can be used directly to probe files.

    Args:
        ffprobe_path: Path to ffprobe executable.

    Returns:
        An operator function (pass-through).
    """

    def operator(source: FLVStream) -> FLVStream:
        def subscribe(
            observer: ObserverBase[FLVStreamItem],
            scheduler: SchedulerBase | None = None,
        ) -> Disposable:
            disposed = False

            def on_next(item: FLVStreamItem) -> None:
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
