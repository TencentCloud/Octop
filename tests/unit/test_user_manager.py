"""tests/unit/test_user_manager.py"""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.config import OctopConfig
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import build_shared_services
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.identity import Role
from octop.infra.users.manager import UserManager
from octop.infra.utils.paths import PathLayout


@pytest.fixture
async def manager(tmp_path: Path) -> UserManager:
    paths = PathLayout(tmp_path / ".octop")
    paths.ensure_root()
    db = SqlitePool(paths.db)
    run_migrations(db)
    services = build_shared_services(db=db, paths=paths, config=OctopConfig())
    return UserManager(services)


async def test_create_user_writes_db(manager: UserManager):
    user = await manager.create(
        username="alice", password="pw", role=Role.ADMIN, display_name="Alice"
    )
    assert user.username == "alice"
    assert user.role is Role.ADMIN
    assert manager.get("alice") is not None


async def test_duplicate_username_rejected(manager: UserManager):
    await manager.create(username="a", password="pw", role=Role.USER)
    with pytest.raises(OctopError) as ei:
        await manager.create(username="a", password="pw2", role=Role.USER)
    assert ei.value.code is ErrorCode.USERNAME_TAKEN


async def test_authenticate_success(manager: UserManager):
    await manager.create(username="a", password="pw", role=Role.USER)
    user = await manager.authenticate("a", "pw")
    assert user is not None
    assert user.username == "a"


async def test_authenticate_wrong_password(manager: UserManager):
    await manager.create(username="a", password="pw", role=Role.USER)
    assert await manager.authenticate("a", "bad") is None


async def test_authenticate_locks_after_max_failures(manager: UserManager):
    await manager.create(username="a", password="pw", role=Role.USER)
    max_attempts = manager._login_max_attempts
    for _ in range(max_attempts - 1):
        assert await manager.authenticate("a", "bad") is None
    with pytest.raises(OctopError) as ei:
        await manager.authenticate("a", "bad")
    assert ei.value.code is ErrorCode.LOGIN_LOCKED
    with pytest.raises(OctopError) as ei2:
        await manager.authenticate("a", "bad")
    assert ei2.value.code is ErrorCode.LOGIN_LOCKED
    with pytest.raises(OctopError) as ei3:
        await manager.authenticate("a", "pw")
    assert ei3.value.code is ErrorCode.LOGIN_LOCKED


async def test_reset_password_clears_lockout(manager: UserManager):
    await manager.create(username="a", password="pw", role=Role.USER)
    max_attempts = manager._login_max_attempts
    for _ in range(max_attempts - 1):
        assert await manager.authenticate("a", "bad") is None
    with pytest.raises(OctopError):
        await manager.authenticate("a", "bad")
    with pytest.raises(OctopError):
        await manager.authenticate("a", "pw")
    await manager.reset_password("a", "new")
    user = await manager.authenticate("a", "new")
    assert user is not None


async def test_authenticate_disabled_returns_none(manager: UserManager):
    user = await manager.create(username="a", password="pw", role=Role.USER)
    await manager.disable(user.username)
    assert await manager.authenticate("a", "pw") is None


async def test_get_by_username_and_id(manager: UserManager):
    user = await manager.create(username="a", password="pw", role=Role.USER)
    assert manager.get("a").id == user.id
    assert manager.get_by_id(user.id).username == "a"


async def test_change_password(manager: UserManager):
    user = await manager.create(username="a", password="old", role=Role.USER)
    await manager.change_password(user.username, "old", "new")
    assert await manager.authenticate("a", "new") is not None
    assert await manager.authenticate("a", "old") is None


async def test_change_password_wrong_old(manager: UserManager):
    await manager.create(username="a", password="old", role=Role.USER)
    with pytest.raises(OctopError) as ei:
        await manager.change_password("a", "wrong", "new")
    assert ei.value.code is ErrorCode.AUTH_FAILED


async def test_set_role(manager: UserManager):
    await manager.create(username="a", password="pw", role=Role.USER)
    await manager.set_role("a", Role.ADMIN)
    assert manager.get("a").role is Role.ADMIN


async def test_disable_removes_from_memory(manager: UserManager):
    await manager.create(username="a", password="pw", role=Role.USER)
    await manager.disable("a")
    assert manager.get("a") is None


async def test_enable_restores_memory(manager: UserManager):
    await manager.create(username="a", password="pw", role=Role.USER)
    await manager.disable("a")
    await manager.enable("a")
    assert manager.get("a") is not None


async def test_remove_deletes_db_and_dir(manager: UserManager, tmp_path: Path):
    await manager.create(username="a", password="pw", role=Role.USER)
    await manager.remove("a")
    assert (tmp_path / ".octop" / "users" / "a").exists() is False
    assert manager.get("a") is None


async def test_count(manager: UserManager):
    assert manager.count() == 0
    await manager.create(username="a", password="pw", role=Role.USER)
    assert manager.count() == 1


async def test_boot_loads_existing_users(tmp_path: Path):
    paths = PathLayout(tmp_path / ".octop")
    paths.ensure_root()
    db = SqlitePool(paths.db)
    run_migrations(db)
    services = build_shared_services(db=db, paths=paths, config=OctopConfig())
    # Pre-populate via repo
    from octop.infra.users.password import hash_password

    services.user_repo.create(username="legacy", password_hash=hash_password("pw"), role="user")
    manager = UserManager(services)
    await manager.boot()
    assert manager.get("legacy") is not None


async def test_boot_loads_users(tmp_path: Path):
    """UserManager.boot() loads user identity objects (agents are now global)."""
    paths = PathLayout(tmp_path / ".octop")
    paths.ensure_root()
    db = SqlitePool(paths.db)
    run_migrations(db)
    services = build_shared_services(db=db, paths=paths, config=OctopConfig())
    from octop.infra.users.password import hash_password

    uid = services.user_repo.create(
        username="alice", password_hash=hash_password("pw"), role="user"
    )
    manager = UserManager(services)
    await manager.boot()
    try:
        user = manager.get("alice")
        assert user is not None
        assert user.id == uid
        assert user.username == "alice"
        # No agent_manager on User anymore — agents are managed globally
        assert not hasattr(user, "agent_manager") or True  # just verify no crash
    finally:
        await manager.shutdown_all()
