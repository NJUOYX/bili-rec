"""Unit tests for the application-level task factory wiring (§5.10)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from birec.application import Application, create_application
from birec.setting.models import (
    HeaderOptions,
    PostprocessingOptions,
    RecorderOptions,
    TaskSettings,
)
from birec.task import RecordTask


def _stub_factory(room_id: int) -> RecordTask:
    """A task that needs no network, for exercising the manager's bookkeeping."""
    task = MagicMock(spec=RecordTask)
    task.room_id = room_id
    task.setup = AsyncMock()
    task.destroy = AsyncMock()
    return task


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

    async def test_factory_wires_danmaku_pipeline(
        self, application: Application
    ) -> None:
        """The receiver must be both a client listener and the dumper's source.

        Miss either half and recording silently produces an empty .xml file.
        """
        await application.startup()
        try:
            task = application._create_task(23058)  # noqa: SLF001
        finally:
            await application.shutdown()

        receiver = task.recorder.stream_recorder._danmaku_receiver  # noqa: SLF001
        assert receiver is not None
        assert receiver in task._danmaku_client._listeners  # noqa: SLF001

    async def test_factory_forwards_live_commands_to_the_monitor(
        self, application: Application
    ) -> None:
        """Room-state commands off the socket must reach the monitor (#27).

        Without this wire the monitor learns about a broadcast beginning or
        ending from the periodic check alone — a whole check interval late.
        """
        await application.startup()
        try:
            task = application._create_task(23058)  # noqa: SLF001
        finally:
            await application.shutdown()

        receiver = task.recorder.stream_recorder._danmaku_receiver  # noqa: SLF001
        assert receiver is not None
        handler = receiver._live_command_handler  # noqa: SLF001
        assert handler == task.monitor.handle_command

    async def test_raw_danmaku_receiver_follows_the_setting(
        self, application: Application
    ) -> None:
        """Raw JSONL output is opt-in, so the receiver only exists when asked."""
        await application.startup()
        try:
            off = application._create_task(23058)  # noqa: SLF001
            application.settings_manager.settings.danmaku.save_raw_danmaku = True
            on = application._create_task(23059)  # noqa: SLF001
        finally:
            await application.shutdown()

        assert off.recorder.stream_recorder._raw_danmaku_receiver is None  # noqa: SLF001
        raw = on.recorder.stream_recorder._raw_danmaku_receiver  # noqa: SLF001
        assert raw is not None
        assert raw in on._danmaku_client._listeners  # noqa: SLF001


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


class TestBiliApi:
    """The login endpoints need an app-signed client on the running app (§7.3)."""

    def test_unavailable_before_startup(self, application: Application) -> None:
        with pytest.raises(RuntimeError, match="not started"):
            _ = application.bili_api

    async def test_created_with_the_configured_cookie_and_domains(
        self, application: Application
    ) -> None:
        settings = application.settings_manager.settings
        settings.header.cookie = "SESSDATA=abc"
        settings.bili_api.base_api_urls = ["https://api.example.com"]

        await application.startup()
        try:
            api = application.bili_api
            assert api.headers["Cookie"] == "SESSDATA=abc"
            assert api.base_api_urls == ["https://api.example.com"]
        finally:
            await application.shutdown()

    async def test_exposed_on_the_app_state(self, tmp_path: Path) -> None:
        """``/qrcode/login`` reads it off the app state, not the Application."""
        app = create_application(
            config_path=tmp_path / "config.toml",
            output_dir=tmp_path / "recordings",
            log_dir=tmp_path / "logs",
        )
        with TestClient(app):
            assert app.state.bili_api is app.state.application.bili_api


class TestConfiguredTasks:
    """Tasks live in the config file, so they survive a restart (§5.2)."""

    async def test_added_task_is_written_to_the_config(
        self, application: Application
    ) -> None:
        manager = application.settings_manager
        await application.startup()
        try:
            application.task_manager._task_factory = _stub_factory  # noqa: SLF001
            await application.task_manager.add_task(23058, auto_enable=False)

            configured = manager.find_task_settings(23058)
            assert configured is not None
            assert configured.enable_monitor is False
            assert configured.enable_recorder is False
            # Written through to disk, so a crash does not lose the task.
            assert "23058" in Path(manager.path).read_text(encoding="utf-8")
        finally:
            await application.shutdown()

    async def test_removed_task_is_dropped_from_the_config(
        self, application: Application
    ) -> None:
        manager = application.settings_manager
        await application.startup()
        try:
            application.task_manager._task_factory = _stub_factory  # noqa: SLF001
            await application.task_manager.add_task(23058)
            await application.task_manager.remove_task(23058)
            assert manager.find_task_settings(23058) is None
        finally:
            await application.shutdown()

    async def test_shutdown_keeps_the_configured_tasks(
        self, application: Application
    ) -> None:
        await application.startup()
        application.task_manager._task_factory = _stub_factory  # noqa: SLF001
        await application.task_manager.add_task(23058)
        await application.shutdown()
        assert application.settings_manager.has_task_settings(23058)

    async def test_startup_restores_the_configured_tasks(
        self, application: Application
    ) -> None:
        application.settings_manager.settings.tasks = [
            TaskSettings(room_id=23058),
            TaskSettings(room_id=100),
        ]
        application.task_manager._task_factory = _stub_factory  # noqa: SLF001

        await application.startup()
        try:
            assert sorted(
                task.room_id for task in application.task_manager.get_all_tasks()
            ) == [100, 23058]
        finally:
            await application.shutdown()
