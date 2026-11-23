"""ACP file edits become write_file / edit_file calls the chat card already understands."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from octop_harness.acp.client import ACPHostedClient
from octop_harness.acp.models import ACPRunnerConfig

from octop.infra.agents.acp.file_edits import (
    file_edits_from_update,
    install_acp_file_edits,
)
from octop.infra.agents.acp.tool_names import install_acp_tool_titles


def _install() -> None:
    install_acp_tool_titles()
    install_acp_file_edits()


def _client() -> ACPHostedClient:
    _install()
    client = ACPHostedClient(
        runner_name="opencode",
        runner_config=ACPRunnerConfig(command="opencode", args=["acp"]),
        cwd=".",
    )
    client.start_prompt(lambda _payload, _is_last: None)
    return client


def _chunk_calls(chunk: Any) -> list[dict[str, Any]]:
    message = chunk.message
    calls = getattr(message, "tool_call_chunks", None) or []
    out: list[dict[str, Any]] = []
    for call in calls:
        if isinstance(call, dict):
            out.append(call)
            continue
        out.append(
            {
                "name": getattr(call, "name", ""),
                "args": getattr(call, "args", ""),
                "id": getattr(call, "id", ""),
                "index": getattr(call, "index", 0),
            }
        )
    return out


def test_diff_update_keeps_path_and_body() -> None:
    update = SimpleNamespace(
        content=[
            {
                "type": "diff",
                "path": "src/app.py",
                "oldText": "a\n",
                "newText": "b\n",
            }
        ],
        locations=[{"path": "src/app.py"}],
        kind="edit",
        raw_input=None,
    )
    edits = file_edits_from_update(update)
    assert edits == [{"path": "src/app.py", "old": "a\n", "new": "b\n"}]


def test_read_without_diff_is_not_a_file_edit() -> None:
    update = SimpleNamespace(
        content=None,
        locations=[{"path": "README.md"}],
        kind="read",
        raw_input={"path": "README.md"},
    )
    assert file_edits_from_update(update) == []


def test_client_event_carries_files() -> None:
    client = _client()
    update = SimpleNamespace(
        tool_call_id="call-1",
        title="Edit app.py",
        kind="edit",
        status="in_progress",
        raw_input=None,
        raw_output=None,
        content=[{"type": "diff", "path": "app.py", "oldText": None, "newText": "print(1)\n"}],
        locations=None,
    )
    event = client._tool_event_from_state(update)
    assert event is not None
    assert event["files"] == [{"path": "app.py", "old": None, "new": "print(1)\n"}]


def test_completed_diff_streams_as_edit_file() -> None:
    _install()
    from octop_harness.acp.managed import _tool_chunks

    opened: dict[str, int] = {}
    chunks, _index = _tool_chunks(
        {
            "call_id": "call-edit",
            "name": "Edit app.py",
            "status": "completed",
            "output": "done",
            "files": [{"path": "app.py", "old": "a\n", "new": "b\n"}],
        },
        opened,
        0,
    )
    calls = [call for chunk in chunks for call in _chunk_calls(chunk)]
    assert len(calls) == 1
    assert calls[0]["name"] == "edit_file"
    assert json.loads(calls[0]["args"]) == {
        "file_path": "app.py",
        "old_string": "a\n",
        "new_string": "b\n",
    }
    assert opened == {}


def test_new_file_streams_as_write_file() -> None:
    _install()
    from octop_harness.acp.managed import _tool_chunks

    chunks, _index = _tool_chunks(
        {
            "call_id": "call-write",
            "name": "Write notes.md",
            "status": "completed",
            "files": [{"path": "notes.md", "old": None, "new": "hello\n"}],
        },
        {},
        0,
    )
    calls = [call for chunk in chunks for call in _chunk_calls(chunk)]
    assert calls[0]["name"] == "write_file"
    assert json.loads(calls[0]["args"]) == {"file_path": "notes.md", "content": "hello\n"}


def test_path_only_waits_until_the_call_finishes() -> None:
    _install()
    from octop_harness.acp.managed import _tool_chunks

    opened: dict[str, int] = {}
    started, index = _tool_chunks(
        {
            "call_id": "call-path",
            "name": "Edit README.md",
            "status": "in_progress",
            "files": [{"path": "README.md", "old": None, "new": None}],
        },
        opened,
        0,
    )
    started_calls = [call for chunk in started for call in _chunk_calls(chunk)]
    assert started_calls[0]["name"] == "Edit README.md"
    assert started_calls[0]["args"] == ""

    finished, _index = _tool_chunks(
        {"call_id": "call-path", "name": "Edit README.md", "status": "completed", "files": []},
        opened,
        index,
    )
    names = [call["name"] for chunk in finished for call in _chunk_calls(chunk)]
    args = [call["args"] for chunk in finished for call in _chunk_calls(chunk)]
    assert "edit_file" in names
    assert json.loads(next(item for item in args if item)) == {"file_path": "README.md"}


def test_two_diffs_open_two_file_tools() -> None:
    _install()
    from octop_harness.acp.managed import _tool_chunks

    chunks, _index = _tool_chunks(
        {
            "call_id": "call-two",
            "name": "Edit",
            "status": "completed",
            "files": [
                {"path": "a.py", "old": "a", "new": "b"},
                {"path": "b.py", "old": None, "new": "c"},
            ],
        },
        {},
        0,
    )
    calls = [call for chunk in chunks for call in _chunk_calls(chunk)]
    assert [call["name"] for call in calls] == ["edit_file", "write_file"]
    assert [call["id"] for call in calls] == ["call-two", "call-two:1"]


def test_history_keeps_the_edit_arguments() -> None:
    _install()
    from octop_harness.acp.managed import (
        _collect_managed_chunk,
        _managed_history_messages,
        _tool_chunks,
    )

    chunks, _index = _tool_chunks(
        {
            "call_id": "call-hist",
            "name": "Edit a.py",
            "status": "completed",
            "output": "ok",
            "files": [{"path": "a.py", "old": "a\n", "new": "b\n"}],
        },
        {},
        0,
    )
    text: list[str] = []
    reasoning: list[str] = []
    tools: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for chunk in chunks:
        _collect_managed_chunk(chunk, text, reasoning, tools, by_id)
    messages = _managed_history_messages(text, reasoning, tools)
    ai = next(message for message in messages if getattr(message, "tool_calls", None))
    call = ai.tool_calls[0]
    assert call["name"] == "edit_file"
    assert call["args"]["file_path"] == "a.py"
    assert call["args"]["old_string"] == "a\n"
    assert call["args"]["new_string"] == "b\n"
