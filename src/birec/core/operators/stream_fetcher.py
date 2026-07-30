"""StreamFetcher: fetches stream data from a URL via HTTP."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

import aiohttp

__all__ = ("StreamFetcher",)

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 64 * 1024  # 64KB

# Headers required by Bilibili CDN anti-hotlinking.
_STREAM_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    ),
    "Referer": "https://live.bilibili.com/",
    "Origin": "https://live.bilibili.com",
}


class StreamFetcher:
    """Fetches stream data from a URL, yielding chunks asynchronously."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        chunk_size: int = _CHUNK_SIZE,
        timeout: float = 30.0,
    ) -> None:
        self._session = session
        self._chunk_size = chunk_size
        self._timeout = aiohttp.ClientTimeout(
            total=None,
            connect=timeout,
            sock_read=timeout,
        )
        self._current_url: str = ""
        self._bytes_fetched: int = 0

    @property
    def current_url(self) -> str:
        return self._current_url

    @property
    def bytes_fetched(self) -> int:
        return self._bytes_fetched

    def reset_bytes(self) -> None:
        self._bytes_fetched = 0

    async def fetch(self, url: str) -> AsyncIterator[bytes]:
        """Fetch stream data from URL, yielding chunks.

        Raises aiohttp.ClientError on connection issues.
        """
        self._current_url = url
        self._bytes_fetched = 0

        async with self._session.get(
            url, timeout=self._timeout, headers=_STREAM_HEADERS
        ) as resp:
            resp.raise_for_status()
            async for chunk in resp.content.iter_chunked(self._chunk_size):
                self._bytes_fetched += len(chunk)
                yield chunk

    async def fetch_flv(self, url: str) -> AsyncIterator[bytes]:
        """Fetch FLV stream data."""
        async for chunk in self.fetch(url):
            yield chunk

    async def fetch_ts(self, url: str) -> AsyncIterator[bytes]:
        """Fetch TS/HLS stream data."""
        async for chunk in self.fetch(url):
            yield chunk
