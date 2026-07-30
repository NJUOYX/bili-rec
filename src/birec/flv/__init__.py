"""FLV engine for parsing and processing FLV streams."""

from __future__ import annotations

from . import common, exceptions, format, io, models, struct_io, utils
from .exceptions import (
    FlvDataError,
    FlvFileCorruptedError,
    FlvHeaderError,
    FlvStreamCorruptedError,
    FlvTagError,
)
from .format import FlvDumper, FlvParser
from .io import FlvReader, FlvWriter
from .models import (
    BACK_POINTER_SIZE,
    TAG_HEADER_SIZE,
    AACPacketType,
    AudioTag,
    AudioTagHeader,
    AVCPacketType,
    CodecID,
    FlvHeader,
    FlvTag,
    FlvTagHeader,
    FrameType,
    ScriptTag,
    SoundFormat,
    SoundRate,
    SoundSize,
    SoundType,
    TagType,
    VideoTag,
    VideoTagHeader,
)
from .stream_buffer import StreamBuffer
from .struct_io import RandomIO, StructReader, StructWriter
from .utils import AutoRollbacker, OffsetRepositor, format_timestamp

__all__ = (
    # Submodules
    "common",
    "exceptions",
    "format",
    "io",
    "models",
    "struct_io",
    "utils",
    # Exceptions
    "FlvDataError",
    "FlvFileCorruptedError",
    "FlvHeaderError",
    "FlvStreamCorruptedError",
    "FlvTagError",
    # Format
    "FlvDumper",
    "FlvParser",
    # IO
    "FlvReader",
    "FlvWriter",
    # Models
    "AACPacketType",
    "AudioTag",
    "AudioTagHeader",
    "AVCPacketType",
    "BACK_POINTER_SIZE",
    "CodecID",
    "FlvHeader",
    "FlvTag",
    "FlvTagHeader",
    "FrameType",
    "ScriptTag",
    "SoundFormat",
    "SoundRate",
    "SoundSize",
    "SoundType",
    "TAG_HEADER_SIZE",
    "TagType",
    "VideoTag",
    "VideoTagHeader",
    # StructIO
    "RandomIO",
    "StreamBuffer",
    "StructReader",
    "StructWriter",
    # Utils
    "AutoRollbacker",
    "OffsetRepositor",
    "format_timestamp",
)
