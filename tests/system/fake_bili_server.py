"""Fake Bilibili server for end-to-end system tests (§11.3).

Provides controllable API endpoints that simulate the Bilibili live
platform: room info, play info (stream URLs), danmaku info, a minimal
FLV stream endpoint, and a WebSocket danmaku endpoint.
"""

from __future__ import annotations

import asyncio
import struct
from typing import Any

from aiohttp import web


def _make_flv_header() -> bytes:
    """FLV file header: signature + version + flags + header size."""
    return b"FLV" + b"\x01" + b"\x05" + b"\x00\x00\x00\x09"


def _make_flv_tag(tag_type: int, data: bytes, timestamp: int = 0) -> bytes:
    """Build a single FLV tag with previous-tag-size trailer."""
    data_size = len(data)
    ts_lower = timestamp & 0xFFFFFF
    ts_ext = (timestamp >> 24) & 0xFF
    header = (
        struct.pack(
            ">B",
            tag_type,
        )
        + struct.pack(">I", data_size)[1:]
    )  # 3 bytes size
    header += struct.pack(">I", ts_lower)[1:]  # 3 bytes ts lower
    header += struct.pack(">B", ts_ext)  # 1 byte ts ext
    header += b"\x00\x00\x00"  # stream id
    tag = header + data
    # Previous tag size = 11 (header) + data_size
    prev_size = struct.pack(">I", 11 + data_size)
    return tag + prev_size


def _make_script_tag() -> bytes:
    """Minimal onMetaData script tag."""
    # Simplified AMF: just enough to be recognized
    name = b"\x02\x00\x0aonMetaData"
    # Empty ECMA array marker
    value = b"\x08\x00\x00\x00\x00\x00\x00\x09"
    data = name + value
    return _make_flv_tag(18, data, 0)


def _make_video_tag(timestamp: int = 0) -> bytes:
    """Minimal video tag (keyframe, AVC NALU)."""
    # Frame type 1 (keyframe) | CodecID 7 (AVC)
    data = b"\x17\x01\x00\x00\x00" + b"\x00" * 20
    return _make_flv_tag(9, data, timestamp)


def _make_audio_tag(timestamp: int = 0) -> bytes:
    """Minimal audio tag (AAC)."""
    # Sound format 10 (AAC) | rate 3 | size 1 | type 1
    data = b"\xaf\x01" + b"\x00" * 16
    return _make_flv_tag(8, data, timestamp)


def generate_flv_stream(num_frames: int = 10) -> bytes:
    """Generate a minimal valid FLV byte stream."""
    buf = bytearray()
    buf += _make_flv_header()
    # First previous tag size = 0
    buf += struct.pack(">I", 0)
    buf += _make_script_tag()
    for i in range(num_frames):
        ts = i * 40  # 25fps
        buf += _make_video_tag(ts)
        buf += _make_audio_tag(ts)
    return bytes(buf)


class FakeBiliServer:
    """Controllable fake Bilibili live server."""

    def __init__(self, room_id: int = 12345) -> None:
        self.room_id = room_id
        self.live_status = 0  # 0=offline, 1=live, 2=replay
        self.stream_format = "flv"
        self._app = web.Application()
        self._setup_routes()
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self.port: int = 0
        self.flv_data = generate_flv_stream(20)
        self.danmaku_ws_connections: list[web.WebSocketResponse] = []

    def _setup_routes(self) -> None:
        # Both API platforms are served: ``Live`` defaults to the web platform,
        # while the stream fetcher rotates to android on failure.
        for prefix in ("app-room", "web-room"):
            self._app.router.add_get(
                f"/xlive/{prefix}/v1/index/getInfoByRoom",
                self._handle_get_info_by_room,
            )
            self._app.router.add_get(
                f"/xlive/{prefix}/v2/index/getRoomPlayInfo",
                self._handle_get_room_play_info,
            )
            self._app.router.add_get(
                f"/xlive/{prefix}/v1/index/getDanmuInfo",
                self._handle_get_danmu_info,
            )
        self._app.router.add_get("/x/web-interface/nav", self._handle_nav)
        self._app.router.add_get("/stream.flv", self._handle_stream)
        self._app.router.add_get("/ws/danmaku", self._handle_ws_danmaku)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    async def start(self) -> None:
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await self._site.start()
        # Get the actual port
        assert self._site._server is not None
        sockets = self._site._server.sockets
        assert sockets is not None
        self.port = sockets[0].getsockname()[1]

    async def stop(self) -> None:
        for ws in self.danmaku_ws_connections:
            await ws.close()
        if self._runner:
            await self._runner.cleanup()

    def set_live(self) -> None:
        self.live_status = 1

    def set_offline(self) -> None:
        self.live_status = 0

    async def _handle_get_info_by_room(self, request: web.Request) -> web.Response:
        data: dict[str, Any] = {
            "code": 0,
            "message": "ok",
            "data": {
                "room_info": {
                    "room_id": self.room_id,
                    "short_id": 0,
                    "uid": 99999,
                    "title": "Test Live Room",
                    "live_status": self.live_status,
                    "live_start_time": 1700000000,
                    "area_id": 371,
                    "area_name": "测试分区",
                    "parent_area_id": 11,
                    "parent_area_name": "测试父分区",
                    "online": 42,
                    "tags": "test",
                    "description": "测试直播间",
                    "cover": f"{self.base_url}/cover.jpg",
                },
                "anchor_info": {
                    "base_info": {
                        "uname": "TestStreamer",
                        "gender": "男",
                        "face": f"{self.base_url}/face.jpg",
                    },
                },
            },
        }
        return web.json_response(data)

    async def _handle_get_room_play_info(self, request: web.Request) -> web.Response:
        if self.live_status != 1:
            data: dict[str, Any] = {
                "code": 0,
                "message": "ok",
                "data": {
                    "playurl_info": {
                        "playurl": None,
                    },
                },
            }
            return web.json_response(data)

        stream_url = f"{self.base_url}/stream.flv"
        data = {
            "code": 0,
            "message": "ok",
            "data": {
                "playurl_info": {
                    "playurl": {
                        "stream": [
                            {
                                "protocol_name": "http_stream",
                                "format": [
                                    {
                                        "format_name": "flv",
                                        "codec": [
                                            {
                                                "codec_name": "avc",
                                                "current_qn": 10000,
                                                "accept_qn": [
                                                    10000,
                                                    400,
                                                ],
                                                "base_url": stream_url,
                                                "url_info": [
                                                    {
                                                        "host": f"http://127.0.0.1:{self.port}",
                                                        "extra": "/stream.flv",
                                                    }
                                                ],
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    },
                },
            },
        }
        return web.json_response(data)

    async def _handle_get_danmu_info(self, request: web.Request) -> web.Response:
        data: dict[str, Any] = {
            "code": 0,
            "message": "ok",
            "data": {
                "host_list": [
                    {
                        "host": "127.0.0.1",
                        "port": self.port,
                        "wss_port": self.port,
                        "ws_port": self.port,
                    }
                ],
                "token": "fake_danmaku_token",
            },
        }
        return web.json_response(data)

    async def _handle_nav(self, request: web.Request) -> web.Response:
        """Serve the WBI key material the web API signs its requests with."""
        img = "a" * 32
        sub = "b" * 32
        data: dict[str, Any] = {
            "code": 0,
            "message": "ok",
            "data": {
                "wbi_img": {
                    "img_url": f"https://i0.hdslb.com/bfs/wbi/{img}.png",
                    "sub_url": f"https://i0.hdslb.com/bfs/wbi/{sub}.png",
                },
            },
        }
        return web.json_response(data)

    async def _handle_stream(self, request: web.Request) -> web.StreamResponse:
        """Serve the FLV stream."""
        resp = web.StreamResponse(
            status=200,
            headers={"Content-Type": "video/x-flv"},
        )
        await resp.prepare(request)
        await resp.write(self.flv_data)
        # Keep connection open briefly to simulate streaming
        await asyncio.sleep(0.5)
        await resp.write_eof()
        return resp

    async def _handle_ws_danmaku(self, request: web.Request) -> web.WebSocketResponse:
        """WebSocket danmaku endpoint."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.danmaku_ws_connections.append(ws)
        try:
            async for _msg in ws:
                pass  # Ignore incoming messages
        finally:
            self.danmaku_ws_connections.remove(ws)
        return ws

    async def send_danmaku_command(self, cmd: str, data: dict[str, Any]) -> None:
        """Broadcast a danmaku command to all connected WS clients."""
        import json

        msg = json.dumps({"cmd": cmd, **data})
        for ws in self.danmaku_ws_connections:
            await ws.send_str(msg)
