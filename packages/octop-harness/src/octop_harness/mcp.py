"""MCP server configuration merge + tool loading helpers."""

from __future__ import annotations

import asyncio
import concurrent.futures
import inspect
import logging
import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from langchain_mcp_adapters.client import MultiServerMCPClient
from pydantic import BaseModel, Field, GetJsonSchemaHandler, create_model, model_validator
from pydantic_core import core_schema as pydantic_core_schema

from octop_harness.backends.utils import DEFENSIVE_OP_ERRORS
from octop_harness.runtime_env import merge_host_stdio_env

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)

_LLM_TOOL_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
_MCP_SPEC_META_KEYS = frozenset({"allowed_tools", "tool_arg_aliases"})
_RESERVED_PYDANTIC_FIELD_NAMES = frozenset(name for name in dir(BaseModel) if not name.startswith("_"))


def merge_mcp_server_configs(
    shared: dict[str, Any] | None,
    agent: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge manager-level and agent-level MCP configs (agent wins on conflict)."""
    merged = dict(shared or {})
    merged.update(agent or {})
    return merged


def validate_mcp_default_servers(
    default_servers: list[str] | None,
    available_configs: dict[str, Any],
) -> None:
    """Ensure ``mcp_default_servers`` only references configured server names."""
    if not default_servers:
        return
    unknown = sorted(set(default_servers) - set(available_configs))
    if unknown:
        raise ValueError(
            f"mcp_default_servers references unknown server(s): {unknown}; "
            f"configured servers: {sorted(available_configs)}",
        )


def sanitize_llm_tool_name(name: str) -> str:
    """Return a tool name accepted by strict LLM APIs (``^[a-zA-Z0-9_-]+$``)."""
    if _LLM_TOOL_NAME_RE.match(name):
        return name
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name)


def _pydantic_field_name(key: str, used: set[str]) -> str:
    """Map JSON Schema property names to valid Pydantic field identifiers."""
    name = key.lstrip("_") or "field"
    if name[0].isdigit() or name in _RESERVED_PYDANTIC_FIELD_NAMES:
        name = f"arg_{name}"
    while name in used or name in _RESERVED_PYDANTIC_FIELD_NAMES:
        name = f"{name}_"
    used.add(name)
    return name


def _strip_nullables_from_json_schema(schema: dict[str, Any]) -> None:
    """Omit ``null`` from optional property schemas shown to the LLM.

    MCP servers (e.g. Notion Zod) reject explicit ``null`` for optional fields —
    the key must be omitted. Advertising ``anyOf: [T, null]`` + ``default: null``
    pushes models to fill unused keys with null.
    """
    props = schema.get("properties")
    if not isinstance(props, dict):
        return
    for prop in props.values():
        if not isinstance(prop, dict):
            continue
        for key in ("anyOf", "oneOf"):
            variants = prop.get(key)
            if not isinstance(variants, list):
                continue
            non_null = [v for v in variants if not (isinstance(v, dict) and v.get("type") == "null")]
            if len(non_null) == 1 and len(variants) >= 2:
                kept = dict(non_null[0])
                desc = prop.get("description")
                title = prop.get("title")
                prop.clear()
                prop.update(kept)
                if desc and "description" not in prop:
                    prop["description"] = desc
                if title and "title" not in prop:
                    prop["title"] = title
                break
        if prop.get("default") is None:
            prop.pop("default", None)


class _McpArgsBase(BaseModel):
    """MCP arg models strip nullables from the LLM-facing JSON Schema."""

    @model_validator(mode="before")
    @classmethod
    def _drop_null_arguments(cls, data: Any) -> Any:
        """Drop explicit ``null`` before validation.

        Models often fill unused optional keys with null; required keys may also
        arrive as null. Omitting those keys lets optionals use defaults and
        surfaces a clear \"field required\" error for missing required args.
        """
        if not isinstance(data, dict):
            return data
        return {key: value for key, value in data.items() if value is not None}

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: pydantic_core_schema.CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> dict[str, Any]:
        json_schema = handler(core_schema)
        _strip_nullables_from_json_schema(json_schema)
        return json_schema


def mcp_args_model(tool_name: str, input_schema: dict[str, Any]) -> type[Any]:
    """Build a Pydantic args model from an MCP tool ``inputSchema``."""
    props = input_schema.get("properties") or {}
    if not isinstance(props, dict):
        props = {}
    required = set(input_schema.get("required") or [])

    fields: dict[str, Any] = {}
    used_names: set[str] = set()
    for key, spec in props.items():
        spec_dict: dict[str, Any] = spec if isinstance(spec, dict) else {}
        json_type = spec_dict.get("type")
        if json_type == "integer":
            py_type: Any = int
        elif json_type == "number":
            py_type = float
        elif json_type == "boolean":
            py_type = bool
        else:
            py_type = str
        desc = spec_dict.get("description")
        field_name = _pydantic_field_name(str(key), used_names)
        if field_name != key:
            field = Field(description=desc, validation_alias=key, serialization_alias=key)
        else:
            field = Field(description=desc)
        if key in required:
            fields[field_name] = (py_type, field)
        else:
            optional_field = (
                Field(default=None, description=desc, validation_alias=key, serialization_alias=key)
                if field_name != key
                else Field(default=None, description=desc)
            )
            fields[field_name] = (py_type | None, optional_field)

    model_name = re.sub(r"[^A-Za-z0-9_]", "_", tool_name)
    if not model_name or model_name[0].isdigit():
        model_name = f"Mcp_{model_name}"
    return create_model(model_name, __base__=_McpArgsBase, **fields)


def _connection_spec_loadable(spec: Any) -> bool:
    """True when *spec* looks like a remote MCP connection (has ``transport``)."""
    if not isinstance(spec, dict):
        return True
    return bool(spec.get("transport"))


async def aload_mcp_tools(configs: dict[str, Any]) -> list[BaseTool]:
    """Load LangChain tools from MCP server connection specs.

    Loads each configured server independently so one unreachable or
    misconfigured server does not prevent others from registering tools.

    If a spec contains an ``allowed_tools`` list, only tools whose base name
    (after stripping the ``{server}_`` prefix) matches an entry in that list
    are kept.  This lets callers restrict the tool surface of remote MCP
    servers without modifying the server itself.
    """
    if not configs:
        return []
    tools: list[BaseTool] = []
    for name, spec in configs.items():
        if not _connection_spec_loadable(spec):
            continue
        try:
            allowed: set[str] | None = None
            tool_arg_aliases: dict[str, dict[str, str]] = {}
            connection_spec = spec
            if isinstance(spec, dict):
                if "allowed_tools" in spec:
                    allowed = set(spec["allowed_tools"])
                raw_aliases = spec.get("tool_arg_aliases")
                if isinstance(raw_aliases, dict):
                    for tool_name, aliases in raw_aliases.items():
                        if isinstance(tool_name, str) and isinstance(aliases, dict):
                            tool_arg_aliases[tool_name] = {
                                str(alias): str(canonical)
                                for alias, canonical in aliases.items()
                                if str(alias) and str(canonical)
                            }
                # Strip Octop/harness meta keys before MultiServerMCPClient sees the spec.
                connection_spec = {k: v for k, v in spec.items() if k not in _MCP_SPEC_META_KEYS}
                if str(connection_spec.get("transport") or "").lower() == "stdio":
                    extra = connection_spec.get("env")
                    spec_env = extra if isinstance(extra, dict) else {}
                    connection_spec["env"] = merge_host_stdio_env(spec_env)
            client = MultiServerMCPClient({name: connection_spec}, tool_name_prefix=True)
            server_tools = await client.get_tools()
            if allowed is not None:
                prefix = f"{name}_"
                server_tools = [t for t in server_tools if _tool_name(t).removeprefix(prefix) in allowed]
            _postprocess_mcp_tools(
                server_tools,
                server_name=name,
                tool_arg_aliases=tool_arg_aliases,
            )
            tools.extend(server_tools)
        except DEFENSIVE_OP_ERRORS:
            logger.warning(
                "Failed to load MCP tools from server %r",
                name,
                exc_info=True,
            )
        except BaseExceptionGroup:
            # MCP SSE clients (anyio TaskGroup) wrap httpx errors in ExceptionGroup.
            logger.warning(
                "Failed to load MCP tools from server %r",
                name,
                exc_info=True,
            )
    return tools


def load_mcp_tools(configs: dict[str, Any]) -> list[BaseTool]:
    """Synchronous wrapper around :func:`aload_mcp_tools` for agent construction."""
    if not configs:
        return []
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(aload_mcp_tools(configs))
    # Construction inside a running loop (unusual for HarnessAgent.__init__).
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, aload_mcp_tools(configs)).result()


def mcp_tool_names(tools: list[Any]) -> frozenset[str]:
    """Return the set of tool names considered MCP-provided."""
    return frozenset(_tool_name(t) for t in tools if _tool_name(t))


def prioritize_active_mcp_tools(
    tools: list[Any],
    *,
    mcp_tool_names: frozenset[str],
    active_servers: list[str] | None,
) -> list[Any]:
    """Place active MCP tools immediately after builtins.

      Some providers silently truncate long tool lists. When many MCP servers are
    registered, gateway tools appended last (e.g. IMA) can be dropped unless
      they are moved ahead of inactive MCP tools.
    """
    if not active_servers:
        return list(tools)

    non_mcp: list[Any] = []
    active_by_server: dict[str, list[Any]] = {server: [] for server in active_servers}
    other_mcp: list[Any] = []
    for tool in tools:
        name = _tool_name(tool)
        if name not in mcp_tool_names:
            non_mcp.append(tool)
            continue
        matched = False
        for server in active_servers:
            if name.startswith(f"{server}_"):
                active_by_server[server].append(tool)
                matched = True
                break
        if not matched:
            other_mcp.append(tool)

    ordered_active: list[Any] = []
    for server in active_servers:
        ordered_active.extend(active_by_server[server])
    return non_mcp + ordered_active + other_mcp


def filter_tools_for_mcp_servers(
    tools: list[Any],
    *,
    mcp_tool_names: frozenset[str],
    server_names: frozenset[str],
    active_servers: list[str] | None,
) -> list[Any]:
    """Filter *tools* for the MCP servers active on this model call.

    Parameters
    ----------
    active_servers:
        ``None`` — strip all MCP tools (opt-out default).
        ``[]`` — same as ``None``.
        ``["github", ...]`` — keep non-MCP tools plus MCP tools whose names
        are prefixed with ``{server}_`` (requires ``tool_name_prefix=True``).
    """
    if not mcp_tool_names:
        return list(tools)
    if not active_servers:
        return [t for t in tools if _tool_name(t) not in mcp_tool_names]

    allowed_prefixes = tuple(f"{server}_" for server in active_servers)
    filtered: list[Any] = []
    for tool in tools:
        name = _tool_name(tool)
        if name not in mcp_tool_names:
            filtered.append(tool)
            continue
        if any(name.startswith(prefix) for prefix in allowed_prefixes):
            filtered.append(tool)
    return filtered


def resolve_active_mcp_servers(
    *,
    mcp_use_default: bool,
    mcp_servers: list[str] | None,
    default_servers: list[str] | None,
) -> list[str] | None:
    """Resolve which MCP servers are active for one invocation.

    Returns ``None`` when MCP tools should be hidden (the default).
    """
    if mcp_use_default:
        if not default_servers:
            raise ValueError(
                "ChatRequest.mcp_use_default=True but HarnessAgentConfig.mcp_default_servers is empty",
            )
        return list(default_servers)
    if mcp_servers is not None:
        return list(mcp_servers)
    return None


def _tool_name(tool: Any) -> str:
    if isinstance(tool, dict):
        return str(tool.get("name", ""))
    return str(getattr(tool, "name", ""))


def _postprocess_mcp_tools(
    tools: list[Any],
    *,
    server_name: str,
    tool_arg_aliases: dict[str, dict[str, str]],
) -> None:
    prefix = f"{server_name}_"
    used_names: set[str] = set()
    for tool in tools:
        name = _tool_name(tool)
        aliases: dict[str, str] | None = None
        if name.startswith(prefix):
            aliases = tool_arg_aliases.get(name.removeprefix(prefix))
        # One wrap: optional aliases, then drop None before the MCP call.
        _wrap_tool_arguments(tool, aliases=aliases)
        _coerce_tool_args_schema(tool)
        sanitized = sanitize_llm_tool_name(name)
        if sanitized == name:
            used_names.add(name)
            continue
        candidate = sanitized
        suffix = 2
        while candidate in used_names:
            candidate = f"{sanitized}_{suffix}"
            suffix += 1
        used_names.add(candidate)
        tool.name = candidate


def _prepare_tool_arguments(
    arguments: dict[str, Any],
    aliases: dict[str, str] | None,
) -> dict[str, Any]:
    prepared = _remap_tool_arguments(arguments, aliases) if aliases else arguments
    return {key: value for key, value in prepared.items() if value is not None}


def _wrap_tool_arguments(tool: Any, *, aliases: dict[str, str] | None = None) -> None:
    """Remap aliases (if any) and omit ``None`` values before the MCP tool runs."""
    for attr in ("coroutine", "func"):
        original = getattr(tool, attr, None)
        if original is None or not callable(original):
            continue
        setattr(tool, attr, _with_prepared_arguments(original, aliases))


def _with_prepared_arguments(
    original: Callable[..., Any],
    aliases: dict[str, str] | None,
) -> Callable[..., Any]:
    if inspect.iscoroutinefunction(original):

        async def _async_wrapped(**arguments: Any) -> Any:
            return await original(**_prepare_tool_arguments(arguments, aliases))

        return _async_wrapped

    def _sync_wrapped(**arguments: Any) -> Any:
        return original(**_prepare_tool_arguments(arguments, aliases))

    return _sync_wrapped


def _remap_tool_arguments(arguments: dict[str, Any], aliases: dict[str, str]) -> dict[str, Any]:
    remapped = dict(arguments)
    for alias, canonical in aliases.items():
        if alias not in remapped:
            continue
        alias_value = remapped.get(alias)
        if alias_value in (None, ""):
            continue
        if canonical not in remapped or remapped.get(canonical) in (None, ""):
            remapped[canonical] = alias_value
        remapped.pop(alias, None)
    return remapped


def _coerce_tool_args_schema(tool: Any) -> None:
    """Replace raw JSON Schema dicts with Pydantic models for clearer LLM binding."""
    schema = getattr(tool, "args_schema", None)
    if schema is None or not isinstance(schema, dict):
        return
    try:
        tool.args_schema = mcp_args_model(_tool_name(tool), schema)
    except (NameError, TypeError, ValueError):
        logger.debug(
            "Keeping raw JSON schema for tool %s",
            _tool_name(tool),
            exc_info=True,
        )


__all__ = [
    "aload_mcp_tools",
    "filter_tools_for_mcp_servers",
    "load_mcp_tools",
    "mcp_args_model",
    "mcp_tool_names",
    "merge_mcp_server_configs",
    "prioritize_active_mcp_tools",
    "resolve_active_mcp_servers",
    "sanitize_llm_tool_name",
    "validate_mcp_default_servers",
]
