"""Analyse operator for HLS: generate metadata from segments."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from reactivex import Observable
from reactivex.abc import ObserverBase, SchedulerBase
from reactivex.disposable import Disposable

from .segment_fetcher import FetchedSegment

__all__ = ("analyse", "HlsAnalyser", "HlsMetadata")

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SegmentMeta:
    """Metadata for a single segment."""

    sequence_number: int
    duration: float
    size: int
    crc32: int


@dataclass(frozen=True, slots=True)
class HlsMetadata:
    """Aggregated metadata for an HLS recording session."""

    total_duration: float = 0.0
    total_size: int = 0
    segment_count: int = 0
    segments: tuple[SegmentMeta, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_duration": self.total_duration,
            "total_size": self.total_size,
            "segment_count": self.segment_count,
            "segments": [
                {
                    "sequence_number": s.sequence_number,
                    "duration": s.duration,
                    "size": s.size,
                    "crc32": s.crc32,
                }
                for s in self.segments
            ],
        }


class HlsAnalyser:
    """Analyse HLS segments and generate metadata."""

    def __init__(self) -> None:
        self._segments: list[SegmentMeta] = []
        self._total_duration: float = 0.0
        self._total_size: int = 0

    def add_segment(self, fetched: FetchedSegment) -> None:
        """Add a fetched segment to the analysis.

        Args:
            fetched: The fetched segment.
        """
        meta = SegmentMeta(
            sequence_number=fetched.segment.sequence_number,
            duration=fetched.segment.duration,
            size=len(fetched.data),
            crc32=fetched.crc32,
        )
        self._segments.append(meta)
        self._total_duration += fetched.segment.duration
        self._total_size += len(fetched.data)

    def get_metadata(self) -> HlsMetadata:
        """Get the aggregated metadata.

        Returns:
            HlsMetadata with all collected segment info.
        """
        return HlsMetadata(
            total_duration=self._total_duration,
            total_size=self._total_size,
            segment_count=len(self._segments),
            segments=tuple(self._segments),
        )

    def dump_metadata(self, path: Path) -> None:
        """Write metadata to a JSON file.

        Args:
            path: Output path for the metadata JSON.
        """
        metadata = self.get_metadata()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(metadata.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.debug("Wrote HLS metadata to %s", path)

    def reset(self) -> None:
        """Reset the analyser state."""
        self._segments.clear()
        self._total_duration = 0.0
        self._total_size = 0


def analyse() -> Callable[[Observable[FetchedSegment]], Observable[FetchedSegment]]:
    """Create an analyse operator that collects segment metadata.

    The HlsAnalyser instance can be accessed to retrieve metadata
    after the stream completes.

    Returns:
        Pass-through operator that collects metadata.
    """

    def operator(
        source: Observable[FetchedSegment],
    ) -> Observable[FetchedSegment]:
        def subscribe(
            observer: ObserverBase[FetchedSegment],
            scheduler: SchedulerBase | None = None,
        ) -> Disposable:
            analyser = HlsAnalyser()
            disposed = False

            def on_next(fetched: FetchedSegment) -> None:
                if disposed:
                    return
                try:
                    analyser.add_segment(fetched)
                    observer.on_next(fetched)
                except Exception as e:
                    logger.error("Error analysing segment: %s", e)
                    observer.on_error(e)

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
