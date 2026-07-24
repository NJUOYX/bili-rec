import threading

import pytest

from birec.utils.libc import malloc_trim
from birec.utils.mixins import (
    AsyncStoppableMixin,
    StoppableMixin,
    SwitchableMixin,
)


class _Switch(SwitchableMixin):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []

    def _do_enable(self) -> None:
        self.calls.append("enable")

    def _do_disable(self) -> None:
        self.calls.append("disable")


def test_switchable_is_idempotent() -> None:
    s = _Switch()
    assert s.enabled is False
    s.enable()
    s.enable()
    assert s.enabled is True
    s.disable()
    s.disable()
    assert s.enabled is False
    assert s.calls == ["enable", "disable"]


class _Stop(StoppableMixin):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []

    def _do_start(self) -> None:
        self.calls.append("start")

    def _do_stop(self) -> None:
        self.calls.append("stop")


def test_stoppable_is_idempotent() -> None:
    s = _Stop()
    assert s.stopped is True
    s.start()
    s.start()
    assert s.stopped is False
    s.stop()
    s.stop()
    assert s.stopped is True
    assert s.calls == ["start", "stop"]


class _AsyncStop(AsyncStoppableMixin):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []

    async def _do_start(self) -> None:
        self.calls.append("start")

    async def _do_stop(self) -> None:
        self.calls.append("stop")


async def test_async_stoppable_is_idempotent() -> None:
    s = _AsyncStop()
    assert s.stopped is True
    await s.start()
    await s.start()
    assert s.stopped is False
    await s.stop()
    await s.stop()
    assert s.stopped is True
    assert s.calls == ["start", "stop"]


def test_switchable_and_stoppable_are_abstract() -> None:
    with pytest.raises(TypeError):
        SwitchableMixin()  # type: ignore[abstract]
    with pytest.raises(TypeError):
        StoppableMixin()  # type: ignore[abstract]


def test_malloc_trim_returns_bool() -> None:
    assert isinstance(malloc_trim(0), bool)


def test_switchable_enable_disable_thread_safe() -> None:
    s = _Switch()
    barrier = threading.Barrier(8)

    def worker() -> None:
        barrier.wait()
        for _ in range(100):
            s.enable()
            s.disable()

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert s.enabled is False
