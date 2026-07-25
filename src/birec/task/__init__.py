"""Task management: RecordTask, RecordTaskManager, and models."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

__all__ = (
    "RunningStatus",
    "FileStatus",
    "TaskStatus",
    "TaskData",
    "VideoFileDetail",
    "DanmakuFileDetail",
    "RecordTask",
    "RecordTaskManager",
)

logger = logging.getLogger(__name__)


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


class RecordTask:
    """A single room recording task.

    Combines monitoring, recording, and post-processing for one room.
    """

    def __init__(self, room_id: int) -> None:
        self._room_id = room_id
        self._monitor_enabled = False
        self._recorder_enabled = False
        self._running_status = RunningStatus.STOPPED
        self._data = TaskData(room_id=room_id)
        self._video_files: list[VideoFileDetail] = []
        self._danmaku_files: list[DanmakuFileDetail] = []

    @property
    def room_id(self) -> int:
        return self._room_id

    @property
    def monitor_enabled(self) -> bool:
        return self._monitor_enabled

    @property
    def recorder_enabled(self) -> bool:
        return self._recorder_enabled

    @property
    def running_status(self) -> RunningStatus:
        return self._running_status

    @property
    def data(self) -> TaskData:
        return self._data

    @property
    def video_files(self) -> list[VideoFileDetail]:
        return self._video_files.copy()

    @property
    def danmaku_files(self) -> list[DanmakuFileDetail]:
        return self._danmaku_files.copy()

    def enable_monitor(self) -> None:
        """Enable live monitoring."""
        self._monitor_enabled = True
        logger.debug("Monitor enabled for room %d", self._room_id)

    def disable_monitor(self) -> None:
        """Disable live monitoring."""
        self._monitor_enabled = False
        logger.debug("Monitor disabled for room %d", self._room_id)

    def enable_recorder(self) -> None:
        """Enable recording."""
        self._recorder_enabled = True
        logger.debug("Recorder enabled for room %d", self._room_id)

    def disable_recorder(self) -> None:
        """Disable recording."""
        self._recorder_enabled = False
        logger.debug("Recorder disabled for room %d", self._room_id)

    def update_data(self, data: TaskData) -> None:
        """Update task data."""
        self._data = data

    def add_video_file(self, detail: VideoFileDetail) -> None:
        """Add a video file detail."""
        self._video_files.append(detail)

    def add_danmaku_file(self, detail: DanmakuFileDetail) -> None:
        """Add a danmaku file detail."""
        self._danmaku_files.append(detail)


class RecordTaskManager:
    """Manages multiple record tasks.

    Provides add/remove/start/stop/query operations for tasks.
    """

    def __init__(self) -> None:
        self._tasks: dict[int, RecordTask] = {}

    @property
    def task_count(self) -> int:
        return len(self._tasks)

    def get_task(self, room_id: int) -> RecordTask | None:
        """Get a task by room ID."""
        return self._tasks.get(room_id)

    def add_task(self, room_id: int) -> RecordTask:
        """Add a new task.

        Args:
            room_id: Room ID to add.

        Returns:
            The created RecordTask.

        Raises:
            ValueError: If task already exists.
        """
        if room_id in self._tasks:
            raise ValueError(f"Task for room {room_id} already exists")
        task = RecordTask(room_id)
        self._tasks[room_id] = task
        logger.info("Added task for room %d", room_id)
        return task

    def remove_task(self, room_id: int) -> None:
        """Remove a task.

        Args:
            room_id: Room ID to remove.

        Raises:
            KeyError: If task does not exist.
        """
        if room_id not in self._tasks:
            raise KeyError(f"No task for room {room_id}")
        del self._tasks[room_id]
        logger.info("Removed task for room %d", room_id)

    def get_all_tasks(self) -> list[RecordTask]:
        """Get all tasks."""
        return list(self._tasks.values())

    def enable_all_monitors(self) -> None:
        """Enable monitoring for all tasks."""
        for task in self._tasks.values():
            task.enable_monitor()

    def disable_all_monitors(self) -> None:
        """Disable monitoring for all tasks."""
        for task in self._tasks.values():
            task.disable_monitor()

    def enable_all_recorders(self) -> None:
        """Enable recording for all tasks."""
        for task in self._tasks.values():
            task.enable_recorder()

    def disable_all_recorders(self) -> None:
        """Disable recording for all tasks."""
        for task in self._tasks.values():
            task.disable_recorder()
