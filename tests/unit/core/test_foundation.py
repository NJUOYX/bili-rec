"""Tests for core foundation modules."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from birec.bili.models import LiveStatus, RoomInfo, UserInfo
from birec.core.models import (
    Danmaku,
    DanmakuMessage,
    Gift,
    GuardBuy,
    StreamEvent,
    SuperChat,
)
from birec.core.path_provider import PathProvider, escape_path
from birec.core.statistics import SizedStatistics, Statistics
from birec.core.stream_param_holder import StreamParamHolder

UTC8 = timezone(timedelta(hours=8))


# ── Statistics ────────────────────────────────────────────────────────────────


class TestStatistics:
    def test_initial_state(self):
        stats = Statistics()
        assert stats.dl_total == 0
        assert stats.dl_rate == 0.0
        assert stats.danmu_total == 0
        assert stats.danmu_rate == 0.0
        assert stats.rec_elapsed == 0.0
        assert stats.rec_total == 0.0
        assert stats.rec_rate == 0.0

    def test_update_dl(self):
        stats = Statistics()
        stats.update_dl(1000)
        stats.update_dl(2000)
        assert stats.dl_total == 3000

    def test_update_danmu(self):
        stats = Statistics()
        stats.update_danmu(5)
        stats.update_danmu()  # default count=1
        assert stats.danmu_total == 6

    def test_start_stop(self):
        stats = Statistics()
        stats.start()
        assert stats._start_time is not None
        stats.stop()
        assert stats._start_time is None
        assert stats.rec_total > 0

    def test_reset(self):
        stats = Statistics()
        stats.update_dl(5000)
        stats.update_danmu(10)
        stats.start()
        stats.reset()
        assert stats.dl_total == 0
        assert stats.danmu_total == 0
        assert stats._start_time is None

    def test_tick_first_call(self):
        stats = Statistics()
        stats.start()
        stats.tick()  # first tick just sets baseline

    def test_tick_calculates_rate(self):
        stats = Statistics()
        stats.start()
        stats.update_dl(1000)
        stats._last_update = stats._start_time  # type: ignore[assignment]
        stats.tick()
        # Rate should be non-zero since we have data
        assert stats.dl_rate >= 0

    def test_snapshot(self):
        stats = Statistics()
        stats.update_dl(1000)
        stats.update_danmu(5)
        snap = stats.snapshot()
        assert snap["dl_total"] == 1000
        assert snap["danmu_total"] == 5
        assert "dl_rate" in snap
        assert "rec_elapsed" in snap


class TestSizedStatistics:
    def test_file_size(self):
        stats = SizedStatistics()
        stats.update_file_size(5000)
        assert stats.file_size == 5000

    def test_snapshot_includes_file_size(self):
        stats = SizedStatistics()
        stats.update_file_size(3000)
        snap = stats.snapshot()
        assert snap["file_size"] == 3000


# ── StreamParamHolder ─────────────────────────────────────────────────────────


class TestStreamParamHolder:
    def test_defaults(self):
        holder = StreamParamHolder()
        assert holder.stream_format == "flv"
        assert holder.stream_codec == "avc"
        assert holder.quality_number == 10000

    def test_custom_init(self):
        holder = StreamParamHolder("ts", "hevc", 400)
        assert holder.stream_format == "ts"
        assert holder.stream_codec == "hevc"
        assert holder.quality_number == 400

    def test_fallback_quality(self):
        holder = StreamParamHolder(quality_number=10000)
        next_q = holder.fallback_quality()
        assert next_q == 401  # next after 10000
        assert holder.quality_number == 401

    def test_fallback_quality_exhausted(self):
        holder = StreamParamHolder(quality_number=80)
        result = holder.fallback_quality()
        assert result is None

    def test_fallback_quality_unknown(self):
        holder = StreamParamHolder(quality_number=99999)  # type: ignore[arg-type]
        result = holder.fallback_quality()
        assert result is None

    def test_reset_quality(self):
        holder = StreamParamHolder(quality_number=10000)
        holder.fallback_quality()
        holder.reset_quality()
        assert holder.quality_number == 10000

    def test_next_platform(self):
        holder = StreamParamHolder()
        next_p = holder.next_platform()
        assert next_p == "android"
        assert holder.next_platform() is None

    def test_reset_platform(self):
        holder = StreamParamHolder()
        holder.next_platform()
        holder.reset_platform()
        assert holder.next_platform() == "android"

    def test_use_alternative(self):
        holder = StreamParamHolder()
        assert holder.use_alternative is False
        holder.use_alternative = True
        assert holder.use_alternative is True

    def test_reset_all(self):
        holder = StreamParamHolder()
        holder.fallback_quality()
        holder.next_platform()
        holder.use_alternative = True
        holder.reset()
        assert holder.quality_number == 10000
        assert holder.use_alternative is False

    def test_setters(self):
        holder = StreamParamHolder()
        holder.stream_format = "ts"
        holder.stream_codec = "hevc"
        holder.quality_number = 400
        assert holder.stream_format == "ts"
        assert holder.stream_codec == "hevc"
        assert holder.quality_number == 400


# ── PathProvider ──────────────────────────────────────────────────────────────


class TestEscapePath:
    def test_removes_illegal_chars(self):
        assert escape_path('a/b\\c:d*e?f"g<h>i|j') == "abcdefghij"

    def test_preserves_valid_chars(self):
        assert escape_path("hello world_123") == "hello world_123"


class TestPathProvider:
    def test_render_with_room_and_user(self, tmp_path):
        room = RoomInfo(
            room_id=12345,
            short_room_id=0,
            area_id=1,
            title="Test Room",
            area_name="Game",
            parent_area_id=1,
            parent_area_name="Entertainment",
            live_status=LiveStatus.LIVE,
            live_start_time=0,
            online=1,
            cover="",
            tags="",
            description="",
            uid=99,
        )
        user = UserInfo(uid=99, name="Streamer", gender="male", face="")
        pp = PathProvider(
            str(tmp_path),
            "{uname}/{roomid}/{year}{month}{day}",
            room,
            user,
        )
        now = datetime(2026, 7, 25, tzinfo=UTC8)
        result = pp.render(now)
        assert result == str(tmp_path / "Streamer/12345/20260725")

    def test_render_missing_vars_default_empty(self, tmp_path):
        pp = PathProvider(str(tmp_path), "{uname}/{roomid}")
        now = datetime(2026, 1, 1, tzinfo=UTC8)
        result = pp.render(now)
        # Missing vars should be empty strings
        assert result == str(tmp_path / "/")

    def test_render_time_only(self, tmp_path):
        pp = PathProvider(str(tmp_path), "{year}-{month}-{day}_{hour}{minute}{second}")
        now = datetime(2026, 3, 15, 14, 30, 45, tzinfo=UTC8)
        result = pp.render(now)
        assert result == str(tmp_path / "2026-03-15_143045")

    def test_update_info(self, tmp_path):
        pp = PathProvider(str(tmp_path), "{roomid}")
        room = RoomInfo(
            room_id=999,
            short_room_id=0,
            area_id=1,
            title="",
            area_name="",
            parent_area_id=1,
            parent_area_name="",
            live_status=LiveStatus.PREPARING,
            live_start_time=0,
            online=0,
            cover="",
            tags="",
            description="",
            uid=1,
        )
        pp.update_info(room_info=room)
        now = datetime(2026, 1, 1, tzinfo=UTC8)
        assert pp.render(now) == str(tmp_path / "999")

    def test_make_dirs(self, tmp_path):
        pp = PathProvider(str(tmp_path), "test")
        target = str(tmp_path / "a" / "b" / "c" / "file.flv")
        result = pp.make_dirs(target)
        assert result == target
        assert os.path.isdir(str(tmp_path / "a" / "b" / "c"))

    def test_dedup_no_conflict(self, tmp_path):
        pp = PathProvider(str(tmp_path), "test")
        result = pp.dedup(str(tmp_path / "video"), ".flv")
        assert result == str(tmp_path / "video.flv")

    def test_dedup_with_conflict(self, tmp_path):
        pp = PathProvider(str(tmp_path), "test")
        # Create the file
        (tmp_path / "video.flv").touch()
        result = pp.dedup(str(tmp_path / "video"), ".flv")
        assert result == str(tmp_path / "video_1.flv")

    def test_dedup_multiple_conflicts(self, tmp_path):
        pp = PathProvider(str(tmp_path), "test")
        (tmp_path / "video.flv").touch()
        (tmp_path / "video_1.flv").touch()
        (tmp_path / "video_2.flv").touch()
        result = pp.dedup(str(tmp_path / "video"), ".flv")
        assert result == str(tmp_path / "video_3.flv")

    def test_video_path(self, tmp_path):
        pp = PathProvider(str(tmp_path), "{roomid}")
        room = RoomInfo(
            room_id=100,
            short_room_id=0,
            area_id=1,
            title="",
            area_name="",
            parent_area_id=1,
            parent_area_name="",
            live_status=LiveStatus.LIVE,
            live_start_time=0,
            online=1,
            cover="",
            tags="",
            description="",
            uid=1,
        )
        pp.update_info(room_info=room)
        now = datetime(2026, 1, 1, tzinfo=UTC8)
        result = pp.video_path(now)
        assert result.endswith(".flv")
        assert "100" in result

    def test_danmaku_path(self, tmp_path):
        pp = PathProvider(str(tmp_path), "test")
        result = pp.danmaku_path("/path/to/video.flv")
        assert result == "/path/to/video.xml"

    def test_raw_danmaku_path(self, tmp_path):
        pp = PathProvider(str(tmp_path), "test")
        result = pp.raw_danmaku_path("/path/to/video.flv")
        assert result == "/path/to/video.jsonl"

    def test_cover_path(self, tmp_path):
        pp = PathProvider(str(tmp_path), "test")
        result = pp.cover_path("/path/to/video.flv")
        assert result == "/path/to/video.jpg"

    def test_cover_path_custom_ext(self, tmp_path):
        pp = PathProvider(str(tmp_path), "test")
        result = pp.cover_path("/path/to/video.flv", ".png")
        assert result == "/path/to/video.png"

    def test_meta_path(self, tmp_path):
        pp = PathProvider(str(tmp_path), "test")
        result = pp.meta_path("/path/to/video.flv")
        assert result == "/path/to/video.meta"

    def test_meta_json_path(self, tmp_path):
        pp = PathProvider(str(tmp_path), "test")
        result = pp.meta_json_path("/path/to/video.flv")
        assert result == "/path/to/video.meta.json"

    def test_out_dir_property(self, tmp_path):
        pp = PathProvider(str(tmp_path), "test")
        assert pp.out_dir == str(tmp_path)
        new_dir = str(tmp_path / "new")
        pp.out_dir = new_dir
        assert pp.out_dir == new_dir


# ── Models ────────────────────────────────────────────────────────────────────


class TestDanmaku:
    def test_create(self):
        d = Danmaku(timestamp=1.0, content="hello")
        assert d.timestamp == 1.0
        assert d.content == "hello"
        assert d.uid == 0
        assert d.color == 0xFFFFFF

    def test_frozen(self):
        d = Danmaku(timestamp=1.0, content="hello")
        with pytest.raises(AttributeError):
            d.content = "changed"  # type: ignore[misc]


class TestSuperChat:
    def test_create(self):
        sc = SuperChat(timestamp=2.0, uid=1, uname="user", price=30, content="SC!")
        assert sc.price == 30
        assert sc.content == "SC!"


class TestGift:
    def test_create(self):
        g = Gift(timestamp=3.0, uid=1, uname="user", gift_name="小花")
        assert g.gift_name == "小花"
        assert g.num == 1
        assert g.action == "投喂"


class TestGuardBuy:
    def test_create(self):
        gb = GuardBuy(timestamp=4.0, uid=1, uname="user", guard_level=3)
        assert gb.guard_level == 3


class TestDanmakuMessage:
    def test_danmaku_factory(self):
        msg = DanmakuMessage.danmaku(1.0, "hello", uid=42, uname="test")
        assert msg.type == "danmaku"
        assert isinstance(msg.data, Danmaku)
        assert msg.data.content == "hello"
        assert msg.data.uid == 42

    def test_super_chat_factory(self):
        msg = DanmakuMessage.super_chat(2.0, 1, "user", 30, "SC!")
        assert msg.type == "super_chat"
        assert isinstance(msg.data, SuperChat)

    def test_gift_factory(self):
        msg = DanmakuMessage.gift(3.0, 1, "user", "小花")
        assert msg.type == "gift"
        assert isinstance(msg.data, Gift)

    def test_guard_buy_factory(self):
        msg = DanmakuMessage.guard_buy(4.0, 1, "user", 3)
        assert msg.type == "guard_buy"
        assert isinstance(msg.data, GuardBuy)


class TestStreamEvent:
    def test_create(self):
        event = StreamEvent(type="stream_started", room_id=12345)
        assert event.type == "stream_started"
        assert event.room_id == 12345
        assert event.reason == ""

    def test_with_reason(self):
        event = StreamEvent(type="stream_failed", room_id=12345, reason="timeout")
        assert event.reason == "timeout"
