"""``PATCH /api/users/{user_id}`` must apply the assign guard to template defaults.

``_assert_can_assign`` states the delegation rule ("Non-admin actors may only grant
permissions they themselves hold"). ``create_user`` applies it to the list expanded
from a role template before writing, and the same PATCH handler applies it to an
explicit ``permissions`` list — but the role branch wrote the expanded template list
straight to the database when the client omitted ``permissions``.
"""

from __future__ import annotations

from typing import Any

from tests.support.auth import create_user, resolve_user_id

# Permissions a ``users``-only delegate does not hold.
OVERREACH = ["channels", "connectors", "knowledge_bases", "skill_packages"]


async def _make_template(client: Any, admin_auth: dict[str, str], permissions: list[str]) -> str:
    r = await client.post(
        "/api/users/roles",
        headers=admin_auth,
        json={"user_role_name": "helper", "permissions": list(permissions), "policies": []},
    )
    assert r.status_code == 201, r.text
    return str(r.json()["user_role_id"])


async def _make_peer(client: Any, admin_auth: dict[str, str]) -> int:
    await create_user(client, admin_auth, username="peer", permissions=["channels"])
    return await resolve_user_id(client, admin_auth, "peer")


async def test_delegate_cannot_grant_template_permissions_it_lacks(env: Any) -> None:
    c, _srv, admin_auth = env
    role_id = await _make_template(c, admin_auth, OVERREACH)
    clerk_auth = await create_user(c, admin_auth, username="clerk", permissions=["users"])
    peer_id = await _make_peer(c, admin_auth)

    r = await c.patch(f"/api/users/{peer_id}", headers=clerk_auth, json={"role": role_id})

    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "FORBIDDEN"


async def test_refused_role_change_leaves_target_untouched(env: Any) -> None:
    """The guard must run before ``set_role`` so a refused PATCH writes nothing."""
    c, _srv, admin_auth = env
    role_id = await _make_template(c, admin_auth, OVERREACH)
    clerk_auth = await create_user(c, admin_auth, username="clerk", permissions=["users"])
    peer_id = await _make_peer(c, admin_auth)

    r = await c.patch(f"/api/users/{peer_id}", headers=clerk_auth, json={"role": role_id})
    assert r.status_code == 403, r.text

    kept = await c.get(f"/api/users/{peer_id}", headers=admin_auth)
    assert kept.status_code == 200, kept.text
    assert kept.json()["role"] == "user"
    assert kept.json()["permissions"] == ["channels"]


async def test_delegate_can_assign_template_within_its_own_permissions(env: Any) -> None:
    c, _srv, admin_auth = env
    role_id = await _make_template(c, admin_auth, ["channels"])
    clerk_auth = await create_user(
        c, admin_auth, username="clerk", permissions=["users", "channels"]
    )
    peer_id = await _make_peer(c, admin_auth)

    r = await c.patch(f"/api/users/{peer_id}", headers=clerk_auth, json={"role": role_id})

    assert r.status_code == 200, r.text
    assert r.json()["role"] == role_id
    assert r.json()["permissions"] == ["channels"]


async def test_admin_can_assign_the_same_template(env: Any) -> None:
    c, _srv, admin_auth = env
    role_id = await _make_template(c, admin_auth, OVERREACH)
    peer_id = await _make_peer(c, admin_auth)

    r = await c.patch(f"/api/users/{peer_id}", headers=admin_auth, json={"role": role_id})

    assert r.status_code == 200, r.text
    assert sorted(r.json()["permissions"]) == sorted(OVERREACH)
