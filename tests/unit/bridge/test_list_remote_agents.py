"""BridgeManager.list_remote_agents rewrites team member ids onto shadows."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.infra.bridge.manager import BridgeManager
from octop.infra.db.repos.bridge_connections import BridgeConnectionRow


def _row(**overrides: Any) -> BridgeConnectionRow:
    base = {
        "pk": 1,
        "connection_id": "cid1",
        "owner_user_id": 1,
        "peer_base_url": "https://peer.example",
        "peer_username": "alice",
        "display_name": "云端",
        "notes": None,
        "icon_name": None,
        "credential_blob": b"enc-pass",
        "access_token_blob": b"enc-token",
        "token_expires_at": None,
        "status": "connected",
        "last_error": None,
        "last_seen_at": None,
        "auto_reconnect": True,
        "created_at": 1,
        "updated_at": 1,
    }
    base.update(overrides)
    return BridgeConnectionRow(**base)  # type: ignore[arg-type]


def _mgr() -> BridgeManager:
    return BridgeManager(
        bridge_repo=MagicMock(),
        secret_repo=MagicMock(),
        user_repo=MagicMock(),
        advertise_base_url="http://local.test",
    )


@pytest.mark.asyncio
async def test_list_remote_agents_rewrites_team_member_ids() -> None:
    mgr = _mgr()
    mgr.get_owned = MagicMock(return_value=_row())  # type: ignore[method-assign]

    class Resp:
        status_code = 200
        text = ""

        def json(self) -> list[dict[str, Any]]:
            return [
                {
                    "agent_id": "host",
                    "name": "主持团队",
                    "kind": "team",
                    "member_ids": ["doctor", "nurse", "doctor"],
                    "icon_url": "/experts/avatars/team-host.svg",
                },
                {
                    "agent_id": "doctor",
                    "name": "临床辅助",
                    "kind": "expert",
                    "icon_url": "/api/agents/doctor/avatar",
                },
            ]

    mgr.tunnel_http = AsyncMock(return_value=Resp())  # type: ignore[method-assign]
    out = await mgr.list_remote_agents("cid1", owner_user_id=1)
    team = next(item for item in out if item["remote_agent_id"] == "host")
    doctor = next(item for item in out if item["remote_agent_id"] == "doctor")
    assert team["agent_id"] == "bridge:cid1:host"
    assert team["is_owner"] is True
    assert team["member_ids"] == ["bridge:cid1:doctor", "bridge:cid1:nurse"]
    assert doctor["agent_id"] == "bridge:cid1:doctor"
    assert doctor["icon_url"] == "/api/agents/bridge:cid1:doctor/avatar"


@pytest.mark.asyncio
async def test_list_remote_agents_keeps_peer_ownership() -> None:
    mgr = _mgr()
    mgr.get_owned = MagicMock(return_value=_row())  # type: ignore[method-assign]

    class Resp:
        status_code = 200
        text = ""

        def json(self) -> list[dict[str, Any]]:
            return [
                {
                    "agent_id": "mine",
                    "name": "我的",
                    "is_owner": True,
                    "is_shared": False,
                },
                {
                    "agent_id": "shared",
                    "name": "别人共享",
                    "is_owner": False,
                    "is_shared": True,
                },
            ]

    mgr.tunnel_http = AsyncMock(return_value=Resp())  # type: ignore[method-assign]
    out = await mgr.list_remote_agents("cid1", owner_user_id=1)
    by_remote = {item["remote_agent_id"]: item for item in out}
    assert by_remote["mine"]["is_owner"] is True
    assert by_remote["mine"]["is_shared"] is False
    assert by_remote["shared"]["is_owner"] is False
    assert by_remote["shared"]["is_shared"] is True
