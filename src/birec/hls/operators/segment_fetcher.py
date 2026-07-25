"""SegmentFetcher: download HLS segments with retry and integrity check."""

from __future__ import annotations

import logging
import zlib
from collections.abc import Callable
from dataclasses import dataclass

import aiohttp
from reactivex import Observable
from reactivex.abc import ObserverBase, SchedulerBase
from reactivex.disposable import Disposable

from ..exceptions import SegmentCorruptedError, SegmentFetchError
from ..models import HlsSegment

__all__ = ("fetch_segments", "SegmentFetcher", "FetchedSegment")

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FetchedSegment:
    """A downloaded segment with its data."""

    segment: HlsSegment
    data: bytes
    crc32: int

    @property
    def size(self) -> int:
        return len(self.data)


class SegmentFetcher:
    """Download HLS segments with retry and CRC32 verification."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str = "",
        *,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._max_retries = max_retries

    def _resolve_url(self, uri: str) -> str:
        """Resolve segment URI to full URL."""
        if uri.startswith(("http://", "https://")):
            return uri
        if self._base_url:
            return f"{self._base_url}/{uri.lstrip('/')}"
        return uri

    async def fetch(self, segment: HlsSegment) -> FetchedSegment:
        """Download a segment with retry.

        Args:
            segment: The segment to download.

        Returns:
            FetchedSegment with data and CRC32.

        Raises:
            SegmentFetchError: If download fails after retries.
        """
        url = self._resolve_url(segment.uri)
        last_error: Exception | None = None

        for attempt in range(self._max_retries):
            try:
                async with self._session.get(url, timeout=self._timeout) as resp:
                    if resp.status != 200:
                        raise SegmentFetchError(segment.uri, f"HTTP {resp.status}")
                    data = await resp.read()
                    crc = zlib.crc32(data) & 0xFFFFFFFF
                    return FetchedSegment(segment=segment, data=data, crc32=crc)
            except SegmentFetchError:
                raise
            except Exception as e:
                last_error = e
                logger.warning(
                    "Segment fetch attempt %d/%d failed for %s: %s",
                    attempt + 1,
                    self._max_retries,
                    segment.uri,
                    e,
                )

        raise SegmentFetchError(
            segment.uri,
            f"failed after {self._max_retries} retries: {last_error}",
        )

    async def fetch_init(self, uri: str) -> bytes:
        """Download an initialization segment with retry.

        Args:
            uri: URI of the init segment.

        Returns:
            Raw bytes of the init segment.

        Raises:
            SegmentFetchError: If download fails after retries.
        """
        url = self._resolve_url(uri)
        last_error: Exception | None = None

        for attempt in range(self._max_retries):
            try:
                async with self._session.get(url, timeout=self._timeout) as resp:
                    if resp.status != 200:
                        raise SegmentFetchError(uri, f"HTTP {resp.status}")
                    return await resp.read()
            except SegmentFetchError:
                raise
            except Exception as e:
                last_error = e
                logger.warning(
                    "Init segment fetch attempt %d/%d failed for %s: %s",
                    attempt + 1,
                    self._max_retries,
                    uri,
                    e,
                )

        raise SegmentFetchError(
            uri,
            f"failed after {self._max_retries} retries: {last_error}",
        )

    @staticmethod
    def verify_crc(data: bytes, expected_crc: int) -> None:
        """Verify data integrity with CRC32.

        Raises:
            SegmentCorruptedError: If CRC mismatch.
        """
        actual_crc = zlib.crc32(data) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise SegmentCorruptedError("", expected_crc, actual_crc)


def fetch_segments(
    session: aiohttp.ClientSession,
    base_url: str = "",
    *,
    timeout: float = 30.0,
    max_retries: int = 3,
) -> Callable[[Observable[HlsSegment]], Observable[FetchedSegment]]:
    """Create an operator that fetches segments.

    Note: In the reactive pipeline, actual async fetching is coordinated
    by the StreamRecorder. This operator provides the structure.

    Args:
        session: aiohttp client session.
        base_url: Base URL for resolving relative URIs.
        timeout: Request timeout.
        max_retries: Maximum retry attempts.

    Returns:
        Operator that emits FetchedSegment items.
    """

    def operator(source: Observable[HlsSegment]) -> Observable[FetchedSegment]:
        def subscribe(
            observer: ObserverBase[FetchedSegment],
            scheduler: SchedulerBase | None = None,
        ) -> Disposable:
            disposed = False
            _fetcher = SegmentFetcher(
                session, base_url, timeout=timeout, max_retries=max_retries
            )

            def on_next(segment: HlsSegment) -> None:
                if disposed:
                    return
                # Placeholder: actual async fetch is done by StreamRecorder
                observer.on_next(FetchedSegment(segment=segment, data=b"", crc32=0))

            def on_error(error: Exception) -> None:
                if not disposed:
                    observer.on_error(error)

            def on_completed() -> None:
                if not disposed:
                    observer.on_completed()

            subscription = source.subscribe(
                on_next=on_next,
                on_error=on_error,
                on_completed=on_completed,
                scheduler=scheduler,
            )

            def dispose() -> None:
                nonlocal disposed
                disposed = True
                subscription.dispose()

            return Disposable(dispose)

        return Observable(subscribe)

    return operator
