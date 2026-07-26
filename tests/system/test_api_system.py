"""System tests for the HTTP API surface (driven via ASGITransport)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI
    from httpx import AsyncClient


class TestAppInfoEndpoint:
    async def test_get_app_info(self, async_client: AsyncClient) -> None:
        resp = await async_client.get("/api/v1/app/info")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["name"] == "bili-rec"
        assert "version" in body["data"]


class TestTasksEndpoint:
    async def test_get_tasks_data(self, async_client: AsyncClient) -> None:
        resp = await async_client.get("/api/v1/tasks/data")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["tasks"] == []


class TestSettingsEndpoint:
    async def test_get_settings(self, async_client: AsyncClient) -> None:
        resp = await async_client.get("/api/v1/settings")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0


class TestErrorHandlers:
    async def test_unknown_route_returns_404_body(
        self, async_client: AsyncClient
    ) -> None:
        resp = await async_client.get("/api/v1/does-not-exist")
        assert resp.status_code == 404
        body = resp.json()
        assert body["code"] == 404
        assert body["message"] == "Not Found"

    def test_403_handler_registered(self, app: FastAPI) -> None:
        assert 403 in app.exception_handlers

    def test_404_handler_registered(self, app: FastAPI) -> None:
        assert 404 in app.exception_handlers
