"""HLS-specific exceptions."""

from __future__ import annotations

__all__ = (
    "HlsError",
    "PlaylistFetchError",
    "PlaylistParseError",
    "SegmentFetchError",
    "SegmentCorruptedError",
)


class HlsError(Exception):
    """Base exception for HLS operations."""


class PlaylistFetchError(HlsError):
    """Failed to fetch playlist from server."""

    def __init__(self, url: str, reason: str = "") -> None:
        self.url = url
        self.reason = reason
        msg = f"Failed to fetch playlist: {url}"
        if reason:
            msg += f" ({reason})"
        super().__init__(msg)


class PlaylistParseError(HlsError):
    """Failed to parse playlist content."""

    def __init__(self, reason: str = "") -> None:
        self.reason = reason
        msg = "Failed to parse playlist"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)


class SegmentFetchError(HlsError):
    """Failed to fetch a segment."""

    def __init__(self, uri: str, reason: str = "") -> None:
        self.uri = uri
        self.reason = reason
        msg = f"Failed to fetch segment: {uri}"
        if reason:
            msg += f" ({reason})"
        super().__init__(msg)


class SegmentCorruptedError(HlsError):
    """Segment data failed integrity check."""

    def __init__(self, uri: str, expected_crc: int, actual_crc: int) -> None:
        self.uri = uri
        self.expected_crc = expected_crc
        self.actual_crc = actual_crc
        super().__init__(
            f"Segment corrupted: {uri} "
            f"(expected crc32={expected_crc:#010x}, got {actual_crc:#010x})"
        )
