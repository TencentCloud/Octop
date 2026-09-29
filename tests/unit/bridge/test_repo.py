"""Bridge connection repo tests."""

from __future__ import annotations

from pathlib import Path

from octop.infra.db.migrate import _ensure_bridge_connections_schema, run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos._base import now_ts
from octop.infra.db.repos.bridge_connections import BridgeConnectionRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.utils.ulid import new_ulid


def test_bridge_connection_crud(tmp_path: Path) -> None:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    users = UserRepo(pool)
    uid = users.create(username="alice", password_hash="x", role="user")
    repo = BridgeConnectionRepo(pool)
    cid = new_ulid()
    row = repo.create(
        connection_id=cid,
        owner_user_id=uid,
        peer_base_url="https://peer.example",
        peer_username="bob",
        display_name="Cloud",
        notes="demo node",
        status="disconnected",
    )
    assert row.connection_id == cid
    assert row.display_name == "Cloud"
    assert row.notes == "demo node"
    assert row.auto_reconnect is True
    assert repo.find_by_display_name(uid, "Cloud") is not None
    assert repo.find_by_display_name(uid, "Other") is None
    assert repo.get_for_owner(cid, uid) is not None
    assert repo.get_for_owner(cid, uid + 1) is None
    listed = repo.list_for_owner(uid)
    assert len(listed) == 1
    repo.update_status(cid, status="connected", touch_seen=True)
    again = repo.get(cid)
    assert again is not None
    assert again.status == "connected"
    assert again.last_seen_at is not None
    repo.set_auto_reconnect(cid, False)
    disabled = repo.get(cid)
    assert disabled is not None and disabled.auto_reconnect is False
    assert repo.delete(cid) is True
    assert repo.get(cid) is None


def test_upsert_reverse_disables_auto_reconnect(tmp_path: Path) -> None:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    users = UserRepo(pool)
    uid = users.create(username="alice", password_hash="x", role="user")
    repo = BridgeConnectionRepo(pool)
    cid = new_ulid()
    created = repo.upsert_reverse(
        connection_id=cid,
        owner_user_id=uid,
        peer_base_url="http://127.0.0.1",
        peer_username="peer",
        display_name="Inbound",
        status="connected",
    )
    assert created.auto_reconnect is False
    assert created.credential_blob is None
    repo.set_auto_reconnect(cid, True)
    again = repo.upsert_reverse(
        connection_id=cid,
        owner_user_id=uid,
        peer_base_url="http://127.0.0.1",
        peer_username="peer",
        display_name="Inbound",
        status="connected",
    )
    assert again.auto_reconnect is False


def test_ensure_bridge_dedupes_duplicate_display_names(tmp_path: Path) -> None:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    users = UserRepo(pool)
    uid = users.create(username="alice", password_hash="x", role="user")
    ts = now_ts()
    with pool.transaction() as conn:
        conn.execute("DROP INDEX IF EXISTS idx_bridge_connections_owner_display")
        for i, name in enumerate(("Cloud", "Cloud", ""), start=1):
            conn.execute(
                "INSERT INTO bridge_connections("
                "connection_id, owner_user_id, peer_base_url, peer_username, "
                "display_name, status, created_at, updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"cid-{i}",
                    uid,
                    "https://peer.example",
                    "bob",
                    name,
                    "disconnected",
                    ts,
                    ts,
                ),
            )
    _ensure_bridge_connections_schema(pool)
    repo = BridgeConnectionRepo(pool)
    names = sorted(r.display_name for r in repo.list_for_owner(uid))
    assert names == ["Cloud", "Cloud (2)", "bob"]
    # Index exists and rejects a new duplicate insert.
    raised = False
    try:
        with pool.transaction() as conn:
            conn.execute(
                "INSERT INTO bridge_connections("
                "connection_id, owner_user_id, peer_base_url, peer_username, "
                "display_name, status, created_at, updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("cid-dup", uid, "https://x", "u", "Cloud", "disconnected", ts, ts),
            )
    except Exception:
        raised = True
    assert raised
