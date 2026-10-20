"""Tests for postgres spec normalization and factory."""

from __future__ import annotations

import logging

import pytest

from octop_harness.backends.postgres import postgres_config_kwargs


def test_postgres_config_kwargs_maps_uri() -> None:
    out = postgres_config_kwargs(
        {
            "connection_string": "postgresql://octop_app:p%40ss@127.0.0.1:5433/mydb?sslmode=require",
            "schema": "agent",
            "previewable": False,
        }
    )
    assert out["host"] == "127.0.0.1"
    assert out["port"] == 5433
    assert out["database"] == "mydb"
    assert out["user"] == "octop_app"
    assert out["password"] == "p@ss"
    assert out["sslmode"] == "require"
    assert out["schema"] == "agent"
    assert "connection_string" not in out
    assert "previewable" not in out


def test_postgres_config_kwargs_explicit_fields_win() -> None:
    out = postgres_config_kwargs(
        {
            "dsn": "postgresql://from-uri:pw@example:5432/uri-db",
            "host": "127.0.0.1",
            "database": "named",
        }
    )
    assert out["host"] == "127.0.0.1"
    assert out["database"] == "named"
    assert out["user"] == "from-uri"


def test_postgres_config_kwargs_drops_unknown_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        out = postgres_config_kwargs({"host": "localhost", "previewable": True})
    assert out == {"host": "localhost"}
    assert any("previewable" in rec.message for rec in caplog.records)


def test_postgres_config_kwargs_invalid_uri_hides_secret() -> None:
    with pytest.raises(ValueError, match="invalid postgres connection_string") as exc_info:
        postgres_config_kwargs({"connection_string": "not-a-postgres-uri://x:secret@h/db"})
    assert "secret" not in str(exc_info.value)
    assert exc_info.value.__cause__ is None


def test_resolve_postgres_from_uri() -> None:
    pytest.importorskip("psycopg")
    from octop_harness.backends import resolve_backend
    from octop_harness.backends.postgres import PostgresBackend

    backend = resolve_backend(
        {
            "type": "postgres",
            "connection_string": "postgresql://octop_app:p%40ss@127.0.0.1/mydb",
            "connection_timeout": 1,
            "previewable": True,
        }
    )
    assert isinstance(backend, PostgresBackend)
    assert backend._config.host == "127.0.0.1"
    assert backend._config.user == "octop_app"
    assert backend._config.password == "p@ss"
    assert backend._config.database == "mydb"


def test_postgres_config_kwargs_fits_dataclass() -> None:
    from octop_harness.backends.postgres import PostgresConfig

    fitted = postgres_config_kwargs(
        {
            "connection_string": "postgresql://u:p@127.0.0.1:5432/db",
            "min_pool_size": 1,
            "previewable": True,
        },
        field_names={f.name for f in PostgresConfig.__dataclass_fields__.values()} - {"extra"},
    )
    assert set(fitted) <= set(PostgresConfig.__dataclass_fields__)
    PostgresConfig(**fitted)
