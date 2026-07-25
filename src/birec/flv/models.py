"""FLV data models: Header, Tags, and enumerations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from enum import IntEnum
from typing import Any, Final

from ..utils.hash import cksum

__all__ = (
    "TagType",
    "FrameType",
    "CodecID",
    "AVCPacketType",
    "SoundFormat",
    "SoundRate",
    "SoundSize",
    "SoundType",
    "AACPacketType",
    "FlvHeader",
    "FlvTagHeader",
    "AudioTagHeader",
    "VideoTagHeader",
    "FlvTag",
    "AudioTag",
    "VideoTag",
    "ScriptTag",
    "BACK_POINTER_SIZE",
    "TAG_HEADER_SIZE",
    "AUDIO_TAG_HEADER_SIZE",
    "VIDEO_TAG_HEADER_SIZE",
)


class TagType(IntEnum):
    """FLV tag type."""

    AUDIO = 8
    VIDEO = 9
    SCRIPT = 18


class FrameType(IntEnum):
    """Video frame type."""

    KEY_FRAME = 1
    INNER_FRAME = 2
    DISPOSABLE_INNER_FRAME = 3
    GENERATED_KEY_FRAME = 4
    VIDEO_INFO = 5


class CodecID(IntEnum):
    """Video codec ID."""

    SORENSON_H263 = 2
    SCREEN_VIDEO = 3
    ON2_VP6 = 4
    ON2_VP6_WITH_ALPHA_CHANNEL = 5
    SCREEN_VIDEO_V2 = 6
    AVC = 7


class AVCPacketType(IntEnum):
    """AVC packet type."""

    AVC_SEQUENCE_HEADER = 0
    AVC_NALU = 1
    AVC_END_OF_SEQUENCE = 2


class SoundFormat(IntEnum):
    """Audio sound format."""

    LINEAR_PCM_PLATFORM_ENDIAN = 0
    ADPCM = 1
    MP3 = 2
    LINEAR_PCM_LITTLE_ENDIAN = 3
    NELLYMOSER_16KHZ_MONO = 4
    NELLYMOSER_8KHZ_MONO = 5
    NELLYMOSER = 6
    G711_A_LAW_LOGARITHMIC_PCM = 7
    G711_MU_LAW_LOGARITHMIC_PCM = 8
    AAC = 10
    SPEEX = 11
    MP3_8KHZ = 14
    DEVICE_SPECIFIC_SOUND = 15


class SoundRate(IntEnum):
    """Audio sound rate."""

    F_5_5KHZ = 0
    F_11KHZ = 1
    F_22KHZ = 2
    F_44KHZ = 3


class SoundSize(IntEnum):
    """Audio sample size."""

    SAMPLES_8BIT = 0
    SAMPLES_16BIT = 1


class SoundType(IntEnum):
    """Audio channel type."""

    MONO = 0
    STEREO = 1


class AACPacketType(IntEnum):
    """AAC packet type."""

    AAC_SEQUENCE_HEADER = 0
    AAC_RAW = 1


BACK_POINTER_SIZE: Final[int] = 4
TAG_HEADER_SIZE: Final[int] = 11
AUDIO_TAG_HEADER_SIZE: Final[int] = 2
VIDEO_TAG_HEADER_SIZE: Final[int] = 5


@dataclass(frozen=True, slots=True)
class FlvHeader:
    """FLV file header."""

    signature: str
    version: int
    type_flag: int
    data_offset: int

    def has_video(self) -> bool:
        """Check if video is present."""
        return bool(self.type_flag & 0b0000_0001)

    def has_audio(self) -> bool:
        """Check if audio is present."""
        return bool(self.type_flag & 0b0000_0100)

    def set_video_flag(self, value: bool) -> FlvHeader:
        """Return a new header with video flag set."""
        type_flag = self.type_flag | 1 if value else self.type_flag & ~1
        return replace(self, type_flag=type_flag)

    def set_audio_flag(self, value: bool) -> FlvHeader:
        """Return a new header with audio flag set."""
        type_flag = self.type_flag | 4 if value else self.type_flag & ~4
        return replace(self, type_flag=type_flag)

    def __len__(self) -> int:
        return self.size

    @property
    def size(self) -> int:
        """Header size in bytes."""
        return self.data_offset


@dataclass(frozen=True, slots=True)
class FlvTagHeader:
    """FLV tag header (11 bytes)."""

    filtered: bool
    tag_type: TagType
    data_size: int
    timestamp: int
    stream_id: int


@dataclass(frozen=True, slots=True)
class AudioTagHeader:
    """Audio tag header."""

    sound_format: SoundFormat
    sound_rate: SoundRate
    sound_size: SoundSize
    sound_type: SoundType
    aac_packet_type: AACPacketType | None


@dataclass(frozen=True, slots=True)
class VideoTagHeader:
    """Video tag header."""

    frame_type: FrameType
    codec_id: CodecID
    avc_packet_type: AVCPacketType | None
    composition_time: int | None


@dataclass(frozen=True, slots=True, kw_only=True)
class FlvTag(ABC, FlvTagHeader):
    """Base class for FLV tags."""

    offset: int
    body: bytes = field(default=b"", repr=False)

    def __len__(self) -> int:
        return self.tag_size

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}("
            f"offset={self.offset}, "
            f"timestamp={self.timestamp}, "
            f"data_size={self.data_size}, "
            f"body=cksum:{cksum(self.body) if self.body else 'empty'})"
        )

    @property
    @abstractmethod
    def header_size(self) -> int:
        """Size of the tag-specific header."""
        ...

    @property
    def tag_size(self) -> int:
        """Total tag size (header + data)."""
        return TAG_HEADER_SIZE + self.data_size

    @property
    def body_offset(self) -> int:
        """Offset of body data in the stream."""
        return self.offset + TAG_HEADER_SIZE + self.header_size

    @property
    def body_size(self) -> int:
        """Size of body data."""
        return self.data_size - self.header_size

    @property
    def tag_end_offset(self) -> int:
        """Offset of tag end."""
        return self.offset + self.tag_size

    @property
    def next_tag_offset(self) -> int:
        """Offset of next tag (after back pointer)."""
        return self.tag_end_offset + BACK_POINTER_SIZE

    def is_audio_tag(self) -> bool:
        """Check if this is an audio tag."""
        return self.tag_type == TagType.AUDIO

    def is_video_tag(self) -> bool:
        """Check if this is a video tag."""
        return self.tag_type == TagType.VIDEO

    def is_script_tag(self) -> bool:
        """Check if this is a script tag."""
        return self.tag_type == TagType.SCRIPT

    def is_the_same_as(self, another: FlvTag) -> bool:
        """Check if two tags have the same content."""
        return (
            self.tag_type == another.tag_type
            and self.data_size == another.data_size
            and self.body == another.body
        )

    def evolve(self, **changes: Any) -> FlvTag:
        """Return a new tag with the given changes."""
        if "body" in changes:
            body = changes["body"]
            changes["data_size"] = self.header_size + len(body)
        return replace(self, **changes)


@dataclass(frozen=True, slots=True, kw_only=True)
class AudioTag(FlvTag):
    """Audio tag."""

    sound_format: SoundFormat
    sound_rate: SoundRate
    sound_size: SoundSize
    sound_type: SoundType
    aac_packet_type: AACPacketType

    @property
    def header_size(self) -> int:
        if self.sound_format != SoundFormat.AAC:
            return 1
        return 2

    def is_aac_format(self) -> bool:
        """Check if AAC format."""
        return self.sound_format == SoundFormat.AAC

    def is_aac_header(self) -> bool:
        """Check if AAC sequence header."""
        return self.aac_packet_type == AACPacketType.AAC_SEQUENCE_HEADER

    def is_aac_raw(self) -> bool:
        """Check if AAC raw data."""
        return self.aac_packet_type == AACPacketType.AAC_RAW


@dataclass(frozen=True, slots=True, kw_only=True)
class VideoTag(FlvTag):
    """Video tag."""

    frame_type: FrameType
    codec_id: CodecID
    avc_packet_type: AVCPacketType
    composition_time: int

    @property
    def header_size(self) -> int:
        if self.codec_id != CodecID.AVC:
            return 1
        return 5

    def is_avc_header(self) -> bool:
        """Check if AVC sequence header."""
        return self.avc_packet_type == AVCPacketType.AVC_SEQUENCE_HEADER

    def is_avc_nalu(self) -> bool:
        """Check if AVC NALU data."""
        return self.avc_packet_type == AVCPacketType.AVC_NALU

    def is_avc_end(self) -> bool:
        """Check if AVC end of sequence."""
        return self.avc_packet_type == AVCPacketType.AVC_END_OF_SEQUENCE

    def is_keyframe(self) -> bool:
        """Check if keyframe."""
        return self.frame_type == FrameType.KEY_FRAME


@dataclass(frozen=True, slots=True, kw_only=True)
class ScriptTag(FlvTag):
    """Script tag (metadata)."""

    @property
    def header_size(self) -> int:
        return 0
