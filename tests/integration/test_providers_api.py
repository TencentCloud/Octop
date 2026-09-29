"""tests/integration/test_providers_api.py"""

from __future__ import annotations


async def test_list_providers(env):
    """GET /providers returns all providers (read-only endpoint for any user)."""
    c, _, auth = env
    r = await c.post(
        "/api/admin/providers",
        headers=auth,
        json={"name": "openai", "kind": "openai", "api_key": "k"},
    )
    assert r.status_code == 201

    r = await c.get("/api/providers", headers=auth)
    assert r.status_code == 200
    assert any(p["name"] == "openai" for p in r.json())


async def test_admin_creates_provider(env):
    """POST /admin/providers creates a provider."""
    c, _, auth = env
    r = await c.post(
        "/api/admin/providers",
        headers=auth,
        json={"name": "openai", "kind": "openai", "api_key": "k"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "openai"
    assert "user_id" not in body


async def test_regular_user_cannot_create_provider(env):
    """POST /admin/providers is admin-only."""
    c, _, admin_auth = env
    await c.post(
        "/api/users",
        headers=admin_auth,
        json={"username": "regular", "password": "TestPass12", "role": "user"},
    )
    tok = (
        await c.post("/api/auth/login", json={"username": "regular", "password": "TestPass12"})
    ).json()["access_token"]
    user_auth = {"Authorization": f"Bearer {tok}"}

    r = await c.post(
        "/api/admin/providers",
        headers=user_auth,
        json={"name": "should-fail", "kind": "openai"},
    )
    assert r.status_code == 403


async def test_admin_delete_provider(env):
    """DELETE /admin/providers/{id} removes the provider."""
    c, _, auth = env
    r = await c.post(
        "/api/admin/providers",
        headers=auth,
        json={"name": "to-delete", "kind": "openai"},
    )
    assert r.status_code == 201
    pid = r.json()["id"]

    r = await c.delete(f"/api/admin/providers/{pid}", headers=auth)
    assert r.status_code in (200, 204)

    r = await c.get("/api/admin/providers", headers=auth)
    ids = [p["id"] for p in r.json()]
    assert pid not in ids


async def test_admin_cannot_delete_local_runtime_provider(env):
    """DELETE /admin/providers/{id} keeps ONNX / Ollama local rows."""
    c, _, auth = env
    r = await c.post(
        "/api/admin/providers",
        headers=auth,
        json={"name": "ONNX (Local)", "kind": "openai", "api_key": "onnx"},
    )
    assert r.status_code == 201
    pid = r.json()["id"]

    r = await c.delete(f"/api/admin/providers/{pid}", headers=auth)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "PROVIDER_LOCAL_PROTECTED"

    r = await c.get("/api/admin/providers", headers=auth)
    ids = [p["id"] for p in r.json()]
    assert pid in ids


async def _seed_provider(c, auth, *, name: str = "openai", api_key: str = "sk-secret") -> int:
    r = await c.post(
        "/api/admin/providers",
        headers=auth,
        json={"name": name, "kind": "openai", "api_key": api_key},
    )
    assert r.status_code == 201
    return int(r.json()["id"])


async def test_patch_api_key_null_actually_revokes_the_stored_key(env):
    """Revoke used to be a silent no-op that the dashboard reported as success.

    The dashboard sends ``{"api_key": null}``; ``ProviderPatchBody`` typed the
    field ``str | None = None`` and the repo's ``partial_updates`` skipped every
    ``None``, so the row kept its key. This asserts on the stored row rather
    than the response, because SEC-4 masks ``api_key`` in reads and a
    response-level check cannot see the difference.
    """
    c, srv, auth = env
    pid = await _seed_provider(c, auth)
    assert srv.services.provider_repo.get(pid).api_key == "sk-secret"

    r = await c.patch(f"/api/admin/providers/{pid}", headers=auth, json={"api_key": None})

    assert r.status_code == 200
    assert srv.services.provider_repo.get(pid).api_key is None, "revoke did not delete the key"


async def test_patch_without_api_key_leaves_the_stored_key_untouched(env):
    """The regression this fix must not introduce: an unrelated patch wiping keys."""
    c, srv, auth = env
    pid = await _seed_provider(c, auth)

    r = await c.patch(f"/api/admin/providers/{pid}", headers=auth, json={"note": "renamed"})

    assert r.status_code == 200
    row = srv.services.provider_repo.get(pid)
    assert row.api_key == "sk-secret", "an omitted api_key must not clear the stored key"
    assert row.note == "renamed"


async def test_patch_with_empty_body_leaves_the_stored_key_untouched(env):
    c, srv, auth = env
    pid = await _seed_provider(c, auth)

    r = await c.patch(f"/api/admin/providers/{pid}", headers=auth, json={})

    assert r.status_code == 200
    assert srv.services.provider_repo.get(pid).api_key == "sk-secret"


async def test_patch_api_key_with_a_value_replaces_the_stored_key(env):
    c, srv, auth = env
    pid = await _seed_provider(c, auth)

    r = await c.patch(f"/api/admin/providers/{pid}", headers=auth, json={"api_key": "sk-new"})

    assert r.status_code == 200
    assert srv.services.provider_repo.get(pid).api_key == "sk-new"


async def test_patch_api_key_null_can_be_combined_with_other_fields(env):
    c, srv, auth = env
    pid = await _seed_provider(c, auth)

    r = await c.patch(
        f"/api/admin/providers/{pid}",
        headers=auth,
        json={"api_key": None, "base_url": "https://proxy.example"},
    )

    assert r.status_code == 200
    row = srv.services.provider_repo.get(pid)
    assert row.api_key is None
    assert row.base_url == "https://proxy.example"


def test_revoking_a_key_still_requests_a_runtime_rehydrate():
    """``api_key`` is in ``_PROVIDER_REHYDRATE_FIELDS``.

    Without ``on_provider_changed`` the agent runtime keeps using the revoked
    credential from memory, so the revoke would be reported but not effective.
    """
    from octop.api.routers.providers import (
        ProviderPatchBody,
        _patch_requires_provider_rehydrate,
    )

    assert _patch_requires_provider_rehydrate(ProviderPatchBody(api_key=None)) is True
    assert _patch_requires_provider_rehydrate(ProviderPatchBody(note="x")) is False
    assert _patch_requires_provider_rehydrate(ProviderPatchBody()) is False
