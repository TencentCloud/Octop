"""Coding runtimes repository — per-session Docker sandbox records (S4)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow

RUNTIME_COLS = (
    "runtime_id, session_id, image, cpus, memory, pids_limit, "
    "allow_network, status, container_id, meta_json, created_at, updated_at"
)


def _decode_meta(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        val = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return val if isinstance(val, dict) else {}


@dataclass(frozen=True)
class RuntimeRow:
    runtime_id: str
    session_id: str
    image: str
    cpus: float | None
    memory: str | None
    pids_limit: int | None
    allow_network: bool
    status: str
    container_id: str | None
    meta: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0

    @classmethod
    def from_row(cls, r: DbRow) -> RuntimeRow:
        return cls(
            runtime_id=str(r["runtime_id"]),
            session_id=str(r["session_id"]),
            image=str(r["image"]),
            cpus=float(r["cpus"]) if r["cpus"] is not None else None,
            memory=r["memory"],
            pids_limit=int(r["pids_limit"]) if r["pids_limit"] is not None else None,
            allow_network=bool(r["allow_network"]),
            status=str(r["status"]),
            container_id=r["container_id"],
            meta=_decode_meta(r["meta_json"]),
            created_at=float(r["created_at"]),
            updated_at=float(r["updated_at"]),
        )


class RuntimeRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def create(
        self,
        *,
        runtime_id: str,
        session_id: str,
        image: str,
        cpus: float | None = None,
        memory: str | None = None,
        pids_limit: int | None = None,
        allow_network: bool = True,
        status: str = "creating",
    ) -> RuntimeRow:
        now = time.time()
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO coding_runtimes("
                "runtime_id, session_id, image, cpus, memory, pids_limit, "
                "allow_network, status, meta_json, created_at, updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, '{}', ?, ?)",
                (
                    runtime_id,
                    session_id,
                    image,
                    cpus,
                    memory,
                    pids_limit,
                    1 if allow_network else 0,
                    status,
                    now,
                    now,
                ),
            )
        row = self.get(runtime_id)
        assert row is not None
        return row

    def get(self, runtime_id: str) -> RuntimeRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                f"SELECT {RUNTIME_COLS} FROM coding_runtimes WHERE runtime_id = ?",
                (runtime_id,),
            ).fetchone()
        return RuntimeRow.from_row(r) if r else None

    def by_session(self, session_id: str) -> RuntimeRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                f"SELECT {RUNTIME_COLS} FROM coding_runtimes WHERE session_id = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (session_id,),
            ).fetchone()
        return RuntimeRow.from_row(r) if r else None

    def update_status(self, runtime_id: str, status: str) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE coding_runtimes SET status = ?, updated_at = ? WHERE runtime_id = ?",
                (status, time.time(), runtime_id),
            )

    def set_container(self, runtime_id: str, container_id: str) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE coding_runtimes SET container_id = ?, status = 'running', "
                "updated_at = ? WHERE runtime_id = ?",
                (container_id, time.time(), runtime_id),
            )

    def list_active(self) -> list[RuntimeRow]:
        with self._db.connect() as conn:
            rows = conn.execute(
                f"SELECT {RUNTIME_COLS} FROM coding_runtimes "
                "WHERE status IN ('creating', 'running', 'idle') "
                "ORDER BY created_at ASC"
            ).fetchall()
        return [RuntimeRow.from_row(r) for r in rows]
