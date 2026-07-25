"""Integration tests for StreamRecorder FLV pipeline."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from birec.bili.models import LiveStatus, RoomInfo
from birec.core.metadata_provider import MetadataProvider
from birec.core.path_provider import PathProvider
from birec.core.stream_recorder import StreamRecorder


def _make_live() -> MagicMock:
    live = MagicMock()
    live.room_id = 12345
    live.get_stream_url = AsyncMock(return_value="https://cdn.example.com/live.flv")
    live.get_live_status = AsyncMock(return_value=LiveStatus.LIVE)
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


class TestStreamRecorderFlvPipeline:
    """Tests for StreamRecorder FLV pipeline integration."""

    @pytest.fixture
    def recorder(self, tmp_path: Path) -> StreamRecorder:
        live = _make_live()
        session = MagicMock()
        room = _make_room_info()
        pp = PathProvider(str(tmp_path), "{roomid}", room_info=room)
        mp = MetadataProvider(room_id=12345)
        return StreamRecorder(live, session, pp, mp)

    def test_create_flv_pipeline(
        self, recorder: StreamRecorder, tmp_path: Path
    ) -> None:
        """Test creating FLV pipeline returns a stream."""
        output = tmp_path / "output.flv"
        stream = recorder.create_flv_pipeline(output)
        assert stream is not None
        assert recorder.flv_progress is not None

    def test_flv_progress_initially_none(self, recorder: StreamRecorder) -> None:
        """Test flv_progress is None before pipeline creation."""
        assert recorder.flv_progress is None

    @pytest.mark.asyncio
    async def test_stop_recording_finalizes_pipeline(
        self, recorder: StreamRecorder, tmp_path: Path
    ) -> None:
        """Test that stop_recording cleans up FLV pipeline."""
        await recorder.start_recording()

        output = tmp_path / "test.flv"
        recorder.create_flv_pipeline(output)
        assert recorder.flv_progress is not None

        await recorder.stop_recording()
        assert recorder.flv_progress is None

    @pytest.mark.asyncio
    async def test_stop_recording_without_pipeline(
        self, recorder: StreamRecorder
    ) -> None:
        """Test stop_recording works without FLV pipeline."""
        await recorder.start_recording()
        await recorder.stop_recording()
        assert recorder.is_recording is False

    def test_feed_flv_data_no_pipeline(self, recorder: StreamRecorder) -> None:
        """Test feeding data without pipeline doesn't raise."""
        recorder.feed_flv_data(b"some data")  # Should not raise

    def test_complete_flv_pipeline_no_pipeline(self, recorder: StreamRecorder) -> None:
        """Test completing without pipeline doesn't raise."""
        recorder.complete_flv_pipeline()  # Should not raise

    def test_finalize_flv_pipeline_idempotent(
        self, recorder: StreamRecorder, tmp_path: Path
    ) -> None:
        """Test that finalizing pipeline multiple times is safe."""
        output = tmp_path / "output.flv"
        recorder.create_flv_pipeline(output)
        recorder._finalize_flv_pipeline()
        recorder._finalize_flv_pipeline()  # Should not raise
        assert recorder.flv_progress is None
