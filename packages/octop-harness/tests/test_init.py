"""Tests for ``HarnessAgent.init_workspace()`` and the template helpers."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from deepagents.middleware.memory import MemoryMiddleware as DeepAgentsMemoryMiddleware
from langchain_core.messages import ToolMessage

from octop_harness.agent import HarnessAgent, InitResult
from octop_harness.backends.workspace import DEFAULT_MEMORY_FILES
from octop_harness.builtin.templates import iter_md_template_files
from octop_harness.config import HarnessAgentConfig, ModelConfig, ProviderConfig
from octop_harness.middleware.bootstrap import BOOTSTRAP_FILENAME, BOOTSTRAPPED_MARKER

# Expected templates in zh/ directory (SOUL.md is memory-only, not seeded by init).
_EXPECTED_ZH_TEMPLATES = {
    *(name for name in DEFAULT_MEMORY_FILES if name != "SOUL.md"),
    BOOTSTRAP_FILENAME,
    "PROACTIVE.md",
}


class TestIterMdTemplateFiles:
    def test_returns_zh_templates(self) -> None:
        names = {name for name, _ in iter_md_template_files("zh")}
        assert _EXPECTED_ZH_TEMPLATES.issubset(names)

    def test_returns_en_templates(self) -> None:
        names = {name for name, _ in iter_md_template_files("en")}
        assert _EXPECTED_ZH_TEMPLATES.issubset(names)  # same file set

    def test_skips_dunder_files(self) -> None:
        names = [name for name, _ in iter_md_template_files("zh")]
        assert all(not n.startswith("__") for n in names)
        assert all(not n.startswith(".") for n in names)
        assert all(n.endswith(".md") for n in names)

    def test_contents_non_empty(self) -> None:
        for name, content in iter_md_template_files("zh"):
            assert content, f"{name} is empty"

    def test_invalid_language_raises(self) -> None:
        with pytest.raises(FileNotFoundError, match="language"):
            iter_md_template_files("fr")


@pytest.fixture
def cfg(tmp_path: Path) -> HarnessAgentConfig:
    return HarnessAgentConfig(
        name="test-init",
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
        language="zh",
    )


@pytest.fixture
def agent(cfg: HarnessAgentConfig) -> HarnessAgent:
    with (
        patch("langchain_openai.ChatOpenAI", return_value=MagicMock()),
        patch("deepagents.create_deep_agent", return_value=MagicMock()),
    ):
        return HarnessAgent(cfg)


class TestInitWorkspaceInstanceMethod:
    def test_completed_bootstrap_restores_all_workspace_context(self, agent: HarnessAgent) -> None:
        agent._config.memory = ()
        agent.workspace.write_text("AGENTS.md", "working instructions", force=True)
        agent.workspace.write_text("MEMORY.md", "user-owned strong memory", force=True)
        agent.workspace.write_text(BOOTSTRAPPED_MARKER, "", force=True)
        with patch("deepagents.create_deep_agent", return_value=MagicMock()) as create:
            agent._init_graph()
        loader = next(m for m in create.call_args.kwargs["middleware"] if type(m) is DeepAgentsMemoryMiddleware)
        assert loader.sources == create.call_args.kwargs["memory"]
        assert loader.system_prompt == "<agent_memory>\n{agent_memory}\n</agent_memory>"
        loaded = loader.before_agent({}, MagicMock(), {})
        assert loaded is not None
        assert set(loaded["memory_contents"].values()) == {"working instructions", "user-owned strong memory"}

    def test_bootstrap_suppression_still_loads_only_strong_memory(self, agent: HarnessAgent) -> None:
        agent._config.memory = ()
        agent._config.bootstrap_enabled = True
        agent.workspace.write_text("AGENTS.md", "bootstrap instructions", force=True)
        agent.workspace.write_text("MEMORY.md", "user-owned strong memory", force=True)
        with patch("deepagents.create_deep_agent", return_value=MagicMock()) as create:
            agent._init_graph()
        loader = next(m for m in create.call_args.kwargs["middleware"] if type(m) is DeepAgentsMemoryMiddleware)
        loaded = loader.before_agent({}, MagicMock(), {})
        assert loaded is not None
        assert list(loaded["memory_contents"].values()) == ["user-owned strong memory"]

    def test_memory_writes_stay_blocked_with_optional_guards_disabled(self, agent: HarnessAgent) -> None:
        agent._config.tool_guard_enabled = False
        agent._config.memory_enabled = False
        with patch("deepagents.create_deep_agent", return_value=MagicMock()) as create:
            agent._init_graph()
        guard = next(m for m in create.call_args.kwargs["middleware"] if m.name == "FilesystemGuardMiddleware")
        request = MagicMock(tool_call={"name": "edit_file", "args": {"file_path": "MEMORY.md"}, "id": "edit-1"})
        handler = MagicMock()
        result = guard.wrap_tool_call(request, handler)
        assert isinstance(result, ToolMessage)
        assert result.status == "error"
        assert "memory_save" in str(result.content)
        handler.assert_not_called()

    def test_seeds_templates_via_backend(self, agent: HarnessAgent) -> None:
        result = agent.init_workspace()

        assert isinstance(result, InitResult)
        assert result.workspace_path == str(agent.config.workspace_dir)
        assert len(result.templates_created) > 0
        assert agent.workspace.exists("AGENTS.md")

    def test_skills_synced(self, agent: HarnessAgent) -> None:
        result = agent.init_workspace()
        assert result.skills_synced is True
        assert agent.workspace.exists("_builtin_skills/.version")

    def test_idempotent_second_call_skips(self, agent: HarnessAgent) -> None:
        first = agent.init_workspace()
        assert first.templates_created

        second = agent.init_workspace()
        assert not second.templates_created
        assert len(second.templates_skipped) >= len(_EXPECTED_ZH_TEMPLATES)
        assert second.skills_synced is False

    def test_user_edits_preserved(self, agent: HarnessAgent) -> None:
        agent.init_workspace()
        agent.workspace.write_text("AGENTS.md", "# custom\n", force=True)

        result = agent.init_workspace()
        assert agent.workspace.read_text("AGENTS.md") == "# custom\n"
        assert str(agent.config.workspace_dir / "AGENTS.md") in result.templates_skipped

    def test_overwrite_replaces_user_edits(self, agent: HarnessAgent) -> None:
        agent.init_workspace()
        agent.workspace.write_text("AGENTS.md", "# custom\n", force=True)

        result = agent.init_workspace(overwrite=True)
        assert agent.workspace.read_text("AGENTS.md") != "# custom\n"
        assert str(agent.config.workspace_dir / "AGENTS.md") in result.templates_overwritten

    def test_include_md_files_false(self, agent: HarnessAgent) -> None:
        result = agent.init_workspace(include_md_files=False)
        assert not result.templates_created
        assert not agent.workspace.exists("AGENTS.md")

    def test_include_skills_false(self, agent: HarnessAgent) -> None:
        result = agent.init_workspace(include_skills=False)
        assert result.skills_synced is False
        assert not agent.workspace.exists("_builtin_skills/.version")

    def test_language_en_uses_en_templates(self, tmp_path: Path) -> None:
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            backend={"type": "filesystem", "root_dir": str(tmp_path), "virtual_mode": False},
            providers=[
                ProviderConfig(
                    id="p",
                    base_url="https://x",
                    api_key="k",
                    models=[ModelConfig(id="m")],
                ),
            ],
            language="en",
        )
        with (
            patch("langchain_openai.ChatOpenAI", return_value=MagicMock()),
            patch("deepagents.create_deep_agent", return_value=MagicMock()),
        ):
            en_agent = HarnessAgent(cfg)

        result = en_agent.init_workspace()
        assert len(result.templates_created) > 0
        content = en_agent.workspace.read_text("AGENTS.md")
        assert content is not None and len(content) > 0


class TestInitResultDataclass:
    def test_defaults(self) -> None:
        r = InitResult(workspace_path="/ws")
        assert r.templates_created == []
        assert r.templates_skipped == []
        assert r.templates_overwritten == []
        assert r.skills_synced is False

    def test_independent_default_lists(self) -> None:
        a = InitResult(workspace_path="/a")
        b = InitResult(workspace_path="/b")
        a.templates_created.append("/a/x")
        assert b.templates_created == []


class TestInitWorkspaceTopLevel:
    """Top-level :func:`octop_harness.init_workspace` — used by CLI bootstrap
    where no provider/agent has been configured yet.

    The argument is the absolute workspace directory itself; templates and
    skills land directly inside it (the underlying backend is rooted at
    that directory, so its virtual ``/`` corresponds to the real path).
    """

    def test_creates_templates_and_skills_on_disk(self, tmp_path: Path) -> None:
        from octop_harness import init_workspace

        ws = tmp_path / "workspace"
        result = init_workspace(ws, language="zh")

        assert isinstance(result, InitResult)
        assert result.workspace_path == str(ws.resolve())
        assert result.templates_created  # non-empty
        assert result.skills_synced is True

        # Templates landed directly inside the workspace directory.
        assert (ws / "AGENTS.md").is_file()
        # Built-in skills synced; the version stamp should exist.
        assert (ws / "_builtin_skills" / ".version").is_file()
        # And at least one packaged skill should have been copied.
        skill_dirs = [p for p in (ws / "_builtin_skills").iterdir() if p.is_dir()]
        assert skill_dirs, "expected at least one builtin skill directory"

    def test_idempotent_second_call(self, tmp_path: Path) -> None:
        from octop_harness import init_workspace

        ws = tmp_path / "workspace"
        first = init_workspace(ws, language="zh")
        assert first.templates_created

        second = init_workspace(ws, language="zh")
        assert not second.templates_created
        assert second.templates_skipped
        assert second.skills_synced is False  # version stamp matched

    def test_overwrite_replaces_user_edits(self, tmp_path: Path) -> None:
        from octop_harness import init_workspace

        ws = tmp_path / "workspace"
        init_workspace(ws, language="zh")
        agents_md = ws / "AGENTS.md"
        agents_md.write_text("# custom\n", encoding="utf-8")

        result = init_workspace(ws, language="zh", overwrite=True)
        assert agents_md.read_text(encoding="utf-8") != "# custom\n"
        assert str(ws / "AGENTS.md") in result.templates_overwritten

    def test_include_md_files_false_skips_templates(self, tmp_path: Path) -> None:
        from octop_harness import init_workspace

        ws = tmp_path / "workspace"
        result = init_workspace(ws, include_md_files=False)
        assert not result.templates_created
        assert not (ws / "AGENTS.md").exists()
        # Skills still flow through.
        assert result.skills_synced is True

    def test_include_skills_false_skips_skills(self, tmp_path: Path) -> None:
        from octop_harness import init_workspace

        ws = tmp_path / "workspace"
        result = init_workspace(ws, include_skills=False)
        assert result.skills_synced is False
        assert not (ws / "_builtin_skills").exists()

    def test_relative_workspace_dir_rejected(self, tmp_path: Path) -> None:
        from octop_harness import init_workspace

        with pytest.raises(ValueError, match="absolute"):
            init_workspace("workspace")  # relative path now invalid

    def test_invalid_language_raises(self, tmp_path: Path) -> None:
        from octop_harness import init_workspace

        with pytest.raises(FileNotFoundError, match="language"):
            init_workspace(tmp_path, language="fr")


class TestProvidersTemplateInit:
    def test_init_writes_providers_template(self, tmp_path: Path) -> None:
        from octop_harness.init import init_workspace

        user_dir = tmp_path / "user-home"
        user_dir.mkdir()

        with patch("octop_harness.init._PROVIDERS_USER_DIR", user_dir):
            init_workspace(tmp_path / "workspace")

        out = user_dir / "providers_template.json"
        assert out.exists()
        data = json.loads(out.read_text())
        assert isinstance(data, list)
        assert len(data) >= 17

    def test_init_does_not_overwrite_existing(self, tmp_path: Path) -> None:
        from octop_harness.init import init_workspace

        user_dir = tmp_path / "user-home"
        user_dir.mkdir()
        existing = user_dir / "providers_template.json"
        existing.write_text('["custom"]', encoding="utf-8")

        with patch("octop_harness.init._PROVIDERS_USER_DIR", user_dir):
            init_workspace(tmp_path / "workspace")

        assert existing.read_text() == '["custom"]'

    def test_init_overwrite_true_replaces(self, tmp_path: Path) -> None:
        from octop_harness.init import init_workspace

        user_dir = tmp_path / "user-home"
        user_dir.mkdir()
        existing = user_dir / "providers_template.json"
        existing.write_text('["old"]', encoding="utf-8")

        with patch("octop_harness.init._PROVIDERS_USER_DIR", user_dir):
            init_workspace(tmp_path / "workspace", overwrite=True)

        data = json.loads(existing.read_text())
        assert isinstance(data, list)
        assert len(data) >= 17
