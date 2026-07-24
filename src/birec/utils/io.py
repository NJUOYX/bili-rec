"""Threaded blocking-call helper with timeout."""

from __future__ import annotations

import atexit
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as _FutureTimeoutError
from typing import Any

__all__ = ("wait_for",)

_executor: ThreadPoolExecutor | None = None


def wait_for[T](
    func: Callable[..., T],
    *,
    args: Iterable[Any] = (),
    kwargs: Mapping[str, Any] | None = None,
    timeout: float,
) -> T:
    """Run ``func`` in a worker thread and wait up to ``timeout`` seconds."""
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=200, thread_name_prefix="wait_for")
        atexit.register(_executor.shutdown)

    future = _executor.submit(func, *args, **(kwargs or {}))
    try:
        return future.result(timeout=timeout)
    except _FutureTimeoutError:
        raise TimeoutError(timeout, func, args, kwargs) from None
