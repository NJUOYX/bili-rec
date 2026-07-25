"""Tests for FLV IO."""

from __future__ import annotations

from io import BytesIO

import pytest

from birec.flv import FlvDataError, FlvReader, FlvWriter

from .conftest import (
    make_audio_tag,
    make_flv_bytes,
    make_flv_header,
    make_script_tag,
    make_video_tag,
)


class TestFlvWriter:
    """Tests for FlvWriter."""

    def test_write_header(self) -> None:
        stream = BytesIO()
        writer = FlvWriter(stream)
        header = make_flv_header()
        size = writer.write_header(header)
        assert size == 9 + 4  # header + back_pointer
        assert stream.getvalue()[:3] == b"FLV"

    def test_write_video_tag(self) -> None:
        stream = BytesIO()
        writer = FlvWriter(stream)
        writer.write_header(make_flv_header())
        tag = make_video_tag(body=b"\x01\x02\x03")
        size = writer.write_tag(tag)
        assert size == tag.tag_size + 4

    def test_write_audio_tag(self) -> None:
        stream = BytesIO()
        writer = FlvWriter(stream)
        writer.write_header(make_flv_header())
        tag = make_audio_tag(body=b"\x01\x02\x03")
        size = writer.write_tag(tag)
        assert size == tag.tag_size + 4

    def test_write_script_tag(self) -> None:
        stream = BytesIO()
        writer = FlvWriter(stream)
        writer.write_header(make_flv_header())
        tag = make_script_tag(body=b"\x02\x00\x0aonMetaData")
        size = writer.write_tag(tag)
        assert size == tag.tag_size + 4

    def test_write_tags(self) -> None:
        stream = BytesIO()
        writer = FlvWriter(stream)
        writer.write_header(make_flv_header())
        tags = [
            make_video_tag(timestamp=0),
            make_audio_tag(timestamp=0),
            make_video_tag(timestamp=100),
        ]
        size = writer.write_tags(tags)
        assert size == sum(t.tag_size + 4 for t in tags)


class TestFlvReader:
    """Tests for FlvReader."""

    def test_read_header(self) -> None:
        data = make_flv_bytes()
        stream = BytesIO(data)
        reader = FlvReader(stream)
        header = reader.read_header()
        assert header.signature == "FLV"
        assert header.version == 1

    def test_read_video_tag(self) -> None:
        tag = make_video_tag(body=b"\x01\x02\x03")
        data = make_flv_bytes(tags=[tag])
        stream = BytesIO(data)
        reader = FlvReader(stream)
        reader.read_header()
        read_tag = reader.read_tag()
        assert read_tag.is_video_tag()
        assert read_tag.timestamp == tag.timestamp
        assert read_tag.body == tag.body

    def test_read_audio_tag(self) -> None:
        tag = make_audio_tag(body=b"\x04\x05\x06")
        data = make_flv_bytes(tags=[tag])
        stream = BytesIO(data)
        reader = FlvReader(stream)
        reader.read_header()
        read_tag = reader.read_tag()
        assert read_tag.is_audio_tag()
        assert read_tag.timestamp == tag.timestamp
        assert read_tag.body == tag.body

    def test_read_script_tag(self) -> None:
        tag = make_script_tag(body=b"\x02\x00\x0aonMetaData")
        data = make_flv_bytes(tags=[tag])
        stream = BytesIO(data)
        reader = FlvReader(stream)
        reader.read_header()
        read_tag = reader.read_tag()
        assert read_tag.is_script_tag()
        assert read_tag.body == tag.body

    def test_read_tags(self) -> None:
        tags = [
            make_video_tag(timestamp=0),
            make_audio_tag(timestamp=0),
            make_video_tag(timestamp=100),
        ]
        data = make_flv_bytes(tags=tags)
        stream = BytesIO(data)
        reader = FlvReader(stream)
        reader.read_header()
        read_tags = list(reader.read_tags())
        assert len(read_tags) == 3
        assert read_tags[0].is_video_tag()
        assert read_tags[1].is_audio_tag()
        assert read_tags[2].is_video_tag()

    def test_read_tag_no_body(self) -> None:
        tag = make_video_tag(body=b"\x01\x02\x03")
        data = make_flv_bytes(tags=[tag])
        stream = BytesIO(data)
        reader = FlvReader(stream)
        reader.read_header()
        read_tag = reader.read_tag(no_body=True)
        assert read_tag.body == b""
        # Can read body separately
        body = reader.read_body(read_tag)
        assert body == tag.body

    def test_read_empty_stream(self) -> None:
        stream = BytesIO(b"")
        reader = FlvReader(stream)
        with pytest.raises(EOFError):
            reader.read_header()

    def test_invalid_back_pointer(self) -> None:
        # Create valid FLV data
        data = make_flv_bytes(tags=[make_video_tag()])
        # Corrupt the back-pointer (last 4 bytes before EOF)
        corrupted = bytearray(data)
        corrupted[-4:] = b"\xff\xff\xff\xff"
        stream = BytesIO(bytes(corrupted))
        reader = FlvReader(stream)
        reader.read_header()
        with pytest.raises(FlvDataError):
            reader.read_tag()


class TestRoundTrip:
    """Test write then read round-trip."""

    def test_round_trip_video(self) -> None:
        original_tag = make_video_tag(
            timestamp=12345,
            body=b"\x00\x01\x02\x03\x04\x05",
        )
        data = make_flv_bytes(tags=[original_tag])
        stream = BytesIO(data)
        reader = FlvReader(stream)
        reader.read_header()
        read_tag = reader.read_tag()
        assert read_tag.timestamp == original_tag.timestamp
        assert read_tag.body == original_tag.body
        assert read_tag.frame_type == original_tag.frame_type
        assert read_tag.avc_packet_type == original_tag.avc_packet_type

    def test_round_trip_audio(self) -> None:
        original_tag = make_audio_tag(
            timestamp=54321,
            body=b"\xaa\xbb\xcc\xdd",
        )
        data = make_flv_bytes(tags=[original_tag])
        stream = BytesIO(data)
        reader = FlvReader(stream)
        reader.read_header()
        read_tag = reader.read_tag()
        assert read_tag.timestamp == original_tag.timestamp
        assert read_tag.body == original_tag.body
        assert read_tag.sound_format == original_tag.sound_format
        assert read_tag.aac_packet_type == original_tag.aac_packet_type

    def test_round_trip_multiple_tags(self) -> None:
        original_tags = [
            make_video_tag(timestamp=0, body=b"\x01"),
            make_audio_tag(timestamp=0, body=b"\x02"),
            make_video_tag(timestamp=33, body=b"\x03"),
            make_audio_tag(timestamp=33, body=b"\x04"),
        ]
        data = make_flv_bytes(tags=original_tags)
        stream = BytesIO(data)
        reader = FlvReader(stream)
        reader.read_header()
        read_tags = list(reader.read_tags())
        assert len(read_tags) == len(original_tags)
        for orig, read in zip(original_tags, read_tags, strict=True):
            assert read.timestamp == orig.timestamp
            assert read.body == orig.body
