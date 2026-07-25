"""ExceptionHandler: general exception handler with logging and recovery."""

from __future__ import annotations

import logging
import traceback

__all__ = ("ExceptionHandler",)

logger = logging.getLogger(__name__)


class ExceptionHandler:
    """General exception handler for the recording pipeline.

    Routes exceptions to appropriate handlers based on type.
    """

    def __init__(self) -> None:
        self._exception_count: int = 0
        self._last_exception: Exception | None = None

    @property
    def exception_count(self) -> int:
        return self._exception_count

    @property
    def last_exception(self) -> Exception | None:
        return self._last_exception

    def handle(self, error: Exception, context: str = "") -> str:
        """Handle an exception and return a recovery action.

        Returns:
            "retry" - retry the operation
            "fallback" - try alternative approach
            "abort" - abort the current operation
            "ignore" - ignore and continue
        """
        self._exception_count += 1
        self._last_exception = error

        if context:
            logger.error(
                "Exception in %s (#%d): %s\n%s",
                context,
                self._exception_count,
                error,
                traceback.format_exc(),
            )
        else:
            logger.error(
                "Exception (#%d): %s\n%s",
                self._exception_count,
                error,
                traceback.format_exc(),
            )

        # Determine action based on exception type
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            return "abort"

        if isinstance(error, (OSError, IOError)):
            return "retry"

        if isinstance(error, ValueError):
            return "fallback"

        return "abort"

    def reset(self) -> None:
        """Reset exception state."""
        self._exception_count = 0
        self._last_exception = None
