"""Approval requests repository — HITL permission decisions (S6)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow, insert_returning_id

APPROVAL_COLS = (
    "id, request_id, session_id, turn_id, tool_name, tool_kind, status, "
    "option_id, decided_by, payload_json, created_at, decided_at"
)


def _decode_payload(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        val = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return val if isinstance(val, dict) else {}


@dataclass(frozen=True)
class ApprovalRow:
    id: int
    request_id: str
    session_id: str
    turn_id: str
    tool_name: str
    tool_kind: str
    status: str
    option_id: str | None
    decided_by: int | None
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    decided_at: float | None = None

    @classmethod
    def from_row(cls, r: DbRow) -> ApprovalRow:
        return cls(
            id=int(r["id"]),
            request_id=str(r["request_id"]),
            session_id=str(r["session_id"]),
            turn_id=str(r["turn_id"]),
            tool_name=str(r["tool_name"]),
            tool_kind=str(r["tool_kind"]),
            status=str(r["status"]),
            option_id=r["option_id"],
            decided_by=int(r["decided_by"]) if r["decided_by"] is not None else None,
            payload=_decode_payload(r["payload_json"]),
            created_at=float(r["created_at"]),
            decided_at=float(r["decided_at"]) if r["decided_at"] is not None else None,
        )


class ApprovalRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def create(
        self,
        *,
        request_id: str,
        session_id: str,
        turn_id: str = "",
        tool_name: str = "",
        tool_kind: str = "",
        payload: dict[str, Any] | None = None,
    ) -> ApprovalRow:
        now = time.time()
        payload_json = json.dumps(payload or {}, ensure_ascii=False)
        with self._db.transaction() as conn:
            row_id = insert_returning_id(
                conn,
                "INSERT INTO approval_requests("
                "request_id, session_id, turn_id, tool_name, tool_kind, status, "
                "payload_json, created_at"
                ") VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
                (request_id, session_id, turn_id, tool_name, tool_kind, payload_json, now),
            )
        row = self.get_by_id(row_id)
        assert row is not None
        return row

    def get_by_id(self, row_id: int) -> ApprovalRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                f"SELECT {APPROVAL_COLS} FROM approval_requests WHERE id = ?",
                (row_id,),
            ).fetchone()
        return ApprovalRow.from_row(r) if r else None

    def get_by_request(self, request_id: str) -> ApprovalRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                f"SELECT {APPROVAL_COLS} FROM approval_requests WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        return ApprovalRow.from_row(r) if r else None

    def list_pending(self, session_id: str | None = None) -> list[ApprovalRow]:
        sql = f"SELECT {APPROVAL_COLS} FROM approval_requests WHERE status = 'pending'"
        params: list[Any] = []
        if session_id:
            sql += " AND session_id = ?"
            params.append(session_id)
        sql += " ORDER BY created_at DESC"
        with self._db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [ApprovalRow.from_row(r) for r in rows]

    def resolve(self, row_id: int, option_id: str, decided_by: int) -> None:
        now = time.time()
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE approval_requests SET status = 'resolved', option_id = ?, "
                "decided_by = ?, decided_at = ? WHERE id = ?",
                (option_id, decided_by, now, row_id),
            )
