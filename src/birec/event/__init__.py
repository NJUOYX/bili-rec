"""Event infrastructure: center, emitter, models, and type aliases."""

from __future__ import annotations

from .event_center import EventCenter
from .event_emitter import EventEmitter, EventListener
from .models import (
    BaseEvent,
    BaseEventData,
    CoverImageDownloadedEvent,
    CoverImageDownloadedEventData,
    DanmakuFileCompletedEvent,
    DanmakuFileCompletedEventData,
    DanmakuFileCreatedEvent,
    DanmakuFileCreatedEventData,
    Error,
    ErrorData,
    PostprocessingCompletedEvent,
    PostprocessingCompletedEventData,
    RawDanmakuFileCompletedEvent,
    RawDanmakuFileCompletedEventData,
    RawDanmakuFileCreatedEvent,
    RawDanmakuFileCreatedEventData,
    TaskRefreshedEvent,
    TaskRefreshedEventData,
    VideoFileCompletedEvent,
    VideoFileCompletedEventData,
    VideoFileCreatedEvent,
    VideoFileCreatedEventData,
    VideoPostprocessingCompletedEvent,
    VideoPostprocessingCompletedEventData,
)
from .typing import Event

__all__ = (
    "BaseEvent",
    "BaseEventData",
    "CoverImageDownloadedEvent",
    "CoverImageDownloadedEventData",
    "DanmakuFileCompletedEvent",
    "DanmakuFileCompletedEventData",
    "DanmakuFileCreatedEvent",
    "DanmakuFileCreatedEventData",
    "Error",
    "ErrorData",
    "Event",
    "EventCenter",
    "EventEmitter",
    "EventListener",
    "PostprocessingCompletedEvent",
    "PostprocessingCompletedEventData",
    "RawDanmakuFileCompletedEvent",
    "RawDanmakuFileCompletedEventData",
    "RawDanmakuFileCreatedEvent",
    "RawDanmakuFileCreatedEventData",
    "TaskRefreshedEvent",
    "TaskRefreshedEventData",
    "VideoFileCompletedEvent",
    "VideoFileCompletedEventData",
    "VideoFileCreatedEvent",
    "VideoFileCreatedEventData",
    "VideoPostprocessingCompletedEvent",
    "VideoPostprocessingCompletedEventData",
)
