"""Tests for basic FLV operators (defragment, split, sort, correct, fix)."""

from __future__ import annotations

import reactivex

from birec.flv.operators import correct, defragment, fix, sort, split
from birec.flv.operators.typing import FLVStreamItem

from ..conftest import make_video_tag


class TestDefragment:
    """Tests for defragment operator."""

    def test_pass_through_long_stream(self) -> None:
        """Test that long streams pass through."""
        tags = [
            make_video_tag(timestamp=0),
            make_video_tag(timestamp=2000),
        ]

        results: list[FLVStreamItem] = []
        source = reactivex.from_iterable(tags)
        source.pipe(defragment(min_duration=1000)).subscribe(on_next=results.append)

        assert len(results) == 2

    def test_discard_short_stream(self) -> None:
        """Test that short streams are discarded."""
        tags = [
            make_video_tag(timestamp=0),
            make_video_tag(timestamp=500),
        ]

        results: list[FLVStreamItem] = []
        source = reactivex.from_iterable(tags)
        source.pipe(defragment(min_duration=1000)).subscribe(on_next=results.append)

        # Stream is discarded but items are still emitted
        assert len(results) == 2


class TestSplit:
    """Tests for split operator."""

    def test_pass_through(self) -> None:
        """Test that tags pass through."""
        tags = [
            make_video_tag(timestamp=0),
            make_video_tag(timestamp=100),
        ]

        results: list[FLVStreamItem] = []
        source = reactivex.from_iterable(tags)
        source.pipe(split()).subscribe(on_next=results.append)

        assert len(results) == 2


class TestSort:
    """Tests for sort operator."""

    def test_sort_by_timestamp(self) -> None:
        """Test that tags are sorted by timestamp within GOP."""
        from birec.flv import FrameType

        # First keyframe, then out-of-order non-keyframes, then another keyframe
        tags = [
            make_video_tag(timestamp=0, frame_type=FrameType.KEY_FRAME),
            make_video_tag(timestamp=100, frame_type=FrameType.INNER_FRAME),
            make_video_tag(timestamp=50, frame_type=FrameType.INNER_FRAME),
            make_video_tag(timestamp=200, frame_type=FrameType.KEY_FRAME),
        ]

        results: list[FLVStreamItem] = []
        source = reactivex.from_iterable(tags)
        source.pipe(sort()).subscribe(on_next=results.append)

        # Should be sorted by timestamp within GOP
        assert len(results) == 4
        timestamps = [t.timestamp for t in results if isinstance(t, type(tags[0]))]
        # First keyframe (0), then sorted inner frames (50, 100), then keyframe (200)
        assert timestamps == [0, 50, 100, 200]


class TestCorrect:
    """Tests for correct operator."""

    def test_correct_decreasing_timestamp(self) -> None:
        """Test that decreasing timestamps are corrected."""
        tags = [
            make_video_tag(timestamp=100),
            make_video_tag(timestamp=50),  # Should be corrected to 100
            make_video_tag(timestamp=200),
        ]

        results: list[FLVStreamItem] = []
        source = reactivex.from_iterable(tags)
        source.pipe(correct()).subscribe(on_next=results.append)

        assert len(results) == 3
        timestamps = [t.timestamp for t in results if isinstance(t, type(tags[0]))]
        assert timestamps == [100, 100, 200]

    def test_pass_through_increasing(self) -> None:
        """Test that increasing timestamps pass through."""
        tags = [
            make_video_tag(timestamp=0),
            make_video_tag(timestamp=100),
            make_video_tag(timestamp=200),
        ]

        results: list[FLVStreamItem] = []
        source = reactivex.from_iterable(tags)
        source.pipe(correct()).subscribe(on_next=results.append)

        assert len(results) == 3
        timestamps = [t.timestamp for t in results if isinstance(t, type(tags[0]))]
        assert timestamps == [0, 100, 200]


class TestFix:
    """Tests for fix operator."""

    def test_fix_timestamp_jump(self) -> None:
        """Test that timestamp jumps are fixed."""
        tags = [
            make_video_tag(timestamp=1000),
            make_video_tag(timestamp=5_000_000),  # Large jump
        ]

        results: list[FLVStreamItem] = []
        source = reactivex.from_iterable(tags)
        source.pipe(fix(jump_threshold=1_000_000)).subscribe(on_next=results.append)

        assert len(results) == 2
        # Second tag should have adjusted timestamp
        timestamps = [t.timestamp for t in results if isinstance(t, type(tags[0]))]
        assert timestamps[0] == 1000
        # After fix, the jump should be corrected
        assert timestamps[1] < 5_000_000

    def test_pass_through_normal(self) -> None:
        """Test that normal timestamps pass through."""
        tags = [
            make_video_tag(timestamp=0),
            make_video_tag(timestamp=1000),
            make_video_tag(timestamp=2000),
        ]

        results: list[FLVStreamItem] = []
        source = reactivex.from_iterable(tags)
        source.pipe(fix()).subscribe(on_next=results.append)

        assert len(results) == 3
        timestamps = [t.timestamp for t in results if isinstance(t, type(tags[0]))]
        assert timestamps == [0, 1000, 2000]


class TestCombined:
    """Tests for combined operators."""

    def test_correct_then_fix(self) -> None:
        """Test correct followed by fix."""
        tags = [
            make_video_tag(timestamp=100),
            make_video_tag(timestamp=50),  # Will be corrected to 100
            make_video_tag(timestamp=200),
        ]

        results: list[FLVStreamItem] = []
        source = reactivex.from_iterable(tags)
        source.pipe(correct(), fix()).subscribe(on_next=results.append)

        assert len(results) == 3
