"""Settings KV store — lightweight key/value pairs backed by SQLite."""

from __future__ import annotations

import json

from octop.infra.db.pool import DatabasePool


class SettingsRepo:
    _KEY_ACTIVE_MODEL = "active_model"
    _KEY_EXPERT_VISIBILITY = "expert_visibility"

    def __init__(self, db: DatabasePool):
        self._db = db

    def get(self, key: str) -> str | None:
        with self._db.connect() as conn:
            r = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return r["value"] if r else None

    def set(self, key: str, value: str) -> None:
        with self._db.transaction() as conn:
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

    def get_expert_visibility(self) -> dict[str, bool]:
        """Return the expert-visibility policy.

        ``hide_builtin_experts`` / ``hide_market`` default to ``False`` so an
        unset key preserves the historic (fully visible) behaviour.
        """
        raw = self.get(self._KEY_EXPERT_VISIBILITY)
        hide_builtin = False
        hide_market = False
        if raw:
            try:
                data = json.loads(raw)
            except (TypeError, ValueError):
                data = {}
            if isinstance(data, dict):
                hide_builtin = bool(data.get("hide_builtin_experts", False))
                hide_market = bool(data.get("hide_market", False))
        return {"hide_builtin_experts": hide_builtin, "hide_market": hide_market}

    def set_expert_visibility(
        self,
        *,
        hide_builtin_experts: bool,
        hide_market: bool,
    ) -> dict[str, bool]:
        """Persist the expert-visibility policy and return the stored value."""
        policy = {
            "hide_builtin_experts": bool(hide_builtin_experts),
            "hide_market": bool(hide_market),
        }
        self.set(self._KEY_EXPERT_VISIBILITY, json.dumps(policy))
        return policy
