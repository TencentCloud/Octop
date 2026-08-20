"""Tests for storage backend spec resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.backend.adapter import row_to_backend_spec, storage_backend_kind_agent_resolvable
from octop.infra.backend.resolver import (
    backend_spec_supports_execution,
    collect_named_storage_backend_refs,
    find_agents_using_storage_backend,
    resolve_agent_backend_spec,
)
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.backends import BackendRepo, BackendRow


@pytest.fixture
def repo(tmp_path: Path) -> BackendRepo:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    return BackendRepo(db)


def test_resolve_named_backend(repo: BackendRepo) -> None:
    repo.create(
        name="my-cos",
        kind="cos",
        access_key="AKID",
        secret_key="SECRET",
        bucket="b-125",
        region="ap-guangzhou",
    )
    resolved = resolve_agent_backend_spec(
        {"type": "named", "name": "my-cos"},
        repo=repo,
    )
    assert resolved == {
        "type": "cos",
        "bucket": "b-125",
        "region": "ap-guangzhou",
        "secret_id": "AKID",
        "secret_key": "SECRET",
    }


def test_resolve_composite_with_named(repo: BackendRepo) -> None:
    repo.create(
        name="archive",
        kind="filesystem",
        bucket="/data/archive",
    )
    spec = {
        "type": "composite",
        "default": {"type": "filesystem", "virtual_mode": True},
        "routes": {"/archive": {"type": "named", "name": "archive"}},
    }
    resolved = resolve_agent_backend_spec(spec, repo=repo)
    archive_row = repo.get_by_name("archive")
    assert archive_row is not None
    assert resolved["type"] == "composite"
    assert resolved["routes"]["/archive"] == row_to_backend_spec(archive_row)


def test_backend_spec_supports_execution() -> None:
    assert backend_spec_supports_execution({"type": "local_shell", "virtual_mode": True})
    assert backend_spec_supports_execution({"type": "docker", "image": "python:3.12-slim"})
    assert backend_spec_supports_execution("docker")
    assert not backend_spec_supports_execution({"type": "filesystem", "virtual_mode": True})
    assert not backend_spec_supports_execution({"type": "state"})
    assert backend_spec_supports_execution(
        {
            "type": "composite",
            "default": {"type": "filesystem", "virtual_mode": True},
            "routes": {"/shell": {"type": "local_shell", "virtual_mode": True}},
        }
    )


def test_storage_backend_kind_agent_resolvable() -> None:
    assert storage_backend_kind_agent_resolvable("cos")
    assert storage_backend_kind_agent_resolvable("filesystem")
    assert storage_backend_kind_agent_resolvable("docker")


def test_row_to_backend_spec_docker() -> None:
    row = BackendRow(
        id=1,
        name="sandbox",
        kind="docker",
        endpoint=None,
        access_key=None,
        secret_key=None,
        bucket="python:3.12-slim",
        region=None,
        config_json='{"allow_network": false, "memory": "512m", "sandbox_scope": "user", "sandbox_prefix": "octop_sandbox"}',
        note=None,
        enabled=1,
        created_at=0,
        updated_at=0,
    )
    assert row_to_backend_spec(row) == {
        "type": "docker",
        "image": "python:3.12-slim",
        "allow_network": False,
        "memory": "512m",
        "sandbox_scope": "user",
        "sandbox_prefix": "octop_sandbox",
    }


def test_enrich_docker_backend_spec_defaults() -> None:
    from octop.infra.backend.docker_spec import (
        docker_spec_previewable,
        enrich_docker_backend_spec,
    )

    agent = enrich_docker_backend_spec(
        {"type": "docker", "image": "python:3.12-slim"},
        agent_id="ZE6GR2",
    )
    assert agent["sandbox_prefix"] == "octop_sandbox"
    assert agent["sandbox_scope"] == "agent"
    assert agent["agent_id"] == "ZE6GR2"
    assert docker_spec_previewable(agent) is False

    user = enrich_docker_backend_spec(
        {"type": "docker", "image": "python:3.12-slim", "sandbox_scope": "user"},
        agent_id="ZE6GR2",
        username="alice",
    )
    assert user["username"] == "alice"
    assert docker_spec_previewable(user) is False

    fixed = enrich_docker_backend_spec(
        {
            "type": "docker",
            "image": "python:3.12-slim",
            "sandbox_scope": "fixed",
            "sandbox_id": "shared1",
        },
        agent_id="ZE6GR2",
    )
    assert docker_spec_previewable(fixed) is True
    assert "agent_id" not in fixed or fixed.get("agent_id") == "ZE6GR2"


def test_inject_docker_global_environment_sets_file() -> None:
    from octop.infra.backend.docker_spec import inject_docker_global_environment

    spec = inject_docker_global_environment(
        {"type": "docker", "environment": {"FOO": "from-spec"}},
        "/data/octop/env",
    )
    assert spec["environment_file"] == "/data/octop/env"
    assert spec["environment"] == {"FOO": "from-spec"}
    local = inject_docker_global_environment({"type": "local_shell"}, "/data/octop/env")
    assert "environment_file" not in local


def test_collect_named_storage_backend_refs() -> None:
    assert collect_named_storage_backend_refs({"type": "named", "name": "my-cos"}) == {"my-cos"}
    assert collect_named_storage_backend_refs(
        {
            "type": "composite",
            "default": {"type": "filesystem", "virtual_mode": True},
            "routes": {
                "/data": {"type": "named", "name": "archive"},
                "/x": {"type": "local_shell", "virtual_mode": True},
            },
        }
    ) == {"archive"}
    assert collect_named_storage_backend_refs(None) == set()


def test_find_agents_using_storage_backend() -> None:
    class _Row:
        def __init__(self, agent_id: str, name: str) -> None:
            self.agent_id = agent_id
            self.name = name

    class _Repo:
        def list_all(self) -> list[_Row]:
            return [
                _Row("A1", "Alice Bot"),
                _Row("B2", "Bob Bot"),
            ]

    configs = {
        "A1": {"backend": {"type": "named", "name": "my-cos"}},
        "B2": {"backend": {"type": "filesystem", "virtual_mode": True}},
    }

    refs = find_agents_using_storage_backend(
        agent_repo=_Repo(),
        get_config=lambda aid: configs.get(aid, {}),
        backend_name="my-cos",
    )
    assert refs == [{"agent_id": "A1", "name": "Alice Bot"}]
