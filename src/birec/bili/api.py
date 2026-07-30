"""Bilibili Web and App API clients with multi-domain failover and retry."""

from __future__ import annotations

import asyncio
import hashlib
import time
from datetime import UTC, datetime
from typing import Any, Final
from urllib.parse import urlencode

import aiohttp
from loguru import logger
from tenacity import retry, stop_after_delay, wait_exponential

from . import wbi
from .exceptions import ApiRequestError
from .typing import JsonResponse, QualityNumber, ResponseData

__all__ = ("AppApi", "WebApi")

BASE_HEADERS: Final[dict[str, str]] = {
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en;q=0.3,en-US;q=0.2",
    "Accept": "application/json, text/plain, */*",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "Origin": "https://live.bilibili.com",
    "Pragma": "no-cache",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    ),
}


class BaseApi:
    """Base with multi-domain failover and tenacity retry."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        headers: dict[str, str] | None = None,
        *,
        room_id: int | None = None,
    ) -> None:
        self._logger = logger.bind(room_id=room_id or "")

        self.base_api_urls: list[str] = ["https://api.bilibili.com"]
        self.base_live_api_urls: list[str] = ["https://api.live.bilibili.com"]
        self.base_play_info_api_urls: list[str] = ["https://api.live.bilibili.com"]

        self._session = session
        self.headers = headers or {}
        self.timeout = 10

    @property
    def headers(self) -> dict[str, str]:
        return self._headers

    @headers.setter
    def headers(self, value: dict[str, str]) -> None:
        self._headers = {**BASE_HEADERS, **value}

    @staticmethod
    def _check_response(json_res: JsonResponse) -> None:
        if json_res["code"] != 0:
            raise ApiRequestError(
                json_res["code"],
                json_res.get("message") or json_res.get("msg") or "",
            )

    @retry(reraise=True, stop=stop_after_delay(5), wait=wait_exponential(0.1))
    async def _get_json_res(self, *args: Any, **kwds: Any) -> JsonResponse:
        should_check_response = kwds.pop("check_response", True)
        kwds = {"timeout": self.timeout, "headers": self.headers, **kwds}
        async with self._session.get(*args, **kwds) as res:
            self._logger.trace("Request: {}", res.request_info)
            self._logger.trace("Response: {}", await res.text())
            try:
                json_res: JsonResponse = await res.json()
            except aiohttp.ContentTypeError:
                text_res = await res.text()
                self._logger.debug("Response text: {}", text_res[:200])
                raise
            if should_check_response:
                self._check_response(json_res)
            return json_res

    async def _get_json(
        self, base_urls: list[str], path: str, *args: Any, **kwds: Any
    ) -> JsonResponse:
        if not base_urls:
            raise ValueError("No base urls")
        exception: Exception | None = None
        for base_url in base_urls:
            url = base_url + path
            try:
                return await self._get_json_res(url, *args, **kwds)
            except Exception as exc:
                exception = exc
                self._logger.trace("Failed to get json from {}: {}", url, repr(exc))
        assert exception is not None
        raise exception

    async def _get_jsons_concurrently(
        self, base_urls: list[str], path: str, *args: Any, **kwds: Any
    ) -> list[JsonResponse]:
        if not base_urls:
            raise ValueError("No base urls")
        urls = [base_url + path for base_url in base_urls]
        aws = (self._get_json_res(url, *args, **kwds) for url in urls)
        results = await asyncio.gather(*aws, return_exceptions=True)
        exceptions: list[Exception] = []
        json_responses: list[JsonResponse] = []
        for idx, item in enumerate(results):
            if isinstance(item, Exception):
                self._logger.trace(
                    "Failed to get json from {}: {}", urls[idx], repr(item)
                )
                exceptions.append(item)
            elif isinstance(item, dict):
                json_responses.append(item)
        if not json_responses:
            raise exceptions[0]
        return json_responses


class AppApi(BaseApi):
    """Android platform API with MD5 app signing."""

    _appkey = "1d8b6e7d45233436"
    _appsec = "560c52ccd288fed045859ed18bffd973"

    _tv_appkey = "4409e2ce8ffd12b8"
    _tv_appsec = "59b43e04ad6965f34319062b478f83dd"

    _app_headers: Final[dict[str, str]] = {
        "User-Agent": (
            "Mozilla/5.0 BiliDroid/6.64.0 (bbcallen@gmail.com) os/android "
            "model/Unknown mobi_app/android build/6640400 channel/bili "
            "innerVer/6640400 osVer/6.0.1 network/2"
        ),
        "Connection": "Keep-Alive",
        "Accept-Encoding": "gzip",
    }

    @property
    def headers(self) -> dict[str, str]:
        return self._headers

    @headers.setter
    def headers(self, value: dict[str, str]) -> None:
        self._headers = {**value, **self._app_headers}

    @staticmethod
    def _signed_with(
        appkey: str, appsec: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        params = dict(sorted({**params, "appkey": appkey}.items()))
        query = urlencode(params, doseq=True)
        sign = hashlib.md5((query + appsec).encode()).hexdigest()  # noqa: S324
        params["sign"] = sign
        return params

    @classmethod
    def signed(cls, params: dict[str, Any]) -> dict[str, Any]:
        return cls._signed_with(cls._appkey, cls._appsec, params)

    async def get_room_play_infos(
        self,
        room_id: int,
        qn: QualityNumber = 10000,
        *,
        only_video: bool = False,
        only_audio: bool = False,
    ) -> list[ResponseData]:
        path = "/xlive/app-room/v2/index/getRoomPlayInfo"
        params = self.signed(
            {
                "actionKey": "appkey",
                "build": "6640400",
                "channel": "bili",
                "codec": "0,1",
                "device": "android",
                "device_name": "Unknown",
                "disable_rcmd": "0",
                "dolby": "1",
                "format": "0,1,2",
                "free_type": "0",
                "http": "1",
                "mask": "0",
                "mobi_app": "android",
                "need_hdr": "0",
                "no_playurl": "0",
                "only_audio": "1" if only_audio else "0",
                "only_video": "1" if only_video else "0",
                "platform": "android",
                "play_type": "0",
                "protocol": "0,1",
                "qn": qn,
                "room_id": room_id,
                "ts": int(datetime.now(UTC).timestamp()),
            }
        )
        json_responses = await self._get_jsons_concurrently(
            self.base_play_info_api_urls, path, params=params
        )
        return [r["data"] for r in json_responses]

    async def get_info_by_room(self, room_id: int) -> ResponseData:
        path = "/xlive/app-room/v1/index/getInfoByRoom"
        params = self.signed(
            {
                "actionKey": "appkey",
                "build": "6640400",
                "channel": "bili",
                "device": "android",
                "mobi_app": "android",
                "platform": "android",
                "room_id": room_id,
                "ts": int(datetime.now(UTC).timestamp()),
            }
        )
        json_res = await self._get_json(self.base_live_api_urls, path, params=params)
        return json_res["data"]  # type: ignore[no-any-return]

    async def get_user_info(self, uid: int) -> ResponseData:
        base_api_urls = ["https://app.bilibili.com"]
        path = "/x/v2/space"
        params = self.signed(
            {
                "build": "6640400",
                "channel": "bili",
                "mobi_app": "android",
                "platform": "android",
                "ts": int(datetime.now(UTC).timestamp()),
                "vmid": uid,
            }
        )
        json_res = await self._get_json(base_api_urls, path, params=params)
        return json_res["data"]  # type: ignore[no-any-return]

    async def get_danmu_info(self, room_id: int) -> ResponseData:
        path = "/xlive/app-room/v1/index/getDanmuInfo"
        params = self.signed(
            {
                "actionKey": "appkey",
                "build": "6640400",
                "channel": "bili",
                "device": "android",
                "mobi_app": "android",
                "platform": "android",
                "room_id": room_id,
                "ts": int(datetime.now(UTC).timestamp()),
            }
        )
        json_res = await self._get_json(self.base_live_api_urls, path, params=params)
        return json_res["data"]  # type: ignore[no-any-return]

    async def request_tv_qrcode(self, local_id: str = "0") -> ResponseData:
        url = "https://passport.bilibili.com/x/passport-tv-login/qrcode/auth_code"
        params = self._signed_with(
            self._tv_appkey,
            self._tv_appsec,
            {
                "local_id": local_id,
                "ts": int(datetime.now(UTC).timestamp()),
            },
        )
        # TV 端 auth_code 接口要求 POST + 表单编码；若用 GET，passport 网关
        # 会以 405 拒绝并返回 text/plain 错误页，无法按 JSON 解析。
        async with self._session.post(
            url,
            data=params,
            headers=self.headers,
            timeout=aiohttp.ClientTimeout(total=self.timeout),
        ) as res:
            json_res: JsonResponse = await res.json()
        self._check_response(json_res)
        return json_res["data"]  # type: ignore[no-any-return]

    async def poll_tv_qrcode(self, auth_code: str, local_id: str = "0") -> JsonResponse:
        url = "https://passport.bilibili.com/x/passport-tv-login/qrcode/poll"
        params = self._signed_with(
            self._tv_appkey,
            self._tv_appsec,
            {
                "auth_code": auth_code,
                "local_id": local_id,
                "ts": int(datetime.now(UTC).timestamp()),
            },
        )
        async with self._session.post(
            url,
            data=params,
            headers=self.headers,
            timeout=aiohttp.ClientTimeout(total=self.timeout),
        ) as res:
            return await res.json()  # type: ignore[no-any-return]


class WebApi(BaseApi):
    """Web platform API with WBI signing and -352 key refresh."""

    _wbi_key = wbi.make_key(
        img_key="7cd084941338484aae1ad9425b84077c",
        sub_key="4932caff0ff746eab6f01bf08b70ac45",
    )
    _wbi_key_mtime = 0.0

    @retry(reraise=True, stop=stop_after_delay(20), wait=wait_exponential(0.1))
    async def _get_json_res(
        self, url: str, with_wbi: bool = False, *args: Any, **kwds: Any
    ) -> JsonResponse:
        if with_wbi:
            key = self.__class__._wbi_key
            ts = int(datetime.now().timestamp())
            params = list(kwds.pop("params").items())
            query = wbi.build_query(key, ts, params)
            url = f"{url}?{query}"

        try:
            return await super()._get_json_res(url, *args, **kwds)
        except ApiRequestError as e:
            if e.code == -352 and time.monotonic() - self.__class__._wbi_key_mtime > 60:
                await self._update_wbi_key()
            raise

    async def room_init(self, room_id: int) -> ResponseData:
        path = "/room/v1/Room/room_init"
        params = {"id": room_id}
        json_res = await self._get_json(self.base_live_api_urls, path, params=params)
        return json_res["data"]  # type: ignore[no-any-return]

    async def get_room_play_infos(
        self, room_id: int, qn: QualityNumber = 10000
    ) -> list[ResponseData]:
        path = "/xlive/web-room/v2/index/getRoomPlayInfo"
        params = {
            "room_id": room_id,
            "protocol": "0,1",
            "format": "0,1,2",
            "codec": "0,1",
            "qn": qn,
            "platform": "web",
            "ptype": 8,
        }
        json_responses = await self._get_jsons_concurrently(
            self.base_play_info_api_urls, path, with_wbi=True, params=params
        )
        return [r["data"] for r in json_responses]

    async def get_info_by_room(self, room_id: int) -> ResponseData:
        path = "/xlive/web-room/v1/index/getInfoByRoom"
        params = {"room_id": room_id}
        json_res = await self._get_json(
            self.base_live_api_urls, path, with_wbi=True, params=params
        )
        return json_res["data"]  # type: ignore[no-any-return]

    async def get_info(self, room_id: int) -> ResponseData:
        path = "/room/v1/Room/get_info"
        params = {"room_id": room_id}
        json_res = await self._get_json(self.base_live_api_urls, path, params=params)
        return json_res["data"]  # type: ignore[no-any-return]

    async def get_timestamp(self) -> int:
        path = "/av/v1/Time/getTimestamp"
        params = {"platform": "pc"}
        json_res = await self._get_json(self.base_live_api_urls, path, params=params)
        return int(json_res["data"]["timestamp"])

    async def get_user_info(self, uid: int) -> ResponseData:
        path = "/x/space/wbi/acc/info"
        params = {"mid": uid}
        json_res = await self._get_json(
            self.base_api_urls, path, with_wbi=True, params=params
        )
        return json_res["data"]  # type: ignore[no-any-return]

    async def get_danmu_info(self, room_id: int) -> ResponseData:
        path = "/xlive/web-room/v1/index/getDanmuInfo"
        params = {"id": room_id}
        json_res = await self._get_json(
            self.base_live_api_urls, path, with_wbi=True, params=params
        )
        return json_res["data"]  # type: ignore[no-any-return]

    async def get_nav(self) -> ResponseData:
        path = "/x/web-interface/nav"
        json_res = await self._get_json(self.base_api_urls, path, check_response=False)
        return json_res

    async def _update_wbi_key(self) -> None:
        nav = await self.get_nav()
        img_key = wbi.extract_key(nav["data"]["wbi_img"]["img_url"])
        sub_key = wbi.extract_key(nav["data"]["wbi_img"]["sub_url"])
        self.__class__._wbi_key = wbi.make_key(img_key, sub_key)
        self.__class__._wbi_key_mtime = time.monotonic()
