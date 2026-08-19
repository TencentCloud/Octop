"""Agent table access."""

from __future__ import annotations

from dataclasses import dataclass

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import UNSET, DbRow, bool_int, map_rows, now_ts, optional_updates


def _opt_str(r: DbRow, key: str) -> str | None:
    try:
        value = r[key]
    except (KeyError, IndexError):
        return None
    if value is None:
        return None
    text = str(value)
    return text if text else None


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
    is_shared: int = 0
    color: str | None = None
    icon_name: str | None = None
    icon_url: str | None = None
    skill_package_ids: str | None = None
    published_expert_id: str | None = None
    welcome_message: str | None = None

    @classmethod
    def from_row(cls, r: DbRow) -> AgentRow:
        try:
            is_shared = int(r["is_shared"])
        except KeyError:
            is_shared = 0
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
            is_shared=is_shared,
            color=_opt_str(r, "color"),
            icon_name=_opt_str(r, "icon_name"),
            icon_url=_opt_str(r, "icon_url"),
            skill_package_ids=_opt_str(r, "skill_package_ids"),
            published_expert_id=_opt_str(r, "published_expert_id"),
            welcome_message=_opt_str(r, "welcome_message"),
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
        color: str | None = None,
        icon_name: str | None = None,
        icon_url: str | None = None,
        skill_package_ids: str | None = None,
        published_expert_id: str | None = None,
        welcome_message: str | None = None,
    ) -> str:
        ts = now_ts()
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO agents(agent_id, user_id, name, description, "
                "persona_mbti, default_model, system_prompt, enabled, config_json, icon, "
                "template_name, color, icon_name, icon_url, skill_package_ids, "
                "published_expert_id, welcome_message, "
                "created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                    color,
                    icon_name,
                    icon_url,
                    skill_package_ids,
                    published_expert_id,
                    welcome_message,
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

    def set_shared(self, agent_id: str, shared: bool) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE agents SET is_shared = ?, updated_at = ? WHERE agent_id = ?",
                (bool_int(shared), now_ts(), agent_id),
            )

    def list_shared(self, *, exclude_user_id: int | None = None) -> list[AgentRow]:
        sql = "SELECT * FROM agents WHERE is_shared = 1 AND enabled = 1"
        params: list[object] = []
        if exclude_user_id is not None:
            sql += " AND user_id != ?"
            params.append(exclude_user_id)
        sql += " ORDER BY created_at ASC, id ASC"
        with self._db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return map_rows(rows, AgentRow)

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
        color: str | None | object = UNSET,
        icon_name: str | None | object = UNSET,
        icon_url: str | None | object = UNSET,
        skill_package_ids: str | None | object = UNSET,
        published_expert_id: str | None | object = UNSET,
        welcome_message: str | None | object = UNSET,
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
                ("color", color),
                ("icon_name", icon_name),
                ("icon_url", icon_url),
                ("skill_package_ids", skill_package_ids),
                ("published_expert_id", published_expert_id),
                ("welcome_message", welcome_message),
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
