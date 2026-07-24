"""Provider table access."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import (
    DbRow,
    bool_int,
    insert_returning_id,
    map_rows,
    now_ts,
    partial_updates,
)

if TYPE_CHECKING:
    from octop.infra.db.repos.agents import AgentRepo


@dataclass(frozen=True)
class ProviderRow:
    id: int
    name: str
    kind: str
    base_url: str | None
    api_key: str | None
    extra_json: str | None
    models_json: str | None
    note: str | None
    enabled: int
    created_at: int
    updated_at: int

    @classmethod
    def from_row(cls, r: DbRow) -> ProviderRow:
        return cls(
            id=r["id"],
            name=r["name"],
            kind=r["kind"],
            base_url=r["base_url"],
            api_key=r["api_key"],
            extra_json=r["extra_json"],
            models_json=r["models_json"],
            note=r["note"],
            enabled=r["enabled"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )

    def get_models(self) -> list[dict[str, object]]:
        """Return the models list from ``models_json``."""
        if self.models_json:
            try:
                data = json.loads(self.models_json)
                if isinstance(data, list):
                    return data
            except (json.JSONDecodeError, ValueError):
                pass
        return []


class ProviderRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def create(
        self,
        *,
        name: str,
        kind: str,
        base_url: str | None = None,
        api_key: str | None = None,
        extra_json: str | None = None,
        models_json: str | None = None,
        note: str | None = None,
    ) -> int:
        ts = now_ts()
        with self._db.transaction() as conn:
            return insert_returning_id(
                conn,
                "INSERT INTO providers(name, kind, base_url, api_key, "
                "extra_json, models_json, note, enabled, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
                (name, kind, base_url, api_key, extra_json, models_json, note, ts, ts),
            )

    def get(self, provider_id: int) -> ProviderRow | None:
        with self._db.connect() as conn:
            r = conn.execute("SELECT * FROM providers WHERE id = ?", (provider_id,)).fetchone()
        return ProviderRow.from_row(r) if r else None

    def get_by_name(self, name: str) -> ProviderRow | None:
        with self._db.connect() as conn:
            r = conn.execute("SELECT * FROM providers WHERE name = ?", (name,)).fetchone()
        return ProviderRow.from_row(r) if r else None

    def list_all(self) -> list[ProviderRow]:
        with self._db.connect() as conn:
            rows = conn.execute("SELECT * FROM providers ORDER BY name").fetchall()
        return map_rows(rows, ProviderRow)

    def update(
        self,
        provider_id: int,
        *,
        kind: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        extra_json: str | None = None,
        models_json: str | None = None,
        note: str | None = None,
        enabled: bool | None = None,
    ) -> None:
        fields, params = partial_updates(
            [
                ("kind", kind),
                ("base_url", base_url),
                ("api_key", api_key),
                ("extra_json", extra_json),
                ("models_json", models_json),
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
            conn.execute(f"UPDATE providers SET {', '.join(fields)} WHERE id = ?", params)

    def delete(self, provider_id: int) -> None:
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))

    def find_referencing_agent_ids(self, agent_repo: AgentRepo, provider_name: str) -> list[str]:
        out: list[str] = []
        for row in agent_repo.list_all():
            cfg = json.loads(row.config_json or "{}")
            if provider_name in (cfg.get("providers") or []):
                out.append(row.agent_id)
        return out
