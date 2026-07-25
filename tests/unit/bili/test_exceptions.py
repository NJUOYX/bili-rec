"""Tests for birec.bili.exceptions."""

from __future__ import annotations

from birec.bili.exceptions import (
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


class TestApiRequestError:
    def test_attributes(self) -> None:
        exc = ApiRequestError(code=-352, message="risk control")
        assert exc.code == -352
        assert exc.message == "risk control"
        assert str(exc) == "code=-352 message=risk control"

    def test_is_exception(self) -> None:
        assert issubclass(ApiRequestError, Exception)


class TestStreamExceptions:
    def test_hierarchy(self) -> None:
        for cls in (
            NoStreamAvailable,
            NoStreamFormatAvailable,
            NoStreamCodecAvailable,
            NoStreamQualityAvailable,
            NoAlternativeStreamAvailable,
        ):
            assert issubclass(cls, Exception)
            exc = cls("test")
            assert str(exc) == "test"


class TestRoomExceptions:
    def test_hierarchy(self) -> None:
        for cls in (LiveRoomHidden, LiveRoomLocked, LiveRoomEncrypted):
            assert issubclass(cls, Exception)


class TestDanmakuClientAuthError:
    def test_is_client_error(self) -> None:
        import aiohttp

        assert issubclass(DanmakuClientAuthError, aiohttp.ClientError)
