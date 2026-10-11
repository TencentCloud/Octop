"""Creating a user with copies of an administrator's experts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from octop.infra.errors import ErrorCode, OctopError
from tests.support.auth import auth_header, create_user


async def _source(client, auth, name: str, **options) -> str:
    result = await client.post(
        "/api/agents/from-expert/default",
        headers=auth,
        json={"name": name, **options},
    )
    assert result.status_code == 201, result.text
    return result.json()["agent_id"]


async def _usernames(client, auth) -> set[str]:
    return {row["username"] for row in (await client.get("/api/users", headers=auth)).json()}


async def test_create_user_pushes_expert_settings_into_independent_workspace(env, tmp_path):
    client, server, admin_auth = env
    root = tmp_path / "expert-root"
    root.mkdir()
    backend = {"type": "filesystem", "root_dir": str(root)}
    source_id = await _source(
        client,
        admin_auth,
        "configured-expert",
        backend=backend,
        default_model="test/model",
        temperature=0.4,
        conversation_mode="plan",
    )
    registry = server.app_runtime.agent_registry
    source_workspace = registry.workspace_for_agent(source_id)
    assert source_workspace is not None
    manifest = json.loads(await source_workspace.aread_text(".octop/manifest.json"))
    manifest["prompt_files"].append("USER.md")
    await source_workspace.aupload_many(
        [
            ("AGENTS.md", b"custom expert instructions"),
            ("USER.md", b"administrator personal context"),
            (".octop/manifest.json", json.dumps(manifest).encode()),
        ]
    )
    source_settings = registry.get_config(source_id)
    source_settings["memory"] = {
        "backend": {"type": "sqlite", "db_path": str(tmp_path / "admin-memory.sqlite")}
    }
    registry.persist_harness_config(source_id, source_settings)

    created = await client.post(
        "/api/users",
        headers=admin_auth,
        json={
            "username": "student_expert",
            "password": "TestPass12",
            "role": "user",
            "source_agent_ids": [source_id],
        },
    )
    assert created.status_code == 201, created.text
    target_id = created.json()["id"]
    copies = registry.list_agents(target_id)
    assert len(copies) == 1
    copy = copies[0]
    assert copy.user_id == target_id
    assert copy.agent_id != source_id
    student_auth = await auth_header(client, username="student_expert", password="TestPass12")
    mine = (await client.get("/api/agents", headers=student_auth)).json()
    assert any(row["agent_id"] == copy.agent_id for row in mine)
    assert copy.template_name == "default"
    assert copy.default_model == "test/model"
    source_config = registry.get_config(source_id)
    copy_config = registry.get_config(copy.agent_id)
    assert copy_config["backend"] == backend
    assert copy_config["temperature"] == 0.4
    assert copy_config["conversation_mode"] == "plan"
    assert copy_config["memory"]["backend"] == {"type": "sqlite"}
    assert copy_config["workspace_dir"] != source_config["workspace_dir"]
    assert registry.resolve_workspace_dir(copy.agent_id) != registry.resolve_workspace_dir(
        source_id
    )
    assert copy_config["system_files_path"] == ".octop"
    target_workspace = registry.workspace_for_agent(copy.agent_id)
    assert target_workspace is not None
    assert await target_workspace.aread_text("AGENTS.md") == "custom expert instructions"
    assert await target_workspace.aread_text("USER.md") is None
    target_manifest = json.loads(await target_workspace.aread_text(".octop/manifest.json"))
    assert "USER.md" not in target_manifest["prompt_files"]
    assert await source_workspace.aread_text("USER.md") == "administrator personal context"


async def test_create_user_rejects_foreign_team_and_missing_sources(env):
    client, server, admin_auth = env
    other_auth = await create_user(client, admin_auth, username="other_expert_owner")
    foreign_id = await _source(client, other_auth, "foreign-expert")
    admin_id = (await client.get("/api/auth/me", headers=admin_auth)).json()["id"]
    server.services.agent_repo.create(
        agent_id="team-push-source",
        user_id=admin_id,
        name="team-push-source",
        kind="team",
    )
    for username, source_id, expected in [
        ("foreign_push", foreign_id, 403),
        ("team_push", "team-push-source", 403),
        ("missing_push", "missing-source-id", 404),
    ]:
        result = await client.post(
            "/api/users",
            headers=admin_auth,
            json={
                "username": username,
                "password": "TestPass12",
                "role": "user",
                "source_agent_ids": [source_id],
            },
        )
        assert result.status_code == expected, result.text
        assert username not in await _usernames(client, admin_auth)


async def test_user_manager_without_admin_role_cannot_push_experts(env):
    client, _server, admin_auth = env
    source_id = await _source(client, admin_auth, "manager-source")
    manager_auth = await create_user(
        client, admin_auth, username="account_manager", permissions=["users"]
    )
    denied = await client.post(
        "/api/users",
        headers=manager_auth,
        json={
            "username": "manager_push_denied",
            "password": "TestPass12",
            "role": "user",
            "permissions": [],
            "source_agent_ids": [source_id],
        },
    )
    assert denied.status_code == 403, denied.text
    assert "manager_push_denied" not in await _usernames(client, admin_auth)

    plain = await client.post(
        "/api/users",
        headers=manager_auth,
        json={
            "username": "manager_plain_user",
            "password": "TestPass12",
            "role": "user",
            "permissions": [],
        },
    )
    assert plain.status_code == 201, plain.text


async def test_create_user_push_respects_target_agent_quota(env):
    client, server, admin_auth = env
    source_id = await _source(client, admin_auth, "quota-source")
    before = {row.agent_id for row in server.app_runtime.agent_registry.list_rows()}
    result = await client.post(
        "/api/users",
        headers=admin_auth,
        json={
            "username": "quota_push",
            "password": "TestPass12",
            "role": "user",
            "max_agents": 0,
            "source_agent_ids": [source_id],
        },
    )
    assert result.status_code == 403, result.text
    assert result.json()["error"]["code"] == "AGENT_QUOTA_EXCEEDED"
    assert "quota_push" not in await _usernames(client, admin_auth)
    assert {row.agent_id for row in server.app_runtime.agent_registry.list_rows()} == before


async def test_create_user_push_rejects_inaccessible_knowledge_base(env):
    client, server, admin_auth = env
    admin_id = (await client.get("/api/auth/me", headers=admin_auth)).json()["id"]
    base = server.services.knowledge_repo.create_base(
        owner_user_id=admin_id, name="private-source-base"
    )
    source_id = await _source(client, admin_auth, "private-kb-source", knowledge_base_ids=[base.id])
    result = await client.post(
        "/api/users",
        headers=admin_auth,
        json={
            "username": "private_kb_push",
            "password": "TestPass12",
            "role": "user",
            "source_agent_ids": [source_id],
        },
    )
    assert result.status_code == 404, result.text
    assert result.json()["error"]["code"] == "KNOWLEDGE_NOT_FOUND"
    assert "private_kb_push" not in await _usernames(client, admin_auth)


async def test_create_user_push_checks_resolved_named_backend_root(env, tmp_path, monkeypatch):
    monkeypatch.setenv("OCTOP_IN_CONTAINER", "0")
    client, server, admin_auth = env
    source_id = await _source(client, admin_auth, "named-backend-source")
    registry = server.app_runtime.agent_registry
    source_config = registry.get_config(source_id)
    server.services.storage_backend_repo.create(
        name="source-workspace-backend",
        kind="filesystem",
        config_json=json.dumps({"root_dir": str(Path(source_config["workspace_dir"]).parent)}),
    )
    source_config["backend"] = {"type": "named", "name": "source-workspace-backend"}
    registry.persist_harness_config(source_id, source_config)
    allowed = tmp_path / "student-root"
    allowed.mkdir()

    result = await client.post(
        "/api/users",
        headers=admin_auth,
        json={
            "username": "named_backend_denied",
            "password": "TestPass12",
            "role": "user",
            "workspace_root_dir": str(allowed),
            "source_agent_ids": [source_id],
        },
    )
    assert result.status_code == 400, result.text
    assert result.json()["error"]["code"] == "WORKSPACE_ROOT_RESTRICTED"
    assert "named_backend_denied" not in await _usernames(client, admin_auth)


async def test_create_user_push_rejects_backend_root_at_source_workspace(env):
    client, server, admin_auth = env
    source_id = await _source(client, admin_auth, "source-workspace-root")
    registry = server.app_runtime.agent_registry
    config = registry.get_config(source_id)
    config["backend"] = {"type": "filesystem", "root_dir": config["workspace_dir"]}
    registry.persist_harness_config(source_id, config)

    result = await client.post(
        "/api/users",
        headers=admin_auth,
        json={
            "username": "source_root_target",
            "password": "TestPass12",
            "role": "user",
            "source_agent_ids": [source_id],
        },
    )
    assert result.status_code == 400, result.text
    assert result.json()["error"]["code"] == "EXPERT_PUSH_UNSAFE"
    assert "source_root_target" not in await _usernames(client, admin_auth)


async def test_create_user_push_keeps_safe_named_backend_reference(env):
    client, server, admin_auth = env
    source_id = await _source(client, admin_auth, "safe-named-source")
    registry = server.app_runtime.agent_registry
    config = registry.get_config(source_id)
    server.services.storage_backend_repo.create(
        name="shared-expert-root",
        kind="filesystem",
        config_json=json.dumps({"root_dir": str(Path(config["workspace_dir"]).parent)}),
    )
    config["backend"] = {"type": "named", "name": "shared-expert-root"}
    registry.persist_harness_config(source_id, config)

    result = await client.post(
        "/api/users",
        headers=admin_auth,
        json={
            "username": "safe_named_target",
            "password": "TestPass12",
            "role": "user",
            "source_agent_ids": [source_id],
        },
    )
    assert result.status_code == 201, result.text
    copy = registry.list_agents(result.json()["id"])[0]
    assert registry.get_config(copy.agent_id)["backend"] == config["backend"]
    assert registry.resolve_workspace_dir(copy.agent_id) != registry.resolve_workspace_dir(
        source_id
    )


@pytest.mark.parametrize(
    "backend",
    [
        {
            "type": "docker",
            "image": "python:3.12",
            "sandbox_scope": "fixed",
            "sandbox_id": "shared",
        },
        {"type": "docker", "image": "python:3.12", "agent_id": "source-agent"},
        {"type": "docker", "image": "python:3.12", "container_name": "source-container"},
        {"type": "docker", "image": "python:3.12", "workspace_path": "/shared"},
        {"type": "docker", "image": "python:3.12", "volumes": {"/host/private": "/private"}},
    ],
)
async def test_create_user_push_rejects_shared_docker_configuration_before_user_exists(
    env, backend
):
    client, server, admin_auth = env
    source_id = await _source(client, admin_auth, "unsafe-docker-source")
    registry = server.app_runtime.agent_registry
    config = registry.get_config(source_id)
    config["backend"] = backend
    registry.persist_harness_config(source_id, config)

    result = await client.post(
        "/api/users",
        headers=admin_auth,
        json={
            "username": "unsafe_docker_target",
            "password": "TestPass12",
            "role": "user",
            "source_agent_ids": [source_id],
        },
    )
    assert result.status_code == 400, result.text
    assert result.json()["error"]["code"] == "EXPERT_PUSH_UNSAFE"
    assert "unsafe_docker_target" not in await _usernames(client, admin_auth)


async def test_create_user_push_checks_named_docker_inside_composite_before_user_exists(env):
    client, server, admin_auth = env
    source_id = await _source(client, admin_auth, "named-docker-source")
    registry = server.app_runtime.agent_registry
    server.services.storage_backend_repo.create(
        name="shared-docker-backend",
        kind="docker",
        config_json=json.dumps(
            {"image": "python:3.12", "sandbox_scope": "fixed", "sandbox_id": "shared"}
        ),
    )
    config = registry.get_config(source_id)
    config["backend"] = {
        "type": "composite",
        "default": {
            "type": "filesystem",
            "root_dir": str(Path(config["workspace_dir"]).parent),
        },
        "routes": {"/sandbox/": {"type": "named", "name": "shared-docker-backend"}},
    }
    registry.persist_harness_config(source_id, config)

    result = await client.post(
        "/api/users",
        headers=admin_auth,
        json={
            "username": "named_docker_target",
            "password": "TestPass12",
            "role": "user",
            "source_agent_ids": [source_id],
        },
    )
    assert result.status_code == 400, result.text
    assert result.json()["error"]["code"] == "EXPERT_PUSH_UNSAFE"
    assert "named_docker_target" not in await _usernames(client, admin_auth)


async def test_create_user_push_rejects_named_opensandbox_before_user_exists(env):
    client, server, admin_auth = env
    source_id = await _source(client, admin_auth, "named-opensandbox-source")
    registry = server.app_runtime.agent_registry
    server.services.storage_backend_repo.create(
        name="remote-expert-backend",
        kind="opensandbox",
        config_json=json.dumps({"image": "python:3.12"}),
    )
    config = registry.get_config(source_id)
    config["backend"] = {"type": "named", "name": "remote-expert-backend"}
    registry.persist_harness_config(source_id, config)

    result = await client.post(
        "/api/users",
        headers=admin_auth,
        json={
            "username": "opensandbox_target",
            "password": "TestPass12",
            "role": "user",
            "source_agent_ids": [source_id],
        },
    )
    assert result.status_code == 400, result.text
    assert result.json()["error"]["code"] == "EXPERT_PUSH_UNSAFE"
    assert "opensandbox_target" not in await _usernames(client, admin_auth)


async def test_create_user_push_rejects_named_docker_environment_before_user_exists(env):
    client, server, admin_auth = env
    source_id = await _source(client, admin_auth, "named-docker-environment-source")
    registry = server.app_runtime.agent_registry
    server.services.storage_backend_repo.create(
        name="docker-with-admin-environment",
        kind="docker",
        config_json=json.dumps({"image": "python:3.12", "environment": {"TOKEN": "private"}}),
    )
    config = registry.get_config(source_id)
    config["backend"] = {"type": "named", "name": "docker-with-admin-environment"}
    registry.persist_harness_config(source_id, config)

    result = await client.post(
        "/api/users",
        headers=admin_auth,
        json={
            "username": "named_docker_environment_target",
            "password": "TestPass12",
            "role": "user",
            "source_agent_ids": [source_id],
        },
    )
    assert result.status_code == 400, result.text
    assert result.json()["error"]["code"] == "EXPERT_PUSH_UNSAFE"
    assert "named_docker_environment_target" not in await _usernames(client, admin_auth)


@pytest.mark.parametrize(
    "backend",
    [
        {"type": "docker", "image": "python:3.12", "environment": {"API_TOKEN": "private"}},
        {"type": "docker", "image": "python:3.12", "environment_file": "admin.env"},
        {"type": "s3", "bucket": "example", "secret_access_key": "private"},
        {"type": "postgres", "dsn": "postgresql://admin:private@localhost/db"},
        {"type": "opensandbox", "image": "python:3.12", "api_key": "private"},
    ],
)
async def test_create_user_push_rejects_inline_backend_credentials_before_user_exists(env, backend):
    client, server, admin_auth = env
    source_id = await _source(client, admin_auth, "credential-source")
    registry = server.app_runtime.agent_registry
    config = registry.get_config(source_id)
    config["backend"] = backend
    registry.persist_harness_config(source_id, config)

    result = await client.post(
        "/api/users",
        headers=admin_auth,
        json={
            "username": "credential_target",
            "password": "TestPass12",
            "role": "user",
            "source_agent_ids": [source_id],
        },
    )
    assert result.status_code == 400, result.text
    assert result.json()["error"]["code"] == "EXPERT_PUSH_UNSAFE"
    assert "credential_target" not in await _usernames(client, admin_auth)


async def test_create_user_push_rejects_inline_memory_credentials_before_user_exists(env):
    client, server, admin_auth = env
    source_id = await _source(client, admin_auth, "memory-credential-source")
    registry = server.app_runtime.agent_registry
    config = registry.get_config(source_id)
    config["memory"] = {
        "backend": {"type": "postgres", "dsn": "postgresql://admin:private@localhost/db"}
    }
    registry.persist_harness_config(source_id, config)

    result = await client.post(
        "/api/users",
        headers=admin_auth,
        json={
            "username": "memory_credential_target",
            "password": "TestPass12",
            "role": "user",
            "source_agent_ids": [source_id],
        },
    )
    assert result.status_code == 400, result.text
    assert result.json()["error"]["code"] == "EXPERT_PUSH_UNSAFE"
    assert "memory_credential_target" not in await _usernames(client, admin_auth)


@pytest.mark.parametrize(
    "extra_config",
    [
        {"plugins": {"echo-tool": {"tools": {"echo_message": {"config": {"prefix": "private"}}}}}},
        {"acp": {"tool_enabled": True, "runners": {"legacy": {"env": {"TOKEN": "private"}}}}},
    ],
)
async def test_create_user_push_rejects_private_agent_settings_before_user_exists(
    env, extra_config
):
    client, server, admin_auth = env
    source_id = await _source(client, admin_auth, "private-setting-source")
    registry = server.app_runtime.agent_registry
    config = registry.get_config(source_id)
    config.update(extra_config)
    registry.persist_harness_config(source_id, config)

    result = await client.post(
        "/api/users",
        headers=admin_auth,
        json={
            "username": "private_setting_target",
            "password": "TestPass12",
            "role": "user",
            "source_agent_ids": [source_id],
        },
    )
    assert result.status_code == 400, result.text
    assert result.json()["error"]["code"] == "EXPERT_PUSH_UNSAFE"
    assert "private_setting_target" not in await _usernames(client, admin_auth)


async def test_create_user_push_rejects_private_key_file_before_user_exists(env):
    client, server, admin_auth = env
    source_id = await _source(client, admin_auth, "key-file-source")
    workspace = server.app_runtime.agent_registry.workspace_for_agent(source_id)
    assert workspace is not None
    await workspace.aupload_many([("skills/ssh/id_ed25519", b"private key material")])

    result = await client.post(
        "/api/users",
        headers=admin_auth,
        json={
            "username": "key_file_target",
            "password": "TestPass12",
            "role": "user",
            "source_agent_ids": [source_id],
        },
    )
    assert result.status_code == 400, result.text
    assert result.json()["error"]["code"] == "EXPERT_PUSH_UNSAFE"
    assert "key_file_target" not in await _usernames(client, admin_auth)


async def test_create_user_push_cleans_up_after_second_copy_fails(env_with_provider, monkeypatch):
    client, server, admin_auth = env_with_provider
    source_ids = [
        await _source(client, admin_auth, "rollback-source-1"),
        await _source(client, admin_auth, "rollback-source-2"),
    ]
    registry = server.app_runtime.agent_registry
    before = {row.agent_id for row in registry.list_rows()}
    original_create = registry.create
    calls = 0
    first_copy_id = None

    async def fail_second(*args, **kwargs):
        nonlocal calls, first_copy_id
        calls += 1
        if calls == 2:
            assert first_copy_id is not None
            assert registry.get_agent(first_copy_id) is not None
            raise RuntimeError("test copy failure")
        row = await original_create(*args, **kwargs)
        first_copy_id = row.agent_id
        return row

    monkeypatch.setattr(registry, "create", fail_second)
    with pytest.raises(RuntimeError, match="test copy failure"):
        await client.post(
            "/api/users",
            headers=admin_auth,
            json={
                "username": "rollback_push",
                "password": "TestPass12",
                "role": "user",
                "source_agent_ids": source_ids,
            },
        )
    assert "rollback_push" not in await _usernames(client, admin_auth)
    assert {row.agent_id for row in registry.list_rows()} == before
    assert first_copy_id is not None
    assert registry.get_row(first_copy_id) is None
    with pytest.raises(OctopError) as missing:
        registry.get_agent(first_copy_id)
    assert missing.value.code == ErrorCode.AGENT_NOT_FOUND
