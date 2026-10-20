# tests/test_manager.py
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from octop_harness.agent import HarnessAgent
from octop_harness.config import HarnessAgentConfig, ModelConfig, ProviderConfig
from octop_harness.init import InitResult
from octop_harness.manager import AgentEntry, HarnessAgentManager
from octop_harness.middleware.bootstrap import BOOTSTRAP_FILENAME
from octop_harness.request import ChatRequest


def _config(tmp_path: Path) -> HarnessAgentConfig:
    return HarnessAgentConfig(
        workspace_dir=tmp_path,
        providers=[
            ProviderConfig(
                id="openai",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                models=[],
            )
        ],
        memory_enabled=False,
        checkpointer=False,
    )


def _mock_agent() -> MagicMock:
    """Return a MagicMock that stands in for a HarnessAgent."""
    agent = MagicMock(spec=HarnessAgent)
    agent.init_workspace.return_value = MagicMock()
    agent.aclose = AsyncMock()
    return agent


class TestAgentEntry:
    def test_fields(self, tmp_path: Path) -> None:
        agent = _mock_agent()
        entry = AgentEntry(
            agent_id="abc-123",
            agent=agent,
            config=_config(tmp_path),
            metadata={"env": "prod"},
            tags=["fast", "gpt4"],
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        assert entry.agent_id == "abc-123"
        assert entry.agent is agent
        assert entry.metadata == {"env": "prod"}
        assert entry.tags == ["fast", "gpt4"]

    def test_defaults(self, tmp_path: Path) -> None:
        entry = AgentEntry(
            agent_id="x",
            agent=_mock_agent(),
            config=_config(tmp_path),
            metadata={},
            tags=[],
            created_at=datetime.now(tz=UTC),
        )
        assert entry.metadata == {}
        assert entry.tags == []


class TestAgentManagerCRUD:
    def test_create_passes_agent_id(self, tmp_path: Path) -> None:
        with patch("octop_harness.manager.HarnessAgent") as mock_cls:
            mock_cls.return_value = _mock_agent()
            mgr = HarnessAgentManager()
            mgr.create_agent(_config(tmp_path), agent_id="abc123")
        assert mock_cls.call_args.kwargs["agent_id"] == "abc123"

    def test_manager_configures_process_logging(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "app-logs"
        mgr = HarnessAgentManager(log_dir=log_dir)
        assert mgr._log_dir == log_dir.resolve()
        assert log_dir.is_dir()

    def test_file_logging_disabled_does_not_open_a_log_file(self, tmp_path: Path) -> None:
        from octop_harness.observability.logging import teardown_logging

        log_dir = tmp_path / "app-logs"
        try:
            mgr = HarnessAgentManager(log_dir=log_dir, file_logging=False)
            assert mgr._log_file is None
            assert mgr._log_dir is None
            assert not log_dir.exists()
            assert logging.getLogger("octop_harness").handlers == []
        finally:
            teardown_logging()

    def test_relative_log_dir_anchors_to_library_default(self) -> None:
        mgr = HarnessAgentManager(log_dir="nested")
        assert mgr._log_dir == (Path.home() / ".octop-harness" / "logs" / "nested").resolve()

    def test_create_auto_id(self, tmp_path: Path) -> None:
        with patch("octop_harness.manager.HarnessAgent") as mock_cls:
            mock_cls.return_value = _mock_agent()
            mgr = HarnessAgentManager()
            entry = mgr.create_agent(_config(tmp_path))
        assert len(entry.agent_id) == 6
        assert all(c in "abcdefghijklmnopqrstuvwxyz0123456789" for c in entry.agent_id)
        assert entry.metadata == {}
        assert entry.tags == []

    def test_create_auto_id_unique(self, tmp_path: Path) -> None:
        with patch("octop_harness.manager.HarnessAgent") as mock_cls:
            mock_cls.return_value = _mock_agent()
            mgr = HarnessAgentManager()
            ids = {mgr.create_agent(_config(tmp_path)).agent_id for _ in range(20)}
        assert len(ids) == 20

    def test_create_custom_id(self, tmp_path: Path) -> None:
        with patch("octop_harness.manager.HarnessAgent") as mock_cls:
            mock_cls.return_value = _mock_agent()
            mgr = HarnessAgentManager()
            entry = mgr.create_agent(_config(tmp_path), agent_id="my-agent")
        assert entry.agent_id == "my-agent"

    def test_create_with_metadata_and_tags(self, tmp_path: Path) -> None:
        with patch("octop_harness.manager.HarnessAgent") as mock_cls:
            mock_cls.return_value = _mock_agent()
            mgr = HarnessAgentManager()
            entry = mgr.create_agent(
                _config(tmp_path),
                metadata={"env": "prod", "version": "2"},
                tags=["fast"],
            )
        assert entry.metadata == {"env": "prod", "version": "2"}
        assert entry.tags == ["fast"]

    def test_create_builds_agent_immediately(self, tmp_path: Path) -> None:
        """HarnessAgent is constructed in create_agent(), not lazily."""
        with patch("octop_harness.manager.HarnessAgent") as mock_cls:
            mock_cls.return_value = _mock_agent()
            mgr = HarnessAgentManager()
            entry = mgr.create_agent(_config(tmp_path))
        mock_cls.assert_called_once()
        assert entry.agent is mock_cls.return_value

    def test_create_calls_init_workspace_by_default(self, tmp_path: Path) -> None:
        mock_agent = _mock_agent()
        with patch("octop_harness.manager.HarnessAgent", return_value=mock_agent):
            mgr = HarnessAgentManager()
            mgr.create_agent(_config(tmp_path))
        mock_agent.init_workspace.assert_called_once()

    def test_create_skips_init_workspace_when_disabled(self, tmp_path: Path) -> None:
        mock_agent = _mock_agent()
        with patch("octop_harness.manager.HarnessAgent", return_value=mock_agent):
            mgr = HarnessAgentManager()
            mgr.create_agent(_config(tmp_path), init_workspace=False)
        mock_agent.init_workspace.assert_not_called()

    def test_create_recompiles_graph_after_seeding_workspace(self, tmp_path: Path) -> None:
        """A fresh workspace writes skills/templates the compiled graph must pick up."""
        mock_agent = _mock_agent()
        mock_agent.init_workspace.return_value = InitResult(
            workspace_path=str(tmp_path),
            templates_created=[f"{tmp_path}/AGENTS.md"],
            skills_synced=True,
        )
        with patch("octop_harness.manager.HarnessAgent", return_value=mock_agent):
            mgr = HarnessAgentManager()
            mgr.create_agent(_config(tmp_path))
        mock_agent._init_graph.assert_called_once()

    def test_create_skips_graph_recompile_when_seed_is_a_no_op(self, tmp_path: Path) -> None:
        """An already-seeded workspace leaves the graph built in ``__init__`` intact."""
        mock_agent = _mock_agent()
        mock_agent.init_workspace.return_value = InitResult(
            workspace_path=str(tmp_path),
            templates_skipped=[f"{tmp_path}/AGENTS.md"],
        )
        with patch("octop_harness.manager.HarnessAgent", return_value=mock_agent):
            mgr = HarnessAgentManager()
            mgr.create_agent(_config(tmp_path))
        mock_agent._init_graph.assert_not_called()

    def test_create_duplicate_id_raises(self, tmp_path: Path) -> None:
        with patch("octop_harness.manager.HarnessAgent") as mock_cls:
            mock_cls.return_value = _mock_agent()
            mgr = HarnessAgentManager()
            mgr.create_agent(_config(tmp_path), agent_id="dup")
            with pytest.raises(ValueError, match=r"already exists"):
                mgr.create_agent(_config(tmp_path), agent_id="dup")

    def test_get_existing(self, tmp_path: Path) -> None:
        with patch("octop_harness.manager.HarnessAgent") as mock_cls:
            mock_cls.return_value = _mock_agent()
            mgr = HarnessAgentManager()
            created = mgr.create_agent(_config(tmp_path), agent_id="a1")
        assert mgr.get_agent("a1") is created

    def test_get_missing_raises(self) -> None:
        mgr = HarnessAgentManager()
        with pytest.raises(KeyError):
            mgr.get_agent("nonexistent")

    def test_remove_closes_agent(self, tmp_path: Path) -> None:
        mock_agent = _mock_agent()
        with patch("octop_harness.manager.HarnessAgent", return_value=mock_agent):
            mgr = HarnessAgentManager()
            mgr.create_agent(_config(tmp_path), agent_id="del-me")
        mgr.remove_agent("del-me")
        mock_agent.close.assert_called_once()
        with pytest.raises(KeyError):
            mgr.get_agent("del-me")

    def test_remove_missing_raises(self) -> None:
        mgr = HarnessAgentManager()
        with pytest.raises(KeyError):
            mgr.remove_agent("ghost")

    def test_close_closes_all_agents(self, tmp_path: Path) -> None:
        agents = [_mock_agent(), _mock_agent()]
        with patch("octop_harness.manager.HarnessAgent") as mock_cls:
            mock_cls.side_effect = agents
            mgr = HarnessAgentManager()
            mgr.create_agent(_config(tmp_path), agent_id="a1")
            mgr.create_agent(_config(tmp_path), agent_id="a2")
        mgr.close()
        for agent in agents:
            agent.close.assert_called_once()
        # Registry cleared after close
        assert mgr.list_agents() == []

    def test_close_is_idempotent(self, tmp_path: Path) -> None:
        mock_agent = _mock_agent()
        with patch("octop_harness.manager.HarnessAgent", return_value=mock_agent):
            mgr = HarnessAgentManager()
            mgr.create_agent(_config(tmp_path))
        mgr.close()
        mgr.close()  # second call must not raise

    def test_context_manager_closes_on_exit(self, tmp_path: Path) -> None:
        mock_agent = _mock_agent()
        with patch("octop_harness.manager.HarnessAgent", return_value=mock_agent), HarnessAgentManager() as mgr:
            mgr.create_agent(_config(tmp_path))
        mock_agent.close.assert_called_once()

    def test_async_context_manager_closes_on_exit(self, tmp_path: Path) -> None:
        import asyncio

        mock_agent = _mock_agent()

        async def run() -> None:
            with patch("octop_harness.manager.HarnessAgent", return_value=mock_agent):
                async with HarnessAgentManager() as mgr:
                    mgr.create_agent(_config(tmp_path))

        asyncio.run(run())
        mock_agent.aclose.assert_awaited_once()


class TestAgentManagerList:
    def _setup(self, tmp_path: Path) -> HarnessAgentManager:
        with patch("octop_harness.manager.HarnessAgent") as mock_cls:
            mock_cls.return_value = _mock_agent()
            mgr = HarnessAgentManager()
            mgr.create_agent(_config(tmp_path), agent_id="a1", metadata={"env": "prod"}, tags=["fast"])
            mgr.create_agent(_config(tmp_path), agent_id="a2", metadata={"env": "dev"}, tags=["fast", "debug"])
            mgr.create_agent(_config(tmp_path), agent_id="a3", metadata={"env": "prod", "region": "us"}, tags=["slow"])
        return mgr

    def test_list_all(self, tmp_path: Path) -> None:
        mgr = self._setup(tmp_path)
        assert len(mgr.list_agents()) == 3

    def test_list_by_agent_id(self, tmp_path: Path) -> None:
        mgr = self._setup(tmp_path)
        result = mgr.list_agents(agent_id="a2")
        assert len(result) == 1
        assert result[0].agent_id == "a2"

    def test_list_by_metadata_subset(self, tmp_path: Path) -> None:
        mgr = self._setup(tmp_path)
        result = mgr.list_agents(metadata={"env": "prod"})
        assert {e.agent_id for e in result} == {"a1", "a3"}

    def test_list_by_metadata_multi_key(self, tmp_path: Path) -> None:
        mgr = self._setup(tmp_path)
        result = mgr.list_agents(metadata={"env": "prod", "region": "us"})
        assert len(result) == 1
        assert result[0].agent_id == "a3"

    def test_list_by_tags_and(self, tmp_path: Path) -> None:
        mgr = self._setup(tmp_path)
        result = mgr.list_agents(tags=["fast", "debug"])
        assert len(result) == 1
        assert result[0].agent_id == "a2"

    def test_list_combined_filters(self, tmp_path: Path) -> None:
        mgr = self._setup(tmp_path)
        result = mgr.list_agents(metadata={"env": "prod"}, tags=["fast"])
        assert len(result) == 1
        assert result[0].agent_id == "a1"

    def test_list_no_match(self, tmp_path: Path) -> None:
        mgr = self._setup(tmp_path)
        assert mgr.list_agents(tags=["nonexistent"]) == []


class TestAgentManagerCall:
    def test_call_uses_cached_agent(self, tmp_path: Path) -> None:
        import asyncio

        mock_agent = _mock_agent()
        mock_agent.call = AsyncMock(return_value={"messages": []})

        with patch("octop_harness.manager.HarnessAgent", return_value=mock_agent):
            mgr = HarnessAgentManager()
            mgr.create_agent(_config(tmp_path), agent_id="c1")

        request = ChatRequest(messages="hi", thread_id="thread-1")

        result = asyncio.run(mgr.call("c1", request))
        assert result == {"messages": []}
        mock_agent.call.assert_called_once()

    def test_call_unknown_agent_raises(self) -> None:
        import asyncio

        mgr = HarnessAgentManager()

        with pytest.raises(KeyError):
            asyncio.run(mgr.call("ghost", ChatRequest(messages="hi", thread_id="t")))


class TestAgentManagerStream:
    def test_stream_uses_cached_agent(self, tmp_path: Path) -> None:
        """stream() reuses the agent built at create_agent() time."""
        import asyncio

        async def fake_stream(*_args: Any, **_kwargs: Any) -> AsyncIterator[str]:
            for chunk in ["hello", " world"]:
                yield chunk

        mock_agent = _mock_agent()
        mock_agent.stream = fake_stream

        with patch("octop_harness.manager.HarnessAgent", return_value=mock_agent):
            mgr = HarnessAgentManager()
            entry = mgr.create_agent(_config(tmp_path), agent_id="s1")

        request = ChatRequest(messages="hi", thread_id="thread-1")

        async def run() -> list[str]:
            return [c async for c in mgr.stream("s1", request)]

        result = asyncio.run(run())
        assert result == ["hello", " world"]
        # HarnessAgent was built once (at create), not again at stream
        assert entry.agent is mock_agent

    def test_stream_accepts_dict_request(self, tmp_path: Path) -> None:
        import asyncio

        async def fake_stream(*_args: Any, **_kwargs: Any) -> AsyncIterator[str]:
            yield "ok"

        mock_agent = _mock_agent()
        mock_agent.stream = fake_stream

        with patch("octop_harness.manager.HarnessAgent", return_value=mock_agent):
            mgr = HarnessAgentManager()
            mgr.create_agent(_config(tmp_path), agent_id="s1")

        request = {"messages": [{"role": "user", "content": "hi"}], "thread_id": "t-dict"}

        async def run() -> list[str]:
            return [c async for c in mgr.stream("s1", request)]

        assert asyncio.run(run()) == ["ok"]

    def test_stream_unknown_agent_raises(self) -> None:
        import asyncio

        mgr = HarnessAgentManager()

        async def run() -> None:
            async for _ in mgr.stream("ghost", ChatRequest(messages="hi", thread_id="t")):
                pass

        with pytest.raises(KeyError):
            asyncio.run(run())

    def test_cancel_stops_stream(self, tmp_path: Path) -> None:
        """cancel() forwards to agent.cancel and stops an in-flight stream."""
        import asyncio

        cancel_event = asyncio.Event()

        async def slow_stream(*_args: Any, **_kwargs: Any) -> AsyncIterator[str]:
            for i in range(10):
                if cancel_event.is_set():
                    break
                yield str(i)
                await asyncio.sleep(0)

        mock_agent = _mock_agent()
        mock_agent.stream = slow_stream
        mock_agent.cancel = lambda _thread_id: cancel_event.set()

        with patch("octop_harness.manager.HarnessAgent", return_value=mock_agent):
            mgr = HarnessAgentManager()
            mgr.create_agent(_config(tmp_path), agent_id="c1")

        request = ChatRequest(messages="hi", thread_id="thread-cancel")

        async def run() -> list[str]:
            chunks: list[str] = []

            async def consume() -> None:
                async for c in mgr.stream("c1", request):
                    chunks.append(c)
                    if len(chunks) == 3:
                        mgr.cancel("c1", "thread-cancel")

            await consume()
            return chunks

        result = asyncio.run(run())
        assert len(result) <= 4  # stopped shortly after cancel

    def test_cancel_idempotent(self) -> None:
        """cancel() on nonexistent key does not raise."""
        mgr = HarnessAgentManager()
        mgr.cancel("no-such-agent", "no-such-thread")  # must not raise


class TestPublicExports:
    def test_importable_from_top_level(self) -> None:
        from octop_harness import AgentEntry, HarnessAgentManager

        assert HarnessAgentManager is not None
        assert AgentEntry is not None


class TestAgentManagerListProviderTemplates:
    def test_returns_builtin_presets_by_default(self) -> None:
        from octop_harness.providers import ProviderPreset

        manager = HarnessAgentManager()
        presets = manager.list_provider_templates()
        assert isinstance(presets, list)
        assert len(presets) >= 17
        ids = {p.id for p in presets}
        assert "openai" in ids
        assert "deepseek" in ids
        assert all(isinstance(p, ProviderPreset) for p in presets)

    def test_returns_custom_presets_from_path(self, tmp_path: Path) -> None:
        import json

        from octop_harness.providers import ProviderPreset

        custom = tmp_path / "custom.json"
        custom.write_text(
            json.dumps(
                [
                    {
                        "id": "myprovider",
                        "name": "My Provider",
                        "base_url": "https://my.example/v1",
                        "protocol": "openai",
                        "api_key_env": "MY_API_KEY",
                        "api_key_prefix": "",
                        "models": [],
                    }
                ]
            ),
            encoding="utf-8",
        )
        manager = HarnessAgentManager()
        presets = manager.list_provider_templates(custom)
        assert len(presets) == 1
        assert isinstance(presets[0], ProviderPreset)
        assert presets[0].id == "myprovider"

    def test_missing_path_raises_file_not_found(self, tmp_path: Path) -> None:
        manager = HarnessAgentManager()
        with pytest.raises(FileNotFoundError):
            manager.list_provider_templates(tmp_path / "no_such.json")


class TestAgentManagerSharedFactory:
    def _providers(self) -> list[ProviderConfig]:
        return [
            ProviderConfig(
                id="openai",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                models=[],
            )
        ]

    def test_shared_factory_created_when_providers_given(self) -> None:
        from octop_harness.llm.factory import ChatModelFactory

        mgr = HarnessAgentManager(providers=self._providers())
        assert isinstance(mgr.shared_factory, ChatModelFactory)

    def test_shared_factory_none_when_no_providers(self) -> None:
        mgr = HarnessAgentManager()
        assert mgr.shared_factory is None

    def test_create_passes_shared_factory_to_agent(self, tmp_path: Path) -> None:
        """HarnessAgentManager.create_agent must pass shared_factory to HarnessAgent."""
        from octop_harness.llm.factory import ChatModelFactory

        providers = self._providers()
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            providers=providers,
        )

        with patch("octop_harness.manager.HarnessAgent") as mock_cls:
            mock_cls.return_value = _mock_agent()
            mgr = HarnessAgentManager(providers=providers)
            mgr.create_agent(cfg)

        _, kwargs = mock_cls.call_args
        assert isinstance(kwargs.get("model_factory"), ChatModelFactory)
        assert kwargs["model_factory"] is mgr.shared_factory

    def test_create_passes_merged_mcp_configs(self, tmp_path: Path) -> None:
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            providers=self._providers(),
            mcp_server_configs={
                "agent": {"transport": "http", "url": "http://agent"},
            },
        )
        shared = {
            "shared": {"transport": "http", "url": "http://shared"},
            "agent": {"transport": "http", "url": "http://override"},
        }

        with patch("octop_harness.manager.HarnessAgent") as mock_cls:
            mock_cls.return_value = _mock_agent()
            mgr = HarnessAgentManager(mcp_server_configs=shared)
            mgr.create_agent(cfg)

        effective_config = mock_cls.call_args.args[0]
        merged = effective_config.mcp_server_configs
        assert merged["shared"]["url"] == "http://shared"
        assert merged["agent"]["url"] == "http://agent"

    def test_create_merges_shared_mcp_for_default_servers(self, tmp_path: Path) -> None:
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            providers=self._providers(),
            mcp_default_servers=["shared"],
        )
        shared = {"shared": {"transport": "http", "url": "http://shared"}}

        with patch("octop_harness.manager.HarnessAgent") as mock_cls:
            mock_cls.return_value = _mock_agent()
            mgr = HarnessAgentManager(mcp_server_configs=shared)
            entry = mgr.create_agent(cfg)

        assert entry.config.mcp_default_servers == ["shared"]
        assert "shared" in entry.config.mcp_server_configs


class TestAgentManagerMcpIntegration:
    """End-to-end: manager-level MCP configs must reach the live HarnessAgent."""

    def _providers(self) -> list[ProviderConfig]:
        return [
            ProviderConfig(
                id="openai",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                models=[ModelConfig(id="gpt-4o-mini")],
            )
        ]

    def _agent_config(self, tmp_path: Path, **overrides: object) -> HarnessAgentConfig:
        base: dict[str, object] = {
            "workspace_dir": tmp_path,
            "backend": {"type": "filesystem", "root_dir": str(tmp_path), "virtual_mode": True},
            "providers": self._providers(),
            "default_model": "openai/gpt-4o-mini",
        }
        base.update(overrides)
        return HarnessAgentConfig(**base)  # type: ignore[arg-type]

    def test_shared_mcp_tools_loaded_into_agent(self, tmp_path: Path) -> None:
        from octop_harness.middleware.mcp_tools import MCPToolMiddleware

        fake_tool = MagicMock()
        fake_tool.name = "context7_search"
        load_calls: list[dict[str, object]] = []
        graph_kwargs: dict[str, object] = {}

        def fake_load(configs: dict[str, object]) -> list[MagicMock]:
            load_calls.append(dict(configs))
            return [fake_tool]

        def fake_create(**kwargs: object) -> MagicMock:
            graph_kwargs.update(kwargs)
            return MagicMock(name="fake-graph")

        shared = {
            "context7": {"transport": "http", "url": "http://mcp.example/mcp"},
        }
        providers = self._providers()
        mgr = HarnessAgentManager(providers=providers, mcp_server_configs=shared)
        cfg = self._agent_config(
            tmp_path,
            mcp_default_servers=["context7"],
        )

        with (
            patch("langchain_openai.ChatOpenAI", return_value=MagicMock(name="seed-model")),
            patch("deepagents.create_deep_agent", side_effect=fake_create),
            patch("octop_harness.agent.load_mcp_tools", side_effect=fake_load),
        ):
            entry = mgr.create_agent(cfg, init_workspace=False)

        assert load_calls == [shared]
        assert entry.config.mcp_server_configs == shared
        assert entry.agent._mcp_tool_name_set == frozenset({"context7_search"})
        tool_names = [getattr(t, "name", None) for t in graph_kwargs["tools"]]  # type: ignore[index]
        assert "context7_search" in tool_names
        middleware_types = [type(m) for m in graph_kwargs["middleware"]]  # type: ignore[index]
        assert MCPToolMiddleware in middleware_types

    def test_agent_mcp_config_overrides_manager_on_conflict(self, tmp_path: Path) -> None:
        load_calls: list[dict[str, object]] = []

        def fake_load(configs: dict[str, object]) -> list[MagicMock]:
            load_calls.append(dict(configs))
            tool = MagicMock()
            tool.name = "github_search"
            return [tool]

        shared = {
            "github": {"transport": "http", "url": "http://manager"},
            "math": {"transport": "stdio", "command": "math-server"},
        }
        agent_only = {
            "github": {"transport": "http", "url": "http://agent"},
        }
        providers = self._providers()
        mgr = HarnessAgentManager(providers=providers, mcp_server_configs=shared)
        cfg = self._agent_config(tmp_path, mcp_server_configs=agent_only)

        with (
            patch("langchain_openai.ChatOpenAI", return_value=MagicMock(name="seed-model")),
            patch("deepagents.create_deep_agent", return_value=MagicMock(name="fake-graph")),
            patch("octop_harness.agent.load_mcp_tools", side_effect=fake_load),
        ):
            entry = mgr.create_agent(cfg, init_workspace=False)

        expected = {
            "github": {"transport": "http", "url": "http://agent"},
            "math": {"transport": "stdio", "command": "math-server"},
        }
        assert load_calls == [expected]
        assert entry.config.mcp_server_configs == expected

    def test_no_manager_mcp_when_agent_also_empty(self, tmp_path: Path) -> None:
        load_calls: list[dict[str, object]] = []

        def fake_load(configs: dict[str, object]) -> list[MagicMock]:
            load_calls.append(dict(configs))
            return []

        providers = self._providers()
        mgr = HarnessAgentManager(providers=providers)
        cfg = self._agent_config(tmp_path)

        with (
            patch("langchain_openai.ChatOpenAI", return_value=MagicMock(name="seed-model")),
            patch("deepagents.create_deep_agent", return_value=MagicMock(name="fake-graph")),
            patch("octop_harness.agent.load_mcp_tools", side_effect=fake_load),
        ):
            entry = mgr.create_agent(cfg, init_workspace=False)

        assert load_calls == []
        assert entry.agent._mcp_tool_name_set == frozenset()

    def test_manager_mcp_loads_via_mcp_client(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Full chain: manager merge → aload_mcp_tools → agent tool list (no load_mcp_tools mock)."""

        class _Client:
            def __init__(self, configs: dict[str, object], **kwargs: object) -> None:
                self._name = next(iter(configs))

            async def get_tools(self) -> list[MagicMock]:
                tool = MagicMock()
                tool.name = f"{self._name}_echo"
                return [tool]

        monkeypatch.setattr("octop_harness.mcp.MultiServerMCPClient", _Client)
        graph_kwargs: dict[str, object] = {}

        def fake_create(**kwargs: object) -> MagicMock:
            graph_kwargs.update(kwargs)
            return MagicMock(name="fake-graph")

        shared = {
            "demo": {"transport": "http", "url": "http://demo/mcp"},
            "extra": {"transport": "http", "url": "http://extra/mcp"},
        }
        providers = self._providers()
        mgr = HarnessAgentManager(providers=providers, mcp_server_configs=shared)
        cfg = self._agent_config(tmp_path, mcp_default_servers=["demo", "extra"])

        with (
            patch("langchain_openai.ChatOpenAI", return_value=MagicMock(name="seed-model")),
            patch("deepagents.create_deep_agent", side_effect=fake_create),
        ):
            entry = mgr.create_agent(cfg, init_workspace=False)

        tool_names = {getattr(t, "name", None) for t in graph_kwargs["tools"]}  # type: ignore[index]
        assert tool_names >= {"demo_echo", "extra_echo"}
        assert entry.agent._mcp_tool_name_set == frozenset({"demo_echo", "extra_echo"})


class TestBootstrapOnCreate:
    def test_create_agent_includes_bootstrap_middleware_after_init(self, tmp_path: Path) -> None:
        from octop_harness.middleware.bootstrap import BootstrapMiddleware

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
            bootstrap_enabled=True,
            providers=providers,
            default_model="p/m",
            backend={"type": "filesystem", "root_dir": str(tmp_path), "virtual_mode": False},
            memory_enabled=False,
            session_log_enabled=False,
            checkpointer=False,
        )
        graph_kwargs: dict[str, object] = {}

        def fake_create(**kwargs: object) -> MagicMock:
            graph_kwargs.update(kwargs)
            return MagicMock(name="fake-graph")

        with (
            patch("langchain_openai.ChatOpenAI", return_value=MagicMock(name="seed-model")),
            patch("deepagents.create_deep_agent", side_effect=fake_create),
        ):
            mgr = HarnessAgentManager(providers=providers)
            entry = mgr.create_agent(cfg, init_workspace=True)

        assert (tmp_path / BOOTSTRAP_FILENAME).is_file()
        middleware = graph_kwargs.get("middleware", [])
        assert any(isinstance(m, BootstrapMiddleware) for m in middleware)  # type: ignore[union-attr]
        mw = entry.agent._build_bootstrap_middleware()
        assert mw is not None
        assert not mw.is_bootstrapped


class TestHarnessAgentManagerAsyncLifecycle:
    @pytest.mark.asyncio
    async def test_arebuild_agent_replaces_runtime(self, tmp_path: Path) -> None:
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
            backend={"type": "filesystem", "root_dir": str(tmp_path), "virtual_mode": True},
            memory_enabled=False,
            session_log_enabled=False,
            checkpointer=False,
        )
        with (
            patch("langchain_openai.ChatOpenAI", return_value=MagicMock(name="seed-model")),
            patch("deepagents.create_deep_agent", return_value=MagicMock(name="fake-graph")),
        ):
            mgr = HarnessAgentManager(providers=providers)
            created = await mgr.acreate_agent(cfg, agent_id="aid1", init_workspace=True)
            assert created.agent_id == "aid1"
            rebuilt = await mgr.arebuild_agent("aid1", cfg)
            assert rebuilt.agent_id == "aid1"
            mgr.close()


class TestARemoveAgentReleasesOnThisLoop:
    """``aremove_agent`` must await ``aclose`` here, not run ``close`` in a thread.

    It used to be ``asyncio.to_thread(self.remove_agent, ...)``. aiosqlite is
    bound to the calling loop, and the sync-close fallback drives it with
    ``asyncio.run`` from the worker — so the worker waits on a loop that is
    itself blocked waiting for the worker. Octop hit that hang when a chat
    reloaded its MCP servers mid-turn.
    """

    @staticmethod
    def _entry(agent: MagicMock, tmp_path: Path) -> AgentEntry:
        return AgentEntry(
            agent_id="aid",
            agent=agent,
            config=_config(tmp_path),
            metadata={},
            tags=[],
            created_at=datetime(2026, 9, 1, tzinfo=UTC),
        )

    @pytest.mark.asyncio
    async def test_release_runs_on_the_calling_thread(self, tmp_path: Path) -> None:
        import threading

        closed_on: list[int] = []
        agent = _mock_agent()

        async def _aclose() -> None:
            closed_on.append(threading.get_ident())

        agent.aclose = _aclose
        mgr = HarnessAgentManager()
        mgr._registry.add(self._entry(agent, tmp_path))

        await mgr.aremove_agent("aid")

        assert closed_on == [threading.get_ident()]

    @pytest.mark.asyncio
    async def test_sync_close_is_not_used(self, tmp_path: Path) -> None:
        agent = _mock_agent()
        agent.aclose = AsyncMock()
        mgr = HarnessAgentManager()
        mgr._registry.add(self._entry(agent, tmp_path))

        await mgr.aremove_agent("aid")

        agent.aclose.assert_awaited_once()
        agent.close.assert_not_called()

    @pytest.mark.asyncio
    async def test_unknown_agent_is_a_noop(self) -> None:
        mgr = HarnessAgentManager()
        await mgr.aremove_agent("never-registered")  # must not raise

    @pytest.mark.asyncio
    async def test_agent_is_dropped_from_the_registry(self, tmp_path: Path) -> None:
        agent = _mock_agent()
        agent.aclose = AsyncMock()
        mgr = HarnessAgentManager()
        mgr._registry.add(self._entry(agent, tmp_path))

        await mgr.aremove_agent("aid")

        with pytest.raises(KeyError):
            mgr.get_agent("aid")
