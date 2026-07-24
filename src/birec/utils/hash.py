"""Checksum and message-digest helpers over bytes or file paths."""

from __future__ import annotations

import hashlib
import os
import zlib
from typing import Final

__all__ = ("cksum", "md5sum", "sha1sum")

CHUNK_SIZE: Final[int] = 8192

_PathOrBytes = bytes | str | os.PathLike[str]


def cksum(data_or_path: _PathOrBytes) -> str:
    """Compute the CRC32 checksum of ``data_or_path`` as a hex string."""
    if isinstance(data_or_path, bytes):
        return format(zlib.crc32(data_or_path, 0) & 0xFFFFFFFF, "x")

    value = 0
    with open(data_or_path, "rb") as f:
        while data := f.read(CHUNK_SIZE):
            value = zlib.crc32(data, value)
    return format(value & 0xFFFFFFFF, "x")


def _hexdigest(algorithm: str, data_or_path: _PathOrBytes) -> str:
    digest = hashlib.new(algorithm)
    if isinstance(data_or_path, bytes):
        digest.update(data_or_path)
        return digest.hexdigest()

    with open(data_or_path, "rb") as f:
        while data := f.read(CHUNK_SIZE):
            digest.update(data)
    return digest.hexdigest()


def md5sum(data_or_path: _PathOrBytes) -> str:
    """Compute the MD5 digest of ``data_or_path`` as a hex string."""
    return _hexdigest("md5", data_or_path)


def sha1sum(data_or_path: _PathOrBytes) -> str:
    """Compute the SHA1 digest of ``data_or_path`` as a hex string."""
    return _hexdigest("sha1", data_or_path)
