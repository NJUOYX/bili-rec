"""Discovery helper for locating a currently-live Bilibili room.

Real verification tests need a room that is actually streaming. Resolution
order:

1. ``BIREC_TEST_ROOM_ID`` environment variable (a fixed 24/7 room the operator
   trusts to be live), if set and numeric.
2. Public recommendation endpoints for currently-online rooms, returning the
   first room id they advertise. A ``buvid3`` cookie is warmed up first from the
   home page because the live listing endpoints are risk-controlled (``-352``)
   for cold, cookie-less clients.

Returns ``None`` when neither source yields a usable room id, letting callers
skip gracefully instead of failing.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from typing import Any

import aiohttp

from birec.bili.api import BASE_HEADERS

__all__ = ("discover_live_room",)

_HOME_URL = "https://www.bilibili.com/"

# Anonymous-accessible recommendation lists. Both expose ``recommend_room_list``
# under ``data`` with items carrying a ``roomid``. ``second/getList`` (sorted by
# online count) is intentionally avoided: it now returns ``-352`` for anonymous
# clients even with WBI signing and a warmed-up buvid.
_REC_URLS = (
    "https://api.live.bilibili.com/xlive/web-interface/v1/webMain/getMoreRecList",
    "https://api.live.bilibili.com/xlive/web-interface/v1/index/getList",
)
_REC_PARAMS = {"platform": "web", "page": 1}
_TIMEOUT = aiohttp.ClientTimeout(total=10)


def _room_id_from_env() -> int | None:
    raw = os.environ.get("BIREC_TEST_ROOM_ID")
    if not raw:
        return None
    try:
        room_id = int(raw)
    except ValueError:
        return None
    return room_id if room_id > 0 else None


def _iter_room_ids(payload: Any) -> Iterable[int]:
    if not isinstance(payload, dict) or payload.get("code") != 0:
        return
    data = payload.get("data") or {}
    for key in ("recommend_room_list", "room_list", "list"):
        rooms = data.get(key)
        if not isinstance(rooms, list):
            continue
        for room in rooms:
            if not isinstance(room, dict):
                continue
            room_id = room.get("roomid") or room.get("room_id")
            if isinstance(room_id, int) and room_id > 0:
                yield room_id


async def _warm_up_buvid(session: aiohttp.ClientSession) -> None:
    try:
        async with session.get(_HOME_URL, headers=BASE_HEADERS, timeout=_TIMEOUT):
            pass
    except Exception:
        pass


async def discover_live_room(session: aiohttp.ClientSession) -> int | None:
    """Return a currently-live room id, or ``None`` if none can be found."""
    env_room = _room_id_from_env()
    if env_room is not None:
        return env_room

    await _warm_up_buvid(session)

    for url in _REC_URLS:
        try:
            async with session.get(
                url,
                params=_REC_PARAMS,
                headers=BASE_HEADERS,
                timeout=_TIMEOUT,
            ) as res:
                payload = await res.json()
        except Exception:
            continue
        for room_id in _iter_room_ids(payload):
            return room_id
    return None
