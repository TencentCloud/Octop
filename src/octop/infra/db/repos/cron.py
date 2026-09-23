"""Cron jobs table access."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from octop.infra.cron.task_type import (
    DEFAULT_CRON_TASK_TYPE,
    CronTaskType,
    default_cron_name,
    normalize_cron_task_type,
    require_cron_task_type,
)
from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import (
    UNSET,
    DbRow,
    bool_int,
    map_rows,
    now_ts,
    partial_updates,
)

__all__ = [
    "DEFAULT_CRON_TASK_TYPE",
    "CronJobRepo",
    "CronJobRow",
    "CronTaskType",
    "normalize_cron_task_type",
    "require_cron_task_type",
]


def _encode_mcp_servers(names: list[str] | None) -> str:
    cleaned = [str(n).strip() for n in (names or []) if str(n).strip()]
    return json.dumps(cleaned, ensure_ascii=False)


def _decode_mcp_servers(raw: Any) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        return [str(n).strip() for n in raw if str(n).strip()]
    try:
        parsed = json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(n).strip() for n in parsed if str(n).strip()]


def _optional_str(r: DbRow, key: str) -> str | None:
    try:
        value = r[key]
    except (KeyError, IndexError):
        return None
    text = str(value).strip() if value else ""
    return text or None


@dataclass(frozen=True)
class CronJobRow:
    id: int
    cron_id: str
    name: str
    agent_id: str
    user_id: int
    trigger: str
    prompt: str
    session_key: str
    model: str | None
    fresh_thread: int
    enabled: int
    task_type: str
    mcp_servers: list[str]
    last_run_at: int | None
    last_status: str | None
    last_error: str | None
    token_budget_24h: int | None
    budget_tokens_used: int
    budget_window_started_at: int | None
    created_at: int
    updated_at: int

    @classmethod
    def from_row(cls, r: DbRow) -> CronJobRow:
        return cls(
            id=r["id"],
            cron_id=r["cron_id"],
            name=_optional_str(r, "name") or default_cron_name(r["prompt"], r["cron_id"]),
            agent_id=r["agent_id"],
            user_id=r["user_id"],
            trigger=r["schedule_spec"],
            prompt=r["prompt"],
            session_key=r["session_key"],
            model=r["model"],
            fresh_thread=r["fresh_thread"],
            enabled=r["enabled"],
            task_type=normalize_cron_task_type(str(r["task_type"])),
            mcp_servers=_decode_mcp_servers(r["mcp_servers"]),
            last_run_at=r["last_run_at"],
            last_status=r["last_status"],
            last_error=r["last_error"],
            token_budget_24h=r["token_budget_24h"],
            budget_tokens_used=r["budget_tokens_used"],
            budget_window_started_at=r["budget_window_started_at"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )

    def to_public_dict(self, *, include_agent: bool = False) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.cron_id,
            "name": self.name,
            "trigger": self.trigger,
            "prompt": self.prompt,
            "session_key": self.session_key,
            "model": self.model,
            "fresh_thread": bool(self.fresh_thread),
            "enabled": bool(self.enabled),
            "task_type": self.task_type,
            "mcp_servers": list(self.mcp_servers),
            "last_run_at": self.last_run_at,
            "last_status": self.last_status,
            "token_budget_24h": self.token_budget_24h,
            "budget_tokens_used": self.budget_tokens_used,
        }
        if include_agent:
            out["agent_id"] = self.agent_id
            out["last_error"] = self.last_error
        return out


class CronJobRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def create(
        self,
        *,
        cron_id: str,
        agent_id: str,
        user_id: int,
        trigger: str,
        prompt: str,
        session_key: str,
        fresh_thread: bool = False,
        model: str | None = None,
        task_type: CronTaskType = DEFAULT_CRON_TASK_TYPE,
        mcp_servers: list[str] | None = None,
        enabled: bool = True,
        name: str | None = None,
        token_budget_24h: int | None = None,
    ) -> str:
        ts = now_ts()
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO cron_jobs(cron_id, name, agent_id, user_id, schedule_spec, prompt, "
                "session_key, model, fresh_thread, task_type, mcp_servers, enabled, "
                "token_budget_24h, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    cron_id,
                    (name or "").strip() or default_cron_name(prompt, cron_id),
                    agent_id,
                    user_id,
                    trigger,
                    prompt,
                    session_key,
                    model,
                    bool_int(fresh_thread),
                    task_type,
                    _encode_mcp_servers(mcp_servers),
                    bool_int(enabled),
                    token_budget_24h,
                    ts,
                    ts,
                ),
            )
        return cron_id

    def get(self, cron_id: str) -> CronJobRow | None:
        with self._db.connect() as conn:
            r = conn.execute("SELECT * FROM cron_jobs WHERE cron_id = ?", (cron_id,)).fetchone()
        return CronJobRow.from_row(r) if r else None

    def list_by_agent(
        self,
        agent_id: str,
        *,
        include_disabled: bool = True,
        user_id: int | None = None,
    ) -> list[CronJobRow]:
        sql = "SELECT * FROM cron_jobs WHERE agent_id = ?"
        params: list[object] = [agent_id]
        if user_id is not None:
            sql += " AND user_id = ?"
            params.append(user_id)
        if not include_disabled:
            sql += " AND enabled = 1"
        sql += " ORDER BY created_at DESC"
        with self._db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return map_rows(rows, CronJobRow)

    def list_all(self, *, include_disabled: bool = True) -> list[CronJobRow]:
        sql = "SELECT * FROM cron_jobs"
        if not include_disabled:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY agent_id, created_at DESC"
        with self._db.connect() as conn:
            rows = conn.execute(sql).fetchall()
        return map_rows(rows, CronJobRow)

    def set_run_status(
        self,
        cron_id: str,
        *,
        ts: int,
        status: str,
        error: str | None = None,
    ) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE cron_jobs SET last_run_at = ?, last_status = ?, last_error = ?, "
                "updated_at = ? WHERE cron_id = ?",
                (ts, status, error, now_ts(), cron_id),
            )

    def apply_token_budget(
        self,
        cron_id: str,
        *,
        run_tokens: int,
        window_seconds: int = 86_400,
    ) -> bool:
        """Add one run's tokens to the 24h window; disable the job when over budget.

        The window is anchored at the first counted run and restarts whenever it
        has expired — a fixed 24h window, not a strict rolling one. Jobs without
        a budget are left untouched (no writes). Returns True when the budget
        was exceeded and the row was disabled.
        """
        now = now_ts()
        with self._db.transaction() as conn:
            row = conn.execute(
                "SELECT token_budget_24h, budget_tokens_used, budget_window_started_at "
                "FROM cron_jobs WHERE cron_id = ?",
                (cron_id,),
            ).fetchone()
            if row is None:
                return False
            budget = row["token_budget_24h"]
            if budget is None or int(budget) <= 0:
                return False
            window_start = row["budget_window_started_at"]
            used = int(row["budget_tokens_used"] or 0)
            if window_start is None or now - int(window_start) >= window_seconds:
                window_start = now
                used = 0
            used += max(0, int(run_tokens))
            fields = "budget_tokens_used = ?, budget_window_started_at = ?"
            params: list[object] = [used, window_start]
            tripped = used > int(budget)
            if tripped:
                fields += ", enabled = 0, updated_at = ?"
                params.append(now)
            params.append(cron_id)
            conn.execute(
                f"UPDATE cron_jobs SET {fields} WHERE cron_id = ?",
                params,
            )
            return tripped

    def update(
        self,
        cron_id: str,
        *,
        trigger: str | None = None,
        name: str | None = None,
        prompt: str | None = None,
        session_key: str | None = None,
        fresh_thread: bool | None = None,
        enabled: bool | None = None,
        task_type: CronTaskType | None = None,
        model: str | None | object = UNSET,
        mcp_servers: list[str] | None | object = UNSET,
        token_budget_24h: int | None | object = UNSET,
    ) -> None:
        fields, params = partial_updates(
            [
                ("schedule_spec", trigger),
                ("name", name),
                ("prompt", prompt),
                ("session_key", session_key),
                ("task_type", task_type),
            ]
        )
        if fresh_thread is not None:
            fields.append("fresh_thread = ?")
            params.append(bool_int(fresh_thread))
        if model is not UNSET:
            fields.append("model = ?")
            params.append(model)
        if mcp_servers is not UNSET:
            fields.append("mcp_servers = ?")
            params.append(
                _encode_mcp_servers(mcp_servers if isinstance(mcp_servers, list) else None)
            )
        if token_budget_24h is not UNSET:
            fields.append("token_budget_24h = ?")
            params.append(int(token_budget_24h) if isinstance(token_budget_24h, int) else None)
        if enabled is not None:
            fields.append("enabled = ?")
            params.append(bool_int(enabled))
        if not fields:
            return
        fields.append("updated_at = ?")
        params.append(now_ts())
        params.append(cron_id)
        with self._db.transaction() as conn:
            conn.execute(f"UPDATE cron_jobs SET {', '.join(fields)} WHERE cron_id = ?", params)

    def delete(self, cron_id: str) -> None:
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM cron_jobs WHERE cron_id = ?", (cron_id,))
