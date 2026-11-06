"""Channel table access."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from octop.infra.db.lease import cell, opt_int, unix_now_sql
from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow, bool_int, map_rows, now_ts, partial_updates


@dataclass(frozen=True)
class ChannelRow:
    id: int
    channel_id: str
    agent_id: str
    user_id: int
    kind: str
    name: str
    config_json: str
    enabled: int
    created_at: int
    updated_at: int
    runtime_lease_owner: str | None = None
    runtime_lease_token: str | None = None
    runtime_lease_until: int | None = None
    runtime_generation: int = 0

    @classmethod
    def from_row(cls, r: DbRow) -> ChannelRow:
        return cls(
            id=r["id"],
            channel_id=r["channel_id"],
            agent_id=r["agent_id"],
            user_id=r["user_id"],
            kind=r["kind"],
            name=r["name"],
            config_json=r["config_json"],
            enabled=r["enabled"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            runtime_lease_owner=cell(r, "runtime_lease_owner") or None,
            runtime_lease_token=cell(r, "runtime_lease_token") or None,
            runtime_lease_until=opt_int(cell(r, "runtime_lease_until")),
            runtime_generation=int(cell(r, "runtime_generation") or 0),
        )


class ChannelRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def create(
        self,
        *,
        channel_id: str,
        agent_id: str,
        user_id: int,
        kind: str,
        name: str,
        config_json: str,
    ) -> str:
        ts = now_ts()
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO channels(channel_id, agent_id, user_id, kind, name, config_json, "
                "enabled, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
                (channel_id, agent_id, user_id, kind, name, config_json, ts, ts),
            )
        return channel_id

    def get(self, channel_id: str) -> ChannelRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT * FROM channels WHERE channel_id = ?", (channel_id,)
            ).fetchone()
        return ChannelRow.from_row(r) if r else None

    def get_by_agent_and_name(self, agent_id: str, name: str) -> ChannelRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT * FROM channels WHERE agent_id = ? AND name = ?",
                (agent_id, name),
            ).fetchone()
        return ChannelRow.from_row(r) if r else None

    def list_by_agent(self, agent_id: str, *, include_disabled: bool = True) -> list[ChannelRow]:
        sql = "SELECT * FROM channels WHERE agent_id = ?"
        if not include_disabled:
            sql += " AND enabled = 1"
        sql += " ORDER BY name"
        with self._db.connect() as conn:
            rows = conn.execute(sql, (agent_id,)).fetchall()
        return map_rows(rows, ChannelRow)

    def list_all(self, *, include_disabled: bool = True) -> list[ChannelRow]:
        sql = "SELECT * FROM channels"
        if not include_disabled:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY agent_id, name"
        with self._db.connect() as conn:
            rows = conn.execute(sql).fetchall()
        return map_rows(rows, ChannelRow)

    def update(
        self,
        channel_id: str,
        *,
        kind: str | None = None,
        name: str | None = None,
        config_json: str | None = None,
        enabled: bool | None = None,
    ) -> None:
        fields, params = partial_updates(
            [("kind", kind), ("name", name), ("config_json", config_json)]
        )
        if enabled is not None:
            fields.append("enabled = ?")
            params.append(bool_int(enabled))
        if not fields:
            return
        # Config or enabled changes invalidate a connection held by any instance.
        fields.append("runtime_generation = runtime_generation + 1")
        fields.append("updated_at = ?")
        params.append(now_ts())
        params.append(channel_id)
        with self._db.transaction() as conn:
            conn.execute(f"UPDATE channels SET {', '.join(fields)} WHERE channel_id = ?", params)

    def _now_sql(self) -> str:
        return unix_now_sql(self._db.dialect)

    def claim_runtime_lease(
        self,
        channel_id: str,
        *,
        owner: str,
        lease_seconds: int,
    ) -> ChannelRow | None:
        """Connect only when the channel is enabled and its lease is free or expired."""
        token = uuid.uuid4().hex
        now = self._now_sql()
        sql = (
            "UPDATE channels SET runtime_lease_owner = ?, runtime_lease_token = ?, "
            f"runtime_lease_until = {now} + ? "
            "WHERE channel_id = ? AND enabled = 1 "
            f"AND (runtime_lease_until IS NULL OR runtime_lease_until < {now}) "
            "RETURNING *"
        )
        with self._db.transaction() as conn:
            row = conn.execute(sql, (owner, token, int(lease_seconds), channel_id)).fetchone()
        return ChannelRow.from_row(row) if row else None

    def renew_runtime_lease(
        self,
        channel_id: str,
        *,
        token: str,
        generation: int,
        lease_seconds: int,
    ) -> bool:
        now = self._now_sql()
        sql = (
            "UPDATE channels SET "
            f"runtime_lease_until = {now} + ? "
            "WHERE channel_id = ? AND runtime_lease_token = ? "
            "AND runtime_generation = ? AND enabled = 1 "
            f"AND runtime_lease_until >= {now}"
        )
        with self._db.transaction() as conn:
            cur = conn.execute(sql, (int(lease_seconds), channel_id, token, int(generation)))
            return int(cur.rowcount or 0) > 0

    def release_runtime_lease(self, channel_id: str, *, token: str) -> bool:
        with self._db.transaction() as conn:
            cur = conn.execute(
                "UPDATE channels SET runtime_lease_owner = NULL, runtime_lease_token = NULL, "
                "runtime_lease_until = NULL WHERE channel_id = ? AND runtime_lease_token = ?",
                (channel_id, token),
            )
            return int(cur.rowcount or 0) > 0

    def delete(self, channel_id: str) -> None:
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM channels WHERE channel_id = ?", (channel_id,))
