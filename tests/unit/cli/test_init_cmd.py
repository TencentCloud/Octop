"""Unit tests for `octop init`."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from octop.cli.main import cli


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


def test_init_non_interactive_creates_admin(fake_home: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "init",
            "--admin-username",
            "alice",
            "--admin-password",
            "wonderland",
            "--yes",
        ],
    )
    assert result.exit_code == 0, result.output
    assert (fake_home / ".octop").is_dir()
    assert (fake_home / ".octop" / "octop.db").is_file()

    from octop.infra.db.pool import DBPool
    from octop.infra.db.repos.users import UserRepo
    from octop.infra.utils.paths import PathLayout

    paths = PathLayout(fake_home / ".octop")
    db = DBPool(paths.db)
    row = UserRepo(db).get_by_username("alice")
    assert row is not None
    assert row.role == "admin"


def test_init_refuses_to_overwrite_without_force(fake_home: Path) -> None:
    runner = CliRunner()
    args = ["init", "--admin-username", "alice", "--admin-password", "pw1234", "--yes"]
    r1 = runner.invoke(cli, args)
    assert r1.exit_code == 0
    r2 = runner.invoke(cli, args)
    assert r2.exit_code != 0
    out = (r2.output + (r2.stderr if hasattr(r2, "stderr") else "")).lower()
    assert "already" in out or "exists" in out


def test_init_force_resets(fake_home: Path) -> None:
    if os.name == "nt":
        pytest.skip("Windows may lock SQLite during init force reset")
    runner = CliRunner()
    args_a = ["init", "--admin-username", "alice", "--admin-password", "pw1234", "--yes"]
    args_b = [
        "init",
        "--force",
        "--admin-username",
        "bob",
        "--admin-password",
        "pw5678",
        "--yes",
    ]
    runner.invoke(cli, args_a)
    r2 = runner.invoke(cli, args_b)
    assert r2.exit_code == 0, r2.output

    from octop.infra.db.pool import DBPool
    from octop.infra.db.repos.users import UserRepo
    from octop.infra.utils.paths import PathLayout

    paths = PathLayout(fake_home / ".octop")
    repo = UserRepo(DBPool(paths.db))
    assert repo.get_by_username("bob") is not None


def test_init_password_too_short_rejects(fake_home: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["init", "--admin-username", "a", "--admin-password", "abc", "--yes"],
    )
    assert result.exit_code != 0
    assert "password" in result.output.lower()


def test_init_env_vars_supply_credentials(fake_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCTOP_ADMIN_USERNAME", "fromenv")
    monkeypatch.setenv("OCTOP_ADMIN_PASSWORD", "envpass1")
    runner = CliRunner()
    result = runner.invoke(cli, ["init", "--yes"])
    assert result.exit_code == 0, result.output

    from octop.infra.db.pool import DBPool
    from octop.infra.db.repos.users import UserRepo
    from octop.infra.utils.paths import PathLayout

    paths = PathLayout(fake_home / ".octop")
    repo = UserRepo(DBPool(paths.db))
    assert repo.get_by_username("fromenv") is not None
