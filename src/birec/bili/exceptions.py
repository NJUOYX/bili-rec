"""Bilibili API domain exceptions."""

from __future__ import annotations

import aiohttp

__all__ = (
    "ApiRequestError",
    "DanmakuClientAuthError",
    "LiveRoomHidden",
    "LiveRoomLocked",
    "LiveRoomEncrypted",
    "NoStreamAvailable",
    "NoStreamFormatAvailable",
    "NoStreamCodecAvailable",
    "NoStreamQualityAvailable",
    "NoAlternativeStreamAvailable",
)


class ApiRequestError(Exception):
    """Non-zero code returned by a Bilibili API endpoint."""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"code={code} message={message}")


class DanmakuClientAuthError(aiohttp.ClientError):
    """WebSocket authentication failed during danmaku handshake."""


class LiveRoomHidden(Exception):
    """Room is hidden from public listing."""


class LiveRoomLocked(Exception):
    """Room is locked by the platform."""


class LiveRoomEncrypted(Exception):
    """Room requires a password to enter."""


class NoStreamAvailable(Exception):
    """No live stream is currently available for this room."""


class NoStreamFormatAvailable(Exception):
    """Requested stream format (flv/ts/fmp4) is not offered."""


class NoStreamCodecAvailable(Exception):
    """Requested stream codec (avc/hevc) is not offered."""


class NoStreamQualityAvailable(Exception):
    """Requested quality number is not in the accepted list."""


class NoAlternativeStreamAvailable(Exception):
    """No alternative CDN stream is available."""
