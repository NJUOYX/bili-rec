"""String helpers: case conversion and cookie field extraction."""

from __future__ import annotations

import re

__all__ = (
    "snake_case",
    "camel_case",
    "extract_uid_from_cookie",
    "extract_buvid_from_cookie",
)


def snake_case(string: str) -> str:
    """Convert a camelCase string to snake_case."""
    return re.sub(
        r"([a-z0-9])([A-Z])", lambda m: m.group(1) + "_" + m.group(2).lower(), string
    )


def camel_case(string: str) -> str:
    """Convert a snake_case string to camelCase."""
    words = string.split("_")
    return "".join([words[0].casefold(), *(w.capitalize() for w in words[1:])])


def extract_uid_from_cookie(cookie: str) -> int | None:
    """Extract the ``DedeUserID`` (uid) from a cookie string."""
    match = re.search(r"DedeUserID=(\d+)", cookie)
    return int(match.group(1)) if match else None


def extract_buvid_from_cookie(cookie: str) -> str | None:
    """Extract the ``buvid3`` value from a cookie string."""
    match = re.search(r"buvid3=([\w-]+)", cookie)
    return match.group(1) if match else None
