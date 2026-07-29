"""Application assembly: lifecycle management and component wiring."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiohttp
from fastapi import FastAPI

from birec.bili.danmaku_client import DanmakuClient
from birec.bili.live import Live
from birec.bili.live_monitor import LiveMonitor
from birec.core.cover_downloader import CoverDownloader
from birec.core.path_provider import PathProvider
from birec.core.recorder import Recorder
from birec.event import EventCenter
from birec.exception import ExceptionCenter
from birec.postprocess.danmaku_to_ass import DanmakuToAssConfig
from birec.postprocess.postprocessor import Postprocessor
from birec.setting.env import EnvSettings
from birec.setting.models import Settings, TaskSettings
from birec.setting.setting_manager import SettingsManager
from birec.task import RecordTask, RecordTaskManager
from birec.web import create_app

__all__ = ("create_application", "Application")

logger = logging.getLogger(__name__)


def _pick[T](override: T | None, fallback: T) -> T:
    """Task-level override wins; ``None`` falls back to the global setting."""
    return fallback if override is None else override


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
        self._task_manager = RecordTaskManager(self._create_task)

    @property
    def is_started(self) -> bool:
        return self._started

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

    async def startup(self) -> None:
        """Initialize application components."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._session = aiohttp.ClientSession()
        await self._task_manager.start()
        self._started = True
        logger.info("Application started (output=%s)", self.output_dir)

    async def shutdown(self) -> None:
        """Persist settings and release application components."""
        await self._task_manager.stop()
        if self._session is not None:
            await self._session.close()
            self._session = None
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
        recorder = Recorder(
            room_id,
            live,
            monitor,
            self._session,
            path_provider,
            cover_downloader=CoverDownloader(self._session) if save_cover else None,
        )

        post = settings.postprocessing
        overrides = task.postprocessing if task else None
        postprocessor = Postprocessor(
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
