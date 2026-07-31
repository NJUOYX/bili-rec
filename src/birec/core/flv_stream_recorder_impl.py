"""FLV stream download loop implementation.

Resolves stream URL → fetches via HTTP → feeds into FLV pipeline → updates
statistics. Handles connection errors with retry and CDN fallback.

Design reference: backend-design.md §5.4.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path
from urllib.parse import urlparse

import aiohttp

from ..bili.live import Live
from .operators.connection_error_handler import ConnectionErrorHandler
from .operators.stream_fetcher import StreamFetcher
from .operators.stream_url_resolver import StreamURLResolver
from .stream_param_holder import StreamParamHolder
from .stream_recorder import StreamRecorder

__all__ = ("FLVStreamRecorderImpl",)

logger = logging.getLogger(__name__)

# How long to wait between successive fetches after a connection breaks.
_RECONNECT_BASE_DELAY = 1.0
_RECONNECT_MAX_DELAY = 30.0
# Statistics tick interval (seconds).
_STATS_TICK_INTERVAL = 2.0
# How long to wait before re-fetching a stream that ended cleanly.
_STREAM_END_DELAY = 1.0


class FLVStreamRecorderImpl:
    """FLV download main loop.

    Lifecycle:
        1. ``run()`` is called as an asyncio Task after ``start_recording()``.
        2. Resolves the stream URL via ``StreamURLResolver``.
        3. Opens HTTP connection via ``StreamFetcher``.
        4. Reads chunks and feeds them into ``StreamRecorder.feed_flv_data()``.
        5. Updates statistics on each chunk.
        6. On connection error: retry with backoff / CDN fallback.
        7. Stops when ``stop()`` is called or retries are exhausted.
    """

    def __init__(
        self,
        stream_recorder: StreamRecorder,
        live: Live,
        session: aiohttp.ClientSession,
        stream_params: StreamParamHolder,
    ) -> None:
        self._stream_recorder = stream_recorder
        self._live = live
        self._session = session
        self._stream_params = stream_params
        self._url_resolver = StreamURLResolver(live)
        self._fetcher = StreamFetcher(session)
        self._error_handler = ConnectionErrorHandler(
            max_retries=10,
            base_delay=_RECONNECT_BASE_DELAY,
            max_delay=_RECONNECT_MAX_DELAY,
        )
        self._running = False
        self._stats_task: asyncio.Task[None] | None = None

    @property
    def running(self) -> bool:
        return self._running

    async def run(self) -> None:
        """Main download loop. Runs until stop() or retries exhausted."""
        self._running = True
        self._stats_task = asyncio.create_task(self._stats_ticker())

        try:
            await self._download_loop()
        finally:
            self._running = False
            if self._stats_task and not self._stats_task.done():
                self._stats_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._stats_task

    def stop(self) -> None:
        """Signal the download loop to stop."""
        self._running = False

    async def _download_loop(self) -> None:
        """Resolve URL, fetch, and feed data in a retry loop."""
        sr = self._stream_recorder
        params = self._stream_params
        first_attempt = True

        while self._running:
            # Anything the previous connection left half-written belongs to a
            # document that has ended; the next one starts its own.
            if not first_attempt:
                sr.discard_partial_stream()
            first_attempt = False

            # 1. Resolve stream URL
            try:
                url = await self._url_resolver.resolve(
                    stream_format=params.stream_format,
                    stream_codec=params.stream_codec,
                    quality_number=params.quality_number,
                )
            except Exception as exc:
                logger.error("Failed to resolve stream URL: %s", exc)
                if not await self._handle_error():
                    break
                continue

            # Update stream URL/host tracking on StreamRecorder
            parsed = urlparse(url)
            sr._current_stream_url = url
            sr._current_stream_host = parsed.hostname or ""

            # 2. Mark stream available (first time)
            sr.mark_stream_available(
                stream_format=params.stream_format,
                quality_number=params.quality_number,
            )

            # 3. Create FLV pipeline if not already active
            if sr.active_pipeline != "flv":
                video_path = Path(sr.current_video_path)
                sr.create_flv_pipeline(video_path)

            # 4. Fetch and feed
            logger.info(
                "Downloading FLV stream from %s",
                parsed.hostname or url[:60],
            )
            delivered = False
            try:
                async for chunk in self._fetcher.fetch(url):
                    if not self._running:
                        break
                    delivered = True
                    sr.feed_flv_data(chunk)
                    sr.statistics.update_dl(len(chunk))
            except (aiohttp.ClientError, TimeoutError) as exc:
                logger.warning("Stream connection lost: %s", exc)
                if not self._running:
                    break
                if not await self._handle_error():
                    break
                continue
            except Exception as exc:
                logger.error("Unexpected error during stream fetch: %s", exc)
                if not self._running:
                    break
                if not await self._handle_error():
                    break
                continue

            # Stream ended normally (server closed connection). For live
            # streams that usually means a reconnect is needed.
            if not self._running:
                break
            logger.info("Stream ended, reconnecting...")
            if delivered:
                # A connection that carried data is evidence the stream is
                # healthy, so the retry budget starts over.
                self._error_handler.reset()
                await asyncio.sleep(_STREAM_END_DELAY)
            elif not await self._handle_error():
                # One that carried nothing is not evidence of anything. Resetting
                # the budget on those makes an endpoint answering 200 with an
                # empty body retryable forever, with the task claiming to record
                # a file that never grows past its header.
                break

    async def _handle_error(self) -> bool:
        """Handle a connection error. Returns True if should retry."""
        if not self._running:
            return False
        return await self._error_handler.wait_retry()

    async def _stats_ticker(self) -> None:
        """Periodically tick statistics to compute rates."""
        try:
            while self._running:
                await asyncio.sleep(_STATS_TICK_INTERVAL)
                self._stream_recorder.statistics.tick()
                # Bytes downloaded and bytes written diverge (buffering, dropped
                # tags), so report the on-disk size rather than inferring it.
                self._stream_recorder.update_file_size()
        except asyncio.CancelledError:
            pass
