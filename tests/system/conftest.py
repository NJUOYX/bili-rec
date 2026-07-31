"""Shared fixtures for system tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from httpx import ASGITransport, AsyncClient

from birec.application import create_application
from birec.event import EventCenter

from .fake_bili_server import FakeBiliServer
from .harness import ROOM_ID

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator
    from pathlib import Path

    from fastapi import FastAPI


@pytest.fixture
def app(tmp_path: Path) -> FastAPI:
    """Full application instance backed by temporary directories."""
    return create_application(
        config_path=tmp_path / "config.toml",
        output_dir=tmp_path / "recordings",
        log_dir=tmp_path / "logs",
    )


@pytest.fixture
async def async_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Async HTTP client driving the ASGI app without network I/O."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture()
async def fake_server() -> AsyncIterator[FakeBiliServer]:
    """A Bilibili the tests own, on a port of its own choosing."""
    server = FakeBiliServer(room_id=ROOM_ID)
    await server.start()
    try:
        yield server
    finally:
        await server.stop()


@pytest.fixture()
def out_dir(tmp_path: Path) -> Path:
    return tmp_path / "recordings"


@pytest.fixture()
async def client(
    tmp_path: Path, out_dir: Path, fake_server: FakeBiliServer
) -> AsyncIterator[AsyncClient]:
    """A started application whose Bilibili endpoints are the fake server."""
    app = create_application(
        config_path=tmp_path / "config.toml",
        output_dir=out_dir,
        log_dir=tmp_path / "logs",
    )
    settings = app.state.settings_manager.settings
    settings.bili_api.base_api_urls = [fake_server.base_url]
    settings.bili_api.base_live_api_urls = [fake_server.base_url]
    settings.bili_api.base_play_info_api_urls = [fake_server.base_url]

    application = app.state.application
    await application.startup()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            c.app = app  # type: ignore[attr-defined]
            yield c
    finally:
        await application.shutdown()


@pytest.fixture()
def events() -> Iterator[list[Any]]:
    """Collect everything published on the event bus during a test.

    The bus-to-WebSocket hop is covered by the unit tests, which drive a real
    client against a submitted event; what is missing, and what this captures,
    is whether a real recording publishes anything at all.
    """
    collected: list[Any] = []
    subscription = EventCenter.get_instance().events.subscribe(collected.append)
    try:
        yield collected
    finally:
        subscription.dispose()


@pytest.fixture()
def fast_reconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shrink the recorder's reconnect backoff so a test can watch it happen.

    The production delays are measured in seconds and the retry budget is ten
    attempts, which is right for a CDN having a bad minute and hopeless for a
    test. Only the waiting is shortened; the logic under test is untouched.
    """
    monkeypatch.setattr(
        "birec.core.flv_stream_recorder_impl._RECONNECT_BASE_DELAY", 0.02
    )
    monkeypatch.setattr(
        "birec.core.flv_stream_recorder_impl._RECONNECT_MAX_DELAY", 0.05
    )


@pytest.fixture()
def fast_danmaku_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shrink the broadcast client's backoff and heartbeat interval likewise."""
    monkeypatch.setattr("birec.bili.danmaku_client._RETRY_BACKOFF_BASE", 0.02)
    monkeypatch.setattr("birec.bili.danmaku_client._RETRY_BACKOFF_MAX", 0.05)
    monkeypatch.setattr("birec.bili.danmaku_client._HEARTBEAT_INTERVAL", 0.1)
