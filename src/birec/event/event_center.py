"""Global event bus backed by a reactivex Subject."""

from __future__ import annotations

from reactivex import Observable, Subject

from ..utils.patterns import Singleton
from .models import BaseEvent, BaseEventData

__all__ = ("EventCenter",)


class EventCenter(Singleton):
    """Singleton hub that broadcasts events to all subscribers (e.g. WebSocket)."""

    def __init__(self) -> None:
        super().__init__()
        self._source: Subject[BaseEvent[BaseEventData]] = Subject()

    @property
    def events(self) -> Observable[BaseEvent[BaseEventData]]:
        return self._source

    def submit(self, event: BaseEvent[BaseEventData]) -> None:
        self._source.on_next(event)
