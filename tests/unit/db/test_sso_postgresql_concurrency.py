"""Concurrent SSO provider saves on a real, isolated PostgreSQL schema."""

from __future__ import annotations

import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from tests.support.postgresql import requires_postgresql

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import PostgresPool, _PgConnectionProxy
from octop.infra.db.repos.sso import SsoRepo


@requires_postgresql
@pytest.mark.postgresql
def test_concurrent_first_provider_saves(monkeypatch: pytest.MonkeyPatch) -> None:
    import psycopg
    from psycopg.conninfo import make_conninfo

    conninfo = os.environ["OCTOP_TEST_DATABASE_URL"]
    schema = f"sso_race_{uuid.uuid4().hex}"
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute(f'CREATE SCHEMA "{schema}"')
    scoped_conninfo = make_conninfo(conninfo, options=f"-csearch_path={schema}")
    pools = [PostgresPool(scoped_conninfo, min_size=1, max_size=1) for _ in range(2)]
    try:
        run_migrations(pools[0])
        read_barrier = threading.Barrier(2)
        original_execute = _PgConnectionProxy.execute
        first_reads: set[int] = set()
        reads_lock = threading.Lock()

        class CoordinatedCursor:
            def __init__(self, cursor: Any) -> None:
                self._cursor = cursor

            def fetchone(self) -> Any:
                row = self._cursor.fetchone()
                read_barrier.wait(timeout=10)
                return row

        def execute(self: _PgConnectionProxy, sql: str, params: Any = None) -> Any:
            cursor = original_execute(self, sql, params)
            # Both real transactions must observe the initial miss before either
            # INSERT. Do not replace the database, SQL, constraint, or error.
            if sql == "SELECT * FROM sso_providers WHERE kind = ?":
                with reads_lock:
                    first = id(self) not in first_reads
                    first_reads.add(id(self))
                if first:
                    return CoordinatedCursor(cursor)
            return cursor

        monkeypatch.setattr(_PgConnectionProxy, "execute", execute)

        def save(index: int) -> int:
            row = SsoRepo(pools[index]).upsert_by_kind(
                "oidc",
                enabled=True,
                display_name=f"Provider {index}",
                issuer="https://idp.example.test",
                client_id=f"client-{index}",
                client_secret_enc=b"fixture-secret",
                scopes="openid",
                dashboard_origin=None,
                extra={"save": index},
            )
            assert row.display_name == f"Provider {index}"
            assert row.extra == {"save": index}
            return row.id

        with ThreadPoolExecutor(max_workers=2) as executor:
            ids = list(executor.map(save, range(2)))
        assert ids[0] == ids[1]
        monkeypatch.setattr(_PgConnectionProxy, "execute", original_execute)
        assert len(SsoRepo(pools[0]).list()) == 1
        updated = SsoRepo(pools[0]).upsert_by_kind(
            "oidc",
            enabled=False,
            display_name="Edited",
            issuer="https://idp.example.test",
            client_id="edited-client",
            client_secret_enc=None,
            scopes="openid profile",
            dashboard_origin=None,
        )
        assert updated.id == ids[0]
        assert updated.client_secret_enc == b"fixture-secret"
        assert updated.enabled == 0
    finally:
        for pool in pools:
            pool.close()
        with psycopg.connect(conninfo, autocommit=True) as conn:
            conn.execute(f'DROP SCHEMA "{schema}" CASCADE')
