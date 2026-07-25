"""Tests for update module (PypiApi)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from birec.update import PypiApi


class TestPypiApi:
    @pytest.mark.asyncio
    async def test_get_latest_version_success(self) -> None:
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"info": {"version": "1.2.3"}})
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)

        api = PypiApi(mock_session)
        version = await api.get_latest_version_string("birec")
        assert version == "1.2.3"

    @pytest.mark.asyncio
    async def test_get_latest_version_http_error(self) -> None:
        mock_resp = AsyncMock()
        mock_resp.status = 404
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)

        api = PypiApi(mock_session)
        version = await api.get_latest_version_string("nonexistent")
        assert version is None

    @pytest.mark.asyncio
    async def test_get_latest_version_network_error(self) -> None:
        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=OSError("network error"))

        api = PypiApi(mock_session)
        version = await api.get_latest_version_string("birec")
        assert version is None

    @pytest.mark.asyncio
    async def test_get_project_info_success(self) -> None:
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(
            return_value={"info": {"name": "birec", "version": "1.0.0"}}
        )
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)

        api = PypiApi(mock_session)
        info = await api.get_project_info("birec")
        assert info is not None
        assert info["name"] == "birec"

    @pytest.mark.asyncio
    async def test_get_project_info_failure(self) -> None:
        mock_resp = AsyncMock()
        mock_resp.status = 500
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)

        api = PypiApi(mock_session)
        info = await api.get_project_info("birec")
        assert info is None
