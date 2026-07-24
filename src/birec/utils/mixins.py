"""Lifecycle mixins for switchable/stoppable components."""

from __future__ import annotations

import asyncio
import os
import threading
from abc import ABC, abstractmethod
from typing import final

__all__ = (
    "SwitchableMixin",
    "StoppableMixin",
    "AsyncStoppableMixin",
    "SupportDebugMixin",
)


class SwitchableMixin(ABC):
    """A component that can be enabled/disabled idempotently and thread-safely."""

    def __init__(self) -> None:
        super().__init__()
        self._enabled = False
        self._enabled_lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        with self._enabled_lock:
            return self._enabled

    @final
    def enable(self) -> None:
        with self._enabled_lock:
            if self._enabled:
                return
            self._enabled = True
            self._do_enable()

    @final
    def disable(self) -> None:
        with self._enabled_lock:
            if not self._enabled:
                return
            self._enabled = False
            self._do_disable()

    @abstractmethod
    def _do_enable(self) -> None: ...

    @abstractmethod
    def _do_disable(self) -> None: ...


class StoppableMixin(ABC):
    """A component that can be started/stopped idempotently and thread-safely."""

    def __init__(self) -> None:
        super().__init__()
        self._stopped = True
        self._stopped_lock = threading.Lock()

    @property
    def stopped(self) -> bool:
        with self._stopped_lock:
            return self._stopped

    @final
    def start(self) -> None:
        with self._stopped_lock:
            if not self._stopped:
                return
            self._stopped = False
            self._do_start()

    @final
    def stop(self) -> None:
        with self._stopped_lock:
            if self._stopped:
                return
            self._stopped = True
            self._do_stop()

    @abstractmethod
    def _do_start(self) -> None: ...

    @abstractmethod
    def _do_stop(self) -> None: ...


class AsyncStoppableMixin(ABC):
    """Async counterpart of :class:`StoppableMixin`."""

    def __init__(self) -> None:
        super().__init__()
        self._stopped = True
        self._stopped_lock = asyncio.Lock()

    @property
    def stopped(self) -> bool:
        return self._stopped

    @final
    async def start(self) -> None:
        async with self._stopped_lock:
            if not self._stopped:
                return
            self._stopped = False
            await self._do_start()

    @final
    async def stop(self) -> None:
        async with self._stopped_lock:
            if self._stopped:
                return
            self._stopped = True
            await self._do_stop()

    @abstractmethod
    async def _do_start(self) -> None: ...

    @abstractmethod
    async def _do_stop(self) -> None: ...


class SupportDebugMixin:
    """Opt-in per-room debug directory driven by the ``BIREC_DEBUG`` env var."""

    def _init_for_debug(self, room_id: int) -> None:
        value = os.environ.get("BIREC_DEBUG")
        if value and (value == "*" or str(room_id) in value.split(",")):
            self._debug = True
            self._debug_dir = os.path.normpath(
                os.path.expanduser(f"~/.birec/debug/{room_id}")
            )
            os.makedirs(self._debug_dir, exist_ok=True)
        else:
            self._debug = False
            self._debug_dir = ""
