"""Lossless checkpoint storage, mixed formats and offline migration behavior."""

from __future__ import annotations

import asyncio
import copy
import json
import sqlite3
import tracemalloc
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated, TypedDict

import pytest
from click.testing import CliRunner
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command, interrupt

from octop_memory.adapters.cli import main
from octop_memory.application.checkpoint_maintenance import maintain_checkpoints, slim_live_checkpoints
from octop_memory.core import Memory
from octop_memory.storage.backends.sqlite_checkpoint import FORMAT, CompactSqliteSaver
from octop_memory.storage.backends.sqlite_checkpoint_maintenance import migrate_checkpoints


def checkpoint(index=1, text="original"):
    cp = empty_checkpoint()
    cp["id"] = f"{index:08d}"
    cp["ts"] = "2026-09-07T00:00:00+00:00"
    cp["channel_values"] = {
        "skills_metadata": [{"name": "skill", "description": text * 1800}],
        "memory_contents": {"AGENTS.md": text * 1200},
        "counter": index,
    }
    cp["channel_versions"] = dict.fromkeys(cp["channel_values"], index)
    return cp


def config(thread="t", ns=""):
    return {"configurable": {"thread_id": thread, "checkpoint_ns": ns}}


@pytest.fixture
def saver(tmp_path):
    conn = sqlite3.connect(tmp_path / "memory.sqlite", check_same_thread=False)
    instance = CompactSqliteSaver(conn)
    instance.setup()
    yield instance
    conn.close()


def seed_old(path, count=20):
    with sqlite3.connect(path) as conn:
        old = SqliteSaver(conn)
        cfg = config()
        for i in range(1, count + 1):
            cp = checkpoint(i)
            cfg = old.put(cfg, cp, {"source": "loop", "step": i}, cp["channel_versions"])
    conn.close()


def test_reuse_history_and_mutable_isolation(saver):
    original = checkpoint()
    untouched = copy.deepcopy(original)
    cfg1 = saver.put(config(), original, {"source": "input", "step": 0}, {})
    cfg2 = saver.put(cfg1, checkpoint(2), {"source": "loop", "step": 1}, {})
    cfg3 = saver.put(cfg2, checkpoint(3, "changed"), {"source": "loop", "step": 2}, {})
    assert original == untouched
    assert saver.conn.execute("SELECT COUNT(*) FROM hm_checkpoint_blobs").fetchone()[0] == 4
    for cfg, expected in ((cfg1, original), (cfg2, checkpoint(2)), (cfg3, checkpoint(3, "changed"))):
        assert saver.get_tuple(cfg).checkpoint == expected
    read = saver.get_tuple(cfg1)
    read.checkpoint["channel_values"]["skills_metadata"][0]["name"] = "mutated by caller"
    assert saver.get_tuple(cfg1).checkpoint == original
    listed = list(saver.list(config(), before=cfg3, limit=1, filter={"step": 1}))
    assert [item.checkpoint for item in listed] == [checkpoint(2)]
    assert listed[0].parent_config == cfg1


def test_serializer_rebind_uses_new_connection_and_independent_cache(saver, tmp_path):
    cfg = saver.put(config(), checkpoint(), {}, {})
    saver.get_tuple(cfg)  # Warm the live reader's cache.
    path = tmp_path / "snapshot.sqlite"
    with sqlite3.connect(path) as target:
        saver.conn.backup(target)
    conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    try:
        codec = saver.codec.with_connection(conn)
        assert codec.base is saver.codec.base
        assert not codec.cache
        assert codec.cache is not saver.codec.cache
        saver.conn.set_authorizer(lambda *_: sqlite3.SQLITE_DENY)
        kind, payload = conn.execute("SELECT type, checkpoint FROM checkpoints").fetchone()
        assert codec.loads_typed((kind, payload)) == checkpoint()
        assert codec.cache
    finally:
        saver.conn.set_authorizer(None)
        conn.close()


@pytest.mark.parametrize("value", [None, [], {}, "", {"__ref__": "ordinary user content"}])
def test_small_empty_values_stay_exact(saver, value):
    cp = checkpoint()
    cp["channel_values"] = {"memory_contents": value}
    cfg = saver.put(config(), cp, {}, {})
    assert saver.get_tuple(cfg).checkpoint == cp
    assert saver.conn.execute("SELECT type FROM checkpoints").fetchone()[0] != FORMAT


def test_missing_channel_is_not_reintroduced(saver):
    cp = checkpoint()
    del cp["channel_values"]["skills_metadata"]
    cfg = saver.put(config(), cp, {}, {})
    assert saver.get_tuple(cfg).checkpoint == cp


def test_old_rows_mixed_with_new_and_switch_off(saver):
    old = SqliteSaver(saver.conn)
    cfg1 = old.put(config(), checkpoint(1), {}, {})
    cfg2 = saver.put(cfg1, checkpoint(2), {}, {})
    saver.compact = False
    cfg3 = saver.put(cfg2, checkpoint(3), {}, {})
    assert [t.checkpoint for t in saver.list(config())] == [checkpoint(i) for i in (3, 2, 1)]
    assert [r[0] for r in saver.conn.execute("SELECT type FROM checkpoints ORDER BY checkpoint_id")] == [
        "msgpack",
        FORMAT,
        "msgpack",
    ]
    reopened = CompactSqliteSaver(saver.conn, compact=False)
    assert reopened.get_tuple(cfg2).checkpoint == checkpoint(2)
    assert reopened.get_tuple(cfg3).parent_config == cfg2


def test_failed_checkpoint_rolls_back_content_and_previous_row(saver):
    cfg = saver.put(config(), checkpoint(), {}, {})
    saver.conn.execute(
        "CREATE TRIGGER reject_checkpoint BEFORE INSERT ON checkpoints BEGIN SELECT RAISE(ABORT, 'injected'); END"
    )
    with pytest.raises(sqlite3.IntegrityError, match="injected"):
        saver.put(cfg, checkpoint(2, "new-content"), {}, {})
    assert saver.conn.execute("SELECT COUNT(*) FROM hm_checkpoint_blobs").fetchone()[0] == 2
    assert saver.get_tuple(config()).checkpoint == checkpoint()
    assert not saver.conn.in_transaction


def test_failed_writes_are_atomic(saver):
    cfg = saver.put(config(), checkpoint(), {}, {})
    saver.conn.execute(
        "CREATE TRIGGER reject_write BEFORE INSERT ON writes WHEN NEW.idx = 1 "
        "BEGIN SELECT RAISE(ABORT, 'injected'); END"
    )
    with pytest.raises(sqlite3.IntegrityError, match="injected"):
        saver.put_writes(cfg, [("counter", 1), ("counter", 2)], "task")
    assert saver.get_tuple(cfg).pending_writes == []


@pytest.mark.parametrize(
    "corruption", ["DELETE FROM hm_checkpoint_blobs", "UPDATE hm_checkpoint_blobs SET value = x'00'"]
)
def test_missing_or_corrupt_content_fails_closed(saver, corruption):
    cfg = saver.put(config(), checkpoint(), {}, {})
    saver.conn.execute(corruption)
    saver.conn.commit()
    with pytest.raises(ValueError, match="checkpoint content"):
        saver.get_tuple(cfg)


def test_concurrent_puts_do_not_mix_fields(saver):
    def write(i):
        cp = checkpoint(i, str(i))
        cfg = saver.put(config(str(i)), cp, {}, {})
        assert saver.get_tuple(cfg).checkpoint == cp

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(write, range(1, 41)))
    assert saver.conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0] == 40


def test_delta_history_uses_decoding_serializer(saver):
    cp1 = checkpoint(1)
    cp1["channel_values"]["messages"] = ["seed"]
    cfg1 = saver.put(config(), cp1, {}, {})
    saver.put_writes(cfg1, [("messages", ["next"])], "task")
    cfg2 = saver.put(cfg1, checkpoint(2), {}, {})
    history = saver.get_delta_channel_history(config=cfg2, channels=["messages"])
    assert history["messages"]["seed"] == ["seed"]
    assert any(w[2] == ["next"] for w in history["messages"]["writes"])


class GraphState(TypedDict):
    messages: Annotated[list, add_messages]
    skills_metadata: list
    memory_contents: dict
    approved: str


@pytest.mark.asyncio
async def test_memory_async_interrupt_resume_and_restart(tmp_path):
    path = tmp_path / "graph.sqlite"
    memory = Memory(namespace="graph", backend_config={"db_path": str(path)})
    builder = StateGraph(GraphState)

    def ask(state):
        answer = interrupt("approve")
        return {"approved": answer, "messages": [("ai", "done")]}

    builder.add_node("ask", ask)
    builder.add_edge(START, "ask")
    builder.add_edge("ask", END)
    graph = builder.compile(checkpointer=memory)
    state = checkpoint()["channel_values"]
    state.pop("counter")
    state["messages"] = [("human", "hello")]
    await graph.ainvoke(state, config())
    paused = await graph.aget_state(config())
    assert paused.tasks[0].interrupts
    memory._checkpointer.conn.close()
    memory.backend.close()
    memory2 = Memory(namespace="graph", backend_config={"db_path": str(path)})
    try:
        graph2 = builder.compile(checkpointer=memory2)
        resumed = await graph2.ainvoke(Command(resume="yes"), config())
        assert resumed["approved"] == "yes"
        assert [m.content for m in resumed["messages"]] == ["hello", "done"]
        assert resumed["skills_metadata"] == state["skills_metadata"]
        assert resumed["memory_contents"] == state["memory_contents"]
        history = [cp async for cp in memory2.alist(config())]
        assert len(history) >= 3
    finally:
        memory2._checkpointer.conn.close()
        memory2.backend.close()


@pytest.mark.asyncio
async def test_cancelled_async_write_finishes_atomically(tmp_path, monkeypatch):
    import threading

    memory = Memory(namespace="cancel", backend_config={"db_path": str(tmp_path / "cancel.sqlite")})
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    put = memory._checkpointer.put

    def slow_put(*args):
        entered.set()
        release.wait(5)
        try:
            return put(*args)
        finally:
            finished.set()

    monkeypatch.setattr(memory._checkpointer, "put", slow_put)
    task = asyncio.create_task(memory.aput(config(), checkpoint(), {}, {}))
    await asyncio.to_thread(entered.wait, 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    release.set()
    await asyncio.to_thread(finished.wait, 5)
    assert memory.get_tuple(config()).checkpoint == checkpoint()
    memory._checkpointer.conn.close()
    memory.backend.close()


def test_migration_preview_apply_resume_expand_and_reclaim(tmp_path):
    path = tmp_path / "old.sqlite"
    seed_old(path, count=100)
    original_bytes = path.read_bytes()
    preview = maintain_checkpoints(path)
    assert preview["stats"]["rewritten"] == 100
    assert path.read_bytes() == original_bytes
    with sqlite3.connect(path) as conn:
        assert not conn.execute("SELECT name FROM sqlite_master WHERE name='hm_checkpoint_blobs'").fetchall()
    report = maintain_checkpoints(
        path, apply=True, offline=True, backup=tmp_path / "backup.sqlite", batch_size=7, vacuum=True
    )
    assert report["stats"]["rewritten"] == 100
    assert report["after"]["file_bytes"] < report["before"]["file_bytes"] * 0.2
    with sqlite3.connect(path) as conn:
        saver = CompactSqliteSaver(conn)
        assert [t.checkpoint for t in saver.list(config())] == [checkpoint(i) for i in range(100, 0, -1)]
    assert maintain_checkpoints(path)["stats"]["rewritten"] == 0
    maintain_checkpoints(path, apply=True, offline=True, backup=tmp_path / "compact-backup.sqlite", expand=True)
    with sqlite3.connect(path) as conn:
        assert [t.checkpoint for t in SqliteSaver(conn).list(config())] == [checkpoint(i) for i in range(100, 0, -1)]
        assert conn.execute("SELECT COUNT(*) FROM hm_checkpoint_blobs").fetchone()[0] == 0


def test_migration_failed_batch_can_resume(tmp_path):
    path = tmp_path / "old.sqlite"
    seed_old(path, count=6)
    with sqlite3.connect(path) as conn:
        saver = CompactSqliteSaver(conn)
        saver.setup()
        conn.execute(
            "CREATE TRIGGER fail_batch BEFORE UPDATE ON checkpoints WHEN NEW.checkpoint_id = '00000004' "
            "BEGIN SELECT RAISE(ABORT, 'injected'); END"
        )
        with pytest.raises(sqlite3.IntegrityError, match="injected"):
            migrate_checkpoints(saver, apply=True, batch_size=2)
        assert conn.execute("SELECT COUNT(*) FROM checkpoints WHERE type = ?", (FORMAT,)).fetchone()[0] == 2
        conn.execute("DROP TRIGGER fail_batch")
        report = migrate_checkpoints(saver, apply=True, batch_size=2)
        assert report.rewritten == 4
        assert len(list(saver.list(config()))) == 6


def test_prune_preserves_protected_snapshot_and_resume_boundary(tmp_path):
    path = tmp_path / "old.sqlite"
    seed_old(path, count=10)
    report = maintain_checkpoints(
        path,
        apply=True,
        offline=True,
        backup=tmp_path / "before.sqlite",
        completed_threads=("t",),
        keep_last=2,
        protected_ids=("00000003",),
    )
    assert report["stats"]["checkpoints_deleted"] == 7
    with sqlite3.connect(path) as conn:
        kept = list(CompactSqliteSaver(conn).list(config()))
        assert [t.checkpoint["id"] for t in kept] == ["00000010", "00000009", "00000003"]
        assert kept[1].parent_config is None
        assert kept[2].parent_config is None


def test_prune_memory_does_not_scale_with_repeated_body_bytes(tmp_path):
    from octop_memory.storage.backends.sqlite_checkpoint_maintenance import MigrationStats, prune_completed_threads

    with sqlite3.connect(tmp_path / "large.sqlite") as conn:
        saver = CompactSqliteSaver(conn)
        cfg = config()
        for i in range(1, 1001):
            cp = checkpoint(i)
            cp["channel_values"]["memory_contents"] = {"AGENTS.md": "x" * 32768}
            cfg = saver.put(cfg, cp, {}, {})
        stats = MigrationStats()
        tracemalloc.start()
        try:
            prune_completed_threads(saver, stats, completed_threads=("t",), keep_last=2)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        # Retaining 1,000 decoded copies of just AGENTS.md exceeds 31 MiB.
        # Leave ample room for dependency IDs and the bounded encoded cache.
        assert peak < 8 * 1024 * 1024
        assert stats.checkpoints_deleted == 998
        assert conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0] == 1000
    conn.close()


@pytest.mark.parametrize("unsafe", ["delta", "pending", "subgraph", "cycle"])
def test_prune_retains_unknown_dependencies(tmp_path, unsafe):
    path = tmp_path / "old.sqlite"
    seed_old(path, count=5)
    with sqlite3.connect(path) as conn:
        saver = SqliteSaver(conn)
        cfg = {"configurable": {**config()["configurable"], "checkpoint_id": "00000005"}}
        if unsafe == "pending":
            saver.put_writes(cfg, [("__interrupt__", ["approval"])], "task")
        elif unsafe == "subgraph":
            saver.put(config(ns="tools:sub"), checkpoint(6), {}, {})
        else:
            for cp in list(saver.list(config())):
                del cp.checkpoint["channel_values"]["memory_contents"]
                parent = cp.parent_config or config()
                if unsafe == "cycle" and cp.checkpoint["id"] == "00000001":
                    parent = cfg
                saver.put(parent, cp.checkpoint, cp.metadata, {})
    report = maintain_checkpoints(path, completed_threads=("t",), keep_last=1)
    assert report["stats"]["checkpoints_deleted"] == 0
    assert "t" in report["stats"]["skipped_threads"]


def test_cli_guards_and_read_only_preview(tmp_path):
    path = tmp_path / "old.sqlite"
    seed_old(path, count=2)
    runner = CliRunner()
    base = ["--db", str(path), "db", "checkpoints"]
    assert runner.invoke(main, [*base, "--apply"]).exit_code != 0
    assert runner.invoke(main, ["--backend", "postgres", "db", "checkpoints"]).exit_code != 0
    result = runner.invoke(main, base)
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["stats"]["dry_run"]
    backup = tmp_path / "existing-backup"
    backup.write_text("keep")
    result = runner.invoke(main, [*base, "--apply", "--offline", "--backup", str(backup)])
    assert result.exit_code != 0
    assert backup.read_text() == "keep"


def test_slim_preview_is_read_only_and_does_not_create_backup(tmp_path):
    path = tmp_path / "memory.sqlite"
    seed_old(path, count=3)
    original = path.read_bytes()
    result = CliRunner().invoke(main, ["--backend", "sqlite", "db", "slim", str(path)])
    assert result.exit_code == 0, result.output
    assert "eligible for deduplication: 3" in result.output
    assert "not a file-size forecast" in result.output
    assert path.read_bytes() == original
    assert not list(tmp_path.glob("*.bak"))


def test_live_migration_preserves_reader_snapshot_and_concurrent_writer(tmp_path):
    path = tmp_path / "memory.sqlite"
    seed_old(path, count=6)
    reader = sqlite3.connect(path)
    snapshot = list(SqliteSaver(reader).list(config()))
    reader.execute("BEGIN")
    snapshot_rows = reader.execute("SELECT * FROM checkpoints ORDER BY checkpoint_id").fetchall()
    phases = []
    changed = False

    def progress(status):
        nonlocal changed
        phases.append(status["phase"])
        if status["phase"] == "deduplicating" and status["scanned"] == 2:
            # A separate writer changes a later row and appends a new checkpoint
            # between batches. The migration must neither overwrite it nor chase
            # an unbounded stream of newly inserted rows.
            with sqlite3.connect(path) as conn:
                writer = CompactSqliteSaver(conn)
                writer.put(config(), checkpoint(5, text="newer"), {}, {})
                writer.put(config(), checkpoint(7), {}, {})
            changed = True
            assert reader.execute("SELECT * FROM checkpoints ORDER BY checkpoint_id").fetchall() == snapshot_rows
        if status["phase"] == "compacting":
            reader.rollback()

    try:
        report = slim_live_checkpoints(path, backup=tmp_path / "backup.sqlite", batch_size=2, progress=progress)
    finally:
        reader.close()
    assert changed
    assert phases[0] == "backing_up" and phases[-1] == "compacting"
    # INSERT OR REPLACE moved row 5 past the high-water mark; the new-format
    # replacement and appended row 7 are left to the live writer.
    assert report["stats"]["scanned"] == 5
    assert report["stats"]["checkpoints_deleted"] == report["stats"]["writes_deleted"] == 0
    with sqlite3.connect(path) as conn:
        tuples = list(CompactSqliteSaver(conn).list(config()))
        assert len(tuples) == 7
        assert tuples[2].checkpoint == checkpoint(5, text="newer")
    with sqlite3.connect(tmp_path / "backup.sqlite") as conn:
        assert list(SqliteSaver(conn).list(config())) == snapshot


def test_live_migration_failure_leaves_mixed_history_readable_and_backup(tmp_path):
    path = tmp_path / "memory.sqlite"
    seed_old(path, count=6)
    with sqlite3.connect(path) as conn:
        snapshot = list(SqliteSaver(conn).list(config()))
        conn.execute(
            "CREATE TRIGGER fail_live BEFORE UPDATE ON checkpoints WHEN NEW.checkpoint_id = '00000004' "
            "BEGIN SELECT RAISE(ABORT,'injected'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="injected"):
        slim_live_checkpoints(path, backup=tmp_path / "backup.sqlite", batch_size=2)
    with sqlite3.connect(path) as conn:
        assert list(CompactSqliteSaver(conn).list(config())) == snapshot
        assert conn.execute("SELECT count(*) FROM checkpoints WHERE type=?", (FORMAT,)).fetchone()[0] == 2
    assert (tmp_path / "backup.sqlite").exists()
    with pytest.raises(ValueError, match="SQLite-only"):
        slim_live_checkpoints(path, backend="postgres", backup=tmp_path / "unused.sqlite")


def test_live_long_reader_reports_unreclaimed_wal_without_losing_history(tmp_path):
    path = tmp_path / "memory.sqlite"
    seed_old(path, count=3)
    reader = sqlite3.connect(path)
    reader.execute("BEGIN")
    reader.execute("SELECT checkpoint FROM checkpoints").fetchall()
    try:
        with pytest.raises(ValueError, match="live reader still holds WAL"):
            slim_live_checkpoints(path, backup=tmp_path / "backup.sqlite")
    finally:
        reader.close()
    with sqlite3.connect(path) as conn:
        assert [t.checkpoint for t in CompactSqliteSaver(conn).list(config())] == [checkpoint(i) for i in (3, 2, 1)]
    assert (tmp_path / "backup.sqlite").exists()


def test_slim_backs_up_and_preserves_full_history_and_business_data(tmp_path):
    path = tmp_path / "memory.sqlite"
    seed_old(path, count=40)
    with sqlite3.connect(path) as conn:
        old = SqliteSaver(conn)
        head = old.get_tuple(config()).config
        old.put_writes(head, [("messages", "pending tool result")], "task")
        original = list(old.list(config()))
        conn.execute("CREATE TABLE business_records (value TEXT)")
        conn.execute("INSERT INTO business_records VALUES ('keep me')")
    runner = CliRunner()
    args = ["--backend", "sqlite", "--json", "db", "slim", str(path), "--apply", "--offline"]
    result = runner.invoke(main, args)
    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    backup = report["backup_path"]
    with sqlite3.connect(backup) as conn:
        assert list(SqliteSaver(conn).list(config())) == original
    with sqlite3.connect(path) as conn:
        assert list(CompactSqliteSaver(conn).list(config())) == original
        assert conn.execute("SELECT value FROM business_records").fetchall() == [("keep me",)]
    assert report["after"]["file_bytes"] < report["before"]["file_bytes"]
    assert report["stats"]["checkpoints_deleted"] == report["stats"]["writes_deleted"] == 0
    # A second run is idempotent and retains the first backup under its old name.
    second = runner.invoke(main, args)
    assert second.exit_code == 0, second.output
    second_report = json.loads(second.stdout)
    assert second_report["backup_path"] != backup
    assert second_report["stats"]["rewritten"] == 0
    assert len(list(tmp_path.glob("*.bak"))) == 2


def test_slim_rejects_missing_offline_and_postgres_without_mutation(tmp_path):
    path = tmp_path / "memory.sqlite"
    seed_old(path, count=2)
    original = path.read_bytes()
    runner = CliRunner()
    for backend, flags in [("sqlite", ["--apply"]), ("sqlite", ["--offline"]), ("postgres", [])]:
        result = runner.invoke(main, ["--backend", backend, "db", "slim", str(path), *flags])
        assert result.exit_code != 0
    assert path.read_bytes() == original
    assert not list(tmp_path.glob("*.bak"))


def test_memory_switch_preserves_compatible_reader(tmp_path, monkeypatch):
    monkeypatch.setenv("OCTOP_MEMORY_CHECKPOINT_DEDUP", "0")
    memory = Memory(namespace="switch", backend_config={"db_path": str(tmp_path / "switch.sqlite")})
    try:
        memory.put(config(), checkpoint(), {}, {})
        assert memory._checkpointer.conn.execute("SELECT type FROM checkpoints").fetchone()[0] != FORMAT
    finally:
        memory._checkpointer.conn.close()
        memory.backend.close()


def test_parallel_subgraph_round_trip(saver):
    from langchain_core.messages import AIMessage

    def left(state):
        return {"messages": [AIMessage(content="left", id="left")]}

    def right(state):
        return {"messages": [AIMessage(content="right", id="right")]}

    child = StateGraph(GraphState)
    child.add_node("child", right)
    child.add_edge(START, "child")
    child.add_edge("child", END)
    parent = StateGraph(GraphState)
    parent.add_node("left", left)
    parent.add_node("right", child.compile())
    parent.add_edge(START, "left")
    parent.add_edge(START, "right")
    parent.add_edge("left", END)
    parent.add_edge("right", END)
    graph = parent.compile(checkpointer=saver)
    values = checkpoint()["channel_values"]
    del values["counter"]
    values["messages"] = []
    result = graph.invoke(values, config())
    assert sorted(m.content for m in result["messages"]) == ["left", "right"]
    assert result["memory_contents"] == values["memory_contents"]
    restored = parent.compile(checkpointer=CompactSqliteSaver(saver.conn)).get_state(config())
    assert restored.values == result
    assert saver.conn.execute("SELECT COUNT(*) FROM checkpoints WHERE checkpoint_ns != ''").fetchone()[0] > 0


def test_large_fields_cannot_evict_another_required_field(saver, monkeypatch):
    import octop_memory.storage.backends.sqlite_checkpoint as module

    monkeypatch.setattr(module, "CACHE_BYTES", 15000)
    cfg = saver.put(config(), checkpoint(), {}, {})
    for _ in range(3):
        assert saver.get_tuple(cfg).checkpoint == checkpoint()
        assert saver.codec.cache_size <= 15000


def test_unknown_format_and_protected_id_do_not_mutate_source(tmp_path):
    path = tmp_path / "bad.sqlite"
    seed_old(path, count=2)
    original = path.read_bytes()
    with pytest.raises(ValueError, match="protected checkpoint"):
        maintain_checkpoints(path, apply=True, offline=True, backup=tmp_path / "b.sqlite", protected_ids=("absent",))
    assert path.read_bytes() == original
    assert not (tmp_path / "b.sqlite").exists()
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE checkpoints SET type='harness-checkpoint-v999'")
    original = path.read_bytes()
    with pytest.raises(ValueError, match="Unsupported checkpoint format"):
        maintain_checkpoints(path, apply=True, offline=True, backup=tmp_path / "b.sqlite")
    assert path.read_bytes() == original


def test_migration_preserves_other_memory_tables(tmp_path):
    path = tmp_path / "old.sqlite"
    seed_old(path, count=3)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE unrelated_memory (content TEXT)")
        conn.execute("INSERT INTO unrelated_memory VALUES ('keep memory')")
    maintain_checkpoints(path, apply=True, offline=True, backup=tmp_path / "b.sqlite", vacuum=True)
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT content FROM unrelated_memory").fetchall() == [("keep memory",)]
