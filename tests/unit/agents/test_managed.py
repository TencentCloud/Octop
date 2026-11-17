"""Managed agent kind and filesystem pin."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from octop.infra.agents.managed import (
    apply_managed_backend,
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
