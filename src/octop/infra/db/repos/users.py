"""User table access."""

from __future__ import annotations

from dataclasses import dataclass

from octop.infra.db.pool import DBPool
from octop.infra.db.repos._base import DbRow, bool_int, insert_returning_id, map_rows, now_ts


@dataclass(frozen=True)
class UserRow:
    id: int
    username: str
    password_hash: str
    role: str
    display_name: str | None
    disabled: int
    created_at: int
    locale: str
    preferences_json: str = "{}"
    login_failed_count: int = 0
    login_locked_until: int = 0

    @classmethod
    def from_row(cls, r: DbRow) -> UserRow:
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
        )


class UserRepo:
    def __init__(self, db: DBPool) -> None:
        self._db = db

    def create(
        self,
        *,
        username: str,
        password_hash: str,
        role: str,
        display_name: str | None = None,
        locale: str = "zh",
    ) -> int:
        with self._db.transaction() as conn:
            return insert_returning_id(
                conn,
                "INSERT INTO users(username, password_hash, role, display_name, "
                "locale, disabled, created_at) VALUES (?, ?, ?, ?, ?, 0, ?)",
                (username, password_hash, role, display_name, locale, now_ts()),
            )

    def get(self, user_id: int) -> UserRow | None:
        with self._db.connect() as conn:
            r = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return UserRow.from_row(r) if r else None

    def get_by_username(self, username: str) -> UserRow | None:
        with self._db.connect() as conn:
            r = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return UserRow.from_row(r) if r else None

    def list(self, *, include_disabled: bool = False) -> list[UserRow]:
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

    def set_locale(self, user_id: int, locale: str) -> None:
        with self._db.transaction() as conn:
            conn.execute("UPDATE users SET locale = ? WHERE id = ?", (locale, user_id))

    def set_preferences_json(self, user_id: int, preferences_json: str) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE users SET preferences_json = ? WHERE id = ?",
                (preferences_json, user_id),
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
