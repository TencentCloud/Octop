"""Tests for the bundled built-in Skills (skill-creator / install-skill / …).

The Skills themselves are documents, not code, so the unit-test surface
is intentionally narrow: we verify they ship correctly and that scripted
skills (e.g. jupyter-live-kernel, watchers) are packaged as expected.
"""

from __future__ import annotations

import importlib.util
import re
from importlib import resources
from pathlib import Path
from unittest.mock import patch

import pytest

from octop_harness import HarnessAgent
from octop_harness.builtin.templates import iter_builtin_skills

_SKILLS_PACKAGE = "octop_harness.builtin.skills"
_EN_SKILLS_DIR = "en"

MIGRATED_HERMES_SKILLS = (
    "plan",
    "systematic-debugging",
    "ocr-and-documents",
    "llm-wiki",
    "powerpoint",
    "nano-pdf",
    "ascii-art",
    "ascii-video",
    "manim-video",
    "architecture-diagram",
    "excalidraw",
    "docker-management",
    "watchers",
    "fastmcp",
    "apple-notes",
    "apple-reminders",
    "imessage",
    "findmy",
    "jupyter-live-kernel",
)

ALL_BUILTIN_SKILL_NAMES = (
    "memory-management",
    "using-workspace",
    "skill-creator",
    "install-skill",
    "mcporter",
    *MIGRATED_HERMES_SKILLS,
)


# ---------------------------------------------------------------------------
# Packaging
# ---------------------------------------------------------------------------


class TestSkillsPackaged:
    """Ensure the new built-in Skills are visible via ``importlib.resources``."""

    def test_expected_skills_present(self) -> None:
        root = resources.files(_SKILLS_PACKAGE).joinpath(_EN_SKILLS_DIR)
        names = {entry.name for entry in root.iterdir() if entry.is_dir() and not entry.name.startswith("__")}
        assert {"skill-creator", "install-skill", "plan", "apple-reminders"}.issubset(names)

    @pytest.mark.parametrize("skill_name", ALL_BUILTIN_SKILL_NAMES)
    def test_skill_md_has_frontmatter(self, skill_name: str) -> None:
        # Use iter_builtin_skills to get the correct path (supports en/zh layout).
        skills = iter_builtin_skills("en")
        prefix = f"{skill_name}/SKILL.md"
        skill_files = [(lang, path, content) for lang, path, content, _ in skills if path.startswith(prefix)]
        assert skill_files, f"{skill_name}: SKILL.md not found"
        _, _, content = skill_files[0]
        text = content.decode("utf-8")
        match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
        assert match is not None, f"{skill_name}: missing frontmatter"
        fm = match.group(1)
        assert re.search(r"^name:\s*\S", fm, re.MULTILINE), f"{skill_name}: missing name"
        assert re.search(r"^description:", fm, re.MULTILINE), f"{skill_name}: missing description"

    def test_jupyter_live_kernel_ships_script(self) -> None:
        script = (
            resources.files(_SKILLS_PACKAGE)
            .joinpath(_EN_SKILLS_DIR)
            .joinpath("jupyter-live-kernel")
            .joinpath("scripts")
            .joinpath("jupyter_live_kernel.py")
        )
        assert script.is_file()
        compile(script.read_text(encoding="utf-8"), "jupyter_live_kernel.py", "exec")

    def test_watchers_watermark_defaults_to_workspace(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("WATCHER_STATE_DIR", raising=False)
        monkeypatch.chdir(tmp_path)
        script = (
            resources.files(_SKILLS_PACKAGE)
            .joinpath(_EN_SKILLS_DIR)
            .joinpath("watchers")
            .joinpath("scripts")
            .joinpath("_watermark.py")
        )
        spec = importlib.util.spec_from_file_location("_watchers_watermark", str(script))
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module._state_dir() == tmp_path / "watcher-state"


# ---------------------------------------------------------------------------
# Sync into a workspace
# ---------------------------------------------------------------------------


class TestInitSyncsNewSkills:
    def test_init_copies_all_skills(self, tmp_path: Path) -> None:
        from unittest.mock import MagicMock

        from octop_harness.config import HarnessAgentConfig, ModelConfig, ProviderConfig

        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            backend={"type": "filesystem", "root_dir": str(tmp_path), "virtual_mode": False},
            providers=[ProviderConfig(id="p", base_url="https://x", api_key="k", models=[ModelConfig(id="m")])],
        )
        with (
            patch("langchain_openai.ChatOpenAI", return_value=MagicMock()),
            patch("deepagents.create_deep_agent", return_value=MagicMock()),
        ):
            agent = HarnessAgent(cfg)

        agent.init_workspace()

        for name in ALL_BUILTIN_SKILL_NAMES:
            assert agent.workspace.exists(f"_builtin_skills/{name}/SKILL.md"), f"missing {name}/SKILL.md"
