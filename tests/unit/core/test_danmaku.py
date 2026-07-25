"""Tests for core danmaku modules."""

from __future__ import annotations

import json
import os

import pytest

from birec.core.danmaku_dumper import DanmakuDumper, _escape_xml
from birec.core.danmaku_receiver import _MAX_QUEUE_SIZE, DanmakuReceiver
from birec.core.models import DanmakuMessage
from birec.core.raw_danmaku_dumper import RawDanmakuDumper
from birec.core.raw_danmaku_receiver import RawDanmakuReceiver

# ── DanmakuReceiver ───────────────────────────────────────────────────────────


class TestDanmakuReceiver:
    def test_push_and_get_nowait(self):
        r = DanmakuReceiver()
        msg = DanmakuMessage.danmaku(1.0, "hello")
        r.push(msg)
        assert r.queue_size == 1
        result = r.get_nowait()
        assert result is not None
        assert result.type == "danmaku"
        assert r.queue_size == 0

    def test_get_nowait_empty(self):
        r = DanmakuReceiver()
        assert r.get_nowait() is None

    @pytest.mark.asyncio
    async def test_get_with_timeout(self):
        r = DanmakuReceiver()
        msg = DanmakuMessage.danmaku(1.0, "test")
        r.push(msg)
        result = await r.get(timeout=0.1)
        assert result is not None
        assert result.type == "danmaku"

    @pytest.mark.asyncio
    async def test_get_timeout_returns_none(self):
        r = DanmakuReceiver()
        result = await r.get(timeout=0.05)
        assert result is None

    def test_queue_overflow_drops_old(self):
        r = DanmakuReceiver()
        for i in range(_MAX_QUEUE_SIZE + 10):
            r.push(DanmakuMessage.danmaku(float(i), f"msg{i}"))
        assert r.queue_size == _MAX_QUEUE_SIZE
        assert r.dropped_count == 10

    def test_drain(self):
        r = DanmakuReceiver()
        for i in range(5):
            r.push(DanmakuMessage.danmaku(float(i), f"msg{i}"))
        messages = r.drain()
        assert len(messages) == 5
        assert r.queue_size == 0

    def test_clear(self):
        r = DanmakuReceiver()
        r.push(DanmakuMessage.danmaku(1.0, "test"))
        r.clear()
        assert r.queue_size == 0


# ── DanmakuDumper ─────────────────────────────────────────────────────────────


class TestEscapeXml:
    def test_escape_special_chars(self):
        assert _escape_xml("a&b<c>d\"e'f") == "a&amp;b&lt;c&gt;d&quot;e&apos;f"

    def test_no_escape_needed(self):
        assert _escape_xml("hello world") == "hello world"


class TestDanmakuDumper:
    def test_write_header(self, tmp_path):
        receiver = DanmakuReceiver()
        output = str(tmp_path / "test.xml")
        dumper = DanmakuDumper(receiver, output)
        dumper._write_header()
        with open(output, encoding="utf-8") as f:
            content = f.read()
        assert '<?xml version="1.0" encoding="utf-8"?>' in content
        assert "<i>" in content

    def test_write_danmaku(self, tmp_path):
        receiver = DanmakuReceiver()
        output = str(tmp_path / "test.xml")
        dumper = DanmakuDumper(receiver, output)
        dumper._start_time = 1000.0
        dumper._write_header()

        msg = DanmakuMessage.danmaku(1001.5, "hello", uid=42, uname="user")
        dumper._messages.append(msg)
        dumper._flush_messages()

        with open(output, encoding="utf-8") as f:
            content = f.read()
        assert "<d p=" in content
        assert "hello" in content

    def test_write_super_chat(self, tmp_path):
        receiver = DanmakuReceiver()
        output = str(tmp_path / "test.xml")
        dumper = DanmakuDumper(receiver, output)
        dumper._start_time = 1000.0
        dumper._write_header()

        msg = DanmakuMessage.super_chat(1002.0, 1, "user", 30, "SC!")
        dumper._messages.append(msg)
        dumper._flush_messages()

        with open(output, encoding="utf-8") as f:
            content = f.read()
        assert "<sc " in content
        assert "SC!" in content

    def test_write_gift(self, tmp_path):
        receiver = DanmakuReceiver()
        output = str(tmp_path / "test.xml")
        dumper = DanmakuDumper(receiver, output)
        dumper._start_time = 1000.0
        dumper._write_header()

        msg = DanmakuMessage.gift(1003.0, 1, "user", "小花")
        dumper._messages.append(msg)
        dumper._flush_messages()

        with open(output, encoding="utf-8") as f:
            content = f.read()
        assert "<gift " in content
        assert "小花" in content

    def test_write_guard_buy(self, tmp_path):
        receiver = DanmakuReceiver()
        output = str(tmp_path / "test.xml")
        dumper = DanmakuDumper(receiver, output)
        dumper._start_time = 1000.0
        dumper._write_header()

        msg = DanmakuMessage.guard_buy(1004.0, 1, "user", 3)
        dumper._messages.append(msg)
        dumper._flush_messages()

        with open(output, encoding="utf-8") as f:
            content = f.read()
        assert "<guard " in content

    def test_finalize(self, tmp_path):
        receiver = DanmakuReceiver()
        output = str(tmp_path / "test.xml")
        dumper = DanmakuDumper(receiver, output)
        dumper._write_header()
        dumper.finalize()

        with open(output, encoding="utf-8") as f:
            content = f.read()
        assert content.strip().endswith("</i>")

    def test_written_count(self, tmp_path):
        receiver = DanmakuReceiver()
        output = str(tmp_path / "test.xml")
        dumper = DanmakuDumper(receiver, output)
        dumper._start_time = 1000.0
        dumper._write_header()

        for i in range(3):
            msg = DanmakuMessage.danmaku(1001.0 + i, f"msg{i}")
            dumper._messages.append(msg)
            dumper._written_count += 1
        dumper._flush_messages()

        assert dumper.written_count == 3

    def test_creates_directory(self, tmp_path):
        receiver = DanmakuReceiver()
        output = str(tmp_path / "subdir" / "test.xml")
        dumper = DanmakuDumper(receiver, output)
        dumper._write_header()
        assert os.path.exists(output)


# ── RawDanmakuReceiver ────────────────────────────────────────────────────────


class TestRawDanmakuReceiver:
    def test_push_and_get_nowait(self):
        r = RawDanmakuReceiver()
        data = {"cmd": "DANMU_MSG", "info": [0, "hello"]}
        r.push(data)
        assert r.queue_size == 1
        result = r.get_nowait()
        assert result is not None
        assert result["cmd"] == "DANMU_MSG"

    def test_get_nowait_empty(self):
        r = RawDanmakuReceiver()
        assert r.get_nowait() is None

    @pytest.mark.asyncio
    async def test_get_timeout_returns_none(self):
        r = RawDanmakuReceiver()
        result = await r.get(timeout=0.05)
        assert result is None

    def test_queue_overflow(self):
        r = RawDanmakuReceiver()
        for i in range(_MAX_QUEUE_SIZE + 5):
            r.push({"idx": i})
        assert r.queue_size == _MAX_QUEUE_SIZE
        assert r.dropped_count == 5

    def test_drain(self):
        r = RawDanmakuReceiver()
        for i in range(3):
            r.push({"idx": i})
        data = r.drain()
        assert len(data) == 3
        assert r.queue_size == 0

    def test_clear(self):
        r = RawDanmakuReceiver()
        r.push({"test": True})
        r.clear()
        assert r.queue_size == 0


# ── RawDanmakuDumper ─────────────────────────────────────────────────────────


class TestRawDanmakuDumper:
    def test_buffer_and_flush(self, tmp_path):
        receiver = RawDanmakuReceiver()
        output = str(tmp_path / "raw.jsonl")
        dumper = RawDanmakuDumper(receiver, output)

        dumper._buffer_data({"cmd": "DANMU_MSG", "info": "test"})
        assert dumper.written_count == 1
        assert len(dumper._buffer) == 1

        dumper._flush_buffer()
        with open(output, encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["cmd"] == "DANMU_MSG"

    def test_finalize(self, tmp_path):
        receiver = RawDanmakuReceiver()
        output = str(tmp_path / "raw.jsonl")
        dumper = RawDanmakuDumper(receiver, output)

        dumper._buffer_data({"cmd": "TEST"})
        dumper.finalize()

        with open(output, encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 1

    def test_creates_directory(self, tmp_path):
        receiver = RawDanmakuReceiver()
        output = str(tmp_path / "subdir" / "raw.jsonl")
        dumper = RawDanmakuDumper(receiver, output)
        os.makedirs(str(tmp_path / "subdir"), exist_ok=True)
        dumper._buffer_data({"test": True})
        dumper._flush_buffer()
        assert os.path.exists(output)

    def test_multiple_entries(self, tmp_path):
        receiver = RawDanmakuReceiver()
        output = str(tmp_path / "raw.jsonl")
        dumper = RawDanmakuDumper(receiver, output)

        for i in range(5):
            dumper._buffer_data({"idx": i})
        dumper.finalize()

        with open(output, encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 5
        assert dumper.written_count == 5
