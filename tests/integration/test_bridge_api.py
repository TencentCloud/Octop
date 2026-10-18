"""Integration smoke for Bridge connection management API."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from octop.infra.errors import ErrorCode, OctopError


async def test_bridge_list_empty(env: Any) -> None:
    client, _srv, auth = env
    r = await client.get("/api/bridge/connections", headers=auth)
    assert r.status_code == 200
    assert r.json() == []


async def test_bridge_probe_returns_expert_list(env: Any) -> None:
    client, _srv, auth = env
    peer_agents = [
        {
            "agent_id": "01REMOTE",
            "id": 3,
            "name": "Remote Expert",
            "description": "Cloud helper",
            "icon_url": "/experts/avatars/scene-healthcare.svg",
            "color": "#112233",
            "state": "idle",
            "kind": "expert",
        }
    ]
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = peer_agents
    fake_resp.text = "[]"

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=fake_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "octop.infra.bridge.manager.login_peer",
            new=AsyncMock(
                return_value={
                    "access_token": "peer-token",
                    "user": {"username": "peer", "display_name": "Peer User"},
                }
            ),
        ),
        patch("octop.infra.bridge.manager.httpx.AsyncClient", return_value=mock_client),
    ):
        r = await client.post(
            "/api/bridge/probe",
            headers=auth,
            json={
                "peer_base_url": "https://demo.octop.chat",
                "peer_username": "peer",
                "password": "secret",
            },
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["peer_display_name"] == "Peer User"
    assert body["agent_count"] == 1
    assert body["agents"][0]["agent_id"] == "01REMOTE"
    assert body["agents"][0]["name"] == "Remote Expert"
    assert body["agents"][0]["description"] == "Cloud helper"
    assert body["agents"][0]["icon_url"] == "/experts/avatars/scene-healthcare.svg"

    # Probe must not create a persisted connection.
    listed = await client.get("/api/bridge/connections", headers=auth)
    assert listed.json() == []


async def test_bridge_probe_validation(env: Any) -> None:
    client, _srv, auth = env
    r = await client.post(
        "/api/bridge/probe",
        headers=auth,
        json={"peer_base_url": "https://demo.octop.chat", "peer_username": "", "password": "x"},
    )
    assert r.status_code == 422


async def test_bridge_probe_auth_failure_returns_400_not_401(env: Any) -> None:
    """Peer credentials rejection returns 400 Bad Request, preserving the local session."""
    client, _srv, auth = env

    with patch(
        "octop.infra.bridge.manager.login_peer",
        new=AsyncMock(
            side_effect=OctopError(ErrorCode.BRIDGE_AUTH_FAILED, "peer rejected credentials")
        ),
    ):
        r = await client.post(
            "/api/bridge/probe",
            headers=auth,
            json={
                "peer_base_url": "https://demo.octop.chat",
                "peer_username": "peer",
                "password": "wrong-password",
            },
        )
    # Must be 400 Bad Request, NOT 401 Unauthorized (which would evict the local user's session).
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["error"]["code"] == "BRIDGE_AUTH_FAILED"

    # Verify local session authentication remains fully intact.
    listed = await client.get("/api/bridge/connections", headers=auth)
    assert listed.status_code == 200

