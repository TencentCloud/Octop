"""HTTP ACL for knowledge-base instance settings vs page CRUD."""

from __future__ import annotations

from typing import Any

import pytest

from tests.support.auth import create_user


@pytest.fixture
def usable_knowledge(monkeypatch: pytest.MonkeyPatch) -> None:
    # Keep real HTTP/auth/SQLite behavior; only bypass external embedding setup.
    monkeypatch.setattr("octop.api.routers.knowledge_bases._require_usable", lambda *_: None)
    monkeypatch.setattr("octop.infra.knowledge.service.assert_knowledge_usable", lambda *_: None)


@pytest.mark.parametrize(
    ("permissions", "expected"),
    [
        (["knowledge_bases"], 403),
        (["knowledge_bases:create"], 403),
        (["knowledge_bases", "knowledge_bases:create"], 201),
    ],
)
async def test_create_requires_both_knowledge_permissions(
    env: Any, usable_knowledge: None, permissions: list[str], expected: int
) -> None:
    client, server, admin_auth = env
    auth = await create_user(client, admin_auth, username="kb_creator", permissions=permissions)
    response = await client.post("/api/knowledge-bases", headers=auth, json={"name": "Docs"})
    assert response.status_code == expected, response.text
    bases = server.services.knowledge_repo.list_all()
    assert len(bases) == (1 if expected == 201 else 0)


async def test_revoked_creator_keeps_shared_reads_and_existing_owner_edits(
    env: Any, usable_knowledge: None
) -> None:
    client, server, admin_auth = env
    auth = await create_user(client, admin_auth, username="kb_reader")
    owned = await client.post("/api/knowledge-bases", headers=auth, json={"name": "Owned"})
    assert owned.status_code == 201, owned.text
    shared = await client.post(
        "/api/knowledge-bases", headers=admin_auth, json={"name": "Shared", "shared": True}
    )
    assert shared.status_code == 201, shared.text
    await server.user_manager.set_permissions("kb_reader", ["knowledge_bases"])

    denied = await client.post("/api/knowledge-bases", headers=auth, json={"name": "Blocked"})
    assert denied.status_code == 403, denied.text
    assert denied.json()["error"]["details"]["permission"] == "knowledge_bases:create"
    listing = await client.get("/api/knowledge-bases", headers=auth)
    assert listing.status_code == 200, listing.text
    assert {row["name"] for row in listing.json()} == {"Owned", "Shared"}
    shared_id = shared.json()["id"]
    for path in (f"/{shared_id}", f"/{shared_id}/documents"):
        response = await client.get(f"/api/knowledge-bases{path}", headers=auth)
        assert response.status_code == 200, response.text
    forbidden = await client.patch(
        f"/api/knowledge-bases/{shared_id}", headers=auth, json={"name": "Stolen"}
    )
    assert forbidden.status_code == 403, forbidden.text
    edited = await client.patch(
        f"/api/knowledge-bases/{owned.json()['id']}", headers=auth, json={"name": "Updated"}
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["name"] == "Updated"


async def test_feature_toggle_requires_knowledge_settings(env: Any) -> None:
    client, _server, admin_auth = env
    page_auth = await create_user(client, admin_auth, username="kb_page_user")
    denied = await client.put(
        "/api/knowledge-bases/feature",
        headers=page_auth,
        json={"enabled": False},
    )
    assert denied.status_code == 403, denied.text
    assert denied.json()["error"]["code"] == "FORBIDDEN"

    settings_auth = await create_user(
        client,
        admin_auth,
        username="kb_settings_user",
        permissions=["knowledge_bases", "knowledge_settings"],
    )
    allowed = await client.put(
        "/api/knowledge-bases/feature",
        headers=settings_auth,
        json={"enabled": False},
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["feature_enabled"] is False


async def test_embedding_options_require_knowledge_settings(env: Any) -> None:
    client, _server, admin_auth = env
    page_auth = await create_user(client, admin_auth, username="kb_options_user")
    denied = await client.get("/api/knowledge-bases/embedding-options", headers=page_auth)
    assert denied.status_code == 403, denied.text

    settings_auth = await create_user(
        client,
        admin_auth,
        username="kb_options_admin",
        permissions=["knowledge_settings"],
    )
    allowed = await client.get("/api/knowledge-bases/embedding-options", headers=settings_auth)
    assert allowed.status_code == 200, allowed.text
    assert "onnx" in allowed.json()
