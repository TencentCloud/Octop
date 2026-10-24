"""Reload-window visibility for agent updates (#19).

``PATCH /api/agents/{id}`` persists the new config and queues a *background*
harness rebuild before answering 200. In that window the stored row already
reports the new default model while turns still reach the previous runtime —
exactly what made team probes return stale model ids with no hint anything
was pending. The agent payloads now carry ``reload_pending`` so callers and
the dashboard can wait or show a reloading state.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest


async def _wait_until(
    predicate, *, timeout: float = 5.0, interval: float = 0.05
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(interval)
    raise AssertionError("condition not met before timeout")


async def test_patch_reports_reload_pending_until_rebuild_completes(
    env_with_main_agent: tuple[Any, Any, dict[str, str], str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, srv, auth, agent_id = env_with_main_agent
    mgr = srv.app_runtime.agent_registry

    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_reload(self: Any, target_agent_id: str) -> None:
        if target_agent_id != agent_id:
            return
        started.set()
        await release.wait()

    monkeypatch.setattr(type(mgr), "_reload_agent", slow_reload)
    try:
        r = await client.patch(
            f"/api/agents/{agent_id}",
            headers=auth,
            json={"default_model": "openai:gpt-4o-mini"},
        )
        r.raise_for_status()
        body = r.json()
        assert body["default_model"] == "openai:gpt-4o-mini"
        await _wait_until(started.is_set)
        assert body["reload_pending"] is True, (
            "the PATCH response must admit the runtime rebuild is still pending"
        )

        release.set()
        await _wait_until(lambda: mgr.is_reload_pending(agent_id) is False)
    finally:
        release.set()

    detail = (await client.get(f"/api/agents/{agent_id}", headers=auth)).json()
    assert detail["reload_pending"] is False


async def test_quiescent_agent_reports_no_reload_pending(
    env_with_main_agent: tuple[Any, Any, dict[str, str], str],
) -> None:
    client, _srv, auth, agent_id = env_with_main_agent
    detail = (await client.get(f"/api/agents/{agent_id}", headers=auth)).json()
    assert detail["reload_pending"] is False
