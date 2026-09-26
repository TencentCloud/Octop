"""User invite table access."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow, insert_returning_id, map_rows, now_ts
from octop.infra.utils.ulid import new_ulid


def _optional_text(raw: object) -> str | None:
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


@dataclass(frozen=True)
class InviteRow:
    id: int
    code: str
    created_by: int
    note: str | None
    created_at: int
    expires_at: int
    used_at: int | None
    used_by_user_id: int | None
    revoked_at: int | None
    role_name: str | None = None
    user_role_id: str | None = None

    @classmethod
    def from_row(cls, row: DbRow) -> InviteRow:
        keys = set(row.keys())
        return cls(
            id=int(row["id"]),
            code=str(row["code"]),
            created_by=int(row["created_by"]),
            note=row["note"],
            created_at=int(row["created_at"]),
            expires_at=int(row["expires_at"]),
            used_at=int(row["used_at"]) if row["used_at"] is not None else None,
            used_by_user_id=(
                int(row["used_by_user_id"]) if row["used_by_user_id"] is not None else None
            ),
            revoked_at=int(row["revoked_at"]) if row["revoked_at"] is not None else None,
            role_name=_optional_text(row["role_name"]) if "role_name" in keys else None,
            user_role_id=(_optional_text(row["user_role_id"]) if "user_role_id" in keys else None),
        )

    def status(self, *, now: int | None = None) -> str:
        ts = now if now is not None else now_ts()
        if self.revoked_at is not None:
            return "revoked"
        if self.used_at is not None:
            return "used"
        if self.expires_at <= ts:
            return "expired"
        return "pending"


class InviteRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def create(
        self,
        *,
        code: str,
        created_by: int,
        expires_at: int,
        note: str | None = None,
        role_name: str | None = None,
        user_role_id: str | None = None,
    ) -> InviteRow:
        ts = now_ts()
        with self._db.transaction() as conn:
            invite_id = insert_returning_id(
                conn,
                "INSERT INTO user_invites("
                "code, created_by, note, created_at, expires_at, role_name, user_role_id"
                ") VALUES (?, ?, ?, ?, ?, ?, ?)",
                (code, created_by, note, ts, expires_at, role_name, user_role_id),
            )
        row = self.get(invite_id)
        assert row is not None
        return row

    def get(self, invite_id: int) -> InviteRow | None:
        with self._db.connect() as conn:
            row = conn.execute("SELECT * FROM user_invites WHERE id = ?", (invite_id,)).fetchone()
        return InviteRow.from_row(row) if row else None

    def get_by_code(self, code: str) -> InviteRow | None:
        with self._db.connect() as conn:
            row = conn.execute("SELECT * FROM user_invites WHERE code = ?", (code,)).fetchone()
        return InviteRow.from_row(row) if row else None

    def list_all(self) -> list[InviteRow]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM user_invites ORDER BY created_at DESC, id DESC"
            ).fetchall()
        return map_rows(rows, InviteRow)

    def revoke(self, invite_id: int) -> InviteRow | None:
        ts = now_ts()
        with self._db.transaction() as conn:
            row = conn.execute("SELECT * FROM user_invites WHERE id = ?", (invite_id,)).fetchone()
            if row is None:
                return None
            invite = InviteRow.from_row(row)
            if invite.used_at is not None or invite.revoked_at is not None:
                return invite
            conn.execute(
                "UPDATE user_invites SET revoked_at = ? WHERE id = ? AND used_at IS NULL "
                "AND revoked_at IS NULL",
                (ts, invite_id),
            )
        return self.get(invite_id)

    def redeem_creating_user(
        self,
        *,
        code: str,
        username: str,
        password_hash: str,
        display_name: str | None,
        locale: str,
        email: str | None = None,
        account_role: str = "user",
        permissions: list[str] | None = None,
        policies: list[tuple[str, str]] | None = None,
        user_role_id: str | None = None,
        role_name: str | None = None,
    ) -> tuple[int, InviteRow]:
        """Create a user and mark the invite used in one transaction.

        Returns ``(user_id, invite)``. Caller must hold any in-memory locks.
        Raises ``LookupError`` when the invite is missing, ``ValueError`` with
        status ``used`` / ``expired`` / ``revoked`` / ``username_taken`` /
        ``email_taken``.
        """
        ts = now_ts()
        with self._db.transaction() as conn:
            row = conn.execute("SELECT * FROM user_invites WHERE code = ?", (code,)).fetchone()
            if row is None:
                raise LookupError("invite not found")
            invite = InviteRow.from_row(row)
            status = invite.status(now=ts)
            if status != "pending":
                raise ValueError(status)

            existing = conn.execute(
                "SELECT id FROM users WHERE username = ?", (username,)
            ).fetchone()
            if existing is not None:
                raise ValueError("username_taken")
            if email:
                email_owner = conn.execute(
                    "SELECT id FROM users WHERE email = ?", (email,)
                ).fetchone()
                if email_owner is not None:
                    raise ValueError("email_taken")

            perm_list = list(permissions or [])
            user_id = insert_returning_id(
                conn,
                "INSERT INTO users(username, password_hash, role, display_name, locale, "
                "email, sso_provider_id, sso_subject, disabled, created_at, permissions, "
                "role_name, user_role_id) "
                "VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, 0, ?, ?, ?, ?)",
                (
                    username,
                    password_hash,
                    account_role,
                    display_name,
                    locale,
                    email,
                    ts,
                    json.dumps(perm_list, ensure_ascii=False),
                    role_name if role_name is not None else invite.role_name,
                    user_role_id if user_role_id is not None else invite.user_role_id,
                ),
            )
            if policies:
                _insert_named_policies(conn, user_id=user_id, policies=policies, ts=ts)
            updated = conn.execute(
                "UPDATE user_invites SET used_at = ?, used_by_user_id = ? "
                "WHERE id = ? AND used_at IS NULL AND revoked_at IS NULL AND expires_at > ?",
                (ts, user_id, invite.id, ts),
            )
            if getattr(updated, "rowcount", 1) == 0:
                raise ValueError("used")
            fresh = conn.execute("SELECT * FROM user_invites WHERE id = ?", (invite.id,)).fetchone()
            assert fresh is not None
            return user_id, InviteRow.from_row(fresh)


def _insert_named_policies(
    conn: Any,
    *,
    user_id: int,
    policies: list[tuple[str, str]],
    ts: int,
) -> None:
    for name, value in policies:
        conn.execute(
            """
            INSERT INTO user_policies(
              policy_id, user_id, name, enabled, value, created_at, updated_at
            )
            VALUES (?, ?, ?, 1, ?, ?, ?)
            ON CONFLICT(user_id, name) DO UPDATE SET
              enabled = 1,
              value = excluded.value,
              updated_at = excluded.updated_at
            """,
            (new_ulid(), user_id, name, value, ts, ts),
        )


def invite_status_payload(invite: InviteRow, *, now: int | None = None) -> dict[str, Any]:
    ts = now if now is not None else now_ts()
    return {
        "id": invite.id,
        "code": invite.code,
        "note": invite.note,
        "created_by": invite.created_by,
        "created_at": invite.created_at,
        "expires_at": invite.expires_at,
        "used_at": invite.used_at,
        "used_by_user_id": invite.used_by_user_id,
        "revoked_at": invite.revoked_at,
        "status": invite.status(now=ts),
        "role_name": invite.role_name,
        "user_role_id": invite.user_role_id,
    }
