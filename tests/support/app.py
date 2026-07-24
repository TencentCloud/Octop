"""OctopServer + ASGI client lifecycle for integration tests."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, nullcontext
from pathlib import Path
from typing import Any

import httpx

from octop.api.app import build_app
from octop.config import DatabaseConfig, load_config
from octop.infra.db.rebind import persist_database_config
from octop.infra.server import OctopServer
from tests.support.harness import patch_harness


def write_octop_config(home: Path, **overrides: object) -> None:
    """Ensure ``home/config.json`` exists and apply overrides (for tests)."""
    cfg_path = home / "config.json"
    load_config(cfg_path)
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    data.update(overrides)
    cfg_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


async def ensure_control_plane_bound(srv: OctopServer) -> None:
    """Bind default SQLite when greenfield start deferred the control-plane DB."""
    if srv.database_bound:
        return
    persist_database_config(srv.paths.config, DatabaseConfig())
    await srv.bind_control_plane()


@asynccontextmanager
async def octop_client(
    home: Path,
    *,
    fake_agent: Any | None = None,
    patch_llm: bool = True,
    bind_database: bool = True,
) -> AsyncIterator[tuple[httpx.AsyncClient, OctopServer]]:
    """Start OctopServer, yield ``(httpx client, server)``, then stop.

    Greenfield starts defer the control-plane DB until ``/setup/database``.
    Most tests set ``bind_database=True`` (default) to bind SQLite immediately.
    Pass ``bind_database=False`` to exercise deferred password / status paths.
    """
    ctx = patch_harness(fake_agent) if patch_llm else nullcontext(fake_agent)
    with ctx:
        srv = OctopServer(home=home)
        await srv.start()
        if bind_database and not srv.database_bound:
            await ensure_control_plane_bound(srv)
        app = build_app(srv)
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
            ) as client:
                # Expose the ASGI app so tests can open WebSocket sessions via
                # starlette's sync TestClient (httpx removed AsyncClient.websocket_connect).
                client._octop_app = app  # type: ignore[attr-defined]
                yield client, srv
        finally:
            await srv.stop()
