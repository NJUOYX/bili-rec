"""Tests for HLS models and playlist parsing."""

from __future__ import annotations

import pytest

from birec.hls.exceptions import PlaylistParseError
from birec.hls.models import HlsPlaylist, HlsSegment, InitSegment
from birec.hls.playlist import parse_playlist

pytestmark = pytest.mark.unit


class TestHlsSegment:
    """Tests for HlsSegment model."""

    def test_basic_segment(self) -> None:
        seg = HlsSegment(uri="seg0.m4s", duration=4.0, sequence_number=0)
        assert seg.uri == "seg0.m4s"
        assert seg.duration == 4.0
        assert seg.sequence_number == 0
        assert seg.title == ""

    def test_filename_from_uri(self) -> None:
        seg = HlsSegment(
            uri="https://cdn.example.com/path/seg0.m4s",
            duration=4.0,
            sequence_number=0,
        )
        assert seg.filename == "seg0.m4s"

    def test_filename_no_slash(self) -> None:
        seg = HlsSegment(uri="seg0.m4s", duration=4.0, sequence_number=0)
        assert seg.filename == "seg0.m4s"

    def test_frozen(self) -> None:
        seg = HlsSegment(uri="seg0.m4s", duration=4.0, sequence_number=0)
        with pytest.raises(AttributeError):
            seg.uri = "other.m4s"  # type: ignore[misc]


class TestInitSegment:
    """Tests for InitSegment model."""

    def test_basic(self) -> None:
        init = InitSegment(uri="init.mp4")
        assert init.uri == "init.mp4"
        assert init.filename == "init.mp4"

    def test_filename_with_path(self) -> None:
        init = InitSegment(uri="https://cdn.example.com/init.mp4")
        assert init.filename == "init.mp4"


class TestHlsPlaylist:
    """Tests for HlsPlaylist model."""

    def test_empty_playlist(self) -> None:
        pl = HlsPlaylist()
        assert pl.version == 0
        assert pl.target_duration == 0.0
        assert pl.media_sequence == 0
        assert pl.segment_count == 0
        assert pl.total_duration == 0.0
        assert pl.init_segment is None
        assert pl.is_endlist is False

    def test_with_segments(self) -> None:
        segs = (
            HlsSegment(uri="s0.m4s", duration=4.0, sequence_number=0),
            HlsSegment(uri="s1.m4s", duration=4.0, sequence_number=1),
        )
        pl = HlsPlaylist(segments=segs, media_sequence=0)
        assert pl.segment_count == 2
        assert pl.total_duration == 8.0


class TestParsePlaylist:
    """Tests for parse_playlist function."""

    def test_minimal_playlist(self) -> None:
        text = "#EXTM3U\n#EXT-X-VERSION:7\n#EXT-X-TARGETDURATION:4\n"
        pl = parse_playlist(text)
        assert pl.version == 7
        assert pl.target_duration == 4.0
        assert pl.segment_count == 0

    def test_missing_header_raises(self) -> None:
        with pytest.raises(PlaylistParseError, match="missing #EXTM3U"):
            parse_playlist("not a playlist")

    def test_empty_string_raises(self) -> None:
        with pytest.raises(PlaylistParseError):
            parse_playlist("")

    def test_full_playlist(self) -> None:
        text = (
            "#EXTM3U\n"
            "#EXT-X-VERSION:7\n"
            "#EXT-X-TARGETDURATION:4\n"
            "#EXT-X-MEDIA-SEQUENCE:100\n"
            '#EXT-X-MAP:URI="init.mp4"\n'
            "#EXTINF:4.000,\n"
            "seg100.m4s\n"
            "#EXTINF:4.000,\n"
            "seg101.m4s\n"
            "#EXTINF:3.500,\n"
            "seg102.m4s\n"
        )
        pl = parse_playlist(text)
        assert pl.version == 7
        assert pl.target_duration == 4.0
        assert pl.media_sequence == 100
        assert pl.segment_count == 3
        assert pl.init_segment is not None
        assert pl.init_segment.uri == "init.mp4"
        assert pl.is_endlist is False

        assert pl.segments[0].uri == "seg100.m4s"
        assert pl.segments[0].duration == 4.0
        assert pl.segments[0].sequence_number == 100

        assert pl.segments[1].sequence_number == 101
        assert pl.segments[2].sequence_number == 102
        assert pl.segments[2].duration == 3.5

    def test_endlist(self) -> None:
        text = (
            "#EXTM3U\n#EXT-X-TARGETDURATION:4\n#EXTINF:4.0,\nseg0.m4s\n#EXT-X-ENDLIST\n"
        )
        pl = parse_playlist(text)
        assert pl.is_endlist is True
        assert pl.segment_count == 1

    def test_segment_with_title(self) -> None:
        text = "#EXTM3U\n#EXTINF:4.0,segment title\nseg0.m4s\n"
        pl = parse_playlist(text)
        assert pl.segments[0].title == "segment title"

    def test_total_duration(self) -> None:
        text = (
            "#EXTM3U\n"
            "#EXTINF:4.0,\n"
            "s0.m4s\n"
            "#EXTINF:4.0,\n"
            "s1.m4s\n"
            "#EXTINF:2.5,\n"
            "s2.m4s\n"
        )
        pl = parse_playlist(text)
        assert pl.total_duration == pytest.approx(10.5)

    def test_invalid_version_ignored(self) -> None:
        text = "#EXTM3U\n#EXT-X-VERSION:abc\n"
        pl = parse_playlist(text)
        assert pl.version == 0

    def test_invalid_target_duration_ignored(self) -> None:
        text = "#EXTM3U\n#EXT-X-TARGETDURATION:xyz\n"
        pl = parse_playlist(text)
        assert pl.target_duration == 0.0

    def test_map_without_uri(self) -> None:
        text = "#EXTM3U\n#EXT-X-MAP:BYTERANGE=100\n"
        pl = parse_playlist(text)
        assert pl.init_segment is None
