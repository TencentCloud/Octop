"""Agent table access."""

from __future__ import annotations

from dataclasses import dataclass

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import UNSET, DbRow, bool_int, map_rows, now_ts, optional_updates


@dataclass(frozen=True)
class AgentRow:
    id: int
    agent_id: str
    user_id: int | None
    name: str
    description: str | None
    persona_mbti: str | None
    default_model: str | None
    system_prompt: str | None
    enabled: int
    config_json: str | None
    last_state: str | None
    last_error: str | None
    created_at: int
    updated_at: int
    icon: str | None = None
    template_name: str | None = None

    @classmethod
    def from_row(cls, r: DbRow) -> AgentRow:
        return cls(
            id=r["id"],
            agent_id=r["agent_id"],
            user_id=r["user_id"],
            name=r["name"],
            description=r["description"],
            persona_mbti=r["persona_mbti"],
            default_model=r["default_model"],
            system_prompt=r["system_prompt"],
            enabled=r["enabled"],
            config_json=r["config_json"],
            last_state=r["last_state"],
            last_error=r["last_error"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            icon=r["icon"],
            template_name=r["template_name"],
        )


class AgentRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def create(
        self,
        *,
        agent_id: str,
        user_id: int | None,
        name: str,
        description: str | None = None,
        persona_mbti: str | None = None,
        default_model: str | None = None,
        system_prompt: str | None = None,
        config_json: str | None = None,
        icon: str | None = None,
        template_name: str | None = None,
    ) -> str:
        ts = now_ts()
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO agents(agent_id, user_id, name, description, "
                "persona_mbti, default_model, system_prompt, enabled, config_json, icon, "
                "template_name, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)",
                (
                    agent_id,
                    user_id,
                    name,
                    description,
                    persona_mbti,
                    default_model,
                    system_prompt,
                    config_json,
                    icon,
                    template_name,
                    ts,
                    ts,
                ),
            )
        return agent_id

    def get(self, agent_id: str) -> AgentRow | None:
        with self._db.connect() as conn:
            r = conn.execute("SELECT * FROM agents WHERE agent_id = ?", (agent_id,)).fetchone()
        return AgentRow.from_row(r) if r else None

    def list_by_user(self, user_id: int, *, include_disabled: bool = True) -> list[AgentRow]:
        sql = "SELECT * FROM agents WHERE user_id = ?"
        if not include_disabled:
            sql += " AND enabled = 1"
        sql += " ORDER BY created_at ASC, id ASC"
        with self._db.connect() as conn:
            rows = conn.execute(sql, (user_id,)).fetchall()
        return map_rows(rows, AgentRow)

    def list_all(self, *, include_disabled: bool = True) -> list[AgentRow]:
        sql = "SELECT * FROM agents"
        if not include_disabled:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY created_at ASC, id ASC"
        with self._db.connect() as conn:
            rows = conn.execute(sql).fetchall()
        return map_rows(rows, AgentRow)

    def set_enabled(self, agent_id: str, enabled: bool) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE agents SET enabled = ?, updated_at = ? WHERE agent_id = ?",
                (bool_int(enabled), now_ts(), agent_id),
            )

    def set_state(self, agent_id: str, state: str, *, error: str | None = None) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE agents SET last_state = ?, last_error = ?, updated_at = ? "
                "WHERE agent_id = ?",
                (state, error, now_ts(), agent_id),
            )

    def update_config(
        self,
        agent_id: str,
        *,
        name: str | None | object = UNSET,
        description: str | None | object = UNSET,
        persona_mbti: str | None | object = UNSET,
        default_model: str | None | object = UNSET,
        system_prompt: str | None | object = UNSET,
        config_json: str | None | object = UNSET,
        icon: str | None | object = UNSET,
        template_name: str | None | object = UNSET,
    ) -> None:
        fields, params = optional_updates(
            [
                ("name", name),
                ("description", description),
                ("persona_mbti", persona_mbti),
                ("default_model", default_model),
                ("system_prompt", system_prompt),
                ("config_json", config_json),
                ("icon", icon),
                ("template_name", template_name),
            ]
        )
        if not fields:
            return
        fields.append("updated_at = ?")
        params.append(now_ts())
        params.append(agent_id)
        with self._db.transaction() as conn:
            conn.execute(f"UPDATE agents SET {', '.join(fields)} WHERE agent_id = ?", params)

    def delete(self, agent_id: str) -> None:
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM agents WHERE agent_id = ?", (agent_id,))
