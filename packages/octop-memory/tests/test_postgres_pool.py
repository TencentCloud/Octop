"""Real PostgreSQL capacity, ownership and recovery regressions (Octop #2060)."""

from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from typing import Any

import pytest

psycopg = pytest.importorskip("psycopg")
pytest.importorskip("psycopg_pool")
pytest.importorskip("langgraph.checkpoint.postgres")

from langgraph.checkpoint.base import empty_checkpoint  # noqa: E402
from psycopg.conninfo import make_conninfo  # noqa: E402
from psycopg_pool import PoolClosed, PoolTimeout, TooManyRequests  # noqa: E402

from octop_memory import Memory  # noqa: E402
from octop_memory.storage.backends import postgres_pool  # noqa: E402


@pytest.fixture
def pool_dsn(postgres_dsn: str) -> str:
    return make_conninfo(postgres_dsn, application_name=f"pool_test_{uuid.uuid4().hex[:12]}")


def _sessions(admin: Any, dsn: str) -> int:
    app = psycopg.conninfo.conninfo_to_dict(dsn)["application_name"]
    return int(admin.execute("SELECT count(*) FROM pg_stat_activity WHERE application_name=%s", (app,)).fetchone()[0])


def _wait_for_sessions(admin: Any, dsn: str, expected: int = 0) -> None:
    # PQfinish closes the client socket synchronously. The remote backend
    # exits asynchronously, so its pg_stat_activity row can briefly remain.
    deadline = time.monotonic() + 5
    observed = _sessions(admin, dsn)
    while observed != expected and time.monotonic() < deadline:
        time.sleep(0.01)
        observed = _sessions(admin, dsn)
    assert observed == expected


def _close(memory: Memory) -> None:
    if memory._checkpointer_pool is not None:
        memory._checkpointer_pool.close()
    memory.backend.close()


def _memory(stack: ExitStack, dsn: str) -> Memory:
    memory = Memory(namespace=f"pool_{uuid.uuid4().hex[:12]}", backend="postgres", backend_config={"dsn": dsn})
    stack.callback(_close, memory)
    return memory


def test_69_agents_share_a_bounded_budget_under_mixed_load(pool_dsn: str, postgres_dsn: str) -> None:
    """69 warmed agents used 138 sessions and failed with max_connections=100."""
    with psycopg.connect(postgres_dsn, autocommit=True) as admin, ExitStack() as stack:
        memories = [_memory(stack, pool_dsn) for _ in range(69)]
        assert _sessions(admin, pool_dsn) <= postgres_pool.BUSINESS_POOL_SIZE

        def exercise(index: int) -> None:
            memory = memories[index]
            thread = f"pool-cp-{uuid.uuid4().hex}"
            config = {"configurable": {"thread_id": thread, "checkpoint_ns": ""}}
            node = memory.store(str(index), level="root")
            try:
                checkpoint = empty_checkpoint()
                checkpoint["channel_values"] = {"agent": index}
                checkpoint["channel_versions"] = {"agent": 1}
                saved = memory.put(config, checkpoint, {"source": "input", "step": 0}, {"agent": 1})
                for _ in range(3):
                    assert memory.get(node.id).content == str(index)
                    assert [item.content for item in memory.get_tree()] == [str(index)]
                    assert memory.get_tuple(saved).checkpoint["channel_values"] == {"agent": index}
            finally:
                memory.delete_thread(thread)
                memory.backend.purge_namespace()

        peak = 0
        with ThreadPoolExecutor(max_workers=8) as executor:
            tasks = [executor.submit(exercise, i) for i in range(69)]
            while not all(task.done() for task in tasks):
                peak = max(peak, _sessions(admin, pool_dsn))
                time.sleep(0.01)
            for task in tasks:
                task.result()
        assert peak <= postgres_pool.BUSINESS_POOL_SIZE + postgres_pool.CHECKPOINT_POOL_SIZE
        assert len({id(m.backend._pool._entry) for m in memories}) == 1
        assert len({id(m._checkpointer_pool._entry) for m in memories}) == 1
        stack.close()
        for memory in memories:
            for lease in (memory.backend._pool, memory._checkpointer_pool):
                assert lease.closed
                assert lease._entry.refs == 0
                assert lease._entry.pool.closed
        _wait_for_sessions(admin, pool_dsn)


def test_pool_exhaustion_times_out_then_recovers(pool_dsn: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(postgres_pool, "BUSINESS_POOL_SIZE", 2)
    with ExitStack() as stack:
        leases = [postgres_pool.acquire_pool(pool_dsn, purpose="business") for _ in range(3)]
        for lease in leases:
            stack.callback(lease.close)
        with leases[0].connection():
            with leases[1].connection(), pytest.raises(PoolTimeout), leases[2].connection(timeout=0.05):
                pytest.fail("a third session exceeded the shared budget")
            with leases[2].connection(timeout=1) as conn:
                assert conn.execute("SELECT 1 AS n").fetchone() == {"n": 1}
        assert leases[0].get_stats()["pool_size"] == 2


def test_waiting_queue_is_bounded(pool_dsn: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(postgres_pool, "BUSINESS_POOL_SIZE", 1)
    monkeypatch.setattr(postgres_pool, "POOL_MAX_WAITING", 1)
    with ExitStack() as stack:
        leases = [postgres_pool.acquire_pool(pool_dsn, purpose="business") for _ in range(3)]
        for lease in leases:
            stack.callback(lease.close)
        with ThreadPoolExecutor(max_workers=1) as executor:
            with leases[0].connection():

                def wait_for_slot() -> None:
                    with leases[1].connection(timeout=2):
                        pass

                waiter = executor.submit(wait_for_slot)
                deadline = time.monotonic() + 1
                while leases[0].get_stats()["requests_waiting"] != 1 and time.monotonic() < deadline:
                    time.sleep(0.005)
                assert leases[0].get_stats()["requests_waiting"] == 1
                with pytest.raises(TooManyRequests), leases[2].connection():
                    pytest.fail("unbounded admission")
            waiter.result(timeout=2)


def test_close_is_per_owner_idempotent_and_waits_for_query(pool_dsn: str, postgres_dsn: str) -> None:
    with psycopg.connect(postgres_dsn, autocommit=True) as admin, ExitStack() as stack:
        first = postgres_pool.acquire_pool(pool_dsn, purpose="checkpoint")
        second = postgres_pool.acquire_pool(pool_dsn, purpose="checkpoint")
        stack.callback(first.close)
        stack.callback(second.close)
        started = threading.Event()

        def close_first() -> None:
            started.set()
            first.close()

        with ThreadPoolExecutor(max_workers=1) as executor:
            with first.connection() as conn:
                task = executor.submit(close_first)
                assert started.wait(1)
                assert not task.done()
                assert conn.execute("SELECT 1 AS n").fetchone() == {"n": 1}
            task.result(timeout=2)
        first.close()
        with pytest.raises(PoolClosed), first.connection():
            pytest.fail("closed lease reopened")
        with second.connection() as conn:
            assert conn.execute("SELECT 1 AS n").fetchone() == {"n": 1}
        second.close()
        _wait_for_sessions(admin, pool_dsn)


def test_idle_pool_releases_and_reconnects(pool_dsn: str, postgres_dsn: str, monkeypatch: pytest.MonkeyPatch) -> None:
    # Accelerate maintenance only; production keeps the existing 10-minute TTL.
    monkeypatch.setattr(postgres_pool, "POOL_MAX_IDLE", 0.1)
    with psycopg.connect(postgres_dsn, autocommit=True) as admin, ExitStack() as stack:
        memory = _memory(stack, pool_dsn)
        config = {"configurable": {"thread_id": "idle-test", "checkpoint_ns": ""}}
        assert memory.get_tuple(config) is None
        assert _sessions(admin, pool_dsn) == 2
        deadline = time.monotonic() + 5
        while _sessions(admin, pool_dsn) and time.monotonic() < deadline:
            time.sleep(0.02)
        assert _sessions(admin, pool_dsn) == 0
        assert memory.get("missing") is None
        assert memory.get_tuple(config) is None
        assert _sessions(admin, pool_dsn) == 2


def test_checkpoint_setup_failure_releases_lease_and_can_retry(
    pool_dsn: str, postgres_dsn: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from langgraph.checkpoint.postgres import PostgresSaver

    original = PostgresSaver.setup
    calls = 0

    def setup(saver: Any) -> None:
        nonlocal calls
        calls += 1
        original(saver)
        if calls == 1:
            raise RuntimeError("injected setup failure after opening a connection")

    monkeypatch.setattr(PostgresSaver, "setup", setup)
    with psycopg.connect(postgres_dsn, autocommit=True) as admin, ExitStack() as stack:
        first = _memory(stack, pool_dsn)
        second = _memory(stack, pool_dsn)
        before = _sessions(admin, pool_dsn)
        with pytest.raises(RuntimeError, match="injected setup failure"):
            first._ensure_checkpointer()
        assert first._checkpointer_pool is None
        _wait_for_sessions(admin, pool_dsn, expected=before)
        first._ensure_checkpointer()
        second._ensure_checkpointer()
        assert calls == 2  # one failed attempt, one successful shared setup
        first._checkpointer_pool.close()
        assert second.get_tuple({"configurable": {"thread_id": "after-close"}}) is None


def test_connection_options_are_not_shared(pool_dsn: str) -> None:
    with ExitStack() as stack:
        first = postgres_pool.acquire_pool(pool_dsn, purpose="business")
        second = postgres_pool.acquire_pool(pool_dsn, purpose="business", connect_kwargs={"application_name": "other"})
        stack.callback(first.close)
        stack.callback(second.close)
        with first.connection() as a, second.connection() as b:
            assert a.info.backend_pid != b.info.backend_pid
            assert a.execute("SHOW application_name").fetchone() != b.execute("SHOW application_name").fetchone()


def test_server_dropped_idle_connections_are_probed_before_use(pool_dsn: str, postgres_dsn: str) -> None:
    with psycopg.connect(postgres_dsn, autocommit=True) as admin, ExitStack() as stack:
        memory = _memory(stack, pool_dsn)
        config = {"configurable": {"thread_id": "killed-idle", "checkpoint_ns": ""}}
        assert memory.get_tuple(config) is None
        app = psycopg.conninfo.conninfo_to_dict(pool_dsn)["application_name"]
        killed = admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE application_name=%s", (app,)
        ).fetchall()
        assert len(killed) == 2
        # No client-side SELECT to discover the failure first: checkout must
        # probe it, including the shared LangGraph pool.
        assert memory.get("missing") is None
        assert memory.get_tuple(config) is None


def test_maintenance_uses_checkpoint_budget(pool_dsn: str, postgres_dsn: str) -> None:
    from octop_memory.pipeline.lifecycle.vacuum import check_storage, nudge_vacuum

    with psycopg.connect(postgres_dsn, autocommit=True) as admin, ExitStack() as stack:
        memory = _memory(stack, pool_dsn)
        memory._ensure_checkpointer()
        assert _sessions(admin, pool_dsn) == 2
        assert check_storage(memory).backend == "postgres"
        assert nudge_vacuum(memory).backend == "postgres"
        assert _sessions(admin, pool_dsn) == 2
        assert memory._checkpointer_pool.get_stats()["pool_size"] == 1


def test_equivalent_dsn_spellings_share_pool(pool_dsn: str) -> None:
    params = psycopg.conninfo.conninfo_to_dict(pool_dsn)
    alternate = make_conninfo(**dict(reversed(list(params.items()))))
    with ExitStack() as stack:
        first = postgres_pool.acquire_pool(pool_dsn, purpose="business")
        second = postgres_pool.acquire_pool(alternate, purpose="business")
        stack.callback(first.close)
        stack.callback(second.close)
        assert first._entry is second._entry


def test_business_bootstrap_failure_releases_pool(
    pool_dsn: str, postgres_dsn: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from octop_memory.storage.backends.postgres import PostgresMemoryBackend

    original = PostgresMemoryBackend._init_schema

    def fail(backend: Any) -> None:
        original(backend)
        raise RuntimeError("injected bootstrap failure")

    with psycopg.connect(postgres_dsn, autocommit=True) as admin:
        monkeypatch.setattr(PostgresMemoryBackend, "_init_schema", fail)
        with pytest.raises(RuntimeError, match="injected bootstrap failure"):
            PostgresMemoryBackend("failed_bootstrap", dsn=pool_dsn)
        _wait_for_sessions(admin, pool_dsn)
        monkeypatch.setattr(PostgresMemoryBackend, "_init_schema", original)
        with ExitStack() as stack:
            memory = _memory(stack, pool_dsn)
            assert memory.get("missing") is None


def test_separate_agents_do_not_commit_each_others_transaction(pool_dsn: str) -> None:
    with ExitStack() as stack:
        first = _memory(stack, pool_dsn)
        second = _memory(stack, pool_dsn)
        try:
            with pytest.raises(RuntimeError, match="rollback first"), first.backend.transaction():
                first.store("must roll back", level="root")
                second.store("must remain", level="root")
                raise RuntimeError("rollback first")
            assert first.get_tree() == []
            assert [node.content for node in second.get_tree()] == ["must remain"]
        finally:
            first.backend.purge_namespace()
            second.backend.purge_namespace()
