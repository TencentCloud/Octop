"""Settings KV store — lightweight key/value pairs backed by SQLite."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from octop.infra.db.pool import DatabasePool


class SettingsRepo:
    _KEY_ACTIVE_MODEL = "active_model"

    def __init__(self, db: DatabasePool):
        self._db = db

    def get(self, key: str) -> str | None:
        with self._db.connect() as conn:
            r = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return r["value"] if r else None

    def get_many(self, keys: Sequence[str]) -> dict[str, str]:
        if not keys:
            return {}
        placeholders = ", ".join("?" for _ in keys)
        with self._db.connect() as conn:
            rows = conn.execute(
                f"SELECT key, value FROM settings WHERE key IN ({placeholders})",
                tuple(keys),
            ).fetchall()
        return {row["key"]: row["value"] for row in rows}

    def set(self, key: str, value: str) -> None:
        self.set_many({key: value})

    def set_many(self, values: Mapping[str, str]) -> None:
        with self._db.transaction() as conn:
            for key, value in values.items():
                conn.execute(
                    "INSERT INTO settings(key, value) VALUES(?, ?)"
                    " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, value),
                )

    def delete(self, key: str) -> None:
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM settings WHERE key = ?", (key,))

    def get_active_model(self) -> tuple[str, str]:
        """Return (provider_name, model_id); empty strings if not set."""
        raw = self.get(self._KEY_ACTIVE_MODEL) or ""
        name, _, model = raw.partition("/")
        return name, model

    def set_active_model(self, provider_name: str, model_id: str) -> None:
        self.set(self._KEY_ACTIVE_MODEL, f"{provider_name}/{model_id}")
