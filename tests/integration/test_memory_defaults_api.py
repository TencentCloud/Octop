"""Integration tests for global default memory settings & per-expert inheritance (#2963)."""

from __future__ import annotations

import pytest

from tests.support.auth import create_provider, create_user


@pytest.mark.asyncio
async def test_global_memory_defaults_api_and_expert_inheritance_lifecycle(
    env_with_main_agent,
) -> None:
    client, srv, admin_auth, main_aid = env_with_main_agent

    # Seed two usable models so we can test global default + custom override.
    await create_provider(
        client,
        admin_auth,
        name="mem-prov",
        base_url="https://api.example.com/v1",
        models=[
            {"id": "light", "name": "Light", "enabled": True},
            {"id": "specialist", "name": "Specialist", "enabled": True},
        ],
    )

    # Create a second expert that pins its own custom aux_model BEFORE global defaults exist.
    r_create_custom = await client.post(
        "/api/agents",
        headers=admin_auth,
        json={"name": "Custom Expert"},
    )
    assert r_create_custom.status_code == 201, r_create_custom.text
    custom_aid = r_create_custom.json()["agent_id"]

    r_pin = await client.put(
        f"/api/agents/{custom_aid}/memory/extract-config",
        headers=admin_auth,
        json={"aux_model": "mem-prov/specialist"},
    )
    assert r_pin.status_code == 200, r_pin.text
    assert r_pin.json()["aux_model_mode"] == "custom"
    assert r_pin.json()["aux_model"] == "mem-prov/specialist"

    # A legacy partial update may serialize unset optional fields as null.
    legacy_update = await client.put(
        f"/api/agents/{custom_aid}/memory/extract-config",
        headers=admin_auth,
        json={"aux_model": None, "extract_idle_seconds": 120},
    )
    assert legacy_update.status_code == 200, legacy_update.text
    assert legacy_update.json()["aux_model"] == "mem-prov/specialist"
    assert legacy_update.json()["aux_model_mode"] == "custom"

    # Initial global defaults are unset.
    r_glob0 = await client.get("/api/settings/memory-defaults", headers=admin_auth)
    assert r_glob0.status_code == 200, r_glob0.text
    assert r_glob0.json()["aux_model"] is None
    assert r_glob0.json()["extract_keep_rules"] == ""
    assert r_glob0.json()["extract_skip_rules"] == ""

    # Admin updates global defaults (model + keep/skip rules).
    r_glob1 = await client.put(
        "/api/settings/memory-defaults",
        headers=admin_auth,
        json={
            "aux_model": "mem-prov/light",
            "extract_keep_rules": "Keep stable preferences and long-term decisions.",
            "extract_skip_rules": "Skip greetings and one-off lookups.",
        },
    )
    assert r_glob1.status_code == 200, r_glob1.text
    body_glob1 = r_glob1.json()
    assert body_glob1["aux_model"] == "mem-prov/light"
    assert body_glob1["aux_model_usable"] is True
    assert body_glob1["extract_keep_rules"] == "Keep stable preferences and long-term decisions."
    assert body_glob1["extract_skip_rules"] == "Skip greetings and one-off lookups."
    assert body_glob1["affected_agent_count"] >= 1

    # Existing uncustomized expert (main_aid) automatically inherits both model and rules.
    r_main = await client.get(f"/api/agents/{main_aid}/memory/extract-config", headers=admin_auth)
    assert r_main.status_code == 200, r_main.text
    main_cfg = r_main.json()
    assert main_cfg["aux_model_mode"] == "inherit"
    assert main_cfg["aux_model"] is None
    assert main_cfg["extract_rules_mode"] == "inherit"
    assert main_cfg["effective"]["aux_model"] == "mem-prov/light"
    assert (
        main_cfg["effective"]["extract_keep_rules"]
        == "Keep stable preferences and long-term decisions."
    )
    assert main_cfg["effective"]["extract_skip_rules"] == "Skip greetings and one-off lookups."

    # Existing expert with prior custom aux_model keeps its custom model, while inheriting rules.
    r_custom = await client.get(
        f"/api/agents/{custom_aid}/memory/extract-config", headers=admin_auth
    )
    assert r_custom.status_code == 200, r_custom.text
    custom_cfg = r_custom.json()
    assert custom_cfg["aux_model_mode"] == "custom"
    assert custom_cfg["aux_model"] == "mem-prov/specialist"
    assert custom_cfg["effective"]["aux_model"] == "mem-prov/specialist"
    assert custom_cfg["extract_rules_mode"] == "inherit"
    assert (
        custom_cfg["effective"]["extract_keep_rules"]
        == "Keep stable preferences and long-term decisions."
    )

    # Newly created expert also inherits global defaults out of the box.
    r_new = await client.post(
        "/api/agents",
        headers=admin_auth,
        json={"name": "Fresh Expert"},
    )
    assert r_new.status_code == 201, r_new.text
    fresh_aid = r_new.json()["agent_id"]
    r_fresh_cfg = await client.get(
        f"/api/agents/{fresh_aid}/memory/extract-config", headers=admin_auth
    )
    assert r_fresh_cfg.status_code == 200, r_fresh_cfg.text
    assert r_fresh_cfg.json()["effective"]["aux_model"] == "mem-prov/light"
    assert (
        r_fresh_cfg.json()["effective"]["extract_keep_rules"]
        == "Keep stable preferences and long-term decisions."
    )

    # Expert can override rules independently while keeping inherited model.
    r_rules_custom = await client.put(
        f"/api/agents/{main_aid}/memory/extract-config",
        headers=admin_auth,
        json={
            "extract_rules_mode": "custom",
            "extract_keep_rules": "Keep legal contract clauses and deadlines.",
            "extract_skip_rules": "Skip draft brainstorming.",
        },
    )
    assert r_rules_custom.status_code == 200, r_rules_custom.text
    rc = r_rules_custom.json()
    assert rc["aux_model_mode"] == "inherit"
    assert rc["effective"]["aux_model"] == "mem-prov/light"
    assert rc["extract_rules_mode"] == "custom"
    assert rc["effective"]["extract_keep_rules"] == "Keep legal contract clauses and deadlines."
    assert rc["effective"]["extract_skip_rules"] == "Skip draft brainstorming."

    # Expert can explicitly override extraction model to follow its own chat model (custom + null).
    r_chat_follow = await client.put(
        f"/api/agents/{main_aid}/memory/extract-config",
        headers=admin_auth,
        json={"aux_model_mode": "custom", "aux_model": None},
    )
    assert r_chat_follow.status_code == 200, r_chat_follow.text
    cf = r_chat_follow.json()
    assert cf["aux_model_mode"] == "custom"
    assert cf["aux_model"] is None
    assert cf["effective"]["aux_model"] is None

    # Restore inheritance for both model and rules.
    r_restore = await client.put(
        f"/api/agents/{main_aid}/memory/extract-config",
        headers=admin_auth,
        json={"aux_model_mode": "inherit", "extract_rules_mode": "inherit"},
    )
    assert r_restore.status_code == 200, r_restore.text
    restored = r_restore.json()
    assert restored["aux_model_mode"] == "inherit"
    assert restored["extract_rules_mode"] == "inherit"
    assert restored["effective"]["aux_model"] == "mem-prov/light"
    assert (
        restored["effective"]["extract_keep_rules"]
        == "Keep stable preferences and long-term decisions."
    )

    # Regular user cannot access global admin settings, but sees read-only global summary on own agent.
    user_auth = await create_user(client, admin_auth, username="alice", password="AlicePass123!")

    r_denied_get = await client.get("/api/settings/memory-defaults", headers=user_auth)
    assert r_denied_get.status_code == 403
    r_denied_put = await client.put(
        "/api/settings/memory-defaults",
        headers=user_auth,
        json={"aux_model": ""},
    )
    assert r_denied_put.status_code == 403

    r_alice_agent = await client.post(
        "/api/agents",
        headers=user_auth,
        json={"name": "Alice Expert"},
    )
    assert r_alice_agent.status_code == 201, r_alice_agent.text
    alice_aid = r_alice_agent.json()["agent_id"]
    r_alice_cfg = await client.get(
        f"/api/agents/{alice_aid}/memory/extract-config", headers=user_auth
    )
    assert r_alice_cfg.status_code == 200, r_alice_cfg.text
    assert r_alice_cfg.json()["global_defaults"]["aux_model"] == "mem-prov/light"
    assert r_alice_cfg.json()["effective"]["aux_model"] == "mem-prov/light"
    repos = srv.services.repos
    group = repos.user_group_repo.create(name="specialists", description=None)
    repos.resource_group_grant_repo.replace("model", "mem-prov/specialist", [group.user_group_id])
    denied = await client.put(
        f"/api/agents/{alice_aid}/memory/extract-config",
        headers=user_auth,
        json={"aux_model_mode": "custom", "aux_model": "mem-prov/specialist"},
    )
    assert denied.status_code == 403
    current = await client.get(f"/api/agents/{alice_aid}/memory/extract-config", headers=user_auth)
    assert current.json()["aux_model_mode"] == "inherit"


@pytest.mark.asyncio
async def test_global_memory_defaults_validation(env_with_main_agent) -> None:
    client, _srv, admin_auth, _aid = env_with_main_agent

    r_bad_model = await client.put(
        "/api/settings/memory-defaults",
        headers=admin_auth,
        json={"aux_model": "nonexistent/model"},
    )
    assert r_bad_model.status_code == 400

    r_too_long = await client.put(
        "/api/settings/memory-defaults",
        headers=admin_auth,
        json={"extract_keep_rules": "x" * 2001},
    )
    assert r_too_long.status_code == 400


@pytest.mark.asyncio
async def test_memory_defaults_respect_delegated_model_grants(env) -> None:
    client, server, admin = env
    await create_provider(
        client,
        admin,
        name="restricted",
        base_url="https://example.com/v1",
        models=[{"id": "lite", "enabled": True}],
    )
    repos = server.services.repos
    group = repos.user_group_repo.create(name="model users", description=None)
    repos.resource_group_grant_repo.replace("model", "restricted/lite", [group.user_group_id])
    editor = await create_user(client, admin, username="editor", permissions=["memory_defaults"])
    url = "/api/settings/memory-defaults"
    model = {"aux_model": "restricted/lite"}
    assert (await client.put(url, headers=editor, json=model)).status_code == 403
    assert (await client.get(url, headers=editor)).json()["aux_model"] is None
    assert (await client.put(url, headers=admin, json=model)).status_code == 200
    rules = await client.put(url, headers=editor, json={"extract_skip_rules": "Skip greetings"})
    assert rules.status_code == 200
    assert rules.json()["aux_model"] == "restricted/lite"
    user = repos.user_repo.get_by_username("editor")
    repos.user_group_member_repo.add(group.user_group_id, user.id)
    assert (await client.put(url, headers=editor, json=model)).status_code == 200
