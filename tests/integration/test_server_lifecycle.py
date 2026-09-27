"""tests/integration/test_server_lifecycle.py"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from octop.infra.gateway.gateway import Gateway
from octop.infra.server import OctopServer
from tests.support.app import ensure_control_plane_bound


async def _bind_default_sqlite(srv: OctopServer) -> None:
    await ensure_control_plane_bound(srv)


@pytest.fixture
async def server(tmp_octop_home: Path):
    srv = OctopServer(home=tmp_octop_home)
    await srv.start()
    await _bind_default_sqlite(srv)
    yield srv
    await srv.stop()


async def test_start_defers_db_until_bind(tmp_octop_home: Path):
    srv = OctopServer(home=tmp_octop_home)
    await srv.start()
    try:
        assert tmp_octop_home.is_dir()
        assert (tmp_octop_home / "config.json").exists()
        assert not (tmp_octop_home / "octop.db").exists()
        assert srv.database_bound is False
        assert srv.services is None
        await _bind_default_sqlite(srv)
        assert (tmp_octop_home / "octop.db").exists()
        assert srv.database_bound is True
    finally:
        await srv.stop()


async def test_embedded_server_skips_im_channel_registration(tmp_octop_home: Path):
    boot = Gateway.boot
    registration_flags: list[bool] = []

    async def record_boot(gateway: Gateway, *, register_im_channels: bool = True) -> None:
        registration_flags.append(register_im_channels)
        await boot(gateway, register_im_channels=register_im_channels)

    srv = OctopServer(home=tmp_octop_home, register_im_channels=False)
    with patch.object(Gateway, "boot", record_boot):
        await srv.start()
        try:
            await _bind_default_sqlite(srv)
        finally:
            await srv.stop()

    assert registration_flags == [False]


async def test_start_creates_root_and_db(server: OctopServer, tmp_octop_home: Path):
    assert tmp_octop_home.is_dir()
    assert (tmp_octop_home / "octop.db").exists()
    assert (tmp_octop_home / "config.json").exists()


async def test_jwt_secret_seeded(server: OctopServer):
    assert server.services is not None
    secret = server.services.secret_repo.get("jwt")
    assert secret is not None
    assert len(secret) >= 32


async def test_user_manager_loaded(server: OctopServer):
    assert server.user_manager is not None
    assert server.user_manager.count() == 0


async def test_boot_then_stop_idempotent(tmp_octop_home: Path):
    srv = OctopServer(home=tmp_octop_home)
    await srv.start()
    await _bind_default_sqlite(srv)
    await srv.stop()
    await srv.stop()  # idempotent
