"""Unit tests for the application-level task factory wiring (§5.10)."""

from __future__ import annotations

from pathlib import Path

import pytest

from birec.application import Application
from birec.setting.models import (
    HeaderOptions,
    PostprocessingOptions,
    RecorderOptions,
    TaskSettings,
)


@pytest.fixture
def application(tmp_path: Path) -> Application:
    """An application rooted in a temporary directory (no network calls)."""
    return Application(
        config_path=tmp_path / "config.toml",
        output_dir=tmp_path / "recordings",
        log_dir=tmp_path / "logs",
    )


class TestTaskFactory:
    def test_manager_has_a_factory(self, application: Application) -> None:
        """Adding a task over the API must not fail for lack of a factory."""
        assert application.task_manager._task_factory is not None  # noqa: SLF001

    def test_factory_requires_startup(self, application: Application) -> None:
        """Without the HTTP session created at startup the factory refuses."""
        with pytest.raises(RuntimeError, match="not started"):
            application._create_task(23058)  # noqa: SLF001

    async def test_factory_builds_wired_task(self, application: Application) -> None:
        """Global settings flow into the assembled component graph."""
        settings = application.settings_manager.settings
        settings.bili_api.base_api_urls = ["https://api.example.com"]
        settings.header.cookie = "SESSDATA=abc"
        settings.header.user_agent = "birec-test-ua"

        await application.startup()
        try:
            task = application._create_task(23058)  # noqa: SLF001
        finally:
            await application.shutdown()

        assert task.room_id == 23058
        assert task.live.base_api_urls == ["https://api.example.com"]
        assert task.live.cookie == "SESSDATA=abc"
        assert task.live.user_agent == "birec-test-ua"
        assert task.monitor is not None
        assert task.recorder.room_id == 23058
        assert task.monitor_enabled
        assert task.recorder_enabled

    async def test_task_level_options_override_globals(
        self, application: Application
    ) -> None:
        """A configured task entry overrides the matching global options."""
        settings = application.settings_manager.settings
        settings.header.cookie = "global"
        settings.postprocessing.remux_to_mp4 = True
        settings.tasks = [
            TaskSettings(
                room_id=23058,
                enable_monitor=False,
                enable_recorder=False,
                header=HeaderOptions(cookie="task-level"),
                recorder=RecorderOptions(save_cover=False),
                postprocessing=PostprocessingOptions(remux_to_mp4=False),
            )
        ]

        await application.startup()
        try:
            task = application._create_task(23058)  # noqa: SLF001
        finally:
            await application.shutdown()

        assert task.live.cookie == "task-level"
        assert not task.monitor_enabled
        assert not task.recorder_enabled
        assert not task.postprocessor._remux_enabled  # noqa: SLF001

    async def test_unconfigured_room_uses_globals(
        self, application: Application
    ) -> None:
        """A room without a task entry falls back to the global settings."""
        settings = application.settings_manager.settings
        settings.header.cookie = "global"
        settings.tasks = [TaskSettings(room_id=999)]

        await application.startup()
        try:
            task = application._create_task(23058)  # noqa: SLF001
        finally:
            await application.shutdown()

        assert task.live.cookie == "global"
        assert task.monitor_enabled


class TestSessionLifecycle:
    async def test_session_created_and_closed(self, application: Application) -> None:
        """The shared aiohttp session lives exactly as long as the app runs."""
        assert application._session is None  # noqa: SLF001
        await application.startup()
        session = application._session  # noqa: SLF001
        assert session is not None
        assert not session.closed

        await application.shutdown()
        assert application._session is None  # noqa: SLF001
        assert session.closed
