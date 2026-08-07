"""Tests for the danmaku pipeline: client → receiver → dumper → file.

The individual pieces are covered in ``test_danmaku.py``; what matters here is
that they are actually connected, since a break anywhere in this chain silently
yields an empty danmaku file rather than an error.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from birec.bili.danmaku_client import DanmakuClient
from birec.bili.live import Live
from birec.bili.live_monitor import LiveMonitor, LiveMonitorListener
from birec.core.danmaku_dumper import DanmakuDumper
from birec.core.danmaku_receiver import DanmakuReceiver
from birec.core.raw_danmaku_dumper import RawDanmakuDumper
from birec.core.raw_danmaku_receiver import RawDanmakuReceiver

_DANMU_MSG = {
    "cmd": "DANMU_MSG",
    # [meta, content, user, ...]; meta[4] is a millisecond timestamp.
    "info": [[0, 1, 25, 16777215, 1700000000123, 0, 0, "0"], "hello", [42, "alice"]],
}
_SEND_GIFT = {
    "cmd": "SEND_GIFT",
    "data": {
        "uid": 7,
        "uname": "bob",
        "giftName": "辣条",
        "giftId": 1,
        "num": 2,
        "price": 100,
        "action": "投喂",
        "timestamp": 1700000001,
    },
}
_GUARD_BUY = {
    "cmd": "GUARD_BUY",
    "data": {
        "uid": 8,
        "username": "carol",
        "guard_level": 3,
        "num": 1,
        "price": 198000,
        "start_time": 1700000002,
    },
}
_SUPER_CHAT = {
    "cmd": "SUPER_CHAT_MESSAGE",
    "data": {
        "id": 99,
        "uid": 9,
        "price": 30,
        "message": "sc!",
        "start_time": 1700000003,
        "user_info": {"uname": "dave"},
    },
}


class TestDanmakuReceiverParsing:
    def test_parses_danmaku(self):
        r = DanmakuReceiver()
        r.on_danmaku(_DANMU_MSG)
        msg = r.get_nowait()
        assert msg is not None
        assert msg.type == "danmaku"
        assert msg.data.content == "hello"
        assert msg.data.uid == 42
        assert msg.data.uname == "alice"
        assert msg.data.timestamp == pytest.approx(1700000000.123)

    def test_parses_suffixed_danmaku_command(self):
        """Some rooms broadcast ``DANMU_MSG:4:0:2:2:2:0``."""
        r = DanmakuReceiver()
        r.on_danmaku({**_DANMU_MSG, "cmd": "DANMU_MSG:4:0:2:2:2:0"})
        msg = r.get_nowait()
        assert msg is not None
        assert msg.data.content == "hello"

    def test_parses_gift(self):
        r = DanmakuReceiver()
        r.on_danmaku(_SEND_GIFT)
        msg = r.get_nowait()
        assert msg is not None
        assert msg.type == "gift"
        assert msg.data.gift_name == "辣条"
        assert msg.data.num == 2

    def test_parses_guard_buy(self):
        r = DanmakuReceiver()
        r.on_danmaku(_GUARD_BUY)
        msg = r.get_nowait()
        assert msg is not None
        assert msg.type == "guard_buy"
        assert msg.data.uname == "carol"
        assert msg.data.guard_level == 3

    def test_parses_super_chat(self):
        r = DanmakuReceiver()
        r.on_danmaku(_SUPER_CHAT)
        msg = r.get_nowait()
        assert msg is not None
        assert msg.type == "super_chat"
        assert msg.data.uname == "dave"
        assert msg.data.price == 30
        assert msg.data.content == "sc!"

    def test_ignores_unrecorded_commands(self):
        r = DanmakuReceiver()
        r.on_danmaku({"cmd": "INTERACT_WORD", "data": {"uname": "eve"}})
        assert r.queue_size == 0

    def test_drops_malformed_payload(self):
        """The payload shape is not contractual, so it must not raise."""
        r = DanmakuReceiver()
        r.on_danmaku({"cmd": "DANMU_MSG", "info": []})
        r.on_danmaku({"cmd": "SEND_GIFT", "data": {}})
        assert r.queue_size == 0

    def test_raw_receiver_queues_verbatim(self):
        r = RawDanmakuReceiver()
        r.on_danmaku({"cmd": "INTERACT_WORD", "data": {"uname": "eve"}})
        assert r.get_nowait() == {"cmd": "INTERACT_WORD", "data": {"uname": "eve"}}


class TestClientToReceiver:
    @pytest.fixture
    def client(self):
        return DanmakuClient(12345, session=MagicMock())

    @pytest.mark.asyncio
    async def test_broadcast_reaches_receiver(self, client):
        receiver = DanmakuReceiver()
        client.add_listener(receiver)
        await client._handle_notification(json.dumps(_DANMU_MSG).encode())
        msg = receiver.get_nowait()
        assert msg is not None
        assert msg.data.content == "hello"

    @pytest.mark.asyncio
    async def test_broadcast_reaches_raw_receiver(self, client):
        raw = RawDanmakuReceiver()
        client.add_listener(raw)
        await client._handle_notification(json.dumps(_SEND_GIFT).encode())
        assert raw.get_nowait() == _SEND_GIFT


class TestDumperLifecycle:
    @pytest.mark.asyncio
    async def test_running_dumper_writes_incoming_danmaku(self, tmp_path):
        receiver = DanmakuReceiver()
        output = str(tmp_path / "d.xml")
        dumper = DanmakuDumper(receiver, output, flush_interval=0.01)
        await dumper.start()
        receiver.on_danmaku(_DANMU_MSG)
        await asyncio.sleep(0.05)
        # A dumper whose loop was awaited inside ``_do_start`` would deadlock
        # here, holding the lifecycle lock forever.
        await asyncio.wait_for(dumper.stop(), timeout=1)

        content = (tmp_path / "d.xml").read_text(encoding="utf-8")
        assert "<d p=" in content
        assert "hello" in content
        assert content.strip().endswith("</i>")
        assert dumper.written_count == 1

    @pytest.mark.asyncio
    async def test_stop_persists_queued_messages(self, tmp_path):
        """Messages queued but not yet consumed still belong in this file."""
        receiver = DanmakuReceiver()
        output = str(tmp_path / "d.xml")
        dumper = DanmakuDumper(receiver, output, flush_interval=60.0)
        await dumper.start()
        receiver.on_danmaku(_SUPER_CHAT)
        await dumper.stop()

        content = (tmp_path / "d.xml").read_text(encoding="utf-8")
        assert "<sc " in content
        assert "sc!" in content

    @pytest.mark.asyncio
    async def test_raw_dumper_writes_incoming_commands(self, tmp_path):
        receiver = RawDanmakuReceiver()
        output = str(tmp_path / "raw.jsonl")
        dumper = RawDanmakuDumper(receiver, output, flush_interval=0.01)
        await dumper.start()
        receiver.on_danmaku(_DANMU_MSG)
        await asyncio.sleep(0.05)
        await asyncio.wait_for(dumper.stop(), timeout=1)

        lines = (tmp_path / "raw.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["cmd"] == "DANMU_MSG"

    @pytest.mark.asyncio
    async def test_raw_stop_persists_queued_commands(self, tmp_path):
        receiver = RawDanmakuReceiver()
        output = str(tmp_path / "raw.jsonl")
        dumper = RawDanmakuDumper(receiver, output, flush_interval=60.0)
        await dumper.start()
        receiver.on_danmaku(_SEND_GIFT)
        await dumper.stop()

        lines = (tmp_path / "raw.jsonl").read_text(encoding="utf-8").splitlines()
        assert json.loads(lines[0])["cmd"] == "SEND_GIFT"


# ── live-status command forwarding (#27) ─────────────────────────────────────


class TestLiveCommandForwarding:
    """The receiver must hand LIVE/PREPARING/ROUND/ROOM_CHANGE to the handler.

    Before #27 these commands were dropped on the floor, so production learned
    about broadcasts beginning or ending from the periodic poll alone.
    """

    @pytest.mark.asyncio
    async def test_forwards_live_status_commands(self):
        seen: list[tuple[str, object]] = []

        async def handler(cmd: str, data: object) -> None:
            seen.append((cmd, data))

        r = DanmakuReceiver(live_command_handler=handler)
        for cmd in ("LIVE", "PREPARING", "ROUND", "ROOM_CHANGE"):
            r.on_danmaku({"cmd": cmd, "data": {"room_id": 12345}})
        await asyncio.sleep(0.01)

        assert seen == [
            ("LIVE", {"room_id": 12345}),
            ("PREPARING", {"room_id": 12345}),
            ("ROUND", {"room_id": 12345}),
            ("ROOM_CHANGE", {"room_id": 12345}),
        ]

    @pytest.mark.asyncio
    async def test_forwards_none_when_payload_is_missing_or_not_a_dict(self):
        seen: list[tuple[str, object]] = []

        async def handler(cmd: str, data: object) -> None:
            seen.append((cmd, data))

        r = DanmakuReceiver(live_command_handler=handler)
        r.on_danmaku({"cmd": "LIVE"})
        r.on_danmaku({"cmd": "PREPARING", "data": "odd"})
        await asyncio.sleep(0.01)

        assert seen == [("LIVE", None), ("PREPARING", None)]

    @pytest.mark.asyncio
    async def test_keeps_arrival_order(self):
        """The state machine must see the transitions in the order they aired."""
        seen: list[str] = []

        async def handler(cmd: str, data: object) -> None:
            seen.append(cmd)

        r = DanmakuReceiver(live_command_handler=handler)
        r.on_danmaku({"cmd": "LIVE"})
        r.on_danmaku({"cmd": "PREPARING"})
        r.on_danmaku({"cmd": "LIVE"})
        await asyncio.sleep(0.01)

        assert seen == ["LIVE", "PREPARING", "LIVE"]

    def test_no_handler_drops_the_commands_silently(self):
        """The old behaviour (drop) stays intact when nothing is wired."""
        r = DanmakuReceiver()
        r.on_danmaku({"cmd": "LIVE", "data": {}})
        r.on_danmaku({"cmd": "PREPARING", "data": {}})
        assert r.queue_size == 0

    @pytest.mark.asyncio
    async def test_live_commands_never_enter_the_record_queue(self):
        async def handler(cmd: str, data: object) -> None:
            pass

        r = DanmakuReceiver(live_command_handler=handler)
        r.on_danmaku({"cmd": "LIVE", "data": {}})
        await asyncio.sleep(0.01)
        assert r.queue_size == 0
        assert r.get_nowait() is None

    @pytest.mark.asyncio
    async def test_recordable_commands_are_not_forwarded(self):
        seen: list[str] = []

        async def handler(cmd: str, data: object) -> None:
            seen.append(cmd)

        r = DanmakuReceiver(live_command_handler=handler)
        r.on_danmaku(_DANMU_MSG)
        r.on_danmaku(_SEND_GIFT)
        await asyncio.sleep(0.01)

        assert seen == []
        # Still queued for the dumper as before.
        assert r.queue_size == 2

    @pytest.mark.asyncio
    async def test_handler_failure_does_not_break_the_receiver(self):
        calls: list[str] = []

        async def exploding(cmd: str, data: object) -> None:
            calls.append(cmd)
            raise RuntimeError("boom")

        r = DanmakuReceiver(live_command_handler=exploding)
        r.on_danmaku({"cmd": "LIVE"})
        r.on_danmaku({"cmd": "PREPARING"})
        await asyncio.sleep(0.01)

        # Both commands still reached the handler, and the receiver works on.
        assert calls == ["LIVE", "PREPARING"]
        r.on_danmaku(_DANMU_MSG)
        assert r.queue_size == 1


class _RecordingListener(LiveMonitorListener):
    """Collects the monitor's events so the tests can read the sequence."""

    def __init__(self) -> None:
        self.events: list[str] = []

    def on_live_began(self, live: Live) -> None:
        self.events.append("live_began")

    def on_live_ended(self, live: Live) -> None:
        self.events.append("live_ended")

    def on_live_stream_available(self, live: Live) -> None:
        self.events.append("live_stream_available")

    def on_live_stream_reset(self, live: Live) -> None:
        self.events.append("live_stream_reset")

    def on_room_changed(self, live: Live) -> None:
        self.events.append("room_changed")


def _make_wired_monitor() -> tuple[LiveMonitor, _RecordingListener, DanmakuReceiver]:
    """A real receiver whose live commands feed a real monitor."""
    live = Live(12345, session=MagicMock(), api_platform="web")
    monitor = LiveMonitor(live)
    listener = _RecordingListener()
    monitor.add_listener(listener)
    receiver = DanmakuReceiver(live_command_handler=monitor.handle_command)
    return monitor, listener, receiver


class TestLiveCommandsReachTheMonitor:
    """Receiver wired to a real LiveMonitor: the instant begin/end channel."""

    @pytest.mark.asyncio
    async def test_live_command_flips_the_monitor(self):
        monitor, listener, receiver = _make_wired_monitor()
        with (
            patch.object(monitor, "_periodic_check_loop", new=AsyncMock()),
            patch.object(monitor, "_start_stream_poll"),
        ):
            monitor.enable()
            receiver.on_danmaku({"cmd": "LIVE"})
            await asyncio.sleep(0.01)

        assert monitor.is_living is True
        assert listener.events == ["live_began"]
        monitor.disable()

    @pytest.mark.asyncio
    async def test_preparing_command_flips_it_back(self):
        monitor, listener, receiver = _make_wired_monitor()
        with (
            patch.object(monitor, "_periodic_check_loop", new=AsyncMock()),
            patch.object(monitor, "_start_stream_poll"),
        ):
            monitor.enable()
            receiver.on_danmaku({"cmd": "LIVE"})
            await asyncio.sleep(0.01)
            receiver.on_danmaku({"cmd": "PREPARING"})
            await asyncio.sleep(0.01)

        assert monitor.is_living is False
        assert listener.events == ["live_began", "live_ended"]
        monitor.disable()

    @pytest.mark.asyncio
    async def test_room_change_reaches_the_monitor(self):
        monitor, listener, receiver = _make_wired_monitor()
        with (
            patch.object(monitor, "_periodic_check_loop", new=AsyncMock()),
            # ROOM_CHANGE now pulls the fresh room info first (#40); against
            # the mocked session that would stall on retries.
            patch.object(monitor._live, "refresh", new_callable=AsyncMock),
        ):
            monitor.enable()
            receiver.on_danmaku({"cmd": "ROOM_CHANGE"})
            await asyncio.sleep(0.01)

        assert listener.events == ["room_changed"]
        monitor.disable()

    @pytest.mark.asyncio
    async def test_repeated_commands_do_not_duplicate_begin_or_end(self):
        """Commands and polling can both report a transition; the state machine
        must stay idempotent: began/ended fire on the flip only, never twice.
        """
        monitor, listener, receiver = _make_wired_monitor()
        with (
            patch.object(monitor, "_periodic_check_loop", new=AsyncMock()),
            patch.object(monitor, "_start_stream_poll"),
        ):
            monitor.enable()
            receiver.on_danmaku({"cmd": "LIVE"})
            await asyncio.sleep(0.01)
            # A second LIVE is a stream restart, not a second broadcast start.
            receiver.on_danmaku({"cmd": "LIVE"})
            await asyncio.sleep(0.01)
            receiver.on_danmaku({"cmd": "PREPARING"})
            await asyncio.sleep(0.01)
            # A second PREPARING is a no-op once the room already went dark.
            receiver.on_danmaku({"cmd": "PREPARING"})
            await asyncio.sleep(0.01)

        assert listener.events == ["live_began", "live_stream_reset", "live_ended"]
        assert monitor.is_living is False
        monitor.disable()
