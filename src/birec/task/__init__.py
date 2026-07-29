"""Task management: RecordTask orchestration and RecordTaskManager."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..bili.danmaku_client import DanmakuClient
    from ..bili.live import Live
    from ..bili.live_monitor import LiveMonitor
    from ..core.recorder import Recorder
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
    ) -> None:
        self._room_id = room_id
        self._live = live
        self._danmaku_client = danmaku_client
        self._monitor = monitor
        self._recorder = recorder
        self._postprocessor = postprocessor
        self._monitor_enabled = enable_monitor
        self._recorder_enabled = enable_recorder

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
        if self._postprocessor.is_running:
            return RunningStatus.REMUXING
        if self._monitor_enabled and self._monitor.is_living:
            return RunningStatus.WAITING
        return RunningStatus.STOPPED

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
        if self._monitor_enabled:
            await self._start_monitoring()
        if not self._recorder_enabled:
            self._monitor.remove_listener(self._recorder)

    async def _fetch_danmu_info(self) -> None:
        """Feed the danmaku client the broadcast hosts and auth token."""
        info = await self._live.api.get_danmu_info(self._room_id)
        hosts = [
            entry["host"] for entry in info.get("host_list", []) if entry.get("host")
        ]
        self._danmaku_client.set_danmu_info(hosts, info.get("token", ""))

    async def destroy(self) -> None:
        """Tear down all components for this task."""
        self._monitor.disable()
        self._monitor.remove_listener(self._recorder)
        await self._danmaku_client.stop()
        await self._recorder.stop()

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
        logger.debug("Monitor disabled for room %d", self._room_id)

    async def _start_monitoring(self) -> None:
        await self._danmaku_client.start()
        self._monitor.enable()

    # ── recorder control ─────────────────────────────────────────────────

    def enable_recorder(self) -> None:
        """Enable recording by registering the recorder as a monitor listener."""
        if self._recorder_enabled:
            return
        self._recorder_enabled = True
        self._monitor.add_listener(self._recorder)
        logger.debug("Recorder enabled for room %d", self._room_id)

    def disable_recorder(self) -> None:
        """Disable recording by removing the recorder from the monitor."""
        if not self._recorder_enabled:
            return
        self._recorder_enabled = False
        self._monitor.remove_listener(self._recorder)
        logger.debug("Recorder disabled for room %d", self._room_id)

    # ── data ─────────────────────────────────────────────────────────────

    def get_data(self) -> TaskData:
        """Build a snapshot of the task data for API responses."""
        room_info = self._live.room_info
        user_info = self._live.user_info
        stream_recorder = self._recorder.stream_recorder
        status = TaskStatus(
            monitor_enabled=self._monitor_enabled,
            recorder_enabled=self._recorder_enabled,
            running_status=self.running_status,
            recording_path=stream_recorder.current_video_path,
            real_stream_format=stream_recorder.real_stream_format or "",
            real_quality_number=stream_recorder.real_quality_number or 0,
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
    ) -> None:
        self._tasks: dict[int, RecordTask] = {}
        self._task_factory = task_factory
        self._space_monitor = space_monitor
        self._space_reclaimer = space_reclaimer

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
        """Stop background services and destroy all tasks."""
        if self._space_monitor is not None:
            await self._space_monitor.stop()
        for room_id in list(self._tasks):
            await self.remove_task(room_id)

    def get_task(self, room_id: int) -> RecordTask | None:
        """Get a task by room ID."""
        return self._tasks.get(room_id)

    def get_all_tasks(self) -> list[RecordTask]:
        """Get all tasks."""
        return list(self._tasks.values())

    async def add_task(self, room_id: int) -> RecordTask:
        """Create, set up, and register a new task.

        Raises:
            ValueError: If a task for the room already exists.
            RuntimeError: If no task factory was configured.
        """
        if room_id in self._tasks:
            raise ValueError(f"Task for room {room_id} already exists")
        if self._task_factory is None:
            raise RuntimeError("No task factory configured")
        task = self._task_factory(room_id)
        await task.setup()
        self._tasks[room_id] = task
        logger.info("Added task for room %d", room_id)
        return task

    async def remove_task(self, room_id: int) -> None:
        """Destroy and remove a task.

        Raises:
            KeyError: If no task exists for the room.
        """
        task = self._get_or_raise(room_id)
        await task.destroy()
        del self._tasks[room_id]
        logger.info("Removed task for room %d", room_id)

    async def start_task(self, room_id: int) -> None:
        """Enable monitoring for a task."""
        await self._get_or_raise(room_id).enable_monitor()

    async def stop_task(self, room_id: int) -> None:
        """Disable monitoring for a task."""
        await self._get_or_raise(room_id).disable_monitor()

    def enable_recorder(self, room_id: int) -> None:
        """Enable recording for a task."""
        self._get_or_raise(room_id).enable_recorder()

    def disable_recorder(self, room_id: int) -> None:
        """Disable recording for a task."""
        self._get_or_raise(room_id).disable_recorder()

    def get_task_data(self, room_id: int) -> TaskData:
        """Get the task data snapshot for a room."""
        return self._get_or_raise(room_id).get_data()

    def get_all_task_data(self) -> list[TaskData]:
        """Get task data snapshots for all rooms."""
        return [task.get_data() for task in self._tasks.values()]

    async def load_tasks(self, room_ids: list[int]) -> None:
        """Add tasks for any of the given room IDs not already present."""
        for room_id in room_ids:
            if room_id not in self._tasks:
                await self.add_task(room_id)

    async def batch_refresh_info(self) -> None:
        """Refresh info for all tasks."""
        for task in self._tasks.values():
            await task.refresh_info()

    def _get_or_raise(self, room_id: int) -> RecordTask:
        task = self._tasks.get(room_id)
        if task is None:
            raise KeyError(f"No task for room {room_id}")
        return task
