"""Unit tests for bridge agent id helpers."""

from __future__ import annotations

import pytest

from octop.infra.bridge.ids import (
    format_bridge_agent_id,
    is_bridge_agent_id,
    parse_bridge_agent_id,
    restore_peer_path_ids,
    rewrite_peer_agent_id,
    rewrite_peer_agent_ids,
    rewrite_peer_payload_agent_id,
    rewrite_tunneled_json,
)


def test_format_and_parse_roundtrip() -> None:
    agent_id = format_bridge_agent_id("01ABCDEF", "agent-1")
    assert agent_id == "bridge:01ABCDEF:agent-1"
    ref = parse_bridge_agent_id(agent_id)
    assert ref is not None
    assert ref.connection_id == "01ABCDEF"
    assert ref.remote_agent_id == "agent-1"
    assert is_bridge_agent_id(agent_id)


def test_parse_rejects_local_ids() -> None:
    assert parse_bridge_agent_id("01LOCALAGENT") is None
    assert not is_bridge_agent_id("01LOCALAGENT")


def test_format_rejects_colon_in_connection_id() -> None:
    with pytest.raises(ValueError):
        format_bridge_agent_id("bad:id", "agent")


def test_rewrite_peer_agent_ids_maps_roster() -> None:
    assert rewrite_peer_agent_id("CID", "mem-1") == "bridge:CID:mem-1"
    assert rewrite_peer_agent_id("CID", "bridge:CID:mem-1") == "bridge:CID:mem-1"
    assert rewrite_peer_agent_ids("CID", ["a", "a", "", "b"]) == [
        "bridge:CID:a",
        "bridge:CID:b",
    ]


def test_rewrite_peer_payload_agent_id_maps_speaker() -> None:
    frame = {"type": "token", "agent_id": "doctor", "content": "ok"}
    out = rewrite_peer_payload_agent_id("CID", frame)
    assert out["agent_id"] == "bridge:CID:doctor"
    unlabeled = {"type": "token", "content": "host"}
    assert rewrite_peer_payload_agent_id("CID", unlabeled) is unlabeled


def test_rewrite_tunneled_json_keeps_peer_thread_and_session_ids() -> None:
    payload = {
        "thread_id": "01ROOM~doctor",
        "session_key": "doctor:dashboard:1:team:01ROOM",
        "agent_id": "doctor",
        "content": "ask doctor",
        "icon_url": "/api/agents/doctor/avatar",
        "member_ids": ["doctor", "nurse"],
    }
    out = rewrite_tunneled_json(
        payload,
        remote_agent_id="doctor",
        bridge_agent_id="bridge:cid:doctor",
    )
    assert out["thread_id"] == "01ROOM~doctor"
    assert out["session_key"] == "doctor:dashboard:1:team:01ROOM"
    assert out["agent_id"] == "bridge:cid:doctor"
    assert out["content"] == "ask doctor"
    assert out["icon_url"] == "/api/agents/bridge:cid:doctor/avatar"
    assert out["member_ids"] == ["bridge:cid:doctor", "nurse"]


def test_restore_peer_path_ids_unwraps_stale_shadow_thread() -> None:
    rest = "/threads/01ROOM~bridge:cid:doctor/history"
    assert (
        restore_peer_path_ids(
            rest,
            bridge_agent_id="bridge:cid:doctor",
            remote_agent_id="doctor",
        )
        == "/threads/01ROOM~doctor/history"
    )
