"""Tests for parse operator."""

from __future__ import annotations

from io import BytesIO

import pytest
import reactivex
from reactivex.subject import Subject
from reactivex.testing import TestScheduler

from birec.flv import FlvHeader, FlvTag, StreamBuffer
from birec.flv.common import is_avc_end_sequence_tag
from birec.flv.exceptions import (
    FlvDataError,
    FlvStreamCorruptedError,
    FlvTagError,
)
from birec.flv.format import FlvParser
from birec.flv.operators import parse
from birec.flv.operators.typing import FLVStreamItem
from birec.flv.struct_io import RandomIO

from ..conftest import (
    make_audio_tag,
    make_flv_bytes,
    make_flv_header,
    make_video_tag,
)


class TestParse:
    """Tests for parse operator."""

    def test_parse_header(self) -> None:
        """Test parsing FLV header with precise field assertions."""
        data = make_flv_bytes()
        stream = BytesIO(data)

        results: list[FLVStreamItem] = []
        source = reactivex.of(stream)
        parsed = source.pipe(parse())
        parsed.subscribe(on_next=results.append)

        assert len(results) == 1
        header = results[0]
        assert isinstance(header, FlvHeader)
        assert header.signature == "FLV"
        assert header.version == 1
        assert header.data_offset == 9
        # Default make_flv_header has both video and audio
        assert header.has_video() is True
        assert header.has_audio() is True
        assert header.type_flag == 0b0000_0101

    def test_parse_header_audio_only(self) -> None:
        """Header type_flag must reflect the actual streams present."""
        hdr = make_flv_header(has_video=False, has_audio=True)
        data = make_flv_bytes(header=hdr)
        stream = BytesIO(data)

        results: list[FLVStreamItem] = []
        reactivex.of(stream).pipe(parse()).subscribe(on_next=results.append)

        header = results[0]
        assert isinstance(header, FlvHeader)
        assert header.has_video() is False
        assert header.has_audio() is True
        assert header.type_flag == 0b0000_0100

    def test_parse_video_tag(self) -> None:
        """Test parsing video tag with precise field assertions."""
        tag = make_video_tag(body=b"\x01\x02\x03", timestamp=42)
        data = make_flv_bytes(tags=[tag])
        stream = BytesIO(data)

        results: list[FLVStreamItem] = []
        source = reactivex.of(stream)
        parsed = source.pipe(parse())
        parsed.subscribe(on_next=results.append)

        # Header + video tag + AVC end sequence tag
        assert len(results) == 3
        assert isinstance(results[0], FlvHeader)
        video = results[1]
        assert isinstance(video, FlvTag)
        assert video.is_video_tag()
        assert video.timestamp == 42
        assert video.data_size == 5 + 3  # video header + body
        assert video.body == b"\x01\x02\x03"
        # AVC end sequence tag
        end_tag = results[2]
        assert isinstance(end_tag, FlvTag)
        assert end_tag.is_video_tag()
        assert is_avc_end_sequence_tag(end_tag)
        assert end_tag.timestamp == 42

    def test_parse_audio_tag(self) -> None:
        """Test parsing audio tag with precise field assertions."""
        tag = make_audio_tag(body=b"\x04\x05\x06", timestamp=77)
        data = make_flv_bytes(tags=[tag])
        stream = BytesIO(data)

        results: list[FLVStreamItem] = []
        source = reactivex.of(stream)
        parsed = source.pipe(parse())
        parsed.subscribe(on_next=results.append)

        # Header + audio tag (no AVC end for audio-only)
        assert len(results) == 2
        assert isinstance(results[0], FlvHeader)
        audio = results[1]
        assert isinstance(audio, FlvTag)
        assert audio.is_audio_tag()
        assert audio.timestamp == 77
        assert audio.data_size == 2 + 3  # audio header + body
        assert audio.body == b"\x04\x05\x06"

    def test_parse_multiple_tags(self) -> None:
        """Test parsing multiple tags with timestamp ordering."""
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
        assert results[1].timestamp == 0
        assert isinstance(results[2], FlvTag)
        assert results[2].is_audio_tag()
        assert results[2].timestamp == 0
        assert isinstance(results[3], FlvTag)
        assert results[3].is_video_tag()
        assert results[3].timestamp == 100
        # AVC end sequence inherits last video tag timestamp
        assert isinstance(results[4], FlvTag)
        assert is_avc_end_sequence_tag(results[4])
        assert results[4].timestamp == 100

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

    def test_a_second_flv_header_continues_the_same_recording(self) -> None:
        """Regression: a reconnect must not cost the rest of the recording.

        One HTTP connection is one FLV document, so a live download that
        reconnects — which it does, repeatedly, over hours — hands the parser a
        second file header in the middle of the byte stream. That header used to
        be read where a tag was expected: ``0x46`` masks down to tag type 6,
        which no enum accepts, so the stream was declared corrupt and the
        subscription ended. Downloading carried on, the byte counter carried on,
        and not one further byte reached the disk — the file simply stopped
        growing while the UI still said "recording".

        The header is consumed instead, and the tags behind it are recorded as
        part of the same file.
        """
        first = make_flv_bytes(tags=[make_video_tag(timestamp=0)])
        # A whole second document, exactly as a reconnected CDN sends it.
        second = make_flv_bytes(tags=[make_video_tag(timestamp=40, body=b"\x02" * 8)])
        buffer = StreamBuffer()
        source: Subject[RandomIO] = Subject()

        results: list[FLVStreamItem] = []
        errors: list[Exception] = []
        source.pipe(parse(resumable=True)).subscribe(
            on_next=results.append,
            on_error=errors.append,
        )

        buffer.append(first + second)
        source.on_next(buffer)

        assert errors == []
        # Only the first header reaches the file; a second one written into the
        # middle of a recording is not something a player can read.
        assert len([i for i in results if isinstance(i, FlvHeader)]) == 1
        tags = [i for i in results if isinstance(i, FlvTag)]
        assert len(tags) == 2, "the tags after the reconnect were dropped"
        assert tags[1].body == b"\x02" * 8

    def test_junk_where_a_tag_header_belongs_is_a_stream_error(self) -> None:
        """Bytes that are neither a tag nor a new document are corruption.

        Tolerating the reconnect header must not turn into tolerating anything:
        a byte that cannot be a tag type still ends the stream, and it does so
        as an FLV error rather than a bare ``ValueError`` escaping the layer.
        """
        # Tag type 0 is not one FLV defines, with enough bytes behind it that
        # the parser commits rather than waiting for more.
        junk = b"\x00" * 24
        data = make_flv_bytes(tags=[make_video_tag()]) + junk
        buffer = StreamBuffer()
        source: Subject[RandomIO] = Subject()

        results: list[FLVStreamItem] = []
        errors: list[Exception] = []
        source.pipe(parse(resumable=True)).subscribe(
            on_next=results.append,
            on_error=errors.append,
        )

        buffer.append(data)
        source.on_next(buffer)

        assert len(errors) == 1
        assert isinstance(errors[0], FlvStreamCorruptedError)
        # The tags before the junk still came through.
        assert any(isinstance(item, FlvTag) for item in results)


class TestTagHeaderParsing:
    """Malformed bytes must be reported as FLV errors, whichever field they hit."""

    def test_an_unknown_tag_type_is_an_flv_error(self) -> None:
        parser = FlvParser(BytesIO(b""))
        with pytest.raises(FlvTagError):
            parser.parse_flv_tag_header(b"\x06" + b"\x00" * 10)

    def test_an_unknown_sound_format_is_an_flv_error(self) -> None:
        parser = FlvParser(BytesIO(b""))
        # High nibble 0xD is not a sound format any decoder knows.
        with pytest.raises(FlvTagError):
            parser.parse_audio_tag_header(b"\xd0\x00")

    def test_an_unknown_frame_type_is_an_flv_error(self) -> None:
        parser = FlvParser(BytesIO(b""))
        with pytest.raises(FlvTagError):
            parser.parse_video_tag_header(b"\xf7\x00\x00\x00\x00")

    def test_an_unsupported_codec_is_still_reported_as_data(self) -> None:
        """A known-but-unsupported value keeps its existing, distinct error."""
        parser = FlvParser(BytesIO(b""))
        with pytest.raises(FlvDataError) as exc_info:
            # Frame type 1 (keyframe), codec 2 (Sorenson H.263): valid, unsupported.
            parser.parse_video_tag_header(b"\x12\x00\x00\x00\x00")
        assert "Unsupported video codec" in str(exc_info.value)
