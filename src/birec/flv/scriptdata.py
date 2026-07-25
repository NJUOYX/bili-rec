"""FLV Script Data (onMetaData, onJoinPoint, etc.)."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any

from . import amf

__all__ = ("ScriptData", "load", "dump", "loads", "dumps")


@dataclass(frozen=True, slots=True)
class ScriptData:
    """FLV script data."""

    name: str
    value: Any


def load(data: bytes) -> ScriptData:
    """Load script data from bytes."""
    stream = BytesIO(data)
    name = amf.load(stream)
    value = amf.load(stream)
    return ScriptData(name=str(name), value=value)


def dump(script_data: ScriptData) -> bytes:
    """Dump script data to bytes."""
    stream = BytesIO()
    amf.dump(script_data.name, stream)
    amf.dump(script_data.value, stream)
    return stream.getvalue()


def loads(data: bytes) -> ScriptData:
    """Load script data from bytes (alias for load)."""
    return load(data)


def dumps(script_data: ScriptData) -> bytes:
    """Dump script data to bytes (alias for dump)."""
    return dump(script_data)
