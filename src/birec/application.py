"""Application assembly: lifecycle management and component wiring."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from birec.web import create_app

__all__ = ("create_application", "Application")

logger = logging.getLogger(__name__)


class Application:
    """Application container holding all components."""

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

    @property
    def is_started(self) -> bool:
        return self._started

    async def startup(self) -> None:
        """Initialize application components."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._started = True
        logger.info("Application started (output=%s)", self.output_dir)

    async def shutdown(self) -> None:
        """Cleanup application components."""
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

    return app
