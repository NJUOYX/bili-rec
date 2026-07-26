"""Application assembly: lifecycle management and component wiring."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from birec.event import EventCenter
from birec.exception import ExceptionCenter
from birec.setting.env import EnvSettings
from birec.setting.setting_manager import SettingsManager
from birec.web import create_app

__all__ = ("create_application", "Application")

logger = logging.getLogger(__name__)


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

    async def startup(self) -> None:
        """Initialize application components."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._started = True
        logger.info("Application started (output=%s)", self.output_dir)

    async def shutdown(self) -> None:
        """Persist settings and release application components."""
        self._settings_manager.dump()
        self._started = False
        logger.info("Application stopped")


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

    return app
