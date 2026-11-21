from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
import pytest
from tests.support.app import ensure_control_plane_bound
from tests.support.auth import bearer, bootstrap_admin, login

from octop.api.app import build_app
from octop.api.routers import settings
from octop.infra.server import OctopServer
from octop.infra.utils import user_downloads


@pytest.fixture
def isolated_download_dir(repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    scratch = repo_root / ".pytest_cache"
    scratch.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="local-download-", dir=scratch) as directory:
        destination = Path(directory)
        monkeypatch.setattr(user_downloads, "downloads_dir", lambda *, home=None: destination)
        # The router holds its own reference to the function that opens the file manager.
        monkeypatch.setattr(settings, "reveal_download", lambda _path: None)
        yield destination


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


async def test_save_local_download_writes_file(client, isolated_download_dir: Path) -> None:
    c, _srv, home = client
    await bootstrap_admin(c, home)
    token = await login(c)
    response = await c.post(
        "/api/downloads/local",
        headers=bearer(token),
        files={"file": ("note.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["filename"] == "note.txt"
    saved_file = isolated_download_dir / "note.txt"
    assert Path(response.json()["path"]) == saved_file
    assert saved_file.read_bytes() == b"hello"


async def test_save_local_download_rejects_public_host(
    tmp_path: Path, isolated_download_dir: Path
) -> None:
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
            assert not any(isolated_download_dir.iterdir())
    finally:
        await srv.stop()
