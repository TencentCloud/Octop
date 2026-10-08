from __future__ import annotations

import pytest

from octop.infra.db.pool import PostgresPool, qmark_to_pyformat


def test_qmark_to_pyformat_replaces_placeholders():
    assert qmark_to_pyformat("SELECT * FROM t WHERE a = ? AND b = ?") == (
        "SELECT * FROM t WHERE a = %s AND b = %s"
    )


def test_qmark_to_pyformat_leaves_percent_alone():
    assert qmark_to_pyformat("SELECT %s") == "SELECT %s"


@pytest.fixture
def pool_kwargs(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    """Capture what ``PostgresPool`` hands psycopg, so no server is needed."""
    import psycopg_pool

    captured: list[dict[str, object]] = []

    class _FakeConnectionPool:
        def __init__(self, **kwargs: object) -> None:
            captured.append(kwargs)

        def close(self) -> None:
            return None

    monkeypatch.setattr(psycopg_pool, "ConnectionPool", _FakeConnectionPool)
    return captured


def test_postgres_pool_forwards_sizing_and_idle_policy(
    pool_kwargs: list[dict[str, object]],
) -> None:
    PostgresPool(
        "postgresql://octop@127.0.0.1:5432/octop",
        min_size=2,
        max_size=6,
        max_idle=15.0,
    ).close()
    assert len(pool_kwargs) == 1
    assert pool_kwargs[0]["min_size"] == 2
    assert pool_kwargs[0]["max_size"] == 6
    assert pool_kwargs[0]["max_idle"] == 15.0


def test_postgres_pool_holds_nothing_at_rest_by_default(
    pool_kwargs: list[dict[str, object]],
) -> None:
    PostgresPool("postgresql://octop@127.0.0.1:5432/octop").close()
    assert pool_kwargs[0]["min_size"] == 0
