"""Tests for birec.core.statistics — mutation-killing precision."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from birec.core.statistics import SizedStatistics, Statistics


class TestStatisticsInit:
    """Verify every initial field value so __init__ mutants die."""

    def test_initial_values(self) -> None:
        s = Statistics()
        assert s._dl_total == 0
        assert s._dl_rate == 0.0
        assert s._danmu_total == 0
        assert s._danmu_rate == 0.0
        assert s._rec_elapsed == 0.0
        assert s._rec_total == 0.0
        assert s._rec_rate == 0.0
        assert s._start_time is None
        assert s._last_update is None
        assert s._last_dl == 0
        assert s._last_danmu == 0

    def test_properties_reflect_init(self) -> None:
        s = Statistics()
        assert s.dl_total == 0
        assert s.dl_rate == 0.0
        assert s.danmu_total == 0
        assert s.danmu_rate == 0.0
        assert s.rec_elapsed == 0.0
        assert s.rec_total == 0.0
        assert s.rec_rate == 0.0


class TestStartStop:
    """start/stop timer with mocked monotonic."""

    def test_start_sets_timestamps(self) -> None:
        s = Statistics()
        with patch("birec.core.statistics.time.monotonic", return_value=100.0):
            s.start()
        assert s._start_time == 100.0
        assert s._last_update == 100.0

    def test_stop_accumulates_elapsed(self) -> None:
        s = Statistics()
        with patch("birec.core.statistics.time.monotonic", return_value=10.0):
            s.start()
        with patch("birec.core.statistics.time.monotonic", return_value=15.5):
            s.stop()
        assert s._rec_elapsed == pytest.approx(5.5)
        assert s._rec_total == pytest.approx(5.5)
        assert s._start_time is None
        assert s._last_update is None

    def test_stop_without_start_is_noop(self) -> None:
        s = Statistics()
        s.stop()
        assert s._rec_elapsed == 0.0
        assert s._rec_total == 0.0
        assert s._start_time is None

    def test_multiple_start_stop_accumulates_total(self) -> None:
        s = Statistics()
        with patch("birec.core.statistics.time.monotonic", return_value=0.0):
            s.start()
        with patch("birec.core.statistics.time.monotonic", return_value=3.0):
            s.stop()
        with patch("birec.core.statistics.time.monotonic", return_value=10.0):
            s.start()
        with patch("birec.core.statistics.time.monotonic", return_value=12.0):
            s.stop()
        assert s._rec_total == pytest.approx(5.0)
        assert s._rec_elapsed == pytest.approx(2.0)

    def test_rec_elapsed_while_running(self) -> None:
        s = Statistics()
        with patch("birec.core.statistics.time.monotonic", return_value=5.0):
            s.start()
        with patch("birec.core.statistics.time.monotonic", return_value=8.0):
            assert s.rec_elapsed == pytest.approx(3.0)

    def test_rec_elapsed_after_stop_returns_frozen(self) -> None:
        s = Statistics()
        with patch("birec.core.statistics.time.monotonic", return_value=5.0):
            s.start()
        with patch("birec.core.statistics.time.monotonic", return_value=9.0):
            s.stop()
        # After stop, rec_elapsed returns _rec_elapsed (frozen)
        with patch("birec.core.statistics.time.monotonic", return_value=100.0):
            assert s.rec_elapsed == pytest.approx(4.0)


class TestReset:
    """reset() must zero every field."""

    def test_reset_clears_all(self) -> None:
        s = Statistics()
        with patch("birec.core.statistics.time.monotonic", return_value=0.0):
            s.start()
        s.update_dl(5000)
        s.update_danmu(10)
        with patch("birec.core.statistics.time.monotonic", return_value=2.0):
            s.tick()
        with patch("birec.core.statistics.time.monotonic", return_value=5.0):
            s.stop()

        s.reset()

        assert s._dl_total == 0
        assert s._dl_rate == 0.0
        assert s._danmu_total == 0
        assert s._danmu_rate == 0.0
        assert s._rec_elapsed == 0.0
        assert s._rec_total == 0.0
        assert s._rec_rate == 0.0
        assert s._start_time is None
        assert s._last_update is None
        assert s._last_dl == 0
        assert s._last_danmu == 0


class TestUpdateMethods:
    """update_dl and update_danmu accumulate correctly."""

    def test_update_dl_accumulates(self) -> None:
        s = Statistics()
        s.update_dl(100)
        s.update_dl(200)
        assert s.dl_total == 300

    def test_update_danmu_default_count(self) -> None:
        s = Statistics()
        s.update_danmu()
        assert s.danmu_total == 1

    def test_update_danmu_explicit_count(self) -> None:
        s = Statistics()
        s.update_danmu(5)
        s.update_danmu(3)
        assert s.danmu_total == 8


class TestTick:
    """tick() rate calculations with controlled time."""

    def test_tick_without_start_sets_last_update(self) -> None:
        s = Statistics()
        with patch("birec.core.statistics.time.monotonic", return_value=50.0):
            s.tick()
        assert s._last_update == 50.0
        # No rate computed on first tick
        assert s._dl_rate == 0.0
        assert s._danmu_rate == 0.0

    def test_tick_zero_dt_is_noop(self) -> None:
        s = Statistics()
        with patch("birec.core.statistics.time.monotonic", return_value=10.0):
            s.start()
        # tick at same time → dt == 0
        with patch("birec.core.statistics.time.monotonic", return_value=10.0):
            s.tick()
        assert s._dl_rate == 0.0
        assert s._danmu_rate == 0.0

    def test_tick_computes_rates(self) -> None:
        s = Statistics()
        with patch("birec.core.statistics.time.monotonic", return_value=0.0):
            s.start()
        s.update_dl(1000)
        s.update_danmu(20)
        with patch("birec.core.statistics.time.monotonic", return_value=2.0):
            s.tick()
        # dl_rate = (1000 - 0) / 2.0 = 500
        assert s._dl_rate == pytest.approx(500.0)
        # danmu_rate = (20 - 0) / 2.0 = 10
        assert s._danmu_rate == pytest.approx(10.0)
        # rec_rate = dl_total / elapsed = 1000 / 2.0 = 500
        assert s._rec_rate == pytest.approx(500.0)
        # last markers updated
        assert s._last_dl == 1000
        assert s._last_danmu == 20
        assert s._last_update == 2.0

    def test_tick_incremental_rate(self) -> None:
        s = Statistics()
        with patch("birec.core.statistics.time.monotonic", return_value=0.0):
            s.start()
        s.update_dl(1000)
        with patch("birec.core.statistics.time.monotonic", return_value=1.0):
            s.tick()
        # Second interval: only 500 new bytes in 1s
        s.update_dl(500)
        with patch("birec.core.statistics.time.monotonic", return_value=2.0):
            s.tick()
        assert s._dl_rate == pytest.approx(500.0)
        assert s._last_dl == 1500

    def test_tick_updates_last_update(self) -> None:
        s = Statistics()
        with patch("birec.core.statistics.time.monotonic", return_value=0.0):
            s.start()
        with patch("birec.core.statistics.time.monotonic", return_value=1.0):
            s.tick()
        assert s._last_update == 1.0
        with patch("birec.core.statistics.time.monotonic", return_value=3.0):
            s.tick()
        assert s._last_update == 3.0

    def test_tick_rec_rate_zero_elapsed(self) -> None:
        """When not started, elapsed is 0 so rec_rate stays unchanged."""
        s = Statistics()
        s._last_update = 0.0  # simulate prior tick
        s.update_dl(100)
        with patch("birec.core.statistics.time.monotonic", return_value=1.0):
            s.tick()
        # elapsed == 0 (never started), so rec_rate not updated
        assert s._rec_rate == 0.0


class TestSnapshot:
    """snapshot() returns precise dict with rounded values."""

    def test_snapshot_keys_and_values(self) -> None:
        s = Statistics()
        with patch("birec.core.statistics.time.monotonic", return_value=0.0):
            s.start()
        s.update_dl(2048)
        s.update_danmu(7)
        with patch("birec.core.statistics.time.monotonic", return_value=4.0):
            s.tick()

        with patch("birec.core.statistics.time.monotonic", return_value=4.0):
            snap = s.snapshot()

        assert snap["dl_total"] == 2048
        assert snap["dl_rate"] == 512.0  # 2048/4 rounded
        assert snap["danmu_total"] == 7
        assert snap["danmu_rate"] == 1.75  # 7/4 rounded
        assert snap["rec_elapsed"] == 4.0
        assert snap["rec_total"] == 0.0  # not stopped yet
        assert snap["rec_rate"] == 512.0  # 2048/4

    def test_snapshot_rounding(self) -> None:
        s = Statistics()
        with patch("birec.core.statistics.time.monotonic", return_value=0.0):
            s.start()
        s.update_dl(1)
        s.update_danmu(1)
        with patch("birec.core.statistics.time.monotonic", return_value=3.0):
            s.tick()
        with patch("birec.core.statistics.time.monotonic", return_value=3.0):
            snap = s.snapshot()
        # 1/3 = 0.333... → rounded to 0.33
        assert snap["dl_rate"] == 0.33
        assert snap["danmu_rate"] == 0.33
        assert snap["rec_rate"] == 0.33

    def test_snapshot_after_stop(self) -> None:
        s = Statistics()
        with patch("birec.core.statistics.time.monotonic", return_value=0.0):
            s.start()
        s.update_dl(500)
        with patch("birec.core.statistics.time.monotonic", return_value=2.0):
            s.tick()
        with patch("birec.core.statistics.time.monotonic", return_value=5.0):
            s.stop()
        with patch("birec.core.statistics.time.monotonic", return_value=99.0):
            snap = s.snapshot()
        assert snap["rec_elapsed"] == 5.0
        assert snap["rec_total"] == 5.0
        assert snap["dl_total"] == 500

    def test_snapshot_initial(self) -> None:
        s = Statistics()
        snap = s.snapshot()
        assert snap == {
            "dl_total": 0,
            "dl_rate": 0.0,
            "danmu_total": 0,
            "danmu_rate": 0.0,
            "rec_elapsed": 0.0,
            "rec_total": 0.0,
            "rec_rate": 0.0,
        }


class TestSizedStatistics:
    """SizedStatistics extends Statistics with file_size."""

    def test_initial_file_size(self) -> None:
        s = SizedStatistics()
        assert s.file_size == 0
        assert s._file_size == 0

    def test_update_file_size(self) -> None:
        s = SizedStatistics()
        s.update_file_size(9999)
        assert s.file_size == 9999

    def test_snapshot_includes_file_size(self) -> None:
        s = SizedStatistics()
        s.update_dl(100)
        s.update_file_size(4096)
        snap = s.snapshot()
        assert snap["file_size"] == 4096
        assert snap["dl_total"] == 100
        assert "dl_rate" in snap
        assert "danmu_total" in snap
        assert "danmu_rate" in snap
        assert "rec_elapsed" in snap
        assert "rec_total" in snap
        assert "rec_rate" in snap

    def test_inherits_statistics_behavior(self) -> None:
        s = SizedStatistics()
        with patch("birec.core.statistics.time.monotonic", return_value=0.0):
            s.start()
        s.update_dl(200)
        s.update_danmu(4)
        with patch("birec.core.statistics.time.monotonic", return_value=2.0):
            s.tick()
        assert s.dl_rate == pytest.approx(100.0)
        assert s.danmu_rate == pytest.approx(2.0)
