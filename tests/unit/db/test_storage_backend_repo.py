"""Unit tests for BackendRepo."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.backends import BackendRepo


@pytest.fixture
def repo(tmp_path: Path) -> BackendRepo:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    return BackendRepo(db)


def test_create_and_get(repo: BackendRepo) -> None:
    rid = repo.create(
        name="my-cos",
        kind="cos",
        access_key="AK",
        secret_key="SK",
        bucket="my-bucket",
        region="ap-guangzhou",
    )
    row = repo.get(rid)
    assert row is not None
    assert row.name == "my-cos"
    assert row.kind == "cos"
    assert row.access_key == "AK"
    assert row.bucket == "my-bucket"
    assert row.enabled == 1


def test_get_by_name(repo: BackendRepo) -> None:
    repo.create(
        name="test-s3", kind="s3", access_key="A", secret_key="S", bucket="b", region="us-east-1"
    )
    row = repo.get_by_name("test-s3")
    assert row is not None
    assert row.kind == "s3"


def test_list_all(repo: BackendRepo) -> None:
    repo.create(name="b1", kind="cos", access_key="a", secret_key="s", bucket="x", region="r")
    repo.create(name="b2", kind="s3", access_key="a", secret_key="s", bucket="y", region="r")
    rows = repo.list_all()
    assert len(rows) == 2
    names = {r.name for r in rows}
    assert "b1" in names and "b2" in names


def test_update(repo: BackendRepo) -> None:
    rid = repo.create(name="u1", kind="oss", access_key="a", secret_key="s", bucket="b", region="r")
    repo.update(rid, bucket="new-bucket", enabled=False)
    row = repo.get(rid)
    assert row is not None
    assert row.bucket == "new-bucket"
    assert row.enabled == 0


def test_delete(repo: BackendRepo) -> None:
    rid = repo.create(name="d1", kind="cos", access_key="a", secret_key="s", bucket="b", region="r")
    repo.delete(rid)
    assert repo.get(rid) is None


def test_get_missing_returns_none(repo: BackendRepo) -> None:
    assert repo.get(9999) is None
