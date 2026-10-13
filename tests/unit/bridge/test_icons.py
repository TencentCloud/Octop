"""Unit tests for Bridge remote icon URL rewriting."""

from __future__ import annotations

from octop.infra.bridge.icons import bridge_avatar_api_path, rewrite_remote_icon_url


def test_keeps_bundled_expert_avatars() -> None:
    assert (
        rewrite_remote_icon_url(
            "/experts/avatars/scene-healthcare.svg",
            remote_agent_id="01REMOTE",
            bridge_agent_id="bridge:CID:01REMOTE",
        )
        == "/experts/avatars/scene-healthcare.svg"
    )


def test_keeps_cdn_absolute_urls() -> None:
    url = "https://cdn.skillhub.cn/icons/nursing.png"
    assert (
        rewrite_remote_icon_url(
            url,
            remote_agent_id="01REMOTE",
            bridge_agent_id="bridge:CID:01REMOTE",
        )
        == url
    )


def test_rewrites_peer_avatar_api_to_bridge_proxy() -> None:
    bridge_id = "bridge:01CID:01REMOTE"
    out = rewrite_remote_icon_url(
        "/api/agents/01REMOTE/avatar",
        remote_agent_id="01REMOTE",
        bridge_agent_id=bridge_id,
    )
    assert out == f"/api/agents/{bridge_id}/avatar"
    assert bridge_avatar_api_path(bridge_id) == out


def test_rewrites_absolute_peer_avatar() -> None:
    bridge_id = "bridge:01CID:01REMOTE"
    out = rewrite_remote_icon_url(
        "https://peer.example/api/agents/01REMOTE/avatar?v=3",
        remote_agent_id="01REMOTE",
        bridge_agent_id=bridge_id,
    )
    assert out == f"/api/agents/{bridge_id}/avatar"


def test_drops_peer_avatar_without_bridge_id() -> None:
    assert (
        rewrite_remote_icon_url(
            "/api/agents/01REMOTE/avatar",
            remote_agent_id="01REMOTE",
        )
        is None
    )


def test_empty_returns_none() -> None:
    assert (
        rewrite_remote_icon_url(
            None,
            remote_agent_id="01REMOTE",
            bridge_agent_id="bridge:CID:01REMOTE",
        )
        is None
    )
