"""LangGraph runtime helpers shared across middleware."""

from __future__ import annotations

from typing import Any, cast

from langchain.agents.middleware import ModelRequest
from langgraph.config import get_config


def runtime_config(request: ModelRequest) -> dict[str, Any]:
    """Return the current graph ``RunnableConfig`` for middleware.

    LangGraph v0.6+ injects per-run settings via :func:`langgraph.config.get_config`.
    ``ModelRequest.runtime`` is a :class:`langgraph.runtime.Runtime` with ``context``,
    not ``config`` — do not read ``runtime.config``.
    """
    try:
        config = get_config()
        if isinstance(config, dict):
            configurable = config.get("configurable")
            if isinstance(configurable, dict) and (
                configurable.get("mcp_servers") is not None or configurable.get("mcp_use_default")
            ):
                return cast(dict[str, Any], config)
    except RuntimeError:
        pass

    runtime = getattr(request, "runtime", None)
    context = getattr(runtime, "context", None) if runtime is not None else None
    if isinstance(context, dict) and (context.get("mcp_servers") is not None or context.get("mcp_use_default")):
        return {"configurable": context}

    try:
        config = get_config()
        if isinstance(config, dict):
            configurable = config.get("configurable")
            if isinstance(configurable, dict) and configurable:
                return cast(dict[str, Any], config)
    except RuntimeError:
        pass

    if runtime is not None:
        runtime_config_value = getattr(runtime, "config", None)
        if isinstance(runtime_config_value, dict):
            return cast(dict[str, Any], runtime_config_value)
        configurable = getattr(runtime, "configurable", None)
        if isinstance(configurable, dict):
            return {"configurable": configurable}
    return {}


__all__ = ["runtime_config"]
