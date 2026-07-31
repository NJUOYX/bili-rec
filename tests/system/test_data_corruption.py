"""System tests for bytes that are not what the parser was promised.

A CDN can hand over a byte that no FLV grammar accepts, and the recorder has to
do something sensible with what it already has. Sensible has two parts, and the
weaker one is easy to mistake for the whole thing: not crashing. The part that
matters is that the recording made so far stays on disk and the task stops
claiming to be recording, because the alternative — a live-looking task whose
file never grows again — is how every silent data loss in this project has
looked so far.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from httpx import AsyncClient

from .fake_bili_server import FakeBiliServer
from .harness import (
    add_task,
    begin_live,
    end_live,
    files,
    status,
    wait_until,
    wait_until_not_recording,
    wait_until_recording,
)

pytestmark = pytest.mark.usefixtures("fast_reconnect")


class TestCorruptedBytes:
    """Unparseable data must cost the rest of the stream, not what was recorded."""

    async def test_a_bad_tag_type_finalizes_instead_of_spinning(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """Regression: a dead pipeline must not look like an ongoing recording.

        Reactivex delivers ``on_error`` once and tears the chain down with it, so
        after one bad byte nothing is ever written again. The error was only
        logged: the file stopped growing while the task reported itself as
        recording and the download went on consuming the stream.

        Closing the segment is a deliberate trade. Skipping the bad byte and
        carrying on would be better still, and is a larger piece of work; being
        honest about having stopped is the part that matters.
        """
        fake_server.set_fault(stream_bad_tag_type=True)

        await add_task(client)
        await begin_live(client, fake_server)
        await wait_until_recording(client)

        await wait_until_not_recording(client)

        recorded = files(out_dir, ".flv")
        assert recorded, "everything recorded before the bad byte was lost"
        assert recorded[0].stat().st_size > 13, "only the header survived"

    async def test_garbage_in_the_middle_keeps_what_came_before(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """Bytes spliced into a tag boundary are the same class of problem.

        Here the junk is read as a tag header whose fields are nonsense, rather
        than as an unknown type; the outcome the user cares about is the same.
        """
        fake_server.set_fault(stream_garbage_at_byte=900)

        await add_task(client)
        await begin_live(client, fake_server)
        await wait_until_recording(client)

        await wait_until_not_recording(client)

        recorded = files(out_dir, ".flv")
        assert recorded, "the recording up to the junk was lost"
        assert recorded[0].stat().st_size > 13

    async def test_the_abandoned_segment_still_reaches_post_processing(
        self,
        client: AsyncClient,
        fake_server: FakeBiliServer,
        out_dir: Path,
        events: list,
    ) -> None:
        """A recording cut short by bad data is still a recording to finish.

        If it never reaches the post-processor it is never remuxed, never gets
        its subtitles, and never leaves the "recording" state in the file list.
        """
        fake_server.set_fault(stream_bad_tag_type=True)

        await add_task(client)
        await begin_live(client, fake_server)

        await wait_until(
            lambda: any(e.type == "VideoFileCompletedEvent" for e in events),
            what="the truncated segment to be handed over",
        )

    async def test_a_truncated_tail_is_waited_on_not_rejected(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """Half a tag is "not yet", not "corrupt".

        Every chunk boundary looks like this, so treating a partial tag as an
        error would break the ordinary case; the parser has to rewind and wait.
        Here the connection ends mid-tag and then reconnects, which is the shape
        that has to survive.
        """
        fake_server.stream_extra_frames = 20
        fake_server.set_fault(stream_truncate_tail=True)

        await add_task(client)
        await begin_live(client, fake_server)

        await wait_until(
            lambda: bool(files(out_dir, ".flv")), what="recording to start"
        )
        flv = files(out_dir, ".flv")[0]

        # The truncated tail is refetched on reconnect; the recording carries on.
        await wait_until(
            lambda: fake_server.stream_requests >= 3,
            what="the truncated stream to be refetched",
        )
        assert (await status(client))["running_status"] == "recording", (
            "a partial tag was mistaken for a corrupt stream"
        )
        assert flv.exists()


class TestNonsenseFromTheApi:
    """The API can answer with things that are well-formed and useless."""

    async def test_a_stalling_api_does_not_wedge_the_task(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """An endpoint that answers slowly must not stop the room recording.

        The API layer has its own timeout and retry, and the delay here is well
        inside it: the point is that the recording still gets going rather than
        being held up behind a slow poll.
        """
        fake_server.set_fault(api_delay=0.3)

        await add_task(client)
        await begin_live(client, fake_server)

        await wait_until(
            lambda: bool(files(out_dir, ".flv")),
            what="the recording to start despite the slow API",
        )

    async def test_an_api_that_starts_failing_mid_recording_is_survived(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """A room can be recorded fine while its metadata endpoint is broken.

        The monitor polls that endpoint every so often, and a failure there must
        not touch the download that is already running.
        """
        await add_task(client)
        await begin_live(client, fake_server)
        await wait_until(
            lambda: bool(files(out_dir, ".flv")), what="recording to start"
        )
        flv = files(out_dir, ".flv")[0]
        await wait_until(lambda: flv.stat().st_size > 2000, what="data on disk")

        fake_server.set_fault(api_error_code=-500)
        size = flv.stat().st_size

        await wait_until(
            lambda: flv.stat().st_size > size,
            what="the recording to carry on through the API failure",
        )

    async def test_a_room_that_goes_offline_mid_recording_is_finalized(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """The ordinary end of a broadcast, checked against a real recording.

        The stream keeps flowing from the fake CDN's point of view, so the only
        thing that ends the segment is the monitor being told the room stopped —
        which is exactly the production sequence.
        """
        await add_task(client)
        await begin_live(client, fake_server)
        await wait_until(
            lambda: bool(files(out_dir, ".flv")), what="recording to start"
        )
        flv = files(out_dir, ".flv")[0]
        await wait_until(lambda: flv.stat().st_size > 2000, what="data on disk")
        recorded = flv.stat().st_size

        await end_live(client, fake_server)
        await wait_until_not_recording(client)
        await asyncio.sleep(0.3)

        survivors = files(out_dir, ".flv") + files(out_dir, ".mp4")
        assert survivors, "the recording vanished when the room went offline"
        assert survivors[0].stat().st_size >= recorded
