"""Voice provider table access."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

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
class VoiceProviderRow:
    id: int
    name: str
    kind: str
    capability: str
    base_url: str | None
    api_key: str | None
    extra_json: str | None
    note: str | None
    enabled: int
    created_at: int
    updated_at: int

    @classmethod
    def from_row(cls, r: DbRow) -> VoiceProviderRow:
        return cls(
            id=r["id"],
            name=r["name"],
            kind=r["kind"],
            capability=r["capability"],
            base_url=r["base_url"],
            api_key=r["api_key"],
            extra_json=r["extra_json"],
            note=r["note"],
            enabled=r["enabled"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )

    def get_extra(self) -> dict[str, Any]:
        if not self.extra_json:
            return {}
        try:
            data = json.loads(self.extra_json)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, ValueError):
            pass
        return {}


class VoiceProviderRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def create(
        self,
        *,
        name: str,
        kind: str,
        capability: str,
        base_url: str | None = None,
        api_key: str | None = None,
        extra_json: str | None = None,
        note: str | None = None,
    ) -> int:
        ts = now_ts()
        with self._db.transaction() as conn:
            return insert_returning_id(
                conn,
                "INSERT INTO voice_providers("
                "name, kind, capability, base_url, api_key, extra_json, note, "
                "enabled, created_at, updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
                (name, kind, capability, base_url, api_key, extra_json, note, ts, ts),
            )

    def get(self, provider_id: int) -> VoiceProviderRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT * FROM voice_providers WHERE id = ?", (provider_id,)
            ).fetchone()
        return VoiceProviderRow.from_row(r) if r else None

    def get_by_name(self, name: str) -> VoiceProviderRow | None:
        with self._db.connect() as conn:
            r = conn.execute("SELECT * FROM voice_providers WHERE name = ?", (name,)).fetchone()
        return VoiceProviderRow.from_row(r) if r else None

    def list_all(self) -> list[VoiceProviderRow]:
        with self._db.connect() as conn:
            rows = conn.execute("SELECT * FROM voice_providers ORDER BY name").fetchall()
        return map_rows(rows, VoiceProviderRow)

    def update(
        self,
        provider_id: int,
        *,
        kind: str | None = None,
        capability: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        extra_json: str | None = None,
        note: str | None = None,
        enabled: bool | None = None,
    ) -> None:
        fields, params = partial_updates(
            [
                ("kind", kind),
                ("capability", capability),
                ("base_url", base_url),
                ("api_key", api_key),
                ("extra_json", extra_json),
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
        params.append(provider_id)
        with self._db.transaction() as conn:
            conn.execute(f"UPDATE voice_providers SET {', '.join(fields)} WHERE id = ?", params)

    def delete(self, provider_id: int) -> None:
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM voice_providers WHERE id = ?", (provider_id,))
