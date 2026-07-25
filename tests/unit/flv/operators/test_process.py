"""Tests for process operator."""

from __future__ import annotations

import reactivex

from birec.flv import FrameType
from birec.flv.operators import process
from birec.flv.operators.typing import FLVStreamItem

from ..conftest import make_video_tag


class TestProcess:
    """Tests for process operator."""

    def test_basic_pipeline(self) -> None:
        """Test basic processing pipeline."""
        tags = [
            make_video_tag(timestamp=0, frame_type=FrameType.KEY_FRAME, body=b"\x01"),
            make_video_tag(timestamp=100, frame_type=FrameType.INNER_FRAME, body=b"\x02"),
            make_video_tag(timestamp=200, frame_type=FrameType.KEY_FRAME, body=b"\x03"),
        ]

        results: list[FLVStreamItem] = []
        source = reactivex.from_iterable(tags)
        source.pipe(process()).subscribe(on_next=results.append)

        assert len(results) == 3

    def test_without_sort(self) -> None:
        """Test pipeline without sorting."""
        tags = [
            make_video_tag(timestamp=0, body=b"\x01"),
            make_video_tag(timestamp=100, body=b"\x02"),
        ]

        results: list[FLVStreamItem] = []
        source = reactivex.from_iterable(tags)
        source.pipe(process(sort_tags=False)).subscribe(on_next=results.append)

        assert len(results) == 2

    def test_correct_timestamps(self) -> None:
        """Test that timestamps are corrected."""
        tags = [
            make_video_tag(timestamp=100, body=b"\x01"),
            make_video_tag(timestamp=50, body=b"\x02"),  # Should be corrected
            make_video_tag(timestamp=200, body=b"\x03"),
        ]

        results: list[FLVStreamItem] = []
        source = reactivex.from_iterable(tags)
        source.pipe(process()).subscribe(on_next=results.append)

        timestamps = [t.timestamp for t in results if isinstance(t, type(tags[0]))]
        # Timestamps should be monotonically increasing
        assert timestamps == sorted(timestamps)

    def test_custom_min_duration(self) -> None:
        """Test custom min_duration parameter."""
        tags = [
            make_video_tag(timestamp=0, body=b"\x01"),
            make_video_tag(timestamp=500, body=b"\x02"),
        ]

        results: list[FLVStreamItem] = []
        source = reactivex.from_iterable(tags)
        source.pipe(process(min_duration=100)).subscribe(on_next=results.append)

        assert len(results) == 2
