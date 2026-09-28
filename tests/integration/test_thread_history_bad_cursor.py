"""Bad ``cursor`` values on the thread-history endpoint must be a 400, not a 500."""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from tests.support.app import octop_client, write_octop_config
from tests.support.auth import auth_header, bootstrap_admin, create_agent, seed_openai_provider
from tests.support.fakes import FakeHarnessAgent


@pytest.fixture
async def env(tmp_octop_home: Path) -> AsyncIterator[Any]:
    """Server with the documented ``history_v2_enabled`` feature turned on."""
    write_octop_config(tmp_octop_home, history_v2_enabled=True)
    fake = FakeHarnessAgent(chunks=[{"type": "token", "node": "agent", "content": "Hi."}])
    async with octop_client(tmp_octop_home, fake_agent=fake) as (c, srv):
        await bootstrap_admin(c, tmp_octop_home)
        admin = await auth_header(c)
        await seed_openai_provider(c, admin)
        aid = await create_agent(c, admin)
        created = await c.post(f"/api/agents/{aid}/threads", headers=admin)
        assert created.status_code == 201, created.text
        yield c, srv, admin, aid, created.json()["thread_id"]


def _legacy_cursor(thread: str, before: int = 2) -> str:
    payload = {"thread": thread, "source": "projection", "before": before}
    return "legacy:" + base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


async def test_history_accepts_the_cursor_it_issued(env: Any) -> None:
    """Control: a cursor the server handed out keeps working (contract in docs)."""
    c, _srv, admin, aid, tid = env
    first = await c.get(f"/api/agents/{aid}/threads/{tid}/history", headers=admin)
    assert first.status_code == 200
    assert first.json()["next_cursor"] is None


@pytest.mark.parametrize(
    ("cursor", "reason"),
    [
        ("garbage", "not a segment id"),
        ("AAAA", "undecodable segment id"),
        (_legacy_cursor("another-thread"), "legacy cursor for another thread"),
        ("legacy:not-base64!!", "undecodable legacy cursor"),
        (_legacy_cursor("t", before="x"), "legacy cursor with a non-integer anchor"),
    ],
)
async def test_rejected_cursor_is_400(env: Any, cursor: str, reason: str) -> None:
    c, _srv, admin, aid, tid = env
    r = await c.get(
        f"/api/agents/{aid}/threads/{tid}/history",
        headers=admin,
        params={"cursor": cursor},
    )
    assert r.status_code == 400, f"{reason}: {r.status_code} {r.text}"
    assert r.json()["error"]["code"] == "SLASH_BAD_ARGS"
