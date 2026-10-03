"""Workspace write endpoints must never touch host-absolute paths.

The workspace API is a *workspace* API: a mutation addresses a path inside the
agent's own workspace directory, or nothing. Before this guard the six write
endpoints forwarded whatever ``_workspace_io_path()`` returned straight to the
backend, and that helper returns a host path for ``file://`` URLs and (with
``from_workspace=false``) for a leading ``/``. ``BackendWorkspace`` only applies
its ``relative_to(workspace)`` containment check to paths *without* a leading
``/``, so those spellings reached the host filesystem unchecked.

Every target below sits outside the agent workspace, so a 2xx means the guard
did not hold. Each case also asserts the target was not created / deleted, so a
status code alone cannot pass.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

FROM_WORKSPACE = {"from_workspace": "true"}


def _workspace_dir(srv: Any, aid: str) -> Path:
    return Path(srv.app_runtime.agent_registry.get_agent(aid).workspace.workspace_dir)


def _agent_host_path(srv: Any, aid: str, rel: str) -> str:
    """Host-absolute path of *rel* inside the test agent's workspace."""
    return str(_workspace_dir(srv, aid) / rel)


def _file_url(host_path: str) -> str:
    """Build the ``file://`` form of a host path the way the dashboard does.

    ``as_uri()`` places the third slash and percent-escapes per platform, so a
    Windows ``C:\\…`` becomes ``file:///C:/…`` instead of ``file://C:\\…``
    (which ``urlparse`` would read as netloc ``C:``).
    """
    return Path(host_path).as_uri()


@pytest.fixture
async def env(env_with_agent: Any) -> Any:
    yield env_with_agent


@pytest.fixture
def outside(env: Any) -> Path:
    """A directory that is a *sibling* of the agent workspace (outside it)."""
    _c, srv, _auth, aid = env
    ws = _workspace_dir(srv, aid)
    out = ws.parent / f"{ws.name}-OUTSIDE"
    out.mkdir(parents=True, exist_ok=True)
    return out


# --- the six write endpoints refuse host-absolute spellings -----------------


@pytest.mark.parametrize("spelling", ["file-url", "bare-absolute"])
async def test_write_file_host_absolute_forbidden(env: Any, outside: Path, spelling: str) -> None:
    c, srv, auth, aid = env
    target = outside / "put.txt"
    query = _file_url(str(target)) if spelling == "file-url" else str(target)

    r = await c.put(
        f"/api/agents/{aid}/workspace/file",
        params={"path": query},
        headers=auth,
        json={"content": "pwned\n"},
    )
    assert r.status_code == 403, r.text
    assert not target.exists()


@pytest.mark.parametrize("spelling", ["file-url", "bare-absolute"])
async def test_upload_host_absolute_forbidden(env: Any, outside: Path, spelling: str) -> None:
    c, srv, auth, aid = env
    target = outside / "upload.txt"
    query = _file_url(str(target)) if spelling == "file-url" else str(target)

    r = await c.post(
        f"/api/agents/{aid}/workspace/upload",
        params={"path": query},
        headers=auth,
        files={"file": ("x.txt", b"pwned\n", "text/plain")},
    )
    assert r.status_code == 403, r.text
    assert not target.exists()


async def test_mkdir_host_absolute_forbidden(env: Any, outside: Path) -> None:
    c, srv, auth, aid = env
    target = outside / "mkdir-dir"

    r = await c.post(
        f"/api/agents/{aid}/workspace/mkdir",
        params={"path": _file_url(str(target))},
        headers=auth,
    )
    assert r.status_code == 403, r.text
    assert not target.exists()


async def test_delete_host_absolute_forbidden(env: Any, outside: Path) -> None:
    c, srv, auth, aid = env
    target = outside / "delete-me.txt"
    target.write_text("victim\n")

    r = await c.delete(
        f"/api/agents/{aid}/workspace/file",
        params={"path": _file_url(str(target))},
        headers=auth,
    )
    assert r.status_code == 403, r.text
    assert target.exists(), "the guard must refuse before the file is removed"


async def test_move_host_absolute_forbidden(env: Any, outside: Path) -> None:
    c, srv, auth, aid = env
    src = outside / "move-src.txt"
    src.write_text("victim\n")

    r = await c.post(
        f"/api/agents/{aid}/workspace/move",
        params={"path": _file_url(str(src))},
        headers=auth,
        json={"destination": "moved.txt"},
    )
    assert r.status_code == 403, r.text
    assert src.exists()


async def test_write_doc_host_absolute_forbidden(env: Any, outside: Path) -> None:
    c, srv, auth, aid = env
    target = outside / "doc.docx"

    r = await c.put(
        f"/api/agents/{aid}/workspace/doc",
        params={"path": _file_url(str(target))},
        headers=auth,
        json={"content": "# pwned\n"},
    )
    assert r.status_code == 403, r.text
    assert not target.exists()


async def test_write_host_absolute_outside_octop_home_forbidden(env: Any) -> None:
    """A target unrelated to the Octop tree, not just a workspace sibling.

    The sibling case could be argued away as "agent dirs are reachable anyway";
    a path outside ``~/.octop`` cannot.
    """
    c, srv, auth, aid = env
    ws = _workspace_dir(srv, aid)
    far = ws.parent.parent.parent / f"far-{aid}"  # <home>/far-<id> — outside .octop/
    far.mkdir(parents=True, exist_ok=True)
    target = far / "put.txt"

    r = await c.put(
        f"/api/agents/{aid}/workspace/file",
        params={"path": _file_url(str(target))},
        headers=auth,
        json={"content": "pwned\n"},
    )
    assert r.status_code == 403, r.text
    assert not target.exists()


async def test_write_tilde_path_forbidden(env: Any) -> None:
    """``~`` used to reach the host: the backend expands it before resolving.

    ``_workspace_io_path`` leaves ``~/x`` alone (it is neither ``file://`` nor
    host-absolute by its own test), and ``BackendWorkspace`` then returns
    ``Path(s).expanduser().resolve()`` — a host path with no containment check.
    """
    c, srv, auth, aid = env
    target = Path("~").expanduser() / f"tilde-{aid}.txt"

    r = await c.put(
        f"/api/agents/{aid}/workspace/file",
        params={"path": f"~/{target.name}"},
        headers=auth,
        json={"content": "pwned\n"},
    )
    assert r.status_code == 403, r.text
    assert not target.exists()


@pytest.mark.parametrize("spelling", ["drive-letter", "unc"])
async def test_write_windows_host_path_forbidden(env: Any, spelling: str) -> None:
    """Windows spellings are host paths too, even when the suite runs on POSIX."""
    c, _srv, auth, aid = env
    target = "c:/octop-guard-test.txt" if spelling == "drive-letter" else "\\\\host\\share\\x.txt"

    r = await c.put(
        f"/api/agents/{aid}/workspace/file",
        params={"path": target},
        headers=auth,
        json={"content": "pwned\n"},
    )
    assert r.status_code == 403, r.text


# --- workspace-relative writes keep working ---------------------------------


async def test_file_url_inside_workspace_allowed(env: Any) -> None:
    """A ``file://`` URL that resolves *inside* the workspace is still writable.

    This is the path the dashboard's dock actually takes: ``toWorkspaceApiPath``
    turns a host path into ``file://…`` (it must, so virtual ``root_dir`` nests
    resolve) and ``FilePanelContent`` PUTs to it without ``from_workspace``. A
    blanket refusal of ``file://`` would break saving a file the user opened.
    """
    c, srv, auth, aid = env
    ws = _workspace_dir(srv, aid)
    target = ws / "outbound" / "dock-saved.md"

    r = await c.put(
        f"/api/agents/{aid}/workspace/file",
        params={"path": _file_url(str(target))},
        headers=auth,
        json={"content": "saved from the dock\n"},
    )
    assert r.status_code == 200, r.text
    agent = srv.app_runtime.agent_registry.get_agent(aid)
    assert await agent.workspace.aexists("outbound/dock-saved.md") is True


async def test_workspace_relative_writes_still_work(env: Any) -> None:
    """The guard must not break ordinary workspace I/O (dashboard spellings)."""
    c, srv, auth, aid = env

    r = await c.put(
        f"/api/agents/{aid}/workspace/file",
        params={**FROM_WORKSPACE, "path": "/notes.md"},
        headers=auth,
        json={"content": "hello\n"},
    )
    assert r.status_code == 200, r.text

    r = await c.post(
        f"/api/agents/{aid}/workspace/mkdir",
        params={**FROM_WORKSPACE, "path": "/sub"},
        headers=auth,
    )
    assert r.status_code == 201, r.text

    r = await c.post(
        f"/api/agents/{aid}/workspace/upload",
        params={**FROM_WORKSPACE, "path": "/sub/up.txt"},
        headers=auth,
        files={"file": ("up.txt", b"data", "text/plain")},
    )
    assert r.status_code == 200, r.text

    r = await c.delete(
        f"/api/agents/{aid}/workspace/file",
        params={**FROM_WORKSPACE, "path": "/sub/up.txt"},
        headers=auth,
    )
    assert r.status_code == 204, r.text

    agent = srv.app_runtime.agent_registry.get_agent(aid)
    assert await agent.workspace.aexists("notes.md") is True
    assert await agent.workspace.aexists("sub") is True
    assert await agent.workspace.aexists("sub/up.txt") is False


async def test_workspace_relative_without_leading_slash_still_works(env: Any) -> None:
    """``outbound/x.md`` (no leading slash) is workspace-relative under any flag."""
    c, srv, auth, aid = env

    r = await c.put(
        f"/api/agents/{aid}/workspace/file",
        params={"path": "outbound/note.md"},
        headers=auth,
        json={"content": "hello\n"},
    )
    assert r.status_code == 200, r.text
    agent = srv.app_runtime.agent_registry.get_agent(aid)
    assert await agent.workspace.aexists("outbound/note.md") is True


# --- protected prefix is the Octop-owned root, at any spelling --------------


async def test_builtin_skills_root_still_protected(env: Any) -> None:
    """Both owned spellings are refused, including one that escapes via ``..``."""
    c, _srv, auth, aid = env
    for path in (
        "/_builtin_skills/skill-manager/SKILL.md",
        "/.octop/_builtin_skills/skill-manager/SKILL.md",
        "/sub/../_builtin_skills/skill-manager/SKILL.md",
    ):
        r = await c.put(
            f"/api/agents/{aid}/workspace/file",
            params={**FROM_WORKSPACE, "path": path},
            headers=auth,
            json={"content": "pwned\n"},
        )
        assert r.status_code == 403, f"{path}: {r.text}"


async def test_builtin_skills_name_below_root_is_writable(env: Any) -> None:
    """Only the workspace-root ``_builtin_skills`` is Octop-owned.

    A user directory that happens to share the name is ordinary content; matching
    the name at any depth would make those files impossible to write.
    """
    c, srv, auth, aid = env

    r = await c.put(
        f"/api/agents/{aid}/workspace/file",
        params={**FROM_WORKSPACE, "path": "/notes/_builtin_skills/a.md"},
        headers=auth,
        json={"content": "mine\n"},
    )
    assert r.status_code == 200, r.text
    agent = srv.app_runtime.agent_registry.get_agent(aid)
    assert await agent.workspace.aexists("notes/_builtin_skills/a.md") is True


# --- the reported path is the one that was written --------------------------


async def test_write_response_path_follows_folded_target(env: Any) -> None:
    """``/sub/../notes.md`` writes and reports ``/notes.md``, not the raw request."""
    c, srv, auth, aid = env

    r = await c.put(
        f"/api/agents/{aid}/workspace/file",
        params={**FROM_WORKSPACE, "path": "/sub/../folded.md"},
        headers=auth,
        json={"content": "hello\n"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["path"] == "/folded.md"
    agent = srv.app_runtime.agent_registry.get_agent(aid)
    assert await agent.workspace.aexists("folded.md") is True


# --- move destination and derived upload names ------------------------------


async def test_move_destination_host_absolute_forbidden(env: Any, outside: Path) -> None:
    """The destination side is guarded too, not just the source."""
    c, srv, auth, aid = env
    target = outside / "move-dest.txt"

    r = await c.post(
        f"/api/agents/{aid}/workspace/move",
        params={**FROM_WORKSPACE, "path": "/src.txt"},
        headers=auth,
        json={"destination": _file_url(str(target))},
    )
    assert r.status_code == 403, r.text
    assert not target.exists()


async def test_upload_without_path_lands_in_workspace(env: Any) -> None:
    """Omitting ``path`` derives a workspace name — the default flag must not veto it.

    ``from_workspace`` defaults to false, which makes a bare ``/name`` a host path;
    a filename the server itself derived is always workspace-relative.
    """
    c, srv, auth, aid = env

    r = await c.post(
        f"/api/agents/{aid}/workspace/upload",
        headers=auth,
        files={"file": ("derived.txt", b"data", "text/plain")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["path"] == "/derived.txt"
    agent = srv.app_runtime.agent_registry.get_agent(aid)
    assert await agent.workspace.aexists("derived.txt") is True


async def test_write_tilde_without_slash_forbidden(env: Any) -> None:
    """``~notes.md`` is a workspace name, not a home dir — never resolve it to cwd."""
    c, _srv, auth, aid = env

    r = await c.put(
        f"/api/agents/{aid}/workspace/file",
        params={"path": "~notes.md"},
        headers=auth,
        json={"content": "pwned\n"},
    )
    assert r.status_code == 403, r.text
