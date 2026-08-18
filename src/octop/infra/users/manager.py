"""UserManager — process-singleton user lifecycle."""

from __future__ import annotations

import asyncio
import builtins
import hashlib
import logging
import re
import shutil
import sqlite3
import time
from typing import Any

try:
    from psycopg import errors as pg_errors
except ImportError:  # pragma: no cover - optional PostgreSQL driver
    pg_errors = None  # type: ignore[assignment]

from octop.infra.db.repos.audit import ACTOR_ADMIN
from octop.infra.db.repos.users import UserRepo
from octop.infra.db.services import SharedServices
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.identity import Role, User
from octop.infra.users.password import hash_password, validate_password_policy, verify_password
from octop.infra.users.permissions import validate_permission_keys
from octop.infra.users.preferences import (
    ModelReasoningPreference,
    RemoteBrowserBookmark,
    get_avatar_reference_from_json,
    get_remote_browser_bookmarks_from_json,
    merge_avatar_preferences_json,
    merge_model_preferences_json,
    merge_preferences_json,
    validate_remote_browser_bookmarks,
)
from octop.infra.utils.locale import normalize_locale

logger = logging.getLogger(__name__)
_USERNAME_ALLOWED = re.compile(r"[^a-zA-Z0-9_.-]")
_MAX_USERNAME_LENGTH = 64


def allocate_username(repo: UserRepo, claims: dict[str, Any], subject: str) -> str:
    """Return an available username derived from OIDC claims and subject."""
    preferred = claims.get("preferred_username")
    email = claims.get("email")
    candidate = preferred if isinstance(preferred, str) and preferred.strip() else None
    if candidate is None and isinstance(email, str) and email.strip():
        candidate = email.strip().split("@", maxsplit=1)[0]
    if candidate is None:
        candidate = f"sso_{hashlib.sha256(subject.encode()).hexdigest()[:12]}"

    base = _USERNAME_ALLOWED.sub("", candidate)[:_MAX_USERNAME_LENGTH]
    if not base:
        base = f"sso_{hashlib.sha256(subject.encode()).hexdigest()[:12]}"

    username = base
    suffix = 2
    while repo.get_by_username(username) is not None:
        marker = f"_{suffix}"
        username = f"{base[: _MAX_USERNAME_LENGTH - len(marker)]}{marker}"
        suffix += 1
    return username


def _normalized_claim_email(claims: dict[str, Any]) -> str | None:
    email = claims.get("email")
    if not isinstance(email, str):
        return None
    return email.strip().lower() or None


def _claim_display_name(claims: dict[str, Any]) -> str | None:
    name = claims.get("name")
    return name.strip() if isinstance(name, str) and name.strip() else None


def _is_unique_violation(exc: BaseException) -> bool:
    if isinstance(exc, sqlite3.IntegrityError):
        return "unique" in str(exc).lower()
    return pg_errors is not None and isinstance(exc, pg_errors.UniqueViolation)


class UserManager:
    """Owns the in-memory dict of ``User`` objects.

    User management only — agent lifecycle is now handled by AgentManager.
    """

    def __init__(self, services: SharedServices):
        self._services = services
        self._users: dict[str, User] = {}
        self._lock = asyncio.Lock()
        self._login_max_attempts = max(1, services.config.login_max_attempts)
        self._login_lockout_seconds = max(60, services.config.login_lockout_seconds)

    def replace_services(self, services: SharedServices) -> None:
        """Point at a new SharedServices (control-plane DB rebind during setup)."""
        self._services = services
        self._login_max_attempts = max(1, services.config.login_max_attempts)
        self._login_lockout_seconds = max(60, services.config.login_lockout_seconds)

    # ----- lifecycle -----

    async def boot(self) -> None:
        async with self._lock:
            for row in self._services.user_repo.list(include_disabled=False):
                user = User(
                    id=row.id,
                    username=row.username,
                    role=Role(row.role),
                    display_name=row.display_name,
                    locale=normalize_locale(row.locale),
                    permissions=list(row.permissions),
                )
                self._users[row.username] = user

    async def shutdown_all(self) -> None:
        async with self._lock:
            self._users.clear()

    # ----- CRUD -----

    async def create(
        self,
        *,
        username: str,
        password: str,
        role: Role,
        display_name: str | None = None,
        locale: str | None = None,
        permissions: builtins.list[str] | None = None,
    ) -> User:
        if not username:
            raise OctopError(ErrorCode.USERNAME_TAKEN, "username must not be empty")
        loc = normalize_locale(locale)
        validate_password_policy(password)
        try:
            keys = validate_permission_keys(permissions or [])
        except ValueError as exc:
            raise OctopError(ErrorCode.FORBIDDEN, str(exc), status=400) from exc
        async with self._lock:
            if self._services.user_repo.get_by_username(username) is not None:
                raise OctopError(
                    ErrorCode.USERNAME_TAKEN,
                    f"username {username!r} already exists",
                )
            uid = self._services.user_repo.create(
                username=username,
                password_hash=hash_password(password),
                role=role.value,
                display_name=display_name,
                locale=loc,
                permissions=keys,
            )
            user = User(
                id=uid,
                username=username,
                role=role,
                display_name=display_name,
                locale=loc,
                permissions=keys,
            )
            self._users[username] = user
            self._services.audit_repo.write(actor=username, action="user.create", target=username)
            return user

    def get(self, username: str) -> User | None:
        return self._users.get(username)

    def get_by_id(self, user_id: int) -> User | None:
        for u in self._users.values():
            if u.id == user_id:
                return u
        return None

    def get_row(self, user_id: int) -> Any:
        """Return the raw UserRow (includes disabled flag) for admin read operations."""
        return self._services.user_repo.get(user_id)

    def list(self) -> list[User]:
        return sorted(self._users.values(), key=lambda u: u.username)

    def list_all(self, *, include_disabled: bool = True) -> builtins.list[Any]:
        """Return all UserRow objects (for admin listing, includes disabled users)."""
        return self._services.user_repo.list(include_disabled=include_disabled)

    def count(self) -> int:
        return self._services.user_repo.count()

    # ----- auth -----

    async def resolve_or_create_sso_user(
        self,
        *,
        provider_id: int,
        subject: str,
        claims: dict[str, Any],
    ) -> User:
        async with self._lock:
            row = self._services.user_repo.get_by_sso(provider_id, subject)
            email = _normalized_claim_email(claims)
            display_name = _claim_display_name(claims)

            if row is None:
                for attempt in range(3):
                    if (
                        email is not None
                        and self._services.user_repo.get_by_email(email) is not None
                    ):
                        email = None
                    username = allocate_username(self._services.user_repo, claims, subject)
                    try:
                        uid = self._services.user_repo.create(
                            username=username,
                            password_hash=None,
                            role=Role.USER.value,
                            display_name=display_name,
                            email=email,
                            sso_provider_id=provider_id,
                            sso_subject=subject,
                        )
                    except Exception as exc:
                        if not _is_unique_violation(exc):
                            raise
                        row = self._services.user_repo.get_by_sso(provider_id, subject)
                        if row is not None:
                            break
                        if attempt == 2:
                            raise
                        await asyncio.sleep(0.01 * (attempt + 1))
                    else:
                        user = User(
                            id=uid,
                            username=username,
                            role=Role.USER,
                            display_name=display_name,
                            permissions=[],
                        )
                        self._users[username] = user
                        self._services.audit_repo.write(
                            actor=username, action="user.sso_create", target=username
                        )
                        return user

            assert row is not None  # The retry loop either returns, raises, or finds this identity.
            if row.disabled:
                raise OctopError(ErrorCode.USER_DISABLED, "user is disabled")
            if email is not None:
                email_owner = self._services.user_repo.get_by_email(email)
                if email_owner is not None and email_owner.id != row.id:
                    email = None
            self._services.user_repo.update_sso_profile(
                row.id,
                email=email,
                display_name=display_name,
            )
            cached_user = self._users.get(row.username)
            if cached_user is None:
                user = User(
                    id=row.id,
                    username=row.username,
                    role=Role(row.role),
                    display_name=display_name if display_name is not None else row.display_name,
                    locale=normalize_locale(row.locale),
                    permissions=list(row.permissions),
                )
                self._users[row.username] = user
                return user
            if display_name is not None:
                cached_user.display_name = display_name
            return cached_user

    async def authenticate(self, username: str, password: str) -> User | None:
        row = self._services.user_repo.get_by_username(username)
        if row is None:
            return None
        now = int(time.time())
        if row.disabled:
            return None
        if not row.password_hash:
            return None
        locked_until = int(row.login_locked_until or 0)
        if locked_until > now:
            retry_after = locked_until - now
            minutes = max(1, (retry_after + 59) // 60)
            raise OctopError(
                ErrorCode.LOGIN_LOCKED,
                "account temporarily locked",
                details={"retry_after_seconds": retry_after, "minutes": minutes},
            )
        if not verify_password(password, row.password_hash):
            retry_after = self._services.user_repo.record_failed_login(
                row.id,
                max_attempts=self._login_max_attempts,
                lockout_seconds=self._login_lockout_seconds,
                now=now,
            )
            self._services.audit_repo.write(actor=username, action="auth.failed", target=username)
            if retry_after > 0:
                minutes = max(1, (retry_after + 59) // 60)
                raise OctopError(
                    ErrorCode.LOGIN_LOCKED,
                    "account temporarily locked",
                    details={"retry_after_seconds": retry_after, "minutes": minutes},
                )
            return None
        self._services.user_repo.clear_login_lockout(row.id)
        user = self._users.get(username)
        if user is None:
            user = User(
                id=row.id,
                username=row.username,
                role=Role(row.role),
                display_name=row.display_name,
                locale=normalize_locale(row.locale),
                permissions=list(row.permissions),
            )
            self._users[username] = user
        self._services.audit_repo.write(actor=username, action="auth.login")
        return user

    async def change_password(self, username: str, old: str, new: str) -> None:
        row = self._services.user_repo.get_by_username(username)
        if row is None or not row.password_hash or not verify_password(old, row.password_hash):
            raise OctopError(ErrorCode.AUTH_FAILED, "current password incorrect")
        validate_password_policy(new, old_password=old)
        self._services.user_repo.set_password_hash(row.id, hash_password(new))
        self._services.user_repo.clear_login_lockout(row.id)
        self._services.audit_repo.write(
            actor=username, action="user.password_changed", target=username
        )

    async def reset_password(self, username: str, new: str) -> None:
        """Admin-driven reset (no old-password check)."""
        row = self._services.user_repo.get_by_username(username)
        if row is None:
            raise OctopError(ErrorCode.NOT_FOUND, "user not found")
        validate_password_policy(new)
        self._services.user_repo.set_password_hash(row.id, hash_password(new))
        self._services.user_repo.clear_login_lockout(row.id)
        self._services.audit_repo.write(
            actor=ACTOR_ADMIN, action="user.password_reset", target=username
        )

    async def set_permissions(self, username: str, permissions: builtins.list[str]) -> None:
        row = self._services.user_repo.get_by_username(username)
        if row is None:
            raise OctopError(ErrorCode.NOT_FOUND, "user not found")
        try:
            keys = validate_permission_keys(permissions)
        except ValueError as exc:
            raise OctopError(ErrorCode.FORBIDDEN, str(exc), status=400) from exc
        self._services.user_repo.set_permissions(row.id, keys)
        async with self._lock:
            current = self._users.get(username)
            if current is not None:
                current.permissions = list(keys)
        self._services.audit_repo.write(
            actor=ACTOR_ADMIN,
            action="user.set_permissions",
            target=username,
            payload=",".join(keys),
        )

    async def set_role(self, username: str, role: Role) -> None:
        row = self._services.user_repo.get_by_username(username)
        if row is None:
            raise OctopError(ErrorCode.NOT_FOUND, "user not found")
        self._services.user_repo.set_role(row.id, role.value)
        async with self._lock:
            current = self._users.get(username)
            if current is not None:
                current.role = role
        self._services.audit_repo.write(
            actor=ACTOR_ADMIN,
            action="user.set_role",
            target=username,
            payload=role.value,
        )

    async def set_display_name(self, username: str, display_name: str | None) -> None:
        row = self._services.user_repo.get_by_username(username)
        if row is None:
            raise OctopError(ErrorCode.NOT_FOUND, "user not found")
        self._services.user_repo.set_display_name(row.id, display_name)
        async with self._lock:
            current = self._users.get(username)
            if current is not None:
                current.display_name = display_name

    async def set_locale(self, username: str, locale: str) -> None:
        row = self._services.user_repo.get_by_username(username)
        if row is None:
            raise OctopError(ErrorCode.NOT_FOUND, "user not found")
        loc = normalize_locale(locale)
        self._services.user_repo.set_locale(row.id, loc)
        async with self._lock:
            current = self._users.get(username)
            if current is not None:
                current.locale = loc

    def get_remote_browser_bookmarks(self, user_id: int) -> builtins.list[RemoteBrowserBookmark]:
        row = self._services.user_repo.get(user_id)
        if row is None:
            return []
        return get_remote_browser_bookmarks_from_json(row.preferences_json)

    async def set_remote_browser_bookmarks(
        self,
        username: str,
        items: builtins.list[dict[str, str]],
    ) -> builtins.list[RemoteBrowserBookmark]:
        row = self._services.user_repo.get_by_username(username)
        if row is None:
            raise OctopError(ErrorCode.NOT_FOUND, "user not found")
        bookmarks = validate_remote_browser_bookmarks(items)
        merged = merge_preferences_json(row.preferences_json, bookmarks)
        self._services.user_repo.set_preferences_json(row.id, merged)
        return bookmarks

    def get_avatar_reference(self, user_id: int) -> str | None:
        row = self._services.user_repo.get(user_id)
        if row is None:
            return None
        return get_avatar_reference_from_json(row.preferences_json)

    async def set_avatar_reference(self, user_id: int, avatar: str | None) -> None:
        row = self._services.user_repo.get(user_id)
        if row is None:
            raise OctopError(ErrorCode.NOT_FOUND, "user not found")
        merged = merge_avatar_preferences_json(row.preferences_json, avatar=avatar)
        self._services.user_repo.set_preferences_json(row.id, merged)

    async def set_model_preferences(
        self,
        username: str,
        *,
        preferred_model: str | None | object = ...,
        model_reasoning: dict[str, ModelReasoningPreference] | None = None,
    ) -> None:
        row = self._services.user_repo.get_by_username(username)
        if row is None:
            raise OctopError(ErrorCode.NOT_FOUND, "user not found")
        merged = merge_model_preferences_json(
            row.preferences_json,
            preferred_model=preferred_model,
            model_reasoning=model_reasoning,
        )
        self._services.user_repo.set_preferences_json(row.id, merged)

    async def disable(self, username: str) -> None:
        row = self._services.user_repo.get_by_username(username)
        if row is None:
            raise OctopError(ErrorCode.NOT_FOUND, "user not found")
        async with self._lock:
            self._users.pop(username, None)
        self._services.user_repo.set_disabled(row.id, True)
        self._services.audit_repo.write(actor=ACTOR_ADMIN, action="user.disable", target=username)

    async def enable(self, username: str) -> None:
        row = self._services.user_repo.get_by_username(username)
        if row is None:
            raise OctopError(ErrorCode.NOT_FOUND, "user not found")
        self._services.user_repo.set_disabled(row.id, False)
        user = User(
            id=row.id,
            username=row.username,
            role=Role(row.role),
            display_name=row.display_name,
            locale=normalize_locale(row.locale),
            permissions=list(row.permissions),
        )
        async with self._lock:
            self._users[username] = user
        self._services.audit_repo.write(actor=ACTOR_ADMIN, action="user.enable", target=username)

    async def unlock_login(self, username: str) -> None:
        row = self._services.user_repo.get_by_username(username)
        if row is None:
            raise OctopError(ErrorCode.NOT_FOUND, "user not found")
        self._services.user_repo.clear_login_lockout(row.id)
        self._services.audit_repo.write(
            actor=ACTOR_ADMIN, action="user.unlock_login", target=username
        )

    async def remove(self, username: str) -> None:
        row = self._services.user_repo.get_by_username(username)
        if row is None:
            raise OctopError(ErrorCode.NOT_FOUND, "user not found")
        async with self._lock:
            self._users.pop(username, None)
        user_dir = self._services.paths.user_dir(row.username)
        try:
            if user_dir.exists():
                shutil.rmtree(user_dir)
        except OSError:
            logger.exception("rmtree failed for %s; user removed from DB anyway", user_dir)
        self._services.user_repo.delete(row.id)
        self._services.audit_repo.write(actor=ACTOR_ADMIN, action="user.delete", target=username)
