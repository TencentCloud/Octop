"""Embedded OctopServer helpers for CLI ops that need a live runtime."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from pathlib import Path
from typing import Any, cast

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
        await mgr.run_now(cron_id, wait=True)


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


# ── Bridge (lightweight manager; no full OctopServer) ────────────────────────


def _make_bridge_manager(svc: Any) -> Any:
    from octop.infra.bridge.manager import BridgeManager, public_base_url_from_config

    cfg = svc.config
    return BridgeManager(
        bridge_repo=svc.bridge_connection_repo,
        secret_repo=svc.secret_repo,
        user_repo=svc.user_repo,
        advertise_base_url=public_base_url_from_config(cfg.bind_host, cfg.port),
    )


def _bridge_sync(fn: Callable[[Any], Any], *, home: Path | None = None) -> Any:
    from octop.cli.support.db import open_cli_services

    with open_cli_services(home) as svc:
        return fn(_make_bridge_manager(svc))


async def _bridge_async(fn: Callable[[Any], Awaitable[Any]], *, home: Path | None = None) -> Any:
    from octop.cli.support.db import open_cli_services

    with open_cli_services(home) as svc:
        return await fn(_make_bridge_manager(svc))


async def _close_cli_session(mgr: Any, connection_id: str) -> None:
    """CLI cannot keep a Bridge WS after the process exits."""
    with suppress(Exception):
        await mgr.disconnect(connection_id)


def list_bridge_connections(
    owner_user_id: int, *, home: Path | None = None
) -> list[dict[str, Any]]:
    def _run(mgr: Any) -> Any:
        return [mgr.connection_public(r) for r in mgr.list_connections(owner_user_id)]

    return cast(list[dict[str, Any]], _bridge_sync(_run, home=home))


def get_bridge_connection(
    connection_id: str, owner_user_id: int, *, home: Path | None = None
) -> dict[str, Any]:
    def _run(mgr: Any) -> Any:
        return mgr.connection_public(mgr.get_owned(connection_id, owner_user_id))

    return cast(dict[str, Any], _bridge_sync(_run, home=home))


def probe_bridge_peer(
    *,
    peer_base_url: str,
    peer_username: str,
    password: str,
    home: Path | None = None,
) -> dict[str, Any]:
    async def _run(mgr: Any) -> Any:
        return await mgr.probe_peer(
            peer_base_url=peer_base_url,
            peer_username=peer_username,
            password=password,
        )

    return cast(dict[str, Any], asyncio.run(_bridge_async(_run, home=home)))


def probe_bridge_connection(
    connection_id: str,
    owner_user_id: int,
    *,
    peer_base_url: str | None = None,
    peer_username: str | None = None,
    password: str | None = None,
    home: Path | None = None,
) -> dict[str, Any]:
    async def _run(mgr: Any) -> Any:
        row = mgr.get_owned(connection_id, owner_user_id)
        return await mgr.probe_owned_connection(
            connection_id,
            owner_user_id=owner_user_id,
            peer_base_url=peer_base_url or row.peer_base_url,
            peer_username=peer_username or row.peer_username,
            password=password,
        )

    return cast(dict[str, Any], asyncio.run(_bridge_async(_run, home=home)))


def create_bridge_connection(
    owner_user_id: int,
    *,
    peer_base_url: str,
    peer_username: str,
    password: str,
    display_name: str,
    notes: str | None = None,
    icon_name: str | None = None,
    connect: bool = True,
    home: Path | None = None,
) -> dict[str, Any]:
    async def _run(mgr: Any) -> Any:
        row = await mgr.create_connection(
            owner_user_id=owner_user_id,
            peer_base_url=peer_base_url,
            peer_username=peer_username,
            password=password,
            display_name=display_name,
            notes=notes,
            icon_name=icon_name,
            connect=connect,
        )
        if connect:
            await _close_cli_session(mgr, row.connection_id)
            row = mgr.get_owned(row.connection_id, owner_user_id)
        return mgr.connection_public(row)

    return cast(dict[str, Any], asyncio.run(_bridge_async(_run, home=home)))


def patch_bridge_connection(
    connection_id: str,
    owner_user_id: int,
    *,
    display_name: str | None = None,
    notes: str | None = None,
    update_notes: bool = False,
    icon_name: str | None = None,
    update_icon: bool = False,
    peer_base_url: str | None = None,
    peer_username: str | None = None,
    password: str | None = None,
    auto_reconnect: bool | None = None,
    home: Path | None = None,
) -> dict[str, Any]:
    async def _run(mgr: Any) -> Any:
        cred_touch = (
            peer_base_url is not None or peer_username is not None or bool((password or "").strip())
        )
        meta_touch = any(
            (
                display_name is not None,
                update_notes,
                update_icon,
                cred_touch,
            )
        )
        opened = False
        row = mgr.get_owned(connection_id, owner_user_id)
        if meta_touch:
            row = await mgr.update_connection_meta(
                connection_id,
                owner_user_id=owner_user_id,
                display_name=display_name,
                notes=notes,
                update_notes=update_notes,
                icon_name=icon_name,
                update_icon=update_icon,
                peer_base_url=peer_base_url,
                peer_username=peer_username,
                password=password,
            )
            # Credential edits re-dial when auto_reconnect is on.
            opened = cred_touch and bool(row.auto_reconnect)
        if auto_reconnect is not None:
            row = await mgr.set_auto_reconnect(
                connection_id, owner_user_id=owner_user_id, enabled=auto_reconnect
            )
            opened = opened or bool(auto_reconnect)
        if opened:
            await _close_cli_session(mgr, connection_id)
            row = mgr.get_owned(connection_id, owner_user_id)
        return mgr.connection_public(row)

    return cast(dict[str, Any], asyncio.run(_bridge_async(_run, home=home)))


def delete_bridge_connection(
    connection_id: str, owner_user_id: int, *, home: Path | None = None
) -> None:
    async def _run(mgr: Any) -> None:
        await mgr.delete_connection(connection_id, owner_user_id=owner_user_id)

    asyncio.run(_bridge_async(_run, home=home))


def connect_bridge_connection(
    connection_id: str, owner_user_id: int, *, home: Path | None = None
) -> dict[str, Any]:
    async def _run(mgr: Any) -> Any:
        await mgr.connect(connection_id, owner_user_id=owner_user_id)
        await _close_cli_session(mgr, connection_id)
        return mgr.connection_public(mgr.get_owned(connection_id, owner_user_id))

    return cast(dict[str, Any], asyncio.run(_bridge_async(_run, home=home)))


def disconnect_bridge_connection(
    connection_id: str, owner_user_id: int, *, home: Path | None = None
) -> dict[str, Any]:
    async def _run(mgr: Any) -> Any:
        mgr.get_owned(connection_id, owner_user_id)
        await mgr.disconnect(connection_id)
        return mgr.connection_public(mgr.get_owned(connection_id, owner_user_id))

    return cast(dict[str, Any], asyncio.run(_bridge_async(_run, home=home)))


def list_bridge_remote_agents(
    connection_id: str, owner_user_id: int, *, home: Path | None = None
) -> list[dict[str, Any]]:
    async def _run(mgr: Any) -> Any:
        await mgr.connect(connection_id, owner_user_id=owner_user_id)
        try:
            return await mgr.list_remote_agents(connection_id, owner_user_id=owner_user_id)
        finally:
            await _close_cli_session(mgr, connection_id)

    return cast(list[dict[str, Any]], asyncio.run(_bridge_async(_run, home=home)))
