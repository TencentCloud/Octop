"""Tests for materializing harness built-in tool sources into agent workspaces."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.support.fakes import FakeHarnessAgent

from octop.infra.agents.builtin_tools import BUILTIN_TOOLS_ROOT, sync_builtin_tool_sources


@pytest.mark.asyncio
async def test_sync_materializes_tool_sources_under_system_dir(tmp_path: Path) -> None:
    agent = FakeHarnessAgent(
        workspace_dir=tmp_path,
        virtual_mode=False,
        system_files_path=".octop",
    )

    written = await sync_builtin_tool_sources(agent.workspace)

    assert "browser_use.py" in [Path(p).name for p in written]
    deployed = tmp_path / ".octop" / "builtin" / "tools" / "browser_use.py"
    assert deployed.is_file()
    content = deployed.read_text(encoding="utf-8")
    assert "browser_use" in content
    assert not (tmp_path / "builtin").exists()
    # The read that used to fail (`File .../builtin/tools/browser_use.py not
    # found`) resolves through the workspace facade.
    read_back = await agent.workspace.aread_text(".octop/builtin/tools/browser_use.py")
    assert read_back is not None and "browser_use" in read_back


@pytest.mark.asyncio
async def test_sync_uses_workspace_root_for_legacy_agents(tmp_path: Path) -> None:
    agent = FakeHarnessAgent(workspace_dir=tmp_path, virtual_mode=False)

    written = await sync_builtin_tool_sources(agent.workspace)

    assert any(p.endswith("builtin/tools/browser_use.py") for p in written)
    assert (tmp_path / "builtin" / "tools" / "browser_use.py").is_file()


@pytest.mark.asyncio
async def test_sync_skips_when_version_stamp_matches(tmp_path: Path) -> None:
    agent = FakeHarnessAgent(
        workspace_dir=tmp_path,
        virtual_mode=False,
        system_files_path=".octop",
    )

    first = await sync_builtin_tool_sources(agent.workspace)
    assert first

    deployed = tmp_path / ".octop" / BUILTIN_TOOLS_ROOT / "browser_use.py"
    deployed.write_text("# user-edited marker\n", encoding="utf-8")

    second = await sync_builtin_tool_sources(agent.workspace)

    assert second == []
    # Stamp matched, so the edited copy was left alone.
    assert deployed.read_text(encoding="utf-8") == "# user-edited marker\n"


@pytest.mark.asyncio
async def test_sync_refreshes_when_harness_version_changes(tmp_path: Path) -> None:
    agent = FakeHarnessAgent(
        workspace_dir=tmp_path,
        virtual_mode=False,
        system_files_path=".octop",
    )

    await sync_builtin_tool_sources(agent.workspace)

    stamp = tmp_path / ".octop" / BUILTIN_TOOLS_ROOT / ".version"
    stamp.write_text("0.0.0+stale\n", encoding="utf-8")
    deployed = tmp_path / ".octop" / BUILTIN_TOOLS_ROOT / "browser_use.py"
    deployed.write_text("# stale copy\n", encoding="utf-8")

    refreshed = await sync_builtin_tool_sources(agent.workspace)

    assert "browser_use.py" in [Path(p).name for p in refreshed]
    assert "browser_use" in deployed.read_text(encoding="utf-8")
