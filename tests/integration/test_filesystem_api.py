"""Integration tests for /api/filesystem (host root_dir pickers)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest


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
    assert body["path"] == str(tmp_path.resolve())
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
    assert r.json() == {"ok": True, "path": str(tmp_path.resolve())}


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
