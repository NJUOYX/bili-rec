"""Tests for notification module."""

from __future__ import annotations

from birec.event import (
    Error,
    ErrorData,
    EventCenter,
    VideoFileCreatedEvent,
    VideoFileCreatedEventData,
)
from birec.event.models import BaseEvent, BaseEventData
from birec.notification import Notification, NotificationCenter, NotificationType


class _StrRoomData(BaseEventData):
    """Event data whose room_id is not an int, to exercise the fallback."""

    room_id: str


class _StrRoomEvent(BaseEvent[_StrRoomData]):
    type: str = "StrRoomEvent"


def _video_created_event(
    room_id: int = 123, path: str = "/tmp/test.flv"
) -> VideoFileCreatedEvent:
    return VideoFileCreatedEvent.from_data(
        VideoFileCreatedEventData(room_id=room_id, path=path)
    )


class TestNotification:
    def test_defaults(self) -> None:
        notification = Notification(event_type="Test", room_id=1)
        assert notification.event_type == "Test"
        assert notification.room_id == 1
        assert notification.title == ""
        assert notification.message == ""
        assert notification.data == {}

    def test_from_event_with_room_id(self) -> None:
        event = _video_created_event(room_id=123)
        notification = Notification.from_event(event)
        assert notification.event_type == "VideoFileCreatedEvent"
        assert notification.room_id == 123
        assert notification.data["path"] == "/tmp/test.flv"

    def test_from_event_without_room_id_defaults_to_zero(self) -> None:
        event = Error.from_data(ErrorData(name="ValueError", detail="boom"))
        notification = Notification.from_event(event)
        assert notification.event_type == "Error"
        assert notification.room_id == 0

    def test_from_event_with_non_int_room_id_defaults_to_zero(self) -> None:
        event = _StrRoomEvent.from_data(_StrRoomData(room_id="not-an-int"))
        notification = Notification.from_event(event)
        assert notification.room_id == 0


class TestNotificationType:
    def test_constants(self) -> None:
        assert NotificationType.LIVE_BEGAN == "LiveBeganEvent"
        assert NotificationType.ERROR == "Error"
        assert NotificationType.VIDEO_FILE_CREATED == "VideoFileCreatedEvent"


class TestNotificationCenter:
    def test_events_property_returns_center_observable(self) -> None:
        center = EventCenter()
        nc = NotificationCenter(event_center=center)
        assert nc.events is center.events

    def test_subscribe_receives_converted_notification(self) -> None:
        center = EventCenter()
        nc = NotificationCenter(event_center=center)
        received: list[Notification] = []

        disposable = nc.subscribe(received.append)
        center.submit(_video_created_event(room_id=7, path="/rec/a.flv"))

        assert len(received) == 1
        assert received[0].event_type == "VideoFileCreatedEvent"
        assert received[0].room_id == 7
        assert received[0].data["path"] == "/rec/a.flv"
        disposable.dispose()

    def test_subscribe_room_id_filter_matches(self) -> None:
        center = EventCenter()
        nc = NotificationCenter(event_center=center)
        received: list[Notification] = []

        disposable = nc.subscribe(received.append, room_id=100)
        center.submit(_video_created_event(room_id=100))

        assert len(received) == 1
        disposable.dispose()

    def test_subscribe_room_id_filter_excludes(self) -> None:
        center = EventCenter()
        nc = NotificationCenter(event_center=center)
        received: list[Notification] = []

        disposable = nc.subscribe(received.append, room_id=100)
        center.submit(_video_created_event(room_id=999))

        assert received == []
        disposable.dispose()

    def test_subscribe_event_types_filter_matches(self) -> None:
        center = EventCenter()
        nc = NotificationCenter(event_center=center)
        received: list[Notification] = []

        disposable = nc.subscribe(
            received.append, event_types=["VideoFileCreatedEvent"]
        )
        center.submit(_video_created_event())

        assert len(received) == 1
        disposable.dispose()

    def test_subscribe_event_types_filter_excludes(self) -> None:
        center = EventCenter()
        nc = NotificationCenter(event_center=center)
        received: list[Notification] = []

        disposable = nc.subscribe(
            received.append, event_types=["VideoFileCompletedEvent"]
        )
        center.submit(_video_created_event())

        assert received == []
        disposable.dispose()

    def test_dispose_stops_delivery(self) -> None:
        center = EventCenter()
        nc = NotificationCenter(event_center=center)
        received: list[Notification] = []

        disposable = nc.subscribe(received.append)
        disposable.dispose()
        center.submit(_video_created_event())

        assert received == []

    def test_subscriber_exception_does_not_break_bus(self) -> None:
        center = EventCenter()
        nc = NotificationCenter(event_center=center)
        good: list[Notification] = []

        def bad_callback(notification: Notification) -> None:
            raise RuntimeError("subscriber failure")

        bad = nc.subscribe(bad_callback)
        good_sub = nc.subscribe(good.append)

        # Must not raise even though the first subscriber throws.
        center.submit(_video_created_event())

        assert len(good) == 1
        bad.dispose()
        good_sub.dispose()

    def test_subscribe_uses_singleton_when_no_center_given(self) -> None:
        from birec.utils.patterns import Singleton

        Singleton._instances.pop(EventCenter, None)
        try:
            nc = NotificationCenter()
            received: list[Notification] = []
            disposable = nc.subscribe(received.append)

            EventCenter.get_instance().submit(_video_created_event(room_id=5))

            assert len(received) == 1
            assert received[0].room_id == 5
            disposable.dispose()
        finally:
            Singleton._instances.pop(EventCenter, None)
