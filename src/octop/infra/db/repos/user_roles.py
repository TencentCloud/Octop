"""Role templates. Users store ``role_name`` as text, not a foreign key."""

from __future__ import annotations

import builtins
import json
import sqlite3
from dataclasses import dataclass

try:
    from psycopg import errors as pg_errors
except ImportError:  # pragma: no cover - optional PostgreSQL driver
    pg_errors = None  # type: ignore[assignment]

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow, insert_returning_id, map_rows, now_ts
from octop.infra.utils.ulid import new_ulid

ADMIN_USER_ROLE_ID = "admin"
SEEDED_USER_ROLE_ID = "user"


def parse_string_list(raw: object) -> builtins.list[str]:
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


def parse_policies(raw: object) -> builtins.list[tuple[str, str]]:
    """Return enabled policies. A missing name means that policy is off."""
    items: object
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, str):
        try:
            items = json.loads(raw or "[]")
        except (ValueError, TypeError):
            return []
    else:
        return []
    if not isinstance(items, list):
        return []
    out: builtins.list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        value = item.get("value")
        text = str(value).strip() if value is not None else ""
        if not name or not text or name in seen:
            continue
        seen.add(name)
        out.append((name, text))
    return out


def dump_policies(policies: builtins.list[tuple[str, str]]) -> str:
    payload = [{"name": name, "value": value} for name, value in policies if name and value]
    return json.dumps(payload, ensure_ascii=False)


def _is_unique_violation(exc: BaseException) -> bool:
    if isinstance(exc, sqlite3.IntegrityError):
        return "unique" in str(exc).lower()
    return pg_errors is not None and isinstance(exc, pg_errors.UniqueViolation)


@dataclass(frozen=True)
class UserRoleRow:
    id: int
    user_role_id: str
    user_role_name: str
    description: str | None
    permissions: builtins.list[str]
    policies: builtins.list[tuple[str, str]]
    created_at: int
    updated_at: int
    avatar_icon: str | None = None

    @classmethod
    def from_row(cls, row: DbRow) -> UserRoleRow:
        keys = set(row.keys())
        raw_icon = row["avatar_icon"] if "avatar_icon" in keys else None
        avatar_icon = str(raw_icon).strip() if isinstance(raw_icon, str) else ""
        return cls(
            id=int(row["id"]),
            user_role_id=str(row["user_role_id"]),
            user_role_name=str(row["user_role_name"]),
            description=(
                str(row["description"]).strip() or None if row["description"] is not None else None
            ),
            permissions=parse_string_list(row["permissions"]),
            policies=parse_policies(row["policies"]),
            created_at=int(row["created_at"]),
            updated_at=int(row["updated_at"]),
            avatar_icon=avatar_icon or None,
        )

    @property
    def is_admin(self) -> bool:
        return self.user_role_id == ADMIN_USER_ROLE_ID

    def policy_value(self, name: str) -> str | None:
        for key, value in self.policies:
            if key == name:
                return value
        return None


class UserRoleRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def list_all(self) -> builtins.list[UserRoleRow]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM user_role ORDER BY "
                "CASE user_role_id WHEN 'admin' THEN 0 WHEN 'user' THEN 1 ELSE 2 END, "
                "user_role_name, id"
            ).fetchall()
        return map_rows(rows, UserRoleRow)

    def get(self, user_role_id: str) -> UserRoleRow | None:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM user_role WHERE user_role_id = ?",
                (user_role_id,),
            ).fetchone()
        return UserRoleRow.from_row(row) if row else None

    def get_by_name(self, user_role_name: str) -> UserRoleRow | None:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM user_role WHERE user_role_name = ?",
                (user_role_name,),
            ).fetchone()
        return UserRoleRow.from_row(row) if row else None

    def create(
        self,
        *,
        user_role_name: str,
        description: str | None = None,
        permissions: builtins.list[str],
        policies: builtins.list[tuple[str, str]],
        user_role_id: str | None = None,
    ) -> UserRoleRow:
        ts = now_ts()
        public_id = user_role_id or new_ulid()
        try:
            with self._db.transaction() as conn:
                insert_returning_id(
                    conn,
                    "INSERT INTO user_role("
                    "user_role_id, user_role_name, description, permissions, policies, "
                    "created_at, updated_at"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        public_id,
                        user_role_name,
                        description,
                        json.dumps(permissions, ensure_ascii=False),
                        dump_policies(policies),
                        ts,
                        ts,
                    ),
                )
        except Exception as exc:
            if _is_unique_violation(exc):
                raise ValueError("name_taken") from exc
            raise
        row = self.get(public_id)
        assert row is not None
        return row

    def update(
        self,
        user_role_id: str,
        *,
        user_role_name: str | None = None,
        description: str | None | object = ...,
        permissions: builtins.list[str] | None = None,
        policies: builtins.list[tuple[str, str]] | None = None,
        avatar_icon: str | None | object = ...,
    ) -> UserRoleRow | None:
        current = self.get(user_role_id)
        if current is None:
            return None
        fields: list[str] = []
        params: list[object] = []
        if user_role_name is not None:
            fields.append("user_role_name = ?")
            params.append(user_role_name)
        if description is not ...:
            fields.append("description = ?")
            params.append(description)
        if permissions is not None:
            fields.append("permissions = ?")
            params.append(json.dumps(permissions, ensure_ascii=False))
        if policies is not None:
            fields.append("policies = ?")
            params.append(dump_policies(policies))
        if avatar_icon is not ...:
            fields.append("avatar_icon = ?")
            params.append(avatar_icon)
        if not fields:
            return current
        fields.append("updated_at = ?")
        params.append(now_ts())
        params.append(user_role_id)
        try:
            with self._db.transaction() as conn:
                conn.execute(
                    f"UPDATE user_role SET {', '.join(fields)} WHERE user_role_id = ?",
                    params,
                )
        except Exception as exc:
            if _is_unique_violation(exc):
                raise ValueError("name_taken") from exc
            raise
        return self.get(user_role_id)

    def delete(self, user_role_id: str) -> bool:
        with self._db.transaction() as conn:
            cur = conn.execute(
                "DELETE FROM user_role WHERE user_role_id = ?",
                (user_role_id,),
            )
            return int(cur.rowcount or 0) > 0


def seeded_user_role_assignment(
    db: DatabasePool,
) -> tuple[str, str, builtins.list[str], builtins.list[tuple[str, str]]] | None:
    """Defaults from the preset user role, when that role still exists.

    Returns ``(user_role_id, user_role_name, permissions, policies)``. ``None`` means the
    preset was deleted, and new SSO or CLI users keep an empty permission set.
    """
    from octop.infra.users.permissions import PERMISSIONS

    role = UserRoleRepo(db).get(SEEDED_USER_ROLE_ID)
    if role is None:
        return None
    permissions = [key for key in role.permissions if key in PERMISSIONS]
    return role.user_role_id, role.user_role_name, permissions, list(role.policies)
