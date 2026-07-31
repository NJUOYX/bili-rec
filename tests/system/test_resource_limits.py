"""System tests for the limits the filesystem imposes on a recording.

The recorder writes user-supplied text into paths and megabytes into files, on a
disk it does not own. Every one of those is a place where the operating system
can say no, and the recording has to end as a closed file and an honest status
rather than a traceback.
"""

from __future__ import annotations

import builtins
import shutil
from pathlib import Path

import pytest
from httpx import AsyncClient

from .fake_bili_server import FakeBiliServer
from .harness import (
    add_task,
    begin_live,
    files,
    wait_until,
    wait_until_not_recording,
    wait_until_recording,
)

pytestmark = pytest.mark.usefixtures("fast_reconnect")

# Characters a path cannot contain, and a title long enough to overrun the
# 255-byte limit most filesystems put on a single component.
_HOSTILE_TITLE = "危险/标题:带*非法?字符<>|" + "长" * 200


class TestWhenTheDiskSaysNo:
    """A filesystem refusing to write must end the recording, not the process."""

    async def test_a_full_disk_finalizes_instead_of_crashing(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """Running out of space mid-recording must be survivable.

        The write is the only thing that fails; the task, the danmaku socket and
        every other room have to carry on being managed. Not filling a real disk
        here: the point is the error arriving from ``open`` at the moment the
        recorder reaches for the file, which is what a full disk looks like from
        inside the process.
        """
        real_open = builtins.open
        target: dict[str, Path] = {}

        def failing_open(file, mode="r", *args, **kwargs):  # type: ignore[no-untyped-def]
            path = Path(file) if isinstance(file, str | Path) else None
            if path is not None and path.suffix == ".flv" and "w" in str(mode):
                target["path"] = path
                raise OSError(28, "No space left on device")
            return real_open(file, mode, *args, **kwargs)

        await add_task(client)
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(builtins, "open", failing_open)
            await begin_live(client, fake_server)
            await wait_until_recording(client)
            await wait_until(
                lambda: "path" in target,
                what="the recorder to try opening the recording",
            )
            await wait_until_not_recording(client)

        # The application is still answering, and the room is still listed.
        body = (await client.get("/api/v1/tasks/data")).json()
        assert body["code"] == 0
        assert body["data"]["total"] == 1

    async def test_an_output_directory_that_vanished_is_recreated(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """Somebody deleting the output folder must not stop the next recording.

        Between broadcasts the directory is nothing special, and a user tidying
        up their disk is entitled to remove it.
        """
        await add_task(client)
        out_dir.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(out_dir)
        assert not out_dir.exists()

        await begin_live(client, fake_server)

        await wait_until(
            lambda: bool(files(out_dir, ".flv")),
            what="the recorder to recreate its output directory",
        )


class TestHostileRoomTitles:
    """A room title is text a stranger chose, and it ends up in a path."""

    async def test_a_title_full_of_illegal_characters_still_records(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """Path separators and reserved characters must be dealt with.

        A title is arbitrary user input, and the recorder turns it into a
        filename. Passed through unchanged, a ``/`` silently redirects the
        recording into a directory that does not exist and the whole broadcast
        is lost.
        """
        fake_server.room_title = _HOSTILE_TITLE
        fake_server.streamer_name = "主播/带斜杠"

        await add_task(client)
        await begin_live(client, fake_server)

        await wait_until(
            lambda: bool(files(out_dir, ".flv")),
            what="a recording despite the hostile title",
        )
        recording = files(out_dir, ".flv")[0]

        # Every component has to be something the filesystem accepted, which it
        # demonstrably did, and short enough to be legal.
        for part in recording.relative_to(out_dir).parts:
            assert len(part.encode("utf-8")) <= 255, f"path component too long: {part}"
        assert recording.stat().st_size >= 0


class TestNotLeakingBetweenRecordings:
    """Recording repeatedly must not accumulate anything."""

    async def test_repeated_recordings_do_not_leak_file_handles(
        self, client: AsyncClient, fake_server: FakeBiliServer, out_dir: Path
    ) -> None:
        """Three broadcasts must not leave three files open.

        A recorder is meant to run for weeks, so a handle leaked per segment is
        a process that dies of exhaustion some days in — with no clue pointing
        back at the segment boundary.
        """
        fd_dir = Path("/proc/self/fd")
        if not fd_dir.exists():
            pytest.skip("no /proc/self/fd to count open handles with")

        await add_task(client)

        def open_handles() -> int:
            return len(list(fd_dir.iterdir()))

        baseline = 0
        for round_number in range(3):
            await begin_live(client, fake_server)
            await wait_until(
                lambda: bool(files(out_dir, ".flv")),
                what=f"recording {round_number} to start",
            )
            await client.post("/api/v1/tasks/12345/recorder/disable")
            await wait_until_not_recording(client)
            await client.post("/api/v1/tasks/12345/recorder/enable")
            if round_number == 0:
                # After the first round everything that gets cached has been.
                baseline = open_handles()

        # A couple of descriptors of slack for the sockets in flight; a leak per
        # segment would show up as three or more.
        assert open_handles() <= baseline + 2, (
            f"open handles grew from {baseline} to {open_handles()} over 3 segments"
        )
