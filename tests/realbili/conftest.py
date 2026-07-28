"""Fixtures and opt-in gating for real Bilibili verification tests.

Every test under ``tests/realbili/`` is skipped unless ``BIREC_REALBILI=1`` is
set, so the suite is inert during the normal quality gate and CI runs even
though the ``realbili`` marker is auto-applied by the root conftest.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import aiohttp
import pytest

from birec.bili.live import Live
from birec.bili.net import get_connector, timeout

from .live_room import discover_live_room

_REALBILI_DIR = Path(__file__).parent


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Skip every real Bilibili test unless explicitly opted in."""
    if os.environ.get("BIREC_REALBILI") == "1":
        return
    skip = pytest.mark.skip(
        reason="real Bilibili tests are opt-in; set BIREC_REALBILI=1 to run them"
    )
    for item in items:
        try:
            Path(item.fspath).relative_to(_REALBILI_DIR)
        except ValueError:
            continue
        item.add_marker(skip)


@pytest.fixture
def bili_cookie() -> str:
    """Optional login cookie supplied via ``BIREC_BILI_COOKIE``."""
    return os.environ.get("BIREC_BILI_COOKIE", "")


@pytest.fixture
async def bili_session() -> AsyncIterator[aiohttp.ClientSession]:
    """A shared aiohttp session backed by the birec connector."""
    session = aiohttp.ClientSession(
        connector=get_connector(),
        connector_owner=False,
        timeout=timeout,
    )
    try:
        yield session
    finally:
        await session.close()


@pytest.fixture
async def live_room_id(bili_session: aiohttp.ClientSession) -> int:
    """A currently-live room id, or skip the test when none can be found."""
    room_id = await discover_live_room(bili_session)
    if room_id is None:
        pytest.skip("no live Bilibili room available for verification")
    return room_id


@pytest.fixture
async def live(
    bili_session: aiohttp.ClientSession,
    bili_cookie: str,
    live_room_id: int,
) -> Live:
    """A refreshed ``Live`` bound to a currently-live room."""
    obj = Live(live_room_id, session=bili_session)
    if bili_cookie:
        obj.cookie = bili_cookie
    await obj.refresh()
    return obj
