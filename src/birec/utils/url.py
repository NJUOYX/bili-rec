"""URL helpers."""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlparse, urlunparse

__all__ = ("ensure_scheme",)


def ensure_scheme(url: str, scheme: Literal["http", "https"]) -> str:
    """Return ``url`` with its scheme replaced by ``scheme``."""
    return urlunparse(urlparse(url)._replace(scheme=scheme))
