"""Unit tests for birec.bili.live_monitor — LiveMonitor state machine."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from birec.bili.live import Live
from birec.bili.live_monitor import LiveMonitor, LiveMonitorListener
from birec.bili.models import LiveStatus

pytestmark = pytest.mark.unit


def _make_monitor() -> tuple[LiveMonitor, Live]:
    session = MagicMock()
    live = Live(12345, session=session, api_platform="web")
    monitor = LiveMonitor(live)
    return monitor, live


class _RecordingListener(LiveMonitorListener):
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


class TestLiveMonitorCommands:
    async def test_live_command_emits_began(self) -> None:
        monitor, live = _make_monitor()
        listener = _RecordingListener()
        monitor.add_listener(listener)
        monitor.enable()

        with patch.object(monitor, "_start_stream_poll"):
            await monitor.handle_command("LIVE")

        assert "live_began" in listener.events
        assert monitor.is_living is True
        monitor.disable()

    async def test_preparing_command_emits_ended(self) -> None:
        monitor, live = _make_monitor()
        listener = _RecordingListener()
        monitor.add_listener(listener)
        monitor.enable()

        with patch.object(monitor, "_start_stream_poll"):
            await monitor.handle_command("LIVE")
        await monitor.handle_command("PREPARING")

        assert "live_ended" in listener.events
        assert monitor.is_living is False
        monitor.disable()

    async def test_round_command_emits_ended(self) -> None:
        monitor, live = _make_monitor()
        listener = _RecordingListener()
        monitor.add_listener(listener)
        monitor.enable()

        with patch.object(monitor, "_start_stream_poll"):
            await monitor.handle_command("LIVE")
        await monitor.handle_command("ROUND")

        assert "live_ended" in listener.events
        assert monitor.is_living is False
        monitor.disable()

    async def test_consecutive_live_emits_stream_reset(self) -> None:
        monitor, live = _make_monitor()
        listener = _RecordingListener()
        monitor.add_listener(listener)
        monitor.enable()

        with patch.object(monitor, "_start_stream_poll"):
            await monitor.handle_command("LIVE")
            await monitor.handle_command("LIVE")

        assert listener.events.count("live_began") == 1
        assert "live_stream_reset" in listener.events
        monitor.disable()

    async def test_room_change_command(self) -> None:
        monitor, live = _make_monitor()
        listener = _RecordingListener()
        monitor.add_listener(listener)
        monitor.enable()

        await monitor.handle_command("ROOM_CHANGE")

        assert "room_changed" in listener.events
        monitor.disable()

    async def test_disabled_monitor_ignores_commands(self) -> None:
        monitor, live = _make_monitor()
        listener = _RecordingListener()
        monitor.add_listener(listener)
        # Not enabled

        await monitor.handle_command("LIVE")

        assert listener.events == []
        assert monitor.is_living is False

    async def test_preparing_when_not_living_no_event(self) -> None:
        monitor, live = _make_monitor()
        listener = _RecordingListener()
        monitor.add_listener(listener)
        monitor.enable()

        await monitor.handle_command("PREPARING")

        assert listener.events == []
        monitor.disable()


class TestStreamPolling:
    async def test_stream_poll_success(self) -> None:
        monitor, live = _make_monitor()
        listener = _RecordingListener()
        monitor.add_listener(listener)
        monitor.enable()
        monitor._is_living = True

        with (
            patch.object(live, "get_stream_url", new_callable=AsyncMock) as m_url,
            patch.object(live, "test_connectivity", new_callable=AsyncMock) as m_conn,
        ):
            m_url.return_value = "https://example.com/stream.flv"
            m_conn.return_value = True

            # Run the poll loop directly
            await monitor._stream_poll_loop()

        assert "live_stream_available" in listener.events
        assert monitor.stream_available is True
        monitor.disable()

    async def test_stream_poll_retries_on_failure(self) -> None:
        monitor, live = _make_monitor()
        listener = _RecordingListener()
        monitor.add_listener(listener)
        monitor.enable()
        monitor._is_living = True

        call_count = 0

        async def mock_get_url() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("No stream")
            return "https://example.com/stream.flv"

        with (
            patch.object(live, "get_stream_url", side_effect=mock_get_url),
            patch.object(live, "test_connectivity", new_callable=AsyncMock) as m_conn,
            patch("birec.bili.live_monitor._STREAM_POLL_INTERVAL", 0.01),
        ):
            m_conn.return_value = True
            await monitor._stream_poll_loop()

        assert monitor.stream_available is True
        assert call_count == 3
        monitor.disable()


class TestPeriodicCheck:
    async def test_enable_checks_status_immediately(self) -> None:
        """A room already live when enabled must be detected without waiting.

        The danmaku server only pushes future transitions, so a task added
        mid-stream would otherwise look offline for a full check interval.
        """
        monitor, live = _make_monitor()
        listener = _RecordingListener()
        monitor.add_listener(listener)

        with (
            patch.object(live, "get_live_status", new_callable=AsyncMock) as m,
            patch.object(monitor, "_start_stream_poll"),
        ):
            m.return_value = LiveStatus.LIVE
            monitor.enable()
            await asyncio.sleep(0)  # let the check task run its first step
            await asyncio.sleep(0)

        assert monitor.is_living is True
        assert "live_began" in listener.events
        monitor.disable()

    async def test_periodic_check_detects_live(self) -> None:
        monitor, live = _make_monitor()
        listener = _RecordingListener()
        monitor.add_listener(listener)

        with (
            patch.object(live, "get_live_status", new_callable=AsyncMock) as m,
            patch.object(monitor, "_start_stream_poll"),
        ):
            m.return_value = LiveStatus.LIVE
            await monitor._check_status()

        assert monitor.is_living is True
        assert "live_began" in listener.events

    async def test_periodic_check_detects_ended(self) -> None:
        monitor, live = _make_monitor()
        listener = _RecordingListener()
        monitor.add_listener(listener)
        monitor._is_living = True

        with patch.object(live, "get_live_status", new_callable=AsyncMock) as m:
            m.return_value = LiveStatus.PREPARING
            await monitor._check_status()

        assert monitor.is_living is False
        assert "live_ended" in listener.events

    async def test_periodic_check_no_change(self) -> None:
        monitor, live = _make_monitor()
        listener = _RecordingListener()
        monitor.add_listener(listener)
        monitor._is_living = True

        with (
            patch.object(live, "get_live_status", new_callable=AsyncMock) as m,
            patch.object(monitor, "_start_stream_poll"),
        ):
            m.return_value = LiveStatus.LIVE
            await monitor._check_status()

        # No new events since already living
        assert listener.events == []


class TestReconnectRepair:
    async def test_repair_detects_live(self) -> None:
        monitor, live = _make_monitor()
        listener = _RecordingListener()
        monitor.add_listener(listener)

        with (
            patch.object(live, "get_live_status", new_callable=AsyncMock) as m,
            patch.object(monitor, "_start_stream_poll"),
        ):
            m.return_value = LiveStatus.LIVE
            await monitor.repair_state_on_reconnect()

        assert monitor.is_living is True
        assert "live_began" in listener.events

    async def test_repair_detects_ended(self) -> None:
        monitor, live = _make_monitor()
        listener = _RecordingListener()
        monitor.add_listener(listener)
        monitor._is_living = True

        with patch.object(live, "get_live_status", new_callable=AsyncMock) as m:
            m.return_value = LiveStatus.PREPARING
            await monitor.repair_state_on_reconnect()

        assert monitor.is_living is False
        assert "live_ended" in listener.events

    async def test_repair_already_living_starts_poll(self) -> None:
        monitor, live = _make_monitor()
        listener = _RecordingListener()
        monitor.add_listener(listener)
        monitor._is_living = True
        monitor._stream_available = False

        with (
            patch.object(live, "get_live_status", new_callable=AsyncMock) as m,
            patch.object(monitor, "_start_stream_poll") as m_poll,
        ):
            m.return_value = LiveStatus.LIVE
            await monitor.repair_state_on_reconnect()

        # Should not re-emit live_began, but should start poll
        assert "live_began" not in listener.events
        m_poll.assert_called_once()
