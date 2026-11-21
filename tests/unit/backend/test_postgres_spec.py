"""Tests for postgres storage-spec mapping onto PostgresConfig fields."""

from __future__ import annotations

from octop.infra.backend.postgres_spec import (
    normalize_postgres_spec,
    parse_postgres_conninfo,
    split_host_port,
)
from octop.infra.db.repos.backends import BackendRow


def test_split_host_port() -> None:
    assert split_host_port("localhost:5432") == ("localhost", 5432)
    assert split_host_port("db.internal") == ("db.internal", None)
    assert split_host_port("[::1]:5432") == ("::1", 5432)


def test_parse_postgres_uri() -> None:
    parsed = parse_postgres_conninfo(
        "postgresql://alice:s3cret@pg.example:5432/app?sslmode=require"
    )
    assert parsed["host"] == "pg.example"
    assert parsed["port"] == 5432
    assert parsed["user"] == "alice"
    assert parsed["password"] == "s3cret"
    assert parsed["database"] == "app"
    assert parsed["sslmode"] == "require"


def test_normalize_postgres_spec_drops_uri_and_unknown_keys() -> None:
    out = normalize_postgres_spec(
        {
            "type": "postgres",
            "connection_string": "postgresql://u:p@localhost/db",
            "table": "files",
            "unknown": "drop-me",
        }
    )
    assert out == {
        "type": "postgres",
        "host": "localhost",
        "user": "u",
        "password": "p",
        "database": "db",
        "table": "files",
    }


def test_mapped_spec_is_accepted_by_postgres_config() -> None:
    from deepagents_backends import PostgresConfig

    from octop.infra.backend.adapter import row_to_backend_spec

    row = BackendRow(
        id=1,
        name="pg",
        kind="postgres",
        endpoint="localhost:5432",
        access_key="octop",
        secret_key="secret",
        bucket="octop",
        region="public",
        config_json=None,
        note=None,
        enabled=1,
        created_at=0,
        updated_at=0,
    )
    spec = row_to_backend_spec(row)
    assert spec is not None
    kwargs = {k: v for k, v in spec.items() if k != "type"}
    config = PostgresConfig(**kwargs)
    assert config.host == "localhost"
    assert config.port == 5432
    assert config.user == "octop"


def test_row_discrete_fields_override_uri() -> None:
    from octop.infra.backend.postgres_spec import row_to_postgres_spec

    row = BackendRow(
        id=1,
        name="pg",
        kind="postgres",
        endpoint="override.example:6543",
        access_key="rowuser",
        secret_key="rowpass",
        bucket="rowdb",
        region="agents",
        config_json='{"connection_string": "postgresql://u:p@localhost/db"}',
        note=None,
        enabled=1,
        created_at=0,
        updated_at=0,
    )
    spec = row_to_postgres_spec(row, {"connection_string": "postgresql://u:p@localhost/db"})
    assert spec is not None
    assert spec["host"] == "override.example"
    assert spec["port"] == 6543
    assert spec["user"] == "rowuser"
    assert spec["password"] == "rowpass"
    assert spec["database"] == "rowdb"
    assert spec["schema"] == "agents"
    assert "connection_string" not in spec
