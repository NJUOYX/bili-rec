"""Integration tests for StreamRecorder FLV pipeline."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from birec.bili.models import LiveStatus, RoomInfo
from birec.core.metadata_provider import MetadataProvider
from birec.core.path_provider import PathProvider
from birec.core.stream_recorder import StreamRecorder
from birec.flv import (
    AVCPacketType,
    CodecID,
    FlvHeader,
    FlvWriter,
    FrameType,
    TagType,
    VideoTag,
)


def _make_flv_bytes() -> bytes:
    """Build a minimal valid FLV byte blob (header + one keyframe video tag)."""
    header = FlvHeader(signature="FLV", version=1, type_flag=0b0000_0101, data_offset=9)
    tag = VideoTag(
        offset=0,
        filtered=False,
        tag_type=TagType.VIDEO,
        data_size=15,
        timestamp=0,
        stream_id=0,
        frame_type=FrameType.KEY_FRAME,
        codec_id=CodecID.AVC,
        avc_packet_type=AVCPacketType.AVC_NALU,
        composition_time=0,
        body=b"\x00" * 10,
    )
    stream = BytesIO()
    writer = FlvWriter(stream)
    writer.write_header(header)
    writer.write_tags([tag])
    return stream.getvalue()


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

    def test_active_pipeline_flv(
        self, recorder: StreamRecorder, tmp_path: Path
    ) -> None:
        """Creating an FLV pipeline marks it active."""
        assert recorder.active_pipeline is None
        recorder.create_flv_pipeline(tmp_path / "out.flv")
        assert recorder.active_pipeline == "flv"

    def test_active_pipeline_hls(
        self, recorder: StreamRecorder, tmp_path: Path
    ) -> None:
        """Creating an HLS pipeline marks it active."""
        recorder.create_hls_pipeline(tmp_path / "out.m4s")
        assert recorder.active_pipeline == "hls"
        recorder.finalize_hls_pipeline()

    @pytest.mark.asyncio
    async def test_flv_bytes_to_disk(
        self, recorder: StreamRecorder, tmp_path: Path
    ) -> None:
        """Feed synthetic FLV bytes through the pipeline down to a file."""
        await recorder.start_recording()
        output = tmp_path / "recorded.flv"
        recorder.create_flv_pipeline(output)

        recorder.feed_flv_data(_make_flv_bytes())
        recorder.complete_flv_pipeline()

        assert output.exists()
        data = output.read_bytes()
        assert data[:3] == b"FLV"
        assert len(data) > 9  # header plus at least one tag
        await recorder.stop_recording()

    @pytest.mark.asyncio
    async def test_fmp4_segments_to_disk(
        self, recorder: StreamRecorder, tmp_path: Path
    ) -> None:
        """Feed synthetic fMP4 segments through the HLS pipeline to a file."""
        import zlib

        from birec.hls.models import HlsSegment
        from birec.hls.operators.segment_fetcher import FetchedSegment

        await recorder.start_recording()
        output = tmp_path / "recorded.m4s"
        recorder.create_hls_pipeline(output)
        assert recorder.active_pipeline == "hls"

        recorder.write_hls_init(b"init_data")
        seg = HlsSegment(uri="seg0.m4s", duration=4.0, sequence_number=0)
        payload = b"segment_payload"
        crc = zlib.crc32(payload) & 0xFFFFFFFF
        recorder.feed_hls_segment(FetchedSegment(segment=seg, data=payload, crc32=crc))

        await recorder.stop_recording()

        assert output.exists()
        assert output.read_bytes() == b"init_datasegment_payload"
        assert recorder.active_pipeline is None
        assert recorder.hls_segment_dumper is None

    @pytest.mark.asyncio
    async def test_stop_recording_finalizes_hls(
        self, recorder: StreamRecorder, tmp_path: Path
    ) -> None:
        """stop_recording must finalize an active HLS pipeline."""
        await recorder.start_recording()
        recorder.create_hls_pipeline(tmp_path / "out.m4s")
        assert recorder.hls_segment_dumper is not None

        await recorder.stop_recording()

        assert recorder.hls_segment_dumper is None
        assert recorder.active_pipeline is None

    @pytest.mark.asyncio
    async def test_active_pipeline_reset_on_start(
        self, recorder: StreamRecorder, tmp_path: Path
    ) -> None:
        """Starting a new recording resets the active pipeline marker."""
        recorder.create_flv_pipeline(tmp_path / "out.flv")
        assert recorder.active_pipeline == "flv"

        await recorder.start_recording()
        assert recorder.active_pipeline is None
