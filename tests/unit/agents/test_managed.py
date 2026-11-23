"""Managed agent kind and filesystem pin."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from octop.infra.agents.managed import (
    apply_managed_backend,
    link_managed_skill_packages,
    managed_default_workspace,
    managed_project_root,
    managed_skill_dir,
    managed_subagent_dir,
    managed_template_payload,
    preserve_managed_config,
    require_managed_fields,
)
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.errors import OctopError


def test_repo_stores_managed_kind(tmp_path: Path) -> None:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    repo = AgentRepo(pool)
    repo.create(agent_id="m1", user_id=None, name="coder", kind="managed")
    row = repo.get("m1")
    assert row is not None
    assert row.kind == "managed"


def test_preserve_keeps_runner_and_filesystem_root() -> None:
    config = {
        "backend": {"type": "docker"},
        "workspace_dir": "/work",
        "conversation_mode": "plan",
    }
    preserve_managed_config(config, {"managed_runner": "opencode"})
    assert config["backend"] == {
        "type": "filesystem",
        "root_dir": "/",
        "virtual_mode": True,
    }
    assert config["managed_runner"] == "opencode"
    assert "conversation_mode" not in config
    assert config["memory"]["memory_enabled"] is False
    assert config["memory"]["memory_capture_enabled"] is False
    assert config["memory"]["memory_recall_inject_enabled"] is False


def test_preserve_keeps_yolo_when_the_patch_omits_it() -> None:
    config: dict[str, Any] = {"workspace_dir": "/work"}
    preserve_managed_config(
        config,
        {"managed_runner": "opencode", "managed_permission_mode": "yolo"},
    )
    assert config["managed_permission_mode"] == "yolo"


def test_preserve_drops_a_session_mode_the_runner_does_not_offer() -> None:
    foreign = {"managed_runner": "cursor_cli", "managed_session_mode": "bypassPermissions"}
    preserve_managed_config(foreign, {})
    assert "managed_session_mode" not in foreign

    cleared = {"managed_runner": "codebuddy", "managed_session_mode": ""}
    preserve_managed_config(cleared, {"managed_session_mode": "plan"})
    assert "managed_session_mode" not in cleared

    kept = {"managed_runner": "opencode", "managed_session_mode": "plan"}
    preserve_managed_config(kept, {})
    assert kept["managed_session_mode"] == "plan"

    restored: dict[str, Any] = {"managed_runner": "codebuddy"}
    preserve_managed_config(restored, {"managed_session_mode": "plan"})
    assert restored["managed_session_mode"] == "plan"


def test_preserve_keeps_an_enabled_memory_setting() -> None:
    config = {"memory": {"memory_enabled": True, "memory_capture_enabled": True}}
    preserve_managed_config(config, {"managed_runner": "opencode"})
    assert config["memory"]["memory_enabled"] is True
    assert config["memory"]["memory_capture_enabled"] is True
    assert config["memory"]["memory_recall_inject_enabled"] is False

    later: dict[str, Any] = {"workspace_dir": "/work"}
    preserve_managed_config(
        later,
        {"managed_runner": "opencode", "memory": {"memory_enabled": True}},
    )
    assert later["memory"]["memory_enabled"] is True


def test_managed_template_is_programming_seed() -> None:
    payload = managed_template_payload()
    prompts = payload["quick_prompts"]
    assert len(prompts) == 6
    files = {item["name"]: item["content"] for item in payload["files"]}
    assert "代码" in files["AGENTS.md"]
    assert Path(payload["home"]) == Path.home()
    assert managed_default_workspace("abc") == str(Path.home() / "abc")


def test_runner_project_dirs() -> None:
    assert managed_project_root("codebuddy") == ".codebuddy"
    assert managed_skill_dir("codebuddy") == ".codebuddy/skills"
    assert managed_subagent_dir("codebuddy") == ".codebuddy/agents"
    assert managed_project_root("unknown") == ".octop"
    assert managed_skill_dir("claude_code") == ".claude/skills"


def test_require_managed_fields() -> None:
    config: dict[str, Any] = {}
    apply_managed_backend(config)
    try:
        require_managed_fields(config)
    except OctopError as exc:
        assert exc.status == 400
    else:
        raise AssertionError("expected missing runner to fail")


def test_link_managed_skill_packages_tracks_owned_links(tmp_path: Path) -> None:
    if os.name != "posix":
        pytest.skip("skill package links use symlinks")

    package = tmp_path / "pkg"
    skill = package / "review"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("name: review\n", encoding="utf-8")
    (package / "notes.txt").write_text("skip", encoding="utf-8")
    workspace = tmp_path / "ws"
    link_managed_skill_packages(workspace, "codebuddy", [package])
    link = workspace / ".codebuddy" / "skills" / "review"
    assert link.is_symlink()
    assert link.resolve() == skill.resolve()

    local = workspace / ".codebuddy" / "skills" / "local"
    local.mkdir()
    (local / "SKILL.md").write_text("keep", encoding="utf-8")
    link_managed_skill_packages(workspace, "codebuddy", [])
    assert not link.exists()
    assert (local / "SKILL.md").read_text(encoding="utf-8") == "keep"


def test_link_managed_skill_packages_follows_the_runner(tmp_path: Path) -> None:
    if os.name != "posix":
        pytest.skip("skill package links use symlinks")

    package = tmp_path / "pkg"
    skill = package / "review"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("name: review\n", encoding="utf-8")
    other = tmp_path / "other" / "review"
    other.mkdir(parents=True)
    (other / "SKILL.md").write_text("second\n", encoding="utf-8")
    workspace = tmp_path / "ws"
    link_managed_skill_packages(workspace, "codebuddy", [package])
    skipped = link_managed_skill_packages(workspace, "claude_code", [package, other.parent])
    assert skipped == ["review"]
    assert not (workspace / ".codebuddy" / "skills" / "review").exists()
    kept = workspace / ".claude" / "skills" / "review"
    assert kept.is_symlink()
    assert kept.resolve() == skill.resolve()
