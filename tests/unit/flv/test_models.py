"""Tests for FLV models."""

from __future__ import annotations

from birec.flv import (
    AACPacketType,
    AVCPacketType,
    FrameType,
)

from .conftest import make_audio_tag, make_flv_header, make_script_tag, make_video_tag


class TestFlvHeader:
    """Tests for FlvHeader."""

    def test_has_video(self) -> None:
        header = make_flv_header(has_video=True, has_audio=False)
        assert header.has_video() is True
        assert header.has_audio() is False

    def test_has_audio(self) -> None:
        header = make_flv_header(has_video=False, has_audio=True)
        assert header.has_video() is False
        assert header.has_audio() is True

    def test_set_video_flag(self) -> None:
        header = make_flv_header(has_video=False, has_audio=True)
        new_header = header.set_video_flag(True)
        assert new_header.has_video() is True
        assert new_header.has_audio() is True

    def test_set_audio_flag(self) -> None:
        header = make_flv_header(has_video=True, has_audio=False)
        new_header = header.set_audio_flag(True)
        assert new_header.has_video() is True
        assert new_header.has_audio() is True

    def test_len(self) -> None:
        header = make_flv_header()
        assert len(header) == 9


class TestVideoTag:
    """Tests for VideoTag."""

    def test_is_keyframe(self) -> None:
        tag = make_video_tag(frame_type=FrameType.KEY_FRAME)
        assert tag.is_keyframe() is True

    def test_is_not_keyframe(self) -> None:
        tag = make_video_tag(frame_type=FrameType.INNER_FRAME)
        assert tag.is_keyframe() is False

    def test_is_avc_header(self) -> None:
        tag = make_video_tag(avc_packet_type=AVCPacketType.AVC_SEQUENCE_HEADER)
        assert tag.is_avc_header() is True

    def test_is_avc_nalu(self) -> None:
        tag = make_video_tag(avc_packet_type=AVCPacketType.AVC_NALU)
        assert tag.is_avc_nalu() is True

    def test_is_avc_end(self) -> None:
        tag = make_video_tag(avc_packet_type=AVCPacketType.AVC_END_OF_SEQUENCE)
        assert tag.is_avc_end() is True

    def test_tag_size(self) -> None:
        body = b"\x00" * 10
        tag = make_video_tag(body=body)
        # 11 (tag header) + 5 (video header) + 10 (body) = 26
        assert tag.tag_size == 11 + 5 + len(body)

    def test_header_size(self) -> None:
        tag = make_video_tag()
        assert tag.header_size == 5

    def test_evolve(self) -> None:
        tag = make_video_tag(timestamp=100)
        new_tag = tag.evolve(timestamp=200)
        assert new_tag.timestamp == 200
        assert tag.timestamp == 100  # Original unchanged


class TestAudioTag:
    """Tests for AudioTag."""

    def test_is_aac_format(self) -> None:
        tag = make_audio_tag()
        assert tag.is_aac_format() is True

    def test_is_aac_header(self) -> None:
        tag = make_audio_tag(aac_packet_type=AACPacketType.AAC_SEQUENCE_HEADER)
        assert tag.is_aac_header() is True

    def test_is_aac_raw(self) -> None:
        tag = make_audio_tag(aac_packet_type=AACPacketType.AAC_RAW)
        assert tag.is_aac_raw() is True

    def test_tag_size(self) -> None:
        body = b"\x00" * 10
        tag = make_audio_tag(body=body)
        # 11 (tag header) + 2 (audio header) + 10 (body) = 23
        assert tag.tag_size == 11 + 2 + len(body)

    def test_header_size(self) -> None:
        tag = make_audio_tag()
        assert tag.header_size == 2


class TestScriptTag:
    """Tests for ScriptTag."""

    def test_header_size(self) -> None:
        tag = make_script_tag()
        assert tag.header_size == 0

    def test_tag_size(self) -> None:
        body = b"\x02\x00\x0aonMetaData"
        tag = make_script_tag(body=body)
        assert tag.tag_size == 11 + len(body)


class TestFlvTagMethods:
    """Tests for FlvTag common methods."""

    def test_is_audio_tag(self) -> None:
        tag = make_audio_tag()
        assert tag.is_audio_tag() is True
        assert tag.is_video_tag() is False
        assert tag.is_script_tag() is False

    def test_is_video_tag(self) -> None:
        tag = make_video_tag()
        assert tag.is_video_tag() is True
        assert tag.is_audio_tag() is False
        assert tag.is_script_tag() is False

    def test_is_script_tag(self) -> None:
        tag = make_script_tag()
        assert tag.is_script_tag() is True
        assert tag.is_audio_tag() is False
        assert tag.is_video_tag() is False

    def test_is_the_same_as(self) -> None:
        tag1 = make_video_tag(body=b"\x01\x02\x03")
        tag2 = make_video_tag(body=b"\x01\x02\x03")
        tag3 = make_video_tag(body=b"\x04\x05\x06")
        assert tag1.is_the_same_as(tag2) is True
        assert tag1.is_the_same_as(tag3) is False

    def test_offsets(self) -> None:
        tag = make_video_tag(offset=100, body=b"\x00" * 10)
        assert tag.offset == 100
        assert tag.body_offset == 100 + 11 + 5  # offset + tag_header + video_header
        assert tag.body_size == 10
        assert tag.tag_end_offset == 100 + tag.tag_size
        assert tag.next_tag_offset == tag.tag_end_offset + 4  # + back_pointer
