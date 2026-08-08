"""Real danmaku WebSocket long-connection verification.

Discovers the danmaku servers for a live room, opens a real WebSocket
connection through ``DanmakuClient``, waits for the authenticated
``danmaku_connected`` event, and (best-effort) observes broadcast messages.
Connection establishment is the hard assertion; receiving messages is
opportunistic since a room may be momentarily quiet.
"""

from __future__ import annotations

import asyncio

import aiohttp
import pytest

from birec.bili.danmaku_client import DanmakuClient, DanmakuClientListener
from birec.bili.live import Live
from birec.bili.models import LiveStatus
from birec.bili.typing import Danmaku

_CONNECT_TIMEOUT = 15.0
_OBSERVE_SECONDS = 8.0


class _CollectingListener(DanmakuClientListener):
    def __init__(self) -> None:
        self.connected = asyncio.Event()
        self.disconnected = asyncio.Event()
        self.danmakus: list[Danmaku] = []

    def on_danmaku(self, danmaku: Danmaku) -> None:
        self.danmakus.append(danmaku)

    def on_danmaku_connected(self) -> None:
        self.connected.set()

    def on_danmaku_disconnected(self) -> None:
        self.disconnected.set()


class TestDanmakuWebSocket:
    async def test_connect_and_observe(
        self,
        live: Live,
        bili_session: aiohttp.ClientSession,
        bili_cookie: str,
    ) -> None:
        status = await live.get_live_status()
        if status != LiveStatus.LIVE:
            pytest.skip(f"room {live.room_id} is not LIVE (status={status.name})")

        info = await live.api.get_danmu_info(live.room_id)
        usable = [entry for entry in info["host_list"] if entry.get("host")]
        assert usable, "danmu_info returned no hosts"
        # Mirror the production task layer: each host's port travels with the
        # scheme of the field it came from. The platform's TLS endpoint moved
        # off 443, so assuming the default port no longer reaches it (#43).
        hosts = [entry["host"] for entry in usable]
        ports: list[int] = []
        secure: list[bool] = []
        for entry in usable:
            if entry.get("wss_port"):
                ports.append(entry["wss_port"])
                secure.append(True)
            elif entry.get("ws_port"):
                ports.append(entry["ws_port"])
                secure.append(False)
            else:
                ports.append(443)
                secure.append(True)

        client = DanmakuClient(
            live.room_id,
            session=bili_session,
            cookie=bili_cookie,
            user_agent=live.user_agent,
        )
        client.set_danmu_info(hosts, info["token"], ports=ports, secure=secure)
        listener = _CollectingListener()
        client.add_listener(listener)

        await client.start()
        try:
            await asyncio.wait_for(listener.connected.wait(), timeout=_CONNECT_TIMEOUT)
            assert client.connected
            # Best-effort: give the room a window to broadcast messages.
            await asyncio.sleep(_OBSERVE_SECONDS)
        finally:
            await client.stop()

        assert not client.connected
