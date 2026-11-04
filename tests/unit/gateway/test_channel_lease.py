"""Channel connection leases across two gateways sharing one database."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.config import OctopConfig
from octop.infra.agents.manager import AgentManager
from octop.infra.db.lease import LEASE_SECONDS
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.db.services import build_shared_services
from octop.infra.gateway.gateway import Gateway
from octop.infra.utils.paths import PathLayout


def _gateway(path: Path, instance_id: str) -> Gateway:
    db = SqlitePool(path)
    services = build_shared_services(db=db, paths=PathLayout(path.parent), config=OctopConfig())
    registry = AgentManager(repos=services.repos, paths=services.paths, config=services.config)
    gateway = Gateway(agent_manager=registry, repos=services.repos, instance_id=instance_id)
    gateway._channel_manager = MagicMock()
    gateway._channel_manager.add_channel = AsyncMock()
    gateway._channel_manager.remove_channel = AsyncMock()
    gateway._channel_manager.get_channel = MagicMock(return_value=MagicMock())
    gateway._processor = MagicMock()
    return gateway


@pytest.mark.asyncio
async def test_only_one_gateway_connects_and_generation_forces_reconnect(tmp_path: Path) -> None:
    path = tmp_path / "octop.db"
    db = SqlitePool(path)
    run_migrations(db)
    user_id = UserRepo(db).create(username="alice", password_hash="h", role="admin")
    AgentRepo(db).create(agent_id="agent-1", user_id=user_id, name="bot")
    from octop.infra.db.repos.channels import ChannelRepo

    ChannelRepo(db).create(
        channel_id="ch-1",
        agent_id="agent-1",
        user_id=user_id,
        kind="feishu",
        name="main",
        config_json='{"app_id":"x","app_secret":"y"}',
    )
    db.close()

    owner = _gateway(path, "owner")
    other = _gateway(path, "other")
    row = owner._repos.channel_repo.get("ch-1")
    assert row is not None

    await owner._safe_register_channel(row)
    await other._safe_register_channel(row)

    owner._channel_manager.add_channel.assert_awaited()  # type: ignore[attr-defined]
    other._channel_manager.add_channel.assert_not_awaited()  # type: ignore[attr-defined]
    status = other.get_runtime_status("ch-1")
    assert status is not None
    assert status.reason == "other_instance"
    rendered = other.runtime_status_to_dict("ch-1", locale="en")
    assert rendered is not None
    assert rendered["lease_owner"] == "owner"

    owner._repos.channel_repo.update("ch-1", config_json='{"app_id":"x","app_secret":"z"}')
    await owner.reconcile_channels()
    owner._channel_manager.remove_channel.assert_awaited()  # type: ignore[attr-defined]
    held = owner._repos.channel_repo.get("ch-1")
    assert held is not None
    assert held.runtime_lease_owner == "owner"
    assert held.runtime_generation == 1
    assert (
        other._repos.channel_repo.renew_runtime_lease(
            "ch-1",
            token="stale",
            generation=0,
            lease_seconds=LEASE_SECONDS,
        )
        is False
    )
