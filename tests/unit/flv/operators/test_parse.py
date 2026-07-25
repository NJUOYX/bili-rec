"""Tests for parse operator."""

from __future__ import annotations

from io import BytesIO

import reactivex
from reactivex.testing import TestScheduler

from birec.flv import FlvHeader, FlvTag
from birec.flv.operators import parse
from birec.flv.operators.typing import FLVStreamItem

from ..conftest import make_audio_tag, make_flv_bytes, make_video_tag


class TestParse:
    """Tests for parse operator."""

    def test_parse_header(self) -> None:
        """Test parsing FLV header."""
        data = make_flv_bytes()
        stream = BytesIO(data)

        results: list[FLVStreamItem] = []
        source = reactivex.of(stream)
        parsed = source.pipe(parse())
        parsed.subscribe(on_next=results.append)

        assert len(results) == 1
        assert isinstance(results[0], FlvHeader)
        assert results[0].signature == "FLV"

    def test_parse_video_tag(self) -> None:
        """Test parsing video tag."""
        tag = make_video_tag(body=b"\x01\x02\x03")
        data = make_flv_bytes(tags=[tag])
        stream = BytesIO(data)

        results: list[FLVStreamItem] = []
        source = reactivex.of(stream)
        parsed = source.pipe(parse())
        parsed.subscribe(on_next=results.append)

        # Header + video tag + AVC end sequence tag
        assert len(results) == 3
        assert isinstance(results[0], FlvHeader)
        assert isinstance(results[1], FlvTag)
        assert results[1].is_video_tag()
        # AVC end sequence tag
        assert isinstance(results[2], FlvTag)
        assert results[2].is_video_tag()

    def test_parse_audio_tag(self) -> None:
        """Test parsing audio tag."""
        tag = make_audio_tag(body=b"\x04\x05\x06")
        data = make_flv_bytes(tags=[tag])
        stream = BytesIO(data)

        results: list[FLVStreamItem] = []
        source = reactivex.of(stream)
        parsed = source.pipe(parse())
        parsed.subscribe(on_next=results.append)

        # Header + audio tag (no AVC end for audio-only)
        assert len(results) == 2
        assert isinstance(results[0], FlvHeader)
        assert isinstance(results[1], FlvTag)
        assert results[1].is_audio_tag()

    def test_parse_multiple_tags(self) -> None:
        """Test parsing multiple tags."""
        tags = [
            make_video_tag(timestamp=0),
            make_audio_tag(timestamp=0),
            make_video_tag(timestamp=100),
        ]
        data = make_flv_bytes(tags=tags)
        stream = BytesIO(data)

        results: list[FLVStreamItem] = []
        source = reactivex.of(stream)
        parsed = source.pipe(parse())
        parsed.subscribe(on_next=results.append)

        # Header + 3 tags + AVC end sequence
        assert len(results) == 5
        assert isinstance(results[0], FlvHeader)
        assert isinstance(results[1], FlvTag)
        assert results[1].is_video_tag()
        assert isinstance(results[2], FlvTag)
        assert results[2].is_audio_tag()
        assert isinstance(results[3], FlvTag)
        assert results[3].is_video_tag()

    def test_parse_empty_stream(self) -> None:
        """Test parsing empty stream."""
        stream = BytesIO(b"")

        results: list[FLVStreamItem] = []
        completed = []
        source = reactivex.of(stream)
        parsed = source.pipe(parse())
        parsed.subscribe(
            on_next=results.append,
            on_completed=lambda: completed.append(True),
        )

        assert len(results) == 0
        assert len(completed) == 1

    def test_parse_with_scheduler(self) -> None:
        """Test parse operator with test scheduler."""
        scheduler = TestScheduler()
        data = make_flv_bytes()
        stream = BytesIO(data)

        results: list[FLVStreamItem] = []
        source = reactivex.of(stream)
        parsed = source.pipe(parse())
        parsed.subscribe(on_next=results.append, scheduler=scheduler)

        scheduler.start()
        assert len(results) == 1
        assert isinstance(results[0], FlvHeader)

    def test_parse_complete_on_eof_false(self) -> None:
        """Test parse with complete_on_eof=False."""
        data = make_flv_bytes()
        stream = BytesIO(data)

        results: list[FLVStreamItem] = []
        completed = []
        source = reactivex.of(stream)
        parsed = source.pipe(parse(complete_on_eof=False))
        parsed.subscribe(
            on_next=results.append,
            on_completed=lambda: completed.append(True),
        )

        assert len(results) == 1
        # Should not complete since complete_on_eof=False
        # But source completes, so it will complete
        assert len(completed) == 1
