"""Tests for web module."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from birec.task import RecordTaskManager
from birec.web import ResponseMessage, create_app


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    app.state.task_manager = RecordTaskManager()
    return TestClient(app)


class TestResponseMessage:
    def test_defaults(self) -> None:
        msg = ResponseMessage()
        assert msg.code == 0
        assert msg.message == ""
        assert msg.data is None

    def test_to_dict_no_data(self) -> None:
        msg = ResponseMessage(code=0, message="ok")
        d = msg.to_dict()
        assert d == {"code": 0, "message": "ok"}
        assert "data" not in d

    def test_to_dict_with_data(self) -> None:
        msg = ResponseMessage(data={"key": "value"})
        d = msg.to_dict()
        assert d["data"] == {"key": "value"}


class TestAppInfo:
    def test_get_app_info(self, client: TestClient) -> None:
        resp = client.get("/api/v1/app/info")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["name"] == "bili-rec"


class TestTasksRoute:
    def test_get_tasks_data(self, client: TestClient) -> None:
        resp = client.get("/api/v1/tasks/data")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["total"] == 0
        assert body["data"]["tasks"] == []


class TestSettingsRoute:
    def test_get_settings(self, client: TestClient) -> None:
        resp = client.get("/api/v1/settings")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0


class TestNotFound:
    def test_404_response(self, client: TestClient) -> None:
        resp = client.get("/api/v1/nonexistent")
        assert resp.status_code == 404
        body = resp.json()
        assert body["code"] == 404
