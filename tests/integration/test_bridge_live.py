"""Live Bridge smoke against a reachable remote Octop (opt-in).

Run::

    OCTOP_BRIDGE_LIVE=1 \\
    OCTOP_BRIDGE_PEER_URL=https://demo.octop.chat \\
    OCTOP_BRIDGE_PEER_USER=jubaoliang \\
    OCTOP_BRIDGE_PEER_PASSWORD='...' \\
    uv run pytest tests/integration/test_bridge_live.py -m live -vv
"""

from __future__ import annotations

import os
from typing import Any

import pytest

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("OCTOP_BRIDGE_LIVE") != "1",
        reason="set OCTOP_BRIDGE_LIVE=1 to hit a real peer",
    ),
]


def _peer_creds() -> tuple[str, str, str]:
    url = (os.environ.get("OCTOP_BRIDGE_PEER_URL") or "").strip()
    user = (os.environ.get("OCTOP_BRIDGE_PEER_USER") or "").strip()
    password = os.environ.get("OCTOP_BRIDGE_PEER_PASSWORD") or ""
    if not url or not user or not password:
        pytest.skip("OCTOP_BRIDGE_PEER_URL/USER/PASSWORD required")
    return url, user, password


@pytest.mark.asyncio
async def test_bridge_connect_and_list_remote_agents(env: Any) -> None:
    client, srv, auth = env
    peer_url, peer_user, peer_password = _peer_creds()

    assert srv.app_runtime is not None
    assert srv.app_runtime.bridge_manager is not None

    create = await client.post(
        "/api/bridge/connections",
        headers=auth,
        json={
            "peer_base_url": peer_url,
            "peer_username": peer_user,
            "password": peer_password,
            "display_name": "live-demo",
            "connect": True,
        },
    )
    assert create.status_code == 201, create.text
    body = create.json()
    connection_id = body["connection_id"]
    assert body["status"] == "connected", body

    agents = await client.get(
        f"/api/bridge/connections/{connection_id}/agents",
        headers=auth,
    )
    assert agents.status_code == 200, agents.text
    rows = agents.json()
    assert isinstance(rows, list) and len(rows) >= 1, rows
    first = rows[0]
    assert str(first["id"]).startswith(f"bridge:{connection_id}:")
    assert first.get("bridge") is True

    # Tunnel a local-looking history/list call through the bridge proxy.
    remote_path_agent = first["id"]
    threads = await client.get(
        f"/api/agents/{remote_path_agent}/threads",
        headers=auth,
    )
    assert threads.status_code == 200, threads.text
    assert isinstance(threads.json(), list)

    disconnect = await client.post(
        f"/api/bridge/connections/{connection_id}/disconnect",
        headers=auth,
    )
    assert disconnect.status_code == 200, disconnect.text
    assert disconnect.json()["status"] == "disconnected"
