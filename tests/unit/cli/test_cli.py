"""Tests for CLI and application modules."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from birec.application import Application, create_application
from birec.cli import app


class TestCli:
    def test_version_flag(self) -> None:
        runner = CliRunner()
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "birec" in result.output

    def test_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "bili-rec" in result.output or "birec" in result.output

    def test_console_script_entry_point_loads(self) -> None:
        from importlib.metadata import entry_points

        scripts = entry_points(group="console_scripts", name="birec")
        entry_point = next(iter(scripts), None)
        assert entry_point is not None, "birec console script is not installed"
        assert entry_point.value == "birec.cli:app"
        assert entry_point.load() is app


class TestApplication:
    @pytest.mark.asyncio
    async def test_startup_shutdown(self, tmp_path) -> None:
        app_instance = Application(
            config_path=tmp_path / "config.toml",
            output_dir=tmp_path / "output",
            log_dir=tmp_path / "logs",
        )
        assert not app_instance.is_started

        await app_instance.startup()
        assert app_instance.is_started
        assert (tmp_path / "output").exists()
        assert (tmp_path / "logs").exists()

        await app_instance.shutdown()
        assert not app_instance.is_started

    def test_create_application(self, tmp_path) -> None:
        fastapi_app = create_application(
            config_path=tmp_path / "config.toml",
            output_dir=tmp_path / "out",
            log_dir=tmp_path / "log",
        )
        assert fastapi_app is not None
        assert hasattr(fastapi_app.state, "application")
