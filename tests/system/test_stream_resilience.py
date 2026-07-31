"""System tests for a stream that misbehaves: breaks, restarts, dead CDNs.

Recording a stream that arrives intact is the easy half. In production the
interesting half is the other one: a live pull lasting hours reconnects many
times, and every reconnect is a place where the recording can quietly stop
without anything saying so. Both bugs behind #9 were of exactly that kind, and
so were the three this file was written to find.

Everything here drives the real download loop, the real FLV pipeline and real
files, against a fake CDN that has been told to fail in a specific way.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient

from .fake_bili_server import FakeBiliServer
from .harness import (
    ROOM_ID,
    add_task,
    begin_live,
    files,
    wait_for_recording,
    wait_until,
    wait_until_not_recording,
    wait_until_recording,
)

# Every test in this file needs the reconnect backoff shortened, or it would
# spend its whole budget waiting for production-sized delays.
pytestmark = pytest.mark.usefixtures("fast_reconnect")


class TestReconnectingAfterABreak:
    """A dropped connection must cost the stream a moment, not the recording."""

    async def test_the_recording_survives_a_dropped_connection(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """Regression: after a reconnect the file must keep growing.

        One HTTP connection is one FLV document, so the CDN starts the next one
        with a fresh file header. That header landed where a tag was expected,
        the stream was declared corrupt, and the subscription ended: downloading
        went on, the byte counter went on, and nothing further reached the disk.
        The file stopped growing while the UI still said "recording" — the same
        silent loss as #9, reached by a different road.
        """
        fake_server.set_fault(stream_break_after_chunks=40, stream_break_times=1)

        await add_task(client)
        await begin_live(client, fake_server)
        flv = await wait_for_recording(out_dir, min_size=1000)

        await wait_until(
            lambda: fake_server.stream_requests >= 2,
            what="the download to reconnect",
        )
        after_reconnect = flv.stat().st_size

        await wait_until(
            lambda: flv.stat().st_size > after_reconnect,
            what="the recording to keep growing after the reconnect",
        )

    async def test_repeated_breaks_are_all_recovered_from(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """A bad few minutes is many breaks, not one; each must recover.

        The interesting part is that the breaks land at arbitrary byte offsets,
        so some of them cut a tag in half. A fragment spliced onto the next
        document's header leaves the parser misaligned from there on, which is
        indistinguishable from the stream simply stopping.
        """
        fake_server.set_fault(stream_break_after_chunks=25, stream_break_times=4)

        await add_task(client)
        await begin_live(client, fake_server)
        flv = await wait_for_recording(out_dir, min_size=1000)

        await wait_until(
            lambda: fake_server.stream_requests >= 5,
            what="all four breaks to be reconnected through",
        )
        recovered = flv.stat().st_size
        await wait_until(
            lambda: flv.stat().st_size > recovered,
            what="the recording to keep growing once the breaks stop",
        )

    async def test_a_stream_that_ends_normally_is_picked_up_again(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """A CDN closing the connection cleanly is still a live room.

        Nothing is wrong here and nothing is being retried: the loop is supposed
        to reconnect and carry on appending to the same file.
        """
        # A short payload, so the server reaches its end and closes repeatedly.
        fake_server.stream_extra_frames = 30

        await add_task(client)
        await begin_live(client, fake_server)
        flv = await wait_for_recording(out_dir, min_size=1000)

        await wait_until(
            lambda: fake_server.stream_requests >= 3,
            what="the stream to be re-fetched after ending",
        )
        size = flv.stat().st_size
        await wait_until(
            lambda: flv.stat().st_size > size,
            what="the re-fetched stream to be appended to the same file",
        )


class TestGivingUp:
    """When the stream is unrecoverable, the task must say so."""

    async def test_a_download_that_gives_up_stops_claiming_to_record(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """Regression: running out of retries must settle the task's status.

        The loop stops after ten failed attempts and nothing was watching for
        it, so the task reported itself as recording for as long as the room
        stayed live: segment never closed, never post-processed, not a byte
        written. What the dashboard showed and what was happening were
        unrelated.
        """
        fake_server.set_fault(stream_break_after_chunks=2, stream_break_times=999)

        await add_task(client)
        await begin_live(client, fake_server)
        await wait_until_recording(client)

        await wait_until_not_recording(client)

        # And the little that did arrive was closed off rather than abandoned.
        assert files(out_dir, ".flv"), "the abandoned recording is gone from disk"

    async def test_giving_up_hands_the_segment_over(
        self,
        client: AsyncClient,
        fake_server: FakeBiliServer,
        out_dir: Path,
        events: list,
    ) -> None:
        """Whatever was recorded before giving up must still be announced."""
        fake_server.set_fault(stream_break_after_chunks=2, stream_break_times=999)

        await add_task(client)
        await begin_live(client, fake_server)

        await wait_until(
            lambda: any(e.type == "VideoFileCompletedEvent" for e in events),
            what="the abandoned segment to be handed over",
        )


class TestDeadCdn:
    """The API offers several CDNs; one of them being down is ordinary."""

    async def test_an_unreachable_cdn_falls_back_to_a_working_one(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """Regression: a dead first CDN must cost a retry, not the recording.

        ``StreamURLResolver`` had ``resolve_alternative`` for exactly this and
        nothing called it. The loop re-resolved after every failure and
        ``_build_stream_url`` always takes ``url_info[0]``, so the same dead host
        came back ten times and the recording was abandoned with an entirely
        healthy CDN sitting second in the list.
        """
        fake_server.set_fault(stream_dead_cdn_first=True)

        await add_task(client)
        await begin_live(client, fake_server)

        await wait_for_recording(out_dir, min_size=1000, timeout=10.0)
        assert fake_server.stream_requests > 0, "the live CDN was never reached"

    async def test_a_working_cdn_is_not_abandoned_over_a_hiccup(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """Switching away is for hosts that never delivered, not for every drop.

        A CDN that has been streaming happily and then drops one connection is
        the ordinary case; walking away from it each time would keep re-resolving
        and bouncing between hosts instead of picking the stream back up.
        """
        fake_server.set_fault(stream_break_after_chunks=30, stream_break_times=1)

        await add_task(client)
        await begin_live(client, fake_server)
        flv = await wait_for_recording(out_dir, min_size=1000)

        await wait_until(lambda: fake_server.stream_requests >= 2, what="the reconnect")
        size = flv.stat().st_size
        await wait_until(
            lambda: flv.stat().st_size > size,
            what="the same CDN to carry on after the drop",
        )


class TestAStreamThatOffersNothing:
    """Being live is not the same as having something to record."""

    async def test_a_live_room_with_no_playable_url_does_not_crash(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """The API can say "live" and hand back no stream at all.

        The URL never resolves, so the loop retries and eventually gives up.
        What must not happen is an exception escaping into the task, or the
        status sitting on "recording" forever.
        """
        fake_server.set_fault(playurl_null=True)

        await add_task(client)
        await begin_live(client, fake_server)
        await wait_until_recording(client)

        await wait_until_not_recording(client)

    async def test_an_empty_stream_is_given_up_on(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """Regression: an endpoint answering 200 with no body must not be forever.

        A connection ending cleanly is the ordinary end of a live stream, so the
        retry budget was reset every time one did. An endpoint that answers 200
        and immediately closes ends cleanly too, so it was retryable without
        limit: the task claimed to be recording a file that never grew past its
        header, for as long as the room stayed live.

        Now only a connection that actually carried bytes counts as evidence the
        stream is healthy, so this one burns the budget and the segment closes.
        """
        fake_server.set_fault(stream_empty=True)

        await add_task(client)
        await begin_live(client, fake_server)
        await wait_until_recording(client)

        await wait_until(
            lambda: fake_server.stream_requests >= 2,
            what="the empty stream to be retried",
        )
        await wait_until_not_recording(client)

        # Nothing was parseable, so nothing but the header can have been written.
        for flv in files(out_dir, ".flv"):
            assert flv.stat().st_size < 100, "bytes appeared out of an empty stream"

    async def test_an_api_that_errors_is_answered_not_raised(
        self, client: AsyncClient, fake_server: FakeBiliServer
    ) -> None:
        """Regression: Bilibili refusing the room must come back as an answer.

        ``ApiRequestError`` is neither a ``ValueError`` nor a ``RuntimeError``,
        the two the handler caught, so it escaped into the framework and the
        caller got a bare 500 instead of the ``{code, message}`` every other
        endpoint answers with.
        """
        fake_server.set_fault(api_error_code=-400)

        # Slow on purpose: the API layer retries a failing endpoint for twenty
        # seconds before giving up, and going through that budget for real is
        # the difference between this and the unit test of the same handler.
        resp = await client.post(f"/api/v1/tasks/{ROOM_ID}", json={"room_id": ROOM_ID})

        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 502
        assert "-400" in body["message"] or "injected" in body["message"]

        # And nothing half-built was left behind for the room.
        listed = (await client.get("/api/v1/tasks/data")).json()
        assert listed["data"]["total"] == 0
