"""Tests for core stream_recorder and recorder modules."""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from birec.bili.live import Live
from birec.bili.live_monitor import LiveMonitor
from birec.bili.models import LiveStatus, RoomInfo, UserInfo
from birec.core.cover_downloader import CoverDownloader
from birec.core.danmaku_receiver import DanmakuReceiver
from birec.core.metadata_provider import MetadataProvider
from birec.core.path_provider import PathProvider
from birec.core.raw_danmaku_receiver import RawDanmakuReceiver
from birec.core.recorder import Recorder
from birec.core.stream_recorder import StreamRecorder


def _make_live() -> MagicMock:
    live = MagicMock()
    live.room_id = 12345
    live.room_info = _make_room_info()
    live.user_info = _make_user_info()
    live.get_stream_url = AsyncMock(return_value="https://cdn.example.com/live.flv")
    live.select_alternative = AsyncMock(
        return_value="https://cdn2.example.com/live.flv"
    )
    live.get_live_status = AsyncMock(return_value=LiveStatus.LIVE)
    live.test_connectivity = AsyncMock(return_value=True)
    live.check_room_state = AsyncMock()
    return live


def _make_room_info() -> RoomInfo:
    return RoomInfo(
        room_id=12345,
        short_room_id=0,
        area_id=1,
        title="Test Room",
        area_name="Game",
        parent_area_id=1,
        parent_area_name="Entertainment",
        live_status=LiveStatus.LIVE,
        live_start_time=0,
        online=1,
        cover="https://example.com/cover.jpg",
        tags="",
        description="",
        uid=99,
    )


def _make_user_info() -> UserInfo:
    return UserInfo(uid=99, name="Streamer", gender="male", face="")


class TestStreamRecorder:
    @pytest.fixture
    def recorder(self, tmp_path):
        live = _make_live()
        session = MagicMock()
        room = _make_room_info()
        pp = PathProvider(str(tmp_path), "{roomid}", room_info=room)
        mp = MetadataProvider(room_id=12345)
        return StreamRecorder(live, session, pp, mp)

    def test_initial_state(self, recorder):
        assert recorder.is_recording is False
        assert recorder.current_video_path == ""

    @pytest.mark.asyncio
    async def test_start_recording(self, recorder, tmp_path):
        segment = await recorder.start_recording()
        assert recorder.is_recording is True
        assert segment.video_path.endswith(".flv")
        assert "12345" in segment.video_path

    @pytest.mark.asyncio
    async def test_start_recording_reports_the_danmaku_files(self, recorder):
        """The paths a segment opens are what "recording began" is about."""
        recorder.setup_danmaku(DanmakuReceiver(), RawDanmakuReceiver())

        segment = await recorder.start_recording()

        assert segment.danmaku_path.endswith(".xml")
        assert segment.raw_danmaku_path.endswith(".jsonl")

    @pytest.mark.asyncio
    async def test_stop_recording(self, recorder):
        await recorder.start_recording()
        await recorder.stop_recording()
        assert recorder.is_recording is False

    @pytest.mark.asyncio
    async def test_stop_recording_when_not_started(self, recorder):
        assert await recorder.stop_recording() is None
        assert recorder.is_recording is False

    @pytest.mark.asyncio
    async def test_stop_recording_reports_the_danmaku_files(self, recorder):
        """Regression: the segment's danmaku paths must survive the teardown.

        They only live on the dumpers, which the same teardown drops, so read
        afterwards they come back empty and post-processing gets no XML to
        convert.
        """
        recorder.setup_danmaku(DanmakuReceiver(), RawDanmakuReceiver())
        await recorder.start_recording()

        segment = await recorder.stop_recording()

        assert segment is not None
        assert segment.video_path.endswith(".flv")
        assert segment.danmaku_path.endswith(".xml")
        assert segment.raw_danmaku_path.endswith(".jsonl")
        # The paths are now unreachable through the recorder itself.
        assert recorder.current_danmaku_path == ""

    @pytest.mark.asyncio
    async def test_stop_recording_without_danmaku_reports_video_only(self, recorder):
        await recorder.start_recording()

        segment = await recorder.stop_recording()

        assert segment is not None
        assert segment.video_path.endswith(".flv")
        assert segment.danmaku_path == ""
        assert segment.raw_danmaku_path == ""

    def test_setup_danmaku(self, recorder):
        dr = DanmakuReceiver()
        rdr = RawDanmakuReceiver()
        recorder.setup_danmaku(dr, rdr)
        assert recorder._danmaku_receiver is dr
        assert recorder._raw_danmaku_receiver is rdr

    def test_setup_cover_downloader(self, recorder):
        cd = MagicMock(spec=CoverDownloader)
        recorder.setup_cover_downloader(cd)
        assert recorder._cover_downloader is cd

    def test_format_size(self, recorder):
        assert recorder.format_size(500) == "500B"
        assert recorder.format_size(1500) == "1.5KB"
        assert recorder.format_size(1500000) == "1.4MB"
        assert recorder.format_size(1500000000) == "1.40GB"


class TestRecorder:
    @pytest.fixture
    def recorder(self, tmp_path):
        live = _make_live()
        monitor = MagicMock(spec=LiveMonitor)
        monitor.add_listener = MagicMock()
        monitor.remove_listener = MagicMock()
        session = MagicMock()
        pp = PathProvider(str(tmp_path), "{roomid}")
        return Recorder(
            room_id=12345,
            live=live,
            monitor=monitor,
            session=session,
            path_provider=pp,
        )

    def test_initial_state(self, recorder):
        assert recorder.room_id == 12345
        assert recorder.is_recording is False

    def test_update_info(self, recorder):
        room = _make_room_info()
        user = _make_user_info()
        recorder.update_info(room, user)
        # Should not raise

    @pytest.mark.asyncio
    async def test_on_live_started(self, recorder):
        recorder.on_live_began(recorder._live)
        await asyncio.sleep(0.01)  # Let task run
        assert recorder.is_recording is True

    @pytest.mark.asyncio
    async def test_on_live_began_creates_download_task(self, recorder):
        """Regression: start must create a _download_task (FLV download loop).

        Without this, is_recording can be True but no data actually flows.
        """
        recorder.on_live_began(recorder._live)
        await asyncio.sleep(0.05)  # Let _start_recording_async complete
        # The FLV impl must be instantiated
        assert recorder._flv_impl is not None
        assert recorder._flv_impl.running is True
        # A download asyncio.Task must be scheduled
        assert recorder._download_task is not None
        assert not recorder._download_task.done()
        await recorder.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_download_task(self, recorder):
        """stop() must cancel the download loop and await its cleanup."""
        recorder.on_live_began(recorder._live)
        await asyncio.sleep(0.05)
        assert recorder._download_task is not None
        await recorder.stop()
        # After stop, download task and impl must be cleaned
        assert recorder._download_task is None
        assert recorder._flv_impl is None

    @pytest.mark.asyncio
    async def test_on_live_began_refreshes_info(self, recorder, tmp_path):
        """Paths are rendered at recording start, so info must land first."""
        recorder._path_provider._path_template = "{roomid} - {uname}/rec"
        recorder.on_live_began(recorder._live)
        assert recorder._path_provider.render().startswith(
            f"{tmp_path}/12345 - Streamer/rec"
        )
        await recorder.stop()

    def test_on_room_changed_refreshes_info(self, recorder, tmp_path):
        """A renamed room/streamer must be reflected in later paths."""
        recorder._live.room_info = _make_room_info().model_copy(
            update={"room_id": 54321}
        )
        recorder._path_provider._path_template = "{roomid}/rec"
        recorder.on_room_changed(recorder._live)
        assert recorder._path_provider.render().startswith(f"{tmp_path}/54321/rec")

    def test_update_out_dir_moves_future_renders(self, recorder, tmp_path):
        """update_out_dir must hot-swap the base dir used by later renders."""
        recorder._path_provider._path_template = "rec"
        new_dir = tmp_path / "elsewhere"
        recorder.update_out_dir(str(new_dir))
        assert recorder._path_provider.out_dir == str(new_dir)
        assert recorder._path_provider.render() == f"{new_dir}/rec"

    @pytest.mark.asyncio
    async def test_on_live_started_idempotent(self, recorder):
        recorder.on_live_began(recorder._live)
        recorder.on_live_began(recorder._live)  # Should not start again
        await asyncio.sleep(0.01)
        assert recorder.is_recording is True

    @pytest.mark.asyncio
    async def test_on_live_ended(self, recorder):
        recorder.on_live_began(recorder._live)
        await asyncio.sleep(0.01)
        recorder.on_live_ended(recorder._live)
        await asyncio.sleep(0.01)
        assert recorder.is_recording is False

    @pytest.mark.asyncio
    async def test_on_live_ended_when_not_recording(self, recorder):
        recorder.on_live_ended(recorder._live)  # Should not raise
        assert recorder.is_recording is False

    @pytest.mark.asyncio
    async def test_stop(self, recorder):
        recorder.on_live_began(recorder._live)
        await asyncio.sleep(0.01)
        await recorder.stop()
        assert recorder.is_recording is False

    @pytest.mark.asyncio
    async def test_stop_recording_keeps_monitor_subscription(self, recorder):
        """Regression: switching recording off must not unsubscribe the recorder.

        ``stop()`` detaches from the monitor, which would make a later
        re-enable silently never record again.
        """
        recorder.on_live_began(recorder._live)
        await asyncio.sleep(0.05)

        await recorder.stop_recording()

        assert recorder.is_recording is False
        assert recorder._download_task is None
        assert recorder._flv_impl is None
        recorder._monitor.remove_listener.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_recording_settles_an_in_flight_start(self, recorder):
        """Stopping right after a live-start must not leave the loop running.

        ``on_live_began`` only schedules the start, so a stop arriving before it
        finishes used to tear down nothing and the download loop kept writing.
        """
        recorder.on_live_began(recorder._live)
        # Deliberately no sleep: _start_task has not run yet.
        await recorder.stop_recording()

        assert recorder.is_recording is False
        assert recorder._download_task is None
        assert recorder._flv_impl is None

    @pytest.mark.asyncio
    async def test_a_download_that_gives_up_finalizes_the_recording(
        self, recorder, monkeypatch
    ):
        """Regression: a loop out of retries must not leave the task 'recording'.

        The download loop stops after ten failed attempts, and nothing was
        watching for that. ``_is_recording`` stayed true, so the task went on
        reporting itself as recording for as long as the room stayed live, with
        the segment never closed, never post-processed, and not one byte being
        written. What the user saw and what was happening had nothing to do with
        each other.
        """
        monkeypatch.setattr(
            "birec.core.flv_stream_recorder_impl._RECONNECT_BASE_DELAY", 0.001
        )
        monkeypatch.setattr(
            "birec.core.flv_stream_recorder_impl._RECONNECT_MAX_DELAY", 0.001
        )
        segments = []
        recorder.set_segment_listener(segments.append)

        # The session is a mock, so every fetch fails and the loop burns through
        # its retry budget by itself, which is the situation under test.
        recorder.on_live_began(recorder._live)
        for _ in range(200):
            await asyncio.sleep(0.01)
            if not recorder.is_recording:
                break

        assert recorder.is_recording is False, (
            "the recorder still claims to be recording after the download gave up"
        )
        assert len(segments) == 1, "the abandoned segment was never handed over"

    @pytest.mark.asyncio
    async def test_a_stream_that_never_delivers_bytes_is_given_up_on(
        self, recorder, monkeypatch
    ):
        """Regression: an endpoint answering with an empty body is not forever.

        A connection ending cleanly is the ordinary end of a live stream, so the
        retry budget was reset every time one did. An endpoint that answers and
        immediately closes ends cleanly too, so it was retryable without limit:
        the task claimed to be recording a file that never grew past its header,
        for as long as the room stayed live.
        """
        monkeypatch.setattr(
            "birec.core.flv_stream_recorder_impl._RECONNECT_BASE_DELAY", 0.001
        )
        monkeypatch.setattr(
            "birec.core.flv_stream_recorder_impl._RECONNECT_MAX_DELAY", 0.001
        )
        monkeypatch.setattr(
            "birec.core.flv_stream_recorder_impl._STREAM_END_DELAY", 0.001
        )

        async def _nothing_at_all(_self, _url):
            """A fetch that succeeds and yields not a single chunk."""
            return
            yield b""  # pragma: no cover - makes this an async generator

        monkeypatch.setattr(
            "birec.core.operators.stream_fetcher.StreamFetcher.fetch", _nothing_at_all
        )
        segments = []
        recorder.set_segment_listener(segments.append)

        recorder.on_live_began(recorder._live)
        for _ in range(200):
            await asyncio.sleep(0.01)
            if not recorder.is_recording:
                break

        assert recorder.is_recording is False, (
            "an endpoint that never sends anything was retried without limit"
        )
        assert len(segments) == 1

    @pytest.mark.asyncio
    async def test_an_unparseable_stream_finalizes_the_recording(self, recorder):
        """Regression: a dead pipeline must not look like an ongoing recording.

        Reactivex delivers ``on_error`` once and tears the chain down, so after
        one unparseable byte nothing further is ever written. The error was only
        logged, so the file stopped growing while the task kept reporting itself
        as recording and the download kept burning bandwidth — the same silent
        loss as #9, from a third direction.
        """
        segments = []
        recorder.set_segment_listener(segments.append)
        recorder.on_live_began(recorder._live)
        await asyncio.sleep(0.05)
        assert recorder.is_recording is True

        recorder.stream_recorder.create_flv_pipeline(
            Path(recorder.stream_recorder.current_video_path)
        )
        recorder.stream_recorder.feed_flv_data(b"FLV\x01\x05\x00\x00\x00\x09")
        recorder.stream_recorder.feed_flv_data(b"\x00" * 32)
        await asyncio.sleep(0.05)

        assert recorder.is_recording is False
        assert len(segments) == 1

    @pytest.mark.asyncio
    async def test_segment_started_listener_gets_the_new_segment(self, recorder):
        """Regression: the start of a recording must be announced too.

        Only the recorder knows a segment has opened and which files it is
        writing to, and nothing asked it: the "recording began" events the
        notification module offers had no producer at all.
        """
        started = []
        recorder.set_segment_started_listener(started.append)

        recorder.on_live_began(recorder._live)
        await asyncio.sleep(0.05)

        assert len(started) == 1
        assert started[0].video_path.endswith(".flv")

    @pytest.mark.asyncio
    async def test_segment_started_listener_failure_does_not_stop_the_recording(
        self, recorder
    ):
        """A broken listener must not cost the user the recording itself."""

        def _boom(_segment):
            raise RuntimeError("listener exploded")

        recorder.set_segment_started_listener(_boom)

        recorder.on_live_began(recorder._live)
        await asyncio.sleep(0.05)

        assert recorder.is_recording is True
        assert recorder._flv_impl is not None

    @pytest.mark.asyncio
    async def test_segment_listener_gets_the_finished_segment(self, recorder):
        """Regression: a finished segment must be announced to post-processing.

        The recorder is the only place that knows a segment is complete and what
        it produced; without this callback nothing is ever remuxed or converted.
        """
        segments = []
        recorder.set_segment_listener(segments.append)

        recorder.on_live_began(recorder._live)
        await asyncio.sleep(0.05)
        await recorder.stop_recording()

        assert len(segments) == 1
        assert segments[0].video_path.endswith(".flv")

    @pytest.mark.asyncio
    async def test_segment_listener_failure_does_not_break_stop(self, recorder):
        """A broken listener must not leave the recording half torn down."""

        def _boom(_segment):
            raise RuntimeError("listener exploded")

        recorder.set_segment_listener(_boom)

        recorder.on_live_began(recorder._live)
        await asyncio.sleep(0.05)
        await recorder.stop_recording()

        assert recorder.is_recording is False
        assert recorder._flv_impl is None

    @pytest.mark.asyncio
    async def test_segment_listener_can_be_detached(self, recorder):
        segments = []
        recorder.set_segment_listener(segments.append)
        recorder.set_segment_listener(None)

        recorder.on_live_began(recorder._live)
        await asyncio.sleep(0.05)
        await recorder.stop_recording()

        assert segments == []

    def test_with_danmaku(self, tmp_path):
        live = _make_live()
        monitor = MagicMock(spec=LiveMonitor)
        monitor.add_listener = MagicMock()
        monitor.remove_listener = MagicMock()
        session = MagicMock()
        pp = PathProvider(str(tmp_path), "{roomid}")
        dr = DanmakuReceiver()
        recorder = Recorder(
            room_id=12345,
            live=live,
            monitor=monitor,
            session=session,
            path_provider=pp,
            danmaku_receiver=dr,
        )
        assert recorder.stream_recorder._danmaku_receiver is dr

    def test_on_live_stream_available_logs(self, recorder):
        """on_live_stream_available must log the room id."""
        with patch("birec.core.recorder.logger") as mock_logger:
            recorder.on_live_stream_available(recorder._live)
        mock_logger.debug.assert_called_once_with(
            "Room %d: stream URL available", 12345
        )

    def test_on_live_stream_reset_logs(self, recorder):
        """on_live_stream_reset must log the room id."""
        with patch("birec.core.recorder.logger") as mock_logger:
            recorder.on_live_stream_reset(recorder._live)
        mock_logger.debug.assert_called_once_with("Room %d: stream reset", 12345)

    def test_on_live_stream_available_does_not_change_state(self, recorder):
        """Stream-available is informational; recording state stays unchanged."""
        assert recorder.is_recording is False
        recorder.on_live_stream_available(recorder._live)
        assert recorder.is_recording is False

    def test_on_live_stream_reset_does_not_change_state(self, recorder):
        """Stream-reset is informational; recording state stays unchanged."""
        assert recorder.is_recording is False
        recorder.on_live_stream_reset(recorder._live)
        assert recorder.is_recording is False


def _info_payload(title: str, uname: str) -> dict:
    """A getInfoByRoom payload whose display fields are parameters."""
    return {
        "room_info": {
            "uid": 99,
            "room_id": 12345,
            "short_id": 0,
            "area_id": 1,
            "area_name": "Game",
            "parent_area_id": 1,
            "parent_area_name": "Entertainment",
            "live_status": 1,
            "live_start_time": 0,
            "online": 1,
            "title": title,
            "cover": "",
            "tags": "",
            "description": "",
        },
        "anchor_info": {
            "base_info": {
                "uname": uname,
                "gender": "",
                "face": "https://example.com/face.jpg",
            }
        },
    }


class TestRecorderRoomChangedWiring:
    """The recorder must subscribe to Live's room_changed (#40).

    A renamed room used to die on the vine: ``Live.refresh()`` stored the new
    info and stopped, so the recorder's ``on_room_changed`` never ran and the
    path provider kept rendering the old title/uname into every later session.
    These tests drive a real ``Live`` so the emission is exercised end to end.
    """

    @staticmethod
    def _build(tmp_path: Path) -> tuple[Recorder, PathProvider, Live]:
        live = Live(12345, session=MagicMock(), api_platform="web")
        monitor = LiveMonitor(live)
        pp = PathProvider(str(tmp_path), "{uname} - {title}")
        recorder = Recorder(
            room_id=12345,
            live=live,
            monitor=monitor,
            session=MagicMock(),
            path_provider=pp,
        )
        return recorder, pp, live

    @staticmethod
    async def _load(live: Live, title: str, uname: str) -> None:
        with (
            patch.object(live.api, "get_info_by_room", new_callable=AsyncMock) as m,
            patch.object(live.api, "get_room_play_infos", new_callable=AsyncMock) as m2,
        ):
            m.return_value = _info_payload(title, uname)
            m2.return_value = []
            await live.refresh()

    @pytest.mark.asyncio
    async def test_init_registers_as_room_changed_listener(self, tmp_path):
        recorder, _, live = self._build(tmp_path)
        assert recorder in live._listeners

    @pytest.mark.asyncio
    async def test_rename_renders_into_later_paths(self, tmp_path):
        recorder, pp, live = self._build(tmp_path)
        await self._load(live, "Old Title", "OldName")
        # The first load is what on_live_began would apply at broadcast start.
        recorder.update_info(live.room_info, live.user_info)
        assert pp.render() == str(tmp_path) + "/OldName - Old Title"

        await self._load(live, "New Title", "NewName")

        assert pp.render() == str(tmp_path) + "/NewName - New Title"
        await recorder.stop()

    @pytest.mark.asyncio
    async def test_stop_detaches_room_changed_listener(self, tmp_path):
        recorder, pp, live = self._build(tmp_path)
        await self._load(live, "Old Title", "OldName")
        recorder.update_info(live.room_info, live.user_info)
        await recorder.stop()

        await self._load(live, "New Title", "NewName")

        # Detached on stop: the rename no longer reaches the path provider.
        assert pp.render() == str(tmp_path) + "/OldName - Old Title"


class TestRecorderMutationKillers:
    """Targeted tests to kill surviving mutants in birec.core.recorder."""

    @pytest.fixture
    def recorder(self, tmp_path):
        live = _make_live()
        monitor = MagicMock(spec=LiveMonitor)
        monitor.add_listener = MagicMock()
        monitor.remove_listener = MagicMock()
        session = MagicMock()
        pp = PathProvider(str(tmp_path), "{roomid}")
        return Recorder(
            room_id=12345,
            live=live,
            monitor=monitor,
            session=session,
            path_provider=pp,
        )

    # ── __init__ mutants ──────────────────────────────────────────────

    def test_init_registers_as_monitor_listener(self, recorder):
        recorder._monitor.add_listener.assert_called_once_with(recorder)

    def test_init_statistics_is_fresh(self, recorder):
        assert recorder.statistics.dl_total == 0
        assert recorder.statistics.dl_rate == 0.0
        assert recorder.statistics.rec_elapsed == 0.0

    def test_init_internal_tasks_are_none(self, recorder):
        assert recorder._start_task is None
        assert recorder._stop_task is None
        assert recorder._download_task is None
        assert recorder._flv_impl is None
        assert recorder._cover_task is None

    def test_init_listeners_are_none(self, recorder):
        assert recorder._segment_listener is None
        assert recorder._segment_started_listener is None
        assert recorder._cover_listener is None

    # ── update_info mutants ───────────────────────────────────────────

    def test_update_info_delegates_to_path_provider(self, recorder):
        room = _make_room_info()
        user = _make_user_info()
        recorder.update_info(room, user)
        # Path provider should have the info now
        assert recorder._path_provider._room_info is room
        assert recorder._path_provider._user_info is user

    def test_update_info_delegates_to_metadata_provider(self, recorder):
        room = _make_room_info()
        user = _make_user_info()
        recorder.update_info(room, user)
        assert recorder._metadata_provider._room_info is room
        assert recorder._metadata_provider._user_info is user

    def test_update_info_with_none(self, recorder):
        recorder.update_info(None, None)
        assert recorder._path_provider._room_info is None

    # ── set_cover_listener mutants ────────────────────────────────────

    def test_set_cover_listener(self, recorder):
        cb = MagicMock()
        recorder.set_cover_listener(cb)
        assert recorder._cover_listener is cb

    def test_set_cover_listener_none(self, recorder):
        recorder.set_cover_listener(MagicMock())
        recorder.set_cover_listener(None)
        assert recorder._cover_listener is None

    # ── on_live_began mutants ─────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_on_live_began_resets_and_starts_statistics(self, recorder):
        recorder._statistics.update_dl(999)
        recorder.on_live_began(recorder._live)
        await asyncio.sleep(0.01)
        # Statistics must have been reset then started
        assert recorder._statistics.dl_total == 0
        assert recorder._statistics._start_time is not None
        await recorder.stop()

    @pytest.mark.asyncio
    async def test_on_live_began_updates_info_before_paths(self, recorder):
        recorder.on_live_began(recorder._live)
        await asyncio.sleep(0.01)
        # update_info was called with the live's room/user info
        assert recorder._path_provider._room_info is not None
        await recorder.stop()

    @pytest.mark.asyncio
    async def test_on_live_began_creates_start_task(self, recorder):
        recorder.on_live_began(recorder._live)
        assert recorder._start_task is not None
        await asyncio.sleep(0.05)
        assert recorder._start_task.done()
        await recorder.stop()

    # ── _on_start_done mutants ────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_on_start_done_cancelled_is_noop(self, recorder):
        recorder.on_live_began(recorder._live)
        task = recorder._start_task
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        # Recorder should still think it's recording (cancelled = ignored)
        assert recorder.is_recording is True
        await recorder.stop()

    @pytest.mark.asyncio
    async def test_on_start_done_exception_stops_recording(self, recorder):
        """If _start_recording_async raises, recording must be marked false."""
        recorder._stream_recorder.start_recording = AsyncMock(
            side_effect=RuntimeError("boom")
        )
        recorder.on_live_began(recorder._live)
        await asyncio.sleep(0.05)
        assert recorder.is_recording is False
        assert recorder._statistics._start_time is None

    # ── _on_download_done mutants ─────────────────────────────────────

    @pytest.mark.asyncio
    async def test_on_download_done_cancelled_is_noop(self, recorder):
        recorder.on_live_began(recorder._live)
        await asyncio.sleep(0.05)
        assert recorder._download_task is not None
        recorder._download_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await recorder._download_task
        await asyncio.sleep(0.01)
        # Cancelled download should not trigger stop
        await recorder.stop()

    @pytest.mark.asyncio
    async def test_on_download_done_not_recording_is_noop(self, recorder):
        """If recording already stopped, download done should not re-stop."""
        recorder.on_live_began(recorder._live)
        await asyncio.sleep(0.05)
        await recorder.stop_recording()
        # After stop_recording, _is_recording is False
        assert recorder.is_recording is False

    # ── on_live_ended mutants ─────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_on_live_ended_stops_statistics(self, recorder):
        recorder.on_live_began(recorder._live)
        await asyncio.sleep(0.05)
        assert recorder._statistics._start_time is not None
        recorder.on_live_ended(recorder._live)
        await asyncio.sleep(0.05)
        assert recorder.is_recording is False
        assert recorder._statistics._start_time is None

    @pytest.mark.asyncio
    async def test_on_live_ended_creates_stop_task(self, recorder):
        recorder.on_live_began(recorder._live)
        await asyncio.sleep(0.05)
        recorder.on_live_ended(recorder._live)
        assert recorder._stop_task is not None
        await asyncio.sleep(0.05)

    def test_on_live_ended_when_not_recording_is_noop(self, recorder):
        recorder.on_live_ended(recorder._live)
        assert recorder._stop_task is None

    # ── _stop_recording_async mutants ─────────────────────────────────

    @pytest.mark.asyncio
    async def test_stop_recording_async_cleans_up_all_tasks(self, recorder):
        recorder.on_live_began(recorder._live)
        await asyncio.sleep(0.05)
        assert recorder._flv_impl is not None
        assert recorder._download_task is not None

        recorder.on_live_ended(recorder._live)
        await asyncio.sleep(0.1)

        assert recorder._flv_impl is None
        assert recorder._download_task is None
        assert recorder._cover_task is None

    @pytest.mark.asyncio
    async def test_stop_recording_async_notifies_segment_listener(self, recorder):
        segments = []
        recorder.set_segment_listener(segments.append)
        recorder.on_live_began(recorder._live)
        await asyncio.sleep(0.05)
        recorder.on_live_ended(recorder._live)
        await asyncio.sleep(0.1)
        assert len(segments) == 1
        assert segments[0].video_path.endswith(".flv")

    # ── _download_cover_async mutants ─────────────────────────────────

    @pytest.mark.asyncio
    async def test_download_cover_no_room_info(self, recorder):
        recorder._live.room_info = None
        recorder.set_cover_listener(MagicMock())
        await recorder._download_cover_async()
        recorder._cover_listener.assert_not_called()

    @pytest.mark.asyncio
    async def test_download_cover_empty_cover_url(self, recorder):
        recorder._live.room_info = _make_room_info().model_copy(update={"cover": ""})
        recorder.set_cover_listener(MagicMock())
        await recorder._download_cover_async()
        recorder._cover_listener.assert_not_called()

    @pytest.mark.asyncio
    async def test_download_cover_success_calls_listener(self, recorder):
        recorder._live.room_info = _make_room_info()
        recorder._stream_recorder.download_cover = AsyncMock(
            return_value="/tmp/cover.jpg"
        )
        listener = MagicMock()
        recorder.set_cover_listener(listener)
        await recorder._download_cover_async()
        listener.assert_called_once_with("/tmp/cover.jpg")

    @pytest.mark.asyncio
    async def test_download_cover_no_listener(self, recorder):
        recorder._live.room_info = _make_room_info()
        recorder._stream_recorder.download_cover = AsyncMock(
            return_value="/tmp/cover.jpg"
        )
        recorder.set_cover_listener(None)
        # Should not raise
        await recorder._download_cover_async()

    @pytest.mark.asyncio
    async def test_download_cover_exception_is_swallowed(self, recorder):
        recorder._live.room_info = _make_room_info()
        recorder._stream_recorder.download_cover = AsyncMock(
            side_effect=OSError("network down")
        )
        listener = MagicMock()
        recorder.set_cover_listener(listener)
        await recorder._download_cover_async()
        listener.assert_not_called()

    @pytest.mark.asyncio
    async def test_download_cover_listener_exception_is_swallowed(self, recorder):
        recorder._live.room_info = _make_room_info()
        recorder._stream_recorder.download_cover = AsyncMock(
            return_value="/tmp/cover.jpg"
        )

        def _boom(_path):
            raise RuntimeError("listener exploded")

        recorder.set_cover_listener(_boom)
        # Should not raise
        await recorder._download_cover_async()

    @pytest.mark.asyncio
    async def test_download_cover_returns_none_path(self, recorder):
        recorder._live.room_info = _make_room_info()
        recorder._stream_recorder.download_cover = AsyncMock(return_value="")
        listener = MagicMock()
        recorder.set_cover_listener(listener)
        await recorder._download_cover_async()
        listener.assert_not_called()

    # ── _notify_segment_started mutants ───────────────────────────────

    def test_notify_segment_started_no_listener(self, recorder):
        from birec.core.models import StartedSegment

        seg = StartedSegment(video_path="/tmp/a.flv")
        recorder.set_segment_started_listener(None)
        # Should not raise
        recorder._notify_segment_started(seg)

    def test_notify_segment_started_listener_exception_swallowed(self, recorder):
        from birec.core.models import StartedSegment

        seg = StartedSegment(video_path="/tmp/a.flv")

        def _boom(_s):
            raise ValueError("oops")

        recorder.set_segment_started_listener(_boom)
        # Should not raise
        recorder._notify_segment_started(seg)

    # ── _notify_segment_completed mutants ─────────────────────────────

    def test_notify_segment_completed_no_listener(self, recorder):
        from birec.core.models import CompletedSegment

        seg = CompletedSegment(video_path="/tmp/a.flv")
        recorder.set_segment_listener(None)
        recorder._notify_segment_completed(seg)

    def test_notify_segment_completed_listener_exception_swallowed(self, recorder):
        from birec.core.models import CompletedSegment

        seg = CompletedSegment(video_path="/tmp/a.flv")

        def _boom(_s):
            raise ValueError("oops")

        recorder.set_segment_listener(_boom)
        recorder._notify_segment_completed(seg)

    # ── _on_stop_done mutants ─────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_on_stop_done_cancelled_is_noop(self, recorder):
        recorder.on_live_began(recorder._live)
        await asyncio.sleep(0.05)
        recorder.on_live_ended(recorder._live)
        await asyncio.sleep(0.01)
        # If stop task exists, cancel it
        if recorder._stop_task and not recorder._stop_task.done():
            recorder._stop_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await recorder._stop_task

    @pytest.mark.asyncio
    async def test_on_stop_done_exception_is_logged(self, recorder):
        recorder.on_live_began(recorder._live)
        await asyncio.sleep(0.05)
        # Make stop_recording raise
        recorder._stream_recorder.stop_recording = AsyncMock(
            side_effect=RuntimeError("stop failed")
        )
        recorder.on_live_ended(recorder._live)
        await asyncio.sleep(0.1)
        # Should not crash the event loop; exception is logged
        assert recorder.is_recording is False

    # ── on_room_changed mutants ───────────────────────────────────────

    def test_on_room_changed_calls_update_info(self, recorder):
        room = _make_room_info()
        user = _make_user_info()
        recorder._live.room_info = room
        recorder._live.user_info = user
        recorder.on_room_changed(recorder._live)
        assert recorder._path_provider._room_info is room
        assert recorder._metadata_provider._user_info is user

    # ── _on_pipeline_failure mutants ──────────────────────────────────

    @pytest.mark.asyncio
    async def test_on_pipeline_failure_stops_recording(self, recorder):
        recorder.on_live_began(recorder._live)
        await asyncio.sleep(0.05)
        assert recorder.is_recording is True
        recorder._on_pipeline_failure(RuntimeError("corrupt"))
        await asyncio.sleep(0.1)
        assert recorder.is_recording is False
        assert recorder._statistics._start_time is None

    def test_on_pipeline_failure_not_recording_is_noop(self, recorder):
        recorder._on_pipeline_failure(RuntimeError("corrupt"))
        assert recorder._stop_task is None

    # ── stop_recording mutants ────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_stop_recording_stops_statistics(self, recorder):
        recorder.on_live_began(recorder._live)
        await asyncio.sleep(0.05)
        assert recorder._statistics._start_time is not None
        await recorder.stop_recording()
        assert recorder._statistics._start_time is None
        assert recorder.is_recording is False

    @pytest.mark.asyncio
    async def test_stop_recording_awaits_pending_stop_task(self, recorder):
        """If a stop task is in flight, stop_recording awaits it."""
        recorder.on_live_began(recorder._live)
        await asyncio.sleep(0.05)
        recorder.on_live_ended(recorder._live)
        # Immediately call stop_recording while stop_task may be running
        await recorder.stop_recording()
        assert recorder.is_recording is False

    # ── stop mutants ──────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_stop_removes_listener_from_monitor(self, recorder):
        recorder.on_live_began(recorder._live)
        await asyncio.sleep(0.05)
        await recorder.stop()
        recorder._monitor.remove_listener.assert_called_with(recorder)
