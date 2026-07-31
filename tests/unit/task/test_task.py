"""Tests for task orchestration: RecordTask and RecordTaskManager."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from birec.bili.live_monitor import LiveMonitor
from birec.bili.models import LiveStatus, RoomInfo, UserInfo
from birec.core.models import CompletedSegment, StartedSegment
from birec.core.path_provider import PathProvider
from birec.core.recorder import Recorder
from birec.postprocess.danmaku_to_ass import DanmakuToAssConfig
from birec.postprocess.models import (
    PostprocessingItem,
    PostprocessingProgress,
    PostprocessingStatus,
)
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
            "host_list": [
                {"host": "broadcastlv.chat.bilibili.com", "wss_port": 443},
                {"host": ""},
            ],
            "token": "danmu-token",
        }
    )
    return live


def _make_postprocessor() -> MagicMock:
    """A postprocessor mock that behaves like an idle, running worker."""
    postprocessor = MagicMock()
    postprocessor.is_running = False
    postprocessor.current_item = None
    postprocessor.queue_size = 0
    postprocessor.start = AsyncMock()
    postprocessor.stop = AsyncMock()
    return postprocessor


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
    recorder.stop_recording = AsyncMock()
    recorder.stream_recorder.current_video_path = ""
    recorder.stream_recorder.current_danmaku_path = ""
    recorder.stream_recorder.current_raw_danmaku_path = ""
    recorder.stream_recorder.real_stream_format = None
    recorder.stream_recorder.real_quality_number = None
    postprocessor = _make_postprocessor()
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
    event_center: MagicMock | None = None,
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
        event_center=event_center or MagicMock(),
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
        comps["postprocessor"].current_item = PostprocessingItem(
            source_path=Path("a.flv"),
            output_path=Path("a.mp4"),
            status=PostprocessingStatus.REMUXING,
        )
        assert task.running_status == RunningStatus.REMUXING

    def test_status_injecting(self) -> None:
        task, comps = _make_task()
        comps["postprocessor"].current_item = PostprocessingItem(
            source_path=Path("a.flv"),
            output_path=Path("a.mp4"),
            status=PostprocessingStatus.INJECTING,
        )
        assert task.running_status == RunningStatus.INJECTING

    def test_status_ignores_idle_postprocessor(self) -> None:
        """Regression: the worker runs for the task's whole life.

        Keying "remuxing" off ``is_running`` made every task claim to be
        post-processing from the moment it was set up.
        """
        task, comps = _make_task()
        comps["postprocessor"].is_running = True
        comps["postprocessor"].current_item = None
        assert task.running_status == RunningStatus.STOPPED

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
        """Without hosts the danmaku client can never open its WebSocket.

        The port travels with them: the API states it alongside each host, and
        assuming 443 would be ignoring what it told us.
        """
        task, comps = _make_task()
        await task.setup()
        comps["danmaku_client"].set_danmu_info.assert_called_once_with(
            ["broadcastlv.chat.bilibili.com"], "danmu-token", ports=[443]
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

    async def test_setup_starts_the_postprocessor(self) -> None:
        """Regression: the queue worker must be running to process anything.

        Nothing ever started it, so every finished segment just piled up in the
        queue: no remux, and no danmaku XML ever converted to ASS.
        """
        task, comps = _make_task()
        await task.setup()
        comps["postprocessor"].start.assert_awaited_once()

    async def test_destroy_stops_the_postprocessor_and_unbinds(self) -> None:
        task, comps = _make_task()
        await task.destroy()
        comps["postprocessor"].stop.assert_awaited_once()
        # The listener must go too, or a torn-down task keeps being fed.
        comps["recorder"].set_segment_listener.assert_called_with(None)


class TestRecordTaskPostprocessingWiring:
    """A finished segment must reach the postprocessor and the event bus."""

    def _segment_listener(self, comps: dict[str, MagicMock]) -> Callable[..., None]:
        """The callback the task registered on the recorder."""
        listener = comps["recorder"].set_segment_listener.call_args[0][0]
        assert callable(listener)
        return listener  # type: ignore[no-any-return]

    def _started_listener(self, comps: dict[str, MagicMock]) -> Callable[..., None]:
        """The callback the task registered for a segment starting."""
        listener = comps["recorder"].set_segment_started_listener.call_args[0][0]
        assert callable(listener)
        return listener  # type: ignore[no-any-return]

    def _cover_listener(self, comps: dict[str, MagicMock]) -> Callable[..., None]:
        """The callback the task registered for a downloaded cover."""
        listener = comps["recorder"].set_cover_listener.call_args[0][0]
        assert callable(listener)
        return listener  # type: ignore[no-any-return]

    def test_started_files_are_announced(self) -> None:
        """Regression: the "recording began" events had no producer at all.

        Three event classes existed and the notification module offered them as
        something to subscribe to, but nothing ever submitted one, so the whole
        family was unreachable.
        """
        event_center = MagicMock()
        task, comps = _make_task(event_center=event_center)

        self._started_listener(comps)(
            StartedSegment(
                video_path="/rec/a.flv",
                danmaku_path="/rec/a.xml",
                raw_danmaku_path="/rec/a.jsonl",
            )
        )

        submitted = [call.args[0] for call in event_center.submit.call_args_list]
        assert [event.type for event in submitted] == [
            "VideoFileCreatedEvent",
            "DanmakuFileCreatedEvent",
            "RawDanmakuFileCreatedEvent",
        ]
        assert submitted[0].data.room_id == 12345
        assert submitted[0].data.path == "/rec/a.flv"

    def test_a_segment_without_danmaku_announces_only_the_video(self) -> None:
        """Recording with danmaku off must not claim files that do not exist."""
        event_center = MagicMock()
        task, comps = _make_task(event_center=event_center)

        self._started_listener(comps)(StartedSegment(video_path="/rec/a.flv"))

        submitted = [call.args[0] for call in event_center.submit.call_args_list]
        assert [event.type for event in submitted] == ["VideoFileCreatedEvent"]

    def test_a_downloaded_cover_is_announced(self) -> None:
        """Regression: CoverImageDownloadedEvent had no producer either.

        The download itself was unreachable too: nothing in ``src`` ever called
        ``download_cover``.
        """
        event_center = MagicMock()
        task, comps = _make_task(event_center=event_center)

        self._cover_listener(comps)("/rec/a.jpg")

        event = event_center.submit.call_args.args[0]
        assert event.type == "CoverImageDownloadedEvent"
        assert event.data.room_id == 12345
        assert event.data.path == "/rec/a.jpg"

    def test_finished_segment_is_submitted_with_its_danmaku(self) -> None:
        """Regression: the whole post-processing stage was never wired up.

        The recorder finished a segment and nobody was told, so the XML sitting
        next to it was never handed over for ASS conversion.
        """
        task, comps = _make_task()
        self._segment_listener(comps)(
            CompletedSegment(
                video_path="/rec/a.flv",
                danmaku_path="/rec/a.xml",
                raw_danmaku_path="/rec/a.jsonl",
            )
        )

        args, kwargs = comps["postprocessor"].submit.call_args
        assert args == (Path("/rec/a.flv"), Path("/rec/a.mp4"))
        assert kwargs["related_files"] == [Path("/rec/a.xml"), Path("/rec/a.jsonl")]

    def test_segment_without_danmaku_submits_video_only(self) -> None:
        task, comps = _make_task()
        self._segment_listener(comps)(CompletedSegment(video_path="/rec/a.flv"))

        assert comps["postprocessor"].submit.call_args.kwargs["related_files"] == []

    def test_segment_without_video_is_not_submitted(self) -> None:
        task, comps = _make_task()
        self._segment_listener(comps)(CompletedSegment(video_path=""))

        comps["postprocessor"].submit.assert_not_called()

    def test_completed_files_are_announced(self) -> None:
        """The events the WebSocket layer forwards must actually be published."""
        event_center = MagicMock()
        task, comps = _make_task(event_center=event_center)
        self._segment_listener(comps)(
            CompletedSegment(
                video_path="/rec/a.flv",
                danmaku_path="/rec/a.xml",
                raw_danmaku_path="/rec/a.jsonl",
            )
        )

        submitted = [call.args[0] for call in event_center.submit.call_args_list]
        assert [event.type for event in submitted] == [
            "VideoFileCompletedEvent",
            "DanmakuFileCompletedEvent",
            "RawDanmakuFileCompletedEvent",
        ]
        assert submitted[1].data.path == "/rec/a.xml"
        assert submitted[0].data.room_id == 12345

    def test_postprocessed_item_is_announced(self) -> None:
        event_center = MagicMock()
        task, comps = _make_task(event_center=event_center)
        listener = comps["postprocessor"].set_completion_listener.call_args[0][0]

        listener(
            PostprocessingItem(
                source_path=Path("/rec/a.flv"),
                output_path=Path("/rec/a.mp4"),
                status=PostprocessingStatus.COMPLETED,
            )
        )

        submitted = [call.args[0] for call in event_center.submit.call_args_list]
        assert [event.type for event in submitted] == [
            "VideoPostprocessingCompletedEvent",
            "PostprocessingCompletedEvent",
        ]
        assert submitted[1].data.files == ["/rec/a.mp4"]

    def test_failed_item_is_not_reported_as_produced(self) -> None:
        event_center = MagicMock()
        task, comps = _make_task(event_center=event_center)
        listener = comps["postprocessor"].set_completion_listener.call_args[0][0]

        listener(
            PostprocessingItem(
                source_path=Path("/rec/a.flv"),
                output_path=Path("/rec/a.mp4"),
                status=PostprocessingStatus.FAILED,
            )
        )

        event_center.submit.assert_not_called()

    def test_batch_event_waits_for_the_queue_to_drain(self) -> None:
        """The batch event lists a whole run, so it must not fire mid-queue."""
        event_center = MagicMock()
        task, comps = _make_task(event_center=event_center)
        listener = comps["postprocessor"].set_completion_listener.call_args[0][0]
        comps["postprocessor"].queue_size = 1

        listener(
            PostprocessingItem(
                source_path=Path("/rec/a.flv"),
                output_path=Path("/rec/a.mp4"),
                status=PostprocessingStatus.COMPLETED,
            )
        )

        types = [call.args[0].type for call in event_center.submit.call_args_list]
        assert types == ["VideoPostprocessingCompletedEvent"]

        comps["postprocessor"].queue_size = 0
        listener(
            PostprocessingItem(
                source_path=Path("/rec/b.flv"),
                output_path=Path("/rec/b.mp4"),
                status=PostprocessingStatus.COMPLETED,
            )
        )

        batch = event_center.submit.call_args_list[-1].args[0]
        assert batch.type == "PostprocessingCompletedEvent"
        assert batch.data.files == ["/rec/a.mp4", "/rec/b.mp4"]

    def test_update_postprocessing_reaches_the_worker(self) -> None:
        """Regression: settings changes must apply to an already running task."""
        task, comps = _make_task()
        config = DanmakuToAssConfig(font_size=48)

        task.update_postprocessing(danmaku_to_ass_enabled=True, danmaku_config=config)

        comps["postprocessor"].update_options.assert_called_once_with(
            remux_enabled=None,
            inject_metadata_enabled=None,
            danmaku_to_ass_enabled=True,
            danmaku_config=config,
        )

    def test_get_data_reports_the_item_in_flight(self) -> None:
        """Regression: the postprocessing status fields were never filled in."""
        task, comps = _make_task()
        item = PostprocessingItem(
            source_path=Path("/rec/a.flv"),
            output_path=Path("/rec/a.mp4"),
            status=PostprocessingStatus.REMUXING,
        )
        item.progress = PostprocessingProgress(
            status=PostprocessingStatus.REMUXING, percent=42.0
        )
        comps["postprocessor"].current_item = item

        status = task.get_data().task_status
        assert status.postprocessor_status == "remuxing"
        assert status.postprocessing_path == "/rec/a.flv"
        assert status.postprocessing_progress == 42.0

    def test_get_data_is_blank_while_idle(self) -> None:
        task, _ = _make_task()
        status = task.get_data().task_status
        assert status.postprocessor_status == ""
        assert status.postprocessing_path == ""
        assert status.postprocessing_progress == 0.0


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
        # No monitor means no live-end event, so the segment must be closed here.
        comps["recorder"].stop_recording.assert_awaited_once()

    async def test_enable_disable_recorder(self) -> None:
        task, comps = _make_task(enable_recorder=False)
        task.enable_recorder()
        assert task.recorder_enabled
        comps["monitor"].add_listener.assert_called_once_with(comps["recorder"])

        await task.disable_recorder()
        assert not task.recorder_enabled
        comps["monitor"].remove_listener.assert_called_once_with(comps["recorder"])

    async def test_disable_recorder_stops_recording_in_progress(self) -> None:
        """Regression: turning recording off must finalize the current segment.

        Dropping the monitor listener alone leaves the download loop running and
        ``running_status`` stuck at "recording".
        """
        task, comps = _make_task(enable_recorder=True)
        comps["recorder"].is_recording = True
        assert task.running_status == RunningStatus.RECORDING

        await task.disable_recorder()

        comps["recorder"].stop_recording.assert_awaited_once()

    async def test_disable_monitor_reports_stopped_afterwards(self) -> None:
        """Regression: after stopping a task the status must leave "recording"."""
        task, comps = _make_task(enable_monitor=True)
        comps["recorder"].is_recording = True

        async def _stop_recording() -> None:
            comps["recorder"].is_recording = False

        comps["recorder"].stop_recording = AsyncMock(side_effect=_stop_recording)

        await task.disable_monitor()

        assert task.running_status == RunningStatus.STOPPED


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

    def test_get_data_statistics_fields_populated(self) -> None:
        """Regression: all statistics fields must come from stream_recorder.statistics.

        Previously get_data() left dl_total, dl_rate, etc. at default 0,
        even while recording was active with real data.
        """
        task, comps = _make_task()
        # Set up realistic statistics mock values
        stats = comps["recorder"].stream_recorder.statistics
        stats.dl_total = 1024000
        stats.dl_rate = 512.5
        stats.rec_elapsed = 60.0
        stats.rec_total = 120.0
        stats.rec_rate = 8533.3
        stats.danmu_total = 42
        stats.danmu_rate = 0.7
        comps[
            "recorder"
        ].stream_recorder.current_stream_url = "https://cdn.example.com/live.flv"
        comps["recorder"].stream_recorder.current_stream_host = "cdn.example.com"

        data = task.get_data()
        status = data.task_status
        # Each statistics field must reflect the mocked values
        assert status.dl_total == 1024000
        assert status.dl_rate == 512.5
        assert status.rec_elapsed == 60.0
        assert status.rec_total == 120
        assert status.rec_rate == 8533.3
        assert status.danmu_total == 42
        assert status.danmu_rate == 0.7
        assert status.stream_url == "https://cdn.example.com/live.flv"
        assert status.stream_host == "cdn.example.com"


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

    async def test_load_tasks_skips_a_room_that_fails(self) -> None:
        """One unreachable room must not keep the others from being restored."""

        def factory(room_id: int) -> RecordTask:
            task, _ = _make_task(room_id=room_id)
            task.destroy = AsyncMock()  # type: ignore[method-assign]
            task.setup = AsyncMock(  # type: ignore[method-assign]
                side_effect=OSError("boom") if room_id == 2 else None
            )
            return task

        mgr = RecordTaskManager(factory)
        await mgr.load_tasks([1, 2, 3])
        assert sorted(t.room_id for t in mgr.get_all_tasks()) == [1, 3]


class TestRecordTaskManagerRegistry:
    """The manager reports task adds/removals so they can be persisted (§5.2)."""

    def _factory(self, *, failing: bool = False) -> Callable[[int], RecordTask]:
        def factory(room_id: int) -> RecordTask:
            task, _ = _make_task(room_id=room_id)
            task.destroy = AsyncMock()  # type: ignore[method-assign]
            task.setup = AsyncMock(  # type: ignore[method-assign]
                side_effect=OSError("boom") if failing else None
            )
            return task

        return factory

    async def test_add_task_reports_the_room_before_building_it(self) -> None:
        added: list[tuple[int, bool]] = []

        def on_added(room_id: int, auto_enable: bool) -> bool:
            added.append((room_id, auto_enable))
            return True

        factory = MagicMock(side_effect=self._factory())
        mgr = RecordTaskManager(factory, on_task_added=on_added)
        await mgr.add_task(23058, auto_enable=False)
        # Registered first, so the factory can read the room's configuration.
        assert added == [(23058, False)]
        factory.assert_called_once_with(23058)

    async def test_remove_task_reports_the_room(self) -> None:
        removed: list[int] = []
        mgr = RecordTaskManager(
            self._factory(), on_task_removed=lambda room_id: removed.append(room_id)
        )
        await mgr.add_task(1)
        await mgr.remove_task(1)
        assert removed == [1]

    async def test_stop_keeps_the_rooms_registered(self) -> None:
        """Shutting down is not the user deleting tasks."""
        removed: list[int] = []
        mgr = RecordTaskManager(
            self._factory(), on_task_removed=lambda room_id: removed.append(room_id)
        )
        await mgr.add_task(1)
        await mgr.stop()
        assert mgr.task_count == 0
        assert removed == []

    async def test_failed_setup_rolls_back_a_new_room(self) -> None:
        removed: list[int] = []
        mgr = RecordTaskManager(
            self._factory(failing=True),
            on_task_added=lambda room_id, auto: True,
            on_task_removed=lambda room_id: removed.append(room_id),
        )
        with pytest.raises(OSError, match="boom"):
            await mgr.add_task(1)
        assert mgr.task_count == 0
        assert removed == [1]

    async def test_failed_setup_keeps_an_already_configured_room(self) -> None:
        """A transient failure must not delete configuration the user wrote."""
        removed: list[int] = []
        mgr = RecordTaskManager(
            self._factory(failing=True),
            on_task_added=lambda room_id, auto: False,
            on_task_removed=lambda room_id: removed.append(room_id),
        )
        with pytest.raises(OSError, match="boom"):
            await mgr.add_task(1)
        assert removed == []


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
        postprocessor = _make_postprocessor()

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
        postprocessor = _make_postprocessor()

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
