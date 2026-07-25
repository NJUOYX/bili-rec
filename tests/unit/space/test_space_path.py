"""Tests for space and path modules."""

from __future__ import annotations

import time
from pathlib import Path

from birec.path import (
    deduplicate_path,
    derive_path,
    escape_path,
    render_template,
    validate_template,
)
from birec.space import SpaceInfo, SpaceMonitor, SpaceReclaimer


class TestSpaceInfo:
    def test_percent_used(self) -> None:
        info = SpaceInfo(total=100, used=75, free=25, path="/")
        assert info.percent_used == 75.0

    def test_percent_used_zero_total(self) -> None:
        info = SpaceInfo(total=0, used=0, free=0, path="/")
        assert info.percent_used == 0.0


class TestSpaceMonitor:
    def test_get_space_info(self, tmp_path) -> None:
        monitor = SpaceMonitor(tmp_path)
        info = monitor.get_space_info()
        assert info.total > 0
        assert info.free > 0
        assert info.path == str(tmp_path)

    def test_not_running_initially(self, tmp_path) -> None:
        monitor = SpaceMonitor(tmp_path)
        assert not monitor.is_running


class TestSpaceReclaimer:
    def test_find_reclaimable_files(self, tmp_path) -> None:
        # Create old files
        old_file = tmp_path / "old.flv"
        old_file.write_bytes(b"data")
        # Set mtime to 48 hours ago
        old_time = time.time() - 48 * 3600
        import os

        os.utime(old_file, (old_time, old_time))

        # Create recent file
        new_file = tmp_path / "new.flv"
        new_file.write_bytes(b"data")

        reclaimer = SpaceReclaimer([tmp_path], rec_ttl=24 * 3600)
        files = reclaimer.find_reclaimable_files()
        assert len(files) == 1
        assert files[0] == old_file

    def test_find_reclaimable_respects_extension(self, tmp_path) -> None:
        old_file = tmp_path / "old.txt"
        old_file.write_bytes(b"data")
        old_time = time.time() - 48 * 3600
        import os

        os.utime(old_file, (old_time, old_time))

        reclaimer = SpaceReclaimer([tmp_path], rec_ttl=24 * 3600)
        files = reclaimer.find_reclaimable_files()
        assert len(files) == 0

    def test_reclaim(self, tmp_path) -> None:
        old_file = tmp_path / "old.flv"
        old_file.write_bytes(b"x" * 1000)
        old_time = time.time() - 48 * 3600
        import os

        os.utime(old_file, (old_time, old_time))

        reclaimer = SpaceReclaimer([tmp_path], rec_ttl=24 * 3600)
        reclaimed = reclaimer.reclaim(target_free=0)
        assert reclaimed == 1000
        assert not old_file.exists()


class TestEscapePath:
    def test_basic(self) -> None:
        assert escape_path("hello world") == "hello world"

    def test_unsafe_chars(self) -> None:
        assert escape_path('a<b>c:d"e') == "a_b_c_d_e"

    def test_strips_dots_and_spaces(self) -> None:
        assert escape_path("..test..") == "test"

    def test_backslash(self) -> None:
        assert escape_path("a\\b") == "a_b"


class TestRenderTemplate:
    def test_basic_substitution(self) -> None:
        result = render_template("{roomid}_{uname}", roomid=12345, uname="test")
        assert result == "12345_test"

    def test_datetime_variables(self) -> None:
        result = render_template(
            "{year}-{month}-{day}",
            year="2026",
            month="07",
            day="25",
        )
        assert result == "2026-07-25"

    def test_escapes_values(self) -> None:
        result = render_template("{title}", title='test<>:"file')
        assert "<" not in result
        assert ">" not in result


class TestDerivePath:
    def test_xml(self) -> None:
        base = Path("/recordings/stream.flv")
        assert derive_path(base, ".xml") == Path("/recordings/stream.xml")

    def test_ass(self) -> None:
        base = Path("/recordings/stream.flv")
        assert derive_path(base, ".ass") == Path("/recordings/stream.ass")

    def test_meta_json(self) -> None:
        base = Path("/recordings/stream.flv")
        result = derive_path(base, ".meta.json")
        assert result.name == "stream.meta.json"


class TestDeduplicatePath:
    def test_no_conflict(self, tmp_path) -> None:
        path = tmp_path / "new_file.flv"
        assert deduplicate_path(path) == path

    def test_with_conflict(self, tmp_path) -> None:
        existing = tmp_path / "file.flv"
        existing.write_bytes(b"data")
        result = deduplicate_path(existing)
        assert result == tmp_path / "file_1.flv"

    def test_multiple_conflicts(self, tmp_path) -> None:
        (tmp_path / "file.flv").write_bytes(b"1")
        (tmp_path / "file_1.flv").write_bytes(b"2")
        result = deduplicate_path(tmp_path / "file.flv")
        assert result == tmp_path / "file_2.flv"


class TestValidateTemplate:
    def test_valid(self) -> None:
        assert validate_template("{roomid}/{uname}/{title}") is True

    def test_invalid(self) -> None:
        assert validate_template("{roomid}/{invalid_var}") is False

    def test_no_vars(self) -> None:
        assert validate_template("static/path") is True
