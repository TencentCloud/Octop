"""Tests for ``octop_harness.agent.HarnessAgent``.

These tests focus on construction wiring — what middleware/tools/skills get
passed to ``create_deep_agent`` — without actually calling an LLM. The
real agent.call / stream paths are exercised via a mocked graph that
echoes whatever was passed to it.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from octop_harness.agent import HarnessAgent
from octop_harness.backends.workspace import DEFAULT_MEMORY_FILES
from octop_harness.config import HarnessAgentConfig, ModelConfig, ProviderConfig
from octop_harness.middleware.bootstrap import BOOTSTRAP_FILENAME, BOOTSTRAPPED_MARKER
from octop_harness.middleware.skill_filter import render_slash_skill_prompt
from octop_harness.observability.logging import _HANDLER_NAME, _log_agent_id
from octop_harness.request import ChatRequest


def _package_log_dir() -> Path:
    pkg = logging.getLogger("octop_harness")
    for handler in pkg.handlers:
        if getattr(handler, "name", None) == _HANDLER_NAME:
            return Path(handler.baseFilename).parent
    raise AssertionError("octop_harness file handler is missing")


@pytest.fixture
def mock_model_factory() -> Callable[[], Any]:
    """Return a function that patches the OpenAI client construction."""

    def _patch() -> Any:
        sentinel = MagicMock(name="seed-model")
        return patch("langchain_openai.ChatOpenAI", return_value=sentinel)

    return _patch


@pytest.fixture
def stub_create_deep_agent() -> Any:
    """Patch ``deepagents.create_deep_agent`` to return a recording mock."""
    fake_graph = MagicMock(name="fake-graph")
    fake_graph.invoke.return_value = {"messages": [], "stub": True}
    return patch("deepagents.create_deep_agent", return_value=fake_graph)


@pytest.fixture
def cfg(tmp_path: Path) -> HarnessAgentConfig:
    return HarnessAgentConfig(
        name="test-agent",
        workspace_dir=tmp_path,
        backend={"type": "filesystem", "root_dir": str(tmp_path), "virtual_mode": False},
        providers=[
            ProviderConfig(
                id="p",
                base_url="https://x",
                api_key="k",
                models=[
                    ModelConfig(id="text", input=["text"]),
                    ModelConfig(id="vision", input=["text", "image"]),
                ],
            ),
        ],
        default_model="p/text",
        memory_enabled=False,
        checkpointer=False,
    )


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_default_log_dir_is_global_not_workspace(
        self,
        cfg: HarnessAgentConfig,
        mock_model_factory: Callable[[], Any],
        stub_create_deep_agent: Any,
    ) -> None:
        with mock_model_factory(), stub_create_deep_agent:
            HarnessAgent(cfg)
        log_dir = _package_log_dir()
        assert log_dir == (Path.home() / ".octop-harness" / "logs").resolve()
        assert (
            not (Path(cfg.workspace_dir) / "logs").exists() or log_dir != (Path(cfg.workspace_dir) / "logs").resolve()
        )

    def test_direct_agent_does_not_override_app_log_dir(
        self,
        cfg: HarnessAgentConfig,
        mock_model_factory: Callable[[], Any],
        stub_create_deep_agent: Any,
        tmp_path: Path,
    ) -> None:
        from octop_harness.observability.logging import setup_logging

        app_dir = tmp_path / "app-logs"
        setup_logging(app_dir)
        with mock_model_factory(), stub_create_deep_agent:
            HarnessAgent(cfg)
        assert _package_log_dir() == app_dir.resolve()

    def test_config_debug_does_not_change_process_log_level(
        self,
        cfg: HarnessAgentConfig,
        mock_model_factory: Callable[[], Any],
        stub_create_deep_agent: Any,
        tmp_path: Path,
    ) -> None:
        from octop_harness.observability.logging import setup_logging

        setup_logging(tmp_path / "logs", level="INFO")
        with mock_model_factory(), stub_create_deep_agent:
            HarnessAgent(replace(cfg, debug=True))
        assert logging.getLogger("octop_harness").level == logging.INFO

    def test_direct_construction_has_no_agent_id(
        self,
        cfg: HarnessAgentConfig,
        mock_model_factory: Callable[[], Any],
        stub_create_deep_agent: Any,
    ) -> None:
        with mock_model_factory(), stub_create_deep_agent:
            assert HarnessAgent(cfg).agent_id is None

    def test_constructor_agent_id_is_exposed(
        self,
        cfg: HarnessAgentConfig,
        mock_model_factory: Callable[[], Any],
        stub_create_deep_agent: Any,
    ) -> None:
        with mock_model_factory(), stub_create_deep_agent:
            assert HarnessAgent(cfg, agent_id="abc123").agent_id == "abc123"

    def test_construction_creates_graph_and_backend(
        self,
        cfg: HarnessAgentConfig,
        mock_model_factory: Callable[[], Any],
        stub_create_deep_agent: Any,
    ) -> None:
        with mock_model_factory(), stub_create_deep_agent:
            agent = HarnessAgent(cfg)
        # Agent should have a graph, backend, and workspace facade.
        assert agent.graph is not None
        assert agent.backend is not None
        assert agent.workspace is not None
        assert agent.workspace.backend is agent.backend

    def test_middleware_includes_router_and_memory(
        self,
        cfg: HarnessAgentConfig,
        mock_model_factory: Callable[[], Any],
    ) -> None:
        captured: dict[str, Any] = {}

        def fake_create(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return MagicMock(name="fake-graph")

        with mock_model_factory(), patch("deepagents.create_deep_agent", side_effect=fake_create):
            HarnessAgent(cfg)

        mw_classes = [type(m).__name__ for m in captured["middleware"]]
        assert "ModelRouterMiddleware" in mw_classes
        # The octop-memory adapter also owns the default-on JSONL session log.
        assert "HarnessMemoryMiddleware" in [m.name for m in captured["middleware"]]
        # ModelRetry and PII (api-key redaction) are on by default.
        assert "ModelRetryMiddleware" in mw_classes
        retry = next(m for m in captured["middleware"] if type(m).__name__ == "ModelRetryMiddleware")
        assert retry.on_failure == "error"
        from langchain.agents.middleware import ModelRetryMiddleware

        assert retry.retry_on is ModelRetryMiddleware().retry_on
        assert "PIIMiddleware" in mw_classes

    def test_can_disable_model_retry_and_pii(
        self,
        tmp_path: Path,
        mock_model_factory: Callable[[], Any],
    ) -> None:
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            backend={"type": "filesystem", "root_dir": str(tmp_path), "virtual_mode": False},
            providers=[
                ProviderConfig(
                    id="p",
                    base_url="https://x",
                    api_key="k",
                    models=[ModelConfig(id="text")],
                ),
            ],
            default_model="p/text",
            model_retry_enabled=False,
            pii_enabled=False,
        )
        captured: dict[str, Any] = {}

        def fake_create(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return MagicMock(name="fake-graph")

        with mock_model_factory(), patch("deepagents.create_deep_agent", side_effect=fake_create):
            HarnessAgent(cfg)

        mw_classes = [type(m).__name__ for m in captured["middleware"]]
        assert "ModelRetryMiddleware" not in mw_classes
        assert "PIIMiddleware" not in mw_classes
        # The router stays on regardless.
        assert "ModelRouterMiddleware" in mw_classes

    def test_session_logger_can_be_disabled(
        self,
        tmp_path: Path,
        mock_model_factory: Callable[[], Any],
    ) -> None:
        """Disabling ordinary memory and JSONL keeps only workspace context."""
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            backend={"type": "filesystem", "root_dir": str(tmp_path), "virtual_mode": False},
            providers=[
                ProviderConfig(
                    id="p",
                    base_url="https://x",
                    api_key="k",
                    models=[ModelConfig(id="text")],
                ),
            ],
            default_model="p/text",
            memory_enabled=False,
            session_log_enabled=False,
        )
        captured: dict[str, Any] = {}

        def fake_create(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return MagicMock(name="fake-graph")

        with mock_model_factory(), patch("deepagents.create_deep_agent", side_effect=fake_create):
            HarnessAgent(cfg)

        mw_classes = [type(m).__name__ for m in captured["middleware"]]
        assert "HarnessMemoryMiddleware" not in [m.name for m in captured["middleware"]]
        assert "MemoryMiddleware" in [m.name for m in captured["middleware"]]
        assert "ModelRouterMiddleware" in mw_classes
        assert "SkillFilterMiddleware" in mw_classes
        assert "ToolsFilterMiddleware" in mw_classes

    def test_user_tools_and_middleware_appended(
        self,
        cfg: HarnessAgentConfig,
        mock_model_factory: Callable[[], Any],
    ) -> None:
        custom_tool = MagicMock(name="custom-tool")
        custom_mw = MagicMock(name="custom-mw")
        cfg2 = HarnessAgentConfig(
            workspace_dir=cfg.workspace_dir,
            backend=cfg.backend,
            providers=cfg.providers,
            default_model=cfg.default_model,
            tools=[custom_tool],
            middleware=[custom_mw],
            checkpointer=False,
        )
        captured: dict[str, Any] = {}

        def fake_create(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return MagicMock()

        with mock_model_factory(), patch("deepagents.create_deep_agent", side_effect=fake_create):
            HarnessAgent(cfg2)

        assert custom_tool in captured["tools"]
        assert custom_mw in captured["middleware"]
        # Built-in tools are still there.
        tool_names = [getattr(t, "name", str(t)) for t in captured["tools"]]
        assert "current_time" in tool_names
        assert "web_fetch" in tool_names

    def test_client_tool_search_runs_after_user_middleware_before_tool_order(
        self,
        cfg: HarnessAgentConfig,
        mock_model_factory: Callable[[], Any],
    ) -> None:
        custom_mw = MagicMock(name="custom-mw")
        cfg.deferred_tools = frozenset({"web_fetch"})
        cfg.middleware = [custom_mw]
        captured: dict[str, Any] = {}

        def fake_create(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return MagicMock()

        with mock_model_factory(), patch("deepagents.create_deep_agent", side_effect=fake_create):
            HarnessAgent(cfg)

        middleware = captured["middleware"]
        names = [type(item).__name__ for item in middleware]
        custom_index = middleware.index(custom_mw)
        search_index = names.index("ToolSearchMiddleware")
        task_index = names.index("TaskToolLastMiddleware")
        context_index = names.index("ContextUsageMiddleware")
        assert custom_index < search_index < task_index < context_index

    def test_skills_paths_include_builtin_and_user(
        self,
        cfg: HarnessAgentConfig,
        mock_model_factory: Callable[[], Any],
    ) -> None:
        captured: dict[str, Any] = {}

        def fake_create(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return MagicMock()

        with mock_model_factory(), patch("deepagents.create_deep_agent", side_effect=fake_create):
            HarnessAgent(cfg)

        skills = captured["skills"]
        ws = str(cfg.workspace_dir)
        assert f"{ws}/_builtin_skills" in skills
        assert f"{ws}/skills" in skills

    def test_skills_paths_scoped_virtual_are_agent_facing(
        self,
        tmp_path: Path,
        mock_model_factory: Callable[[], Any],
    ) -> None:
        root = tmp_path / "home"
        host_ws = root / ".octop" / "workspaces" / "NBR8CP"
        host_ws.mkdir(parents=True)
        (host_ws / ".octop" / "_builtin_skills").mkdir(parents=True)
        (host_ws / ".octop" / "skills").mkdir(parents=True)

        cfg = HarnessAgentConfig(
            name="skills-virtual",
            workspace_dir="/.octop/workspaces/NBR8CP",
            system_files_path=".octop",
            backend={
                "type": "filesystem",
                "root_dir": str(root),
                "virtual_mode": True,
            },
            providers=[
                ProviderConfig(
                    id="p",
                    base_url="https://x",
                    api_key="k",
                    models=[ModelConfig(id="text", input=["text"])],
                ),
            ],
            default_model="p/text",
            memory_enabled=False,
            checkpointer=False,
        )
        captured: dict[str, Any] = {}

        def fake_create(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return MagicMock()

        with mock_model_factory(), patch("deepagents.create_deep_agent", side_effect=fake_create):
            HarnessAgent(cfg)

        skills = captured["skills"]
        assert "/.octop/workspaces/NBR8CP/.octop/_builtin_skills" in skills
        assert "/.octop/workspaces/NBR8CP/.octop/skills" in skills
        assert not any(str(root) in path for path in skills)

    def test_memory_sources_include_files_created_after_graph_construction(
        self,
        cfg: HarnessAgentConfig,
        mock_model_factory: Callable[[], Any],
    ) -> None:
        # Pre-create AGENTS.md inside the workspace (= backend root for this fixture).
        (Path(cfg.workspace_dir) / "AGENTS.md").write_text("# project rules", encoding="utf-8")
        captured: dict[str, Any] = {}

        def fake_create(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return MagicMock()

        with mock_model_factory(), patch("deepagents.create_deep_agent", side_effect=fake_create):
            HarnessAgent(cfg)

        memory = captured.get("memory")
        assert memory == [str(Path(cfg.workspace_dir) / name) for name in DEFAULT_MEMORY_FILES]
        (Path(cfg.workspace_dir) / "MEMORY.md").write_text("new manual memory", encoding="utf-8")
        loader = next(m for m in captured["middleware"] if m.name == "MemoryMiddleware")
        loaded = loader.before_agent({}, MagicMock(), {})
        assert loaded is not None
        assert set(loaded["memory_contents"].values()) == {"# project rules", "new manual memory"}


# ---------------------------------------------------------------------------
# Invocation surface
# ---------------------------------------------------------------------------


class TestInvocation:
    @pytest.mark.asyncio
    async def test_call_passes_normalized_input_and_config(
        self,
        cfg: HarnessAgentConfig,
        mock_model_factory: Callable[[], Any],
    ) -> None:
        fake_graph = MagicMock(name="graph")
        fake_graph.ainvoke = AsyncMock(return_value={"messages": []})
        with mock_model_factory(), patch("deepagents.create_deep_agent", return_value=fake_graph):
            agent = HarnessAgent(cfg)

        await agent.call("hello")
        args, kwargs = fake_graph.ainvoke.call_args
        graph_input = args[0]
        # The input should contain a single HumanMessage.
        assert "messages" in graph_input
        assert len(graph_input["messages"]) == 1
        # The config should carry an auto-generated thread_id.
        assert "thread_id" in kwargs["config"]["configurable"]

    @pytest.mark.asyncio
    async def test_call_with_explicit_chat_request(
        self,
        cfg: HarnessAgentConfig,
        mock_model_factory: Callable[[], Any],
    ) -> None:
        fake_graph = MagicMock()
        fake_graph.ainvoke = AsyncMock(return_value={"messages": []})
        with mock_model_factory(), patch("deepagents.create_deep_agent", return_value=fake_graph):
            agent = HarnessAgent(cfg)

        req = ChatRequest(
            messages="hi",
            thread_id="t-explicit",
            user="alice",
            model="p/vision",
        )
        await agent.call(req)
        configurable = fake_graph.ainvoke.call_args.kwargs["config"]["configurable"]
        assert configurable["thread_id"] == "t-explicit"
        assert configurable["user"] == "alice"
        assert configurable["model"] == "p/vision"

    @pytest.mark.asyncio
    async def test_call_with_dict(
        self,
        cfg: HarnessAgentConfig,
        mock_model_factory: Callable[[], Any],
    ) -> None:
        fake_graph = MagicMock()
        fake_graph.ainvoke = AsyncMock(return_value={"messages": []})
        with mock_model_factory(), patch("deepagents.create_deep_agent", return_value=fake_graph):
            agent = HarnessAgent(cfg)

        await agent.call({"messages": "hi", "user": "bob"})
        configurable = fake_graph.ainvoke.call_args.kwargs["config"]["configurable"]
        assert configurable["user"] == "bob"

    @pytest.mark.asyncio
    async def test_stream_restores_logging_scope_between_chunks(
        self,
        cfg: HarnessAgentConfig,
        mock_model_factory: Callable[[], Any],
    ) -> None:
        scoped_ids: list[str | None] = []

        async def fake_iter(*args: Any, **kwargs: Any) -> Any:
            scoped_ids.append(_log_agent_id.get())
            yield "first"
            scoped_ids.append(_log_agent_id.get())
            yield "second"

        with (
            mock_model_factory(),
            patch("deepagents.create_deep_agent", return_value=MagicMock()),
            patch("octop_harness.slash.runtime.iter_with_runtime_slash", side_effect=fake_iter),
        ):
            agent = HarnessAgent(cfg, agent_id="agent-a")
            stream = agent.stream("hello")
            assert await anext(stream) == "first"
            assert _log_agent_id.get() is None
            await stream.aclose()

        assert scoped_ids == ["agent-a"]


# ---------------------------------------------------------------------------
# Properties / escape hatches
# ---------------------------------------------------------------------------


class TestEscapeHatches:
    def test_graph_property_returns_underlying_graph(
        self,
        cfg: HarnessAgentConfig,
        mock_model_factory: Callable[[], Any],
    ) -> None:
        fake_graph = MagicMock()
        with mock_model_factory(), patch("deepagents.create_deep_agent", return_value=fake_graph):
            agent = HarnessAgent(cfg)
        assert agent.graph is fake_graph

    def test_backend_property_returns_filesystem_backend(
        self,
        cfg: HarnessAgentConfig,
        mock_model_factory: Callable[[], Any],
        stub_create_deep_agent: Any,
    ) -> None:
        from deepagents.backends import FilesystemBackend

        with mock_model_factory(), stub_create_deep_agent:
            agent = HarnessAgent(cfg)
        assert isinstance(agent.backend, FilesystemBackend)

    def test_config_property_round_trips(
        self,
        cfg: HarnessAgentConfig,
        mock_model_factory: Callable[[], Any],
        stub_create_deep_agent: Any,
    ) -> None:
        with mock_model_factory(), stub_create_deep_agent:
            agent = HarnessAgent(cfg)
        assert agent.config is cfg


# ---------------------------------------------------------------------------
# Checkpointer resolution
# ---------------------------------------------------------------------------


class TestCheckpointerResolution:
    """``_resolve_checkpointer`` should: explicit override > Memory > SqliteSaver."""

    def test_memory_instance_used_as_checkpointer_when_enabled(
        self,
        tmp_path: Path,
        mock_model_factory: Callable[[], Any],
    ) -> None:
        from octop_memory import Memory

        captured: dict[str, Any] = {}

        def fake_create(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return MagicMock(name="fake-graph")

        cfg = HarnessAgentConfig(
            name="test-agent",
            workspace_dir=tmp_path,
            backend={"type": "filesystem", "root_dir": str(tmp_path), "virtual_mode": False},
            providers=[
                ProviderConfig(
                    id="p",
                    base_url="https://x",
                    api_key="k",
                    models=[ModelConfig(id="text", input=["text"])],
                ),
            ],
            default_model="p/text",
            memory_enabled=True,
        )
        with mock_model_factory(), patch("deepagents.create_deep_agent", side_effect=fake_create):
            agent = HarnessAgent(cfg)

        # Memory acts as the checkpointer (it inherits BaseCheckpointSaver).
        assert isinstance(agent.memory, Memory)
        assert captured["checkpointer"] is agent.memory
        assert agent.checkpointer is agent.memory
        agent.close()

    def test_falls_back_to_sqlite_when_memory_disabled(
        self,
        tmp_path: Path,
        mock_model_factory: Callable[[], Any],
    ) -> None:
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            backend={"type": "filesystem", "root_dir": str(tmp_path), "virtual_mode": False},
            providers=[
                ProviderConfig(
                    id="p",
                    base_url="https://x",
                    api_key="k",
                    models=[ModelConfig(id="text")],
                ),
            ],
            default_model="p/text",
            memory_enabled=False,
        )
        captured: dict[str, Any] = {}

        def fake_create(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return MagicMock(name="fake-graph")

        with mock_model_factory(), patch("deepagents.create_deep_agent", side_effect=fake_create):
            agent = HarnessAgent(cfg)

        assert agent.memory is None
        # Default fallback: an AsyncSqliteSaver instance kept open on the agent
        # (async so it works under the async ``stream`` / ``call`` paths).
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        assert isinstance(captured["checkpointer"], AsyncSqliteSaver)
        agent.close()

    def test_explicit_checkpointer_overrides_memory(
        self,
        cfg: HarnessAgentConfig,
        mock_model_factory: Callable[[], Any],
    ) -> None:
        from dataclasses import replace

        sentinel = MagicMock(name="user-checkpointer")
        cfg = replace(cfg, checkpointer=sentinel)
        captured: dict[str, Any] = {}

        def fake_create(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return MagicMock(name="fake-graph")

        with mock_model_factory(), patch("deepagents.create_deep_agent", side_effect=fake_create):
            HarnessAgent(cfg)

        # Explicit instance wins over Memory.
        assert captured["checkpointer"] is sentinel

    def test_explicit_false_disables_checkpointer(
        self,
        cfg: HarnessAgentConfig,
        mock_model_factory: Callable[[], Any],
    ) -> None:
        from dataclasses import replace

        cfg = replace(cfg, checkpointer=False)
        captured: dict[str, Any] = {}

        def fake_create(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return MagicMock(name="fake-graph")

        with mock_model_factory(), patch("deepagents.create_deep_agent", side_effect=fake_create):
            HarnessAgent(cfg)

        assert captured["checkpointer"] is False


# ---------------------------------------------------------------------------
# Protocol integration
# ---------------------------------------------------------------------------


class TestProtocolIntegration:
    def test_agent_has_protocol_property(
        self,
        cfg: HarnessAgentConfig,
        mock_model_factory: Callable[[], Any],
        stub_create_deep_agent: Any,
    ) -> None:
        with mock_model_factory(), stub_create_deep_agent:
            agent = HarnessAgent(cfg)
        assert agent.protocol.name == "langgraph"

    def test_get_protocol_returns_cached_instance(
        self,
        cfg: HarnessAgentConfig,
        mock_model_factory: Callable[[], Any],
        stub_create_deep_agent: Any,
    ) -> None:
        with mock_model_factory(), stub_create_deep_agent:
            agent = HarnessAgent(cfg)
        proto1 = agent.get_protocol("openai")
        proto2 = agent.get_protocol("openai")
        assert proto1 is proto2

    @pytest.mark.asyncio
    async def test_call_delegates_to_protocol(
        self,
        cfg: HarnessAgentConfig,
        mock_model_factory: Callable[[], Any],
    ) -> None:
        fake_graph = MagicMock(name="graph")
        fake_graph.ainvoke = AsyncMock(return_value={"messages": []})
        with mock_model_factory(), patch("deepagents.create_deep_agent", return_value=fake_graph):
            agent = HarnessAgent(cfg)

        result = await agent.call("hello")
        # The default protocol is langgraph which delegates to graph.ainvoke
        fake_graph.ainvoke.assert_called_once()
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_call_with_protocol_override(
        self,
        cfg: HarnessAgentConfig,
        mock_model_factory: Callable[[], Any],
    ) -> None:
        fake_graph = MagicMock(name="graph")
        fake_graph.ainvoke = AsyncMock(return_value={"messages": []})
        with mock_model_factory(), patch("deepagents.create_deep_agent", return_value=fake_graph):
            agent = HarnessAgent(cfg)

        result = await agent.call("hello", protocol="openai")
        # OpenAI protocol wraps in ChatCompletion format
        assert "id" in result
        assert "object" in result
        assert result["object"] == "chat.completion"
        assert "choices" in result


# ---------------------------------------------------------------------------
# model_factory injection
# ---------------------------------------------------------------------------


class TestHarnessAgentModelFactory:
    def test_accepts_external_model_factory(self, tmp_path: Path) -> None:
        """When model_factory is passed, HarnessAgent must use it, not build its own."""
        from octop_harness.config import ModelConfig, ProviderConfig
        from octop_harness.llm.factory import ChatModelFactory

        providers = [
            ProviderConfig(
                id="p",
                base_url="https://x",
                api_key="k",
                models=[ModelConfig(id="m")],
            )
        ]
        factory = ChatModelFactory(providers)
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            providers=providers,
            default_model="p/m",
        )
        with patch("octop_harness.agent.deepagents.create_deep_agent"):
            agent = HarnessAgent(cfg, model_factory=factory)
        assert agent._model_factory is factory

    def test_no_factory_builds_own(self, tmp_path: Path) -> None:
        """When model_factory is not passed, HarnessAgent builds its own."""
        from octop_harness.config import ModelConfig, ProviderConfig
        from octop_harness.llm.factory import ChatModelFactory

        providers = [
            ProviderConfig(
                id="p",
                base_url="https://x",
                api_key="k",
                models=[ModelConfig(id="m")],
            )
        ]
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            providers=providers,
            default_model="p/m",
        )
        with patch("octop_harness.agent.deepagents.create_deep_agent"):
            agent = HarnessAgent(cfg)
        assert isinstance(agent._model_factory, ChatModelFactory)

    def test_injected_factory_syncs_providers_when_config_empty(self, tmp_path: Path) -> None:
        """Shared factory from HarnessAgentManager may be the sole provider source."""
        from octop_harness.config import ModelConfig, ProviderConfig
        from octop_harness.llm.factory import ChatModelFactory

        providers = [
            ProviderConfig(
                id="p",
                base_url="https://x",
                api_key="k",
                models=[ModelConfig(id="m")],
            )
        ]
        factory = ChatModelFactory(providers)
        cfg = HarnessAgentConfig(workspace_dir=tmp_path)
        with patch("octop_harness.agent.deepagents.create_deep_agent"):
            agent = HarnessAgent(cfg, model_factory=factory)
        assert agent._model_factory is factory
        assert len(agent.config.providers) == 1
        assert agent.config.providers[0].id == "p"
        assert agent._seed_model_ref == "p/m"


# ---------------------------------------------------------------------------
# aget_history
# ---------------------------------------------------------------------------


class TestAgetHistory:
    """Tests for HarnessAgent.aget_history()."""

    def _make_agent(self, tmp_path: Path, checkpointer: Any) -> HarnessAgent:
        cfg = HarnessAgentConfig(
            name="hist-agent",
            workspace_dir=tmp_path,
            backend={"type": "filesystem", "root_dir": str(tmp_path), "virtual_mode": False},
            providers=[
                ProviderConfig(
                    id="p",
                    base_url="https://x",
                    api_key="k",
                    models=[ModelConfig(id="text", input=["text"])],
                ),
            ],
            default_model="p/text",
            checkpointer=checkpointer,
            memory_enabled=False,
        )
        with (
            patch("langchain_openai.ChatOpenAI", return_value=MagicMock()),
            patch("deepagents.create_deep_agent", return_value=MagicMock()),
        ):
            return HarnessAgent(cfg)

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_checkpointer(self, tmp_path: Path) -> None:
        agent = self._make_agent(tmp_path, checkpointer=False)
        result = await agent.aget_history("thread-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_thread_not_found(self, tmp_path: Path) -> None:
        async def _empty_alist(
            config: Any,
            *,
            before: Any = None,
            limit: Any = None,
            filter: Any = None,
        ) -> Any:
            return
            yield  # make it an async generator

        fake_cp = MagicMock()
        fake_cp.alist = _empty_alist
        agent = self._make_agent(tmp_path, checkpointer=fake_cp)
        result = await agent.aget_history("nonexistent-thread")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_messages_from_latest_checkpoint(self, tmp_path: Path) -> None:
        from langchain_core.messages import AIMessage, HumanMessage

        msgs = [HumanMessage(content="hi"), AIMessage(content="hello")]

        async def _alist(
            config: Any,
            *,
            before: Any = None,
            limit: Any = None,
            filter: Any = None,
        ) -> Any:
            fake_tuple = MagicMock()
            fake_tuple.checkpoint = {"channel_values": {"messages": msgs}}
            yield fake_tuple

        fake_cp = MagicMock()
        fake_cp.alist = _alist
        agent = self._make_agent(tmp_path, checkpointer=fake_cp)
        agent._graph.aget_state = AsyncMock(
            side_effect=AssertionError("aget_state must not run when checkpoint has messages"),
        )
        result = await agent.aget_history("thread-1")
        assert result == msgs
        agent._graph.aget_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_back_to_graph_when_checkpoint_messages_empty(self, tmp_path: Path) -> None:
        from langchain_core.messages import AIMessage, HumanMessage

        graph_msgs = [HumanMessage(content="hi"), AIMessage(content="hello")]

        async def _alist(
            config: Any,
            *,
            before: Any = None,
            limit: Any = None,
            filter: Any = None,
        ) -> Any:
            fake_tuple = MagicMock()
            fake_tuple.checkpoint = {"channel_values": {"skills_metadata": []}}
            yield fake_tuple

        fake_cp = MagicMock()
        fake_cp.alist = _alist

        fake_graph = MagicMock()
        fake_state = MagicMock()
        fake_state.values = {"messages": graph_msgs}
        fake_graph.aget_state = AsyncMock(return_value=fake_state)

        with (
            patch("langchain_openai.ChatOpenAI", return_value=MagicMock()),
            patch("deepagents.create_deep_agent", return_value=fake_graph),
        ):
            cfg = HarnessAgentConfig(
                name="hist-agent",
                workspace_dir=tmp_path,
                backend={"type": "filesystem", "root_dir": str(tmp_path), "virtual_mode": False},
                providers=[
                    ProviderConfig(
                        id="p",
                        base_url="https://x",
                        api_key="k",
                        models=[ModelConfig(id="text", input=["text"])],
                    ),
                ],
                default_model="p/text",
                checkpointer=fake_cp,
                memory_enabled=False,
            )
            agent = HarnessAgent(cfg)

        result = await agent.aget_history("thread-1")
        assert result == graph_msgs
        fake_graph.aget_state.assert_awaited_once_with({"configurable": {"thread_id": "thread-1"}})

    @pytest.mark.asyncio
    async def test_limit_truncates_to_most_recent(self, tmp_path: Path) -> None:
        from langchain_core.messages import HumanMessage

        msgs = [HumanMessage(content=str(i)) for i in range(10)]

        async def _alist(
            config: Any,
            *,
            before: Any = None,
            limit: Any = None,
            filter: Any = None,
        ) -> Any:
            fake_tuple = MagicMock()
            fake_tuple.checkpoint = {"channel_values": {"messages": msgs}}
            yield fake_tuple

        fake_cp = MagicMock()
        fake_cp.alist = _alist
        agent = self._make_agent(tmp_path, checkpointer=fake_cp)
        result = await agent.aget_history("thread-1", limit=3)
        assert result == msgs[-3:]

    @pytest.mark.asyncio
    async def test_before_cursor_passed_to_alist(self, tmp_path: Path) -> None:
        from langchain_core.messages import HumanMessage

        received_before: list[Any] = []

        async def _alist(
            config: Any,
            *,
            before: Any = None,
            limit: Any = None,
            filter: Any = None,
        ) -> Any:
            received_before.append(before)
            fake_tuple = MagicMock()
            fake_tuple.checkpoint = {"channel_values": {"messages": [HumanMessage(content="x")]}}
            yield fake_tuple

        fake_cp = MagicMock()
        fake_cp.alist = _alist
        agent = self._make_agent(tmp_path, checkpointer=fake_cp)
        await agent.aget_history("thread-1", before="ckpt-abc")
        assert received_before[0] == {"configurable": {"checkpoint_id": "ckpt-abc"}}

    @pytest.mark.asyncio
    async def test_returns_empty_on_checkpointer_exception(self, tmp_path: Path) -> None:
        async def _boom(
            config: Any,
            *,
            before: Any = None,
            limit: Any = None,
            filter: Any = None,
        ) -> Any:
            raise RuntimeError("db gone")
            yield  # make it an async generator

        fake_cp = MagicMock()
        fake_cp.alist = _boom
        agent = self._make_agent(tmp_path, checkpointer=fake_cp)
        result = await agent.aget_history("thread-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_falls_back_to_sync_list_when_alist_unsupported(self, tmp_path: Path) -> None:
        from langchain_core.messages import HumanMessage

        msgs = [HumanMessage(content="sync")]

        async def _alist(
            config: Any,
            *,
            before: Any = None,
            limit: Any = None,
            filter: Any = None,
        ) -> Any:
            raise NotImplementedError("sync saver")
            yield

        def _list(
            config: Any,
            *,
            before: Any = None,
            limit: Any = None,
            filter: Any = None,
        ) -> Any:
            fake_tuple = MagicMock()
            fake_tuple.checkpoint = {"channel_values": {"messages": msgs}}
            yield fake_tuple

        fake_cp = MagicMock()
        fake_cp.alist = _alist
        fake_cp.list = _list
        agent = self._make_agent(tmp_path, checkpointer=fake_cp)
        result = await agent.aget_history("thread-1")
        assert result == msgs


# ---------------------------------------------------------------------------
# aappend_messages
# ---------------------------------------------------------------------------


class TestAappendMessages:
    """Tests for HarnessAgent.aappend_messages()."""

    @pytest.mark.asyncio
    async def test_appends_stamped_messages_through_graph(self, tmp_path: Path) -> None:
        from langchain_core.messages import AIMessage, HumanMessage

        from octop_harness.messages import CHECKPOINT_TS_KEY

        fake_cp = MagicMock()
        agent = TestAgetHistory()._make_agent(tmp_path, checkpointer=fake_cp)
        agent._graph.aupdate_state = AsyncMock()

        appended = await agent.aappend_messages(
            "thread-1",
            [
                HumanMessage(content="scheduled task", id="cron:run-1:human"),
                AIMessage(content="drink water"),
            ],
        )

        assert [message.id for message in appended] == [
            "cron:run-1:human",
            appended[1].id,
        ]
        assert appended[1].id
        assert all(CHECKPOINT_TS_KEY in message.additional_kwargs for message in appended)
        timestamps = {message.additional_kwargs[CHECKPOINT_TS_KEY] for message in appended}
        assert len(timestamps) == 1
        agent._graph.aupdate_state.assert_awaited_once_with(
            {"configurable": {"thread_id": "thread-1"}},
            {"messages": appended},
        )

    @pytest.mark.asyncio
    async def test_preserves_ids_and_timestamps_for_idempotent_retry(self, tmp_path: Path) -> None:
        from langchain_core.messages import HumanMessage

        from octop_harness.messages import CHECKPOINT_TS_KEY

        fake_cp = MagicMock()
        agent = TestAgetHistory()._make_agent(tmp_path, checkpointer=fake_cp)
        agent._graph.aupdate_state = AsyncMock()
        original = HumanMessage(
            content="scheduled task",
            id="cron:run-1:human",
            additional_kwargs={CHECKPOINT_TS_KEY: 123},
        )

        appended = await agent.aappend_messages("thread-1", [original])

        assert appended == [original]

    @pytest.mark.asyncio
    async def test_rejects_append_without_checkpointer(self, tmp_path: Path) -> None:
        from langchain_core.messages import HumanMessage

        agent = TestAgetHistory()._make_agent(tmp_path, checkpointer=False)

        with pytest.raises(RuntimeError, match="without a checkpointer"):
            await agent.aappend_messages("thread-1", [HumanMessage(content="hi")])

    @pytest.mark.asyncio
    async def test_validates_thread_and_messages(self, tmp_path: Path) -> None:
        from langchain_core.messages import HumanMessage

        agent = TestAgetHistory()._make_agent(tmp_path, checkpointer=MagicMock())

        with pytest.raises(ValueError, match="thread_id"):
            await agent.aappend_messages(" ", [HumanMessage(content="hi")])
        with pytest.raises(ValueError, match="messages"):
            await agent.aappend_messages("thread-1", [])


# ---------------------------------------------------------------------------
# adelete_thread
# ---------------------------------------------------------------------------


class TestAdeleteThread:
    """Tests for HarnessAgent.adelete_thread()."""

    @pytest.mark.asyncio
    async def test_returns_false_when_no_checkpointer(self, tmp_path: Path) -> None:
        agent = TestAgetHistory()._make_agent(tmp_path, checkpointer=False)
        result = await agent.adelete_thread("thread-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_prefers_async_delete_when_available(self, tmp_path: Path) -> None:
        fake_cp = MagicMock()
        fake_cp.adelete_thread = AsyncMock()
        fake_cp.delete_thread = MagicMock(
            side_effect=AssertionError("must prefer adelete_thread over sync delete_thread"),
        )
        agent = TestAgetHistory()._make_agent(tmp_path, checkpointer=fake_cp)
        result = await agent.adelete_thread("thread-1")
        assert result is True
        fake_cp.adelete_thread.assert_awaited_once_with("thread-1")

    @pytest.mark.asyncio
    async def test_falls_back_to_sync_delete_thread(self, tmp_path: Path) -> None:
        fake_cp = MagicMock(spec=["delete_thread"])
        agent = TestAgetHistory()._make_agent(tmp_path, checkpointer=fake_cp)
        result = await agent.adelete_thread("thread-1")
        assert result is True
        fake_cp.delete_thread.assert_called_once_with("thread-1")

    @pytest.mark.asyncio
    async def test_raises_when_saver_does_not_support_delete(self, tmp_path: Path) -> None:
        fake_cp = MagicMock(spec=[])  # neither adelete_thread nor delete_thread
        agent = TestAgetHistory()._make_agent(tmp_path, checkpointer=fake_cp)
        with pytest.raises(NotImplementedError):
            await agent.adelete_thread("thread-1")

    @pytest.mark.asyncio
    async def test_propagates_unexpected_delete_errors(self, tmp_path: Path) -> None:
        """A configured checkpointer that fails mid-delete must not look like success."""
        fake_cp = MagicMock(spec=["delete_thread"])
        fake_cp.delete_thread.side_effect = RuntimeError("db unavailable")
        agent = TestAgetHistory()._make_agent(tmp_path, checkpointer=fake_cp)
        with pytest.raises(RuntimeError, match="db unavailable"):
            await agent.adelete_thread("thread-1")


class TestMcpIntegration:
    def test_loads_mcp_tools_and_middleware_when_configured(
        self,
        tmp_path: Path,
        mock_model_factory: Callable[[], Any],
    ) -> None:
        from octop_harness.middleware.mcp_tools import MCPToolMiddleware

        fake_tool = MagicMock(name="github_search")
        fake_tool.name = "github_search"
        captured: dict[str, Any] = {}

        def fake_create(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return MagicMock(name="fake-graph")

        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            backend={"type": "filesystem", "root_dir": str(tmp_path), "virtual_mode": False},
            providers=[
                ProviderConfig(
                    id="p",
                    base_url="https://x",
                    api_key="k",
                    models=[ModelConfig(id="text")],
                ),
            ],
            default_model="p/text",
            mcp_server_configs={"github": {"transport": "http", "url": "http://example/mcp"}},
            mcp_default_servers=["github"],
        )

        with (
            mock_model_factory(),
            patch("deepagents.create_deep_agent", side_effect=fake_create),
            patch("octop_harness.agent.load_mcp_tools", return_value=[fake_tool]),
        ):
            HarnessAgent(cfg)

        tool_names = [getattr(t, "name", None) for t in captured["tools"]]
        assert "github_search" in tool_names
        middleware_types = [type(m) for m in captured["middleware"]]
        assert MCPToolMiddleware in middleware_types

    def test_mcp_default_servers_unknown_raises_at_init(
        self,
        tmp_path: Path,
        mock_model_factory: Callable[[], Any],
    ) -> None:
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            backend={"type": "filesystem", "root_dir": str(tmp_path), "virtual_mode": False},
            providers=[
                ProviderConfig(
                    id="p",
                    base_url="https://x",
                    api_key="k",
                    models=[ModelConfig(id="text")],
                ),
            ],
            default_model="p/text",
            mcp_server_configs={"github": {"transport": "http", "url": "http://x"}},
            mcp_default_servers=["missing"],
        )
        with (
            mock_model_factory(),
            patch("deepagents.create_deep_agent", return_value=MagicMock(name="fake-graph")),
            pytest.raises(ValueError, match="mcp_default_servers"),
        ):
            HarnessAgent(cfg)

    def test_reinit_graph_refreshes_cached_protocol_graph(
        self,
        tmp_path: Path,
        mock_model_factory: Callable[[], Any],
    ) -> None:
        counter = {"n": 0}

        def fake_create(**kwargs: Any) -> Any:
            counter["n"] += 1
            return MagicMock(name=f"graph-v{counter['n']}")

        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            backend={"type": "filesystem", "root_dir": str(tmp_path), "virtual_mode": False},
            providers=[
                ProviderConfig(
                    id="p",
                    base_url="https://x",
                    api_key="k",
                    models=[ModelConfig(id="text")],
                ),
            ],
            default_model="p/text",
        )

        with (
            mock_model_factory(),
            patch("deepagents.create_deep_agent", side_effect=fake_create),
            patch("octop_harness.agent.load_mcp_tools", return_value=[]),
        ):
            agent = HarnessAgent(cfg)
            stale_graph = agent.protocol._graph
            agent._init_graph()
            assert agent.protocol._graph is agent._graph
            assert agent.protocol._graph is not stale_graph


class TestBootstrapMiddlewareWiring:
    def test_registers_when_bootstrap_pending(self, tmp_path: Path, mock_model_factory: Callable[[], Any]) -> None:
        from octop_harness.middleware.bootstrap import BootstrapMiddleware

        (tmp_path / BOOTSTRAP_FILENAME).write_text("onboarding", encoding="utf-8")
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            backend={"type": "filesystem", "root_dir": str(tmp_path)},
            bootstrap_enabled=True,
            providers=[
                ProviderConfig(
                    id="p",
                    base_url="https://x",
                    api_key="k",
                    models=[ModelConfig(id="m")],
                ),
            ],
            default_model="p/m",
        )
        with mock_model_factory(), patch("deepagents.create_deep_agent"):
            agent = HarnessAgent(cfg)
        mw = agent._build_bootstrap_middleware()
        assert isinstance(mw, BootstrapMiddleware)
        assert not mw.is_bootstrapped

    def test_registers_before_bootstrap_file_exists(
        self,
        tmp_path: Path,
        mock_model_factory: Callable[[], Any],
    ) -> None:
        from octop_harness.middleware.bootstrap import BootstrapMiddleware

        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            backend={"type": "filesystem", "root_dir": str(tmp_path)},
            bootstrap_enabled=True,
            providers=[
                ProviderConfig(
                    id="p",
                    base_url="https://x",
                    api_key="k",
                    models=[ModelConfig(id="m")],
                ),
            ],
            default_model="p/m",
        )
        with mock_model_factory(), patch("deepagents.create_deep_agent"):
            agent = HarnessAgent(cfg)
        mw = agent._build_bootstrap_middleware()
        assert isinstance(mw, BootstrapMiddleware)

    def test_skips_when_marker_exists(self, tmp_path: Path, mock_model_factory: Callable[[], Any]) -> None:
        (tmp_path / BOOTSTRAP_FILENAME).write_text("onboarding", encoding="utf-8")
        (tmp_path / BOOTSTRAPPED_MARKER).write_text("", encoding="utf-8")
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            backend={"type": "filesystem", "root_dir": str(tmp_path), "virtual_mode": False},
            bootstrap_enabled=True,
            providers=[
                ProviderConfig(
                    id="p",
                    base_url="https://x",
                    api_key="k",
                    models=[ModelConfig(id="m")],
                ),
            ],
            default_model="p/m",
        )
        with mock_model_factory(), patch("deepagents.create_deep_agent"):
            agent = HarnessAgent(cfg)
        assert agent._build_bootstrap_middleware() is None

    def test_omits_interrupt_on_while_bootstrap_pending(
        self,
        tmp_path: Path,
        mock_model_factory: Callable[[], Any],
    ) -> None:
        from octop_harness.security.models import SecurityPolicy

        (tmp_path / BOOTSTRAP_FILENAME).write_text("onboarding", encoding="utf-8")
        base_cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            backend={"type": "filesystem", "root_dir": str(tmp_path), "virtual_mode": False},
            bootstrap_enabled=True,
            providers=[
                ProviderConfig(
                    id="p",
                    base_url="https://x",
                    api_key="k",
                    models=[ModelConfig(id="m")],
                ),
            ],
            default_model="p/m",
        )
        # defaults() keep HITL off; enable it so interrupt_on is populated for this gate.
        policy = SecurityPolicy.merge(SecurityPolicy.defaults(), {"hitl": {"enabled": True}})
        cfg = policy.apply_to_config(base_cfg)
        assert cfg.interrupt_on is not None

        captured: dict[str, Any] = {}

        def fake_create(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return MagicMock(name="fake-graph")

        with mock_model_factory(), patch("deepagents.create_deep_agent", side_effect=fake_create):
            HarnessAgent(cfg)

        # ``ask_user_question`` is a collaboration channel, not an approval gate,
        # so it stays mounted; the security-derived file-tool gates must not.
        assert set(captured.get("interrupt_on", {})) == {"ask_user_question"}

    def test_passes_interrupt_on_after_bootstrap(
        self,
        tmp_path: Path,
        mock_model_factory: Callable[[], Any],
    ) -> None:
        from octop_harness.security.models import SecurityPolicy

        (tmp_path / BOOTSTRAP_FILENAME).write_text("onboarding", encoding="utf-8")
        (tmp_path / BOOTSTRAPPED_MARKER).write_text("", encoding="utf-8")
        base_cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            backend={"type": "filesystem", "root_dir": str(tmp_path), "virtual_mode": False},
            bootstrap_enabled=True,
            providers=[
                ProviderConfig(
                    id="p",
                    base_url="https://x",
                    api_key="k",
                    models=[ModelConfig(id="m")],
                ),
            ],
            default_model="p/m",
        )
        policy = SecurityPolicy.merge(SecurityPolicy.defaults(), {"hitl": {"enabled": True}})
        cfg = policy.apply_to_config(base_cfg)
        captured: dict[str, Any] = {}

        def fake_create(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return MagicMock(name="fake-graph")

        with mock_model_factory(), patch("deepagents.create_deep_agent", side_effect=fake_create):
            HarnessAgent(cfg)

        assert captured["interrupt_on"] is not None
        assert "write_file" in captured["interrupt_on"]

    def test_disabled_via_config(self, tmp_path: Path, mock_model_factory: Callable[[], Any]) -> None:
        (tmp_path / BOOTSTRAP_FILENAME).write_text("onboarding", encoding="utf-8")
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            bootstrap_enabled=False,
            providers=[
                ProviderConfig(
                    id="p",
                    base_url="https://x",
                    api_key="k",
                    models=[ModelConfig(id="m")],
                ),
            ],
            default_model="p/m",
        )
        with mock_model_factory(), patch("deepagents.create_deep_agent"):
            agent = HarnessAgent(cfg)
        assert agent._build_bootstrap_middleware() is None


class TestHarnessAgentIsBootstrapped:
    def test_matches_middleware_marker(self, tmp_path: Path, mock_model_factory: Callable[[], Any]) -> None:
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            backend={"type": "filesystem", "root_dir": str(tmp_path), "virtual_mode": False},
            bootstrap_enabled=True,
            providers=[
                ProviderConfig(
                    id="p",
                    base_url="https://x",
                    api_key="k",
                    models=[ModelConfig(id="m")],
                ),
            ],
            default_model="p/m",
        )
        with mock_model_factory(), patch("deepagents.create_deep_agent"):
            agent = HarnessAgent(cfg)

        assert agent.is_bootstrapped() is False
        (tmp_path / BOOTSTRAPPED_MARKER).write_text("", encoding="utf-8")
        assert agent.is_bootstrapped() is True

    def test_true_when_bootstrap_disabled(self, tmp_path: Path, mock_model_factory: Callable[[], Any]) -> None:
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            backend={"type": "filesystem", "root_dir": str(tmp_path), "virtual_mode": False},
            bootstrap_enabled=False,
            providers=[
                ProviderConfig(
                    id="p",
                    base_url="https://x",
                    api_key="k",
                    models=[ModelConfig(id="m")],
                ),
            ],
            default_model="p/m",
        )
        with mock_model_factory(), patch("deepagents.create_deep_agent"):
            agent = HarnessAgent(cfg)

        assert agent.is_bootstrapped() is True


class TestAgetHistoryTimestamps:
    """History returns write-time stamps as-is; no read-path backfill."""

    @pytest.mark.asyncio
    async def test_returns_persisted_checkpoint_ts(self, tmp_path: Path) -> None:
        from langchain_core.messages import HumanMessage

        from octop_harness.messages import CHECKPOINT_TS_KEY

        human = HumanMessage(
            content="hello",
            id="m-1",
            additional_kwargs={CHECKPOINT_TS_KEY: 1_700_000_000_000},
        )

        async def _alist(
            config: Any,
            *,
            before: Any = None,
            limit: Any = None,
            filter: Any = None,
        ) -> Any:
            fake_tuple = MagicMock()
            fake_tuple.checkpoint = {"channel_values": {"messages": [human]}}
            yield fake_tuple

        fake_cp = MagicMock()
        fake_cp.alist = _alist
        agent = TestAgetHistory()._make_agent(tmp_path, checkpointer=fake_cp)
        agent._graph.aget_state = AsyncMock(
            side_effect=AssertionError("must not backfill via graph state"),
        )
        history = await agent.aget_history("thr_test", limit=10)

        assert len(history) == 1
        assert history[0].additional_kwargs[CHECKPOINT_TS_KEY] == 1_700_000_000_000

    @pytest.mark.asyncio
    async def test_does_not_backfill_missing_checkpoint_ts(self, tmp_path: Path) -> None:
        from langchain_core.messages import HumanMessage

        from octop_harness.messages import CHECKPOINT_TS_KEY

        human = HumanMessage(content="hello", id="m-1")

        async def _alist(
            config: Any,
            *,
            before: Any = None,
            limit: Any = None,
            filter: Any = None,
        ) -> Any:
            fake_tuple = MagicMock()
            fake_tuple.checkpoint = {"channel_values": {"messages": [human]}}
            yield fake_tuple

        fake_cp = MagicMock()
        fake_cp.alist = _alist
        agent = TestAgetHistory()._make_agent(tmp_path, checkpointer=fake_cp)
        agent._graph.aget_state = AsyncMock(
            side_effect=AssertionError("must not backfill via graph state"),
        )
        history = await agent.aget_history("thr_test", limit=10)

        assert len(history) == 1
        assert CHECKPOINT_TS_KEY not in (history[0].additional_kwargs or {})


class TestAgentVisibleWorkspaceDir:
    def test_scoped_virtual_root_accepts_agent_facing_workspace(
        self,
        tmp_path: Path,
        mock_model_factory: Callable[[], Any],
        stub_create_deep_agent: Any,
    ) -> None:
        """Octop passes ``/.octop/workspaces/<id>``; harness maps disk under root_dir."""
        root = tmp_path / "home"
        host_ws = root / ".octop" / "workspaces" / "J1BT2X"
        host_ws.mkdir(parents=True)
        cfg = HarnessAgentConfig(
            name="vis-ws",
            workspace_dir="/.octop/workspaces/J1BT2X",
            system_files_path=".octop",
            backend={
                "type": "local_shell",
                "root_dir": str(root),
                "virtual_mode": True,
            },
            providers=[
                ProviderConfig(
                    id="p",
                    base_url="https://x",
                    api_key="k",
                    models=[ModelConfig(id="text", input=["text"])],
                ),
            ],
            default_model="p/text",
            memory_enabled=False,
            checkpointer=False,
        )
        with mock_model_factory(), stub_create_deep_agent as create:
            agent = HarnessAgent(cfg)
            assert Path(agent.config.workspace_dir) == Path("/.octop/workspaces/J1BT2X")
            assert agent._workspace_path == host_ws.resolve()
            assert agent._agent_visible_workspace_dir() == Path("/.octop/workspaces/J1BT2X")
            prompt = create.call_args.kwargs["system_prompt"]
            assert "Your working directory is /.octop/workspaces/J1BT2X" in prompt
            assert "Keep routine filesystem tool paths" in prompt
            assert "/.octop/workspaces/J1BT2X/notes.txt" in prompt
            assert "Do not treat `/` as the workspace" in prompt
            assert str(host_ws) not in prompt

    def test_scoped_host_workspace_still_presents_rootfs_path(
        self,
        tmp_path: Path,
        mock_model_factory: Callable[[], Any],
        stub_create_deep_agent: Any,
    ) -> None:
        """Legacy callers that pass the host join still get a rootfs prompt."""
        root = tmp_path / "home"
        ws = root / ".octop" / "workspaces" / "J1BT2X"
        ws.mkdir(parents=True)
        cfg = HarnessAgentConfig(
            name="vis-ws-host",
            workspace_dir=ws,
            backend={
                "type": "local_shell",
                "root_dir": str(root),
                "virtual_mode": True,
            },
            providers=[
                ProviderConfig(
                    id="p",
                    base_url="https://x",
                    api_key="k",
                    models=[ModelConfig(id="text", input=["text"])],
                ),
            ],
            default_model="p/text",
            memory_enabled=False,
            checkpointer=False,
        )
        with mock_model_factory(), stub_create_deep_agent as create:
            agent = HarnessAgent(cfg)
            assert agent._agent_visible_workspace_dir() == Path("/.octop/workspaces/J1BT2X")
            prompt = create.call_args.kwargs["system_prompt"]
            assert "Your working directory is /.octop/workspaces/J1BT2X" in prompt
            assert "Keep routine filesystem tool paths" in prompt
            assert str(ws) not in prompt

    def test_host_rooted_keeps_host_workspace_in_prompt(
        self,
        cfg: HarnessAgentConfig,
        mock_model_factory: Callable[[], Any],
        stub_create_deep_agent: Any,
    ) -> None:
        with mock_model_factory(), stub_create_deep_agent as create:
            agent = HarnessAgent(cfg)
            assert agent._agent_visible_workspace_dir() == Path(cfg.workspace_dir).resolve()
            prompt = create.call_args.kwargs["system_prompt"]
            assert f"Your working directory is {Path(cfg.workspace_dir).resolve()}" in prompt

    def test_compiled_system_prompt_includes_slash_skill_rule(
        self,
        cfg: HarnessAgentConfig,
        mock_model_factory: Callable[[], Any],
        stub_create_deep_agent: Any,
    ) -> None:
        with mock_model_factory(), stub_create_deep_agent as create:
            HarnessAgent(cfg)
            prompt = create.call_args.kwargs["system_prompt"]
        assert render_slash_skill_prompt(language=cfg.language) in prompt
        assert "SKILL.md" in prompt


class TestExplicitVirtualPathTool:
    def test_build_tools_registers_bound_converter(
        self,
        cfg: HarnessAgentConfig,
        mock_model_factory: Callable[[], Any],
        stub_create_deep_agent: Any,
        tmp_path: Path,
    ) -> None:
        root = tmp_path / "root"
        root.mkdir()
        explicit = replace(
            cfg,
            explicit_virtual_paths=True,
            workspace_dir=root,
            backend={
                "type": "filesystem",
                "root_dir": str(root),
                "virtual_mode": True,
            },
        )
        with mock_model_factory(), stub_create_deep_agent as create, HarnessAgent(explicit) as agent:
            registered = create.call_args.kwargs["tools"]
            built = agent._build_tools()
            assert any(getattr(tool, "name", None) == "virtual_to_native_path" for tool in registered)
            tool = next(item for item in built if getattr(item, "name", None) == "virtual_to_native_path")
            result = tool.invoke({"path": "/data/a.txt"})
            assert result == {
                "kind": "native_path",
                "path": os.fspath((root / "data" / "a.txt").resolve()),
            }
            with pytest.raises(ValueError, match="explicit virtual"):
                tool.invoke({"path": "C:/work/data/a.txt"})
            prompt = create.call_args.kwargs["system_prompt"]
            assert "virtual_to_native_path" in prompt
            assert "execute/shell is not rewritten" in prompt

        with mock_model_factory(), stub_create_deep_agent as create, HarnessAgent(cfg) as agent:
            names = [getattr(tool, "name", None) for tool in create.call_args.kwargs["tools"]]
            built_names = [getattr(tool, "name", None) for tool in agent._build_tools()]
            assert "virtual_to_native_path" not in names
            assert "virtual_to_native_path" not in built_names
            prompt = create.call_args.kwargs["system_prompt"]
            assert "execute/shell is not rewritten" not in prompt
