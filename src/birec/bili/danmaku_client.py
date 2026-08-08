"""DanmakuClient: WebSocket long-connection for Bilibili live danmaku."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import struct
import zlib

import aiohttp
import brotli
from loguru import logger

from ..event.event_emitter import EventEmitter, EventListener
from ..utils.mixins import AsyncStoppableMixin
from .exceptions import DanmakuClientAuthError
from .typing import Danmaku

__all__ = ("DanmakuClient", "DanmakuClientListener")

# Protocol constants
_HEADER_SIZE = 16
_HEADER_STRUCT = struct.Struct(">IHHiI")  # total_len, header_len, ver, op, seq

# Operations
_OP_HEARTBEAT = 2
_OP_HEARTBEAT_REPLY = 3
_OP_NOTIFICATION = 5
_OP_AUTH = 7
_OP_AUTH_REPLY = 8

# Protocol versions
_PROTO_NORMAL = 0
_PROTO_DEFLATE = 2
_PROTO_BROTLI = 3

_HEARTBEAT_INTERVAL = 30  # seconds
_MAX_RETRIES = 60
_RETRY_BACKOFF_BASE = 1.0
_RETRY_BACKOFF_MAX = 60.0


class DanmakuClientListener(EventListener):
    """Interface for DanmakuClient event listeners."""

    def on_danmaku(self, danmaku: Danmaku) -> None: ...
    def on_danmaku_connected(self) -> None: ...
    def on_danmaku_disconnected(self) -> None: ...


class DanmakuClient(AsyncStoppableMixin, EventEmitter[DanmakuClientListener]):
    """WebSocket client for receiving live danmaku messages.

    Supports protocol versions: NORMAL(0), DEFLATE(2), BROTLI(3).
    Auto-reconnects with host rotation and exponential backoff.
    """

    def __init__(
        self,
        room_id: int,
        *,
        session: aiohttp.ClientSession,
        cookie: str = "",
        user_agent: str = "",
    ) -> None:
        AsyncStoppableMixin.__init__(self)
        EventEmitter.__init__(self)
        self._room_id = room_id
        self._logger = logger.bind(room_id=room_id)
        self._session = session
        self._cookie = cookie
        self._user_agent = user_agent

        # Danmaku server info
        self._hosts: list[str] = []
        self._token: str = ""
        self._host_index: int = 0
        self._ports: list[int] = []
        self._secure: list[bool] = []

        # Connection state
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._authenticated: bool = False
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._receive_task: asyncio.Task[None] | None = None
        self._retry_count: int = 0

        # Protocol version from env or default
        env_ver = os.environ.get("BIREC_DANMAKU_PROTOCOL_VERSION")
        self._protocol_version: int = int(env_ver) if env_ver else _PROTO_BROTLI

        # Parsed cookie info
        self._uid: int = 0
        self._buvid: str = ""
        self._parse_cookie()

    @property
    def room_id(self) -> int:
        return self._room_id

    @property
    def connected(self) -> bool:
        """Whether the socket is open *and* has been through the handshake.

        A socket the server accepted but refused to authenticate delivers
        nothing at all, so counting it as connected describes a room that looks
        fine and silently receives no danmaku for the rest of the broadcast.
        """
        return self._ws is not None and not self._ws.closed and self._authenticated

    # --- Cookie / UA hot-swap ---

    @property
    def cookie(self) -> str:
        return self._cookie

    @cookie.setter
    def cookie(self, value: str) -> None:
        if value != self._cookie:
            self._cookie = value
            self._parse_cookie()

    @property
    def user_agent(self) -> str:
        return self._user_agent

    @user_agent.setter
    def user_agent(self, value: str) -> None:
        self._user_agent = value

    def _parse_cookie(self) -> None:
        """Extract uid and buvid from cookie string."""
        self._uid = 0
        self._buvid = ""
        for part in self._cookie.split(";"):
            part = part.strip()
            if part.startswith("DedeUserID="):
                with contextlib.suppress(ValueError):
                    self._uid = int(part.split("=", 1)[1])
            elif part.startswith("buvid3="):
                self._buvid = part.split("=", 1)[1]

    # --- Danmaku server info ---

    def set_danmu_info(
        self,
        hosts: list[str],
        token: str,
        *,
        ports: list[int] | None = None,
        secure: list[bool] | None = None,
    ) -> None:
        """Set danmaku server hosts and auth token from get_danmu_info API.

        ``ports`` pairs up with ``hosts``: each broadcast server states its own
        port, and the two lists have to stay aligned, because rotating to the
        next host while keeping the previous host's port is a different address
        than the one advertised, and usually a dead one. ``secure`` pairs up
        with ``ports`` the same way and says whether that port is a TLS
        endpoint. The scheme follows the API field the port came from
        (``wss_port`` vs ``ws_port``), never the number itself (#43): the
        platform's TLS endpoint is not on 443 any more, so guessing TLS from
        the number aims a TLS port at a plaintext handshake. A port without a
        stated flag is treated as TLS, the safer of the two.
        """
        self._hosts = hosts
        self._token = token
        self._host_index = 0
        self._ports = list(ports) if ports else []
        self._secure = list(secure) if secure else []

    # --- AsyncStoppableMixin ---

    async def _do_start(self) -> None:
        self._retry_count = 0
        self._receive_task = asyncio.ensure_future(self._connection_loop())

    async def _do_stop(self) -> None:
        await self._close_connection()
        if self._receive_task is not None:
            self._receive_task.cancel()
            self._receive_task = None

    async def _close_connection(self) -> None:
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        self._ws = None
        self._authenticated = False

    # --- Connection Loop with Reconnect ---

    async def _connection_loop(self) -> None:
        """Main connection loop with auto-reconnect."""
        try:
            while not self.stopped:
                try:
                    await self._connect_and_receive()
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    self._logger.debug("Connection error: {}", repr(e))

                if self.stopped:
                    break

                # Reconnect with backoff
                self._retry_count += 1
                if self._retry_count > _MAX_RETRIES:
                    self._logger.error("Max retries exceeded, giving up")
                    break

                delay = min(
                    _RETRY_BACKOFF_BASE * (2 ** (self._retry_count - 1)),
                    _RETRY_BACKOFF_MAX,
                )
                self._logger.debug(
                    "Reconnecting in {:.1f}s (attempt {}/{})",
                    delay,
                    self._retry_count,
                    _MAX_RETRIES,
                )
                await asyncio.sleep(delay)

                # Rotate host
                if self._hosts:
                    self._host_index = (self._host_index + 1) % len(self._hosts)

        except asyncio.CancelledError:
            pass
        finally:
            await self._close_connection()

    def _build_url(self, index: int) -> str:
        """Build the broadcast WebSocket URL for the host at ``index``.

        The scheme follows the flag paired with that host's port — i.e. the
        API field the port came from — not the number itself (#43): a
        ``wss_port`` is the TLS endpoint even at 2245, and only a port
        advertised via ``ws_port`` is plaintext. A host that stated no port
        falls back to the TLS default endpoint.
        """
        host = self._hosts[index]
        if index >= len(self._ports):
            return f"wss://{host}/sub"
        port = self._ports[index]
        secure = self._secure[index] if index < len(self._secure) else True
        if not secure:
            return f"ws://{host}:{port}/sub"
        if port == 443:
            return f"wss://{host}/sub"
        return f"wss://{host}:{port}/sub"

    async def _connect_and_receive(self) -> None:
        """Establish WS connection, authenticate, and receive messages."""
        if not self._hosts:
            raise RuntimeError("No danmaku hosts configured")

        host = self._hosts[self._host_index]
        url = self._build_url(self._host_index)

        headers: dict[str, str] = {}
        if self._user_agent:
            headers["User-Agent"] = self._user_agent
        if self._cookie:
            headers["Cookie"] = self._cookie

        self._ws = await self._session.ws_connect(url, headers=headers)
        self._authenticated = False
        self._logger.debug("WebSocket connected to {}", host)

        # Send auth packet
        await self._send_auth()

        # Wait for auth reply
        await self._wait_auth_reply()

        # Connected successfully
        self._authenticated = True
        self._retry_count = 0
        await self._emit("danmaku_connected")

        # Start heartbeat
        self._heartbeat_task = asyncio.ensure_future(self._heartbeat_loop())

        # Receive loop
        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.BINARY:
                    await self._handle_binary(msg.data)
                elif msg.type in (
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.ERROR,
                ):
                    break
        finally:
            self._authenticated = False
            await self._emit("danmaku_disconnected")
            if self._heartbeat_task is not None:
                self._heartbeat_task.cancel()
                self._heartbeat_task = None

    # --- Auth ---

    def _build_auth_payload(self) -> bytes:
        """Build the JSON auth payload."""
        payload = {
            "uid": self._uid,
            "roomid": self._room_id,
            "protover": self._protocol_version,
            "platform": "web",
            "type": 2,
            "key": self._token,
        }
        if self._buvid:
            payload["buvid"] = self._buvid
        return json.dumps(payload).encode()

    async def _send_auth(self) -> None:
        """Send authentication packet."""
        body = self._build_auth_payload()
        packet = self._encode_packet(_OP_AUTH, _PROTO_NORMAL, body)
        assert self._ws is not None
        await self._ws.send_bytes(packet)

    async def _wait_auth_reply(self) -> None:
        """Wait for auth reply; raise on failure."""
        assert self._ws is not None
        msg = await self._ws.receive()
        if msg.type != aiohttp.WSMsgType.BINARY:
            raise DanmakuClientAuthError("Expected binary auth reply")

        packets = self._decode_packets(msg.data)
        for op, _ver, body in packets:
            if op == _OP_AUTH_REPLY:
                data = json.loads(body)
                if data.get("code", -1) != 0:
                    raise DanmakuClientAuthError(
                        f"Auth failed: {data.get('message', 'unknown')}"
                    )
                self._logger.debug("Auth successful")
                return
        raise DanmakuClientAuthError("No auth reply received")

    # --- Heartbeat ---

    async def _heartbeat_loop(self) -> None:
        """Send heartbeat every 30 seconds."""
        try:
            while not self.stopped and self.connected:
                packet = self._encode_packet(_OP_HEARTBEAT, _PROTO_NORMAL, b"")
                assert self._ws is not None
                await self._ws.send_bytes(packet)
                await asyncio.sleep(_HEARTBEAT_INTERVAL)
        except asyncio.CancelledError:
            pass

    # --- Message Handling ---

    async def _handle_binary(self, data: bytes) -> None:
        """Decode and dispatch binary WebSocket messages."""
        packets = self._decode_packets(data)
        for op, _ver, body in packets:
            if op == _OP_NOTIFICATION:
                await self._handle_notification(body)
            elif op == _OP_HEARTBEAT_REPLY:
                pass  # Popularity count, ignore

    async def _handle_notification(self, body: bytes) -> None:
        """Parse notification body and broadcast to listeners."""
        try:
            danmaku: Danmaku = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        await self._emit("danmaku", danmaku)

    # --- Protocol Encoding/Decoding ---

    @staticmethod
    def _encode_packet(op: int, ver: int, body: bytes) -> bytes:
        """Encode a packet with the 16-byte header."""
        total_len = _HEADER_SIZE + len(body)
        header = _HEADER_STRUCT.pack(total_len, _HEADER_SIZE, ver, op, 1)
        return header + body

    @staticmethod
    def _decode_packets(data: bytes) -> list[tuple[int, int, bytes]]:
        """Decode one or more packets from raw bytes.

        Returns list of (operation, version, body) tuples.
        Handles DEFLATE and BROTLI decompression recursively.
        """
        packets: list[tuple[int, int, bytes]] = []
        offset = 0

        while offset < len(data):
            if offset + _HEADER_SIZE > len(data):
                break

            total_len, header_len, ver, op, _seq = _HEADER_STRUCT.unpack_from(
                data, offset
            )
            body_start = offset + header_len
            body_end = offset + total_len
            body = data[body_start:body_end]
            offset = body_end

            if ver == _PROTO_DEFLATE:
                decompressed = zlib.decompress(body)
                packets.extend(DanmakuClient._decode_packets(decompressed))
            elif ver == _PROTO_BROTLI:
                decompressed = brotli.decompress(body)
                packets.extend(DanmakuClient._decode_packets(decompressed))
            else:
                packets.append((op, ver, body))

        return packets
