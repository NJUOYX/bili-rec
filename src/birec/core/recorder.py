"""Recorder: top-level recording coordinator for a live room."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable

import aiohttp

from ..bili.live import Live
from ..bili.live_monitor import LiveMonitor, LiveMonitorListener
from ..bili.models import RoomInfo, UserInfo
from .cover_downloader import CoverDownloader
from .danmaku_receiver import DanmakuReceiver
from .flv_stream_recorder_impl import FLVStreamRecorderImpl
from .metadata_provider import MetadataProvider
from .models import CompletedSegment, StartedSegment
from .path_provider import PathProvider
from .raw_danmaku_receiver import RawDanmakuReceiver
from .statistics import Statistics
from .stream_recorder import StreamRecorder

__all__ = ("Recorder",)

logger = logging.getLogger(__name__)


class Recorder(LiveMonitorListener):
    """Top-level recording coordinator.

    Responds to LiveMonitor events to start/stop recording.
    Manages the full recording lifecycle: stream, danmaku, cover, metadata.
    """

    def __init__(
        self,
        room_id: int,
        live: Live,
        monitor: LiveMonitor,
        session: aiohttp.ClientSession,
        path_provider: PathProvider,
        *,
        danmaku_receiver: DanmakuReceiver | None = None,
        raw_danmaku_receiver: RawDanmakuReceiver | None = None,
        cover_downloader: CoverDownloader | None = None,
    ) -> None:
        self._room_id = room_id
        self._live = live
        self._monitor = monitor
        self._session = session
        self._path_provider = path_provider
        self._metadata_provider = MetadataProvider(room_id=room_id)
        self._stream_recorder = StreamRecorder(
            live=live,
            session=session,
            path_provider=path_provider,
            metadata_provider=self._metadata_provider,
        )
        self._statistics = Statistics()
        self._is_recording: bool = False
        self._start_task: asyncio.Task[None] | None = None
        self._stop_task: asyncio.Task[None] | None = None
        self._download_task: asyncio.Task[None] | None = None
        self._flv_impl: FLVStreamRecorderImpl | None = None
        self._segment_listener: Callable[[CompletedSegment], None] | None = None
        self._segment_started_listener: Callable[[StartedSegment], None] | None = None
        self._cover_listener: Callable[[str], None] | None = None
        self._cover_task: asyncio.Task[None] | None = None

        # Set up danmaku if provided
        if danmaku_receiver:
            self._stream_recorder.setup_danmaku(
                danmaku_receiver,
                raw_danmaku_receiver,
            )

        # Set up cover downloader if provided
        if cover_downloader:
            self._stream_recorder.setup_cover_downloader(cover_downloader)

        # A pipeline that dies on unparseable bytes is the only thing that
        # knows the recording has stopped working, and it cannot close the
        # segment itself.
        self._stream_recorder.set_pipeline_failure_listener(self._on_pipeline_failure)

        # Register as monitor listener
        monitor.add_listener(self)

    @property
    def room_id(self) -> int:
        return self._room_id

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    @property
    def statistics(self) -> Statistics:
        return self._statistics

    @property
    def stream_recorder(self) -> StreamRecorder:
        return self._stream_recorder

    def update_info(
        self,
        room_info: RoomInfo | None = None,
        user_info: UserInfo | None = None,
    ) -> None:
        """Update room/user info for metadata and path rendering."""
        self._path_provider.update_info(room_info, user_info)
        self._metadata_provider.update(room_info, user_info)

    def update_out_dir(self, out_dir: str) -> None:
        """Hot-update the output directory for future recordings."""
        self._path_provider.out_dir = out_dir

    def set_segment_listener(
        self, listener: Callable[[CompletedSegment], None] | None
    ) -> None:
        """Register the callback fired once a segment's files are finalized.

        This is how post-processing learns that a recording is ready: the
        segment is only ever complete here, after the pipelines are flushed and
        the danmaku dumpers closed.
        """
        self._segment_listener = listener

    def set_segment_started_listener(
        self, listener: Callable[[StartedSegment], None] | None
    ) -> None:
        """Register the callback fired once a segment's files are opened.

        The counterpart of :meth:`set_segment_listener`: this is how anything
        outside the recorder learns that a recording has begun and which files
        it is writing to.
        """
        self._segment_started_listener = listener

    def set_cover_listener(self, listener: Callable[[str], None] | None) -> None:
        """Register the callback fired once a cover image has been saved."""
        self._cover_listener = listener

    def on_live_began(self, live: Live) -> None:
        """Called when LiveMonitor detects live start."""
        if self._is_recording:
            return
        # Refresh before rendering paths / metadata: otherwise the template
        # variables ({roomid}, {uname}, ...) resolve to empty strings.
        self.update_info(live.room_info, live.user_info)
        logger.info("Room %d: live started, starting recording", self._room_id)
        self._is_recording = True
        self._statistics.reset()
        self._statistics.start()
        self._start_task = asyncio.create_task(self._start_recording_async())
        self._start_task.add_done_callback(self._on_start_done)

    async def _start_recording_async(self) -> None:
        """Internal async start: initialize segment then start download loop."""
        segment = await self._stream_recorder.start_recording()
        self._notify_segment_started(segment)
        # Launch FLV download loop as a background task.
        self._flv_impl = FLVStreamRecorderImpl(
            self._stream_recorder,
            self._live,
            self._session,
            self._stream_recorder.stream_params,
        )
        self._download_task = asyncio.create_task(self._flv_impl.run())
        self._download_task.add_done_callback(self._on_download_done)
        # The cover is a nice-to-have next to the recording, so it is fetched
        # after the download loop is up and never allowed to hold it back.
        self._cover_task = asyncio.create_task(self._download_cover_async())

    def _on_start_done(self, task: asyncio.Task[None]) -> None:
        """Handle start task completion."""
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error(
                "Room %d: failed to start recording: %s",
                self._room_id,
                exc,
            )
            self._is_recording = False
            self._statistics.stop()

    def _on_download_done(self, task: asyncio.Task[None]) -> None:
        """Handle download task completion (stream ended or error)."""
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error(
                "Room %d: download loop crashed: %s",
                self._room_id,
                exc,
            )

        if not self._is_recording:
            # An ordinary stop: whoever asked for it is already closing the
            # segment.
            return

        # The loop finished while the recording is still supposed to be running,
        # so it gave up by itself: out of retries, or the stream URL never
        # resolved. Nobody else will close this segment, and leaving it open
        # means the task reports itself as recording for as long as the room
        # stays live while not a single byte is being written.
        logger.warning(
            "Room %d: the download gave up, finalizing the recording",
            self._room_id,
        )
        self._is_recording = False
        self._statistics.stop()
        self._stop_task = asyncio.create_task(self._stop_recording_async())
        self._stop_task.add_done_callback(self._on_stop_done)

    def _on_pipeline_failure(self, error: Exception) -> None:
        """Close the segment when the stream stops being parseable.

        Nothing further will be written once the pipeline has errored, so the
        alternatives are closing the segment or reporting a recording that is
        not happening. Closing it keeps what was recorded, hands it to
        post-processing, and lets the next broadcast start a fresh file.
        """
        if not self._is_recording:
            return
        logger.warning(
            "Room %d: the stream became unparseable (%s), finalizing the recording",
            self._room_id,
            error,
        )
        self._is_recording = False
        self._statistics.stop()
        self._stop_task = asyncio.create_task(self._stop_recording_async())
        self._stop_task.add_done_callback(self._on_stop_done)

    def on_live_ended(self, live: Live) -> None:
        """Called when LiveMonitor detects live end."""
        if not self._is_recording:
            return
        logger.info("Room %d: live ended, stopping recording", self._room_id)
        self._is_recording = False
        self._statistics.stop()
        self._stop_task = asyncio.create_task(self._stop_recording_async())
        self._stop_task.add_done_callback(self._on_stop_done)

    async def _stop_recording_async(self) -> None:
        """Internal async stop: stop download loop then finalize segment."""
        # A start still in flight would spawn the download loop right after we
        # tore it down, so let it settle before cancelling anything.
        if self._start_task is not None and not self._start_task.done():
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._start_task
        if self._flv_impl is not None:
            self._flv_impl.stop()
        if self._download_task is not None and not self._download_task.done():
            self._download_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._download_task
        if self._cover_task is not None and not self._cover_task.done():
            self._cover_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cover_task
        self._cover_task = None
        self._flv_impl = None
        self._download_task = None
        segment = await self._stream_recorder.stop_recording()
        if segment is not None:
            self._notify_segment_completed(segment)

    async def _download_cover_async(self) -> None:
        """Fetch the room's cover image alongside the recording.

        Best-effort by design: a room without a usable cover, or a CDN having a
        bad day, must never disturb the recording that is already running.
        """
        room_info = self._live.room_info
        if room_info is None or not room_info.cover:
            return
        try:
            path = await self._stream_recorder.download_cover(room_info.cover)
        except Exception:
            logger.exception("Room %d: cover download failed", self._room_id)
            return
        if path and self._cover_listener is not None:
            try:
                self._cover_listener(path)
            except Exception:
                logger.exception(
                    "Room %d: cover listener failed for %s", self._room_id, path
                )

    def _notify_segment_started(self, segment: StartedSegment) -> None:
        """Announce the new segment without letting a listener abort the start."""
        if self._segment_started_listener is None:
            return
        try:
            self._segment_started_listener(segment)
        except Exception:
            logger.exception(
                "Room %d: segment started listener failed for %s",
                self._room_id,
                segment.video_path,
            )

    def _notify_segment_completed(self, segment: CompletedSegment) -> None:
        """Hand the finished segment over without letting a listener break stop."""
        if self._segment_listener is None:
            return
        try:
            self._segment_listener(segment)
        except Exception:
            logger.exception(
                "Room %d: segment listener failed for %s",
                self._room_id,
                segment.video_path,
            )

    def _on_stop_done(self, task: asyncio.Task[None]) -> None:
        """Handle stop task completion."""
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error(
                "Room %d: failed to stop recording cleanly: %s",
                self._room_id,
                exc,
            )

    def on_live_stream_available(self, live: Live) -> None:
        """Called when a new stream URL is available."""
        logger.debug("Room %d: stream URL available", self._room_id)

    def on_live_stream_reset(self, live: Live) -> None:
        """Called when the stream is reset."""
        logger.debug("Room %d: stream reset", self._room_id)

    def on_room_changed(self, live: Live) -> None:
        """Called when room info changes."""
        logger.debug("Room %d: room changed", self._room_id)
        self.update_info(live.room_info, live.user_info)

    async def stop_recording(self) -> None:
        """Finalize the current recording but stay subscribed to the monitor.

        Used when recording is switched off by the user: no live-end event will
        arrive to close the segment, so it has to be finalized explicitly, while
        the recorder itself must remain reusable if recording is switched back on.
        """
        if self._is_recording:
            self._is_recording = False
            self._statistics.stop()
            await self._stop_recording_async()
        elif self._stop_task is not None and not self._stop_task.done():
            await self._stop_task

    async def stop(self) -> None:
        """Stop recording, clean up, and detach from the monitor.

        Awaits the stop task to ensure files are finalized before returning.
        """
        await self.stop_recording()
        self._monitor.remove_listener(self)
