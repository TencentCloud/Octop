"""tests/unit/test_gateway.py"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from octop.config import OctopConfig
from octop.infra.agents.manager import AgentManager
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.db.services import build_shared_services
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.gateway import ChannelCreateSpec, Gateway
from octop.infra.utils.paths import PathLayout
from octop.infra.utils.ulid import new_ulid


def _make_services(tmp_path: Path):
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    return build_shared_services(db=db, paths=PathLayout(tmp_path), config=OctopConfig())


def _seed_agent(services, tmp_path: Path) -> tuple[str, int]:
    uid = UserRepo(services.db).create(username="alice", password_hash="h", role="admin")
    aid = new_ulid()
    AgentRepo(services.db).create(agent_id=aid, user_id=uid, name="bot")
    return aid, uid


@pytest.mark.asyncio
async def test_gateway_boot_and_shutdown(tmp_path: Path) -> None:
    services = _make_services(tmp_path)
    with patch("octop.infra.agents.manager.HarnessAgentManager") as mock_hm_cls:
        mock_hm_cls.return_value = MagicMock()

        registry = AgentManager(
            repos=services.repos,
            paths=services.paths,
            config=services.config,
        )
        await registry.boot()

        gw = Gateway(agent_manager=registry, repos=services.repos)
        await gw.boot()
        assert gw._channel_manager is not None
        assert gw._processor is not None

        await gw.shutdown()
        assert gw._channel_manager is None
        await registry.shutdown()


@pytest.mark.asyncio
async def test_create_channel_updates_existing_same_kind(tmp_path: Path) -> None:
    services = _make_services(tmp_path)
    agent_id, user_id = _seed_agent(services, tmp_path)
    registry = AgentManager(
        repos=services.repos,
        paths=services.paths,
        config=services.config,
    )
    gw = Gateway(agent_manager=registry, repos=services.repos)
    gw._channel_manager = MagicMock()
    gw._channel_manager.add_channel = AsyncMock()
    gw._channel_manager.remove_channel = AsyncMock()
    gw._channel_manager.get_channel = MagicMock(return_value=MagicMock())
    gw._processor = MagicMock()

    first_id = new_ulid()
    first = await gw.create_channel(
        ChannelCreateSpec(
            channel_id=first_id,
            agent_id=agent_id,
            user_id=user_id,
            kind="weixin",
            name="weixin",
            config={"token": "old"},
        )
    )
    second_id = new_ulid()
    second = await gw.create_channel(
        ChannelCreateSpec(
            channel_id=second_id,
            agent_id=agent_id,
            user_id=user_id,
            kind="weixin",
            name="weixin",
            config={"token": "new"},
        )
    )
    assert second.channel_id == first.channel_id
    assert json.loads(second.config_json)["token"] == "new"
    assert gw._repos.channel_repo.get(second_id) is None


@pytest.mark.asyncio
async def test_create_channel_rejects_name_taken_by_other_kind(tmp_path: Path) -> None:
    services = _make_services(tmp_path)
    agent_id, user_id = _seed_agent(services, tmp_path)
    registry = AgentManager(
        repos=services.repos,
        paths=services.paths,
        config=services.config,
    )
    gw = Gateway(agent_manager=registry, repos=services.repos)
    gw._channel_manager = MagicMock()
    gw._channel_manager.add_channel = AsyncMock()
    gw._channel_manager.remove_channel = AsyncMock()
    gw._channel_manager.get_channel = MagicMock(return_value=MagicMock())
    gw._processor = MagicMock()

    await gw.create_channel(
        ChannelCreateSpec(
            channel_id=new_ulid(),
            agent_id=agent_id,
            user_id=user_id,
            kind="feishu",
            name="shared",
            config={},
        )
    )
    with pytest.raises(OctopError) as exc:
        await gw.create_channel(
            ChannelCreateSpec(
                channel_id=new_ulid(),
                agent_id=agent_id,
                user_id=user_id,
                kind="weixin",
                name="shared",
                config={},
            )
        )
    assert exc.value.code is ErrorCode.CHANNEL_NAME_TAKEN
