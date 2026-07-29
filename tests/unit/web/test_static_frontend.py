"""Unit tests: frontend static hosting + SPA fallback + base-href (§12)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from birec.web import (
    _resolve_static_dir,  # type: ignore[attr-defined]
    create_app,
)

INDEX_HTML = "<html><head></head><body>BIREC-APP</body></html>"


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

    def test_spa_deep_link_falls_back_to_index(self, dist: Path) -> None:
        """Extension-less HTML GET that 404s → 302 to /index.html (§5.14)."""
        app = create_app(static_dir=dist)
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/tasks/23058", headers={"Accept": "text/html"})
        assert resp.status_code == 302
        assert resp.headers["location"] == "/index.html"

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

    def test_no_base_href_at_root(self, dist: Path) -> None:
        app = create_app(static_dir=dist, base_href="")
        client = TestClient(app)
        resp = client.get("/")
        assert "<base" not in resp.text


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
