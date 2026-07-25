"""Tests for birec.bili.helpers."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from birec.bili.exceptions import ApiRequestError
from birec.bili.helpers import (
    build_cookie_str,
    ensure_room_id,
    extract_codecs,
    extract_formats,
    extract_streams,
    get_quality_name,
)
from birec.exception import NotFoundError


class TestGetQualityName:
    def test_known_values(self) -> None:
        assert get_quality_name(20000) == "4K"
        assert get_quality_name(10000) == "原画"
        assert get_quality_name(401) == "蓝光(杜比)"
        assert get_quality_name(400) == "蓝光"
        assert get_quality_name(250) == "超清"
        assert get_quality_name(150) == "高清"
        assert get_quality_name(80) == "流畅"

    def test_unknown_returns_empty(self) -> None:
        assert get_quality_name(999) == ""  # type: ignore[arg-type]


class TestBuildCookieStr:
    def test_joins_cookies(self) -> None:
        info = {
            "cookies": [
                {"name": "SESSDATA", "value": "abc123"},
                {"name": "bili_jct", "value": "xyz"},
            ]
        }
        assert build_cookie_str(info) == "SESSDATA=abc123; bili_jct=xyz"

    def test_empty_cookies(self) -> None:
        assert build_cookie_str({"cookies": []}) == ""
        assert build_cookie_str({}) == ""


class TestEnsureRoomId:
    async def test_returns_real_room_id(self) -> None:
        with patch(
            "birec.bili.helpers.room_init",
            new=AsyncMock(return_value={"room_id": 12345}),
        ):
            assert await ensure_room_id(123) == 12345

    async def test_60004_raises_not_found(self) -> None:
        with (
            patch(
                "birec.bili.helpers.room_init",
                new=AsyncMock(side_effect=ApiRequestError(60004, "not found")),
            ),
            pytest.raises(NotFoundError, match="not existed"),
        ):
            await ensure_room_id(999)

    async def test_other_error_propagates(self) -> None:
        with (
            patch(
                "birec.bili.helpers.room_init",
                new=AsyncMock(side_effect=ApiRequestError(500, "server error")),
            ),
            pytest.raises(ApiRequestError),
        ):
            await ensure_room_id(1)


class TestExtractStreams:
    def test_extracts_from_play_infos(self) -> None:
        play_infos: list[dict[str, Any]] = [
            {
                "playurl_info": {
                    "playurl": {
                        "stream": [
                            {"protocol_name": "http_stream"},
                            {"protocol_name": "http_hls"},
                        ]
                    }
                }
            }
        ]
        streams = extract_streams(play_infos)
        assert len(streams) == 2

    def test_empty_play_infos(self) -> None:
        assert extract_streams([]) == []

    def test_missing_keys(self) -> None:
        assert extract_streams([{"foo": "bar"}]) == []


class TestExtractFormats:
    def test_filters_by_format_name(self) -> None:
        streams = [
            {
                "format": [
                    {"format_name": "flv"},
                    {"format_name": "ts"},
                ]
            },
            {
                "format": [
                    {"format_name": "fmp4"},
                ]
            },
        ]
        result = extract_formats(streams, "flv")
        assert len(result) == 1
        assert result[0]["format_name"] == "flv"

    def test_no_match(self) -> None:
        streams = [{"format": [{"format_name": "ts"}]}]
        assert extract_formats(streams, "flv") == []


class TestExtractCodecs:
    def test_filters_by_codec_name(self) -> None:
        formats = [
            {
                "codec": [
                    {"codec_name": "avc"},
                    {"codec_name": "hevc"},
                ]
            }
        ]
        result = extract_codecs(formats, "avc")
        assert len(result) == 1
        assert result[0]["codec_name"] == "avc"

    def test_no_match(self) -> None:
        formats = [{"codec": [{"codec_name": "hevc"}]}]
        assert extract_codecs(formats, "avc") == []
