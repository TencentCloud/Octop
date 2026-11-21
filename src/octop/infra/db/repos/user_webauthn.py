"""WebAuthn / passkey credential rows."""

from __future__ import annotations

import json
from dataclasses import dataclass

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow, insert_returning_id, map_rows, now_ts


@dataclass(frozen=True)
class UserWebauthnRow:
    id: int
    credential_id: str
    user_id: int
    public_key: bytes
    user_handle: str
    rp_id: str
    aaguid: str | None
    sign_count: int
    backup_eligible: bool
    backup_state: bool
    name: str | None
    transports_json: str
    created_at: int
    last_used_at: int | None

    @classmethod
    def from_row(cls, r: DbRow) -> UserWebauthnRow:
        raw = r["public_key"]
        public_key = bytes(raw) if not isinstance(raw, bytes) else raw
        return cls(
            id=int(r["id"]),
            credential_id=str(r["credential_id"]),
            user_id=int(r["user_id"]),
            public_key=public_key,
            user_handle=str(r["user_handle"]),
            rp_id=str(r["rp_id"]),
            aaguid=str(r["aaguid"]) if r["aaguid"] is not None else None,
            sign_count=int(r["sign_count"] or 0),
            backup_eligible=bool(int(r["backup_eligible"] or 0)),
            backup_state=bool(int(r["backup_state"] or 0)),
            name=str(r["name"]) if r["name"] is not None else None,
            transports_json=str(r["transports_json"] or "[]"),
            created_at=int(r["created_at"]),
            last_used_at=int(r["last_used_at"]) if r["last_used_at"] is not None else None,
        )

    @property
    def transports(self) -> list[str]:
        try:
            parsed = json.loads(self.transports_json or "[]")
        except (ValueError, TypeError):
            return []
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
        return []


class UserWebauthnRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def get_by_credential_id(self, credential_id: str) -> UserWebauthnRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT * FROM user_webauthn_credentials WHERE credential_id = ?",
                (credential_id,),
            ).fetchone()
        return UserWebauthnRow.from_row(r) if r else None

    def list_for_user(self, user_id: int) -> list[UserWebauthnRow]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM user_webauthn_credentials WHERE user_id = ? "
                "ORDER BY created_at ASC, id ASC",
                (user_id,),
            ).fetchall()
        return map_rows(rows, UserWebauthnRow)

    def count_for_user(self, user_id: int) -> int:
        with self._db.connect() as conn:
            return int(
                conn.execute(
                    "SELECT COUNT(*) FROM user_webauthn_credentials WHERE user_id = ?",
                    (user_id,),
                ).fetchone()[0]
            )

    def user_handle_for(self, user_id: int) -> str | None:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT user_handle FROM user_webauthn_credentials "
                "WHERE user_id = ? ORDER BY id ASC LIMIT 1",
                (user_id,),
            ).fetchone()
        return str(r["user_handle"]) if r else None

    def insert(
        self,
        *,
        credential_id: str,
        user_id: int,
        public_key: bytes,
        user_handle: str,
        rp_id: str,
        aaguid: str | None = None,
        sign_count: int = 0,
        backup_eligible: bool = False,
        backup_state: bool = False,
        name: str | None = None,
        transports: list[str] | None = None,
    ) -> UserWebauthnRow:
        ts = now_ts()
        transports_json = json.dumps(transports or [], ensure_ascii=False)
        with self._db.transaction() as conn:
            row_id = insert_returning_id(
                conn,
                "INSERT INTO user_webauthn_credentials("
                "credential_id, user_id, public_key, user_handle, rp_id, aaguid, "
                "sign_count, backup_eligible, backup_state, name, transports_json, "
                "created_at, last_used_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                (
                    credential_id,
                    user_id,
                    public_key,
                    user_handle,
                    rp_id,
                    aaguid,
                    sign_count,
                    1 if backup_eligible else 0,
                    1 if backup_state else 0,
                    name,
                    transports_json,
                    ts,
                ),
            )
        row = self.get_by_credential_id(credential_id)
        assert row is not None and row.id == row_id
        return row

    def update_sign_count(
        self,
        credential_id: str,
        *,
        sign_count: int,
        last_used_at: int | None = None,
    ) -> None:
        ts = last_used_at if last_used_at is not None else now_ts()
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE user_webauthn_credentials SET sign_count = ?, last_used_at = ? "
                "WHERE credential_id = ?",
                (sign_count, ts, credential_id),
            )

    def set_user_handle_for_user(self, user_id: int, user_handle: str) -> None:
        """Align all of a user's credentials to one handle (SPEC: one handle per user)."""
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE user_webauthn_credentials SET user_handle = ? WHERE user_id = ?",
                (user_handle, user_id),
            )

    def delete(self, user_id: int, credential_id: str) -> bool:
        with self._db.transaction() as conn:
            cur = conn.execute(
                "DELETE FROM user_webauthn_credentials WHERE user_id = ? AND credential_id = ?",
                (user_id, credential_id),
            )
            return int(cur.rowcount or 0) > 0

    def delete_all_for_user(self, user_id: int) -> int:
        with self._db.transaction() as conn:
            cur = conn.execute(
                "DELETE FROM user_webauthn_credentials WHERE user_id = ?",
                (user_id,),
            )
            return int(cur.rowcount or 0)
