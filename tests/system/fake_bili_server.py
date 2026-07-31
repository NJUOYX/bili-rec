"""Fake Bilibili server for end-to-end system tests (§11.3).

Provides controllable API endpoints that simulate the Bilibili live
platform: room info, play info (stream URLs), danmaku info, a minimal
FLV stream endpoint, and a WebSocket danmaku endpoint.

Everything the real platform can do badly is expressible here too, through
``FaultConfig``: connections that drop mid-stream, APIs that error or stall,
bytes that are not FLV, broadcast sockets that hang up after the handshake.
The faults live on the server side on purpose — the recorder under test stays
entirely real, and what it copes with is a socket behaving badly, which is the
shape of the problem in production.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import struct
import time
import zlib
from dataclasses import dataclass
from typing import Any

import brotli
from aiohttp import WSMsgType, web

# The broadcast protocol, mirrored from birec.bili.danmaku_client: a 16-byte
# header of total length, header length, protocol version, operation, sequence.
_HEADER = struct.Struct(">IHHiI")
_OP_HEARTBEAT = 2
_OP_HEARTBEAT_REPLY = 3
_OP_NOTIFICATION = 5
_OP_AUTH = 7
_OP_AUTH_REPLY = 8
_PROTO_NORMAL = 0
_PROTO_DEFLATE = 2
_PROTO_BROTLI = 3


def _encode_packet(op: int, body: bytes) -> bytes:
    header = _HEADER.pack(len(body) + 16, 16, _PROTO_NORMAL, op, 1)
    return header + body


def _decode_packets(data: bytes) -> list[tuple[int, bytes]]:
    """Split a frame into (operation, body) pairs."""
    packets: list[tuple[int, bytes]] = []
    offset = 0
    while offset + 16 <= len(data):
        total_len, header_len, _ver, op, _seq = _HEADER.unpack_from(data, offset)
        if total_len < header_len or offset + total_len > len(data):
            break
        packets.append((op, data[offset + header_len : offset + total_len]))
        offset += total_len
    return packets


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


def generate_flv_tag_pairs(num_frames: int, start_frame: int = 0) -> bytes:
    """Generate tag pairs without a header, to append to a running stream."""
    buf = bytearray()
    for i in range(start_frame, start_frame + num_frames):
        ts = i * 40
        buf += _make_video_tag(ts)
        buf += _make_audio_tag(ts)
    return bytes(buf)


def _make_bad_tag_type_tag() -> bytes:
    """A tag whose type byte is not one of FLV's three.

    31 survives the 5-bit mask the parser applies, so it reaches the enum and
    is rejected there — the shape of a corrupted byte on the wire.
    """
    return _make_flv_tag(0x1F, b"\x00" * 8, 0)


@dataclass
class FaultConfig:
    """What the fake server should do wrong, and for how long.

    Every field is off by default, so a server without a configured fault
    behaves exactly as it did before this existed.
    """

    # --- Stream faults ---
    # Abort the connection after this many chunks have been written.
    stream_break_after_chunks: int | None = None
    # How many of the first requests get broken; later ones are served whole.
    stream_break_times: int = 1
    # Splice bytes that are not FLV into the payload at this offset.
    stream_garbage_at_byte: int | None = None
    # Embed a tag whose type byte is not one FLV defines.
    stream_bad_tag_type: bool = False
    # End the payload halfway through its last tag, as a dropped connection does.
    stream_truncate_tail: bool = False
    # Answer 200 and then immediately close without a single byte.
    stream_empty: bool = False

    # --- API faults ---
    # Answer room/play info with this business code instead of 0.
    api_error_code: int | None = None
    # Stall this long before answering, the way a struggling endpoint does.
    api_delay: float = 0.0
    # Claim the room is live but offer no playable URL.
    playurl_null: bool = False
    # Advertise an unreachable CDN ahead of the real one.
    stream_dead_cdn_first: bool = False
    # Advertise an unreachable broadcast host ahead of the real one.
    danmaku_dead_host_first: bool = False

    # --- Broadcast (WebSocket) faults ---
    # Hang up as soon as the handshake has been answered.
    ws_close_after_auth: bool = False
    # Reject the handshake with this code.
    ws_auth_fail_code: int | None = None
    # Receive heartbeats and never answer them.
    ws_skip_heartbeat_reply: bool = False
    # Apply the socket faults only to the first connection, so a reconnect
    # succeeds and the test can check that recovery actually works.
    ws_fault_first_only: bool = False


# A port nothing listens on, for the faults that need an unreachable endpoint.
_DEAD_PORT = 1


class FakeBiliServer:
    """Controllable fake Bilibili live server."""

    def __init__(
        self, room_id: int = 12345, *, extra_room_ids: tuple[int, ...] = ()
    ) -> None:
        self.room_id = room_id
        # Rooms this server knows about. Several tasks recording at once need
        # each room to come back with its own id, or they all write to one path.
        self.room_ids = [room_id, *extra_room_ids]
        self.live_status = 0  # 0=offline, 1=live, 2=replay
        self.stream_format = "flv"
        # What the room calls itself. Writable because the recorder turns it
        # into a path, and a title is user-supplied text with no rules.
        self.room_title = "Test Live Room"
        self.streamer_name = "TestStreamer"
        self.fault = FaultConfig()
        self._app = web.Application()
        self._setup_routes()
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self.port: int = 0
        self.flv_data = generate_flv_stream(20)
        self.danmaku_ws_connections: list[web.WebSocketResponse] = []
        # A real CDN hands the stream over in many small writes. Serving the
        # whole blob in one go hides every failure mode that only shows up at a
        # chunk boundary, so the size is deliberately small and configurable.
        self.stream_chunk_size = 64
        self.stream_chunk_delay = 0.01
        # Frames appended after the initial blob, to keep the stream alive for
        # as long as a test needs it.
        self.stream_extra_frames = 400
        self.stream_requests = 0
        # HLS counters and the sliding window's position.
        self.playlist_requests = 0
        self.segment_requests = 0
        self._hls_media_sequence = 0
        # Auth payloads the broadcast endpoint received, so a test can check
        # what the client claimed about itself.
        self.auth_payloads: list[str] = []
        # Every socket the broadcast endpoint has accepted, including the ones
        # already closed: this is how a reconnect becomes observable.
        self.ws_connections_total = 0
        self.heartbeats_received = 0
        self.room_info_requests = 0
        self.play_info_requests = 0

    def set_fault(self, **kwargs: Any) -> None:
        """Turn faults on or off, including while a recording is running."""
        for name, value in kwargs.items():
            if not hasattr(self.fault, name):
                raise AttributeError(f"Unknown fault: {name}")
            setattr(self.fault, name, value)

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
        self._app.router.add_get("/live.m3u8", self._handle_playlist)
        self._app.router.add_get("/seg/{name}", self._handle_segment)
        # The path the real broadcast servers use.
        self._app.router.add_get("/sub", self._handle_ws_danmaku)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def dead_url(self) -> str:
        """An address of the same shape as ``base_url`` that refuses connections."""
        return f"http://127.0.0.1:{_DEAD_PORT}"

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

    async def _apply_api_fault(self) -> web.Response | None:
        """Stall and/or fail the way a struggling endpoint does.

        Returns the error response to send, or ``None`` to carry on normally.
        """
        if self.fault.api_delay:
            await asyncio.sleep(self.fault.api_delay)
        if self.fault.api_error_code is not None:
            return web.json_response(
                {"code": self.fault.api_error_code, "message": "injected fault"}
            )
        return None

    async def _handle_get_info_by_room(self, request: web.Request) -> web.Response:
        self.room_info_requests += 1
        fault_response = await self._apply_api_fault()
        if fault_response is not None:
            return fault_response

        room_id = self._requested_room_id(request)
        data: dict[str, Any] = {
            "code": 0,
            "message": "ok",
            "data": {
                "room_info": {
                    "room_id": room_id,
                    "short_id": 0,
                    "uid": 99999,
                    "title": self.room_title,
                    "live_status": self.live_status,
                    "live_start_time": 1700000000,
                    "area_id": 371,
                    "area_name": "测试分区",
                    "parent_area_id": 11,
                    "parent_area_name": "测试父分区",
                    "online": 42,
                    "tags": "test",
                    "description": "测试直播间",
                    # Left empty on purpose. Cover URLs are forced to https by
                    # the API layer, which this plaintext server cannot serve,
                    # and a room without a cover is an ordinary case anyway.
                    # The cover wiring is covered by the unit tests.
                    "cover": "",
                },
                "anchor_info": {
                    "base_info": {
                        "uname": self.streamer_name,
                        "gender": "男",
                        "face": f"{self.base_url}/face.jpg",
                    },
                },
            },
        }
        return web.json_response(data)

    def _requested_room_id(self, request: web.Request) -> int:
        """The room the request asked about, as long as this server serves it."""
        raw = request.query.get("room_id")
        if raw is None:
            return self.room_id
        try:
            room_id = int(raw)
        except ValueError:
            return self.room_id
        return room_id if room_id in self.room_ids else self.room_id

    async def _handle_get_room_play_info(self, request: web.Request) -> web.Response:
        self.play_info_requests += 1
        fault_response = await self._apply_api_fault()
        if fault_response is not None:
            return fault_response

        if self.live_status != 1 or self.fault.playurl_null:
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
                                                # The real API splits the URL up:
                                                # host + base_url + extra. Putting
                                                # a whole URL in base_url makes the
                                                # stream unreachable, which is how
                                                # this fake used to be written.
                                                "base_url": "/stream.flv",
                                                "url_info": self._flv_url_info(),
                                            }
                                        ],
                                    }
                                ],
                            },
                            {
                                # The HLS variant the fmp4 stream format needs.
                                "protocol_name": "http_hls",
                                "format": [
                                    {
                                        "format_name": "fmp4",
                                        "codec": [
                                            {
                                                "codec_name": "avc",
                                                "current_qn": 10000,
                                                "accept_qn": [10000, 400],
                                                "base_url": "/live.m3u8",
                                                "url_info": [
                                                    {
                                                        "host": self.base_url,
                                                        "extra": "?token=fake",
                                                    }
                                                ],
                                            }
                                        ],
                                    }
                                ],
                            },
                        ],
                    },
                },
            },
        }
        return web.json_response(data)

    def _flv_url_info(self) -> list[dict[str, str]]:
        """The CDN list for the FLV stream, dead host first when asked for."""
        live = {"host": self.base_url, "extra": "?token=fake"}
        if not self.fault.stream_dead_cdn_first:
            return [live]
        return [{"host": self.dead_url, "extra": "?token=fake"}, live]

    async def _handle_get_danmu_info(self, request: web.Request) -> web.Response:
        data: dict[str, Any] = {
            "code": 0,
            "message": "ok",
            "data": {
                "host_list": self._danmaku_host_list(),
                "token": "fake_danmaku_token",
            },
        }
        return web.json_response(data)

    def _danmaku_host_list(self) -> list[dict[str, Any]]:
        """The broadcast servers to advertise, dead one first when asked for.

        The client picks the TLS port; this server is plaintext, so it
        advertises its own port and the client's scheme follows it.
        """
        live = {
            "host": "127.0.0.1",
            "port": self.port,
            "wss_port": self.port,
            "ws_port": self.port,
        }
        if not self.fault.danmaku_dead_host_first:
            return [live]
        dead = {
            "host": "127.0.0.1",
            "port": _DEAD_PORT,
            "wss_port": _DEAD_PORT,
            "ws_port": _DEAD_PORT,
        }
        return [dead, live]

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

    def _build_stream_payload(self) -> bytes:
        """The bytes this request will serve, faults included."""
        payload = self.flv_data + generate_flv_tag_pairs(
            self.stream_extra_frames, start_frame=20
        )
        fault = self.fault
        if fault.stream_bad_tag_type:
            # After the header and a few good tags, so the recording has really
            # started before the bad byte arrives.
            cut = len(self.flv_data)
            payload = payload[:cut] + _make_bad_tag_type_tag() + payload[cut:]
        if fault.stream_garbage_at_byte is not None:
            cut = min(fault.stream_garbage_at_byte, len(payload))
            payload = payload[:cut] + b"\xff" * 8 + payload[cut:]
        if fault.stream_truncate_tail:
            # Half a tag, which is what a connection dying mid-write leaves.
            payload = payload[:-20]
        return payload

    async def _handle_stream(self, request: web.Request) -> web.StreamResponse:
        """Serve the FLV stream in small chunks, the way a CDN does.

        The chunking is the point: tags land split across writes, which is the
        shape of the data the parser actually has to cope with in production.
        """
        self.stream_requests += 1
        attempt = self.stream_requests
        resp = web.StreamResponse(
            status=200,
            headers={"Content-Type": "video/x-flv"},
        )
        await resp.prepare(request)

        if self.fault.stream_empty:
            await resp.write_eof()
            return resp

        fault = self.fault
        break_after = fault.stream_break_after_chunks
        breaks_this_time = (
            break_after is not None and attempt <= fault.stream_break_times
        )

        payload = self._build_stream_payload()
        written = 0
        try:
            for start in range(0, len(payload), self.stream_chunk_size):
                await resp.write(payload[start : start + self.stream_chunk_size])
                written += 1
                if (
                    breaks_this_time
                    and break_after is not None
                    and written >= break_after
                ):
                    # Cut the socket rather than closing it politely: an
                    # incomplete chunked body is what the client has to survive.
                    self._abort(request)
                    return resp
                await asyncio.sleep(self.stream_chunk_delay)
            await resp.write_eof()
        except (ConnectionResetError, asyncio.CancelledError):
            # The recorder hung up, which is exactly what stopping looks like.
            pass
        return resp

    @staticmethod
    def _abort(request: web.Request) -> None:
        """Drop the connection without finishing the response."""
        transport = request.transport
        if transport is not None:
            with contextlib.suppress(Exception):
                transport.abort()

    async def _handle_playlist(self, request: web.Request) -> web.Response:
        """Serve a live HLS playlist that advances a sliding window each poll."""
        self.playlist_requests += 1
        first = self._hls_media_sequence
        lines = [
            "#EXTM3U",
            "#EXT-X-VERSION:7",
            "#EXT-X-TARGETDURATION:1",
            f"#EXT-X-MEDIA-SEQUENCE:{first}",
            '#EXT-X-MAP:URI="/seg/init.mp4"',
        ]
        for i in range(first, first + 3):
            lines.append("#EXTINF:1.0,")
            lines.append(f"/seg/{i}.m4s")
        self._hls_media_sequence += 1
        return web.Response(
            text="\n".join(lines) + "\n",
            content_type="application/vnd.apple.mpegurl",
        )

    async def _handle_segment(self, request: web.Request) -> web.Response:
        """Serve an HLS segment: the init section, or a media segment."""
        self.segment_requests += 1
        name = request.match_info["name"]
        body = b"\x00\x00\x00\x18ftypiso5" if name == "init.mp4" else b"\x00" * 512
        return web.Response(body=body, content_type="video/mp4")

    async def _handle_ws_danmaku(self, request: web.Request) -> web.WebSocketResponse:
        """Broadcast endpoint speaking the real packet framing.

        The client will not consider itself connected until it has been through
        the handshake, so the fake has to answer the auth packet properly rather
        than just accepting the socket.
        """
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.ws_connections_total += 1
        faulty = self._ws_is_faulty()
        self.danmaku_ws_connections.append(ws)
        try:
            async for msg in ws:
                if msg.type != WSMsgType.BINARY:
                    continue
                for op, body in _decode_packets(msg.data):
                    if op == _OP_AUTH:
                        self.auth_payloads.append(body.decode("utf-8", "replace"))
                        if faulty and self.fault.ws_auth_fail_code is not None:
                            reply = json.dumps(
                                {
                                    "code": self.fault.ws_auth_fail_code,
                                    "message": "injected fault",
                                }
                            ).encode()
                            await ws.send_bytes(_encode_packet(_OP_AUTH_REPLY, reply))
                            await ws.close()
                            return ws
                        await ws.send_bytes(
                            _encode_packet(_OP_AUTH_REPLY, b'{"code":0}')
                        )
                        if faulty and self.fault.ws_close_after_auth:
                            await ws.close()
                            return ws
                    elif op == _OP_HEARTBEAT:
                        self.heartbeats_received += 1
                        if faulty and self.fault.ws_skip_heartbeat_reply:
                            continue
                        await ws.send_bytes(
                            _encode_packet(_OP_HEARTBEAT_REPLY, b"\x00\x00\x00\x01")
                        )
        finally:
            self.danmaku_ws_connections.remove(ws)
        return ws

    def _ws_is_faulty(self) -> bool:
        """Whether this connection is one of the ones meant to misbehave.

        ``ws_fault_first_only`` is how a test asks for a broken first attempt
        and a working reconnect, which is the interesting half of recovery.
        """
        if self.fault.ws_fault_first_only:
            return self.ws_connections_total == 1
        return True

    async def send_danmaku_command(self, cmd: str, data: dict[str, Any]) -> None:
        """Broadcast a danmaku command to all connected WS clients."""
        payload = json.dumps({"cmd": cmd, **data}).encode("utf-8")
        packet = _encode_packet(_OP_NOTIFICATION, payload)
        for ws in self.danmaku_ws_connections:
            await ws.send_bytes(packet)

    async def send_danmaku(self, text: str, *, uname: str = "Viewer") -> None:
        """Broadcast one ordinary danmaku message.

        The wire timestamp is in milliseconds and has to be roughly now: the
        dumper writes each message's offset from the start of the recording, so
        a fixed date in the past would land every line far outside the video.
        """
        await self.send_danmaku_command("DANMU_MSG", self._danmaku_body(text, uname))

    @staticmethod
    def _danmaku_body(text: str, uname: str) -> dict[str, Any]:
        return {
            "info": [
                [0, 1, 25, 0xFFFFFF, int(time.time() * 1000), 0, "", 0, 0, 0],
                text,
                [12345, uname, 0, 0, 0, 10000, 1, ""],
            ]
        }

    async def send_compressed_danmaku(
        self, text: str, *, proto: int = _PROTO_DEFLATE, uname: str = "Viewer"
    ) -> None:
        """Broadcast a danmaku inside a compressed envelope, as the API does.

        Bilibili wraps a whole inner packet (header included) in zlib or brotli
        and marks the outer header's protocol version accordingly. The client
        has to unwrap before it can read anything, so the compressed path is
        the one production actually uses.
        """
        payload = json.dumps(
            {"cmd": "DANMU_MSG", **self._danmaku_body(text, uname)}
        ).encode("utf-8")
        inner = _encode_packet(_OP_NOTIFICATION, payload)
        if proto == _PROTO_DEFLATE:
            body = zlib.compress(inner)
        elif proto == _PROTO_BROTLI:
            body = brotli.compress(inner)
        else:
            raise ValueError(f"Not a compressed protocol version: {proto}")
        packet = _HEADER.pack(len(body) + 16, 16, proto, _OP_NOTIFICATION, 1) + body
        for ws in self.danmaku_ws_connections:
            await ws.send_bytes(packet)

    async def send_malformed_packet(self) -> None:
        """Broadcast bytes that are not a packet, to be survived and ignored."""
        for ws in self.danmaku_ws_connections:
            await ws.send_bytes(b"\x00\x00\x00\x02\x00\x10")
