"""WBI signing algorithm for Bilibili Web API requests."""

from __future__ import annotations

import hashlib
from typing import Any

__all__ = ("extract_key", "make_key", "encode_value", "build_query")

_MAPPING = (
    46,
    47,
    18,
    2,
    53,
    8,
    23,
    32,
    15,
    50,
    10,
    31,
    58,
    3,
    45,
    35,
    27,
    43,
    5,
    49,
    33,
    9,
    42,
    19,
    29,
    28,
    14,
    39,
    12,
    38,
    41,
    13,
)


def extract_key(url: str) -> str:
    """Extract the WBI key (filename without extension) from a CDN URL."""
    return url.rsplit("/", 1)[-1].rsplit(".", 1)[0]


def make_key(img_key: str, sub_key: str) -> str:
    """Mix img_key and sub_key using the fixed permutation table."""
    raw = (img_key + sub_key).encode()
    return bytes(raw[n] for n in _MAPPING).decode()


def encode_value(value: str) -> str:
    """Percent-encode a value, stripping ``!'()*`` characters."""
    chars: list[str] = []
    for c in value:
        if c in "!'()*":
            continue
        if (c.isascii() and c.isalnum()) or c in "-_.~":
            chars.append(c)
        else:
            for b in c.encode():
                chars.append(f"%{b:02X}")
    return "".join(chars)


def build_query(key: str, ts: int, params: list[tuple[str, Any]]) -> str:
    """Build a WBI-signed query string.

    Appends ``wts``, sorts by key, encodes values, and appends ``w_rid`` MD5.
    """
    params.append(("wts", str(ts)))
    params.sort(key=lambda p: p[0])

    query = "&".join(f"{name}={encode_value(str(value))}" for name, value in params)
    sign = hashlib.md5((query + key).encode()).hexdigest()  # noqa: S324
    return f"{query}&w_rid={sign}"
