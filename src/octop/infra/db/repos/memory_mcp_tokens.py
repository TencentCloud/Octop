"""Memory MCP API tokens — one row per user-issued client token."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow, map_rows


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _dump_expert_ids(expert_ids: list[str] | None) -> str | None:
    return None if expert_ids is None else json.dumps(expert_ids)


def _load_expert_ids(raw: object) -> list[str] | None:
    if raw is None:
        return None
    text = str(raw)
    if not text:
        return None
    return [str(item) for item in json.loads(text)]


def _dump_disabled_clients(clients: list[str] | None) -> str | None:
    """``None``/empty means "every client allowed", stored as SQL NULL."""
    return None if not clients else json.dumps(clients)


def _load_disabled_clients(raw: object) -> list[str] | None:
    if raw is None:
        return None
    text = str(raw)
    if not text:
        return None
    return [str(item) for item in json.loads(text)] or None


def _load_client_stats(raw: object) -> dict[str, dict[str, Any]] | None:
    if raw is None:
        return None
    text = str(raw)
    if not text:
        return None
    return {str(client): dict(stats) for client, stats in json.loads(text).items()} or None


@dataclass(frozen=True)
class MemoryMcpTokenRow:
    id: int
    token_id: str
    user_id: int
    name: str
    expert_ids: list[str] | None
    token_hash: str
    token_hint: str
    created_at: str
    last_used_at: str | None
    revoked_at: str | None
    disabled_clients: list[str] | None = None
    client_stats: dict[str, dict[str, Any]] | None = None

    @classmethod
    def from_row(cls, r: DbRow) -> MemoryMcpTokenRow:
        return cls(
            id=int(r["id"]),
            token_id=str(r["token_id"]),
            user_id=int(r["user_id"]),
            name=str(r["name"]),
            expert_ids=_load_expert_ids(r["expert_ids"]),
            token_hash=str(r["token_hash"]),
            token_hint=str(r["token_hint"]),
            created_at=str(r["created_at"]),
            last_used_at=str(r["last_used_at"]) if r["last_used_at"] is not None else None,
            revoked_at=str(r["revoked_at"]) if r["revoked_at"] is not None else None,
            disabled_clients=_load_disabled_clients(r["disabled_clients"]),
            client_stats=_load_client_stats(r["client_stats"]),
        )


class MemoryMcpTokenRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def create(
        self,
        *,
        user_id: int,
        name: str,
        expert_ids: list[str] | None,
        token_id: str,
        token_hash: str,
        token_hint: str,
    ) -> MemoryMcpTokenRow:
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO memory_mcp_tokens("
                "token_id, user_id, name, expert_ids, token_hash, token_hint, created_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    token_id,
                    user_id,
                    name,
                    _dump_expert_ids(expert_ids),
                    token_hash,
                    token_hint,
                    _utc_now_iso(),
                ),
            )
        row = self.get_by_token_hash(token_hash)
        if row is None:
            raise RuntimeError(f"memory MCP token insert failed: {token_id}")
        return row

    def list_for_user(self, user_id: int) -> list[MemoryMcpTokenRow]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memory_mcp_tokens WHERE user_id = ? "
                "ORDER BY created_at DESC, id DESC",
                (user_id,),
            ).fetchall()
        return map_rows(rows, MemoryMcpTokenRow)

    def get_by_token_hash(self, token_hash: str) -> MemoryMcpTokenRow | None:
        """Look up by digest; revoked rows are returned so the caller can reject them."""
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT * FROM memory_mcp_tokens WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
        return MemoryMcpTokenRow.from_row(r) if r else None

    def any_active(self) -> bool:
        """True when at least one unrevoked token exists (MCP mount gate)."""
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT 1 FROM memory_mcp_tokens WHERE revoked_at IS NULL LIMIT 1"
            ).fetchone()
        return r is not None

    def get_for_user(self, token_id: str, *, user_id: int) -> MemoryMcpTokenRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT * FROM memory_mcp_tokens WHERE token_id = ? AND user_id = ?",
                (token_id, user_id),
            ).fetchone()
        return MemoryMcpTokenRow.from_row(r) if r else None

    def update(
        self,
        token_id: str,
        *,
        user_id: int,
        name: str,
        expert_ids: list[str] | None,
        disabled_clients: list[str] | None = None,
    ) -> MemoryMcpTokenRow | None:
        """Replace one live token's name / expert allow-list / disabled clients.

        ``None`` for ``disabled_clients`` clears the restriction (every client
        allowed). ``None`` as the return value means the row is gone or already
        revoked — the caller decides whether that is 404 or 409.
        """
        with self._db.transaction() as conn:
            cursor = conn.execute(
                "UPDATE memory_mcp_tokens SET name = ?, expert_ids = ?, disabled_clients = ? "
                "WHERE token_id = ? AND user_id = ? AND revoked_at IS NULL",
                (
                    name,
                    _dump_expert_ids(expert_ids),
                    _dump_disabled_clients(disabled_clients),
                    token_id,
                    user_id,
                ),
            )
            if int(cursor.rowcount or 0) == 0:
                return None
        return self.get_for_user(token_id, user_id=user_id)

    def rotate(
        self,
        token_id: str,
        *,
        user_id: int,
        token_hash: str,
        token_hint: str,
    ) -> MemoryMcpTokenRow | None:
        """Replace a live token's secret (hash + hint); old plaintext stops working.

        Returns ``None`` when the row is gone, owned by somebody else, or already
        revoked — the caller decides whether that is 404 or 409.
        """
        with self._db.transaction() as conn:
            cursor = conn.execute(
                "UPDATE memory_mcp_tokens SET token_hash = ?, token_hint = ?, last_used_at = NULL "
                "WHERE token_id = ? AND user_id = ? AND revoked_at IS NULL",
                (token_hash, token_hint, token_id, user_id),
            )
            if int(cursor.rowcount or 0) <= 0:
                return None
            row = conn.execute(
                "SELECT * FROM memory_mcp_tokens WHERE token_id = ?", (token_id,)
            ).fetchone()
        return MemoryMcpTokenRow.from_row(row) if row is not None else None

    def revoke(self, token_id: str, *, user_id: int) -> bool:
        """Mark the token revoked; ``False`` when it was already revoked."""
        with self._db.transaction() as conn:
            cursor = conn.execute(
                "UPDATE memory_mcp_tokens SET revoked_at = ? "
                "WHERE token_id = ? AND user_id = ? AND revoked_at IS NULL",
                (_utc_now_iso(), token_id, user_id),
            )
            return int(cursor.rowcount or 0) > 0

    def touch(self, token_id: str) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE memory_mcp_tokens SET last_used_at = ? WHERE token_id = ?",
                (_utc_now_iso(), token_id),
            )

    def record_client(self, token_id: str, client: str, now: str | None = None) -> None:
        """Count one request from ``client`` on this token; keep first/last seen.

        A missing or revoked row is a no-op: the caller has already validated
        the token, so there is nothing to report. Concurrent requests may lose
        an increment (read-modify-write) — acceptable for usage statistics.
        """
        with self._db.transaction() as conn:
            r = conn.execute(
                "SELECT client_stats, revoked_at FROM memory_mcp_tokens WHERE token_id = ?",
                (token_id,),
            ).fetchone()
            if r is None or r["revoked_at"] is not None:
                return
            stats = _load_client_stats(r["client_stats"]) or {}
            seen = now or _utc_now_iso()
            entry = dict(stats.get(client) or {})
            entry["first_seen"] = entry.get("first_seen") or seen
            entry["last_seen"] = seen
            entry["count"] = int(entry.get("count") or 0) + 1
            stats[client] = entry
            conn.execute(
                "UPDATE memory_mcp_tokens SET client_stats = ? WHERE token_id = ?",
                (json.dumps(stats), token_id),
            )
