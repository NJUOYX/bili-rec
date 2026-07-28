"""Discovery helper for locating a currently-live Bilibili room.

Real verification tests need a room that is actually streaming. Resolution
order:

1. ``BIREC_TEST_ROOM_ID`` environment variable (a fixed 24/7 room the operator
   trusts to be live), if set and numeric.
2. The public "get list" endpoint for currently-online rooms, returning the
   first room id it advertises.

Returns ``None`` when neither source yields a usable room id, letting callers
skip gracefully instead of failing.
"""

from __future__ import annotations

import os

import aiohttp

from birec.bili.api import BASE_HEADERS

__all__ = ("discover_live_room",)

# Public listing of currently-online rooms (no auth / signing required).
_GET_LIST_URL = (
    "https://api.live.bilibili.com/xlive/web-interface/v1/second/getList"
    "?platform=web&sort_type=online&page=1&parent_area_id=1&area_id=0"
)


def _room_id_from_env() -> int | None:
    raw = os.environ.get("BIREC_TEST_ROOM_ID")
    if not raw:
        return None
    try:
        room_id = int(raw)
    except ValueError:
        return None
    return room_id if room_id > 0 else None


async def discover_live_room(session: aiohttp.ClientSession) -> int | None:
    """Return a currently-live room id, or ``None`` if none can be found."""
    env_room = _room_id_from_env()
    if env_room is not None:
        return env_room

    try:
        async with session.get(
            _GET_LIST_URL,
            headers=BASE_HEADERS,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as res:
            payload = await res.json()
    except Exception:
        return None

    if not isinstance(payload, dict) or payload.get("code") != 0:
        return None

    data = payload.get("data") or {}
    rooms = data.get("list") or []
    for room in rooms:
        if not isinstance(room, dict):
            continue
        room_id = room.get("roomid")
        if isinstance(room_id, int) and room_id > 0:
            return room_id
    return None
