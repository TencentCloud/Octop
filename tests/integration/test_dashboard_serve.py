"""tests/integration/test_dashboard_serve.py"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from octop.api.app import build_app
from tests.support.app import octop_client

_DASHBOARD = Path(__file__).resolve().parents[2] / "src" / "octop" / "dashboard"


async def test_root_serves_dashboard_index(tmp_octop_home: Path) -> None:
    async with octop_client(tmp_octop_home) as (_client, srv):
        app = build_app(srv)
        with TestClient(app) as c:
            r = c.get("/")
            assert r.status_code in (200, 404)
            r2 = c.get("/api/health")
            assert r2.status_code == 200


async def test_dashboard_shell_is_not_cached(tmp_octop_home: Path) -> None:
    async with octop_client(tmp_octop_home) as (_client, srv):
        app = build_app(srv)
        with TestClient(app) as c:
            for path in ("/", "/index.html", "/sw.js", "/chat"):
                r = c.get(path)
                if r.status_code != 200:
                    continue
                assert "no-cache" in r.headers.get("cache-control", ""), path


async def test_hashed_dashboard_assets_are_immutable(tmp_octop_home: Path) -> None:
    asset_dir = _DASHBOARD / "assets"
    sample = next(asset_dir.glob("*.js"), None)
    if sample is None:
        return
    async with octop_client(tmp_octop_home) as (_client, srv):
        app = build_app(srv)
        with TestClient(app) as c:
            r = c.get(f"/assets/{sample.name}")
            assert r.status_code == 200
            assert r.headers.get("cache-control") == "public, max-age=31536000, immutable"


async def test_missing_hashed_asset_returns_404(tmp_octop_home: Path) -> None:
    if not (_DASHBOARD / "index.html").exists():
        return
    async with octop_client(tmp_octop_home) as (_client, srv):
        app = build_app(srv)
        with TestClient(app) as c:
            # A stale shell asks for a deleted chunk; answering with index.html
            # would make the browser reject HTML as a module script.
            r = c.get("/assets/index.deadbeef.js")
            assert r.status_code == 404


async def test_path_traversal_is_blocked(tmp_octop_home: Path) -> None:
    async with octop_client(tmp_octop_home) as (_client, srv):
        app = build_app(srv)
        with TestClient(app) as c:
            # Percent-encoded and literal `..` must not escape the dashboard
            # root; the SPA fallback must serve index.html (or 404), never a
            # file outside the dashboard directory.
            for encoded in ("/%2e%2e%2f%2e%2e%2fetc%2fpasswd", "/..%2f..%2fetc%2fpasswd"):
                r = c.get(encoded)
                assert r.status_code in (200, 404)
                assert "root:" not in r.text
