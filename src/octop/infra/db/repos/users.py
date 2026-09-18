"""User table access."""

from __future__ import annotations

import builtins
import json
from dataclasses import dataclass, field

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow, bool_int, insert_returning_id, map_rows, now_ts


def _parse_permissions(raw: object) -> builtins.list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw or "[]")
        except (ValueError, TypeError):
            return []
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
        return []
    return []


@dataclass(frozen=True)
class UserSsoIdentityRow:
    user_id: int
    provider_id: int
    subject: str
    kind: str
    created_at: int

    @classmethod
    def from_row(cls, r: DbRow) -> UserSsoIdentityRow:
        return cls(
            user_id=int(r["user_id"]),
            provider_id=int(r["provider_id"]),
            subject=str(r["subject"]),
            kind=str(r["kind"]),
            created_at=int(r["created_at"]),
        )


@dataclass(frozen=True)
class UserRow:
    id: int
    username: str
    password_hash: str | None
    role: str
    display_name: str | None
    disabled: int
    created_at: int
    locale: str
    email: str | None
    sso_provider_id: int | None
    sso_subject: str | None
    preferences_json: str = "{}"
    login_failed_count: int = 0
    login_locked_until: int = 0
    permissions: builtins.list[str] = field(default_factory=list)

    @classmethod
    def from_row(cls, r: DbRow) -> UserRow:
        keys = set(r.keys())
        return cls(
            id=r["id"],
            username=r["username"],
            password_hash=r["password_hash"],
            role=r["role"],
            display_name=r["display_name"],
            disabled=r["disabled"],
            created_at=r["created_at"],
            locale=r["locale"],
            preferences_json=str(r["preferences_json"] or "{}"),
            login_failed_count=int(r["login_failed_count"] or 0),
            login_locked_until=int(r["login_locked_until"] or 0),
            email=r["email"] if "email" in keys else None,
            sso_provider_id=r["sso_provider_id"] if "sso_provider_id" in keys else None,
            sso_subject=r["sso_subject"] if "sso_subject" in keys else None,
            permissions=_parse_permissions(r["permissions"] if "permissions" in keys else None),
        )


class UserRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def create(
        self,
        *,
        username: str,
        password_hash: str | None = None,
        role: str,
        display_name: str | None = None,
        locale: str = "zh",
        email: str | None = None,
        sso_provider_id: int | None = None,
        sso_subject: str | None = None,
        permissions: builtins.list[str] | None = None,
    ) -> int:
        perms_json = json.dumps(permissions or [], ensure_ascii=False)
        with self._db.transaction() as conn:
            return insert_returning_id(
                conn,
                "INSERT INTO users(username, password_hash, role, display_name, locale, "
                "email, sso_provider_id, sso_subject, disabled, created_at, permissions) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
                (
                    username,
                    password_hash,
                    role,
                    display_name,
                    locale,
                    email,
                    sso_provider_id,
                    sso_subject,
                    now_ts(),
                    perms_json,
                ),
            )

    def get(self, user_id: int) -> UserRow | None:
        with self._db.connect() as conn:
            r = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return UserRow.from_row(r) if r else None

    def get_by_username(self, username: str) -> UserRow | None:
        with self._db.connect() as conn:
            r = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return UserRow.from_row(r) if r else None

    def get_by_sso(self, provider_id: int, subject: str) -> UserRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT u.* FROM users u "
                "INNER JOIN user_sso_identities i ON i.user_id = u.id "
                "WHERE i.provider_id = ? AND i.subject = ?",
                (provider_id, subject),
            ).fetchone()
            if r is not None:
                return UserRow.from_row(r)
            # Legacy single-slot fallback for rows not yet backfilled.
            r = conn.execute(
                "SELECT * FROM users WHERE sso_provider_id = ? AND sso_subject = ?",
                (provider_id, subject),
            ).fetchone()
        if r is None:
            return None
        row = UserRow.from_row(r)
        self.upsert_sso_identity(row.id, provider_id=provider_id, subject=subject)
        return row

    def list_sso_identities(self, user_id: int) -> builtins.list[UserSsoIdentityRow]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT i.user_id, i.provider_id, i.subject, i.created_at, p.kind "
                "FROM user_sso_identities i "
                "INNER JOIN sso_providers p ON p.id = i.provider_id "
                "WHERE i.user_id = ? "
                "ORDER BY i.created_at ASC, i.id ASC",
                (user_id,),
            ).fetchall()
        return map_rows(rows, UserSsoIdentityRow)

    def upsert_sso_identity(
        self,
        user_id: int,
        *,
        provider_id: int,
        subject: str,
    ) -> None:
        """Link ``(provider_id, subject)`` to ``user_id`` (one subject per provider)."""
        ts = now_ts()
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO user_sso_identities(user_id, provider_id, subject, created_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(user_id, provider_id) DO UPDATE SET subject = excluded.subject",
                (user_id, provider_id, subject, ts),
            )
            conn.execute(
                "UPDATE users SET sso_provider_id = ?, sso_subject = ? WHERE id = ?",
                (provider_id, subject, user_id),
            )

    def remove_sso_identity(self, user_id: int, *, provider_id: int) -> bool:
        """Remove one provider link. Returns True when a row was deleted."""
        with self._db.transaction() as conn:
            cur = conn.execute(
                "DELETE FROM user_sso_identities WHERE user_id = ? AND provider_id = ?",
                (user_id, provider_id),
            )
            deleted = int(cur.rowcount or 0) > 0
            remaining = conn.execute(
                "SELECT provider_id, subject FROM user_sso_identities "
                "WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
                (user_id,),
            ).fetchone()
            if remaining is None:
                conn.execute(
                    "UPDATE users SET sso_provider_id = NULL, sso_subject = NULL WHERE id = ?",
                    (user_id,),
                )
            else:
                conn.execute(
                    "UPDATE users SET sso_provider_id = ?, sso_subject = ? WHERE id = ?",
                    (remaining["provider_id"], remaining["subject"], user_id),
                )
        return deleted

    def get_by_email(self, email: str) -> UserRow | None:
        with self._db.connect() as conn:
            r = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return UserRow.from_row(r) if r else None

    def set_sso(
        self,
        user_id: int,
        *,
        sso_provider_id: int | None,
        sso_subject: str | None,
    ) -> None:
        """Legacy primary-slot writer; prefer ``upsert_sso_identity`` / ``remove_sso_identity``."""
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE users SET sso_provider_id = ?, sso_subject = ? WHERE id = ?",
                (sso_provider_id, sso_subject, user_id),
            )

    def update_sso_profile(
        self,
        user_id: int,
        *,
        email: str | None = None,
        display_name: str | None = None,
    ) -> None:
        fields: list[str] = []
        params: list[object] = []
        if email is not None:
            fields.append("email = ?")
            params.append(email)
        if display_name is not None:
            fields.append("display_name = ?")
            params.append(display_name)
        if not fields:
            return
        params.append(user_id)
        with self._db.transaction() as conn:
            conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", params)

    def list(self, *, include_disabled: bool = False) -> builtins.list[UserRow]:
        sql = "SELECT * FROM users"
        if not include_disabled:
            sql += " WHERE disabled = 0"
        sql += " ORDER BY username"
        with self._db.connect() as conn:
            rows = conn.execute(sql).fetchall()
        return map_rows(rows, UserRow)

    def set_disabled(self, user_id: int, disabled: bool) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE users SET disabled = ? WHERE id = ?",
                (bool_int(disabled), user_id),
            )

    def set_role(self, user_id: int, role: str) -> None:
        with self._db.transaction() as conn:
            conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))

    def set_password_hash(self, user_id: int, password_hash: str) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (password_hash, user_id),
            )

    def set_display_name(self, user_id: int, display_name: str | None) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE users SET display_name = ? WHERE id = ?",
                (display_name, user_id),
            )

    def set_email(self, user_id: int, email: str | None) -> None:
        with self._db.transaction() as conn:
            conn.execute("UPDATE users SET email = ? WHERE id = ?", (email, user_id))

    def set_locale(self, user_id: int, locale: str) -> None:
        with self._db.transaction() as conn:
            conn.execute("UPDATE users SET locale = ? WHERE id = ?", (locale, user_id))

    def set_preferences_json(self, user_id: int, preferences_json: str) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE users SET preferences_json = ? WHERE id = ?",
                (preferences_json, user_id),
            )

    def set_permissions(self, user_id: int, permissions: builtins.list[str]) -> None:
        payload = json.dumps(permissions, ensure_ascii=False)
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE users SET permissions = ? WHERE id = ?",
                (payload, user_id),
            )

    def delete(self, user_id: int) -> None:
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))

    def count(self) -> int:
        with self._db.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])

    def clear_login_lockout(self, user_id: int) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE users SET login_failed_count = 0, login_locked_until = 0 WHERE id = ?",
                (user_id,),
            )

    def record_failed_login(
        self,
        user_id: int,
        *,
        max_attempts: int,
        lockout_seconds: int,
        now: int | None = None,
    ) -> int:
        """Increment failure count; lock when threshold reached. Returns retry_after seconds if locked."""
        ts = now if now is not None else now_ts()
        with self._db.transaction() as conn:
            row = conn.execute(
                "SELECT login_failed_count, login_locked_until FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if row is None:
                return 0
            locked_until = int(row["login_locked_until"] or 0)
            if locked_until > ts:
                return locked_until - ts
            failed = int(row["login_failed_count"] or 0) + 1
            new_locked_until = 0
            retry_after = 0
            if failed >= max_attempts:
                new_locked_until = ts + lockout_seconds
                retry_after = lockout_seconds
                failed = 0
            conn.execute(
                "UPDATE users SET login_failed_count = ?, login_locked_until = ? WHERE id = ?",
                (failed, new_locked_until, user_id),
            )
        return retry_after
