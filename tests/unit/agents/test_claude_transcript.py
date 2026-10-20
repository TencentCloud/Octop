"""Unit tests for the Claude Code transcript importer (infra/agents/claude_transcript)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from octop_memory.core import Memory

from octop.infra.agents.claude_transcript import (
    import_content,
    import_session,
    parse_dsh_text,
    parse_kiro_text,
    parse_session,
)

_SESSION = "sess-abc"
_TS = "2026-09-22T05:00:00.000Z"


def _record(**kwargs):
    base = {"sessionId": _SESSION, "timestamp": _TS, "isSidechain": False}
    base.update(kwargs)
    return base


def _write(tmp_path: Path, records: list[dict]) -> Path:
    path = tmp_path / "session.jsonl"
    path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records), encoding="utf-8"
    )
    return path


def _turn_records() -> list[dict]:
    return [
        {"type": "queue-operation", "sessionId": _SESSION, "operation": "enqueue"},
        _record(type="progress", uuid="p1"),
        _record(type="user", uuid="u1", message={"role": "user", "content": "帮我加一个导入命令"}),
        _record(
            type="assistant",
            uuid="a1",
            message={
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "model scratchpad"},
                    {"type": "text", "text": "好的，先看现有 CLI 结构"},
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "Read",
                        "input": {"file_path": "src/octop/cli/main.py"},
                    },
                ],
            },
        ),
        _record(
            type="user",
            uuid="u2",
            message={
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_1",
                        "content": [{"type": "text", "text": "@click.group ..."}],
                        "is_error": False,
                    }
                ],
            },
        ),
    ]


@pytest.fixture
def agent_memory(tmp_path: Path) -> Memory:
    return Memory(
        namespace="agent_TEST",
        backend="sqlite",
        backend_config={"db_path": str(tmp_path / "memory.sqlite")},
    )


def test_parse_maps_conversation_records(tmp_path: Path) -> None:
    parsed = parse_session(_write(tmp_path, _turn_records()))

    assert parsed.session_id == _SESSION
    # thinking / progress / queue-operation carry no L0 content
    assert [event.event_type for event in parsed.events] == [
        "user_message",
        "assistant_message",
        "tool_call",
        "tool_result",
    ]
    # keys use the ORIGINAL block index (thinking keeps index 0) so they stay
    # stable if the importer later changes which block types it maps
    assert [event.key for event in parsed.events] == ["u1:0", "a1:1", "a1:2", "u2:0"]

    user, assistant, tool_call, tool_result = parsed.events
    assert user.content == "帮我加一个导入命令"
    assert assistant.content == "好的，先看现有 CLI 结构"
    assert tool_call.content.startswith("Read ")
    assert tool_call.payload["tool_name"] == "Read"
    assert tool_call.payload["tool_use_id"] == "toolu_1"
    assert tool_call.payload["input"] == {"file_path": "src/octop/cli/main.py"}
    assert tool_result.content == "@click.group ..."
    assert tool_result.payload["tool_use_id"] == "toolu_1"
    assert tool_result.payload["is_error"] is False
    assert user.timestamp.year == 2026 and user.timestamp.tzinfo is not None
    # role/session markers survive on every event
    assert {event.payload["role"] for event in parsed.events} == {"user", "assistant"}
    assert all(event.payload["src_key"] == event.key for event in parsed.events)


def test_parse_skips_non_conversation_records(tmp_path: Path) -> None:
    parsed = parse_session(_write(tmp_path, _turn_records()))
    assert not [event for event in parsed.events if event.payload["src_key"].startswith("p1")]


def test_import_writes_l0_and_is_idempotent(tmp_path: Path, agent_memory: Memory) -> None:
    path = _write(tmp_path, _turn_records())

    first = import_session(agent_memory, path)
    assert first.session_id == f"cc:{_SESSION}"
    assert first.parsed == 4
    assert first.imported == 4
    assert first.skipped_existing == 0

    stored = agent_memory.list_raw(session_id=f"cc:{_SESSION}", limit=100)
    assert len(stored) == 4
    assert {raw.event_type for raw in stored} == {
        "user_message",
        "assistant_message",
        "tool_call",
        "tool_result",
    }
    assert all(raw.host == "claude-code" for raw in stored)
    assert all(raw.thread_id == f"cc:{_SESSION}" for raw in stored)

    again = import_session(agent_memory, path)
    assert again.imported == 0
    assert again.skipped_existing == 4
    assert len(agent_memory.list_raw(session_id=f"cc:{_SESSION}", limit=100)) == 4


def test_import_appends_only_new_turns(tmp_path: Path, agent_memory: Memory) -> None:
    records = _turn_records()
    path = _write(tmp_path, records)
    import_session(agent_memory, path)

    records.append(
        _record(type="user", uuid="u3", message={"role": "user", "content": "继续，加上 --dry-run"})
    )
    path = _write(tmp_path, records)

    stats = import_session(agent_memory, path)
    assert stats.imported == 1
    assert stats.skipped_existing == 4


def test_import_dry_run_writes_nothing(tmp_path: Path, agent_memory: Memory) -> None:
    path = _write(tmp_path, _turn_records())

    stats = import_session(agent_memory, path, dry_run=True)
    assert stats.imported == 0
    assert stats.parsed == 4
    assert agent_memory.list_raw(session_id=f"cc:{_SESSION}", limit=100) == []


def test_import_caps_long_tool_results(tmp_path: Path, agent_memory: Memory) -> None:
    huge = "x" * 20_000
    records = [
        _record(
            type="user",
            uuid="u1",
            message={
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "t", "content": huge, "is_error": False}
                ],
            },
        )
    ]
    import_session(agent_memory, _write(tmp_path, records))

    stored = agent_memory.list_raw(session_id=f"cc:{_SESSION}", limit=10)
    assert len(stored) == 1
    assert len(stored[0].content) == 4000


def test_user_attribution_is_stored(tmp_path: Path, agent_memory: Memory) -> None:
    import_session(agent_memory, _write(tmp_path, _turn_records()), user="alice")
    stored = agent_memory.list_raw(session_id=f"cc:{_SESSION}", limit=10)
    assert {raw.user for raw in stored} == {"alice"}


@pytest.mark.parametrize(
    "tool_name",
    [
        "memory_search",
        "mcp__octop-memory-local__memory_search",
        "mcp__octop-memory-prod__memory_search",
        "mcp__octop-memory-oauth__memory_search",
        "mcp__whatever-the-user-called-it__memory_recall",
        "mcp_octop_memory_local_memory_search",
        "mcp_octop_memory_prod_memory_get",
    ],
)
def test_our_read_tools_are_recognized_under_any_mcp_name(tool_name: str) -> None:
    """MCP 服务名可能是 local / prod / oauth 或用户自取的名字：只按工具名认。"""
    from octop.infra.agents.claude_transcript import _is_own_read_tool

    assert _is_own_read_tool(tool_name)
    # 写工具（memory_capture / memory_save）不是「读工具」，别把用户自己的调用误丢
    assert not _is_own_read_tool("mcp__octop-memory-prod__memory_capture")
    assert not _is_own_read_tool("Bash")


def test_parse_drops_our_own_memory_read_results(tmp_path: Path) -> None:
    """Re-importing our own recall output would close the echo loop."""
    records = [
        _record(
            type="assistant",
            uuid="a1",
            message={
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "t1",
                        "name": "mcp__octop-memory-local__memory_search",
                        "input": {"query": "x"},
                    },
                    {"type": "tool_use", "id": "t2", "name": "Bash", "input": {"command": "ls"}},
                ],
            },
        ),
        _record(
            type="user",
            uuid="u1",
            message={
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "t1",
                        "content": '{"hits": [{"snippet": "旧记忆"}]}',
                        "is_error": False,
                    },
                    {
                        "type": "tool_result",
                        "tool_use_id": "t2",
                        "content": "file list",
                        "is_error": False,
                    },
                ],
            },
        ),
    ]

    parsed = parse_session(_write(tmp_path, records))

    assert [event.event_type for event in parsed.events] == [
        "tool_call",
        "tool_call",
        "tool_result",
    ]
    assert parsed.events[-1].content == "file list"
    assert parsed.skipped_own_results == 1


def test_import_content_drops_marked_events(agent_memory: Memory) -> None:
    """A recalled block must not be written back into L0 as new evidence."""
    records = [
        _record(type="user", uuid="u1", message={"role": "user", "content": "正常提问"}),
        _record(
            type="user",
            uuid="u2",
            message={"role": "user", "content": "## Memory Recall\n- [atom] 旧记忆块"},
        ),
    ]
    text = "\n".join(json.dumps(record, ensure_ascii=False) for record in records)

    stats = import_content(agent_memory, text, skip_markers=("## Memory Recall",))

    assert stats.parsed == 2
    assert stats.skipped_echo == 1
    assert stats.imported == 1
    stored = agent_memory.list_raw(session_id=stats.session_id, limit=10)
    assert [raw.content for raw in stored] == ["正常提问"]


def test_user_messages_are_attributed_to_the_caller(agent_memory: Memory) -> None:
    """transcript 形态也要让发送者进正文：提取器 prompt 看不到 raw 的 ``user`` 列。"""
    records = [
        _record(type="user", uuid="u1", message={"role": "user", "content": "帮我加一个导入命令"}),
        _record(
            type="assistant",
            uuid="a1",
            message={"role": "assistant", "content": [{"type": "text", "text": "好的"}]},
        ),
    ]
    text = "\n".join(json.dumps(record, ensure_ascii=False) for record in records)

    stats = import_content(agent_memory, text, session_id="cc:s1", user="alice")

    by_type = {raw.event_type: raw for raw in agent_memory.list_raw(session_id="cc:s1", limit=10)}
    assert by_type["user_message"].content == "alice说：帮我加一个导入命令"
    assert by_type["assistant_message"].content == "好的"  # 助手侧不加前缀
    assert by_type["user_message"].user == "alice"  # raw 的 user 列照旧
    assert stats.imported == 2

    # 重发（offset 丢失后的 mode=full）靠 src_key 去重，也不会把前缀叠成两层
    again = import_content(agent_memory, text, session_id="cc:s1", user="alice")
    assert again.imported == 0


def test_sidechain_user_records_are_not_attributed(agent_memory: Memory) -> None:
    """子代理记录里的 user 消息是系统合成提示，不是调用者说过的话。"""
    records = [
        _record(type="user", uuid="u1", message={"role": "user", "content": "真实提问"}),
        _record(
            type="user",
            uuid="u2",
            isSidechain=True,
            message={"role": "user", "content": "子代理提示"},
        ),
    ]
    text = "\n".join(json.dumps(record, ensure_ascii=False) for record in records)

    import_content(agent_memory, text, session_id="cc:s2", user="alice")

    contents = {raw.content for raw in agent_memory.list_raw(session_id="cc:s2", limit=10)}
    assert "alice说：真实提问" in contents
    assert "子代理提示" in contents
    assert "alice说：子代理提示" not in contents


# ---------------------------------------------------------------------------
# Kiro (``~/.kiro/sessions/<workspace>/<session_id>/messages.jsonl``)
# ---------------------------------------------------------------------------

_KIRO_RECORDS = [
    {
        "id": "r1",
        "timestamp": _TS,
        "payload": {"type": "user", "content": "Kiro 里问的问题", "source": "chat"},
    },
    {"id": "r2", "timestamp": _TS, "payload": {"type": "turn_start", "executionId": "e1"}},
    {
        "id": "r3",
        "timestamp": _TS,
        "payload": {
            "type": "ContextualHookInvoked",
            "hookId": "h",
            "output": "[octop memory search] 旧记忆",
        },
    },
    {
        "id": "r4",
        "timestamp": _TS,
        "payload": {
            "type": "tool_call",
            "toolCallId": "c1",
            "toolName": "readFiles",
            "args": {"files": ["a.ts"]},
        },
    },
    {
        "id": "r5",
        "timestamp": _TS,
        "payload": {
            "type": "tool_result",
            "toolCallId": "c1",
            "content": "file body",
            "success": True,
        },
    },
    {
        "id": "r6",
        "timestamp": _TS,
        "payload": {"type": "assistant", "content": "scratchpad", "operationType": "Reasoning"},
    },
    {
        "id": "r7",
        "timestamp": _TS,
        "payload": {"type": "assistant", "content": "这是回答", "operationType": "Say"},
    },
    {"id": "r8", "timestamp": _TS, "payload": {"type": "turn_end", "stopReason": "end_turn"}},
]


def _kiro_text() -> str:
    return "\n".join(json.dumps(r, ensure_ascii=False) for r in _KIRO_RECORDS)


def test_parse_kiro_maps_records() -> None:
    parsed = parse_kiro_text(_kiro_text())

    assert [e.event_type for e in parsed.events] == [
        "user_message",
        "tool_call",
        "tool_result",
        "assistant_message",
    ]
    assert parsed.events[3].content == "这是回答"  # Reasoning 是草稿，跳过
    assert parsed.events[1].payload["tool_name"] == "readFiles"
    assert parsed.events[2].payload["success"] is True
    # ContextualHookInvoked 是我们自己 hook 的调用记录（连 output 都在里面）
    assert parsed.skipped_own_results == 1
    assert all(e.event_type != "tool_result" or "旧记忆" not in e.content for e in parsed.events)


def test_import_content_kiro_is_idempotent(agent_memory: Memory) -> None:
    first = import_content(
        agent_memory, _kiro_text(), session_id="kiro:s1", host="kiro", parser="kiro"
    )
    assert first.session_id == "kiro:s1"
    assert first.imported == 4
    assert first.by_type == {
        "user_message": 1,
        "tool_call": 1,
        "tool_result": 1,
        "assistant_message": 1,
    }

    again = import_content(
        agent_memory, _kiro_text(), session_id="kiro:s1", host="kiro", parser="kiro"
    )
    assert again.imported == 0
    assert again.skipped_existing == 4


def test_import_content_rejects_unknown_parser(agent_memory: Memory) -> None:
    with pytest.raises(ValueError, match="unknown transcript parser"):
        import_content(agent_memory, _kiro_text(), parser="no-such-host")


# ---------------------------------------------------------------------------
# DSH (``~/.dsh/sessions/<escaped-cwd>/<session_id>/session.jsonl.zstd``)
# ---------------------------------------------------------------------------

_DSH_MS = 1788952324078
_DSH_RECORDS = [
    {"type": "session", "version": 0, "id": "session-x", "createdAt": _DSH_MS, "cwd": "/tmp"},
    {
        "type": "user/message",
        "seq": 1,
        "time": _DSH_MS,
        "data": {"content": [{"type": "text", "text": "真实提问"}], "source": {"kind": "user"}},
    },
    {
        "type": "user/message",
        "seq": 2,
        "time": _DSH_MS,
        "data": {
            "content": [
                {"type": "text", "text": "Current runtime context. This snapshot supersedes…"}
            ],
            "source": {"kind": "plugin"},
        },
    },
    {"type": "assistant/chunk", "seq": 3, "time": _DSH_MS, "data": {"text": "流式增量"}},
    {
        "type": "assistant/message",
        "seq": 4,
        "time": _DSH_MS,
        "data": {
            "turn": 1,
            "step": 1,
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "reasoning", "text": "草稿"},
                    {"type": "text", "text": "回答正文"},
                    {
                        "type": "tool-call",
                        "id": "call_1",
                        "name": "bash",
                        "arguments": '{"command": "ls"}',
                    },
                ],
            },
        },
    },
    {
        "type": "tool/call",
        "seq": 5,
        "time": _DSH_MS,
        "data": {
            "turn": 1,
            "step": 1,
            "callId": "call_1",
            "name": "bash",
            "arguments": '{"command": "ls"}',
        },
    },
    {
        "type": "tool/result",
        "seq": 6,
        "time": _DSH_MS,
        "data": {
            "turn": 1,
            "step": 1,
            "message": {
                "source": {"kind": "tool", "callId": "call_1"},
                "content": [
                    {
                        "type": "tool-result",
                        "toolCallId": "call_1",
                        "content": [{"type": "text", "text": "file list"}],
                        "isError": False,
                    }
                ],
            },
        },
    },
    {"type": "turn/end", "seq": 7, "time": _DSH_MS, "data": {"turn": 1, "stopReason": "end_turn"}},
]


def _dsh_text() -> str:
    return "\n".join(json.dumps(r, ensure_ascii=False) for r in _DSH_RECORDS)


def test_parse_dsh_maps_records() -> None:
    parsed = parse_dsh_text(_dsh_text())

    assert parsed.session_id == "session-x"
    assert [e.event_type for e in parsed.events] == [
        "user_message",
        "assistant_message",
        "tool_call",
        "tool_result",
    ]
    # 流式增量与 Reasoning 草稿都不入库
    assert all("流式增量" not in e.content for e in parsed.events)
    assert all("草稿" not in e.content for e in parsed.events)
    # 同一个 call 既在 assistant/message 的 tool-call 块里、又是独立 tool/call 记录 —— 只留一条
    assert [e.content for e in parsed.events if e.event_type == "tool_call"] == [
        'bash {"command": "ls"}'
    ]
    assert parsed.events[3].content == "file list"
    assert parsed.events[3].payload["is_error"] is False
    # plugin / skill-catalog / agent-instructions 注入是管道，不是用户说的话
    assert parsed.skipped_own_results == 1


def test_import_content_dsh_uses_terminal_prefix(agent_memory: Memory) -> None:
    stats = import_content(agent_memory, _dsh_text(), host="dsh", parser="dsh")

    assert stats.session_id == "dsh:session-x"
    assert stats.imported == 4
    assert stats.by_type == {
        "user_message": 1,
        "assistant_message": 1,
        "tool_call": 1,
        "tool_result": 1,
    }


def test_echo_rule_differs_by_role() -> None:
    """回声判定按角色区分：助手侧看是否以标记开头，用户侧看标记是否出现。"""
    from octop.infra.agents.claude_transcript import _is_echo

    markers = ("[octop memory search]", "[octop memory capture]")
    # 助手侧：只是引用标记的回答必须保留
    assert not _is_echo(
        "靠两个 hook：召回把 [octop memory search] 块注入上下文", "assistant_message", markers
    )
    assert _is_echo("[octop memory search] related memories…", "assistant_message", markers)
    # 用户侧：出现标记就是我们注入的上下文（CC 会加 "Stop hook feedback:" 前缀）
    assert _is_echo(
        "Stop hook feedback:\n[octop memory search] 请记录要点", "user_message", markers
    )
    assert not _is_echo("正常提问", "user_message", markers)


def test_a_reply_that_quotes_our_marker_survives(agent_memory: Memory) -> None:
    """模型回答只是**引用**召回标记时必须入库——否则解释接入方式的对话会被当回声丢掉。"""
    records = [
        _record(type="user", uuid="u1", message={"role": "user", "content": "记忆接入怎么做的？"}),
        _record(
            type="assistant",
            uuid="a1",
            message={
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": "靠两个 hook：召回会把 [octop memory search] 块注入上下文。",
                    }
                ],
            },
        ),
    ]
    text = "\n".join(json.dumps(record, ensure_ascii=False) for record in records)

    stats = import_content(agent_memory, text, skip_markers=("[octop memory search]",))

    assert stats.skipped_echo == 0
    assert stats.imported == 2
    stored = agent_memory.list_raw(session_id=stats.session_id, limit=10)
    assert any("[octop memory search]" in raw.content for raw in stored)


def test_codex_rollout_maps_to_events() -> None:
    """Codex rollout：event_msg 带对话，response_item 带工具与（重复的）消息副本。"""
    from octop.infra.agents.claude_transcript import parse_codex_text

    records = [
        {
            "timestamp": "2026-08-08T13:47:31.000Z",
            "type": "session_meta",
            "payload": {"id": "s-1", "cwd": "/tmp", "cli_version": "0.142.5"},
        },
        {
            "timestamp": "2026-08-08T13:47:31.163Z",
            "type": "event_msg",
            "payload": {"type": "user_message", "message": "现在是什么模型\n"},
        },
        {
            "timestamp": "2026-08-08T13:47:32.000Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "developer",
                "content": [{"type": "input_text", "text": "<permissions instructions>"}],
            },
        },
        {
            "timestamp": "2026-08-08T13:47:33.000Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "id": "a1",
                "content": [{"type": "output_text", "text": "我是 Codex。"}],
            },
        },
        {
            "timestamp": "2026-08-08T13:47:34.000Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "id": "t1",
                "name": "shell",
                "arguments": '{"command":"ls"}',
            },
        },
        {
            "timestamp": "2026-08-08T13:47:35.000Z",
            "type": "response_item",
            "payload": {"type": "function_call_output", "id": "t2", "output": "a.txt"},
        },
        {
            "timestamp": "2026-08-08T13:47:36.000Z",
            "type": "turn_context",
            "payload": {"cwd": "/tmp", "model": "x"},
        },
    ]
    text = "\n".join(json.dumps(record, ensure_ascii=False) for record in records)

    parsed = parse_codex_text(text)

    assert [event.event_type for event in parsed.events] == [
        "user_message",
        "assistant_message",
        "tool_call",
        "tool_result",
    ]
    assert parsed.events[0].content == "现在是什么模型\n"
    assert parsed.events[1].content == "我是 Codex。"
    assert parsed.events[2].content.startswith("shell ")
    assert parsed.events[3].content == "a.txt"
    assert parsed.skipped_own_results == 1  # developer instructions 是宿主管线


def test_codex_does_not_store_the_same_turn_twice() -> None:
    """event_msg 与 response_item 会带同一段文本：只入库一次。"""
    from octop.infra.agents.claude_transcript import parse_codex_text

    records = [
        {
            "timestamp": "2026-08-08T13:47:31.163Z",
            "type": "event_msg",
            "payload": {"type": "user_message", "message": "同一个问题"},
        },
        {
            "timestamp": "2026-08-08T13:47:31.900Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "id": "u9",
                "content": [{"type": "input_text", "text": "同一个问题"}],
            },
        },
    ]
    text = "\n".join(json.dumps(record, ensure_ascii=False) for record in records)

    parsed = parse_codex_text(text)

    assert [event.content for event in parsed.events] == ["同一个问题"]
    assert parsed.skipped_own_results == 1


def test_cursor_transcript_shapes_are_tolerated() -> None:
    """Cursor 的 transcript_path 格式未公开：JSONL / 数组 / {messages:[]} 都要能读。"""
    from octop.infra.agents.claude_transcript import parse_cursor_text

    pairs = [("user", "怎么接入？"), ("assistant", "两条 hook 就够了。")]
    shapes = [
        "\n".join(json.dumps({"role": r, "content": c}, ensure_ascii=False) for r, c in pairs),
        json.dumps([{"role": r, "text": c} for r, c in pairs], ensure_ascii=False),
        json.dumps(
            {"messages": [{"role": r, "content": [{"type": "text", "text": c}]} for r, c in pairs]},
            ensure_ascii=False,
        ),
    ]

    for text in shapes:
        parsed = parse_cursor_text(text)
        assert [event.event_type for event in parsed.events] == [
            "user_message",
            "assistant_message",
        ], text[:60]
        assert parsed.events[0].content == "怎么接入？"


def test_cursor_agent_transcript_jsonl_keeps_text_and_drops_tool_blocks() -> None:
    """stop 交给的真实文件：一行一个 {role, message:{content:[{type,text}]}}。"""
    from octop.infra.agents.claude_transcript import parse_cursor_text

    lines = [
        {
            "role": "user",
            "message": {"content": [{"type": "text", "text": "怎么接入？"}]},
        },
        {
            "role": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "两条 hook 就够了。"},
                    {"type": "tool_use", "name": "read", "input": {"path": "a"}},
                ]
            },
        },
    ]
    text = "\n".join(json.dumps(line, ensure_ascii=False) for line in lines)

    parsed = parse_cursor_text(text)

    assert [event.event_type for event in parsed.events] == [
        "user_message",
        "assistant_message",
    ]
    assert parsed.events[0].content == "怎么接入？"
    assert parsed.events[1].content == "两条 hook 就够了。"


def test_cursor_skips_entries_without_a_conversational_role() -> None:
    from octop.infra.agents.claude_transcript import parse_cursor_text

    text = json.dumps(
        [
            {"role": "user", "content": "问题"},
            {"kind": "toolCall", "tool": "read", "args": {"path": "a"}},
            {"role": "assistant", "content": "回答"},
        ],
        ensure_ascii=False,
    )

    parsed = parse_cursor_text(text)

    assert [event.event_type for event in parsed.events] == ["user_message", "assistant_message"]
    assert parsed.skipped_own_results == 1


def test_cursor_delta_uploads_do_not_collide_on_line_index_src_key() -> None:
    """stop hook ships byte deltas; each chunk used to renumber from line0.

    Distinct user turns at the head of consecutive deltas must get distinct
    ``src_key`` values, otherwise the later user message is dropped as
    ``skipped_existing`` while later assistant lines still import.
    """
    from octop.infra.agents.claude_transcript import parse_cursor_text

    def _line(role: str, text: str) -> str:
        return json.dumps(
            {"role": role, "message": {"content": [{"type": "text", "text": text}]}},
            ensure_ascii=False,
        )

    delta_a = "\n".join(
        [
            _line("user", "上一轮用户问题"),
            _line("assistant", "上一轮助手回答"),
        ]
    )
    delta_b = "\n".join(
        [
            _line("user", "原始素材只有回复，没有用户消息"),
            _line("assistant", "这是助手的长回复，超过十二个字符。"),
        ]
    )

    keys_a = {event.payload["src_key"] for event in parse_cursor_text(delta_a).events}
    parsed_b = parse_cursor_text(delta_b)
    keys_b = [event.payload["src_key"] for event in parsed_b.events]

    assert parsed_b.events[0].event_type == "user_message"
    assert parsed_b.events[0].content == "原始素材只有回复，没有用户消息"
    assert keys_b[0] not in keys_a
    assert keys_b[0].startswith("c") and keys_b[0].endswith(":0")
    # Re-parsing the same delta stays idempotent.
    assert parse_cursor_text(delta_b).events[0].payload["src_key"] == keys_b[0]


def test_cursor_prefers_explicit_record_id_for_src_key() -> None:
    from octop.infra.agents.claude_transcript import parse_cursor_text

    text = json.dumps(
        {"id": "msg_abc", "role": "user", "content": "有稳定 id"},
        ensure_ascii=False,
    )
    parsed = parse_cursor_text(text)
    assert parsed.events[0].payload["src_key"] == "msg_abc:0"
