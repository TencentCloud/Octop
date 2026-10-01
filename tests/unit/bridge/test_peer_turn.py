"""Peer turn.start should keep dashboard composer fields."""

from __future__ import annotations

from octop.infra.bridge.manager import _bridge_turn_ws_payload


def test_bridge_turn_ws_payload_keeps_composer_fields() -> None:
    out = _bridge_turn_ws_payload(
        {
            "type": "turn.start",
            "request_id": "r1",
            "agent_id": "main",
            "text": "hi",
            "thread_id": "thr_1",
            "knowledge_base_ids": ["kb1"],
            "hitl_policy": {"mode": "allow_all"},
            "conversation_mode": "ask",
            "reasoning_mode": "enabled",
            "target_agent_ids": ["doctor"],
            "mcp_servers": ["gmail"],
            "skills": ["notes"],
        }
    )
    assert out["type"] == "user_turn"
    assert out["text"] == "hi"
    assert out["thread_id"] == "thr_1"
    assert out["knowledge_base_ids"] == ["kb1"]
    assert out["hitl_policy"] == {"mode": "allow_all"}
    assert out["conversation_mode"] == "ask"
    assert out["reasoning_mode"] == "enabled"
    assert out["target_agent_ids"] == ["doctor"]
    assert out["mcp_servers"] == ["gmail"]
    assert out["skills"] == ["notes"]
    assert "request_id" not in out
    assert "agent_id" not in out


def test_bridge_turn_ws_payload_defaults_empty_text() -> None:
    out = _bridge_turn_ws_payload({"messages": [{"role": "user", "content": "x"}]})
    assert out["type"] == "user_turn"
    assert out["text"] == ""
    assert out["messages"][0]["content"] == "x"
