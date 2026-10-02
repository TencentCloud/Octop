"""Integration tests for /api/filesystem (host root_dir pickers)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
import pytest

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX root '/' probe behavior")


async def _jail(client: httpx.AsyncClient, auth: dict[str, str]) -> Path:
    """The caller's effective jail root, as the server reports it.

    With no admin policy this is the app-owned ``<OCTOP_HOME>/workspaces/<uid>``
    the server creates on first use. Reading it from the endpoint keeps these
    tests asserting the contract rather than a hardcoded path.
    """
    r = await client.get("/api/filesystem/defaults", headers=auth)
    assert r.status_code == 200, r.text
    return Path(r.json()["default_root_dir"])


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
    jail = await _jail(client, auth)
    (jail / "alpha").mkdir()
    (jail / "beta").mkdir()
    (jail / "notes.txt").write_text("x", encoding="utf-8")

    monkeypatch.setattr(
        "octop.infra.utils.host_dirs.normalize_host_path",
        lambda path: Path(path).resolve(),
    )

    r = await client.get(
        f"/api/filesystem/dirs?path={jail.as_posix()}",
        headers=auth,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == jail.resolve().as_posix()
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
    client, auth = env_admin_client
    home = tmp_path / "os_home"
    home.mkdir()
    monkeypatch.setattr("octop.infra.utils.host_dirs.Path.home", lambda: home)
    monkeypatch.setenv("OCTOP_IN_CONTAINER", "0")

    r = await client.get("/api/filesystem/defaults", headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    # No admin policy: the default is app-owned and per-user, never the host root.
    assert body["default_root_dir"] == body["tree_root"]
    jail = Path(body["default_root_dir"])
    assert jail.is_dir()
    assert jail.name.isdigit()
    assert body["in_container"] is False
    assert "home" not in body
    assert "allow_outside_home" not in body


@pytest.mark.asyncio
async def test_filesystem_defaults_in_container(
    env_admin_client: tuple[httpx.AsyncClient, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client, auth = env_admin_client
    home = tmp_path / "os_home"
    home.mkdir()
    monkeypatch.setattr("octop.infra.utils.host_dirs.Path.home", lambda: home)
    monkeypatch.setenv("OCTOP_IN_CONTAINER", "1")

    r = await client.get("/api/filesystem/defaults", headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    # The per-user default applies in containers too; an admin can still
    # override it with a workspace_root_dir policy.
    jail = Path(body["default_root_dir"])
    assert jail.is_dir()
    assert body["default_root_dir"] == body["tree_root"]
    assert body["in_container"] is True
    assert "home" not in body
    assert "allow_outside_home" not in body


@pytest.mark.asyncio
async def test_non_admin_is_jailed_to_its_own_workspace_default(
    env: tuple[httpx.AsyncClient, Any, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A regular user is scoped to their own app-owned directory.

    This replaces ``test_non_admin_can_list_outside_home``, which pinned the old
    default: every authenticated user browsed from the host root, so any user
    could point an agent at any directory the server uid could read. The jail is
    now ``<OCTOP_HOME>/workspaces/<user-id>`` unless an admin configures a
    ``workspace_root_dir`` policy.
    """
    from tests.support.auth import create_user

    client, _srv, admin_auth = env
    home = tmp_path / "os_home"
    home.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setattr("octop.infra.utils.host_dirs.Path.home", lambda: home)
    monkeypatch.setenv("OCTOP_IN_CONTAINER", "0")

    user_auth = await create_user(client, admin_auth, username="alice", password="TestPass12")

    defaults = await client.get("/api/filesystem/defaults", headers=user_auth)
    assert defaults.status_code == 200, defaults.text
    body = defaults.json()
    jail = Path(body["default_root_dir"])
    assert jail.is_dir(), "the default jail is created on first use"
    assert body["tree_root"] == body["default_root_dir"] == jail.as_posix()
    assert body["in_container"] is False
    assert "home" not in body
    assert "allow_outside_home" not in body
    # Never the three forbidden fallbacks.
    assert jail.as_posix() not in {"/", home.as_posix()}
    assert str(Path.cwd().resolve()) not in jail.parents

    # A per-user directory: the admin's jail is a different path.
    admin_jail = Path(
        (await client.get("/api/filesystem/defaults", headers=admin_auth)).json()[
            "default_root_dir"
        ]
    )
    assert admin_jail != jail

    # Outside the jail is refused.
    listed = await client.get(
        f"/api/filesystem/dirs?path={outside.as_posix()}",
        headers=user_auth,
    )
    assert listed.status_code == 400, listed.text

    ok = await client.get(
        f"/api/filesystem/dirs?path={jail.as_posix()}",
        headers=user_auth,
    )
    assert ok.status_code == 200, ok.text

    probe = await client.post(
        "/api/filesystem/probe",
        headers=user_auth,
        json={"path": outside.as_posix()},
    )
    assert probe.status_code == 200, probe.text
    assert probe.json()["ok"] is False
    assert probe.json()["code"] == "outside_root"

    probe_home = await client.post(
        "/api/filesystem/probe",
        headers=user_auth,
        json={"path": home.as_posix()},
    )
    assert probe_home.json()["ok"] is False


@pytest.mark.asyncio
@posix_only
async def test_probe_host_dir_rejects_host_root(
    env_admin_client: tuple[httpx.AsyncClient, dict[str, str]],
) -> None:
    client, auth = env_admin_client
    r = await client.post("/api/filesystem/probe", headers=auth, json={"path": "/"})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is False
    assert r.json()["code"] == "outside_root"


@pytest.mark.asyncio
async def test_probe_host_dir_ok_for_writable_dir(
    env_admin_client: tuple[httpx.AsyncClient, dict[str, str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, auth = env_admin_client
    jail = await _jail(client, auth)
    target = jail / "writable"
    target.mkdir()
    monkeypatch.setattr(
        "octop.infra.utils.host_dirs.normalize_host_path",
        lambda path: Path(path).resolve(),
    )

    r = await client.post(
        "/api/filesystem/probe",
        headers=auth,
        json={"path": str(target)},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "path": target.resolve().as_posix()}


@pytest.mark.asyncio
async def test_probe_host_dir_rejects_file(
    env_admin_client: tuple[httpx.AsyncClient, dict[str, str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, auth = env_admin_client
    file_path = (await _jail(client, auth)) / "notes.txt"
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
    jail = await _jail(client, auth)
    monkeypatch.setattr(
        "octop.infra.utils.host_dirs.normalize_host_path",
        lambda path: Path(path).resolve(),
    )

    r = await client.post(
        "/api/filesystem/mkdir",
        headers=auth,
        json={"path": str(jail), "base_name": "New Folder"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "New Folder"
    assert (jail / "New Folder").is_dir()
    assert Path(body["path"]).resolve() == (jail / "New Folder").resolve()


@pytest.mark.asyncio
async def test_rename_host_dir_renames_child(
    env_admin_client: tuple[httpx.AsyncClient, dict[str, str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, auth = env_admin_client
    jail = await _jail(client, auth)
    target = jail / "New Folder"
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
    assert (jail / "workspace").is_dir()
    assert not target.exists()


@pytest.mark.asyncio
async def test_filesystem_respects_user_workspace_root(
    env: tuple[httpx.AsyncClient, Any, dict[str, str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OCTOP_IN_CONTAINER", "0")
    from tests.support.auth import TEST_PASSWORD, create_user

    client, _srv, admin_auth = env
    jail = tmp_path / "jail"
    nested = jail / "ok"
    outside = tmp_path / "outside"
    jail.mkdir()
    nested.mkdir()
    outside.mkdir()

    user_auth = await create_user(client, admin_auth, username="fs_policy", password=TEST_PASSWORD)
    listed = (await client.get("/api/users", headers=admin_auth)).json()
    uid = next(u["id"] for u in listed if u["username"] == "fs_policy")
    patched = await client.patch(
        f"/api/users/{uid}",
        headers=admin_auth,
        json={"workspace_root_dir": jail.as_posix()},
    )
    assert patched.status_code == 200, patched.text

    defaults = await client.get("/api/filesystem/defaults", headers=user_auth)
    assert defaults.status_code == 200, defaults.text
    body = defaults.json()
    assert body["tree_root"] == jail.resolve().as_posix()
    assert body["default_root_dir"] == jail.resolve().as_posix()
    assert "home" not in body
    assert "allow_outside_home" not in body

    inside = await client.get(
        f"/api/filesystem/dirs?path={nested.as_posix()}",
        headers=user_auth,
    )
    assert inside.status_code == 200, inside.text

    listed_out = await client.get(
        f"/api/filesystem/dirs?path={outside.as_posix()}",
        headers=user_auth,
    )
    assert listed_out.status_code == 400, listed_out.text

    probe = await client.post(
        "/api/filesystem/probe",
        headers=user_auth,
        json={"path": outside.as_posix()},
    )
    assert probe.status_code == 200, probe.text
    assert probe.json()["ok"] is False
    assert probe.json()["code"] == "outside_root"


@pytest.mark.asyncio
async def test_mkdir_cannot_escape_the_users_jail(
    env: tuple[httpx.AsyncClient, Any, dict[str, str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """mkdir is host-mutating, so confinement is the whole security property.

    This settles SEC-7 on the agreed basis: a user is jailed to their own
    app-owned workspace, and the write endpoints may therefore be reachable by
    any authenticated user as long as they cannot step outside that jail.
    """
    from tests.support.auth import create_user

    monkeypatch.setenv("OCTOP_IN_CONTAINER", "0")
    client, _srv, admin_auth = env
    outside = tmp_path / "outside"
    outside.mkdir()

    user_auth = await create_user(
        client, admin_auth, username="jailed_writer", password="TestPass12"
    )
    jail = await _jail(client, user_auth)

    for payload in (
        {"path": outside.as_posix(), "base_name": "escaped"},
        {"path": "/", "base_name": "escaped"},
        {"path": outside.as_posix(), "base_name": "../escaped"},
    ):
        r = await client.post("/api/filesystem/mkdir", headers=user_auth, json=payload)
        assert r.status_code == 400, (payload, r.text)
        assert r.json()["error"]["code"] == "WORKSPACE_OP_UNSUPPORTED"

    assert list(outside.iterdir()) == [], "nothing was created outside the jail"

    # Inside the jail it still works.
    ok = await client.post(
        "/api/filesystem/mkdir",
        headers=user_auth,
        json={"path": jail.as_posix(), "base_name": "mine"},
    )
    assert ok.status_code == 200, ok.text
    assert (jail / "mine").is_dir()


@pytest.mark.asyncio
async def test_rename_cannot_escape_the_users_jail(
    env: tuple[httpx.AsyncClient, Any, dict[str, str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """rename must be confined to the jail, including via a traversal new_name."""
    from tests.support.auth import create_user

    monkeypatch.setenv("OCTOP_IN_CONTAINER", "0")
    client, _srv, admin_auth = env
    outside = tmp_path / "outside"
    outside.mkdir()
    victim = outside / "victim"
    victim.mkdir()

    user_auth = await create_user(
        client, admin_auth, username="jailed_renamer", password="TestPass12"
    )
    jail = await _jail(client, user_auth)

    for path, new_name in (
        (victim.as_posix(), "renamed"),
        (jail.as_posix(), "../../outside/victim"),
        (outside.as_posix(), "renamed"),
    ):
        r = await client.post(
            "/api/filesystem/rename",
            headers=user_auth,
            json={"path": path, "new_name": new_name},
        )
        assert r.status_code == 400, (path, new_name, r.text)

    assert victim.is_dir(), "the directory outside the jail is untouched"
    assert list(outside.iterdir()) == [victim]
