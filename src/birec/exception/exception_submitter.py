"""Utilities for submitting exceptions to the ExceptionCenter."""

from __future__ import annotations

from concurrent.futures import Future
from types import TracebackType

from .exception_center import ExceptionCenter

__all__ = ("ExceptionSubmitter", "submit_exception", "exception_callback")


def submit_exception(exc: BaseException) -> None:
    """Push an exception to the global ExceptionCenter."""
    ExceptionCenter.get_instance().submit(exc)


class ExceptionSubmitter:
    """Context manager that catches any exception and submits it to the center."""

    def __enter__(self) -> ExceptionSubmitter:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        if exc_val is not None:
            submit_exception(exc_val)
        return True  # suppress the exception


def exception_callback(future: Future[object]) -> None:
    """Callback for asyncio/concurrent Futures: extract and submit the exception."""
    if future.cancelled():
        return
    exc = future.exception()
    if exc is not None:
        submit_exception(exc)
