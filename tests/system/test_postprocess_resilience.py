"""System tests for post-processing that goes wrong after a real recording.

Post-processing is the last thing between a finished download and the file a
user keeps, and it is where the worst failures live: everything upstream can be
perfect and the recording still be deleted, converted into nothing, or left
sitting in the queue forever. #10 was this stage never being connected at all,
and the deletion bug was this stage removing a recording it had not replaced.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree

import pytest
from httpx import AsyncClient

from .fake_bili_server import FakeBiliServer
from .harness import (
    ROOM_ID,
    add_task,
    begin_live,
    end_live,
    files,
    wait_until,
    wait_until_not_recording,
    wait_until_recording,
)

pytestmark = pytest.mark.usefixtures("fast_reconnect")


async def _record_briefly(
    client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
) -> Path:
    """Record a real segment and stop it, returning the file it wrote."""
    await begin_live(client, fake_server)
    await wait_until(lambda: bool(files(out_dir, ".flv")), what="recording to start")
    flv = files(out_dir, ".flv")[0]
    await wait_until(lambda: flv.stat().st_size > 2000, what="data on disk")
    return flv


class TestWhenTheRemuxFails:
    """A conversion that does not happen must not cost the original."""

    async def test_a_failed_remux_keeps_the_recording(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """ffmpeg missing or refusing must leave the FLV exactly where it is.

        Deleting the source is the step after the remux, and it is only safe
        because the remux produced a replacement. A remux that reports failure
        has produced nothing, so the recording is all the user has left.
        """
        await client.patch(
            "/api/v1/settings", json={"postprocessing": {"remux_to_mp4": True}}
        )
        await add_task(client)

        async def _refuse(_src: Path, _dst: Path) -> bool:
            return False

        with patch(
            "birec.postprocess.postprocessor.remux_flv_to_mp4",
            new=_refuse,
        ):
            flv = await _record_briefly(client, fake_server, out_dir)
            recorded = flv.stat().st_size

            await client.post(f"/api/v1/tasks/{ROOM_ID}/recorder/disable")
            await wait_until_not_recording(client)
            await asyncio.sleep(1.0)

        assert flv.exists(), "the recording was deleted after a failed remux"
        assert flv.stat().st_size >= recorded
        assert not files(out_dir, ".mp4"), "an MP4 appeared out of a failed remux"

    async def test_a_remux_that_raises_keeps_the_recording(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """An exception is a harsher failure than ``False`` and must cost no more.

        A crash mid-conversion is where a half-written MP4 could be mistaken for
        a replacement, and the source deleted against it.
        """
        await client.patch(
            "/api/v1/settings", json={"postprocessing": {"remux_to_mp4": True}}
        )
        await add_task(client)

        async def _explode(_src: Path, _dst: Path) -> bool:
            raise OSError("ffmpeg died")

        with patch(
            "birec.postprocess.postprocessor.remux_flv_to_mp4",
            new=_explode,
        ):
            flv = await _record_briefly(client, fake_server, out_dir)

            await client.post(f"/api/v1/tasks/{ROOM_ID}/recorder/disable")
            await wait_until_not_recording(client)
            await asyncio.sleep(1.0)

        assert flv.exists(), "the recording was deleted after the remux crashed"


class TestWhenTheDanmakuCannotBeConverted:
    """Subtitles are a bonus; failing to make them must cost only them."""

    async def test_a_failed_ass_conversion_leaves_the_recording_alone(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """The video and the XML both have to survive a converter that fails.

        The XML is the source of truth for the danmaku and can be converted
        again later; losing it to a failed conversion would be losing the only
        copy.
        """
        await client.patch(
            "/api/v1/settings",
            json={"postprocessing": {"danmaku_to_ass": True, "remux_to_mp4": False}},
        )
        await add_task(client)

        async def _explode(*_args: object, **_kwargs: object) -> None:
            raise ValueError("not convertible")

        with patch(
            "birec.postprocess.postprocessor.convert_danmaku_to_ass",
            new=_explode,
        ):
            flv = await _record_briefly(client, fake_server, out_dir)
            await client.post(f"/api/v1/tasks/{ROOM_ID}/recorder/disable")
            await wait_until_not_recording(client)
            await asyncio.sleep(1.0)

        assert flv.exists(), "the recording was lost to a subtitle conversion"
        assert files(out_dir, ".xml"), "the danmaku XML was lost with the conversion"
        assert not files(out_dir, ".ass")


class TestDanmakuTextThatFightsXml:
    """Danmaku text is arbitrary, and the XML it goes into is not."""

    async def test_xml_hostile_danmaku_still_produce_a_readable_document(
        self,
        client: AsyncClient,
        fake_server: FakeBiliServer,
        out_dir: Path,
    ) -> None:
        """A viewer typing ``&`` or ``<`` must not corrupt the whole file.

        The XML is written by hand, one line at a time, so an unescaped
        character does not fail loudly: it produces a document that every parser
        rejects, taking the entire session's danmaku with it and failing the ASS
        conversion downstream. Checked with a real parser rather than by looking
        for substrings, because well-formedness is exactly the property at stake.
        """
        await client.patch(
            "/api/v1/settings",
            json={"postprocessing": {"danmaku_to_ass": True, "remux_to_mp4": False}},
        )
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

        hostile = 'A & B < C > D " E \' F <d p="fake">injected</d>'
        await fake_server.send_danmaku(hostile, uname='an<gry>&"viewer"')
        await fake_server.send_danmaku("plain one after it")
        await wait_until(
            lambda: "plain one after it" in xml.read_text(encoding="utf-8"),
            what="the hostile danmaku and the one behind it to be written",
        )

        await client.post(f"/api/v1/tasks/{ROOM_ID}/recorder/disable")
        await wait_until_not_recording(client)
        await wait_until(
            lambda: xml.read_text(encoding="utf-8").rstrip().endswith("</i>"),
            what="the document to be closed off",
        )

        # The whole point: a parser has to accept it.
        tree = ElementTree.parse(xml)
        texts = [element.text or "" for element in tree.getroot().iter("d")]
        assert hostile in texts, "the text was mangled on its way through the escaping"
        # And the injected markup stayed text rather than becoming an element.
        assert tree.getroot().find(".//d/d") is None, "the danmaku injected an element"

        # Downstream still works: the subtitles were produced from that document.
        await wait_until(
            lambda: bool(files(out_dir, ".ass")),
            what="the ASS subtitle to be written from the hostile XML",
        )


class TestTheQueue:
    """Segments arrive faster than they are processed; none may be dropped."""

    async def test_three_segments_are_all_processed(
        self,
        client: AsyncClient,
        fake_server: FakeBiliServer,
        out_dir: Path,
        events: list,
    ) -> None:
        """Back-to-back broadcasts queue up, and the queue must drain.

        A worker that only ever handles the item it happened to see is the kind
        of bug that shows up as "the last recording never finished", which is
        both easy to miss and unrecoverable.

        The remux is switched off so the outcome does not depend on whether the
        machine running the tests happens to have ffmpeg.
        """
        await client.patch(
            "/api/v1/settings", json={"postprocessing": {"remux_to_mp4": False}}
        )
        await add_task(client)

        for _ in range(3):
            await begin_live(client, fake_server)
            await wait_until_recording(client)
            await wait_until(
                lambda: bool(files(out_dir, ".flv") + files(out_dir, ".mp4")),
                what="a recording to appear",
            )
            await end_live(client, fake_server)
            await wait_until_not_recording(client)
            # Long enough for the next filename's timestamp to differ.
            await asyncio.sleep(1.1)

        completed = [e for e in events if e.type == "VideoFileCompletedEvent"]
        assert len(completed) == 3, (
            f"only {len(completed)} of 3 segments were handed to post-processing"
        )

        await wait_until(
            lambda: (
                len(
                    [e for e in events if e.type == "VideoPostprocessingCompletedEvent"]
                )
                == 3
            ),
            what="all three segments to finish post-processing",
        )
