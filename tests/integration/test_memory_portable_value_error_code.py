"""A rejected portable-migration request must not be reported as a server fault.

``POST /api/agents/{id}/memory/portable/pack`` and ``.../adopt`` forward caller
input to ``octop-memory``, whose ``ValueError``s are "you asked for something
the store cannot satisfy" (an agent with no raw events, a file that is not a
``.hmpkg``). ``docs/api.md`` documents ``INTERNAL_ERROR`` as a 500 that is
"logged with traceback", and ``api/app.py`` only logs at ``status >= 500``, so
mapping caller input to that code leaves the client with "Internal server
error." and the operator with no log line. These tests pin the client-error
code on the caller-input branches and keep the genuine 5xx branches intact.
"""

from __future__ import annotations

import sys
from typing import Any

import pytest

from tests.support.auth import create_agent

INTERNAL = "INTERNAL_ERROR"
CLIENT = "SLASH_BAD_ARGS"


async def test_pack_agent_without_memory_is_not_internal_error(env: Any) -> None:
    c, _srv, auth = env
    agent_id = await create_agent(c, auth, name="nomemory")
    r = await c.post(
        f"/api/agents/{agent_id}/memory/portable/pack",
        headers={**auth, "Accept-Language": "en"},
    )
    assert r.status_code == 400
    body = r.json()["error"]
    assert body["code"] == CLIENT
    assert body["details"] == {"agent_id": agent_id}


async def test_adopt_corrupt_package_is_not_internal_error(env: Any) -> None:
    c, _srv, auth = env
    agent_id = await create_agent(c, auth, name="corrupt")
    r = await c.post(
        f"/api/agents/{agent_id}/memory/portable/adopt",
        headers={**auth, "Accept-Language": "en"},
        files={"pkg_file": ("notes.hmpkg", b"not a portable package", "application/octet-stream")},
        data={"target_host": "agent", "on_conflict": "skip", "dry_run": "true"},
    )
    assert r.status_code == 400
    body = r.json()["error"]
    assert body["code"] == CLIENT
    assert body["details"] == {"filename": "notes.hmpkg"}


async def test_pack_without_octop_memory_stays_internal_error(
    env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The missing-library branch keeps its 500: it is not caller input."""
    c, _srv, auth = env
    agent_id = await create_agent(c, auth, name="nolib")
    monkeypatch.setitem(sys.modules, "octop_memory.operations.migration.portable", None)
    r = await c.post(
        f"/api/agents/{agent_id}/memory/portable/pack",
        headers={**auth, "Accept-Language": "en"},
    )
    assert r.status_code == 500
    assert r.json()["error"]["code"] == INTERNAL


async def test_pack_unknown_agent_stays_not_found(env: Any) -> None:
    """Guard against over-rejecting: an unusable agent id is not a bad argument."""
    c, _srv, auth = env
    r = await c.post(
        "/api/agents/does-not-exist/memory/portable/pack",
        headers={**auth, "Accept-Language": "en"},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] != CLIENT
