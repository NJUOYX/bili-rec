"""Tests for parse operator."""

from __future__ import annotations

from io import BytesIO

import reactivex
from reactivex.subject import Subject
from reactivex.testing import TestScheduler

from birec.flv import FlvHeader, FlvTag, StreamBuffer
from birec.flv.common import is_avc_end_sequence_tag
from birec.flv.operators import parse
from birec.flv.operators.typing import FLVStreamItem
from birec.flv.struct_io import RandomIO

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


class TestParseResumable:
    """Tests for parse(resumable=True), used by live FLV downloads."""

    def test_chunked_feed_yields_every_tag(self) -> None:
        """Regression: chunk boundaries must not drop tags or end the stream.

        A live download hands over arbitrary HTTP chunks that cut tags in half.
        Without resumable parsing the first chunk is parsed as a whole FLV
        document and everything after it is silently discarded.
        """
        tags = [make_video_tag(timestamp=i * 40, body=bytes([i]) * 8) for i in range(6)]
        data = make_flv_bytes(tags=tags)
        buffer = StreamBuffer()
        source: Subject[RandomIO] = Subject()

        results: list[FLVStreamItem] = []
        completed: list[bool] = []
        source.pipe(parse(resumable=True)).subscribe(
            on_next=results.append,
            on_completed=lambda: completed.append(True),
        )

        # 5 bytes splits the 9-byte header, the 11-byte tag headers and bodies.
        for i in range(0, len(data), 5):
            buffer.append(data[i : i + 5])
            source.on_next(buffer)
            buffer.discard_consumed()
            assert not completed, "a partial chunk must not end the stream"

        header = results[0]
        assert isinstance(header, FlvHeader)
        parsed_tags = [item for item in results if isinstance(item, FlvTag)]
        assert [t.timestamp for t in parsed_tags] == [i * 40 for i in range(6)]
        assert [t.body for t in parsed_tags] == [bytes([i]) * 8 for i in range(6)]

    def test_tag_offsets_are_absolute_across_chunks(self) -> None:
        """Tag offsets must reflect the whole stream, not the current chunk."""
        tags = [make_video_tag(timestamp=i * 40) for i in range(4)]
        data = make_flv_bytes(tags=tags)
        buffer = StreamBuffer()
        source: Subject[RandomIO] = Subject()

        results: list[FLVStreamItem] = []
        source.pipe(parse(resumable=True)).subscribe(on_next=results.append)

        for i in range(0, len(data), 9):
            buffer.append(data[i : i + 9])
            source.on_next(buffer)
            buffer.discard_consumed()

        offsets = [item.offset for item in results if isinstance(item, FlvTag)]
        assert offsets == sorted(offsets)
        assert offsets[0] == 13  # 9-byte header + 4-byte back-pointer

    def test_end_sequence_tag_emitted_once_on_completion(self) -> None:
        """The AVC end sequence tag belongs at the end, not at every boundary."""
        data = make_flv_bytes(tags=[make_video_tag()])
        buffer = StreamBuffer()
        source: Subject[RandomIO] = Subject()

        results: list[FLVStreamItem] = []
        source.pipe(parse(resumable=True)).subscribe(on_next=results.append)

        for i in range(0, len(data), 4):
            buffer.append(data[i : i + 4])
            source.on_next(buffer)
            buffer.discard_consumed()

        before_completion = len(results)
        source.on_completed()

        end_tags = [item for item in results if is_avc_end_sequence_tag(item)]
        assert len(end_tags) == 1
        assert len(results) == before_completion + 1
