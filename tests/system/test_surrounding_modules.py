"""System tests for the pieces around the recording: disk space and updates.

Both have unit tests that drive them with hand-made input. What those cannot
answer is whether the module is reachable at all from a running application —
the question behind #10, and the one this file asks of each.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from birec.space import SpaceReclaimer

from .fake_bili_server import FakeBiliServer
from .harness import add_task, begin_live


async def begin_recording(client: AsyncClient, fake_server: FakeBiliServer) -> None:
    await add_task(client)
    await begin_live(client, fake_server)


class TestDiskSpace:
    """Disk-space handling has to be reachable from the running application."""

    @pytest.mark.xfail(
        reason="nothing constructs a SpaceMonitor; the manager's slot stays None",
        strict=True,
    )
    async def test_the_application_watches_disk_space(
        self, client: AsyncClient
    ) -> None:
        """A long recording filling the disk should be noticed.

        ``RecordTaskManager`` takes a monitor and a reclaimer, but nothing in
        ``src`` ever builds one, so both slots are always ``None`` and the disk
        is never watched. Once more: implemented, never connected.

        Strict, so it turns green the day they are wired up.
        """
        task_manager = client.app.state.application.task_manager  # type: ignore[attr-defined]
        assert task_manager.space_monitor is not None

    async def test_the_reclaimer_finds_old_recordings(self, out_dir: Path) -> None:
        """The reclaimer must work against a real directory of recordings.

        Pinned here because it is the part that deletes the user's files: it has
        to agree with the layout the recorder actually writes.
        """
        room_dir = out_dir / "12345 - TestStreamer"
        room_dir.mkdir(parents=True)
        old = room_dir / "blive_12345_old.flv"
        old.write_bytes(b"x" * 4096)

        reclaimer = SpaceReclaimer([out_dir], rec_ttl=0)

        assert old in reclaimer.find_reclaimable_files()


class TestUpdateCheck:
    """The update endpoint must answer without reaching the real PyPI."""

    async def test_it_reports_the_latest_version(self, client: AsyncClient) -> None:
        with patch(
            "birec.update.PypiApi.get_latest_version_string",
            new=AsyncMock(return_value="9.9.9"),
        ):
            body = (await client.get("/api/v1/update/version/latest")).json()

        assert body["code"] == 0
        assert body["data"]["version"] == "9.9.9"

    async def test_an_unreachable_pypi_is_reported_not_raised(
        self, client: AsyncClient
    ) -> None:
        """A checker that cannot reach PyPI must not take the endpoint down."""
        with patch(
            "birec.update.PypiApi.get_latest_version_string",
            new=AsyncMock(side_effect=OSError("network down")),
        ):
            resp = await client.get("/api/v1/update/version/latest")

        assert resp.status_code == 200
        assert resp.json()["code"] == 502

    async def test_an_unknown_project_is_a_404(self, client: AsyncClient) -> None:
        with patch(
            "birec.update.PypiApi.get_latest_version_string",
            new=AsyncMock(return_value=None),
        ):
            body = (await client.get("/api/v1/update/version/latest")).json()

        assert body["code"] == 404
