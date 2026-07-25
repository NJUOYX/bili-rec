"""Shared aiohttp connector and timeout for Bilibili API requests."""

from __future__ import annotations

import os
import socket

import aiohttp

__all__ = ("get_connector", "timeout")

USE_IPV4_ONLY = bool(os.environ.get("BIREC_IPV4"))

_family: socket.AddressFamily = (
    socket.AF_INET if USE_IPV4_ONLY else socket.AddressFamily(0)
)

timeout = aiohttp.ClientTimeout(total=10)

_connector: aiohttp.TCPConnector | None = None


def get_connector() -> aiohttp.TCPConnector:
    """Return the shared TCPConnector, creating it on first call.

    Must be called from within a running event loop.
    """
    global _connector  # noqa: PLW0603
    if _connector is None or _connector.closed:
        _connector = aiohttp.TCPConnector(family=_family, limit=200)
    return _connector
