"""User-scoped MCP tool cache helpers (fingerprint + serialized tool wrappers)."""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any

from langchain_core.tools import StructuredTool

# Connection fields that affect the live MCP session (exclude Octop meta like enabled).
_FINGERPRINT_KEYS = (
    "transport",
    "url",
    "headers",
    "command",
    "args",
    "env",
)


def fingerprint_mcp_spec(spec: dict[str, Any]) -> str:
    """Stable short hash of a harness MCP connection spec."""
    payload: dict[str, Any] = {}
    for key in _FINGERPRINT_KEYS:
        if key not in spec:
            continue
        value = spec[key]
        if key in ("headers", "env") and isinstance(value, dict):
            payload[key] = {str(k): str(v) for k, v in sorted(value.items())}
        elif key == "args" and isinstance(value, list):
            payload[key] = [str(x) for x in value]
        else:
            payload[key] = value
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def wrap_tools_for_shared_use(tools: list[Any], lock: asyncio.Lock) -> list[Any]:
    """Return LangChain ``StructuredTool`` wrappers that serialize invoke/ainvoke.

    Must be real ``BaseTool`` instances so ``HarnessAgent.append_mcp_tools`` /
    LangGraph ``ToolNode`` accept them (plain proxies raise ValueError).
    """
    from pydantic import BaseModel, create_model

    wrapped: list[Any] = []
    for tool in tools:
        name = str(getattr(tool, "name", "") or "") or "mcp_tool"
        description = str(getattr(tool, "description", "") or "")
        args_schema = getattr(tool, "args_schema", None)
        metadata = getattr(tool, "metadata", None)
        if not (
            isinstance(args_schema, type)
            and issubclass(args_schema, BaseModel)
            or isinstance(args_schema, dict)
        ):
            args_schema = create_model(f"{name.replace('-', '_')}_Args")

        async def _acall(
            _tool: Any = tool,
            _lock: asyncio.Lock = lock,
            **kwargs: Any,
        ) -> Any:
            async with _lock:
                if isinstance(_tool, StructuredTool) and _tool.coroutine is not None:
                    return await _tool.coroutine(**kwargs)
                return await _tool.ainvoke(kwargs)

        def _call(
            _tool: Any = tool,
            _lock: asyncio.Lock = lock,
            **kwargs: Any,
        ) -> Any:
            if isinstance(_tool, StructuredTool) and _tool.func is not None:
                return _tool.func(**kwargs)

            async def _run() -> Any:
                async with _lock:
                    if isinstance(_tool, StructuredTool) and _tool.coroutine is not None:
                        return await _tool.coroutine(**kwargs)
                    return await _tool.ainvoke(kwargs)

            try:
                asyncio.get_running_loop()
            except RuntimeError:
                return asyncio.run(_run())
            return _tool.invoke(kwargs)

        st_kwargs: dict[str, Any] = {
            "name": name,
            "description": description,
            "args_schema": args_schema,
            "coroutine": _acall,
            "func": _call,
        }
        if isinstance(metadata, dict) and metadata:
            st_kwargs["metadata"] = dict(metadata)
        if isinstance(tool, StructuredTool):
            st_kwargs["response_format"] = tool.response_format
            st_kwargs["handle_tool_error"] = tool.handle_tool_error
            st_kwargs["handle_validation_error"] = tool.handle_validation_error
        wrapped.append(StructuredTool(**st_kwargs))
    return wrapped


class StdioMCPTools:
    """Load selected stdio tools and release their conversation-scoped connections."""

    def __init__(self, service: Any, repos: Any, *, root: Any = None) -> None:
        self._service, self._repos, self._root = service, repos, root
        self._runtimes: dict[str, Any] = {}

    def runtime_for(self, kind: str) -> Any:
        from octop.infra.connectors.builder import create_stdio_runtime

        if kind not in self._runtimes:
            self._runtimes[kind] = create_stdio_runtime(kind, self._service, self._repos)
        return self._runtimes[kind]

    def replace_persistence(self, service: Any, repos: Any) -> None:
        self._service, self._repos = service, repos
        for runtime in self._runtimes.values():
            runtime.replace_persistence(service, repos)

    async def close(self, *, user_id: int | None = None, agent_id: str | None = None) -> None:
        for runtime in self._runtimes.values():
            await runtime.close(user_id=user_id, agent_id=agent_id)

    async def prepare_tools(
        self, agent: Any, *, agent_id: str, user_id: int | None, names: list[str]
    ) -> None:
        import logging
        from types import SimpleNamespace

        from octop.infra.connectors.catalog import get_catalog_entry
        from octop.infra.utils.env_file import env_file_path, load_env_file

        if user_id is None:
            return
        env = (
            await asyncio.to_thread(load_env_file, env_file_path(self._root)) if self._root else {}
        )
        instances = await asyncio.to_thread(
            self._service.list_user_instances,
            user_id,
            active_only=True,
            with_credentials=True,
            include_shared=True,
        )
        selected = []
        for instance in instances:
            entry = get_catalog_entry(instance.kind)
            if entry and entry.mcp_mode == "stdio" and instance.mcp_server_name in names:
                selected.append(instance)
        custom = await asyncio.to_thread(self._service.custom_harness_configs, user_id)
        for name in names:
            spec = custom.get(name)
            if isinstance(spec, dict) and spec.get("transport") == "stdio":
                selected.append(
                    SimpleNamespace(
                        instance_id=f"custom:{name}",
                        kind="custom-mcp",
                        mcp_server_name=name,
                    )
                )
        for instance in selected:
            prefix = f"{instance.mcp_server_name}_"
            if any(t.startswith(prefix) for t in getattr(agent, "_mcp_tool_name_set", frozenset())):
                continue
            try:
                runtime = self.runtime_for(instance.kind)
                runtime._env = env
                tools = await runtime.build_tools(
                    user_id=user_id, instance=instance, agent_id=agent_id
                )
                agent.append_mcp_tools(tools)
            except (Exception, BaseExceptionGroup):
                logging.getLogger(__name__).warning(
                    "Stdio tool discovery failed for instance %s", instance.instance_id
                )
