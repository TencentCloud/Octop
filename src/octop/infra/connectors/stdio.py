"""Persistent standard stdio MCP connections, scoped to a host conversation."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

from langchain_core.tools import ToolException
from langchain_mcp_adapters.tools import convert_mcp_tool_to_langchain_tool
from langgraph.config import get_config
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

from octop.i18n import tr
from octop.infra.connectors.mcp_tool_cache import fingerprint_mcp_spec

_IDLE_SECONDS = 600


def new_stdio_client(spec: dict[str, Any]) -> Any:
    from octop_harness import ManagedMCPClient

    return ManagedMCPClient(spec)


class StdioRuntime:
    """Reuse the SDK connection across tool calls; keep transport ownership in one task."""

    def __init__(self, service: Any, repos: Any) -> None:
        self._service, self._repos = service, repos
        self._env: dict[str, str] = {}
        self._clients: dict[tuple[int, str, str, str, str], Any] = {}
        self._locks: dict[tuple[int, str, str, str, str], asyncio.Lock] = {}
        self._timers: dict[tuple[int, str, str, str, str], asyncio.TimerHandle] = {}

    def replace_persistence(self, service: Any, repos: Any) -> None:
        self._service, self._repos = service, repos

    async def close(self, *, user_id: int | None = None, agent_id: str | None = None) -> None:
        for key in list(self._clients):
            if (user_id is None or key[0] == user_id) and (agent_id is None or key[2] == agent_id):
                await self._expire(key)

    async def _expire(self, key: tuple[int, str, str, str, str]) -> None:
        lock = self._locks.get(key)
        if lock is None:
            return
        async with lock:
            timer = self._timers.pop(key, None)
            if timer:
                timer.cancel()
            client = self._clients.pop(key, None)
            if client:
                await client.aclose()

    @asynccontextmanager
    async def session(
        self,
        user_id: int,
        instance_id: str,
        agent_id: str,
        thread_id: str,
        spec: dict[str, Any],
        *,
        client_factory: Any = new_stdio_client,
    ) -> AsyncIterator[Any]:
        key = (user_id, instance_id, agent_id, thread_id, fingerprint_mcp_spec(spec))
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            timer = self._timers.pop(key, None)
            if timer:
                timer.cancel()
            client = self._clients.get(key)
            if client is None:
                client = client_factory(spec)
                self._clients[key] = client
            try:
                yield client
            except ToolException:
                raise
            except (Exception, BaseExceptionGroup):
                self._clients.pop(key, None)
                await client.aclose()
                raise
            finally:
                if key in self._clients:
                    self._timers[key] = asyncio.get_running_loop().call_later(
                        _IDLE_SECONDS, lambda: asyncio.create_task(self._expire(key))
                    )

    async def _spec(self, user_id: int, instance_id: str) -> dict[str, Any]:
        from octop.infra.connectors.builder import _build_stdio_spec
        from octop.infra.connectors.catalog import get_catalog_entry
        from octop.infra.connectors.custom_mcp import parse_synthetic_instance_id
        from octop.infra.utils.env_file import overlay_stdio_spec_env

        custom_name = parse_synthetic_instance_id(instance_id)
        if custom_name is not None:
            configs = await asyncio.to_thread(self._service.custom_harness_configs, user_id)
            spec = configs.get(custom_name)
            if not isinstance(spec, dict) or spec.get("transport") != "stdio":
                raise ToolException(tr("connector.stdio.context_required", "en"))
        else:
            instances = await asyncio.to_thread(
                self._service.list_user_instances,
                user_id,
                active_only=True,
                with_credentials=True,
                include_shared=True,
            )
            instance = next((i for i in instances if i.instance_id == instance_id), None)
            entry = get_catalog_entry(instance.kind) if instance else None
            if entry is None or entry.mcp_mode != "stdio":
                raise ToolException(tr("connector.stdio.context_required", "en"))
            creds = await asyncio.to_thread(self._service.decrypt, instance_id)
            spec = _build_stdio_spec(entry, creds)
        return overlay_stdio_spec_env(spec, self._env)

    async def build_tools(self, *, user_id: int, instance: Any, agent_id: str) -> list[Any]:
        spec = await self._spec(user_id, instance.instance_id)
        params = StdioServerParameters(
            command=spec["command"],
            args=spec.get("args") or [],
            env={**os.environ, **(spec.get("env") or {})},
            cwd=spec.get("cwd"),
        )
        definitions: list[types.Tool] = []
        async with asyncio.timeout(25):
            async with stdio_client(params) as (read, write), ClientSession(read, write) as client:
                await client.initialize()
                cursor = None
                while True:
                    page = await client.list_tools(cursor=cursor)
                    definitions.extend(page.tools)
                    cursor = page.nextCursor
                    if cursor is None:
                        break
        session = _ScopedStdioSession(self, instance.instance_id, agent_id)
        return [
            convert_mcp_tool_to_langchain_tool(
                cast(ClientSession, session),
                definition,
                server_name=instance.mcp_server_name,
                tool_name_prefix=True,
            )
            for definition in definitions
        ]

    async def call(
        self, user_id: int, instance_id: str, agent_id: str, name: str, args: dict[str, Any]
    ) -> Any:
        config = get_config().get("configurable") or {}
        locale = str(config.get("locale") or "en")
        thread_id = str(config.get("thread_id") or "")
        row = await asyncio.to_thread(self._repos.agent_repo.get, agent_id)
        if (
            not thread_id
            or str(config.get("user") or "") != str(user_id)
            or row is None
            or row.user_id not in (None, user_id)
        ):
            raise ToolException(tr("connector.stdio.context_required", locale))
        spec = await self._spec(user_id, instance_id)
        try:
            async with self.session(user_id, instance_id, agent_id, thread_id, spec) as client:
                return await client.call_tool(
                    name, {k: v for k, v in args.items() if v is not None}
                )
        except ToolException:
            raise
        except (Exception, BaseExceptionGroup) as exc:
            raise ToolException(tr("connector.stdio.connection_failed", locale)) from exc


class _ScopedStdioSession:
    def __init__(self, runtime: StdioRuntime, instance_id: str, agent_id: str) -> None:
        self._runtime, self._instance_id, self._agent_id = runtime, instance_id, agent_id

    async def call_tool(self, name: str, arguments: dict[str, Any], **_kwargs: Any) -> Any:
        try:
            config = get_config().get("configurable") or {}
            try:
                user_id = int(config.get("user") or "")
            except (ValueError, TypeError) as exc:
                raise ToolException(tr("connector.stdio.context_required", "en")) from exc
            return await self._runtime.call(
                user_id, self._instance_id, self._agent_id, name, arguments
            )
        except ToolException as exc:
            return types.CallToolResult(
                isError=True, content=[types.TextContent(type="text", text=str(exc))]
            )
