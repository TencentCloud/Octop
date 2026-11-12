"""Which user groups may see one resource."""

from __future__ import annotations

from octop.infra.db.pool import DatabasePool


class ResourceGroupGrantRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def list_all(self) -> list[tuple[str, str, str]]:
        """Return ``(user_group_id, resource_type, resource_key)`` rows."""
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT user_group_id, resource_type, resource_key FROM resource_group_grant"
                " ORDER BY resource_type, resource_key"
            ).fetchall()
        return [
            (str(row["user_group_id"]), str(row["resource_type"]), str(row["resource_key"]))
            for row in rows
        ]

    def group_ids(self, resource_type: str, resource_key: str) -> set[str]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT user_group_id FROM resource_group_grant"
                " WHERE resource_type = ? AND resource_key = ?",
                (resource_type, resource_key),
            ).fetchall()
        return {str(row["user_group_id"]) for row in rows}

    def group_ids_by_resource(self, resource_type: str) -> dict[str, set[str]]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT resource_key, user_group_id FROM resource_group_grant"
                " WHERE resource_type = ?",
                (resource_type,),
            ).fetchall()
        out: dict[str, set[str]] = {}
        for row in rows:
            out.setdefault(str(row["resource_key"]), set()).add(str(row["user_group_id"]))
        return out

    def replace(self, resource_type: str, resource_key: str, group_ids: list[str]) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "DELETE FROM resource_group_grant WHERE resource_type = ? AND resource_key = ?",
                (resource_type, resource_key),
            )
            for group_id in group_ids:
                conn.execute(
                    "INSERT INTO resource_group_grant(resource_type, resource_key, user_group_id)"
                    " VALUES (?, ?, ?)",
                    (resource_type, resource_key, group_id),
                )

    def delete_resource(self, resource_type: str, resource_key: str) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "DELETE FROM resource_group_grant WHERE resource_type = ? AND resource_key = ?",
                (resource_type, resource_key),
            )

    def rename_key(self, resource_type: str, old: str, new: str) -> None:
        if old == new:
            return
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE resource_group_grant SET resource_key = ?"
                " WHERE resource_type = ? AND resource_key = ?",
                (new, resource_type, old),
            )

    def rewrite_prefix(self, resource_type: str, old_prefix: str, new_prefix: str) -> None:
        """Rewrite ``old_prefix/...`` keys, including an exact ``old_prefix`` key."""
        if old_prefix == new_prefix:
            return
        needle = f"{old_prefix}/"
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT resource_key FROM resource_group_grant WHERE resource_type = ?",
                (resource_type,),
            ).fetchall()
        updates: list[tuple[str, str]] = []
        for row in rows:
            key = str(row["resource_key"])
            if key == old_prefix:
                updates.append((new_prefix, key))
            elif key.startswith(needle):
                updates.append((new_prefix + key[len(old_prefix) :], key))
        if not updates:
            return
        with self._db.transaction() as conn:
            for new_key, old_key in updates:
                conn.execute(
                    "UPDATE resource_group_grant SET resource_key = ?"
                    " WHERE resource_type = ? AND resource_key = ?",
                    (new_key, resource_type, old_key),
                )

    def delete_prefix(self, resource_type: str, prefix: str) -> None:
        needle = f"{prefix}/%"
        exact = prefix
        with self._db.transaction() as conn:
            conn.execute(
                "DELETE FROM resource_group_grant"
                " WHERE resource_type = ? AND (resource_key = ? OR resource_key LIKE ?)",
                (resource_type, exact, needle),
            )
