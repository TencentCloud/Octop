"""The raw-session markdown archive: L0 keeps messages, the archive keeps everything."""

from __future__ import annotations

import json

from octop.infra.agents.memory_session_archive import (
    _MAX_BODY_CHARS,
    append_session,
    archive_path,
)


def _jsonl(records: list[dict]) -> str:
    return "\n".join(json.dumps(record, ensure_ascii=False) for record in records)


def _user(uuid: str, text: str = "跑一下测试", session: str = "s1") -> dict:
    return {
        "type": "user",
        "uuid": uuid,
        "sessionId": session,
        "timestamp": "2026-09-29T02:00:00Z",
        "message": {"role": "user", "content": text},
    }


def _assistant(uuid: str, blocks: list[dict], session: str = "s1") -> dict:
    return {
        "type": "assistant",
        "uuid": uuid,
        "sessionId": session,
        "timestamp": "2026-09-29T02:00:05Z",
        "message": {"role": "assistant", "content": blocks},
    }


def test_archive_renders_every_block_not_just_messages(tmp_path):
    """L0 会丢 thinking / tool 事件，归档必须都留着。"""
    text = _jsonl(
        [
            _user("u1"),
            _assistant(
                "a1",
                [
                    {"type": "thinking", "thinking": "先想一下"},
                    {"type": "text", "text": "我跑一下"},
                    {
                        "type": "tool_use",
                        "id": "t1",
                        "name": "Bash",
                        "input": {"command": "pytest -q"},
                    },
                    {
                        "type": "tool_result",
                        "tool_use_id": "t1",
                        "content": "1 failed",
                    },
                ],
            ),
        ]
    )

    path = append_session(
        tmp_path, session_id="cc:s1", text=text, host="claude-code", user="alice"
    )

    assert path == archive_path(tmp_path, "cc:s1")
    assert path.name == "cc_s1.md"  # 文件名净化
    body = path.read_text(encoding="utf-8")
    assert "# claude-code session cc:s1" in body
    assert "- user: alice" in body
    assert "跑一下测试" in body
    assert "*（thinking）*" in body and "先想一下" in body
    assert "**tool_call · Bash**" in body and '"command": "pytest -q"' in body
    assert "**tool_result" in body and "1 failed" in body
    assert body.count("<!-- key: ") == 2


def test_archive_appends_deltas_and_dedups_resends(tmp_path):
    """客户端按增量上传：新记录追加，offset 丢失后的整份重发不重复。"""
    session = "cc:s2"
    first = _jsonl([_user("u1", session=session)])
    second = _jsonl(
        [
            _user("u1", session=session),
            _assistant("a1", [{"type": "text", "text": "好"}], session=session),
        ]
    )

    append_session(tmp_path, session_id=session, text=first, host="claude-code")
    assert append_session(tmp_path, session_id=session, text=second, host="claude-code") is not None
    after_delta = (tmp_path / "cc_s2.md").read_text(encoding="utf-8")

    # 重发整份：没有新记录 -> 不写、返回 None，文件不变
    assert append_session(tmp_path, session_id=session, text=second, host="claude-code") is None
    assert (tmp_path / "cc_s2.md").read_text(encoding="utf-8") == after_delta

    assert after_delta.count("<!-- key: u1 -->") == 1
    assert after_delta.count("<!-- key: a1 -->") == 1
    assert after_delta.count("# claude-code session cc:s2") == 1  # 头只写一次


def test_archive_keeps_long_tool_output_beyond_the_l0_cap(tmp_path):
    """归档给人看：单条上限比 L0 的 4000 宽松得多。"""
    body_text = "line\n" * 2000  # ~10KB，超过 L0 的 4000
    text = _jsonl(
        [
            _user("u1"),
            _assistant(
                "a1",
                [{"type": "tool_result", "tool_use_id": "t1", "content": body_text}],
            ),
        ]
    )

    path = append_session(tmp_path, session_id="cc:s3", text=text, host="claude-code")
    body = path.read_text(encoding="utf-8")

    assert body.count("line") >= 1500  # 远多于 4000 字符
    assert len(body) <= _MAX_BODY_CHARS * 2  # 仍然有界


def test_archive_skips_non_records_and_keeps_thinking_optional(tmp_path):
    """非 user/assistant 记录（mode / cost-state / attachment）不进归档。"""
    text = _jsonl(
        [
            {"type": "mode", "mode": "acceptEdits"},
            _user("u1", text="问了"),
            {"type": "cost-state", "total": 1},
        ]
    )

    path = append_session(tmp_path, session_id="cc:s4", text=text, host="claude-code")
    body = path.read_text(encoding="utf-8")

    assert "问了" in body
    assert "acceptEdits" not in body
    assert body.count("<!-- key: ") == 1
