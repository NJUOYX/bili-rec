"""Inject operator: inject metadata into FLV stream."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from reactivex import Observable
from reactivex.abc import ObserverBase, SchedulerBase
from reactivex.disposable import Disposable

from ..common import create_metadata_tag, is_metadata_tag
from ..models import FlvHeader
from .typing import FLVStream, FLVStreamItem

__all__ = ("inject",)

logger = logging.getLogger(__name__)


def inject(
    metadata: dict[str, Any] | None = None,
) -> Callable[[FLVStream], FLVStream]:
    """Create an inject operator that adds metadata to the stream.

    Injects an onMetaData script tag at the beginning of the stream
    (after the header).

    Args:
        metadata: Metadata dictionary to inject. If None, no injection.

    Returns:
        An operator function that injects metadata.
    """

    def operator(source: FLVStream) -> FLVStream:
        def subscribe(
            observer: ObserverBase[FLVStreamItem],
            scheduler: SchedulerBase | None = None,
        ) -> Disposable:
            header_emitted = False
            metadata_injected = False
            disposed = False

            def on_next(item: FLVStreamItem) -> None:
                nonlocal header_emitted, metadata_injected

                if disposed:
                    return

                # Emit header first
                if isinstance(item, FlvHeader):
                    observer.on_next(item)
                    header_emitted = True

                    # Inject metadata after header
                    if metadata is not None and not metadata_injected:
                        metadata_tag = create_metadata_tag(metadata)
                        observer.on_next(metadata_tag)
                        metadata_injected = True
                    return

                # Skip existing metadata tags if we're injecting new ones
                if metadata is not None and is_metadata_tag(item):
                    logger.debug("Skipping existing metadata tag")
                    return

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
