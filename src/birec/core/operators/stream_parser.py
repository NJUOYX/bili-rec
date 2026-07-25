"""StreamParser: parses FLV/HLS stream data into segments."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

__all__ = ("StreamParser",)

logger = logging.getLogger(__name__)


class StreamParser:
    """Parses raw stream bytes into logical segments.

    For FLV: detects tag boundaries for splitting.
    For HLS/TS: passes through TS packets (188-byte aligned).
    """

    def __init__(self, stream_type: str = "flv") -> None:
        self._stream_type = stream_type
        self._segment_count: int = 0

    @property
    def stream_type(self) -> str:
        return self._stream_type

    @stream_type.setter
    def stream_type(self, value: str) -> None:
        self._stream_type = value

    @property
    def segment_count(self) -> int:
        return self._segment_count

    def reset(self) -> None:
        self._segment_count = 0

    async def parse(self, chunks: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
        """Parse stream chunks, yielding segments.

        For now, passes through chunks as-is (identity transform).
        Future: implement FLV tag boundary detection for segment splitting.
        """
        async for chunk in chunks:
            yield chunk

    def detect_flv_header(self, data: bytes) -> bool:
        """Detect FLV file header (FLV signature)."""
        return len(data) >= 3 and data[:3] == b"FLV"

    def detect_ts_sync(self, data: bytes) -> bool:
        """Detect TS sync byte (0x47)."""
        return len(data) > 0 and data[0] == 0x47
