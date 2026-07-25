"""Test fixtures for FLV tests."""

from __future__ import annotations

from io import BytesIO

from birec.flv import (
    AACPacketType,
    AudioTag,
    AVCPacketType,
    CodecID,
    FlvHeader,
    FlvWriter,
    FrameType,
    ScriptTag,
    SoundFormat,
    SoundRate,
    SoundSize,
    SoundType,
    TagType,
    VideoTag,
)


def make_flv_header(
    *,
    has_video: bool = True,
    has_audio: bool = True,
) -> FlvHeader:
    """Create a test FLV header."""
    type_flag = 0
    if has_video:
        type_flag |= 0b0000_0001
    if has_audio:
        type_flag |= 0b0000_0100
    return FlvHeader(
        signature="FLV",
        version=1,
        type_flag=type_flag,
        data_offset=9,
    )


def make_video_tag(
    *,
    offset: int = 0,
    timestamp: int = 0,
    frame_type: FrameType = FrameType.KEY_FRAME,
    avc_packet_type: AVCPacketType = AVCPacketType.AVC_NALU,
    body: bytes = b"\x00" * 10,
) -> VideoTag:
    """Create a test video tag."""
    return VideoTag(
        offset=offset,
        filtered=False,
        tag_type=TagType.VIDEO,
        data_size=5 + len(body),
        timestamp=timestamp,
        stream_id=timestamp,
        frame_type=frame_type,
        codec_id=CodecID.AVC,
        avc_packet_type=avc_packet_type,
        composition_time=0,
        body=body,
    )


def make_audio_tag(
    *,
    offset: int = 0,
    timestamp: int = 0,
    aac_packet_type: AACPacketType = AACPacketType.AAC_RAW,
    body: bytes = b"\x00" * 10,
) -> AudioTag:
    """Create a test audio tag."""
    return AudioTag(
        offset=offset,
        filtered=False,
        tag_type=TagType.AUDIO,
        data_size=2 + len(body),
        timestamp=timestamp,
        stream_id=timestamp,
        sound_format=SoundFormat.AAC,
        sound_rate=SoundRate.F_44KHZ,
        sound_size=SoundSize.SAMPLES_16BIT,
        sound_type=SoundType.STEREO,
        aac_packet_type=aac_packet_type,
        body=body,
    )


def make_script_tag(
    *,
    offset: int = 0,
    timestamp: int = 0,
    body: bytes = b"\x02\x00\x0aonMetaData",
) -> ScriptTag:
    """Create a test script tag."""
    return ScriptTag(
        offset=offset,
        filtered=False,
        tag_type=TagType.SCRIPT,
        data_size=len(body),
        timestamp=timestamp,
        stream_id=0,
        body=body,
    )


def make_flv_bytes(
    *,
    header: FlvHeader | None = None,
    tags: list[VideoTag | AudioTag | ScriptTag] | None = None,
) -> bytes:
    """Create FLV bytes from header and tags."""
    stream = BytesIO()
    writer = FlvWriter(stream)
    writer.write_header(header or make_flv_header())
    if tags:
        writer.write_tags(tags)
    return stream.getvalue()
