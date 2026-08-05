"""Application assembly: lifecycle management and component wiring."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import NamedTuple

import aiohttp
from fastapi import FastAPI

from birec.bili.api import AppApi
from birec.bili.danmaku_client import DanmakuClient
from birec.bili.live import Live
from birec.bili.live_monitor import LiveMonitor
from birec.core.cover_downloader import CoverDownloader
from birec.core.danmaku_receiver import DanmakuReceiver
from birec.core.path_provider import PathProvider
from birec.core.raw_danmaku_receiver import RawDanmakuReceiver
from birec.core.recorder import Recorder
from birec.event import EventCenter
from birec.exception import ExceptionCenter
from birec.logging import configure_logger
from birec.postprocess.danmaku_to_ass import DanmakuToAssConfig
from birec.postprocess.postprocessor import Postprocessor
from birec.setting.env import EnvSettings
from birec.setting.models import Settings, TaskSettings
from birec.setting.setting_manager import SettingsManager
from birec.space import SpaceInfo, SpaceMonitor, SpaceReclaimer
from birec.task import RecordTask, RecordTaskManager
from birec.web import create_app

__all__ = ("create_application", "Application")

logger = logging.getLogger(__name__)


def _pick[T](override: T | None, fallback: T) -> T:
    """Task-level override wins; ``None`` falls back to the global setting."""
    return fallback if override is None else override


class _PostprocessingChoice(NamedTuple):
    """The post-processing switches resolved for one room."""

    remux_enabled: bool
    inject_metadata_enabled: bool
    danmaku_to_ass_enabled: bool
    danmaku_config: DanmakuToAssConfig


class Application:
    """Application container holding all components.

    Wires the configuration manager and the event/exception buses. The
    settings manager is loaded eagerly so it is available as soon as the
    application is assembled; ``startup``/``shutdown`` manage runtime state
    and persist settings back to disk.
    """

    def __init__(
        self,
        config_path: Path,
        output_dir: Path,
        log_dir: Path,
    ) -> None:
        self.config_path = config_path
        self.output_dir = output_dir
        self.log_dir = log_dir
        self._started = False
        env = EnvSettings.model_construct(
            config=str(config_path),
            out_dir=str(output_dir),
            log_dir=str(log_dir),
        )
        self._settings_manager = SettingsManager.load_with_env(env)
        self._session: aiohttp.ClientSession | None = None
        self._bili_api: AppApi | None = None
        space = self._settings_manager.settings.space
        self._space_reclaimer = SpaceReclaimer([output_dir])
        self._space_monitor = SpaceMonitor(
            output_dir,
            threshold=space.space_threshold,
            check_interval=space.check_interval,
            on_space_low=self._on_space_low,
        )
        self._task_manager = RecordTaskManager(
            self._create_task,
            on_task_added=self._register_task_settings,
            on_task_removed=self._forget_task_settings,
            space_monitor=self._space_monitor,
            space_reclaimer=self._space_reclaimer,
        )

    def _on_space_low(self, info: SpaceInfo) -> None:
        """React to the disk filling up under the recordings directory.

        The warning always goes out, because a recording that runs out of room
        fails in a way the user can do nothing about after the fact. Deleting
        their recordings to make room is another matter, so that only happens
        when they asked for it.
        """
        logger.warning(
            "Low disk space at %s: %.1f GiB free of %.1f GiB",
            info.path,
            info.free / 1024**3,
            info.total / 1024**3,
        )
        if not self._settings_manager.settings.space.recycle_records:
            return
        target = self._settings_manager.settings.space.space_threshold * 2
        reclaimed = self._space_reclaimer.reclaim(target)
        if reclaimed:
            logger.info("Reclaimed %.1f GiB of old recordings", reclaimed / 1024**3)
        else:
            logger.warning(
                "Nothing was old enough to reclaim; the disk is still nearly full"
            )

    def _apply_logging_config(self) -> None:
        """Apply the logging settings from the settings manager.

        Exception isolation: a failure here (permissions, bad path, etc.) must
        not prevent the application from starting. The user still gets console
        output at the default level; only the file sink is lost.
        """
        log_settings = self._settings_manager.settings.logging
        log_dir = os.path.expanduser(log_settings.log_dir)
        try:
            configure_logger(
                log_dir,
                console_log_level=log_settings.console_log_level,
                backup_count=log_settings.backup_count,
            )
        except Exception:
            logger.exception(
                "Failed to configure file logging to %s; "
                "continuing with console output only",
                log_dir,
            )

    @property
    def is_started(self) -> bool:
        return self._started

    @property
    def space_monitor(self) -> SpaceMonitor:
        return self._space_monitor

    @property
    def space_reclaimer(self) -> SpaceReclaimer:
        return self._space_reclaimer

    @property
    def settings_manager(self) -> SettingsManager:
        return self._settings_manager

    @property
    def event_center(self) -> EventCenter:
        return EventCenter.get_instance()

    @property
    def exception_center(self) -> ExceptionCenter:
        return ExceptionCenter.get_instance()

    @property
    def task_manager(self) -> RecordTaskManager:
        return self._task_manager

    @property
    def bili_api(self) -> AppApi:
        """The app-signed API client backing TV QR code login (§7.3).

        Raises:
            RuntimeError: If called before ``startup`` created the HTTP session.
        """
        if self._bili_api is None:
            raise RuntimeError("Application not started: no HTTP session")
        return self._bili_api

    async def startup(self) -> None:
        """Initialize application components."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._apply_logging_config()
        self._session = aiohttp.ClientSession()
        self._bili_api = self._create_bili_api(self._session)
        await self._task_manager.start()
        await self._restore_configured_tasks()
        self._started = True
        logger.info("Application started (output=%s)", self.output_dir)

    def _create_bili_api(self, session: aiohttp.ClientSession) -> AppApi:
        """The login client shares the configured cookie and API domains."""
        settings = self._settings_manager.settings
        api = AppApi(session, {"Cookie": settings.header.cookie})
        api.base_api_urls = list(settings.bili_api.base_api_urls)
        api.base_live_api_urls = list(settings.bili_api.base_live_api_urls)
        api.base_play_info_api_urls = list(settings.bili_api.base_play_info_api_urls)
        return api

    async def _restore_configured_tasks(self) -> None:
        """Recreate the tasks recorded in the config file (§5.2)."""
        room_ids = [task.room_id for task in self._settings_manager.settings.tasks]
        if room_ids:
            await self._task_manager.load_tasks(room_ids)

    # ── task settings registry (§5.2) ───────────────────────────────

    def _register_task_settings(self, room_id: int, auto_enable: bool) -> bool:
        """Put a room in the config before its task is built.

        Returns:
            Whether a new entry was created (an already configured room keeps
            its overrides, and must not be dropped if setup then fails).
        """
        created = not self._settings_manager.has_task_settings(room_id)
        self._settings_manager.add_task_settings(
            room_id, enable_monitor=auto_enable, enable_recorder=auto_enable
        )
        if created:
            self._settings_manager.dump()
        return created

    def _forget_task_settings(self, room_id: int) -> None:
        """Drop a removed room from the config so it is not restored again."""
        self._settings_manager.remove_task_settings(room_id)
        self._settings_manager.dump()

    async def shutdown(self) -> None:
        """Persist settings and release application components."""
        await self._task_manager.stop()
        if self._session is not None:
            await self._session.close()
            self._session = None
        self._bili_api = None
        self._settings_manager.dump()
        self._started = False
        logger.info("Application stopped")

    # ── task factory (§5.10) ────────────────────────────────────────

    def _create_task(self, room_id: int) -> RecordTask:
        """Assemble a fully wired ``RecordTask`` for a room.

        Injected into ``RecordTaskManager`` so adding a task over the API
        builds the real component graph (§3.2). Settings are resolved per task:
        a task-level option overrides the matching global one, ``None`` falls
        back to the global value.

        Raises:
            RuntimeError: If called before ``startup`` created the HTTP session.
        """
        if self._session is None:
            raise RuntimeError("Application not started: no HTTP session")

        settings = self._settings_manager.settings
        task = self._task_for(settings, room_id)
        user_agent = _pick(
            task.header.user_agent if task else None, settings.header.user_agent
        )
        cookie = _pick(task.header.cookie if task else None, settings.header.cookie)

        live = Live(room_id, session=self._session)
        live.user_agent = user_agent
        live.cookie = cookie
        live.base_api_urls = list(settings.bili_api.base_api_urls)
        live.base_live_api_urls = list(settings.bili_api.base_live_api_urls)
        live.base_play_info_api_urls = list(settings.bili_api.base_play_info_api_urls)

        danmaku_client = DanmakuClient(
            room_id, session=self._session, cookie=cookie, user_agent=user_agent
        )
        monitor = LiveMonitor(live)
        path_provider = PathProvider(
            settings.output.out_dir,
            _pick(
                task.output.path_template if task else None,
                settings.output.path_template,
            ),
        )
        save_cover = _pick(
            task.recorder.save_cover if task else None, settings.recorder.save_cover
        )
        # The receivers are the danmaku client's listeners: the client only
        # broadcasts, so without this registration nothing would ever reach the
        # dumpers and the .xml/.jsonl files would stay empty (§3.3).
        # The receiver also forwards the room-state commands (LIVE/PREPARING/
        # ROOM_CHANGE) to the monitor — the instant begin/end channel. The
        # periodic check only backs it up; on its own it would learn about a
        # transition a whole check interval late (#27).
        # The receiver additionally schedules a state repair whenever the
        # danmaku client (re)connects, so a status change missed during the
        # disconnect window is caught the moment the WebSocket comes back
        # rather than waiting for the next periodic poll (#28).
        danmaku_receiver = DanmakuReceiver(
            live_command_handler=monitor.handle_command,
            on_reconnect=monitor.repair_state_on_reconnect,
        )
        danmaku_client.add_listener(danmaku_receiver)
        save_raw = _pick(
            task.danmaku.save_raw_danmaku if task else None,
            settings.danmaku.save_raw_danmaku,
        )
        raw_danmaku_receiver: RawDanmakuReceiver | None = None
        if save_raw:
            raw_danmaku_receiver = RawDanmakuReceiver()
            danmaku_client.add_listener(raw_danmaku_receiver)
        recorder = Recorder(
            room_id,
            live,
            monitor,
            self._session,
            path_provider,
            danmaku_receiver=danmaku_receiver,
            raw_danmaku_receiver=raw_danmaku_receiver,
            cover_downloader=CoverDownloader(self._session) if save_cover else None,
        )

        choice = self._postprocessing_for(settings, task)
        postprocessor = Postprocessor(
            remux_enabled=choice.remux_enabled,
            inject_metadata_enabled=choice.inject_metadata_enabled,
            danmaku_to_ass_enabled=choice.danmaku_to_ass_enabled,
            danmaku_config=choice.danmaku_config,
        )

        return RecordTask(
            room_id,
            live,
            danmaku_client,
            monitor,
            recorder,
            postprocessor,
            enable_monitor=task.enable_monitor if task else True,
            enable_recorder=task.enable_recorder if task else True,
        )

    def refresh_postprocessing_options(self) -> None:
        """Push the current post-processing settings onto every live task.

        The switches are resolved per room the same way ``_create_task`` does,
        so a task-level override still wins over the global value.
        """
        settings = self._settings_manager.settings
        for task in self._task_manager.get_all_tasks():
            choice = self._postprocessing_for(
                settings, self._task_for(settings, task.room_id)
            )
            task.update_postprocessing(
                remux_enabled=choice.remux_enabled,
                inject_metadata_enabled=choice.inject_metadata_enabled,
                danmaku_to_ass_enabled=choice.danmaku_to_ass_enabled,
                danmaku_config=choice.danmaku_config,
            )

    def refresh_logging(self) -> None:
        """Re-apply logging settings after a configuration change.

        ``configure_logger`` is idempotent: unchanged parameters are skipped,
        so calling this on every settings PATCH is cheap.
        """
        self._apply_logging_config()

    @staticmethod
    def _postprocessing_for(
        settings: Settings, task: TaskSettings | None
    ) -> _PostprocessingChoice:
        """Resolve the post-processing switches for a room."""
        post = settings.postprocessing
        overrides = task.postprocessing if task else None
        return _PostprocessingChoice(
            remux_enabled=_pick(
                overrides.remux_to_mp4 if overrides else None, post.remux_to_mp4
            ),
            inject_metadata_enabled=_pick(
                overrides.inject_extra_metadata if overrides else None,
                post.inject_extra_metadata,
            ),
            danmaku_to_ass_enabled=_pick(
                overrides.danmaku_to_ass if overrides else None, post.danmaku_to_ass
            ),
            danmaku_config=DanmakuToAssConfig(
                font_size=_pick(
                    overrides.ass_font_size if overrides else None, post.ass_font_size
                ),
                sc_font_size=_pick(
                    overrides.ass_sc_font_size if overrides else None,
                    post.ass_sc_font_size,
                ),
                resolution_x=_pick(
                    overrides.ass_resolution_x if overrides else None,
                    post.ass_resolution_x,
                ),
                resolution_y=_pick(
                    overrides.ass_resolution_y if overrides else None,
                    post.ass_resolution_y,
                ),
            ),
        )

    @staticmethod
    def _task_for(settings: Settings, room_id: int) -> TaskSettings | None:
        """The configured task entry for a room, if the user pre-configured one."""
        return next((t for t in settings.tasks if t.room_id == room_id), None)


def create_application(
    config_path: Path = Path("config.toml"),
    output_dir: Path = Path("./recordings"),
    log_dir: Path = Path("./logs"),
) -> FastAPI:
    """Create and configure the full application.

    Args:
        config_path: Path to config file.
        output_dir: Recording output directory.
        log_dir: Log file directory.

    Returns:
        Configured FastAPI application with lifecycle hooks.
    """
    application = Application(config_path, output_dir, log_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await application.startup()
        # Only available once startup created the HTTP session it needs.
        app.state.bili_api = application.bili_api
        yield
        await application.shutdown()

    app = create_app()
    app.router.lifespan_context = lifespan
    app.state.application = application
    app.state.settings_manager = application.settings_manager
    app.state.event_center = application.event_center
    app.state.exception_center = application.exception_center
    app.state.task_manager = application.task_manager

    return app
