"""Retry operator with optional count, delay, and predicate."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator

from reactivex import Observable, abc, catch_with_iterable
from reactivex import operators as ops

__all__ = ("retry",)


def retry[T](
    count: int | None = None,
    delay: float | None = None,
    should_retry: Callable[[Exception], bool] = lambda _: True,
) -> Callable[[Observable[T]], Observable[T]]:
    """Resubscribe to the source on error, honouring count/delay/predicate."""

    def _retry(source: Observable[T]) -> Observable[T]:
        def subscribe(
            observer: abc.ObserverBase[T],
            scheduler: abc.SchedulerBase | None = None,
        ) -> abc.DisposableBase:
            exception: Exception | None = None

            def counter() -> Iterator[int]:
                n = 0
                while True:
                    if exception is not None:
                        if not should_retry(exception):
                            break
                        if count is not None and n > count:
                            break
                        if delay:
                            time.sleep(delay)
                    yield n
                    n += 1

            def on_error(exc: Exception) -> None:
                nonlocal exception
                exception = exc

            _source = source.pipe(ops.do_action(on_error=on_error))
            return catch_with_iterable(_source for _ in counter()).subscribe(
                observer, scheduler=scheduler
            )

        return Observable(subscribe)

    return _retry
