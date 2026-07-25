"""PlaylistDumper: maintain playlist state and detect segment loss."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from reactivex import Observable
from reactivex.abc import ObserverBase, SchedulerBase
from reactivex.disposable import Disposable

from ..models import HlsPlaylist, HlsSegment

__all__ = ("dump_playlist", "PlaylistDumper")

logger = logging.getLogger(__name__)


class PlaylistDumper:
    """Maintain playlist state and detect segment gaps.

    Tracks total duration, sequence numbers, and detects when
    segments are missing (gaps in sequence numbers).
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._total_duration: float = 0.0
        self._last_sequence: int = -1
        self._segment_count: int = 0
        self._lost_segments: int = 0
        self._playlists_written: int = 0

    @property
    def total_duration(self) -> float:
        """Total accumulated duration in seconds."""
        return self._total_duration

    @property
    def segment_count(self) -> int:
        """Total segments processed."""
        return self._segment_count

    @property
    def lost_segments(self) -> int:
        """Number of detected lost/missing segments."""
        return self._lost_segments

    def update(self, playlist: HlsPlaylist) -> int:
        """Update state from a new playlist.

        Detects gaps in sequence numbers indicating lost segments.

        Args:
            playlist: The latest playlist.

        Returns:
            Number of new segments in this playlist.
        """
        new_count = 0
        for segment in playlist.segments:
            if self._last_sequence >= 0:
                expected = self._last_sequence + 1
                if segment.sequence_number > expected:
                    gap = segment.sequence_number - expected
                    self._lost_segments += gap
                    logger.warning(
                        "Detected %d lost segments (seq %d-%d)",
                        gap,
                        expected,
                        segment.sequence_number - 1,
                    )

            if segment.sequence_number > self._last_sequence:
                self._total_duration += segment.duration
                self._segment_count += 1
                self._last_sequence = segment.sequence_number
                new_count += 1

        return new_count

    def add_segment(self, segment: HlsSegment) -> None:
        """Add a single segment to tracking.

        Args:
            segment: The segment to add.
        """
        if self._last_sequence >= 0:
            expected = self._last_sequence + 1
            if segment.sequence_number > expected:
                gap = segment.sequence_number - expected
                self._lost_segments += gap
                logger.warning(
                    "Detected %d lost segments (seq %d-%d)",
                    gap,
                    expected,
                    segment.sequence_number - 1,
                )

        self._total_duration += segment.duration
        self._segment_count += 1
        self._last_sequence = segment.sequence_number

    def dump(self, playlist: HlsPlaylist) -> None:
        """Write playlist to file if path is set.

        Args:
            playlist: The playlist to write.
        """
        if self._path is None:
            return

        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(playlist.raw_text, encoding="utf-8")
        self._playlists_written += 1
        logger.debug("Wrote playlist to %s", self._path)

    def reset(self) -> None:
        """Reset all tracking state."""
        self._total_duration = 0.0
        self._last_sequence = -1
        self._segment_count = 0
        self._lost_segments = 0
        self._playlists_written = 0


def dump_playlist(
    path: Path | None = None,
) -> Callable[[Observable[HlsPlaylist]], Observable[HlsPlaylist]]:
    """Create an operator that tracks and optionally writes playlists.

    Args:
        path: Optional path to write playlist files.

    Returns:
        Operator that passes through playlists while tracking state.
    """

    def operator(
        source: Observable[HlsPlaylist],
    ) -> Observable[HlsPlaylist]:
        def subscribe(
            observer: ObserverBase[HlsPlaylist],
            scheduler: SchedulerBase | None = None,
        ) -> Disposable:
            dumper = PlaylistDumper(path)
            disposed = False

            def on_next(playlist: HlsPlaylist) -> None:
                if disposed:
                    return
                try:
                    dumper.update(playlist)
                    dumper.dump(playlist)
                    observer.on_next(playlist)
                except Exception as e:
                    logger.error("Error in playlist dumper: %s", e)
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
