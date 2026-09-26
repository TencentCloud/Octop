"""Thread workspace artifact extraction and middleware persistence."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from langchain_core.messages import ToolMessage
from langgraph.types import Command

from octop.infra.agents.middleware.thread_artifacts import (
    ThreadArtifactsMiddleware,
    peer_room_thread_id,
)
from octop.infra.agents.threads.artifact import (
    artifact_path_allowed,
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
from octop.infra.utils.thread_artifact import ThreadArtifact


def _ws(tmp_path: Path) -> Path:
    return tmp_path / ".octop" / "agents" / "ABC123"


class _FakeThreads:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str], str]] = []

    def append_artifacts(
        self,
        thread_id: str,
        paths: list[str] | tuple[str, ...],
        *,
        agent_id: str = "",
    ) -> None:
        self.calls.append((thread_id, list(paths), agent_id))


def _request(name: str, args: dict[str, Any] | None = None) -> MagicMock:
    req = MagicMock()
    req.tool_call = {"name": name, "args": args or {}, "id": "tc1"}
    return req


def test_is_artifact_tool_name() -> None:
    assert is_artifact_tool_name("write_file")
    assert is_artifact_tool_name("ns/edit_file")
    assert is_artifact_tool_name("desktop_screenshot")
    assert is_artifact_tool_name("mobile_screenshot")
    assert is_artifact_tool_name("send_file_to_user")
    assert not is_artifact_tool_name("browser_screenshot")
    assert not is_artifact_tool_name("read_file")
    assert not is_artifact_tool_name("ls")


def test_peer_room_thread_id() -> None:
    assert peer_room_thread_id("room~member") == "room"
    assert peer_room_thread_id("room") == ""
    assert peer_room_thread_id("") == ""


def test_normalize_artifact_path_absolute_passthrough_relative_joins_workspace(
    tmp_path: Path,
) -> None:
    ws = _ws(tmp_path)
    abs_path = str((ws / "docs" / "note.md").as_posix())
    assert normalize_artifact_path(abs_path, ws) == abs_path
    # Absolute-looking paths are stored as-is (no rewrite).
    assert (
        normalize_artifact_path("/.octop/agents/main/skills/env-reader/SKILL.md", ws)
        == "/.octop/agents/main/skills/env-reader/SKILL.md"
    )
    assert normalize_artifact_path("outbound/screenshots/harness.png", ws) == str(
        (ws / "outbound/screenshots/harness.png").as_posix()
    )
    assert normalize_artifact_path("_builtin_skills/foo/SKILL.md", ws) == ""


def test_artifact_path_allowed_rejects_builtin_and_extensionless() -> None:
    assert artifact_path_allowed("docs/note.md")
    assert artifact_path_allowed("outbound/screenshots/a.png")
    assert not artifact_path_allowed("_builtin_skills/foo/SKILL.md")
    assert not artifact_path_allowed("notes")
    assert not artifact_path_allowed("")


def test_artifacts_for_response_upgrades_legacy_relative_paths(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    abs_path = str((ws / "docs" / "a.md").as_posix())
    out = artifacts_for_response(
        ["docs/a.md", abs_path, "/.octop/agents/main/skills/x.md"],
        ws,
        default_agent_id="host",
    )
    # Relative upgrades to workspace abs; identical abs dedupes; other abs kept.
    assert out == [
        ThreadArtifact(path=str((ws / "docs/a.md").as_posix()), agent_id="host"),
        ThreadArtifact(path="/.octop/agents/main/skills/x.md", agent_id="host"),
    ]


def test_artifacts_for_response_keeps_producer_path_without_host_join(
    tmp_path: Path,
) -> None:
    ws = _ws(tmp_path)
    out = artifacts_for_response(
        [ThreadArtifact(path="outbound/a.md", agent_id="member-a")],
        ws,
        default_agent_id="host",
    )
    assert out == [ThreadArtifact(path="outbound/a.md", agent_id="member-a")]


def test_thread_artifacts_payload_has_legacy_and_refs(tmp_path: Path) -> None:
    from octop.infra.agents.threads.artifact import thread_artifacts_payload

    ws = _ws(tmp_path)
    payload = thread_artifacts_payload(
        [
            ThreadArtifact(path="outbound/a.md", agent_id="member-a"),
            "docs/b.md",
        ],
        ws,
        default_agent_id="host",
    )
    assert payload["artifacts"] == [
        "outbound/a.md",
        str((ws / "docs/b.md").as_posix()),
    ]
    assert payload["artifact_refs"] == [
        {"path": "outbound/a.md", "agent_id": "member-a"},
        {"path": str((ws / "docs/b.md").as_posix()), "agent_id": "host"},
    ]


def test_extract_from_write_file_args(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    paths = extract_artifact_paths(
        tool_name="write_file",
        args={"path": "generated/report.pptx"},
        workspace_dir=ws,
    )
    assert paths == [str((ws / "generated/report.pptx").as_posix())]
    assert extract_artifact_paths(tool_name="read_file", args={"path": "a.md"}) == []


def test_extract_prefers_args_over_result_text(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    paths = extract_artifact_paths(
        tool_name="write_file",
        args={"path": "generated/report.pptx"},
        result="Also mentioned outbound/screenshots/harness.png in the log",
        workspace_dir=ws,
    )
    assert paths == [str((ws / "generated/report.pptx").as_posix())]


def test_extract_screenshot_from_tool_result_text(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    abs_path = "/Users/me/.octop/agents/A1/outbound/screenshots/harness.png"
    paths = extract_artifact_paths(
        tool_name="desktop_screenshot",
        args={},
        result=f"Screenshot saved to {abs_path}",
        workspace_dir=ws,
    )
    assert paths == [abs_path]


def test_middleware_records_successful_write(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    store = _FakeThreads()
    mw = ThreadArtifactsMiddleware(thread_repo=store, workspace_dir=ws, agent_id="member-a")
    request = _request("write_file", {"path": "docs/note.md"})
    result = ToolMessage(content="ok", tool_call_id="tc1")
    with patch(
        "octop.infra.agents.middleware.thread_artifacts.current_thread_id",
        return_value="thr_1",
    ):
        out = mw.wrap_tool_call(request, lambda _req: result)
    assert out is result
    assert store.calls == [
        ("thr_1", [str((ws / "docs/note.md").as_posix())], "member-a"),
    ]


def test_middleware_mirrors_peer_artifacts_to_room(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    store = _FakeThreads()
    mw = ThreadArtifactsMiddleware(thread_repo=store, workspace_dir=ws, agent_id="member-a")
    request = _request("write_file", {"path": "docs/note.md"})
    with patch(
        "octop.infra.agents.middleware.thread_artifacts.current_thread_id",
        return_value="room~member-a",
    ):
        mw.wrap_tool_call(
            request,
            lambda _req: ToolMessage(content="ok", tool_call_id="tc1"),
        )
    path = str((ws / "docs/note.md").as_posix())
    assert store.calls == [
        ("room~member-a", [path], "member-a"),
        ("room", [path], "member-a"),
    ]


def test_middleware_records_absolute_write_as_is(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    store = _FakeThreads()
    mw = ThreadArtifactsMiddleware(thread_repo=store, workspace_dir=ws)
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
    assert store.calls == [("thr_1", [abs_path], "")]


def test_middleware_skips_error_and_command(tmp_path: Path) -> None:
    store = _FakeThreads()
    mw = ThreadArtifactsMiddleware(thread_repo=store, workspace_dir=_ws(tmp_path))
    request = _request("write_file", {"path": "docs/note.md"})
    error = ToolMessage(content="fail", tool_call_id="tc1", status="error")
    with patch(
        "octop.infra.agents.middleware.thread_artifacts.current_thread_id",
        return_value="thr_1",
    ):
        mw.wrap_tool_call(request, lambda _req: error)
        mw.wrap_tool_call(request, lambda _req: Command())
    assert store.calls == []


def test_middleware_skips_without_thread_id(tmp_path: Path) -> None:
    store = _FakeThreads()
    mw = ThreadArtifactsMiddleware(thread_repo=store, workspace_dir=_ws(tmp_path))
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
    assert row.artifacts == (
        ThreadArtifact(path="docs/a.md"),
        ThreadArtifact(path="docs/b.md"),
    )


def test_append_artifacts_dedupes_by_agent_and_path(tmp_path: Path) -> None:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    UserRepo(db).create(username="u", password_hash="h", role="user")
    AgentRepo(db).create(agent_id="host", user_id=1, name="Host")
    repo = ThreadRepo(db)
    repo.insert(
        thread_id="room",
        agent_id="host",
        user_id=1,
        channel_type="dashboard",
        session_key="sk",
    )
    repo.append_artifacts("room", ["outbound/a.md"], agent_id="member-a")
    repo.append_artifacts("room", ["outbound/a.md"], agent_id="member-b")
    repo.append_artifacts("room", ["outbound/a.md"], agent_id="member-a")
    row = repo.get("room")
    assert row is not None
    assert row.artifacts == (
        ThreadArtifact(path="outbound/a.md", agent_id="member-a"),
        ThreadArtifact(path="outbound/a.md", agent_id="member-b"),
    )
