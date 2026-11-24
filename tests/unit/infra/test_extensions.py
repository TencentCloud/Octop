"""``octop.extensions`` entry points: lifecycle, routes, and public paths."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import APIRouter
from tests.support.app import ensure_control_plane_bound

from octop.api.app import build_app
from octop.infra import extensions
from octop.infra.extensions import PublicPaths, extension_public_paths, load_extensions
from octop.infra.server import OctopServer


class _Demo:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def on_startup(self, server: Any) -> None:
        assert server.services is not None
        self.events.append("startup")

    async def on_shutdown(self, server: Any) -> None:
        assert server.services is not None, "database must still be open"
        self.events.append("shutdown")

    def configure_app(self, app: Any, server: Any) -> None:
        router = APIRouter()

        @router.get("/api/demo/ping")
        async def ping() -> dict[str, str]:
            return {"pong": "yes"}

        @router.get("/api/demo/private")
        async def private() -> dict[str, str]:
            return {"secret": "yes"}

        app.include_router(router)

    def public_paths(self) -> PublicPaths:
        return PublicPaths(exact=("/api/demo/ping",), setup_exact=("/api/demo/ping",))


def _entry(name: str, obj: Any = None, error: Exception | None = None) -> SimpleNamespace:
    def load() -> Any:
        if error is not None:
            raise error
        return obj

    return SimpleNamespace(name=name, load=load)


@pytest.fixture()
def demo(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Demo]:
    ext = _Demo()
    entries = [_entry("demo", ext), _entry("broken", error=ImportError("nope"))]
    monkeypatch.setattr(extensions, "entry_points", lambda group: entries)
    load_extensions.cache_clear()
    extension_public_paths.cache_clear()
    yield ext
    load_extensions.cache_clear()
    extension_public_paths.cache_clear()


def test_broken_extension_is_skipped(demo: _Demo) -> None:
    assert [e.name for e in load_extensions()] == ["demo"]


def test_public_paths_must_stay_under_api(monkeypatch: pytest.MonkeyPatch, demo: _Demo) -> None:
    monkeypatch.setattr(demo, "public_paths", lambda: PublicPaths(prefixes=("/",)))
    with pytest.raises(ValueError, match="not under /api/"):
        extension_public_paths()


@pytest.mark.asyncio
async def test_open_before_setup_and_without_jwt(demo: _Demo, tmp_path: Path) -> None:
    server = OctopServer(home=tmp_path)
    await server.start()
    await ensure_control_plane_bound(server)
    app = build_app(server)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # No user exists yet: setup lockdown lets the declared path through.
        ping = await client.get("/api/demo/ping")
        private = await client.get("/api/demo/private")
    await server.stop()

    assert ping.status_code == 200
    assert ping.json() == {"pong": "yes"}
    assert private.status_code == 503
    assert demo.events == ["startup", "shutdown"]


@pytest.mark.asyncio
async def test_undeclared_route_still_needs_jwt(demo: _Demo, tmp_path: Path) -> None:
    from tests.support.auth import bootstrap_admin

    server = OctopServer(home=tmp_path)
    await server.start()
    await ensure_control_plane_bound(server)
    app = build_app(server)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        await bootstrap_admin(client, tmp_path)
        ping = await client.get("/api/demo/ping")
        private = await client.get("/api/demo/private")
    await server.stop()

    assert ping.status_code == 200
    assert private.status_code == 401
