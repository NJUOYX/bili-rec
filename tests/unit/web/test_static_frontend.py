"""Unit tests: frontend static hosting + SPA fallback + base-href (§12)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from birec.web import (
    _resolve_static_dir,  # type: ignore[attr-defined]
    create_app,
)

INDEX_HTML = (
    '<html><head></head><body>BIREC-APP<script src="./assets/app.js"></script>'
    "</body></html>"
)


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    """A minimal built-frontend directory: index.html + one asset."""
    (tmp_path / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("console.log('birec')", encoding="utf-8")
    return tmp_path


class TestStaticHosting:
    def test_api_only_when_no_build(self, tmp_path: Path) -> None:
        """Empty static dir → no mount; root path 404s as JSON."""
        app = create_app(static_dir=tmp_path)
        client = TestClient(app)
        resp = client.get("/")
        assert resp.status_code == 404
        assert resp.json()["code"] == 404

    def test_serves_index_at_root(self, dist: Path) -> None:
        app = create_app(static_dir=dist)
        client = TestClient(app)
        resp = client.get("/")
        assert resp.status_code == 200
        assert "BIREC-APP" in resp.text

    def test_serves_static_asset(self, dist: Path) -> None:
        app = create_app(static_dir=dist)
        client = TestClient(app)
        resp = client.get("/assets/app.js")
        assert resp.status_code == 200
        assert "birec" in resp.text

    def test_spa_deep_link_served_in_place(self, dist: Path) -> None:
        """Extension-less HTML GET that 404s → index.html at the same URL (§12)."""
        app = create_app(static_dir=dist)
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/tasks/23058", headers={"Accept": "text/html"})
        assert resp.status_code == 200
        assert "BIREC-APP" in resp.text
        # The deep link must survive: no redirect away from the requested path.
        assert "location" not in resp.headers
        assert resp.url.path == "/tasks/23058"

    def test_spa_deep_link_preserves_query_string(self, dist: Path) -> None:
        """Fallback keeps the query string for the client-side router."""
        app = create_app(static_dir=dist)
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/tasks?status=recording", headers={"Accept": "text/html"})
        assert resp.status_code == 200
        assert resp.url.query == b"status=recording"

    def test_api_namespace_not_shadowed(self, dist: Path) -> None:
        """Unknown API path still yields JSON 404 (not the SPA fallback)."""
        app = create_app(static_dir=dist)
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/api/v1/does-not-exist")
        assert resp.status_code == 404
        assert resp.headers["content-type"].startswith("application/json")

    def test_base_href_injected_for_subpath(self, dist: Path) -> None:
        app = create_app(static_dir=dist, base_href="/birec")
        client = TestClient(app)
        resp = client.get("/")
        assert resp.status_code == 200
        assert '<base href="/birec/">' in resp.text

    def test_base_href_recomputes_content_length(self, dist: Path) -> None:
        """Injection must refresh ``content-length`` or clients truncate HTML."""
        app = create_app(static_dir=dist, base_href="/birec")
        client = TestClient(app)
        resp = client.get("/")
        assert resp.status_code == 200
        assert int(resp.headers["content-length"]) == len(resp.content)
        assert len(resp.content) > len(INDEX_HTML)

    def test_base_href_injected_into_deep_link_fallback(self, dist: Path) -> None:
        """The SPA shell served for a deep link also carries ``<base href>``."""
        app = create_app(static_dir=dist, base_href="/birec")
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/tasks/23058", headers={"Accept": "text/html"})
        assert resp.status_code == 200
        assert '<base href="/birec/">' in resp.text
        assert int(resp.headers["content-length"]) == len(resp.content)

    def test_base_href_defaults_to_root(self, dist: Path) -> None:
        """Root deployments still get ``<base href="/">``.

        The build emits relative asset URLs (``./assets/...``); without a base
        they resolve against the requested directory, so a nested deep link
        like ``/tasks/new`` would fetch ``/tasks/assets/...`` and 404.
        """
        app = create_app(static_dir=dist, base_href="")
        client = TestClient(app)
        resp = client.get("/")
        assert '<base href="/">' in resp.text

    def test_nested_deep_link_anchors_assets_to_root(self, dist: Path) -> None:
        """A two-segment deep link keeps relative assets pointing at the root."""
        app = create_app(static_dir=dist, base_href="")
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/tasks/new", headers={"Accept": "text/html"})
        assert resp.status_code == 200
        assert '<base href="/">' in resp.text
        assert int(resp.headers["content-length"]) == len(resp.content)


class TestResolveStaticDir:
    def test_explicit_takes_precedence(self, tmp_path: Path) -> None:
        assert _resolve_static_dir(tmp_path) == tmp_path

    def test_env_used_when_no_explicit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BIREC_STATIC_DIR", str(tmp_path))
        assert _resolve_static_dir(None) == tmp_path

    def test_bundled_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BIREC_STATIC_DIR", raising=False)
        resolved = _resolve_static_dir(None)
        assert resolved.name == "static"
        assert resolved.parent.name == "web"
