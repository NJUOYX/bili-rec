"""Tests for birec.event module."""

from __future__ import annotations

import uuid
from datetime import timedelta, timezone
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from birec.event import (
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
    EventCenter,
    EventEmitter,
    EventListener,
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

if TYPE_CHECKING:
    from collections.abc import Generator

UTC8 = timezone(timedelta(hours=8))


class TestBaseEvent:
    def test_from_data_creates_event_with_uuid_and_utc8_date(self) -> None:
        data = VideoFileCreatedEventData(room_id=123, path="/tmp/test.flv")
        event = VideoFileCreatedEvent.from_data(data)

        assert isinstance(event.id, uuid.UUID)
        assert event.date.tzinfo == UTC8
        assert event.type == "VideoFileCreatedEvent"
        assert event.data is data

    def test_event_is_frozen(self) -> None:
        data = VideoFileCreatedEventData(room_id=1, path="/a")
        event = VideoFileCreatedEvent.from_data(data)
        with pytest.raises(ValidationError):
            event.type = "hacked"  # type: ignore[misc]

    def test_event_data_is_frozen(self) -> None:
        data = VideoFileCreatedEventData(room_id=1, path="/a")
        with pytest.raises(ValidationError):
            data.room_id = 999  # type: ignore[misc]

    def test_model_dump_serializes_uuid_and_datetime_as_strings(self) -> None:
        data = VideoFileCreatedEventData(room_id=42, path="/rec/test.flv")
        event = VideoFileCreatedEvent.from_data(data)
        dumped = event.model_dump(mode="json")

        assert isinstance(dumped["id"], str)
        assert isinstance(dumped["date"], str)
        assert dumped["type"] == "VideoFileCreatedEvent"
        assert dumped["data"]["room_id"] == 42
        assert dumped["data"]["path"] == "/rec/test.flv"


class TestEventDataModels:
    def test_video_file_created(self) -> None:
        data = VideoFileCreatedEventData(room_id=100, path="/out/video.flv")
        assert data.room_id == 100
        assert data.path == "/out/video.flv"

    def test_video_file_completed(self) -> None:
        data = VideoFileCompletedEventData(room_id=100, path="/out/video.flv")
        event = VideoFileCompletedEvent.from_data(data)
        assert event.type == "VideoFileCompletedEvent"

    def test_danmaku_file_created(self) -> None:
        data = DanmakuFileCreatedEventData(room_id=200, path="/out/danmaku.xml")
        event = DanmakuFileCreatedEvent.from_data(data)
        assert event.type == "DanmakuFileCreatedEvent"

    def test_danmaku_file_completed(self) -> None:
        data = DanmakuFileCompletedEventData(room_id=200, path="/out/danmaku.xml")
        event = DanmakuFileCompletedEvent.from_data(data)
        assert event.type == "DanmakuFileCompletedEvent"

    def test_raw_danmaku_file_created(self) -> None:
        data = RawDanmakuFileCreatedEventData(room_id=300, path="/out/raw.json")
        event = RawDanmakuFileCreatedEvent.from_data(data)
        assert event.type == "RawDanmakuFileCreatedEvent"

    def test_raw_danmaku_file_completed(self) -> None:
        data = RawDanmakuFileCompletedEventData(room_id=300, path="/out/raw.json")
        event = RawDanmakuFileCompletedEvent.from_data(data)
        assert event.type == "RawDanmakuFileCompletedEvent"

    def test_cover_image_downloaded(self) -> None:
        data = CoverImageDownloadedEventData(room_id=400, path="/out/cover.jpg")
        event = CoverImageDownloadedEvent.from_data(data)
        assert event.type == "CoverImageDownloadedEvent"

    def test_video_postprocessing_completed(self) -> None:
        data = VideoPostprocessingCompletedEventData(room_id=500, path="/out/video.mp4")
        event = VideoPostprocessingCompletedEvent.from_data(data)
        assert event.type == "VideoPostprocessingCompletedEvent"

    def test_postprocessing_completed_with_files(self) -> None:
        data = PostprocessingCompletedEventData(
            room_id=600, files=["/out/a.mp4", "/out/a.xml"]
        )
        event = PostprocessingCompletedEvent.from_data(data)
        assert event.type == "PostprocessingCompletedEvent"
        assert event.data.files == ["/out/a.mp4", "/out/a.xml"]

    def test_task_refreshed(self) -> None:
        """Room-info edits get their own event so clients refetch task data (#40)."""
        data = TaskRefreshedEventData(room_id=700)
        event = TaskRefreshedEvent.from_data(data)
        assert event.type == "TaskRefreshedEvent"
        assert event.data.room_id == 700
        dumped = event.model_dump(mode="json")
        assert dumped["type"] == "TaskRefreshedEvent"
        assert dumped["data"] == {"room_id": 700}


class TestErrorEvent:
    def test_error_data_from_exc(self) -> None:
        try:
            raise ValueError("test error detail")
        except ValueError as exc:
            data = ErrorData.from_exc(exc)

        assert data.name == "ValueError"
        assert "test error detail" in data.detail
        assert "Traceback" in data.detail

    def test_error_event(self) -> None:
        try:
            raise RuntimeError("boom")
        except RuntimeError as exc:
            data = ErrorData.from_exc(exc)
        event = Error.from_data(data)
        assert event.type == "Error"
        assert event.data.name == "RuntimeError"


class TestEventCenter:
    @pytest.fixture(autouse=True)
    def _reset_singleton(self) -> Generator[None]:
        from birec.utils.patterns import Singleton

        Singleton._instances.pop(EventCenter, None)
        yield
        Singleton._instances.pop(EventCenter, None)

    def test_singleton(self) -> None:
        c1 = EventCenter.get_instance()
        c2 = EventCenter.get_instance()
        assert c1 is c2

    def test_submit_and_observe(self) -> None:
        center = EventCenter.get_instance()
        received: list[BaseEvent[BaseEventData]] = []
        sub = center.events.subscribe(on_next=received.append)

        data = VideoFileCreatedEventData(room_id=1, path="/x")
        event = VideoFileCreatedEvent.from_data(data)
        center.submit(event)

        assert len(received) == 1
        assert received[0] is event
        sub.dispose()

    def test_multiple_subscribers(self) -> None:
        center = EventCenter.get_instance()
        r1: list[BaseEvent[BaseEventData]] = []
        r2: list[BaseEvent[BaseEventData]] = []
        s1 = center.events.subscribe(on_next=r1.append)
        s2 = center.events.subscribe(on_next=r2.append)

        data = VideoFileCompletedEventData(room_id=2, path="/y")
        event = VideoFileCompletedEvent.from_data(data)
        center.submit(event)

        assert r1 == [event]
        assert r2 == [event]
        s1.dispose()
        s2.dispose()


class TestEventEmitter:
    def test_add_and_remove_listener(self) -> None:
        class MyListener(EventListener):
            def on_test(self, value: int) -> None:
                self.received = value

        emitter: EventEmitter[MyListener] = EventEmitter()
        listener = MyListener()
        emitter.add_listener(listener)
        assert listener in emitter._listeners

        emitter.remove_listener(listener)
        assert listener not in emitter._listeners

    async def test_emit_calls_listener_method(self) -> None:
        class MyListener(EventListener):
            def __init__(self) -> None:
                self.received: list[int] = []

            def on_data(self, value: int) -> None:
                self.received.append(value)

        emitter: EventEmitter[MyListener] = EventEmitter()
        listener = MyListener()
        emitter.add_listener(listener)

        await emitter._emit("data", 42)
        assert listener.received == [42]

    async def test_emit_to_multiple_listeners(self) -> None:
        class MyListener(EventListener):
            def __init__(self) -> None:
                self.values: list[str] = []

            def on_msg(self, text: str) -> None:
                self.values.append(text)

        emitter: EventEmitter[MyListener] = EventEmitter()
        l1, l2 = MyListener(), MyListener()
        emitter.add_listener(l1)
        emitter.add_listener(l2)

        await emitter._emit("msg", "hello")
        assert l1.values == ["hello"]
        assert l2.values == ["hello"]

    async def test_emit_ignores_missing_method(self) -> None:
        class BareListener(EventListener):
            pass

        emitter: EventEmitter[BareListener] = EventEmitter()
        emitter.add_listener(BareListener())

        # Should not raise even though listener has no on_nonexistent
        await emitter._emit("nonexistent", 1)

    async def test_emit_catches_listener_exception(self) -> None:
        class BadListener(EventListener):
            def on_boom(self) -> None:
                raise RuntimeError("listener error")

        emitter: EventEmitter[BadListener] = EventEmitter()
        emitter.add_listener(BadListener())

        # Should not propagate the exception
        await emitter._emit("boom")
