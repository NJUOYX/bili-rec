"""Tests for AsyncCooperationMixin."""

from __future__ import annotations

import asyncio
import threading

from birec.utils.mixins import AsyncCooperationMixin


class Worker(AsyncCooperationMixin):
    """Test helper that uses AsyncCooperationMixin from a worker thread."""


class TestAsyncCooperationMixin:
    async def test_captures_running_loop(self) -> None:
        worker = Worker()
        assert worker._loop is asyncio.get_running_loop()

    async def test_run_coroutine_from_worker_thread(self) -> None:
        worker = Worker()
        result_holder: list[int] = []

        async def compute() -> int:
            await asyncio.sleep(0.01)
            return 42

        def thread_fn() -> None:
            future = worker._run_coroutine(compute())
            result_holder.append(future.result(timeout=5))

        thread = threading.Thread(target=thread_fn)
        thread.start()
        await asyncio.to_thread(thread.join, 5)

        assert result_holder == [42]

    async def test_call_coroutine_from_worker_thread(self) -> None:
        worker = Worker()
        result_holder: list[str] = []

        async def greet() -> str:
            await asyncio.sleep(0.01)
            return "hello"

        def thread_fn() -> None:
            result_holder.append(worker._call_coroutine(greet()))

        thread = threading.Thread(target=thread_fn)
        thread.start()
        await asyncio.to_thread(thread.join, 5)

        assert result_holder == ["hello"]

    async def test_call_coroutine_propagates_exception(self) -> None:
        worker = Worker()
        error_holder: list[BaseException] = []

        async def fail() -> None:
            raise ValueError("async error")

        def thread_fn() -> None:
            try:
                worker._call_coroutine(fail())
            except ValueError as exc:
                error_holder.append(exc)

        thread = threading.Thread(target=thread_fn)
        thread.start()
        await asyncio.to_thread(thread.join, 5)

        assert len(error_holder) == 1
        assert str(error_holder[0]) == "async error"

    async def test_submit_exception_from_worker_thread(self) -> None:
        from birec.exception import ExceptionCenter
        from birec.utils.patterns import Singleton

        Singleton._instances.pop(ExceptionCenter, None)
        try:
            worker = Worker()
            center = ExceptionCenter.get_instance()
            received: list[BaseException] = []
            sub = center.exceptions.subscribe(on_next=received.append)

            def thread_fn() -> None:
                worker._submit_exception(ValueError("from thread"))

            thread = threading.Thread(target=thread_fn)
            thread.start()
            await asyncio.to_thread(thread.join, 5)

            assert len(received) == 1
            assert str(received[0]) == "from thread"
            sub.dispose()
        finally:
            Singleton._instances.pop(ExceptionCenter, None)

    async def test_multiple_workers_share_loop(self) -> None:
        w1 = Worker()
        w2 = Worker()
        assert w1._loop is w2._loop
