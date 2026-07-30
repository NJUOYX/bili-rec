"""Parse operator: convert raw IO stream to FLVStream."""

from __future__ import annotations

import logging
from collections.abc import Callable

from reactivex import Observable
from reactivex.abc import ObserverBase, SchedulerBase
from reactivex.disposable import Disposable

from ..common import create_avc_end_sequence_tag, is_video_tag
from ..exceptions import FlvDataError, FlvStreamCorruptedError
from ..format import FlvParser
from ..models import FlvHeader, FlvTag
from ..struct_io import RandomIO
from .typing import FLVStream, FLVStreamItem

__all__ = ("parse",)

logger = logging.getLogger(__name__)


def parse(
    *,
    ignore_eof: bool = False,
    complete_on_eof: bool = True,
    backup_timestamp: bool = False,
    restore_timestamp: bool = False,
    resumable: bool = False,
) -> Callable[[Observable[RandomIO]], FLVStream]:
    """Create a parse operator that converts raw IO to FLVStream.

    Args:
        ignore_eof: If True, ignore EOF errors and continue.
        complete_on_eof: If True, complete the stream on EOF.
        backup_timestamp: If True, backup timestamp to stream_id.
        restore_timestamp: If True, restore timestamp from stream_id.
        resumable: If True, every emission is treated as more bytes appended to
            the same growing stream (see ``flv.stream_buffer.StreamBuffer``):
            running out of data rewinds to the start of the unfinished tag and
            waits for the next emission instead of ending the FLVStream. Use
            this for live downloads, where EOF only means "not yet arrived".

    Returns:
        An operator function that transforms Observable[RandomIO] to FLVStream.
    """

    def operator(source: Observable[RandomIO]) -> FLVStream:
        def subscribe(
            observer: ObserverBase[FLVStreamItem],
            scheduler: SchedulerBase | None = None,
        ) -> Disposable:
            parser: FlvParser | None = None
            header: FlvHeader | None = None
            last_tag: FlvTag | None = None
            disposed = False

            def emit_end_sequence() -> None:
                """Close off a video stream with an AVC end sequence tag.

                Idempotent: clearing ``last_tag`` keeps a second call (source
                completion after an EOF) from appending a duplicate tag.
                """
                nonlocal last_tag
                if last_tag is not None and is_video_tag(last_tag):
                    observer.on_next(
                        create_avc_end_sequence_tag(
                            offset=last_tag.next_tag_offset,
                            timestamp=last_tag.timestamp,
                        )
                    )
                last_tag = None

            def on_next(stream: RandomIO) -> None:
                nonlocal parser, header, last_tag

                if disposed:
                    return

                if parser is None:
                    start = stream.tell()
                    parser = FlvParser(
                        stream,
                        backup_timestamp=backup_timestamp,
                        restore_timestamp=restore_timestamp,
                    )
                    try:
                        header = parser.parse_header()
                        parser.parse_previous_tag_size()
                        observer.on_next(header)
                    except EOFError:
                        if resumable:
                            # Header split across chunks: retry from scratch
                            # once the rest of it arrives.
                            parser = None
                            stream.seek(start)
                            return
                        if complete_on_eof:
                            observer.on_completed()
                        return
                    except FlvDataError as e:
                        observer.on_error(FlvStreamCorruptedError(str(e)))
                        return

                while not disposed:
                    tag_offset = stream.tell()
                    try:
                        tag = parser.parse_tag()
                        parser.parse_previous_tag_size()
                        last_tag = tag
                        observer.on_next(tag)
                    except EOFError:
                        if resumable:
                            # Partial tag: rewind so the next emission reparses
                            # it whole, and keep the FLVStream open.
                            stream.seek(tag_offset)
                            return
                        emit_end_sequence()
                        if complete_on_eof:
                            observer.on_completed()
                        return
                    except FlvDataError as e:
                        if ignore_eof:
                            logger.debug("Ignoring FLV data error: %s", e)
                            return
                        observer.on_error(FlvStreamCorruptedError(str(e)))
                        return

            def on_error(error: Exception) -> None:
                if not disposed:
                    observer.on_error(error)

            def on_completed() -> None:
                if not disposed:
                    emit_end_sequence()
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
