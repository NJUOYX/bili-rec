"""System tests for several rooms at once, and for switches flipped fast.

A recorder that works for one room in isolation can still fail the moment there
are three of them sharing an event bus, a settings object and a disk, or when a
user flips a switch twice before the first flip has finished. Those are the
states that produce "it works on my machine" bug reports, and none of them are
reachable from a unit test.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from birec.application import create_application

from .fake_bili_server import FakeBiliServer
from .harness import (
    ROOM_ID,
    add_task,
    begin_live,
    end_live,
    files,
    status,
    wait_until,
    wait_until_not_recording,
)

pytestmark = pytest.mark.usefixtures("fast_reconnect")

_ROOMS = (111, 222, 333)


@pytest.fixture()
async def many_rooms_server() -> AsyncIterator[FakeBiliServer]:
    """One fake Bilibili that answers for three different rooms."""
    server = FakeBiliServer(room_id=_ROOMS[0], extra_room_ids=_ROOMS[1:])
    await server.start()
    try:
        yield server
    finally:
        await server.stop()


@pytest.fixture()
async def many_rooms_client(
    tmp_path: Path, out_dir: Path, many_rooms_server: FakeBiliServer
) -> AsyncIterator[AsyncClient]:
    app = create_application(
        config_path=tmp_path / "config.toml",
        output_dir=out_dir,
        log_dir=tmp_path / "logs",
    )
    settings = app.state.settings_manager.settings
    base = many_rooms_server.base_url
    settings.bili_api.base_api_urls = [base]
    settings.bili_api.base_live_api_urls = [base]
    settings.bili_api.base_play_info_api_urls = [base]

    application = app.state.application
    await application.startup()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            c.app = app  # type: ignore[attr-defined]
            yield c
    finally:
        await application.shutdown()


class TestSeveralRoomsAtOnce:
    """Rooms recorded side by side must not interfere with each other."""

    async def test_three_rooms_each_get_their_own_recording(
        self,
        many_rooms_client: AsyncClient,
        many_rooms_server: FakeBiliServer,
        out_dir: Path,
    ) -> None:
        """Three live rooms, three growing files, no crossed wires.

        Everything below the task is per-room, but the event bus, the settings
        and the output directory are shared, so this is where a piece of state
        that should have been per-room shows itself.
        """
        for room in _ROOMS:
            await add_task(many_rooms_client, room)
        for room in _ROOMS:
            await begin_live(many_rooms_client, many_rooms_server, room)

        await wait_until(
            lambda: len(files(out_dir, ".flv")) == len(_ROOMS),
            what="one recording per room",
        )
        recordings = files(out_dir, ".flv")

        # Each room writes under its own id, so no two tasks share a file.
        for room in _ROOMS:
            assert any(str(room) in str(p) for p in recordings), (
                f"room {room} has no recording of its own"
            )

        sizes = {p: p.stat().st_size for p in recordings}
        await wait_until(
            lambda: all(p.stat().st_size > sizes[p] for p in recordings),
            what="every room's recording to keep growing",
        )

    async def test_stopping_one_room_leaves_the_others_recording(
        self,
        many_rooms_client: AsyncClient,
        many_rooms_server: FakeBiliServer,
        out_dir: Path,
    ) -> None:
        """Disabling one task must be a per-room operation, not a global one."""
        for room in _ROOMS:
            await add_task(many_rooms_client, room)
        for room in _ROOMS:
            await begin_live(many_rooms_client, many_rooms_server, room)
        await wait_until(
            lambda: len(files(out_dir, ".flv")) == len(_ROOMS),
            what="all three rooms to be recording",
        )

        await many_rooms_client.post(f"/api/v1/tasks/{_ROOMS[0]}/recorder/disable")
        await wait_until_not_recording(many_rooms_client, _ROOMS[0])

        for room in _ROOMS[1:]:
            assert (await status(many_rooms_client, room))[
                "running_status"
            ] == "recording", f"room {room} stopped along with room {_ROOMS[0]}"


class TestFlippingSwitchesFast:
    """The switches are a UI, so they get pressed faster than work completes."""

    async def test_toggling_the_recorder_repeatedly_settles_correctly(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """The last press must decide the outcome.

        Each toggle starts or tears down a download loop, and doing it again
        before the previous one has settled is how a half-torn-down recording
        gets left running behind a task that thinks it stopped.
        """
        await add_task(client)
        await begin_live(client, fake_server)
        await wait_until(
            lambda: bool(files(out_dir, ".flv")), what="recording to start"
        )

        for _ in range(3):
            await client.post(f"/api/v1/tasks/{ROOM_ID}/recorder/disable")
            await asyncio.sleep(0.1)
            await client.post(f"/api/v1/tasks/{ROOM_ID}/recorder/enable")
            await asyncio.sleep(0.1)
        await client.post(f"/api/v1/tasks/{ROOM_ID}/recorder/disable")

        await wait_until_not_recording(client)
        final = await status(client)
        assert final["recorder_enabled"] is False

    async def test_a_disable_arriving_before_the_start_finishes(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """Stopping mid-start must not leave a download loop behind.

        ``on_live_began`` only schedules the start, so a disable arriving in that
        window used to tear down nothing while the loop went on writing.
        """
        await add_task(client)
        await begin_live(client, fake_server)
        # Deliberately no wait: the start is still in flight.
        await client.post(f"/api/v1/tasks/{ROOM_ID}/recorder/disable")

        await wait_until_not_recording(client)
        task = client.app.state.application.task_manager.get_task(ROOM_ID)  # type: ignore[attr-defined]
        assert task._recorder._download_task is None  # noqa: SLF001


class TestBroadcastsBackToBack:
    """Rooms go off and come back; each broadcast is its own recording."""

    async def test_going_offline_and_live_again_starts_a_new_file(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """A second broadcast must not be appended to the first one's file.

        The first file is closed and handed to post-processing, so writing the
        next broadcast into it would corrupt something already being worked on.
        """
        await add_task(client)
        await begin_live(client, fake_server)
        await wait_until(
            lambda: bool(files(out_dir, ".flv")), what="the first recording to start"
        )
        first = files(out_dir, ".flv")[0]
        await wait_until(lambda: first.stat().st_size > 2000, what="data on disk")

        await end_live(client, fake_server)
        await wait_until_not_recording(client)

        # A pause long enough for the filename's timestamp to differ.
        await asyncio.sleep(1.1)
        await begin_live(client, fake_server)

        await wait_until(
            lambda: len(files(out_dir, ".flv") + files(out_dir, ".mp4")) >= 2,
            what="the second broadcast to open its own file",
        )

    async def test_a_flood_of_danmaku_all_reach_the_xml(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """A busy room sends far more messages than a test usually does.

        The dumper batches writes, so a burst is where a batch boundary can eat
        a message or leave the document unclosed.
        """
        await add_task(client)
        task = client.app.state.application.task_manager.get_task(ROOM_ID)  # type: ignore[attr-defined]
        await wait_until(
            lambda: task._danmaku_client.connected,  # noqa: SLF001
            what="the danmaku client to connect",
        )
        await begin_live(client, fake_server)
        await wait_until(
            lambda: bool(list(out_dir.rglob("*.xml"))), what="the XML to be created"
        )
        xml = next(iter(out_dir.rglob("*.xml")))

        for i in range(500):
            await fake_server.send_danmaku(f"flood {i}")

        await wait_until(
            lambda: "flood 499" in xml.read_text(encoding="utf-8"),
            what="the whole burst to be written",
        )
        content = xml.read_text(encoding="utf-8")
        missing = [i for i in range(500) if f">flood {i}<" not in content]
        assert not missing, f"{len(missing)} messages were dropped from the burst"
