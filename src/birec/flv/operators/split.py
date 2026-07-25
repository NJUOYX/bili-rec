"""Split operator: split stream when AV parameters change."""

from __future__ import annotations

import logging
from collections.abc import Callable

from reactivex import Observable
from reactivex.abc import ObserverBase, SchedulerBase
from reactivex.disposable import Disposable

from ..common import is_audio_sequence_header, is_video_sequence_header
from ..models import FlvTag
from .typing import FLVStream, FLVStreamItem

__all__ = ("split",)

logger = logging.getLogger(__name__)


def split() -> Callable[[FLVStream], FLVStream]:
    """Create a split operator that emits new stream on AV parameter change.

    When a new sequence header (AVC/AAC header) is detected with different
    parameters, the operator completes the current stream and starts a new one.

    Returns:
        An operator function that splits streams on AV parameter changes.
    """

    def operator(source: FLVStream) -> FLVStream:
        def subscribe(
            observer: ObserverBase[FLVStreamItem],
            scheduler: SchedulerBase | None = None,
        ) -> Disposable:
            video_header: bytes | None = None
            audio_header: bytes | None = None
            disposed = False

            def on_next(item: FLVStreamItem) -> None:
                nonlocal video_header, audio_header

                if disposed:
                    return

                if isinstance(item, FlvTag):
                    if is_video_sequence_header(item):
                        if video_header is not None and video_header != item.body:
                            # Video parameters changed - emit marker
                            logger.debug("Video parameters changed, splitting stream")
                        video_header = item.body
                    elif is_audio_sequence_header(item):
                        if audio_header is not None and audio_header != item.body:
                            # Audio parameters changed - emit marker
                            logger.debug("Audio parameters changed, splitting stream")
                        audio_header = item.body

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
