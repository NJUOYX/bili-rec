"""Tests for birec.bili.models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from birec.bili.models import LiveStatus, RoomInfo, UserInfo


class TestLiveStatus:
    def test_values(self) -> None:
        assert LiveStatus.PREPARING == 0
        assert LiveStatus.LIVE == 1
        assert LiveStatus.ROUND == 2

    def test_from_int(self) -> None:
        assert LiveStatus(1) is LiveStatus.LIVE


class TestRoomInfo:
    def _make_data(self, **overrides: object) -> dict:
        base = {
            "uid": 12345,
            "room_id": 67890,
            "short_id": 123,
            "area_id": 1,
            "area_name": "网游",
            "parent_area_id": 2,
            "parent_area_name": "游戏",
            "live_status": 1,
            "live_start_time": 1700000000,
            "online": 5000,
            "title": "Test Room",
            "cover": "https://example.com/cover.jpg",
            "tags": "tag1,tag2",
            "description": "Hello<br/>World",
        }
        base.update(overrides)
        return base

    def test_from_data_basic(self) -> None:
        info = RoomInfo.from_data(self._make_data())
        assert info.uid == 12345
        assert info.room_id == 67890
        assert info.short_room_id == 123
        assert info.area_name == "网游"
        assert info.parent_area_name == "游戏"
        assert info.live_status is LiveStatus.LIVE
        assert info.live_start_time == 1700000000
        assert info.online == 5000
        assert info.title == "Test Room"
        assert info.cover == "https://example.com/cover.jpg"
        assert info.tags == "tag1,tag2"

    def test_from_data_html_description_cleaned(self) -> None:
        info = RoomInfo.from_data(self._make_data(description="<b>Bold</b><br/>text"))
        assert "<b>" not in info.description
        assert "Bold" in info.description
        assert "text" in info.description

    def test_from_data_live_time_string(self) -> None:
        data = self._make_data(live_start_time=None, live_time="2024-01-15 10:30:00")
        info = RoomInfo.from_data(data)
        assert info.live_start_time > 0

    def test_from_data_live_time_zero_string(self) -> None:
        data = self._make_data(live_start_time=None, live_time="0000-00-00 00:00:00")
        info = RoomInfo.from_data(data)
        assert info.live_start_time == 0

    def test_from_data_missing_time_raises(self) -> None:
        data = self._make_data()
        del data["live_start_time"]
        with pytest.raises(ValueError, match="live_start_time"):
            RoomInfo.from_data(data)

    def test_from_data_cover_fallback_user_cover(self) -> None:
        data = self._make_data(cover="", user_cover="https://example.com/user.jpg")
        info = RoomInfo.from_data(data)
        assert info.cover == "https://example.com/user.jpg"

    def test_from_data_cover_scheme_forced_https(self) -> None:
        data = self._make_data(cover="http://example.com/cover.jpg")
        info = RoomInfo.from_data(data)
        assert info.cover.startswith("https://")

    def test_frozen(self) -> None:
        info = RoomInfo.from_data(self._make_data())
        with pytest.raises(ValidationError):
            info.title = "hacked"  # type: ignore[misc]


class TestUserInfo:
    def test_from_web_api_data(self) -> None:
        data = {
            "name": "TestUser",
            "sex": "男",
            "face": "http://example.com/face.jpg",
            "mid": 999,
        }
        user = UserInfo.from_web_api_data(data)
        assert user.name == "TestUser"
        assert user.gender == "男"
        assert user.face == "https://example.com/face.jpg"
        assert user.uid == 999

    def test_from_app_api_data(self) -> None:
        data = {
            "card": {
                "name": "AppUser",
                "sex": "女",
                "face": "http://example.com/app.jpg",
                "mid": 888,
            }
        }
        user = UserInfo.from_app_api_data(data)
        assert user.name == "AppUser"
        assert user.gender == "女"
        assert user.face.startswith("https://")
        assert user.uid == 888

    def test_from_app_api_data_missing_sex(self) -> None:
        data = {"card": {"name": "NoSex", "face": "http://x.com/f.jpg", "mid": 1}}
        user = UserInfo.from_app_api_data(data)
        assert user.gender == ""

    def test_from_info_by_room(self) -> None:
        data = {
            "room_info": {"uid": 777},
            "anchor_info": {
                "base_info": {
                    "uname": "Anchor",
                    "gender": "保密",
                    "face": "http://example.com/anchor.jpg",
                }
            },
        }
        user = UserInfo.from_info_by_room(data)
        assert user.name == "Anchor"
        assert user.gender == "保密"
        assert user.uid == 777
        assert user.face.startswith("https://")

    def test_frozen(self) -> None:
        user = UserInfo(name="a", gender="b", face="c", uid=1)
        with pytest.raises(ValidationError):
            user.name = "hacked"  # type: ignore[misc]
