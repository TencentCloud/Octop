"""Tests for storage backend spec resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.backend.adapter import row_to_backend_spec, storage_backend_kind_agent_resolvable
from octop.infra.backend.resolver import backend_spec_supports_execution, resolve_agent_backend_spec
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.backends import BackendRepo


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
    assert not storage_backend_kind_agent_resolvable("docker")
