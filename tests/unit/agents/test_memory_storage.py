"""Dashboard maintenance stays inside the selected expert's dedicated store."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from tests.unit.agents.test_memory_slim import make_manager

from octop.config import OctopConfig
from octop.infra.agents.memory.sqlite_storage import _checkpoint_policy
from octop.infra.agents.memory.storage import sqlite_store_is_shared


@pytest.fixture
def store(tmp_path):
    coordinator, registry, memory, cfg, cp = make_manager(tmp_path)
    row = SimpleNamespace(agent_id="a", user_id=1, config_json="{}")
    registry.get_row = lambda aid: row if aid == "a" else None
    registry._repos = SimpleNamespace(agent_repo=MagicMock())
    registry._repos.agent_repo.list_all.return_value = [row]
    registry._config = OctopConfig()
    registry._paths = SimpleNamespace()
    yield coordinator, registry, memory, cfg, cp
    memory._checkpointer.conn.close()
    memory.backend.close()


@pytest.mark.asyncio
async def test_inspect_then_maintain_preserves_history_and_never_sweeps_host(store, monkeypatch):
    coordinator, registry, memory, cfg, cp = store
    before = await coordinator.inspect_storage("a")
    assert before["backend"] == "sqlite"
    assert before["scope"] == "agent"
    assert before["maintenance_supported"]
    assert before["file_size"] > 0
    assert before["elapsed_ms"] >= before["file_check_ms"] >= 0
    counts = {item["table"]: item["rows"] for item in before["checkpoint_counts"]}
    assert counts["checkpoints"] == counts["checkpoint_threads"] == 1
    assert coordinator.task is None
    assert memory.get_tuple(cfg).checkpoint == cp

    def forbidden(*args, **kwargs):
        pytest.fail("current-expert maintenance must never sweep the host")

    monkeypatch.setattr(
        "octop.infra.agents.memory.thread_cleanup.sweep_deleted_residuals", forbidden
    )
    first = coordinator.start_current("a", 1)
    assert first["busy"] and first["job"]["phase"] == "waiting"
    with pytest.raises(ValueError):
        coordinator.start_current("a", 1)
    await coordinator.task
    result = coordinator.storage_status("a")
    assert not result["busy"]
    assert result["job"]["phase"] == "done"
    report = result["job"]["report"]
    assert Path(report["backup_path"]).is_file()
    assert report["stats"]["scanned"] == 1
    for snapshot in (report["inspection_before"], report["inspection_after"]):
        assert snapshot["namespace"] == memory.backend._ns
        counts = {item["table"]: item["rows"] for item in snapshot["checkpoint_counts"]}
        assert counts["checkpoints"] == counts["checkpoint_threads"] == 1
        assert snapshot["elapsed_ms"] >= 0
    assert report["inspection_after"]["file_size"] == report["after"]["file_bytes"]
    assert memory.get_tuple(cfg).checkpoint == cp
    assert not registry._history_backfills
    # A different host job must not make this expert's last result disappear.
    coordinator.agent_id = "another"
    coordinator.state = {"phase": "waiting"}
    assert coordinator.storage_status("a")["job"]["report"] == report
    assert coordinator.storage_status("another")["job"] is None


@pytest.mark.asyncio
async def test_current_job_rechecks_owner_after_waiting(store):
    coordinator, registry, _memory, _cfg, _cp = store
    await registry._begin_invocation("a")
    coordinator.start_current("a", 1)
    await asyncio.sleep(0.02)
    registry.get_row("a").user_id = 2
    registry._end_invocation("a")
    await coordinator.task
    assert coordinator.storage_status("a")["job"]["phase"] == "failed"
    assert "report" not in coordinator.storage_status("a")["job"]
    assert not registry._history_backfills


def test_reject_nonowner_and_ambiguous_postgres_namespace_before_scheduling(store):
    coordinator, registry, _memory, _cfg, _cp = store
    with pytest.raises(ValueError):
        coordinator.start_current("a", 2)
    postgres = SimpleNamespace(backend=type("PostgresMemoryBackend", (), {"_ns": "agent_a"})())
    registry.get_agent = lambda _: SimpleNamespace(_memory_runtime=SimpleNamespace(memory=postgres))
    assert coordinator._storage_target("a", "en")[1] is None
    registry._repos.agent_repo.list_all.return_value.append(SimpleNamespace(agent_id="A"))
    assert coordinator._storage_target("a", "en")[1] == "shared_namespace"
    with pytest.raises(ValueError, match="namespace"):
        coordinator.start_current("a", 1)
    assert coordinator.task is None
    postgres.backend._ns = "agent_b"
    with pytest.raises(ValueError, match="namespace"):
        coordinator.start_current("a", 1)


def test_stopped_expert_sharing_sqlite_disables_maintenance(store, monkeypatch, tmp_path):
    coordinator, registry, memory, _cfg, _cp = store
    other = SimpleNamespace(
        agent_id="b",
        config_json=json.dumps(
            {"memory": {"backend": {"type": "sqlite", "db_path": str(memory.backend._db_path)}}}
        ),
    )
    registry._repos.agent_repo.list_all.return_value.append(other)
    monkeypatch.setattr(
        "octop.infra.agents.memory.storage.workspace_for_agent_row",
        lambda *args, **kwargs: tmp_path,
    )
    assert sqlite_store_is_shared(registry, "a", memory)
    with pytest.raises(ValueError, match="shared"):
        coordinator.start_current("a", 1)
    assert coordinator.task is None


@pytest.mark.asyncio
async def test_failure_retains_result_and_releases_turn_gate(store, monkeypatch):
    coordinator, registry, _memory, _cfg, _cp = store
    from octop_memory.application import checkpoint_maintenance

    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(checkpoint_maintenance, "slim_live_checkpoints", fail)
    coordinator.start_current("a", 1)
    await coordinator.task
    job = coordinator.storage_status("a")["job"]
    assert job["phase"] == "failed"
    assert "disk full" in job["error"]
    assert not registry._history_backfills


@pytest.mark.asyncio
async def test_shared_file_counts_only_selected_namespace_and_never_maintains(store):
    coordinator, _registry, memory, _cfg, _cp = store
    with sqlite3.connect(memory.backend._db_path) as conn:
        conn.execute("CREATE TABLE other_raw_events (id INTEGER)")
        conn.executemany("INSERT INTO other_raw_events VALUES (?)", [(1,), (2,), (3,)])
    before_bytes = Path(memory.backend._db_path).read_bytes()
    inspection = await coordinator.inspect_storage("a")
    assert inspection["blocked_reason"] == "shared_sqlite"
    assert not inspection["maintenance_supported"]
    assert not inspection["checkpoints_available"]
    assert inspection["checkpoint_counts"] == []
    rows = {item["table"]: item["rows"] for item in inspection["memory_counts"]}
    assert rows["raw_events"] == 0  # Do not include other_raw_events.
    assert not any("fts" in item["table"] for item in inspection["memory_counts"])
    coordinator.start_current("a", 1)
    await coordinator.task
    assert coordinator.storage_status("a")["job"]["phase"] == "failed"
    assert Path(memory.backend._db_path).read_bytes() == before_bytes
    assert not list(Path(memory.backend._db_path).parent.glob("*.bak"))


def test_read_only_counts_distinguish_missing_zero_and_timeout(tmp_path, monkeypatch):
    from octop.infra.agents.memory.sqlite_storage import inspect_sqlite_storage

    path = tmp_path / "minimal.sqlite"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE current_raw_events (id INTEGER)")
        conn.execute("CREATE TABLE checkpoints (thread_id TEXT)")
        conn.executemany("INSERT INTO checkpoints VALUES (?)", [("a",), ("a",), ("b",)])
    original = path.read_bytes()
    backend = SimpleNamespace(_db_path=path, _ns="current")
    snapshot = inspect_sqlite_storage(backend, shared=False)
    rows = {
        item["table"]: item for item in snapshot["memory_counts"] + snapshot["checkpoint_counts"]
    }
    assert rows["raw_events"]["rows"] == 0
    assert rows["atoms"]["rows"] is None and rows["atoms"]["status"] == "missing"
    assert rows["checkpoints"]["rows"] == 3
    assert rows["checkpoint_threads"]["rows"] == 2
    assert path.read_bytes() == original
    monkeypatch.setattr("octop.infra.agents.memory.sqlite_storage.COUNT_BUDGET_SECONDS", 0)
    snapshot = inspect_sqlite_storage(backend, shared=False)
    assert snapshot["memory_counts"][0]["status"] == "timed_out"
    assert snapshot["memory_counts"][0]["rows"] is None
    assert path.read_bytes() == original


@pytest.mark.parametrize(
    ("value", "mode", "warning"),
    [
        (None, "first", False),
        ("first", "first", False),
        ("always", "always", False),
        ("1", "always", False),
        (" TRUE ", "always", False),
        ("on", "always", False),
        ("yes", "always", False),
        ("0", "off", False),
        ("false", "off", False),
        ("off", "off", False),
        ("no", "off", False),
        ("unrecognized", "first", True),
    ],
)
def test_checkpoint_backup_modes_match_harness(value, mode, warning, monkeypatch, caplog):
    # Same cases as octop-harness tests/test_checkpoint_backup.py, including
    # when this test runs against an older installed Harness wheel.
    variable = "OCTOP_CHECKPOINT_BACKUP_BEFORE_PRUNE"
    if value is None:
        monkeypatch.delenv(variable, raising=False)
    else:
        monkeypatch.setenv(variable, value)
    monkeypatch.delenv("OCTOP_CHECKPOINT_BACKUP_KEEP_DAYS", raising=False)
    for _ in range(2):
        policy = _checkpoint_policy(0)
        assert policy["checkpoint_backup_before_prune"] == mode
        assert policy["checkpoint_backup_keep_days"] == 7
    assert caplog.text.count(variable) == int(warning)


@pytest.mark.parametrize(("value", "expected"), [("0", 0), (" 14 ", 14), ("-1", 7), ("invalid", 7)])
def test_checkpoint_backup_keep_days_match_harness(value, expected, monkeypatch):
    monkeypatch.setenv("OCTOP_CHECKPOINT_BACKUP_KEEP_DAYS", value)
    assert _checkpoint_policy(0)["checkpoint_backup_keep_days"] == expected


def test_checkpoint_backup_policy_agrees_with_installed_harness(monkeypatch):
    harness = pytest.importorskip("octop_harness.middleware.checkpoint_backup")
    mode_env = "OCTOP_CHECKPOINT_BACKUP_BEFORE_PRUNE"
    days_env = "OCTOP_CHECKPOINT_BACKUP_KEEP_DAYS"
    for mode, days in (
        ("", ""),
        ("first", "7"),
        ("always", "0"),
        ("off", "12"),
        (" TRUE ", " 5 "),
        ("0", "-1"),
        ("unexpected-mode", "unexpected-days"),
    ):
        monkeypatch.setenv(mode_env, mode)
        monkeypatch.setenv(days_env, days)
        policy = _checkpoint_policy(0)
        assert (
            policy["checkpoint_backup_before_prune"],
            policy["checkpoint_backup_keep_days"],
        ) == harness.checkpoint_backup_policy_from_env()
