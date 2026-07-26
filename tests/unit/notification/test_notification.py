"""Tests for notification module."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from birec.event.models import (
    VideoFileCreatedEvent,
    VideoFileCreatedEventData,
)
from birec.notification import Notification, NotificationCenter, NotificationType


class TestNotification:
    def test_defaults(self) -> None:
        notification = Notification(event_type="Test", room_id=1)
        assert notification.event_type == "Test"
        assert notification.room_id == 1
        assert notification.title == ""
        assert notification.message == ""

    def test_from_event(self) -> None:
        event = VideoFileCreatedEvent(
            id=uuid.uuid4(),
            date=datetime.now(UTC),
            data=VideoFileCreatedEventData(room_id=123, path="/tmp/test.flv"),
        )
        notification = Notification.from_event(event)
        assert notification.event_type == "VideoFileCreatedEvent"
        assert notification.room_id == 123


class TestNotificationType:
    def test_constants(self) -> None:
        assert NotificationType.LIVE_BEGAN == "LiveBeganEvent"
        assert NotificationType.ERROR == "Error"


class TestNotificationCenter:
    def test_init(self) -> None:
        nc = NotificationCenter()
        assert nc is not None
        assert nc.events is not None

    def test_subscribe(self) -> None:
        nc = NotificationCenter()
        notifications: list[Notification] = []

        disposable = nc.subscribe(notifications.append)
        assert disposable is not None
        disposable.dispose()
