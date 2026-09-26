"""Tests for ``octop user passwd`` as the forgotten-password escape hatch."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner

from octop.cli.main import cli
from octop.config import OctopConfig
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import build_shared_services
from octop.infra.errors import OctopError
from octop.infra.users.manager import UserManager
from octop.infra.utils.paths import PathLayout

USERNAME = "alice"
OLD_PASSWORD = "TestPass12"
NEW_PASSWORD = "NewPass12"


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


@pytest.fixture
def manager(fake_home: Path) -> Iterator[UserManager]:
    """A ``UserManager`` over the database that ``octop init`` just created."""
    result = CliRunner().invoke(
        cli,
        ["init", "--admin-username", USERNAME, "--admin-password", OLD_PASSWORD, "--yes"],
    )
    assert result.exit_code == 0, result.output
    paths = PathLayout(fake_home / ".octop")
    db = SqlitePool(paths.db)
    try:
        services = build_shared_services(db=db, paths=paths, config=OctopConfig())
        yield UserManager(services)
    finally:
        db.close()


async def _lock_out(manager: UserManager) -> None:
    for _ in range(manager._login_max_attempts - 1):
        assert await manager.authenticate(USERNAME, "wrong") is None
    with pytest.raises(OctopError):
        await manager.authenticate(USERNAME, "wrong")


def _passwd() -> None:
    result = CliRunner().invoke(cli, ["user", "passwd", USERNAME, "--password", NEW_PASSWORD])
    assert result.exit_code == 0, result.output


async def test_passwd_clears_a_login_lockout(manager: UserManager) -> None:
    await _lock_out(manager)
    with pytest.raises(OctopError):
        await manager.authenticate(USERNAME, OLD_PASSWORD)

    _passwd()

    user = await manager.authenticate(USERNAME, NEW_PASSWORD)
    assert user is not None
    assert user.username == USERNAME


async def test_passwd_clears_the_failed_attempt_counter(manager: UserManager) -> None:
    await _lock_out(manager)
    _passwd()

    assert await manager.authenticate(USERNAME, "wrong") is None
