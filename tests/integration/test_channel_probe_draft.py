"""Integration tests for draft channel config probe."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
async def env(env_alice_bob_agent):
    yield env_alice_bob_agent


@pytest.mark.parametrize(
    "kind,config",
    [("qq", {"app_id": "1", "client_secret": "sec"}), ("discord", {"bot_token": "fake"})],
)
async def test_probe_draft_config(env: Any, kind: str, config: dict) -> None:
    c, srv, alice_auth, _bob_auth, aid = env
    with patch.object(
        srv.app_runtime.gateway,
        "probe_config",
        new=AsyncMock(return_value={"ok": True}),
    ) as probe:
        r = await c.post(
            f"/api/agents/{aid}/channels/probe",
            headers=alice_auth,
            json={"kind": kind, "config": config},
        )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    probe.assert_awaited_once()
