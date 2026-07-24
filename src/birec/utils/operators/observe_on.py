"""Operator that observes emissions on a dedicated worker thread."""

from __future__ import annotations

from collections.abc import Callable
from queue import Queue
from threading import Thread, current_thread
from typing import Any

from loguru import logger
from reactivex import Observable, abc
from reactivex.disposable import CompositeDisposable, Disposable, SerialDisposable

__all__ = ("observe_on_new_thread",)


def observe_on_new_thread[T](
    queue_size: int | None = None,
    thread_name: str | None = None,
    logger_context: dict[str, Any] | None = None,
) -> Callable[[Observable[T]], Observable[T]]:
    """Deliver notifications on a private daemon thread with a bounded queue."""

    def observe_on(source: Observable[T]) -> Observable[T]:
        def subscribe(
            observer: abc.ObserverBase[T],
            scheduler: abc.SchedulerBase | None = None,
        ) -> abc.DisposableBase:
            disposed = False
            subscription = SerialDisposable()
            queue: Queue[Callable[..., Any]] = Queue(maxsize=queue_size or 0)

            def run() -> None:
                with logger.contextualize(**(logger_context or {})):
                    while not disposed:
                        queue.get()()

            thread = Thread(target=run, name=thread_name, daemon=True)
            thread.start()

            def on_next(value: T) -> None:
                queue.put(lambda: observer.on_next(value))

            def on_error(exc: Exception) -> None:
                queue.put(lambda: observer.on_error(exc))

            def on_completed() -> None:
                queue.put(lambda: observer.on_completed())

            def dispose() -> None:
                nonlocal disposed
                disposed = True
                queue.put(lambda: None)
                if thread is not current_thread():
                    thread.join()

            subscription.disposable = source.subscribe(
                on_next, on_error, on_completed, scheduler=scheduler
            )

            return CompositeDisposable(subscription, Disposable(dispose))

        return Observable(subscribe)

    return observe_on
