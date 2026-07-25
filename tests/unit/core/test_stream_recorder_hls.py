"""Tests for StreamRecorder HLS pipeline integration."""

from __future__ import annotations

import zlib
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from birec.core.stream_recorder import StreamRecorder
from birec.hls.models import HlsPlaylist, HlsSegment, InitSegment
from birec.hls.operators.segment_fetcher import FetchedSegment

pytestmark = pytest.mark.unit


def _make_segment(seq: int, duration: float = 4.0) -> HlsSegment:
    return HlsSegment(uri=f"seg{seq}.m4s", duration=duration, sequence_number=seq)


def _make_playlist(
    segments: list[HlsSegment],
    media_sequence: int = 0,
) -> HlsPlaylist:
    return HlsPlaylist(
        media_sequence=media_sequence,
        segments=tuple(segments),
        init_segment=InitSegment(uri="init.mp4"),
        raw_text="#EXTM3U\n",
    )


def _make_fetched(seq: int, data: bytes = b"fake_data") -> FetchedSegment:
    seg = _make_segment(seq)
    crc = zlib.crc32(data) & 0xFFFFFFFF
    return FetchedSegment(segment=seg, data=data, crc32=crc)


@pytest.fixture
def stream_recorder() -> StreamRecorder:
    """Create a StreamRecorder with mocked dependencies."""
    live = MagicMock()
    session = MagicMock()
    path_provider = MagicMock()
    metadata_provider = MagicMock()
    return StreamRecorder(
        live=live,
        session=session,
        path_provider=path_provider,
        metadata_provider=metadata_provider,
    )


class TestStreamRecorderHlsPipeline:
    """Tests for StreamRecorder HLS pipeline integration."""

    def test_create_hls_pipeline(
        self, stream_recorder: StreamRecorder, tmp_path: Path
    ) -> None:
        output = tmp_path / "output.m4s"
        stream_recorder.create_hls_pipeline(output, "https://cdn.example.com")

        assert stream_recorder.hls_segment_dumper is not None
        assert stream_recorder.hls_analyser is not None
        assert stream_recorder.hls_fetcher is not None

        stream_recorder.finalize_hls_pipeline()

    def test_feed_hls_playlist(
        self, stream_recorder: StreamRecorder, tmp_path: Path
    ) -> None:
        output = tmp_path / "output.m4s"
        stream_recorder.create_hls_pipeline(output)

        pl = _make_playlist([_make_segment(0), _make_segment(1)])
        new_segments = stream_recorder.feed_hls_playlist(pl)

        assert len(new_segments) == 2
        assert new_segments[0].sequence_number == 0
        assert new_segments[1].sequence_number == 1

        stream_recorder.finalize_hls_pipeline()

    def test_feed_hls_playlist_incremental(
        self, stream_recorder: StreamRecorder, tmp_path: Path
    ) -> None:
        output = tmp_path / "output.m4s"
        stream_recorder.create_hls_pipeline(output)

        pl1 = _make_playlist([_make_segment(0), _make_segment(1)])
        new1 = stream_recorder.feed_hls_playlist(pl1)
        assert len(new1) == 2

        pl2 = _make_playlist([_make_segment(1), _make_segment(2)])
        new2 = stream_recorder.feed_hls_playlist(pl2)
        assert len(new2) == 1
        assert new2[0].sequence_number == 2

        stream_recorder.finalize_hls_pipeline()

    def test_feed_hls_segment(
        self, stream_recorder: StreamRecorder, tmp_path: Path
    ) -> None:
        output = tmp_path / "output.m4s"
        stream_recorder.create_hls_pipeline(output)

        fetched = _make_fetched(0, b"segment_data")
        stream_recorder.feed_hls_segment(fetched)

        analyser = stream_recorder.hls_analyser
        assert analyser is not None
        meta = analyser.get_metadata()
        assert meta.segment_count == 1
        assert meta.total_size == 12

        stream_recorder.finalize_hls_pipeline()
        assert output.read_bytes() == b"segment_data"

    def test_write_hls_init(
        self, stream_recorder: StreamRecorder, tmp_path: Path
    ) -> None:
        output = tmp_path / "output.m4s"
        stream_recorder.create_hls_pipeline(output)

        stream_recorder.write_hls_init(b"init_data")
        stream_recorder.feed_hls_segment(_make_fetched(0, b"seg0"))

        stream_recorder.finalize_hls_pipeline()
        assert output.read_bytes() == b"init_dataseg0"

    def test_finalize_hls_pipeline(
        self, stream_recorder: StreamRecorder, tmp_path: Path
    ) -> None:
        output = tmp_path / "output.m4s"
        stream_recorder.create_hls_pipeline(output)
        stream_recorder.finalize_hls_pipeline()

        assert stream_recorder.hls_segment_dumper is None
        assert stream_recorder.hls_analyser is None
        assert stream_recorder.hls_fetcher is None

    def test_feed_playlist_without_pipeline(
        self, stream_recorder: StreamRecorder
    ) -> None:
        pl = _make_playlist([_make_segment(0)])
        new_segments = stream_recorder.feed_hls_playlist(pl)
        assert new_segments == []

    def test_feed_segment_without_pipeline(
        self, stream_recorder: StreamRecorder
    ) -> None:
        # Should not raise
        stream_recorder.feed_hls_segment(_make_fetched(0))

    def test_multiple_segments(
        self, stream_recorder: StreamRecorder, tmp_path: Path
    ) -> None:
        output = tmp_path / "output.m4s"
        stream_recorder.create_hls_pipeline(output)

        for i in range(5):
            stream_recorder.feed_hls_segment(_make_fetched(i, b"x" * 100))

        analyser = stream_recorder.hls_analyser
        assert analyser is not None
        meta = analyser.get_metadata()
        assert meta.segment_count == 5
        assert meta.total_size == 500
        assert meta.total_duration == 20.0

        stream_recorder.finalize_hls_pipeline()
        assert output.stat().st_size == 500
