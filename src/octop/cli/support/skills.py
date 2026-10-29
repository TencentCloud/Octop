"""Offline CLI helpers for per-agent skills (no HTTP / login)."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
from typing import Any

from octop.cli.repl.embedded_session import embedded_runtime
from octop.infra.agents.manager import skills_disabled_set
from octop.infra.errors import ErrorCode, OctopError


def _run_sync(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


async def list_skills_async(agent_id: str) -> list[dict[str, Any]]:
    """List installed skills via a short-lived embedded OctopServer."""
    async with embedded_runtime() as server:
        assert server.app_runtime is not None
        return await server.app_runtime.agent_registry.list_skill_summaries(agent_id)


def list_skills_offline(agent_id: str) -> list[dict[str, Any]]:
    return _run_sync(list_skills_async(agent_id))


def set_skill_enabled(agent_id: str, name: str, *, enabled: bool) -> None:
    """Toggle a skill slug in ``config_json`` (persisted to SQLite)."""
    from octop.cli.support.db import open_cli_services

    with open_cli_services() as svc:
        row = svc.agent_repo.get(agent_id)
        if row is None:
            raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not found")
        raw = row.config_json or "{}"
        try:
            cfg = json.loads(raw)
        except json.JSONDecodeError:
            cfg = {}
        if not isinstance(cfg, dict):
            cfg = {}
        disabled = skills_disabled_set(cfg)
        if enabled:
            disabled.discard(name)
        else:
            disabled.add(name)
        cfg["skills_disabled"] = sorted(disabled)
        svc.agent_repo.update_config(agent_id, config_json=json.dumps(cfg))
