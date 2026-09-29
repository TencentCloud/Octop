"""``team_runs`` / ``team_run_phases`` / ``team_run_members`` rows (migration 025).

The three tables hold a team run's pipeline state. ``team_runs`` is the 1:1
extension row of the project the run owns -- ``project_id`` is ``UNIQUE`` and
``ON DELETE CASCADE``, so a run can neither share a project nor outlive it.

Child rows FK the **public string** id (``run_id``), never the integer ``id``
(AGENTS.md section 7). ``is_lead`` marks the run's host; "at most one lead per
run" is enforced by the partial unique index ``WHERE is_lead = 1`` created in 025,
so this repo does not re-check it in Python.

``pending_decision`` is a column on ``threads`` (the run's room thread). 025 added
it and this repo owns its set / clear / read path, because the decision belongs to
the run and is addressed by ``run_id``; the payload shape is frozen in PLAN.md
answer B: ``{"id", "kind", "question", "options":[{"key","label","effect"}],
"created_at"}``.
"""

from __future__ import annotations

import builtins
import json
from dataclasses import dataclass
from typing import Any

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow, map_rows, now_ts

RUN_MODES = ("one-shot", "persist")
RUN_STATUSES = (
    "running",
    "awaiting_confirmation",
    "awaiting_decision",
    "complete",
    "failed",
    "cancelled",
)
RUN_TIERS = ("quick", "standard", "strict")
PHASE_STATUSES = ("pending", "active", "passed", "failed", "skipped")


def _decode_json_object(raw: object) -> dict[str, Any] | None:
    """Decode a JSON object column; ``None``/empty/garbage all read as unset."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        decoded = json.loads(text)
    except ValueError:
        return None
    return decoded if isinstance(decoded, dict) else None


@dataclass(frozen=True)
class TeamRunRow:
    pk: int
    run_id: str
    team_agent_id: str
    project_id: str
    room_thread_id: str | None
    goal: str
    mode: str
    deliverable: str
    tier: str
    status: str
    phase: str
    run_root: str
    max_review_rounds: int
    max_test_rounds: int
    created_by: int
    created_at: int
    updated_at: int

    @classmethod
    def from_row(cls, r: DbRow) -> TeamRunRow:
        return cls(
            pk=int(r["id"]),
            run_id=str(r["run_id"]),
            team_agent_id=str(r["team_agent_id"]),
            project_id=str(r["project_id"]),
            room_thread_id=(str(r["room_thread_id"]) if r["room_thread_id"] is not None else None),
            goal=str(r["goal"]),
            mode=str(r["mode"]),
            deliverable=str(r["deliverable"]),
            tier=str(r["tier"]),
            status=str(r["status"]),
            phase=str(r["phase"]),
            run_root=str(r["run_root"]),
            max_review_rounds=int(r["max_review_rounds"]),
            max_test_rounds=int(r["max_test_rounds"]),
            created_by=int(r["created_by"]),
            created_at=int(r["created_at"]),
            updated_at=int(r["updated_at"]),
        )


@dataclass(frozen=True)
class TeamRunPhaseRow:
    pk: int
    run_id: str
    phase: str
    seq: int
    status: str
    entered_at: int | None
    passed_at: int | None
    gate_detail: dict[str, Any]

    @classmethod
    def from_row(cls, r: DbRow) -> TeamRunPhaseRow:
        detail = _decode_json_object(r["gate_detail"])
        return cls(
            pk=int(r["id"]),
            run_id=str(r["run_id"]),
            phase=str(r["phase"]),
            seq=int(r["seq"]),
            status=str(r["status"]),
            entered_at=(int(r["entered_at"]) if r["entered_at"] is not None else None),
            passed_at=(int(r["passed_at"]) if r["passed_at"] is not None else None),
            gate_detail=detail if detail is not None else {},
        )


@dataclass(frozen=True)
class TeamRunMemberRow:
    pk: int
    run_id: str
    role: str
    agent_id: str
    is_lead: bool
    joined_at: int

    @classmethod
    def from_row(cls, r: DbRow) -> TeamRunMemberRow:
        return cls(
            pk=int(r["id"]),
            run_id=str(r["run_id"]),
            role=str(r["role"]),
            agent_id=str(r["agent_id"]),
            is_lead=bool(int(r["is_lead"])),
            joined_at=int(r["joined_at"]),
        )


class TeamRunRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    # ── team_runs ────────────────────────────────────────────────────────────

    def create(
        self,
        *,
        run_id: str,
        team_agent_id: str,
        project_id: str,
        goal: str,
        created_by: int,
        room_thread_id: str | None = None,
        mode: str = "one-shot",
        deliverable: str = "code+artifacts",
        tier: str = "standard",
        status: str = "running",
        phase: str = "clarify",
        run_root: str = "host_workspace",
        max_review_rounds: int = 3,
        max_test_rounds: int = 3,
    ) -> TeamRunRow:
        ts = now_ts()
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO team_runs("
                "run_id, team_agent_id, project_id, room_thread_id, goal, mode, deliverable,"
                " tier, status, phase, run_root, max_review_rounds, max_test_rounds,"
                " created_by, created_at, updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    team_agent_id,
                    project_id,
                    room_thread_id,
                    goal,
                    mode,
                    deliverable,
                    tier,
                    status,
                    phase,
                    run_root,
                    max_review_rounds,
                    max_test_rounds,
                    created_by,
                    ts,
                    ts,
                ),
            )
        row = self.get(run_id)
        if row is None:
            raise RuntimeError(f"team run insert failed: {run_id}")
        return row

    def get(self, run_id: str) -> TeamRunRow | None:
        with self._db.connect() as conn:
            r = conn.execute("SELECT * FROM team_runs WHERE run_id = ?", (run_id,)).fetchone()
        return TeamRunRow.from_row(r) if r is not None else None

    def list(
        self,
        *,
        team_agent_id: str | None = None,
        status: str | None = None,
    ) -> builtins.list[TeamRunRow]:
        clauses: list[str] = []
        params: list[object] = []
        if team_agent_id is not None:
            clauses.append("team_agent_id = ?")
            params.append(team_agent_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._db.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM team_runs{where} ORDER BY created_at DESC, id DESC", params
            ).fetchall()
        return map_rows(rows, TeamRunRow)

    def update_phase(self, run_id: str, phase: str) -> bool:
        with self._db.transaction() as conn:
            cur = conn.execute(
                "UPDATE team_runs SET phase = ?, updated_at = ? WHERE run_id = ?",
                (phase, now_ts(), run_id),
            )
        return bool(cur.rowcount > 0)

    def update_status(self, run_id: str, status: str) -> bool:
        with self._db.transaction() as conn:
            cur = conn.execute(
                "UPDATE team_runs SET status = ?, updated_at = ? WHERE run_id = ?",
                (status, now_ts(), run_id),
            )
        return bool(cur.rowcount > 0)

    def set_room_thread(self, run_id: str, thread_id: str) -> bool:
        with self._db.transaction() as conn:
            cur = conn.execute(
                "UPDATE team_runs SET room_thread_id = ?, updated_at = ? WHERE run_id = ?",
                (thread_id, now_ts(), run_id),
            )
        return bool(cur.rowcount > 0)

    def delete(self, run_id: str) -> bool:
        with self._db.transaction() as conn:
            cur = conn.execute("DELETE FROM team_runs WHERE run_id = ?", (run_id,))
        return bool(cur.rowcount > 0)

    # ── pending_decision (threads.pending_decision, addressed by run) ────────

    def _room_thread_id(self, run_id: str) -> str | None:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT room_thread_id FROM team_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if r is None or r["room_thread_id"] is None:
            return None
        return str(r["room_thread_id"])

    def set_pending_decision(self, run_id: str, payload: dict[str, Any]) -> bool:
        """Store the pending decision on the run's room thread.

        ``False`` when the run is unknown or has no room thread yet -- the caller
        owns the error semantics (``TEAM_DECISION_*`` codes live in ``infra/errors``).
        """
        thread_id = self._room_thread_id(run_id)
        if thread_id is None:
            return False
        blob = json.dumps(payload, ensure_ascii=False)
        with self._db.transaction() as conn:
            cur = conn.execute(
                "UPDATE threads SET pending_decision = ? WHERE thread_id = ?",
                (blob, thread_id),
            )
        return bool(cur.rowcount > 0)

    def get_pending_decision(self, run_id: str) -> dict[str, Any] | None:
        """Idempotent read: unset, unknown run and malformed JSON all return None."""
        thread_id = self._room_thread_id(run_id)
        if thread_id is None:
            return None
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT pending_decision FROM threads WHERE thread_id = ?", (thread_id,)
            ).fetchone()
        if r is None:
            return None
        return _decode_json_object(r["pending_decision"])

    # ── team_run_phases ──────────────────────────────────────────────────────

    def upsert_phase(
        self,
        run_id: str,
        phase: str,
        *,
        seq: int,
        status: str = "pending",
        gate_detail: dict[str, Any] | None = None,
        entered_at: int | None = None,
        passed_at: int | None = None,
    ) -> None:
        blob = json.dumps(gate_detail if gate_detail is not None else {}, ensure_ascii=False)
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO team_run_phases("
                "run_id, phase, seq, status, entered_at, passed_at, gate_detail"
                ") VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(run_id, phase) DO UPDATE SET "
                "seq = excluded.seq, status = excluded.status,"
                " entered_at = excluded.entered_at, passed_at = excluded.passed_at,"
                " gate_detail = excluded.gate_detail",
                (run_id, phase, seq, status, entered_at, passed_at, blob),
            )

    def list_phases(self, run_id: str) -> builtins.list[TeamRunPhaseRow]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM team_run_phases WHERE run_id = ? ORDER BY seq ASC, id ASC",
                (run_id,),
            ).fetchall()
        return map_rows(rows, TeamRunPhaseRow)

    def get_phase(self, run_id: str, phase: str) -> TeamRunPhaseRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT * FROM team_run_phases WHERE run_id = ? AND phase = ?", (run_id, phase)
            ).fetchone()
        return TeamRunPhaseRow.from_row(r) if r is not None else None

    # ── team_run_members ─────────────────────────────────────────────────────

    def add_member(
        self,
        run_id: str,
        *,
        role: str,
        agent_id: str,
        is_lead: bool = False,
    ) -> TeamRunMemberRow:
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO team_run_members(run_id, role, agent_id, is_lead, joined_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (run_id, role, agent_id, 1 if is_lead else 0, now_ts()),
            )
        row = self.get_member(run_id, role)
        if row is None:
            raise RuntimeError(f"team run member insert failed: {run_id}/{role}")
        return row

    def get_member(self, run_id: str, role: str) -> TeamRunMemberRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT * FROM team_run_members WHERE run_id = ? AND role = ?", (run_id, role)
            ).fetchone()
        return TeamRunMemberRow.from_row(r) if r is not None else None

    def list_members(self, run_id: str) -> builtins.list[TeamRunMemberRow]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM team_run_members WHERE run_id = ? ORDER BY id ASC", (run_id,)
            ).fetchall()
        return map_rows(rows, TeamRunMemberRow)

    def lead_member(self, run_id: str) -> TeamRunMemberRow | None:
        """The single ``is_lead=1`` row, or None when the host leads directly."""
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT * FROM team_run_members WHERE run_id = ? AND is_lead = 1", (run_id,)
            ).fetchone()
        return TeamRunMemberRow.from_row(r) if r is not None else None

    def remove_member(self, run_id: str, role: str) -> bool:
        with self._db.transaction() as conn:
            cur = conn.execute(
                "DELETE FROM team_run_members WHERE run_id = ? AND role = ?", (run_id, role)
            )
        return bool(cur.rowcount > 0)
