"""Connector database access — one row per (user, kind)."""

from __future__ import annotations

import json
from dataclasses import dataclass

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow, map_rows, now_ts


@dataclass(frozen=True)
class ConnectorRow:
    id: int
    instance_id: str
    user_id: int
    kind: str
    display_name: str
    status: str
    mcp_server_name: str
    credential_blob: bytes | None
    credential_expires_at: int | None
    credential_rotated_at: int | None
    config_json: str | None
    created_at: int
    updated_at: int

    @classmethod
    def from_row(cls, r: DbRow) -> ConnectorRow:
        blob = r["credential_blob"]
        return cls(
            id=r["id"],
            instance_id=r["instance_id"],
            user_id=r["user_id"],
            kind=r["kind"],
            display_name=r["display_name"],
            status=r["status"],
            mcp_server_name=r["mcp_server_name"],
            credential_blob=bytes(blob) if blob is not None else None,
            credential_expires_at=r["credential_expires_at"],
            credential_rotated_at=r["credential_rotated_at"],
            config_json=r["config_json"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )

    @property
    def has_credentials(self) -> bool:
        return bool(self.credential_blob)


@dataclass(frozen=True)
class ConnectorOAuthStateRow:
    id: int
    state_id: str
    state: str
    user_id: int
    kind: str
    code_verifier: str
    redirect_after: str | None
    created_at: int

    @classmethod
    def from_row(cls, r: DbRow) -> ConnectorOAuthStateRow:
        return cls(
            id=r["id"],
            state_id=r["state_id"],
            state=r["state"],
            user_id=r["user_id"],
            kind=r["kind"],
            code_verifier=r["code_verifier"],
            redirect_after=r["redirect_after"],
            created_at=r["created_at"],
        )


class ConnectorRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def create(
        self,
        *,
        instance_id: str,
        user_id: int,
        kind: str,
        display_name: str,
        mcp_server_name: str,
        config_json: str | None = None,
    ) -> str:
        ts = now_ts()
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO connectors("
                "instance_id, user_id, kind, display_name, status, mcp_server_name, "
                "config_json, created_at, updated_at"
                ") VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?)",
                (
                    instance_id,
                    user_id,
                    kind,
                    display_name,
                    mcp_server_name,
                    config_json,
                    ts,
                    ts,
                ),
            )
        return instance_id

    def get(self, instance_id: str) -> ConnectorRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT * FROM connectors WHERE instance_id = ?", (instance_id,)
            ).fetchone()
        return ConnectorRow.from_row(r) if r else None

    def get_by_user_kind(self, user_id: int, kind: str) -> ConnectorRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT * FROM connectors WHERE user_id = ? AND kind = ?",
                (user_id, kind),
            ).fetchone()
        return ConnectorRow.from_row(r) if r else None

    def list_by_user(self, user_id: int) -> list[ConnectorRow]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM connectors WHERE user_id = ? ORDER BY display_name",
                (user_id,),
            ).fetchall()
        return map_rows(rows, ConnectorRow)

    def update_status(self, instance_id: str, status: str) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE connectors SET status = ?, updated_at = ? WHERE instance_id = ?",
                (status, now_ts(), instance_id),
            )

    def upsert_credentials(
        self,
        *,
        instance_id: str,
        blob: bytes,
        expires_at: int | None = None,
    ) -> None:
        ts = now_ts()
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE connectors SET credential_blob = ?, credential_expires_at = ?, "
                "credential_rotated_at = ?, updated_at = ? WHERE instance_id = ?",
                (blob, expires_at, ts, ts, instance_id),
            )

    def delete(self, instance_id: str) -> None:
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM connectors WHERE instance_id = ?", (instance_id,))

    def list_active_mcp_server_names_for_user(self, user_id: int) -> list[str]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT mcp_server_name FROM connectors "
                "WHERE user_id = ? AND status = 'active' AND credential_blob IS NOT NULL "
                "ORDER BY display_name",
                (user_id,),
            ).fetchall()
        return [str(r["mcp_server_name"]) for r in rows]

    def validate_mcp_servers_for_user(self, user_id: int, names: list[str]) -> list[str]:
        allowed = set(self.list_active_mcp_server_names_for_user(user_id))
        unknown = sorted(set(names) - allowed)
        if unknown:
            raise ValueError(f"mcp_servers not available for user: {unknown}")
        return list(names)

    def create_oauth_state(
        self,
        *,
        state_id: str,
        state: str,
        user_id: int,
        kind: str,
        code_verifier: str,
        redirect_after: str | None = None,
    ) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO connector_oauth_states("
                "state_id, state, user_id, kind, code_verifier, redirect_after, created_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?)",
                (state_id, state, user_id, kind, code_verifier, redirect_after, now_ts()),
            )

    def consume_oauth_state(self, state: str) -> ConnectorOAuthStateRow | None:
        with self._db.transaction() as conn:
            r = conn.execute(
                "SELECT * FROM connector_oauth_states WHERE state = ?", (state,)
            ).fetchone()
            if not r:
                return None
            conn.execute("DELETE FROM connector_oauth_states WHERE state = ?", (state,))
        return ConnectorOAuthStateRow.from_row(r)

    def prune_old_oauth_states(self, older_than_ts: int) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "DELETE FROM connector_oauth_states WHERE created_at < ?", (older_than_ts,)
            )

    @staticmethod
    def parse_config_json(row: ConnectorRow) -> dict[str, object]:
        if not row.config_json:
            return {}
        try:
            data = json.loads(row.config_json)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
