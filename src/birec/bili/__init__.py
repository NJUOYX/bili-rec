"""Bilibili adapter layer: models, API clients, helpers, and shared types."""

from __future__ import annotations

from .api import AppApi, WebApi
from .exceptions import (
    ApiRequestError,
    DanmakuClientAuthError,
    LiveRoomEncrypted,
    LiveRoomHidden,
    LiveRoomLocked,
    NoAlternativeStreamAvailable,
    NoStreamAvailable,
    NoStreamCodecAvailable,
    NoStreamFormatAvailable,
    NoStreamQualityAvailable,
)
from .helpers import (
    build_cookie_str,
    ensure_room_id,
    extract_codecs,
    extract_formats,
    extract_streams,
    get_nav,
    get_quality_name,
    poll_qrcode,
    request_qrcode,
    room_init,
)
from .models import LiveStatus, RoomInfo, UserInfo
from .net import get_connector, timeout
from .typing import (
    ApiPlatform,
    Danmaku,
    JsonResponse,
    QualityNumber,
    ResponseData,
    StreamCodec,
    StreamFormat,
)
from .wbi import build_query, encode_value, extract_key, make_key

__all__ = (
    "ApiPlatform",
    "ApiRequestError",
    "AppApi",
    "Danmaku",
    "DanmakuClientAuthError",
    "JsonResponse",
    "LiveRoomEncrypted",
    "LiveRoomHidden",
    "LiveRoomLocked",
    "LiveStatus",
    "NoAlternativeStreamAvailable",
    "NoStreamAvailable",
    "NoStreamCodecAvailable",
    "NoStreamFormatAvailable",
    "NoStreamQualityAvailable",
    "QualityNumber",
    "ResponseData",
    "RoomInfo",
    "StreamCodec",
    "StreamFormat",
    "UserInfo",
    "WebApi",
    "build_cookie_str",
    "build_query",
    "encode_value",
    "ensure_room_id",
    "extract_codecs",
    "extract_formats",
    "extract_key",
    "extract_streams",
    "get_connector",
    "get_nav",
    "get_quality_name",
    "make_key",
    "poll_qrcode",
    "request_qrcode",
    "room_init",
    "timeout",
)
