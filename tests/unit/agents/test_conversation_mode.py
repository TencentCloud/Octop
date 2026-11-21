"""Ask / Plan / Craft helpers."""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

import pytest

from octop.infra.agents.conversation_mode import (
    HOST_READ_TOOLS,
    execute_user_message,
    is_allowed_plan_path,
    is_plan_execute_utterance,
    plan_relpath_from_artifact,
    resolve_conversation_mode,
    stamp_conversation_mode,
    workspace_plan_path,
)


def test_resolve_explicit_wins() -> None:
    assert resolve_conversation_mode(explicit="ask", thread_mode="plan") == "ask"
    assert resolve_conversation_mode(explicit="nope", thread_mode="plan") == "craft"


def test_resolve_sticky_when_explicit_absent() -> None:
    assert resolve_conversation_mode(thread_mode="plan") == "plan"
    assert resolve_conversation_mode() == "craft"


def test_plan_relpath_from_artifact() -> None:
    assert (
        plan_relpath_from_artifact("plans/add-ask-plan-modes.md") == "plans/add-ask-plan-modes.md"
    )
    assert plan_relpath_from_artifact("/workspace/plans/foo.md") == "plans/foo.md"
    assert plan_relpath_from_artifact("SOUL.md") == ""
    assert plan_relpath_from_artifact("plans/中文.md") == ""


def test_is_allowed_plan_path_accepts_workspace_prefix() -> None:
    assert is_allowed_plan_path("plans/foo.md")
    assert is_allowed_plan_path("/plans/foo.md")
    assert is_allowed_plan_path("/data/.octop/agents/ABC/plans/foo.md")
    assert not is_allowed_plan_path("SOUL.md")
    assert not is_allowed_plan_path("docs/foo.md")


def test_harness_allowlist_accepts_workspace_plan_after_octop_patch() -> None:
    from octop_harness.middleware.conversation_mode import (
        is_allowed_plan_path as harness_ok,
    )

    assert harness_ok("/data/.octop/agents/ABC/plans/foo.md")
    assert harness_ok("plans/foo.md")
    assert not harness_ok("SOUL.md")


def test_workspace_plan_path_rewrites_container_root() -> None:
    # POSIX-style so the container-root rewrite branch is exercised on Windows too;
    # drive-path workspaces are intentionally passed through below.
    ws = PurePosixPath("/data/.octop/agents/ABC123")
    expected = f"{ws.as_posix()}/plans/foo.md"
    assert workspace_plan_path("plans/foo.md", ws) == expected
    assert workspace_plan_path("/plans/foo.md", ws) == expected
    assert workspace_plan_path(expected, ws) == expected
    assert workspace_plan_path("SOUL.md", ws) == "SOUL.md"
    assert workspace_plan_path("plans/foo.md", "D:/octop/agents/ABC") == "plans/foo.md"


posix_only = pytest.mark.skipif(
    os.name != "posix", reason="host-root /plans is a POSIX container bug"
)


@posix_only
def test_rewritten_plan_write_lands_in_workspace_not_container_root(tmp_path: Path) -> None:
    from deepagents.backends.filesystem import FilesystemBackend
    from deepagents.backends.utils import validate_path

    ws = tmp_path / "agents" / "ABC123"
    ws.mkdir(parents=True)
    backend = FilesystemBackend(root_dir="/", virtual_mode=True)
    remapped = workspace_plan_path(validate_path("plans/foo.md"), ws)
    result = backend.write(remapped, "# plan\n")
    assert result.error is None
    assert (ws / "plans" / "foo.md").read_text(encoding="utf-8") == "# plan\n"
    assert not Path("/plans/foo.md").exists()


def test_execute_user_message() -> None:
    assert execute_user_message("plans/foo.md", "zh") == "请按 plans/foo.md 执行"
    assert execute_user_message("plans/foo.md", "en") == "Execute plans/foo.md"


def test_is_plan_execute_utterance() -> None:
    assert is_plan_execute_utterance("按计划执行")
    assert is_plan_execute_utterance("执行计划")
    assert is_plan_execute_utterance("execute the plan")
    assert is_plan_execute_utterance("start executing")
    assert is_plan_execute_utterance("请按 plans/foo.md 执行")
    assert is_plan_execute_utterance("Execute plans/foo.md")
    assert not is_plan_execute_utterance("执行")
    assert not is_plan_execute_utterance("execute")
    assert not is_plan_execute_utterance("帮我看看这个计划写得对不对")
    assert not is_plan_execute_utterance("go")
    assert not is_plan_execute_utterance("start")
    assert not is_plan_execute_utterance("go on")


def test_stamp_ask_clears_skills_and_mcp() -> None:
    request: dict[str, object] = {
        "skills": ["docker"],
        "mcp_servers": ["github"],
        "configurable": {"skills": ["docker"]},
    }
    stamp_conversation_mode(request, "ask")
    assert request["skills"] == []
    assert request["mcp_servers"] == []
    cfg = request["configurable"]
    assert isinstance(cfg, dict)
    assert cfg["conversation_mode"] == "ask"
    assert cfg["conversation_mode_extra_read_tools"] == list(HOST_READ_TOOLS)
    assert cfg["skills"] == []
