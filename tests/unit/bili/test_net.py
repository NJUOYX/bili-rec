"""Tests for birec.bili.net."""

from __future__ import annotations

import socket

import aiohttp
import pytest

from birec.bili.net import get_connector, timeout


class TestNet:
    async def test_connector_is_tcp(self) -> None:
        conn = get_connector()
        assert isinstance(conn, aiohttp.TCPConnector)

    async def test_connector_limit(self) -> None:
        conn = get_connector()
        assert conn.limit == 200

    def test_timeout_total(self) -> None:
        assert isinstance(timeout, aiohttp.ClientTimeout)
        assert timeout.total == 10

    async def test_default_family_allows_ipv6(self) -> None:
        conn = get_connector()
        assert conn._family == 0  # noqa: SLF001

    async def test_connector_reused(self) -> None:
        c1 = get_connector()
        c2 = get_connector()
        assert c1 is c2

    async def test_ipv4_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import importlib

        from birec.bili import net

        monkeypatch.setenv("BIREC_IPV4", "1")
        importlib.reload(net)
        try:
            conn = net.get_connector()
            assert conn._family == socket.AF_INET  # noqa: SLF001
        finally:
            monkeypatch.delenv("BIREC_IPV4", raising=False)
            importlib.reload(net)
