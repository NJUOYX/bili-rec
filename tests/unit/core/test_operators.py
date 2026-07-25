"""Tests for core operators."""

from __future__ import annotations

import time

import pytest

from birec.core.operators.connection_error_handler import ConnectionErrorHandler
from birec.core.operators.exception_handler import ExceptionHandler
from birec.core.operators.progress_bar import ProgressBar
from birec.core.operators.recording_monitor import RecordingMonitor
from birec.core.operators.request_exception_handler import RequestExceptionHandler
from birec.core.operators.stream_parser import StreamParser
from birec.core.operators.stream_statistics import StreamStatistics

# ── ConnectionErrorHandler ────────────────────────────────────────────────────


class TestConnectionErrorHandler:
    def test_initial_state(self):
        h = ConnectionErrorHandler()
        assert h.retry_count == 0
        assert h.max_retries == 5

    def test_should_retry(self):
        h = ConnectionErrorHandler(max_retries=3)
        assert h.should_retry() is True
        h._retry_count = 3
        assert h.should_retry() is False

    def test_get_delay_exponential(self):
        h = ConnectionErrorHandler(base_delay=1.0, max_delay=60.0)
        assert h.get_delay() == 1.0  # 2^0
        h._retry_count = 1
        assert h.get_delay() == 2.0  # 2^1
        h._retry_count = 3
        assert h.get_delay() == 8.0  # 2^3

    def test_get_delay_capped(self):
        h = ConnectionErrorHandler(base_delay=1.0, max_delay=5.0)
        h._retry_count = 10
        assert h.get_delay() == 5.0

    @pytest.mark.asyncio
    async def test_wait_retry(self):
        h = ConnectionErrorHandler(max_retries=2, base_delay=0.01)
        result = await h.wait_retry()
        assert result is True
        assert h.retry_count == 1

    @pytest.mark.asyncio
    async def test_wait_retry_exhausted(self):
        h = ConnectionErrorHandler(max_retries=0)
        result = await h.wait_retry()
        assert result is False

    def test_reset(self):
        h = ConnectionErrorHandler()
        h._retry_count = 3
        h.reset()
        assert h.retry_count == 0

    def test_record_success(self):
        h = ConnectionErrorHandler()
        h._retry_count = 3
        h.record_success()
        assert h.retry_count == 0

    @pytest.mark.asyncio
    async def test_callbacks(self):
        retry_calls = []
        exhausted_calls = []
        h = ConnectionErrorHandler(max_retries=1, base_delay=0.01)
        h.set_callbacks(
            on_retry=lambda n, d: retry_calls.append((n, d)),
            on_exhausted=lambda: exhausted_calls.append(True),
        )
        h._retry_count = 1
        h.should_retry()  # False
        await h.wait_retry()  # exhausted
        assert len(exhausted_calls) == 1


# ── RequestExceptionHandler ───────────────────────────────────────────────────


class TestRequestExceptionHandler:
    def test_handle_timeout(self):
        h = RequestExceptionHandler()
        action = h.handle(TimeoutError("timeout"))
        assert action == "retry"
        assert h.error_count == 1

    def test_handle_client_error(self):
        h = RequestExceptionHandler()
        import aiohttp

        action = h.handle(aiohttp.ClientError("conn failed"))
        assert action == "fallback"

    def test_handle_unknown(self):
        h = RequestExceptionHandler()
        action = h.handle(RuntimeError("unknown"))
        assert action == "abort"

    def test_reset(self):
        h = RequestExceptionHandler()
        h.handle(ValueError("test"))
        h.reset()
        assert h.error_count == 0
        assert h.last_error == ""


# ── ExceptionHandler ──────────────────────────────────────────────────────────


class TestExceptionHandler:
    def test_handle_os_error(self):
        h = ExceptionHandler()
        action = h.handle(OSError("disk full"))
        assert action == "retry"
        assert h.exception_count == 1

    def test_handle_value_error(self):
        h = ExceptionHandler()
        action = h.handle(ValueError("bad value"))
        assert action == "fallback"

    def test_handle_keyboard_interrupt(self):
        h = ExceptionHandler()
        action = h.handle(KeyboardInterrupt())
        assert action == "abort"

    def test_handle_with_context(self):
        h = ExceptionHandler()
        action = h.handle(OSError("test"), context="stream_fetcher")
        assert action == "retry"

    def test_reset(self):
        h = ExceptionHandler()
        h.handle(OSError("test"))
        h.reset()
        assert h.exception_count == 0
        assert h.last_exception is None


# ── RecordingMonitor ─────────────────────────────────────────────────────────


class TestRecordingMonitor:
    def test_initial_state(self):
        m = RecordingMonitor()
        assert m.is_recording is False
        assert m.stalled is False
        assert m.total_bytes == 0

    def test_start_stop(self):
        m = RecordingMonitor()
        m.start()
        assert m.is_recording is True
        m.stop()
        assert m.is_recording is False

    def test_on_data(self):
        m = RecordingMonitor()
        m.start()
        m.on_data(1000)
        m.on_data(2000)
        assert m.total_bytes == 3000

    def test_stall_detection(self):
        m = RecordingMonitor(stall_timeout=0.01)
        m.start()
        time.sleep(0.02)
        m.tick()
        assert m.stalled is True

    def test_stall_recovery(self):
        m = RecordingMonitor(stall_timeout=0.01)
        m.start()
        time.sleep(0.02)
        m.tick()
        assert m.stalled is True
        m.on_data(100)
        assert m.stalled is False

    def test_callbacks(self):
        stall_calls = []
        report_calls = []
        m = RecordingMonitor(stall_timeout=0.01, report_interval=0.01)
        m.set_callbacks(
            on_stall=lambda: stall_calls.append(True),
            on_report=lambda r: report_calls.append(r),
        )
        m.start()
        time.sleep(0.02)
        m.tick()
        assert len(stall_calls) == 1
        assert len(report_calls) == 1

    def test_reset(self):
        m = RecordingMonitor()
        m.start()
        m.on_data(1000)
        m.reset()
        assert m.total_bytes == 0
        assert m.is_recording is False


# ── ProgressBar ───────────────────────────────────────────────────────────────


class TestProgressBar:
    def test_initial_state(self):
        p = ProgressBar()
        assert p.total_bytes == 0
        assert p.rate == 0.0

    def test_start(self):
        p = ProgressBar()
        p.start()
        assert p.elapsed >= 0

    def test_update(self):
        p = ProgressBar()
        p.start()
        p.update(1000)
        assert p.total_bytes == 1000

    def test_format_size(self):
        p = ProgressBar()
        assert p.format_size(500) == "500B"
        assert p.format_size(1500) == "1.5KB"
        assert p.format_size(1500000) == "1.4MB"
        assert p.format_size(1500000000) == "1.40GB"

    def test_format_elapsed(self):
        p = ProgressBar()
        assert p.format_elapsed(3661) == "01:01:01"
        assert p.format_elapsed(0) == "00:00:00"

    def test_render(self):
        p = ProgressBar()
        p.start()
        p.update(1000)
        result = p.render()
        assert "1000B" in result

    def test_reset(self):
        p = ProgressBar()
        p.start()
        p.update(1000)
        p.reset()
        assert p.total_bytes == 0


# ── StreamParser ──────────────────────────────────────────────────────────────


class TestStreamParser:
    def test_detect_flv_header(self):
        p = StreamParser()
        assert p.detect_flv_header(b"FLV\x01\x05") is True
        assert p.detect_flv_header(b"not flv") is False
        assert p.detect_flv_header(b"FL") is False

    def test_detect_ts_sync(self):
        p = StreamParser()
        assert p.detect_ts_sync(b"\x47\x00") is True
        assert p.detect_ts_sync(b"\x00\x47") is False
        assert p.detect_ts_sync(b"") is False

    def test_stream_type_property(self):
        p = StreamParser("ts")
        assert p.stream_type == "ts"
        p.stream_type = "flv"
        assert p.stream_type == "flv"

    @pytest.mark.asyncio
    async def test_parse_passthrough(self):
        p = StreamParser()

        async def gen():
            yield b"chunk1"
            yield b"chunk2"

        chunks = []
        async for chunk in p.parse(gen()):
            chunks.append(chunk)
        assert chunks == [b"chunk1", b"chunk2"]


# ── StreamStatistics ─────────────────────────────────────────────────────────


class TestStreamStatistics:
    def test_initial_state(self):
        s = StreamStatistics()
        assert s.expected_size == 0
        assert s.segment_count == 0
        assert s.progress_percent == 0.0

    def test_expected_size(self):
        s = StreamStatistics()
        s.expected_size = 1000
        assert s.expected_size == 1000

    def test_increment_segment(self):
        s = StreamStatistics()
        s.increment_segment()
        s.increment_segment()
        assert s.segment_count == 2

    def test_progress_percent(self):
        s = StreamStatistics()
        s.expected_size = 1000
        s.update_file_size(500)
        assert s.progress_percent == 50.0

    def test_progress_percent_capped(self):
        s = StreamStatistics()
        s.expected_size = 100
        s.update_file_size(200)
        assert s.progress_percent == 100.0

    def test_snapshot(self):
        s = StreamStatistics()
        s.expected_size = 1000
        s.update_file_size(500)
        s.increment_segment()
        snap = s.snapshot()
        assert snap["expected_size"] == 1000
        assert snap["segment_count"] == 1
        assert snap["progress_percent"] == 50.0
