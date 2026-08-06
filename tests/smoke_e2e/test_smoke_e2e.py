"""The publish-artifact smoke timeline (#19 §4).

One test walks the whole life of a recording against the real image: add a
task, go live, record, survive a CDN cut, survive a container restart, end
the stream, and leave behind artifacts that actually play. The HTTP variant
of the invariant monitor watches the whole run.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from . import validate
from .conftest import SmokeEnv
from .fake_control import FakeControl
from .http_invariant import HttpInvariantMonitor

ROOM_ID = 12345
PROBE = "smoke-probe"

# How long the steady-state recording phase lasts. CI keeps this short; the
# manual workflow_dispatch runs the full 5–10 minute version from the issue.
STABLE_SECONDS = int(os.environ.get("SMOKE_STABLE_SECONDS", "60"))

pytestmark = pytest.mark.smoke


def _wait_until(
    predicate: Callable[[], bool], timeout: float, what: str, interval: float = 0.5
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval)
    raise AssertionError(f"timed out after {timeout:.0f}s waiting for {what}")


def _tasks(client: httpx.Client) -> list[dict[str, Any]]:
    resp = client.get("/api/v1/tasks/data", params={"page": 1, "size": 100})
    resp.raise_for_status()
    return resp.json()["data"]["tasks"]


def _task_of(client: httpx.Client, room_id: int) -> dict[str, Any]:
    for task in _tasks(client):
        if int(task["room_id"]) == room_id:
            return task
    raise AssertionError(f"task {room_id} not found in /tasks/data")


def _running_status(client: httpx.Client) -> str:
    return str(_task_of(client, ROOM_ID)["task_status"]["running_status"])


def _dl_total(client: httpx.Client) -> int:
    return int(_task_of(client, ROOM_ID)["task_status"]["dl_total"])


def _app_ready(client: httpx.Client) -> bool:
    try:
        return client.get("/api/v1/app/status").status_code == 200
    except httpx.HTTPError:
        return False


def _rec_bytes(rec_dir: Path) -> int:
    total = 0
    for path in rec_dir.rglob("*"):
        try:
            if path.is_file():
                total += path.stat().st_size
        except OSError:
            pass
    return total


def test_publish_artifact_smoke(smoke_env: SmokeEnv) -> None:
    env = smoke_env
    client = httpx.Client(base_url=env.birec_url, timeout=10)
    fake = FakeControl(env.fake_url)
    monitor = HttpInvariantMonitor(env.birec_url, env.rec_dir)
    monitor.start()
    try:
        # 1. Ready, and the image must serve the UI, not just the API.
        _wait_until(lambda: _app_ready(client), 30, "the app API to come up")
        validate.validate_ui(env.birec_url)

        # 2. Add the task through the public API.
        resp = client.post(
            f"/api/v1/tasks/{ROOM_ID}",
            json={"room_id": ROOM_ID, "auto_enable": True},
        )
        assert resp.json()["code"] == 0, resp.text
        task = _task_of(client, ROOM_ID)
        assert task["task_status"]["recorder_enabled"]

        # 3. Go live. The LIVE broadcast must wait for the danmaku socket:
        # without a receiver it is lost, and the periodic poll only catches
        # up ten minutes later.
        _wait_until(
            lambda: fake.state()["ws_connections_total"] >= 1,
            30,
            "the danmaku socket to connect",
        )
        fake.set_live()
        fake.send_command("LIVE")  # once: a second LIVE means stream reset
        _wait_until(
            lambda: _running_status(client) == "recording", 30, "recording to start"
        )

        # 4. Steady recording with probe danmaku for the artifact checks.
        probe_count = 0
        phase_end = time.monotonic() + STABLE_SECONDS
        while time.monotonic() < phase_end:
            probe_count += 1
            fake.send_danmaku(f"{PROBE}-{probe_count}")
            time.sleep(5)

        # 5. Survive a CDN cut: the recorder must reconnect and keep going.
        monitor.suspend()
        cut = fake.cut_streams()
        assert cut >= 1, "no stream was in flight to cut"
        dl_at_cut = _dl_total(client)
        # A reconnect shows up as the counter moving; a fresh segment may
        # rewind it to zero first, so any change counts.
        _wait_until(
            lambda: (
                _dl_total(client) != dl_at_cut
                and _running_status(client) == "recording"
            ),
            30,
            "the recorder to reconnect after the cut",
        )
        monitor.resume()

        # 6. Survive a container restart: task and recording must come back.
        monitor.suspend()
        env.compose("restart", "birec")
        _wait_until(lambda: _app_ready(client), 60, "the app to come back")
        assert len(_tasks(client)) == 1, "the task did not survive the restart"
        _wait_until(
            lambda: _running_status(client) == "recording",
            60,
            "recording to resume after the restart",
        )
        monitor.resume()
        probe_count += 1
        fake.send_danmaku(f"{PROBE}-{probe_count}")
        time.sleep(10)

        # 7. End the stream and wait for the pipeline to drain.
        fake.set_offline()
        fake.send_command("PREPARING")
        _wait_until(
            lambda: _running_status(client) == "stopped",
            90,
            "the task to stop after the stream ended",
        )
        _wait_until(_files_settled(env.rec_dir), 120, "postprocessing to finish")

        # 8. No invariant violated anywhere along the timeline.
        monitor.stop()
        assert not monitor.violations, monitor.report()

        # 9. The artifacts must be real: playable, well-formed, complete.
        image = os.environ.get("BIREC_IMAGE", "birec:ci")
        validate.validate_mp4_playable(env.rec_dir, image)
        validate.validate_danmaku_xml(env.rec_dir, PROBE)
        validate.validate_ass(env.rec_dir)
        leftovers = validate.validate_no_leftover_flv(env.rec_dir)
        if leftovers:
            print(f"warning: flv leftovers after remux: {leftovers}")
    finally:
        monitor.stop()
        fake.close()
        client.close()


def _files_settled(rec_dir: Path, quiet_seconds: float = 3.0) -> Callable[[], bool]:
    """True once the volume's size has not changed for ``quiet_seconds``."""
    state = {"size": -1, "since": 0.0}

    def settled() -> bool:
        size = _rec_bytes(rec_dir)
        now = time.monotonic()
        if size != state["size"]:
            state["size"] = size
            state["since"] = now
            return False
        return now - state["since"] >= quiet_seconds

    return settled
