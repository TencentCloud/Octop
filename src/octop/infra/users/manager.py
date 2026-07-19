"""UserManager — process-singleton user lifecycle."""

from __future__ import annotations

import asyncio
import builtins
import logging
import shutil
import time
from typing import Any

from octop.infra.db.repos.audit import ACTOR_ADMIN
from octop.infra.db.services import SharedServices
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.identity import Role, User
from octop.infra.users.password import hash_password, verify_password
from octop.infra.users.preferences import (
    RemoteBrowserBookmark,
    get_remote_browser_bookmarks_from_json,
    merge_preferences_json,
    validate_remote_browser_bookmarks,
)
from octop.infra.utils.locale import normalize_locale

logger = logging.getLogger(__name__)


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
    ) -> User:
        if not username:
            raise OctopError(ErrorCode.USERNAME_TAKEN, "username must not be empty")
        loc = normalize_locale(locale)
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
            )
            user = User(
                id=uid,
                username=username,
                role=role,
                display_name=display_name,
                locale=loc,
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

    async def authenticate(self, username: str, password: str) -> User | None:
        row = self._services.user_repo.get_by_username(username)
        if row is None:
            return None
        now = int(time.time())
        if row.disabled:
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
            )
            self._users[username] = user
        self._services.audit_repo.write(actor=username, action="auth.login")
        return user

    async def change_password(self, username: str, old: str, new: str) -> None:
        row = self._services.user_repo.get_by_username(username)
        if row is None or not verify_password(old, row.password_hash):
            raise OctopError(ErrorCode.AUTH_FAILED, "current password incorrect")
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
        self._services.user_repo.set_password_hash(row.id, hash_password(new))
        self._services.user_repo.clear_login_lockout(row.id)
        self._services.audit_repo.write(
            actor=ACTOR_ADMIN, action="user.password_reset", target=username
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
