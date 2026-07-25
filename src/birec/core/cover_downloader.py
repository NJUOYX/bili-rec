"""CoverDownloader: downloads live cover images with sha1 dedup and retry."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os

import aiohttp

from ..event.event_emitter import EventEmitter, EventListener
from ..utils.mixins import AsyncStoppableMixin

__all__ = ("CoverDownloader", "CoverDownloaderListener")

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY = 1.0


class CoverDownloaderListener(EventListener):
    """Listener interface for CoverDownloader events."""


class CoverDownloader(AsyncStoppableMixin, EventEmitter[CoverDownloaderListener]):
    """Downloads live cover images with sha1 dedup and retry.

    Only saves the cover if its content hash differs from the previous one.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        max_retries: int = _MAX_RETRIES,
        retry_delay: float = _RETRY_DELAY,
    ) -> None:
        super().__init__()
        self._session = session
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._last_hash: str = ""
        self._download_count: int = 0

    @property
    def download_count(self) -> int:
        return self._download_count

    @property
    def last_hash(self) -> str:
        return self._last_hash

    async def _do_start(self) -> None:
        """No-op start (cover download is on-demand)."""

    async def _do_stop(self) -> None:
        """No-op stop."""

    async def download(self, url: str, output_path: str) -> bool:
        """Download cover image from URL.

        Returns True if the cover was saved (new content), False if skipped
        (duplicate) or failed.
        """
        if not url:
            return False

        for attempt in range(self._max_retries):
            try:
                async with self._session.get(url) as resp:
                    if resp.status != 200:
                        logger.warning(
                            "Cover download failed: HTTP %d from %s",
                            resp.status,
                            url,
                        )
                        continue

                    data = await resp.read()
                    content_hash = hashlib.sha1(data).hexdigest()

                    if content_hash == self._last_hash:
                        logger.debug(
                            "Cover unchanged (sha1=%s), skipping",
                            content_hash,
                        )
                        return False

                    dir_path = os.path.dirname(output_path)
                    if dir_path:
                        os.makedirs(dir_path, exist_ok=True)

                    with open(output_path, "wb") as f:
                        f.write(data)

                    self._last_hash = content_hash
                    self._download_count += 1
                    logger.info("Cover saved: %s (sha1=%s)", output_path, content_hash)
                    return True

            except (aiohttp.ClientError, OSError) as e:
                logger.warning(
                    "Cover download attempt %d/%d failed: %s",
                    attempt + 1,
                    self._max_retries,
                    e,
                )
                if attempt < self._max_retries - 1:
                    await asyncio.sleep(self._retry_delay)

        return False
