"""Postprocessor: queue-driven async worker for post-recording processing."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from pathlib import Path

from .danmaku_to_ass import DanmakuToAssConfig, convert_danmaku_to_ass
from .metadata import MediaMetadata, inject_metadata
from .models import PostprocessingItem, PostprocessingProgress, PostprocessingStatus
from .remux import remux_flv_to_mp4, remux_fmp4_to_mp4

__all__ = ("Postprocessor",)

logger = logging.getLogger(__name__)

# Source extensions to delete on success (AUTO strategy)
_AUTO_DELETE_EXTENSIONS = {".flv", ".m4s", ".m3u8", ".meta", ".meta.json"}


class Postprocessor:
    """Queue-driven post-processing worker.

    Processes recording files sequentially (global concurrency 1).
    Capabilities:
    - Remux FLV→MP4 (with filler removal)
    - Remux fMP4(.m4s)→MP4
    - FFmpeg metadata injection
    - Danmaku XML→ASS conversion
    - AUTO delete source strategy (delete on success only)
    """

    def __init__(
        self,
        *,
        remux_enabled: bool = True,
        inject_metadata_enabled: bool = True,
        danmaku_to_ass_enabled: bool = False,
        danmaku_config: DanmakuToAssConfig | None = None,
        on_completed: Callable[[PostprocessingItem], None] | None = None,
    ) -> None:
        self._remux_enabled = remux_enabled
        self._inject_metadata_enabled = inject_metadata_enabled
        self._danmaku_to_ass_enabled = danmaku_to_ass_enabled
        self._danmaku_config = danmaku_config or DanmakuToAssConfig()
        self._on_completed = on_completed

        self._queue: asyncio.Queue[PostprocessingItem] = asyncio.Queue()
        self._worker_task: asyncio.Task[None] | None = None
        self._running = False
        self._current_item: PostprocessingItem | None = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    @property
    def current_item(self) -> PostprocessingItem | None:
        return self._current_item

    @property
    def remux_enabled(self) -> bool:
        return self._remux_enabled

    @property
    def inject_metadata_enabled(self) -> bool:
        return self._inject_metadata_enabled

    @property
    def danmaku_to_ass_enabled(self) -> bool:
        return self._danmaku_to_ass_enabled

    @property
    def danmaku_config(self) -> DanmakuToAssConfig:
        return self._danmaku_config

    def update_options(
        self,
        *,
        remux_enabled: bool | None = None,
        inject_metadata_enabled: bool | None = None,
        danmaku_to_ass_enabled: bool | None = None,
        danmaku_config: DanmakuToAssConfig | None = None,
    ) -> None:
        """Hot-update the processing switches; ``None`` leaves one untouched.

        The switches are read per item, so a settings change reaches recordings
        that are still to come on an already running task instead of only the
        tasks created afterwards.
        """
        if remux_enabled is not None:
            self._remux_enabled = remux_enabled
        if inject_metadata_enabled is not None:
            self._inject_metadata_enabled = inject_metadata_enabled
        if danmaku_to_ass_enabled is not None:
            self._danmaku_to_ass_enabled = danmaku_to_ass_enabled
        if danmaku_config is not None:
            self._danmaku_config = danmaku_config

    def set_completion_listener(
        self, listener: Callable[[PostprocessingItem], None] | None
    ) -> None:
        """Register the callback fired after each item leaves the queue."""
        self._on_completed = listener

    async def start(self) -> None:
        """Start the postprocessor worker."""
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._worker())
        logger.debug("Postprocessor started")

    async def stop(self) -> None:
        """Stop the postprocessor worker."""
        self._running = False
        if self._worker_task is not None:
            self._worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task
            self._worker_task = None
        logger.debug("Postprocessor stopped")

    def submit(
        self,
        source_path: Path,
        output_path: Path,
        *,
        metadata: MediaMetadata | None = None,
        related_files: list[Path] | None = None,
    ) -> PostprocessingItem:
        """Submit a file for post-processing.

        Args:
            source_path: Source recording file.
            output_path: Desired output path.
            metadata: Optional metadata to inject.
            related_files: Related files (danmaku xml, etc).

        Returns:
            The created PostprocessingItem.
        """
        item = PostprocessingItem(
            source_path=source_path,
            output_path=output_path,
            related_files=related_files or [],
            metadata=metadata,
        )
        self._queue.put_nowait(item)
        logger.debug("Submitted %s for postprocessing", source_path)
        return item

    async def _worker(self) -> None:
        """Main worker loop: process items sequentially."""
        while self._running:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except TimeoutError:
                continue

            self._current_item = item
            try:
                await self._process_item(item)
            except Exception as e:
                logger.error("Postprocessing failed for %s: %s", item.source_path, e)
                item.status = PostprocessingStatus.FAILED
                item.error = str(e)
            finally:
                self._current_item = None
                self._queue.task_done()
                if self._on_completed is not None:
                    self._on_completed(item)

    async def _process_item(self, item: PostprocessingItem) -> None:
        """Process a single item through the pipeline."""
        source = item.source_path
        suffix = source.suffix.lower()

        # Step 1: Danmaku XML→ASS. Runs ahead of the remux so that a missing or
        # failing ffmpeg does not cost the user their subtitles as well.
        if self._danmaku_to_ass_enabled:
            await self._convert_danmaku(item)

        # Step 2: Remux
        if self._remux_enabled:
            item.status = PostprocessingStatus.REMUXING
            item.progress = PostprocessingProgress(status=PostprocessingStatus.REMUXING)

            success = False
            if suffix == ".flv":
                success = await remux_flv_to_mp4(source, item.output_path)
            elif suffix == ".m4s":
                success = await remux_fmp4_to_mp4(source, item.output_path)
            else:
                # Unknown format, skip remux
                success = True
                item.output_path = source

            if not success:
                item.status = PostprocessingStatus.FAILED
                item.error = f"Remux failed for {source}"
                return

        # Step 3: Metadata injection
        if self._inject_metadata_enabled and item.metadata is not None:
            item.status = PostprocessingStatus.INJECTING
            item.progress = PostprocessingProgress(
                status=PostprocessingStatus.INJECTING
            )
            # Inject into the remuxed output if it exists, else into the source.
            target = item.output_path if item.output_path.exists() else source
            # Metadata injection is optional - don't fail the whole task
            # if it fails
            if not await inject_metadata(target, item.metadata):
                logger.warning("Metadata injection failed for %s, continuing", target)

        # Step 4: AUTO delete source, but only once something has taken its
        # place. Skipping the remux skips the only step that produces a
        # replacement, and an unknown format points the output back at the
        # source; deleting in either case would destroy the recording outright.
        if item.output_path != source and item.output_path.exists():
            self._delete_source(item)

        item.status = PostprocessingStatus.COMPLETED
        item.progress = PostprocessingProgress(
            status=PostprocessingStatus.COMPLETED, percent=100.0
        )
        logger.debug("Postprocessing completed: %s", item.source_path)

    async def _convert_danmaku(self, item: PostprocessingItem) -> None:
        """Convert every danmaku XML among the item's related files to ASS."""
        for related in item.related_files:
            if related.suffix.lower() == ".xml":
                ass_path = related.with_suffix(".ass")
                await convert_danmaku_to_ass(
                    related, ass_path, config=self._danmaku_config
                )

    def _delete_source(self, item: PostprocessingItem) -> None:
        """Delete source files (AUTO strategy: only on success)."""
        source = item.source_path
        if source.suffix.lower() in _AUTO_DELETE_EXTENSIONS and source.exists():
            try:
                source.unlink()
                logger.debug("Deleted source: %s", source)
            except OSError as e:
                logger.warning("Failed to delete source %s: %s", source, e)

        # Delete related intermediate files
        for related in item.related_files:
            if related.suffix.lower() in _AUTO_DELETE_EXTENSIONS and related.exists():
                try:
                    related.unlink()
                    logger.debug("Deleted related: %s", related)
                except OSError as e:
                    logger.warning("Failed to delete %s: %s", related, e)
