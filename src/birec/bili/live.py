"""Live room abstraction: status, stream URL resolution, CDN selection."""

from __future__ import annotations

from typing import Any

import aiohttp
from loguru import logger

from .api import AppApi, WebApi
from .exceptions import (
    LiveRoomEncrypted,
    LiveRoomHidden,
    LiveRoomLocked,
    NoAlternativeStreamAvailable,
    NoStreamAvailable,
    NoStreamCodecAvailable,
    NoStreamFormatAvailable,
    NoStreamQualityAvailable,
)
from .helpers import extract_codecs, extract_formats, extract_streams
from .models import LiveStatus, RoomInfo, UserInfo
from .typing import ApiPlatform, QualityNumber, StreamCodec, StreamFormat

__all__ = ("Live",)


class Live:
    """Encapsulates a Bilibili live room's runtime state and stream access."""

    def __init__(
        self,
        room_id: int,
        *,
        session: aiohttp.ClientSession,
        api_platform: ApiPlatform = "web",
    ) -> None:
        self._room_id = room_id
        self._logger = logger.bind(room_id=room_id)
        self._session = session

        self._api: WebApi | AppApi
        if api_platform == "web":
            self._api = WebApi(session, room_id=room_id)
        else:
            self._api = AppApi(session, room_id=room_id)

        self._room_info: RoomInfo | None = None
        self._user_info: UserInfo | None = None
        self._has_flv_stream: bool = False

    @property
    def room_id(self) -> int:
        return self._room_id

    @property
    def room_info(self) -> RoomInfo | None:
        return self._room_info

    @property
    def user_info(self) -> UserInfo | None:
        return self._user_info

    @property
    def has_flv_stream(self) -> bool:
        return self._has_flv_stream

    @property
    def api(self) -> WebApi | AppApi:
        return self._api

    # --- Hot-swappable properties ---

    @property
    def user_agent(self) -> str:
        return self._api.headers.get("User-Agent", "")

    @user_agent.setter
    def user_agent(self, value: str) -> None:
        self._api.headers = {**self._api.headers, "User-Agent": value}

    @property
    def cookie(self) -> str:
        return self._api.headers.get("Cookie", "")

    @cookie.setter
    def cookie(self, value: str) -> None:
        self._api.headers = {**self._api.headers, "Cookie": value}

    @property
    def base_api_urls(self) -> list[str]:
        return self._api.base_api_urls

    @base_api_urls.setter
    def base_api_urls(self, value: list[str]) -> None:
        self._api.base_api_urls = value

    @property
    def base_live_api_urls(self) -> list[str]:
        return self._api.base_live_api_urls

    @base_live_api_urls.setter
    def base_live_api_urls(self, value: list[str]) -> None:
        self._api.base_live_api_urls = value

    @property
    def base_play_info_api_urls(self) -> list[str]:
        return self._api.base_play_info_api_urls

    @base_play_info_api_urls.setter
    def base_play_info_api_urls(self, value: list[str]) -> None:
        self._api.base_play_info_api_urls = value

    # --- Initialization / Refresh ---

    async def init(self) -> None:
        """Initialize room and user info, detect FLV stream availability."""
        await self.refresh()

    async def refresh(self) -> None:
        """Reload room and user info from API."""
        data = await self._api.get_info_by_room(self._room_id)
        self._room_info = RoomInfo.from_data(data["room_info"])
        self._user_info = UserInfo.from_info_by_room(data)
        self._room_id = self._room_info.room_id
        self._logger = logger.bind(room_id=self._room_id)
        self._has_flv_stream = await self._detect_flv_stream()

    async def _detect_flv_stream(self) -> bool:
        """Check if FLV stream is available for this room."""
        try:
            play_infos = await self._api.get_room_play_infos(self._room_id)
            streams = extract_streams(play_infos)
            formats = extract_formats(streams, "flv")
            return len(formats) > 0
        except Exception:
            return False

    # --- Live Status ---

    async def get_live_status(self) -> LiveStatus:
        """Query live status via API, with HTML page fallback."""
        try:
            data = await self._api.get_info_by_room(self._room_id)
            return LiveStatus(data["room_info"]["live_status"])
        except Exception:
            self._logger.debug("API live status failed, trying HTML fallback")
            return await self._get_live_status_from_html()

    async def _get_live_status_from_html(self) -> LiveStatus:
        """Parse live status from the room HTML page as fallback."""
        url = f"https://live.bilibili.com/{self._room_id}"
        async with self._session.get(url, headers=self._api.headers) as res:
            text = await res.text()
        if '"liveStatus":1' in text or '"live_status":1' in text:
            return LiveStatus.LIVE
        if '"liveStatus":2' in text or '"live_status":2' in text:
            return LiveStatus.ROUND
        return LiveStatus.PREPARING

    # --- Connectivity ---

    async def test_connectivity(self, url: str) -> bool:
        """HEAD request to test if a stream URL is reachable."""
        try:
            async with self._session.head(
                url,
                headers=self._api.headers,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as res:
                return res.status == 200
        except Exception:
            return False

    # --- Stream URL Resolution ---

    async def get_stream_url(
        self,
        stream_format: StreamFormat = "flv",
        stream_codec: StreamCodec = "avc",
        quality_number: QualityNumber = 10000,
    ) -> str:
        """Resolve stream URL by format/codec/quality with precise exceptions.

        Raises:
            NoStreamAvailable: No stream at all.
            NoStreamFormatAvailable: Requested format not offered.
            NoStreamCodecAvailable: Requested codec not offered.
            NoStreamQualityAvailable: Requested quality not in accepted list.
        """
        play_infos = await self._api.get_room_play_infos(
            self._room_id, qn=quality_number
        )
        streams = extract_streams(play_infos)
        if not streams:
            raise NoStreamAvailable(f"No stream available for room {self._room_id}")

        formats = extract_formats(streams, stream_format)
        if not formats:
            raise NoStreamFormatAvailable(
                f"Format '{stream_format}' not available for room {self._room_id}"
            )

        codecs = extract_codecs(formats, stream_codec)
        if not codecs:
            raise NoStreamCodecAvailable(
                f"Codec '{stream_codec}' not available for room {self._room_id}"
            )

        # Find the best matching quality
        url = self._select_quality(codecs, quality_number)
        if url is None:
            raise NoStreamQualityAvailable(
                f"Quality {quality_number} not available for room {self._room_id}"
            )
        return url

    def _select_quality(
        self, codecs: list[dict[str, Any]], quality_number: QualityNumber
    ) -> str | None:
        """Select stream URL matching quality, preferring exact match then highest."""
        best_url: str | None = None
        best_qn: int = -1

        for codec in codecs:
            current_qn = codec.get("current_qn", 0)
            accept_qn_list = codec.get("accept_qn", [])
            url_info_list = codec.get("url_info", [])

            if not url_info_list:
                continue

            # Build the full URL from url_info
            url = self._build_stream_url(url_info_list, codec.get("base_url", ""))
            if not url:
                continue

            if current_qn == quality_number:
                return url

            if quality_number in accept_qn_list and current_qn > best_qn:
                best_qn = current_qn
                best_url = url

        # Fallback: return highest quality available
        if best_url is None:
            for codec in codecs:
                current_qn = codec.get("current_qn", 0)
                url_info_list = codec.get("url_info", [])
                if url_info_list and current_qn > best_qn:
                    best_qn = current_qn
                    best_url = self._build_stream_url(
                        url_info_list, codec.get("base_url", "")
                    )

        return best_url

    @staticmethod
    def _build_stream_url(url_info_list: list[dict[str, Any]], base_url: str) -> str:
        """Build full stream URL from url_info entries and base_url."""
        if not url_info_list or not base_url:
            return ""
        info = url_info_list[0]
        host: str = info.get("host", "")
        extra: str = info.get("extra", "")
        if host and base_url:
            return host + base_url + extra
        return ""

    # --- CDN Host Prioritization ---

    @staticmethod
    def sort_stream_urls(url_info_list: list[dict[str, Any]]) -> list[str]:
        """Sort CDN hosts by priority: gotcha > others > mcdn/cn-*."""
        urls: list[tuple[int, str]] = []
        for info in url_info_list:
            host = info.get("host", "")
            extra = info.get("extra", "")
            url = host + extra if host else ""
            if not url:
                continue
            priority = Live._cdn_priority(host)
            urls.append((priority, url))
        urls.sort(key=lambda x: x[0])
        return [u for _, u in urls]

    @staticmethod
    def _cdn_priority(host: str) -> int:
        """Lower number = higher priority."""
        if "gotcha" in host:
            return 0
        if "mcdn" in host:
            return 2
        if "cn-" in host:
            return 2
        return 1

    # --- Alternative Stream ---

    async def select_alternative(
        self,
        stream_format: StreamFormat = "flv",
        stream_codec: StreamCodec = "avc",
        quality_number: QualityNumber = 10000,
        exclude_host: str = "",
    ) -> str:
        """Select an alternative CDN stream, excluding the given host.

        Raises:
            NoAlternativeStreamAvailable: No other CDN available.
        """
        play_infos = await self._api.get_room_play_infos(
            self._room_id, qn=quality_number
        )
        streams = extract_streams(play_infos)
        formats = extract_formats(streams, stream_format)
        codecs = extract_codecs(formats, stream_codec)

        alternatives: list[str] = []
        for codec in codecs:
            url_info_list = codec.get("url_info", [])
            base_url = codec.get("base_url", "")
            for info in url_info_list:
                host = info.get("host", "")
                extra = info.get("extra", "")
                if host and base_url and exclude_host not in host:
                    alternatives.append(host + base_url + extra)

        if not alternatives:
            raise NoAlternativeStreamAvailable(
                f"No alternative stream for room {self._room_id}"
            )

        # Sort by CDN priority
        sorted_urls = self.sort_stream_urls(
            [
                {"host": u.split("/")[0] + "//" + u.split("/")[2], "extra": ""}
                for u in alternatives
            ]
        )
        return sorted_urls[0] if sorted_urls else alternatives[0]

    # --- Room State Detection ---

    async def check_room_state(self) -> None:
        """Check if room is hidden/locked/encrypted and raise accordingly.

        Raises:
            LiveRoomHidden: Room is hidden.
            LiveRoomLocked: Room is locked.
            LiveRoomEncrypted: Room requires password.
        """
        data = await self._api.get_info_by_room(self._room_id)
        room_data = data["room_info"]
        if room_data.get("hidden_till", 0) != 0:
            raise LiveRoomHidden(f"Room {self._room_id} is hidden")
        if room_data.get("lock_till", 0) != 0:
            raise LiveRoomLocked(f"Room {self._room_id} is locked")
        if room_data.get("encrypted", False):
            raise LiveRoomEncrypted(f"Room {self._room_id} is encrypted")
