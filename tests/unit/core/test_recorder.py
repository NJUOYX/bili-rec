"""Tests for core stream_recorder and recorder modules."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

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
