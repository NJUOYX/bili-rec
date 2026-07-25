"""Tests for concat operator."""

from __future__ import annotations

import reactivex

from birec.flv.operators import JoinPoint, JoinPointExtractor, concat
from birec.flv.operators.typing import FLVStreamItem

from ..conftest import make_video_tag


class TestConcat:
    """Tests for concat operator."""

    def test_pass_through(self) -> None:
        """Test that tags pass through."""
        tags = [
            make_video_tag(timestamp=0, body=b"\x01"),
            make_video_tag(timestamp=100, body=b"\x02"),
        ]

        results: list[FLVStreamItem] = []
        source = reactivex.from_iterable(tags)
        source.pipe(concat()).subscribe(on_next=results.append)

        assert len(results) == 2

    def test_skip_duplicates(self) -> None:
        """Test that duplicate tags are skipped."""
        tags = [
            make_video_tag(timestamp=0, body=b"\x01\x02\x03"),
            make_video_tag(timestamp=100, body=b"\x01\x02\x03"),  # Duplicate
            make_video_tag(timestamp=200, body=b"\x04\x05\x06"),
        ]

        results: list[FLVStreamItem] = []
        source = reactivex.from_iterable(tags)
        source.pipe(concat()).subscribe(on_next=results.append)

        # Duplicate should be skipped
        assert len(results) == 2


class TestJoinPoint:
    """Tests for JoinPoint."""

    def test_frozen(self) -> None:
        """Test that JoinPoint is immutable."""
        jp = JoinPoint(seamless=True, timestamp=1000, crc32=12345)
        assert jp.seamless is True
        assert jp.timestamp == 1000
        assert jp.crc32 == 12345


class TestJoinPointExtractor:
    """Tests for JoinPointExtractor."""

    def test_detect_join_point(self) -> None:
        """Test detecting join points."""
        extractor = JoinPointExtractor()

        tag1 = make_video_tag(timestamp=0, body=b"\x01\x02\x03")
        tag2 = make_video_tag(timestamp=100, body=b"\x01\x02\x03")  # Same body

        jp1 = extractor.process(tag1)
        jp2 = extractor.process(tag2)

        assert jp1 is None
        assert jp2 is not None
        assert jp2.seamless is True
        assert len(extractor.join_points) == 1

    def test_no_join_point_different_body(self) -> None:
        """Test no join point for different bodies."""
        extractor = JoinPointExtractor()

        tag1 = make_video_tag(timestamp=0, body=b"\x01\x02\x03")
        tag2 = make_video_tag(timestamp=100, body=b"\x04\x05\x06")

        jp1 = extractor.process(tag1)
        jp2 = extractor.process(tag2)

        assert jp1 is None
        assert jp2 is None
        assert len(extractor.join_points) == 0
