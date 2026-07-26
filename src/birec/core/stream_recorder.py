"""StreamRecorder: facade for stream recording with FLV↔fMP4 fallback."""

from __future__ import annotations

import logging
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import Literal

import aiohttp
from reactivex.abc import DisposableBase
from reactivex.disposable import CompositeDisposable
from reactivex.subject import Subject

from ..bili.live import Live
from ..flv.operators import Dumper, ProgressBar, dump, parse, process, progress
from ..flv.operators.typing import FLVStream, FLVStreamItem
from ..flv.struct_io import RandomIO
from ..hls.models import HlsPlaylist, HlsSegment
from ..hls.operators.analyse import HlsAnalyser
from ..hls.operators.playlist_dumper import PlaylistDumper
from ..hls.operators.playlist_resolver import PlaylistResolver
from ..hls.operators.segment_dumper import SegmentDumper
from ..hls.operators.segment_fetcher import FetchedSegment, SegmentFetcher
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
        # FLV pipeline state
        self._flv_dumper: Dumper | None = None
        self._flv_progress: ProgressBar | None = None
        self._flv_subscription: DisposableBase | None = None
        self._flv_disposables: CompositeDisposable | None = None
        self._flv_source: Subject[RandomIO] | None = None
        # HLS pipeline state
        self._hls_segment_dumper: SegmentDumper | None = None
        self._hls_playlist_dumper: PlaylistDumper | None = None
        self._hls_analyser: HlsAnalyser | None = None
        self._hls_resolver: PlaylistResolver | None = None
        self._hls_fetcher: SegmentFetcher | None = None
        # Active pipeline tracking ("flv" / "hls" / None)
        self._active_pipeline: Literal["flv", "hls"] | None = None

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

    @property
    def active_pipeline(self) -> Literal["flv", "hls"] | None:
        """The currently active recording pipeline, if any."""
        return self._active_pipeline

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
        self._active_pipeline = None
        self._is_recording = True

        logger.info("Recording started: %s", video_path)
        return video_path

    async def stop_recording(self) -> None:
        """Stop the current recording segment."""
        if not self._is_recording:
            return

        self._is_recording = False
        self._statistics.stop()

        # Finalize whichever pipeline(s) are active. Both finalizers are safe
        # to call unconditionally (no-op when the pipeline was never created).
        self._finalize_flv_pipeline()
        self.finalize_hls_pipeline()
        self._active_pipeline = None

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

    def create_flv_pipeline(
        self,
        output_path: Path,
        *,
        sort_tags: bool = True,
        progress_callback: Callable[[ProgressBar], None] | None = None,
    ) -> FLVStream:
        """Create an FLV processing pipeline for recording.

        Creates: parse → process → progress → dump pipeline.

        Args:
            output_path: Path for the output FLV file.
            sort_tags: Whether to sort tags within GOP.
            progress_callback: Optional progress callback.

        Returns:
            The processed FLVStream ready for subscription.
        """
        self._flv_dumper = Dumper(output_path)
        self._flv_progress = ProgressBar()

        # Build a source subject for feeding raw IO data
        source: Subject[RandomIO] = Subject()
        self._flv_source = source

        # Build pipeline: parse → process → progress → dump
        parsed = parse()(source)
        processed = process(sort_tags=sort_tags)(parsed)

        # Add progress tracking
        if progress_callback is not None:
            processed = progress(callback=progress_callback)(processed)

        # Add dump
        processed = dump(output_path)(processed)

        self._active_pipeline = "flv"

        # Subscribe internally so that feed_flv_data drives the live pipeline
        # (parse -> process -> dump) without the caller managing subscriptions.
        def _on_next(_: FLVStreamItem) -> None:
            return None

        def _on_error(error: Exception) -> None:
            logger.error("FLV pipeline error: %s", error)

        subscription = processed.subscribe(
            on_next=_on_next,
            on_error=_on_error,
        )
        self._flv_subscription = subscription
        self._flv_disposables = CompositeDisposable()
        self._flv_disposables.add(subscription)
        return processed

    def feed_flv_data(self, data: bytes) -> None:
        """Feed raw FLV bytes into the pipeline.

        Wraps data in BytesIO and pushes to the parse stage.
        """
        if self._flv_source is not None:
            stream = BytesIO(data)
            self._flv_source.on_next(stream)

    def complete_flv_pipeline(self) -> None:
        """Signal completion of the FLV data stream."""
        if self._flv_source is not None:
            self._flv_source.on_completed()

    def _finalize_flv_pipeline(self) -> None:
        """Finalize and clean up the FLV pipeline."""
        if self._flv_disposables is not None:
            self._flv_disposables.dispose()
            self._flv_disposables = None

        if self._flv_subscription is not None:
            self._flv_subscription.dispose()
            self._flv_subscription = None

        if self._flv_dumper is not None:
            self._flv_dumper.close()
            self._flv_dumper = None

        self._flv_progress = None
        self._flv_source = None

    @property
    def flv_progress(self) -> ProgressBar | None:
        """Get the current FLV progress tracker."""
        return self._flv_progress

    def format_size(self, size: int) -> str:
        """Format byte size to human-readable string."""
        if size < 1024:
            return f"{size}B"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f}KB"
        if size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f}MB"
        return f"{size / (1024 * 1024 * 1024):.2f}GB"

    # ─── HLS Pipeline ────────────────────────────────────────────────────

    def create_hls_pipeline(
        self,
        output_path: Path,
        base_url: str = "",
        *,
        playlist_path: Path | None = None,
    ) -> None:
        """Create an HLS processing pipeline for recording.

        Sets up segment dumper, playlist dumper, analyser, and resolver.

        Args:
            output_path: Path for the output fMP4 file.
            base_url: Base URL for resolving relative segment URIs.
            playlist_path: Optional path to write playlist files.
        """
        self._hls_segment_dumper = SegmentDumper(output_path)
        self._hls_segment_dumper.open()
        self._hls_playlist_dumper = PlaylistDumper(playlist_path)
        self._hls_analyser = HlsAnalyser()
        self._hls_resolver = PlaylistResolver()
        self._hls_fetcher = SegmentFetcher(self._session, base_url)
        self._active_pipeline = "hls"
        logger.debug("HLS pipeline created: %s", output_path)

    def feed_hls_playlist(self, playlist: HlsPlaylist) -> list[HlsSegment]:
        """Feed a playlist into the HLS pipeline.

        Resolves new segments and updates playlist tracking.

        Args:
            playlist: The parsed playlist.

        Returns:
            List of new segments to fetch.
        """
        if self._hls_resolver is None or self._hls_playlist_dumper is None:
            return []

        self._hls_playlist_dumper.update(playlist)
        self._hls_playlist_dumper.dump(playlist)
        return self._hls_resolver.resolve(playlist)

    def feed_hls_segment(self, fetched: FetchedSegment) -> None:
        """Feed a fetched segment into the HLS pipeline.

        Writes the segment and updates analysis.

        Args:
            fetched: The fetched segment with data.
        """
        if self._hls_segment_dumper is not None:
            self._hls_segment_dumper.write_segment(fetched)
        if self._hls_analyser is not None:
            self._hls_analyser.add_segment(fetched)

    def write_hls_init(self, data: bytes) -> None:
        """Write initialization segment data.

        Args:
            data: Init segment bytes.
        """
        if self._hls_segment_dumper is not None:
            self._hls_segment_dumper.write_init(data)

    def finalize_hls_pipeline(self) -> None:
        """Finalize and clean up the HLS pipeline."""
        if self._hls_segment_dumper is not None:
            self._hls_segment_dumper.close()
            self._hls_segment_dumper = None

        self._hls_playlist_dumper = None
        self._hls_analyser = None
        self._hls_resolver = None
        self._hls_fetcher = None
        logger.debug("HLS pipeline finalized")

    @property
    def hls_segment_dumper(self) -> SegmentDumper | None:
        """Get the current HLS segment dumper."""
        return self._hls_segment_dumper

    @property
    def hls_analyser(self) -> HlsAnalyser | None:
        """Get the current HLS analyser."""
        return self._hls_analyser

    @property
    def hls_fetcher(self) -> SegmentFetcher | None:
        """Get the current HLS segment fetcher."""
        return self._hls_fetcher
