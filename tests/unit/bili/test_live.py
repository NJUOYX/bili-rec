"""Unit tests for birec.bili.live — Live room abstraction."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from birec.bili.exceptions import (
    LiveRoomEncrypted,
    LiveRoomHidden,
    LiveRoomLocked,
    NoAlternativeStreamAvailable,
    NoStreamAvailable,
    NoStreamCodecAvailable,
    NoStreamFormatAvailable,
)
from birec.bili.live import Live
from birec.bili.models import LiveStatus

pytestmark = pytest.mark.unit


def _make_live(room_id: int = 12345) -> Live:
    session = MagicMock()
    live = Live(room_id, session=session, api_platform="web")
    return live


def _play_info_response(
    format_name: str = "flv",
    codec_name: str = "avc",
    current_qn: int = 10000,
    accept_qn: list[int] | None = None,
    host: str = "https://cn-gotcha01.bilivideo.com",
    base_url: str = "/live/room.flv",
    extra: str = "?expires=123",
) -> dict:
    return {
        "playurl_info": {
            "playurl": {
                "stream": [
                    {
                        "format": [
                            {
                                "format_name": format_name,
                                "codec": [
                                    {
                                        "codec_name": codec_name,
                                        "current_qn": current_qn,
                                        "accept_qn": accept_qn or [10000, 250, 150],
                                        "base_url": base_url,
                                        "url_info": [
                                            {"host": host, "extra": extra},
                                        ],
                                    }
                                ],
                            }
                        ]
                    }
                ]
            }
        }
    }


class TestLiveInit:
    async def test_init_sets_room_and_user_info(self) -> None:
        live = _make_live()
        data = {
            "room_info": {
                "uid": 100,
                "room_id": 12345,
                "short_id": 123,
                "area_id": 1,
                "area_name": "网游",
                "parent_area_id": 2,
                "parent_area_name": "游戏",
                "live_status": 1,
                "live_start_time": 1700000000,
                "online": 500,
                "title": "Test Room",
                "cover": "https://example.com/cover.jpg",
                "tags": "tag1",
                "description": "desc",
            },
            "anchor_info": {
                "base_info": {
                    "uname": "TestUser",
                    "gender": "男",
                    "face": "https://example.com/face.jpg",
                }
            },
        }
        with (
            patch.object(live.api, "get_info_by_room", new_callable=AsyncMock) as m,
            patch.object(live.api, "get_room_play_infos", new_callable=AsyncMock) as m2,
        ):
            m.return_value = data
            m2.return_value = [_play_info_response()]
            await live.init()

        assert live.room_info is not None
        assert live.room_info.room_id == 12345
        assert live.user_info is not None
        assert live.user_info.name == "TestUser"
        assert live.has_flv_stream is True

    async def test_init_no_flv_stream(self) -> None:
        live = _make_live()
        data = {
            "room_info": {
                "uid": 100,
                "room_id": 12345,
                "short_id": 123,
                "area_id": 1,
                "area_name": "网游",
                "parent_area_id": 2,
                "parent_area_name": "游戏",
                "live_status": 0,
                "live_start_time": 0,
                "online": 0,
                "title": "Test",
                "cover": "",
                "tags": "",
                "description": "",
            },
            "anchor_info": {
                "base_info": {
                    "uname": "User",
                    "gender": "",
                    "face": "https://example.com/f.jpg",
                }
            },
        }
        with (
            patch.object(live.api, "get_info_by_room", new_callable=AsyncMock) as m,
            patch.object(live.api, "get_room_play_infos", new_callable=AsyncMock) as m2,
        ):
            m.return_value = data
            m2.return_value = [_play_info_response(format_name="fmp4")]
            await live.init()

        assert live.has_flv_stream is False


class TestLiveStatus:
    async def test_get_live_status_from_api(self) -> None:
        live = _make_live()
        with patch.object(live.api, "get_info_by_room", new_callable=AsyncMock) as m:
            m.return_value = {"room_info": {"live_status": 1}}
            status = await live.get_live_status()
        assert status == LiveStatus.LIVE

    async def test_get_live_status_html_fallback(self) -> None:
        live = _make_live()
        mock_resp = AsyncMock()
        mock_resp.text = AsyncMock(return_value='"liveStatus":1')
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(live.api, "get_info_by_room", new_callable=AsyncMock) as m,
            patch.object(live._session, "get", return_value=mock_resp),
        ):
            m.side_effect = Exception("API error")
            status = await live.get_live_status()
        assert status == LiveStatus.LIVE

    async def test_get_live_status_preparing(self) -> None:
        live = _make_live()
        with patch.object(live.api, "get_info_by_room", new_callable=AsyncMock) as m:
            m.return_value = {"room_info": {"live_status": 0}}
            status = await live.get_live_status()
        assert status == LiveStatus.PREPARING


class TestConnectivity:
    async def test_connectivity_success(self) -> None:
        live = _make_live()
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        with patch.object(live._session, "head", return_value=mock_resp):
            assert await live.test_connectivity("https://example.com/stream") is True

    async def test_connectivity_failure(self) -> None:
        live = _make_live()
        with patch.object(live._session, "head", side_effect=Exception("timeout")):
            assert await live.test_connectivity("https://example.com/stream") is False


class TestStreamURL:
    async def test_get_stream_url_success(self) -> None:
        live = _make_live()
        with patch.object(live.api, "get_room_play_infos", new_callable=AsyncMock) as m:
            m.return_value = [_play_info_response()]
            url = await live.get_stream_url("flv", "avc", 10000)
        assert "cn-gotcha01" in url
        assert "/live/room.flv" in url

    async def test_no_stream_available(self) -> None:
        live = _make_live()
        with patch.object(live.api, "get_room_play_infos", new_callable=AsyncMock) as m:
            m.return_value = [{"playurl_info": {"playurl": {"stream": []}}}]
            with pytest.raises(NoStreamAvailable):
                await live.get_stream_url()

    async def test_no_format_available(self) -> None:
        live = _make_live()
        with patch.object(live.api, "get_room_play_infos", new_callable=AsyncMock) as m:
            m.return_value = [_play_info_response(format_name="fmp4")]
            with pytest.raises(NoStreamFormatAvailable):
                await live.get_stream_url(stream_format="flv")

    async def test_no_codec_available(self) -> None:
        live = _make_live()
        with patch.object(live.api, "get_room_play_infos", new_callable=AsyncMock) as m:
            m.return_value = [_play_info_response(codec_name="hevc")]
            with pytest.raises(NoStreamCodecAvailable):
                await live.get_stream_url(stream_codec="avc")

    async def test_no_quality_available(self) -> None:
        live = _make_live()
        resp = _play_info_response(current_qn=250, accept_qn=[250, 150])
        with patch.object(live.api, "get_room_play_infos", new_callable=AsyncMock) as m:
            m.return_value = [resp]
            # Should still return a URL (fallback to highest available)
            url = await live.get_stream_url(quality_number=10000)
            assert url != ""


class TestCDNPriority:
    def test_gotcha_highest_priority(self) -> None:
        urls = [
            {"host": "https://mcdn.bilivideo.com", "extra": "?a=1"},
            {"host": "https://cn-gotcha01.bilivideo.com", "extra": "?a=2"},
            {"host": "https://other.bilivideo.com", "extra": "?a=3"},
        ]
        sorted_urls = Live.sort_stream_urls(urls)
        assert "gotcha" in sorted_urls[0]

    def test_mcdn_lowest_priority(self) -> None:
        urls = [
            {"host": "https://mcdn.bilivideo.com", "extra": "?a=1"},
            {"host": "https://cn-gotcha01.bilivideo.com", "extra": "?a=2"},
        ]
        sorted_urls = Live.sort_stream_urls(urls)
        assert "mcdn" in sorted_urls[-1]

    def test_cn_prefix_low_priority(self) -> None:
        assert Live._cdn_priority("https://cn-hk01.bilivideo.com") == 2
        assert Live._cdn_priority("https://gotcha01.bilivideo.com") == 0
        assert Live._cdn_priority("https://other.bilivideo.com") == 1


class TestAlternativeStream:
    async def test_select_alternative_success(self) -> None:
        live = _make_live()
        resp = _play_info_response()
        # Add a second url_info
        codec = resp["playurl_info"]["playurl"]["stream"][0]["format"][0]["codec"][0]
        codec["url_info"].append(
            {"host": "https://backup.bilivideo.com", "extra": "?b=1"}
        )
        with patch.object(live.api, "get_room_play_infos", new_callable=AsyncMock) as m:
            m.return_value = [resp]
            url = await live.select_alternative(exclude_host="cn-gotcha01")
        assert "backup" in url

    async def test_no_alternative_available(self) -> None:
        live = _make_live()
        resp = _play_info_response()
        with patch.object(live.api, "get_room_play_infos", new_callable=AsyncMock) as m:
            m.return_value = [resp]
            with pytest.raises(NoAlternativeStreamAvailable):
                await live.select_alternative(exclude_host="cn-gotcha01")


class TestRoomState:
    async def test_hidden_room(self) -> None:
        live = _make_live()
        with patch.object(live.api, "get_info_by_room", new_callable=AsyncMock) as m:
            m.return_value = {"room_info": {"hidden_till": 9999999999, "lock_till": 0}}
            with pytest.raises(LiveRoomHidden):
                await live.check_room_state()

    async def test_locked_room(self) -> None:
        live = _make_live()
        with patch.object(live.api, "get_info_by_room", new_callable=AsyncMock) as m:
            m.return_value = {"room_info": {"hidden_till": 0, "lock_till": 9999999999}}
            with pytest.raises(LiveRoomLocked):
                await live.check_room_state()

    async def test_encrypted_room(self) -> None:
        live = _make_live()
        with patch.object(live.api, "get_info_by_room", new_callable=AsyncMock) as m:
            m.return_value = {
                "room_info": {"hidden_till": 0, "lock_till": 0, "encrypted": True}
            }
            with pytest.raises(LiveRoomEncrypted):
                await live.check_room_state()

    async def test_normal_room(self) -> None:
        live = _make_live()
        with patch.object(live.api, "get_info_by_room", new_callable=AsyncMock) as m:
            m.return_value = {
                "room_info": {"hidden_till": 0, "lock_till": 0, "encrypted": False}
            }
            await live.check_room_state()  # Should not raise


class TestHotSwap:
    def test_user_agent_swap(self) -> None:
        live = _make_live()
        live.user_agent = "CustomUA/1.0"
        assert live.user_agent == "CustomUA/1.0"

    def test_cookie_swap(self) -> None:
        live = _make_live()
        live.cookie = "SESSDATA=abc123"
        assert live.cookie == "SESSDATA=abc123"

    def test_base_urls_swap(self) -> None:
        live = _make_live()
        live.base_api_urls = ["https://custom.api.com"]
        assert live.base_api_urls == ["https://custom.api.com"]
        live.base_live_api_urls = ["https://custom.live.com"]
        assert live.base_live_api_urls == ["https://custom.live.com"]
        live.base_play_info_api_urls = ["https://custom.play.com"]
        assert live.base_play_info_api_urls == ["https://custom.play.com"]
