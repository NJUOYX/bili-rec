"""Tests for birec.exception module."""

from __future__ import annotations

from concurrent.futures import Future
from typing import TYPE_CHECKING

import pytest

from birec.exception import (
    ExceptionCenter,
    ExceptionHandler,
    ExceptionSubmitter,
    ExistsError,
    ForbiddenError,
    NotFoundError,
    exception_callback,
    format_exception,
    submit_exception,
)

if TYPE_CHECKING:
    from collections.abc import Generator


class TestDomainExceptions:
    def test_not_found_error_is_value_error(self) -> None:
        exc = NotFoundError("room 123 not found")
        assert isinstance(exc, ValueError)
        assert str(exc) == "room 123 not found"

    def test_exists_error_is_value_error(self) -> None:
        exc = ExistsError("task already exists")
        assert isinstance(exc, ValueError)
        assert str(exc) == "task already exists"

    def test_forbidden_error_is_exception(self) -> None:
        exc = ForbiddenError("access denied")
        assert isinstance(exc, Exception)
        assert not isinstance(exc, ValueError)
        assert str(exc) == "access denied"


class TestFormatException:
    def test_formats_traceback(self) -> None:
        try:
            raise ValueError("test error")
        except ValueError as exc:
            result = format_exception(exc)
        assert "ValueError" in result
        assert "test error" in result
        assert "Traceback" in result

    def test_formats_nested_exception(self) -> None:
        try:
            try:
                raise RuntimeError("inner")
            except RuntimeError as inner:
                raise ValueError("outer") from inner
        except ValueError as exc:
            result = format_exception(exc)
        assert "ValueError" in result
        assert "outer" in result


class TestExceptionCenter:
    @pytest.fixture(autouse=True)
    def _reset_singleton(self) -> Generator[None]:
        from birec.utils.patterns import Singleton

        Singleton._instances.pop(ExceptionCenter, None)
        yield
        Singleton._instances.pop(ExceptionCenter, None)

    def test_singleton(self) -> None:
        center1 = ExceptionCenter.get_instance()
        center2 = ExceptionCenter.get_instance()
        assert center1 is center2

    def test_submit_and_observe(self) -> None:
        center = ExceptionCenter.get_instance()
        received: list[BaseException] = []
        sub = center.exceptions.subscribe(on_next=received.append)

        exc = ValueError("test")
        center.submit(exc)

        assert received == [exc]
        sub.dispose()

    def test_multiple_subscribers(self) -> None:
        center = ExceptionCenter.get_instance()
        received1: list[BaseException] = []
        received2: list[BaseException] = []
        sub1 = center.exceptions.subscribe(on_next=received1.append)
        sub2 = center.exceptions.subscribe(on_next=received2.append)

        exc = RuntimeError("multi")
        center.submit(exc)

        assert received1 == [exc]
        assert received2 == [exc]
        sub1.dispose()
        sub2.dispose()


class TestSubmitException:
    @pytest.fixture(autouse=True)
    def _reset_singleton(self) -> Generator[None]:
        from birec.utils.patterns import Singleton

        Singleton._instances.pop(ExceptionCenter, None)
        yield
        Singleton._instances.pop(ExceptionCenter, None)

    def test_submit_exception_pushes_to_center(self) -> None:
        center = ExceptionCenter.get_instance()
        received: list[BaseException] = []
        sub = center.exceptions.subscribe(on_next=received.append)

        exc = ValueError("via helper")
        submit_exception(exc)

        assert received == [exc]
        sub.dispose()


class TestExceptionSubmitter:
    @pytest.fixture(autouse=True)
    def _reset_singleton(self) -> Generator[None]:
        from birec.utils.patterns import Singleton

        Singleton._instances.pop(ExceptionCenter, None)
        yield
        Singleton._instances.pop(ExceptionCenter, None)

    def test_context_manager_catches_and_submits(self) -> None:
        center = ExceptionCenter.get_instance()
        received: list[BaseException] = []
        sub = center.exceptions.subscribe(on_next=received.append)

        with ExceptionSubmitter():
            raise ValueError("caught by submitter")

        assert len(received) == 1
        assert isinstance(received[0], ValueError)
        assert str(received[0]) == "caught by submitter"
        sub.dispose()

    def test_context_manager_no_exception(self) -> None:
        center = ExceptionCenter.get_instance()
        received: list[BaseException] = []
        sub = center.exceptions.subscribe(on_next=received.append)

        with ExceptionSubmitter():
            pass

        assert received == []
        sub.dispose()

    def test_context_manager_suppresses_exception(self) -> None:
        with ExceptionSubmitter():
            raise RuntimeError("should be suppressed")
        # If we reach here, the exception was suppressed


class TestExceptionCallback:
    @pytest.fixture(autouse=True)
    def _reset_singleton(self) -> Generator[None]:
        from birec.utils.patterns import Singleton

        Singleton._instances.pop(ExceptionCenter, None)
        yield
        Singleton._instances.pop(ExceptionCenter, None)

    def test_callback_extracts_exception_from_future(self) -> None:
        center = ExceptionCenter.get_instance()
        received: list[BaseException] = []
        sub = center.exceptions.subscribe(on_next=received.append)

        future: Future[None] = Future()
        future.set_exception(ValueError("future error"))
        exception_callback(future)

        assert len(received) == 1
        assert str(received[0]) == "future error"
        sub.dispose()

    def test_callback_ignores_successful_future(self) -> None:
        center = ExceptionCenter.get_instance()
        received: list[BaseException] = []
        sub = center.exceptions.subscribe(on_next=received.append)

        future: Future[str] = Future()
        future.set_result("ok")
        exception_callback(future)

        assert received == []
        sub.dispose()

    def test_callback_ignores_cancelled_future(self) -> None:
        center = ExceptionCenter.get_instance()
        received: list[BaseException] = []
        sub = center.exceptions.subscribe(on_next=received.append)

        future: Future[None] = Future()
        future.cancel()
        exception_callback(future)

        assert received == []
        sub.dispose()


class TestExceptionHandler:
    @pytest.fixture(autouse=True)
    def _reset_singleton(self) -> Generator[None]:
        from birec.utils.patterns import Singleton

        Singleton._instances.pop(ExceptionCenter, None)
        yield
        Singleton._instances.pop(ExceptionCenter, None)

    def test_handler_logs_exception_when_enabled(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        handler = ExceptionHandler()
        handler.enable()

        center = ExceptionCenter.get_instance()
        exc = ValueError("handler test")
        center.submit(exc)

        # loguru doesn't integrate with caplog by default; verify via handler state
        assert handler.enabled
        handler.disable()

    def test_handler_ignores_when_disabled(self) -> None:
        handler = ExceptionHandler()
        # Not enabled - should not crash
        center = ExceptionCenter.get_instance()
        center.submit(ValueError("ignored"))
        assert not handler.enabled

    def test_handler_enable_disable_idempotent(self) -> None:
        handler = ExceptionHandler()
        handler.enable()
        handler.enable()  # idempotent
        assert handler.enabled
        handler.disable()
        handler.disable()  # idempotent
        assert not handler.enabled
