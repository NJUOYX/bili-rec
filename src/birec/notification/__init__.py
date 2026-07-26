"""Notification module: event-based notification subscription interface."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from reactivex import Observable
from reactivex.abc import DisposableBase
from reactivex.disposable import Disposable

from ..event import EventCenter
from ..event.models import BaseEvent, BaseEventData

__all__ = (
    "Notification",
    "NotificationType",
    "NotificationCenter",
)

logger = logging.getLogger(__name__)


class NotificationType:
    """Notification event type constants."""

    LIVE_BEGAN = "LiveBeganEvent"
    LIVE_ENDED = "LiveEndedEvent"
    RECORDING_STARTED = "RecordingStartedEvent"
    RECORDING_FINISHED = "RecordingFinishedEvent"
    RECORDING_CANCELLED = "RecordingCancelledEvent"
    VIDEO_FILE_CREATED = "VideoFileCreatedEvent"
    VIDEO_FILE_COMPLETED = "VideoFileCompletedEvent"
    DANMAKU_FILE_CREATED = "DanmakuFileCreatedEvent"
    DANMAKU_FILE_COMPLETED = "DanmakuFileCompletedEvent"
    POSTPROCESSING_COMPLETED = "PostprocessingCompletedEvent"
    SPACE_NO_ENOUGH = "SpaceNoEnoughEvent"
    ERROR = "Error"


@dataclass(frozen=True, slots=True)
class Notification:
    """A notification message derived from an event."""

    event_type: str
    room_id: int
    title: str = ""
    message: str = ""
    data: dict[str, object] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_event(cls, event: BaseEvent[BaseEventData]) -> Notification:
        """Create a notification from a BaseEvent."""
        data = event.data.model_dump(mode="json")
        room_id = data.get("room_id", 0)
        if not isinstance(room_id, int):
            room_id = 0

        return cls(
            event_type=event.type,
            room_id=room_id,
            data=data,
        )


class NotificationCenter:
    """Notification subscription interface over the event bus.

    Subscribes to EventCenter and converts events to Notification objects.
    Used by WebSocket layer to push notifications to frontend.

    Note: External notification channels (email, serverchan, telegram, etc.)
    and webhook are removed per design. Only WebSocket-based internal
    notification is supported.
    """

    def __init__(self, event_center: EventCenter | None = None) -> None:
        self._event_center = event_center

    def subscribe(
        self,
        on_next: Callable[[Notification], None],
        *,
        room_id: int | None = None,
        event_types: list[str] | None = None,
    ) -> Disposable:
        """Subscribe to notifications.

        Args:
            on_next: Callback for each notification.
            room_id: Optional filter by room ID.
            event_types: Optional filter by event types.

        Returns:
            A Disposable to unsubscribe.
        """
        ec = self._event_center or EventCenter.get_instance()

        def _on_event(event: BaseEvent[BaseEventData]) -> None:
            try:
                notification = Notification.from_event(event)
                if room_id is not None and notification.room_id != room_id:
                    return
                if (
                    event_types is not None
                    and notification.event_type not in event_types
                ):
                    return
                on_next(notification)
            except Exception:
                logger.exception("Error processing notification")

        d: DisposableBase = ec.events.subscribe(on_next=_on_event)
        return Disposable(d.dispose)

    @property
    def events(self) -> Observable[BaseEvent[BaseEventData]]:
        """Get the raw event observable."""
        ec = self._event_center or EventCenter.get_instance()
        return ec.events
