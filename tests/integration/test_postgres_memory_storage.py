"""Real PostgreSQL safety gate; use a dedicated disposable database, never production.

Run with OCTOP_MEMORY_MAINTENANCE_TEST_DSN. An explicitly supplied but
unreachable database fails the gate instead of silently skipping it.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from octop_memory import Memory
from octop_memory.storage.backends.postgres import PostgresMemoryBackend
from octop_memory.types import AtomCard, Candidate, JournalEntry

from octop.infra.agents.memory import postgres_storage as storage
from octop.infra.agents.memory.thread_cleanup import memory_namespace

DSN = os.environ.get("OCTOP_MEMORY_MAINTENANCE_TEST_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="dedicated PostgreSQL test DSN not configured")


def seed(backend):
    old = datetime.now(UTC) - timedelta(days=60)
    candidate = Candidate(
        id="expired",
        raw_event_ids=["evidence"],
        candidate_type="Fact",
        status="rejected",
        title="历史候选",
        assertion="original",
        verbatim_quote="original",
        quote_event_id="evidence",
        subject_name="User",
        subject_entity_type="User",
        target_entity_id=None,
        confidence="high",
        importance="low",
        recommended_action="promote",
        promotion_reason="test",
        extractor_version="test",
        created_at=old,
        decided_at=old,
    )
    for item in (
        candidate,
        replace(candidate, id="referenced"),
        replace(candidate, id="recent", decided_at=datetime.now(UTC)),
        replace(candidate, id="pending", status="pending", decided_at=None),
        replace(candidate, id="promoted", status="promoted"),
    ):
        backend.save_candidate(item)
    backend.save_atom(
        AtomCard(
            id="fact",
            entity_id="user",
            candidate_id="referenced",
            raw_event_ids=["evidence"],
            assertion="keep fact",
            verbatim_quote="keep fact",
            quote_event_id="evidence",
            search_terms=[],
            occurred_at=old,
            confidence="high",
            importance="low",
            created_at=old,
        )
    )
    for name, action, stamp in (
        ("expired", "extract_run", old),
        ("recent", "extract_run", datetime.now(UTC)),
        ("decision", "reject", old),
        ("consolidated", "consolidate", old),
    ):
        backend.append_journal(JournalEntry(id=name, timestamp=stamp, action=action, actor="auto"))


@pytest.fixture
def stores():
    prefix = f"test_maintenance_{uuid.uuid4().hex}"
    first = PostgresMemoryBackend(namespace=prefix + "_a", dsn=DSN)
    second = PostgresMemoryBackend(namespace=prefix + "_b", dsn=DSN)
    try:
        seed(first)
        seed(second)  # Deliberately identical IDs in the two expert namespaces.
        yield first, second
    finally:
        for backend in (first, second):
            backend.purge_namespace()
            backend.close()


def snapshot(backend):
    from psycopg import sql

    with storage._connect(backend) as conn, conn.cursor() as cur:
        result = {}
        for table in storage.TABLES:
            cur.execute(
                sql.SQL(
                    "SELECT to_jsonb(t) AS data FROM octop_memory.{} t WHERE namespace = %s"
                ).format(sql.Identifier(table)),
                (backend._ns,),
            )
            result[table] = sorted(
                (row["data"] for row in cur.fetchall()), key=lambda row: str(row)
            )
        return result


def test_cleanup_is_scoped_backed_up_and_other_expert_remains_writable(stores, tmp_path):
    first, second = stores
    before_a, before_b = snapshot(first), snapshot(second)
    check = storage.inspect_postgres_storage(first)
    assert check["scope"] == "agent" and check["maintenance_supported"]
    assert check["cleanup_preview"]["total"] == 2
    assert (
        next(row for row in check["namespace_tables"] if row["table"] == "candidates")["rows"] == 5
    )
    assert snapshot(first) == before_a  # Inspection is read-only.
    phases = []

    def progress(value):
        phases.append(value["phase"])
        if value["phase"] == "cleaning":
            # Locks for A are still held here. Read/write identical IDs in B.
            with storage._connect(second) as conn, conn.cursor() as cur:
                cur.execute("SET LOCAL lock_timeout = '500ms'")
                cur.execute(
                    "UPDATE octop_memory.journal SET note = 'concurrent write' "
                    "WHERE namespace = %s AND id = 'expired'",
                    (second._ns,),
                )
                assert cur.rowcount == 1

    backup = tmp_path / "rows.jsonl"
    report = storage.maintain_postgres_storage(first, backup=backup, progress=progress)
    assert report["candidates_deleted"] == report["journal_deleted"] == 1
    assert not report["physical_space_reclaimed"]
    assert phases == ["inspecting", "backing_up", "cleaning"]
    lines = [json.loads(line) for line in backup.read_text().splitlines()]
    assert lines[0]["namespace"] == first._ns and lines[0]["rows"] == 2
    assert {line["table"] for line in lines[1:]} == {"candidates", "journal"}
    assert all(line["row"]["namespace"] == first._ns for line in lines[1:])
    assert all("fts_tsv" not in line["row"] for line in lines[1:])
    for table in ("candidates", "journal"):
        before_a[table] = [row for row in before_a[table] if row["id"] != "expired"]
    for row in before_b["journal"]:
        if row["id"] == "expired":
            row["note"] = "concurrent write"
    assert snapshot(first) == before_a
    assert snapshot(second) == before_b
    noop = storage.maintain_postgres_storage(
        first, backup=tmp_path / "noop.jsonl", progress=lambda _: None
    )
    assert noop["total_deleted"] == 0 and noop["backup_path"] is None
    assert not (tmp_path / "noop.jsonl").exists()


def test_backup_failure_deletes_nothing(stores, tmp_path, monkeypatch):
    first, second = stores
    before = snapshot(first), snapshot(second)

    def disk_full(_fd):
        raise OSError("disk full")

    monkeypatch.setattr(storage.os, "fsync", disk_full)
    backup = tmp_path / "partial.jsonl"
    with pytest.raises(OSError, match="disk full"):
        storage.maintain_postgres_storage(first, backup=backup, progress=lambda _: None)
    assert (snapshot(first), snapshot(second)) == before
    assert not backup.exists()


def test_sql_failure_rolls_back_both_tables_and_retains_backup(stores, tmp_path):
    from psycopg import errors, sql

    first, second = stores
    before = snapshot(first), snapshot(second)
    name = "fail_cleanup_" + uuid.uuid4().hex
    with storage._connect(first) as conn, conn.cursor() as cur:
        cur.execute(
            sql.SQL(
                "CREATE FUNCTION public.{}() RETURNS trigger LANGUAGE plpgsql AS $$ "
                "BEGIN IF OLD.namespace = {} THEN RAISE EXCEPTION 'test rollback'; "
                "END IF; RETURN OLD; END $$"
            ).format(sql.Identifier(name), sql.Literal(first._ns))
        )
        cur.execute(
            sql.SQL(
                "CREATE TRIGGER {} BEFORE DELETE ON octop_memory.journal "
                "FOR EACH ROW EXECUTE FUNCTION public.{}()"
            ).format(sql.Identifier(name), sql.Identifier(name))
        )
    backup = tmp_path / "rollback.jsonl"
    try:
        with pytest.raises(errors.RaiseException, match="test rollback"):
            storage.maintain_postgres_storage(first, backup=backup, progress=lambda _: None)
        assert (snapshot(first), snapshot(second)) == before
        assert len(backup.read_text().splitlines()) == 3
    finally:
        with storage._connect(first) as conn, conn.cursor() as cur:
            cur.execute(
                sql.SQL("DROP TRIGGER {} ON octop_memory.journal").format(sql.Identifier(name))
            )
            cur.execute(sql.SQL("DROP FUNCTION public.{}()").format(sql.Identifier(name)))


def test_namespace_lock_and_busy_rows_do_not_block_other_experts(stores, tmp_path):
    first, second = stores
    with storage._connect(first) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"octop:memory-maintenance:{first._ns}",),
        )
        with pytest.raises(ValueError):
            storage.maintain_postgres_storage(
                first, backup=tmp_path / "blocked.jsonl", progress=lambda _: None
            )
        report = storage.maintain_postgres_storage(
            second, backup=tmp_path / "other.jsonl", progress=lambda _: None
        )
        assert report["total_deleted"] == 2
    with storage._connect(first) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM octop_memory.candidates WHERE namespace = %s AND id = 'expired' FOR UPDATE",
            (first._ns,),
        )
        report = storage.maintain_postgres_storage(
            first, backup=tmp_path / "skip.jsonl", progress=lambda _: None
        )
        assert report["candidates_deleted"] == 0 and report["journal_deleted"] == 1
    assert first.get_candidate("expired") is not None


def test_each_pass_is_bounded(stores, tmp_path, monkeypatch):
    first, _ = stores
    monkeypatch.setattr(storage, "LIMIT_PER_TABLE", 2)
    for i in range(4):
        first.append_journal(
            JournalEntry(
                id=f"old_{i}",
                timestamp=datetime.now(UTC) - timedelta(days=60),
                action="extract_run",
                actor="auto",
            )
        )
    assert storage.inspect_postgres_storage(first)["cleanup_preview"]["journal"] == 2
    report = storage.maintain_postgres_storage(
        first, backup=tmp_path / "bounded.jsonl", progress=lambda _: None
    )
    assert report["journal_deleted"] == 2 and report["candidates_deleted"] == 1
    assert storage.inspect_postgres_storage(first)["cleanup_preview"]["journal"] == 2


@pytest.mark.asyncio
async def test_http_job_waits_only_for_current_expert_and_preserves_checkpoints(
    env_with_main_agent, monkeypatch, tmp_path
):
    from langgraph.checkpoint.base import empty_checkpoint

    client, srv, auth, aid = env_with_main_agent
    registry = srv.app_runtime.agent_registry
    memory = Memory(memory_namespace(aid), backend="postgres", backend_config={"dsn": DSN})
    seed(memory.backend)
    checkpoint = empty_checkpoint()
    checkpoint["channel_values"] = {"memory_contents": {"USER.md": "keep full history"}}
    checkpoint["channel_versions"] = {"memory_contents": "1"}
    thread = "maintenance_test_" + uuid.uuid4().hex
    cfg = memory.put(
        {"configurable": {"thread_id": thread, "checkpoint_ns": ""}},
        checkpoint,
        {},
        {"memory_contents": "1"},
    )
    monkeypatch.setattr(
        registry,
        "get_agent",
        lambda _: SimpleNamespace(_memory_runtime=SimpleNamespace(memory=memory)),
    )
    base = f"/api/agents/{aid}/memory/storage"
    try:
        check = await client.get(base + "/check", headers=auth)
        assert check.status_code == 200, check.text
        assert check.json()["namespace"] == memory_namespace(aid)
        assert check.json()["cleanup_preview"]["total"] == 2
        await registry._begin_invocation(aid)
        response = await client.post(base + "/maintenance", headers=auth, json={"confirmed": True})
        assert response.status_code == 202, response.text
        await asyncio.sleep(0.02)
        assert registry.memory_slim.state["phase"] == "waiting"
        await asyncio.wait_for(registry._begin_invocation("different_expert"), timeout=1)
        registry._end_invocation("different_expert")
        registry._end_invocation(aid)
        await registry.memory_slim.task
        status = await client.get(base + "/maintenance", headers=auth)
        job = status.json()["job"]
        assert job["phase"] == "done", job
        assert job["backend"] == "postgres"
        assert job["report"]["total_deleted"] == 2
        assert memory.get_tuple(cfg).checkpoint == checkpoint
        assert not registry._history_backfills
    finally:
        memory.delete_thread(thread)
        memory.backend.purge_namespace()
        memory.backend.close()
        if memory._checkpointer_pool:
            memory._checkpointer_pool.close()
