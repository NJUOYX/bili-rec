"""Tests for analyse operator."""

from __future__ import annotations

import reactivex

from birec.flv import FrameType
from birec.flv.operators import Analyser, StreamProfile, analyse
from birec.flv.operators.typing import FLVStreamItem

from ..conftest import make_video_tag


class TestAnalyser:
    """Tests for Analyser class."""

    def test_track_timestamps(self) -> None:
        """Test timestamp tracking."""
        analyser = Analyser()

        tag1 = make_video_tag(timestamp=0)
        tag2 = make_video_tag(timestamp=1000)
        tag3 = make_video_tag(timestamp=2000)

        analyser.process(tag1)
        analyser.process(tag2)
        analyser.process(tag3)

        assert analyser.first_timestamp == 0
        assert analyser.last_timestamp == 2000
        assert analyser.duration == 2.0

    def test_track_keyframes(self) -> None:
        """Test keyframe tracking."""
        analyser = Analyser()

        tag1 = make_video_tag(timestamp=0, frame_type=FrameType.KEY_FRAME)
        tag2 = make_video_tag(timestamp=100, frame_type=FrameType.INNER_FRAME)
        tag3 = make_video_tag(timestamp=200, frame_type=FrameType.KEY_FRAME)

        analyser.process(tag1)
        analyser.process(tag2)
        analyser.process(tag3)

        assert analyser.keyframe_count == 2
        assert analyser.keyframe_timestamps == [0, 200]

    def test_get_metadata(self) -> None:
        """Test metadata generation."""
        analyser = Analyser()
        analyser.width = 1920
        analyser.height = 1080
        analyser.first_timestamp = 0
        analyser.last_timestamp = 10000

        metadata = analyser.get_metadata()

        assert metadata["width"] == 1920.0
        assert metadata["height"] == 1080.0
        assert metadata["duration"] == 10.0

    def test_get_profile(self) -> None:
        """Test profile generation."""
        analyser = Analyser()
        analyser.width = 1920
        analyser.height = 1080
        analyser.first_timestamp = 0
        analyser.last_timestamp = 5000

        profile = analyser.get_profile()

        assert isinstance(profile, StreamProfile)
        assert profile.width == 1920
        assert profile.height == 1080
        assert profile.duration == 5.0


class TestAnalyseOperator:
    """Tests for analyse operator."""

    def test_pass_through(self) -> None:
        """Test that items pass through."""
        tags = [
            make_video_tag(timestamp=0, body=b"\x01"),
            make_video_tag(timestamp=100, body=b"\x02"),
        ]

        results: list[FLVStreamItem] = []
        source = reactivex.from_iterable(tags)
        source.pipe(analyse()).subscribe(on_next=results.append)

        assert len(results) == 2
