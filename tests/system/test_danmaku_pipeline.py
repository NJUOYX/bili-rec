"""System tests for the danmaku path: broadcast socket → receiver → XML on disk.

The danmaku client speaks a binary framing over a WebSocket, and everything
downstream of it — the receiver, the dumper, the XML on disk, the counters the
UI shows — only ever runs when a real socket has been through a real handshake.
The unit tests drive each piece with hand-made messages; these drive the whole
path from a server that answers the way Bilibili's does.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from .fake_bili_server import FakeBiliServer
from .harness import (
    ROOM_ID,
    add_task,
    begin_live,
    task_of,
    wait_for_recording,
    wait_until,
    wait_until_not_recording,
    wait_until_recording,
)


async def connected_task(client: AsyncClient) -> Any:
    """Add the room and wait for its danmaku socket to finish the handshake."""
    await add_task(client)
    task = task_of(client)
    await wait_until(
        lambda: task._danmaku_client.connected,  # noqa: SLF001
        what="the danmaku client to connect",
    )
    return task


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
        await connected_task(client)

        assert len(fake_server.danmaku_ws_connections) == 1

    async def test_it_authenticates_with_the_room_and_token(
        self, client: AsyncClient, fake_server: FakeBiliServer
    ) -> None:
        """The handshake must carry what the server needs to accept us."""
        await connected_task(client)

        assert fake_server.auth_payloads
        payload = fake_server.auth_payloads[0]
        assert '"roomid": 12345' in payload
        assert "fake_danmaku_token" in payload


class TestDanmakuReachesTheRecording:
    """A broadcast message must end up in this segment's XML."""

    async def test_a_danmaku_lands_in_the_xml(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        await connected_task(client)
        await begin_live(client, fake_server)
        await wait_until(
            lambda: bool(list(out_dir.rglob("*.xml"))), what="the XML to be created"
        )

        await fake_server.send_danmaku("hello from the fake")

        xml = next(iter(out_dir.rglob("*.xml")))
        await wait_until(
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
        await connected_task(client)
        await begin_live(client, fake_server)
        await wait_until(
            lambda: bool(list(out_dir.rglob("*.xml"))), what="the XML to be created"
        )
        xml = next(iter(out_dir.rglob("*.xml")))

        await fake_server.send_danmaku("timed")
        await wait_until(
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
        await connected_task(client)
        await begin_live(client, fake_server)
        await wait_until(
            lambda: bool(list(out_dir.rglob("*.xml"))), what="the XML to be created"
        )
        xml = next(iter(out_dir.rglob("*.xml")))

        for i in range(5):
            await fake_server.send_danmaku(f"message {i}")

        await wait_until(
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
        await connected_task(client)
        await begin_live(client, fake_server)
        await wait_until(
            lambda: bool(list(out_dir.rglob("*.xml"))), what="the XML to be created"
        )
        xml = next(iter(out_dir.rglob("*.xml")))
        await fake_server.send_danmaku("last words")
        await wait_until(
            lambda: "last words" in xml.read_text(encoding="utf-8"),
            what="the danmaku to be written",
        )

        await client.post(f"/api/v1/tasks/{ROOM_ID}/recorder/disable")
        await asyncio.sleep(0.5)

        content = xml.read_text(encoding="utf-8")
        assert content.rstrip().endswith("</i>")
        assert "last words" in content

    async def test_the_api_reports_how_many_danmaku_arrived(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """Regression: the counter has to follow what is being received.

        Nothing ever called ``update_danmu``, so the dashboard showed 0 however
        busy the room was. The messages really did arrive — they were in the XML
        — only the counter never heard about it.
        """
        await connected_task(client)
        await begin_live(client, fake_server)
        await wait_until(
            lambda: bool(list(out_dir.rglob("*.xml"))), what="the XML to be created"
        )

        for i in range(3):
            await fake_server.send_danmaku(f"counted {i}")
        xml = next(iter(out_dir.rglob("*.xml")))
        await wait_until(
            lambda: "counted 2" in xml.read_text(encoding="utf-8"),
            what="the danmaku to be written",
        )

        body = (await client.get(f"/api/v1/tasks/{ROOM_ID}/data")).json()
        assert body["data"]["task_status"]["danmu_total"] == 3


class TestLiveCommandsDriveTheMonitor:
    """LIVE/PREPARING on the broadcast socket flip the room state at once (#27).

    Before the wiring landed, production learned about a broadcast beginning or
    ending from the periodic check alone — these drive the same transitions
    through the real socket and watch the state move without any poll in reach.
    """

    async def test_commands_flip_the_state_without_waiting_for_polling(
        self,
        client: AsyncClient,
        fake_server: FakeBiliServer,
        out_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Move the periodic channel out of reach for the whole test: if the
        # flips below came from polling instead of the commands, they could
        # not arrive inside the wait timeout and the test would fail.
        monkeypatch.setattr(
            "birec.bili.live_monitor._PERIODIC_CHECK_INTERVAL", 24 * 3600
        )
        task = await connected_task(client)
        monitor = task._monitor  # noqa: SLF001
        assert monitor.is_living is False

        fake_server.set_live()
        await fake_server.send_danmaku_command("LIVE", {})

        await wait_until(
            lambda: monitor.is_living,
            what="the LIVE command to flip the monitor",
        )
        await wait_until_recording(client)
        await wait_for_recording(out_dir)

        fake_server.set_offline()
        await fake_server.send_danmaku_command("PREPARING", {})

        await wait_until(
            lambda: not monitor.is_living,
            what="the PREPARING command to flip the monitor back",
        )
        await wait_until_not_recording(client)
