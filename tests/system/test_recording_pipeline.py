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
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from .fake_bili_server import FakeBiliServer
from .harness import (
    ROOM_ID,
    add_task,
    begin_live,
    files,
    status,
    wait_until,
    wait_until_async,
    wait_until_not_recording,
)


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
        await add_task(client)
        await begin_live(client, fake_server)

        await wait_until(
            lambda: bool(files(out_dir, ".flv")), what="the FLV file to be created"
        )
        flv = files(out_dir, ".flv")[0]

        # Well past the 13-byte header and the metadata tag: real tags got
        # through, across chunk boundaries.
        await wait_until(
            lambda: flv.stat().st_size > 2000, what="stream data to reach the disk"
        )

    async def test_the_file_keeps_growing_while_recording(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """Regression (#9): the data must be flushed, not held in a buffer.

        A file that only materialises at the end looks identical to a broken
        recording while it is happening, which is exactly what users reported.
        """
        await add_task(client)
        await begin_live(client, fake_server)

        await wait_until(
            lambda: bool(files(out_dir, ".flv")), what="the FLV file to be created"
        )
        flv = files(out_dir, ".flv")[0]
        await wait_until(lambda: flv.stat().st_size > 1000, what="the first flush")

        first = flv.stat().st_size
        await wait_until(
            lambda: flv.stat().st_size > first, what="the recording to grow further"
        )

    async def test_the_api_reports_the_recording_it_is_writing(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """The path and byte count the UI shows must match what is on disk."""
        await add_task(client)
        await begin_live(client, fake_server)

        await wait_until(
            lambda: bool(files(out_dir, ".flv")), what="the FLV file to be created"
        )
        flv = files(out_dir, ".flv")[0]
        await wait_until(lambda: flv.stat().st_size > 2000, what="data on disk")

        reported = await status(client)
        assert reported["running_status"] == "recording"
        assert Path(reported["recording_path"]) == flv
        # ``dl_total`` is the byte count the UI shows as downloaded. (``rec_total``
        # is deliberately not asserted: its type says bytes and its name says
        # total, but it holds accumulated seconds and only moves on stop.)
        assert reported["dl_total"] > 0

    async def test_the_file_creation_is_announced(
        self, client: AsyncClient, fake_server: FakeBiliServer, events: list[Any]
    ) -> None:
        """Regression: starting to record must reach the event bus.

        The event class existed and the WebSocket stream offered it to
        subscribers, but nothing ever submitted it, so "recording started" never
        arrived. Same shape as #10: defined, wired to nothing.
        """
        await add_task(client)
        await begin_live(client, fake_server)

        await wait_until(
            lambda: any(e.type == "VideoFileCreatedEvent" for e in events),
            what="a VideoFileCreatedEvent",
        )
        created = next(e for e in events if e.type == "VideoFileCreatedEvent")
        assert created.data.room_id == ROOM_ID
        assert created.data.path.endswith(".flv")

        # The danmaku file is opened by the same segment, so it is announced too.
        await wait_until(
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
        await add_task(client)
        await begin_live(client, fake_server)
        await wait_until(
            lambda: bool(files(out_dir, ".flv")), what="recording to start"
        )

        resp = await client.post(f"/api/v1/tasks/{ROOM_ID}/recorder/disable")
        assert resp.json()["code"] == 0

        await wait_until_not_recording(client)

        assert (await status(client))["recorder_enabled"] is False

    async def test_the_recording_is_finalised_on_disk(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """Whatever was recorded must survive the stop, not be truncated."""
        await add_task(client)
        await begin_live(client, fake_server)
        await wait_until(
            lambda: bool(files(out_dir, ".flv")), what="recording to start"
        )
        flv = files(out_dir, ".flv")[0]
        await wait_until(lambda: flv.stat().st_size > 2000, what="data on disk")
        recorded = flv.stat().st_size

        await client.post(f"/api/v1/tasks/{ROOM_ID}/recorder/disable")
        await asyncio.sleep(0.5)

        # Post-processing may move it, so accept either the FLV or its output.
        survivors = files(out_dir, ".flv") + files(out_dir, ".mp4")
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

        await add_task(client)
        await begin_live(client, fake_server)
        await wait_until(
            lambda: bool(files(out_dir, ".xml")), what="the danmaku XML to be created"
        )
        await wait_until(
            lambda: bool(files(out_dir, ".flv")), what="recording to start"
        )

        await client.post(f"/api/v1/tasks/{ROOM_ID}/recorder/disable")

        await wait_until(
            lambda: bool(files(out_dir, ".ass")), what="the ASS subtitle to be written"
        )
        ass = files(out_dir, ".ass")[0]
        assert "[Script Info]" in ass.read_text(encoding="utf-8")

    async def test_no_ass_when_the_option_is_off(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """The default must not start writing subtitles nobody asked for."""
        await add_task(client)
        await begin_live(client, fake_server)
        await wait_until(
            lambda: bool(files(out_dir, ".flv")), what="recording to start"
        )

        await client.post(f"/api/v1/tasks/{ROOM_ID}/recorder/disable")
        await asyncio.sleep(1.0)

        assert files(out_dir, ".ass") == []

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

        await add_task(client)
        await begin_live(client, fake_server)
        await wait_until(
            lambda: bool(files(out_dir, ".flv")), what="recording to start"
        )
        flv = files(out_dir, ".flv")[0]
        await wait_until(lambda: flv.stat().st_size > 2000, what="data on disk")

        await client.post(f"/api/v1/tasks/{ROOM_ID}/recorder/disable")
        await asyncio.sleep(1.5)

        assert files(out_dir, ".flv") or files(out_dir, ".mp4"), (
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
        await add_task(client)
        await begin_live(client, fake_server)
        await wait_until(
            lambda: bool(files(out_dir, ".flv")), what="recording to start"
        )

        await client.post(f"/api/v1/tasks/{ROOM_ID}/recorder/disable")

        await wait_until(
            lambda: any(e.type == "VideoFileCompletedEvent" for e in events),
            what="a VideoFileCompletedEvent",
        )
        completed = next(e for e in events if e.type == "VideoFileCompletedEvent")
        assert completed.data.room_id == ROOM_ID
        assert completed.data.path.endswith(".flv")


class TestHlsRecording:
    """Choosing the HLS stream format must actually record over HLS."""

    @pytest.mark.xfail(
        reason="no HLS download loop exists; create_hls_pipeline has no caller",
        strict=True,
    )
    async def test_choosing_fmp4_records_over_hls(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """Asking for fmp4 should pull the playlist, not silently fall back.

        It does not. ``StreamRecorder`` can build an HLS pipeline, but nothing
        in ``src`` ever calls ``create_hls_pipeline``: the only download loop
        there is speaks FLV. So the setting is accepted, reported back, and
        quietly ignored — the recording is FLV and the playlist is never
        fetched. The same shape as #10 once more: built, never connected.

        Strict, so it turns green the day the HLS loop lands.
        """
        resp = await client.patch(
            "/api/v1/settings",
            json={"recorder": {"stream_format": "fmp4"}},
        )
        assert resp.json()["code"] == 0

        await add_task(client)
        await begin_live(client, fake_server)

        await wait_until(
            lambda: fake_server.playlist_requests > 0,
            timeout=4.0,
            what="the HLS playlist to be fetched",
        )
        assert fake_server.segment_requests > 0

    async def test_the_fallback_to_flv_is_reported_honestly(
        self, client: AsyncClient, fake_server: FakeBiliServer
    ) -> None:
        """Until HLS works, the status must not claim a format it is not using.

        This pins today's behaviour so the fallback stays visible rather than
        being mistaken for working HLS: the recording really is FLV, and that is
        what the API reports.
        """
        await client.patch(
            "/api/v1/settings",
            json={"recorder": {"stream_format": "fmp4"}},
        )
        await add_task(client)
        await begin_live(client, fake_server)

        async def _has_format() -> bool:
            return bool((await status(client))["real_stream_format"])

        await wait_until_async(_has_format, what="the recorder to settle on a format")

        assert (await status(client))["real_stream_format"] == "flv"
        assert fake_server.playlist_requests == 0
