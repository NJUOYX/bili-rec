"""RequestExceptionHandler: handles request-level exceptions."""

from __future__ import annotations

import logging

__all__ = ("RequestExceptionHandler",)

logger = logging.getLogger(__name__)


class RequestExceptionHandler:
    """Handles request-level exceptions (HTTP errors, timeouts, etc.)."""

    def __init__(self) -> None:
        self._error_count: int = 0
        self._last_error: str = ""

    @property
    def error_count(self) -> int:
        return self._error_count

    @property
    def last_error(self) -> str:
        return self._last_error

    def handle(self, error: Exception) -> str:
        """Handle an exception and return a recovery action.

        Returns:
            "retry" - retry the request
            "fallback" - try alternative
            "abort" - abort recording
        """
        self._error_count += 1
        self._last_error = str(error)

        error_type = type(error).__name__

        if "TimeoutError" in error_type or "timeout" in str(error).lower():
            logger.warning("Request timeout (#%d): %s", self._error_count, error)
            return "retry"

        if "ClientError" in error_type or "ConnectionError" in error_type:
            logger.warning("Connection error (#%d): %s", self._error_count, error)
            return "fallback"

        if "HTTPError" in error_type:
            logger.warning("HTTP error (#%d): %s", self._error_count, error)
            return "fallback"

        logger.error("Unknown error (#%d): %s", self._error_count, error)
        return "abort"

    def reset(self) -> None:
        """Reset error state."""
        self._error_count = 0
        self._last_error = ""
