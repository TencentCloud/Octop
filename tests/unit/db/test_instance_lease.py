"""Same-row cron and channel leases across two database connections."""

from __future__ import annotations

import os
import threading
import uuid
from pathlib import Path

import pytest
from tests.support.postgresql import requires_postgresql

from octop.infra.db.lease import LEASE_SECONDS
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.channels import ChannelRepo
from octop.infra.db.repos.cron import CronJobRepo
from octop.infra.db.repos.users import UserRepo


def _seed(db: SqlitePool) -> tuple[str, str]:
    user_id = UserRepo(db).create(username="alice", password_hash="h", role="admin")
    agent_id = "agent-lease"
    AgentRepo(db).create(agent_id=agent_id, user_id=user_id, name="bot")
    cron_id = "cron-lease"
    CronJobRepo(db).create(
        cron_id=cron_id,
        agent_id=agent_id,
        user_id=user_id,
        trigger="interval:60",
        prompt="run",
        session_key="session",
    )
    channel_id = "channel-lease"
    ChannelRepo(db).create(
        channel_id=channel_id,
        agent_id=agent_id,
        user_id=user_id,
        kind="feishu",
        name="main",
        config_json="{}",
    )
    return cron_id, channel_id


def test_cron_claim_is_exclusive_and_fenced(tmp_path: Path) -> None:
    path = tmp_path / "octop.db"
    first = SqlitePool(path)
    run_migrations(first)
    second = SqlitePool(path)
    cron_id, _channel_id = _seed(first)
    repo_a = CronJobRepo(first)
    repo_b = CronJobRepo(second)

    held = repo_a.claim_run(cron_id, owner="instance-a", lease_seconds=LEASE_SECONDS)
    assert held is not None
    assert repo_b.claim_run(cron_id, owner="instance-b", lease_seconds=LEASE_SECONDS) is None
    assert repo_b.renew_run_lease(cron_id, token="other", lease_seconds=LEASE_SECONDS) is False

    with second.transaction() as conn:
        conn.execute("UPDATE cron_jobs SET run_lease_until = 1 WHERE cron_id = ?", (cron_id,))
    taken = repo_b.claim_run(cron_id, owner="instance-b", lease_seconds=LEASE_SECONDS)
    assert taken is not None
    assert taken.run_lease_owner == "instance-b"
    assert repo_a.finish_run(cron_id, token=str(held.run_lease_token), ts=1, status="ok") is False
    assert (
        repo_b.finish_run(
            cron_id,
            token=str(taken.run_lease_token),
            ts=2,
            status="ok",
            disable=True,
        )
        is True
    )
    row = repo_a.get(cron_id)
    assert row is not None
    assert row.enabled == 0
    assert row.last_status == "ok"
    assert row.run_lease_token is None
    first.close()
    second.close()


def test_concurrent_cron_claims_have_one_winner(tmp_path: Path) -> None:
    path = tmp_path / "octop.db"
    first = SqlitePool(path)
    run_migrations(first)
    second = SqlitePool(path)
    cron_id, _channel_id = _seed(first)
    repos = (CronJobRepo(first), CronJobRepo(second))
    barrier = threading.Barrier(2)
    results: list[object] = []

    def _claim(repo: CronJobRepo, owner: str) -> None:
        barrier.wait()
        results.append(repo.claim_run(cron_id, owner=owner, lease_seconds=LEASE_SECONDS))

    threads = [
        threading.Thread(target=_claim, args=(repos[0], "a")),
        threading.Thread(target=_claim, args=(repos[1], "b")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sum(result is not None for result in results) == 1
    first.close()
    second.close()


def test_channel_generation_invalidates_old_owner(tmp_path: Path) -> None:
    path = tmp_path / "octop.db"
    first = SqlitePool(path)
    run_migrations(first)
    second = SqlitePool(path)
    _cron_id, channel_id = _seed(first)
    repo_a = ChannelRepo(first)
    repo_b = ChannelRepo(second)

    held = repo_a.claim_runtime_lease(channel_id, owner="instance-a", lease_seconds=LEASE_SECONDS)
    assert held is not None
    assert (
        repo_b.claim_runtime_lease(channel_id, owner="instance-b", lease_seconds=LEASE_SECONDS)
        is None
    )
    repo_a.update(channel_id, name="renamed")
    assert (
        repo_a.renew_runtime_lease(
            channel_id,
            token=str(held.runtime_lease_token),
            generation=held.runtime_generation,
            lease_seconds=LEASE_SECONDS,
        )
        is False
    )
    assert repo_a.release_runtime_lease(channel_id, token=str(held.runtime_lease_token)) is True
    taken = repo_b.claim_runtime_lease(channel_id, owner="instance-b", lease_seconds=LEASE_SECONDS)
    assert taken is not None
    assert taken.runtime_generation == held.runtime_generation + 1
    assert repo_a.release_runtime_lease(channel_id, token=str(held.runtime_lease_token)) is False
    first.close()
    second.close()


def _postgres_pools() -> tuple[object, object, str]:
    import psycopg
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    from octop.infra.db.pool import PostgresPool

    url = os.environ["OCTOP_TEST_DATABASE_URL"]
    schema = "lease_" + uuid.uuid4().hex[:12]
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(f'CREATE SCHEMA "{schema}"')
    info = conninfo_to_dict(url)
    info["options"] = f"-c search_path={schema}"
    conninfo = make_conninfo(**info)
    return PostgresPool(conninfo), PostgresPool(conninfo), schema


@requires_postgresql
@pytest.mark.postgresql
def test_postgres_cron_claim_has_one_winner() -> None:
    import psycopg

    first, second, schema = _postgres_pools()
    url = os.environ["OCTOP_TEST_DATABASE_URL"]
    try:
        run_migrations(first)  # type: ignore[arg-type]
        cron_id, _channel_id = _seed(first)  # type: ignore[arg-type]
        repo_a = CronJobRepo(first)  # type: ignore[arg-type]
        repo_b = CronJobRepo(second)  # type: ignore[arg-type]
        assert repo_a.claim_run(cron_id, owner="pg-a", lease_seconds=LEASE_SECONDS) is not None
        assert repo_b.claim_run(cron_id, owner="pg-b", lease_seconds=LEASE_SECONDS) is None
    finally:
        first.close()  # type: ignore[attr-defined]
        second.close()  # type: ignore[attr-defined]
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
