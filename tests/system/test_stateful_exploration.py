"""Hypothesis stateful exploration of the record task (#19, scheme 2).

Unit tests feed hand-built inputs to single parts; system tests run hand-built
operation sequences against the whole application. The bugs that kept escaping
lived in *sequences nobody thought of* — #17 was found by a user, not by a
test. This file hands the sequencing to Hypothesis: a ``RuleBasedStateMachine``
drives a real application against the fake Bilibili server, and after every
step the same invariants the background monitor watches (#19, scheme 1) are
checked inline. When a sequence breaks one, Hypothesis shrinks it to a minimal
reproduction.

Rules (the things a user and a CDN can do):

- add a task for the room
- room goes live / goes offline
- recorder switch: enable / disable
- monitor switch: stop / start
- the CDN drops the connection mid-stream
- the CDN splices a byte that is not FLV
- let time pass (background work advances, growth windows accumulate)

Invariants (checked after every step):

1. claiming to record ⟹ the disk bytes grow within ``GROWTH_GRACE``;
2. ``dl_total`` moving ⟹ the disk follows within ``GROWTH_GRACE``;
3. recorder enabled + room live ⟹ recording is up within
   ``EVENTUALLY_GRACE``. Rather than betting that the next few steps happen
   to add up to that window, the check spends the window itself, so one
   invariant call is enough to catch a resume that never comes.

The two growth invariants are suspended while a segment lies finalized after a
fault: after bad bytes the recorder honestly stops and waits for a fresh live
cycle (the trade documented in ``test_data_corruption.py``), and the counters
freeze while it waits. Suspension lifts the moment a new cycle can start —
the recorder is switched back on, the monitor restarts, or the room ends.

The background ``invariant_monitor`` fixture is opted out for this test
(``no_invariant_monitor``): it samples on its own clock and knows nothing
about that suspension, so it would cry wolf over the same honest pause.

Finding #17 without any hint
-----------------------------

With the fix from commit 8520222 reverted, this machine finds the bug on its
own and shrinks it to (exact output of the validation run)::

    add_task → begin_live → bad_bytes → disable_recorder → enable_recorder
    [recorder enabled + live ⟹ eventually recording] enabled and live,
    given 1s to start, yet nothing is recording

The ``bad_bytes`` step is incidental to the exploration path Hypothesis
shrank from; the bare core ``add_task → begin_live → disable_recorder →
enable_recorder`` fails the same invariant on its own. Either way it is
exactly the sequence the user reported: recording switched off while the room
was live, switched back on, and nothing happened — enable only re-attached
the listener for a ``live_began`` that had already been and gone.

Budget: ``derandomize=True`` seeds the search from the test name, so the run
is the same on every machine and in CI; ``max_examples`` is sized so a green
run stays a small fraction of the system suite, and a re-introduced #17 is
still caught (the failing sequence is short, so it surfaces early — the
exploration reaches the ``disable → enable while live`` pattern within the
first handful of examples).
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
import time
from collections.abc import Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

import pytest
from hypothesis import HealthCheck, settings
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule

from birec.application import create_application
from birec.core import flv_stream_recorder_impl

from .fake_bili_server import FakeBiliServer
from .harness import ROOM_ID
from .invariant_monitor import GROWTH_GRACE

pytestmark = pytest.mark.no_invariant_monitor

_T = TypeVar("_T")

# How long an enabled-but-live task may sit out of recording before it is a
# lie. Tighter than the background monitor's 5s: every resume path flips
# ``is_recording`` synchronously with the state change, so a healthy task is
# never "enabled + live + not recording" for any measurable span — the window
# only ever runs to the end when something is genuinely stuck.
EVENTUALLY_GRACE = 1.0

# Poll cadence while the stuck check waits out ``EVENTUALLY_GRACE``.
_STUCK_POLL = 0.05

# One settle after an ordinary step. This is the only clock the machine has —
# invariant windows accumulate these sleeps — so it is short enough that many
# steps stay cheap, and the "let time pass" rule provides the longer strides.
# Chunks arrive every 5ms and every recording flag flips synchronously with
# the call that changes it, so a beat this short still lets the loop breathe.
SETTLE = 0.05

# The longer stride for ``let_time_pass``.
PASS_TIME = 0.4

# How long the bad-bytes rule waits for the honest finalization.
FINALIZE_TIMEOUT = 3.0

REPO_ROOT = Path(__file__).resolve().parents[2]


def _scratch_dir() -> Path:
    """A workspace-local home for per-example temp dirs.

    The sandbox this repo is developed in cannot write to ``/tmp``, so the
    scratch lives next to the checkout and is git-ignored.
    """
    root = REPO_ROOT / ".stateful_tmp"
    root.mkdir(exist_ok=True)
    return root


@dataclass(slots=True)
class _Window:
    """What the invariant checks remember between steps."""

    recording: bool = False
    growth_at: float = 0.0
    growth_disk: int = 0
    last_dl: int = 0
    dl_since: float | None = None
    dl_disk: int = 0


class RecorderStateMachine(RuleBasedStateMachine):
    """One room, a real application, and every switch a user can flip."""

    def __init__(self) -> None:
        super().__init__()
        self._steps: list[str] = []
        # Set while a fault-finalized segment waits out the rest of the live
        # cycle; suspends invariants 2 and 3 (see the module docstring).
        self._abandoned = False
        self._window = _Window()
        self._loop = asyncio.new_event_loop()
        self._root = Path(tempfile.mkdtemp(prefix="stateful-", dir=_scratch_dir()))
        self._server = FakeBiliServer(room_id=ROOM_ID)
        # Small, fast chunks: the disk has to show growth between steps, and a
        # short payload keeps the natural end-of-stream reconnects frequent
        # enough to be part of the exploration.
        self._server.stream_chunk_delay = 0.005
        self._server.stream_extra_frames = 60
        self._run(self._server.start())
        # Production backoff is measured in seconds; the reconnects it spaces
        # out are exactly what the invariants have to see through, so shrink
        # the waiting, not the logic (same knob as the fast_reconnect fixture).
        self._saved_backoff = (
            flv_stream_recorder_impl._RECONNECT_BASE_DELAY,
            flv_stream_recorder_impl._RECONNECT_MAX_DELAY,
        )
        flv_stream_recorder_impl._RECONNECT_BASE_DELAY = 0.02
        flv_stream_recorder_impl._RECONNECT_MAX_DELAY = 0.05
        app = create_application(
            config_path=self._root / "config.toml",
            output_dir=self._root / "recordings",
            log_dir=self._root / "logs",
        )
        bili = app.state.settings_manager.settings.bili_api
        bili.base_api_urls = [self._server.base_url]
        bili.base_live_api_urls = [self._server.base_url]
        bili.base_play_info_api_urls = [self._server.base_url]
        self._application = app.state.application
        self._run(self._application.startup())
        self._note("boot")

    # ── plumbing ────────────────────────────────────────────────────

    def _run(self, coro: Coroutine[Any, Any, _T]) -> _T:
        """Run a coroutine on the machine's loop.

        Background tasks advance while the coroutine runs, so settling is a
        sleep passed through here.
        """
        return self._loop.run_until_complete(coro)

    def _task(self) -> Any:
        return self._application.task_manager.get_task(ROOM_ID)

    def _settle(self, seconds: float = SETTLE) -> None:
        self._run(asyncio.sleep(seconds))

    def _disk_total(self) -> int:
        root = self._root / "recordings"
        if not root.is_dir():
            return 0
        return sum(p.stat().st_size for p in root.rglob("*") if p.is_file())

    def _note(self, action: str) -> None:
        """Append what the step did and what the world looks like now."""
        task = self._task()
        if task is None:
            state = "no task"
        else:
            state = (
                f"monitor={'on' if task.monitor_enabled else 'off'} "
                f"recorder={'on' if task.recorder_enabled else 'off'} "
                f"live={'yes' if task.monitor.is_living else 'no'} "
                f"recording={'yes' if task.recorder.is_recording else 'no'} "
                f"dl={task.recorder.stream_recorder.statistics.dl_total} "
                f"disk={self._disk_total()}"
            )
        self._steps.append(f"{action} → {state}")

    def _resync_windows(self) -> None:
        """Forget everything the growth checks had accumulated.

        Used when the model legitimately breaks continuity: a fault-finalized
        segment, or the fresh cycle that ends the abandonment.
        """
        task = self._task()
        now = time.monotonic()
        disk = self._disk_total()
        dl = task.recorder.stream_recorder.statistics.dl_total if task else 0
        recording = bool(task and task.recorder.is_recording)
        self._window = _Window(
            recording=recording,
            growth_at=now,
            growth_disk=disk,
            last_dl=dl,
        )

    def _fail(self, name: str, detail: str) -> None:
        trail = "\n".join(f"  {step}" for step in self._steps)
        raise AssertionError(f"[{name}] {detail}\nobserved sequence:\n{trail}")

    def teardown(self) -> None:
        try:
            if self._application.is_started:
                self._run(asyncio.wait_for(self._application.shutdown(), 10))
            self._run(asyncio.wait_for(self._server.stop(), 5))
        finally:
            pending = [t for t in asyncio.all_tasks(self._loop) if not t.done()]
            for task in pending:
                task.cancel()
            if pending:
                self._loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            self._loop.close()
            (
                flv_stream_recorder_impl._RECONNECT_BASE_DELAY,
                flv_stream_recorder_impl._RECONNECT_MAX_DELAY,
            ) = self._saved_backoff
            shutil.rmtree(self._root, ignore_errors=True)

    # ── rules ───────────────────────────────────────────────────────

    @precondition(lambda self: self._task() is None)
    @rule()
    def add_task(self) -> None:
        """Ask the recorder to watch this room."""
        self._run(self._application.task_manager.add_task(ROOM_ID))
        self._note("add_task")
        self._settle()

    @precondition(
        lambda self: self._task() is not None and self._server.live_status == 0
    )
    @rule()
    def begin_live(self) -> None:
        """The streamer goes on air, and the room says so."""
        self._server.set_live()
        self._run(self._task().monitor.handle_command("LIVE"))
        self._note("begin_live")
        self._settle()

    @precondition(
        lambda self: self._task() is not None and self._server.live_status == 1
    )
    @rule()
    def end_live(self) -> None:
        """The broadcast ends."""
        self._server.set_offline()
        self._run(self._task().monitor.handle_command("PREPARING"))
        if self._abandoned:
            # The cycle the abandoned segment belonged to is over; the next
            # live start is a fresh one.
            self._abandoned = False
            self._resync_windows()
        self._note("end_live")
        self._settle()

    @precondition(
        lambda self: (task := self._task()) is not None and not task.recorder_enabled
    )
    @rule()
    def enable_recorder(self) -> None:
        """Flip the recording switch on.

        The call is sync, but since the #17 fix an enable against a live room
        starts the recording, which spawns tasks on the running loop — so the
        call itself has to happen on the loop.
        """

        async def _enable() -> None:
            self._task().enable_recorder()

        self._run(_enable())
        if self._abandoned:
            # Enabling opens a fresh pipeline; whatever the fault killed is
            # not owed any more patience.
            self._abandoned = False
            self._resync_windows()
        self._note("enable_recorder")
        self._settle()

    @precondition(
        lambda self: (task := self._task()) is not None and task.recorder_enabled
    )
    @rule()
    def disable_recorder(self) -> None:
        """Flip the recording switch off."""
        self._run(self._task().disable_recorder())
        self._note("disable_recorder")
        self._settle()

    @precondition(
        lambda self: (task := self._task()) is not None and task.monitor_enabled
    )
    @rule()
    def stop_monitor(self) -> None:
        """Stop watching the room altogether."""
        self._run(self._task().disable_monitor())
        self._note("stop_monitor")
        self._settle()

    @precondition(
        lambda self: (task := self._task()) is not None and not task.monitor_enabled
    )
    @rule()
    def start_monitor(self) -> None:
        """Start watching the room again; an ongoing broadcast must be picked up."""
        self._run(self._task().enable_monitor())
        if self._abandoned:
            # Restarting the monitor re-emits the live state as a fresh
            # ``live_began``, which is a new cycle's worth of patience.
            self._abandoned = False
            self._resync_windows()
        self._note("start_monitor")
        # The reconcile that picks up an already-live room is a background
        # task; give it its beat.
        self._settle(0.3)

    @precondition(
        lambda self: (task := self._task()) is not None and task.recorder.is_recording
    )
    @rule()
    def break_stream(self) -> None:
        """The CDN drops the connection; the next one breaks once."""
        self._server.set_fault(
            stream_break_after_chunks=3,
            stream_break_times=self._server.stream_requests + 1,
        )
        self._note("break_stream")
        self._settle(0.4)

    @precondition(
        lambda self: (
            (task := self._task()) is not None
            and task.recorder.is_recording
            and not self._abandoned
        )
    )
    @rule()
    def bad_bytes(self) -> None:
        """A byte that is not FLV arrives; the segment must finalize honestly."""
        self._server.set_fault(stream_bad_tag_type=True)
        recorder = self._task().recorder

        async def _wait_finalized() -> None:
            deadline = self._loop.time() + FINALIZE_TIMEOUT
            while recorder.is_recording:
                if self._loop.time() > deadline:
                    raise AssertionError(
                        "bad bytes arrived, yet the recording never finalized"
                    )
                await asyncio.sleep(0.05)

        self._run(_wait_finalized())
        assert self._disk_total() > 13, "the bad byte swallowed everything recorded"
        self._server.set_fault(stream_bad_tag_type=False)
        self._abandoned = True
        self._resync_windows()
        self._note("bad_bytes → finalized")
        self._settle()

    @precondition(lambda self: self._task() is not None)
    @rule()
    def let_time_pass(self) -> None:
        """Do nothing for a while — 'eventually' claims still have to hold."""
        self._settle(PASS_TIME)
        self._note("let_time_pass")

    # ── invariants ──────────────────────────────────────────────────

    @invariant()
    def claims_match_the_disk(self) -> None:
        task = self._task()
        if task is None:
            return
        now = time.monotonic()
        disk = self._disk_total()
        dl_total: int = task.recorder.stream_recorder.statistics.dl_total
        recording = bool(task.recorder.is_recording)
        window = self._window

        # 1. Claiming to record means the disk must grow.
        if recording:
            if not window.recording:
                window.recording = True
                window.growth_at = now
                window.growth_disk = disk
            elif disk > window.growth_disk:
                window.growth_at = now
                window.growth_disk = disk
            elif now - window.growth_at >= GROWTH_GRACE:
                self._fail(
                    "recording ⟹ disk bytes grow",
                    f"claimed recording for {GROWTH_GRACE:.0f}s with the disk "
                    f"frozen at {disk} bytes",
                )
        else:
            window.recording = False

        if self._abandoned:
            # A fault-finalized segment waits out the live cycle honestly;
            # its counters are frozen on purpose. Keep last_dl fresh so the
            # rewind at the next segment is not mistaken for growth.
            window.last_dl = dl_total
            return

        # 2. The download counter moving means the disk must follow.
        if dl_total < window.last_dl:
            # A new segment starts the counter over.
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
                self._fail(
                    "dl_total grows ⟹ disk grows",
                    "dl_total moved, but the disk did not follow within "
                    f"{GROWTH_GRACE:.0f}s",
                )
                window.dl_since = None

        # 3. Enabled and live means the recording must come. Rather than
        # betting that the steps Hypothesis happens to schedule after this one
        # add up to the grace window — a fast disable/enable toggle resets an
        # accumulating window, and a minimal shrunk example can simply run out
        # of steps — spend the window right here. A healthy resume flips
        # ``is_recording`` synchronously with the enable, so this loop exits on
        # its first poll; an enable that does nothing (#17) leaves it off for
        # the whole wait, and the failure is deterministic in one invariant
        # call.
        stuck = task.recorder_enabled and task.monitor.is_living and not recording
        if stuck:
            deadline = self._loop.time() + EVENTUALLY_GRACE
            while not task.recorder.is_recording and self._loop.time() < deadline:
                self._run(asyncio.sleep(_STUCK_POLL))
            if not task.recorder.is_recording:
                self._fail(
                    "recorder enabled + live ⟹ eventually recording",
                    f"enabled and live, given {EVENTUALLY_GRACE:.0f}s to start, "
                    "yet nothing is recording",
                )


class TestRecorderExploration(RecorderStateMachine.TestCase):
    """The pytest face of the machine.

    ``derandomize`` seeds the search from the test name, so every run — local
    or CI — explores the same sequences; a bug that is found once is found
    always, and a green run stays green without luck.
    """


TestRecorderExploration.settings = settings(
    max_examples=8,
    stateful_step_count=10,
    deadline=None,
    derandomize=True,
    database=None,
    suppress_health_check=[HealthCheck.too_slow],
)
