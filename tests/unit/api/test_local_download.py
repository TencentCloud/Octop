from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from tests.support.app import ensure_control_plane_bound
from tests.support.auth import bearer, bootstrap_admin, login

from octop.api.app import build_app
from octop.infra.server import OctopServer


@pytest.fixture
async def client(tmp_path: Path):
    srv = OctopServer(home=tmp_path)
    await srv.start()
    await ensure_control_plane_bound(srv)
    app = build_app(srv)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as c:
        yield c, srv, tmp_path
    await srv.stop()


async def test_save_local_download_writes_downloads(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    c, _srv, home = client
    downloads = home / "Downloads"
    downloads.mkdir()
    monkeypatch.setattr(
        "octop.infra.utils.user_downloads.downloads_dir",
        lambda home=None: downloads,
    )
    monkeypatch.setattr("octop.infra.utils.user_downloads.reveal_download", lambda _path: None)
    await bootstrap_admin(c, home)
    token = await login(c)
    response = await c.post(
        "/api/downloads/local",
        headers=bearer(token),
        files={"file": ("note.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["filename"] == "note.txt"
    assert (downloads / "note.txt").read_bytes() == b"hello"


async def test_save_local_download_rejects_public_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("octop.infra.utils.user_downloads.reveal_download", lambda _path: None)
    srv = OctopServer(home=tmp_path)
    await srv.start()
    await ensure_control_plane_bound(srv)
    app = build_app(srv)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as c:
            await bootstrap_admin(c, tmp_path)
            token = await login(c)
            response = await c.post(
                "/api/downloads/local",
                headers=bearer(token),
                files={"file": ("note.txt", b"hello", "text/plain")},
            )
            assert response.status_code == 403
            assert response.json()["error"]["code"] == "LOCAL_DOWNLOAD_UNAVAILABLE"
    finally:
        await srv.stop()
