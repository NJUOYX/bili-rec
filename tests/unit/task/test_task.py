"""Tests for task module."""

from __future__ import annotations

import pytest

from birec.task import (
    DanmakuFileDetail,
    RecordTask,
    RecordTaskManager,
    RunningStatus,
    TaskData,
    TaskStatus,
    VideoFileDetail,
)


class TestRunningStatus:
    def test_values(self) -> None:
        assert RunningStatus.STOPPED.value == "stopped"
        assert RunningStatus.RECORDING.value == "recording"


class TestTaskStatus:
    def test_defaults(self) -> None:
        status = TaskStatus()
        assert not status.monitor_enabled
        assert status.running_status == RunningStatus.STOPPED


class TestRecordTask:
    def test_init(self) -> None:
        task = RecordTask(12345)
        assert task.room_id == 12345
        assert not task.monitor_enabled
        assert not task.recorder_enabled
        assert task.running_status == RunningStatus.STOPPED

    def test_enable_disable_monitor(self) -> None:
        task = RecordTask(1)
        task.enable_monitor()
        assert task.monitor_enabled
        task.disable_monitor()
        assert not task.monitor_enabled

    def test_enable_disable_recorder(self) -> None:
        task = RecordTask(1)
        task.enable_recorder()
        assert task.recorder_enabled
        task.disable_recorder()
        assert not task.recorder_enabled

    def test_update_data(self) -> None:
        task = RecordTask(1)
        data = TaskData(room_id=1, user_name="test_user")
        task.update_data(data)
        assert task.data.user_name == "test_user"

    def test_video_files(self) -> None:
        task = RecordTask(1)
        task.add_video_file(VideoFileDetail(path="/tmp/a.mp4", size=100))
        assert len(task.video_files) == 1
        assert task.video_files[0].path == "/tmp/a.mp4"

    def test_danmaku_files(self) -> None:
        task = RecordTask(1)
        task.add_danmaku_file(DanmakuFileDetail(path="/tmp/a.xml"))
        assert len(task.danmaku_files) == 1


class TestRecordTaskManager:
    def test_add_task(self) -> None:
        mgr = RecordTaskManager()
        task = mgr.add_task(12345)
        assert task.room_id == 12345
        assert mgr.task_count == 1

    def test_add_duplicate_raises(self) -> None:
        mgr = RecordTaskManager()
        mgr.add_task(1)
        with pytest.raises(ValueError, match="already exists"):
            mgr.add_task(1)

    def test_remove_task(self) -> None:
        mgr = RecordTaskManager()
        mgr.add_task(1)
        mgr.remove_task(1)
        assert mgr.task_count == 0

    def test_remove_nonexistent_raises(self) -> None:
        mgr = RecordTaskManager()
        with pytest.raises(KeyError):
            mgr.remove_task(999)

    def test_get_task(self) -> None:
        mgr = RecordTaskManager()
        mgr.add_task(1)
        assert mgr.get_task(1) is not None
        assert mgr.get_task(2) is None

    def test_get_all_tasks(self) -> None:
        mgr = RecordTaskManager()
        mgr.add_task(1)
        mgr.add_task(2)
        assert len(mgr.get_all_tasks()) == 2

    def test_enable_all_monitors(self) -> None:
        mgr = RecordTaskManager()
        t1 = mgr.add_task(1)
        t2 = mgr.add_task(2)
        mgr.enable_all_monitors()
        assert t1.monitor_enabled
        assert t2.monitor_enabled

    def test_disable_all_recorders(self) -> None:
        mgr = RecordTaskManager()
        t1 = mgr.add_task(1)
        t1.enable_recorder()
        mgr.disable_all_recorders()
        assert not t1.recorder_enabled
