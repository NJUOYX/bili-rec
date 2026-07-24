"""Shared Bilibili adapter type aliases."""

from __future__ import annotations

from typing import Any, Literal

__all__ = (
    "ApiPlatform",
    "QualityNumber",
    "StreamCodec",
    "StreamFormat",
    "JsonResponse",
    "ResponseData",
    "Danmaku",
)

ApiPlatform = Literal["web", "android"]

QualityNumber = Literal[
    20000,  # 4K
    10000,  # 原画
    401,  # 蓝光(杜比)
    400,  # 蓝光
    250,  # 超清
    150,  # 高清
    80,  # 流畅
]

StreamFormat = Literal["flv", "ts", "fmp4"]

StreamCodec = Literal["avc", "hevc"]

JsonResponse = dict[str, Any]
ResponseData = dict[str, Any]
Danmaku = dict[str, Any]
