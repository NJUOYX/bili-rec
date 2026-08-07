"""Pydantic v2 event models (frozen, generic)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Self

from pydantic import BaseModel, ConfigDict

from ..exception import format_exception

__all__ = (
    "BaseEventData",
    "BaseEvent",
    "VideoFileCreatedEventData",
    "VideoFileCreatedEvent",
    "VideoFileCompletedEventData",
    "VideoFileCompletedEvent",
    "DanmakuFileCreatedEventData",
    "DanmakuFileCreatedEvent",
    "DanmakuFileCompletedEventData",
    "DanmakuFileCompletedEvent",
    "RawDanmakuFileCreatedEventData",
    "RawDanmakuFileCreatedEvent",
    "RawDanmakuFileCompletedEventData",
    "RawDanmakuFileCompletedEvent",
    "CoverImageDownloadedEventData",
    "CoverImageDownloadedEvent",
    "VideoPostprocessingCompletedEventData",
    "VideoPostprocessingCompletedEvent",
    "PostprocessingCompletedEventData",
    "PostprocessingCompletedEvent",
    "TaskRefreshedEventData",
    "TaskRefreshedEvent",
    "ErrorData",
    "Error",
)

UTC8 = timezone(timedelta(hours=8))


class BaseEventData(BaseModel):
    model_config = ConfigDict(frozen=True)


class BaseEvent[D: BaseEventData](BaseModel):
    model_config = ConfigDict(frozen=True)

    type: str = ""
    id: uuid.UUID
    date: datetime
    data: D

    @classmethod
    def from_data(cls, data: D) -> Self:
        return cls(
            id=uuid.uuid1(),
            date=datetime.now(UTC8),
            data=data,
        )


# --- Video file events ---


class VideoFileCreatedEventData(BaseEventData):
    room_id: int
    path: str


class VideoFileCreatedEvent(BaseEvent[VideoFileCreatedEventData]):
    type: str = "VideoFileCreatedEvent"


class VideoFileCompletedEventData(BaseEventData):
    room_id: int
    path: str


class VideoFileCompletedEvent(BaseEvent[VideoFileCompletedEventData]):
    type: str = "VideoFileCompletedEvent"


# --- Danmaku file events ---


class DanmakuFileCreatedEventData(BaseEventData):
    room_id: int
    path: str


class DanmakuFileCreatedEvent(BaseEvent[DanmakuFileCreatedEventData]):
    type: str = "DanmakuFileCreatedEvent"


class DanmakuFileCompletedEventData(BaseEventData):
    room_id: int
    path: str


class DanmakuFileCompletedEvent(BaseEvent[DanmakuFileCompletedEventData]):
    type: str = "DanmakuFileCompletedEvent"


# --- Raw danmaku file events ---


class RawDanmakuFileCreatedEventData(BaseEventData):
    room_id: int
    path: str


class RawDanmakuFileCreatedEvent(BaseEvent[RawDanmakuFileCreatedEventData]):
    type: str = "RawDanmakuFileCreatedEvent"


class RawDanmakuFileCompletedEventData(BaseEventData):
    room_id: int
    path: str


class RawDanmakuFileCompletedEvent(BaseEvent[RawDanmakuFileCompletedEventData]):
    type: str = "RawDanmakuFileCompletedEvent"


# --- Cover image event ---


class CoverImageDownloadedEventData(BaseEventData):
    room_id: int
    path: str


class CoverImageDownloadedEvent(BaseEvent[CoverImageDownloadedEventData]):
    type: str = "CoverImageDownloadedEvent"


# --- Postprocessing events ---


class VideoPostprocessingCompletedEventData(BaseEventData):
    room_id: int
    path: str


class VideoPostprocessingCompletedEvent(
    BaseEvent[VideoPostprocessingCompletedEventData]
):
    type: str = "VideoPostprocessingCompletedEvent"


class PostprocessingCompletedEventData(BaseEventData):
    room_id: int
    files: list[str]


class PostprocessingCompletedEvent(BaseEvent[PostprocessingCompletedEventData]):
    type: str = "PostprocessingCompletedEvent"


# --- Task info events ---


class TaskRefreshedEventData(BaseEventData):
    room_id: int


class TaskRefreshedEvent(BaseEvent[TaskRefreshedEventData]):
    type: str = "TaskRefreshedEvent"


# --- Error event ---


class ErrorData(BaseEventData):
    name: str
    detail: str

    @classmethod
    def from_exc(cls, exc: BaseException) -> ErrorData:
        return cls(name=type(exc).__name__, detail=format_exception(exc))


class Error(BaseEvent[ErrorData]):
    type: str = "Error"
