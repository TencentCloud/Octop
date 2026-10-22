"""SQL persistence for host-owned OpenDesign generation tasks."""

from __future__ import annotations

import json
from typing import Any

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import now_ts
from octop.infra.utils.ulid import new_ulid


class OpenDesignTaskRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def record(
        self,
        *,
        user_id: int,
        instance_id: str,
        agent_id: str,
        thread_id: str,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        ts = now_ts()
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO open_design_tasks(task_id,user_id,instance_id,agent_id,thread_id,project,request_id,run_id,status,created_at,updated_at,result_json) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id,instance_id,agent_id,thread_id,request_id) DO UPDATE SET "
                "run_id=COALESCE(excluded.run_id,open_design_tasks.run_id), status=excluded.status, updated_at=excluded.updated_at, revision=open_design_tasks.revision+1",
                (
                    new_ulid(),
                    user_id,
                    instance_id,
                    agent_id,
                    thread_id,
                    str(state["project"]),
                    str(state["requestId"]),
                    state.get("runId"),
                    state.get("status", "submitting"),
                    ts,
                    ts,
                    json.dumps(
                        {"_originUserSeq": state["origin_user_seq"]}
                        if state.get("origin_user_seq")
                        else {}
                    ),
                ),
            )
            row = conn.execute(
                "SELECT * FROM open_design_tasks WHERE user_id=? AND instance_id=? AND agent_id=? AND thread_id=? AND request_id=?",
                (user_id, instance_id, agent_id, thread_id, state["requestId"]),
            ).fetchone()
        assert row is not None
        return dict(row)

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM open_design_tasks WHERE task_id=?", (task_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_thread(self, user_id: int, agent_id: str, thread_id: str) -> list[dict[str, Any]]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM open_design_tasks WHERE user_id=? AND agent_id=? AND thread_id=? ORDER BY created_at DESC,id DESC LIMIT 50",
                (user_id, agent_id, thread_id),
            ).fetchall()
        return [dict(r) for r in rows]

    def active_project(self, user_id: int, instance_id: str, project: str) -> list[dict[str, Any]]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM open_design_tasks WHERE instance_id=? AND project=? AND status IN ('submitting','queued','running','unavailable')",
                (instance_id, project),
            ).fetchall()
        return [dict(r) for r in rows]

    def due(self, now: int) -> list[dict[str, Any]]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM open_design_tasks WHERE status IN ('queued','running','submitting','unavailable') AND run_id IS NOT NULL AND next_check<=? ORDER BY next_check LIMIT 50",
                (now,),
            ).fetchall()
        return [dict(r) for r in rows]

    def update(
        self,
        task_id: str,
        *,
        status: str,
        result: dict[str, Any],
        error: str | None,
        failures: int,
        next_check: int,
    ) -> None:
        serialized = json.dumps(result, ensure_ascii=False)
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE open_design_tasks SET status=?,result_json=?,last_error=?,failures=?,next_check=?,updated_at=?,revision=revision+1 WHERE task_id=? AND (status<>? OR result_json<>? OR COALESCE(last_error,'')<>? OR next_check<>?)",
                (
                    status,
                    serialized,
                    error,
                    failures,
                    next_check,
                    now_ts(),
                    task_id,
                    status,
                    serialized,
                    error or "",
                    next_check,
                ),
            )
