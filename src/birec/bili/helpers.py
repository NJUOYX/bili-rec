"""Bilibili API helper functions: room init, QR login, cookie, quality mapping."""

from __future__ import annotations

from typing import Any

import aiohttp

from ..exception import NotFoundError
from .api import AppApi, WebApi
from .exceptions import ApiRequestError
from .net import get_connector, timeout
from .typing import JsonResponse, QualityNumber, ResponseData, StreamCodec, StreamFormat

__all__ = (
    "room_init",
    "ensure_room_id",
    "get_nav",
    "request_qrcode",
    "poll_qrcode",
    "build_cookie_str",
    "get_quality_name",
    "extract_streams",
    "extract_formats",
    "extract_codecs",
)

QUALITY_MAPPING: dict[int, str] = {
    20000: "4K",
    10000: "原画",
    401: "蓝光(杜比)",
    400: "蓝光",
    250: "超清",
    150: "高清",
    80: "流畅",
}


def _make_session() -> aiohttp.ClientSession:
    return aiohttp.ClientSession(
        connector=get_connector(),
        connector_owner=False,
        raise_for_status=True,
        trust_env=True,
        timeout=timeout,
    )


async def room_init(room_id: int) -> ResponseData:
    async with _make_session() as session:
        api = WebApi(session, room_id=room_id)
        return await api.room_init(room_id)


async def ensure_room_id(room_id: int) -> int:
    """Validate room_id and return the real room id."""
    try:
        result = await room_init(room_id)
    except ApiRequestError as e:
        if e.code == 60004:
            raise NotFoundError(f"the room {room_id} not existed") from e
        raise
    else:
        return int(result["room_id"])


async def get_nav(cookie: str) -> ResponseData:
    async with _make_session() as session:
        headers = {
            "Origin": "https://passport.bilibili.com",
            "Referer": "https://passport.bilibili.com/account/security",
            "Cookie": cookie,
        }
        api = WebApi(session, headers)
        return await api.get_nav()


async def request_qrcode() -> ResponseData:
    async with _make_session() as session:
        api = AppApi(session)
        return await api.request_tv_qrcode()


async def poll_qrcode(auth_code: str) -> JsonResponse:
    async with _make_session() as session:
        api = AppApi(session)
        return await api.poll_tv_qrcode(auth_code)


def build_cookie_str(cookie_info: dict[str, Any]) -> str:
    cookies: list[dict[str, str]] = cookie_info.get("cookies") or []
    return "; ".join(f"{c['name']}={c['value']}" for c in cookies)


def get_quality_name(qn: QualityNumber) -> str:
    return QUALITY_MAPPING.get(qn, "")


def extract_streams(play_infos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract all stream objects from play info responses."""
    streams: list[dict[str, Any]] = []
    for info in play_infos:
        playurl = info.get("playurl_info", {}).get("playurl", {})
        streams.extend(playurl.get("stream", []))
    return streams


def extract_formats(
    streams: list[dict[str, Any]], stream_format: StreamFormat
) -> list[dict[str, Any]]:
    """Filter streams by format name (flv/ts/fmp4)."""
    formats: list[dict[str, Any]] = []
    for stream in streams:
        for fmt in stream.get("format", []):
            if fmt.get("format_name") == stream_format:
                formats.append(fmt)
    return formats


def extract_codecs(
    formats: list[dict[str, Any]], stream_codec: StreamCodec
) -> list[dict[str, Any]]:
    """Filter formats by codec name (avc/hevc)."""
    codecs: list[dict[str, Any]] = []
    for fmt in formats:
        for codec in fmt.get("codec", []):
            if codec.get("codec_name") == stream_codec:
                codecs.append(codec)
    return codecs
