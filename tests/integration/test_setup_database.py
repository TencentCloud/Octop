"""Setup wizard database step API tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.config import DatabaseConfig, OctopConfig, load_config
from octop.infra.db.factory import open_database
from octop.infra.db.migrate import run_migrations
from octop.infra.db.repos.users import UserRepo
from octop.infra.setup.password_file import read_password
from octop.infra.utils.paths import PathLayout
from tests.support.app import octop_client
from tests.support.auth import bootstrap_admin, wizard_token


def _seed_occupied_sqlite(home, *, relative_path: str = "occupied.db") -> None:
    """Create a sibling SQLite control-plane DB that already has one user."""
    paths = PathLayout(home)
    cfg = OctopConfig(
        database=DatabaseConfig(driver="sqlite", sqlite_path=relative_path),
        database_in_file=True,
    )
    db = open_database(cfg, paths)
    try:
        run_migrations(db)
        UserRepo(db).create(username="existing", password_hash="x", role="admin")
    finally:
        db.close()


@pytest.mark.asyncio
async def test_setup_database_sqlite_bind(patched_app_client) -> None:
    """Already-bound empty wizard can still swap sqlite path via rebind."""
    client, srv, home = patched_app_client
    r = await client.post(
        "/api/setup/test-database",
        json={"driver": "sqlite", "sqlite_path": "data/wizard.db"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True

    r = await client.post(
        "/api/setup/database",
        json={"driver": "sqlite", "sqlite_path": "data/wizard.db"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["driver"] == "sqlite"

    cfg = load_config(home / "config.json")
    assert cfg.database.sqlite_path == "data/wizard.db"
    assert (home / "data" / "wizard.db").is_file()

    status = await client.get("/api/setup/status")
    assert status.json()["database_driver"] == "sqlite"
    assert status.json()["database_bound"] is True

    # Runtime stores must use the live pool (not a closed previous sqlite).
    assert srv.app_runtime is not None
    list(srv.app_runtime.agent_registry.providers.iter_usable_rows())
    assert srv.services.db is srv.app_runtime.agent_registry._providers._provider_repo._db  # noqa: SLF001


@pytest.mark.asyncio
async def test_deferred_verify_password_then_bind(tmp_octop_home: Path) -> None:
    """Greenfield: password works with no pool; /setup/database binds once."""
    async with octop_client(tmp_octop_home, bind_database=False) as (client, srv):
        assert srv.database_bound is False
        assert not (tmp_octop_home / "octop.db").exists()

        status = await client.get("/api/setup/status")
        assert status.status_code == 200
        body = status.json()
        assert body["setup_required"] is True
        assert body["database_bound"] is False
        assert body["database_driver"] is None

        health = await client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["db"] is False

        pw = read_password(tmp_octop_home.parent)
        assert pw is not None
        verified = await client.post("/api/setup/verify-password", json={"password": pw})
        assert verified.status_code == 200, verified.text
        tok = verified.json()["wizard_token"]

        # Admin requires a bound DB.
        early = await client.post(
            "/api/setup/initial-admin",
            json={"username": "admin", "password": "pw"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert early.status_code == 503
        assert early.json()["error"]["code"] == "SETUP_REQUIRED"

        applied = await client.post(
            "/api/setup/database",
            json={"driver": "sqlite", "sqlite_path": "octop.db"},
        )
        assert applied.status_code == 200, applied.text
        assert srv.database_bound is True
        assert (tmp_octop_home / "octop.db").is_file()

        status2 = await client.get("/api/setup/status")
        assert status2.json()["database_bound"] is True
        assert status2.json()["database_driver"] == "sqlite"

        created = await client.post(
            "/api/setup/initial-admin",
            json={"username": "admin", "password": "pw"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert created.status_code == 201, created.text


@pytest.mark.asyncio
async def test_setup_database_refuses_nonempty_target(patched_app_client) -> None:
    """Greenfield setup must not rebind onto a control-plane DB that already has users."""
    client, srv, home = patched_app_client
    _seed_occupied_sqlite(home)
    before = load_config(home / "config.json")

    r = await client.post(
        "/api/setup/database",
        json={"driver": "sqlite", "sqlite_path": "occupied.db"},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "DATABASE_NOT_EMPTY"

    after = load_config(home / "config.json")
    assert after.database.sqlite_path == before.database.sqlite_path
    assert srv.user_manager.count() == 0

    tok = await wizard_token(client, home)
    created = await client.post(
        "/api/setup/initial-admin",
        json={"username": "admin", "password": "pw"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert created.status_code == 201, created.text


@pytest.mark.asyncio
async def test_setup_database_refused_after_admin(patched_app_client) -> None:
    client, _srv, home = patched_app_client
    await bootstrap_admin(client, home)
    r = await client.post(
        "/api/setup/database",
        json={"driver": "sqlite", "sqlite_path": "octop.db"},
    )
    assert r.status_code == 410
