"""Startup-only import of the old archive into the v1 read models."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, message_to_dict
from langgraph.checkpoint.base import empty_checkpoint
from octop_memory import Memory
from octop_memory.pipeline.lifecycle.checkpoint_gc import prune_checkpoints

from octop.config import OctopConfig
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.thread_messages import ThreadMessageRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.trajectory_events import TrajectoryEventRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.history.projection import message_inputs
from octop.infra.history.retire_v2 import ARCHIVE_NAME, MARKER_NAME, migrate_history_v2
from octop.infra.utils.paths import PathLayout

_SCHEMA = """
CREATE TABLE archive_meta (version INTEGER, identity TEXT);
INSERT INTO archive_meta VALUES (1, 'original-host');
CREATE TABLE segments (id INTEGER PRIMARY KEY, thread_id TEXT, agent_id TEXT, format TEXT,
 legacy_start INTEGER, legacy_end INTEGER, anchor TEXT, trajectory_start INTEGER, trajectory_end INTEGER);
CREATE TABLE turns (id TEXT PRIMARY KEY, segment_id INTEGER);
CREATE TABLE documents (id TEXT PRIMARY KEY, thread_id TEXT, turn_id TEXT, kind TEXT, seq INTEGER, data TEXT);
CREATE TABLE bodies (digest TEXT PRIMARY KEY, value TEXT);
"""


@pytest.fixture
def stores(tmp_octop_home: Path):
    paths = PathLayout(tmp_octop_home)
    pool = SqlitePool(paths.db)
    run_migrations(pool)
    user_id = UserRepo(pool).create(username="test", password_hash="x", role="user")
    cfg = {
        "workspace_dir": str(paths.root),
        "memory": {"backend": {"db_path": str(paths.root / "memory.sqlite")}},
    }
    agents = AgentRepo(pool)
    agents.create(agent_id="agent", user_id=user_id, name="Agent", config_json=json.dumps(cfg))
    agents.set_state("agent", "stopped")
    threads = ThreadRepo(pool)
    for tid in ("a", "b"):
        threads.insert(
            thread_id=tid,
            agent_id="agent",
            user_id=user_id,
            channel_type="dashboard",
            session_key=tid,
            last_active=0,
        )
    registry = SimpleNamespace(
        get_row=agents.get, get_config=lambda _: cfg, octop_config=OctopConfig()
    )
    with closing(sqlite3.connect(paths.root / ARCHIVE_NAME)) as conn, conn:
        conn.executescript(_SCHEMA)
    (paths.root / MARKER_NAME).write_text("required", encoding="utf-8")
    yield paths, pool, registry
    pool.close()


def _segment(conn, segment_id, thread_id, fmt, *, start=0, end=None, anchor=None):
    conn.execute(
        "INSERT INTO segments VALUES (?,?,'agent',?,?,?,?,0,NULL)",
        (
            segment_id,
            thread_id,
            fmt,
            start,
            end,
            json.dumps({"checkpoint_config": anchor}) if anchor else None,
        ),
    )
    conn.execute("INSERT INTO turns VALUES (?,?)", (f"turn-{segment_id}", segment_id))


def _document(conn, thread_id, segment_id, kind, seq, value):
    conn.execute(
        "INSERT INTO documents VALUES (?,?,?,?,?,?)",
        (
            f"{kind}-{thread_id}-{seq}",
            thread_id,
            f"turn-{segment_id}",
            kind,
            seq,
            json.dumps(value),
        ),
    )


def _wire_rows(pool, thread_id):
    rows, more = ThreadMessageRepo(pool).page(thread_id, limit=100)
    assert not more
    return [json.loads(row.message_json) for row in rows]


def _memory(paths):
    return Memory("agent_agent", backend_config={"db_path": str(paths.root / "memory.sqlite")})


def test_anchored_prefix_and_v2_documents_survive_prune_and_retry(stores, caplog):
    paths, pool, registry = stores
    old = HumanMessage(content="old prompt", id="old")
    new = AIMessage(content="new answer", id="new")
    memory = _memory(paths)
    checkpoint = empty_checkpoint()
    checkpoint["channel_values"]["messages"] = [old]
    anchor = memory.put({"configurable": {"thread_id": "a"}}, checkpoint, {}, {})
    for _ in range(7):
        memory.put({"configurable": {"thread_id": "a"}}, empty_checkpoint(), {}, {})
    try:
        with closing(sqlite3.connect(paths.root / ARCHIVE_NAME)) as conn, conn:
            _segment(conn, 1, "a", "legacy", anchor=anchor)
            _segment(conn, 2, "a", "v2")
            # Read a content-addressed body, the same representation used by export_messages.
            conn.execute(
                "INSERT INTO bodies VALUES (?,?)", ("body", json.dumps(message_to_dict(new)))
            )
            _document(conn, "a", 2, "message", 1, ["body", "body"])
            event = {
                "event_id": "event",
                "thread_id": "a",
                "agent_id": "agent",
                "seq": 1,
                "ts": 5.0,
                "kind": "tool",
                "payload": {"content": "result"},
                "summary": "tool",
            }
            _document(conn, "a", 2, "event", 1, ["value", event])
            _document(conn, "a", 2, "event", 2, ["body", "missing"])

        migrate_history_v2(paths, pool, registry)
        expected = [message_to_dict(old), message_to_dict(new)]
        assert _wire_rows(pool, "a") == expected
        assert ThreadMessageRepo(pool).projection_status("a") == "ready"
        saved = TrajectoryEventRepo(pool).get("event")
        assert saved is not None and saved.payload == event["payload"]
        assert "event-a-2" in caplog.text and "archive body reference is missing" in caplog.text

        archived = list(paths.root.glob(f"{ARCHIVE_NAME}.migrated-*"))
        assert len(archived) == 1
        assert len(list(paths.root.glob(f"{MARKER_NAME}.migrated-*"))) == 1
        assert prune_checkpoints(memory, keep_last=3).checkpoints_deleted == 5
        assert memory.get_tuple(anchor) is None
        # Simulate a restart/retry after writing the projections and before moving the archive.
        archived[0].rename(paths.root / ARCHIVE_NAME)
        migrate_history_v2(paths, pool, registry)
        assert _wire_rows(pool, "a") == expected
        assert len(list(TrajectoryEventRepo(pool).iter_for_export("a"))) == 1
    finally:
        memory._checkpointer.conn.close()
        memory.backend.close()


def test_interleaved_legacy_rows_keep_order_and_only_insert_missing_bodies(stores):
    paths, pool, registry = stores
    prefix = HumanMessage(content="prefix", id="prefix")
    tail = HumanMessage(content="tail", id="tail")
    archived = AIMessage(content="archived", id="archived")
    projection = ThreadMessageRepo(pool)
    projection.replace_all("a", message_inputs([prefix, tail]))
    with pool.connect() as conn:
        original_ids = [
            row[0] for row in conn.execute("SELECT id FROM thread_messages ORDER BY seq")
        ]
    with closing(sqlite3.connect(paths.root / ARCHIVE_NAME)) as conn, conn:
        _segment(conn, 1, "a", "legacy", end=1)
        _segment(conn, 2, "a", "v2")
        _segment(conn, 3, "a", "legacy", start=1)
        _document(conn, "a", 2, "message", 1, ["value", message_to_dict(archived)])

    migrate_history_v2(paths, pool, registry)
    assert _wire_rows(pool, "a") == [message_to_dict(m) for m in (prefix, archived, tail)]
    with pool.connect() as conn:
        kept_ids = [
            row[0]
            for row in conn.execute(
                "SELECT id FROM thread_messages WHERE message_id IN ('prefix','tail') ORDER BY seq"
            )
        ]
    assert kept_ids == original_ids


@pytest.mark.asyncio
async def test_failed_thread_prevents_agent_boot_and_leaves_original_archive(stores, monkeypatch):
    from octop.infra.agents.manager import AgentManager
    from octop.infra.server import OctopServer

    paths, pool, _ = stores
    with closing(sqlite3.connect(paths.root / ARCHIVE_NAME)) as conn, conn:
        _segment(conn, 1, "a", "v2")
        _document(
            conn, "a", 1, "message", 1, ["value", message_to_dict(HumanMessage(content="ok"))]
        )
        _segment(
            conn,
            2,
            "b",
            "legacy",
            anchor={"configurable": {"thread_id": "b", "checkpoint_id": "lost"}},
        )
        _segment(conn, 3, "b", "v2")
    archive = paths.root / ARCHIVE_NAME
    marker = paths.root / MARKER_NAME
    original = archive.read_bytes(), marker.read_bytes()

    async def must_not_boot(self):
        raise AssertionError("agent maintenance must not start before all threads migrate")

    monkeypatch.setattr(AgentManager, "boot", must_not_boot)
    server = OctopServer(home=paths.root)
    with pytest.raises(ValueError, match="thread b: checkpoint anchor lost is unavailable"):
        await server.start(serve_background=False)
    assert (archive.read_bytes(), marker.read_bytes()) == original
    assert not list(paths.root.glob("*.migrated-*"))
    assert len(_wire_rows(pool, "a")) == 1
    assert _wire_rows(pool, "b") == []


@pytest.mark.asyncio
async def test_ignored_v2_settings_warn_once_and_do_not_prevent_startup(
    tmp_octop_home, monkeypatch, caplog
):
    from octop.config import _warn_retired_history_config, load_config
    from octop.infra.server import OctopServer

    _warn_retired_history_config.cache_clear()
    paths = PathLayout(tmp_octop_home)
    paths.config.write_text('{"history_v2_enabled": {"invalid": true}}', encoding="utf-8")
    monkeypatch.setenv("OCTOP_HISTORY_V2_ENABLED", "invalid")
    server = OctopServer(home=paths.root)
    try:
        await server.start(serve_background=False)
        assert not hasattr(load_config(paths.config), "history_v2_enabled")
        assert sum("are retired and ignored" in record.message for record in caplog.records) == 1
    finally:
        await server.stop()
        _warn_retired_history_config.cache_clear()


def test_offline_backup_restore_installs_legacy_archive_for_next_start(stores, tmp_path):
    import tarfile

    from octop.infra.backup.system_archive import create_system_backup, restore_system_backup
    from octop.infra.errors import OctopError

    paths, pool, registry = stores
    message = message_to_dict(HumanMessage(content="stored in the old archive", id="legacy"))
    with closing(sqlite3.connect(paths.root / ARCHIVE_NAME)) as conn, conn:
        _segment(conn, 1, "a", "v2")
        _document(conn, "a", 1, "message", 1, ["value", message])

    modern = tmp_path / "modern.tar.gz"
    db_config = OctopConfig().database
    create_system_backup(
        paths=paths, agent_rows=[], pool=pool, db_config=db_config, dest=modern, include_chats=True
    )
    legacy = tmp_path / "legacy.tar.gz"
    with tarfile.open(modern, "r:gz") as source, tarfile.open(legacy, "w:gz") as output:
        assert not any(
            ARCHIVE_NAME in member.name or MARKER_NAME in member.name for member in source
        )
        for member in source.getmembers():
            output.addfile(member, source.extractfile(member))
        for name in (ARCHIVE_NAME, MARKER_NAME):
            output.add(paths.root / name, arcname=f"history/{name}")

    destination = PathLayout(tmp_path / "restored")
    target = SqlitePool(destination.db)
    try:
        run_migrations(target)
        with pytest.raises(OctopError, match="Stop Octop"):
            restore_system_backup(
                legacy,
                paths=destination,
                pool=target,
                db_config=db_config,
                allow_legacy_history=False,
            )
        assert ThreadRepo(target).get("a") is None
        restore_system_backup(legacy, paths=destination, pool=target, db_config=db_config)
        assert (destination.root / ARCHIVE_NAME).is_file()
        assert (destination.root / MARKER_NAME).is_file()
        migrate_history_v2(destination, target, registry)
        assert _wire_rows(target, "a") == [message]
    finally:
        target.close()
