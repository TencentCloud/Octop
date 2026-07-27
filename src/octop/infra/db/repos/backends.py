"""Storage backend table access."""

from __future__ import annotations

from dataclasses import dataclass

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import (
    DbRow,
    bool_int,
    insert_returning_id,
    map_rows,
    now_ts,
    partial_updates,
)


@dataclass(frozen=True)
class BackendRow:
    id: int
    name: str
    kind: str
    endpoint: str | None
    access_key: str | None
    secret_key: str | None
    bucket: str | None
    region: str | None
    config_json: str | None
    note: str | None
    enabled: int
    created_at: int
    updated_at: int

    @classmethod
    def from_row(cls, r: DbRow) -> BackendRow:
        return cls(
            id=r["id"],
            name=r["name"],
            kind=r["kind"],
            endpoint=r["endpoint"],
            access_key=r["access_key"],
            secret_key=r["secret_key"],
            bucket=r["bucket"],
            region=r["region"],
            config_json=r["config_json"],
            note=r["note"],
            enabled=r["enabled"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )


class BackendRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def create(
        self,
        *,
        name: str,
        kind: str,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        bucket: str | None = None,
        region: str | None = None,
        config_json: str | None = None,
        note: str | None = None,
    ) -> int:
        ts = now_ts()
        with self._db.transaction() as conn:
            return insert_returning_id(
                conn,
                "INSERT INTO storage_backends"
                "(name, kind, endpoint, access_key, secret_key, bucket, region,"
                " config_json, note, enabled, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
                (
                    name,
                    kind,
                    endpoint,
                    access_key,
                    secret_key,
                    bucket,
                    region,
                    config_json,
                    note,
                    ts,
                    ts,
                ),
            )

    def get(self, backend_id: int) -> BackendRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT * FROM storage_backends WHERE id = ?", (backend_id,)
            ).fetchone()
        return BackendRow.from_row(r) if r else None

    def get_by_name(self, name: str) -> BackendRow | None:
        with self._db.connect() as conn:
            r = conn.execute("SELECT * FROM storage_backends WHERE name = ?", (name,)).fetchone()
        return BackendRow.from_row(r) if r else None

    def list_all(self) -> list[BackendRow]:
        with self._db.connect() as conn:
            rows = conn.execute("SELECT * FROM storage_backends ORDER BY name").fetchall()
        return map_rows(rows, BackendRow)

    def update(
        self,
        backend_id: int,
        *,
        kind: str | None = None,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        bucket: str | None = None,
        region: str | None = None,
        config_json: str | None = None,
        note: str | None = None,
        enabled: bool | None = None,
    ) -> None:
        fields, params = partial_updates(
            [
                ("kind", kind),
                ("endpoint", endpoint),
                ("access_key", access_key),
                ("secret_key", secret_key),
                ("bucket", bucket),
                ("region", region),
                ("config_json", config_json),
                ("note", note),
            ]
        )
        if enabled is not None:
            fields.append("enabled = ?")
            params.append(bool_int(enabled))
        if not fields:
            return
        fields.append("updated_at = ?")
        params.append(now_ts())
        params.append(backend_id)
        with self._db.transaction() as conn:
            conn.execute(
                f"UPDATE storage_backends SET {', '.join(fields)} WHERE id = ?",
                params,
            )

    def delete(self, backend_id: int) -> None:
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM storage_backends WHERE id = ?", (backend_id,))
