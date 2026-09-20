"""SSO provider and login-state table access."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any

try:
    from psycopg import errors as pg_errors
except ImportError:  # pragma: no cover - optional PostgreSQL driver
    pg_errors = None  # type: ignore[assignment]

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow, bool_int, insert_returning_id, map_rows, now_ts


def _is_unique_violation(exc: BaseException) -> bool:
    if isinstance(exc, sqlite3.IntegrityError):
        return "unique" in str(exc).lower()
    return pg_errors is not None and isinstance(exc, pg_errors.UniqueViolation)


def _parse_extra(raw: object) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def _extra_json(extra: dict[str, Any] | None) -> str:
    return json.dumps(extra or {}, ensure_ascii=False)


@dataclass(frozen=True)
class SsoProviderRow:
    id: int
    enabled: int
    display_name: str
    issuer: str
    client_id: str
    client_secret_enc: bytes | None
    scopes: str
    dashboard_origin: str | None
    created_at: int
    updated_at: int
    kind: str = "oidc"
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_row(cls, row: DbRow) -> SsoProviderRow:
        secret = row["client_secret_enc"]
        keys = set(row.keys())
        return cls(
            id=int(row["id"]),
            enabled=int(row["enabled"]),
            display_name=str(row["display_name"]),
            issuer=str(row["issuer"]),
            client_id=str(row["client_id"]),
            client_secret_enc=bytes(secret) if secret is not None else None,
            scopes=str(row["scopes"]),
            dashboard_origin=row["dashboard_origin"],
            created_at=int(row["created_at"]),
            updated_at=int(row["updated_at"]),
            kind=str(row["kind"]) if "kind" in keys and row["kind"] else "oidc",
            extra=_parse_extra(row["extra"] if "extra" in keys else None),
        )


@dataclass(frozen=True)
class SsoLoginStateRow:
    state: str
    provider_id: int
    nonce: str
    code_verifier: str
    redirect_after: str
    login_code: str | None
    user_id: int | None
    expires_at: int
    consumed_at: int | None
    created_at: int

    @classmethod
    def from_row(cls, row: DbRow) -> SsoLoginStateRow:
        return cls(
            state=str(row["state"]),
            provider_id=int(row["provider_id"]),
            nonce=str(row["nonce"]),
            code_verifier=str(row["code_verifier"]),
            redirect_after=str(row["redirect_after"]),
            login_code=row["login_code"],
            user_id=int(row["user_id"]) if row["user_id"] is not None else None,
            expires_at=int(row["expires_at"]),
            consumed_at=int(row["consumed_at"]) if row["consumed_at"] is not None else None,
            created_at=int(row["created_at"]),
        )


class SsoRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def get_provider(self) -> SsoProviderRow | None:
        """Return the OIDC provider row (legacy single-provider helper)."""
        return self.get_by_kind("oidc")

    def get_by_id(self, provider_id: int) -> SsoProviderRow | None:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM sso_providers WHERE id = ?", (provider_id,)
            ).fetchone()
        return SsoProviderRow.from_row(row) if row else None

    def get_by_kind(self, kind: str) -> SsoProviderRow | None:
        with self._db.connect() as conn:
            row = conn.execute("SELECT * FROM sso_providers WHERE kind = ?", (kind,)).fetchone()
        return SsoProviderRow.from_row(row) if row else None

    def list(self) -> list[SsoProviderRow]:
        with self._db.connect() as conn:
            rows = conn.execute("SELECT * FROM sso_providers ORDER BY id").fetchall()
        return map_rows(rows, SsoProviderRow)

    def upsert_provider(
        self,
        *,
        enabled: bool,
        display_name: str,
        issuer: str,
        client_id: str,
        client_secret_enc: bytes | None,
        scopes: str,
        dashboard_origin: str | None,
    ) -> SsoProviderRow:
        return self.upsert_by_kind(
            "oidc",
            enabled=enabled,
            display_name=display_name,
            issuer=issuer,
            client_id=client_id,
            client_secret_enc=client_secret_enc,
            scopes=scopes,
            dashboard_origin=dashboard_origin,
        )

    def upsert_by_kind(
        self,
        kind: str,
        *,
        enabled: bool,
        display_name: str,
        issuer: str,
        client_id: str,
        client_secret_enc: bytes | None,
        scopes: str,
        dashboard_origin: str | None,
        extra: dict[str, Any] | None = None,
    ) -> SsoProviderRow:
        ts = now_ts()
        extra_json = _extra_json(extra)
        with self._db.transaction() as conn:
            existing = conn.execute(
                "SELECT * FROM sso_providers WHERE kind = ?", (kind,)
            ).fetchone()
            if existing is None:
                try:
                    provider_id = insert_returning_id(
                        conn,
                        "INSERT INTO sso_providers("
                        "enabled, display_name, issuer, client_id, client_secret_enc, scopes, "
                        "dashboard_origin, kind, extra, created_at, updated_at"
                        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            bool_int(enabled),
                            display_name,
                            issuer,
                            client_id,
                            client_secret_enc,
                            scopes,
                            dashboard_origin,
                            kind,
                            extra_json,
                            ts,
                            ts,
                        ),
                    )
                except Exception as exc:
                    if not _is_unique_violation(exc):
                        raise
                    existing = conn.execute(
                        "SELECT * FROM sso_providers WHERE kind = ?", (kind,)
                    ).fetchone()
                    if existing is None:
                        raise
                    provider_id = self._update_provider(
                        conn,
                        int(existing["id"]),
                        enabled=enabled,
                        display_name=display_name,
                        issuer=issuer,
                        client_id=client_id,
                        client_secret_enc=client_secret_enc,
                        scopes=scopes,
                        dashboard_origin=dashboard_origin,
                        extra_json=extra_json,
                        ts=ts,
                    )
            else:
                provider_id = self._update_provider(
                    conn,
                    int(existing["id"]),
                    enabled=enabled,
                    display_name=display_name,
                    issuer=issuer,
                    client_id=client_id,
                    client_secret_enc=client_secret_enc,
                    scopes=scopes,
                    dashboard_origin=dashboard_origin,
                    extra_json=extra_json,
                    ts=ts,
                )
            row = conn.execute(
                "SELECT * FROM sso_providers WHERE id = ?", (provider_id,)
            ).fetchone()
        if row is None:
            raise RuntimeError("SSO provider upsert returned no row")
        return SsoProviderRow.from_row(row)

    @staticmethod
    def _update_provider(
        conn: Any,
        provider_id: int,
        *,
        enabled: bool,
        display_name: str,
        issuer: str,
        client_id: str,
        client_secret_enc: bytes | None,
        scopes: str,
        dashboard_origin: str | None,
        extra_json: str,
        ts: int,
    ) -> int:
        fields = [
            "enabled = ?",
            "display_name = ?",
            "issuer = ?",
            "client_id = ?",
            "scopes = ?",
            "dashboard_origin = ?",
            "extra = ?",
            "updated_at = ?",
        ]
        params: list[object] = [
            bool_int(enabled),
            display_name,
            issuer,
            client_id,
            scopes,
            dashboard_origin,
            extra_json,
            ts,
        ]
        if client_secret_enc is not None:
            fields.insert(4, "client_secret_enc = ?")
            params.insert(4, client_secret_enc)
        conn.execute(
            f"UPDATE sso_providers SET {', '.join(fields)} WHERE id = ?",
            (*params, provider_id),
        )
        return provider_id

    def create_login_state(
        self,
        *,
        state: str,
        provider_id: int,
        nonce: str,
        code_verifier: str,
        redirect_after: str,
        expires_at: int,
        user_id: int | None = None,
    ) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO sso_login_states("
                "state, provider_id, nonce, code_verifier, redirect_after, user_id, "
                "expires_at, created_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    state,
                    provider_id,
                    nonce,
                    code_verifier,
                    redirect_after,
                    user_id,
                    expires_at,
                    now_ts(),
                ),
            )

    def take_login_state(self, state: str) -> SsoLoginStateRow | None:
        """Atomically claim a login state for one callback attempt."""
        with self._db.transaction() as conn:
            row = conn.execute(
                "UPDATE sso_login_states SET consumed_at = ? "
                "WHERE state = ? AND consumed_at IS NULL AND expires_at > ? "
                "AND login_code IS NULL RETURNING *",
                (now_ts(), state, now_ts()),
            ).fetchone()
        return SsoLoginStateRow.from_row(row) if row else None

    def attach_login_code(self, state: str, login_code: str, user_id: int, expires_at: int) -> None:
        """Attach a one-time login code after a claimed callback succeeds.

        Clears ``consumed_at`` so ``consume_login_code`` can finalize the session.
        """
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE sso_login_states SET login_code = ?, user_id = ?, expires_at = ?, "
                "consumed_at = NULL WHERE state = ? AND login_code IS NULL",
                (login_code, user_id, expires_at, state),
            )

    def consume_login_code(self, login_code: str) -> dict[str, int] | None:
        with self._db.transaction() as conn:
            row = conn.execute(
                "UPDATE sso_login_states SET consumed_at = ? "
                "WHERE login_code = ? AND consumed_at IS NULL AND expires_at > ? "
                "AND user_id IS NOT NULL RETURNING user_id",
                (now_ts(), login_code, now_ts()),
            ).fetchone()
        return {"user_id": int(row["user_id"])} if row else None

    def delete_expired(self, now: int | None = None) -> None:
        ts = now if now is not None else now_ts()
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM sso_login_states WHERE expires_at <= ?", (ts,))
