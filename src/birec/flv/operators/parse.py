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
) -> Callable[[Observable[RandomIO]], FLVStream]:
    """Create a parse operator that converts raw IO to FLVStream.

    Args:
        ignore_eof: If True, ignore EOF errors and continue.
        complete_on_eof: If True, complete the stream on EOF.
        backup_timestamp: If True, backup timestamp to stream_id.
        restore_timestamp: If True, restore timestamp from stream_id.

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

            def on_next(stream: RandomIO) -> None:
                nonlocal parser, header, last_tag

                if disposed:
                    return

                if parser is None:
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
                        if complete_on_eof:
                            observer.on_completed()
                        return
                    except FlvDataError as e:
                        observer.on_error(FlvStreamCorruptedError(str(e)))
                        return

                while not disposed:
                    try:
                        tag = parser.parse_tag()
                        parser.parse_previous_tag_size()
                        last_tag = tag
                        observer.on_next(tag)
                    except EOFError:
                        # Insert AVC end sequence tag if last tag was video
                        if last_tag is not None and is_video_tag(last_tag):
                            end_tag = create_avc_end_sequence_tag(
                                offset=last_tag.next_tag_offset,
                                timestamp=last_tag.timestamp,
                            )
                            observer.on_next(end_tag)
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
