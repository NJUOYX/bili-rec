"""The invariant monitor: a background witness for the system tests (#19).

The class-A "lying" bugs have happened nine times, and every one of them
violated the same mechanical invariant:

    running_status == "recording"  ⟹  disk bytes must be growing

Rather than relying on every test to remember to assert that, the autouse
``invariant_monitor`` fixture in the system conftest hooks every application
that starts up and samples its tasks and its disk in the background for the
whole test. Any invariant violated at any moment fails the test, and the
failure carries the observed sequence so it can be located. New system tests
get this protection for free.

The invariants checked:

- recording ⟹ disk grows: a task claiming to record must see the disk grow
  within ``GROWTH_GRACE`` seconds;
- dl_total grows ⟹ disk grows: the download counter moving must be followed
  by disk bytes within ``GROWTH_GRACE`` seconds;
- recorder enabled + live ⟹ eventually recording: an enabled task cannot sit
  out of the recording state for more than ``EVENTUALLY_GRACE`` seconds while
  its room is live.

``connected ⟹ danmaku arrives`` is deliberately not checked: the fake server
only sends danmaku when a test calls ``send_danmaku`` itself, so the monitor
cannot tell "nothing arrived" from "nothing was sent".
"""

from __future__ import annotations

import asyncio
import contextlib
import time
import traceback
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# How often the monitor looks at the application, in seconds.
SAMPLE_INTERVAL = 0.1

# The longest a "recording, but the disk is frozen" state may legitimately
# last: a clean stream end costs a one-second wait before the re-fetch, plus
# connection setup. Anything frozen longer than this is a lie.
GROWTH_GRACE = 3.0

# The longest an enabled task may legitimately sit out of recording while its
# room is live: going live reaches the file in well under a second normally.
EVENTUALLY_GRACE = 5.0

# How many recent samples each failure message carries.
_HISTORY_LENGTH = 40


@dataclass(frozen=True, slots=True)
class Violation:
    """One caught lie: which invariant, which room, and what was observed."""

    invariant: str
    room_id: int
    detail: str
    samples: tuple[str, ...]


@dataclass(slots=True)
class _TaskWindow:
    """The state the monitor keeps per task between samples."""

    growth_at: float = 0.0
    growth_disk: int = 0
    recording: bool = False
    last_dl: int = 0
    dl_since: float | None = None
    dl_disk: int = 0
    stuck_since: float | None = None


class InvariantMonitor:
    """Samples every registered application and records violations.

    The conftest fixture registers applications on startup and unregisters
    them on shutdown. The sampler task is born on the loop the first
    application runs on and retires when the last one leaves, so tests that
    never start an application cost nothing.
    """

    def __init__(self, test_name: str) -> None:
        self.test_name = test_name
        self.violations: list[Violation] = []
        self._apps: list[Any] = []
        self._windows: dict[tuple[int, int], _TaskWindow] = {}
        self._histories: dict[tuple[int, int], deque[str]] = {}
        self._sampler: asyncio.Task[None] | None = None
        self._first_sample_at: float | None = None
        self._internal_error_reported = False

    # ── lifecycle ───────────────────────────────────────────────────

    def register(self, app: Any) -> None:
        """Start watching an application, from inside its running loop."""
        if app not in self._apps:
            self._apps.append(app)
        if self._sampler is not None and not self._sampler.done():
            return
        with contextlib.suppress(RuntimeError):
            self._sampler = asyncio.get_running_loop().create_task(self._run())

    def unregister(self, app: Any) -> None:
        """Stop watching an application before it is torn down."""
        if app in self._apps:
            self._apps.remove(app)
        if not self._apps and self._sampler is not None and not self._sampler.done():
            self._sampler.cancel()

    async def _run(self) -> None:
        while self._apps:
            await asyncio.sleep(SAMPLE_INTERVAL)
            self.sample()

    # ── sampling ────────────────────────────────────────────────────

    def sample(self, now: float | None = None) -> None:
        """One pass over every registered application.

        Called by the sampler loop in production; tests call it directly with
        chosen timestamps to drive the windows deterministically.
        """
        now = time.monotonic() if now is None else now
        for app in list(self._apps):
            tasks = list(app.task_manager.get_all_tasks())
            try:
                files = _scan_files(app)
            except Exception:
                self._internal_error("scanning the disk")
                continue
            totals = _disk_totals(files, [task.room_id for task in tasks])
            for task in tasks:
                try:
                    self._sample_task(app, task, totals[task.room_id], now)
                except Exception:
                    self._internal_error(f"sampling room {task.room_id}")

    def _sample_task(self, app: Any, task: Any, disk: int, now: float) -> None:
        key = (id(app), task.room_id)
        window = self._windows.setdefault(key, _TaskWindow())
        status = str(task.running_status.value)
        dl_total: int = task.recorder.stream_recorder.statistics.dl_total
        recording = status == "recording"

        if self._first_sample_at is None:
            self._first_sample_at = now
        history = self._histories.setdefault(key, deque(maxlen=_HISTORY_LENGTH))
        history.append(
            f"t+{now - self._first_sample_at:5.1f}s {status:<9} "
            f"dl={dl_total:<8} disk={disk}"
        )

        # Invariant 1: claiming to record means the disk must grow.
        if recording:
            if not window.recording:
                window.recording = True
                window.growth_at = now
                window.growth_disk = disk
            elif disk > window.growth_disk:
                window.growth_at = now
                window.growth_disk = disk
            elif now - window.growth_at >= GROWTH_GRACE:
                self._record(
                    "recording ⟹ disk bytes grow",
                    task.room_id,
                    f"claimed recording, yet the disk gained not one byte for "
                    f"{GROWTH_GRACE:.0f}s (stuck at {disk} bytes)",
                    key,
                )
                window.growth_at = now
                window.growth_disk = disk
        else:
            window.recording = False

        # Invariant 2: the download counter moving means the disk must follow.
        if dl_total < window.last_dl:
            # A new segment starts the counter over; the rewind invalidates
            # whatever the previous segment's counter had promised.
            window.last_dl = dl_total
            window.dl_since = None
        elif dl_total > window.last_dl:
            window.last_dl = dl_total
            if window.dl_since is None:
                window.dl_since = now
                window.dl_disk = disk
        if window.dl_since is not None:
            if disk > window.dl_disk:
                window.dl_since = None
            elif now - window.dl_since >= GROWTH_GRACE:
                self._record(
                    "dl_total grows ⟹ disk grows",
                    task.room_id,
                    f"dl_total moved, but the disk did not follow within "
                    f"{GROWTH_GRACE:.0f}s",
                    key,
                )
                window.dl_since = None

        # Invariant 3: enabled and live means the recording must come.
        stuck = task.recorder_enabled and task.monitor.is_living and not recording
        if stuck:
            if window.stuck_since is None:
                window.stuck_since = now
            elif now - window.stuck_since >= EVENTUALLY_GRACE:
                self._record(
                    "recorder enabled + live ⟹ eventually recording",
                    task.room_id,
                    f"the task is enabled and the room is live, yet nothing "
                    f"started recording within {EVENTUALLY_GRACE:.0f}s",
                    key,
                )
                window.stuck_since = now
        else:
            window.stuck_since = None

    # ── reporting ───────────────────────────────────────────────────

    def _record(self, invariant: str, room_id: int, detail: str, key: Any) -> None:
        history = self._histories.get(key)
        samples = tuple(history) if history else ()
        self.violations.append(Violation(invariant, room_id, detail, samples))

    def _internal_error(self, what: str) -> None:
        """A monitor that breaks must fail loudly, not pretend all is well."""
        if self._internal_error_reported:
            return
        self._internal_error_reported = True
        last_line = traceback.format_exc(limit=3).strip().splitlines()[-1]
        self.violations.append(
            Violation("invariant monitor internal error", 0, f"{what}: {last_line}", ())
        )

    def report(self) -> str:
        lines = [f"invariant monitor caught a lie in {self.test_name}:"]
        for violation in self.violations:
            lines.append(
                f"  [{violation.invariant}] room {violation.room_id}: "
                f"{violation.detail}"
            )
            lines.extend(f"    {sample}" for sample in violation.samples)
        return "\n".join(lines)


# ── disk scanning ───────────────────────────────────────────────────


def _scan_files(app: Any) -> list[tuple[str, int]]:
    """Every file under the application's output directories, with sizes."""
    roots = {Path(app.output_dir)}
    with contextlib.suppress(Exception):
        # A task-level or settings-level redirect can move the recordings
        # away from the directory the application was built with.
        roots.add(Path(app.settings_manager.settings.output.out_dir))
    files: list[tuple[str, int]] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            with contextlib.suppress(OSError):
                if path.is_file():
                    files.append((str(path.relative_to(root)), path.stat().st_size))
    return files


def _disk_totals(files: list[tuple[str, int]], room_ids: list[int]) -> dict[int, int]:
    """Total bytes per room.

    Recordings live under a per-room directory whose name carries the room id,
    and the file names carry it too, so a room id appearing in any path
    component owns the file. Files no room owns count for every room: it is
    better to miss a lie than to accuse a task over a file it may have
    written.
    """
    totals = dict.fromkeys(room_ids, 0)
    unattributed = 0
    for relative, size in files:
        parts = relative.split("/")
        for room_id in room_ids:
            if any(str(room_id) in part for part in parts):
                totals[room_id] += size
                break
        else:
            unattributed += size
    return {room_id: total + unattributed for room_id, total in totals.items()}
