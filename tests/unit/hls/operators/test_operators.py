"""Tests for HLS operators."""

from __future__ import annotations

import zlib
from pathlib import Path

import pytest
from reactivex.subject import Subject

from birec.hls.models import HlsPlaylist, HlsSegment, InitSegment
from birec.hls.operators.analyse import HlsAnalyser, analyse
from birec.hls.operators.playlist_dumper import PlaylistDumper, dump_playlist
from birec.hls.operators.playlist_resolver import PlaylistResolver, resolve_playlist
from birec.hls.operators.segment_dumper import SegmentDumper, dump_segments
from birec.hls.operators.segment_fetcher import FetchedSegment, SegmentFetcher

pytestmark = pytest.mark.unit


def _make_segment(seq: int, duration: float = 4.0) -> HlsSegment:
    return HlsSegment(uri=f"seg{seq}.m4s", duration=duration, sequence_number=seq)


def _make_playlist(
    segments: list[HlsSegment],
    media_sequence: int = 0,
    init_uri: str | None = None,
) -> HlsPlaylist:
    return HlsPlaylist(
        media_sequence=media_sequence,
        segments=tuple(segments),
        init_segment=InitSegment(uri=init_uri) if init_uri else None,
        raw_text="#EXTM3U\n",
    )


def _make_fetched(seq: int, data: bytes = b"fake_data") -> FetchedSegment:
    seg = _make_segment(seq)
    crc = zlib.crc32(data) & 0xFFFFFFFF
    return FetchedSegment(segment=seg, data=data, crc32=crc)


class TestPlaylistResolver:
    """Tests for PlaylistResolver."""

    def test_first_playlist_all_new(self) -> None:
        resolver = PlaylistResolver()
        pl = _make_playlist([_make_segment(0), _make_segment(1), _make_segment(2)])
        new = resolver.resolve(pl)
        assert len(new) == 3
        assert new[0].sequence_number == 0
        assert new[2].sequence_number == 2

    def test_second_playlist_only_new(self) -> None:
        resolver = PlaylistResolver()
        pl1 = _make_playlist([_make_segment(0), _make_segment(1)])
        resolver.resolve(pl1)

        pl2 = _make_playlist([_make_segment(1), _make_segment(2), _make_segment(3)])
        new = resolver.resolve(pl2)
        assert len(new) == 2
        assert new[0].sequence_number == 2
        assert new[1].sequence_number == 3

    def test_no_new_segments(self) -> None:
        resolver = PlaylistResolver()
        pl = _make_playlist([_make_segment(0), _make_segment(1)])
        resolver.resolve(pl)
        new = resolver.resolve(pl)
        assert len(new) == 0

    def test_reset(self) -> None:
        resolver = PlaylistResolver()
        pl = _make_playlist([_make_segment(5)])
        resolver.resolve(pl)
        assert resolver.last_sequence == 5

        resolver.reset()
        assert resolver.last_sequence == -1

    def test_last_sequence_tracking(self) -> None:
        resolver = PlaylistResolver()
        assert resolver.last_sequence == -1
        pl = _make_playlist([_make_segment(10)])
        resolver.resolve(pl)
        assert resolver.last_sequence == 10


class TestPlaylistResolverOperator:
    """Tests for resolve_playlist operator."""

    def test_emits_new_segments(self) -> None:
        source: Subject[HlsPlaylist] = Subject()
        results: list[HlsSegment] = []

        resolve_playlist()(source).subscribe(on_next=results.append)

        pl1 = _make_playlist([_make_segment(0), _make_segment(1)])
        source.on_next(pl1)
        assert len(results) == 2

        pl2 = _make_playlist([_make_segment(1), _make_segment(2)])
        source.on_next(pl2)
        assert len(results) == 3
        assert results[2].sequence_number == 2


class TestSegmentDumper:
    """Tests for SegmentDumper."""

    def test_write_segments(self, tmp_path: Path) -> None:
        path = tmp_path / "output.m4s"
        dumper = SegmentDumper(path)
        dumper.open()

        fetched = _make_fetched(0, b"hello")
        written = dumper.write_segment(fetched)
        assert written == 5
        assert dumper.bytes_written == 5
        assert dumper.segment_count == 1

        dumper.close()
        assert path.read_bytes() == b"hello"

    def test_write_init(self, tmp_path: Path) -> None:
        path = tmp_path / "output.m4s"
        dumper = SegmentDumper(path)
        dumper.open()

        written = dumper.write_init(b"init_data")
        assert written == 9
        assert dumper.bytes_written == 9

        dumper.close()
        assert path.read_bytes() == b"init_data"

    def test_multiple_segments(self, tmp_path: Path) -> None:
        path = tmp_path / "output.m4s"
        dumper = SegmentDumper(path)
        dumper.open()

        dumper.write_segment(_make_fetched(0, b"aaa"))
        dumper.write_segment(_make_fetched(1, b"bbb"))
        assert dumper.bytes_written == 6
        assert dumper.segment_count == 2

        dumper.close()
        assert path.read_bytes() == b"aaabbb"

    def test_not_opened_raises(self, tmp_path: Path) -> None:
        dumper = SegmentDumper(tmp_path / "x.m4s")
        with pytest.raises(RuntimeError, match="not opened"):
            dumper.write_segment(_make_fetched(0))

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "sub" / "dir" / "output.m4s"
        dumper = SegmentDumper(path)
        dumper.open()
        dumper.write_segment(_make_fetched(0, b"data"))
        dumper.close()
        assert path.exists()


class TestSegmentDumperOperator:
    """Tests for dump_segments operator."""

    def test_writes_and_passes_through(self, tmp_path: Path) -> None:
        path = tmp_path / "out.m4s"
        source: Subject[FetchedSegment] = Subject()
        results: list[FetchedSegment] = []
        completed = []

        dump_segments(path)(source).subscribe(
            on_next=results.append, on_completed=lambda: completed.append(True)
        )

        fetched = _make_fetched(0, b"test_data")
        source.on_next(fetched)
        source.on_completed()  # Close the dumper

        assert len(results) == 1
        assert results[0] == fetched
        assert completed
        assert path.read_bytes() == b"test_data"


class TestPlaylistDumper:
    """Tests for PlaylistDumper."""

    def test_track_duration(self) -> None:
        dumper = PlaylistDumper()
        pl = _make_playlist([_make_segment(0, 4.0), _make_segment(1, 4.0)])
        dumper.update(pl)
        assert dumper.total_duration == 8.0
        assert dumper.segment_count == 2

    def test_detect_lost_segments(self) -> None:
        dumper = PlaylistDumper()
        # First playlist: seq 0, 1
        pl1 = _make_playlist([_make_segment(0), _make_segment(1)])
        dumper.update(pl1)
        assert dumper.lost_segments == 0

        # Second playlist: seq 4, 5 (gap of 2: seq 2, 3 missing)
        pl2 = _make_playlist([_make_segment(4), _make_segment(5)])
        dumper.update(pl2)
        assert dumper.lost_segments == 2

    def test_add_segment(self) -> None:
        dumper = PlaylistDumper()
        dumper.add_segment(_make_segment(0, 4.0))
        dumper.add_segment(_make_segment(1, 4.0))
        assert dumper.segment_count == 2
        assert dumper.total_duration == 8.0

    def test_add_segment_with_gap(self) -> None:
        dumper = PlaylistDumper()
        dumper.add_segment(_make_segment(0))
        dumper.add_segment(_make_segment(3))  # gap: 1, 2 missing
        assert dumper.lost_segments == 2

    def test_dump_to_file(self, tmp_path: Path) -> None:
        path = tmp_path / "playlist.m3u8"
        dumper = PlaylistDumper(path)
        pl = _make_playlist([_make_segment(0)])
        dumper.dump(pl)
        assert path.exists()
        assert path.read_text() == "#EXTM3U\n"

    def test_reset(self) -> None:
        dumper = PlaylistDumper()
        dumper.add_segment(_make_segment(0, 4.0))
        dumper.reset()
        assert dumper.total_duration == 0.0
        assert dumper.segment_count == 0
        assert dumper.lost_segments == 0


class TestPlaylistDumperOperator:
    """Tests for dump_playlist operator."""

    def test_passes_through(self) -> None:
        source: Subject[HlsPlaylist] = Subject()
        results: list[HlsPlaylist] = []

        dump_playlist()(source).subscribe(on_next=results.append)

        pl = _make_playlist([_make_segment(0)])
        source.on_next(pl)
        assert len(results) == 1
        assert results[0] == pl


class TestHlsAnalyser:
    """Tests for HlsAnalyser."""

    def test_add_segments(self) -> None:
        analyser = HlsAnalyser()
        analyser.add_segment(_make_fetched(0, b"aaaa"))
        analyser.add_segment(_make_fetched(1, b"bbbbbb"))

        meta = analyser.get_metadata()
        assert meta.segment_count == 2
        assert meta.total_size == 10
        assert meta.total_duration == 8.0

    def test_metadata_to_dict(self) -> None:
        analyser = HlsAnalyser()
        analyser.add_segment(_make_fetched(0, b"data"))

        meta = analyser.get_metadata()
        d = meta.to_dict()
        assert d["segment_count"] == 1
        assert d["total_size"] == 4
        assert isinstance(d["segments"], list)

    def test_dump_metadata(self, tmp_path: Path) -> None:
        analyser = HlsAnalyser()
        analyser.add_segment(_make_fetched(0, b"test"))

        path = tmp_path / "meta.json"
        analyser.dump_metadata(path)
        assert path.exists()

        import json

        data = json.loads(path.read_text())
        assert data["segment_count"] == 1

    def test_reset(self) -> None:
        analyser = HlsAnalyser()
        analyser.add_segment(_make_fetched(0))
        analyser.reset()
        meta = analyser.get_metadata()
        assert meta.segment_count == 0


class TestAnalyseOperator:
    """Tests for analyse operator."""

    def test_passes_through(self) -> None:
        source: Subject[FetchedSegment] = Subject()
        results: list[FetchedSegment] = []

        analyse()(source).subscribe(on_next=results.append)

        fetched = _make_fetched(0)
        source.on_next(fetched)
        assert len(results) == 1
        assert results[0] == fetched


class TestSegmentFetcher:
    """Tests for SegmentFetcher."""

    def test_resolve_url_absolute(self) -> None:
        fetcher = SegmentFetcher(
            session=None,  # type: ignore[arg-type]
            base_url="https://cdn.example.com",
        )
        url = fetcher._resolve_url("https://other.com/seg.m4s")
        assert url == "https://other.com/seg.m4s"

    def test_resolve_url_relative(self) -> None:
        fetcher = SegmentFetcher(
            session=None,  # type: ignore[arg-type]
            base_url="https://cdn.example.com/path",
        )
        url = fetcher._resolve_url("seg.m4s")
        assert url == "https://cdn.example.com/path/seg.m4s"

    def test_resolve_url_no_base(self) -> None:
        fetcher = SegmentFetcher(
            session=None,  # type: ignore[arg-type]
            base_url="",
        )
        url = fetcher._resolve_url("seg.m4s")
        assert url == "seg.m4s"

    def test_verify_crc_valid(self) -> None:
        data = b"test data"
        crc = zlib.crc32(data) & 0xFFFFFFFF
        # Should not raise
        SegmentFetcher.verify_crc(data, crc)

    def test_verify_crc_invalid(self) -> None:
        from birec.hls.exceptions import SegmentCorruptedError

        data = b"test data"
        with pytest.raises(SegmentCorruptedError):
            SegmentFetcher.verify_crc(data, 12345)


class TestFetchedSegment:
    """Tests for FetchedSegment model."""

    def test_size(self) -> None:
        fetched = _make_fetched(0, b"hello world")
        assert fetched.size == 11

    def test_frozen(self) -> None:
        fetched = _make_fetched(0)
        with pytest.raises(AttributeError):
            fetched.data = b"other"  # type: ignore[misc]
