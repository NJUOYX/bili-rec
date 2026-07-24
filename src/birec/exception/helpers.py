"""Exception formatting helpers."""

from __future__ import annotations

import traceback

__all__ = ("format_exception",)


def format_exception(exc: BaseException) -> str:
    """Format an exception with its full traceback as a string."""
    return "".join(traceback.format_exception(exc))
