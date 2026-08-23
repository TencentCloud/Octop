"""Integration tests for /api/filesystem (host root_dir pickers)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
import pytest

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX root '/' probe behavior")


@pytest.mark.asyncio
async def test_list_host_dirs_requires_auth(
    env: tuple[httpx.AsyncClient, Any, dict[str, str]],
) -> None:
    client, _srv, _auth = env
    r = await client.get("/api/filesystem/dirs")
    assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_list_host_dirs_lists_children(
    env_admin_client: tuple[httpx.AsyncClient, dict[str, str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, auth = env_admin_client
    (tmp_path / "alpha").mkdir()
    (tmp_path / "beta").mkdir()
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")

    monkeypatch.setattr(
        "octop.infra.utils.host_dirs.normalize_host_path",
        lambda path: Path(path).resolve(),
    )

    r = await client.get(
        f"/api/filesystem/dirs?path={tmp_path.as_posix()}",
        headers=auth,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == tmp_path.resolve().as_posix()
    names = [entry["name"] for entry in body["entries"]]
    assert {"alpha", "beta"}.issubset(names)


@pytest.mark.asyncio
async def test_list_host_dirs_rejects_proc(
    env_admin_client: tuple[httpx.AsyncClient, dict[str, str]],
) -> None:
    client, auth = env_admin_client
    r = await client.get("/api/filesystem/dirs?path=/proc", headers=auth)
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "WORKSPACE_OP_UNSUPPORTED"


@pytest.mark.asyncio
async def test_probe_host_dir_requires_auth(
    env: tuple[httpx.AsyncClient, Any, dict[str, str]],
) -> None:
    client, _srv, _auth = env
    r = await client.post("/api/filesystem/probe", json={"path": "/"})
    assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_ensure_bwrap_requires_auth(
    env: tuple[httpx.AsyncClient, Any, dict[str, str]],
) -> None:
    client, _srv, _auth = env
    r = await client.post("/api/filesystem/ensure-bwrap")
    assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_ensure_bwrap_returns_status_shape(
    env_admin_client: tuple[httpx.AsyncClient, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, auth = env_admin_client
    monkeypatch.setattr(
        "octop.api.routers.filesystem.ensure_bubblewrap",
        lambda: {"status": "skipped", "reason": "not_linux", "detail": "test"},
    )
    r = await client.post("/api/filesystem/ensure-bwrap", headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "skipped"
    assert body["reason"] == "not_linux"
    assert "detail" in body


@pytest.mark.asyncio
async def test_filesystem_defaults_for_admin(
    env_admin_client: tuple[httpx.AsyncClient, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from octop.infra.utils.host_dirs import host_fs_tree_root

    client, auth = env_admin_client
    home = tmp_path / "os_home"
    home.mkdir()
    monkeypatch.setattr("octop.infra.utils.host_dirs.Path.home", lambda: home)

    r = await client.get("/api/filesystem/defaults", headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["home"] == home.resolve().as_posix()
    assert body["default_root_dir"] == home.resolve().as_posix()
    assert body["allow_outside_home"] is True
    assert body["tree_root"] == host_fs_tree_root(allow_outside_home=True)


@pytest.mark.asyncio
async def test_non_admin_can_list_outside_home(
    env: tuple[httpx.AsyncClient, Any, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from octop.infra.utils.host_dirs import host_fs_tree_root
    from tests.support.auth import create_user

    client, _srv, admin_auth = env
    home = tmp_path / "os_home"
    home.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setattr("octop.infra.utils.host_dirs.Path.home", lambda: home)

    user_auth = await create_user(client, admin_auth, username="alice", password="TestPass12")

    defaults = await client.get("/api/filesystem/defaults", headers=user_auth)
    assert defaults.status_code == 200, defaults.text
    body = defaults.json()
    assert body["allow_outside_home"] is True
    assert body["default_root_dir"] == home.resolve().as_posix()
    assert body["tree_root"] == host_fs_tree_root(allow_outside_home=True)

    listed = await client.get(
        f"/api/filesystem/dirs?path={outside.as_posix()}",
        headers=user_auth,
    )
    assert listed.status_code == 200, listed.text

    ok = await client.get(
        f"/api/filesystem/dirs?path={home.as_posix()}",
        headers=user_auth,
    )
    assert ok.status_code == 200, ok.text

    probe = await client.post(
        "/api/filesystem/probe",
        headers=user_auth,
        json={"path": outside.as_posix()},
    )
    assert probe.status_code == 200, probe.text
    assert probe.json()["ok"] is True


@pytest.mark.asyncio
@posix_only
async def test_probe_host_dir_ok_for_slash(
    env_admin_client: tuple[httpx.AsyncClient, dict[str, str]],
) -> None:
    client, auth = env_admin_client
    r = await client.post("/api/filesystem/probe", headers=auth, json={"path": "/"})
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "path": "/"}


@pytest.mark.asyncio
async def test_probe_host_dir_ok_for_writable_dir(
    env_admin_client: tuple[httpx.AsyncClient, dict[str, str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, auth = env_admin_client
    monkeypatch.setattr(
        "octop.infra.utils.host_dirs.normalize_host_path",
        lambda path: Path(path).resolve(),
    )

    r = await client.post(
        "/api/filesystem/probe",
        headers=auth,
        json={"path": str(tmp_path)},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "path": tmp_path.resolve().as_posix()}


@pytest.mark.asyncio
async def test_probe_host_dir_rejects_file(
    env_admin_client: tuple[httpx.AsyncClient, dict[str, str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, auth = env_admin_client
    file_path = tmp_path / "notes.txt"
    file_path.write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        "octop.infra.utils.host_dirs.normalize_host_path",
        lambda path: Path(path).resolve(),
    )

    r = await client.post(
        "/api/filesystem/probe",
        headers=auth,
        json={"path": str(file_path)},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is False
    assert body["code"] == "not_directory"


@pytest.mark.asyncio
async def test_mkdir_host_dir_requires_auth(
    env: tuple[httpx.AsyncClient, Any, dict[str, str]],
) -> None:
    client, _srv, _auth = env
    r = await client.post("/api/filesystem/mkdir", json={"path": "/"})
    assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_mkdir_host_dir_creates_child(
    env_admin_client: tuple[httpx.AsyncClient, dict[str, str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, auth = env_admin_client
    monkeypatch.setattr(
        "octop.infra.utils.host_dirs.normalize_host_path",
        lambda path: Path(path).resolve(),
    )

    r = await client.post(
        "/api/filesystem/mkdir",
        headers=auth,
        json={"path": str(tmp_path), "base_name": "New Folder"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "New Folder"
    assert (tmp_path / "New Folder").is_dir()
    assert Path(body["path"]).resolve() == (tmp_path / "New Folder").resolve()


@pytest.mark.asyncio
async def test_rename_host_dir_renames_child(
    env_admin_client: tuple[httpx.AsyncClient, dict[str, str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, auth = env_admin_client
    target = tmp_path / "New Folder"
    target.mkdir()
    monkeypatch.setattr(
        "octop.infra.utils.host_dirs.normalize_host_path",
        lambda path: Path(path).resolve(),
    )

    r = await client.post(
        "/api/filesystem/rename",
        headers=auth,
        json={"path": str(target), "new_name": "workspace"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "workspace"
    assert (tmp_path / "workspace").is_dir()
    assert not target.exists()
