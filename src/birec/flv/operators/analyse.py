"""Analyse operator: analyze FLV stream and generate metadata."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from reactivex import Observable
from reactivex.abc import ObserverBase, SchedulerBase
from reactivex.disposable import Disposable

from ..avc import extract_resolution
from ..common import is_video_nalu_keyframe, is_video_sequence_header
from ..models import FlvTag
from .typing import FLVStream, FLVStreamItem

__all__ = ("analyse", "Analyser", "StreamProfile")

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StreamProfile:
    """Stream profile information."""

    width: int | None = None
    height: int | None = None
    framerate: float | None = None
    duration: float | None = None


@dataclass
class Analyser:
    """Analyze FLV stream and collect metadata."""

    width: int | None = None
    height: int | None = None
    first_timestamp: int | None = None
    last_timestamp: int | None = None
    keyframe_count: int = 0
    keyframe_timestamps: list[int] = field(default_factory=list)
    keyframe_offsets: list[int] = field(default_factory=list)

    def process(self, item: FLVStreamItem) -> None:
        """Process a stream item."""
        if not isinstance(item, FlvTag):
            return

        # Track timestamps
        if self.first_timestamp is None:
            self.first_timestamp = item.timestamp
        self.last_timestamp = item.timestamp

        # Extract resolution from video sequence header
        if is_video_sequence_header(item) and self.width is None:
            resolution = extract_resolution(item.body)
            if resolution is not None:
                self.width = resolution.width
                self.height = resolution.height

        # Track keyframes
        if is_video_nalu_keyframe(item):
            self.keyframe_count += 1
            self.keyframe_timestamps.append(item.timestamp)
            self.keyframe_offsets.append(item.offset)

    @property
    def duration(self) -> float | None:
        """Get stream duration in seconds."""
        if self.first_timestamp is not None and self.last_timestamp is not None:
            return (self.last_timestamp - self.first_timestamp) / 1000.0
        return None

    def get_metadata(self) -> dict[str, Any]:
        """Get metadata dictionary."""
        metadata: dict[str, Any] = {}

        if self.width is not None:
            metadata["width"] = float(self.width)
        if self.height is not None:
            metadata["height"] = float(self.height)
        if self.duration is not None:
            metadata["duration"] = self.duration

        # Add keyframe index (yamdi style)
        if self.keyframe_timestamps:
            metadata["keyframes"] = {
                "times": [ts / 1000.0 for ts in self.keyframe_timestamps],
                "filepositions": [float(off) for off in self.keyframe_offsets],
            }

        return metadata

    def get_profile(self) -> StreamProfile:
        """Get stream profile."""
        return StreamProfile(
            width=self.width,
            height=self.height,
            duration=self.duration,
        )


def analyse() -> Callable[[FLVStream], FLVStream]:
    """Create an analyse operator that collects stream metadata.

    The operator passes through all items while collecting metadata
    about the stream (resolution, duration, keyframes).

    Returns:
        An operator function that analyzes the stream.
    """

    def operator(source: FLVStream) -> FLVStream:
        def subscribe(
            observer: ObserverBase[FLVStreamItem],
            scheduler: SchedulerBase | None = None,
        ) -> Disposable:
            analyser = Analyser()
            disposed = False

            def on_next(item: FLVStreamItem) -> None:
                if disposed:
                    return

                analyser.process(item)
                observer.on_next(item)

            def on_error(error: Exception) -> None:
                if not disposed:
                    observer.on_error(error)

            def on_completed() -> None:
                if not disposed:
                    logger.debug(
                        "Stream analysis complete: %dx%d, duration=%.2fs, keyframes=%d",
                        analyser.width or 0,
                        analyser.height or 0,
                        analyser.duration or 0,
                        analyser.keyframe_count,
                    )
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
