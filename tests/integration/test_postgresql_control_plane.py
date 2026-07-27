"""Gated PostgreSQL control-plane integration tests.

Set ``OCTOP_TEST_DATABASE_URL`` to a **dedicated** database (tests DROP SCHEMA public).
Example::

    export OCTOP_TEST_DATABASE_URL='postgresql://postgres:postgres@127.0.0.1:15432/octop_test'

Avoid pointing at a shared app DB (locks from other sessions will hang resets).
Without the env var these tests are skipped — default CI stays SQLite-only.
"""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from urllib.parse import urlparse

import pytest

from tests.support.postgresql import requires_postgresql


def _conninfo() -> str:
    return os.environ["OCTOP_TEST_DATABASE_URL"]


def _reset_public_schema(pool: object) -> None:
    with pool.connect() as conn:  # type: ignore[attr-defined]
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.execute("GRANT ALL ON SCHEMA public TO CURRENT_USER")
        conn.execute("COMMIT")


def _pg_payload_from_url(url: str) -> dict[str, object]:
    parsed = urlparse(url)
    return {
        "driver": "postgresql",
        "host": parsed.hostname or "127.0.0.1",
        "port": parsed.port or 5432,
        "database": (parsed.path or "/octop").lstrip("/") or "octop",
        "user": parsed.username or "postgres",
        "password": parsed.password or "",
        "url": url,
    }


@requires_postgresql
@pytest.mark.postgresql
def test_pg_migrate_and_user_roundtrip() -> None:
    from octop.infra.db.migrate import run_migrations
    from octop.infra.db.pool import PostgresPool
    from octop.infra.db.repos.users import UserRepo

    pool = PostgresPool(_conninfo())
    try:
        _reset_public_schema(pool)
        run_migrations(pool)
        repo = UserRepo(pool)
        username = f"pg_tester_{uuid.uuid4().hex[:8]}"
        uid = repo.create(username=username, password_hash="x", role="user")
        row = repo.get(uid)
        assert row is not None
        assert row.username == username
    finally:
        pool.close()


@requires_postgresql
@pytest.mark.postgresql
def test_pg_control_plane_repo_smoke() -> None:
    """Exercise the main control-plane repos on a live PG schema."""
    from octop.infra.db.migrate import run_migrations
    from octop.infra.db.pool import PostgresPool
    from octop.infra.db.repos.agents import AgentRepo
    from octop.infra.db.repos.channels import ChannelRepo
    from octop.infra.db.repos.cron import CronJobRepo
    from octop.infra.db.repos.providers import ProviderRepo
    from octop.infra.db.repos.sessions import SessionRepo
    from octop.infra.db.repos.threads import ThreadRepo
    from octop.infra.db.repos.users import UserRepo
    from octop.infra.gateway.threads import ThreadRegistry
    from octop.infra.utils.ulid import new_ulid

    pool = PostgresPool(_conninfo())
    try:
        _reset_public_schema(pool)
        run_migrations(pool)

        users = UserRepo(pool)
        uid = users.create(username=f"u_{uuid.uuid4().hex[:8]}", password_hash="h", role="admin")
        aid = new_ulid()
        AgentRepo(pool).create(agent_id=aid, user_id=uid, name="bot")
        assert AgentRepo(pool).get(aid) is not None

        cid = new_ulid()
        ChannelRepo(pool).create(
            channel_id=cid,
            agent_id=aid,
            user_id=uid,
            kind="slack",
            name="main",
            config_json="{}",
        )
        assert ChannelRepo(pool).get(cid) is not None

        sk = ThreadRegistry.dashboard_key(agent_id=aid, user_id=uid)
        tid = f"thr_{uuid.uuid4().hex[:10]}"
        ThreadRepo(pool).insert(
            thread_id=tid,
            agent_id=aid,
            user_id=uid,
            channel_type="dashboard",
            session_key=sk,
        )
        SessionRepo(pool).upsert(
            session_key=sk,
            agent_id=aid,
            user_id=uid,
            channel_type="dashboard",
            chat_type="dm",
            thread_id=tid,
        )
        assert SessionRepo(pool).get(sk) is not None
        assert ThreadRepo(pool).get(tid) is not None

        cron_id = new_ulid()
        CronJobRepo(pool).create(
            cron_id=cron_id,
            agent_id=aid,
            user_id=uid,
            trigger="0 9 * * *",
            prompt="ping",
            session_key=sk,
        )
        assert CronJobRepo(pool).get(cron_id) is not None

        ProviderRepo(pool).create(
            name=f"p_{uuid.uuid4().hex[:6]}",
            kind="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-test",
        )
        assert len(ProviderRepo(pool).list_all()) >= 1
    finally:
        pool.close()


@requires_postgresql
@pytest.mark.postgresql
def test_pg_probe_ok() -> None:
    from octop.config import DatabaseConfig
    from octop.infra.db.probe import probe_database
    from octop.infra.utils.paths import PathLayout

    payload = _pg_payload_from_url(_conninfo())
    cfg = DatabaseConfig(
        driver="postgresql",
        url=str(payload["url"]),
        host=str(payload["host"]),
        port=int(payload["port"]),
        database=str(payload["database"]),
        user=str(payload["user"]),
        password=str(payload["password"]),
    )
    probe_database(cfg, PathLayout(Path("/tmp")))


@requires_postgresql
@pytest.mark.postgresql
def test_pg_backup_roundtrip(tmp_path: Path) -> None:
    if not shutil.which("pg_dump") or not shutil.which("pg_restore"):
        pytest.skip("pg_dump/pg_restore not on PATH")

    from octop.config import DatabaseConfig
    from octop.infra.backup.system_archive import create_system_backup, restore_system_backup
    from octop.infra.db.migrate import run_migrations
    from octop.infra.db.pool import PostgresPool
    from octop.infra.db.repos.users import UserRepo
    from octop.infra.utils.paths import PathLayout

    conninfo = _conninfo()
    payload = _pg_payload_from_url(conninfo)
    db_config = DatabaseConfig(
        driver="postgresql",
        url=conninfo,
        host=str(payload["host"]),
        port=int(payload["port"]),
        database=str(payload["database"]),
        user=str(payload["user"]),
        password=str(payload["password"]),
    )
    pool = PostgresPool(conninfo)
    try:
        _reset_public_schema(pool)
        run_migrations(pool)
        repo = UserRepo(pool)
        username = f"pg_bak_{uuid.uuid4().hex[:8]}"
        repo.create(username=username, password_hash="x", role="user")

        layout = PathLayout(tmp_path / ".octop")
        layout.root.mkdir(parents=True, exist_ok=True)
        layout.config.write_text('{"port": 8088}', encoding="utf-8")

        class Row:
            agent_id = "agent01"
            name = "Test"

        data, _ = create_system_backup(
            paths=layout,
            agent_rows=[Row()],
            pool=pool,
            db_config=db_config,
        )

        _reset_public_schema(pool)
        run_migrations(pool)
        result = restore_system_backup(
            data,
            paths=layout,
            pool=pool,
            db_config=db_config,
            restore_config=False,
        )
        assert result["database_driver"] == "postgresql"
        found = repo.get_by_username(username)
        assert found is not None
    finally:
        pool.close()


@requires_postgresql
@pytest.mark.postgresql
@pytest.mark.asyncio
async def test_setup_database_postgresql_bind(tmp_octop_home: Path) -> None:
    """Wizard: probe + bind live PostgreSQL, then create admin."""
    from octop.infra.db.pool import PostgresPool
    from octop.infra.setup.password_file import read_password
    from tests.support.app import octop_client

    pool = PostgresPool(_conninfo())
    try:
        _reset_public_schema(pool)
    finally:
        pool.close()

    payload = _pg_payload_from_url(_conninfo())
    async with octop_client(tmp_octop_home, bind_database=False) as (client, srv):
        assert srv.database_bound is False

        probed = await client.post("/api/setup/test-database", json=payload)
        assert probed.status_code == 200, probed.text
        assert probed.json()["ok"] is True

        bound = await client.post("/api/setup/database", json=payload)
        assert bound.status_code == 200, bound.text
        body = bound.json()
        assert body["ok"] is True
        assert body["driver"] == "postgresql"
        assert srv.database_bound is True

        status = await client.get("/api/setup/status")
        assert status.json()["database_bound"] is True
        assert status.json()["database_driver"] == "postgresql"

        pw = read_password(tmp_octop_home.parent)
        assert pw is not None
        verified = await client.post("/api/setup/verify-password", json={"password": pw})
        assert verified.status_code == 200, verified.text
        tok = verified.json()["wizard_token"]

        created = await client.post(
            "/api/setup/initial-admin",
            json={"username": "admin", "password": "admin-pass", "display_name": "Admin"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert created.status_code in (200, 201), created.text
        assert srv.user_manager is not None
        assert srv.user_manager.count() == 1
