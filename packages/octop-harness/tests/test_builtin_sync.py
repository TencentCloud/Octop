"""Tests for ``octop_harness.builtin._sync.sync_builtin_skills_to_backend``."""

from __future__ import annotations

from pathlib import Path

import pytest
from deepagents.backends import FilesystemBackend

from octop_harness.backends.workspace import DEFAULT_BUILTIN_SKILLS_DIR, BackendWorkspace
from octop_harness.builtin._sync import sync_builtin_skills_to_backend


@pytest.fixture
def workspace(tmp_path: Path) -> BackendWorkspace:
    return BackendWorkspace(
        FilesystemBackend(root_dir=str(tmp_path), virtual_mode=False),
        tmp_path,
    )


class TestSyncBuiltinSkillsToBackend:
    def test_syncs_skills_to_backend(self, workspace: BackendWorkspace) -> None:
        synced, fallback = sync_builtin_skills_to_backend(workspace, agent_version="0.1.0")
        assert synced is True
        assert fallback == []
        assert workspace.exists(f"{DEFAULT_BUILTIN_SKILLS_DIR}/using-workspace/SKILL.md")
        assert workspace.read_text(f"{DEFAULT_BUILTIN_SKILLS_DIR}/.version") == "0.1.0"

    def test_skips_when_version_matches(self, workspace: BackendWorkspace) -> None:
        sync_builtin_skills_to_backend(workspace, agent_version="0.1.0")
        synced, fallback = sync_builtin_skills_to_backend(workspace, agent_version="0.1.0")
        assert synced is False
        assert fallback == []

    def test_re_syncs_when_version_differs(self, workspace: BackendWorkspace) -> None:
        sync_builtin_skills_to_backend(workspace, agent_version="0.1.0")
        synced, fallback = sync_builtin_skills_to_backend(workspace, agent_version="0.2.0")
        assert synced is True
        assert fallback == []
        assert workspace.read_text(f"{DEFAULT_BUILTIN_SKILLS_DIR}/.version") == "0.2.0"

    def test_zh_overlays_skill_md_and_inherits_en_scripts(self, workspace: BackendWorkspace) -> None:
        from importlib import resources

        synced, fallback = sync_builtin_skills_to_backend(workspace, agent_version="0.1.0", language="zh")
        assert synced is True
        assert fallback == []

        package = resources.files("octop_harness.builtin.skills")
        zh_skill = package.joinpath("zh/watchers/SKILL.md").read_text(encoding="utf-8")
        en_script = package.joinpath("en/watchers/scripts/watch_github.py").read_text(encoding="utf-8")
        assert workspace.read_text(f"{DEFAULT_BUILTIN_SKILLS_DIR}/watchers/SKILL.md") == zh_skill
        assert workspace.read_text(f"{DEFAULT_BUILTIN_SKILLS_DIR}/watchers/scripts/watch_github.py") == en_script
        assert workspace.exists(f"{DEFAULT_BUILTIN_SKILLS_DIR}/jupyter-live-kernel/scripts/jupyter_live_kernel.py")
