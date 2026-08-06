"""Task management: RecordTask orchestration and RecordTaskManager."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from ..core.models import CompletedSegment, StartedSegment
from ..event import (
    CoverImageDownloadedEvent,
    CoverImageDownloadedEventData,
    DanmakuFileCompletedEvent,
    DanmakuFileCompletedEventData,
    DanmakuFileCreatedEvent,
    DanmakuFileCreatedEventData,
    EventCenter,
    PostprocessingCompletedEvent,
    PostprocessingCompletedEventData,
    RawDanmakuFileCompletedEvent,
    RawDanmakuFileCompletedEventData,
    RawDanmakuFileCreatedEvent,
    RawDanmakuFileCreatedEventData,
    VideoFileCompletedEvent,
    VideoFileCompletedEventData,
    VideoFileCreatedEvent,
    VideoFileCreatedEventData,
    VideoPostprocessingCompletedEvent,
    VideoPostprocessingCompletedEventData,
)
from ..postprocess.metadata import MediaMetadata
from ..postprocess.models import PostprocessingItem, PostprocessingStatus

if TYPE_CHECKING:
    from ..bili.danmaku_client import DanmakuClient
    from ..bili.live import Live
    from ..bili.live_monitor import LiveMonitor
    from ..core.recorder import Recorder
    from ..postprocess.danmaku_to_ass import DanmakuToAssConfig
    from ..postprocess.postprocessor import Postprocessor
    from ..space import SpaceMonitor, SpaceReclaimer

__all__ = (
    "RunningStatus",
    "FileStatus",
    "TaskStatus",
    "TaskData",
    "TaskParam",
    "TaskMetadata",
    "VideoFileDetail",
    "DanmakuFileDetail",
    "RecordTask",
    "RecordTaskManager",
)

logger = logging.getLogger(__name__)


def _file_size(path: str) -> int:
    """Size on disk, or 0 while the file has not been created yet."""
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


class RunningStatus(Enum):
    """Running status of a record task."""

    STOPPED = "stopped"
    WAITING = "waiting"
    RECORDING = "recording"
    REMUXING = "remuxing"
    INJECTING = "injecting"


class FileStatus(Enum):
    """Status of a recording file."""

    RECORDING = "recording"
    REMUXING = "remuxing"
    INJECTING = "injecting"
    COMPLETED = "completed"
    MISSING = "missing"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class TaskStatus:
    """Current status of a record task."""

    monitor_enabled: bool = False
    recorder_enabled: bool = False
    running_status: RunningStatus = RunningStatus.STOPPED
    stream_url: str = ""
    stream_host: str = ""
    dl_total: int = 0
    dl_rate: float = 0.0
    rec_elapsed: float = 0.0
    rec_total: int = 0
    rec_rate: float = 0.0
    danmu_total: int = 0
    danmu_rate: float = 0.0
    real_stream_format: str = ""
    real_quality_number: int = 0
    recording_path: str = ""
    postprocessor_status: str = ""
    postprocessing_path: str = ""
    postprocessing_progress: float = 0.0


@dataclass(frozen=True, slots=True)
class TaskData:
    """Task data including user info, room info, and status."""

    room_id: int
    user_name: str = ""
    room_title: str = ""
    area: str = ""
    parent_area: str = ""
    live_status: bool = False
    task_status: TaskStatus = field(default_factory=TaskStatus)


@dataclass(frozen=True, slots=True)
class VideoFileDetail:
    """Detail of a video file."""

    path: str
    size: int = 0
    status: FileStatus = FileStatus.UNKNOWN


@dataclass(frozen=True, slots=True)
class DanmakuFileDetail:
    """Detail of a danmaku file."""

    path: str
    size: int = 0
    status: FileStatus = FileStatus.UNKNOWN


@dataclass(frozen=True, slots=True)
class TaskParam:
    """Task parameters (configuration snapshot)."""

    room_id: int
    enable_monitor: bool = True
    enable_recorder: bool = True
    out_dir: str = ""
    path_template: str = ""
    stream_format: str = "flv"
    quality_number: int = 10000


@dataclass(frozen=True, slots=True)
class TaskMetadata:
    """Recording metadata for a task."""

    room_id: int
    user_name: str = ""
    room_title: str = ""
    area: str = ""
    parent_area: str = ""
    live_start_time: int = 0
    cover_url: str = ""


class RecordTask:
    """Orchestrates monitoring, recording, and post-processing for one room.

    Composes the Bilibili adapter (``Live``/``DanmakuClient``/``LiveMonitor``),
    the ``Recorder`` and the ``Postprocessor``. The monitor watches for live
    events; when the recorder is enabled the ``Recorder`` is registered as a
    monitor listener so recording starts/stops automatically on live events.
    """

    def __init__(
        self,
        room_id: int,
        live: Live,
        danmaku_client: DanmakuClient,
        monitor: LiveMonitor,
        recorder: Recorder,
        postprocessor: Postprocessor,
        *,
        enable_monitor: bool = True,
        enable_recorder: bool = True,
        event_center: EventCenter | None = None,
    ) -> None:
        self._room_id = room_id
        self._live = live
        self._danmaku_client = danmaku_client
        self._monitor = monitor
        self._recorder = recorder
        self._postprocessor = postprocessor
        self._monitor_enabled = enable_monitor
        self._recorder_enabled = enable_recorder
        self._event_center = event_center or EventCenter.get_instance()
        self._postprocessed_files: list[str] = []
        # Close the loop between recording and post-processing: the recorder is
        # the only place that knows a segment is finished and what it produced.
        recorder.set_segment_listener(self._on_segment_completed)
        recorder.set_segment_started_listener(self._on_segment_started)
        recorder.set_cover_listener(self._on_cover_downloaded)
        postprocessor.set_completion_listener(self._on_postprocessing_completed)

    @property
    def room_id(self) -> int:
        return self._room_id

    @property
    def live(self) -> Live:
        return self._live

    @property
    def monitor(self) -> LiveMonitor:
        return self._monitor

    @property
    def recorder(self) -> Recorder:
        return self._recorder

    @property
    def postprocessor(self) -> Postprocessor:
        return self._postprocessor

    @property
    def monitor_enabled(self) -> bool:
        return self._monitor_enabled

    @property
    def recorder_enabled(self) -> bool:
        return self._recorder_enabled

    @property
    def running_status(self) -> RunningStatus:
        """Derive the running status from the underlying components."""
        if self._recorder.is_recording:
            return RunningStatus.RECORDING
        # The worker runs for as long as the task exists, so only an item
        # actually in flight means post-processing is happening.
        item = self._postprocessor.current_item
        if item is not None:
            if item.status is PostprocessingStatus.INJECTING:
                return RunningStatus.INJECTING
            return RunningStatus.REMUXING
        if self._monitor_enabled and self._monitor.is_living:
            return RunningStatus.WAITING
        return RunningStatus.STOPPED

    # ── post-processing wiring ───────────────────────────────────

    def _on_segment_started(self, segment: StartedSegment) -> None:
        """Announce the files a new segment has opened (§3.3)."""
        if segment.video_path:
            self._event_center.submit(
                VideoFileCreatedEvent.from_data(
                    VideoFileCreatedEventData(
                        room_id=self._room_id, path=segment.video_path
                    )
                )
            )
        if segment.danmaku_path:
            self._event_center.submit(
                DanmakuFileCreatedEvent.from_data(
                    DanmakuFileCreatedEventData(
                        room_id=self._room_id, path=segment.danmaku_path
                    )
                )
            )
        if segment.raw_danmaku_path:
            self._event_center.submit(
                RawDanmakuFileCreatedEvent.from_data(
                    RawDanmakuFileCreatedEventData(
                        room_id=self._room_id, path=segment.raw_danmaku_path
                    )
                )
            )

    def _on_cover_downloaded(self, path: str) -> None:
        """Announce a saved cover image (§3.3)."""
        self._event_center.submit(
            CoverImageDownloadedEvent.from_data(
                CoverImageDownloadedEventData(room_id=self._room_id, path=path)
            )
        )

    def _on_segment_completed(self, segment: CompletedSegment) -> None:
        """Announce a finished segment and queue it for post-processing (§3.3)."""
        self._emit_file_completed_events(segment)
        if not segment.video_path:
            return
        video = Path(segment.video_path)
        # The ffmpeg .meta file is written beside every video at recording
        # start; listing it as a related file is what lets the postprocessor's
        # AUTO delete clean it up once the remux succeeds (#37).
        related = [
            Path(path)
            for path in (
                segment.danmaku_path,
                segment.raw_danmaku_path,
                str(video.parent / (video.stem + ".meta")),
            )
            if path
        ]
        self._postprocessor.submit(
            video,
            video.with_suffix(".mp4"),
            related_files=related,
            metadata=self._build_media_metadata(),
        )

    def _build_media_metadata(self) -> MediaMetadata:
        """Build ffmpeg-injectable metadata from the current live room state."""
        room_info = self._live.room_info
        user_info = self._live.user_info
        title = room_info.title if room_info else ""
        artist = user_info.name if user_info else ""
        date = ""
        if room_info and room_info.live_start_time:
            date = datetime.fromtimestamp(room_info.live_start_time, tz=UTC).strftime(
                "%Y-%m-%d"
            )
        description = room_info.description if room_info else ""
        area = room_info.area_name if room_info else ""
        comment = f"Bilibili Live Room {self._room_id}"
        if area:
            comment += f" - {area}"
        return MediaMetadata(
            title=title,
            artist=artist,
            date=date,
            description=description,
            comment=comment,
        )

    def _emit_file_completed_events(self, segment: CompletedSegment) -> None:
        """Publish one completed-file event per file the segment produced."""
        if segment.video_path:
            self._event_center.submit(
                VideoFileCompletedEvent.from_data(
                    VideoFileCompletedEventData(
                        room_id=self._room_id, path=segment.video_path
                    )
                )
            )
        if segment.danmaku_path:
            self._event_center.submit(
                DanmakuFileCompletedEvent.from_data(
                    DanmakuFileCompletedEventData(
                        room_id=self._room_id, path=segment.danmaku_path
                    )
                )
            )
        if segment.raw_danmaku_path:
            self._event_center.submit(
                RawDanmakuFileCompletedEvent.from_data(
                    RawDanmakuFileCompletedEventData(
                        room_id=self._room_id, path=segment.raw_danmaku_path
                    )
                )
            )

    def _on_postprocessing_completed(self, item: PostprocessingItem) -> None:
        """Publish the post-processing events once an item leaves the queue.

        The per-video event fires for every successful item; the batch event
        only once the queue has drained, listing everything it produced.
        """
        if item.status is PostprocessingStatus.COMPLETED:
            self._postprocessed_files.append(str(item.output_path))
            self._event_center.submit(
                VideoPostprocessingCompletedEvent.from_data(
                    VideoPostprocessingCompletedEventData(
                        room_id=self._room_id, path=str(item.output_path)
                    )
                )
            )
        if self._postprocessor.queue_size == 0 and self._postprocessed_files:
            files = self._postprocessed_files
            self._postprocessed_files = []
            self._event_center.submit(
                PostprocessingCompletedEvent.from_data(
                    PostprocessingCompletedEventData(room_id=self._room_id, files=files)
                )
            )

    # ── lifecycle ────────────────────────────────────────────────────────

    async def setup(self) -> None:
        """Load room info, resolve danmaku servers, then start the components.

        Both steps are prerequisites, not niceties: without ``live.init()`` the
        room/user info stays empty (so file names and the task card have nothing
        to show), and without the danmaku server list the client has nowhere to
        connect, which strands the whole event-driven start/stop flow.
        """
        await self._live.init()
        await self._fetch_danmu_info()
        # The postprocessor is a queue worker: unless it is running, everything
        # a finished segment submits just sits in the queue, so no recording
        # would ever be remuxed or have its danmaku converted.
        await self._postprocessor.start()
        if self._monitor_enabled:
            await self._start_monitoring()
        if not self._recorder_enabled:
            self._monitor.remove_listener(self._recorder)

    async def _fetch_danmu_info(self) -> None:
        """Feed the danmaku client the broadcast hosts and auth token."""
        info = await self._live.api.get_danmu_info(self._room_id)
        usable = [entry for entry in info.get("host_list", []) if entry.get("host")]
        hosts = [entry["host"] for entry in usable]
        # Each host states its own port, and the two lists have to stay aligned:
        # rotating to a later host with the first one's port aims at an address
        # nobody advertised.
        ports = [entry.get("wss_port") or 443 for entry in usable]
        self._danmaku_client.set_danmu_info(hosts, info.get("token", ""), ports=ports)

    async def destroy(self) -> None:
        """Tear down all components for this task."""
        self._monitor.disable()
        self._monitor.remove_listener(self._recorder)
        await self._danmaku_client.stop()
        await self._recorder.stop()
        self._recorder.set_segment_listener(None)
        self._recorder.set_segment_started_listener(None)
        self._recorder.set_cover_listener(None)
        await self._postprocessor.stop()

    # ── monitor control ──────────────────────────────────────────────────

    async def enable_monitor(self) -> None:
        """Enable live monitoring (starts the danmaku client + monitor)."""
        if self._monitor_enabled:
            return
        self._monitor_enabled = True
        await self._start_monitoring()
        logger.debug("Monitor enabled for room %d", self._room_id)

    async def disable_monitor(self) -> None:
        """Disable live monitoring (stops the monitor + danmaku client)."""
        if not self._monitor_enabled:
            return
        self._monitor_enabled = False
        self._monitor.disable()
        await self._danmaku_client.stop()
        # Without the monitor no live-end event will ever arrive, so a recording
        # in progress would keep running and report "recording" forever.
        await self._recorder.stop_recording()
        logger.debug("Monitor disabled for room %d", self._room_id)

    async def _start_monitoring(self) -> None:
        await self._danmaku_client.start()
        self._monitor.enable()

    # ── recorder control ─────────────────────────────────────────────────

    def enable_recorder(self) -> None:
        """Enable recording, picking up a broadcast that is already under way.

        Attaching the listener only arranges for the *next* ``live_began``, and
        for a room that is live right now that event has already been and gone.
        Waiting for another one means waiting for the streamer to go off and back
        on air, which is why switching recording back on used to do nothing at
        all (#17).
        """
        if self._recorder_enabled:
            return
        self._recorder_enabled = True
        self._monitor.add_listener(self._recorder)
        if self._monitor.is_living:
            logger.info(
                "Recorder enabled for room %d while it is live, starting now",
                self._room_id,
            )
            self._recorder.on_live_began(self._live)
        else:
            logger.debug("Recorder enabled for room %d", self._room_id)

    async def disable_recorder(self) -> None:
        """Disable recording and finalize any segment still in progress."""
        if not self._recorder_enabled:
            return
        self._recorder_enabled = False
        self._monitor.remove_listener(self._recorder)
        # Dropping the listener only blocks future live-start events; the
        # current segment has to be closed out explicitly.
        await self._recorder.stop_recording()
        logger.debug("Recorder disabled for room %d", self._room_id)

    def update_out_dir(self, out_dir: str) -> None:
        """Propagate an output directory change to the underlying recorder."""
        self._recorder.update_out_dir(out_dir)

    def update_postprocessing(
        self,
        *,
        remux_enabled: bool | None = None,
        inject_metadata_enabled: bool | None = None,
        danmaku_to_ass_enabled: bool | None = None,
        danmaku_config: DanmakuToAssConfig | None = None,
    ) -> None:
        """Propagate a post-processing settings change to the running worker.

        Without this a task keeps the switches it was built with, so turning
        e.g. danmaku→ASS on only takes effect for rooms added afterwards.
        """
        self._postprocessor.update_options(
            remux_enabled=remux_enabled,
            inject_metadata_enabled=inject_metadata_enabled,
            danmaku_to_ass_enabled=danmaku_to_ass_enabled,
            danmaku_config=danmaku_config,
        )

    # ── data ─────────────────────────────────────────────────────────────

    def get_data(self) -> TaskData:
        """Build a snapshot of the task data for API responses."""
        room_info = self._live.room_info
        user_info = self._live.user_info
        stream_recorder = self._recorder.stream_recorder
        stats = stream_recorder.statistics
        item = self._postprocessor.current_item
        status = TaskStatus(
            monitor_enabled=self._monitor_enabled,
            recorder_enabled=self._recorder_enabled,
            running_status=self.running_status,
            stream_url=stream_recorder.current_stream_url,
            stream_host=stream_recorder.current_stream_host,
            dl_total=stats.dl_total,
            dl_rate=stats.dl_rate,
            rec_elapsed=stats.rec_elapsed,
            rec_total=int(stats.rec_total),
            rec_rate=stats.rec_rate,
            danmu_total=stats.danmu_total,
            danmu_rate=stats.danmu_rate,
            recording_path=stream_recorder.current_video_path,
            real_stream_format=stream_recorder.real_stream_format or "",
            real_quality_number=stream_recorder.real_quality_number or 0,
            postprocessor_status=item.status.value if item else "",
            postprocessing_path=str(item.source_path) if item else "",
            postprocessing_progress=item.progress.percent if item else 0.0,
        )
        return TaskData(
            room_id=self._room_id,
            user_name=user_info.name if user_info else "",
            room_title=room_info.title if room_info else "",
            area=room_info.area_name if room_info else "",
            parent_area=room_info.parent_area_name if room_info else "",
            live_status=self._monitor.is_living,
            task_status=status,
        )

    def get_param(self) -> TaskParam:
        """Get task parameters (configuration snapshot)."""
        return TaskParam(
            room_id=self._room_id,
            enable_monitor=self._monitor_enabled,
            enable_recorder=self._recorder_enabled,
        )

    def get_metadata(self) -> TaskMetadata:
        """Get recording metadata."""
        room_info = self._live.room_info
        user_info = self._live.user_info
        return TaskMetadata(
            room_id=self._room_id,
            user_name=user_info.name if user_info else "",
            room_title=room_info.title if room_info else "",
            area=room_info.area_name if room_info else "",
            parent_area=room_info.parent_area_name if room_info else "",
            live_start_time=room_info.live_start_time if room_info else 0,
            cover_url=room_info.cover if room_info else "",
        )

    def get_profile(self) -> dict[str, object]:
        """Get current stream ffprobe profile (empty if not recording)."""
        return {}

    def get_videos(self) -> list[VideoFileDetail]:
        """Detail of the video file being written, if a recording is in progress."""
        path = self._recorder.stream_recorder.current_video_path
        if not path:
            return []
        return [
            VideoFileDetail(
                path=path, size=_file_size(path), status=FileStatus.RECORDING
            )
        ]

    def get_danmakus(self) -> list[DanmakuFileDetail]:
        """Detail of the danmaku files being written alongside the video.

        The raw JSONL file is listed too when the user enabled it, so the UI
        reflects everything the recording actually produces.
        """
        recorder = self._recorder.stream_recorder
        paths = [recorder.current_danmaku_path, recorder.current_raw_danmaku_path]
        return [
            DanmakuFileDetail(
                path=path, size=_file_size(path), status=FileStatus.RECORDING
            )
            for path in paths
            if path
        ]

    async def refresh_info(self) -> None:
        """Refresh room/user info from the API."""
        await self._live.init()


class RecordTaskManager:
    """Manages multiple record tasks.

    Tasks are created through an injected factory so the manager stays
    decoupled from component construction (and is easy to test). Provides
    add/remove/start/stop/query operations.
    """

    def __init__(
        self,
        task_factory: Callable[[int], RecordTask] | None = None,
        *,
        space_monitor: SpaceMonitor | None = None,
        space_reclaimer: SpaceReclaimer | None = None,
        on_task_added: Callable[[int, bool], bool] | None = None,
        on_task_removed: Callable[[int], None] | None = None,
    ) -> None:
        """
        Args:
            task_factory: Builds a task's component graph for a room.
            space_monitor: Disk-space monitor started with the manager.
            space_reclaimer: Disk-space reclaimer bound to the monitor.
            on_task_added: Called as ``(room_id, auto_enable)`` before the task
                is built, so the factory can read the room's configuration.
                Returns whether a new config entry was created, which decides
                whether a failed setup should roll it back again.
            on_task_removed: Called after a task is destroyed.
        """
        self._tasks: dict[int, RecordTask] = {}
        self._task_factory = task_factory
        self._space_monitor = space_monitor
        self._space_reclaimer = space_reclaimer
        self._on_task_added = on_task_added
        self._on_task_removed = on_task_removed

    @property
    def task_count(self) -> int:
        return len(self._tasks)

    @property
    def space_monitor(self) -> SpaceMonitor | None:
        return self._space_monitor

    @property
    def space_reclaimer(self) -> SpaceReclaimer | None:
        return self._space_reclaimer

    async def start(self) -> None:
        """Start background services (disk-space monitoring)."""
        if self._space_monitor is not None:
            await self._space_monitor.start()

    async def stop(self) -> None:
        """Stop background services and destroy all tasks.

        Shutting down is not the same as the user deleting tasks: the config
        entries stay behind so the rooms are restored on the next start.
        """
        if self._space_monitor is not None:
            await self._space_monitor.stop()
        for room_id in list(self._tasks):
            await self._destroy_task(room_id)

    def get_task(self, room_id: int) -> RecordTask | None:
        """Get a task by room ID."""
        return self._tasks.get(room_id)

    def get_all_tasks(self) -> list[RecordTask]:
        """Get all tasks."""
        return list(self._tasks.values())

    async def add_task(self, room_id: int, *, auto_enable: bool = True) -> RecordTask:
        """Create, set up, and register a new task.

        The room is registered in the configuration first so the factory can
        resolve its options, and so the task survives a restart. A setup that
        fails halfway is rolled back: the half-built task is torn down and a
        config entry created by this call is removed again.

        Args:
            room_id: The room to record.
            auto_enable: Whether monitoring and recording start enabled. Only
                applies to a room that is not configured yet.

        Raises:
            ValueError: If a task for the room already exists.
            RuntimeError: If no task factory was configured.
        """
        if room_id in self._tasks:
            raise ValueError(f"Task for room {room_id} already exists")
        if self._task_factory is None:
            raise RuntimeError("No task factory configured")
        registered = (
            self._on_task_added(room_id, auto_enable)
            if self._on_task_added is not None
            else False
        )
        task = self._task_factory(room_id)
        try:
            await task.setup()
        except Exception:
            await self._rollback_task(task, room_id, registered)
            raise
        self._tasks[room_id] = task
        logger.info("Added task for room %d", room_id)
        return task

    async def _rollback_task(
        self, task: RecordTask, room_id: int, registered: bool
    ) -> None:
        """Undo a failed ``add_task`` without masking the original error."""
        try:
            await task.destroy()
        except Exception:
            logger.exception("Failed to tear down task for room %d", room_id)
        if registered and self._on_task_removed is not None:
            self._on_task_removed(room_id)

    async def remove_task(self, room_id: int) -> None:
        """Destroy and remove a task, and forget its configuration.

        Raises:
            KeyError: If no task exists for the room.
        """
        await self._destroy_task(room_id)
        if self._on_task_removed is not None:
            self._on_task_removed(room_id)
        logger.info("Removed task for room %d", room_id)

    async def _destroy_task(self, room_id: int) -> None:
        """Tear a task down and drop it from the registry.

        Raises:
            KeyError: If no task exists for the room.
        """
        task = self._get_or_raise(room_id)
        await task.destroy()
        del self._tasks[room_id]

    async def start_task(self, room_id: int) -> None:
        """Enable monitoring for a task."""
        await self._get_or_raise(room_id).enable_monitor()

    async def stop_task(self, room_id: int) -> None:
        """Disable monitoring for a task."""
        await self._get_or_raise(room_id).disable_monitor()

    def enable_recorder(self, room_id: int) -> None:
        """Enable recording for a task."""
        self._get_or_raise(room_id).enable_recorder()

    async def disable_recorder(self, room_id: int) -> None:
        """Disable recording for a task."""
        await self._get_or_raise(room_id).disable_recorder()

    def get_task_data(self, room_id: int) -> TaskData:
        """Get the task data snapshot for a room."""
        return self._get_or_raise(room_id).get_data()

    def get_all_task_data(self) -> list[TaskData]:
        """Get task data snapshots for all rooms."""
        return [task.get_data() for task in self._tasks.values()]

    async def load_tasks(self, room_ids: list[int]) -> None:
        """Add tasks for any of the given room IDs not already present.

        Used to restore the configured tasks at startup (§5.2): one room that
        cannot be loaded (network failure, room gone) must not keep the others
        from loading, so failures are logged per room.
        """
        for room_id in room_ids:
            if room_id in self._tasks:
                continue
            try:
                await self.add_task(room_id)
            except Exception:
                logger.exception("Failed to load task for room %d", room_id)

    async def batch_refresh_info(self) -> None:
        """Refresh info for all tasks."""
        for task in self._tasks.values():
            await task.refresh_info()

    def _get_or_raise(self, room_id: int) -> RecordTask:
        task = self._tasks.get(room_id)
        if task is None:
            raise KeyError(f"No task for room {room_id}")
        return task
