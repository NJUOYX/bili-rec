"""The invariant monitor's own tests (#19, scheme 1).

The real system tests only reach a violated invariant when a fixed bug is
re-introduced, so these tests feed the monitor hand-made applications instead:
simple objects shaped like the parts of a real application the monitor reads.
That makes every invariant checkable at controlled moments, deterministically
and without a server.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from .invariant_monitor import EVENTUALLY_GRACE, GROWTH_GRACE, InvariantMonitor


def make_task(
    room_id: int,
    *,
    status: str = "stopped",
    dl: int = 0,
    enabled: bool = True,
    living: bool = False,
) -> Any:
    """A task as the monitor sees it, with handles the test can mutate."""
    stats = SimpleNamespace(dl_total=dl)
    return SimpleNamespace(
        room_id=room_id,
        running_status=SimpleNamespace(value=status),
        recorder_enabled=enabled,
        monitor=SimpleNamespace(is_living=living),
        recorder=SimpleNamespace(stream_recorder=SimpleNamespace(statistics=stats)),
        stats=stats,
    )


def make_app(out_dir: Path, tasks: list[Any]) -> Any:
    """An application as the monitor sees it."""
    return SimpleNamespace(
        output_dir=out_dir,
        task_manager=SimpleNamespace(get_all_tasks=lambda: list(tasks)),
    )


def write(out_dir: Path, room_id: int, size: int) -> None:
    """Bring that room's recording to this size on disk."""
    room_dir = out_dir / f"{room_id} - TestStreamer"
    room_dir.mkdir(parents=True, exist_ok=True)
    (room_dir / f"blive_{room_id}.flv").write_bytes(b"x" * size)


def run(monitor: InvariantMonitor, start: float, duration: float) -> None:
    """Sample every interval from ``start`` to ``start + duration``."""
    t = start
    while t <= start + duration:
        monitor.sample(now=t)
        t += 0.1


@pytest.fixture
def monitor() -> InvariantMonitor:
    return InvariantMonitor("tests/system/test_invariant_monitor.py::test_case")


@pytest.fixture
def out_dir(tmp_path: Path) -> Path:
    return tmp_path / "recordings"


class TestRecordingMeansDiskGrows:
    """running_status == recording ⟹ disk bytes must be growing."""

    def test_a_growing_disk_passes(
        self, monitor: InvariantMonitor, out_dir: Path
    ) -> None:
        task = make_task(1, status="recording")
        monitor.register(make_app(out_dir, [task]))

        for second in range(6):
            write(out_dir, 1, 1000 * (second + 1))
            run(monitor, float(second), 1.0)

        assert monitor.violations == []

    def test_a_frozen_disk_fails(
        self, monitor: InvariantMonitor, out_dir: Path
    ) -> None:
        task = make_task(1, status="recording")
        monitor.register(make_app(out_dir, [task]))
        write(out_dir, 1, 500)

        run(monitor, 0.0, GROWTH_GRACE + 1.0)

        assert len(monitor.violations) == 1
        violation = monitor.violations[0]
        assert "recording" in violation.invariant
        assert violation.room_id == 1
        # The failure has to be locatable: the observed sequence goes with it.
        assert violation.samples, "no observed sequence in the violation"

    def test_growth_resets_the_window(
        self, monitor: InvariantMonitor, out_dir: Path
    ) -> None:
        """A stall shorter than the grace, followed by growth, is a reconnect."""
        task = make_task(1, status="recording")
        monitor.register(make_app(out_dir, [task]))
        write(out_dir, 1, 500)

        run(monitor, 0.0, GROWTH_GRACE - 1.0)
        write(out_dir, 1, 1500)
        run(monitor, GROWTH_GRACE, GROWTH_GRACE - 1.0)

        assert monitor.violations == []

    def test_stops_counting_once_the_claim_stops(
        self, monitor: InvariantMonitor, out_dir: Path
    ) -> None:
        task = make_task(1, status="recording")
        monitor.register(make_app(out_dir, [task]))
        write(out_dir, 1, 500)

        run(monitor, 0.0, GROWTH_GRACE - 1.0)
        task.running_status = SimpleNamespace(value="stopped")
        run(monitor, GROWTH_GRACE, GROWTH_GRACE + 5.0)

        assert monitor.violations == []


class TestDlGrowthMeansDiskGrows:
    """dl_total going up ⟹ the disk must follow within the grace."""

    def test_a_counter_the_disk_follows_passes(
        self, monitor: InvariantMonitor, out_dir: Path
    ) -> None:
        task = make_task(1, status="recording")
        monitor.register(make_app(out_dir, [task]))

        for second in range(6):
            task.stats.dl_total += 1000
            write(out_dir, 1, 1000 * (second + 1))
            run(monitor, float(second), 1.0)

        assert monitor.violations == []

    def test_a_counter_the_disk_ignores_fails(
        self, monitor: InvariantMonitor, out_dir: Path
    ) -> None:
        task = make_task(1, status="recording")
        monitor.register(make_app(out_dir, [task]))
        write(out_dir, 1, 500)

        for second in range(5):
            task.stats.dl_total += 1000
            run(monitor, float(second), 1.0)

        assert any("dl_total" in v.invariant for v in monitor.violations)

    def test_a_counter_reset_clears_a_pending_window(
        self, monitor: InvariantMonitor, out_dir: Path
    ) -> None:
        """The counter rewinds at a segment boundary; a growth window that was
        open at that moment must go with it rather than fire three seconds
        later over a download that belongs to a previous file."""
        task = make_task(1, status="recording")
        monitor.register(make_app(out_dir, [task]))
        write(out_dir, 1, 500)
        run(monitor, 0.0, 1.0)

        task.stats.dl_total = 3000
        monitor.sample(now=1.2)  # the download moved, the disk has not yet
        task.stats.dl_total = 0  # the segment boundary rewinds the counter
        task.running_status = SimpleNamespace(value="stopped")
        run(monitor, 1.5, 6.0)  # idle; a stuck window would fire in here

        assert monitor.violations == []


class TestEnabledAndLiveMeansEventuallyRecording:
    """recorder enabled + room live ⟹ the task must end up recording."""

    def test_an_enabled_live_room_left_waiting_fails(
        self, monitor: InvariantMonitor, out_dir: Path
    ) -> None:
        task = make_task(1, enabled=True, living=True)
        monitor.register(make_app(out_dir, [task]))

        run(monitor, 0.0, EVENTUALLY_GRACE + 1.0)

        assert any("recording" in v.invariant for v in monitor.violations)

    def test_starting_within_the_grace_passes(
        self, monitor: InvariantMonitor, out_dir: Path
    ) -> None:
        task = make_task(1, enabled=True, living=True)
        monitor.register(make_app(out_dir, [task]))
        run(monitor, 0.0, 2.0)

        task.running_status = SimpleNamespace(value="recording")
        for second in range(2, 8):
            write(out_dir, 1, 1000 * (second - 1))
            run(monitor, float(second), 1.0)

        assert monitor.violations == []

    def test_disabled_or_offline_rooms_are_not_held_to_it(
        self, monitor: InvariantMonitor, out_dir: Path
    ) -> None:
        disabled = make_task(1, enabled=False, living=True)
        offline = make_task(2, enabled=True, living=False)
        monitor.register(make_app(out_dir, [disabled, offline]))

        run(monitor, 0.0, EVENTUALLY_GRACE + 2.0)

        assert monitor.violations == []


class TestPerRoomAttribution:
    """One room lying must not hide behind another room writing."""

    def test_a_lying_room_is_caught_despite_a_writing_room(
        self, monitor: InvariantMonitor, out_dir: Path
    ) -> None:
        liar = make_task(1, status="recording")
        writer = make_task(2, status="recording")
        monitor.register(make_app(out_dir, [liar, writer]))
        write(out_dir, 1, 100)  # the liar's one tiny file, never growing

        for second in range(5):
            write(out_dir, 2, 1000 * (second + 1))
            run(monitor, float(second), 1.0)

        assert {v.room_id for v in monitor.violations} == {1}

    def test_unattributable_growth_is_never_blamed(
        self, monitor: InvariantMonitor, out_dir: Path
    ) -> None:
        """Files no room owns count for every room: better to miss a lie than
        to accuse a task over a file it may well have written."""
        task = make_task(1, status="recording")
        monitor.register(make_app(out_dir, [task]))
        (out_dir / "somewhere_else").mkdir(parents=True, exist_ok=True)

        for second in range(5):
            (out_dir / "somewhere_else" / "mystery.bin").write_bytes(
                b"x" * 1000 * (second + 1)
            )
            run(monitor, float(second), 1.0)

        assert monitor.violations == []


class TestTheReport:
    def test_the_report_names_the_test_the_invariant_and_the_sequence(
        self, monitor: InvariantMonitor, out_dir: Path
    ) -> None:
        task = make_task(1, status="recording")
        monitor.register(make_app(out_dir, [task]))
        write(out_dir, 1, 500)
        run(monitor, 0.0, GROWTH_GRACE + 1.0)

        report = monitor.report()
        assert "test_case" in report
        assert "room 1" in report
        assert "dl=" in report and "disk=" in report

    def test_no_apps_no_sampling_no_violations(self, monitor: InvariantMonitor) -> None:
        run(monitor, 0.0, 10.0)
        assert monitor.violations == []


def test_the_graces_fit_inside_the_harness_budgets() -> None:
    """The graces must stay between the longest legitimate pause and the
    harness's own timeout, or the monitor would either miss real lies or fire
    after the test has already given up waiting."""
    assert 1.0 < GROWTH_GRACE < 20.0
    assert GROWTH_GRACE < EVENTUALLY_GRACE < 20.0
