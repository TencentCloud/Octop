"""HTTP ACL for knowledge-base instance settings vs page CRUD."""

from __future__ import annotations

import asyncio
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


async def _wait_for_status(client: Any, auth: Any, kb_id: str, doc_id: str, want: str) -> None:
    for _ in range(100):
        rows = (await client.get(f"/api/knowledge-bases/{kb_id}/documents", headers=auth)).json()
        if any(row["document_id"] == doc_id and row["status"] == want for row in rows):
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"{doc_id} never reached {want}: {rows}")


async def test_move_document_into_another_knowledge_base(
    env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from octop.api.routers import knowledge_bases as router
    from octop.infra.knowledge import jobs, service

    for module in (router, service, jobs):
        monkeypatch.setattr(module, "assert_knowledge_usable", lambda *_args: None)
    monkeypatch.setattr(
        jobs, "embed_knowledge_texts", lambda _services, texts: [[1.0, 0.0] for _ in texts]
    )
    client, _server, admin_auth = env
    source = (
        await client.post("/api/knowledge-bases", headers=admin_auth, json={"name": "产品资料库"})
    ).json()
    target = (
        await client.post("/api/knowledge-bases", headers=admin_auth, json={"name": "客服话术"})
    ).json()
    folder = await client.post(
        f"/api/knowledge-bases/{target['id']}/folders", headers=admin_auth, json={"path": "售后"}
    )
    assert folder.status_code in (200, 201), folder.text
    created = await client.post(
        f"/api/knowledge-bases/{source['id']}/documents/text",
        headers=admin_auth,
        json={"name": "退款流程", "format": "md", "content": "七天内可以无理由退款。"},
    )
    assert created.status_code == 201, created.text
    doc_id = created.json()["document_id"]
    await _wait_for_status(client, admin_auth, source["id"], doc_id, "ready")

    moved = await client.post(
        f"/api/knowledge-bases/{source['id']}/documents/{doc_id}/move",
        headers=admin_auth,
        json={"target_folder": "售后", "target_kb_id": target["id"]},
    )

    assert moved.status_code == 200, moved.text
    assert (moved.json()["kb_id"], moved.json()["path"]) == (target["id"], "售后/退款流程.md")
    assert moved.json()["status"] == "ready"
    left = await client.get(f"/api/knowledge-bases/{source['id']}/documents", headers=admin_auth)
    assert left.json() == []
    chunks = await client.get(
        f"/api/knowledge-bases/{target['id']}/documents/{doc_id}/chunks", headers=admin_auth
    )
    assert chunks.status_code == 200, chunks.text
    assert "七天内可以无理由退款" in str(chunks.json())
    original = await client.get(
        f"/api/knowledge-bases/{target['id']}/documents/{doc_id}/file", headers=admin_auth
    )
    assert original.status_code == 200, original.text
    assert "七天内可以无理由退款" in original.content.decode("utf-8")
    bases = {
        row["id"]: row["doc_count"]
        for row in (await client.get("/api/knowledge-bases", headers=admin_auth)).json()
    }
    assert (bases[source["id"]], bases[target["id"]]) == (0, 1)
