"""Unified client-side and provider-native progressive tool loading."""

import json
import re
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Mapping
from threading import RLock
from typing import Annotated, Any, Literal, NotRequired, cast

from langchain.agents.middleware import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
    ProviderToolSearchMiddleware,
)
from langchain.agents.middleware.types import AgentState, OmitFromInput
from langchain.tools import ToolRuntime
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.config import get_config
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command
from pydantic import BaseModel, Field

_TOOL_SEARCH_NAME = "tool_search"
_MAX_THREAD_CATALOGS = 2048
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_DEFERRED_DESCRIPTION_SUFFIX = "\n\n[Deferred reference: call tool_search before use.]"
_SUPPORTED_NATIVE_PROVIDERS = frozenset({"openai", "anthropic"})


def _merge_loaded_tool_names(left: list[str] | None, right: list[str] | None) -> list[str]:
    """Union concurrent tool-search updates in deterministic order."""
    return sorted(set(left or ()) | set(right or ()))


class ClientToolSearchState(AgentState[Any]):
    """Persistent per-thread state used by client-side tool search."""

    loaded_tool_names: NotRequired[
        Annotated[
            list[str],
            OmitFromInput,
            _merge_loaded_tool_names,
        ]
    ]


class ToolSearchInput(BaseModel):
    """Arguments accepted by the provider-agnostic search tool."""

    query: str = Field(description="Short capability keywords, preferably in English.")
    max_results: int = Field(default=3, ge=1, le=5)


class _DeferredToolInput(BaseModel):
    """Empty schema used by model-facing deferred tool references."""


class _ToolDescriptor(BaseModel):
    name: str
    description: str


def _thread_key(config: Mapping[str, Any] | None) -> str | None:
    if not config:
        return None
    configurable = config.get("configurable")
    if not isinstance(configurable, Mapping):
        return None
    thread_id = configurable.get("thread_id")
    if thread_id is None:
        return None
    return str(thread_id)


def _current_thread_key() -> str | None:
    try:
        return _thread_key(get_config())
    except RuntimeError:
        return None


def _loaded_names(state: Any) -> frozenset[str]:
    if not isinstance(state, Mapping):
        return frozenset()
    value = state.get("loaded_tool_names")
    if not isinstance(value, list | tuple | set | frozenset):
        return frozenset()
    return frozenset(str(name) for name in value)


def _is_self_deferred(tool: BaseTool) -> bool:
    extras = tool.extras if isinstance(tool.extras, dict) else {}
    return extras.get("defer_loading") is True


def _make_eager(tool: Any) -> Any:
    """Return a tool copy without a provider-specific defer marker."""
    if not isinstance(tool, BaseTool) or not _is_self_deferred(tool):
        return tool
    extras = dict(tool.extras or {})
    extras.pop("defer_loading", None)
    return tool.model_copy(update={"extras": extras})


def _tokens(text: str) -> set[str]:
    tokens = set(_TOKEN_RE.findall(text.lower().replace("_", " ")))
    return {token[:-1] if len(token) > 3 and token.endswith("s") else token for token in tokens}


def _search_score(query: str, descriptor: _ToolDescriptor) -> int:
    query_tokens = _tokens(query)
    if not query_tokens:
        return 0
    name_tokens = _tokens(descriptor.name)
    description_tokens = _tokens(descriptor.description)
    normalized_query = "_".join(_TOKEN_RE.findall(query.lower()))
    score = 40 * len(query_tokens & name_tokens)
    score += 5 * len(query_tokens & description_tokens)
    if normalized_query and normalized_query in descriptor.name.lower():
        score += 100
    return score


class ToolSearchMiddleware(AgentMiddleware[ClientToolSearchState, Any]):
    """Own progressive discovery, loading state, and execution gating.

    ``client`` mode exposes lightweight name/description references and uses an
    ordinary ``tool_search`` function, so any function-calling model can use it.
    ``native`` mode delegates the same authorized inventory to the provider's
    hosted OpenAI/Anthropic search protocol. In both modes the complete real tool
    set remains registered with the graph for normal guarded execution.
    """

    state_schema = ClientToolSearchState

    def __init__(
        self,
        *,
        deferred_tools: frozenset[str],
        mcp_tool_names: frozenset[str] | None = None,
        defer_mcp_tools: bool = False,
        mode: Literal["client", "native"] = "client",
        fallback: Literal["eager", "error"] = "eager",
    ) -> None:
        super().__init__()
        self._deferred_tools = deferred_tools
        self._mcp_tool_names = mcp_tool_names or frozenset()
        self._defer_mcp_tools = defer_mcp_tools
        self._mode = mode
        self._fallback = fallback
        self._catalogs: OrderedDict[str, dict[str, _ToolDescriptor]] = OrderedDict()
        self._catalog_lock = RLock()
        client_tools = [
            StructuredTool.from_function(
                name=_TOOL_SEARCH_NAME,
                description=(
                    "Load the full input schemas for deferred tool references. Deferred tools "
                    "are already listed by name and description, but must be searched before "
                    "use. Search with short capability keywords (preferably English), then call "
                    "a returned tool by its real name."
                ),
                func=self._tool_search,
                coroutine=self._atool_search,
                args_schema=ToolSearchInput,
                infer_schema=False,
            )
        ]
        self.tools = client_tools if mode == "client" else []

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        if self._mode == "client":
            return handler(self._prepare_client(request))
        prepared, delegate = self._prepare_native(request)
        if delegate is None:
            return handler(prepared)
        return cast(ModelResponse, delegate.wrap_model_call(prepared, handler))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        if self._mode == "client":
            return await handler(self._prepare_client(request))
        prepared, delegate = self._prepare_native(request)
        if delegate is None:
            return await handler(prepared)
        return cast(ModelResponse, await delegate.awrap_model_call(prepared, handler))

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        if self._mode == "native":
            return handler(request)
        blocked = self._unloaded_error(request)
        return blocked if blocked is not None else handler(request)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        if self._mode == "native":
            return await handler(request)
        blocked = self._unloaded_error(request)
        return blocked if blocked is not None else await handler(request)

    def _prepare_client(self, request: ModelRequest) -> ModelRequest:
        tools = list(request.tools or [])
        selected: dict[str, BaseTool] = {}
        eager: list[Any] = []
        provider_tools: list[Any] = []

        for tool in tools:
            if not isinstance(tool, BaseTool):
                provider_tools.append(tool)
                continue
            if tool.name == _TOOL_SEARCH_NAME:
                continue
            should_defer = tool.name in self._deferred_tools or _is_self_deferred(tool)
            if self._defer_mcp_tools and tool.name in self._mcp_tool_names:
                should_defer = True
            if should_defer:
                selected[tool.name] = tool
            else:
                eager.append(tool)

        self._remember_catalog(self._request_thread_key(), selected)
        loaded = _loaded_names(request.state)
        deferred_tools = [
            _make_eager(selected[name]) if name in loaded else self._deferred_reference(selected[name])
            for name in sorted(selected)
        ]
        search_tools = self.tools if selected else []
        return request.override(tools=[*eager, *search_tools, *deferred_tools, *provider_tools])

    def _request_thread_key(self) -> str | None:
        return _current_thread_key()

    def _prepare_native(
        self,
        request: ModelRequest,
    ) -> tuple[ModelRequest, ProviderToolSearchMiddleware | None]:
        tools = list(request.tools or [])
        visible_names = {tool.name for tool in tools if isinstance(tool, BaseTool)}
        selected = self._deferred_tools & visible_names
        if self._defer_mcp_tools:
            selected |= self._mcp_tool_names & visible_names

        has_deferred = bool(selected) or any(isinstance(tool, BaseTool) and _is_self_deferred(tool) for tool in tools)
        if not has_deferred:
            return request, None

        enabled = getattr(request.model, "_harness_native_tool_search", False) is True
        provider = getattr(request.model, "_harness_tool_search_provider", None)
        if not (enabled and provider in _SUPPORTED_NATIVE_PROVIDERS):
            if self._fallback == "error":
                model_name = request.model.__class__.__name__
                raise ValueError(
                    "Native tool search is configured for this request, but "
                    f"model {model_name!r} does not advertise OpenAI or Anthropic "
                    "hosted tool-search support",
                )
            eager_tools = [_make_eager(tool) for tool in tools]
            if eager_tools == tools:
                return request, None
            return request.override(tools=eager_tools), None

        searchable: list[str | BaseTool] = []
        searchable.extend(sorted(selected))
        return request, ProviderToolSearchMiddleware(searchable_tools=searchable)

    @staticmethod
    def _deferred_reference(tool: BaseTool) -> BaseTool:
        extras = dict(tool.extras or {})
        extras.pop("defer_loading", None)
        return tool.model_copy(
            update={
                "args_schema": _DeferredToolInput,
                "description": f"{tool.description or ''}{_DEFERRED_DESCRIPTION_SUFFIX}",
                "extras": extras,
            }
        )

    def _remember_catalog(self, thread_key: str | None, tools: Mapping[str, BaseTool]) -> None:
        if thread_key is None:
            return
        catalog = {
            name: _ToolDescriptor(name=name, description=(tool.description or "")[:320]) for name, tool in tools.items()
        }
        with self._catalog_lock:
            self._catalogs[thread_key] = catalog
            self._catalogs.move_to_end(thread_key)
            while len(self._catalogs) > _MAX_THREAD_CATALOGS:
                self._catalogs.popitem(last=False)

    def _catalog(self, thread_key: str | None) -> dict[str, _ToolDescriptor]:
        if thread_key is None:
            return {}
        with self._catalog_lock:
            return dict(self._catalogs.get(thread_key, {}))

    def _tool_search(
        self,
        runtime: ToolRuntime[Any, ClientToolSearchState],
        query: str,
        max_results: int,
    ) -> Command[Any]:
        return self._search(query, max_results, runtime)

    async def _atool_search(
        self,
        runtime: ToolRuntime[Any, ClientToolSearchState],
        query: str,
        max_results: int,
    ) -> Command[Any]:
        return self._search(query, max_results, runtime)

    def _search(
        self,
        query: str,
        max_results: int,
        runtime: ToolRuntime[Any, ClientToolSearchState],
    ) -> Command[Any]:
        catalog = self._catalog(_thread_key(runtime.config))
        ranked = sorted(
            ((_search_score(query, descriptor), descriptor) for descriptor in catalog.values()),
            key=lambda item: (-item[0], item[1].name),
        )
        matches = [descriptor for score, descriptor in ranked if score > 0][:max_results]
        if matches:
            lines = ["Loaded tools:"]
            lines.extend(f"- {item.name}: {item.description}" for item in matches)
            lines.append("These tool schemas are available on the next model step.")
        else:
            lines = ["No deferred tools matched. Try broader English capability keywords."]
        return Command(
            update={
                "loaded_tool_names": [item.name for item in matches],
                "messages": [
                    ToolMessage(
                        content="\n".join(lines),
                        tool_call_id=runtime.tool_call_id or "",
                    )
                ],
            }
        )

    def _unloaded_error(self, request: ToolCallRequest) -> ToolMessage | Command[Any] | None:
        name = str(request.tool_call.get("name", ""))
        if name == _TOOL_SEARCH_NAME:
            return None
        catalog = self._catalog(_thread_key(request.runtime.config))
        deferred = name in self._deferred_tools or name in catalog
        if self._defer_mcp_tools and name in self._mcp_tool_names:
            deferred = True
        if request.tool is not None and _is_self_deferred(request.tool):
            deferred = True
        if not deferred:
            return None
        if name in catalog and name in _loaded_names(request.state):
            return None
        tool_call_id = str(request.tool_call.get("id", ""))
        if name in catalog:
            payload = {
                "schema_version": 1,
                "type": "tool_activation_error",
                "tool": name,
                "status": "failed",
                "is_error": True,
                "message": f"The schema for tool {name!r} was not loaded before invocation.",
                "error": {
                    "code": "tool_schema_not_loaded",
                    "category": "tool_loading",
                    "message": f"The schema for tool {name!r} was not loaded before invocation.",
                    "retryable": True,
                    "safe_to_resubmit": True,
                },
                "remediation": {
                    "action": "retry_with_loaded_schema",
                    "model_instruction": (
                        "The full tool schema is now activated. Retry once on the next model step "
                        "using the loaded schema; do not guess arguments."
                    ),
                },
            }
            return Command(
                update={
                    "loaded_tool_names": [name],
                    "messages": [
                        ToolMessage(
                            content=json.dumps(payload, separators=(",", ":")),
                            tool_call_id=tool_call_id,
                            status="error",
                        )
                    ],
                }
            )
        payload = {
            "schema_version": 1,
            "type": "tool_activation_error",
            "tool": name,
            "status": "failed",
            "is_error": True,
            "message": f"Tool {name!r} is not available in this request.",
            "error": {
                "code": "tool_not_authorized",
                "category": "authorization",
                "message": f"Tool {name!r} is not available in this request.",
                "retryable": False,
                "safe_to_resubmit": False,
            },
            "remediation": {
                "action": "contact_administrator",
                "model_instruction": (
                    "Do not retry or attempt to bypass tool availability. Explain that the tool "
                    "is unavailable in the current runtime."
                ),
            },
        }
        return ToolMessage(
            content=json.dumps(payload, separators=(",", ":")),
            tool_call_id=tool_call_id,
            status="error",
        )


__all__ = [
    "ClientToolSearchState",
    "ToolSearchInput",
    "ToolSearchMiddleware",
]
