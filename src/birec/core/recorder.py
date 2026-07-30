"""Recorder: top-level recording coordinator for a live room."""

from __future__ import annotations

import asyncio
import logging

import aiohttp

from ..bili.live import Live
from ..bili.live_monitor import LiveMonitor, LiveMonitorListener
from ..bili.models import RoomInfo, UserInfo
from .cover_downloader import CoverDownloader
from .danmaku_receiver import DanmakuReceiver
from .metadata_provider import MetadataProvider
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

        # Set up danmaku if provided
        if danmaku_receiver:
            self._stream_recorder.setup_danmaku(
                danmaku_receiver,
                raw_danmaku_receiver,
            )

        # Set up cover downloader if provided
        if cover_downloader:
            self._stream_recorder.setup_cover_downloader(cover_downloader)

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
        """Internal async start."""
        await self._stream_recorder.start_recording()

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
        """Internal async stop."""
        await self._stream_recorder.stop_recording()

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

    async def stop(self) -> None:
        """Stop recording and clean up.

        Awaits the stop task to ensure files are finalized before returning.
        """
        if self._is_recording:
            self._is_recording = False
            self._statistics.stop()
            await self._stream_recorder.stop_recording()
        elif self._stop_task is not None and not self._stop_task.done():
            await self._stop_task
        self._monitor.remove_listener(self)
