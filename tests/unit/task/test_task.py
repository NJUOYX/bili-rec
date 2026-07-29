"""Tests for task orchestration: RecordTask and RecordTaskManager."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from birec.bili.live_monitor import LiveMonitor
from birec.bili.models import LiveStatus, RoomInfo, UserInfo
from birec.core.path_provider import PathProvider
from birec.core.recorder import Recorder
from birec.task import (
    DanmakuFileDetail,
    FileStatus,
    RecordTask,
    RecordTaskManager,
    RunningStatus,
    TaskData,
    TaskStatus,
    VideoFileDetail,
)


def _make_live() -> MagicMock:
    live = MagicMock()
    live.room_id = 12345
    live.room_info = None
    live.user_info = None
    live.init = AsyncMock()
    live.get_stream_url = AsyncMock(return_value="https://cdn.example.com/live.flv")
    live.get_live_status = AsyncMock(return_value=LiveStatus.LIVE)
    live.api.get_danmu_info = AsyncMock(
        return_value={
            "host_list": [{"host": "broadcastlv.chat.bilibili.com"}, {"host": ""}],
            "token": "danmu-token",
        }
    )
    return live


def _make_components() -> dict[str, MagicMock]:
    """Build mocked task components."""
    live = _make_live()
    danmaku_client = MagicMock()
    danmaku_client.start = AsyncMock()
    danmaku_client.stop = AsyncMock()
    monitor = MagicMock()
    monitor.is_living = False
    recorder = MagicMock()
    recorder.is_recording = False
    recorder.stop = AsyncMock()
    recorder.stream_recorder.current_video_path = ""
    recorder.stream_recorder.current_danmaku_path = ""
    recorder.stream_recorder.current_raw_danmaku_path = ""
    recorder.stream_recorder.real_stream_format = None
    recorder.stream_recorder.real_quality_number = None
    postprocessor = MagicMock()
    postprocessor.is_running = False
    return {
        "live": live,
        "danmaku_client": danmaku_client,
        "monitor": monitor,
        "recorder": recorder,
        "postprocessor": postprocessor,
    }


def _make_task(
    *,
    room_id: int = 12345,
    enable_monitor: bool = True,
    enable_recorder: bool = True,
) -> tuple[RecordTask, dict[str, MagicMock]]:
    comps = _make_components()
    task = RecordTask(
        room_id,
        comps["live"],
        comps["danmaku_client"],
        comps["monitor"],
        comps["recorder"],
        comps["postprocessor"],
        enable_monitor=enable_monitor,
        enable_recorder=enable_recorder,
    )
    return task, comps


class TestModels:
    def test_running_status_values(self) -> None:
        assert RunningStatus.STOPPED.value == "stopped"
        assert RunningStatus.RECORDING.value == "recording"
        assert RunningStatus.REMUXING.value == "remuxing"

    def test_task_status_defaults(self) -> None:
        status = TaskStatus()
        assert not status.monitor_enabled
        assert status.running_status == RunningStatus.STOPPED

    def test_file_detail_models(self) -> None:
        video = VideoFileDetail(path="/tmp/a.mp4", size=100)
        assert video.status == FileStatus.UNKNOWN
        danmaku = DanmakuFileDetail(path="/tmp/a.xml")
        assert danmaku.size == 0


class TestRecordTaskFileDetails:
    def test_no_files_while_idle(self) -> None:
        task, _ = _make_task()
        assert task.get_videos() == []
        assert task.get_danmakus() == []

    def test_files_report_real_paths_and_sizes(self, tmp_path: Path) -> None:
        task, comps = _make_task()
        video = tmp_path / "a.flv"
        video.write_bytes(b"x" * 7)
        danmaku = tmp_path / "a.xml"
        danmaku.write_text("<i></i>", encoding="utf-8")
        stream_recorder = comps["recorder"].stream_recorder
        stream_recorder.current_video_path = str(video)
        stream_recorder.current_danmaku_path = str(danmaku)

        videos = task.get_videos()
        assert [(f.path, f.size, f.status) for f in videos] == [
            (str(video), 7, FileStatus.RECORDING)
        ]
        danmakus = task.get_danmakus()
        assert [(f.path, f.size) for f in danmakus] == [(str(danmaku), 7)]

    def test_raw_danmaku_file_is_listed_too(self, tmp_path: Path) -> None:
        task, comps = _make_task()
        stream_recorder = comps["recorder"].stream_recorder
        stream_recorder.current_danmaku_path = str(tmp_path / "a.xml")
        stream_recorder.current_raw_danmaku_path = str(tmp_path / "a.jsonl")

        # Neither file exists yet: a size of 0 beats hiding the file entirely.
        assert [f.size for f in task.get_danmakus()] == [0, 0]
        assert [Path(f.path).suffix for f in task.get_danmakus()] == [
            ".xml",
            ".jsonl",
        ]


class TestRecordTaskStatus:
    def test_properties(self) -> None:
        task, _ = _make_task()
        assert task.room_id == 12345
        assert task.monitor_enabled
        assert task.recorder_enabled

    def test_status_recording(self) -> None:
        task, comps = _make_task()
        comps["recorder"].is_recording = True
        assert task.running_status == RunningStatus.RECORDING

    def test_status_remuxing(self) -> None:
        task, comps = _make_task()
        comps["postprocessor"].is_running = True
        assert task.running_status == RunningStatus.REMUXING

    def test_status_waiting(self) -> None:
        task, comps = _make_task()
        comps["monitor"].is_living = True
        assert task.running_status == RunningStatus.WAITING

    def test_status_stopped(self) -> None:
        task, _ = _make_task()
        assert task.running_status == RunningStatus.STOPPED


class TestRecordTaskLifecycle:
    async def test_setup_loads_room_info(self) -> None:
        """Room/user info must be loaded, or the task card renders empty."""
        task, comps = _make_task()
        await task.setup()
        comps["live"].init.assert_awaited_once()

    async def test_setup_feeds_danmaku_hosts(self) -> None:
        """Without hosts the danmaku client can never open its WebSocket."""
        task, comps = _make_task()
        await task.setup()
        comps["danmaku_client"].set_danmu_info.assert_called_once_with(
            ["broadcastlv.chat.bilibili.com"], "danmu-token"
        )

    async def test_setup_feeds_hosts_even_when_monitor_disabled(self) -> None:
        """A later ``enable_monitor`` must not need a second info fetch."""
        task, comps = _make_task(enable_monitor=False)
        await task.setup()
        comps["danmaku_client"].set_danmu_info.assert_called_once()

    async def test_setup_starts_monitoring(self) -> None:
        task, comps = _make_task(enable_monitor=True)
        await task.setup()
        comps["danmaku_client"].start.assert_awaited_once()
        comps["monitor"].enable.assert_called_once()

    async def test_setup_skips_monitor_when_disabled(self) -> None:
        task, comps = _make_task(enable_monitor=False)
        await task.setup()
        comps["danmaku_client"].start.assert_not_awaited()
        comps["monitor"].enable.assert_not_called()

    async def test_setup_removes_recorder_when_disabled(self) -> None:
        task, comps = _make_task(enable_recorder=False)
        await task.setup()
        comps["monitor"].remove_listener.assert_called_once_with(comps["recorder"])

    async def test_destroy_stops_everything(self) -> None:
        task, comps = _make_task()
        await task.destroy()
        comps["monitor"].disable.assert_called_once()
        comps["danmaku_client"].stop.assert_awaited_once()
        comps["recorder"].stop.assert_awaited_once()
        comps["monitor"].remove_listener.assert_called_once_with(comps["recorder"])


class TestRecordTaskControl:
    async def test_enable_monitor_idempotent(self) -> None:
        task, comps = _make_task(enable_monitor=True)
        await task.enable_monitor()  # already enabled -> no-op
        comps["danmaku_client"].start.assert_not_awaited()

    async def test_disable_then_enable_monitor(self) -> None:
        task, comps = _make_task(enable_monitor=False)
        await task.enable_monitor()
        assert task.monitor_enabled
        comps["danmaku_client"].start.assert_awaited_once()

        await task.disable_monitor()
        assert not task.monitor_enabled
        comps["monitor"].disable.assert_called_once()
        comps["danmaku_client"].stop.assert_awaited_once()

    def test_enable_disable_recorder(self) -> None:
        task, comps = _make_task(enable_recorder=False)
        task.enable_recorder()
        assert task.recorder_enabled
        comps["monitor"].add_listener.assert_called_once_with(comps["recorder"])

        task.disable_recorder()
        assert not task.recorder_enabled
        comps["monitor"].remove_listener.assert_called_once_with(comps["recorder"])


class TestRecordTaskData:
    def test_get_data_minimal(self) -> None:
        task, _ = _make_task()
        data = task.get_data()
        assert isinstance(data, TaskData)
        assert data.room_id == 12345
        assert data.user_name == ""
        assert data.task_status.monitor_enabled

    def test_get_data_with_room_info(self) -> None:
        task, comps = _make_task()
        comps["live"].room_info = RoomInfo(
            room_id=12345,
            short_room_id=0,
            area_id=1,
            title="Test Room",
            area_name="Game",
            parent_area_id=1,
            parent_area_name="Entertainment",
            live_status=LiveStatus.LIVE,
            live_start_time=0,
            online=1,
            cover="",
            tags="",
            description="",
            uid=99,
        )
        comps["live"].user_info = UserInfo(
            uid=99, name="Streamer", gender="male", face=""
        )
        comps["monitor"].is_living = True
        comps["recorder"].stream_recorder.real_stream_format = "flv"
        comps["recorder"].stream_recorder.real_quality_number = 10000

        data = task.get_data()
        assert data.room_title == "Test Room"
        assert data.user_name == "Streamer"
        assert data.area == "Game"
        assert data.parent_area == "Entertainment"
        assert data.live_status is True
        assert data.task_status.real_stream_format == "flv"
        assert data.task_status.real_quality_number == 10000


class TestRecordTaskManager:
    def _factory(self, tasks: dict[int, RecordTask]) -> MagicMock:
        def factory(room_id: int) -> RecordTask:
            task, _ = _make_task(room_id=room_id)
            task.setup = AsyncMock()  # type: ignore[method-assign]
            task.destroy = AsyncMock()  # type: ignore[method-assign]
            tasks[room_id] = task
            return task

        return MagicMock(side_effect=factory)

    async def test_add_task(self) -> None:
        created: dict[int, RecordTask] = {}
        mgr = RecordTaskManager(self._factory(created))
        task = await mgr.add_task(1)
        assert task.room_id == 1
        assert mgr.task_count == 1
        created[1].setup.assert_awaited_once()  # type: ignore[attr-defined]

    async def test_add_duplicate_raises(self) -> None:
        mgr = RecordTaskManager(self._factory({}))
        await mgr.add_task(1)
        with pytest.raises(ValueError, match="already exists"):
            await mgr.add_task(1)

    async def test_add_without_factory_raises(self) -> None:
        mgr = RecordTaskManager()
        with pytest.raises(RuntimeError, match="factory"):
            await mgr.add_task(1)

    async def test_remove_task(self) -> None:
        created: dict[int, RecordTask] = {}
        mgr = RecordTaskManager(self._factory(created))
        await mgr.add_task(1)
        await mgr.remove_task(1)
        assert mgr.task_count == 0
        created[1].destroy.assert_awaited_once()  # type: ignore[attr-defined]

    async def test_remove_nonexistent_raises(self) -> None:
        mgr = RecordTaskManager(self._factory({}))
        with pytest.raises(KeyError):
            await mgr.remove_task(999)

    async def test_get_task(self) -> None:
        mgr = RecordTaskManager(self._factory({}))
        await mgr.add_task(1)
        assert mgr.get_task(1) is not None
        assert mgr.get_task(2) is None

    async def test_start_stop_task(self) -> None:
        created: dict[int, RecordTask] = {}
        mgr = RecordTaskManager(self._factory(created))
        await mgr.add_task(1)
        created[1].enable_monitor = AsyncMock()  # type: ignore[method-assign]
        created[1].disable_monitor = AsyncMock()  # type: ignore[method-assign]
        await mgr.start_task(1)
        created[1].enable_monitor.assert_awaited_once()  # type: ignore[attr-defined]
        await mgr.stop_task(1)
        created[1].disable_monitor.assert_awaited_once()  # type: ignore[attr-defined]

    async def test_get_task_data(self) -> None:
        mgr = RecordTaskManager(self._factory({}))
        await mgr.add_task(1)
        data = mgr.get_task_data(1)
        assert data.room_id == 1
        assert len(mgr.get_all_task_data()) == 1

    async def test_load_tasks(self) -> None:
        mgr = RecordTaskManager(self._factory({}))
        await mgr.load_tasks([1, 2, 3])
        assert mgr.task_count == 3
        await mgr.load_tasks([2, 3, 4])  # 2,3 already present
        assert mgr.task_count == 4


class TestRecordTaskManagerSpace:
    async def test_start_starts_space_monitor(self) -> None:
        space_monitor = MagicMock()
        space_monitor.start = AsyncMock()
        mgr = RecordTaskManager(
            lambda rid: _make_task(room_id=rid)[0], space_monitor=space_monitor
        )
        await mgr.start()
        space_monitor.start.assert_awaited_once()

    async def test_start_without_monitor_is_noop(self) -> None:
        mgr = RecordTaskManager(lambda rid: _make_task(room_id=rid)[0])
        await mgr.start()  # should not raise
        assert mgr.space_monitor is None

    async def test_stop_stops_monitor_and_destroys_tasks(self) -> None:
        created: dict[int, RecordTask] = {}
        space_monitor = MagicMock()
        space_monitor.stop = AsyncMock()

        def factory(room_id: int) -> RecordTask:
            task, _ = _make_task(room_id=room_id)
            task.setup = AsyncMock()  # type: ignore[method-assign]
            task.destroy = AsyncMock()  # type: ignore[method-assign]
            created[room_id] = task
            return task

        mgr = RecordTaskManager(factory, space_monitor=space_monitor)
        await mgr.add_task(1)
        await mgr.add_task(2)

        await mgr.stop()

        space_monitor.stop.assert_awaited_once()
        assert mgr.task_count == 0
        created[1].destroy.assert_awaited_once()  # type: ignore[attr-defined]
        created[2].destroy.assert_awaited_once()  # type: ignore[attr-defined]

    def test_space_reclaimer_property(self) -> None:
        reclaimer = MagicMock()
        mgr = RecordTaskManager(space_reclaimer=reclaimer)
        assert mgr.space_reclaimer is reclaimer


class TestEventDrivenRecording:
    """Acceptance: event-driven auto start/stop of recording via the monitor."""

    async def test_live_began_starts_recording(self, tmp_path: Path) -> None:
        live = _make_live()
        monitor = LiveMonitor(live)
        recorder = Recorder(
            room_id=12345,
            live=live,
            monitor=monitor,
            session=MagicMock(),
            path_provider=PathProvider(str(tmp_path), "{roomid}"),
        )
        danmaku_client = MagicMock()
        danmaku_client.start = AsyncMock()
        danmaku_client.stop = AsyncMock()
        postprocessor = MagicMock()
        postprocessor.is_running = False

        task = RecordTask(
            12345,
            live,
            danmaku_client,
            monitor,
            recorder,
            postprocessor,
            enable_monitor=True,
            enable_recorder=True,
        )
        await task.setup()

        # Simulate the monitor detecting live start; the recorder (registered
        # as a listener) should begin recording automatically.
        await monitor._emit("live_began", live)
        await asyncio.sleep(0.02)

        assert recorder.is_recording is True
        assert task.running_status == RunningStatus.RECORDING

        # Simulate live end; recording should stop.
        await monitor._emit("live_ended", live)
        await asyncio.sleep(0.02)

        assert recorder.is_recording is False
        await task.destroy()

    async def test_recorder_disabled_does_not_record(self, tmp_path: Path) -> None:
        live = _make_live()
        monitor = LiveMonitor(live)
        recorder = Recorder(
            room_id=12345,
            live=live,
            monitor=monitor,
            session=MagicMock(),
            path_provider=PathProvider(str(tmp_path), "{roomid}"),
        )
        danmaku_client = MagicMock()
        danmaku_client.start = AsyncMock()
        danmaku_client.stop = AsyncMock()
        postprocessor = MagicMock()
        postprocessor.is_running = False

        task = RecordTask(
            12345,
            live,
            danmaku_client,
            monitor,
            recorder,
            postprocessor,
            enable_monitor=True,
            enable_recorder=False,  # recorder not listening
        )
        await task.setup()

        await monitor._emit("live_began", live)
        await asyncio.sleep(0.02)

        assert recorder.is_recording is False
        await task.destroy()
