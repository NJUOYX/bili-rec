"""Tests for dump and progress operators."""

from __future__ import annotations

from pathlib import Path

from reactivex import of

from birec.flv import FlvParser
from birec.flv.operators import Dumper, ProgressBar, dump, progress
from birec.flv.operators.typing import FLVStreamItem

from ..conftest import make_audio_tag, make_flv_header, make_video_tag


class TestDumper:
    """Tests for Dumper class."""

    def test_open_close(self, tmp_path: Path) -> None:
        """Test opening and closing a file."""
        path = tmp_path / "test.flv"
        dumper = Dumper(path)
        dumper.open()
        assert path.exists()
        dumper.close()

    def test_write_header(self, tmp_path: Path) -> None:
        """Test writing FLV header."""
        path = tmp_path / "test.flv"
        dumper = Dumper(path)
        dumper.open()

        header = make_flv_header()
        written = dumper.write(header)

        assert written == header.size + 4  # header + back pointer
        assert dumper.bytes_written == written
        dumper.close()

    def test_write_video_tag(self, tmp_path: Path) -> None:
        """Test writing video tag."""
        path = tmp_path / "test.flv"
        dumper = Dumper(path)
        dumper.open()

        header = make_flv_header()
        dumper.write(header)

        tag = make_video_tag(timestamp=1000)
        written = dumper.write(tag)

        assert written == tag.tag_size + 4
        dumper.close()

    def test_write_audio_tag(self, tmp_path: Path) -> None:
        """Test writing audio tag."""
        path = tmp_path / "test.flv"
        dumper = Dumper(path)
        dumper.open()

        header = make_flv_header()
        dumper.write(header)

        tag = make_audio_tag(timestamp=500)
        written = dumper.write(tag)

        assert written == tag.tag_size + 4
        dumper.close()

    def test_write_without_open_raises(self, tmp_path: Path) -> None:
        """Test writing without opening raises RuntimeError."""
        path = tmp_path / "test.flv"
        dumper = Dumper(path)

        try:
            dumper.write(make_flv_header())
            assert False, "Should have raised RuntimeError"
        except RuntimeError:
            pass

    def test_roundtrip(self, tmp_path: Path) -> None:
        """Test that dumped file can be parsed back."""
        path = tmp_path / "test.flv"
        dumper = Dumper(path)
        dumper.open()

        header = make_flv_header()
        video = make_video_tag(timestamp=0)
        audio = make_audio_tag(timestamp=0)

        dumper.write(header)
        dumper.write(video)
        dumper.write(audio)
        dumper.close()

        # Parse back
        with open(path, "rb") as f:
            parser = FlvParser(f)
            parsed_header = parser.parse_header()
            assert parsed_header.signature == "FLV"
            assert parsed_header.version == 1

            parser.parse_previous_tag_size()
            tag1 = parser.parse_tag()
            assert tag1.timestamp == 0

    def test_path_property(self, tmp_path: Path) -> None:
        """Test path property."""
        path = tmp_path / "test.flv"
        dumper = Dumper(path)
        assert dumper.path == path


class TestDumpOperator:
    """Tests for dump() operator."""

    def test_dump_writes_file(self, tmp_path: Path) -> None:
        """Test that dump operator writes items to file."""
        path = tmp_path / "output.flv"
        items: list[FLVStreamItem] = [
            make_flv_header(),
            make_video_tag(timestamp=0),
            make_audio_tag(timestamp=0),
            make_video_tag(timestamp=1000),
        ]

        source = of(*items)
        result = dump(path)(source)

        received: list[FLVStreamItem] = []
        result.subscribe(on_next=received.append)

        assert path.exists()
        assert len(received) == 4

    def test_dump_passes_through(self, tmp_path: Path) -> None:
        """Test that dump operator passes items through."""
        path = tmp_path / "output.flv"
        header = make_flv_header()
        source = of(header)
        result = dump(path)(source)

        received: list[FLVStreamItem] = []
        result.subscribe(on_next=received.append)

        assert len(received) == 1
        assert received[0] is header


class TestProgressBar:
    """Tests for ProgressBar class."""

    def test_initial_state(self) -> None:
        """Test initial state."""
        bar = ProgressBar()
        assert bar.bytes_written == 0
        assert bar.duration_ms == 0
        assert bar.duration_str == "00:00:00.000"

    def test_update_with_tags(self) -> None:
        """Test updating with tags."""
        bar = ProgressBar()
        tag1 = make_video_tag(timestamp=0)
        tag2 = make_video_tag(timestamp=5000)

        bar.update(tag1, 100)
        bar.update(tag2, 200)

        assert bar.bytes_written == 300
        assert bar.duration_ms == 5000

    def test_duration_str_format(self) -> None:
        """Test duration string formatting."""
        bar = ProgressBar()
        tag1 = make_video_tag(timestamp=0)
        # 1h 2m 3s 456ms = 3723456ms
        tag2 = make_video_tag(timestamp=3_723_456)

        bar.update(tag1, 10)
        bar.update(tag2, 10)

        assert bar.duration_str == "01:02:03.456"

    def test_get_status(self) -> None:
        """Test get_status returns dict."""
        bar = ProgressBar()
        tag = make_video_tag(timestamp=1000)
        bar.update(tag, 50)

        status = bar.get_status()
        assert status["bytes_written"] == 50
        assert status["duration_ms"] == 0  # Only one tag, no duration yet
        assert "duration_str" in status


class TestProgressOperator:
    """Tests for progress() operator."""

    def test_progress_tracks_items(self) -> None:
        """Test that progress operator tracks items."""
        items: list[FLVStreamItem] = [
            make_flv_header(),
            make_video_tag(timestamp=0),
            make_video_tag(timestamp=2000),
        ]

        source = of(*items)
        result = progress()(source)

        received: list[FLVStreamItem] = []
        result.subscribe(on_next=received.append)

        assert len(received) == 3

    def test_progress_callback(self) -> None:
        """Test that callback is invoked."""
        callbacks: list[ProgressBar] = []

        items: list[FLVStreamItem] = [
            make_video_tag(timestamp=0),
            make_video_tag(timestamp=2000),
        ]

        source = of(*items)
        result = progress(callback=callbacks.append, interval=1000)(source)

        received: list[FLVStreamItem] = []
        completed = False

        def on_completed() -> None:
            nonlocal completed
            completed = True

        result.subscribe(on_next=received.append, on_completed=on_completed)

        assert len(received) == 2
        assert completed
        # Final callback on complete
        assert len(callbacks) >= 1
