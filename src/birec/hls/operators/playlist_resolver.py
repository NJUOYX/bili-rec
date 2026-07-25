"""PlaylistResolver: track and emit only new segments."""

from __future__ import annotations

import logging
from collections.abc import Callable

from reactivex import Observable
from reactivex.abc import ObserverBase, SchedulerBase
from reactivex.disposable import Disposable

from ..models import HlsPlaylist, HlsSegment

__all__ = ("resolve_playlist", "PlaylistResolver")

logger = logging.getLogger(__name__)


class PlaylistResolver:
    """Resolve new segments from successive playlists.

    Tracks media sequence numbers to only emit segments that
    haven't been seen before.
    """

    def __init__(self) -> None:
        self._last_sequence: int = -1
        self._init_segment_uri: str | None = None

    @property
    def last_sequence(self) -> int:
        """Last emitted segment sequence number."""
        return self._last_sequence

    def resolve(self, playlist: HlsPlaylist) -> list[HlsSegment]:
        """Extract new segments from a playlist.

        Args:
            playlist: The latest playlist.

        Returns:
            List of new segments not previously emitted.
        """
        new_segments: list[HlsSegment] = []

        # Track init segment changes
        if playlist.init_segment is not None:
            self._init_segment_uri = playlist.init_segment.uri

        for segment in playlist.segments:
            if segment.sequence_number > self._last_sequence:
                new_segments.append(segment)
                self._last_sequence = segment.sequence_number

        if new_segments:
            logger.debug(
                "Resolved %d new segments (seq %d-%d)",
                len(new_segments),
                new_segments[0].sequence_number,
                new_segments[-1].sequence_number,
            )

        return new_segments

    def reset(self) -> None:
        """Reset tracking state."""
        self._last_sequence = -1
        self._init_segment_uri = None


def resolve_playlist() -> Callable[[Observable[HlsPlaylist]], Observable[HlsSegment]]:
    """Create an operator that resolves new segments from playlists.

    Emits only segments that haven't been seen before based on
    media sequence number tracking.

    Returns:
        Operator that emits new HlsSegment items.
    """

    def operator(source: Observable[HlsPlaylist]) -> Observable[HlsSegment]:
        def subscribe(
            observer: ObserverBase[HlsSegment],
            scheduler: SchedulerBase | None = None,
        ) -> Disposable:
            resolver = PlaylistResolver()
            disposed = False

            def on_next(playlist: HlsPlaylist) -> None:
                if disposed:
                    return
                try:
                    new_segments = resolver.resolve(playlist)
                    for segment in new_segments:
                        observer.on_next(segment)
                except Exception as e:
                    logger.error("Error resolving playlist: %s", e)
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
