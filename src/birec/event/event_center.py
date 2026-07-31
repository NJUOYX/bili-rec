"""Global event bus backed by a reactivex Subject."""

from __future__ import annotations

from typing import Any

from reactivex import Observable, Subject

from ..utils.patterns import Singleton
from .models import BaseEvent

__all__ = ("EventCenter",)


class EventCenter(Singleton):
    """Singleton hub that broadcasts events to all subscribers (e.g. WebSocket).

    The data type is left open: the bus carries every event class there is, and
    ``BaseEvent`` is invariant in its payload, so pinning it to ``BaseEventData``
    would reject each concrete event.
    """

    def __init__(self) -> None:
        super().__init__()
        self._source: Subject[BaseEvent[Any]] = Subject()

    @property
    def events(self) -> Observable[BaseEvent[Any]]:
        return self._source

    def submit(self, event: BaseEvent[Any]) -> None:
        self._source.on_next(event)
