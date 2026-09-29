"""tests/integration/test_workspace_guard_api.py — workspace guard, real HTTP end-to-end.

``INT-1``: the only integration surface for this batch. Contract = ``PLAN.md`` §7.1
(the twelve cells: 2 protected surfaces × 3 spellings × 2 endpoints, ``from_workspace``
**omitted**) + §7.2 scope ① (the four mutating endpoints) + ``SPEC.md`` A1–A5/A13.

Requires a running harness agent (``env_with_agent``); workspace I/O goes through
``agent.workspace`` backed by ``local_shell`` on the agent dir.

★ **Locally observable only**: the assertions below hold on this host, with the
local harness backend and no remote (COS/S3/OSS/OBS) or docker ``sandbox_fs``
backend in play. The HTTP-layer symlink bypass is out of this card's scope.
"""

from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest

from octop.api.common.agent_workspace import resolve_agent_workspace_dir

# Workspace UI semantics: leading '/' is relative to the agent workspace.
FROM_WORKSPACE = {"from_workspace": "true"}

TEAM_REL = ".octop/team/LEARNINGS.md"
BUILTIN_REL = "_builtin_skills/x/SKILL.md"

# Verbatim copy, both locales (``src/octop/i18n/{zh,en}.json`` → ``errors.*``).
SURFACES: dict[str, dict[str, Any]] = {
    "team": {
        "rel": TEAM_REL,
        "status": 409,
        "code": "TEAM_ARTIFACT_OWNERSHIP_DENIED",
        "zh": "你不是该工件的归属写者。",
        "en": "You are not the owner of this artifact.",
    },
    "builtin": {
        "rel": BUILTIN_REL,
        "status": 403,
        "code": "FORBIDDEN",
        "zh": "没有权限。",
        "en": "Permission denied.",
    },
}
SHAPES = ("relative", "host_absolute", "file_url")
ENDPOINTS = ("file", "upload")
SENTINELS = {TEAM_REL: b"# team runtime owns these bytes\n", BUILTIN_REL: b"# builtin sentinel\n"}


@pytest.fixture
async def env(env_with_agent):
    yield env_with_agent


def _zip_with(entries: dict[str, bytes]) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, blob in entries.items():
            archive.writestr(name, blob)
    return buffer.getvalue()


async def _seed(env: Any, entries: dict[str, bytes]) -> None:
    """Seed through the sanctioned writer (archive restore) so bytes are observable.

    ``POST …/workspace/archive`` carries the registered ``.octop/**`` exemption
    (deliberate, kept from the previous batch — see the exemption test below), so
    it is the one writer that may place sentinels under a protected surface.
    """
    c, _srv, auth, aid = env
    r = await c.post(
        f"/api/agents/{aid}/workspace/archive",
        params={"mode": "merge"},
        headers=auth,
        files={"file": ("workspace.zip", _zip_with(entries), "application/zip")},
    )
    assert r.status_code == 200, r.text


async def _read(c: Any, auth: dict[str, str], aid: str, rel: str) -> Any:
    return await c.get(
        f"/api/agents/{aid}/workspace/file",
        params={**FROM_WORKSPACE, "path": f"/{rel}"},
        headers=auth,
    )


def _spelling(srv: Any, aid: str, rel: str, shape: str) -> str:
    """The three real spellings that reach the same host file (``RESEARCH`` §5)."""
    host = resolve_agent_workspace_dir(srv, aid) / rel
    if shape == "relative":
        return rel
    if shape == "host_absolute":
        return host.as_posix()
    return host.as_uri()


def _write_request(
    c: Any, aid: str, auth: dict[str, str], endpoint: str, path: str, locale: str
) -> Any:
    """``from_workspace`` is deliberately omitted — that is the shape under test."""
    headers = {**auth, "Accept-Language": locale}
    if endpoint == "file":
        return c.put(
            f"/api/agents/{aid}/workspace/file",
            params={"path": path},
            headers=headers,
            json={"content": "FORGED\n"},
        )
    return c.post(
        f"/api/agents/{aid}/workspace/upload",
        params={"path": path},
        headers=headers,
        files={"file": (Path(path).name, b"FORGED\n", "text/markdown")},
    )


# --- §7.1 twelve cells: 2 surfaces × 3 spellings × 2 endpoints --------------


@pytest.mark.parametrize("endpoint", ENDPOINTS, ids=["file", "upload"])
@pytest.mark.parametrize("shape", SHAPES, ids=["rel", "host_abs", "file_url"])
@pytest.mark.parametrize("surface", sorted(SURFACES), ids=["builtin", "team"])
async def test_matrix_protected_write_denied(
    env: Any, surface: str, shape: str, endpoint: str
) -> None:
    """Default ``from_workspace`` + 3 spellings ⇒ 409/403, code + copy verbatim, no write."""
    c, srv, auth, aid = env
    spec = SURFACES[surface]
    rel = spec["rel"]
    await _seed(env, SENTINELS)
    sentinel = SENTINELS[rel]

    path = _spelling(srv, aid, rel, shape)
    for locale, expected in (("zh", spec["zh"]), ("en", spec["en"])):
        r = await _write_request(c, aid, auth, endpoint, path, locale)
        assert r.status_code == spec["status"], f"{locale}: {r.text}"
        body = r.json()["error"]
        assert body["code"] == spec["code"]
        assert body["message"] == expected  # copy verbatim, not the raw guard string

    after = await _read(c, auth, aid, rel)
    assert after.status_code == 200, after.text
    assert after.json()["content"].encode("utf-8") == sentinel  # bytes unchanged, never deleted


# --- §7.2 scope ①: the four mutating endpoints ------------------------------


@pytest.mark.parametrize("folding", ["plain", "dot_slash"], ids=["plain", "dot_slash"])
@pytest.mark.parametrize("row", ["mkdir", "delete", "move_src", "move_dest", "write_doc"])
async def test_scope1_mutating_endpoints_deny_team_memory(env: Any, row: str, folding: str) -> None:
    """``mkdir`` (``POST …/workspace/mkdir``) / ``delete`` / ``move`` (src **and** dest) /
    ``write_doc`` ⇒ 409 + copy, and nothing lands on disk.

    These four hard-code ``from_workspace=True`` internally, so scope ①'s axis is
    "endpoint × folding variant", not §7.1's spelling axis (they are different matrices).
    """
    c, srv, auth, aid = env
    spec = SURFACES["team"]
    await _seed(env, SENTINELS)
    target = f"./{TEAM_REL}" if folding == "dot_slash" else TEAM_REL
    headers = {**auth, "Accept-Language": "zh"}
    readback: list[tuple[str, int]] = []  # (rel, expected status)

    if row == "mkdir":
        r = await c.post(
            f"/api/agents/{aid}/workspace/mkdir", params={"path": target}, headers=headers
        )
        assert not (resolve_agent_workspace_dir(srv, aid) / TEAM_REL).is_dir()
    elif row == "delete":
        r = await c.delete(
            f"/api/agents/{aid}/workspace/file", params={"path": target}, headers=headers
        )
        readback.append((TEAM_REL, 200))
    elif row == "move_src":
        r = await c.post(
            f"/api/agents/{aid}/workspace/move",
            params={"path": target},
            headers=headers,
            json={"destination": "notes/stolen.md"},
        )
        readback.extend([(TEAM_REL, 200), ("notes/stolen.md", 404)])
    elif row == "move_dest":
        await c.put(
            f"/api/agents/{aid}/workspace/file",
            params={**FROM_WORKSPACE, "path": "/notes/movable.txt"},
            headers=auth,
            json={"content": "keep\n"},
        )
        dest = f"./{TEAM_REL}.stolen" if folding == "dot_slash" else f"{TEAM_REL}.stolen"
        r = await c.post(
            f"/api/agents/{aid}/workspace/move",
            params={"path": "notes/movable.txt"},
            headers=headers,
            json={"destination": dest},
        )
        readback.extend([("notes/movable.txt", 200), (f"{TEAM_REL}.stolen", 404)])
    else:
        r = await c.put(
            f"/api/agents/{aid}/workspace/doc",
            params={"path": target},
            headers=headers,
            json={"content": "# forged\n"},
        )
        readback.append((TEAM_REL, 200))

    assert r.status_code == 409, f"{row}/{folding}: {r.text}"
    body = r.json()["error"]
    assert body["code"] == "TEAM_ARTIFACT_OWNERSHIP_DENIED"
    assert body["message"] == spec["zh"]
    for rel, expected in readback:
        after = await _read(c, auth, aid, rel)
        assert after.status_code == expected, f"{row}/{folding}/{rel}: {after.text}"
        if rel == TEAM_REL:
            assert after.json()["content"].encode("utf-8") == SENTINELS[TEAM_REL]


# --- positive controls: the guard must not over-reach -----------------------


@pytest.mark.parametrize("from_workspace", [False, True], ids=["default_params", "explicit_true"])
@pytest.mark.parametrize(
    "rel",
    ["SOUL.md", "outbound/a.txt", "notes/_builtin_skills/x.md", ".octop/sessions/state.db"],
    ids=["soul", "outbound", "nested_builtin_name", "octop_sessions"],
)
async def test_ordinary_paths_still_allowed(env: Any, rel: str, from_workspace: bool) -> None:
    """Positive control, both parameter modes.

    ``notes/_builtin_skills/x.md`` is the ``FIND-3`` case: the protected name appears
    **not as a leading segment**, so it must stay writable (a "any segment equals"
    criterion would break it). ``.octop/sessions/state.db`` is an ``.octop`` sibling
    that is *not* team memory.
    """
    c, _srv, auth, aid = env
    params = {"path": f"/{rel}"} if from_workspace else {"path": rel}
    if from_workspace:
        params["from_workspace"] = "true"
    payload = "guard positive control\n"
    r = await c.put(
        f"/api/agents/{aid}/workspace/file", params=params, headers=auth, json={"content": payload}
    )
    assert r.status_code == 200, r.text
    back = await _read(c, auth, aid, rel)
    assert back.status_code == 200, back.text
    assert back.json()["content"] == payload


async def test_archive_import_exemption_still_writes_team_memory(env: Any) -> None:
    """★ The archive-restore exemption is **intentional**, not a leftover gap.

    The previous batch ruled that workspace archive import is the sanctioned writer
    for ``.octop/**`` (team memory restore path), so this endpoint must keep writing
    team memory: 200 and readable back. Pinned here so a later widening of the guard
    cannot silently break the restore path.
    """
    c, _srv, auth, aid = env
    blob = b"# restored by archive\n"
    r = await c.post(
        f"/api/agents/{aid}/workspace/archive",
        params={"mode": "merge"},
        headers=auth,
        files={"file": ("workspace.zip", _zip_with({TEAM_REL: blob}), "application/zip")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["imported"] == 1
    back = await _read(c, auth, aid, TEAM_REL)
    assert back.status_code == 200, back.text
    assert back.json()["content"].encode("utf-8") == blob
