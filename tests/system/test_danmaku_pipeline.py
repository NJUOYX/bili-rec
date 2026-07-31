"""System tests for the danmaku path: broadcast socket → receiver → XML on disk.

The danmaku client speaks a binary framing over a WebSocket, and everything
downstream of it — the receiver, the dumper, the XML on disk, the counters the
UI shows — only ever runs when a real socket has been through a real handshake.
The unit tests drive each piece with hand-made messages; these drive the whole
path from a server that answers the way Bilibili's does.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from birec.application import create_application

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


def _task(client: AsyncClient) -> Any:
    return client.app.state.application.task_manager.get_task(_ROOM_ID)  # type: ignore[attr-defined]


async def _add_task(client: AsyncClient) -> None:
    resp = await client.post(f"/api/v1/tasks/{_ROOM_ID}", json={"room_id": _ROOM_ID})
    assert resp.json()["code"] == 0


async def _connected_task(client: AsyncClient) -> Any:
    """Add the room and wait for its danmaku socket to finish the handshake."""
    await _add_task(client)
    task = _task(client)
    await _wait_until(
        lambda: task._danmaku_client.connected,  # noqa: SLF001
        what="the danmaku client to connect",
    )
    return task


async def _begin_live(client: AsyncClient, fake_server: FakeBiliServer) -> None:
    fake_server.set_live()
    await _task(client)._monitor.handle_command("LIVE")  # noqa: SLF001


class TestDanmakuConnection:
    """The client must reach the broadcast server the API pointed it at."""

    async def test_it_connects_to_the_advertised_endpoint(
        self, client: AsyncClient, fake_server: FakeBiliServer
    ) -> None:
        """Regression: the port from get_danmu_info must be used.

        The URL was built as ``wss://{host}/sub`` with the port thrown away, so
        a server on anything other than 443 was unreachable — including every
        endpoint the API is free to hand out.
        """
        await _connected_task(client)

        assert len(fake_server.danmaku_ws_connections) == 1

    async def test_it_authenticates_with_the_room_and_token(
        self, client: AsyncClient, fake_server: FakeBiliServer
    ) -> None:
        """The handshake must carry what the server needs to accept us."""
        await _connected_task(client)

        assert fake_server.auth_payloads
        payload = fake_server.auth_payloads[0]
        assert '"roomid": 12345' in payload
        assert "fake_danmaku_token" in payload


class TestDanmakuReachesTheRecording:
    """A broadcast message must end up in this segment's XML."""

    async def test_a_danmaku_lands_in_the_xml(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        await _connected_task(client)
        await _begin_live(client, fake_server)
        await _wait_until(
            lambda: bool(list(out_dir.rglob("*.xml"))), what="the XML to be created"
        )

        await fake_server.send_danmaku("hello from the fake")

        xml = next(iter(out_dir.rglob("*.xml")))
        await _wait_until(
            lambda: "hello from the fake" in xml.read_text(encoding="utf-8"),
            what="the danmaku to be written",
        )

    async def test_the_written_offset_is_within_the_recording(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """Each line is timed against the start of the segment, not the epoch.

        A player reads that offset literally, so getting the unit or the origin
        wrong puts every line somewhere the viewer will never see.
        """
        await _connected_task(client)
        await _begin_live(client, fake_server)
        await _wait_until(
            lambda: bool(list(out_dir.rglob("*.xml"))), what="the XML to be created"
        )
        xml = next(iter(out_dir.rglob("*.xml")))

        await fake_server.send_danmaku("timed")
        await _wait_until(
            lambda: "timed" in xml.read_text(encoding="utf-8"),
            what="the danmaku to be written",
        )

        line = next(
            ln for ln in xml.read_text(encoding="utf-8").splitlines() if "timed" in ln
        )
        offset = float(line.split('p="', 1)[1].split(",", 1)[0])
        assert 0 <= offset < 60, f"offset {offset} is outside the recording"

    async def test_messages_keep_their_order(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        await _connected_task(client)
        await _begin_live(client, fake_server)
        await _wait_until(
            lambda: bool(list(out_dir.rglob("*.xml"))), what="the XML to be created"
        )
        xml = next(iter(out_dir.rglob("*.xml")))

        for i in range(5):
            await fake_server.send_danmaku(f"message {i}")

        await _wait_until(
            lambda: "message 4" in xml.read_text(encoding="utf-8"),
            what="all danmaku to be written",
        )
        content = xml.read_text(encoding="utf-8")
        positions = [content.index(f"message {i}") for i in range(5)]
        assert positions == sorted(positions)

    async def test_the_xml_is_closed_off_when_recording_stops(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """A half-written document is not something a player can open."""
        await _connected_task(client)
        await _begin_live(client, fake_server)
        await _wait_until(
            lambda: bool(list(out_dir.rglob("*.xml"))), what="the XML to be created"
        )
        xml = next(iter(out_dir.rglob("*.xml")))
        await fake_server.send_danmaku("last words")
        await _wait_until(
            lambda: "last words" in xml.read_text(encoding="utf-8"),
            what="the danmaku to be written",
        )

        await client.post(f"/api/v1/tasks/{_ROOM_ID}/recorder/disable")
        await asyncio.sleep(0.5)

        content = xml.read_text(encoding="utf-8")
        assert content.rstrip().endswith("</i>")
        assert "last words" in content

    @pytest.mark.xfail(
        reason="Statistics.update_danmu has no caller, so the count stays 0",
        strict=True,
    )
    async def test_the_api_reports_how_many_danmaku_arrived(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """The danmaku counter should follow what is being received.

        It does not move: nothing in ``src`` ever calls ``update_danmu``, so the
        dashboard shows 0 no matter how busy the room is. The messages really do
        arrive — they are in the XML — only the counter never hears about it.

        Strict, so it turns green once the counter is connected.
        """
        await _connected_task(client)
        await _begin_live(client, fake_server)
        await _wait_until(
            lambda: bool(list(out_dir.rglob("*.xml"))), what="the XML to be created"
        )

        for i in range(3):
            await fake_server.send_danmaku(f"counted {i}")
        xml = next(iter(out_dir.rglob("*.xml")))
        await _wait_until(
            lambda: "counted 2" in xml.read_text(encoding="utf-8"),
            what="the danmaku to be written",
        )

        body = (await client.get(f"/api/v1/tasks/{_ROOM_ID}/data")).json()
        assert body["data"]["task_status"]["danmu_total"] == 3
