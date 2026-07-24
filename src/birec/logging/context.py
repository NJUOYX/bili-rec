"""Bind an object's ``_logger_context`` for the duration of an async method."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from loguru import logger

__all__ = ("async_task_with_logger_context",)


def async_task_with_logger_context[T](
    func: Callable[..., Awaitable[T]],
) -> Callable[..., Awaitable[T]]:
    @wraps(func)
    async def wrapper(obj: Any, *args: Any, **kwargs: Any) -> T:
        with logger.contextualize(**obj._logger_context):
            return await func(obj, *args, **kwargs)

    return wrapper
