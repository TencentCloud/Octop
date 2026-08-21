"""Thread workspace artifact extraction and middleware persistence."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from langchain_core.messages import ToolMessage
from langgraph.types import Command

from octop.infra.agents.middleware.thread_artifacts import (
    ThreadArtifactsMiddleware,
    artifacts_for_response,
    extract_artifact_paths,
    is_artifact_tool_name,
    normalize_artifact_path,
)
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo

_WS = Path("/home/wally/.octop/agents/ABC123")


class _FakeThreads:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []

    def append_artifacts(self, thread_id: str, paths: list[str] | tuple[str, ...]) -> None:
        self.calls.append((thread_id, list(paths)))


def _request(name: str, args: dict[str, Any] | None = None) -> MagicMock:
    req = MagicMock()
    req.tool_call = {"name": name, "args": args or {}, "id": "tc1"}
    return req


def test_is_artifact_tool_name() -> None:
    assert is_artifact_tool_name("write_file")
    assert is_artifact_tool_name("ns/edit_file")
    assert is_artifact_tool_name("desktop_screenshot")
    assert is_artifact_tool_name("send_file_to_user")
    assert not is_artifact_tool_name("browser_screenshot")
    assert not is_artifact_tool_name("read_file")
    assert not is_artifact_tool_name("ls")


def test_normalize_artifact_path_absolute_passthrough_relative_joins_workspace() -> None:
    abs_path = "/home/wally/.octop/agents/ABC123/docs/note.md"
    assert normalize_artifact_path(abs_path, _WS) == abs_path
    # Absolute-looking paths are stored as-is (no rewrite).
    assert (
        normalize_artifact_path("/.octop/agents/main/skills/env-reader/SKILL.md", _WS)
        == "/.octop/agents/main/skills/env-reader/SKILL.md"
    )
    assert normalize_artifact_path("outbound/screenshots/harness.png", _WS) == str(
        (_WS / "outbound/screenshots/harness.png").as_posix()
    )
    assert normalize_artifact_path("_builtin_skills/foo/SKILL.md", _WS) == ""


def test_artifacts_for_response_upgrades_legacy_relative_paths() -> None:
    abs_path = "/home/wally/.octop/agents/ABC123/docs/a.md"
    out = artifacts_for_response(
        ["docs/a.md", abs_path, "/.octop/agents/main/skills/x.md"],
        _WS,
    )
    # Relative upgrades to workspace abs; identical abs dedupes; other abs kept.
    assert out == [
        str((_WS / "docs/a.md").as_posix()),
        "/.octop/agents/main/skills/x.md",
    ]


def test_extract_from_write_file_args() -> None:
    paths = extract_artifact_paths(
        tool_name="write_file",
        args={"path": "generated/report.pptx"},
        workspace_dir=_WS,
    )
    assert paths == [str((_WS / "generated/report.pptx").as_posix())]
    assert extract_artifact_paths(tool_name="read_file", args={"path": "a.md"}) == []


def test_extract_prefers_args_over_result_text() -> None:
    paths = extract_artifact_paths(
        tool_name="write_file",
        args={"path": "generated/report.pptx"},
        result="Also mentioned outbound/screenshots/harness.png in the log",
        workspace_dir=_WS,
    )
    assert paths == [str((_WS / "generated/report.pptx").as_posix())]


def test_extract_screenshot_from_tool_result_text() -> None:
    abs_path = "/Users/me/.octop/agents/A1/outbound/screenshots/harness.png"
    paths = extract_artifact_paths(
        tool_name="desktop_screenshot",
        args={},
        result=f"Screenshot saved to {abs_path}",
        workspace_dir=_WS,
    )
    assert paths == [abs_path]


def test_middleware_records_successful_write() -> None:
    store = _FakeThreads()
    mw = ThreadArtifactsMiddleware(thread_repo=store, workspace_dir=_WS)
    request = _request("write_file", {"path": "docs/note.md"})
    result = ToolMessage(content="ok", tool_call_id="tc1")
    with patch(
        "octop.infra.agents.middleware.thread_artifacts.current_thread_id",
        return_value="thr_1",
    ):
        out = mw.wrap_tool_call(request, lambda _req: result)
    assert out is result
    assert store.calls == [("thr_1", [str((_WS / "docs/note.md").as_posix())])]


def test_middleware_records_absolute_write_as_is() -> None:
    store = _FakeThreads()
    mw = ThreadArtifactsMiddleware(thread_repo=store, workspace_dir=_WS)
    abs_path = "/.octop/agents/main/skills/env-reader/SKILL.md"
    request = _request("write_file", {"path": abs_path})
    with patch(
        "octop.infra.agents.middleware.thread_artifacts.current_thread_id",
        return_value="thr_1",
    ):
        mw.wrap_tool_call(
            request,
            lambda _req: ToolMessage(content="ok", tool_call_id="tc1"),
        )
    assert store.calls == [("thr_1", [abs_path])]


def test_middleware_skips_error_and_command() -> None:
    store = _FakeThreads()
    mw = ThreadArtifactsMiddleware(thread_repo=store, workspace_dir=_WS)
    request = _request("write_file", {"path": "docs/note.md"})
    error = ToolMessage(content="fail", tool_call_id="tc1", status="error")
    with patch(
        "octop.infra.agents.middleware.thread_artifacts.current_thread_id",
        return_value="thr_1",
    ):
        mw.wrap_tool_call(request, lambda _req: error)
        mw.wrap_tool_call(request, lambda _req: Command())
    assert store.calls == []


def test_middleware_skips_without_thread_id() -> None:
    store = _FakeThreads()
    mw = ThreadArtifactsMiddleware(thread_repo=store, workspace_dir=_WS)
    request = _request("write_file", {"path": "docs/note.md"})
    with patch(
        "octop.infra.agents.middleware.thread_artifacts.current_thread_id",
        return_value="",
    ):
        mw.wrap_tool_call(
            request,
            lambda _req: ToolMessage(content="ok", tool_call_id="tc1"),
        )
    assert store.calls == []


def test_append_artifacts_merges_unique(tmp_path: Path) -> None:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    UserRepo(db).create(username="u", password_hash="h", role="user")
    AgentRepo(db).create(agent_id="a1", user_id=1, name="Agent 1")
    repo = ThreadRepo(db)
    repo.insert(
        thread_id="thr_1",
        agent_id="a1",
        user_id=1,
        channel_type="dashboard",
        session_key="sk",
    )
    repo.append_artifacts("thr_1", ["docs/a.md", "docs/a.md"])
    repo.append_artifacts("thr_1", ["docs/b.md"])
    row = repo.get("thr_1")
    assert row is not None
    assert row.artifacts == ("docs/a.md", "docs/b.md")
