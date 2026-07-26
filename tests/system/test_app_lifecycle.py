"""System tests for application lifecycle (lifespan startup/shutdown)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

if TYPE_CHECKING:
    from pathlib import Path

    from fastapi import FastAPI

    from birec.application import Application


class TestApplicationLifespan:
    def test_startup_creates_output_and_log_dirs(
        self, app: FastAPI, tmp_path: Path
    ) -> None:
        output_dir = tmp_path / "recordings"
        log_dir = tmp_path / "logs"
        assert not output_dir.exists()
        assert not log_dir.exists()

        with TestClient(app):
            assert output_dir.is_dir()
            assert log_dir.is_dir()

    def test_is_started_toggles_with_lifespan(self, app: FastAPI) -> None:
        application: Application = app.state.application
        assert not application.is_started

        with TestClient(app):
            assert application.is_started

        assert not application.is_started
