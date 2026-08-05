"""Unit tests for birec.bili.live_monitor — LiveMonitor state machine."""

from __future__ import annotations

import asyncio
import random
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
        self.lives: list[Live] = []

    def _record(self, event: str, live: Live) -> None:
        self.events.append(event)
        self.lives.append(live)

    def on_live_began(self, live: Live) -> None:
        self._record("live_began", live)

    def on_live_ended(self, live: Live) -> None:
        self._record("live_ended", live)

    def on_live_stream_available(self, live: Live) -> None:
        self._record("live_stream_available", live)

    def on_live_stream_reset(self, live: Live) -> None:
        self._record("live_stream_reset", live)

    def on_room_changed(self, live: Live) -> None:
        self._record("room_changed", live)


class TestLiveMonitorCommands:
    async def test_live_command_emits_began(self) -> None:
        monitor, live = _make_monitor()
        listener = _RecordingListener()
        monitor.add_listener(listener)
        monitor.enable()

        with patch.object(monitor, "_start_stream_poll"):
            await monitor.handle_command("LIVE")

        assert listener.events == ["live_began"]
        assert listener.lives == [live]
        assert monitor.is_living is True
        # A fresh broadcast has no confirmed stream yet.
        assert monitor.stream_available is False
        monitor.disable()

    async def test_preparing_command_emits_ended(self) -> None:
        monitor, live = _make_monitor()
        listener = _RecordingListener()
        monitor.add_listener(listener)
        monitor.enable()

        with patch.object(monitor, "_start_stream_poll"):
            await monitor.handle_command("LIVE")
        monitor._stream_available = True
        await monitor.handle_command("PREPARING")

        assert listener.events == ["live_began", "live_ended"]
        assert listener.lives == [live, live]
        assert monitor.is_living is False
        # Live ending also invalidates any previously confirmed stream.
        assert monitor.stream_available is False
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

        assert listener.events == ["live_began", "live_stream_reset"]
        assert listener.lives == [live, live]
        # The restarted stream must be re-confirmed from scratch.
        assert monitor.stream_available is False
        monitor.disable()

    async def test_room_change_command(self) -> None:
        monitor, live = _make_monitor()
        listener = _RecordingListener()
        monitor.add_listener(listener)
        monitor.enable()

        await monitor.handle_command("ROOM_CHANGE")

        assert listener.events == ["room_changed"]
        assert listener.lives == [live]
        monitor.disable()

    async def test_disabling_forgets_whether_the_room_was_live(self) -> None:
        """Regression (#17): a disabled monitor knows nothing, and must say so.

        ``_do_disable`` only cancelled its tasks, so the flag stayed true. The
        check that runs on enable exists precisely to catch a room that is
        already live, and it only fires when the monitor believes the room is
        *not* live — so its own stale flag stopped it, and restarting the monitor
        never picked a broadcast back up.
        """
        monitor, live = _make_monitor()
        monitor.enable()
        await monitor.handle_command("LIVE")
        assert monitor.is_living is True

        monitor.disable()

        assert monitor.is_living is False
        assert monitor.stream_available is False

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

        assert listener.events == ["live_stream_available"]
        assert listener.lives == [live]
        assert monitor.stream_available is True
        # The connectivity probe must target the URL that was resolved.
        m_conn.assert_called_once_with("https://example.com/stream.flv")
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

    async def test_stream_poll_runs_from_zero_elapsed(self) -> None:
        """The very first poll must happen: elapsed starts below the timeout."""
        monitor, live = _make_monitor()
        listener = _RecordingListener()
        monitor.add_listener(listener)
        monitor._is_living = True

        with (
            patch.object(live, "get_stream_url", new_callable=AsyncMock) as m_url,
            patch.object(live, "test_connectivity", new_callable=AsyncMock) as m_conn,
            patch("birec.bili.live_monitor._STREAM_POLL_TIMEOUT", 0.5),
            patch("birec.bili.live_monitor._STREAM_POLL_INTERVAL", 0.01),
        ):
            m_url.return_value = "https://example.com/stream.flv"
            m_conn.return_value = True
            await monitor._stream_poll_loop()

        assert listener.events == ["live_stream_available"]
        assert monitor.stream_available is True

    async def test_stream_poll_gives_up_when_not_living(self) -> None:
        """No broadcast, no polling: the loop must exit without probing."""
        monitor, live = _make_monitor()
        listener = _RecordingListener()
        monitor.add_listener(listener)
        monitor._is_living = False

        with (
            patch.object(live, "get_stream_url", new_callable=AsyncMock) as m_url,
            patch.object(live, "test_connectivity", new_callable=AsyncMock) as m_conn,
            patch("birec.bili.live_monitor._STREAM_POLL_TIMEOUT", 0.05),
            patch("birec.bili.live_monitor._STREAM_POLL_INTERVAL", 0.01),
        ):
            m_url.return_value = "https://example.com/stream.flv"
            m_conn.return_value = True
            await asyncio.wait_for(monitor._stream_poll_loop(), timeout=2.0)

        assert listener.events == []
        assert monitor.stream_available is False
        m_url.assert_not_called()

    async def test_stream_poll_iteration_count_at_timeout(self) -> None:
        """Polling stops once elapsed reaches the timeout: < not <=."""
        monitor, live = _make_monitor()
        monitor._is_living = True

        async def failing_get_url() -> str:
            raise Exception("No stream")

        with (
            patch.object(live, "get_stream_url", side_effect=failing_get_url) as m_url,
            patch("birec.bili.live_monitor._STREAM_POLL_TIMEOUT", 1.0),
            patch("birec.bili.live_monitor._STREAM_POLL_INTERVAL", 0.5),
        ):
            await asyncio.wait_for(monitor._stream_poll_loop(), timeout=3.0)

        # Iterations at elapsed 0 and 0.5 only; elapsed 1.0 is the boundary.
        assert m_url.call_count == 2
        assert monitor.stream_available is False

    async def test_stream_poll_keeps_trying_without_url(self) -> None:
        """A missing URL is retried until timeout, never reported as available."""
        monitor, live = _make_monitor()
        listener = _RecordingListener()
        monitor.add_listener(listener)
        monitor._is_living = True

        with (
            patch.object(live, "get_stream_url", new_callable=AsyncMock) as m_url,
            patch.object(live, "test_connectivity", new_callable=AsyncMock) as m_conn,
            patch("birec.bili.live_monitor._STREAM_POLL_TIMEOUT", 0.05),
            patch("birec.bili.live_monitor._STREAM_POLL_INTERVAL", 0.01),
        ):
            m_url.return_value = "https://example.com/stream.flv"
            m_conn.return_value = False
            await asyncio.wait_for(monitor._stream_poll_loop(), timeout=2.0)

        assert listener.events == []
        assert monitor.stream_available is False
        assert m_url.call_count >= 2

    async def test_stream_poll_no_probe_without_url(self) -> None:
        """Without a URL there is nothing to probe: short-circuit, keep waiting."""
        monitor, live = _make_monitor()
        listener = _RecordingListener()
        monitor.add_listener(listener)
        monitor._is_living = True

        with (
            patch.object(live, "get_stream_url", new_callable=AsyncMock) as m_url,
            patch.object(live, "test_connectivity", new_callable=AsyncMock) as m_conn,
            patch("birec.bili.live_monitor._STREAM_POLL_TIMEOUT", 0.05),
            patch("birec.bili.live_monitor._STREAM_POLL_INTERVAL", 0.01),
        ):
            m_url.return_value = None
            m_conn.return_value = True
            await asyncio.wait_for(monitor._stream_poll_loop(), timeout=2.0)

        assert listener.events == []
        assert monitor.stream_available is False
        m_conn.assert_not_called()

    async def test_stream_poll_loop_terminates_on_timeout(self) -> None:
        """Elapsed must actually accumulate, or the loop would poll forever."""
        monitor, live = _make_monitor()
        monitor._is_living = True

        async def failing_get_url() -> str:
            raise Exception("No stream")

        with (
            patch.object(live, "get_stream_url", side_effect=failing_get_url) as m_url,
            patch("birec.bili.live_monitor._STREAM_POLL_TIMEOUT", 0.05),
            patch("birec.bili.live_monitor._STREAM_POLL_INTERVAL", 0.01),
        ):
            await asyncio.wait_for(monitor._stream_poll_loop(), timeout=1.0)

        assert m_url.call_count >= 2
        assert monitor.stream_available is False


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
        assert monitor.stream_available is False
        assert listener.events == ["live_began"]
        assert listener.lives == [live]

    async def test_periodic_check_detects_ended(self) -> None:
        monitor, live = _make_monitor()
        listener = _RecordingListener()
        monitor.add_listener(listener)
        monitor._is_living = True
        monitor._stream_available = True

        with patch.object(live, "get_live_status", new_callable=AsyncMock) as m:
            m.return_value = LiveStatus.PREPARING
            await monitor._check_status()

        assert monitor.is_living is False
        assert monitor.stream_available is False
        assert listener.events == ["live_ended"]
        assert listener.lives == [live]

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

    async def test_periodic_loop_sleeps_interval_plus_jitter(self) -> None:
        """Each cycle waits the full interval ± jitter, then checks again."""
        monitor, live = _make_monitor()
        with patch.object(live, "get_live_status", new_callable=AsyncMock) as m_status:
            m_status.return_value = LiveStatus.PREPARING

            # Deterministic jitter: peek at the seeded value, then reseed so
            # the loop draws the same one.
            state = random.getstate()
            random.seed(1234)
            expected_jitter = random.uniform(-60, 60)
            random.seed(1234)
            try:
                sleep_calls: list[float] = []

                async def fake_sleep(delay: float) -> None:
                    sleep_calls.append(delay)
                    if len(sleep_calls) >= 2:
                        monitor._enabled = False

                monitor._enabled = True
                with (
                    patch("birec.bili.live_monitor._PERIODIC_CHECK_INTERVAL", 100),
                    patch("birec.bili.live_monitor.asyncio.sleep", new=fake_sleep),
                ):
                    await monitor._periodic_check_loop()
            finally:
                random.setstate(state)

        # One upfront check, then a re-check after each sleep.
        assert m_status.call_count == 2
        assert len(sleep_calls) == 2
        assert sleep_calls[0] == pytest.approx(100 + expected_jitter)


class TestCommandAndPollingInterleaving:
    """Two channels see the same transition; events must fire exactly once.

    The danmaku commands are the instant channel, the periodic poll the
    fallback. Both can report the same change — the state machine must not
    be seen to jitter when the second channel arrives late (#27).
    """

    async def test_polling_confirming_a_live_command_is_a_noop(self) -> None:
        monitor, live = _make_monitor()
        listener = _RecordingListener()
        monitor.add_listener(listener)
        monitor.enable()

        with (
            patch.object(live, "get_live_status", new_callable=AsyncMock) as m,
            patch.object(monitor, "_start_stream_poll"),
        ):
            await monitor.handle_command("LIVE")
            m.return_value = LiveStatus.LIVE
            await monitor._check_status()

        assert listener.events == ["live_began"]
        assert monitor.is_living is True
        monitor.disable()

    async def test_polling_confirming_a_preparing_command_is_a_noop(self) -> None:
        monitor, live = _make_monitor()
        listener = _RecordingListener()
        monitor.add_listener(listener)
        monitor.enable()

        with (
            patch.object(live, "get_live_status", new_callable=AsyncMock) as m,
            patch.object(monitor, "_start_stream_poll"),
        ):
            await monitor.handle_command("LIVE")
            await monitor.handle_command("PREPARING")
            m.return_value = LiveStatus.PREPARING
            await monitor._check_status()

        assert listener.events == ["live_began", "live_ended"]
        assert monitor.is_living is False
        monitor.disable()

    async def test_live_command_after_polling_began_is_a_stream_reset(self) -> None:
        """Once polling already reports the broadcast, a LIVE command can only
        mean the stream restarted — a room cannot begin the same broadcast
        twice, so no second ``live_began`` may come out of it.
        """
        monitor, live = _make_monitor()
        listener = _RecordingListener()
        monitor.add_listener(listener)
        monitor.enable()

        with (
            patch.object(live, "get_live_status", new_callable=AsyncMock) as m,
            patch.object(monitor, "_start_stream_poll"),
        ):
            m.return_value = LiveStatus.LIVE
            await monitor._check_status()
            await monitor.handle_command("LIVE")

        assert listener.events == ["live_began", "live_stream_reset"]
        monitor.disable()

    async def test_preparing_command_after_polling_ended_is_a_noop(self) -> None:
        monitor, live = _make_monitor()
        listener = _RecordingListener()
        monitor.add_listener(listener)
        monitor.enable()
        monitor._is_living = True

        with (
            patch.object(live, "get_live_status", new_callable=AsyncMock) as m,
            patch.object(monitor, "_start_stream_poll"),
        ):
            m.return_value = LiveStatus.PREPARING
            await monitor._check_status()
            await monitor.handle_command("PREPARING")

        assert listener.events == ["live_ended"]
        assert monitor.is_living is False
        monitor.disable()


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
        assert monitor.stream_available is False
        assert listener.events == ["live_began"]
        assert listener.lives == [live]

    async def test_repair_detects_ended(self) -> None:
        monitor, live = _make_monitor()
        listener = _RecordingListener()
        monitor.add_listener(listener)
        monitor._is_living = True
        monitor._stream_available = True

        with patch.object(live, "get_live_status", new_callable=AsyncMock) as m:
            m.return_value = LiveStatus.PREPARING
            await monitor.repair_state_on_reconnect()

        assert monitor.is_living is False
        assert monitor.stream_available is False
        assert listener.events == ["live_ended"]
        assert listener.lives == [live]

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


class TestLifecycle:
    async def test_fresh_monitor_state(self) -> None:
        monitor, live = _make_monitor()

        assert monitor.is_living is False
        assert monitor.stream_available is False
        assert monitor.enabled is False
        assert monitor._stream_poll_task is None
        assert monitor._periodic_check_task is None

    async def test_enable_starts_periodic_check_task(self) -> None:
        monitor, live = _make_monitor()
        with patch.object(monitor, "_periodic_check_loop", new=AsyncMock()):
            monitor.enable()
            assert monitor.enabled is True
            assert monitor._periodic_check_task is not None
            monitor.disable()

    async def test_disable_cancels_periodic_check_task(self) -> None:
        monitor, live = _make_monitor()

        async def wait_forever() -> None:
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                raise

        with patch.object(monitor, "_periodic_check_loop", side_effect=wait_forever):
            monitor.enable()
            task = monitor._periodic_check_task
            assert task is not None

            monitor.disable()

        await asyncio.sleep(0)
        assert monitor.enabled is False
        assert monitor._periodic_check_task is None
        assert task.cancelled() or task.done()

    async def test_disable_is_idempotent(self) -> None:
        monitor, live = _make_monitor()
        monitor.disable()
        monitor.disable()
        assert monitor.enabled is False

    async def test_enable_is_idempotent(self) -> None:
        monitor, live = _make_monitor()
        with patch.object(monitor, "_periodic_check_loop", new=AsyncMock()):
            monitor.enable()
            first = monitor._periodic_check_task
            monitor.enable()
            # Enabling twice must not spawn a second periodic task.
            assert monitor._periodic_check_task is first
            monitor.disable()

    async def test_live_command_starts_real_stream_poll(self) -> None:
        """A LIVE command must schedule a genuine poll task, not a no-op."""
        monitor, live = _make_monitor()
        listener = _RecordingListener()
        monitor.add_listener(listener)
        # Flip the flag directly: enable() would also start the periodic
        # check task, which is not what this test is about.
        monitor._enabled = True

        with (
            patch.object(live, "get_stream_url", new_callable=AsyncMock) as m_url,
            patch.object(live, "test_connectivity", new_callable=AsyncMock) as m_conn,
            patch("birec.bili.live_monitor._STREAM_POLL_INTERVAL", 0.01),
        ):
            m_url.return_value = "https://example.com/stream.flv"
            m_conn.return_value = True

            await monitor.handle_command("LIVE")
            assert monitor._stream_poll_task is not None
            # Let the real poll loop run to completion.
            await asyncio.sleep(0.05)

        assert monitor.stream_available is True
        assert "live_stream_available" in listener.events
        monitor.disable()

    async def test_preparing_cancels_stream_poll(self) -> None:
        monitor, live = _make_monitor()
        monitor.enable()
        monitor._is_living = True

        async def wait_forever() -> None:
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                raise

        poll_task = asyncio.ensure_future(wait_forever())
        monitor._stream_poll_task = poll_task

        await monitor.handle_command("PREPARING")
        await asyncio.sleep(0)

        assert monitor._stream_poll_task is None
        assert poll_task.cancelled() or poll_task.done()
        monitor.disable()

    async def test_start_stream_poll_replaces_running_poll(self) -> None:
        monitor, live = _make_monitor()
        monitor.enable()

        async def wait_forever() -> None:
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                raise

        with patch.object(monitor, "_stream_poll_loop", side_effect=wait_forever):
            monitor._start_stream_poll()
            first = monitor._stream_poll_task
            assert first is not None

            monitor._start_stream_poll()
            second = monitor._stream_poll_task
            assert second is not None
            assert second is not first
            await asyncio.sleep(0)
            assert first.cancelled() or first.done()

            monitor._cancel_stream_poll()
            assert monitor._stream_poll_task is None
        monitor.disable()

    async def test_cancel_tasks_clears_both_handles(self) -> None:
        monitor, live = _make_monitor()
        monitor.enable()

        async def wait_forever() -> None:
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                raise

        with patch.object(monitor, "_stream_poll_loop", side_effect=wait_forever):
            monitor._start_stream_poll()
            assert monitor._stream_poll_task is not None
            assert monitor._periodic_check_task is not None

            monitor._cancel_tasks()

            assert monitor._stream_poll_task is None
            assert monitor._periodic_check_task is None
        monitor.disable()
