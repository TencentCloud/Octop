"""Integration tests for admin-targeting and last-admin invariants (#1877).

Covers the repro matrix from the issue:
- a non-admin holding the ``users`` permission cannot delete / disable /
  demote an administrator (HTTP API and batch endpoint);
- the deployment can never be left with zero enabled administrators (the
  sole-admin self-disable case from #1256, enforced in the domain layer so
  the CLI path is covered too).

Also includes positive cases to prove legitimate operations are not broken:
- with two admins, one admin can disable / delete the other;
- a non-admin with ``users`` can still manage regular users.
"""

from __future__ import annotations

import pytest

from tests.support.auth import create_user, resolve_user_id


@pytest.mark.anyio
async def test_non_admin_with_users_permission_cannot_delete_admin(env):
    client, _server, admin_auth = env
    bob_auth = await create_user(
        client, admin_auth, username="bob", role="user", permissions=["users"]
    )
    admin_id = await resolve_user_id(client, admin_auth, "admin")

    r = await client.delete(f"/api/users/{admin_id}", headers=bob_auth)

    assert r.status_code == 403
    assert (await client.get(f"/api/users/{admin_id}", headers=admin_auth)).status_code == 200


@pytest.mark.anyio
async def test_non_admin_with_users_permission_cannot_disable_admin(env):
    client, _server, admin_auth = env
    bob_auth = await create_user(
        client, admin_auth, username="bob", role="user", permissions=["users"]
    )
    admin_id = await resolve_user_id(client, admin_auth, "admin")

    r = await client.patch(f"/api/users/{admin_id}", headers=bob_auth, json={"disabled": True})

    assert r.status_code == 403
    row = (await client.get(f"/api/users/{admin_id}", headers=admin_auth)).json()
    assert row["disabled"] is False


@pytest.mark.anyio
async def test_non_admin_with_users_permission_cannot_demote_admin(env):
    client, _server, admin_auth = env
    bob_auth = await create_user(
        client, admin_auth, username="bob", role="user", permissions=["users"]
    )
    admin_id = await resolve_user_id(client, admin_auth, "admin")

    r = await client.patch(f"/api/users/{admin_id}", headers=bob_auth, json={"role": "user"})

    assert r.status_code == 403
    row = (await client.get(f"/api/users/{admin_id}", headers=admin_auth)).json()
    assert row["role"] == "admin"


@pytest.mark.anyio
async def test_non_admin_batch_cannot_disable_or_delete_admin(env):
    client, _server, admin_auth = env
    bob_auth = await create_user(
        client, admin_auth, username="bob", role="user", permissions=["users"]
    )
    admin_id = await resolve_user_id(client, admin_auth, "admin")

    for action in ("disable", "delete"):
        r = await client.post(
            "/api/users/batch",
            headers=bob_auth,
            json={"action": action, "user_ids": [admin_id]},
        )
        assert r.status_code == 200
        results = r.json()["results"]
        assert len(results) == 1
        assert results[0]["ok"] is False
        assert results[0]["code"] == "FORBIDDEN"

    row = (await client.get(f"/api/users/{admin_id}", headers=admin_auth)).json()
    assert row["disabled"] is False


@pytest.mark.anyio
async def test_last_admin_cannot_disable_self(env):
    """Sole-admin self-disable (#1256) must be rejected by the domain invariant."""
    client, _server, admin_auth = env
    admin_id = await resolve_user_id(client, admin_auth, "admin")

    r = await client.patch(f"/api/users/{admin_id}", headers=admin_auth, json={"disabled": True})

    assert r.status_code == 403
    row = (await client.get(f"/api/users/{admin_id}", headers=admin_auth)).json()
    assert row["disabled"] is False


@pytest.mark.anyio
async def test_admin_can_disable_another_admin_when_second_exists(env):
    client, _server, admin_auth = env
    await create_user(client, admin_auth, username="admin2", role="admin")
    admin2_id = await resolve_user_id(client, admin_auth, "admin2")

    r = await client.patch(f"/api/users/{admin2_id}", headers=admin_auth, json={"disabled": True})

    assert r.status_code == 200
    row = (await client.get(f"/api/users/{admin2_id}", headers=admin_auth)).json()
    assert row["disabled"] is True


@pytest.mark.anyio
async def test_admin_can_remove_another_admin_when_second_exists(env):
    client, _server, admin_auth = env
    await create_user(client, admin_auth, username="admin2", role="admin")
    admin2_id = await resolve_user_id(client, admin_auth, "admin2")

    r = await client.delete(f"/api/users/{admin2_id}", headers=admin_auth)

    assert r.status_code == 204
    assert (await client.get(f"/api/users/{admin2_id}", headers=admin_auth)).status_code == 404


@pytest.mark.anyio
async def test_non_admin_can_still_manage_regular_users(env):
    client, _server, admin_auth = env
    bob_auth = await create_user(
        client, admin_auth, username="bob", role="user", permissions=["users"]
    )
    await create_user(client, admin_auth, username="carol", role="user")
    carol_id = await resolve_user_id(client, admin_auth, "carol")

    disable = await client.patch(
        f"/api/users/{carol_id}", headers=bob_auth, json={"disabled": True}
    )
    assert disable.status_code == 200

    delete = await client.delete(f"/api/users/{carol_id}", headers=bob_auth)
    assert delete.status_code == 204
