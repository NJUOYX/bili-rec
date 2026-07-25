"""StreamRecorder: facade for stream recording with FLV↔fMP4 fallback."""

from __future__ import annotations

import logging

import aiohttp

from ..bili.live import Live
from .cover_downloader import CoverDownloader
from .danmaku_dumper import DanmakuDumper
from .danmaku_receiver import DanmakuReceiver
from .metadata_provider import MetadataProvider
from .operators.stream_statistics import StreamStatistics
from .path_provider import PathProvider
from .raw_danmaku_dumper import RawDanmakuDumper
from .raw_danmaku_receiver import RawDanmakuReceiver
from .stream_param_holder import StreamParamHolder

__all__ = ("StreamRecorder",)

logger = logging.getLogger(__name__)


class StreamRecorder:
    """Facade for stream recording.

    Coordinates stream fetching, parsing, writing, danmaku, cover download,
    and statistics. Supports FLV↔fMP4 fallback when configured.
    """

    def __init__(
        self,
        live: Live,
        session: aiohttp.ClientSession,
        path_provider: PathProvider,
        metadata_provider: MetadataProvider,
        stream_params: StreamParamHolder | None = None,
    ) -> None:
        self._live = live
        self._session = session
        self._path_provider = path_provider
        self._metadata_provider = metadata_provider
        self._stream_params = stream_params or StreamParamHolder()
        self._statistics = StreamStatistics()
        self._is_recording: bool = False
        self._current_video_path: str = ""
        self._danmaku_receiver: DanmakuReceiver | None = None
        self._danmaku_dumper: DanmakuDumper | None = None
        self._raw_danmaku_receiver: RawDanmakuReceiver | None = None
        self._raw_danmaku_dumper: RawDanmakuDumper | None = None
        self._cover_downloader: CoverDownloader | None = None

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    @property
    def statistics(self) -> StreamStatistics:
        return self._statistics

    @property
    def current_video_path(self) -> str:
        return self._current_video_path

    @property
    def stream_params(self) -> StreamParamHolder:
        return self._stream_params

    def setup_danmaku(
        self,
        receiver: DanmakuReceiver,
        raw_receiver: RawDanmakuReceiver | None = None,
    ) -> None:
        """Set up danmaku recording pipeline."""
        self._danmaku_receiver = receiver
        self._raw_danmaku_receiver = raw_receiver

    def setup_cover_downloader(self, downloader: CoverDownloader) -> None:
        """Set up cover downloader."""
        self._cover_downloader = downloader

    async def start_recording(self) -> str:
        """Start recording a new segment.

        Returns the video file path.
        """
        video_path = self._path_provider.video_path()
        self._path_provider.make_dirs(video_path)
        self._current_video_path = video_path

        # Set up danmaku dumper
        if self._danmaku_receiver:
            danmaku_path = self._path_provider.danmaku_path(video_path)
            self._danmaku_dumper = DanmakuDumper(
                self._danmaku_receiver,
                danmaku_path,
            )

        # Set up raw danmaku dumper
        if self._raw_danmaku_receiver:
            raw_path = self._path_provider.raw_danmaku_path(video_path)
            self._raw_danmaku_dumper = RawDanmakuDumper(
                self._raw_danmaku_receiver,
                raw_path,
            )

        # Write metadata
        self._metadata_provider.mark_rec_start()
        meta_path = self._path_provider.meta_path(video_path)
        meta_content = self._metadata_provider.build_ffmpeg_metadata()
        with open(meta_path, "w", encoding="utf-8") as f:
            f.write(meta_content)

        self._statistics.reset()
        self._statistics.start()
        self._is_recording = True

        logger.info("Recording started: %s", video_path)
        return video_path

    async def stop_recording(self) -> None:
        """Stop the current recording segment."""
        if not self._is_recording:
            return

        self._is_recording = False
        self._statistics.stop()

        # Finalize danmaku
        if self._danmaku_dumper:
            self._danmaku_dumper.finalize()
            self._danmaku_dumper = None

        # Finalize raw danmaku
        if self._raw_danmaku_dumper:
            self._raw_danmaku_dumper.finalize()
            self._raw_danmaku_dumper = None

        logger.info(
            "Recording stopped: %s (%s)",
            self._current_video_path,
            self.format_size(self._statistics.file_size),
        )

    async def download_cover(self, cover_url: str) -> None:
        """Download cover image if cover downloader is set up."""
        if self._cover_downloader and self._current_video_path:
            cover_path = self._path_provider.cover_path(self._current_video_path)
            await self._cover_downloader.download(cover_url, cover_path)

    def format_size(self, size: int) -> str:
        """Format byte size to human-readable string."""
        if size < 1024:
            return f"{size}B"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f}KB"
        if size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f}MB"
        return f"{size / (1024 * 1024 * 1024):.2f}GB"
