"""Global exception bus backed by a reactivex Subject."""

from __future__ import annotations

from reactivex import Observable, Subject

from ..utils.patterns import Singleton

__all__ = ("ExceptionCenter",)


class ExceptionCenter(Singleton):
    """Singleton hub that broadcasts exceptions to all subscribers."""

    def __init__(self) -> None:
        super().__init__()
        self._source: Subject[BaseException] = Subject()

    @property
    def exceptions(self) -> Observable[BaseException]:
        return self._source

    def submit(self, exc: BaseException) -> None:
        self._source.on_next(exc)
