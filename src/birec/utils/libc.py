"""Thin ctypes wrapper over libc for heap trimming."""

from __future__ import annotations

from contextlib import suppress
from ctypes import cdll
from ctypes.util import find_library

__all__ = ("malloc_trim",)

_lib_name = find_library("c")
_libc = cdll.LoadLibrary(_lib_name) if _lib_name else None


def malloc_trim(pad: int = 0) -> bool:
    """Release free memory from the top of the heap back to the OS."""
    assert pad >= 0, "pad must be >= 0"
    if _libc is None:
        return False
    with suppress(Exception):
        return bool(_libc.malloc_trim(pad) == 1)
    return False
