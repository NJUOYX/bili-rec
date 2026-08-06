"""HTTP variant of the invariant monitor for the container smoke test (#19 §4).

The in-process ``InvariantMonitor`` (tests/system/invariant_monitor.py) reads
application internals; a container only exposes its HTTP API. Same invariants,
wider grace — the samples cross a container boundary and reconnect backoffs
legitimately stall the pipeline for a few seconds:

- recording ⟹ disk bytes grow within ``GROWTH_GRACE``;
- dl_total grows ⟹ disk bytes follow within ``GROWTH_GRACE``;
- recorder enabled + live ⟹ recording within ``EVENTUALLY_GRACE``.
"""

from __future__ import annotations

import contextlib
import threading
import time
import traceback
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

SAMPLE_INTERVAL = 0.5
GROWTH_GRACE = 6.0
EVENTUALLY_GRACE = 20.0
_HISTORY_LENGTH = 60


@dataclass(frozen=True, slots=True)
class Violation:
    invariant: str
    room_id: int
    detail: str
    samples: tuple[str, ...]


@dataclass(slots=True)
class _TaskWindow:
    growth_at: float = 0.0
    growth_disk: int = 0
    recording: bool = False
    last_dl: int = 0
    dl_since: float | None = None
    dl_disk: int = 0
    stuck_since: float | None = None


class HttpInvariantMonitor:
    """Samples the tasks API and the recordings volume from outside."""

    def __init__(self, base_url: str, rec_dir: Path) -> None:
        self._base_url = base_url
        self._rec_dir = rec_dir
        self._client = httpx.Client(base_url=base_url, timeout=5)
        self.violations: list[Violation] = []
        self._windows: dict[int, _TaskWindow] = {}
        self._histories: dict[int, deque[str]] = {}
        self._first_sample_at: float | None = None
        self._suspended = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._internal_error_reported = False

    # ── lifecycle ───────────────────────────────────────────────────

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._client.close()

    def suspend(self) -> None:
        """Pause checks across a disturbance (fault injection, restart)."""
        self._suspended = True

    def resume(self) -> None:
        """Re-arm: every window starts fresh after a disturbance."""
        self._suspended = False
        self._windows.clear()
        self._histories.clear()
        self._first_sample_at = None

    def _run(self) -> None:
        while not self._stop.wait(SAMPLE_INTERVAL):
            if self._suspended:
                continue
            try:
                self.sample()
            except httpx.HTTPError:
                # The server may be mid-restart; a missed sample is fine,
                # a frozen disk for GROWTH_GRACE seconds is not.
                continue
            except Exception:
                self._internal_error("sampling the smoke state")

    # ── sampling ────────────────────────────────────────────────────

    def sample(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        resp = self._client.get("/api/v1/tasks/data", params={"page": 1, "size": 100})
        resp.raise_for_status()
        tasks = resp.json()["data"]["tasks"]
        disk_total = _disk_total(self._rec_dir)
        for task in tasks:
            self._sample_task(task, disk_total, now)

    def _sample_task(self, task: dict[str, Any], disk: int, now: float) -> None:
        room_id = int(task["room_id"])
        status = task["task_status"]
        running = str(status["running_status"])
        dl_total = int(status["dl_total"])
        recording = running == "recording"

        if self._first_sample_at is None:
            self._first_sample_at = now
        window = self._windows.setdefault(room_id, _TaskWindow())
        history = self._histories.setdefault(room_id, deque(maxlen=_HISTORY_LENGTH))
        history.append(
            f"t+{now - self._first_sample_at:5.1f}s {running:<9} "
            f"dl={dl_total:<8} disk={disk}"
        )

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
                    room_id,
                    f"claimed recording, yet the disk gained not one byte for "
                    f"{GROWTH_GRACE:.0f}s (stuck at {disk} bytes)",
                    room_id,
                )
                window.growth_at = now
                window.growth_disk = disk
        else:
            window.recording = False

        if dl_total < window.last_dl:
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
                    room_id,
                    f"dl_total moved, but the disk did not follow within "
                    f"{GROWTH_GRACE:.0f}s",
                    room_id,
                )
                window.dl_since = None

        live = bool(task.get("live_status"))
        stuck = bool(status["recorder_enabled"]) and live and not recording
        if stuck:
            if window.stuck_since is None:
                window.stuck_since = now
            elif now - window.stuck_since >= EVENTUALLY_GRACE:
                self._record(
                    "recorder enabled + live ⟹ eventually recording",
                    room_id,
                    f"the task is enabled and the room is live, yet nothing "
                    f"started recording within {EVENTUALLY_GRACE:.0f}s",
                    room_id,
                )
                window.stuck_since = now
        else:
            window.stuck_since = None

    # ── reporting ───────────────────────────────────────────────────

    def _record(self, invariant: str, room_id: int, detail: str, key: int) -> None:
        history = self._histories.get(key)
        samples = tuple(history) if history else ()
        self.violations.append(Violation(invariant, room_id, detail, samples))

    def _internal_error(self, what: str) -> None:
        if self._internal_error_reported:
            return
        self._internal_error_reported = True
        last_line = traceback.format_exc(limit=3).strip().splitlines()[-1]
        self.violations.append(
            Violation(
                "smoke invariant monitor internal error", 0, f"{what}: {last_line}", ()
            )
        )

    def report(self) -> str:
        lines = ["smoke invariant monitor caught a lie:"]
        for violation in self.violations:
            lines.append(
                f"  [{violation.invariant}] room {violation.room_id}: "
                f"{violation.detail}"
            )
            lines.extend(f"    {sample}" for sample in violation.samples)
        return "\n".join(lines)


def _disk_total(root: Path) -> int:
    """Total bytes under the recordings volume.

    The smoke test records a single room, so per-room attribution is
    unnecessary — any growth anywhere in the volume counts.
    """
    total = 0
    if not root.is_dir():
        return 0
    for path in root.rglob("*"):
        with contextlib.suppress(OSError):
            if path.is_file():
                total += path.stat().st_size
    return total
