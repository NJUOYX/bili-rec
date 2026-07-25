"""Tests for core cover_downloader module."""

from __future__ import annotations

import hashlib
import os
from unittest.mock import AsyncMock, MagicMock

import pytest

from birec.core.cover_downloader import CoverDownloader


def _make_mock_session(
    body: bytes = b"",
    status: int = 200,
    side_effect: Exception | None = None,
) -> MagicMock:
    """Create a mock aiohttp session."""
    resp = AsyncMock()
    resp.status = status
    resp.read = AsyncMock(return_value=body)
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    if side_effect:
        session.get = MagicMock(side_effect=side_effect)
    else:
        session.get = MagicMock(return_value=resp)
    return session


class TestCoverDownloader:
    @pytest.mark.asyncio
    async def test_download_success(self, tmp_path):
        session = _make_mock_session(body=b"fake image data")
        downloader = CoverDownloader(session)
        output = str(tmp_path / "cover.jpg")

        result = await downloader.download("https://example.com/cover.jpg", output)

        assert result is True
        assert os.path.exists(output)
        assert downloader.download_count == 1
        expected_hash = hashlib.sha1(b"fake image data").hexdigest()
        assert downloader.last_hash == expected_hash

    @pytest.mark.asyncio
    async def test_download_duplicate_skipped(self, tmp_path):
        session = _make_mock_session(body=b"same data")
        downloader = CoverDownloader(session)
        output = str(tmp_path / "cover.jpg")

        result1 = await downloader.download("https://example.com/cover.jpg", output)
        assert result1 is True
        assert downloader.download_count == 1

        result2 = await downloader.download("https://example.com/cover.jpg", output)
        assert result2 is False
        assert downloader.download_count == 1

    @pytest.mark.asyncio
    async def test_download_empty_url(self, tmp_path):
        session = _make_mock_session()
        downloader = CoverDownloader(session)
        result = await downloader.download("", str(tmp_path / "cover.jpg"))
        assert result is False

    @pytest.mark.asyncio
    async def test_download_http_error_retries(self, tmp_path):
        session = _make_mock_session(status=500)
        downloader = CoverDownloader(session, max_retries=3, retry_delay=0.01)
        output = str(tmp_path / "cover.jpg")
        result = await downloader.download("https://example.com/cover.jpg", output)
        assert result is False
        assert downloader.download_count == 0

    @pytest.mark.asyncio
    async def test_download_creates_directory(self, tmp_path):
        session = _make_mock_session(body=b"image data")
        downloader = CoverDownloader(session)
        output = str(tmp_path / "subdir" / "cover.jpg")

        result = await downloader.download("https://example.com/cover.jpg", output)

        assert result is True
        assert os.path.exists(output)

    @pytest.mark.asyncio
    async def test_download_new_content_overwrites(self, tmp_path):
        # First call returns "first image", second returns "second image"
        resp1 = AsyncMock()
        resp1.status = 200
        resp1.read = AsyncMock(return_value=b"first image")
        resp1.__aenter__ = AsyncMock(return_value=resp1)
        resp1.__aexit__ = AsyncMock(return_value=False)

        resp2 = AsyncMock()
        resp2.status = 200
        resp2.read = AsyncMock(return_value=b"second image")
        resp2.__aenter__ = AsyncMock(return_value=resp2)
        resp2.__aexit__ = AsyncMock(return_value=False)

        session = MagicMock()
        session.get = MagicMock(side_effect=[resp1, resp2])

        downloader = CoverDownloader(session)
        output = str(tmp_path / "cover.jpg")

        await downloader.download("https://example.com/cover.jpg", output)
        assert downloader.download_count == 1

        result = await downloader.download("https://example.com/cover.jpg", output)
        assert result is True
        assert downloader.download_count == 2

        with open(output, "rb") as f:
            assert f.read() == b"second image"

    @pytest.mark.asyncio
    async def test_download_connection_error(self, tmp_path):
        import aiohttp

        session = _make_mock_session(side_effect=aiohttp.ClientError("conn failed"))
        downloader = CoverDownloader(session, max_retries=2, retry_delay=0.01)
        output = str(tmp_path / "cover.jpg")
        result = await downloader.download("https://example.com/cover.jpg", output)
        assert result is False
        assert downloader.download_count == 0
