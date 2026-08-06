"""Compose orchestration for the publish-artifact smoke test (#19 §4).

Brings up the image under test against the containerised fake Bilibili in a
throwaway project directory, and tears everything down afterwards — logs
first, so a failure leaves its evidence behind.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_PROJECT = "birec-smoke"
_UP_TIMEOUT = 120


@dataclass(frozen=True)
class SmokeEnv:
    birec_url: str
    fake_url: str
    rec_dir: Path
    state_dir: Path
    logs_dir: Path

    def compose(self, *args: str, env: dict[str, str] | None = None) -> str:
        """Run a docker compose command against this smoke stack."""
        cmd = [
            "docker",
            "compose",
            "-p",
            _PROJECT,
            "-f",
            str(_HERE / "compose.yaml"),
            *args,
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            env=_compose_env(self, env),
            timeout=_UP_TIMEOUT,
        )
        return result.stdout


def _compose_env(env: SmokeEnv, extra: dict[str, str] | None = None) -> dict[str, str]:
    composed = {
        **os.environ,
        "SMOKE_REC_DIR": str(env.rec_dir),
        "SMOKE_STATE_DIR": str(env.state_dir),
    }
    if extra:
        composed.update(extra)
    return composed


@pytest.fixture(scope="session")
def smoke_env(tmp_path_factory: pytest.TempPathFactory) -> SmokeEnv:
    if shutil.which("docker") is None:
        pytest.skip("docker is not available on this host")

    root = tmp_path_factory.mktemp("smoke")
    rec_dir = root / "rec"
    state_dir = root / "state"
    logs_dir = root / "logs"
    rec_dir.mkdir()
    state_dir.mkdir()
    logs_dir.mkdir()
    shutil.copy(_HERE / "settings.toml", state_dir / "settings.toml")

    env = SmokeEnv(
        birec_url="http://127.0.0.1:2233",
        fake_url="http://127.0.0.1:18080",
        rec_dir=rec_dir,
        state_dir=state_dir,
        logs_dir=logs_dir,
    )
    env.compose("up", "-d", "--wait")
    yield env

    # Evidence before teardown: container logs go to the temp dir, and pytest
    # prints its path when the test failed.
    for service in ("birec", "fake-bili"):
        try:
            logs = env.compose("logs", "--no-color", service)
        except subprocess.CalledProcessError:
            logs = "<failed to collect logs>"
        (logs_dir / f"{service}.log").write_text(logs, encoding="utf-8")
    env.compose("down", "-v", "--remove-orphans")
