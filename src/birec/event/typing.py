"""Event type aliases."""

from __future__ import annotations

from .models import (
    CoverImageDownloadedEvent,
    DanmakuFileCompletedEvent,
    DanmakuFileCreatedEvent,
    Error,
    PostprocessingCompletedEvent,
    RawDanmakuFileCompletedEvent,
    RawDanmakuFileCreatedEvent,
    VideoFileCompletedEvent,
    VideoFileCreatedEvent,
    VideoPostprocessingCompletedEvent,
)

__all__ = ("Event",)

Event = (
    VideoFileCreatedEvent
    | VideoFileCompletedEvent
    | DanmakuFileCreatedEvent
    | DanmakuFileCompletedEvent
    | RawDanmakuFileCreatedEvent
    | RawDanmakuFileCompletedEvent
    | CoverImageDownloadedEvent
    | VideoPostprocessingCompletedEvent
    | PostprocessingCompletedEvent
    | Error
)
