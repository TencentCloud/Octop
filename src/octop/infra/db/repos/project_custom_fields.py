"""Project custom-field definitions and their per-task values.

Two tables, one fact each (PLAN.md §6.1):

* ``project_custom_fields``     — the definition (per-project unique ``key``).
* ``project_task_field_values`` — one value row per ``(task, field)``.

Every custom-field statement in Octop lives here. Validation (types, options,
``key`` shape, required semantics) lives in
:mod:`octop.infra.projects.custom_fields`; this module stays SQL-only.

``options`` is persisted as a JSON array in a TEXT column, so the row dataclass
hands callers a ``list[str]`` and never the raw string. Values are always stored
as *normalised strings* — the column type is TEXT and no per-type column exists
(PLAN §6.2).

``default`` is deliberately absent: S-9 forbids the column, and the definition
schema therefore has no way to seed a value.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import cast

try:
    from psycopg import errors as pg_errors
except ImportError:  # pragma: no cover - optional PostgreSQL driver
    pg_errors = None  # type: ignore[assignment]

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import (
    UNSET,
    DbRow,
    bool_int,
    insert_returning_id,
    map_rows,
    now_ts,
    optional_updates,
    sql_in_placeholders,
)
from octop.infra.utils.ulid import new_short_id

#: The four field types (PLAN.md §6.2). Mirrors the DDL comment on ``type``.
CUSTOM_FIELD_TYPES: tuple[str, ...] = ("text", "number", "date", "select")


def _is_unique_violation(exc: BaseException) -> bool:
    """True when the driver rejected a write on a UNIQUE constraint."""
    if isinstance(exc, sqlite3.IntegrityError):
        return "unique" in str(exc).lower()
    return pg_errors is not None and isinstance(exc, pg_errors.UniqueViolation)


def dump_field_options(options: Iterable[object]) -> str:
    return json.dumps([str(option) for option in options], ensure_ascii=False)


def parse_field_options(raw: object) -> list[str]:
    """Read the ``options`` column back into a list of strings."""
    if isinstance(raw, list):
        return [str(item) for item in raw]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw or "[]")
        except (ValueError, TypeError):
            return []
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    return []


# ── project_custom_fields ────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProjectCustomFieldRow:
    pk: int
    field_id: str
    project_id: str
    key: str
    label: str
    type: str
    required: bool
    options: list[str]
    sort_order: int
    created_by: int
    created_at: int
    updated_at: int

    @classmethod
    def from_row(cls, r: DbRow) -> ProjectCustomFieldRow:
        return cls(
            pk=int(r["id"]),
            field_id=str(r["field_id"]),
            project_id=str(r["project_id"]),
            key=str(r["key"]),
            label=str(r["label"]),
            type=str(r["type"]),
            required=bool(r["required"]),
            options=parse_field_options(r["options"]),
            sort_order=int(r["sort_order"]),
            created_by=int(r["created_by"]),
            created_at=int(r["created_at"]),
            updated_at=int(r["updated_at"]),
        )


class ProjectCustomFieldRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def _allocate_id(self) -> str:
        for _ in range(8):
            candidate = new_short_id()
            if self.get(candidate) is None:
                return candidate
        raise RuntimeError("failed to allocate unique custom field id")

    # ── definition reads ─────────────────────────────────────────────────────

    def get(self, field_id: str) -> ProjectCustomFieldRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT * FROM project_custom_fields WHERE field_id = ?", (field_id,)
            ).fetchone()
        return ProjectCustomFieldRow.from_row(r) if r else None

    def list_by_project(self, project_id: str) -> list[ProjectCustomFieldRow]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM project_custom_fields WHERE project_id = ? "
                "ORDER BY sort_order, created_at, id",
                (project_id,),
            ).fetchall()
        return map_rows(rows, ProjectCustomFieldRow)

    def find_by_key(self, project_id: str, key: str) -> ProjectCustomFieldRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT * FROM project_custom_fields WHERE project_id = ? AND key = ?",
                (project_id, key),
            ).fetchone()
        return ProjectCustomFieldRow.from_row(r) if r else None

    def next_sort_order(self, project_id: str) -> int:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(sort_order), -1) AS m FROM project_custom_fields "
                "WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        return int(row["m"]) + 1 if row else 0

    # ── definition writes ────────────────────────────────────────────────────

    def create(
        self,
        *,
        project_id: str,
        key: str,
        label: str,
        type: str,
        created_by: int,
        required: bool = False,
        options: Iterable[object] = (),
        sort_order: int | None = None,
    ) -> ProjectCustomFieldRow:
        field_id = self._allocate_id()
        ts = now_ts()
        if sort_order is None:
            sort_order = self.next_sort_order(project_id)
        try:
            with self._db.transaction() as conn:
                insert_returning_id(
                    conn,
                    "INSERT INTO project_custom_fields("
                    "field_id, project_id, key, label, type, required, options, sort_order, "
                    "created_by, created_at, updated_at"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        field_id,
                        project_id,
                        key,
                        label,
                        type,
                        bool_int(required),
                        dump_field_options(options),
                        sort_order,
                        created_by,
                        ts,
                        ts,
                    ),
                )
        except Exception as exc:
            if _is_unique_violation(exc):
                raise ValueError("field_key_taken") from exc
            raise
        row = self.get(field_id)
        if row is None:
            raise RuntimeError(f"project custom field insert failed: {field_id}")
        return row

    def update(
        self,
        field_id: str,
        *,
        label: object = UNSET,
        required: object = UNSET,
        options: object = UNSET,
        sort_order: object = UNSET,
    ) -> ProjectCustomFieldRow | None:
        """Patch a definition. ``key`` and ``type`` are immutable by design."""
        current = self.get(field_id)
        if current is None:
            return None
        clauses, params = optional_updates(
            [
                ("label", label),
                ("required", bool_int(bool(required)) if required is not UNSET else UNSET),
                (
                    "options",
                    dump_field_options(cast("Iterable[object]", options))
                    if options is not UNSET
                    else UNSET,
                ),
                ("sort_order", sort_order),
            ]
        )
        if not clauses:
            return current
        clauses.append("updated_at = ?")
        params.append(now_ts())
        params.append(field_id)
        try:
            with self._db.transaction() as conn:
                conn.execute(
                    f"UPDATE project_custom_fields SET {', '.join(clauses)} WHERE field_id = ?",
                    params,
                )
        except Exception as exc:
            if _is_unique_violation(exc):
                raise ValueError("field_key_taken") from exc
            raise
        return self.get(field_id)

    def delete(self, field_id: str) -> bool:
        """Delete a definition. Its values cascade via ``ON DELETE CASCADE``."""
        with self._db.transaction() as conn:
            cur = conn.execute("DELETE FROM project_custom_fields WHERE field_id = ?", (field_id,))
        return bool(cur.rowcount)

    # ── values ───────────────────────────────────────────────────────────────

    def list_values_for_task(self, task_id: str) -> dict[str, str]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT field_id, value FROM project_task_field_values WHERE task_id = ?",
                (task_id,),
            ).fetchall()
        return {str(r["field_id"]): str(r["value"]) for r in rows}

    def list_values_for_tasks(self, task_ids: list[str]) -> dict[str, dict[str, str]]:
        """Resolve values for many tasks at once — a single ``IN`` query.

        The board renders every task in one pass; one query per task would be
        N+1, so this reads them together and groups in Python.
        """
        if not task_ids:
            return {}
        sql = (
            "SELECT task_id, field_id, value FROM project_task_field_values "
            f"WHERE task_id IN ({sql_in_placeholders(len(task_ids))})"
        )
        with self._db.connect() as conn:
            rows = conn.execute(sql, list(task_ids)).fetchall()
        grouped: dict[str, dict[str, str]] = {task_id: {} for task_id in task_ids}
        for r in rows:
            grouped.setdefault(str(r["task_id"]), {})[str(r["field_id"])] = str(r["value"])
        return grouped

    def upsert_values(self, task_id: str, values: Mapping[str, str]) -> None:
        """Write the given values, leaving every other value on the task alone."""
        if not values:
            return
        ts = now_ts()
        with self._db.transaction() as conn:
            for field_id, value in values.items():
                conn.execute(
                    "INSERT INTO project_task_field_values(task_id, field_id, value, updated_at) "
                    "VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(task_id, field_id) DO UPDATE SET "
                    "value = excluded.value, updated_at = excluded.updated_at",
                    (task_id, field_id, value, ts),
                )

    def delete_values(self, task_id: str, field_ids: Iterable[str]) -> None:
        drop = list(dict.fromkeys(str(field_id) for field_id in field_ids))
        if not drop:
            return
        with self._db.transaction() as conn:
            conn.execute(
                "DELETE FROM project_task_field_values WHERE task_id = ? AND field_id IN "
                f"({sql_in_placeholders(len(drop))})",
                (task_id, *drop),
            )

    def set_task_values(self, task_id: str, values: Mapping[str, str]) -> None:
        """Replace a task's values with exactly ``values`` (full replacement).

        The delete and the upserts share one transaction so a reader can never
        observe a task whose values were cleared but not yet rewritten.
        """
        ts = now_ts()
        with self._db.transaction() as conn:
            existing = {
                str(r["field_id"])
                for r in conn.execute(
                    "SELECT field_id FROM project_task_field_values WHERE task_id = ?",
                    (task_id,),
                ).fetchall()
            }
            drop = sorted(existing - set(values))
            if drop:
                conn.execute(
                    "DELETE FROM project_task_field_values WHERE task_id = ? AND field_id IN "
                    f"({sql_in_placeholders(len(drop))})",
                    (task_id, *drop),
                )
            for field_id, value in values.items():
                conn.execute(
                    "INSERT INTO project_task_field_values(task_id, field_id, value, updated_at) "
                    "VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(task_id, field_id) DO UPDATE SET "
                    "value = excluded.value, updated_at = excluded.updated_at",
                    (task_id, field_id, value, ts),
                )

    def count_values_for_field(self, field_id: str) -> int:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM project_task_field_values WHERE field_id = ?",
                (field_id,),
            ).fetchone()
        return int(row["c"]) if row else 0

    def count_values_for_option(self, field_id: str, option: str) -> int:
        """How many stored values equal ``option`` — the S-2 reference count.

        Deleting an option that is still referenced would silently destroy user
        data, so the service refuses the patch while this is non-zero.
        """
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM project_task_field_values "
                "WHERE field_id = ? AND value = ?",
                (field_id, option),
            ).fetchone()
        return int(row["c"]) if row else 0

    def count_values_for_task(self, task_id: str) -> int:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM project_task_field_values WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return int(row["c"]) if row else 0

    def count_orphan_values(self) -> int:
        """Values whose definition or task has vanished — must always be 0."""
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM project_task_field_values AS v "
                "LEFT JOIN project_custom_fields AS f ON f.field_id = v.field_id "
                "LEFT JOIN project_tasks AS t ON t.task_id = v.task_id "
                "WHERE f.field_id IS NULL OR t.task_id IS NULL"
            ).fetchone()
        return int(row["c"]) if row else 0
