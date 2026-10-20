"""Tests for workspace subagent markdown loading."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from deepagents.backends import FilesystemBackend

from octop_harness.agent import HarnessAgent
from octop_harness.backends.workspace import BackendWorkspace
from octop_harness.config import HarnessAgentConfig, ModelConfig, ProviderConfig
from octop_harness.middleware.context_usage import ContextUsageMiddleware
from octop_harness.middleware.tool_order import TaskToolLastMiddleware
from octop_harness.subagents.catalog import DEFAULT_SUBAGENT_EMOJI, list_subagent_summaries
from octop_harness.subagents.loader import (
    collect_agent_markdown_paths,
    load_subagents_from_workspace,
    merge_subagents,
    parse_agent_markdown,
    slug_from_agent_path,
)


def _provider() -> ProviderConfig:
    return ProviderConfig(
        id="ex",
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        models=[ModelConfig(id="gpt-test")],
    )


@pytest.fixture
def workspace(tmp_path: Path) -> BackendWorkspace:
    backend = FilesystemBackend(root_dir=str(tmp_path), virtual_mode=False)
    return BackendWorkspace(backend, tmp_path)


SAMPLE_MD = """---
name: Workflow Optimizer
id: workflow-optimizer
description: Optimizes workflows for efficiency
model: openai:gpt-4.1
tools:
  - current_time
---

# Body

Use tools wisely.
"""


class TestSlugAndParse:
    def test_slug_from_nested_path(self) -> None:
        assert slug_from_agent_path("agents/testing/workflow-optimizer.md") == "testing-workflow-optimizer"

    def test_slug_from_system_files_path(self) -> None:
        assert slug_from_agent_path(".octop/agents/testing/workflow-optimizer.md") == ("testing-workflow-optimizer")

    def test_parse_agent_markdown(self, workspace: BackendWorkspace) -> None:
        parent_tool = MagicMock()
        parent_tool.name = "current_time"
        spec = parse_agent_markdown(
            SAMPLE_MD,
            path_fragment="agents/testing/workflow-optimizer.md",
            parent_tools=[parent_tool],
            workspace=workspace,
        )
        assert spec is not None
        assert spec["name"] == "workflow-optimizer"
        assert spec["description"] == "Optimizes workflows for efficiency"
        assert "Body" in spec["system_prompt"]
        assert spec["model"] == "openai:gpt-4.1"
        assert spec["tools"] == [parent_tool]

    def test_parse_skips_missing_description(self, workspace: BackendWorkspace) -> None:
        text = "---\nname: X\n---\nbody"
        assert parse_agent_markdown(text, path_fragment="agents/x.md", workspace=workspace) is None


class TestCollectAndLoad:
    def test_collect_nested_markdown(self, workspace: BackendWorkspace, tmp_path: Path) -> None:
        target = tmp_path / "agents" / "testing"
        target.mkdir(parents=True)
        (target / "workflow.md").write_text(SAMPLE_MD, encoding="utf-8")
        (target / "README.md").write_text("# readme", encoding="utf-8")
        paths = collect_agent_markdown_paths(workspace, "agents")
        assert paths == ["agents/testing/workflow.md"]

    def test_load_from_workspace(self, workspace: BackendWorkspace, tmp_path: Path) -> None:
        path = tmp_path / "agents" / "workflow.md"
        path.parent.mkdir(parents=True)
        path.write_text(SAMPLE_MD, encoding="utf-8")
        specs = load_subagents_from_workspace(workspace)
        assert len(specs) == 1
        assert specs[0]["name"] == "workflow-optimizer"

    def test_single_system_files_definition_loads_without_duplicate_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        backend = FilesystemBackend(root_dir=str(tmp_path), virtual_mode=False)
        workspace = BackendWorkspace(backend, tmp_path, system_files_path=".octop")
        path = tmp_path / ".octop" / "agents" / "workflow.md"
        path.parent.mkdir(parents=True)
        path.write_text(SAMPLE_MD, encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            specs = load_subagents_from_workspace(workspace)

        assert len(specs) == 1
        assert specs[0]["name"] == "workflow-optimizer"
        assert not any("Duplicate subagent name" in rec.message for rec in caplog.records)

    def test_duplicate_names_from_different_files_still_warn(
        self, workspace: BackendWorkspace, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        first = tmp_path / "agents" / "a" / "same.md"
        first.parent.mkdir(parents=True)
        first.write_text(SAMPLE_MD, encoding="utf-8")
        second = tmp_path / "agents" / "b" / "same.md"
        second.parent.mkdir(parents=True)
        second.write_text(SAMPLE_MD.replace("efficiency", "speed"), encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            specs = load_subagents_from_workspace(workspace)

        assert len(specs) == 1
        assert "speed" in specs[0]["description"]
        assert any("Duplicate subagent name" in rec.message for rec in caplog.records)


class TestMergeSubagents:
    def test_config_overrides_workspace(self) -> None:
        loaded = [{"name": "a", "description": "d", "system_prompt": "w"}]
        config = [{"name": "a", "description": "d2", "system_prompt": "w2"}]
        merged = merge_subagents(loaded, config)
        assert merged[0]["description"] == "d2"


class TestHarnessAgentGraph:
    def test_build_tools_once_and_reuses_order_for_subagents(self, tmp_path: Path) -> None:
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "helper.md").write_text(
            "---\nname: Helper\ndescription: Helps\ntools:\n  - first\n  - second\n---\nDo help.\n",
            encoding="utf-8",
        )
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            providers=[_provider()],
            default_model="ex/gpt-test",
        )
        shared_tools = [MagicMock(), MagicMock()]
        shared_tools[0].name = "first"
        shared_tools[1].name = "second"
        captured: dict[str, Any] = {}

        def fake_create(**kwargs: Any) -> MagicMock:
            captured.update(kwargs)
            return MagicMock()

        with (
            patch("langchain_openai.ChatOpenAI", return_value=MagicMock()),
            patch.object(HarnessAgent, "_build_tools", return_value=shared_tools) as build_tools,
            patch("deepagents.create_deep_agent", side_effect=fake_create),
        ):
            HarnessAgent(cfg)

        build_tools.assert_called_once_with()
        assert captured["tools"] is shared_tools
        assert captured["subagents"][0]["tools"] == shared_tools
        middleware = captured["middleware"]
        assert any(isinstance(m, TaskToolLastMiddleware) for m in middleware)
        assert isinstance(middleware[-1], ContextUsageMiddleware)

    def test_build_graph_passes_merged_subagents(self, tmp_path: Path) -> None:
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "helper.md").write_text(
            "---\nname: Helper\ndescription: Helps\n---\nDo help.\n",
            encoding="utf-8",
        )
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            providers=[_provider()],
            default_model="ex/gpt-test",
            subagents=[{"name": "helper", "description": "override", "system_prompt": "cfg"}],
        )
        captured: dict[str, Any] = {}

        def fake_create(**kwargs: Any) -> MagicMock:
            captured.update(kwargs)
            return MagicMock()

        with (
            patch("langchain_openai.ChatOpenAI", return_value=MagicMock()),
            patch("deepagents.create_deep_agent", side_effect=fake_create),
        ):
            HarnessAgent(cfg)

        subagents = captured.get("subagents")
        assert subagents is not None
        assert len(subagents) == 1
        assert subagents[0]["description"] == "override"

    def test_subagents_auto_load_false_uses_config_only(self, tmp_path: Path) -> None:
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "helper.md").write_text(
            "---\nname: Helper\ndescription: Helps\n---\nDo help.\n",
            encoding="utf-8",
        )
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            providers=[_provider()],
            default_model="ex/gpt-test",
            subagents_auto_load=False,
            subagents=[{"name": "code", "description": "code", "system_prompt": "x"}],
        )
        captured: dict[str, Any] = {}

        def fake_create(**kwargs: Any) -> MagicMock:
            captured.update(kwargs)
            return MagicMock()

        with (
            patch("langchain_openai.ChatOpenAI", return_value=MagicMock()),
            patch("deepagents.create_deep_agent", side_effect=fake_create),
        ):
            HarnessAgent(cfg)

        subagents = captured.get("subagents")
        assert subagents is not None
        assert len(subagents) == 1
        assert subagents[0]["name"] == "code"


class TestSubagentSummaries:
    @pytest.mark.asyncio
    async def test_emoji_from_frontmatter(self, workspace: BackendWorkspace, tmp_path: Path) -> None:
        path = tmp_path / "agents" / "helper.md"
        path.parent.mkdir(parents=True)
        path.write_text(
            "---\nname: Helper\nid: helper\nemoji: 🧰\ndescription: Helps\n---\nBody\n",
            encoding="utf-8",
        )
        rows = await list_subagent_summaries(workspace)
        assert len(rows) == 1
        assert rows[0]["emoji"] == "🧰"

    @pytest.mark.asyncio
    async def test_emoji_defaults_when_missing(self, workspace: BackendWorkspace, tmp_path: Path) -> None:
        path = tmp_path / "agents" / "helper.md"
        path.parent.mkdir(parents=True)
        path.write_text(
            "---\nname: Helper\nid: helper\ndescription: Helps\n---\nBody\n",
            encoding="utf-8",
        )
        rows = await list_subagent_summaries(workspace)
        assert len(rows) == 1
        assert rows[0]["emoji"] == DEFAULT_SUBAGENT_EMOJI
