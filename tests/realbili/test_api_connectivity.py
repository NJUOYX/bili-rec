"""Read-only connectivity checks against the live Bilibili API.

These exercise the WBI-signed Web API surface that every recording depends on:
room/user info, play-info stream listing, danmaku server discovery, and live
status. They mutate nothing and only assert that responses are well-formed.
"""

from __future__ import annotations

from birec.bili.helpers import extract_streams
from birec.bili.live import Live
from birec.bili.models import LiveStatus, RoomInfo, UserInfo


class TestApiConnectivity:
    async def test_room_info_populated(self, live: Live) -> None:
        room_info = live.room_info
        assert isinstance(room_info, RoomInfo)
        assert room_info.room_id > 0
        assert room_info.uid > 0

    async def test_user_info_populated(self, live: Live) -> None:
        user_info = live.user_info
        assert isinstance(user_info, UserInfo)
        assert user_info.name
        assert user_info.uid > 0

    async def test_live_status_is_known(self, live: Live) -> None:
        status = await live.get_live_status()
        assert isinstance(status, LiveStatus)
        assert status in (LiveStatus.PREPARING, LiveStatus.LIVE, LiveStatus.ROUND)

    async def test_play_infos_return_streams(self, live: Live) -> None:
        play_infos = await live.api.get_room_play_infos(live.room_id)
        assert isinstance(play_infos, list)
        # A live room should advertise at least one playable stream.
        streams = extract_streams(play_infos)
        assert streams, "live room advertised no streams"

    async def test_danmu_info_has_hosts_and_token(self, live: Live) -> None:
        data = await live.api.get_danmu_info(live.room_id)
        host_list = data["host_list"]
        assert isinstance(host_list, list) and host_list
        assert all(entry.get("host") for entry in host_list)
        assert data["token"]

    async def test_nav_wbi_keys_available(self, live: Live) -> None:
        nav = await live.api.get_nav()
        wbi_img = nav["data"]["wbi_img"]
        assert wbi_img.get("img_url")
        assert wbi_img.get("sub_url")
