"""StreamURLResolver: resolves stream URLs with CDN fallback."""

from __future__ import annotations

import logging

from ...bili.live import Live

__all__ = ("StreamURLResolver",)

logger = logging.getLogger(__name__)


class StreamURLResolver:
    """Resolves stream URLs from Live, handles CDN fallback.

    Given stream format/codec/quality parameters, fetches the best available
    stream URL. Falls back to alternative CDN if the primary fails.
    """

    def __init__(self, live: Live) -> None:
        self._live = live
        self._last_host: str = ""

    async def resolve(
        self,
        stream_format: str = "flv",
        stream_codec: str = "avc",
        quality_number: int = 10000,
    ) -> str:
        """Resolve a stream URL with the given parameters.

        Returns the stream URL string.
        """
        url = await self._live.get_stream_url(
            stream_format=stream_format,  # type: ignore[arg-type]
            stream_codec=stream_codec,  # type: ignore[arg-type]
            quality_number=quality_number,  # type: ignore[arg-type]
        )
        # Extract host from URL for tracking
        from urllib.parse import urlparse

        parsed = urlparse(url)
        self._last_host = parsed.hostname or ""
        return url

    async def resolve_alternative(
        self,
        stream_format: str = "flv",
        stream_codec: str = "avc",
        quality_number: int = 10000,
    ) -> str:
        """Resolve an alternative stream URL (different CDN host)."""
        url = await self._live.select_alternative(
            stream_format=stream_format,  # type: ignore[arg-type]
            stream_codec=stream_codec,  # type: ignore[arg-type]
            quality_number=quality_number,  # type: ignore[arg-type]
            exclude_host=self._last_host,
        )
        from urllib.parse import urlparse

        parsed = urlparse(url)
        self._last_host = parsed.hostname or ""
        return url

    @property
    def last_host(self) -> str:
        return self._last_host
