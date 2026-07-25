"""AMF0 (Action Message Format) encoding and decoding."""

from __future__ import annotations

import struct
from io import BytesIO
from typing import Any

__all__ = (
    "AMF0Number",
    "AMF0Boolean",
    "AMF0String",
    "AMF0Object",
    "AMF0Null",
    "AMF0ECMAArray",
    "AMF0StrictArray",
    "AMF0Date",
    "load",
    "dump",
    "loads",
    "dumps",
)

# AMF0 type markers
MARKER_NUMBER = 0x00
MARKER_BOOLEAN = 0x01
MARKER_STRING = 0x02
MARKER_OBJECT = 0x03
MARKER_NULL = 0x05
MARKER_UNDEFINED = 0x06
MARKER_ECMA_ARRAY = 0x08
MARKER_OBJECT_END = 0x09
MARKER_STRICT_ARRAY = 0x0A
MARKER_DATE = 0x0B
MARKER_LONG_STRING = 0x0C


class AMF0Number:
    """AMF0 Number type."""

    def __init__(self, value: float) -> None:
        self.value = value


class AMF0Boolean:
    """AMF0 Boolean type."""

    def __init__(self, value: bool) -> None:
        self.value = value


class AMF0String:
    """AMF0 String type."""

    def __init__(self, value: str) -> None:
        self.value = value


class AMF0Object:
    """AMF0 Object type."""

    def __init__(self, value: dict[str, Any]) -> None:
        self.value = value


class AMF0Null:
    """AMF0 Null type."""


class AMF0Undefined:
    """AMF0 Undefined type."""


class AMF0ECMAArray:
    """AMF0 ECMA Array type."""

    def __init__(self, value: dict[str, Any]) -> None:
        self.value = value


class AMF0StrictArray:
    """AMF0 Strict Array type."""

    def __init__(self, value: list[Any]) -> None:
        self.value = value


class AMF0Date:
    """AMF0 Date type."""

    def __init__(self, value: float, timezone: int = 0) -> None:
        self.value = value
        self.timezone = timezone


def load(stream: BytesIO) -> Any:
    """Load a single AMF0 value from stream."""
    marker = stream.read(1)
    if not marker:
        raise EOFError("No more data")
    return _load_value(stream, marker[0])


def loads(data: bytes) -> Any:
    """Load a single AMF0 value from bytes."""
    return load(BytesIO(data))


def dump(value: Any, stream: BytesIO) -> None:
    """Dump a single AMF0 value to stream."""
    _dump_value(value, stream)


def dumps(value: Any) -> bytes:
    """Dump a single AMF0 value to bytes."""
    stream = BytesIO()
    dump(value, stream)
    return stream.getvalue()


def _load_value(stream: BytesIO, marker: int) -> Any:
    """Load a value based on marker."""
    if marker == MARKER_NUMBER:
        return struct.unpack(">d", stream.read(8))[0]
    elif marker == MARKER_BOOLEAN:
        return bool(stream.read(1)[0])
    elif marker == MARKER_STRING:
        return _load_string(stream)
    elif marker == MARKER_OBJECT:
        return _load_object(stream)
    elif marker in (MARKER_NULL, MARKER_UNDEFINED):
        return None
    elif marker == MARKER_ECMA_ARRAY:
        return _load_ecma_array(stream)
    elif marker == MARKER_STRICT_ARRAY:
        return _load_strict_array(stream)
    elif marker == MARKER_DATE:
        return _load_date(stream)
    elif marker == MARKER_LONG_STRING:
        return _load_long_string(stream)
    else:
        raise ValueError(f"Unsupported AMF0 marker: {marker:#x}")


def _load_string(stream: BytesIO) -> str:
    """Load a UTF-8 string."""
    length = struct.unpack(">H", stream.read(2))[0]
    return stream.read(length).decode("utf-8")


def _load_long_string(stream: BytesIO) -> str:
    """Load a long UTF-8 string."""
    length = struct.unpack(">I", stream.read(4))[0]
    return stream.read(length).decode("utf-8")


def _load_object(stream: BytesIO) -> dict[str, Any]:
    """Load an object."""
    result: dict[str, Any] = {}
    while True:
        key = _load_string(stream)
        marker = stream.read(1)
        if not marker:
            raise EOFError("Unexpected end of object")
        if marker[0] == MARKER_OBJECT_END:
            break
        result[key] = _load_value(stream, marker[0])
    return result


def _load_ecma_array(stream: BytesIO) -> dict[str, Any]:
    """Load an ECMA array."""
    _count = struct.unpack(">I", stream.read(4))[0]  # Approximate count
    return _load_object(stream)


def _load_strict_array(stream: BytesIO) -> list[Any]:
    """Load a strict array."""
    count = struct.unpack(">I", stream.read(4))[0]
    result: list[Any] = []
    for _ in range(count):
        marker = stream.read(1)
        if not marker:
            raise EOFError("Unexpected end of array")
        result.append(_load_value(stream, marker[0]))
    return result


def _load_date(stream: BytesIO) -> AMF0Date:
    """Load a date."""
    value = struct.unpack(">d", stream.read(8))[0]
    timezone = struct.unpack(">h", stream.read(2))[0]
    return AMF0Date(value, timezone)


def _dump_value(value: Any, stream: BytesIO) -> None:
    """Dump a value to stream."""
    if isinstance(value, AMF0Number):
        stream.write(bytes([MARKER_NUMBER]))
        stream.write(struct.pack(">d", value.value))
    elif isinstance(value, AMF0Boolean):
        stream.write(bytes([MARKER_BOOLEAN]))
        stream.write(bytes([1 if value.value else 0]))
    elif isinstance(value, AMF0String):
        _dump_string(value.value, stream)
    elif isinstance(value, AMF0Object):
        _dump_object(value.value, stream)
    elif isinstance(value, AMF0Null):
        stream.write(bytes([MARKER_NULL]))
    elif isinstance(value, AMF0Undefined):
        stream.write(bytes([MARKER_UNDEFINED]))
    elif isinstance(value, AMF0ECMAArray):
        _dump_ecma_array(value.value, stream)
    elif isinstance(value, AMF0StrictArray):
        _dump_strict_array(value.value, stream)
    elif isinstance(value, AMF0Date):
        _dump_date(value, stream)
    elif isinstance(value, bool):
        stream.write(bytes([MARKER_BOOLEAN]))
        stream.write(bytes([1 if value else 0]))
    elif isinstance(value, (int, float)):
        stream.write(bytes([MARKER_NUMBER]))
        stream.write(struct.pack(">d", float(value)))
    elif isinstance(value, str):
        _dump_string(value, stream)
    elif isinstance(value, dict):
        _dump_object(value, stream)
    elif isinstance(value, list):
        _dump_strict_array(value, stream)
    elif value is None:
        stream.write(bytes([MARKER_NULL]))
    else:
        raise TypeError(f"Cannot dump value of type {type(value)}")


def _dump_string(value: str, stream: BytesIO) -> None:
    """Dump a UTF-8 string with marker."""
    encoded = value.encode("utf-8")
    if len(encoded) > 0xFFFF:
        stream.write(bytes([MARKER_LONG_STRING]))
        stream.write(struct.pack(">I", len(encoded)))
    else:
        stream.write(bytes([MARKER_STRING]))
        stream.write(struct.pack(">H", len(encoded)))
    stream.write(encoded)


def _dump_string_no_marker(value: str, stream: BytesIO) -> None:
    """Dump a UTF-8 string without marker (for object keys)."""
    encoded = value.encode("utf-8")
    stream.write(struct.pack(">H", len(encoded)))
    stream.write(encoded)


def _dump_object(value: dict[str, Any], stream: BytesIO) -> None:
    """Dump an object."""
    stream.write(bytes([MARKER_OBJECT]))
    for key, val in value.items():
        _dump_string_no_marker(key, stream)
        _dump_value(val, stream)
    stream.write(bytes([0x00, 0x00, MARKER_OBJECT_END]))


def _dump_ecma_array(value: dict[str, Any], stream: BytesIO) -> None:
    """Dump an ECMA array."""
    stream.write(bytes([MARKER_ECMA_ARRAY]))
    stream.write(struct.pack(">I", len(value)))
    for key, val in value.items():
        _dump_string_no_marker(key, stream)
        _dump_value(val, stream)
    stream.write(bytes([0x00, 0x00, MARKER_OBJECT_END]))


def _dump_strict_array(value: list[Any], stream: BytesIO) -> None:
    """Dump a strict array."""
    stream.write(bytes([MARKER_STRICT_ARRAY]))
    stream.write(struct.pack(">I", len(value)))
    for item in value:
        _dump_value(item, stream)


def _dump_date(value: AMF0Date, stream: BytesIO) -> None:
    """Dump a date."""
    stream.write(bytes([MARKER_DATE]))
    stream.write(struct.pack(">d", value.value))
    stream.write(struct.pack(">h", value.timezone))
