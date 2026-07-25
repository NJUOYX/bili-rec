"""FLV common helper functions."""

from __future__ import annotations

from typing import Any, TypeGuard

from .models import (
    AudioTag,
    AVCPacketType,
    CodecID,
    FlvTag,
    FrameType,
    ScriptTag,
    TagType,
    VideoTag,
)

__all__ = (
    "is_audio_tag",
    "is_video_tag",
    "is_script_tag",
    "is_data_tag",
    "is_audio_data_tag",
    "is_video_data_tag",
    "is_sequence_header",
    "is_audio_sequence_header",
    "is_video_sequence_header",
    "is_video_nalu_keyframe",
    "is_avc_end_sequence",
    "is_avc_end_sequence_tag",
    "create_avc_end_sequence_tag",
)


def is_audio_tag(tag: FlvTag) -> TypeGuard[AudioTag]:
    """Check if tag is an audio tag."""
    return tag.tag_type == TagType.AUDIO


def is_video_tag(tag: FlvTag) -> TypeGuard[VideoTag]:
    """Check if tag is a video tag."""
    return tag.tag_type == TagType.VIDEO


def is_script_tag(tag: FlvTag) -> TypeGuard[ScriptTag]:
    """Check if tag is a script tag."""
    return tag.tag_type == TagType.SCRIPT


def is_data_tag(tag: FlvTag) -> TypeGuard[AudioTag | VideoTag]:
    """Check if tag is a data tag (audio raw or video NALU)."""
    return is_audio_data_tag(tag) or is_video_data_tag(tag)


def is_audio_data_tag(tag: FlvTag) -> TypeGuard[AudioTag]:
    """Check if tag is an audio data tag (AAC raw)."""
    return is_audio_tag(tag) and tag.is_aac_raw()


def is_video_data_tag(tag: FlvTag) -> TypeGuard[VideoTag]:
    """Check if tag is a video data tag (AVC NALU)."""
    return is_video_tag(tag) and tag.is_avc_nalu()


def is_sequence_header(tag: FlvTag) -> TypeGuard[AudioTag | VideoTag]:
    """Check if tag is a sequence header (audio or video)."""
    return is_audio_sequence_header(tag) or is_video_sequence_header(tag)


def is_audio_sequence_header(tag: FlvTag) -> TypeGuard[AudioTag]:
    """Check if tag is an audio sequence header (AAC header)."""
    return is_audio_tag(tag) and tag.is_aac_header()


def is_video_sequence_header(tag: FlvTag) -> TypeGuard[VideoTag]:
    """Check if tag is a video sequence header (AVC header)."""
    return is_video_tag(tag) and tag.is_avc_header()


def is_video_nalu_keyframe(tag: FlvTag) -> TypeGuard[VideoTag]:
    """Check if tag is a video keyframe NALU."""
    return is_video_tag(tag) and tag.is_keyframe() and tag.is_avc_nalu()


def is_avc_end_sequence(tag: FlvTag) -> TypeGuard[VideoTag]:
    """Check if tag is an AVC end of sequence."""
    return is_video_tag(tag) and tag.is_avc_end()


def is_avc_end_sequence_tag(value: Any) -> TypeGuard[VideoTag]:
    """Check if value is an AVC end of sequence tag."""
    return isinstance(value, FlvTag) and is_avc_end_sequence(value)


def create_avc_end_sequence_tag(offset: int = 0, timestamp: int = 0) -> VideoTag:
    """Create an AVC end of sequence tag."""
    return VideoTag(
        offset=offset,
        filtered=False,
        tag_type=TagType.VIDEO,
        data_size=5,
        timestamp=timestamp,
        stream_id=timestamp,
        frame_type=FrameType.KEY_FRAME,
        codec_id=CodecID.AVC,
        avc_packet_type=AVCPacketType.AVC_END_OF_SEQUENCE,
        composition_time=0,
    )
