"""FLV exceptions."""

from __future__ import annotations

__all__ = (
    "FlvDataError",
    "FlvHeaderError",
    "FlvTagError",
    "FlvStreamCorruptedError",
    "FlvFileCorruptedError",
)


class FlvDataError(ValueError):
    """Base exception for FLV data errors."""


class FlvHeaderError(FlvDataError):
    """Invalid FLV header."""


class FlvTagError(FlvDataError):
    """Invalid FLV tag."""


class FlvStreamCorruptedError(Exception):
    """FLV stream is corrupted."""


class FlvFileCorruptedError(Exception):
    """FLV file is corrupted."""
