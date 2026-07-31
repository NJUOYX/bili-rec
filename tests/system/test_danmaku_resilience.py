"""System tests for a broadcast socket that misbehaves.

The danmaku client keeps a long-lived WebSocket open for the whole broadcast,
which means it spends most of its life in the states nobody writes tests for:
the server hung up, the first advertised host is down, the handshake was
refused, the frame that arrived is not a frame. None of that is exotic — it is
what a socket held open for six hours does.

Everything here drives the real client against a fake broadcast server that has
been told to behave badly, and checks recovery by what ends up in the XML rather
than by whether the process is still alive.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from .fake_bili_server import FakeBiliServer
from .harness import ROOM_ID, add_task, begin_live, task_of, wait_until

pytestmark = pytest.mark.usefixtures("fast_danmaku_retry")


async def _connected_task(client: AsyncClient) -> Any:
    """Add the room and wait for its broadcast socket through the handshake."""
    await add_task(client)
    task = task_of(client)
    await wait_until(
        lambda: task._danmaku_client.connected,  # noqa: SLF001
        what="the danmaku client to connect",
    )
    return task


async def _recording_with_danmaku(
    client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
) -> Path:
    """Get to the point where danmaku have somewhere to be written."""
    await begin_live(client, fake_server)
    await wait_until(
        lambda: bool(list(out_dir.rglob("*.xml"))), what="the danmaku XML to be created"
    )
    return next(iter(out_dir.rglob("*.xml")))


class TestReconnecting:
    """Losing the socket must cost a reconnect, not the rest of the broadcast."""

    async def test_a_server_that_hangs_up_is_reconnected_to(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """A hung-up socket must come back, and come back usable.

        Reconnecting is only half of it: the new socket has to go through the
        handshake again and actually deliver, or the room looks connected and
        stays silent for the rest of the stream.
        """
        fake_server.set_fault(ws_close_after_auth=True, ws_fault_first_only=True)

        await _connected_task(client)
        xml = await _recording_with_danmaku(client, fake_server, out_dir)

        assert fake_server.ws_connections_total >= 2, "the client never came back"

        await fake_server.send_danmaku("after the reconnect")
        await wait_until(
            lambda: "after the reconnect" in xml.read_text(encoding="utf-8"),
            what="a danmaku over the reconnected socket",
        )

    async def test_a_dead_first_host_rotates_to_the_next(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """Regression: the rotation has to reach the hosts behind the first.

        Only the first host's port was kept, so rotating to the second aimed its
        hostname at the first one's port — an address nobody advertised. With
        host one down, the rotation that exists to save the connection could
        never reach host two, and the room got no danmaku at all.
        """
        fake_server.set_fault(danmaku_dead_host_first=True)

        task = await _connected_task(client)

        assert task._danmaku_client._host_index == 1  # noqa: SLF001
        xml = await _recording_with_danmaku(client, fake_server, out_dir)
        await fake_server.send_danmaku("from the second host")
        await wait_until(
            lambda: "from the second host" in xml.read_text(encoding="utf-8"),
            what="a danmaku from the host the client rotated to",
        )

    async def test_a_refused_handshake_is_retried_not_fatal(
        self, client: AsyncClient, fake_server: FakeBiliServer
    ) -> None:
        """A rejected auth must stay inside the client.

        The token can go stale, and the answer is a business error rather than a
        broken socket. What must not happen is the failure escaping into the
        task and taking the recording down with it: the room can be recorded
        perfectly well while its danmaku cannot be read.
        """
        fake_server.set_fault(ws_auth_fail_code=-101)

        await add_task(client)
        task = task_of(client)

        await wait_until(
            lambda: len(fake_server.auth_payloads) >= 3,
            what="the client to retry the handshake",
        )
        assert task._danmaku_client.connected is False  # noqa: SLF001

        # The application is unharmed and the task is still there to be used.
        body = (await client.get(f"/api/v1/tasks/{ROOM_ID}/data")).json()
        assert body["code"] == 0


class TestTheWireFormat:
    """What the real API sends is compressed, and sometimes malformed."""

    async def test_deflated_danmaku_reach_the_xml(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """zlib is one of the two envelopes production actually uses."""
        await _connected_task(client)
        xml = await _recording_with_danmaku(client, fake_server, out_dir)

        await fake_server.send_compressed_danmaku("deflated words", proto=2)

        await wait_until(
            lambda: "deflated words" in xml.read_text(encoding="utf-8"),
            what="the deflated danmaku to be decoded and written",
        )

    async def test_brotli_danmaku_reach_the_xml(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """And brotli is the other, and the client's own default."""
        await _connected_task(client)
        xml = await _recording_with_danmaku(client, fake_server, out_dir)

        await fake_server.send_compressed_danmaku("brotli words", proto=3)

        await wait_until(
            lambda: "brotli words" in xml.read_text(encoding="utf-8"),
            what="the brotli danmaku to be decoded and written",
        )

    async def test_a_malformed_frame_does_not_cost_the_socket(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """Garbage on the wire must be skipped, not treated as a disconnect.

        Dropping the socket over one bad frame would turn a hiccup into a
        reconnect, and reconnecting is the expensive part.
        """
        await _connected_task(client)
        xml = await _recording_with_danmaku(client, fake_server, out_dir)
        connections_before = fake_server.ws_connections_total

        await fake_server.send_malformed_packet()
        await fake_server.send_danmaku("still here")

        await wait_until(
            lambda: "still here" in xml.read_text(encoding="utf-8"),
            what="the socket to carry on after the bad frame",
        )
        assert fake_server.ws_connections_total == connections_before


class TestKeepingTheSocketAlive:
    """A long-lived socket needs its heartbeat, and needs it answered."""

    async def test_heartbeats_keep_being_sent(
        self, client: AsyncClient, fake_server: FakeBiliServer
    ) -> None:
        """Without them the broadcast server drops the connection on its own."""
        await _connected_task(client)

        await wait_until(
            lambda: fake_server.heartbeats_received >= 2,
            what="the client to keep sending heartbeats",
        )

    @pytest.mark.xfail(
        reason="the client never checks that its heartbeats are answered",
        strict=True,
    )
    async def test_an_unanswered_heartbeat_is_noticed(
        self, client: AsyncClient, fake_server: FakeBiliServer
    ) -> None:
        """A server that stops answering should be treated as gone.

        It is not. ``_heartbeat_loop`` sends and sleeps, and nothing anywhere
        compares what was sent against what came back, so a half-open socket —
        the TCP connection still up, the server no longer talking — looks
        perfectly healthy. The room silently receives no danmaku for the rest of
        the stream while the client reports itself connected.

        Strict, so it turns green the day the heartbeat is actually checked.
        """
        fake_server.set_fault(ws_skip_heartbeat_reply=True, ws_fault_first_only=True)

        await _connected_task(client)

        await wait_until(
            lambda: fake_server.ws_connections_total >= 2,
            timeout=5.0,
            what="the unanswered heartbeat to trigger a reconnect",
        )
