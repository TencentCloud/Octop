"""Internal HTTP MCP endpoints must not serve a connector instance that is turned off.

``POST`` rejects a non-``active`` instance (added in 6f7815bb); ``GET`` and
``DELETE`` in the same router did not follow, so a disabled connector keeps
answering its tokenised internal MCP URL.
"""

from __future__ import annotations

import httpx

from octop.api.routers.internal_mcp import _service


async def _qcc_instance(env: tuple[httpx.AsyncClient, object, dict[str, str]]) -> tuple[str, str]:
    """Create a qcc instance and return ``(instance_id, internal_token)``."""
    client, srv, auth = env
    created = await client.post(
        "/api/connector-instances",
        headers=auth,
        json={"kind": "qcc", "display_name": "QCC", "credentials": {"api_key": "synthetic"}},
    )
    assert created.status_code == 201
    instance_id = created.json()["instance_id"]
    token = str(_service(srv).decrypt(instance_id)["internal_token"])
    return instance_id, token


async def _disable(env: tuple[httpx.AsyncClient, object, dict[str, str]], instance_id: str) -> None:
    client, _, auth = env
    patched = await client.patch(
        f"/api/connector-instances/{instance_id}",
        headers=auth,
        json={"status": "disabled"},
    )
    assert patched.status_code == 200


async def test_post_rejects_disabled_instance(env) -> None:
    """Already guarded — pinned so the three verbs cannot drift apart again."""
    client, srv, _ = env
    instance_id, token = await _qcc_instance(env)
    await _disable(env, instance_id)
    resp = await client.post(
        f"/api/internal/mcp/qcc/{instance_id}",
        params={"token": token},
        json={"id": 1, "method": "tools/list"},
    )
    assert resp.status_code == 404
    assert srv.services.repos.connector_repo.get(instance_id).status == "disabled"


async def test_get_rejects_disabled_instance(env) -> None:
    client, _, _ = env
    instance_id, token = await _qcc_instance(env)
    # Control: while active, GET reaches the session check (405 without a session id).
    active = await client.get(
        f"/api/internal/mcp/qcc/{instance_id}",
        params={"token": token},
    )
    assert active.status_code == 405
    await _disable(env, instance_id)
    resp = await client.get(
        f"/api/internal/mcp/qcc/{instance_id}",
        params={"token": token},
    )
    assert resp.status_code == 404


async def test_delete_rejects_disabled_instance(env) -> None:
    client, _, _ = env
    instance_id, token = await _qcc_instance(env)
    active = await client.delete(
        f"/api/internal/mcp/qcc/{instance_id}",
        params={"token": token},
    )
    assert active.status_code == 204
    await _disable(env, instance_id)
    resp = await client.delete(
        f"/api/internal/mcp/qcc/{instance_id}",
        params={"token": token},
    )
    assert resp.status_code == 404
