"""Metadata analysis helpers for post-processing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ("MetaData", "analyse_metadata", "get_duration", "get_resolution")


@dataclass(frozen=True, slots=True)
class MetaData:
    """Analyzed FLV metadata."""

    duration: float | None
    width: int | None
    height: int | None
    framerate: float | None
    videodatarate: float | None
    audiodatarate: float | None
    keyframes: dict[str, list[Any]] | None


def analyse_metadata(metadata: dict[str, Any]) -> MetaData:
    """Analyze metadata dictionary."""
    keyframes = metadata.get("keyframes")
    if isinstance(keyframes, dict):
        keyframes_data: dict[str, list[Any]] | None = keyframes
    else:
        keyframes_data = None

    return MetaData(
        duration=metadata.get("duration"),
        width=metadata.get("width"),
        height=metadata.get("height"),
        framerate=metadata.get("framerate"),
        videodatarate=metadata.get("videodatarate"),
        audiodatarate=metadata.get("audiodatarate"),
        keyframes=keyframes_data,
    )


def get_duration(metadata: dict[str, Any]) -> float | None:
    """Get duration from metadata."""
    return metadata.get("duration")


def get_resolution(metadata: dict[str, Any]) -> tuple[int, int] | None:
    """Get resolution from metadata."""
    width = metadata.get("width")
    height = metadata.get("height")
    if width is not None and height is not None:
        return (int(width), int(height))
    return None
