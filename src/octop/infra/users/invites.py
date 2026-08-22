"""One-time user invite codes — create, validate, redeem."""

from __future__ import annotations

import secrets
import string
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

from octop.infra.db.repos._base import now_ts
from octop.infra.db.repos.invites import InviteRepo, InviteRow, invite_status_payload
from octop.infra.db.services import SharedServices
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.identity import Role, User
from octop.infra.users.password import hash_password, validate_password_policy
from octop.infra.utils.locale import normalize_locale

DEFAULT_EXPIRES_DAYS = 7
MIN_EXPIRES_DAYS = 1
MAX_EXPIRES_DAYS = 90
_CODE_ALPHABET = string.ascii_letters + string.digits
_CODE_LENGTH = 11

RATE_LIMIT_BURST = 20
RATE_LIMIT_WINDOW = 60.0


@dataclass
class InviteRateLimiter:
    """Simple IP/client burst limiter for public invite endpoints."""

    now: Callable[[], float] = field(default=time.monotonic)
    _attempts: dict[str, deque[float]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def check(self, client_id: str) -> None:
        cutoff = self.now() - RATE_LIMIT_WINDOW
        with self._lock:
            bucket = self._attempts.setdefault(client_id, deque())
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= RATE_LIMIT_BURST:
                raise OctopError(ErrorCode.INVITE_RATE_LIMITED, "too many invite attempts")
            bucket.append(self.now())


_PUBLIC_LIMITER = InviteRateLimiter()


def generate_invite_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))


def invite_path(code: str) -> str:
    """Canonical share path (SPA root query), matching common invite links."""
    return f"/?invite={code}"


def build_invite_url(base_url: str, code: str) -> str:
    return f"{base_url.rstrip('/')}{invite_path(code)}"


class InviteService:
    def __init__(self, services: SharedServices) -> None:
        self._services = services

    @property
    def _repo(self) -> InviteRepo:
        return self._services.invite_repo

    def create(
        self,
        *,
        created_by: int,
        actor_username: str,
        note: str | None = None,
        expires_in_days: int = DEFAULT_EXPIRES_DAYS,
    ) -> InviteRow:
        days = int(expires_in_days)
        if days < MIN_EXPIRES_DAYS or days > MAX_EXPIRES_DAYS:
            raise OctopError(
                ErrorCode.FORBIDDEN,
                f"expires_in_days must be between {MIN_EXPIRES_DAYS} and {MAX_EXPIRES_DAYS}",
                status=400,
            )
        cleaned = note.strip() if isinstance(note, str) else None
        if cleaned == "":
            cleaned = None
        expires_at = now_ts() + days * 86400
        # Extremely unlikely collision; retry a few times.
        for _ in range(8):
            code = generate_invite_code()
            if self._repo.get_by_code(code) is None:
                row = self._repo.create(
                    code=code,
                    created_by=created_by,
                    expires_at=expires_at,
                    note=cleaned,
                )
                self._services.audit_repo.write(
                    actor=actor_username,
                    action="invite.create",
                    target=code,
                )
                return row
        raise OctopError(ErrorCode.INTERNAL_ERROR, "failed to allocate invite code")

    def list_all(self) -> list[dict[str, object]]:
        return [invite_status_payload(row) for row in self._repo.list_all()]

    def revoke(self, invite_id: int, *, actor_username: str) -> dict[str, object]:
        before = self._repo.get(invite_id)
        if before is None:
            raise OctopError(ErrorCode.NOT_FOUND, "invite not found")
        if before.status() != "pending":
            raise OctopError(
                ErrorCode.INVITE_INVALID,
                f"invite cannot be revoked (status={before.status()})",
                status=409,
            )
        after = self._repo.revoke(invite_id)
        assert after is not None
        self._services.audit_repo.write(
            actor=actor_username,
            action="invite.revoke",
            target=after.code,
        )
        return invite_status_payload(after)

    def validate(self, code: str) -> dict[str, object]:
        cleaned = (code or "").strip()
        if not cleaned:
            raise OctopError(ErrorCode.INVITE_INVALID, "invite code required", status=400)
        row = self._repo.get_by_code(cleaned)
        if row is None:
            raise OctopError(ErrorCode.INVITE_INVALID, "invite not found")
        status = row.status()
        if status == "used":
            raise OctopError(ErrorCode.INVITE_USED, "invite already used")
        if status == "expired":
            raise OctopError(ErrorCode.INVITE_EXPIRED, "invite expired")
        if status == "revoked":
            raise OctopError(ErrorCode.INVITE_REVOKED, "invite revoked")
        return {"ok": True, "expires_at": row.expires_at}

    def redeem(
        self,
        *,
        code: str,
        username: str,
        password: str,
        display_name: str | None,
        locale: str | None,
        register_user: Callable[[User], None],
    ) -> User:
        cleaned_code = (code or "").strip()
        cleaned_username = (username or "").strip()
        if not cleaned_code:
            raise OctopError(ErrorCode.INVITE_INVALID, "invite code required", status=400)
        if not cleaned_username:
            raise OctopError(ErrorCode.USERNAME_TAKEN, "username must not be empty", status=400)
        validate_password_policy(password)
        loc = normalize_locale(locale)
        name = display_name.strip() if isinstance(display_name, str) else None
        if name == "":
            name = None
        try:
            user_id, _invite = self._repo.redeem_creating_user(
                code=cleaned_code,
                username=cleaned_username,
                password_hash=hash_password(password),
                display_name=name,
                locale=loc,
            )
        except LookupError as exc:
            raise OctopError(ErrorCode.INVITE_INVALID, "invite not found") from exc
        except ValueError as exc:
            reason = str(exc)
            if reason == "username_taken":
                raise OctopError(
                    ErrorCode.USERNAME_TAKEN,
                    f"username {cleaned_username!r} already exists",
                ) from exc
            if reason == "used":
                raise OctopError(ErrorCode.INVITE_USED, "invite already used") from exc
            if reason == "expired":
                raise OctopError(ErrorCode.INVITE_EXPIRED, "invite expired") from exc
            if reason == "revoked":
                raise OctopError(ErrorCode.INVITE_REVOKED, "invite revoked") from exc
            raise OctopError(ErrorCode.INVITE_INVALID, "invite not usable") from exc

        user = User(
            id=user_id,
            username=cleaned_username,
            role=Role.USER,
            display_name=name,
            locale=loc,
            permissions=[],
        )
        register_user(user)
        self._services.audit_repo.write(
            actor=cleaned_username,
            action="invite.redeem",
            target=cleaned_code,
        )
        return user


def check_invite_rate_limit(client_id: str) -> None:
    _PUBLIC_LIMITER.check(client_id)
