"""Embedded OctopServer helpers for CLI ops that need a live runtime."""

from __future__ import annotations

import asyncio
from typing import Any

from octop.cli.repl.embedded_session import embedded_runtime
from octop.infra.agents.providers.probe import probe_provider_row
from octop.infra.errors import ErrorCode, OctopError


async def cron_run_now_async(agent_id: str, cron_id: str) -> None:
    async with embedded_runtime() as server:
        assert server.app_runtime is not None
        mgr = server.app_runtime.cron_manager
        row = mgr.get(cron_id)
        if row is None or row.agent_id != agent_id:
            raise OctopError(ErrorCode.NOT_FOUND, "cron job not found")
        await mgr.run_now(cron_id)


def cron_run_now(agent_id: str, cron_id: str) -> None:
    asyncio.run(cron_run_now_async(agent_id, cron_id))


async def agent_action_async(agent_id: str, action: str) -> None:
    async with embedded_runtime() as server:
        assert server.app_runtime is not None
        registry = server.app_runtime.agent_registry
        if action == "start":
            await registry.start(agent_id)
        elif action == "stop":
            await registry.stop(agent_id)
        elif action == "reload":
            await registry.reload(agent_id)
        else:
            raise ValueError(f"unknown agent action: {action}")


def agent_action(agent_id: str, action: str) -> None:
    asyncio.run(agent_action_async(agent_id, action))


async def fetch_thread_history_async(agent_id: str, thread_id: str, *, limit: int = 50) -> Any:
    async with embedded_runtime() as server:
        assert server.app_runtime is not None
        registry = server.app_runtime.gateway.thread_registry
        row = registry.get_thread(thread_id)
        if row is None or row.agent_id != agent_id:
            raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"thread {thread_id!r} not found")
        agents = server.app_runtime.agent_registry
        try:
            harness = agents.get_agent(agent_id)
        except OctopError:
            await agents.start(agent_id)
            harness = agents.get_agent(agent_id)
        if hasattr(harness, "aget_history"):
            return await harness.aget_history(thread_id, limit=limit)
        state = await harness.graph.aget_state({"configurable": {"thread_id": thread_id}})
        messages = (state.values or {}).get("messages") or []
        return messages[-limit:]


def fetch_thread_history(agent_id: str, thread_id: str, *, limit: int = 50) -> Any:
    return asyncio.run(fetch_thread_history_async(agent_id, thread_id, limit=limit))


async def probe_provider_async(provider_id: int, *, model_id: str | None = None) -> dict[str, Any]:
    from octop.cli.support.db import open_cli_services, resolve_cli_locale

    with open_cli_services() as svc:
        row = svc.provider_repo.get(provider_id)
        if row is None:
            raise OctopError(ErrorCode.NOT_FOUND, "provider not found")
    return await probe_provider_row(row, model_id=model_id, locale=resolve_cli_locale())


def probe_provider(provider_id: int, *, model_id: str | None = None) -> dict[str, Any]:
    return asyncio.run(probe_provider_async(provider_id, model_id=model_id))


async def test_channel_async(
    agent_id: str, channel_id: str, *, locale: str = "zh"
) -> dict[str, Any]:
    from octop.infra.utils.locale import normalize_locale

    loc = normalize_locale(locale)
    async with embedded_runtime() as server:
        assert server.app_runtime is not None
        gateway = server.app_runtime.gateway
        existing = gateway.get_channel(channel_id)
        if existing is None or existing.agent_id != agent_id:
            raise OctopError(ErrorCode.NOT_FOUND, "channel not found")
        return await gateway.probe_channel(channel_id, locale=loc)


def test_channel(agent_id: str, channel_id: str, *, locale: str = "zh") -> dict[str, Any]:
    return asyncio.run(test_channel_async(agent_id, channel_id, locale=locale))
