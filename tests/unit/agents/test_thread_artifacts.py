"""Thread workspace artifact extraction and middleware persistence."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from langchain_core.messages import ToolMessage
from langgraph.types import Command

from octop.infra.agents.middleware.thread_artifacts import (
    ThreadArtifactsMiddleware,
    extract_artifact_paths,
    is_artifact_tool_name,
    normalize_artifact_path,
)
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo


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


def test_normalize_artifact_path_strips_agent_prefix() -> None:
    path = "/home/wally/.octop/agents/ABC123/docs/note.md"
    assert normalize_artifact_path(path) == "docs/note.md"
    assert (
        normalize_artifact_path("outbound/screenshots/harness.png")
        == "outbound/screenshots/harness.png"
    )
    assert normalize_artifact_path("_builtin_skills/foo/SKILL.md") == ""


def test_extract_from_write_file_args() -> None:
    paths = extract_artifact_paths(
        tool_name="write_file",
        args={"path": "generated/report.pptx"},
    )
    assert paths == ["generated/report.pptx"]
    assert extract_artifact_paths(tool_name="read_file", args={"path": "a.md"}) == []


def test_extract_prefers_args_over_result_text() -> None:
    paths = extract_artifact_paths(
        tool_name="write_file",
        args={"path": "generated/report.pptx"},
        result="Also mentioned outbound/screenshots/harness.png in the log",
    )
    assert paths == ["generated/report.pptx"]


def test_extract_screenshot_from_tool_result_text() -> None:
    paths = extract_artifact_paths(
        tool_name="desktop_screenshot",
        args={},
        result=("Screenshot saved to /Users/me/.octop/agents/A1/outbound/screenshots/harness.png"),
    )
    assert paths == ["outbound/screenshots/harness.png"]


def test_middleware_records_successful_write() -> None:
    store = _FakeThreads()
    mw = ThreadArtifactsMiddleware(thread_repo=store)
    request = _request("write_file", {"path": "docs/note.md"})
    result = ToolMessage(content="ok", tool_call_id="tc1")
    with patch(
        "octop.infra.agents.middleware.thread_artifacts.current_thread_id",
        return_value="thr_1",
    ):
        out = mw.wrap_tool_call(request, lambda _req: result)
    assert out is result
    assert store.calls == [("thr_1", ["docs/note.md"])]


def test_middleware_skips_error_and_command() -> None:
    store = _FakeThreads()
    mw = ThreadArtifactsMiddleware(thread_repo=store)
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
    mw = ThreadArtifactsMiddleware(thread_repo=store)
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
