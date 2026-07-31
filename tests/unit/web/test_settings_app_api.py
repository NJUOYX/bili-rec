"""Tests for settings/app/login/validation/update API endpoints (§7.2/§7.3)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from birec import __version__
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

    async def test_patch_out_dir_propagates_to_existing_tasks(
        self, client: AsyncClient, app: Any
    ) -> None:
        """Regression: changing outDir must hot-update all existing tasks.

        Without propagation, tasks created before the change keep writing
        to the old directory.
        """
        # Add a task so there's something to propagate to
        task_manager = app.state.task_manager
        mock_task = MagicMock()
        mock_task.update_out_dir = MagicMock()
        task_manager._tasks[12345] = mock_task

        resp = await client.patch(
            "/api/v1/settings",
            json={"output": {"out_dir": "/new/recordings"}},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0

        # The task's update_out_dir must have been called with the new path
        mock_task.update_out_dir.assert_called_once_with("/new/recordings")

    async def test_patch_out_dir_propagates_to_multiple_tasks(
        self, client: AsyncClient, app: Any
    ) -> None:
        """All existing tasks must receive the new out_dir, not just the first."""
        task_manager = app.state.task_manager
        mock_tasks = [MagicMock() for _ in range(3)]
        for i, t in enumerate(mock_tasks):
            t.update_out_dir = MagicMock()
            task_manager._tasks[i + 1] = t

        await client.patch(
            "/api/v1/settings",
            json={"output": {"out_dir": "/another/path"}},
        )

        for t in mock_tasks:
            t.update_out_dir.assert_called_once_with("/another/path")

    async def test_patch_postprocessing_propagates_to_existing_tasks(
        self, client: AsyncClient, app: Any
    ) -> None:
        """Regression: enabling danmaku→ASS must reach already running tasks.

        The switches were resolved when the task was built, so without this the
        option only took effect for rooms added after the change.
        """
        task_manager = app.state.task_manager
        mock_task = MagicMock()
        mock_task.room_id = 12345
        task_manager._tasks[12345] = mock_task

        resp = await client.patch(
            "/api/v1/settings",
            json={"postprocessing": {"danmaku_to_ass": True}},
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

        kwargs = mock_task.update_postprocessing.call_args.kwargs
        assert kwargs["danmaku_to_ass_enabled"] is True

    async def test_patch_unrelated_section_leaves_tasks_alone(
        self, client: AsyncClient, app: Any
    ) -> None:
        """Only a post-processing change should touch the running workers."""
        task_manager = app.state.task_manager
        mock_task = MagicMock()
        mock_task.room_id = 12345
        task_manager._tasks[12345] = mock_task

        await client.patch(
            "/api/v1/settings",
            json={"recorder": {"quality_number": 400}},
        )

        mock_task.update_postprocessing.assert_not_called()


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

    async def test_patch_task_settings_applies_the_override(
        self, client: AsyncClient, app: Any
    ) -> None:
        app.state.settings_manager.add_task_settings(12345)

        resp = await client.patch(
            "/api/v1/settings/tasks/12345",
            json={"postprocessing": {"danmaku_to_ass": True}},
        )

        assert resp.json()["code"] == 0
        task_settings = app.state.settings_manager.find_task_settings(12345)
        assert task_settings.postprocessing.danmaku_to_ass is True

    async def test_patch_task_postprocessing_propagates_to_the_task(
        self, client: AsyncClient, app: Any
    ) -> None:
        """Regression: a task-level override must reach the running worker too."""
        app.state.settings_manager.add_task_settings(12345)
        mock_task = MagicMock()
        mock_task.room_id = 12345
        app.state.task_manager._tasks[12345] = mock_task

        await client.patch(
            "/api/v1/settings/tasks/12345",
            json={"postprocessing": {"danmaku_to_ass": True}},
        )

        kwargs = mock_task.update_postprocessing.call_args.kwargs
        assert kwargs["danmaku_to_ass_enabled"] is True

    async def test_patch_task_toggles_are_applied(
        self, client: AsyncClient, app: Any
    ) -> None:
        app.state.settings_manager.add_task_settings(12345)

        await client.patch(
            "/api/v1/settings/tasks/12345",
            json={"enable_monitor": False, "enable_recorder": False},
        )

        task_settings = app.state.settings_manager.find_task_settings(12345)
        assert task_settings.enable_monitor is False
        assert task_settings.enable_recorder is False

    async def test_patch_task_settings_rejects_a_bad_body(
        self, client: AsyncClient, app: Any
    ) -> None:
        app.state.settings_manager.add_task_settings(12345)

        resp = await client.patch(
            "/api/v1/settings/tasks/12345",
            json={"recorder": {"quality_number": "not-a-number"}},
        )

        assert resp.json()["code"] == 422


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

    async def test_the_reported_version_is_the_packaged_one(
        self, client: AsyncClient
    ) -> None:
        """Regression: the version was written out by hand in three places.

        ``birec --version`` read ``__version__`` while the API and the OpenAPI
        document each carried their own literal, so they disagreed the moment
        either was bumped — and the update check compared PyPI against a
        hardcoded string that would go stale on the first release.
        """
        body = (await client.get("/api/v1/app/info")).json()

        assert body["data"]["version"] == __version__

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

    async def test_qrcode_login_upstream_failure(
        self, client: AsyncClient, app: Any
    ) -> None:
        """Bilibili's passport host being unreachable is upstream's fault, not a 500."""
        mock_api = MagicMock()
        mock_api.request_tv_qrcode = AsyncMock(side_effect=OSError("no route"))
        app.state.bili_api = mock_api

        resp = await client.get("/api/v1/qrcode/login")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 502
        assert "no route" in body["message"]

    async def test_qrcode_login_local_bug_is_not_masked_as_upstream(
        self, client: AsyncClient, app: Any
    ) -> None:
        """A bug on our side must not be reported as 「Bilibili unreachable」."""
        mock_api = MagicMock()
        mock_api.request_tv_qrcode = AsyncMock(side_effect=ValueError("our bug"))
        app.state.bili_api = mock_api

        with pytest.raises(ValueError, match="our bug"):
            await client.get("/api/v1/qrcode/login")

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

    async def test_qrcode_poll_upstream_failure(
        self, client: AsyncClient, app: Any
    ) -> None:
        mock_api = MagicMock()
        mock_api.poll_tv_qrcode = AsyncMock(side_effect=OSError("no route"))
        app.state.bili_api = mock_api

        resp = await client.post(
            "/api/v1/qrcode/login/poll",
            json={"auth_code": "abc"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 502
        assert "no route" in body["message"]


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
        # What the update check compares against has to be what is installed.
        assert body["data"]["current"] == __version__

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
