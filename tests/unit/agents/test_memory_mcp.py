"""Unit tests for the expert memory MCP server (infra/agents/memory_mcp)."""

from __future__ import annotations

import base64
import gzip
import json
from datetime import UTC, datetime
from unittest import mock

import pytest

from octop.infra.agents import memory_mcp as mm

_TRANSCRIPT = (
    json.dumps(
        {
            "type": "user",
            "uuid": "u1",
            "sessionId": "s1",
            "timestamp": "2026-09-22T05:00:00Z",
            "message": {"role": "user", "content": "先看看 CLI 结构"},
        }
    )
    + "\n"
    + json.dumps(
        {
            "type": "assistant",
            "uuid": "a1",
            "sessionId": "s1",
            "timestamp": "2026-09-22T05:00:05Z",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "好的，先读文件"},
                    {
                        "type": "tool_use",
                        "id": "t1",
                        "name": "Read",
                        "input": {"file_path": "x.py"},
                    },
                ],
            },
        }
    )
)


@pytest.fixture
def fake_memory(monkeypatch):
    mem = mock.MagicMock()
    mem.recall.return_value = []
    node = mock.MagicMock()
    node.id = "node1"
    node.content = "remember X"
    mem.store.return_value = node

    def _add_raw(content, **_kwargs):
        raw = mock.MagicMock(id="evt1")
        raw.content = content
        return raw

    mem.add_raw.side_effect = _add_raw
    mem.deprecate_atom.return_value = True
    monkeypatch.setattr(mm, "_open_memory", lambda server, agent_id: mem)
    # Capture tests use a MagicMock server; do not let the real trigger schedule
    # a fire-and-forget extract task against that mock (unawaited coroutine noise).
    monkeypatch.setattr(mm, "_trigger_extract", lambda server, session_id: True)
    return mem


@pytest.fixture
def bind_agent():
    """Bind the request-scoped agent contextvar (main resolves the expert per request)."""
    token = mm._current_agent_id.set("A1")
    yield "A1"
    mm._current_agent_id.reset(token)


@pytest.fixture
def bind_user():
    """Bind the ``X-Octop-User-Id`` caller contextvar (sender attribution)."""
    token = mm._current_caller_user.set("alice")
    yield "alice"
    mm._current_caller_user.reset(token)


def _tools(mcp):
    return mcp._tool_manager._tools


def test_build_resolves_agent_per_request(monkeypatch):
    """Expert is bound per request (contextvar), not captured at build time."""
    captured = {}

    def fake_open(server, agent_id):
        captured["agent_id"] = agent_id
        mem = mock.MagicMock()
        mem.store.return_value = mock.MagicMock(id="n1", content="x")
        return mem

    monkeypatch.setattr(mm, "_open_memory", fake_open)
    mcp = mm.build_memory_mcp(mock.MagicMock())
    token = mm._current_agent_id.set("EXPERT42")
    try:
        _tools(mcp)["memory_save"].fn(content="x", source="s")
    finally:
        mm._current_agent_id.reset(token)
    assert captured["agent_id"] == "EXPERT42"


def test_build_registers_nine_tools(fake_memory):
    mcp = mm.build_memory_mcp(mock.MagicMock())
    assert set(_tools(mcp)) == {
        "memory_search",
        "memory_get",
        "memory_save",
        "memory_capture",
        "memory_raws",
        "memory_candidates",
        "memory_extract",
        "memory_promote",
        "memory_reject",
    }


def test_memory_save_goes_store(fake_memory, bind_agent):
    mcp = mm.build_memory_mcp(mock.MagicMock())
    result = _tools(mcp)["memory_save"].fn(content="remember X", source="coding-agent")
    kwargs = fake_memory.store.call_args.kwargs
    assert kwargs["topic"] is None
    assert kwargs["metadata"] == {"source": "coding-agent"}
    assert result["source"] == "coding-agent"


def test_memory_capture_goes_add_raw(fake_memory, bind_agent):
    mcp = mm.build_memory_mcp(mock.MagicMock())
    result = _tools(mcp)["memory_capture"].fn(
        content="raw conversation", source="review-bot", session_id="review-1"
    )
    kwargs = fake_memory.add_raw.call_args.kwargs
    assert kwargs["event_type"] == "user_message"
    assert kwargs["host"] == "mcp-external"
    assert kwargs["session_id"] == "review-1"
    assert kwargs["payload"] == {"source": "review-bot"}
    assert result["recorded"] is True
    assert "raw (L0)" in result["note"]


def test_memory_capture_is_idempotent(fake_memory, bind_agent):
    """Re-capturing the same session + content + role reuses the existing L0 event."""
    existing = mock.MagicMock(id="evt-existing")
    existing.content = "raw conversation"
    existing.event_type = "user_message"
    fake_memory.list_raw.return_value = [existing]

    mcp = mm.build_memory_mcp(mock.MagicMock())
    result = _tools(mcp)["memory_capture"].fn(
        content="raw conversation", source="review-bot", session_id="review-1"
    )

    fake_memory.add_raw.assert_not_called()
    assert result["event_id"] == "evt-existing"
    assert result["duplicate"] is True
    assert "idempotent capture" in result["note"]


def test_memory_capture_implies_role_from_field(fake_memory, bind_agent, bind_user):
    """content → user_message, assistant → assistant_message; no role parameter."""
    mcp = mm.build_memory_mcp(mock.MagicMock())
    result = _tools(mcp)["memory_capture"].fn(
        content="",
        assistant="助手结论：先不做 Replace",
        source="coding-agent",
        session_id="s1",
        thread_id="thr-1",
    )

    kwargs = fake_memory.add_raw.call_args.kwargs
    assert kwargs["event_type"] == "assistant_message"
    assert kwargs["thread_id"] == "thr-1"
    assert result["event_type"] == "assistant_message"
    assert result["thread_id"] == "thr-1"


def test_memory_capture_attributes_only_the_user_side(fake_memory, bind_agent, bind_user):
    """The assistant's own words must not be stamped as if the user had said them.

    The extractor prompt only sees event_id / event_type / content / timestamp /
    session_id, so a sender reaches the atom text only through the prefix — which is
    why the user side carries it while the assistant side (already marked by its
    ``event_type``) must not.
    """
    mcp = mm.build_memory_mcp(mock.MagicMock())

    _tools(mcp)["memory_capture"].fn(
        content="帮我改一下这个函数",
        assistant="改好了，先保留旧签名",
        source="dsh:cordis-memory",
    )

    stored = {c.kwargs["event_type"]: c.args[0] for c in fake_memory.add_raw.call_args_list}
    assert stored["user_message"] == "alice说：帮我改一下这个函数"
    assert stored["assistant_message"] == "改好了，先保留旧签名"


def test_memory_capture_writes_turn_in_one_call(fake_memory, bind_agent, bind_user):
    """content + assistant write both halves of a turn, like MemoryService.capture_turn."""
    mcp = mm.build_memory_mcp(mock.MagicMock())
    result = _tools(mcp)["memory_capture"].fn(
        content="接口先不要动",
        assistant="好的，先保留旧签名",
        source="coding-agent",
        session_id="s1",
        thread_id="thr-1",
    )

    assert [c.kwargs["event_type"] for c in fake_memory.add_raw.call_args_list] == [
        "user_message",
        "assistant_message",
    ]
    assert [e["event_type"] for e in result["events"]] == ["user_message", "assistant_message"]
    assert result["event_type"] == "user_message"


def test_memory_capture_drops_only_the_echoing_half(fake_memory, bind_agent, bind_user):
    mcp = mm.build_memory_mcp(mock.MagicMock())
    result = _tools(mcp)["memory_capture"].fn(
        content="接口先不要动",
        assistant="## Memory Recall\n- 旧记忆块",
        source="hook",
    )

    assert [c.kwargs["event_type"] for c in fake_memory.add_raw.call_args_list] == ["user_message"]
    assert [e["event_type"] for e in result["events"]] == ["user_message"]


def test_memory_capture_rejects_empty_turn(fake_memory, bind_agent):
    mcp = mm.build_memory_mcp(mock.MagicMock())
    with pytest.raises(ValueError, match="both empty"):
        _tools(mcp)["memory_capture"].fn(content="  ", source="review-bot")
    fake_memory.add_raw.assert_not_called()


def test_memory_capture_same_content_different_role_not_deduped(fake_memory, bind_agent):
    """Identical text in two roles is two distinct events, not a duplicate."""
    existing = mock.MagicMock(id="evt-existing")
    existing.content = "接口先不要动"
    existing.event_type = "assistant_message"
    fake_memory.list_raw.return_value = [existing]

    mcp = mm.build_memory_mcp(mock.MagicMock())
    result = _tools(mcp)["memory_capture"].fn(
        content="接口先不要动", source="review-bot", session_id="s1"
    )

    assert fake_memory.add_raw.called
    assert "duplicate" not in result


def test_memory_raws_queries_l0_with_query(fake_memory, bind_agent):
    class _Evt:
        id = "evt1"
        timestamp = __import__("datetime").datetime(2026, 8, 19)
        session_id = "review-1"
        user = "u1"
        event_type = "manual"
        payload = {"source": "review-bot"}
        content = "report panel banner hidden"

    fake_memory.search_raw.return_value = [_Evt()]
    mcp = mm.build_memory_mcp(mock.MagicMock())
    result = _tools(mcp)["memory_raws"].fn(query="report panel banner", limit=5)
    fake_memory.search_raw.assert_called_once_with("report panel banner", limit=5)
    assert result["count"] == 1
    assert result["events"][0]["event_id"] == "evt1"
    assert result["events"][0]["source"] == "review-bot"


def test_memory_capture_transcript_writes_l0(fake_memory, bind_agent, bind_user, monkeypatch):
    """A whole transcript uploads as L0 events carrying role + tool linkage."""
    monkeypatch.setattr(mm, "_trigger_extract", lambda server, session_id: True)
    mcp = mm.build_memory_mcp(mock.MagicMock())

    result = _tools(mcp)["memory_capture"].fn(
        content=_TRANSCRIPT, source="claude-code", session_id="cc:s1", tool_events="all"
    )

    assert result["session_id"] == "cc:s1"
    assert result["parsed"] == 3
    assert result["imported"] == 3
    assert result["events_by_type"] == {
        "user_message": 1,
        "assistant_message": 1,
        "tool_call": 1,
    }
    assert result["extract_scheduled"] is True

    raws = fake_memory.add_raw_batch.call_args.args[0]
    assert {raw.event_type for raw in raws} == {"user_message", "assistant_message", "tool_call"}
    assert all(raw.host == "claude-code" for raw in raws)
    assert all(raw.user == "alice" for raw in raws)
    assert all(raw.session_id == "cc:s1" for raw in raws)


def test_memory_capture_transcript_accepts_gzip_base64(fake_memory, bind_agent, monkeypatch):
    monkeypatch.setattr(mm, "_trigger_extract", lambda server, session_id: False)
    mcp = mm.build_memory_mcp(mock.MagicMock())
    blob = base64.b64encode(gzip.compress(_TRANSCRIPT.encode())).decode()

    result = _tools(mcp)["memory_capture"].fn(content=blob, source="claude-code", tool_events="all")

    assert result["imported"] == 3
    assert result["session_id"] == "cc:s1"


def test_memory_capture_transcript_dry_run_writes_nothing(fake_memory, bind_agent, monkeypatch):
    monkeypatch.setattr(mm, "_trigger_extract", lambda server, session_id: True)
    mcp = mm.build_memory_mcp(mock.MagicMock())

    result = _tools(mcp)["memory_capture"].fn(
        content=_TRANSCRIPT, source="claude-code", dry_run=True
    )

    assert result["parsed"] == 3
    assert result["imported"] == 0
    assert result["extract_scheduled"] is False
    fake_memory.add_raw_batch.assert_not_called()


def test_memory_capture_transcript_can_defer_extraction(fake_memory, bind_agent, monkeypatch):
    """Backfill lands L0 first; promotion happens later in a paced sweep."""
    scheduled: list[str] = []
    monkeypatch.setattr(
        mm, "_trigger_extract", lambda server, session_id: scheduled.append(session_id) or True
    )
    mcp = mm.build_memory_mcp(mock.MagicMock())

    result = _tools(mcp)["memory_capture"].fn(
        content=_TRANSCRIPT, source="claude-code", extract=False, tool_events="all"
    )

    assert result["imported"] == 3
    assert result["extract_scheduled"] is False
    assert scheduled == []
    assert "paced sweep" in result["note"]


def test_memory_capture_terminal_source_with_prose_records_a_turn(
    fake_memory, bind_agent, monkeypatch
):
    """A terminal name used with prose must keep working (pre-transcript callers).

    ``source`` used to be free-form, so a caller that passes a sentence with
    ``source="claude-code"`` would otherwise be parsed into zero events and dropped.
    """
    monkeypatch.setattr(mm, "_trigger_extract", lambda server, session_id: True)
    mcp = mm.build_memory_mcp(mock.MagicMock())

    result = _tools(mcp)["memory_capture"].fn(
        content="用户偏好：Windows 用 pwsh，不用 bash", source="claude-code"
    )

    assert result["recorded"] is True
    assert result["events"][0]["event_type"] == "user_message"
    assert "not a transcript" in result["note"]
    assert "parsed" not in result  # 走的是文本分支，不是 transcript 分支
    assert result["session_id"].startswith("ext:claude-code:")  # 一轮对话的派生 session
    fake_memory.add_raw.assert_called_once()


def test_memory_capture_transcript_drops_own_recall_results(fake_memory, bind_agent, monkeypatch):
    """The transcript path must not re-ingest results of our own memory read tools."""
    monkeypatch.setattr(mm, "_trigger_extract", lambda server, session_id: True)
    mcp = mm.build_memory_mcp(mock.MagicMock())
    records = [
        {
            "type": "user",
            "uuid": "u1",
            "sessionId": "s9",
            "timestamp": "2026-09-22T05:00:00Z",
            "message": {"role": "user", "content": "上周改了什么"},
        },
        {
            "type": "assistant",
            "uuid": "a1",
            "sessionId": "s9",
            "timestamp": "2026-09-22T05:00:01Z",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "t1",
                        "name": "mcp__octop-memory-local__memory_recall",
                        "input": {"query": "上周"},
                    }
                ],
            },
        },
        {
            "type": "user",
            "uuid": "u2",
            "sessionId": "s9",
            "timestamp": "2026-09-22T05:00:02Z",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "t1",
                        "content": "- [atom] (atom:high @ 2026-01-01) 旧记忆：部署在 8088",
                        "is_error": False,
                    }
                ],
            },
        },
    ]

    result = _tools(mcp)["memory_capture"].fn(
        content="\n".join(json.dumps(record, ensure_ascii=False) for record in records),
        source="claude-code",
        session_id="cc:s9",
        tool_events="all",
    )

    assert result["skipped_own_results"] == 1
    assert result["imported"] == 2
    assert "tool_result" not in result["events_by_type"]
    raws = fake_memory.add_raw_batch.call_args.args[0]
    assert all("旧记忆" not in raw.content for raw in raws)


def test_memory_capture_transcript_drops_marked_events(fake_memory, bind_agent, monkeypatch):
    """A recalled block (marker present) is dropped even if no tool produced it."""
    monkeypatch.setattr(mm, "_trigger_extract", lambda server, session_id: True)
    mcp = mm.build_memory_mcp(mock.MagicMock())
    records = [
        {
            "type": "user",
            "uuid": "u1",
            "sessionId": "s8",
            "timestamp": "2026-09-22T05:00:00Z",
            "message": {"role": "user", "content": "正常提问"},
        },
        {
            "type": "user",
            "uuid": "u2",
            "sessionId": "s8",
            "timestamp": "2026-09-22T05:00:01Z",
            "message": {"role": "user", "content": "## Memory Recall\n- [atom] 旧记忆块"},
        },
    ]

    result = _tools(mcp)["memory_capture"].fn(
        content="\n".join(json.dumps(record, ensure_ascii=False) for record in records),
        source="claude-code",
        session_id="cc:s8",
    )

    assert result["parsed"] == 2
    assert result["skipped_echo"] == 1
    assert result["imported"] == 1


_TOOL_TRANSCRIPT = "\n".join(
    json.dumps(record)
    for record in [
        {
            "type": "user",
            "uuid": "tu1",
            "sessionId": "s5",
            "timestamp": "2026-09-22T05:00:00Z",
            "message": {"role": "user", "content": "跑一下测试"},
        },
        {
            "type": "assistant",
            "uuid": "ta1",
            "sessionId": "s5",
            "timestamp": "2026-09-22T05:00:01Z",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "我跑一下"},
                    {
                        "type": "tool_use",
                        "id": "t1",
                        "name": "Bash",
                        "input": {"command": "pytest"},
                    },
                ],
            },
        },
        {
            "type": "user",
            "uuid": "tu2",
            "sessionId": "s5",
            "timestamp": "2026-09-22T05:00:02Z",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "t1",
                        "content": "3 passed",
                        "is_error": False,
                    }
                ],
            },
        },
    ]
)


@pytest.mark.parametrize(
    ("policy", "expected_by_type", "skipped_tools"),
    [
        (
            "all",
            {"user_message": 1, "assistant_message": 1, "tool_call": 1, "tool_result": 1},
            0,
        ),
        ("calls", {"user_message": 1, "assistant_message": 1, "tool_call": 1}, 1),
        ("none", {"user_message": 1, "assistant_message": 1}, 2),
    ],
)
def test_memory_capture_tool_events_policy(
    fake_memory, bind_agent, monkeypatch, policy, expected_by_type, skipped_tools
):
    """``tool_events`` 默认只落 user/assistant（上传始终整份），可显式放开到 calls / all。"""
    monkeypatch.setattr(mm, "_trigger_extract", lambda server, session_id: True)
    mcp = mm.build_memory_mcp(mock.MagicMock())

    result = _tools(mcp)["memory_capture"].fn(
        content=_TOOL_TRANSCRIPT, source="claude-code", session_id="cc:s5", tool_events=policy
    )

    assert result["by_type" if "by_type" in result else "events_by_type"] == expected_by_type
    assert result["skipped_tools"] == skipped_tools
    assert result["tool_events"] == policy
    assert result["imported"] == sum(expected_by_type.values())


def test_memory_capture_transcript_drops_tools_by_default(fake_memory, bind_agent, monkeypatch):
    """上传整份、落库只留人和助手：工具事件解析了但不进 L0（``parsed`` 仍计入）。"""
    monkeypatch.setattr(mm, "_trigger_extract", lambda server, session_id: True)
    mcp = mm.build_memory_mcp(mock.MagicMock())

    result = _tools(mcp)["memory_capture"].fn(
        content=_TOOL_TRANSCRIPT, source="claude-code", session_id="cc:s4"
    )

    assert result["tool_events"] == "none"
    assert result["parsed"] == 4  # 整份 transcript 都解析了（含 call/result）
    assert result["skipped_tools"] == 2
    assert result["events_by_type"] == {"user_message": 1, "assistant_message": 1}
    assert result["imported"] == 2


def test_no_caller_means_no_prefix(fake_memory, bind_agent, monkeypatch, tmp_path):
    """headers 里没有「谁说的」就不加前缀——两种形态一致，不凭空造归属。"""
    monkeypatch.setattr(mm, "_trigger_extract", lambda server, session_id: True)
    monkeypatch.setattr(mm, "_resolve_agent_scope", lambda server, agent_id: (tmp_path, {}))
    mcp = mm.build_memory_mcp(mock.MagicMock())

    # 一轮形态：没有 X-Octop-User-Id
    _tools(mcp)["memory_capture"].fn(content="接口先不要动", source="review-bot")
    assert fake_memory.add_raw.call_args.args[0] == "接口先不要动"

    # transcript 形态：同样不加
    _tools(mcp)["memory_capture"].fn(content=_TRANSCRIPT, source="claude-code", session_id="cc:s7")
    stored = fake_memory.add_raw_batch.call_args.args[0]
    assert stored[0].content == "先看看 CLI 结构"
    assert not stored[0].content.startswith("说：")


def test_memory_capture_archives_the_raw_session_as_markdown(
    fake_memory, bind_agent, monkeypatch, tmp_path
):
    """L0 只留人和助手，整份上传的会话另存 md 归档——工具过程在归档里可查。"""
    from octop.infra.agents.workspace import host_system_dir

    monkeypatch.setattr(mm, "_trigger_extract", lambda server, session_id: True)
    monkeypatch.setattr(mm, "_resolve_agent_scope", lambda server, agent_id: (tmp_path, {}))
    mcp = mm.build_memory_mcp(mock.MagicMock())

    result = _tools(mcp)["memory_capture"].fn(
        content=_TOOL_TRANSCRIPT, source="claude-code", session_id="cc:s5"
    )

    archive = host_system_dir(tmp_path, {}) / "memory-sessions" / "cc_s5.md"
    assert result["events_by_type"] == {"user_message": 1, "assistant_message": 1}
    assert result["session_archive"] == str(archive)
    body = archive.read_text(encoding="utf-8")
    assert "**tool_call" in body and "**tool_result" in body
    assert "<!-- key: tu1 -->" in body

    # 整份重发（offset 丢失后的 mode=full）：不重复追加
    again = _tools(mcp)["memory_capture"].fn(
        content=_TOOL_TRANSCRIPT, source="claude-code", session_id="cc:s5"
    )
    assert again["session_archive"] is None
    assert archive.read_text(encoding="utf-8") == body


def test_memory_capture_dry_run_writes_no_archive(fake_memory, bind_agent, monkeypatch, tmp_path):
    """dry_run 只解析：不落 L0，也不写归档。"""
    monkeypatch.setattr(mm, "_resolve_agent_scope", lambda server, agent_id: (tmp_path, {}))
    mcp = mm.build_memory_mcp(mock.MagicMock())

    result = _tools(mcp)["memory_capture"].fn(
        content=_TOOL_TRANSCRIPT, source="claude-code", session_id="cc:s6", dry_run=True
    )

    assert result["session_archive"] is None
    assert not (tmp_path / "memory-sessions").exists()


def test_memory_capture_rejects_unknown_tool_events(fake_memory, bind_agent):
    mcp = mm.build_memory_mcp(mock.MagicMock())
    with pytest.raises(ValueError, match="unknown tool_events"):
        _tools(mcp)["memory_capture"].fn(
            content=_TOOL_TRANSCRIPT, source="claude-code", tool_events="whatever"
        )


def test_memory_capture_transcript_drops_host_plumbing(fake_memory, bind_agent, monkeypatch):
    """Terminal-injected instructions and bundled skill docs are not conversation.

    Slash-command wrappers and local-command output stay: those record a user action
    and its effect.
    """
    monkeypatch.setattr(mm, "_trigger_extract", lambda server, session_id: True)
    mcp = mm.build_memory_mcp(mock.MagicMock())
    records = [
        {
            "type": "user",
            "uuid": "u1",
            "sessionId": "s6",
            "timestamp": "2026-09-22T05:00:00Z",
            "message": {"role": "user", "content": "正常提问"},
        },
        {
            "type": "user",
            "uuid": "u2",
            "sessionId": "s6",
            "timestamp": "2026-09-22T05:00:01Z",
            "message": {
                "role": "user",
                "content": "<system-reminder>技能目录已更新</system-reminder>",
            },
        },
        {
            "type": "user",
            "uuid": "u3",
            "sessionId": "s6",
            "timestamp": "2026-09-22T05:00:02Z",
            "message": {
                "role": "user",
                "content": "Base directory for this skill: /tmp/x\n# Building LLM apps",
            },
        },
        {
            "type": "user",
            "uuid": "u4",
            "sessionId": "s6",
            "timestamp": "2026-09-22T05:00:03Z",
            "message": {
                "role": "user",
                "content": "<command-name>/model</command-name><command-message>model</command-message>",
            },
        },
        {
            "type": "assistant",
            "uuid": "a1",
            "sessionId": "s6",
            "timestamp": "2026-09-22T05:00:04Z",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "x"}}
                ],
            },
        },
        {
            "type": "user",
            "uuid": "u5",
            "sessionId": "s6",
            "timestamp": "2026-09-22T05:00:05Z",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "t1",
                        "content": "1→Base directory for this skill: /tmp/x",
                        "is_error": False,
                    }
                ],
            },
        },
    ]

    result = _tools(mcp)["memory_capture"].fn(
        content="\n".join(json.dumps(record, ensure_ascii=False) for record in records),
        source="claude-code",
        session_id="cc:s6",
        tool_events="all",
    )

    assert result["parsed"] == 6
    assert result["skipped_echo"] == 2  # system-reminder + skill 文档（都是消息事件）
    assert result["imported"] == 4  # 真实提问 / 斜杠命令 / tool_call / tool_result
    raws = fake_memory.add_raw_batch.call_args.args[0]
    contents = [raw.content for raw in raws]
    assert any("正常提问" in c for c in contents)
    assert any("<command-name>" in c for c in contents)
    assert all("system-reminder" not in c for c in contents)
    # 工具输出里出现同样字符串属于数据（读到的文件刚好含这句），不能当作注入丢弃
    assert any("Base directory for this skill" in c for c in contents)


def test_memory_capture_transcript_drops_own_hook_text(fake_memory, bind_agent, monkeypatch):
    """Our own hook instruction is prompt plumbing, not something the user said."""
    monkeypatch.setattr(mm, "_trigger_extract", lambda server, session_id: True)
    mcp = mm.build_memory_mcp(mock.MagicMock())
    records = [
        {
            "type": "user",
            "uuid": "u1",
            "sessionId": "s7",
            "timestamp": "2026-09-22T05:00:00Z",
            "message": {"role": "user", "content": "AI预定是哪个项目?"},
        },
        {
            "type": "user",
            "uuid": "u2",
            "sessionId": "s7",
            "timestamp": "2026-09-22T05:00:01Z",
            "message": {
                "role": "user",
                "content": "Stop hook feedback:\n[octop-memory hook] 本轮对话结束前，请把要点记录下来",
            },
        },
    ]

    result = _tools(mcp)["memory_capture"].fn(
        content="\n".join(json.dumps(record, ensure_ascii=False) for record in records),
        source="claude-code",
        session_id="cc:s7",
    )

    assert result["parsed"] == 2
    assert result["skipped_echo"] == 1
    assert result["imported"] == 1
    raws = fake_memory.add_raw_batch.call_args.args[0]
    assert all("octop-memory hook" not in raw.content for raw in raws)


def test_memory_capture_transcript_rejects_broken_gzip_marker(fake_memory, bind_agent):
    """``H4sI…`` says gzip+base64; if it does not decode, say so instead of storing junk."""
    mcp = mm.build_memory_mcp(mock.MagicMock())
    with pytest.raises(ValueError, match="gzip\\+base64"):
        _tools(mcp)["memory_capture"].fn(content="H4sI!!!not-base64", source="claude-code")


def test_memory_capture_text_source_ignores_gzip_sniffing(fake_memory, bind_agent):
    """A plain-text capture that happens to look base64-ish must stay verbatim."""
    mcp = mm.build_memory_mcp(mock.MagicMock())
    _tools(mcp)["memory_capture"].fn(content="H4sI 是一段普通笔记", source="review-bot")
    assert fake_memory.add_raw.call_args.args[0] == "H4sI 是一段普通笔记"


def test_memory_save_can_supersede_an_atom(fake_memory, bind_agent):
    """Correcting a fact = save the new one and name what it replaces."""
    mcp = mm.build_memory_mcp(mock.MagicMock())
    result = _tools(mcp)["memory_save"].fn(
        content="new fact", source="review-bot", supersedes="atom1"
    )
    fake_memory.deprecate_atom.assert_called_once_with(
        "atom1", actor="user", note="superseded by memory_save"
    )
    assert fake_memory.store.call_args.kwargs["metadata"] == {
        "source": "review-bot",
        "supersedes": "atom1",
    }
    assert result["deprecated"] is True
    assert result["superseded_atom_id"] == "atom1"


def test_memory_save_without_supersedes_does_not_deprecate(fake_memory, bind_agent):
    mcp = mm.build_memory_mcp(mock.MagicMock())
    result = _tools(mcp)["memory_save"].fn(content="plain fact", source="review-bot")
    fake_memory.deprecate_atom.assert_not_called()
    assert fake_memory.store.call_args.kwargs["metadata"] == {"source": "review-bot"}
    assert "superseded_atom_id" not in result


def _asgi_scope(headers: list[tuple[bytes, bytes]] | None = None) -> dict:
    return {"type": "http", "headers": headers or []}


@pytest.mark.asyncio
async def test_token_middleware_rejects_bad_token():
    inner_called = False

    async def _inner(scope, receive, send):
        nonlocal inner_called
        inner_called = True

    mw = mm._TokenAuthMiddleware(_inner, "secret")
    sent = []
    scope = _asgi_scope([(b"authorization", b"Bearer wrong")])

    async def _send(msg):
        sent.append(msg)

    await mw(scope, lambda: {}, _send)
    assert inner_called is False
    assert sent[0]["status"] == 401


@pytest.mark.asyncio
async def test_token_middleware_accepts_bearer():
    inner_called = False

    async def _inner(scope, receive, send):
        nonlocal inner_called
        inner_called = True

    mw = mm._TokenAuthMiddleware(_inner, "secret")
    scope = _asgi_scope([(b"authorization", b"Bearer secret")])
    await mw(scope, lambda: {}, lambda msg: None)
    assert inner_called is True


def test_mount_fail_closed_without_token(monkeypatch):
    monkeypatch.delenv("OCTOP_MEMORY_MCP_TOKEN", raising=False)
    app = mock.MagicMock()
    assert mm.mount_memory_mcp(app, mock.MagicMock()) == []
    app.mount.assert_not_called()


def test_mount_unified_path_with_shared_app(monkeypatch):
    """A single shared MCP app is mounted once at /mcp/memory."""
    from types import SimpleNamespace

    monkeypatch.setenv("OCTOP_MEMORY_MCP_TOKEN", "secret")
    app = mock.MagicMock()
    server = SimpleNamespace(services=SimpleNamespace(agent_repo=mock.MagicMock()))
    managers = mm.mount_memory_mcp(app, server)
    assert len(managers) == 1
    app.mount.assert_called_once()
    assert app.mount.call_args.args[0] == "/mcp/memory"


@pytest.mark.asyncio
async def test_agent_router_routes_by_header():
    """_AgentRouter validates the agent, binds the contextvar, forwards to the shared app."""
    from types import SimpleNamespace

    seen = {}

    class _FakeApp:
        async def __call__(self, scope, receive, send):
            seen["agent"] = mm._current_agent_id.get()

    rows = {
        "A1": SimpleNamespace(agent_id="A1", enabled=True),
        "A2": SimpleNamespace(agent_id="A2", enabled=True),
    }
    server = SimpleNamespace(
        services=SimpleNamespace(agent_repo=mock.MagicMock(get=lambda aid: rows.get(aid)))
    )
    router = mm._AgentRouter(_FakeApp(), server)
    scope = {"type": "http", "headers": [(b"x-octop-agent-id", b"A2")]}
    await router(scope, lambda: {}, lambda msg: None)
    assert seen["agent"] == "A2"


@pytest.mark.asyncio
async def test_agent_router_404_unknown_agent():
    """Unknown agent_id returns 404 before dispatching."""
    from types import SimpleNamespace

    server = SimpleNamespace(
        services=SimpleNamespace(agent_repo=mock.MagicMock(get=lambda aid: None))
    )
    router = mm._AgentRouter(mock.MagicMock(), server)
    scope = {"type": "http", "headers": [(b"x-octop-agent-id", b"NOPE")]}
    sent = []

    async def _send(msg):
        sent.append(msg)

    await router(scope, lambda: {}, _send)
    assert sent[0]["status"] == 404


def test_trigger_extract_no_session_returns_false():
    """No session_id -> no extraction trigger."""
    assert mm._trigger_extract(mock.MagicMock(), None) is False


def test_trigger_extract_no_service_warns_after_start(monkeypatch, caplog):
    """Stopped / memory-less agent: schedule wake+extract, warn if still no service."""
    import asyncio
    import logging

    agent = mock.MagicMock()
    agent._memory_runtime = mock.MagicMock(service=None)
    registry = mock.MagicMock()
    registry.get_agent.return_value = agent

    async def _start(_aid: str) -> None:
        return None

    registry.start = _start
    server = mock.MagicMock()
    server.app_runtime.agent_registry = registry
    created: list = []

    def _capture(coro):
        created.append(coro)
        return mock.MagicMock()

    monkeypatch.setattr(asyncio, "create_task", _capture)
    token = mm._current_agent_id.set("A1")
    try:
        with caplog.at_level(logging.WARNING, logger="octop.infra.agents.memory_mcp"):
            assert mm._trigger_extract(server, "kiro-chat") is True
            assert len(created) == 1
            asyncio.run(created[0])
    finally:
        mm._current_agent_id.reset(token)
    assert "MemoryService still unavailable" in caplog.text


def test_trigger_extract_starts_stopped_agent(monkeypatch):
    """When get_agent fails (stopped), start the expert then extract."""
    import asyncio

    service = mock.MagicMock()
    service.extract.return_value = {"candidates": 1}
    agent = mock.MagicMock()
    agent._memory_runtime = mock.MagicMock(service=service)
    registry = mock.MagicMock()
    registry.get_agent.side_effect = [
        RuntimeError("not running"),
        agent,
    ]
    registry.start = mock.AsyncMock()
    server = mock.MagicMock()
    server.app_runtime.agent_registry = registry
    created: list = []

    def _capture(coro):
        created.append(coro)
        return mock.MagicMock()

    monkeypatch.setattr(asyncio, "create_task", _capture)
    token = mm._current_agent_id.set("A1")
    try:
        assert mm._trigger_extract(server, "cursor:sess") is True
        assert len(created) == 1
        asyncio.run(created[0])
    finally:
        mm._current_agent_id.reset(token)
    registry.start.assert_awaited_once_with("A1")
    assert registry.get_agent.call_count == 2
    service.extract.assert_called_once_with(
        "cursor:sess", incremental=True, promote=True, regen_pages=True
    )


def test_trigger_extract_schedules_service(monkeypatch):
    """With a service, asynchronously schedule extract and return True."""
    import asyncio

    agent = mock.MagicMock()
    service = mock.MagicMock()
    service.extract.return_value = {"candidates": 0}
    runtime = mock.MagicMock()
    runtime.service = service
    agent._memory_runtime = runtime
    registry = mock.MagicMock(get_agent=lambda aid: agent)
    server = mock.MagicMock()
    server.app_runtime.agent_registry = registry
    created: list = []

    def _capture(coro):
        created.append(coro)
        return mock.MagicMock()

    monkeypatch.setattr(asyncio, "create_task", _capture)

    token = mm._current_agent_id.set("A1")
    try:
        assert mm._trigger_extract(server, "kiro-chat") is True
        assert len(created) == 1
        asyncio.run(created[0])
    finally:
        mm._current_agent_id.reset(token)
    service.extract.assert_called()
    assert service.extract.call_args.args[0] == "kiro-chat"


def _with_agent(agent_id: str):
    """Bind the request-scoped agent contextvar for a single tool call."""
    return mm._current_agent_id.set(agent_id)


def test_memory_candidates_passes_status_string(fake_memory):
    """``status`` is a typing.Literal of strings: pass the raw value, don't
    instantiate it (previously crashed with "Cannot instantiate typing.Literal")."""
    fake_memory.list_candidates.return_value = []
    mcp = mm.build_memory_mcp(mock.MagicMock())
    token = _with_agent("A1")
    try:
        result = _tools(mcp)["memory_candidates"].fn(status="pending", limit=5)
    finally:
        mm._current_agent_id.reset(token)
    assert result["candidates"] == []
    assert fake_memory.list_candidates.call_args.kwargs["status"] == "pending"


def test_memory_candidates_not_a_status_raises(fake_memory):
    mcp = mm.build_memory_mcp(mock.MagicMock())
    token = _with_agent("A1")
    try:
        with pytest.raises(ValueError):
            _tools(mcp)["memory_candidates"].fn(status="no-such-status")
    finally:
        mm._current_agent_id.reset(token)


class _FakeBridge:
    """Stand-in for ``octop_memory``'s ``Bridge``, recording dispatched RPCs."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.results: dict[str, dict] = {}
        self.errors: dict[str, str] = {}

    def handle(self, request):
        method, params = request["method"], request["params"]
        self.calls.append((method, params))
        key = params.get("candidate_id")
        if key in self.errors:
            return {
                "jsonrpc": "2.0",
                "id": request["id"],
                "error": {"code": -32602, "message": self.errors[key]},
            }
        return {"jsonrpc": "2.0", "id": request["id"], "result": self.results.get(key, {})}


@pytest.fixture
def fake_bridge(monkeypatch):
    """Replace the dashboard bridge so review tools need no real Memory."""
    bridge = _FakeBridge()
    monkeypatch.setattr(mm, "_dashboard_bridge", lambda memory: bridge)
    return bridge


_PROMOTED = {
    "promoted": 1,
    "merged": 0,
    "conflicts": 0,
    "needs_review": 0,
    "dropped": 0,
    "llm_calls": 0,
}


def test_memory_promote_delegates_to_dashboard_rpc(fake_memory, fake_bridge):
    """采纳走 dashboard 的 ``promote_candidate``：同参数、同返回、逐条聚合。"""
    fake_bridge.results["c1"] = _PROMOTED
    fake_bridge.results["c2"] = {**_PROMOTED, "promoted": 0, "merged": 1}
    mcp = mm.build_memory_mcp(mock.MagicMock())
    token = _with_agent("A1")
    try:
        result = _tools(mcp)["memory_promote"].fn(candidate_ids=["c1", "c2"])
    finally:
        mm._current_agent_id.reset(token)
    assert fake_bridge.calls == [
        ("promote_candidate", {"candidate_id": "c1"}),
        ("promote_candidate", {"candidate_id": "c2"}),
    ]
    assert result["promoted"] == 1
    assert result["merged"] == 1
    assert [c["candidate_id"] for c in result["candidates"]] == ["c1", "c2"]
    assert result["errors"] == []


def test_memory_promote_isolates_per_candidate_errors(fake_memory, fake_bridge):
    """单条被 dashboard 拒绝（如非 pending）不影响同批其它候选。"""
    fake_bridge.results["c1"] = _PROMOTED
    fake_bridge.errors["c2"] = "candidate 'c2' not pending (current status='promoted')"
    mcp = mm.build_memory_mcp(mock.MagicMock())
    token = _with_agent("A1")
    try:
        result = _tools(mcp)["memory_promote"].fn(candidate_ids=["c1", "c2"])
    finally:
        mm._current_agent_id.reset(token)
    assert result["promoted"] == 1
    assert [c["candidate_id"] for c in result["candidates"]] == ["c1"]
    assert result["errors"] == [
        {"candidate_id": "c2", "error": "candidate 'c2' not pending (current status='promoted')"}
    ]


def test_memory_reject_delegates_to_dashboard_rpc(fake_memory, fake_bridge):
    """忽略走 dashboard 的 ``reject_candidate``；缺省actor与面板一致不传。"""
    fake_bridge.results["c1"] = {"candidate_id": "c1", "status": "rejected"}
    mcp = mm.build_memory_mcp(mock.MagicMock())
    token = _with_agent("A1")
    try:
        result = _tools(mcp)["memory_reject"].fn(candidate_id="c1", reason="dup")
    finally:
        mm._current_agent_id.reset(token)
    assert fake_bridge.calls == [("reject_candidate", {"candidate_id": "c1", "reason": "dup"})]
    assert result == {"ok": True, "candidate_id": "c1", "status": "rejected"}


def test_memory_reject_passes_actor_when_given(fake_memory, fake_bridge):
    mcp = mm.build_memory_mcp(mock.MagicMock())
    token = _with_agent("A1")
    try:
        _tools(mcp)["memory_reject"].fn(candidate_id="c1", reason="dup", actor="auto")
    finally:
        mm._current_agent_id.reset(token)
    assert fake_bridge.calls == [
        ("reject_candidate", {"candidate_id": "c1", "reason": "dup", "actor": "auto"})
    ]


def test_memory_reject_surfaces_bridge_error(fake_memory, fake_bridge):
    fake_bridge.errors["c1"] = "candidate 'c1' cannot be rejected (current status='promoted')"
    mcp = mm.build_memory_mcp(mock.MagicMock())
    token = _with_agent("A1")
    try:
        with pytest.raises(ValueError, match="cannot be rejected"):
            _tools(mcp)["memory_reject"].fn(candidate_id="c1")
    finally:
        mm._current_agent_id.reset(token)


def test_memory_promote_end_to_end_through_real_bridge(tmp_path, monkeypatch):
    """真实 harness-memory + Bridge：pending 候选经 MCP 采纳后落成原子。

    这是本次改动的核心契约——MCP 与记忆面板共用 dashboard_data，而不是各自
    一份实现（旧实现直接调 ``Memory.promote_candidates``，对 conflict 候选无效）。
    """
    pytest.importorskip("octop_memory.adapters.bridge.handlers")
    from octop_memory.core import Memory  # noqa: PLC0415
    from octop_memory.types import Candidate, RawEvent  # noqa: PLC0415

    memory = Memory(
        namespace="agent_a1",
        backend="sqlite",
        backend_config={"db_path": str(tmp_path / "memory.sqlite")},
    )
    memory.add_raw_batch(
        [
            RawEvent(
                id="raw-1",
                host="octop",
                session_id="s1",
                thread_id="t1",
                user="u",
                timestamp=datetime.now(UTC),
                event_type="user_message",
                content="我喜欢喝美式咖啡",
            )
        ]
    )
    memory.add_candidate(
        Candidate(
            id="cand-1",
            raw_event_ids=["raw-1"],
            candidate_type="Preference",
            status="pending",
            title="美式咖啡偏好",
            assertion="喜欢喝美式咖啡",
            verbatim_quote="我喜欢喝美式咖啡",
            quote_event_id="raw-1",
            subject_name="user",
            subject_entity_type="User",
            target_entity_id=None,
            confidence="high",
            importance="high",
            recommended_action="promote",
            promotion_reason="seed",
            extractor_version="test",
            created_at=datetime.now(UTC),
        )
    )
    monkeypatch.setattr(mm, "_open_memory", lambda server, agent_id: memory)
    mcp = mm.build_memory_mcp(mock.MagicMock())
    token = _with_agent("A1")
    try:
        result = _tools(mcp)["memory_promote"].fn(candidate_ids=["cand-1"])
        again = _tools(mcp)["memory_promote"].fn(candidate_ids=["cand-1"])
    finally:
        mm._current_agent_id.reset(token)
    assert result["errors"] == []
    assert result["promoted"] == 1
    assert memory.get_candidate("cand-1").status == "promoted"
    assert [a.assertion for a in memory.list_atoms()] == ["喜欢喝美式咖啡"]
    # 重复采纳被 dashboard 的终态守卫挡下，且报错文本与面板一致（含当前状态）。
    assert again["promoted"] == 0
    assert len(again["errors"]) == 1
    assert "status=" in again["errors"][0]["error"]


def _stub_runtime(monkeypatch, *, hits=None, get_result=None, captured=None):
    """Patch ``MemoryRuntime`` so search/get run against a fake runtime."""

    class _FakeRuntime:
        def __init__(self, memory):
            if captured is not None:
                captured["memory"] = memory

        def memory_search(self, params):
            if captured is not None:
                captured["search_params"] = params
            return {"hits": list(hits or []), "total": len(hits or []), "empty_reason": None}

        def memory_get(self, params):
            if captured is not None:
                captured["get_params"] = params
            return dict(get_result or {})

    import octop_memory.application.runtime as _runtime

    monkeypatch.setattr(_runtime, "MemoryRuntime", _FakeRuntime)


def test_tool_responses_carry_the_family_marker(fake_memory, monkeypatch, bind_agent):
    """One prefix (``[octop memory ``) lets any consumer filter all of our output."""
    _stub_runtime(monkeypatch, hits=[], get_result={"path": "atom/a1.md", "excerpt": ""})
    mcp = mm.build_memory_mcp(mock.MagicMock())
    tools = _tools(mcp)

    assert tools["memory_search"].fn(query="q")["marker"] == "[octop memory search]"
    assert tools["memory_get"].fn(path="atom/a1.md")["marker"] == "[octop memory get]"
    assert tools["memory_capture"].fn(content="x", source="s")["marker"] == "[octop memory capture]"


def test_memory_capture_drops_family_marker_content(fake_memory, bind_agent):
    """A ``[octop memory …]`` payload is our own output, not something the user said."""
    mcp = mm.build_memory_mcp(mock.MagicMock())
    result = _tools(mcp)["memory_capture"].fn(
        content="[octop memory search] related memories: - [atom] 旧内容", source="hook"
    )
    assert result["recorded"] is False
    assert result["skipped"] == "recall_echo"
    fake_memory.add_raw.assert_not_called()


def test_memory_search_projects_hit_paths(fake_memory, monkeypatch, bind_agent):
    """memory_search runs the shared pipeline and returns path-carrying hits."""
    captured = {}
    _stub_runtime(
        monkeypatch,
        hits=[
            {"path": "atom/a1.md", "layer": "atom", "snippet": "s1", "source_id": "a1"},
            {"path": "raw/2026-08-19/r1.md", "layer": "raw", "snippet": "s2", "source_id": "r1"},
        ],
        captured=captured,
    )
    mcp = mm.build_memory_mcp(mock.MagicMock())
    result = _tools(mcp)["memory_search"].fn(query="billing", max_results=5)
    assert captured["memory"] is fake_memory
    assert captured["search_params"] == {"query": "billing", "maxResults": 5, "corpus": "memory"}
    assert [hit["path"] for hit in result["hits"]] == ["atom/a1.md", "raw/2026-08-19/r1.md"]
    assert result["total"] == 2
    assert result["corpus"] == "all"


def test_memory_search_atom_corpus_widens_then_filters(fake_memory, monkeypatch, bind_agent):
    """``corpus=atom`` asks for a wider pool, then keeps only L2 atoms."""
    captured = {}
    _stub_runtime(
        monkeypatch,
        hits=[
            {"path": "raw/2026-08-19/r1.md", "layer": "raw", "snippet": "s2", "source_id": "r1"},
            {"path": "atom/a1.md", "layer": "atom", "snippet": "s1", "source_id": "a1"},
            {"path": "atom/a2.md", "layer": "atom", "snippet": "s3", "source_id": "a2"},
        ],
        captured=captured,
    )
    mcp = mm.build_memory_mcp(mock.MagicMock())
    result = _tools(mcp)["memory_search"].fn(query="billing", max_results=2, corpus="atom")
    assert captured["search_params"]["maxResults"] == 8
    assert [hit["path"] for hit in result["hits"]] == ["atom/a1.md", "atom/a2.md"]
    assert result["corpus"] == "atom"


def test_memory_search_raw_corpus_uses_l0_fts(fake_memory, bind_agent):
    """``corpus=raw`` bypasses the atom-first fallback and searches L0 directly."""
    from datetime import datetime

    event = mock.MagicMock()
    event.id = "r1"
    event.content = "nginx 需要 proxy /api/memory-mcp"
    event.timestamp = datetime(2026, 8, 19, 12, 0)
    fake_memory.search_raw.return_value = [event]

    mcp = mm.build_memory_mcp(mock.MagicMock())
    result = _tools(mcp)["memory_search"].fn(query="proxy", max_results=3, corpus="raw")
    fake_memory.search_raw.assert_called_once_with("proxy", limit=3)
    assert result["hits"][0]["path"] == "raw/2026-08-19/r1.md"
    assert result["hits"][0]["layer"] == "raw"


def test_memory_search_prefers_the_callers_own_hits(
    fake_memory, monkeypatch, bind_agent, bind_user
):
    """带了调用者就先把「这个人的」命中排前面：只调顺序，不过滤团队共享内容。"""
    fake_memory.get_raw_events_by_ids.return_value = [mock.MagicMock(id="r1", user="alice")]
    captured = {}
    _stub_runtime(
        monkeypatch,
        hits=[
            {"path": "atom/a1.md", "layer": "atom", "snippet": "别人说的", "source_id": "a1"},
            {
                "path": "raw/2026-08-19/r1.md",
                "layer": "raw",
                "snippet": "我说的",
                "source_id": "r1",
            },
            {
                "path": "atom/a2.md",
                "layer": "atom",
                "snippet": "alice说：我的坑",
                "source_id": "a2",
            },
        ],
        captured=captured,
    )
    mcp = mm.build_memory_mcp(mock.MagicMock())

    result = _tools(mcp)["memory_search"].fn(query="q", max_results=2)

    assert captured["search_params"]["maxResults"] == 8  # 带 caller 先放大候选池
    assert [hit["path"] for hit in result["hits"]] == ["raw/2026-08-19/r1.md", "atom/a2.md"]
    assert result["caller"] == "alice"
    assert result["personal_hits"] == 2
    assert all(hit["personal"] for hit in result["hits"])
    assert result["hits"][0]["user"] == "alice"  # raw 命中带上 raw 的 user 列


def test_memory_search_without_caller_keeps_the_pipeline_order(
    fake_memory, monkeypatch, bind_agent
):
    """没有调用者：不放大候选池、不加 personal 字段、顺序原样。"""
    captured = {}
    _stub_runtime(
        monkeypatch,
        hits=[{"path": "atom/a1.md", "layer": "atom", "snippet": "x", "source_id": "a1"}],
        captured=captured,
    )
    mcp = mm.build_memory_mcp(mock.MagicMock())

    result = _tools(mcp)["memory_search"].fn(query="q", max_results=3)

    assert captured["search_params"]["maxResults"] == 3
    assert result["caller"] is None
    assert result["personal_hits"] == 0
    assert "personal" not in result["hits"][0]


def test_memory_search_raw_corpus_prefers_the_callers_events(fake_memory, bind_agent, bind_user):
    """``corpus=raw`` 同样按 raw 的 user 列把人自己的行排前面。"""
    from datetime import datetime

    other, mine = mock.MagicMock(), mock.MagicMock()
    for event, uid, event_id in ((other, "someone-else", "r1"), (mine, "alice", "r2")):
        event.id, event.user, event.content = event_id, uid, "内容"
        event.timestamp = datetime(2026, 8, 19, 12, 0)
    fake_memory.search_raw.return_value = [other, mine]

    mcp = mm.build_memory_mcp(mock.MagicMock())
    result = _tools(mcp)["memory_search"].fn(query="q", max_results=2, corpus="raw")

    fake_memory.search_raw.assert_called_once_with("q", limit=8)
    assert [hit["source_id"] for hit in result["hits"]] == ["r2", "r1"]
    assert [hit["personal"] for hit in result["hits"]] == [True, False]
    assert [hit["user"] for hit in result["hits"]] == ["alice", "someone-else"]


def test_memory_search_rejects_unknown_corpus(fake_memory, bind_agent):
    mcp = mm.build_memory_mcp(mock.MagicMock())
    with pytest.raises(ValueError):
        _tools(mcp)["memory_search"].fn(query="billing", corpus="wiki")


def test_memory_get_returns_excerpt_as_content(fake_memory, monkeypatch, bind_agent):
    """memory_get surfaces the excerpt under ``content`` and forwards paging."""
    captured = {}
    _stub_runtime(
        monkeypatch,
        get_result={
            "path": "atom/a1.md",
            "kind": "atom",
            "excerpt": "# body",
            "metadata": {"id": "a1"},
            "total_lines": 3,
            "from_line": 1,
            "to_line": 3,
            "truncated": False,
        },
        captured=captured,
    )
    mcp = mm.build_memory_mcp(mock.MagicMock())
    result = _tools(mcp)["memory_get"].fn(path="atom/a1.md", start=1, lines=10)
    assert captured["get_params"] == {"path": "atom/a1.md", "from": 1, "lines": 10}
    assert result["content"] == "# body"
    assert result["kind"] == "atom"
    assert result["total_lines"] == 3


def test_memory_get_returns_hint_for_bad_path(fake_memory, monkeypatch, bind_agent):
    """A stale/mistyped path degrades to an error payload instead of raising."""

    class _Boom:
        def __init__(self, memory):
            pass

        def memory_get(self, params):
            raise ValueError("path must be non-empty and unpadded: 'nope'")

    import octop_memory.application.runtime as _runtime

    monkeypatch.setattr(_runtime, "MemoryRuntime", _Boom)
    mcp = mm.build_memory_mcp(mock.MagicMock())
    result = _tools(mcp)["memory_get"].fn(path="nope")
    assert "path must be non-empty" in result["error"]
    assert "atom/<atom_id>.md" in result["hint"]


def test_memory_capture_prefixes_sender(fake_memory, bind_agent, bind_user):
    """The header user id is folded into the captured text, not just the payload."""
    mcp = mm.build_memory_mcp(mock.MagicMock())
    result = _tools(mcp)["memory_capture"].fn(content="接口先不要动", source="review-bot")
    assert fake_memory.add_raw.call_args.args[0] == "alice说：接口先不要动"
    assert fake_memory.add_raw.call_args.kwargs["user"] == "alice"
    assert result["content"] == "alice说：接口先不要动"
    assert result["user"] == "alice"


def test_memory_capture_does_not_double_prefix(fake_memory, bind_agent, bind_user):
    mcp = mm.build_memory_mcp(mock.MagicMock())
    _tools(mcp)["memory_capture"].fn(content="alice说：接口先不要动", source="review-bot")
    assert fake_memory.add_raw.call_args.args[0] == "alice说：接口先不要动"


def test_memory_save_prefixes_sender(fake_memory, bind_agent, bind_user):
    mcp = mm.build_memory_mcp(mock.MagicMock())
    _tools(mcp)["memory_save"].fn(content="部署约定：端点挂在 /mcp/memory", source="coding-agent")
    assert fake_memory.store.call_args.args[0] == "alice说：部署约定：端点挂在 /mcp/memory"
    assert fake_memory.store.call_args.kwargs["metadata"]["user"] == "alice"


def test_memory_save_supersede_prefixes_sender(fake_memory, bind_agent, bind_user):
    mcp = mm.build_memory_mcp(mock.MagicMock())
    _tools(mcp)["memory_save"].fn(content="端点改到 /api/memory-mcp", source="s", supersedes="a1")
    assert fake_memory.store.call_args.args[0] == "alice说：端点改到 /api/memory-mcp"


def test_write_without_caller_keeps_content(fake_memory, bind_agent):
    """No ``X-Octop-User-Id`` -> no attribution prefix."""
    mcp = mm.build_memory_mcp(mock.MagicMock())
    _tools(mcp)["memory_save"].fn(content="no sender", source="coding-agent")
    assert fake_memory.store.call_args.args[0] == "no sender"


@pytest.mark.parametrize(
    "content",
    [
        "[memory] Earlier in this workspace, related to your question:\n- [atom] x",
        "结论见下：\n## Memory Recall\n- [atom] y\n[/memory]",
    ],
)
def test_memory_capture_drops_recall_echo(fake_memory, bind_agent, content):
    """Injected recall blocks are not captured back (mirrors skip_memory_echo)."""
    mcp = mm.build_memory_mcp(mock.MagicMock())
    result = _tools(mcp)["memory_capture"].fn(content=content, source="hook")
    assert result["recorded"] is False
    assert result["skipped"] == "recall_echo"
    assert "recall_echo" in result["skipped"]
    fake_memory.add_raw.assert_not_called()


def test_memory_capture_still_records_normal_content(fake_memory, bind_agent, bind_user):
    """The echo guard must not block ordinary captures."""
    mcp = mm.build_memory_mcp(mock.MagicMock())
    result = _tools(mcp)["memory_capture"].fn(content="接口先不要动", source="hook")
    assert result["recorded"] is True
    assert fake_memory.add_raw.call_args.args[0] == "alice说：接口先不要动"


def _installer_scope(query: str = "", method: str = "GET") -> dict:
    return {
        "type": "http",
        "method": method,
        "path": "/mcp/memory/setup",
        "root_path": "/mcp/memory",
        "query_string": query.encode(),
        "headers": [(b"host", b"127.0.0.1:8088")],
    }


async def _run_installer(scope: dict) -> tuple[list[dict], str]:
    app = mm._InstallerApp(mock.MagicMock())
    sent: list[dict] = []

    async def _send(msg):
        sent.append(msg)

    await app(scope, lambda: {}, _send)
    return sent, sent[1]["body"].decode() if len(sent) > 1 else ""


@pytest.mark.asyncio
async def test_installer_serves_the_script_without_authentication(monkeypatch):
    """公共端点：只返回脚本，不要求鉴权；实例没配默认凭据时脚本里也没有凭据。"""
    monkeypatch.delenv("OCTOP_MEMORY_MCP_TOKEN", raising=False)
    sent, body = await _run_installer(_installer_scope("agent=AGT1&terminals=kiro"))

    assert sent[0]["status"] == 200
    assert (b"content-type", b"text/x-shellscript; charset=utf-8") in sent[0]["headers"]
    assert "octop-stop-capture.mjs" in body
    assert "DEFAULT_AGENT='AGT1'" in body
    assert "DEFAULT_TERMINALS='kiro'" in body
    assert "DEFAULT_TOKEN=" not in body


@pytest.mark.asyncio
async def test_installer_bakes_the_instance_token_as_the_default(monkeypatch):
    """实例发布时配的 OCTOP_MEMORY_MCP_TOKEN 直接内置成默认凭据：用户只需专家 ID。"""
    monkeypatch.setenv("OCTOP_MEMORY_MCP_TOKEN", "octopoctop")
    _, body = await _run_installer(_installer_scope())

    assert "DEFAULT_TOKEN='octopoctop'" in body
    assert 'TOKEN="${OCTOP_MEMORY_TOKEN:-}"' in body  # 现场变量仍可覆盖
    assert "OCTOP_ENTRY_TOKEN" not in body  # 只有一份凭据


@pytest.mark.asyncio
async def test_installer_defaults_to_the_host_it_was_fetched_from():
    _, body = await _run_installer(_installer_scope())

    assert "URL='http://127.0.0.1:8088/mcp/memory/'" in body


@pytest.mark.asyncio
async def test_installer_url_query_wins_over_the_default():
    _, body = await _run_installer(_installer_scope("url=https://octop-memory.example.com/mcp"))

    assert "URL='https://octop-memory.example.com/mcp'" in body
    assert "OCTOP_SERVER_NAME='octop-memory'" in body


@pytest.mark.asyncio
async def test_installer_public_url_override(monkeypatch):
    """部署可通过环境变量指定"客户端该连哪个地址"（例如另一个 ingress 域名）。"""
    monkeypatch.setenv("OCTOP_MEMORY_PUBLIC_MCP_URL", "https://oauth.example.com/mcp")
    _, body = await _run_installer(_installer_scope())

    assert "URL='https://oauth.example.com/mcp'" in body


@pytest.mark.asyncio
async def test_installer_rejects_non_get():
    sent, body = await _run_installer(_installer_scope(method="POST"))

    assert sent[0]["status"] == 405
    assert "GET only" in body


def _one_turn_transcript() -> str:
    return json.dumps(
        {
            "type": "user",
            "uuid": "tp1",
            "sessionId": "s-tp",
            "timestamp": "2026-09-22T05:00:00Z",
            "message": {"role": "user", "content": "从文件读的一段会话"},
        }
    )


def test_memory_capture_reads_a_local_transcript_path(
    fake_memory, bind_agent, tmp_path, monkeypatch
):
    """mcp_tool hook 只传 ${transcript_path}：同机服务端把文件读进来。"""
    monkeypatch.setattr(mm, "_TRANSCRIPT_PATH_ROOTS", (str(tmp_path),))
    session_file = tmp_path / "s-tp.jsonl"
    session_file.write_text(_one_turn_transcript(), encoding="utf-8")
    mcp = mm.build_memory_mcp(mock.MagicMock())

    result = _tools(mcp)["memory_capture"].fn(
        content="", source="claude-code", transcript_path=str(session_file), session_id="cc:s-tp"
    )

    assert result["parsed"] == 1
    assert result["imported"] == 1
    assert result["events_by_type"] == {"user_message": 1}


def test_memory_capture_refuses_paths_outside_the_session_stores(fake_memory, bind_agent, tmp_path):
    """不给任意文件读取留后门：只允许终端会话目录。"""
    mcp = mm.build_memory_mcp(mock.MagicMock())
    stray = tmp_path / "secrets.txt"
    stray.write_text("nope", encoding="utf-8")

    with pytest.raises(ValueError, match="terminal session store"):
        _tools(mcp)["memory_capture"].fn(
            content="", source="claude-code", transcript_path=str(stray)
        )


def test_memory_capture_refuses_a_compressed_path(fake_memory, bind_agent, tmp_path, monkeypatch):
    monkeypatch.setattr(mm, "_TRANSCRIPT_PATH_ROOTS", (str(tmp_path),))
    packed = tmp_path / "session.v3.jsonl.zstd"
    packed.write_bytes(b"zstd-bytes")
    mcp = mm.build_memory_mcp(mock.MagicMock())

    with pytest.raises(ValueError, match=r"gzip\+base64"):
        _tools(mcp)["memory_capture"].fn(
            content="", source="claude-code", transcript_path=str(packed)
        )


@pytest.mark.asyncio
async def test_installer_defaults_to_the_deployment_config(monkeypatch, tmp_path):
    """部署在 config.json 里声明一次 memory_public_mcp_url，同学就不用传 ?url=。"""
    monkeypatch.delenv("OCTOP_MEMORY_PUBLIC_MCP_URL", raising=False)
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    (tmp_path / "config.json").write_text(
        json.dumps({"memory_public_mcp_url": "https://octop-memory.example.com/mcp"}),
        encoding="utf-8",
    )

    _, body = await _run_installer(_installer_scope())

    assert "URL='https://octop-memory.example.com/mcp'" in body


@pytest.mark.asyncio
async def test_installer_env_overrides_the_config_file(monkeypatch, tmp_path):
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    (tmp_path / "config.json").write_text(
        json.dumps({"memory_public_mcp_url": "https://from-config.example.com/mcp"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("OCTOP_MEMORY_PUBLIC_MCP_URL", "https://from-env.example.com/mcp")

    _, body = await _run_installer(_installer_scope())

    assert "URL='https://from-env.example.com/mcp'" in body


_EXTERNAL_HOST = "octop.example.com"


@pytest.mark.parametrize("host", [_EXTERNAL_HOST, "octop.internal.example"])
@pytest.mark.parametrize("proto", ["", "http", "https"])
@pytest.mark.asyncio
async def test_installer_defaults_to_this_instance_for_any_host(monkeypatch, host, proto):
    """没有显式覆盖时，条目与 hooks 都指向本实例挂载点；非本机一律 https。"""
    monkeypatch.delenv("OCTOP_MEMORY_PUBLIC_MCP_URL", raising=False)
    scope = _installer_scope()
    scope["headers"] = [(b"host", host.encode())]
    if proto:
        scope["headers"].append((b"x-forwarded-proto", proto.encode()))

    _, body = await _run_installer(scope)

    # 精确匹配整行：只写 "URL=" 会被 "HOOK_URL=" 子串误命中
    assert f"\nURL='https://{host}/mcp/memory/'\n" in body
    assert f"\nHOOK_URL='https://{host}/mcp/memory/'\n" in body


@pytest.mark.asyncio
async def test_installer_splits_the_client_entry_from_the_hook_target(monkeypatch):
    """条目地址可以被部署指到公网入口，hooks 仍拿本实例的直连挂载点（凭据同一份共享 token）。"""
    monkeypatch.setenv("OCTOP_MEMORY_PUBLIC_MCP_URL", "https://octop-memory.example.com/mcp")
    scope = _installer_scope()
    scope["headers"] = [
        (b"host", _EXTERNAL_HOST.encode()),
        (b"x-forwarded-proto", b"https"),
    ]

    _, body = await _run_installer(scope)

    assert "URL='https://octop-memory.example.com/mcp'" in body
    assert f"HOOK_URL='https://{_EXTERNAL_HOST}/mcp/memory/'" in body


@pytest.mark.asyncio
async def test_installer_hook_url_can_be_overridden(monkeypatch):
    """直连挂载点不在本机时，?hook_url= 显式指定。"""
    monkeypatch.delenv("OCTOP_MEMORY_PUBLIC_MCP_URL", raising=False)
    scope = _installer_scope()
    scope["query_string"] = b"hook_url=https%3A%2F%2Foctop.example.com%2Fmcp%2Fmemory%2F"

    _, body = await _run_installer(scope)

    assert "HOOK_URL='https://octop.example.com/mcp/memory/'" in body


@pytest.mark.parametrize("proto", ["", "http", "https"])
@pytest.mark.asyncio
async def test_installer_keeps_loopback_on_this_instance(monkeypatch, proto):
    """本机开发实例指向自己的挂载点：没有 TLS 前置，照请求的 scheme 走 http。"""
    monkeypatch.delenv("OCTOP_MEMORY_PUBLIC_MCP_URL", raising=False)
    scope = _installer_scope()
    if proto:
        scope["headers"].append((b"x-forwarded-proto", proto.encode()))

    _, body = await _run_installer(scope)

    scheme = "https" if proto == "https" else "http"
    assert f"URL='{scheme}://127.0.0.1:8088/mcp/memory/'" in body


def test_mount_serves_setup_before_the_token_check(monkeypatch):
    """GET /mcp/memory/setup 免鉴权（只发脚本）；同一挂载下的其它路径仍要 token。"""
    from types import SimpleNamespace

    from starlette.applications import Starlette
    from starlette.testclient import TestClient

    monkeypatch.setenv("OCTOP_MEMORY_MCP_TOKEN", "secret")
    app = Starlette()
    server = SimpleNamespace(services=SimpleNamespace(agent_repo=mock.MagicMock()))
    mm.mount_memory_mcp(app, server)
    client = TestClient(app)

    served = client.get("/mcp/memory/setup")
    assert served.status_code == 200
    assert served.text.startswith("#!/bin/sh")

    refused = client.post("/mcp/memory/setup")
    assert refused.status_code == 405  # 只支持 GET

    assert client.post("/mcp/memory/", json={}).status_code == 401  # 其它路径照旧鉴权


def test_mount_serves_uninstall_before_the_token_check(monkeypatch):
    """GET /mcp/memory/uninstall 同样免鉴权，只发卸载脚本。"""
    from types import SimpleNamespace

    from starlette.applications import Starlette
    from starlette.testclient import TestClient

    monkeypatch.setenv("OCTOP_MEMORY_MCP_TOKEN", "secret")
    app = Starlette()
    server = SimpleNamespace(services=SimpleNamespace(agent_repo=mock.MagicMock()))
    mm.mount_memory_mcp(app, server)
    client = TestClient(app)

    served = client.get("/mcp/memory/uninstall")
    assert served.status_code == 200
    assert served.text.startswith("#!/bin/sh")
    assert "卸载" in served.text

    assert client.post("/mcp/memory/uninstall").status_code == 405
