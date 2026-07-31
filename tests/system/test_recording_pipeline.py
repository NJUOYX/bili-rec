"""System tests for the recording pipeline: stream → disk → post-processing.

These drive the real component graph against the fake Bilibili server: a real
HTTP stream served in small chunks, the real FLV pipeline, real files on disk,
and the real post-processor.

The point is what the unit tests structurally cannot see. Every piece here has
thorough unit coverage, and both of the bugs users actually hit slipped through
anyway: a chunked stream lost every byte (#9), and the whole post-processing
stage was never wired up (#10). Both are failures of the seams between the
pieces, so they only show up when the pieces are asked to work together against
a real socket and a real filesystem.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from reactivex.abc import DisposableBase

from birec.application import create_application
from birec.event import EventCenter

from .fake_bili_server import FakeBiliServer

_ROOM_ID = 12345

# The recorder is fed by a real socket and a real disk, so the checks poll
# instead of assuming a fixed duration. Generous enough for a loaded CI runner.
_TIMEOUT = 20.0
_POLL = 0.05


async def _wait_until(
    predicate: Callable[[], bool], *, timeout: float = _TIMEOUT, what: str = "condition"
) -> None:
    """Poll until the predicate holds, or fail saying what never happened."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(_POLL)
    pytest.fail(f"Timed out after {timeout}s waiting for {what}")


def _files(out_dir: Path, suffix: str) -> list[Path]:
    return sorted(p for p in out_dir.rglob(f"*{suffix}") if p.is_file())


@pytest.fixture()
async def fake_server() -> AsyncIterator[FakeBiliServer]:
    server = FakeBiliServer(room_id=_ROOM_ID)
    await server.start()
    try:
        yield server
    finally:
        await server.stop()


@pytest.fixture()
def out_dir(tmp_path: Path) -> Path:
    return tmp_path / "recordings"


@pytest.fixture()
async def client(
    tmp_path: Path, out_dir: Path, fake_server: FakeBiliServer
) -> AsyncIterator[AsyncClient]:
    """A started application whose Bilibili endpoints are the fake server."""
    app = create_application(
        config_path=tmp_path / "config.toml",
        output_dir=out_dir,
        log_dir=tmp_path / "logs",
    )
    settings = app.state.settings_manager.settings
    settings.bili_api.base_api_urls = [fake_server.base_url]
    settings.bili_api.base_live_api_urls = [fake_server.base_url]
    settings.bili_api.base_play_info_api_urls = [fake_server.base_url]

    application = app.state.application
    await application.startup()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            c.app = app  # type: ignore[attr-defined]
            yield c
    finally:
        await application.shutdown()


@pytest.fixture()
def events() -> Iterator[list[Any]]:
    """Collect everything published on the event bus during a test.

    The bus-to-WebSocket hop is covered by the unit tests, which drive a real
    client against a submitted event; what is missing, and what this captures,
    is whether a real recording publishes anything at all.
    """
    collected: list[Any] = []
    subscription: DisposableBase = EventCenter.get_instance().events.subscribe(
        collected.append
    )
    try:
        yield collected
    finally:
        subscription.dispose()


async def _add_task(client: AsyncClient) -> None:
    resp = await client.post(f"/api/v1/tasks/{_ROOM_ID}", json={"room_id": _ROOM_ID})
    assert resp.json()["code"] == 0


async def _begin_live(client: AsyncClient, fake_server: FakeBiliServer) -> None:
    """Go live and tell the room's monitor about it, as a danmaku LIVE would.

    The danmaku socket itself is out of reach here: the client hardcodes
    ``wss://{host}/sub``, so it cannot be pointed at a local plaintext server.
    Everything downstream of that command is the real thing.
    """
    fake_server.set_live()
    task = client.app.state.application.task_manager.get_task(_ROOM_ID)  # type: ignore[attr-defined]
    await task._monitor.handle_command("LIVE")  # noqa: SLF001


async def _status(client: AsyncClient) -> dict[str, Any]:
    body = (await client.get(f"/api/v1/tasks/{_ROOM_ID}/data")).json()
    assert body["code"] == 0
    return body["data"]["task_status"]  # type: ignore[no-any-return]


class TestRecordingReachesDisk:
    """A live stream must end up as bytes in a file while it is still running."""

    async def test_the_chunked_stream_lands_on_disk(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """Regression (#9): a stream delivered in pieces must still be recorded.

        The stream arrives as many small writes, and the parser used to treat
        each one as a complete stream that had just ended. Recording ran, the
        file was created, and every byte was dropped: it sat at 0 forever.
        """
        await _add_task(client)
        await _begin_live(client, fake_server)

        await _wait_until(
            lambda: bool(_files(out_dir, ".flv")), what="the FLV file to be created"
        )
        flv = _files(out_dir, ".flv")[0]

        # Well past the 13-byte header and the metadata tag: real tags got
        # through, across chunk boundaries.
        await _wait_until(
            lambda: flv.stat().st_size > 2000, what="stream data to reach the disk"
        )

    async def test_the_file_keeps_growing_while_recording(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """Regression (#9): the data must be flushed, not held in a buffer.

        A file that only materialises at the end looks identical to a broken
        recording while it is happening, which is exactly what users reported.
        """
        await _add_task(client)
        await _begin_live(client, fake_server)

        await _wait_until(
            lambda: bool(_files(out_dir, ".flv")), what="the FLV file to be created"
        )
        flv = _files(out_dir, ".flv")[0]
        await _wait_until(lambda: flv.stat().st_size > 1000, what="the first flush")

        first = flv.stat().st_size
        await _wait_until(
            lambda: flv.stat().st_size > first, what="the recording to grow further"
        )

    async def test_the_api_reports_the_recording_it_is_writing(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """The path and byte count the UI shows must match what is on disk."""
        await _add_task(client)
        await _begin_live(client, fake_server)

        await _wait_until(
            lambda: bool(_files(out_dir, ".flv")), what="the FLV file to be created"
        )
        flv = _files(out_dir, ".flv")[0]
        await _wait_until(lambda: flv.stat().st_size > 2000, what="data on disk")

        status = await _status(client)
        assert status["running_status"] == "recording"
        assert Path(status["recording_path"]) == flv
        # ``dl_total`` is the byte count the UI shows as downloaded. (``rec_total``
        # is deliberately not asserted: its type says bytes and its name says
        # total, but it holds accumulated seconds and only moves on stop.)
        assert status["dl_total"] > 0

    async def test_the_file_creation_is_announced(
        self, client: AsyncClient, fake_server: FakeBiliServer, events: list[Any]
    ) -> None:
        """Regression: starting to record must reach the event bus.

        The event class existed and the notification module listed it as
        something a user can subscribe to, but nothing ever submitted it, so
        "recording started" never arrived. Same shape as #10: defined, wired to
        nothing.
        """
        await _add_task(client)
        await _begin_live(client, fake_server)

        await _wait_until(
            lambda: any(e.type == "VideoFileCreatedEvent" for e in events),
            what="a VideoFileCreatedEvent",
        )
        created = next(e for e in events if e.type == "VideoFileCreatedEvent")
        assert created.data.room_id == _ROOM_ID
        assert created.data.path.endswith(".flv")

        # The danmaku file is opened by the same segment, so it is announced too.
        await _wait_until(
            lambda: any(e.type == "DanmakuFileCreatedEvent" for e in events),
            what="a DanmakuFileCreatedEvent",
        )


class TestStoppingTheRecording:
    """Turning the recorder off must actually stop it and settle the status."""

    async def test_disabling_the_recorder_ends_an_active_recording(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """Regression (#9): the switch used to only stop *future* recordings.

        Disabling it detached the listener and left the recording in flight, so
        the UI kept saying "recording" and the stream kept being pulled.
        """
        await _add_task(client)
        await _begin_live(client, fake_server)
        await _wait_until(
            lambda: bool(_files(out_dir, ".flv")), what="recording to start"
        )

        resp = await client.post(f"/api/v1/tasks/{_ROOM_ID}/recorder/disable")
        assert resp.json()["code"] == 0

        async def _stopped() -> bool:
            return (await _status(client))["running_status"] != "recording"

        deadline = asyncio.get_running_loop().time() + _TIMEOUT
        while asyncio.get_running_loop().time() < deadline:
            if await _stopped():
                break
            await asyncio.sleep(_POLL)
        else:
            pytest.fail("The task still reports itself as recording")

        status = await _status(client)
        assert status["recorder_enabled"] is False

    async def test_the_recording_is_finalised_on_disk(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """Whatever was recorded must survive the stop, not be truncated."""
        await _add_task(client)
        await _begin_live(client, fake_server)
        await _wait_until(
            lambda: bool(_files(out_dir, ".flv")), what="recording to start"
        )
        flv = _files(out_dir, ".flv")[0]
        await _wait_until(lambda: flv.stat().st_size > 2000, what="data on disk")
        recorded = flv.stat().st_size

        await client.post(f"/api/v1/tasks/{_ROOM_ID}/recorder/disable")
        await asyncio.sleep(0.5)

        # Post-processing may move it, so accept either the FLV or its output.
        survivors = _files(out_dir, ".flv") + _files(out_dir, ".mp4")
        assert survivors, "the recording vanished when the recorder stopped"
        assert survivors[0].stat().st_size >= recorded


class TestPostProcessingAfterTheStop:
    """A finished segment must be handed over and produce its artefacts."""

    async def test_the_danmaku_xml_is_converted_to_ass(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """Regression (#10): enabling danmaku→ASS must produce an ASS file.

        Nothing connected the finished segment to the post-processor, so the XML
        was simply left where it was. This is the user-visible promise of the
        option, end to end: switch it on, record, stop, get subtitles.
        """
        resp = await client.patch(
            "/api/v1/settings",
            json={"postprocessing": {"danmaku_to_ass": True}},
        )
        assert resp.json()["code"] == 0

        await _add_task(client)
        await _begin_live(client, fake_server)
        await _wait_until(
            lambda: bool(_files(out_dir, ".xml")), what="the danmaku XML to be created"
        )
        await _wait_until(
            lambda: bool(_files(out_dir, ".flv")), what="recording to start"
        )

        await client.post(f"/api/v1/tasks/{_ROOM_ID}/recorder/disable")

        await _wait_until(
            lambda: bool(_files(out_dir, ".ass")), what="the ASS subtitle to be written"
        )
        ass = _files(out_dir, ".ass")[0]
        assert "[Script Info]" in ass.read_text(encoding="utf-8")

    async def test_no_ass_when_the_option_is_off(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """The default must not start writing subtitles nobody asked for."""
        await _add_task(client)
        await _begin_live(client, fake_server)
        await _wait_until(
            lambda: bool(_files(out_dir, ".flv")), what="recording to start"
        )

        await client.post(f"/api/v1/tasks/{_ROOM_ID}/recorder/disable")
        await asyncio.sleep(1.0)

        assert _files(out_dir, ".ass") == []

    async def test_turning_remux_off_keeps_the_recording(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """Regression: not wanting an MP4 must not cost the user the recording.

        Post-processing deleted the source as its last step, and skipping the
        remux skips the only step that would have produced a replacement. So the
        FLV was removed with nothing put in its place: the recording was gone.
        Wanting the original file and no MP4 is a perfectly ordinary choice.
        """
        resp = await client.patch(
            "/api/v1/settings",
            json={"postprocessing": {"remux_to_mp4": False}},
        )
        assert resp.json()["code"] == 0

        await _add_task(client)
        await _begin_live(client, fake_server)
        await _wait_until(
            lambda: bool(_files(out_dir, ".flv")), what="recording to start"
        )
        flv = _files(out_dir, ".flv")[0]
        await _wait_until(lambda: flv.stat().st_size > 2000, what="data on disk")

        await client.post(f"/api/v1/tasks/{_ROOM_ID}/recorder/disable")
        await asyncio.sleep(1.5)

        assert _files(out_dir, ".flv") or _files(out_dir, ".mp4"), (
            "the recording was deleted and nothing was produced to replace it"
        )

    async def test_the_finished_files_are_announced(
        self,
        client: AsyncClient,
        fake_server: FakeBiliServer,
        out_dir: Path,
        events: list[Any],
    ) -> None:
        """The completion events the UI listens for must actually be published."""
        await _add_task(client)
        await _begin_live(client, fake_server)
        await _wait_until(
            lambda: bool(_files(out_dir, ".flv")), what="recording to start"
        )

        await client.post(f"/api/v1/tasks/{_ROOM_ID}/recorder/disable")

        await _wait_until(
            lambda: any(e.type == "VideoFileCompletedEvent" for e in events),
            what="a VideoFileCompletedEvent",
        )
        completed = next(e for e in events if e.type == "VideoFileCompletedEvent")
        assert completed.data.room_id == _ROOM_ID
        assert completed.data.path.endswith(".flv")
