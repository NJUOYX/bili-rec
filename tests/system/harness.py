"""Shared scaffolding for the system tests.

Every system test drives the same shape of setup: a fake Bilibili server, a
real application pointed at it, a room that goes live, and then polling until
something shows up on disk or on the event bus. That shape lives here so the
tests themselves only contain what is specific to them.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from .fake_bili_server import FakeBiliServer

# The room every test uses unless it needs more than one.
ROOM_ID = 12345

# The recorder is fed by a real socket and a real disk, so the checks poll
# instead of assuming a fixed duration. Generous enough for a loaded CI runner.
TIMEOUT = 20.0
POLL = 0.05


async def wait_until(
    predicate: Callable[[], bool], *, timeout: float = TIMEOUT, what: str = "condition"
) -> None:
    """Poll until the predicate holds, or fail saying what never happened."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(POLL)
    pytest.fail(f"Timed out after {timeout}s waiting for {what}")


async def wait_until_async(
    predicate: Callable[[], Awaitable[bool]],
    *,
    timeout: float = TIMEOUT,
    what: str = "condition",
) -> None:
    """Poll an awaitable predicate, for the checks that go through the API."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if await predicate():
            return
        await asyncio.sleep(POLL)
    pytest.fail(f"Timed out after {timeout}s waiting for {what}")


def files(out_dir: Path, suffix: str) -> list[Path]:
    """Every file of that kind the recorder has written, in a stable order."""
    return sorted(p for p in out_dir.rglob(f"*{suffix}") if p.is_file())


def task_of(client: AsyncClient, room_id: int = ROOM_ID) -> Any:
    """The live task object behind the API, for the checks the API cannot make."""
    return client.app.state.application.task_manager.get_task(room_id)  # type: ignore[attr-defined]


async def add_task(client: AsyncClient, room_id: int = ROOM_ID) -> None:
    resp = await client.post(f"/api/v1/tasks/{room_id}", json={"room_id": room_id})
    assert resp.json()["code"] == 0


async def begin_live(
    client: AsyncClient, fake_server: FakeBiliServer, room_id: int = ROOM_ID
) -> None:
    """Go live and tell the room's monitor about it, as a danmaku LIVE would.

    Used by the tests that are not about the danmaku socket: going through the
    monitor command directly skips the broadcast round-trip while leaving
    everything downstream of it real.
    """
    fake_server.set_live()
    await task_of(client, room_id)._monitor.handle_command("LIVE")  # noqa: SLF001


async def end_live(
    client: AsyncClient, fake_server: FakeBiliServer, room_id: int = ROOM_ID
) -> None:
    """Stop broadcasting, the way the room going back to its idle screen does."""
    fake_server.set_offline()
    await task_of(client, room_id)._monitor.handle_command("PREPARING")  # noqa: SLF001


async def status(client: AsyncClient, room_id: int = ROOM_ID) -> dict[str, Any]:
    body = (await client.get(f"/api/v1/tasks/{room_id}/data")).json()
    assert body["code"] == 0
    return body["data"]["task_status"]  # type: ignore[no-any-return]


async def wait_for_recording(
    out_dir: Path, *, min_size: int = 2000, timeout: float = TIMEOUT
) -> Path:
    """Wait until a recording exists and has real stream data in it."""
    await wait_until(
        lambda: bool(files(out_dir, ".flv")),
        timeout=timeout,
        what="the FLV file to be created",
    )
    flv = files(out_dir, ".flv")[0]
    await wait_until(
        lambda: flv.stat().st_size > min_size,
        timeout=timeout,
        what="stream data to reach the disk",
    )
    return flv


async def wait_until_recording(
    client: AsyncClient, room_id: int = ROOM_ID, *, timeout: float = TIMEOUT
) -> None:
    """Wait for the task to report that it started recording.

    Worth stating explicitly before waiting for a stop: a task that has not
    begun yet also is not recording, so a stop check on its own can pass without
    anything having happened.
    """

    async def _started() -> bool:
        return bool((await status(client, room_id))["running_status"] == "recording")

    await wait_until_async(
        _started, timeout=timeout, what="the task to report itself as recording"
    )


async def wait_until_not_recording(
    client: AsyncClient, room_id: int = ROOM_ID, *, timeout: float = TIMEOUT
) -> None:
    """Wait for the task to settle out of the recording state."""

    async def _settled() -> bool:
        return bool((await status(client, room_id))["running_status"] != "recording")

    await wait_until_async(
        _settled, timeout=timeout, what="the task to stop reporting itself as recording"
    )
