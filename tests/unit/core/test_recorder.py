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
        path = await recorder.start_recording()
        assert recorder.is_recording is True
        assert path.endswith(".flv")
        assert "12345" in path

    @pytest.mark.asyncio
    async def test_stop_recording(self, recorder):
        await recorder.start_recording()
        await recorder.stop_recording()
        assert recorder.is_recording is False

    @pytest.mark.asyncio
    async def test_stop_recording_when_not_started(self, recorder):
        await recorder.stop_recording()  # Should not raise
        assert recorder.is_recording is False

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
