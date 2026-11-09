"""Memory MCP API tokens — one row per user-issued client token."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

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
