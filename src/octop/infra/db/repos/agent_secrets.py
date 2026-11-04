"""Per-agent secret slot database access."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow, map_rows, now_ts
from octop.infra.utils.ulid import new_ulid


@dataclass(frozen=True)
class AgentSecretRow:
    id: int
    secret_id: str
    agent_id: str
    user_id: int
    slot_name: str
    display_name: str | None
    created_at: int
    rotated_at: int | None
    updated_at: int
    # Only populated by queries that select ``secret_blob``. List endpoints
    # must never load it so an accidental serialization cannot leak ciphertext.
    secret_blob: bytes | None = None

    @classmethod
    def from_row(cls, r: DbRow) -> AgentSecretRow:
        keys = r.keys() if hasattr(r, "keys") else ()
        blob = r["secret_blob"] if "secret_blob" in keys else None
        return cls(
            id=r["id"],
            secret_id=r["secret_id"],
            agent_id=r["agent_id"],
            user_id=r["user_id"],
            slot_name=r["slot_name"],
            display_name=r["display_name"],
            created_at=r["created_at"],
            rotated_at=r["rotated_at"],
            updated_at=r["updated_at"],
            secret_blob=_coerce_blob(blob),
        )


def _coerce_blob(blob: Any) -> bytes | None:
    if blob is None:
        return None
    if isinstance(blob, str):
        return blob.encode("utf-8")
    return bytes(blob)


_LIST_COLUMNS = (
    "id, secret_id, agent_id, user_id, slot_name, display_name, created_at, rotated_at, updated_at"
)


class AgentSecretsRepo:
    """CRUD for the ``agent_secrets`` table (SQL only, no crypto here)."""

    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def list_for_agent(self, agent_id: str, *, include_blob: bool = False) -> list[AgentSecretRow]:
        columns = f"{_LIST_COLUMNS}, secret_blob" if include_blob else _LIST_COLUMNS
        with self._db.connect() as conn:
            rows = conn.execute(
                f"SELECT {columns} FROM agent_secrets WHERE agent_id = ? ORDER BY slot_name",
                (agent_id,),
            ).fetchall()
        return map_rows(rows, AgentSecretRow)

    def get(self, agent_id: str, secret_id: str) -> AgentSecretRow | None:
        with self._db.connect() as conn:
            row = conn.execute(
                f"SELECT {_LIST_COLUMNS} FROM agent_secrets WHERE agent_id = ? AND secret_id = ?",
                (agent_id, secret_id),
            ).fetchone()
        return AgentSecretRow.from_row(row) if row is not None else None

    def upsert_slot(
        self,
        *,
        agent_id: str,
        user_id: int,
        slot_name: str,
        display_name: str | None,
        secret_blob: bytes,
    ) -> AgentSecretRow:
        """Insert a slot or rotate the stored blob; returns the stored row."""
        ts = now_ts()
        with self._db.transaction() as conn:
            existing = conn.execute(
                "SELECT id FROM agent_secrets WHERE agent_id = ? AND slot_name = ?",
                (agent_id, slot_name),
            ).fetchone()
            if existing is not None:
                conn.execute(
                    "UPDATE agent_secrets SET secret_blob = ?, display_name = ?, "
                    "rotated_at = ?, updated_at = ? WHERE agent_id = ? AND slot_name = ?",
                    (secret_blob, display_name, ts, ts, agent_id, slot_name),
                )
            else:
                conn.execute(
                    "INSERT INTO agent_secrets "
                    "(secret_id, agent_id, user_id, slot_name, display_name, "
                    "secret_blob, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (new_ulid(), agent_id, user_id, slot_name, display_name, secret_blob, ts, ts),
                )
        stored = self._get_by_slot(agent_id, slot_name)
        assert stored is not None, "agent_secrets upsert lost the row"
        return stored

    def _get_by_slot(self, agent_id: str, slot_name: str) -> AgentSecretRow | None:
        with self._db.connect() as conn:
            row = conn.execute(
                f"SELECT {_LIST_COLUMNS} FROM agent_secrets WHERE agent_id = ? AND slot_name = ?",
                (agent_id, slot_name),
            ).fetchone()
        return AgentSecretRow.from_row(row) if row is not None else None

    def delete(self, agent_id: str, secret_id: str) -> bool:
        with self._db.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM agent_secrets WHERE agent_id = ? AND secret_id = ?",
                (agent_id, secret_id),
            )
            return bool(cursor.rowcount)
