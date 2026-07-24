"""ExceptionHandler: subscribes to ExceptionCenter and logs critical errors."""

from __future__ import annotations

from loguru import logger
from reactivex.abc.disposable import DisposableBase

from ..utils.mixins import SwitchableMixin
from .exception_center import ExceptionCenter
from .helpers import format_exception

__all__ = ("ExceptionHandler",)


class ExceptionHandler(SwitchableMixin):
    """Logs every exception broadcast on the ExceptionCenter when enabled."""

    def __init__(self) -> None:
        super().__init__()
        self._subscription: DisposableBase | None = None

    def _do_enable(self) -> None:
        center = ExceptionCenter.get_instance()
        self._subscription = center.exceptions.subscribe(
            on_next=self._on_exception,
        )

    def _do_disable(self) -> None:
        if self._subscription is not None:
            self._subscription.dispose()
            self._subscription = None

    def _on_exception(self, exc: BaseException) -> None:
        logger.critical(format_exception(exc))
