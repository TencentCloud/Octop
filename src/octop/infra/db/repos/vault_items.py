"""User vault item database access."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow, map_rows, now_ts

# Hard per-user cap on pure inserts; rotation is never cap-guarded (spec: the
# cap counts new credentials, not updates to existing ones).
VAULT_ITEMS_MAX_PER_USER = 256


@dataclass(frozen=True)
class VaultItemRow:
    id: int
    vault_item_id: str
    user_id: int
    item_type: str
    title: str
    origin: str | None
    created_at: int
    updated_at: int
    # Only populated by queries that select ``fields_blob``. List endpoints
    # must never load it so an accidental serialization cannot leak ciphertext.
    fields_blob: bytes | None = None

    @classmethod
    def from_row(cls, r: DbRow) -> VaultItemRow:
        keys = r.keys() if hasattr(r, "keys") else ()
        blob = r["fields_blob"] if "fields_blob" in keys else None
        return cls(
            id=r["id"],
            vault_item_id=r["vault_item_id"],
            user_id=r["user_id"],
            item_type=r["item_type"],
            title=r["title"],
            origin=r["origin"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            fields_blob=_coerce_blob(blob),
        )


def _coerce_blob(blob: Any) -> bytes | None:
    if blob is None:
        return None
    if isinstance(blob, str):
        return blob.encode("utf-8")
    return bytes(blob)


_LIST_COLUMNS = "id, vault_item_id, user_id, item_type, title, origin, created_at, updated_at"


class VaultItemsRepo:
    """CRUD for the ``vault_items`` table (SQL only, no crypto here).

    Write methods accept an optional externally-owned connection: the
    secure-form submit unit opens one transaction and threads it through the
    vault write, the agent-secret slot writes, and the audit row, because
    SQLite cannot nest the per-method ``transaction()`` blocks.
    """

    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    @property
    def db(self) -> DatabasePool:
        """Pool handle for the service-level transaction owner."""
        return self._db

    def get(
        self,
        vault_item_id: str,
        *,
        user_id: int,
        include_blob: bool = False,
    ) -> VaultItemRow | None:
        """Owner-scoped read: a vault id never resolves across users."""
        columns = f"{_LIST_COLUMNS}, fields_blob" if include_blob else _LIST_COLUMNS
        with self._db.connect() as conn:
            row = conn.execute(
                f"SELECT {columns} FROM vault_items WHERE vault_item_id = ? AND user_id = ?",
                (vault_item_id, user_id),
            ).fetchone()
        return VaultItemRow.from_row(row) if row is not None else None

    def list_for_user(self, user_id: int) -> list[VaultItemRow]:
        """Metadata only; never selects ``fields_blob``."""
        with self._db.connect() as conn:
            rows = conn.execute(
                f"SELECT {_LIST_COLUMNS} FROM vault_items WHERE user_id = ? ORDER BY title",
                (user_id,),
            ).fetchall()
        return map_rows(rows, VaultItemRow)

    def find_by_title(
        self,
        *,
        user_id: int,
        item_type: str,
        title: str,
        conn: Any | None = None,
    ) -> VaultItemRow | None:
        """Exact case-sensitive ``(user, type, title)`` lookup.

        Accepts an injected connection so the collision check runs inside the
        caller's serialized unit (on PostgreSQL it must share the connection
        that holds the advisory lock).
        """

        def run(c: Any) -> VaultItemRow | None:
            row = c.execute(
                f"SELECT {_LIST_COLUMNS} FROM vault_items "
                "WHERE user_id = ? AND item_type = ? AND title = ?",
                (user_id, item_type, title),
            ).fetchone()
            return VaultItemRow.from_row(row) if row is not None else None

        if conn is not None:
            return run(conn)
        with self._db.connect() as own:
            return run(own)

    def insert_new(
        self,
        conn: Any | None = None,
        *,
        vault_item_id: str,
        user_id: int,
        item_type: str,
        title: str,
        origin: str | None,
        fields_blob: bytes,
    ) -> bool:
        """Cap-guarded pure insert as ONE conditional statement.

        Keeping the count guard and the insert in a single statement makes the
        cap check atomic under the per-user serialization the caller holds;
        ``False`` means the cap blocked the row. The caller mints
        ``vault_item_id`` because the envelope must be sealed against it first.
        """

        def run(c: Any) -> bool:
            ts = now_ts()
            cursor = c.execute(
                "INSERT INTO vault_items "
                "(vault_item_id, user_id, item_type, title, origin, fields_blob, "
                "created_at, updated_at) "
                "SELECT ?, ?, ?, ?, ?, ?, ?, ? "
                "WHERE (SELECT COUNT(*) FROM vault_items WHERE user_id = ?) < ?",
                (
                    vault_item_id,
                    user_id,
                    item_type,
                    title,
                    origin,
                    fields_blob,
                    ts,
                    ts,
                    user_id,
                    VAULT_ITEMS_MAX_PER_USER,
                ),
            )
            return bool(cursor.rowcount)

        if conn is not None:
            return run(conn)
        with self._db.transaction() as own:
            # Under READ COMMITTED two bare count+insert statements can both
            # pass, so the self-owned fallback takes the same per-user lock
            # the service-level owner holds on the injected-conn path.
            if self._db.dialect == "postgresql":
                own.execute("SELECT pg_advisory_xact_lock(?)", (user_id,))
            return run(own)

    def rotate_by_identity(
        self,
        conn: Any | None = None,
        *,
        vault_item_id: str,
        fields_blob: bytes,
        origin: str | None,
    ) -> int:
        """Rotate the envelope BY IDENTITY; returns the affected rowcount.

        ``COALESCE`` keeps the stored origin when the rotating submit omits
        one. Never inserts: a zero rowcount means the row is gone, and the
        caller re-derives instead of binding a new row to a dead id.
        """

        def run(c: Any) -> int:
            cursor = c.execute(
                "UPDATE vault_items SET fields_blob = ?, "
                "origin = COALESCE(?, origin), updated_at = ? "
                "WHERE vault_item_id = ?",
                (fields_blob, origin, now_ts(), vault_item_id),
            )
            return int(cursor.rowcount)

        if conn is not None:
            return run(conn)
        with self._db.transaction() as own:
            return run(own)

    def delete(self, vault_item_id: str, user_id: int, *, conn: Any | None = None) -> bool:
        def run(c: Any) -> bool:
            cursor = c.execute(
                "DELETE FROM vault_items WHERE vault_item_id = ? AND user_id = ?",
                (vault_item_id, user_id),
            )
            return bool(cursor.rowcount)

        if conn is not None:
            return run(conn)
        with self._db.transaction() as own:
            return run(own)
