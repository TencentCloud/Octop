"""Path-addressed file trees in the control-plane database.

One row is one file. ``namespace`` separates plugins from published-expert
snapshots. The bytes are the source of truth; a process may write a temporary
copy when a caller needs a directory.
"""

from __future__ import annotations

from typing import Any

from octop.infra.db.pool import DatabasePool


def _as_bytes(value: Any) -> bytes:
    if isinstance(value, memoryview):
        return value.tobytes()
    return bytes(value)


def safe_relative_path(path: str) -> str | None:
    """Return a normalized relative path, or None when it is unsafe."""
    text = path.replace("\\", "/").strip()
    if not text or text.startswith("/"):
        return None
    parts = [part for part in text.split("/") if part and part != "."]
    if not parts or any(part == ".." for part in parts):
        return None
    return "/".join(parts)


class ControlFileRepo:
    """File bytes shared by every Octop process on this database."""

    PLUGIN = "plugin"
    PUBLISHED_EXPERT = "published_expert"

    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def owners(self, namespace: str) -> list[str]:
        with self._db.connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT owner_id FROM control_files
                WHERE namespace = ?
                ORDER BY owner_id
                """,
                (namespace,),
            ).fetchall()
        return [str(row["owner_id"]) for row in rows]

    def has_owner(self, namespace: str, owner_id: str) -> bool:
        with self._db.connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM control_files
                WHERE namespace = ? AND owner_id = ?
                LIMIT 1
                """,
                (namespace, owner_id),
            ).fetchone()
        return row is not None

    def get(self, namespace: str, owner_id: str, path: str) -> bytes | None:
        relative = safe_relative_path(path)
        if relative is None:
            return None
        with self._db.connect() as conn:
            row = conn.execute(
                """
                SELECT content FROM control_files
                WHERE namespace = ? AND owner_id = ? AND path = ?
                """,
                (namespace, owner_id, relative),
            ).fetchone()
        if row is None:
            return None
        return _as_bytes(row["content"])

    def paths(self, namespace: str, owner_id: str) -> list[str]:
        with self._db.connect() as conn:
            rows = conn.execute(
                """
                SELECT path FROM control_files
                WHERE namespace = ? AND owner_id = ?
                ORDER BY path
                """,
                (namespace, owner_id),
            ).fetchall()
        return [str(row["path"]) for row in rows]

    def list_files(self, namespace: str, owner_id: str) -> list[tuple[str, bytes]]:
        with self._db.connect() as conn:
            rows = conn.execute(
                """
                SELECT path, content FROM control_files
                WHERE namespace = ? AND owner_id = ?
                ORDER BY path
                """,
                (namespace, owner_id),
            ).fetchall()
        return [(str(row["path"]), _as_bytes(row["content"])) for row in rows]

    def replace_tree(self, namespace: str, owner_id: str, files: list[tuple[str, bytes]]) -> None:
        rows: list[tuple[str, str, str, bytes]] = []
        for path, content in files:
            relative = safe_relative_path(path)
            if relative is None:
                continue
            rows.append((namespace, owner_id, relative, content))
        with self._db.transaction() as conn:
            conn.execute(
                "DELETE FROM control_files WHERE namespace = ? AND owner_id = ?",
                (namespace, owner_id),
            )
            for row in rows:
                conn.execute(
                    """
                    INSERT INTO control_files(namespace, owner_id, path, content)
                    VALUES (?, ?, ?, ?)
                    """,
                    row,
                )

    def delete_owner(self, namespace: str, owner_id: str) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "DELETE FROM control_files WHERE namespace = ? AND owner_id = ?",
                (namespace, owner_id),
            )
