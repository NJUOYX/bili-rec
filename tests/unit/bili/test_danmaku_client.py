"""Unit tests for birec.bili.danmaku_client — DanmakuClient protocol & logic."""

from __future__ import annotations

import json
import struct
import zlib
from unittest.mock import AsyncMock, MagicMock

import brotli
import pytest

from birec.bili.danmaku_client import (
    _HEADER_SIZE,
    _HEADER_STRUCT,
    _OP_AUTH,
    _OP_AUTH_REPLY,
    _OP_HEARTBEAT,
    _OP_HEARTBEAT_REPLY,
    _OP_NOTIFICATION,
    _PROTO_BROTLI,
    _PROTO_DEFLATE,
    _PROTO_NORMAL,
    DanmakuClient,
    DanmakuClientListener,
)
from birec.bili.exceptions import DanmakuClientAuthError
from birec.bili.typing import Danmaku

pytestmark = pytest.mark.unit


def _make_client(
    room_id: int = 12345,
    cookie: str = "",
    user_agent: str = "",
) -> DanmakuClient:
    session = MagicMock()
    return DanmakuClient(room_id, session=session, cookie=cookie, user_agent=user_agent)


class _RecordingListener(DanmakuClientListener):
    def __init__(self) -> None:
        self.danmakus: list[Danmaku] = []
        self.connected_count = 0
        self.disconnected_count = 0

    def on_danmaku(self, danmaku: Danmaku) -> None:
        self.danmakus.append(danmaku)

    def on_danmaku_connected(self) -> None:
        self.connected_count += 1

    def on_danmaku_disconnected(self) -> None:
        self.disconnected_count += 1


class TestProtocolEncoding:
    def test_encode_packet_normal(self) -> None:
        body = b'{"test": true}'
        packet = DanmakuClient._encode_packet(_OP_AUTH, _PROTO_NORMAL, body)
        assert len(packet) == _HEADER_SIZE + len(body)

        total_len, header_len, ver, op, seq = _HEADER_STRUCT.unpack_from(packet, 0)
        assert total_len == _HEADER_SIZE + len(body)
        assert header_len == _HEADER_SIZE
        assert ver == _PROTO_NORMAL
        assert op == _OP_AUTH
        assert seq == 1
        assert packet[_HEADER_SIZE:] == body

    def test_encode_heartbeat_empty_body(self) -> None:
        packet = DanmakuClient._encode_packet(_OP_HEARTBEAT, _PROTO_NORMAL, b"")
        assert len(packet) == _HEADER_SIZE
        total_len, _, _, op, _ = _HEADER_STRUCT.unpack_from(packet, 0)
        assert total_len == _HEADER_SIZE
        assert op == _OP_HEARTBEAT


class TestProtocolDecoding:
    def test_decode_single_normal_packet(self) -> None:
        body = b'{"cmd": "DANMU_MSG"}'
        packet = DanmakuClient._encode_packet(_OP_NOTIFICATION, _PROTO_NORMAL, body)
        packets = DanmakuClient._decode_packets(packet)
        assert len(packets) == 1
        op, ver, decoded_body = packets[0]
        assert op == _OP_NOTIFICATION
        assert ver == _PROTO_NORMAL
        assert decoded_body == body

    def test_decode_multiple_packets(self) -> None:
        body1 = b'{"cmd": "DANMU_MSG"}'
        body2 = b'{"cmd": "SEND_GIFT"}'
        packet1 = DanmakuClient._encode_packet(_OP_NOTIFICATION, _PROTO_NORMAL, body1)
        packet2 = DanmakuClient._encode_packet(_OP_NOTIFICATION, _PROTO_NORMAL, body2)
        data = packet1 + packet2

        packets = DanmakuClient._decode_packets(data)
        assert len(packets) == 2
        assert packets[0][2] == body1
        assert packets[1][2] == body2

    def test_decode_deflate_packet(self) -> None:
        inner_body = b'{"cmd": "DANMU_MSG", "info": [1,2,3]}'
        inner_packet = DanmakuClient._encode_packet(
            _OP_NOTIFICATION, _PROTO_NORMAL, inner_body
        )
        compressed = zlib.compress(inner_packet)
        outer_packet = DanmakuClient._encode_packet(
            _OP_NOTIFICATION, _PROTO_DEFLATE, compressed
        )

        packets = DanmakuClient._decode_packets(outer_packet)
        assert len(packets) == 1
        assert packets[0][0] == _OP_NOTIFICATION
        assert packets[0][2] == inner_body

    def test_decode_brotli_packet(self) -> None:
        inner_body = b'{"cmd": "SUPER_CHAT_MESSAGE"}'
        inner_packet = DanmakuClient._encode_packet(
            _OP_NOTIFICATION, _PROTO_NORMAL, inner_body
        )
        compressed = brotli.compress(inner_packet)
        outer_packet = DanmakuClient._encode_packet(
            _OP_NOTIFICATION, _PROTO_BROTLI, compressed
        )

        packets = DanmakuClient._decode_packets(outer_packet)
        assert len(packets) == 1
        assert packets[0][0] == _OP_NOTIFICATION
        assert packets[0][2] == inner_body

    def test_decode_deflate_multiple_inner_packets(self) -> None:
        body1 = b'{"cmd": "DANMU_MSG"}'
        body2 = b'{"cmd": "SEND_GIFT"}'
        inner = DanmakuClient._encode_packet(
            _OP_NOTIFICATION, _PROTO_NORMAL, body1
        ) + DanmakuClient._encode_packet(_OP_NOTIFICATION, _PROTO_NORMAL, body2)
        compressed = zlib.compress(inner)
        outer = DanmakuClient._encode_packet(
            _OP_NOTIFICATION, _PROTO_DEFLATE, compressed
        )

        packets = DanmakuClient._decode_packets(outer)
        assert len(packets) == 2
        assert packets[0][2] == body1
        assert packets[1][2] == body2

    def test_decode_heartbeat_reply(self) -> None:
        # Heartbeat reply contains popularity count as 4-byte int
        popularity = struct.pack(">I", 12345)
        packet = DanmakuClient._encode_packet(
            _OP_HEARTBEAT_REPLY, _PROTO_NORMAL, popularity
        )
        packets = DanmakuClient._decode_packets(packet)
        assert len(packets) == 1
        assert packets[0][0] == _OP_HEARTBEAT_REPLY

    def test_decode_empty_data(self) -> None:
        packets = DanmakuClient._decode_packets(b"")
        assert packets == []

    def test_decode_truncated_header(self) -> None:
        packets = DanmakuClient._decode_packets(b"\x00" * 10)
        assert packets == []


class TestCookieParsing:
    def test_parse_uid_and_buvid(self) -> None:
        client = _make_client(
            cookie="DedeUserID=123456; buvid3=abc-def-ghi; SESSDATA=xyz"
        )
        assert client._uid == 123456
        assert client._buvid == "abc-def-ghi"

    def test_parse_empty_cookie(self) -> None:
        client = _make_client(cookie="")
        assert client._uid == 0
        assert client._buvid == ""

    def test_parse_no_uid(self) -> None:
        client = _make_client(cookie="buvid3=abc; SESSDATA=xyz")
        assert client._uid == 0
        assert client._buvid == "abc"

    def test_cookie_hot_swap(self) -> None:
        client = _make_client(cookie="DedeUserID=111")
        assert client._uid == 111
        client.cookie = "DedeUserID=222; buvid3=new-buvid"
        assert client._uid == 222
        assert client._buvid == "new-buvid"


class TestAuthPayload:
    def test_build_auth_payload(self) -> None:
        client = _make_client(
            room_id=99999,
            cookie="DedeUserID=123; buvid3=test-buvid",
        )
        client.set_danmu_info(["broadcastlv.chat.bilibili.com"], "my-token")
        payload = json.loads(client._build_auth_payload())

        assert payload["uid"] == 123
        assert payload["roomid"] == 99999
        assert payload["key"] == "my-token"
        assert payload["buvid"] == "test-buvid"
        assert payload["platform"] == "web"
        assert payload["protover"] == client._protocol_version

    def test_build_auth_payload_no_buvid(self) -> None:
        client = _make_client(room_id=11111, cookie="")
        client.set_danmu_info(["host1"], "token1")
        payload = json.loads(client._build_auth_payload())

        assert payload["uid"] == 0
        assert payload["roomid"] == 11111
        assert "buvid" not in payload


class TestMessageHandling:
    async def test_handle_notification_dispatches_danmaku(self) -> None:
        client = _make_client()
        listener = _RecordingListener()
        client.add_listener(listener)

        body = json.dumps({"cmd": "DANMU_MSG", "info": ["hello"]}).encode()
        await client._handle_notification(body)

        assert len(listener.danmakus) == 1
        assert listener.danmakus[0]["cmd"] == "DANMU_MSG"

    async def test_handle_notification_invalid_json(self) -> None:
        client = _make_client()
        listener = _RecordingListener()
        client.add_listener(listener)

        await client._handle_notification(b"not json{{{")
        assert len(listener.danmakus) == 0

    async def test_handle_binary_notification(self) -> None:
        client = _make_client()
        listener = _RecordingListener()
        client.add_listener(listener)

        body = json.dumps({"cmd": "SEND_GIFT"}).encode()
        packet = DanmakuClient._encode_packet(_OP_NOTIFICATION, _PROTO_NORMAL, body)
        await client._handle_binary(packet)

        assert len(listener.danmakus) == 1
        assert listener.danmakus[0]["cmd"] == "SEND_GIFT"

    async def test_handle_binary_heartbeat_reply_ignored(self) -> None:
        client = _make_client()
        listener = _RecordingListener()
        client.add_listener(listener)

        popularity = struct.pack(">I", 9999)
        packet = DanmakuClient._encode_packet(
            _OP_HEARTBEAT_REPLY, _PROTO_NORMAL, popularity
        )
        await client._handle_binary(packet)

        assert len(listener.danmakus) == 0


class TestAuthReply:
    async def test_auth_success(self) -> None:
        client = _make_client()
        auth_reply_body = json.dumps({"code": 0}).encode()
        auth_reply_packet = DanmakuClient._encode_packet(
            _OP_AUTH_REPLY, _PROTO_NORMAL, auth_reply_body
        )

        mock_ws = AsyncMock()
        mock_msg = MagicMock()
        mock_msg.type = 2  # BINARY
        mock_msg.data = auth_reply_packet
        mock_ws.receive = AsyncMock(return_value=mock_msg)
        client._ws = mock_ws

        await client._wait_auth_reply()  # Should not raise

    async def test_auth_failure(self) -> None:
        client = _make_client()
        auth_reply_body = json.dumps(
            {"code": -101, "message": "token expired"}
        ).encode()
        auth_reply_packet = DanmakuClient._encode_packet(
            _OP_AUTH_REPLY, _PROTO_NORMAL, auth_reply_body
        )

        mock_ws = AsyncMock()
        mock_msg = MagicMock()
        mock_msg.type = 2  # BINARY
        mock_msg.data = auth_reply_packet
        mock_ws.receive = AsyncMock(return_value=mock_msg)
        client._ws = mock_ws

        with pytest.raises(DanmakuClientAuthError, match="token expired"):
            await client._wait_auth_reply()

    async def test_auth_non_binary_reply(self) -> None:
        client = _make_client()
        mock_ws = AsyncMock()
        mock_msg = MagicMock()
        mock_msg.type = 1  # TEXT, not BINARY
        mock_ws.receive = AsyncMock(return_value=mock_msg)
        client._ws = mock_ws

        with pytest.raises(DanmakuClientAuthError, match="Expected binary"):
            await client._wait_auth_reply()


class TestBroadcastUrl:
    """The URL must follow what get_danmu_info advertised."""

    def test_the_default_is_the_tls_endpoint(self) -> None:
        client = _make_client()
        client.set_danmu_info(["broadcastlv.chat.bilibili.com"], "t")
        assert client._build_url(0) == "wss://broadcastlv.chat.bilibili.com/sub"

    def test_port_443_stays_on_tls(self) -> None:
        client = _make_client()
        client.set_danmu_info(["host.example"], "t", ports=[443])
        assert client._build_url(0) == "wss://host.example/sub"

    def test_another_port_is_honoured(self) -> None:
        """Regression: the port from the API used to be dropped on the floor.

        The URL was hardcoded to ``wss://{host}/sub``, so any endpoint not on
        443 was simply unreachable, whatever the API said.
        """
        client = _make_client()
        client.set_danmu_info(["127.0.0.1"], "t", ports=[8080])
        assert client._build_url(0) == "ws://127.0.0.1:8080/sub"

    def test_each_host_keeps_its_own_port(self) -> None:
        """Regression: rotating hosts used to carry the first host's port along.

        Only ``host_list[0]``'s port was kept, so the moment the client rotated
        away from the first host it aimed the next one's hostname at the previous
        one's port — an address nobody advertised. With the first host down, the
        rotation that exists to save the connection could never reach any of the
        others.
        """
        client = _make_client()
        client.set_danmu_info(["a.example", "b.example"], "t", ports=[8080, 9090])

        assert client._build_url(0) == "ws://a.example:8080/sub"
        assert client._build_url(1) == "ws://b.example:9090/sub"

    def test_a_host_without_a_stated_port_falls_back_to_tls(self) -> None:
        """A shorter port list must not make the extra hosts unusable."""
        client = _make_client()
        client.set_danmu_info(["a.example", "b.example"], "t", ports=[8080])

        assert client._build_url(1) == "wss://b.example/sub"


class TestConnectionState:
    def test_connected_false_initially(self) -> None:
        client = _make_client()
        assert client.connected is False

    def test_set_danmu_info(self) -> None:
        client = _make_client()
        client.set_danmu_info(["host1.com", "host2.com"], "token123")
        assert client._hosts == ["host1.com", "host2.com"]
        assert client._token == "token123"
        assert client._host_index == 0

    def test_protocol_version_default_brotli(self) -> None:
        client = _make_client()
        assert client._protocol_version == _PROTO_BROTLI

    def test_user_agent_property(self) -> None:
        client = _make_client(user_agent="TestUA/1.0")
        assert client.user_agent == "TestUA/1.0"
        client.user_agent = "NewUA/2.0"
        assert client.user_agent == "NewUA/2.0"
