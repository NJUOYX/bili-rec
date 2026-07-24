"""EventEmitter / EventListener: domain-component-to-bus adapter pattern."""

from __future__ import annotations

from ..exception import ExceptionSubmitter

__all__ = ("EventListener", "EventEmitter")


class EventListener:
    """Marker base for event listeners."""


class EventEmitter[T: EventListener]:
    """Maintains a list of listeners and dispatches ``on_*`` callbacks."""

    def __init__(self) -> None:
        self._listeners: list[T] = []

    def add_listener(self, listener: T) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def remove_listener(self, listener: T) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    async def _emit(self, name: str, *args: object) -> None:
        method_name = f"on_{name}"
        for listener in self._listeners:
            method = getattr(listener, method_name, None)
            if method is not None:
                with ExceptionSubmitter():
                    method(*args)
