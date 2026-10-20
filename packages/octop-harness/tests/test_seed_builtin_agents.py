"""Tests for seeding packaged builtin agents into the workspace."""

from __future__ import annotations

from pathlib import Path

from deepagents.backends import FilesystemBackend

from octop_harness.backends.workspace import DEFAULT_AGENTS_DIR, BackendWorkspace
from octop_harness.builtin._sync import seed_builtin_agents_to_workspace


def _workspace(tmp_path: Path) -> BackendWorkspace:
    backend = FilesystemBackend(root_dir=str(tmp_path), virtual_mode=False)
    return BackendWorkspace(backend, tmp_path)


class TestSeedBuiltinAgents:
    def test_first_run_creates_files(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        result = seed_builtin_agents_to_workspace(ws)
        assert (tmp_path / DEFAULT_AGENTS_DIR / "general-purpose.md").is_file()
        assert result.created
        assert not result.skipped

    def test_second_run_skips_existing(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        seed_builtin_agents_to_workspace(ws)
        second = seed_builtin_agents_to_workspace(ws)
        assert second.skipped
        assert not second.created

    def test_overwrite_replaces(self, tmp_path: Path) -> None:
        ws = _workspace(tmp_path)
        seed_builtin_agents_to_workspace(ws)
        gp = tmp_path / DEFAULT_AGENTS_DIR / "general-purpose.md"
        gp.write_text("stale", encoding="utf-8")
        third = seed_builtin_agents_to_workspace(ws, overwrite=True)
        assert third.overwritten
        assert "General-Purpose Subagent" in gp.read_text(encoding="utf-8")
