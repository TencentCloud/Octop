"""Team file tools read the member's real deepagents directories."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from deepagents.backends.filesystem import FilesystemBackend
from octop_harness.backends.workspace import BackendWorkspace

from octop.infra.agents.middleware.team_file_target import TeamFileTargetMiddleware
from octop.infra.agents.teams.file_target import (
    DIR_KEY,
    HOST_KEY,
    MOUNTS_KEY,
    deepagents_directories,
)


def _workspace(root: Path) -> BackendWorkspace:
    return BackendWorkspace(
        FilesystemBackend(root_dir=str(root), virtual_mode=True),
        root,
        system_files_path=".octop",
    )


def _request(name: str, args: dict[str, Any]) -> Any:
    from unittest.mock import MagicMock

    req = MagicMock()
    req.tool_call = {"name": name, "id": "tc", "args": args}
    req.override = lambda **kwargs: SimpleNamespace(
        tool=kwargs["tool"], tool_call=kwargs.get("tool_call", req.tool_call)
    )
    return req


@pytest.mark.asyncio
async def test_member_skill_file_is_read_through_the_mounted_directory(tmp_path: Path) -> None:
    member_dir = tmp_path / "member"
    host_dir = tmp_path / "host"
    skill = member_dir / ".octop" / "_builtin_skills" / "demo"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("name: demo-skill\nmarker-skill-9f3a\n", encoding="utf-8")
    agents = member_dir / ".octop" / "agents"
    agents.mkdir(parents=True)
    (agents / "helper.md").write_text("marker-agent-9f3a\n", encoding="utf-8")
    host_dir.mkdir()
    (host_dir / "notes.md").write_text("host-note\n", encoding="utf-8")

    member_ws = _workspace(member_dir)
    host_ws = _workspace(host_dir)
    agent = SimpleNamespace(
        workspace=member_ws,
        config=SimpleNamespace(skills_dir=None, subagents_path=None),
    )
    mounts = deepagents_directories(agent)
    builtin = next(path for path in mounts if path.rstrip("/").endswith("_builtin_skills"))
    subagents = next(path for path in mounts if path.rstrip("/").endswith("/agents"))
    skill_path = f"{builtin}/demo/SKILL.md"
    agent_path = f"{subagents}/helper.md"
    assert "marker-skill-9f3a" in (await member_ws.aread_text(skill_path) or "")
    assert "marker-agent-9f3a" in (await member_ws.aread_text(agent_path) or "")

    child = SimpleNamespace(backend=object(), workspace=member_ws)
    host = SimpleNamespace(backend=object(), workspace=host_ws)
    mw = TeamFileTargetMiddleware(
        agent_id="child",
        lookup=lambda agent_id: child if agent_id == "child" else host,
    )
    config = {
        "configurable": {
            HOST_KEY: "host",
            DIR_KEY: str(host_dir),
            MOUNTS_KEY: mounts,
        }
    }

    async def handler(request: Any) -> str:
        result = await request.tool.ainvoke(request.tool_call)
        return str(getattr(result, "content", result))

    with patch(
        "octop.infra.agents.middleware.team_file_target.get_config",
        return_value=config,
    ):
        skill_text = await mw.awrap_tool_call(
            _request("read_file", {"file_path": skill_path}), handler
        )
        agent_text = await mw.awrap_tool_call(
            _request("read_file", {"file_path": agent_path}), handler
        )
        host_text = await mw.awrap_tool_call(
            _request("read_file", {"file_path": "notes.md"}), handler
        )
        blocked = await mw.awrap_tool_call(
            _request("write_file", {"file_path": skill_path, "content": "nope"}),
            handler,
        )
    assert "marker-skill-9f3a" in skill_text
    assert "marker-agent-9f3a" in agent_text
    assert "host-note" in host_text
    assert getattr(blocked, "status", None) == "error"
    assert (skill / "SKILL.md").read_text(encoding="utf-8").startswith("name: demo-skill")
    assert not (host_dir / ".octop" / "_builtin_skills").exists()
