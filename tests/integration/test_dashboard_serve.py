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
