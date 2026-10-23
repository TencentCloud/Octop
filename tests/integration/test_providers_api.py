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


async def test_admin_can_delete_custom_provider_on_local_url(env):
    """Custom OpenAI-compat rows stay deletable even on Ollama-like URLs."""
    c, _, auth = env
    for name, base_url in (
        ("my-local-llm", "http://127.0.0.1:8000/v1"),
        ("new-api", "http://192.168.1.10:3000/v1"),
        ("company-ollama", "http://127.0.0.1:11434"),
        ("docker-ollama", "http://ollama:11434"),
    ):
        r = await c.post(
            "/api/admin/providers",
            headers=auth,
            json={
                "name": name,
                "kind": "openai",
                "api_key": "sk-local",
                "base_url": base_url,
                "models": [{"id": "custom-qwen", "name": "custom-qwen", "enabled": True}],
            },
        )
        assert r.status_code == 201, name
        pid = r.json()["id"]

        r = await c.delete(f"/api/admin/providers/{pid}", headers=auth)
        assert r.status_code in (200, 204), name

        r = await c.get("/api/admin/providers", headers=auth)
        ids = [p["id"] for p in r.json()]
        assert pid not in ids, name


async def test_admin_cannot_delete_ollama_runtime_by_identity(env):
    """Onboard Ollama is protected by placeholder key / exact name, not URL."""
    c, _, auth = env
    r = await c.post(
        "/api/admin/providers",
        headers=auth,
        json={
            "name": "Ollama (Local)",
            "kind": "openai",
            "api_key": "ollama",
            "base_url": "http://127.0.0.1:11434",
        },
    )
    assert r.status_code == 201
    pid = r.json()["id"]

    r = await c.delete(f"/api/admin/providers/{pid}", headers=auth)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "PROVIDER_LOCAL_PROTECTED"


async def test_admin_stream_usage_defaults_and_patch(env):
    """Custom providers default stream_usage off; presets stay on until patched."""
    c, _, auth = env
    custom = await c.post(
        "/api/admin/providers",
        headers=auth,
        json={"name": "mindie-arm", "kind": "openai", "api_key": "k"},
    )
    assert custom.status_code == 201
    assert custom.json()["stream_usage"] is False

    preset = await c.post(
        "/api/admin/providers",
        headers=auth,
        json={"name": "DeepSeek", "kind": "openai", "api_key": "k"},
    )
    assert preset.status_code == 201
    assert preset.json()["stream_usage"] is True

    patched = await c.patch(
        f"/api/admin/providers/{preset.json()['id']}",
        headers=auth,
        json={"stream_usage": False},
    )
    assert patched.status_code == 200
    assert patched.json()["stream_usage"] is False


async def test_admin_cannot_delete_provider_used_as_active_model(env):
    """DELETE /admin/providers/{id} refuses when settings active_model points at it.

    Deleting would leave a dead ref so every turn fails to resolve a default
    model with no hint; the error names the active model to switch to.
    """
    c, _, auth = env
    r = await c.post(
        "/api/admin/providers",
        headers=auth,
        json={
            "name": "active-p",
            "kind": "openai",
            "api_key": "k",
            "base_url": "https://api.example.com/v1",
            "models": [{"id": "m1", "name": "m1", "enabled": True}],
        },
    )
    assert r.status_code == 201
    pid = r.json()["id"]

    r = await c.put(
        "/api/providers/active-model",
        headers=auth,
        json={"provider_name": "active-p", "model": "m1"},
    )
    assert r.status_code == 200

    r = await c.delete(f"/api/admin/providers/{pid}", headers=auth)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "PROVIDER_REFERENCED"
    assert r.json()["error"]["details"]["active_model"] == "active-p/m1"

    r = await c.get("/api/admin/providers", headers=auth)
    ids = [p["id"] for p in r.json()]
    assert pid in ids

    r = await c.get("/api/providers/active-model", headers=auth)
    assert r.json() == {"provider_name": "active-p", "model": "m1"}


async def test_admin_can_delete_provider_after_switching_active_model(env):
    """Control: once the active model points elsewhere the provider is deletable."""
    c, _, auth = env
    pids: dict[str, str] = {}
    for name in ("active-p", "other-p"):
        r = await c.post(
            "/api/admin/providers",
            headers=auth,
            json={
                "name": name,
                "kind": "openai",
                "api_key": "k",
                "base_url": "https://api.example.com/v1",
                "models": [{"id": "m1", "name": "m1", "enabled": True}],
            },
        )
        assert r.status_code == 201, name
        pids[name] = r.json()["id"]
    active_pid = pids["active-p"]
    other_pid = pids["other-p"]

    r = await c.put(
        "/api/providers/active-model",
        headers=auth,
        json={"provider_name": "active-p", "model": "m1"},
    )
    assert r.status_code == 200

    # Deleting the non-active provider is unaffected.
    r = await c.delete(f"/api/admin/providers/{other_pid}", headers=auth)
    assert r.status_code in (200, 204)

    # Switch the default model away, then the formerly-active provider deletes.
    r = await c.post(
        "/api/admin/providers",
        headers=auth,
        json={
            "name": "fresh-p",
            "kind": "openai",
            "api_key": "k",
            "base_url": "https://api.example.com/v1",
            "models": [{"id": "m1", "name": "m1", "enabled": True}],
        },
    )
    assert r.status_code == 201
    r = await c.put(
        "/api/providers/active-model",
        headers=auth,
        json={"provider_name": "fresh-p", "model": "m1"},
    )
    assert r.status_code == 200

    r = await c.delete(f"/api/admin/providers/{active_pid}", headers=auth)
    assert r.status_code in (200, 204)

    rows = (await c.get("/api/admin/providers", headers=auth)).json()
    ids = [p["id"] for p in rows]
    assert active_pid not in ids
    assert other_pid not in ids
