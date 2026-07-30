"""Tests for birec.bili.api (BaseApi/WebApi/AppApi)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from birec.bili.api import AppApi, BaseApi, WebApi
from birec.bili.exceptions import ApiRequestError

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@pytest.fixture
async def session() -> AsyncGenerator[aiohttp.ClientSession]:
    async with aiohttp.ClientSession() as s:
        yield s


class TestCheckResponse:
    def test_zero_code_passes(self) -> None:
        BaseApi._check_response({"code": 0, "data": {}})

    def test_nonzero_raises(self) -> None:
        with pytest.raises(ApiRequestError) as exc_info:
            BaseApi._check_response({"code": -352, "message": "risk"})
        assert exc_info.value.code == -352
        assert exc_info.value.message == "risk"

    def test_msg_fallback(self) -> None:
        with pytest.raises(ApiRequestError) as exc_info:
            BaseApi._check_response({"code": 1, "msg": "fallback"})
        assert exc_info.value.message == "fallback"


class TestAppApiSigning:
    def test_signed_adds_appkey_and_sign(self) -> None:
        params = AppApi.signed({"foo": "bar", "ts": 123})
        assert params["appkey"] == AppApi._appkey
        assert "sign" in params
        assert len(params["sign"]) == 32

    def test_signed_deterministic(self) -> None:
        p1 = AppApi.signed({"a": 1, "b": 2})
        p2 = AppApi.signed({"a": 1, "b": 2})
        assert p1 == p2

    def test_signed_includes_appkey_in_sort(self) -> None:
        params = AppApi.signed({"z": 1, "a": 2})
        keys = list(params.keys())
        assert keys.index("appkey") < keys.index("z")

    def test_tv_signing_uses_different_keys(self) -> None:
        params = AppApi._signed_with(
            AppApi._tv_appkey, AppApi._tv_appsec, {"local_id": "0"}
        )
        assert params["appkey"] == AppApi._tv_appkey
        assert "sign" in params

    def test_tv_appsec_length_32(self) -> None:
        """_tv_appsec must be a full 32-char hex MD5 secret.

        Regression: a truncated secret produces valid-looking but wrong
        signatures, causing silent 403 rejections from passport.
        """
        assert len(AppApi._tv_appsec) == 32
        # Also verify it's valid hex
        int(AppApi._tv_appsec, 16)

    def test_tv_signed_produces_valid_md5_sign(self) -> None:
        """Verify the TV sign is a proper 32-char MD5 hex digest."""
        params = AppApi._signed_with(
            AppApi._tv_appkey, AppApi._tv_appsec, {"local_id": "0", "ts": 0}
        )
        assert len(params["sign"]) == 32
        int(params["sign"], 16)  # must be valid hex


class TestBaseApiFailover:
    async def test_sequential_failover_first_fails(
        self, session: aiohttp.ClientSession
    ) -> None:
        api = AppApi(session)
        call_count = 0

        async def mock_get_json(url: str, **kw: Any) -> dict:
            nonlocal call_count
            call_count += 1
            if "bad" in url:
                raise ConnectionError("fail")
            return {"code": 0, "data": {"ok": True}}

        with patch.object(api, "_get_json_res", side_effect=mock_get_json):
            result = await api._get_json(
                ["https://bad.example.com", "https://good.example.com"], "/api"
            )
        assert result["data"]["ok"] is True
        assert call_count == 2

    async def test_sequential_all_fail_raises(
        self, session: aiohttp.ClientSession
    ) -> None:
        api = AppApi(session)

        async def mock_get_json(url: str, **kw: Any) -> dict:
            raise ConnectionError("fail")

        with (
            patch.object(api, "_get_json_res", side_effect=mock_get_json),
            pytest.raises(ConnectionError),
        ):
            await api._get_json(["https://a.com", "https://b.com"], "/x")

    async def test_concurrent_one_succeeds(
        self, session: aiohttp.ClientSession
    ) -> None:
        api = AppApi(session)

        async def mock_get_json(url: str, **kw: Any) -> dict:
            if "a.com" in url:
                raise ConnectionError("fail")
            return {"code": 0, "data": {"v": 1}}

        with patch.object(api, "_get_json_res", side_effect=mock_get_json):
            results = await api._get_jsons_concurrently(
                ["https://a.com", "https://b.com"], "/x"
            )
        assert len(results) == 1
        assert results[0]["data"]["v"] == 1

    async def test_concurrent_all_fail_raises(
        self, session: aiohttp.ClientSession
    ) -> None:
        api = AppApi(session)

        async def mock_get_json(url: str, **kw: Any) -> dict:
            raise ConnectionError("fail")

        with (
            patch.object(api, "_get_json_res", side_effect=mock_get_json),
            pytest.raises(ConnectionError),
        ):
            await api._get_jsons_concurrently(["https://a.com", "https://b.com"], "/x")

    async def test_empty_base_urls_raises(self, session: aiohttp.ClientSession) -> None:
        api = AppApi(session)
        with pytest.raises(ValueError, match="No base urls"):
            await api._get_json([], "/x")


class TestWebApiWbi:
    async def test_wbi_query_appended(self, session: aiohttp.ClientSession) -> None:
        api = WebApi(session)
        captured: list[tuple[str, dict]] = []

        async def spy(self: BaseApi, url: str, **kw: Any) -> dict:
            captured.append((url, kw))
            return {"code": 0, "data": {"room_id": 123}}

        with patch.object(BaseApi, "_get_json_res", spy):
            result = await api.get_info_by_room(123)

        assert result["room_id"] == 123
        assert len(captured) == 1
        url = captured[0][0]
        assert "w_rid=" in url
        assert "wts=" in url

    async def test_get_nav_skips_check(self, session: aiohttp.ClientSession) -> None:
        api = WebApi(session)
        captured_kw: list[dict] = []

        async def spy(self: BaseApi, url: str, **kw: Any) -> dict:
            captured_kw.append(kw)
            return {"code": -101, "data": {"wbi_img": {}}}

        with patch.object(BaseApi, "_get_json_res", spy):
            result = await api.get_nav()
        assert result["code"] == -101
        assert captured_kw[0].get("check_response") is False

    async def test_api_request_error_propagates(
        self, session: aiohttp.ClientSession
    ) -> None:
        api = WebApi(session)

        async def mock_get_json(base_urls: list[str], path: str, **kw: Any) -> dict:
            raise ApiRequestError(60004, "not found")

        with (
            patch.object(api, "_get_json", side_effect=mock_get_json),
            pytest.raises(ApiRequestError) as exc_info,
        ):
            await api.get_info(999)
        assert exc_info.value.code == 60004


class TestAppApiEndpoints:
    async def test_get_info_by_room(self, session: aiohttp.ClientSession) -> None:
        api = AppApi(session)

        async def mock_get_json(base_urls: list[str], path: str, **kw: Any) -> dict:
            return {"code": 0, "data": {"room_info": {"room_id": 456}}}

        with patch.object(api, "_get_json", side_effect=mock_get_json):
            result = await api.get_info_by_room(456)
        assert result["room_info"]["room_id"] == 456

    async def test_get_danmu_info(self, session: aiohttp.ClientSession) -> None:
        api = AppApi(session)

        async def mock_get_json(base_urls: list[str], path: str, **kw: Any) -> dict:
            return {"code": 0, "data": {"host": "broadcast.example.com"}}

        with patch.object(api, "_get_json", side_effect=mock_get_json):
            result = await api.get_danmu_info(789)
        assert result["host"] == "broadcast.example.com"

    async def test_get_room_play_infos_concurrent(
        self, session: aiohttp.ClientSession
    ) -> None:
        api = AppApi(session)

        async def mock_get_jsons(
            base_urls: list[str], path: str, **kw: Any
        ) -> list[dict]:
            return [{"code": 0, "data": {"stream": {}}}]

        with patch.object(api, "_get_jsons_concurrently", side_effect=mock_get_jsons):
            results = await api.get_room_play_infos(100)
        assert len(results) == 1
        assert "stream" in results[0]

    async def test_request_tv_qrcode_posts(
        self, session: aiohttp.ClientSession
    ) -> None:
        """auth_code 端点必须以 POST 表单请求；用 GET 会被 passport 网关 405 拒绝。"""
        api = AppApi(session)
        mock_resp = AsyncMock()
        mock_resp.json = AsyncMock(
            return_value={
                "code": 0,
                "data": {"url": "https://qr.example.com", "auth_code": "abc"},
            }
        )
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_post = MagicMock(return_value=mock_resp)
        with patch.object(session, "post", mock_post):
            result = await api.request_tv_qrcode()
        assert result["auth_code"] == "abc"
        mock_post.assert_called_once()
        # 签名参数以表单编码发送，而非拼在 query string。
        posted_data = mock_post.call_args.kwargs["data"]
        assert posted_data["appkey"] == AppApi._tv_appkey
        assert "sign" in posted_data

    async def test_poll_tv_qrcode_posts(self, session: aiohttp.ClientSession) -> None:
        api = AppApi(session)
        mock_resp = AsyncMock()
        mock_resp.json = AsyncMock(return_value={"code": 0, "data": {"cookies": []}})
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_post = MagicMock(return_value=mock_resp)
        with patch.object(session, "post", mock_post):
            result = await api.poll_tv_qrcode("test_auth_code")
        assert result["code"] == 0
        mock_post.assert_called_once()
