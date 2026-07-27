"""Tests for settings/app/login/validation/update API endpoints (§7.2/§7.3)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from birec.application import Application
from birec.web import create_app


@pytest.fixture()
def app(tmp_path: Path) -> Any:
    """Create a test application with lifespan-managed state."""
    config = tmp_path / "config.toml"
    out = tmp_path / "recordings"
    logs = tmp_path / "logs"
    application = Application(config, out, logs)

    @asynccontextmanager
    async def lifespan(a: Any) -> AsyncIterator[None]:
        await application.startup()
        yield
        await application.shutdown()

    test_app = create_app()
    test_app.router.lifespan_context = lifespan
    test_app.state.application = application
    test_app.state.settings_manager = application.settings_manager
    test_app.state.event_center = application.event_center
    test_app.state.exception_center = application.exception_center
    test_app.state.task_manager = application.task_manager
    return test_app


@pytest.fixture()
async def client(app: Any) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ── Settings endpoints ───────────────────────────────────────────────────────


class TestGetSettings:
    async def test_get_settings_returns_data(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/settings")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert "data" in body

    async def test_get_settings_with_include(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/settings", params={"include": "header"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0

    async def test_get_settings_with_exclude(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/settings", params={"exclude": "tasks"})
        assert resp.status_code == 200


class TestPatchSettings:
    async def test_patch_settings_updates_header(self, client: AsyncClient) -> None:
        resp = await client.patch(
            "/api/v1/settings",
            json={"header": {"cookie": "SESSDATA=abc123"}},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["message"] == "Settings updated"

    async def test_patch_settings_invalid_payload(self, client: AsyncClient) -> None:
        resp = await client.patch(
            "/api/v1/settings",
            json={"recorder": {"read_timeout": 999}},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 422

    async def test_patch_settings_recorder(self, client: AsyncClient) -> None:
        resp = await client.patch(
            "/api/v1/settings",
            json={"recorder": {"quality_number": 400}},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0


class TestTaskSettings:
    async def test_get_task_settings_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/settings/tasks/99999")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 404

    async def test_patch_task_settings_not_found(self, client: AsyncClient) -> None:
        resp = await client.patch(
            "/api/v1/settings/tasks/99999",
            json={"recorder": {"quality_number": 400}},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 404


# ── App endpoints ────────────────────────────────────────────────────────────


class TestAppEndpoints:
    async def test_get_app_status(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/app/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert "started" in body["data"]
        assert "task_count" in body["data"]

    async def test_get_app_info(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/app/info")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["name"] == "bili-rec"
        assert "pid" in body["data"]

    async def test_restart_app(self, client: AsyncClient) -> None:
        with patch("os.kill") as mock_kill:
            resp = await client.post("/api/v1/app/restart")
            assert resp.status_code == 200
            body = resp.json()
            assert body["message"] == "Restarting..."
            mock_kill.assert_called_once()

    async def test_exit_app(self, client: AsyncClient) -> None:
        with patch("os.kill") as mock_kill:
            resp = await client.post("/api/v1/app/exit")
            assert resp.status_code == 200
            body = resp.json()
            assert body["message"] == "Exiting..."
            mock_kill.assert_called_once()


# ── QR code login ────────────────────────────────────────────────────────────


class TestQrcodeLogin:
    async def test_qrcode_login_no_api(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/qrcode/login")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 503

    async def test_qrcode_login_success(self, client: AsyncClient, app: Any) -> None:
        mock_api = MagicMock()
        mock_api.request_tv_qrcode = AsyncMock(
            return_value={"url": "https://qr.example.com", "auth_code": "abc"}
        )
        app.state.bili_api = mock_api

        resp = await client.get("/api/v1/qrcode/login")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["auth_code"] == "abc"

    async def test_qrcode_poll_no_api(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/qrcode/login/poll",
            json={"auth_code": "abc"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 503

    async def test_qrcode_poll_missing_auth_code(
        self, client: AsyncClient, app: Any
    ) -> None:
        mock_api = MagicMock()
        app.state.bili_api = mock_api

        resp = await client.post("/api/v1/qrcode/login/poll", json={})
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 400

    async def test_qrcode_poll_success(self, client: AsyncClient, app: Any) -> None:
        mock_api = MagicMock()
        mock_api.poll_tv_qrcode = AsyncMock(
            return_value={
                "code": 0,
                "message": "ok",
                "data": {
                    "token_info": {"access_token": "tok123"},
                    "cookie_info": {
                        "cookies": [
                            {"name": "SESSDATA", "value": "sess1"},
                            {"name": "bili_jct", "value": "jct1"},
                        ]
                    },
                },
            }
        )
        app.state.bili_api = mock_api

        resp = await client.post(
            "/api/v1/qrcode/login/poll",
            json={"auth_code": "abc"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert "SESSDATA=sess1" in body["data"]["cookie"]

    async def test_qrcode_poll_pending(self, client: AsyncClient, app: Any) -> None:
        mock_api = MagicMock()
        mock_api.poll_tv_qrcode = AsyncMock(
            return_value={"code": 86039, "message": "未确认"}
        )
        app.state.bili_api = mock_api

        resp = await client.post(
            "/api/v1/qrcode/login/poll",
            json={"auth_code": "abc"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 86039


# ── Validation ───────────────────────────────────────────────────────────────


class TestValidationDir:
    async def test_validate_valid_dir(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        resp = await client.post(
            "/api/v1/validation/dir",
            json={"path": str(tmp_path)},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["message"] == "Directory is valid"

    async def test_validate_nonexistent_dir(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/validation/dir",
            json={"path": "/nonexistent/path/xyz"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 400
        assert "does not exist" in body["message"]

    async def test_validate_not_a_dir(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        file = tmp_path / "afile.txt"
        file.write_text("hi")
        resp = await client.post(
            "/api/v1/validation/dir",
            json={"path": str(file)},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 400
        assert "Not a directory" in body["message"]

    async def test_validate_missing_path(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/validation/dir", json={})
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 400


# ── Update ───────────────────────────────────────────────────────────────────


class TestUpdateVersion:
    async def test_get_latest_version_success(self, client: AsyncClient) -> None:
        with patch("birec.update.PypiApi") as MockPypi:
            instance = MockPypi.return_value
            instance.get_latest_version_string = AsyncMock(return_value="1.2.3")
            resp = await client.get("/api/v1/update/version/latest")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["version"] == "1.2.3"

    async def test_get_latest_version_not_found(self, client: AsyncClient) -> None:
        with patch("birec.update.PypiApi") as MockPypi:
            instance = MockPypi.return_value
            instance.get_latest_version_string = AsyncMock(return_value=None)
            resp = await client.get("/api/v1/update/version/latest")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 404

    async def test_get_latest_version_error(self, client: AsyncClient) -> None:
        with patch(
            "birec.update.PypiApi",
            side_effect=Exception("network error"),
        ):
            resp = await client.get("/api/v1/update/version/latest")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 502
