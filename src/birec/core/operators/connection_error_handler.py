"""ConnectionErrorHandler: handles connection errors with retry logic."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

__all__ = ("ConnectionErrorHandler",)

logger = logging.getLogger(__name__)


class ConnectionErrorHandler:
    """Handles connection errors with exponential backoff retry."""

    def __init__(
        self,
        *,
        max_retries: int = 5,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
    ) -> None:
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._retry_count: int = 0
        self._on_retry: Callable[[int, float], None] | None = None
        self._on_exhausted: Callable[[], None] | None = None

    @property
    def retry_count(self) -> int:
        return self._retry_count

    @property
    def max_retries(self) -> int:
        return self._max_retries

    def set_callbacks(
        self,
        on_retry: Callable[[int, float], None] | None = None,
        on_exhausted: Callable[[], None] | None = None,
    ) -> None:
        self._on_retry = on_retry
        self._on_exhausted = on_exhausted

    def should_retry(self) -> bool:
        """Check if we should retry."""
        return self._retry_count < self._max_retries

    def get_delay(self) -> float:
        """Get the delay before next retry (exponential backoff)."""
        delay: float = min(
            self._base_delay * (2**self._retry_count),
            self._max_delay,
        )
        return delay

    async def wait_retry(self) -> bool:
        """Wait for the retry delay. Returns False if retries exhausted."""
        if not self.should_retry():
            if self._on_exhausted:
                self._on_exhausted()
            return False

        delay = self.get_delay()
        self._retry_count += 1
        logger.info(
            "Connection error, retry %d/%d in %.1fs",
            self._retry_count,
            self._max_retries,
            delay,
        )
        if self._on_retry:
            self._on_retry(self._retry_count, delay)
        await asyncio.sleep(delay)
        return True

    def reset(self) -> None:
        """Reset retry counter."""
        self._retry_count = 0

    def record_success(self) -> None:
        """Record a successful connection."""
        if self._retry_count > 0:
            logger.info("Connection restored after %d retries", self._retry_count)
        self._retry_count = 0
