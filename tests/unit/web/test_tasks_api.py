"""Tests for task API endpoints (§7.1)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from birec.task import (
    DanmakuFileDetail,
    FileStatus,
    RecordTask,
    RecordTaskManager,
    RunningStatus,
    TaskData,
    TaskMetadata,
    TaskParam,
    TaskStatus,
    VideoFileDetail,
)
from birec.web import create_app

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_task_data(
    room_id: int,
    *,
    live_status: bool = False,
    monitor_enabled: bool = True,
    recorder_enabled: bool = True,
    running_status: RunningStatus = RunningStatus.STOPPED,
) -> TaskData:
    return TaskData(
        room_id=room_id,
        user_name=f"user{room_id}",
        room_title=f"Room {room_id}",
        area="娱乐",
        parent_area="直播",
        live_status=live_status,
        task_status=TaskStatus(
            monitor_enabled=monitor_enabled,
            recorder_enabled=recorder_enabled,
            running_status=running_status,
        ),
    )


def _make_mock_task(
    room_id: int,
    *,
    monitor_enabled: bool = True,
    recorder_enabled: bool = True,
) -> MagicMock:
    """Create a mock RecordTask with sensible defaults."""
    task = MagicMock(spec=RecordTask)
    task.room_id = room_id
    task.monitor_enabled = monitor_enabled
    task.recorder_enabled = recorder_enabled
    task.get_data.return_value = _make_task_data(
        room_id,
        monitor_enabled=monitor_enabled,
        recorder_enabled=recorder_enabled,
    )
    task.get_param.return_value = TaskParam(
        room_id=room_id,
        enable_monitor=monitor_enabled,
        enable_recorder=recorder_enabled,
    )
    task.get_metadata.return_value = TaskMetadata(
        room_id=room_id,
        user_name=f"user{room_id}",
        room_title=f"Room {room_id}",
    )
    task.get_profile.return_value = {}
    task.get_videos.return_value = [
        VideoFileDetail(
            path=f"/rec/{room_id}.flv", size=1024, status=FileStatus.RECORDING
        )
    ]
    task.get_danmakus.return_value = [
        DanmakuFileDetail(
            path=f"/rec/{room_id}.xml", size=512, status=FileStatus.COMPLETED
        )
    ]
    task.enable_monitor = AsyncMock()
    task.disable_monitor = AsyncMock()
    task.enable_recorder = MagicMock()
    task.disable_recorder = MagicMock()
    task.refresh_info = AsyncMock()
    task.setup = AsyncMock()
    task.destroy = AsyncMock()
    return task


@pytest.fixture
def task_manager() -> RecordTaskManager:
    return RecordTaskManager()


@pytest.fixture
def app(task_manager: RecordTaskManager) -> FastAPI:
    application = create_app()
    application.state.task_manager = task_manager
    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def _populate_manager(manager: RecordTaskManager, room_ids: list[int]) -> None:
    """Directly inject mock tasks into the manager's internal dict."""
    for rid in room_ids:
        task = _make_mock_task(rid)
        manager._tasks[rid] = task


# ── GET /tasks/data ───────────────────────────────────────────────────────────


class TestGetTasksData:
    def test_empty(self, client: TestClient) -> None:
        resp = client.get("/api/v1/tasks/data")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["total"] == 0
        assert body["data"]["tasks"] == []

    def test_with_tasks(
        self, client: TestClient, task_manager: RecordTaskManager
    ) -> None:
        _populate_manager(task_manager, [1001, 1002, 1003])
        resp = client.get("/api/v1/tasks/data")
        body = resp.json()
        assert body["data"]["total"] == 3
        assert len(body["data"]["tasks"]) == 3

    def test_pagination(
        self, client: TestClient, task_manager: RecordTaskManager
    ) -> None:
        _populate_manager(task_manager, list(range(1, 26)))
        resp = client.get("/api/v1/tasks/data?page=2&size=10")
        body = resp.json()
        assert body["data"]["total"] == 25
        assert body["data"]["page"] == 2
        assert body["data"]["size"] == 10
        assert len(body["data"]["tasks"]) == 10

    def test_filter_living(
        self, client: TestClient, task_manager: RecordTaskManager
    ) -> None:
        task1 = _make_mock_task(1001)
        task1.get_data.return_value = _make_task_data(1001, live_status=True)
        task2 = _make_mock_task(1002)
        task2.get_data.return_value = _make_task_data(1002, live_status=False)
        task_manager._tasks[1001] = task1
        task_manager._tasks[1002] = task2

        resp = client.get("/api/v1/tasks/data?select=living")
        body = resp.json()
        assert body["data"]["total"] == 1
        assert body["data"]["tasks"][0]["room_id"] == 1001

    def test_filter_recording(
        self, client: TestClient, task_manager: RecordTaskManager
    ) -> None:
        task1 = _make_mock_task(1001)
        task1.get_data.return_value = _make_task_data(
            1001, running_status=RunningStatus.RECORDING
        )
        task2 = _make_mock_task(1002)
        task2.get_data.return_value = _make_task_data(
            1002, running_status=RunningStatus.STOPPED
        )
        task_manager._tasks[1001] = task1
        task_manager._tasks[1002] = task2

        resp = client.get("/api/v1/tasks/data?select=recording")
        body = resp.json()
        assert body["data"]["total"] == 1
        assert body["data"]["tasks"][0]["room_id"] == 1001


# ── GET /tasks/{room_id}/data ─────────────────────────────────────────────────


class TestGetTaskData:
    def test_found(self, client: TestClient, task_manager: RecordTaskManager) -> None:
        _populate_manager(task_manager, [1001])
        resp = client.get("/api/v1/tasks/1001/data")
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["room_id"] == 1001

    def test_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/v1/tasks/9999/data")
        body = resp.json()
        assert body["code"] == 404


# ── GET /tasks/{room_id}/param ────────────────────────────────────────────────


class TestGetTaskParam:
    def test_found(self, client: TestClient, task_manager: RecordTaskManager) -> None:
        _populate_manager(task_manager, [1001])
        resp = client.get("/api/v1/tasks/1001/param")
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["room_id"] == 1001
        assert body["data"]["enable_monitor"] is True

    def test_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/v1/tasks/9999/param")
        body = resp.json()
        assert body["code"] == 404


# ── GET /tasks/{room_id}/metadata ─────────────────────────────────────────────


class TestGetTaskMetadata:
    def test_found(self, client: TestClient, task_manager: RecordTaskManager) -> None:
        _populate_manager(task_manager, [1001])
        resp = client.get("/api/v1/tasks/1001/metadata")
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["room_id"] == 1001
        assert body["data"]["user_name"] == "user1001"

    def test_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/v1/tasks/9999/metadata")
        body = resp.json()
        assert body["code"] == 404


# ── GET /tasks/{room_id}/profile ──────────────────────────────────────────────


class TestGetTaskProfile:
    def test_found(self, client: TestClient, task_manager: RecordTaskManager) -> None:
        _populate_manager(task_manager, [1001])
        resp = client.get("/api/v1/tasks/1001/profile")
        body = resp.json()
        assert body["code"] == 0

    def test_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/v1/tasks/9999/profile")
        body = resp.json()
        assert body["code"] == 404


# ── GET /tasks/{room_id}/videos ───────────────────────────────────────────────


class TestGetTaskVideos:
    def test_found(self, client: TestClient, task_manager: RecordTaskManager) -> None:
        _populate_manager(task_manager, [1001])
        resp = client.get("/api/v1/tasks/1001/videos")
        body = resp.json()
        assert body["code"] == 0
        assert len(body["data"]["videos"]) == 1
        assert body["data"]["videos"][0]["path"] == "/rec/1001.flv"

    def test_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/v1/tasks/9999/videos")
        body = resp.json()
        assert body["code"] == 404


# ── GET /tasks/{room_id}/danmakus ─────────────────────────────────────────────


class TestGetTaskDanmakus:
    def test_found(self, client: TestClient, task_manager: RecordTaskManager) -> None:
        _populate_manager(task_manager, [1001])
        resp = client.get("/api/v1/tasks/1001/danmakus")
        body = resp.json()
        assert body["code"] == 0
        assert len(body["data"]["danmakus"]) == 1
        assert body["data"]["danmakus"][0]["path"] == "/rec/1001.xml"

    def test_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/v1/tasks/9999/danmakus")
        body = resp.json()
        assert body["code"] == 404


# ── POST /tasks/{room_id} (add) ───────────────────────────────────────────────


class TestAddTask:
    def test_add_success(
        self, client: TestClient, task_manager: RecordTaskManager
    ) -> None:
        mock_task = _make_mock_task(2001)
        task_manager._task_factory = MagicMock(return_value=mock_task)

        resp = client.post("/api/v1/tasks/2001", json={"room_id": 2001})
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["room_id"] == 2001
        assert 2001 in task_manager._tasks

    def test_add_duplicate(
        self, client: TestClient, task_manager: RecordTaskManager
    ) -> None:
        _populate_manager(task_manager, [2001])
        resp = client.post("/api/v1/tasks/2001", json={"room_id": 2001})
        body = resp.json()
        assert body["code"] == 409

    def test_add_no_factory(self, client: TestClient) -> None:
        resp = client.post("/api/v1/tasks/3001", json={"room_id": 3001})
        body = resp.json()
        assert body["code"] == 500


# ── POST /tasks/{room_id}/start ───────────────────────────────────────────────


class TestStartTask:
    def test_start(self, client: TestClient, task_manager: RecordTaskManager) -> None:
        _populate_manager(task_manager, [1001])
        resp = client.post("/api/v1/tasks/1001/start")
        body = resp.json()
        assert body["code"] == 0
        task_manager._tasks[1001].enable_monitor.assert_awaited_once()

    def test_start_not_found(self, client: TestClient) -> None:
        resp = client.post("/api/v1/tasks/9999/start")
        body = resp.json()
        assert body["code"] == 404


# ── POST /tasks/{room_id}/stop ────────────────────────────────────────────────


class TestStopTask:
    def test_stop(self, client: TestClient, task_manager: RecordTaskManager) -> None:
        _populate_manager(task_manager, [1001])
        resp = client.post("/api/v1/tasks/1001/stop")
        body = resp.json()
        assert body["code"] == 0
        task_manager._tasks[1001].disable_monitor.assert_awaited_once()

    def test_stop_not_found(self, client: TestClient) -> None:
        resp = client.post("/api/v1/tasks/9999/stop")
        body = resp.json()
        assert body["code"] == 404


# ── POST /tasks/{room_id}/recorder/enable ─────────────────────────────────────


class TestEnableRecorder:
    def test_enable(self, client: TestClient, task_manager: RecordTaskManager) -> None:
        _populate_manager(task_manager, [1001])
        resp = client.post("/api/v1/tasks/1001/recorder/enable")
        body = resp.json()
        assert body["code"] == 0
        task_manager._tasks[1001].enable_recorder.assert_called_once()

    def test_enable_not_found(self, client: TestClient) -> None:
        resp = client.post("/api/v1/tasks/9999/recorder/enable")
        body = resp.json()
        assert body["code"] == 404


# ── POST /tasks/{room_id}/recorder/disable ────────────────────────────────────


class TestDisableRecorder:
    def test_disable(self, client: TestClient, task_manager: RecordTaskManager) -> None:
        _populate_manager(task_manager, [1001])
        resp = client.post("/api/v1/tasks/1001/recorder/disable")
        body = resp.json()
        assert body["code"] == 0
        task_manager._tasks[1001].disable_recorder.assert_called_once()

    def test_disable_not_found(self, client: TestClient) -> None:
        resp = client.post("/api/v1/tasks/9999/recorder/disable")
        body = resp.json()
        assert body["code"] == 404


# ── POST /tasks/{room_id}/info ────────────────────────────────────────────────


class TestRefreshInfo:
    def test_refresh(self, client: TestClient, task_manager: RecordTaskManager) -> None:
        _populate_manager(task_manager, [1001])
        resp = client.post("/api/v1/tasks/1001/info")
        body = resp.json()
        assert body["code"] == 0
        task_manager._tasks[1001].refresh_info.assert_awaited_once()

    def test_refresh_not_found(self, client: TestClient) -> None:
        resp = client.post("/api/v1/tasks/9999/info")
        body = resp.json()
        assert body["code"] == 404


# ── POST /tasks/info (batch) ─────────────────────────────────────────────────


class TestBatchRefreshInfo:
    def test_batch_refresh(
        self, client: TestClient, task_manager: RecordTaskManager
    ) -> None:
        _populate_manager(task_manager, [1001, 1002])
        resp = client.post("/api/v1/tasks/info")
        body = resp.json()
        assert body["code"] == 0
        task_manager._tasks[1001].refresh_info.assert_awaited_once()
        task_manager._tasks[1002].refresh_info.assert_awaited_once()


# ── POST /tasks/start (batch) ────────────────────────────────────────────────


class TestBatchStart:
    def test_batch_start_all(
        self, client: TestClient, task_manager: RecordTaskManager
    ) -> None:
        _populate_manager(task_manager, [1001, 1002])
        resp = client.post("/api/v1/tasks/start", json={})
        body = resp.json()
        assert body["code"] == 0
        task_manager._tasks[1001].enable_monitor.assert_awaited_once()
        task_manager._tasks[1002].enable_monitor.assert_awaited_once()

    def test_batch_start_specific(
        self, client: TestClient, task_manager: RecordTaskManager
    ) -> None:
        _populate_manager(task_manager, [1001, 1002])
        resp = client.post("/api/v1/tasks/start", json={"room_ids": [1001]})
        body = resp.json()
        assert body["code"] == 0
        task_manager._tasks[1001].enable_monitor.assert_awaited_once()
        task_manager._tasks[1002].enable_monitor.assert_not_awaited()


# ── POST /tasks/stop (batch) ─────────────────────────────────────────────────


class TestBatchStop:
    def test_batch_stop_all(
        self, client: TestClient, task_manager: RecordTaskManager
    ) -> None:
        _populate_manager(task_manager, [1001, 1002])
        resp = client.post("/api/v1/tasks/stop", json={})
        body = resp.json()
        assert body["code"] == 0
        task_manager._tasks[1001].disable_monitor.assert_awaited_once()
        task_manager._tasks[1002].disable_monitor.assert_awaited_once()


# ── POST /tasks/recorder/enable (batch) ──────────────────────────────────────


class TestBatchEnableRecorder:
    def test_batch_enable(
        self, client: TestClient, task_manager: RecordTaskManager
    ) -> None:
        _populate_manager(task_manager, [1001, 1002])
        resp = client.post("/api/v1/tasks/recorder/enable", json={})
        body = resp.json()
        assert body["code"] == 0
        task_manager._tasks[1001].enable_recorder.assert_called_once()
        task_manager._tasks[1002].enable_recorder.assert_called_once()


# ── POST /tasks/recorder/disable (batch) ─────────────────────────────────────


class TestBatchDisableRecorder:
    def test_batch_disable(
        self, client: TestClient, task_manager: RecordTaskManager
    ) -> None:
        _populate_manager(task_manager, [1001, 1002])
        resp = client.post("/api/v1/tasks/recorder/disable", json={})
        body = resp.json()
        assert body["code"] == 0
        task_manager._tasks[1001].disable_recorder.assert_called_once()
        task_manager._tasks[1002].disable_recorder.assert_called_once()


# ── DELETE /tasks/{room_id} ───────────────────────────────────────────────────


class TestDeleteTask:
    def test_delete(self, client: TestClient, task_manager: RecordTaskManager) -> None:
        _populate_manager(task_manager, [1001])
        resp = client.request("DELETE", "/api/v1/tasks/1001")
        body = resp.json()
        assert body["code"] == 0
        assert 1001 not in task_manager._tasks

    def test_delete_not_found(self, client: TestClient) -> None:
        resp = client.request("DELETE", "/api/v1/tasks/9999")
        body = resp.json()
        assert body["code"] == 404


# ── DELETE /tasks (batch) ─────────────────────────────────────────────────────


class TestDeleteTasks:
    def test_batch_delete(
        self, client: TestClient, task_manager: RecordTaskManager
    ) -> None:
        _populate_manager(task_manager, [1001, 1002])
        resp = client.request(
            "DELETE", "/api/v1/tasks", json={"room_ids": [1001, 1002]}
        )
        body = resp.json()
        assert body["code"] == 0
        assert 1001 not in task_manager._tasks
        assert 1002 not in task_manager._tasks

    def test_batch_delete_partial_not_found(
        self, client: TestClient, task_manager: RecordTaskManager
    ) -> None:
        _populate_manager(task_manager, [1001])
        resp = client.request(
            "DELETE", "/api/v1/tasks", json={"room_ids": [1001, 9999]}
        )
        body = resp.json()
        assert body["code"] == 404
        assert 1001 not in task_manager._tasks
