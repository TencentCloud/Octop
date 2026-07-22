"""Channel table access."""

from __future__ import annotations

from dataclasses import dataclass

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
        fields.append("updated_at = ?")
        params.append(now_ts())
        params.append(channel_id)
        with self._db.transaction() as conn:
            conn.execute(f"UPDATE channels SET {', '.join(fields)} WHERE channel_id = ?", params)

    def delete(self, channel_id: str) -> None:
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM channels WHERE channel_id = ?", (channel_id,))
