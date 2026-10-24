from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from tests.support.app import ensure_control_plane_bound
from tests.support.auth import bearer, bootstrap_admin, login

from octop.api.app import build_app
from octop.api.routers import settings as settings_router
from octop.infra.server import OctopServer
from octop.infra.utils.download_links import DownloadLinkStore


@pytest.fixture
async def client(tmp_path: Path):
    srv = OctopServer(home=tmp_path)
    await srv.start()
    await ensure_control_plane_bound(srv)
    app = build_app(srv)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        yield c, tmp_path
    await srv.stop()


async def test_download_link_opens_without_credentials(client) -> None:
    c, home = client
    await bootstrap_admin(c, home)
    token = await login(c)
    created = await c.post(
        "/api/downloads/link",
        headers=bearer(token),
        files={"file": ("报告.docx", b"hello", "application/octet-stream")},
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["filename"] == "报告.docx"
    assert body["expires_in"] > 0
    assert body["url"].startswith("/api/downloads/link/")

    opened = await c.get(body["url"])
    assert opened.status_code == 200, opened.text
    assert opened.content == b"hello"
    assert opened.headers["content-type"] == "application/octet-stream"
    assert "filename*=UTF-8''%E6%8A%A5%E5%91%8A.docx" in opened.headers["content-disposition"]
    assert opened.headers["cache-control"] == "no-store"


async def test_download_link_requires_login_to_create(client) -> None:
    c, home = client
    await bootstrap_admin(c, home)
    response = await c.post(
        "/api/downloads/link",
        files={"file": ("note.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 401


async def test_unknown_download_link_is_not_found(client) -> None:
    c, home = client
    await bootstrap_admin(c, home)
    response = await c.get("/api/downloads/link/not-a-real-token")
    assert response.status_code == 404


async def test_locked_expired_file_does_not_block_a_live_download(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    c, home = client
    await bootstrap_admin(c, home)
    token = await login(c)
    clock = [1000.0]
    monkeypatch.setattr(
        "octop.infra.utils.download_links.time", SimpleNamespace(time=lambda: clock[0])
    )
    store = DownloadLinkStore(ttl_seconds=60)
    monkeypatch.setattr(settings_router, "_download_links", store)
    expired = await c.post(
        "/api/downloads/link", headers=bearer(token), files={"file": ("old.txt", b"old")}
    )
    assert expired.status_code == 200, expired.text
    old_link = store.get(expired.json()["url"].rsplit("/", 1)[-1])
    assert old_link is not None
    clock[0] = 1020
    live = await c.post(
        "/api/downloads/link", headers=bearer(token), files={"file": ("live.txt", b"live")}
    )
    assert live.status_code == 200, live.text
    clock[0] = 1060
    unlink = Path.unlink

    def locked_unlink(path: Path, *, missing_ok: bool = False) -> None:
        if path == old_link.path:
            raise PermissionError("file is in use")
        unlink(path, missing_ok=missing_ok)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", locked_unlink)
        assert (await c.get(expired.json()["url"])).status_code == 404
        downloaded = await c.get(live.json()["url"])
        assert downloaded.status_code == 200
        assert downloaded.content == b"live"

    assert (await c.get(live.json()["url"])).status_code == 200
    assert not old_link.path.exists()
