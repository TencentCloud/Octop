"""DB-backed short-lived auth challenges (WebAuthn + MFA/reauth jti burn)."""

from __future__ import annotations

from dataclasses import dataclass

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow, insert_returning_id, now_ts

KIND_WEBAUTHN_LOGIN = "webauthn_login"
KIND_WEBAUTHN_REGISTER = "webauthn_register"
KIND_WEBAUTHN_ASSERT = "webauthn_assert"
KIND_MFA = "mfa"
KIND_REAUTH = "reauth"


@dataclass(frozen=True)
class AuthChallengeRow:
    id: int
    challenge: str | None
    jti: str | None
    kind: str
    user_id: int | None
    attempts: int
    expires_at: int
    consumed_at: int | None
    created_at: int

    @classmethod
    def from_row(cls, r: DbRow) -> AuthChallengeRow:
        return cls(
            id=int(r["id"]),
            challenge=str(r["challenge"]) if r["challenge"] is not None else None,
            jti=str(r["jti"]) if r["jti"] is not None else None,
            kind=str(r["kind"]),
            user_id=int(r["user_id"]) if r["user_id"] is not None else None,
            attempts=int(r["attempts"] or 0),
            expires_at=int(r["expires_at"]),
            consumed_at=int(r["consumed_at"]) if r["consumed_at"] is not None else None,
            created_at=int(r["created_at"]),
        )


class AuthChallengeRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def insert(
        self,
        *,
        kind: str,
        expires_at: int,
        challenge: str | None = None,
        jti: str | None = None,
        user_id: int | None = None,
    ) -> AuthChallengeRow:
        self.prune_expired()
        ts = now_ts()
        with self._db.transaction() as conn:
            row_id = insert_returning_id(
                conn,
                "INSERT INTO auth_challenges("
                "challenge, jti, kind, user_id, attempts, expires_at, consumed_at, created_at) "
                "VALUES (?, ?, ?, ?, 0, ?, NULL, ?)",
                (challenge, jti, kind, user_id, expires_at, ts),
            )
        row = self.get(row_id)
        assert row is not None
        return row

    def get(self, challenge_id: int) -> AuthChallengeRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT * FROM auth_challenges WHERE id = ?",
                (challenge_id,),
            ).fetchone()
        return AuthChallengeRow.from_row(r) if r else None

    def get_by_jti(self, jti: str) -> AuthChallengeRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT * FROM auth_challenges WHERE jti = ?",
                (jti,),
            ).fetchone()
        return AuthChallengeRow.from_row(r) if r else None

    def get_by_challenge(self, challenge: str) -> AuthChallengeRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT * FROM auth_challenges WHERE challenge = ?",
                (challenge,),
            ).fetchone()
        return AuthChallengeRow.from_row(r) if r else None

    def try_consume_jti(self, jti: str, *, now: int | None = None) -> AuthChallengeRow | None:
        """Atomically consume an unconsumed, unexpired challenge by jti."""
        ts = now if now is not None else now_ts()
        with self._db.transaction() as conn:
            r = conn.execute(
                "SELECT * FROM auth_challenges WHERE jti = ? "
                "AND consumed_at IS NULL AND expires_at >= ?",
                (jti, ts),
            ).fetchone()
            if r is None:
                return None
            cur = conn.execute(
                "UPDATE auth_challenges SET consumed_at = ? WHERE id = ? AND consumed_at IS NULL",
                (ts, int(r["id"])),
            )
            if int(cur.rowcount or 0) == 0:
                return None
        return AuthChallengeRow.from_row(r)

    def try_consume_id(
        self, challenge_id: int, *, now: int | None = None
    ) -> AuthChallengeRow | None:
        ts = now if now is not None else now_ts()
        with self._db.transaction() as conn:
            r = conn.execute(
                "SELECT * FROM auth_challenges WHERE id = ? "
                "AND consumed_at IS NULL AND expires_at >= ?",
                (challenge_id, ts),
            ).fetchone()
            if r is None:
                return None
            cur = conn.execute(
                "UPDATE auth_challenges SET consumed_at = ? WHERE id = ? AND consumed_at IS NULL",
                (ts, challenge_id),
            )
            if int(cur.rowcount or 0) == 0:
                return None
        return AuthChallengeRow.from_row(r)

    def increment_attempts(
        self,
        challenge_id: int,
        *,
        max_attempts: int = 5,
        now: int | None = None,
    ) -> AuthChallengeRow | None:
        """Bump attempts; burn (consume) when ``max_attempts`` is reached."""
        ts = now if now is not None else now_ts()
        with self._db.transaction() as conn:
            r = conn.execute(
                "SELECT * FROM auth_challenges WHERE id = ? AND consumed_at IS NULL",
                (challenge_id,),
            ).fetchone()
            if r is None:
                return None
            attempts = int(r["attempts"] or 0) + 1
            if attempts >= max_attempts:
                conn.execute(
                    "UPDATE auth_challenges SET attempts = ?, consumed_at = ? WHERE id = ?",
                    (attempts, ts, challenge_id),
                )
            else:
                conn.execute(
                    "UPDATE auth_challenges SET attempts = ? WHERE id = ?",
                    (attempts, challenge_id),
                )
        return self.get(challenge_id)

    def burn_jti(self, jti: str, *, now: int | None = None) -> bool:
        """Force-consume a challenge by jti (version mismatch / lockout)."""
        ts = now if now is not None else now_ts()
        with self._db.transaction() as conn:
            cur = conn.execute(
                "UPDATE auth_challenges SET consumed_at = ? WHERE jti = ? AND consumed_at IS NULL",
                (ts, jti),
            )
            return int(cur.rowcount or 0) > 0

    def prune_expired(self, *, now: int | None = None) -> int:
        ts = now if now is not None else now_ts()
        with self._db.transaction() as conn:
            cur = conn.execute(
                "DELETE FROM auth_challenges WHERE expires_at < ? OR consumed_at IS NOT NULL",
                (ts,),
            )
            return int(cur.rowcount or 0)
