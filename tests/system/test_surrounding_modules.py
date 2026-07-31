"""System tests for the pieces around the recording: notifications, disk, updates.

Each of these modules has unit tests that drive it with hand-made input. What
those cannot answer is whether the module is reachable at all from a running
application — the question behind #10, and the one this file asks of the three
of them.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from birec.application import create_application
from birec.notification import NotificationCenter
from birec.space import SpaceReclaimer

from .fake_bili_server import FakeBiliServer

_ROOM_ID = 12345
_TIMEOUT = 20.0
_POLL = 0.05


async def _wait_until(
    predicate: Callable[[], bool], *, timeout: float = _TIMEOUT, what: str = "condition"
) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(_POLL)
    pytest.fail(f"Timed out after {timeout}s waiting for {what}")


@pytest.fixture()
async def fake_server() -> AsyncIterator[FakeBiliServer]:
    server = FakeBiliServer(room_id=_ROOM_ID)
    await server.start()
    try:
        yield server
    finally:
        await server.stop()


@pytest.fixture()
def out_dir(tmp_path: Path) -> Path:
    return tmp_path / "recordings"


@pytest.fixture()
async def client(
    tmp_path: Path, out_dir: Path, fake_server: FakeBiliServer
) -> AsyncIterator[AsyncClient]:
    app = create_application(
        config_path=tmp_path / "config.toml",
        output_dir=out_dir,
        log_dir=tmp_path / "logs",
    )
    settings = app.state.settings_manager.settings
    settings.bili_api.base_api_urls = [fake_server.base_url]
    settings.bili_api.base_live_api_urls = [fake_server.base_url]
    settings.bili_api.base_play_info_api_urls = [fake_server.base_url]

    application = app.state.application
    await application.startup()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            c.app = app  # type: ignore[attr-defined]
            yield c
    finally:
        await application.shutdown()


async def _begin_recording(client: AsyncClient, fake_server: FakeBiliServer) -> None:
    resp = await client.post(f"/api/v1/tasks/{_ROOM_ID}", json={"room_id": _ROOM_ID})
    assert resp.json()["code"] == 0
    fake_server.set_live()
    task = client.app.state.application.task_manager.get_task(_ROOM_ID)  # type: ignore[attr-defined]
    await task._monitor.handle_command("LIVE")  # noqa: SLF001


class TestNotifications:
    """A real recording must produce notifications a subscriber can act on."""

    async def test_a_recording_notifies_subscribers(
        self, client: AsyncClient, fake_server: FakeBiliServer
    ) -> None:
        """The notification facade must cope with the events really published.

        Its unit tests feed it events built by hand. This one lets a live
        recording drive it, which is the only way to catch an event shape it
        cannot convert.
        """
        received: list[Any] = []
        subscription = NotificationCenter().subscribe(received.append)
        try:
            await _begin_recording(client, fake_server)
            await _wait_until(
                lambda: any(n.event_type == "VideoFileCreatedEvent" for n in received),
                what="a recording notification",
            )
        finally:
            subscription.dispose()

        notification = next(
            n for n in received if n.event_type == "VideoFileCreatedEvent"
        )
        assert notification.room_id == _ROOM_ID
        assert notification.data["path"].endswith(".flv")

    async def test_the_room_filter_keeps_other_rooms_out(
        self, client: AsyncClient, fake_server: FakeBiliServer
    ) -> None:
        """Subscribing to one room must not deliver another room's events."""
        received: list[Any] = []
        subscription = NotificationCenter().subscribe(received.append, room_id=999)
        try:
            await _begin_recording(client, fake_server)
            await asyncio.sleep(1.0)
        finally:
            subscription.dispose()

        assert received == []

    async def test_the_event_type_filter_is_applied(
        self, client: AsyncClient, fake_server: FakeBiliServer
    ) -> None:
        """Asking for one kind of event must not deliver every other kind."""
        received: list[Any] = []
        subscription = NotificationCenter().subscribe(
            received.append, event_types=["DanmakuFileCreatedEvent"]
        )
        try:
            await _begin_recording(client, fake_server)
            await _wait_until(
                lambda: bool(received), what="a danmaku file notification"
            )
        finally:
            subscription.dispose()

        assert {n.event_type for n in received} == {"DanmakuFileCreatedEvent"}


class TestDiskSpace:
    """Disk-space handling has to be reachable from the running application."""

    @pytest.mark.xfail(
        reason="nothing constructs a SpaceMonitor; the manager's slot stays None",
        strict=True,
    )
    async def test_the_application_watches_disk_space(
        self, client: AsyncClient
    ) -> None:
        """A long recording filling the disk should be noticed.

        ``RecordTaskManager`` takes a monitor and a reclaimer, but nothing in
        ``src`` ever builds one, so both slots are always ``None`` and the disk
        is never watched. Once more: implemented, never connected.

        Strict, so it turns green the day they are wired up.
        """
        task_manager = client.app.state.application.task_manager  # type: ignore[attr-defined]
        assert task_manager.space_monitor is not None

    async def test_the_reclaimer_finds_old_recordings(self, out_dir: Path) -> None:
        """The reclaimer must work against a real directory of recordings.

        Pinned here because it is the part that deletes the user's files: it has
        to agree with the layout the recorder actually writes.
        """
        room_dir = out_dir / "12345 - TestStreamer"
        room_dir.mkdir(parents=True)
        old = room_dir / "blive_12345_old.flv"
        old.write_bytes(b"x" * 4096)

        reclaimer = SpaceReclaimer([out_dir], rec_ttl=0)

        assert old in reclaimer.find_reclaimable_files()


class TestUpdateCheck:
    """The update endpoint must answer without reaching the real PyPI."""

    async def test_it_reports_the_latest_version(self, client: AsyncClient) -> None:
        with patch(
            "birec.update.PypiApi.get_latest_version_string",
            new=AsyncMock(return_value="9.9.9"),
        ):
            body = (await client.get("/api/v1/update/version/latest")).json()

        assert body["code"] == 0
        assert body["data"]["version"] == "9.9.9"

    async def test_an_unreachable_pypi_is_reported_not_raised(
        self, client: AsyncClient
    ) -> None:
        """A checker that cannot reach PyPI must not take the endpoint down."""
        with patch(
            "birec.update.PypiApi.get_latest_version_string",
            new=AsyncMock(side_effect=OSError("network down")),
        ):
            resp = await client.get("/api/v1/update/version/latest")

        assert resp.status_code == 200
        assert resp.json()["code"] == 502

    async def test_an_unknown_project_is_a_404(self, client: AsyncClient) -> None:
        with patch(
            "birec.update.PypiApi.get_latest_version_string",
            new=AsyncMock(return_value=None),
        ):
            body = (await client.get("/api/v1/update/version/latest")).json()

        assert body["code"] == 404
