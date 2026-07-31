"""System tests for the pieces around the recording: disk space and updates.

Both have unit tests that drive them with hand-made input. What those cannot
answer is whether the module is reachable at all from a running application —
the question behind #10, and the one this file asks of each.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from birec.space import SpaceInfo, SpaceReclaimer

from .fake_bili_server import FakeBiliServer
from .harness import add_task, begin_live


async def begin_recording(client: AsyncClient, fake_server: FakeBiliServer) -> None:
    await add_task(client)
    await begin_live(client, fake_server)


class TestDiskSpace:
    """Disk-space handling has to be reachable from the running application."""

    async def test_the_application_watches_disk_space(
        self, client: AsyncClient
    ) -> None:
        """Regression: the disk has to actually be watched, not just watchable.

        ``RecordTaskManager`` took a monitor and a reclaimer and nothing ever
        built one, so both slots were always ``None``. A tool meant to run for
        weeks writing video had nobody looking at the disk it was filling.
        """
        application = client.app.state.application  # type: ignore[attr-defined]

        assert application.task_manager.space_monitor is not None
        assert application.task_manager.space_reclaimer is not None
        # Started with the manager, not merely handed to it.
        assert application.space_monitor.is_running is True

    async def test_a_full_disk_is_warned_about(
        self, client: AsyncClient, out_dir: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The user has to hear about it, because afterwards it is too late.

        Driven through the real callback the monitor calls, so what is checked
        is the reaction the application actually wired up rather than a
        hand-rolled stand-in.
        """
        application = client.app.state.application  # type: ignore[attr-defined]
        info = SpaceInfo(
            total=100 * 1024**3, used=99 * 1024**3, free=1024**3, path=str(out_dir)
        )

        with caplog.at_level(logging.WARNING, logger="birec.application"):
            application._on_space_low(info)  # noqa: SLF001

        assert any("Low disk space" in record.message for record in caplog.records)

    async def test_old_recordings_are_only_deleted_when_asked_for(
        self, client: AsyncClient, out_dir: Path
    ) -> None:
        """Reclaiming space deletes the user's recordings, so it is opt-in.

        ``recycle_records`` defaults to off. Filling the disk must not quietly
        cost somebody the archive they were recording it for.
        """
        application = client.app.state.application  # type: ignore[attr-defined]
        room_dir = out_dir / "12345 - TestStreamer"
        room_dir.mkdir(parents=True, exist_ok=True)
        old = room_dir / "blive_12345_old.flv"
        old.write_bytes(b"x" * 4096)
        os.utime(old, (0, 0))  # far older than any TTL

        settings = application.settings_manager.settings
        assert settings.space.recycle_records is False
        info = SpaceInfo(
            total=100 * 1024**3, used=99 * 1024**3, free=1024**3, path=str(out_dir)
        )

        application._on_space_low(info)  # noqa: SLF001
        assert old.exists(), "a recording was deleted without being asked"

        settings.space.recycle_records = True
        application._space_reclaimer._rec_ttl = 0  # noqa: SLF001
        application._on_space_low(info)  # noqa: SLF001
        assert not old.exists(), "the reclaimer left the old recording behind"

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
