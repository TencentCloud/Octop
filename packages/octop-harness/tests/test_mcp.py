"""Tests for MCP helpers and middleware."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.runnables.config import var_child_runnable_config
from pydantic import ValidationError

from octop_harness.mcp import (
    aload_mcp_tools,
    filter_tools_for_mcp_servers,
    mcp_args_model,
    merge_mcp_server_configs,
    prioritize_active_mcp_tools,
    resolve_active_mcp_servers,
    sanitize_llm_tool_name,
    validate_mcp_default_servers,
)
from octop_harness.middleware.mcp_tools import MCPToolMiddleware


def _named_tool(name: str) -> MagicMock:
    tool = MagicMock()
    tool.name = name
    return tool


@pytest.fixture
def sample_tools() -> list[MagicMock]:
    return [_named_tool("builtin"), _named_tool("github_search"), _named_tool("math_add")]


class TestAloadMcpTools:
    @pytest.mark.asyncio
    async def test_skips_failed_servers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _Client:
            def __init__(self, configs: dict[str, object], **kwargs: object) -> None:
                self._name = next(iter(configs))

            async def get_tools(self) -> list[MagicMock]:
                if self._name == "bad":
                    raise RuntimeError("boom")
                return [_named_tool(f"{self._name}_tool")]

        monkeypatch.setattr("octop_harness.mcp.MultiServerMCPClient", _Client)
        tools = await aload_mcp_tools(
            {
                "bad": {"transport": "http", "url": "http://bad"},
                "good": {"transport": "http", "url": "http://good"},
            }
        )
        assert [t.name for t in tools] == ["good_tool"]

    @pytest.mark.asyncio
    async def test_skips_exception_group_from_sse_transport(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class _Client:
            def __init__(self, configs: dict[str, object], **kwargs: object) -> None:
                self._name = next(iter(configs))

            async def get_tools(self) -> list[MagicMock]:
                if self._name == "bad":
                    raise BaseExceptionGroup(
                        "unhandled errors in a TaskGroup (1 sub-exception)",
                        [RuntimeError("sse connect failed")],
                    )
                return [_named_tool(f"{self._name}_tool")]

        monkeypatch.setattr("octop_harness.mcp.MultiServerMCPClient", _Client)
        tools = await aload_mcp_tools(
            {
                "bad": {"transport": "sse", "url": "http://bad"},
                "good": {"transport": "http", "url": "http://good"},
            }
        )
        assert [t.name for t in tools] == ["good_tool"]

    @pytest.mark.asyncio
    async def test_skips_spec_without_transport(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _Client:
            def __init__(self, configs: dict[str, object], **kwargs: object) -> None:
                self._name = next(iter(configs))

            async def get_tools(self) -> list[MagicMock]:
                return [_named_tool(f"{self._name}_tool")]

        monkeypatch.setattr("octop_harness.mcp.MultiServerMCPClient", _Client)
        tools = await aload_mcp_tools(
            {
                "registry_only": {},
                "remote": {"transport": "http", "url": "http://good"},
            }
        )
        assert [t.name for t in tools] == ["remote_tool"]


class TestSanitizeLlmToolName:
    def test_keeps_valid_names(self) -> None:
        assert sanitize_llm_tool_name("github_search") == "github_search"

    def test_replaces_dots(self) -> None:
        assert sanitize_llm_tool_name("tencent-docs__abc_manage.search_file") == (
            "tencent-docs__abc_manage_search_file"
        )


class TestAloadMcpToolPostprocess:
    @pytest.mark.asyncio
    async def test_sanitizes_dotted_tool_names(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _Client:
            def __init__(self, configs: dict[str, object], **kwargs: object) -> None:
                del configs, kwargs

            async def get_tools(self) -> list[MagicMock]:
                tool = MagicMock()
                tool.name = "docs_manage.search_file"
                tool.coroutine = None
                return [tool]

        monkeypatch.setattr("octop_harness.mcp.MultiServerMCPClient", _Client)
        tools = await aload_mcp_tools({"docs": {"transport": "http", "url": "http://docs"}})
        assert [t.name for t in tools] == ["docs_manage_search_file"]

    @pytest.mark.asyncio
    async def test_remaps_tool_arg_aliases(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _Client:
            def __init__(self, configs: dict[str, object], **kwargs: object) -> None:
                del configs, kwargs

            async def get_tools(self) -> list[MagicMock]:
                tool = MagicMock()
                tool.name = "docs_manage.search_file"
                tool.func = None

                async def _run(**arguments: object) -> dict[str, object]:
                    return arguments

                tool.coroutine = _run
                return [tool]

        monkeypatch.setattr("octop_harness.mcp.MultiServerMCPClient", _Client)
        tools = await aload_mcp_tools(
            {
                "docs": {
                    "transport": "http",
                    "url": "http://docs",
                    "tool_arg_aliases": {
                        "manage.search_file": {"query": "search_key"},
                    },
                }
            }
        )
        result = await tools[0].coroutine(query="budget")
        assert result == {"search_key": "budget"}


class TestMcpArgsModel:
    def test_builds_required_fields(self) -> None:
        model = mcp_args_model(
            "docs_manage_search_file",
            {
                "type": "object",
                "required": ["search_key"],
                "properties": {
                    "search_key": {"type": "string", "description": "keyword"},
                },
            },
        )
        assert "search_key" in model.model_fields
        assert model.model_fields["search_key"].is_required()

    def test_renames_leading_underscore_properties(self) -> None:
        model = mcp_args_model(
            "meeting_list",
            {
                "type": "object",
                "required": ["_client_info"],
                "properties": {
                    "_client_info": {"type": "string", "description": "client"},
                    "query": {"type": "string"},
                },
            },
        )
        assert "client_info" in model.model_fields
        assert model.model_fields["client_info"].is_required()
        assert "query" in model.model_fields

    def test_renames_reserved_base_model_properties(self) -> None:
        model = mcp_args_model(
            "tencent_lexiang_smartsheet_create",
            {
                "type": "object",
                "required": ["schema"],
                "properties": {
                    "schema": {"type": "string", "description": "sheet schema"},
                    "title": {"type": "string"},
                },
            },
        )
        assert "schema" not in model.model_fields
        assert "arg_schema" in model.model_fields
        assert model.model_fields["arg_schema"].is_required()
        assert model.model_validate({"schema": "cols"}).model_dump(by_alias=True) == {
            "schema": "cols",
            "title": None,
        }

    def test_llm_schema_omits_null_for_optionals(self) -> None:
        model = mcp_args_model(
            "notion_search",
            {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string", "description": "search"},
                    "page_size": {"type": "number"},
                },
            },
        )
        props = model.model_json_schema()["properties"]
        assert "anyOf" not in props["page_size"]
        assert "default" not in props["page_size"]
        assert props["page_size"]["type"] == "number"

    def test_drops_null_arguments_before_validation(self) -> None:
        model = mcp_args_model(
            "search_flight",
            {
                "type": "object",
                "required": ["origin"],
                "properties": {
                    "origin": {"type": "string"},
                    "destination": {"type": "string"},
                },
            },
        )
        # Optional null is dropped for validation; Pydantic still applies default=None
        # on the model instance. The MCP call path strips None separately.
        parsed = model.model_validate({"origin": "北京", "destination": None})
        assert parsed.origin == "北京"
        assert parsed.destination is None

        with pytest.raises(ValidationError, match="origin"):
            model.model_validate({"origin": None, "destination": None})

    @pytest.mark.asyncio
    async def test_strips_none_arguments_before_mcp_call(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured: dict[str, object] = {}

        class _Client:
            def __init__(self, configs: dict[str, object], **kwargs: object) -> None:
                del configs, kwargs

            async def get_tools(self) -> list[MagicMock]:
                tool = MagicMock()
                tool.name = "notion_notion-search"
                tool.func = None
                tool.args_schema = {
                    "type": "object",
                    "required": ["query"],
                    "properties": {
                        "query": {"type": "string"},
                        "page_size": {"type": "number"},
                    },
                }

                async def _run(**arguments: object) -> dict[str, object]:
                    captured["arguments"] = arguments
                    return arguments

                tool.coroutine = _run
                return [tool]

        monkeypatch.setattr("octop_harness.mcp.MultiServerMCPClient", _Client)
        tools = await aload_mcp_tools({"notion": {"transport": "http", "url": "http://notion"}})
        await tools[0].coroutine(query="budget", page_size=None)
        assert captured["arguments"] == {"query": "budget"}

    @pytest.mark.asyncio
    async def test_coerces_remote_tool_json_schema(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _Client:
            def __init__(self, configs: dict[str, object], **kwargs: object) -> None:
                del configs, kwargs

            async def get_tools(self) -> list[MagicMock]:
                tool = MagicMock()
                tool.name = "docs_manage.search_file"
                tool.coroutine = None
                tool.args_schema = {
                    "type": "object",
                    "required": ["search_key"],
                    "properties": {
                        "search_key": {"type": "string", "description": "keyword"},
                    },
                }
                return [tool]

        monkeypatch.setattr("octop_harness.mcp.MultiServerMCPClient", _Client)
        tools = await aload_mcp_tools({"docs": {"transport": "http", "url": "http://docs"}})
        schema = tools[0].args_schema
        assert isinstance(schema, type)
        assert "search_key" in schema.model_fields
        assert schema.model_fields["search_key"].is_required()


class TestMergeMcpServerConfigs:
    def test_agent_overrides_shared(self) -> None:
        merged = merge_mcp_server_configs(
            {"shared": {"transport": "http", "url": "http://a"}},
            {"shared": {"transport": "http", "url": "http://b"}, "local": {"transport": "stdio", "command": "x"}},
        )
        assert merged["shared"]["url"] == "http://b"
        assert "local" in merged


class TestValidateMcpDefaultServers:
    def test_unknown_server_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown server"):
            validate_mcp_default_servers(["missing"], {"github": {}})


class TestResolveActiveMcpServers:
    def test_default_is_none(self) -> None:
        assert (
            resolve_active_mcp_servers(
                mcp_use_default=False,
                mcp_servers=None,
                default_servers=["github"],
            )
            is None
        )

    def test_explicit_servers(self) -> None:
        assert resolve_active_mcp_servers(
            mcp_use_default=False,
            mcp_servers=["github"],
            default_servers=None,
        ) == ["github"]

    def test_use_default(self) -> None:
        assert resolve_active_mcp_servers(
            mcp_use_default=True,
            mcp_servers=None,
            default_servers=["github", "math"],
        ) == ["github", "math"]

    def test_use_default_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="mcp_default_servers is empty"):
            resolve_active_mcp_servers(
                mcp_use_default=True,
                mcp_servers=None,
                default_servers=None,
            )


class TestFilterToolsForMcpServers:
    def test_hides_mcp_by_default(self, sample_tools: list[MagicMock]) -> None:
        mcp_names = frozenset({"github_search", "math_add"})
        filtered = filter_tools_for_mcp_servers(
            sample_tools,
            mcp_tool_names=mcp_names,
            server_names=frozenset({"github", "math"}),
            active_servers=None,
        )
        assert [t.name for t in filtered] == ["builtin"]

    def test_keeps_selected_servers(self, sample_tools: list[MagicMock]) -> None:
        mcp_names = frozenset({"github_search", "math_add"})
        filtered = filter_tools_for_mcp_servers(
            sample_tools,
            mcp_tool_names=mcp_names,
            server_names=frozenset({"github", "math"}),
            active_servers=["github"],
        )
        assert [t.name for t in filtered] == ["builtin", "github_search"]


class TestPrioritizeActiveMcpTools:
    def test_moves_active_mcp_after_builtins(self) -> None:
        ima = _named_tool("ima_srv_list")
        docs = [_named_tool("docs_srv_a"), _named_tool("docs_srv_b")]
        tools = [_named_tool("builtin"), *docs, ima]
        mcp_names = frozenset(t.name for t in docs) | {ima.name}
        ordered = prioritize_active_mcp_tools(
            tools,
            mcp_tool_names=mcp_names,
            active_servers=["ima_srv"],
        )
        assert [t.name for t in ordered] == ["builtin", "ima_srv_list", "docs_srv_a", "docs_srv_b"]


class TestMCPToolMiddleware:
    @contextmanager
    def _runnable_config(self, configurable: dict[str, object]) -> Iterator[None]:
        token = var_child_runnable_config.set({"configurable": configurable})
        try:
            yield
        finally:
            var_child_runnable_config.reset(token)

    def _middleware(self) -> MCPToolMiddleware:
        return MCPToolMiddleware(
            server_names=frozenset({"github", "math"}),
            mcp_tool_names=frozenset({"github_search", "math_add"}),
            default_servers=["github"],
        )

    def _request(self, tools: list[MagicMock]) -> ModelRequest:
        return ModelRequest(
            model=MagicMock(),
            messages=[],
            system_message=None,
            tool_choice=None,
            tools=tools,
            response_format=None,
            state={},
            runtime=MagicMock(),
            model_settings={},
        )

    def test_filters_out_mcp_without_opt_in(self, sample_tools: list[MagicMock]) -> None:
        mw = self._middleware()
        with self._runnable_config({}):
            req = self._request(list(sample_tools))
            captured: dict[str, list[str]] = {}

            def handler(r: ModelRequest) -> ModelResponse:
                captured["names"] = [t.name for t in r.tools]
                return ModelResponse(result=[])

            mw.wrap_model_call(req, handler)
        assert captured["names"] == ["builtin"]

    def test_exposes_default_servers_on_request(self, sample_tools: list[MagicMock]) -> None:
        mw = self._middleware()
        with self._runnable_config({"mcp_use_default": True}):
            req = self._request(list(sample_tools))
            captured: dict[str, list[str]] = {}

            def handler(r: ModelRequest) -> ModelResponse:
                captured["names"] = [t.name for t in r.tools]
                return ModelResponse(result=[])

            mw.wrap_model_call(req, handler)
        assert captured["names"] == ["builtin", "github_search"]

    def test_exposes_explicit_servers_on_request(self, sample_tools: list[MagicMock]) -> None:
        mw = self._middleware()
        with self._runnable_config({"mcp_servers": ["math"]}):
            req = self._request(list(sample_tools))
            captured: dict[str, list[str]] = {}

            def handler(r: ModelRequest) -> ModelResponse:
                captured["names"] = [t.name for t in r.tools]
                return ModelResponse(result=[])

            mw.wrap_model_call(req, handler)
        assert captured["names"] == ["builtin", "math_add"]
