"""Orphan checkpoint reporting on a live PostgreSQL memory store.

LangGraph's checkpoint tables are shared by every agent and host on a DSN and
record no owner, so Octop only counts orphans there and never deletes them.

Each test creates throwaway databases on the server from
``OCTOP_TEST_DATABASE_URL`` and drops them afterwards. That role needs the
``CREATEDB`` privilege.
"""

from __future__ import annotations

import contextlib
import json
import os
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any, TypedDict

import pytest

from octop.config import DatabaseConfig, OctopConfig
from octop.infra.agents.memory.thread_cleanup import (
    close_memory,
    gc_orphan_checkpoints,
    sweep_deleted_residuals,
)
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import build_shared_services
from octop.infra.utils.paths import PathLayout
from octop.infra.utils.ulid import new_ulid
from tests.support.postgresql import requires_postgresql

pytestmark = requires_postgresql


@pytest.fixture
def make_database() -> Iterator[Any]:
    import psycopg
    from psycopg.conninfo import make_conninfo

    created: list[str] = []
    admin_url = os.environ["OCTOP_TEST_DATABASE_URL"]

    def make() -> DatabaseConfig:
        name = f"octop_orphan_{uuid.uuid4().hex[:12]}"
        with psycopg.connect(admin_url, autocommit=True) as conn:
            conn.execute(f'CREATE DATABASE "{name}"')
        created.append(name)
        # Only the database name changes; every other connection option is kept.
        return DatabaseConfig(driver="postgresql", url=make_conninfo(admin_url, dbname=name))

    yield make
    with psycopg.connect(admin_url, autocommit=True) as conn:
        for name in created:
            with contextlib.suppress(psycopg.Error):
                conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def _services(tmp_path: Path, control_plane: DatabaseConfig) -> tuple[Any, SqlitePool]:
    paths = PathLayout(tmp_path / ".octop")
    paths.ensure_root()
    db = SqlitePool(paths.db)
    run_migrations(db)
    return build_shared_services(db=db, paths=paths, config=OctopConfig(database=control_plane)), db


class _State(TypedDict):
    n: int


def _write_threads(dsn: str, agent_id: str | None, thread_ids: list[str]) -> None:
    """Run a one-step graph so LangGraph writes real checkpoints for each thread."""
    from langgraph.graph import END, START, StateGraph
    from octop_memory.core import Memory

    namespace = f"agent_{agent_id}" if agent_id else "other_host"
    memory = Memory(namespace=namespace, backend="postgres", backend_config={"dsn": dsn})
    try:
        memory._ensure_checkpointer()
        graph = StateGraph(_State)
        graph.add_node("step", lambda state: {"n": state["n"] + 1})
        graph.add_edge(START, "step")
        graph.add_edge("step", END)
        app = graph.compile(checkpointer=memory._checkpointer)
        for thread_id in thread_ids:
            # Octop's harness config carries agent_id; LangGraph copies it into metadata.
            configurable = {"thread_id": thread_id}
            if agent_id:
                configurable["agent_id"] = agent_id
            app.invoke({"n": 0}, {"configurable": configurable})
    finally:
        close_memory(memory)


def _write_memory(dsn: str, namespace: str) -> None:
    from octop_memory.core import Memory

    memory = Memory(namespace=namespace, backend="postgres", backend_config={"dsn": dsn})
    try:
        memory.add_raw("hello", event_type="user_message")
    finally:
        close_memory(memory)


def _checkpoint_rows(dsn: str) -> dict[str, int]:
    """Row count per thread across all three checkpoint tables."""
    import psycopg

    counts: dict[str, int] = {}
    with psycopg.connect(dsn) as conn:
        for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
            found = conn.execute(
                "SELECT COALESCE(to_regclass(%s), to_regclass(%s))::text",
                (f"octop_memory.{table}", f"public.{table}"),
            ).fetchone()
            if found is None or found[0] is None:
                continue
            for thread_id, n in conn.execute(
                f"SELECT thread_id, COUNT(*) FROM {found[0]} GROUP BY thread_id"
            ):
                counts[str(thread_id)] = counts.get(str(thread_id), 0) + int(n)
    return counts


def _tid() -> str:
    return f"thr_{new_ulid()}"


def _seed_two_agents(services: Any, dsn: str) -> dict[str, str]:
    """A: one live thread and one orphan. B: two live threads."""
    user_id = services.user_repo.create(username="alice", password_hash="x", role="admin")
    ids = {
        "a_live": _tid(),
        "a_orphan": _tid(),
        "b_live1": _tid(),
        "b_live2": _tid(),
    }
    for agent_id in ("A", "B"):
        services.agent_repo.create(agent_id=agent_id, user_id=user_id, name=agent_id)
    for key, agent_id in (("a_live", "A"), ("b_live1", "B"), ("b_live2", "B")):
        services.thread_repo.insert(
            thread_id=ids[key],
            agent_id=agent_id,
            user_id=user_id,
            channel_type="dashboard",
            session_key=key,
        )
    _write_threads(dsn, "A", [ids["a_live"], ids["a_orphan"]])
    _write_threads(dsn, "B", [ids["b_live1"], ids["b_live2"]])
    return ids


def _add_external_agent(services: Any, dsn: str) -> None:
    user = services.user_repo.get_by_username("alice")
    user_id = (
        user.id
        if user is not None
        else services.user_repo.create(username="alice", password_hash="x", role="admin")
    )
    services.agent_repo.create(
        agent_id="EXT",
        user_id=user_id,
        name="ext",
        config_json=json.dumps({"memory": {"backend": {"type": "postgres", "dsn": dsn}}}),
    )


def test_gc_orphans_reports_postgres_orphans_without_deleting(
    tmp_path: Path, make_database: Any
) -> None:
    control = make_database()
    dsn = control.postgresql_conninfo()
    services, db = _services(tmp_path, control)
    try:
        ids = _seed_two_agents(services, dsn)
        before = _checkpoint_rows(dsn)

        for agent_id in ("A", None):
            result = gc_orphan_checkpoints(services, agent_id=agent_id, apply=True)

            assert result.orphans == []
            assert [(s.agent_id, s.reason, s.threads) for s in result.skipped] == [
                ("A", "postgres_report_only", 1)
            ]
            assert result.skipped[0].nbytes > 0
        assert _checkpoint_rows(dsn) == before
        assert set(before) == set(ids.values())
    finally:
        db.close()


def test_gc_orphans_does_not_report_a_thread_live_under_another_agent(
    tmp_path: Path, make_database: Any
) -> None:
    control = make_database()
    dsn = control.postgresql_conninfo()
    services, db = _services(tmp_path, control)
    try:
        ids = _seed_two_agents(services, dsn)
        # Same thread id written under A's tag, but B owns it in ``threads``.
        _write_threads(dsn, "A", [ids["b_live1"]])

        result = gc_orphan_checkpoints(services, agent_id="A", apply=False)

        assert [(s.agent_id, s.threads) for s in result.skipped] == [("A", 1)]
    finally:
        db.close()


def test_gc_orphans_does_not_scan_other_databases(tmp_path: Path, make_database: Any) -> None:
    control = make_database()
    external = make_database()
    control_dsn = control.postgresql_conninfo()
    services, db = _services(tmp_path, control)
    try:
        _seed_two_agents(services, control_dsn)
        external_dsn = external.postgresql_conninfo()
        _add_external_agent(services, external_dsn)
        _write_threads(external_dsn, "EXT", [_tid()])
        # Same server and database, spelled differently: still not the control plane.
        _write_threads(control_dsn, "SAME", [_tid()])
        services.agent_repo.create(
            agent_id="SAME",
            user_id=services.user_repo.get_by_username("alice").id,
            name="same",
            config_json=json.dumps(
                {
                    "memory": {
                        "backend": {
                            "type": "postgres",
                            "dsn": f"{control_dsn} application_name=octop_test",
                        }
                    }
                }
            ),
        )
        external_before = _checkpoint_rows(external_dsn)
        control_before = _checkpoint_rows(control_dsn)

        result = gc_orphan_checkpoints(services, agent_id=None, apply=True)

        skipped = {(s.agent_id, s.reason, s.threads) for s in result.skipped}
        assert ("EXT", "external_database", None) in skipped
        assert ("SAME", "external_database", None) in skipped
        assert _checkpoint_rows(external_dsn) == external_before
        assert _checkpoint_rows(control_dsn) == control_before
    finally:
        db.close()


def test_sweep_counts_postgres_residuals_without_deleting(
    tmp_path: Path, make_database: Any
) -> None:
    import psycopg

    control = make_database()
    external = make_database()
    dsn = control.postgresql_conninfo()
    external_dsn = external.postgresql_conninfo()
    services, db = _services(tmp_path, control)
    try:
        _seed_two_agents(services, dsn)
        _add_external_agent(services, external_dsn)
        _write_threads(external_dsn, "EXT", [_tid()])
        _write_threads(dsn, None, [_tid()])  # another host: no agent_id, never counted
        _write_memory(dsn, "agent_A")
        _write_memory(dsn, "agent_GONE")
        # octop_memory has not migrated the pre-rename schema yet: it must stay untouched.
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute("CREATE SCHEMA harness_memory")
            conn.execute("CREATE TABLE harness_memory.raw_events (namespace text, id text)")
            conn.execute("INSERT INTO harness_memory.raw_events VALUES ('agent_OLD', '1')")
        control_before = _checkpoint_rows(dsn)
        external_before = _checkpoint_rows(external_dsn)
        manager = type(
            "Manager",
            (),
            {"_repos": services.repos, "_paths": services.paths, "_config": services.config},
        )()

        result = sweep_deleted_residuals(manager)

        assert result["namespaces"] == 0
        assert result["threads"] == 0
        assert result["postgres_kept"] == {"threads": 1, "namespaces": 1}
        assert result["skipped_databases"] == 1
        assert _checkpoint_rows(dsn) == control_before
        assert _checkpoint_rows(external_dsn) == external_before
        with psycopg.connect(dsn) as conn:
            gone = conn.execute(
                "SELECT COUNT(*) FROM octop_memory.raw_events WHERE namespace = 'agent_gone'"
            ).fetchone()
            old = conn.execute("SELECT COUNT(*) FROM harness_memory.raw_events").fetchone()
        assert gone is not None and gone[0] == 1
        assert old is not None and old[0] == 1
    finally:
        db.close()
