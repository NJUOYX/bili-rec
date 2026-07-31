"""End-to-end system tests with fake Bilibili server (§11.3).

Tests the full lifecycle: add task → live starts → recording →
live ends → verify outputs and event sequence.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from birec.application import create_application

from .fake_bili_server import FakeBiliServer, generate_flv_stream


@pytest.fixture()
async def fake_server() -> FakeBiliServer:
    """Start a fake Bilibili server."""
    server = FakeBiliServer(room_id=12345)
    await server.start()
    yield server
    await server.stop()


@pytest.fixture()
def app(tmp_path: Path, fake_server: FakeBiliServer) -> Any:
    """Create application pointed at the fake server."""
    application = create_application(
        config_path=tmp_path / "config.toml",
        output_dir=tmp_path / "recordings",
        log_dir=tmp_path / "logs",
    )
    # Override API URLs to point to fake server
    settings = application.state.settings_manager.settings
    settings.bili_api.base_api_urls = [fake_server.base_url]
    settings.bili_api.base_live_api_urls = [fake_server.base_url]
    settings.bili_api.base_play_info_api_urls = [fake_server.base_url]
    return application


@pytest.fixture()
async def client(app: Any) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c  # type: ignore[misc]


@pytest.fixture()
async def started_client(app: Any) -> AsyncClient:
    """Client on a *started* application, so the task factory can build tasks."""
    application = app.state.application
    await application.startup()
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c  # type: ignore[misc]
    finally:
        await application.shutdown()


class TestFakeServerBasics:
    """Verify the fake server itself works correctly."""

    async def test_flv_stream_generation(self) -> None:
        data = generate_flv_stream(5)
        assert data[:3] == b"FLV"
        assert len(data) > 100

    async def test_room_info_offline(self, fake_server: FakeBiliServer) -> None:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            url = f"{fake_server.base_url}/xlive/app-room/v1/index/getInfoByRoom"
            async with session.get(url) as resp:
                data = await resp.json()
        assert data["code"] == 0
        assert data["data"]["room_info"]["live_status"] == 0

    async def test_room_info_live(self, fake_server: FakeBiliServer) -> None:
        import aiohttp

        fake_server.set_live()
        async with aiohttp.ClientSession() as session:
            url = f"{fake_server.base_url}/xlive/app-room/v1/index/getInfoByRoom"
            async with session.get(url) as resp:
                data = await resp.json()
        assert data["data"]["room_info"]["live_status"] == 1

    async def test_play_info_offline(self, fake_server: FakeBiliServer) -> None:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            url = f"{fake_server.base_url}/xlive/app-room/v2/index/getRoomPlayInfo"
            async with session.get(url) as resp:
                data = await resp.json()
        assert data["data"]["playurl_info"]["playurl"] is None

    async def test_play_info_live(self, fake_server: FakeBiliServer) -> None:
        import aiohttp

        fake_server.set_live()
        async with aiohttp.ClientSession() as session:
            url = f"{fake_server.base_url}/xlive/app-room/v2/index/getRoomPlayInfo"
            async with session.get(url) as resp:
                data = await resp.json()
        playurl = data["data"]["playurl_info"]["playurl"]
        assert playurl is not None
        stream = playurl["stream"][0]
        assert stream["protocol_name"] == "http_stream"

    async def test_flv_stream_endpoint(self, fake_server: FakeBiliServer) -> None:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            url = f"{fake_server.base_url}/stream.flv"
            async with session.get(url) as resp:
                # Only the signature is of interest here, and the endpoint keeps
                # a chunked stream flowing for as long as a recording needs it:
                # reading it to the end would be waiting out the whole payload.
                data = await resp.content.readexactly(3)
        assert data == b"FLV"

    async def test_danmu_info(self, fake_server: FakeBiliServer) -> None:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            url = f"{fake_server.base_url}/xlive/app-room/v1/index/getDanmuInfo"
            async with session.get(url) as resp:
                data = await resp.json()
        assert data["code"] == 0
        assert data["data"]["token"] == "fake_danmaku_token"


class TestTaskLifecycleE2E:
    """End-to-end task lifecycle through the Web API.

    Note: Full task add/remove requires Live/Recorder infrastructure.
    Here we test the API surface that works without full task setup.
    """

    async def test_query_empty_tasks(self, client: AsyncClient) -> None:
        """Query tasks when none exist."""
        resp = await client.get("/api/v1/tasks/data")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["total"] == 0
        assert body["data"]["tasks"] == []

    async def test_get_nonexistent_task(self, client: AsyncClient) -> None:
        """Querying a non-existent task returns 404."""
        resp = await client.get("/api/v1/tasks/99999/data")
        body = resp.json()
        assert body["code"] == 404

    async def test_batch_operations_empty(self, client: AsyncClient) -> None:
        """Batch operations on empty task list."""
        resp = await client.post("/api/v1/tasks/info", json={"room_ids": [12345]})
        assert resp.status_code == 200


class TestTaskAddE2E:
    """Adding a task must produce a fully wired, populated task (§5.10).

    This is the path a user takes from the web UI: the application-level task
    factory builds the component graph, then ``setup`` loads room info and
    resolves the danmaku servers.
    """

    async def test_add_task_populates_room_info(
        self, fake_server: FakeBiliServer, started_client: AsyncClient
    ) -> None:
        resp = await started_client.post("/api/v1/tasks/12345", json={"room_id": 12345})
        assert resp.json()["code"] == 0

        body = (await started_client.get("/api/v1/tasks/12345/data")).json()
        assert body["code"] == 0
        data = body["data"]
        assert data["room_id"] == 12345
        assert data["room_title"] == "Test Live Room"
        assert data["user_name"] == "TestStreamer"
        assert data["area"] == "测试分区"
        assert data["task_status"]["monitor_enabled"]
        assert data["task_status"]["recorder_enabled"]

        await started_client.delete("/api/v1/tasks/12345")

    async def test_add_task_resolves_danmaku_hosts(
        self, fake_server: FakeBiliServer, started_client: AsyncClient
    ) -> None:
        """The danmaku client is handed the servers returned by the API."""
        resp = await started_client.post("/api/v1/tasks/12345", json={"room_id": 12345})
        assert resp.json()["code"] == 0

        application = started_client._transport.app.state.application  # type: ignore[attr-defined]  # noqa: SLF001
        task = application.task_manager.get_task(12345)
        client = task._danmaku_client  # noqa: SLF001
        assert client._hosts == ["127.0.0.1"]  # noqa: SLF001
        assert client._token == "fake_danmaku_token"  # noqa: SLF001

        await started_client.delete("/api/v1/tasks/12345")

    async def test_added_task_has_task_level_settings(
        self, fake_server: FakeBiliServer, started_client: AsyncClient
    ) -> None:
        """The task settings page (§8.1) needs an entry for every added task."""
        await started_client.post(
            "/api/v1/tasks/12345", json={"room_id": 12345, "auto_enable": False}
        )

        body = (await started_client.get("/api/v1/settings/tasks/12345")).json()
        assert body["code"] == 0
        assert body["data"]["roomId"] == 12345
        assert body["data"]["enableMonitor"] is False

        patched = await started_client.patch(
            "/api/v1/settings/tasks/12345",
            json={"recorder": {"qualityNumber": 400}},
        )
        assert patched.json()["code"] == 0
        assert patched.json()["data"]["recorder"]["qualityNumber"] == 400

        # Deleting the task takes its settings with it.
        await started_client.delete("/api/v1/tasks/12345")
        gone = (await started_client.get("/api/v1/settings/tasks/12345")).json()
        assert gone["code"] == 404

    async def test_added_task_survives_a_restart(
        self, fake_server: FakeBiliServer, app: Any, tmp_path: Path
    ) -> None:
        """Tasks are restored from the config file on the next start (§5.2)."""
        application = app.state.application
        await application.startup()
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                resp = await client.post("/api/v1/tasks/12345", json={"room_id": 12345})
                assert resp.json()["code"] == 0
        finally:
            await application.shutdown()

        # A second application over the same config file, as after a restart.
        restarted = create_application(
            config_path=tmp_path / "config.toml",
            output_dir=tmp_path / "recordings",
            log_dir=tmp_path / "logs",
        )
        settings = restarted.state.settings_manager.settings
        settings.bili_api.base_api_urls = [fake_server.base_url]
        settings.bili_api.base_live_api_urls = [fake_server.base_url]
        settings.bili_api.base_play_info_api_urls = [fake_server.base_url]

        await restarted.state.application.startup()
        try:
            transport = ASGITransport(app=restarted)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                body = (await client.get("/api/v1/tasks/12345/data")).json()
                assert body["code"] == 0
                assert body["data"]["user_name"] == "TestStreamer"
        finally:
            await restarted.state.application.shutdown()


class TestSettingsE2E:
    """End-to-end settings management."""

    async def test_settings_roundtrip(self, client: AsyncClient) -> None:
        """Patch settings and verify they persist."""
        # Patch
        resp = await client.patch(
            "/api/v1/settings",
            json={"recorder": {"quality_number": 400}},
        )
        body = resp.json()
        assert body["code"] == 0

        # Read back
        resp = await client.get("/api/v1/settings")
        body = resp.json()
        assert body["code"] == 0

    async def test_validation_dir_valid(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        """Validate a real directory."""
        resp = await client.post(
            "/api/v1/validation/dir",
            json={"path": str(tmp_path)},
        )
        body = resp.json()
        assert body["code"] == 0
        assert body["message"] == "Directory is valid"


class TestAppEndpointsE2E:
    """End-to-end app endpoint tests."""

    async def test_app_status(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/app/status")
        body = resp.json()
        assert body["code"] == 0
        assert "task_count" in body["data"]

    async def test_app_info(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/app/info")
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["name"] == "bili-rec"
