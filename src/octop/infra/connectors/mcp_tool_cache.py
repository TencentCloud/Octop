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
                return await _tool.ainvoke(kwargs)

        def _call(
            _tool: Any = tool,
            _lock: asyncio.Lock = lock,
            **kwargs: Any,
        ) -> Any:
            async def _run() -> Any:
                async with _lock:
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
        wrapped.append(StructuredTool(**st_kwargs))
    return wrapped
