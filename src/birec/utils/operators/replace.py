"""Operator that renames a file once the source completes."""

from __future__ import annotations

import os
from collections.abc import Callable

from reactivex import Observable, abc

__all__ = ("replace",)


def replace[T](
    src_path: str, dst_path: str
) -> Callable[[Observable[T]], Observable[T]]:
    """Atomically rename ``src_path`` to ``dst_path`` on completion."""

    def _replace(source: Observable[T]) -> Observable[T]:
        def subscribe(
            observer: abc.ObserverBase[T],
            scheduler: abc.SchedulerBase | None = None,
        ) -> abc.DisposableBase:
            def on_completed() -> None:
                try:
                    os.replace(src_path, dst_path)
                except Exception as exc:
                    observer.on_error(exc)
                else:
                    observer.on_completed()

            return source.subscribe(
                observer.on_next, observer.on_error, on_completed, scheduler=scheduler
            )

        return Observable(subscribe)

    return _replace
