"""Tests for WebSocket endpoints and middleware (§7.4, §5.14)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import HTMLResponse, PlainTextResponse

from birec.event import EventCenter, VideoFileCreatedEvent, VideoFileCreatedEventData
from birec.exception import ExceptionCenter
from birec.task import RecordTaskManager
from birec.web import (
    BaseHrefMiddleware,
    RouteRedirectMiddleware,
    create_app,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def app() -> FastAPI:
    application = create_app()
    application.state.task_manager = RecordTaskManager()
    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


# ── WebSocket /ws/v1/events ──────────────────────────────────────────────────


class TestWsEvents:
    def test_connect_and_receive_event(self, client: TestClient) -> None:
        """Connect to WS, submit an event, verify it's received."""
        event_center = EventCenter.get_instance()

        with client.websocket_connect("/ws/v1/events") as ws:
            # Submit an event
            event = VideoFileCreatedEvent.from_data(
                VideoFileCreatedEventData(room_id=1234, path="/tmp/test.flv")
            )
            event_center.submit(event)

            # Receive the event
            data = ws.receive_json()
            assert data["type"] == "VideoFileCreatedEvent"
            assert data["data"]["room_id"] == 1234
            assert data["data"]["path"] == "/tmp/test.flv"

    def test_connect_disconnect(self, client: TestClient) -> None:
        """Connect and disconnect cleanly."""
        with client.websocket_connect("/ws/v1/events"):
            pass  # Just connect and disconnect


# ── WebSocket /ws/v1/exceptions ──────────────────────────────────────────────


class TestWsExceptions:
    def test_connect_and_receive_exception(self, client: TestClient) -> None:
        """Connect to WS, submit an exception, verify it's received."""
        exception_center = ExceptionCenter.get_instance()

        with client.websocket_connect("/ws/v1/exceptions") as ws:
            # Submit an exception
            exc = ValueError("Test error message")
            exception_center.submit(exc)

            # Receive the exception
            data = ws.receive_json()
            assert data["type"] == "ValueError"
            assert data["message"] == "Test error message"
            assert "traceback" in data

    def test_connect_disconnect(self, client: TestClient) -> None:
        """Connect and disconnect cleanly."""
        with client.websocket_connect("/ws/v1/exceptions"):
            pass


# ── BaseHrefMiddleware ────────────────────────────────────────────────────────


class TestBaseHrefMiddleware:
    def test_injects_base_tag(self) -> None:
        """Base tag is injected after <head>."""
        app = FastAPI()
        app.add_middleware(BaseHrefMiddleware, base_href="/birec")

        @app.get("/test")
        async def test_page() -> HTMLResponse:
            return HTMLResponse("<html><head></head><body>Hello</body></html>")

        client = TestClient(app)
        resp = client.get("/test")
        assert '<base href="/birec/">' in resp.text

    def test_no_injection_for_non_html(self) -> None:
        """Non-HTML responses are not modified."""
        app = FastAPI()
        app.add_middleware(BaseHrefMiddleware, base_href="/birec")

        @app.get("/api")
        async def api_endpoint() -> PlainTextResponse:
            return PlainTextResponse("plain text")

        client = TestClient(app)
        resp = client.get("/api")
        assert "<base" not in resp.text

    def test_handles_head_with_attributes(self) -> None:
        """Base tag is injected after <head ...> with attributes."""
        app = FastAPI()
        app.add_middleware(BaseHrefMiddleware, base_href="/app")

        @app.get("/test")
        async def test_page() -> HTMLResponse:
            return HTMLResponse(
                '<html><head lang="en"></head><body>Hello</body></html>'
            )

        client = TestClient(app)
        resp = client.get("/test")
        assert '<base href="/app/">' in resp.text


# ── RouteRedirectMiddleware ──────────────────────────────────────────────────


class TestRouteRedirectMiddleware:
    @staticmethod
    def _index(tmp_path: Path) -> Path:
        """A minimal SPA entry document on disk."""
        index = tmp_path / "index.html"
        index.write_text("<html><body>SPA</body></html>", encoding="utf-8")
        return index

    def test_api_not_redirected(self, tmp_path: Path) -> None:
        """API paths are not redirected."""
        app = FastAPI()
        app.add_middleware(RouteRedirectMiddleware, index_file=self._index(tmp_path))

        @app.get("/api/v1/test")
        async def api_endpoint() -> dict[str, str]:
            return {"status": "ok"}

        client = TestClient(app)
        resp = client.get("/api/v1/test")
        assert resp.status_code == 200

    def test_static_assets_not_redirected(self, tmp_path: Path) -> None:
        """Static asset paths (with extensions) are not redirected."""
        app = FastAPI()
        app.add_middleware(RouteRedirectMiddleware, index_file=self._index(tmp_path))

        @app.get("/static/app.js")
        async def static_js() -> PlainTextResponse:
            return PlainTextResponse("console.log('hi')")

        client = TestClient(app)
        resp = client.get("/static/app.js")
        assert resp.status_code == 200

    def test_404_serves_index_without_redirect(self, tmp_path: Path) -> None:
        """Non-API 404 routes get the SPA shell at the requested URL."""
        app = FastAPI()
        app.add_middleware(RouteRedirectMiddleware, index_file=self._index(tmp_path))

        client = TestClient(app, follow_redirects=False)
        resp = client.get("/some/spa/route", headers={"Accept": "text/html"})
        assert resp.status_code == 200
        assert "SPA" in resp.text
        assert "location" not in resp.headers
        assert resp.url.path == "/some/spa/route"

    def test_missing_index_leaves_404(self, tmp_path: Path) -> None:
        """Without a build on disk the 404 is preserved (API-only deploys)."""
        app = FastAPI()
        app.add_middleware(RouteRedirectMiddleware, index_file=tmp_path / "absent.html")

        client = TestClient(app, follow_redirects=False)
        resp = client.get("/some/spa/route", headers={"Accept": "text/html"})
        assert resp.status_code == 404

    def test_non_html_accept_not_redirected(self, tmp_path: Path) -> None:
        """Requests not accepting HTML are not redirected."""
        app = FastAPI()
        app.add_middleware(RouteRedirectMiddleware, index_file=self._index(tmp_path))

        client = TestClient(app, follow_redirects=False)
        resp = client.get("/some/route", headers={"Accept": "application/json"})
        assert resp.status_code == 404
